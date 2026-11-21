from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from typing import Callable, Protocol

from .adapters import ClaudeAdapter, CodexAdapter
from .adapters.base import AdapterError, SessionAdapter
from .decision import DecisionMode
from .models import Action
from .service import AutoBranchService


class CompletedProcess(Protocol):
    args: object
    returncode: int
    stdout: str
    stderr: str


Runner = Callable[[list[str]], CompletedProcess]
Confirmer = Callable[[str], str]


@dataclass(frozen=True)
class PromptResult:
    action: str
    branch_id: str
    session_id: str
    returncode: int
    stdout: str
    stderr: str
    branch_mode: str = "native"


def _default_runner(command: list[str]) -> CompletedProcess:
    return subprocess.run(command, text=True, capture_output=True, check=False)


def _confirm(prompt: str) -> str:
    return input(prompt)


class PromptRunner:
    def __init__(
        self,
        service: AutoBranchService,
        *,
        runner: Runner = _default_runner,
        confirmer: Confirmer = _confirm,
    ):
        self.service = service
        self.runner = runner
        self.confirmer = confirmer

    def run(
        self,
        *,
        platform: str,
        prompt: str,
        mode: DecisionMode = DecisionMode.SUGGEST,
        confirm: bool = False,
        branch_mode: str = "native",
    ) -> PromptResult:
        if branch_mode not in {"native", "seeded"}:
            raise ValueError("branch_mode must be native or seeded")
        adapter: SessionAdapter = self._adapter(platform)
        active_id = self.service.storage.active_branch_id()
        active = self.service.storage.get_branch(active_id)
        if active is None:
            raise RuntimeError(f"active branch does not exist: {active_id}")
        if active["platform"] not in {"logical", platform}:
            raise RuntimeError(
                f"active branch uses platform {active['platform']}; switch to a {platform} branch first"
            )

        if not active["native_session_id"]:
            command = adapter.build_start_command(prompt)
            process = self.runner(command)
            session_id = self._parse_id(adapter, process)
            self.service.storage.bind_native_session(active_id, platform, session_id)
            return PromptResult("start", active_id, session_id, process.returncode, process.stdout, process.stderr, "native")

        decision = self.service.route(prompt, mode)
        branch = active
        action = "resume"
        if decision.action == Action.SUGGEST_BRANCH:
            print(
                f"Suggested branch: {decision.classification.new_topic}\n"
                f"Reason: {decision.classification.reason}"
            )
            if mode == DecisionMode.AUTO:
                confirm = True
            if not confirm:
                if not sys.stdin.isatty():
                    raise RuntimeError("branch confirmation requires a TTY; use --confirm to accept explicitly")
                answer = self.confirmer("Fork into a new session? [y/N] ").strip().lower()
                confirm = answer in {"y", "yes"}
            if confirm:
                action = "fork"
            else:
                self.service.storage.record_routing_event(
                    branch_id=active_id,
                    relationship=decision.classification.relationship.value,
                    proposed_action=decision.action.value,
                    confidence=decision.classification.confidence,
                    reason=decision.classification.reason,
                    user_choice="continue",
                )
        elif decision.action == Action.ASK:
            if not confirm:
                if not sys.stdin.isatty():
                    raise RuntimeError("uncertain route requires a TTY; pass --confirm to continue in the active session")
                answer = self.confirmer("Relationship is uncertain. Continue in this session? [Y/n] ").strip().lower()
                if answer in {"n", "no"}:
                    raise RuntimeError("cancelled without sending the prompt")
            action = "resume"

        if action == "fork" and branch_mode == "seeded":
            context = self.service.memory.context_package(
                original_goal=self.service.storage.get_branch("mainline")["topic"],
                current_topic=decision.classification.new_topic,
                summary=active["summary"],
                prompt=prompt,
            )
            command = adapter.build_start_command(context)
            action = "start_seeded"
        elif action == "fork":
            command = adapter.build_fork_command(active["native_session_id"], prompt)
        else:
            command = adapter.build_resume_command(active["native_session_id"], prompt)

        # A process is invoked once only. Never retry a prompt after an ambiguous transport failure.
        process = self.runner(command)
        session_id = self._parse_id(adapter, process)
        if action in {"fork", "start_seeded"}:
            branch = self.service.create_branch(
                title=decision.classification.new_topic[:80] or "New topic",
                topic=decision.classification.new_topic[:120] or "New topic",
                platform=platform,
                native_session_id=session_id,
                summary=self.service.memory.context_package(
                    original_goal=self.service.storage.get_branch("mainline")["topic"],
                    current_topic=decision.classification.new_topic,
                    summary=active["summary"],
                    prompt=prompt,
                ),
            )
            self.service.switch(branch["id"])
        elif action == "resume" and session_id != active["native_session_id"]:
            raise AdapterError("resume returned a different session id; refusing to change the active branch")

        return PromptResult(action, branch["id"], session_id, process.returncode, process.stdout, process.stderr, branch_mode)

    @staticmethod
    def _parse_id(adapter: SessionAdapter, process: CompletedProcess) -> str:
        if not process.stdout.strip():
            detail = process.stderr.strip() or f"exit code {process.returncode}"
            raise AdapterError(
                "native CLI returned no structured session output; prompt delivery may be ambiguous, "
                f"do not retry automatically: {detail}"
            )
        try:
            session_id = adapter.parse_session_id(process.stdout)
        except AdapterError as exc:
            detail = process.stderr.strip() or str(exc)
            raise AdapterError(
                "native CLI output did not identify the session; prompt delivery may be ambiguous, "
                f"do not retry automatically: {detail}"
            ) from exc
        return session_id

    @staticmethod
    def _adapter(platform: str) -> SessionAdapter:
        if platform == "codex":
            return CodexAdapter()
        if platform == "claude":
            return ClaudeAdapter()
        raise ValueError(f"unsupported platform: {platform}")
