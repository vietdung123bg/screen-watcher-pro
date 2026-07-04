"""Tests for mock watcher data: first-run seed + the generate_mock_data chat tool."""

from __future__ import annotations

from app.ai.chat_agent import ChatAgent
from app.ai.provider_config import ProviderConfig
from app.ai.watcher_context_service import WatcherContextService
from app.db.database import Database
from app.db.repository import Repository
from app.services.auth import CurrentUser
from app.services.mock_data import generate_mock_data, seed_first_run


def _repo(tmp_path):
    db = Database(db_path=tmp_path / "t.db")
    db.init_schema()
    return Repository(db)


def _agent(repo, tmp_path):
    cfg = ProviderConfig(timeout_seconds=30, max_context_chars=6000, mock=True,
                         default_provider="openrouter", engine="sdk")
    return ChatAgent(cfg, repo, WatcherContextService(db_path=tmp_path / "t.db"))


def test_seed_first_run_is_idempotent(tmp_path):
    repo = _repo(tmp_path)
    admin = repo.get_user_by_username("admin")
    assert seed_first_run(repo, admin["id"]) == 3       # fresh DB -> seeds 3
    assert seed_first_run(repo, admin["id"]) == 0       # already has data -> no-op
    assert len(repo.list_screenshots()) == 3


def test_seed_first_run_latest_is_a_matched_execution(tmp_path):
    """The newest seeded execution should have a matched rule (so 'latest' is useful)."""
    repo = _repo(tmp_path)
    admin = repo.get_user_by_username("admin")
    seed_first_run(repo, admin["id"])
    wc = WatcherContextService(db_path=tmp_path / "t.db").latest(None)
    assert wc.has_data and wc.matched_rules            # latest ends on a matched scenario


def test_generate_mock_data_clamps_count_and_falls_back_scenario(tmp_path):
    repo = _repo(tmp_path)
    admin = repo.get_user_by_username("admin")
    assert len(generate_mock_data(repo, admin["id"], "payment", count=99)) == 5   # clamp
    assert len(generate_mock_data(repo, admin["id"], "bogus", count=1)) == 1      # fallback


def test_chat_tool_generate_mock_data_admin_only(tmp_path):
    repo = _repo(tmp_path)
    admin = repo.get_user_by_username("admin")
    agent = _agent(repo, tmp_path)
    admin_u = CurrentUser(id=admin["id"], username="admin", full_name="A", role_name="admin")
    viewer = CurrentUser(id="v1", username="v", full_name="V", role_name="viewer")

    out = agent._t_generate_mock_data(admin_u, count=2, scenario="error")
    assert out["created"] == 2 and out["scenario"] == "error"
    assert len(out["execution_ids"]) == 2

    denied = agent._t_generate_mock_data(viewer, count=1)
    assert "permission" in denied.get("error", "")
