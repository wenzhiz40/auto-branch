from __future__ import annotations

import json
import fcntl
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import BranchStatus


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class Storage:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.db_path = self.root / "auto_branch.sqlite3"
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    @contextmanager
    def prompt_lock(self):
        lock_path = self.root / "prompt.lock"
        with lock_path.open("w", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def _initialize(self) -> None:
        with self._connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS branches (
                    id TEXT PRIMARY KEY,
                    parent_id TEXT REFERENCES branches(id),
                    title TEXT NOT NULL,
                    topic TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    native_session_id TEXT,
                    status TEXT NOT NULL,
                    summary TEXT NOT NULL DEFAULT '',
                    summary_revision INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS routing_events (
                    operation_id TEXT PRIMARY KEY,
                    branch_id TEXT NOT NULL REFERENCES branches(id),
                    relationship TEXT NOT NULL,
                    proposed_action TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    reason TEXT NOT NULL,
                    user_choice TEXT,
                    adapter_result TEXT,
                    prompt_digest TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS adoptions (
                    id TEXT PRIMARY KEY,
                    source_branch_id TEXT NOT NULL REFERENCES branches(id),
                    source_revision INTEGER NOT NULL,
                    target_branch_id TEXT NOT NULL REFERENCES branches(id),
                    kind TEXT NOT NULL,
                    memory_revision INTEGER NOT NULL,
                    prior_active_branch_id TEXT,
                    new_active_branch_id TEXT,
                    created_at TEXT NOT NULL,
                    UNIQUE(source_branch_id, source_revision, target_branch_id, kind)
                );
                """
            )
            row = db.execute("SELECT id FROM branches WHERE id = 'mainline'").fetchone()
            if row is None:
                now = utc_now()
                db.execute(
                    """
                    INSERT INTO branches
                    (id, parent_id, title, topic, platform, status, created_at, updated_at)
                    VALUES ('mainline', NULL, 'Mainline', 'Mainline', 'logical', ?, ?, ?)
                    """,
                    (BranchStatus.ACTIVE.value, now, now),
                )
            db.execute(
                "INSERT OR IGNORE INTO settings(key, value) VALUES ('active_branch_id', 'mainline')"
            )

    def get_setting(self, key: str) -> str | None:
        with self._connect() as db:
            row = db.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
            return row["value"] if row else None

    def set_setting(self, key: str, value: str) -> None:
        with self._connect() as db:
            db.execute(
                "INSERT INTO settings(key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )

    def active_branch_id(self) -> str:
        return self.get_setting("active_branch_id") or "mainline"

    def get_branch(self, branch_id: str) -> dict[str, Any] | None:
        with self._connect() as db:
            row = db.execute("SELECT * FROM branches WHERE id = ?", (branch_id,)).fetchone()
            return dict(row) if row else None

    def list_branches(self, include_archived: bool = False) -> list[dict[str, Any]]:
        query = "SELECT * FROM branches"
        args: tuple[Any, ...] = ()
        if not include_archived:
            query += " WHERE status != ?"
            args = (BranchStatus.ARCHIVED.value,)
        query += " ORDER BY created_at"
        with self._connect() as db:
            return [dict(row) for row in db.execute(query, args).fetchall()]

    def create_branch(
        self,
        *,
        parent_id: str,
        title: str,
        topic: str,
        platform: str,
        native_session_id: str | None = None,
        branch_id: str | None = None,
        summary: str = "",
        status: BranchStatus = BranchStatus.ACTIVE,
    ) -> dict[str, Any]:
        if self.get_branch(parent_id) is None:
            raise ValueError(f"parent branch does not exist: {parent_id}")
        branch_id = branch_id or new_id("branch")
        now = utc_now()
        with self._connect() as db:
            db.execute(
                """
                INSERT INTO branches
                (id, parent_id, title, topic, platform, native_session_id, status, summary, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    branch_id,
                    parent_id,
                    title,
                    topic,
                    platform,
                    native_session_id,
                    status.value,
                    summary,
                    now,
                    now,
                ),
            )
        return self.get_branch(branch_id)  # type: ignore[return-value]

    def update_branch_summary(self, branch_id: str, summary: str) -> int:
        now = utc_now()
        with self._connect() as db:
            row = db.execute(
                "SELECT summary_revision FROM branches WHERE id = ?", (branch_id,)
            ).fetchone()
            if row is None:
                raise ValueError(f"branch does not exist: {branch_id}")
            revision = int(row["summary_revision"]) + 1
            db.execute(
                "UPDATE branches SET summary = ?, summary_revision = ?, updated_at = ? WHERE id = ?",
                (summary, revision, now, branch_id),
            )
        return revision

    def update_branch_topic(self, branch_id: str, topic: str) -> None:
        with self._connect() as db:
            result = db.execute(
                "UPDATE branches SET topic = ?, title = CASE WHEN id = 'mainline' THEN ? ELSE title END, updated_at = ? WHERE id = ?",
                (topic, topic, utc_now(), branch_id),
            )
            if result.rowcount != 1:
                raise ValueError(f"branch does not exist: {branch_id}")

    def bind_native_session(
        self,
        branch_id: str,
        platform: str,
        session_id: str,
        status: BranchStatus | None = None,
    ) -> None:
        if not session_id.strip():
            raise ValueError("session id cannot be empty")
        with self._connect() as db:
            if status is None:
                result = db.execute(
                    "UPDATE branches SET platform = ?, native_session_id = ?, updated_at = ? WHERE id = ?",
                    (platform, session_id, utc_now(), branch_id),
                )
            else:
                result = db.execute(
                    "UPDATE branches SET platform = ?, native_session_id = ?, status = ?, updated_at = ? WHERE id = ?",
                    (platform, session_id, status.value, utc_now(), branch_id),
                )
            if result.rowcount != 1:
                raise ValueError(f"branch does not exist: {branch_id}")

    def set_branch_status(self, branch_id: str, status: BranchStatus) -> None:
        with self._connect() as db:
            result = db.execute(
                "UPDATE branches SET status = ?, updated_at = ? WHERE id = ?",
                (status.value, utc_now(), branch_id),
            )
            if result.rowcount != 1:
                raise ValueError(f"branch does not exist: {branch_id}")

    def set_active_branch(self, branch_id: str) -> None:
        branch = self.get_branch(branch_id)
        if branch is None:
            raise ValueError(f"branch does not exist: {branch_id}")
        if branch["status"] == BranchStatus.ARCHIVED.value:
            raise ValueError("cannot switch to an archived branch")
        self.set_setting("active_branch_id", branch_id)

    def record_routing_event(
        self,
        *,
        branch_id: str,
        relationship: str,
        proposed_action: str,
        confidence: float,
        reason: str,
        user_choice: str | None = None,
        adapter_result: dict[str, Any] | None = None,
        prompt_digest: str | None = None,
        operation_id: str | None = None,
    ) -> str:
        operation_id = operation_id or new_id("route")
        with self._connect() as db:
            db.execute(
                """
                INSERT OR IGNORE INTO routing_events
                (operation_id, branch_id, relationship, proposed_action, confidence, reason,
                 user_choice, adapter_result, prompt_digest, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    operation_id,
                    branch_id,
                    relationship,
                    proposed_action,
                    confidence,
                    reason,
                    user_choice,
                    json.dumps(adapter_result) if adapter_result else None,
                    prompt_digest,
                    utc_now(),
                ),
            )
        return operation_id

    def update_routing_event(
        self,
        operation_id: str,
        *,
        user_choice: str | None = None,
        adapter_result: dict[str, Any] | None = None,
    ) -> None:
        with self._connect() as db:
            result = db.execute(
                """
                UPDATE routing_events
                SET user_choice = COALESCE(?, user_choice),
                    adapter_result = COALESCE(?, adapter_result)
                WHERE operation_id = ?
                """,
                (
                    user_choice,
                    json.dumps(adapter_result) if adapter_result is not None else None,
                    operation_id,
                ),
            )
            if result.rowcount != 1:
                raise ValueError(f"routing event does not exist: {operation_id}")

    def record_adoption(
        self,
        *,
        source_branch_id: str,
        source_revision: int,
        target_branch_id: str,
        kind: str,
        memory_revision: int,
        prior_active_branch_id: str | None,
        new_active_branch_id: str | None,
    ) -> tuple[str, bool]:
        adoption_id = new_id("adopt")
        with self._connect() as db:
            existing = db.execute(
                """
                SELECT id FROM adoptions
                WHERE source_branch_id = ? AND source_revision = ?
                  AND target_branch_id = ? AND kind = ?
                """,
                (source_branch_id, source_revision, target_branch_id, kind),
            ).fetchone()
            if existing:
                return existing["id"], False
            db.execute(
                """
                INSERT INTO adoptions
                (id, source_branch_id, source_revision, target_branch_id, kind, memory_revision,
                 prior_active_branch_id, new_active_branch_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    adoption_id,
                    source_branch_id,
                    source_revision,
                    target_branch_id,
                    kind,
                    memory_revision,
                    prior_active_branch_id,
                    new_active_branch_id,
                    utc_now(),
                ),
            )
        return adoption_id, True
