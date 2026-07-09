"""Migration 002_prd22.sql: idempotent, creates the 6 new tables, backs up the DB."""

from __future__ import annotations

from app.db.database import Database

PRD22_TABLES = ("events", "rules_db", "ai_event_reviews", "user_review_decisions",
                "rule_test_results", "sos_alerts")


def _tables(db: Database) -> set[str]:
    rows = db.conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    return {r["name"] for r in rows}


def test_migration_creates_all_prd22_tables(tmp_path):
    db = Database(tmp_path / "m.db")
    db.init_schema()
    tables = _tables(db)
    for t in PRD22_TABLES:
        assert t in tables, f"missing table {t}"
    assert "schema_migrations" in tables


def test_migration_is_idempotent(tmp_path):
    db = Database(tmp_path / "m.db")
    db.init_schema()
    # run the whole init (including apply_migrations) again — must not raise
    db.init_schema()
    db.apply_migrations()
    assert set(PRD22_TABLES) <= _tables(db)
    # recorded exactly once
    n = db.conn.execute("SELECT COUNT(*) AS c FROM schema_migrations "
                        "WHERE name='002_prd22.sql'").fetchone()["c"]
    assert n == 1


def test_migration_backs_up_db_once(tmp_path):
    db_path = tmp_path / "m.db"
    db = Database(db_path)
    db.init_schema()
    backup = tmp_path / "m.db.pre-prd22.bak"
    assert backup.exists(), "expected a pre-prd22 backup next to the DB"
    stamp = backup.stat().st_mtime_ns
    db.init_schema()   # second run must not overwrite the backup
    assert backup.stat().st_mtime_ns == stamp


def test_migration_survives_existing_legacy_db(tmp_path):
    """A DB created before PRD 2.2 (legacy schema only) upgrades cleanly."""
    db = Database(tmp_path / "legacy.db")
    with db.lock:
        db.conn.executescript("CREATE TABLE IF NOT EXISTS dummy(x)")
    db.init_schema()
    assert set(PRD22_TABLES) <= _tables(db)


def test_indexes_created(tmp_path):
    db = Database(tmp_path / "m.db")
    db.init_schema()
    idx = {r["name"] for r in db.conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index'")}
    for name in ("idx_sos_pending", "idx_events_status", "idx_rules_db_status"):
        assert name in idx
