"""Repository: CRUD for user/role/permission, screenshot and OCR."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta
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

    # ---------- chatbot conversations ----------
    def create_chat_session(self, user_id: str, title: str = "",
                            metadata: dict | None = None,
                            session_id: str | None = None) -> str:
        """Create a chat session. Pass session_id to use a client-supplied UUID
        (for a brand-new session); otherwise a fresh UUIDv7 is generated."""
        sid, now = (session_id or uuid7()), _now()
        self._exec(
            "INSERT INTO chat_sessions(id, user_id, title, message_count, created_at, "
            "updated_at, last_message_at, metadata) VALUES(?, ?, ?, 0, ?, ?, NULL, ?)",
            (sid, user_id, title, now, now, json.dumps(metadata) if metadata else None),
        )
        return sid

    def get_chat_session(self, session_id: str) -> sqlite3.Row | None:
        return self._query_one("SELECT * FROM chat_sessions WHERE id = ?", (session_id,))

    def list_chat_sessions(self, user_id: str) -> list[sqlite3.Row]:
        return self._query(
            "SELECT * FROM chat_sessions WHERE user_id = ? AND deleted_at IS NULL "
            "ORDER BY updated_at DESC", (user_id,))

    def list_all_chat_sessions(self) -> list[sqlite3.Row]:
        """Every user's chat sessions with the owner's username (admin history view).
        Admins may READ any session but only continue their own — see ChatStore."""
        return self._query(
            "SELECT s.*, u.username AS owner_username FROM chat_sessions s "
            "JOIN users u ON u.id = s.user_id "
            "WHERE s.deleted_at IS NULL ORDER BY s.updated_at DESC")

    def list_chat_messages(self, session_id: str, limit: int | None = None,
                           newest_first: bool = False) -> list[sqlite3.Row]:
        order = "DESC" if newest_first else "ASC"
        # id is UUIDv7 (time-ordered) — a stable chronological tiebreaker for equal timestamps.
        sql = (f"SELECT * FROM chat_messages WHERE session_id = ? "
               f"ORDER BY created_at {order}, id {order}")
        if limit:
            sql += f" LIMIT {int(limit)}"
        return self._query(sql, (session_id,))

    def soft_delete_chat_session(self, session_id: str) -> int:
        cur = self._exec(
            "UPDATE chat_sessions SET deleted_at = ? WHERE id = ? AND deleted_at IS NULL",
            (_now(), session_id))
        return cur.rowcount

    def record_chat_turn(self, session_id: str, user_id: str, user_text: str,
                         assistant_text: str, error_code: str | None = None,
                         metadata: dict | None = None) -> None:
        """Persist one turn (user + assistant) and bump the session counters in a SINGLE
        transaction — the cheapest safe write path for heavy conversation logging."""
        now = _now()
        meta_json = json.dumps(metadata) if metadata else None
        with self.db.lock:
            c = self.db.conn
            c.execute(
                "INSERT INTO chat_messages(id, session_id, user_id, role, content, "
                "error_code, metadata, created_at) VALUES(?, ?, ?, 'user', ?, NULL, NULL, ?)",
                (uuid7(), session_id, user_id, user_text, now))
            c.execute(
                "INSERT INTO chat_messages(id, session_id, user_id, role, content, "
                "error_code, metadata, created_at) VALUES(?, ?, ?, 'assistant', ?, ?, ?, ?)",
                (uuid7(), session_id, user_id, assistant_text, error_code, meta_json, now))
            c.execute(
                "UPDATE chat_sessions SET message_count = message_count + 2, "
                "last_message_at = ?, updated_at = ? WHERE id = ?", (now, now, session_id))
            c.commit()

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

    # ---------- issue vectorstore ----------
    def create_issue_vector(self, title: str, summary: str, rule_id: str,
                            severity: str, owner_group: str, screenshot_id: str,
                            vector_json: str, metadata: dict | None = None) -> str:
        issue_id = uuid7()
        now = _now()
        self._exec(
            "INSERT INTO issue_vectors(id, title, summary, rule_id, severity, owner_group, "
            "status, first_seen_at, last_seen_at, last_screenshot_id, occurrence_count, "
            "vector_json, metadata_json) VALUES(?, ?, ?, ?, ?, ?, 'open', ?, ?, ?, 1, ?, ?)",
            (issue_id, title, summary, rule_id, severity, owner_group, now, now,
             screenshot_id, vector_json, json.dumps(metadata or {}, ensure_ascii=False)),
        )
        return issue_id

    def get_issue_vector(self, issue_id: str) -> sqlite3.Row | None:
        return self._query_one("SELECT * FROM issue_vectors WHERE id = ?", (issue_id,))

    def list_issue_vectors(self, status: str | None = "open") -> list[sqlite3.Row]:
        sql = "SELECT * FROM issue_vectors "
        params: tuple = ()
        if status:
            sql += "WHERE status = ? "
            params = (status,)
        sql += "ORDER BY last_seen_at DESC"
        return self._query(sql, params)

    def touch_issue_vector(self, issue_id: str, screenshot_id: str,
                           metadata: dict | None = None) -> None:
        self._exec(
            "UPDATE issue_vectors SET last_seen_at = ?, last_screenshot_id = ?, "
            "occurrence_count = occurrence_count + 1, metadata_json = ? WHERE id = ?",
            (_now(), screenshot_id, json.dumps(metadata or {}, ensure_ascii=False), issue_id),
        )

    def list_recent_issues(self, limit: int = 10) -> list[sqlite3.Row]:
        return self._query(
            "SELECT * FROM issue_vectors ORDER BY last_seen_at DESC LIMIT ?",
            (int(limit),),
        )

    def list_audit_logs(self, action: str | None = None, actor: str | None = None,
                        since: str | None = None, limit: int = 100) -> list[sqlite3.Row]:
        """Audit trail, newest first. `action` matches as a prefix (e.g. 'rule.'
        returns rule.create/rule.approve/...); `actor` matches a username."""
        sql = ("SELECT a.*, u.username FROM audit_logs a "
               "LEFT JOIN users u ON u.id = a.user_id WHERE 1=1 ")
        params: list = []
        if action:
            sql += "AND a.action LIKE ? "
            params.append(action + "%")
        if actor:
            sql += "AND u.username = ? "
            params.append(actor)
        if since:
            sql += "AND a.created_at >= ? "
            params.append(since)
        sql += "ORDER BY a.created_at DESC, a.id DESC LIMIT ?"
        params.append(int(limit))
        return self._query(sql, tuple(params))


# ============================================================================
# PRD 2.2 repositories (events / rules_db / AI review / user review /
# rule tests / SOS alerts). Kept as separate classes so the legacy Repository
# stays untouched; all share the same Database (and its lock).
# ============================================================================

class _BaseRepo:
    """Shared SQLite helpers for the PRD 2.2 repositories."""

    def __init__(self, db: Database):
        self.db = db

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


class EventRepository(_BaseRepo):
    """CRUD for `events` (PRD 2.2 §events)."""

    def create(self, source: str, screen: str | None, screenshot_id: str | None,
               raw_text: str | None, metadata: dict | None = None,
               confidence: float | None = None, event_time: str | None = None,
               status: str = "NEW") -> str:
        pk = uuid7()
        self._exec(
            "INSERT INTO events(id, event_id, source, screen, screenshot_id, raw_text, "
            "metadata_json, confidence, status, event_time, created_at, updated_at) "
            "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (pk, f"EVT-{pk}", source, screen, screenshot_id, raw_text,
             json.dumps(metadata or {}, ensure_ascii=False), confidence, status,
             event_time or _now(), _now(), _now()),
        )
        return pk

    def get(self, event_id: str) -> sqlite3.Row | None:
        """Accepts either the primary key or the public event_id (EVT-...)."""
        return self._query_one(
            "SELECT * FROM events WHERE id = ? OR event_id = ?", (event_id, event_id))

    def list(self, status: str | None = None, screen: str | None = None,
             source: str | None = None, limit: int = 20, offset: int = 0) -> list[sqlite3.Row]:
        sql = "SELECT * FROM events WHERE 1=1 "
        params: list = []
        if status:
            sql += "AND status = ? "
            params.append(status)
        if screen:
            sql += "AND screen LIKE ? "
            params.append(f"%{screen}%")
        if source:
            sql += "AND source = ? "
            params.append(source)
        sql += "ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?"
        params.extend([int(limit), int(offset)])
        return self._query(sql, tuple(params))

    def count(self, status: str | None = None, screen: str | None = None,
              source: str | None = None) -> int:
        sql = "SELECT COUNT(*) AS c FROM events WHERE 1=1 "
        params: list = []
        if status:
            sql += "AND status = ? "
            params.append(status)
        if screen:
            sql += "AND screen LIKE ? "
            params.append(f"%{screen}%")
        if source:
            sql += "AND source = ? "
            params.append(source)
        row = self._query_one(sql, tuple(params))
        return int(row["c"]) if row else 0

    def set_status(self, event_pk: str, status: str) -> None:
        self._exec("UPDATE events SET status = ?, updated_at = ? WHERE id = ?",
                   (status, _now(), event_pk))

    def set_normalized(self, event_pk: str, normalized: dict, status: str = "NORMALIZED") -> None:
        self._exec(
            "UPDATE events SET normalized_json = ?, status = ?, updated_at = ? WHERE id = ?",
            (json.dumps(normalized, ensure_ascii=False), status, _now(), event_pk))


class RuleDbRepository(_BaseRepo):
    """CRUD for `rules_db` — status changes go through RuleManagementService,
    which enforces the governance rules (GR22-001...)."""

    _FIELDS = ("name", "description", "owner_group", "status", "enabled", "version",
               "priority", "severity", "alert_type", "rule_type", "condition_json",
               "is_incident_rule", "cooldown_seconds", "reject_reason")

    def create(self, rule_id: str, name: str, rule_type: str, condition_json: str,
               status: str = "DRAFT", enabled: int = 0, description: str = "",
               owner_group: str = "", severity: str = "medium", alert_type: str = "",
               is_incident_rule: int = 0, cooldown_seconds: int = 300,
               priority: int = 50, created_by: str | None = None) -> str:
        pk = uuid7()
        self._exec(
            "INSERT INTO rules_db(id, rule_id, name, description, owner_group, status, "
            "enabled, version, priority, severity, alert_type, rule_type, condition_json, "
            "is_incident_rule, cooldown_seconds, created_by, created_at, updated_at) "
            "VALUES(?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (pk, rule_id, name, description, owner_group, status, int(enabled),
             int(priority), severity, alert_type, rule_type, condition_json,
             int(is_incident_rule), int(cooldown_seconds), created_by, _now(), _now()),
        )
        return pk

    def get(self, rule_id: str) -> sqlite3.Row | None:
        """Accepts either the primary key or the public rule_id."""
        return self._query_one(
            "SELECT * FROM rules_db WHERE id = ? OR rule_id = ?", (rule_id, rule_id))

    def list(self, status: str | None = None, enabled: bool | None = None,
             include_rejected: bool = True) -> list[sqlite3.Row]:
        sql = "SELECT * FROM rules_db WHERE 1=1 "
        params: list = []
        if status:
            sql += "AND status = ? "
            params.append(status)
        if enabled is not None:
            sql += "AND enabled = ? "
            params.append(1 if enabled else 0)
        if not include_rejected:
            sql += "AND status != 'REJECTED' "
        sql += "ORDER BY priority ASC, created_at DESC"
        return self._query(sql, tuple(params))

    def list_active(self) -> list[sqlite3.Row]:
        """The rules the event evaluator runs: ACTIVE and enabled."""
        return self._query(
            "SELECT * FROM rules_db WHERE status = 'ACTIVE' AND enabled = 1 "
            "ORDER BY priority ASC")

    def update(self, rule_pk: str, fields: dict) -> None:
        """Update only whitelisted columns; bumps version + updated_at."""
        cols = {k: v for k, v in fields.items() if k in self._FIELDS}
        if not cols:
            return
        assignments = ", ".join(f"{c} = ?" for c in cols)
        self._exec(
            f"UPDATE rules_db SET {assignments}, version = version + 1, updated_at = ? "
            f"WHERE id = ?",
            tuple(cols.values()) + (_now(), rule_pk))


class AiReviewRepository(_BaseRepo):
    """CRUD for `ai_event_reviews` (level-1 AI review results)."""

    def create(self, event_pk: str, status: str = "PENDING",
               model_name: str = "", prompt_version: str = "") -> str:
        pk = uuid7()
        self._exec(
            "INSERT INTO ai_event_reviews(id, event_id, status, model_name, "
            "prompt_version, created_at) VALUES(?, ?, ?, ?, ?, ?)",
            (pk, event_pk, status, model_name, prompt_version, _now()))
        return pk

    _FIELDS = ("classification", "risk_level", "confidence", "reason",
               "suggested_action", "suggested_rule_json", "suggested_rule_id",
               "model_name", "prompt_version", "status")

    def update(self, review_pk: str, fields: dict) -> None:
        cols = {k: v for k, v in fields.items() if k in self._FIELDS}
        if not cols:
            return
        assignments = ", ".join(f"{c} = ?" for c in cols)
        self._exec(f"UPDATE ai_event_reviews SET {assignments} WHERE id = ?",
                   tuple(cols.values()) + (review_pk,))

    def get(self, review_pk: str) -> sqlite3.Row | None:
        return self._query_one("SELECT * FROM ai_event_reviews WHERE id = ?", (review_pk,))

    def latest_for_event(self, event_pk: str) -> sqlite3.Row | None:
        return self._query_one(
            "SELECT * FROM ai_event_reviews WHERE event_id = ? "
            "ORDER BY created_at DESC, id DESC LIMIT 1", (event_pk,))

    def list_review_queue(self, limit: int = 50) -> list[sqlite3.Row]:
        """Reviews awaiting the level-2 user decision, with their event context."""
        return self._query(
            "SELECT r.*, e.event_id AS public_event_id, e.screen, e.status AS event_status, "
            "       e.raw_text "
            "FROM ai_event_reviews r JOIN events e ON e.id = r.event_id "
            "WHERE r.status = 'REVIEWED' AND e.status = 'USER_REVIEW_PENDING' "
            "ORDER BY r.created_at DESC LIMIT ?", (int(limit),))


class UserReviewRepository(_BaseRepo):
    """CRUD for `user_review_decisions` (level-2 user decisions)."""

    def create(self, event_pk: str, ai_review_id: str | None, decision: str,
               reviewed_by: str, edited_rule_json: str | None = None,
               reject_reason: str | None = None, review_note: str | None = None) -> str:
        pk = uuid7()
        self._exec(
            "INSERT INTO user_review_decisions(id, event_id, ai_review_id, decision, "
            "edited_rule_json, reject_reason, review_note, reviewed_by, reviewed_at) "
            "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (pk, event_pk, ai_review_id, decision, edited_rule_json, reject_reason,
             review_note, reviewed_by, _now()))
        return pk

    def list_for_event(self, event_pk: str) -> list[sqlite3.Row]:
        return self._query(
            "SELECT * FROM user_review_decisions WHERE event_id = ? "
            "ORDER BY reviewed_at DESC", (event_pk,))


class RuleTestRepository(_BaseRepo):
    """CRUD for `rule_test_results`."""

    def create(self, rule_pk: str, event_pk: str | None, expected_decision: str,
               actual_decision: str, result_status: str, tested_by: str | None,
               matched_conditions: dict | None = None,
               failed_conditions: dict | None = None) -> str:
        pk = uuid7()
        self._exec(
            "INSERT INTO rule_test_results(id, rule_id, event_id, expected_decision, "
            "actual_decision, matched_conditions_json, failed_conditions_json, "
            "result_status, tested_by, tested_at) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (pk, rule_pk, event_pk, expected_decision, actual_decision,
             json.dumps(matched_conditions or {}, ensure_ascii=False),
             json.dumps(failed_conditions or {}, ensure_ascii=False),
             result_status, tested_by, _now()))
        return pk

    def list_for_rule(self, rule_pk: str, limit: int = 20) -> list[sqlite3.Row]:
        return self._query(
            "SELECT * FROM rule_test_results WHERE rule_id = ? "
            "ORDER BY tested_at DESC LIMIT ?", (rule_pk, int(limit)))


class SosAlertRepository(_BaseRepo):
    """CRUD for `sos_alerts` + the polling contract of the console SosWatcherJob."""

    def create(self, event_pk: str, rule_pk: str, severity: str, message: str,
               incident_id: str | None = None, acknowledge_required: int = 1) -> str:
        pk = uuid7()
        self._exec(
            "INSERT INTO sos_alerts(id, event_id, rule_id, incident_id, severity, message, "
            "sound_played, acknowledge_required, acknowledge_status, created_at) "
            "VALUES(?, ?, ?, ?, ?, ?, 0, ?, 'PENDING', ?)",
            (pk, event_pk, rule_pk, incident_id, severity, message,
             int(acknowledge_required), _now()))
        return pk

    def get(self, alert_id: str) -> sqlite3.Row | None:
        return self._query_one("SELECT * FROM sos_alerts WHERE id = ?", (alert_id,))

    def list(self, status: str | None = None, limit: int = 100) -> list[sqlite3.Row]:
        sql = "SELECT * FROM sos_alerts WHERE 1=1 "
        params: list = []
        if status:
            sql += "AND acknowledge_status = ? "
            params.append(status)
        sql += "ORDER BY created_at DESC LIMIT ?"
        params.append(int(limit))
        return self._query(sql, tuple(params))

    def list_pending_for_beep(self, cooldown_seconds: int) -> list[sqlite3.Row]:
        """PENDING alerts that are due for a(nother) beep: never beeped, or the
        last beep is older than `cooldown_seconds` (the job's re-alarm window)."""
        threshold = (datetime.now() - timedelta(seconds=int(cooldown_seconds))
                     ).isoformat(timespec="seconds")
        return self._query(
            "SELECT * FROM sos_alerts WHERE acknowledge_status = 'PENDING' "
            "AND (last_beep_at IS NULL OR last_beep_at < ?) "
            "ORDER BY created_at", (threshold,))

    def mark_beeped(self, alert_id: str) -> None:
        self._exec(
            "UPDATE sos_alerts SET sound_played = sound_played + 1, last_beep_at = ? "
            "WHERE id = ?", (_now(), alert_id))

    def acknowledge(self, alert_id: str, user_id: str) -> int:
        """GR22-004: acknowledging records WHO and WHEN. Returns rows affected
        (0 = not found or already acknowledged)."""
        cur = self._exec(
            "UPDATE sos_alerts SET acknowledge_status = 'ACKNOWLEDGED', "
            "acknowledged_by = ?, acknowledged_at = ? "
            "WHERE id = ? AND acknowledge_status = 'PENDING'",
            (user_id, _now(), alert_id))
        return cur.rowcount
