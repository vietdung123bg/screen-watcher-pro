"""Engine switching in ChatAgent: `ai.engine`/`CHAT_ENGINE` routes a chat turn
either through the OpenCode CLI adapter or the (unchanged) SDK tool loop."""

from __future__ import annotations

import pytest

from app.ai.chat_agent import ChatAgent
from app.ai.provider_config import (ProviderConfig, ProviderConfigError)
from app.ai.watcher_context_service import WatcherContextService
from app.services.auth import CurrentUser


class FakeRepo:
    def list_roles(self):
        return []


def _agent(tmp_path, engine="opencode", mock=False) -> ChatAgent:
    cfg = ProviderConfig(timeout_seconds=30, max_context_chars=6000, mock=mock,
                         default_provider="openrouter", engine=engine)
    ctx = WatcherContextService(db_path=tmp_path / "missing.db")   # empty context
    return ChatAgent(cfg, FakeRepo(), ctx)


def _user() -> CurrentUser:
    return CurrentUser(id="u1", username="alice", full_name="Alice",
                       role_name="viewer")


def test_engine_opencode_routes_through_cli(tmp_path, fake_opencode, monkeypatch):
    monkeypatch.setenv("FAKE_OPENCODE_MODE", "ok")
    r = _agent(tmp_path, engine="opencode").chat(_user(), "hello", session_id="s1")
    assert r.ok
    assert r.reply.startswith("FAKE-REPLY")
    assert r.provider.startswith("opencode:")


def test_env_chat_engine_overrides_yaml(tmp_path, fake_opencode, monkeypatch):
    monkeypatch.setenv("FAKE_OPENCODE_MODE", "ok")
    monkeypatch.setenv("CHAT_ENGINE", "opencode")
    r = _agent(tmp_path, engine="sdk").chat(_user(), "hello", session_id="s1")
    assert r.ok
    assert r.provider.startswith("opencode:")     # env won over ai.engine: sdk


def test_prompt_carries_watcher_context_and_question(tmp_path, fake_opencode,
                                                     monkeypatch):
    monkeypatch.setenv("FAKE_OPENCODE_MODE", "echo")   # CLI echoes the prompt back
    r = _agent(tmp_path).chat(_user(), "Có rule nào match không?", session_id="s1")
    assert r.ok
    assert "System role:" in r.reply
    # Empty DB -> the context service's "no result yet" block is still injected.
    assert "No watcher result is available yet" in r.reply
    assert "User question:\nCó rule nào match không?" in r.reply


def test_mock_mode_bypasses_cli(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENCODE_BIN", r"C:\does\not\exist.exe")   # would fail if hit
    r = _agent(tmp_path, mock=True).chat(_user(), "hello", session_id="s1")
    assert r.ok
    assert "[MOCK mode]" in r.reply


def test_cli_failure_maps_to_error_response(tmp_path, fake_opencode, monkeypatch):
    monkeypatch.setenv("FAKE_OPENCODE_MODE", "err")
    r = _agent(tmp_path).chat(_user(), "hello", session_id="s1")
    assert not r.ok
    assert r.retryable is True


# ---------- ai.engine parsing (fail fast at boot) ----------

def test_engine_default_is_sdk():
    cfg = ProviderConfig.from_app_config({"ai": {}})
    assert cfg.engine == "sdk"


def test_engine_opencode_parsed():
    cfg = ProviderConfig.from_app_config({"ai": {"engine": "OpenCode"}})
    assert cfg.engine == "opencode"


def test_engine_invalid_raises():
    with pytest.raises(ProviderConfigError):
        ProviderConfig.from_app_config({"ai": {"engine": "bogus"}})
