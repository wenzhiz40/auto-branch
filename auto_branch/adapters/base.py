from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class AdapterError(RuntimeError):
    pass


@dataclass(frozen=True)
class AdapterCapabilities:
    fork_from_session: bool
    resume_by_id: bool
    pre_submit_interception: bool
    native_session_metadata: bool


class SessionAdapter(Protocol):
    name: str
    capabilities: AdapterCapabilities

    def build_fork_command(self, session_id: str, prompt: str | None = None, *, headless: bool = True) -> list[str]: ...

    def build_resume_command(self, session_id: str, prompt: str | None = None, *, headless: bool = True) -> list[str]: ...

    def build_start_command(self, prompt: str, session_id: str | None = None) -> list[str]: ...

    def version_command(self) -> list[str]: ...

    def parse_session_id(self, output: str) -> str: ...
