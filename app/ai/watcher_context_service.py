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
    screenshot_id: int | None = None
    target_app: str = ""
    window_title: str = ""
    captured_at: str = ""
    ocr_text: str = ""
    matched_rules: list[dict] = field(default_factory=list)
    notifications: list[dict] = field(default_factory=list)

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

    def latest(self) -> WatcherContext:
        """Return the most recent successful screenshot + its OCR/rule/email data."""
        if not self.db_path.exists():
            logger.info("DB not found at %s — returning empty context.", self.db_path)
            return WatcherContext()

        conn = self._connect_ro()
        try:
            shot = conn.execute(
                "SELECT id, target_app, window_title, captured_at "
                "FROM screenshots WHERE status = 'success' "
                "ORDER BY id DESC LIMIT 1"
            ).fetchone()
            if shot is None:
                return WatcherContext()

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
                "SELECT rule_id, status, owner_group FROM notifications "
                "WHERE screenshot_id = ? ORDER BY id",
                (sid,),
            ).fetchall()

            return WatcherContext(
                has_data=True,
                screenshot_id=sid,
                target_app=shot["target_app"] or "",
                window_title=shot["window_title"] or "",
                captured_at=shot["captured_at"] or "",
                ocr_text=ocr_text,
                matched_rules=[dict(r) for r in rule_rows],
                notifications=[dict(r) for r in notif_rows],
            )
        finally:
            conn.close()
