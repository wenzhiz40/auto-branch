from __future__ import annotations

import hashlib
from pathlib import Path

from .classifier import Classifier, HeuristicClassifier
from .decision import DecisionEngine, DecisionMode
from .memory import MemoryStore
from .models import Action, BranchStatus, Decision
from .storage import Storage


class AutoBranchService:
    def __init__(self, data_dir: Path, classifier: Classifier | None = None):
        self.data_dir = data_dir
        self.storage = Storage(data_dir)
        self.memory = MemoryStore(data_dir / "memory")
        self.classifier = classifier or HeuristicClassifier()
        self.decisions = DecisionEngine()

    def route(self, prompt: str, mode: DecisionMode = DecisionMode.SUGGEST) -> Decision:
        active = self.storage.get_branch(self.storage.active_branch_id())
        if active is None:
            raise RuntimeError("active branch record is missing")
        summary = active["summary"] or self.memory.read_branch_summary(active["id"])
        classification = self.classifier.classify(
            current_topic=active["topic"], current_summary=summary, prompt=prompt
        )
        decision = self.decisions.decide(classification, mode)
        self.storage.record_routing_event(
            branch_id=active["id"],
            relationship=classification.relationship.value,
            proposed_action=decision.action.value,
            confidence=classification.confidence,
            reason=classification.reason,
            prompt_digest=hashlib.sha256(prompt.encode()).hexdigest(),
        )
        return decision

    def create_branch(
        self,
        *,
        title: str,
        topic: str,
        platform: str,
        native_session_id: str | None = None,
        summary: str = "",
    ) -> dict:
        parent_id = self.storage.active_branch_id()
        branch = self.storage.create_branch(
            parent_id=parent_id,
            title=title,
            topic=topic,
            platform=platform,
            native_session_id=native_session_id,
            summary=summary,
        )
        if summary:
            self.memory.write_branch_summary(branch["id"], summary)
        return branch

    def switch(self, branch_id: str) -> None:
        self.storage.set_active_branch(branch_id)

    def set_topic(self, branch_id: str, topic: str) -> None:
        if not topic.strip():
            raise ValueError("topic cannot be empty")
        self.storage.update_branch_topic(branch_id, topic.strip())

    def set_summary(self, branch_id: str, summary: str) -> int:
        revision = self.storage.update_branch_summary(branch_id, summary)
        self.memory.write_branch_summary(branch_id, summary)
        return revision

    def bind_session(self, branch_id: str, platform: str, session_id: str) -> None:
        if platform not in {"codex", "claude"}:
            raise ValueError(f"unsupported platform: {platform}")
        self.storage.bind_native_session(branch_id, platform, session_id)

    def archive(self, branch_id: str) -> None:
        if branch_id == "mainline":
            raise ValueError("mainline cannot be archived")
        self.storage.set_branch_status(branch_id, BranchStatus.ARCHIVED)

    def adopt(self, branch_id: str, *, kind: str = "findings", rejoin: bool = False) -> tuple[str, bool]:
        source = self.storage.get_branch(branch_id)
        if source is None:
            raise ValueError(f"branch does not exist: {branch_id}")
        if branch_id == "mainline":
            raise ValueError("mainline cannot be adopted into itself")
        summary = source["summary"] or self.memory.read_branch_summary(branch_id, "(no summary recorded)")
        prior_active = self.storage.active_branch_id()
        new_active = "mainline" if rejoin else prior_active
        revision = int(source["summary_revision"])
        note = (
            f"## Adopted from {source['title']} ({branch_id})\n\n"
            f"- Source platform: `{source['platform']}`\n"
            f"- Source session: `{source['native_session_id'] or 'not recorded'}`\n"
            f"- Source summary revision: `{revision}`\n\n"
            f"{summary.strip()}\n"
        )
        memory_revision = self._mainline_revision()
        adoption_id, created = self.storage.record_adoption(
            source_branch_id=branch_id,
            source_revision=revision,
            target_branch_id="mainline",
            kind=kind,
            memory_revision=memory_revision,
            prior_active_branch_id=prior_active,
            new_active_branch_id=new_active,
        )
        # Persist the operation ID first. Retrying after a partial write uses the same marker.
        self.memory.append_mainline_note(adoption_id, note)
        if rejoin:
            self.storage.set_branch_status(branch_id, BranchStatus.REJOINED)
            self.storage.set_active_branch("mainline")
        else:
            self.storage.set_branch_status(branch_id, BranchStatus.ADOPTED)
        return adoption_id, created

    def _mainline_revision(self) -> int:
        return len(self.memory.mainline_path.read_text(encoding="utf-8").splitlines())
