"""Repository: CRUD for user/role/permission, screenshot and OCR."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any

from app.db.database import Database
from app.db.ids import uuid7


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class Repository:
    def __init__(self, db: Database):
        self.db = db

    # ---------- helpers ----------
    def _exec(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        with self.db.lock:
            cur = self.db.conn.execute(sql, params)
            self.db.conn.commit()
            return cur

    def _query(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        with self.db.lock:
            return self.db.conn.execute(sql, params).fetchall()

    def _query_one(self, sql: str, params: tuple = ()) -> sqlite3.Row | None:
        with self.db.lock:
            return self.db.conn.execute(sql, params).fetchone()

    # ---------- roles & permissions ----------
    def list_roles(self) -> list[sqlite3.Row]:
        return self._query("SELECT * FROM roles ORDER BY name")

    def get_role_by_name(self, name: str) -> sqlite3.Row | None:
        return self._query_one("SELECT * FROM roles WHERE name = ?", (name,))

    def get_permissions_for_role(self, role_id: int) -> list[str]:
        rows = self._query(
            "SELECT p.code FROM permissions p "
            "JOIN role_permissions rp ON rp.permission_id = p.id "
            "WHERE rp.role_id = ?",
            (role_id,),
        )
        return [r["code"] for r in rows]

    # ---------- users ----------
    def get_user_by_username(self, username: str) -> sqlite3.Row | None:
        return self._query_one("SELECT * FROM users WHERE username = ?", (username,))

    def get_user(self, user_id: int) -> sqlite3.Row | None:
        return self._query_one("SELECT * FROM users WHERE id = ?", (user_id,))

    def list_users(self, include_deleted: bool = False) -> list[sqlite3.Row]:
        sql = (
            "SELECT u.*, r.name AS role_name FROM users u "
            "LEFT JOIN roles r ON r.id = u.role_id "
        )
        if not include_deleted:
            sql += "WHERE u.deleted_at IS NULL "
        sql += "ORDER BY u.username"
        return self._query(sql)

    # Profile columns an API caller is allowed to set/update.
    PROFILE_FIELDS = ("full_name", "email", "first_name", "last_name", "phone")

    def create_user(self, username: str, password_hash: str, salt: str,
                    full_name: str, role_id: int,
                    must_change_password: bool = True,
                    email: str | None = None, first_name: str | None = None,
                    last_name: str | None = None, phone: str | None = None) -> str:
        """Create a user with a fresh UUIDv7 primary key. Returns the new id (str)."""
        user_id = uuid7()
        self._exec(
            "INSERT INTO users(id, username, password_hash, salt, full_name, email, "
            "first_name, last_name, phone, role_id, is_active, must_change_password, "
            "created_at) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)",
            (user_id, username, password_hash, salt, full_name, email, first_name,
             last_name, phone, role_id, 1 if must_change_password else 0, _now()),
        )
        return user_id

    def update_user_role(self, user_id: int, role_id: int) -> None:
        self._exec("UPDATE users SET role_id = ? WHERE id = ?", (role_id, user_id))

    def update_user_full_name(self, user_id: int, full_name: str) -> None:
        self._exec("UPDATE users SET full_name = ? WHERE id = ?", (full_name, user_id))

    def update_user_username(self, user_id: int, username: str) -> None:
        self._exec("UPDATE users SET username = ? WHERE id = ?", (username, user_id))

    def update_user_profile(self, user_id: int, fields: dict) -> None:
        """Update only the provided profile columns (full_name/email/first_name/
        last_name/phone). Unknown keys are ignored. No-op if nothing to set."""
        cols = {k: v for k, v in fields.items() if k in self.PROFILE_FIELDS}
        if not cols:
            return
        assignments = ", ".join(f"{c} = ?" for c in cols)
        params = tuple(cols.values()) + (user_id,)
        self._exec(f"UPDATE users SET {assignments} WHERE id = ?", params)

    def soft_delete_user(self, user_id: int) -> int:
        """Mark a user as deleted WITHOUT removing the row (keeps FK integrity with
        their screenshots/audit rows). Also deactivates so they cannot sign in.
        Returns rows affected (0 = not found or already deleted)."""
        cur = self._exec(
            "UPDATE users SET deleted_at = ?, is_active = 0 "
            "WHERE id = ? AND deleted_at IS NULL",
            (_now(), user_id),
        )
        return cur.rowcount

    def update_user_password(self, user_id: int, password_hash: str, salt: str,
                             must_change_password: bool = False) -> None:
        """Set a new password. Clears the must-change flag by default (the user just
        set it), or sets it when an admin resets someone else's password."""
        self._exec(
            "UPDATE users SET password_hash = ?, salt = ?, must_change_password = ? "
            "WHERE id = ?",
            (password_hash, salt, 1 if must_change_password else 0, user_id),
        )

    def set_user_active(self, user_id: int, active: bool) -> None:
        self._exec("UPDATE users SET is_active = ? WHERE id = ?", (1 if active else 0, user_id))

    def delete_user(self, user_id: int) -> None:
        self._exec("DELETE FROM users WHERE id = ?", (user_id,))

    # ---------- capture sessions ----------
    def create_session(self, user_id: str, targets: str, note: str = "") -> str:
        session_id = uuid7()
        self._exec(
            "INSERT INTO capture_sessions(id, user_id, targets, note, created_at) "
            "VALUES(?, ?, ?, ?, ?)",
            (session_id, user_id, targets, note, _now()),
        )
        return session_id

    # ---------- screenshots ----------
    def create_screenshot(self, session_id: str | None, user_id: str, target_app: str,
                          window_title: str | None, file_path: str | None,
                          width: int | None, height: int | None,
                          status: str, error: str | None = None) -> str:
        screenshot_id = uuid7()
        self._exec(
            "INSERT INTO screenshots(id, session_id, user_id, target_app, window_title, "
            "file_path, width, height, status, error, captured_at) "
            "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (screenshot_id, session_id, user_id, target_app, window_title, file_path,
             width, height, status, error, _now()),
        )
        return screenshot_id

    def list_screenshots(self, user_id: int | None = None) -> list[sqlite3.Row]:
        """user_id=None -> all (requires the view_all permission); otherwise filter by user."""
        sql = (
            "SELECT s.*, u.username, o.char_count, o.id AS ocr_id "
            "FROM screenshots s "
            "LEFT JOIN users u ON u.id = s.user_id "
            "LEFT JOIN ocr_results o ON o.screenshot_id = s.id "
        )
        params: tuple = ()
        if user_id is not None:
            sql += "WHERE s.user_id = ? "
            params = (user_id,)
        sql += "ORDER BY s.id DESC"
        return self._query(sql, params)

    def get_screenshot(self, screenshot_id: int) -> sqlite3.Row | None:
        return self._query_one("SELECT * FROM screenshots WHERE id = ?", (screenshot_id,))

    def soft_delete_screenshot(self, screenshot_id: int) -> int:
        """Mark a screenshot (watcher execution) as deleted WITHOUT removing the row.
        Returns the number of rows affected (0 = not found or already deleted)."""
        cur = self._exec(
            "UPDATE screenshots SET deleted_at = ? WHERE id = ? AND deleted_at IS NULL",
            (_now(), screenshot_id),
        )
        return cur.rowcount

    # ---------- OCR ----------
    def create_ocr(self, screenshot_id: str, model: str, text: str,
                   char_count: int, duration_ms: int) -> str:
        ocr_id = uuid7()
        self._exec(
            "INSERT INTO ocr_results(id, screenshot_id, model, text, char_count, "
            "duration_ms, created_at) VALUES(?, ?, ?, ?, ?, ?, ?)",
            (ocr_id, screenshot_id, model, text, char_count, duration_ms, _now()),
        )
        return ocr_id

    def get_ocr_for_screenshot(self, screenshot_id: int) -> sqlite3.Row | None:
        return self._query_one(
            "SELECT * FROM ocr_results WHERE screenshot_id = ? ORDER BY id DESC LIMIT 1",
            (screenshot_id,),
        )

    # ---------- audit ----------
    def add_audit(self, user_id: str | None, action: str, detail: str = "") -> None:
        self._exec(
            "INSERT INTO audit_logs(id, user_id, action, detail, created_at) "
            "VALUES(?, ?, ?, ?, ?)",
            (uuid7(), user_id, action, detail, _now()),
        )

    # ---------- rule evaluations ----------
    def create_rule_evaluation(self, screenshot_id: str, rule_id: str, rule_name: str,
                               rule_type: str, matched: int, severity: str,
                               owner_group: str, reason: str, matched_terms: str) -> str:
        eval_id = uuid7()
        self._exec(
            "INSERT INTO rule_evaluations(id, screenshot_id, rule_id, rule_name, rule_type, "
            "matched, severity, owner_group, reason, matched_terms, created_at) "
            "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (eval_id, screenshot_id, rule_id, rule_name, rule_type, matched, severity,
             owner_group, reason, matched_terms, _now()),
        )
        return eval_id

    def list_rule_evaluations(self, screenshot_id: int) -> list[sqlite3.Row]:
        return self._query(
            "SELECT * FROM rule_evaluations WHERE screenshot_id = ? ORDER BY id",
            (screenshot_id,),
        )

    # ---------- notifications ----------
    def create_notification(self, screenshot_id: str, rule_id: str, owner_group: str,
                            recipients: str, status: str, reason: str,
                            subject: str = "", body: str = "") -> str:
        notif_id = uuid7()
        self._exec(
            "INSERT INTO notifications(id, screenshot_id, rule_id, owner_group, recipients, "
            "status, reason, subject, body, created_at) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (notif_id, screenshot_id, rule_id, owner_group, recipients, status, reason,
             subject, body, _now()),
        )
        return notif_id

    def list_notifications(self, screenshot_id: int) -> list[sqlite3.Row]:
        return self._query(
            "SELECT * FROM notifications WHERE screenshot_id = ? ORDER BY id",
            (screenshot_id,),
        )

    def list_emails(self, user_id: int | None = None,
                    screenshot_ids: list[int] | None = None) -> list[sqlite3.Row]:
        """Emails that were sent / simulated / failed (with content), along with screenshot info.

        user_id=None -> all; otherwise only emails for screenshots captured by that user.
        screenshot_ids -> only fetch emails for these screenshots (used for the sub-tab after capturing).
        """
        sql = (
            "SELECT n.*, s.user_id AS s_user_id, s.target_app, s.window_title, "
            "       s.captured_at, u.username "
            "FROM notifications n "
            "JOIN screenshots s ON s.id = n.screenshot_id "
            "LEFT JOIN users u ON u.id = s.user_id "
            "WHERE n.status IN ('sent', 'simulated', 'send_failed') "
        )
        params: list = []
        if user_id is not None:
            sql += "AND s.user_id = ? "
            params.append(user_id)
        if screenshot_ids:
            placeholders = ",".join("?" * len(screenshot_ids))
            sql += f"AND n.screenshot_id IN ({placeholders}) "
            params.extend(screenshot_ids)
        sql += "ORDER BY n.id DESC"
        return self._query(sql, tuple(params))

    def get_notification(self, notif_id: int) -> sqlite3.Row | None:
        return self._query_one("SELECT * FROM notifications WHERE id = ?", (notif_id,))

    # ---------- cooldown ----------
    def get_cooldown(self, rule_id: str):
        """Return the datetime of the most recent send, or None."""
        row = self._query_one(
            "SELECT last_sent_at FROM cooldown_state WHERE rule_id = ?", (rule_id,)
        )
        if row is None:
            return None
        try:
            return datetime.fromisoformat(row["last_sent_at"])
        except (ValueError, TypeError):
            return None

    def set_cooldown(self, rule_id: str, owner_group: str, when: datetime) -> None:
        self._exec(
            "INSERT INTO cooldown_state(rule_id, owner_group, last_sent_at) VALUES(?, ?, ?) "
            "ON CONFLICT(rule_id) DO UPDATE SET owner_group=excluded.owner_group, "
            "last_sent_at=excluded.last_sent_at",
            (rule_id, owner_group, when.isoformat(timespec="seconds")),
        )
