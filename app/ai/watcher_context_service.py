"""Watcher context service (E, FR05, T05): read & normalize the LATEST watcher
result into a context object for the prompt.

Decision (Cách A): read SQLite directly and REUSE the existing schema, rather than
maintaining a second source of truth (data/latest_result.json).

Because the chat server may run in a DIFFERENT process from the GUI, we cannot
share the GUI's sqlite connection. We open our OWN read-only connection
(mode=ro) — SQLite allows many concurrent readers, so this is safe.
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from app import config

logger = logging.getLogger("screen_watcher.ai.context")

# Keep the OCR slice small so the prompt stays cheap in tokens.
OCR_MAX_CHARS = 2000


@dataclass
class WatcherContext:
    has_data: bool = False
    screenshot_id: str | None = None
    owner_id: str = ""            # user id that captured this screenshot (for access control)
    target_app: str = ""
    window_title: str = ""
    captured_at: str = ""
    file_path: str = ""
    status: str = ""
    ocr_text: str = ""
    matched_rules: list[dict] = field(default_factory=list)
    notifications: list[dict] = field(default_factory=list)

    def to_dict(self, include_audit: bool = False) -> dict:
        """JSON-serializable view for the watcher HTTP endpoints (FR07 / audit).

        `execution_id` is an alias of `screenshot_id` — the spec (§10.1) refers to
        an execution id, which in this schema IS the screenshot row id.
        `include_audit=True` adds the artifact fields (file path + capture status).
        """
        data = {
            "has_data": self.has_data,
            "execution_id": self.screenshot_id,
            "screenshot_id": self.screenshot_id,
            "target_app": self.target_app,
            "window_title": self.window_title,
            "captured_at": self.captured_at,
            "ocr_text": self.ocr_text,
            "matched_rules": self.matched_rules,
            "notifications": self.notifications,
        }
        if include_audit:
            data["file_path"] = self.file_path
            data["status"] = self.status
        return data

    def to_prompt_block(self) -> str:
        """Render the context as a compact text block to embed in the prompt."""
        if not self.has_data:
            return "No watcher result is available yet (no screenshot has been captured)."
        lines = [
            f"Source app : {self.target_app}",
            f"Window     : {self.window_title}",
            f"Captured at: {self.captured_at}",
        ]
        if self.matched_rules:
            names = ", ".join(f"{r['rule_name']} [{r['severity']}]" for r in self.matched_rules)
            lines.append(f"Matched rules: {names}")
        else:
            lines.append("Matched rules: (none)")
        if self.notifications:
            notes = ", ".join(f"{n['rule_id']}={n['status']}" for n in self.notifications)
            lines.append(f"Email decisions: {notes}")
        lines.append("OCR text:")
        lines.append(self.ocr_text or "(empty)")
        return "\n".join(lines)


class WatcherContextService:
    def __init__(self, db_path: Path | None = None):
        self.db_path = Path(db_path or config.DB_PATH)

    def _connect_ro(self) -> sqlite3.Connection:
        # Read-only URI connection: never mutates, safe alongside the GUI writer.
        uri = f"file:{self.db_path}?mode=ro"
        conn = sqlite3.connect(uri, uri=True, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    # Columns pulled from `screenshots` for every context build.
    _SHOT_COLS = "id, user_id, target_app, window_title, captured_at, file_path, status"

    def latest(self, user_id: str | None = None) -> WatcherContext:
        """Return the most recent SUCCESSFUL screenshot + its OCR/rule/email data.

        user_id=None -> latest of ANY user (admin view). Otherwise scope to the
        screenshots captured by that user only.
        """
        if not self.db_path.exists():
            logger.info("DB not found at %s — returning empty context.", self.db_path)
            return WatcherContext()

        conn = self._connect_ro()
        try:
            sql = (f"SELECT {self._SHOT_COLS} FROM screenshots "
                   "WHERE status = 'success' AND deleted_at IS NULL ")
            params: tuple = ()
            if user_id is not None:
                sql += "AND user_id = ? "
                params = (user_id,)
            sql += "ORDER BY id DESC LIMIT 1"
            shot = conn.execute(sql, params).fetchone()
            if shot is None:
                return WatcherContext()
            return self._build(conn, shot)
        finally:
            conn.close()

    def get(self, screenshot_id: str) -> WatcherContext:
        """Return the context for ONE specific execution id (= screenshot id).

        Used by GET /watcher/audit/{execution_id}. Unlike latest(), this does NOT
        filter by status — an audit may legitimately look up a failed capture.
        Returns an empty context (has_data=False) when the id does not exist.
        """
        if not self.db_path.exists():
            return WatcherContext()

        conn = self._connect_ro()
        try:
            shot = conn.execute(
                f"SELECT {self._SHOT_COLS} FROM screenshots "
                "WHERE id = ? AND deleted_at IS NULL",
                (screenshot_id,),
            ).fetchone()
            if shot is None:
                return WatcherContext()
            return self._build(conn, shot)
        finally:
            conn.close()

    def _build(self, conn: sqlite3.Connection, shot: sqlite3.Row) -> WatcherContext:
        """Assemble a WatcherContext from a screenshot row + its related rows."""
        sid = shot["id"]
        ocr = conn.execute(
            "SELECT text FROM ocr_results WHERE screenshot_id = ? "
            "ORDER BY id DESC LIMIT 1",
            (sid,),
        ).fetchone()
        ocr_text = (ocr["text"] if ocr and ocr["text"] else "").strip()
        if len(ocr_text) > OCR_MAX_CHARS:
            ocr_text = ocr_text[:OCR_MAX_CHARS] + "\n...(truncated)"

        rule_rows = conn.execute(
            "SELECT rule_id, rule_name, severity, owner_group, reason "
            "FROM rule_evaluations WHERE screenshot_id = ? AND matched = 1 "
            "ORDER BY id",
            (sid,),
        ).fetchall()
        notif_rows = conn.execute(
            "SELECT rule_id, status, owner_group, reason, recipients "
            "FROM notifications WHERE screenshot_id = ? ORDER BY id",
            (sid,),
        ).fetchall()

        return WatcherContext(
            has_data=True,
            screenshot_id=sid,
            owner_id=shot["user_id"] or "",
            target_app=shot["target_app"] or "",
            window_title=shot["window_title"] or "",
            captured_at=shot["captured_at"] or "",
            file_path=shot["file_path"] or "",
            status=shot["status"] or "",
            ocr_text=ocr_text,
            matched_rules=[dict(r) for r in rule_rows],
            notifications=[dict(r) for r in notif_rows],
        )
