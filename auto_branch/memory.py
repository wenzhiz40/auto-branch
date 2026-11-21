from __future__ import annotations

from pathlib import Path


class MemoryStore:
    MAX_CONTEXT_SUMMARY_CHARS = 12000

    def __init__(self, root: Path):
        self.root = root
        self.branches_dir = root / "branches"
        self.branches_dir.mkdir(parents=True, exist_ok=True)
        self.global_path = root / "global.md"
        self.mainline_path = root / "mainline.md"
        if not self.global_path.exists():
            self.global_path.write_text("# Global Memory\n\n", encoding="utf-8")
        if not self.mainline_path.exists():
            self.mainline_path.write_text("# Mainline Memory\n\n", encoding="utf-8")

    def branch_path(self, branch_id: str) -> Path:
        return self.branches_dir / f"{branch_id}.md"

    def write_branch_summary(self, branch_id: str, content: str) -> None:
        self.branch_path(branch_id).write_text(content.rstrip() + "\n", encoding="utf-8")

    def read_branch_summary(self, branch_id: str, fallback: str = "") -> str:
        path = self.branch_path(branch_id)
        return path.read_text(encoding="utf-8") if path.exists() else fallback

    def append_mainline_note(self, adoption_id: str, note: str) -> bool:
        marker = f"<!-- auto-branch:{adoption_id} -->"
        current = self.mainline_path.read_text(encoding="utf-8")
        if marker in current:
            return False
        block = f"\n{marker}\n{note.rstrip()}\n"
        self.mainline_path.write_text(current.rstrip() + "\n" + block, encoding="utf-8")
        return True

    def context_package(self, *, original_goal: str, current_topic: str, summary: str, prompt: str) -> str:
        summary = summary.strip()
        if len(summary) > self.MAX_CONTEXT_SUMMARY_CHARS:
            summary = summary[: self.MAX_CONTEXT_SUMMARY_CHARS].rstrip() + "\n[Summary truncated by Auto-Branch context budget.]"
        return (
            "# Branch Context\n\n"
            f"## Original Goal\n{original_goal.strip()}\n\n"
            f"## Current Subtopic\n{current_topic.strip()}\n\n"
            f"## Relevant Background\n{summary or '(none recorded)'}\n\n"
            f"## Current Question\n{prompt.strip()}\n\n"
            "Answer the current question using the relevant background. Do not repeat the background unless needed.\n"
        )
