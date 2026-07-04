"""Engine switching in ChatAgent: `ai.engine`/`CHAT_ENGINE` routes a chat turn
either through the OpenCode CLI adapter or the (unchanged) SDK tool loop."""

from __future__ import annotations

import types

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


# ---------- SDK streaming path (fake OpenAI streaming client, no network) ----------

def _chunk(content=None, tool_calls=None, reasoning=None):
    delta = types.SimpleNamespace(content=content, tool_calls=tool_calls,
                                  reasoning_content=reasoning)
    return types.SimpleNamespace(choices=[types.SimpleNamespace(delta=delta)], usage=None)


def _tc(index, id=None, name=None, args=None):
    return types.SimpleNamespace(index=index, id=id,
                                 function=types.SimpleNamespace(name=name, arguments=args))


class _FakeStreamClient:
    """Mimics client.chat.completions.create(stream=True) with scripted rounds."""

    def __init__(self, scripts):
        self._scripts = scripts
        self.calls = 0
        outer = self

        class _Comp:
            def create(self, **kw):
                assert kw.get("stream") is True, "streaming loop must pass stream=True"
                script = outer._scripts[outer.calls]
                outer.calls += 1
                return iter(script)

        self.chat = types.SimpleNamespace(completions=_Comp())


def _sdk_agent(tmp_path, monkeypatch, scripts) -> ChatAgent:
    monkeypatch.setenv("OPENROUTER_API_KEY", "dummy")     # make snap.usable() True
    cfg = ProviderConfig(timeout_seconds=30, max_context_chars=6000, mock=False,
                         default_provider="openrouter", engine="sdk")
    ctx = WatcherContextService(db_path=tmp_path / "missing.db")
    agent = ChatAgent(cfg, FakeRepo(), ctx)
    agent._build_client = lambda snap: _FakeStreamClient(scripts)   # bypass real openai
    return agent


def _two_round_scripts():
    """Round 1: a tool call split across chunks. Round 2: the final answer tokens."""
    return [
        [_chunk(tool_calls=[_tc(0, id="c1", name="get_latest_watcher_result", args="")]),
         _chunk(tool_calls=[_tc(0, args="{}")])],
        [_chunk(reasoning="thinking… "), _chunk(content="Latest "), _chunk(content="result: none.")],
    ]


def test_sdk_streaming_assembles_reply_and_forwards_events(tmp_path, monkeypatch):
    agent = _sdk_agent(tmp_path, monkeypatch, _two_round_scripts())
    events = []
    r = agent.chat(_user(), "latest?", session_id="s1",
                   on_event=lambda ev: events.append(ev))
    assert r.ok
    assert r.reply == "Latest result: none."           # assembled from streamed tokens
    kinds = [e[0] for e in events]
    assert "tool_call" in kinds and "tool_result" in kinds
    assert "thinking" in kinds                          # reasoning channel surfaced
    assert "".join(p for k, p in events if k == "delta") == "Latest result: none."
    assert kinds[-1] == "final"


def test_sdk_streaming_single_round_no_tools(tmp_path, monkeypatch):
    scripts = [[_chunk(content="hi "), _chunk(content="there")]]
    agent = _sdk_agent(tmp_path, monkeypatch, scripts)
    r = agent.chat(_user(), "hello", session_id="s1")
    assert r.ok and r.reply == "hi there"


def test_chat_stream_yields_ordered_events(tmp_path, monkeypatch):
    agent = _sdk_agent(tmp_path, monkeypatch, _two_round_scripts())
    evs = list(agent.chat_stream(_user(), "latest?", session_id="s2"))
    kinds = [e[0] for e in evs]
    assert kinds[0] == "meta"                           # metadata first
    assert "tool_call" in kinds and "tool_result" in kinds and "delta" in kinds
    assert [p for k, p in evs if k == "final"][-1] == "Latest result: none."


def test_sdk_batches_multiple_tool_calls_in_one_step(tmp_path, monkeypatch):
    """A step with 2 tool calls executes BOTH (concurrently) then continues in one
    follow-up LLM call — request batching."""
    scripts = [
        [_chunk(tool_calls=[_tc(0, id="c1", name="get_latest_watcher_result", args="{}")]),
         _chunk(tool_calls=[_tc(1, id="c2", name="get_alert_recipients", args="{}")])],
        [_chunk(content="ok")],
    ]
    agent = _sdk_agent(tmp_path, monkeypatch, scripts)
    events = []
    r = agent.chat(_user(), "status?", session_id="s", on_event=lambda e: events.append(e))
    assert r.ok and r.reply == "ok"
    called = [p["name"] for k, p in events if k == "tool_call"]
    results = [p["name"] for k, p in events if k == "tool_result"]
    assert called == ["get_latest_watcher_result", "get_alert_recipients"]
    assert len(results) == 2                       # both tools ran and returned


def test_mock_chat_stream_emits_final(tmp_path, monkeypatch):
    """Mock mode still yields a usable stream (one delta + final) for SSE clients."""
    agent = _agent(tmp_path, engine="sdk", mock=True)
    evs = list(agent.chat_stream(_user(), "hi", session_id="s1"))
    kinds = [e[0] for e in evs]
    assert kinds[0] == "meta" and kinds[-1] == "final"
    assert "[MOCK mode]" in [p for k, p in evs if k == "final"][-1]


# ---------- get_alert_recipients tool ----------

def test_get_alert_recipients_reads_config(tmp_path, monkeypatch):
    """The tool answers 'which email receives alerts?' from config/rules.yaml."""
    yaml_text = (
        "rules:\n"
        "  - id: r1\n"
        "    name: Err\n"
        "    owner_group: ops\n"
        "    severity: high\n"
        "owners:\n"
        "  ops:\n"
        "    emails: [ops@example.com, oncall@example.com]\n"
        "email:\n"
        "  enabled: true\n"
        "  from: sender@example.com\n"
    )
    p = tmp_path / "rules.yaml"
    p.write_text(yaml_text, encoding="utf-8")
    monkeypatch.setattr("app.config.RULES_YAML", p)

    out = _agent(tmp_path, mock=True)._t_get_alert_recipients(_user())
    assert out["email_enabled"] is True
    assert out["email_from"] == "sender@example.com"
    assert out["owner_groups"]["ops"] == ["ops@example.com", "oncall@example.com"]
    assert out["all_recipient_emails"] == ["oncall@example.com", "ops@example.com"]
    assert out["rules"][0]["owner_group"] == "ops"
    assert out["rules"][0]["recipients"] == ["ops@example.com", "oncall@example.com"]
