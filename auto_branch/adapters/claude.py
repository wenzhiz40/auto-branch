from __future__ import annotations

import json
import uuid

from .base import AdapterCapabilities, AdapterError


class ClaudeAdapter:
    name = "claude"
    capabilities = AdapterCapabilities(
        fork_from_session=True,
        resume_by_id=True,
        pre_submit_interception=False,
        native_session_metadata=True,
    )

    def build_fork_command(self, session_id: str, prompt: str | None = None, *, headless: bool = True) -> list[str]:
        command = ["claude", "--resume", session_id, "--fork-session"]
        if headless:
            command.extend(["--print", "--output-format", "json"])
        elif prompt:
            command.append(prompt)
        return command

    def build_resume_command(self, session_id: str, prompt: str | None = None, *, headless: bool = True) -> list[str]:
        command = ["claude", "--resume", session_id]
        if headless:
            command.extend(["--print", "--output-format", "json"])
        elif prompt:
            command.append(prompt)
        return command

    def build_start_command(self, prompt: str | None = None, session_id: str | None = None) -> list[str]:
        session_id = session_id or str(uuid.uuid4())
        return [
            "claude",
            "--session-id",
            session_id,
            "--print",
            "--output-format",
            "json",
        ]

    def version_command(self) -> list[str]:
        return ["claude", "--version"]

    def parse_session_id(self, output: str) -> str:
        for line in output.splitlines():
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            session_id = _find_session_id(payload)
            if session_id:
                return session_id
        raise AdapterError("Claude output did not contain a session id")


def _find_session_id(value: object) -> str | None:
    if isinstance(value, dict):
        for key in ("session_id", "sessionId", "thread_id", "threadId"):
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate:
                return candidate
        for candidate in value.values():
            found = _find_session_id(candidate)
            if found:
                return found
    elif isinstance(value, list):
        for candidate in value:
            found = _find_session_id(candidate)
            if found:
                return found
    return None
