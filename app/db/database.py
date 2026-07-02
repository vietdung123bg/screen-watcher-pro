"""SQLite connection, schema initialization and default data seeding (RBAC)."""

from __future__ import annotations

import logging
import sqlite3
import threading
from pathlib import Path

from app import config
from app.db.ids import uuid7

logger = logging.getLogger("screen_watcher.db")

# ---- Permission definitions ----
PERMISSIONS: dict[str, str] = {
    "capture.run": "Capture the screen and run OCR",
    "screenshot.view": "View own screenshots",
    "screenshot.view_all": "View screenshots of all users",
    "ocr.view": "View OCR text results",
    "rule.view": "View rules, rule evaluations and email decisions",
    "user.manage": "Manage users, roles and permissions",
}

# ---- Role definitions -> permission list ----
ROLES: dict[str, dict] = {
    "admin": {
        "description": "Administrator — full access",
        "permissions": list(PERMISSIONS.keys()),
    },
    "operator": {
        "description": "Operator — capture & view own data",
        "permissions": ["capture.run", "screenshot.view", "ocr.view", "rule.view"],
    },
    "viewer": {
        "description": "Viewer — view own screenshots, OCR & rules only",
        "permissions": ["screenshot.view", "ocr.view", "rule.view"],
    },
}

SCHEMA = """
-- All primary keys are UUIDv7 strings (time-ordered) — see app/db/ids.py.
CREATE TABLE IF NOT EXISTS roles (
    id          TEXT PRIMARY KEY,
    name        TEXT UNIQUE NOT NULL,
    description TEXT
);

CREATE TABLE IF NOT EXISTS permissions (
    id          TEXT PRIMARY KEY,
    code        TEXT UNIQUE NOT NULL,
    description TEXT
);

CREATE TABLE IF NOT EXISTS role_permissions (
    role_id       TEXT NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    permission_id TEXT NOT NULL REFERENCES permissions(id) ON DELETE CASCADE,
    PRIMARY KEY (role_id, permission_id)
);

CREATE TABLE IF NOT EXISTS users (
    id                   TEXT PRIMARY KEY,              -- UUIDv7 (time-ordered)
    username             TEXT UNIQUE NOT NULL,
    password_hash        TEXT NOT NULL,
    salt                 TEXT NOT NULL,
    full_name            TEXT,
    email                TEXT,
    first_name           TEXT,
    last_name            TEXT,
    phone                TEXT,
    role_id              TEXT REFERENCES roles(id),
    is_active            INTEGER NOT NULL DEFAULT 1,
    must_change_password INTEGER NOT NULL DEFAULT 0,  -- 1 = force a password change on next sign-in
    created_at           TEXT NOT NULL,
    deleted_at           TEXT                          -- NULL = live; timestamp = soft-deleted
);

CREATE TABLE IF NOT EXISTS capture_sessions (
    id         TEXT PRIMARY KEY,
    user_id    TEXT NOT NULL REFERENCES users(id),
    targets    TEXT NOT NULL,          -- e.g.: "chrome,edge"
    note       TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS screenshots (
    id           TEXT PRIMARY KEY,
    session_id   TEXT REFERENCES capture_sessions(id) ON DELETE CASCADE,
    user_id      TEXT NOT NULL REFERENCES users(id),
    target_app   TEXT NOT NULL,        -- chrome / edge
    window_title TEXT,
    file_path    TEXT,
    width        INTEGER,
    height       INTEGER,
    status       TEXT NOT NULL,        -- success / failed
    error        TEXT,
    captured_at  TEXT NOT NULL,
    deleted_at   TEXT                  -- NULL = live; timestamp = soft-deleted (hidden from API)
);

CREATE TABLE IF NOT EXISTS ocr_results (
    id            TEXT PRIMARY KEY,
    screenshot_id TEXT NOT NULL REFERENCES screenshots(id) ON DELETE CASCADE,
    model         TEXT NOT NULL,
    text          TEXT,
    char_count    INTEGER,
    duration_ms   INTEGER,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id         TEXT PRIMARY KEY,
    user_id    TEXT REFERENCES users(id),
    action     TEXT NOT NULL,
    detail     TEXT,
    created_at TEXT NOT NULL
);

-- Result of evaluating each rule against the OCR text of a screenshot
CREATE TABLE IF NOT EXISTS rule_evaluations (
    id            TEXT PRIMARY KEY,
    screenshot_id TEXT NOT NULL REFERENCES screenshots(id) ON DELETE CASCADE,
    rule_id       TEXT NOT NULL,
    rule_name     TEXT,
    rule_type     TEXT,
    matched       INTEGER NOT NULL,       -- 0/1
    severity      TEXT,
    owner_group   TEXT,
    reason        TEXT,                   -- explains why it matched / did not match
    matched_terms TEXT,
    created_at    TEXT NOT NULL
);

-- One notification decision (send / skip) for a matched rule
CREATE TABLE IF NOT EXISTS notifications (
    id            TEXT PRIMARY KEY,
    screenshot_id TEXT NOT NULL REFERENCES screenshots(id) ON DELETE CASCADE,
    rule_id       TEXT NOT NULL,
    owner_group   TEXT,
    recipients    TEXT,
    status        TEXT NOT NULL,          -- sent/simulated/skipped_cooldown/no_owner/send_failed/skipped_empty
    reason        TEXT,                   -- explains why it was sent / not sent
    subject       TEXT,                   -- email subject (if sent/simulated)
    body          TEXT,                   -- content of the sent email
    created_at    TEXT NOT NULL
);

-- Cooldown state per rule (prevents sending duplicate emails)
CREATE TABLE IF NOT EXISTS cooldown_state (
    rule_id       TEXT PRIMARY KEY,
    owner_group   TEXT,
    last_sent_at  TEXT NOT NULL
);
"""


class Database:
    """Wraps the SQLite connection. Usable from multiple threads (capture runs in the background)."""

    def __init__(self, db_path: Path | None = None):
        self.path = Path(db_path or config.DB_PATH)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.lock = threading.Lock()

    def init_schema(self) -> None:
        with self.lock:
            self.conn.executescript(SCHEMA)
            self.conn.commit()
        self._migrate_ids_to_uuid()   # legacy INTEGER ids (any table) -> UUIDv7 TEXT
        self._migrate()
        logger.info("Initialized schema at %s", self.path)
        self._seed_rbac()

    # (table, has own `id` PK, [(fk_column, referenced_table), ...])
    _UUID_REBUILD_SPEC = [
        ("permissions", True, []),
        ("roles", True, []),
        ("users", True, [("role_id", "roles")]),
        ("role_permissions", False, [("role_id", "roles"), ("permission_id", "permissions")]),
        ("capture_sessions", True, [("user_id", "users")]),
        ("screenshots", True, [("session_id", "capture_sessions"), ("user_id", "users")]),
        ("ocr_results", True, [("screenshot_id", "screenshots")]),
        ("rule_evaluations", True, [("screenshot_id", "screenshots")]),
        ("notifications", True, [("screenshot_id", "screenshots")]),
        ("audit_logs", True, [("user_id", "users")]),
    ]

    def _migrate_ids_to_uuid(self) -> None:
        """One-time migration for legacy DBs with INTEGER primary keys: rebuild every
        table to a UUIDv7 TEXT id, remapping ALL foreign keys. Backs the DB up first.
        No-op once every id is already TEXT (handles partially-migrated DBs too)."""
        import shutil

        spec = self._UUID_REBUILD_SPEC
        with self.lock:
            cur = self.conn.cursor()

            def id_type(t: str) -> str:
                return next((r["type"] for r in cur.execute(f"PRAGMA table_info({t})")
                             if r["name"] == "id"), "").upper()

            if not any(id_type(t) == "INTEGER" for t, has_id, _ in spec if has_id):
                return  # already all-UUID

            logger.warning("Migrating all INTEGER ids -> UUIDv7 TEXT (rebuilding tables)...")
            try:
                shutil.copy2(self.path, str(self.path) + ".pre-uuid.bak")
            except Exception as e:  # backup is best-effort
                logger.warning("Could not back up DB before UUID migration: %s", e)

            self.conn.commit()
            self.conn.execute("PRAGMA foreign_keys=OFF")
            self.conn.execute("PRAGMA legacy_alter_table=ON")

            # old-id -> new-id per table (identity if already a UUID string).
            maps: dict[str, dict] = {}
            for table, has_id, _ in spec:
                if not has_id:
                    continue
                maps[table] = {r["id"]: (r["id"] if isinstance(r["id"], str) else uuid7())
                               for r in cur.execute(f"SELECT id FROM {table}")}

            for table, _, _ in spec:
                cur.execute(f"ALTER TABLE {table} RENAME TO {table}__old")
            self.conn.executescript(SCHEMA)  # recreate the renamed tables fresh

            for table, has_id, fks in spec:
                new_cols = [r["name"] for r in cur.execute(f"PRAGMA table_info({table})")]
                old_cols = {r["name"] for r in cur.execute(f"PRAGMA table_info({table}__old)")}
                common = [c for c in new_cols if c in old_cols]
                for row in cur.execute(f"SELECT * FROM {table}__old").fetchall():
                    vals = {c: row[c] for c in common}
                    if has_id:
                        vals["id"] = maps[table][row["id"]]
                    for col, ref in fks:
                        if vals.get(col) is not None:
                            vals[col] = maps[ref].get(vals[col], vals[col])
                    cols = ",".join(vals.keys())
                    ph = ",".join("?" * len(vals))
                    cur.execute(f"INSERT INTO {table}({cols}) VALUES({ph})", tuple(vals.values()))

            for table, _, _ in spec:
                cur.execute(f"DROP TABLE {table}__old")
            self.conn.commit()
            self.conn.execute("PRAGMA foreign_keys=ON")
            logger.warning("UUID migration complete. Backup: %s.pre-uuid.bak", self.path)

    def _migrate(self) -> None:
        """Add new columns to an old DB (CREATE TABLE IF NOT EXISTS does not add columns by itself)."""
        with self.lock:
            cur = self.conn.cursor()
            cols = {r["name"] for r in cur.execute("PRAGMA table_info(notifications)")}
            for col in ("subject", "body"):
                if col not in cols:
                    cur.execute(f"ALTER TABLE notifications ADD COLUMN {col} TEXT")
                    logger.info("Migration: added column notifications.%s", col)

            # Soft-delete marker for screenshots (watcher executions). NULL = live;
            # a timestamp = soft-deleted (hidden from the API but kept in the DB).
            shot_cols = {r["name"] for r in cur.execute("PRAGMA table_info(screenshots)")}
            if "deleted_at" not in shot_cols:
                cur.execute("ALTER TABLE screenshots ADD COLUMN deleted_at TEXT")
                logger.info("Migration: added column screenshots.deleted_at (soft delete)")

            user_cols = {r["name"] for r in cur.execute("PRAGMA table_info(users)")}
            if "must_change_password" not in user_cols:
                cur.execute(
                    "ALTER TABLE users ADD COLUMN must_change_password "
                    "INTEGER NOT NULL DEFAULT 0"
                )
                # On an existing DB, force the built-in admin to set a new password
                # the next time it signs in (the feature would otherwise only apply
                # to freshly created databases).
                cur.execute(
                    "UPDATE users SET must_change_password = 1 WHERE username = 'admin'"
                )
                logger.info("Migration: added column users.must_change_password")
            if "deleted_at" not in user_cols:
                cur.execute("ALTER TABLE users ADD COLUMN deleted_at TEXT")
                logger.info("Migration: added column users.deleted_at (soft delete)")
            for col in ("email", "first_name", "last_name", "phone"):
                if col not in user_cols:
                    cur.execute(f"ALTER TABLE users ADD COLUMN {col} TEXT")
                    logger.info("Migration: added column users.%s", col)
            self.conn.commit()

    def _seed_rbac(self) -> None:
        """Seed permissions, roles, role_permissions and the default admin account."""
        from app.services.auth import hash_password  # avoid circular import

        with self.lock:
            cur = self.conn.cursor()

            # permissions
            for code, desc in PERMISSIONS.items():
                cur.execute(
                    "INSERT OR IGNORE INTO permissions(id, code, description) VALUES(?, ?, ?)",
                    (uuid7(), code, desc),
                )
            # roles + role_permissions
            for role_name, info in ROLES.items():
                cur.execute(
                    "INSERT OR IGNORE INTO roles(id, name, description) VALUES(?, ?, ?)",
                    (uuid7(), role_name, info["description"]),
                )
                role_id = cur.execute(
                    "SELECT id FROM roles WHERE name = ?", (role_name,)
                ).fetchone()["id"]
                for perm_code in info["permissions"]:
                    perm_id = cur.execute(
                        "SELECT id FROM permissions WHERE code = ?", (perm_code,)
                    ).fetchone()["id"]
                    cur.execute(
                        "INSERT OR IGNORE INTO role_permissions(role_id, permission_id) "
                        "VALUES(?, ?)",
                        (role_id, perm_id),
                    )

            # default admin account: admin / admin123
            exists = cur.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
            if exists == 0:
                from datetime import datetime

                admin_role_id = cur.execute(
                    "SELECT id FROM roles WHERE name = 'admin'"
                ).fetchone()["id"]
                pwd_hash, salt = hash_password("admin123")
                cur.execute(
                    "INSERT INTO users(id, username, password_hash, salt, full_name, "
                    "role_id, is_active, must_change_password, created_at) "
                    "VALUES(?, ?, ?, ?, ?, ?, 1, 1, ?)",
                    (uuid7(), "admin", pwd_hash, salt, "Administrator", admin_role_id,
                     datetime.now().isoformat(timespec="seconds")),
                )
                logger.info(
                    "Created the default admin account (admin / admin123) — "
                    "must change password on first sign-in."
                )

            self.conn.commit()

    def close(self) -> None:
        try:
            self.conn.close()
        except Exception:
            pass
