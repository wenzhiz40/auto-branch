from __future__ import annotations

import json

from .base import AdapterCapabilities, AdapterError


class CodexAdapter:
    name = "codex"
    capabilities = AdapterCapabilities(
        fork_from_session=True,
        resume_by_id=True,
        pre_submit_interception=False,
        native_session_metadata=True,
    )

    def build_fork_command(self, session_id: str, prompt: str | None = None, *, headless: bool = True) -> list[str]:
        command = ["codex", "exec", "fork", session_id, "--skip-git-repo-check"] if headless else ["codex", "fork", session_id]
        if headless:
            command.append("--json")
        if prompt:
            command.append(prompt)
        return command

    def build_resume_command(self, session_id: str, prompt: str | None = None, *, headless: bool = True) -> list[str]:
        command = ["codex", "exec", "resume", session_id, "--skip-git-repo-check"] if headless else ["codex", "resume", session_id]
        if headless:
            command.append("--json")
        if prompt:
            command.append(prompt)
        return command

    def build_start_command(self, prompt: str, session_id: str | None = None) -> list[str]:
        return ["codex", "exec", "--skip-git-repo-check", "--json", prompt]

    def version_command(self) -> list[str]:
        return ["codex", "--version"]

    def parse_session_id(self, output: str) -> str:
        for line in output.splitlines():
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            session_id = _find_session_id(payload)
            if session_id:
                return session_id
        raise AdapterError("Codex output did not contain a thread/session id")


def _find_session_id(value: object) -> str | None:
    if isinstance(value, dict):
        for key in ("thread_id", "threadId", "session_id", "sessionId"):
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate:
                return candidate
        for key in ("thread", "result", "data", "params"):
            candidate = value.get(key)
            found = _find_session_id(candidate)
            if found:
                return found
    elif isinstance(value, list):
        for candidate in value:
            found = _find_session_id(candidate)
            if found:
                return found
    return None
