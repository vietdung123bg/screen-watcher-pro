"""Shared helpers for the PRD 2.2 test files: a temp DB + the service stack."""

from __future__ import annotations

from pathlib import Path

from app.db.database import Database
from app.db.repository import Repository
from app.services.auth import CurrentUser
from app.services.prd22_bootstrap import Prd22Services, build_prd22

BASE_CONFIG: dict = {
    "ai": {"mock": True, "timeout_seconds": 30, "max_context_chars": 6000},
    "rules": [],
    "owners": {},
    "email": {"enabled": False},
    "auth": {},
    "cooldown": {"default_minutes": 15, "enabled": True},
    "prd22": {
        "enabled": True,
        "ai_review": {"enabled": True, "auto_review_on_no_match": True,
                      "max_context_chars": 6000, "timeout_seconds": 30},
        "rule_governance": {"ai_can_create_draft_rule": True,
                            "ai_can_activate_rule": False,
                            "require_user_review_for_ai_rule": True,
                            "sync_yaml_to_db_on_startup": True},
    },
    "sos_alert": {"enabled": False},
}


def make_db(tmp_path: Path, name: str = "test.db") -> tuple[Database, Repository]:
    db = Database(tmp_path / name)
    db.init_schema()
    return db, Repository(db)


def make_stack(tmp_path: Path, config: dict | None = None
               ) -> tuple[Database, Repository, Prd22Services]:
    db, repo = make_db(tmp_path)
    cfg = config if config is not None else BASE_CONFIG
    return db, repo, build_prd22(db, repo, cfg)


def admin_user(repo: Repository) -> CurrentUser:
    row = repo.get_user_by_username("admin")
    return CurrentUser(id=row["id"], username="admin", full_name="Admin",
                       role_name="admin", permissions={"user.manage"})


INCIDENT_RULE = {
    "rule_id": "incident_payment", "name": "Payment incident",
    "rule_type": "any_keywords",
    "condition": {"keywords": ["declined", "fraud"], "ignore_case": True},
    "status": "ACTIVE", "enabled": 1, "is_incident_rule": 1, "severity": "critical",
}
