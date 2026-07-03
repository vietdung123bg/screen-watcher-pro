"""Notebook chatbox client tests (spec §12 / FR06, testing strategy §18
"Notebook Test: gửi message và hiển thị reply").

Unit tests stub `requests` so no server is needed; the integration test boots
the REAL FastAPI server (uvicorn, mock AI, fresh temp DB) and drives the same
`login` / `send_message` functions the notebook uses, over real HTTP.
"""

from __future__ import annotations

import threading
import time

import pytest
import requests

from app.ai import chatbox


class _FakeResp:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {}
        self.headers = {"content-type": "application/json"}
        self.text = str(payload)

    def json(self):
        return self._payload


# ---------- unit: send_message ----------

def test_send_message_success(monkeypatch):
    seen = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        seen.update(url=url, json=json, headers=headers, timeout=timeout)
        return _FakeResp(200, {"status": "success", "reply": "Xin chào!"})

    monkeypatch.setattr(chatbox.requests, "post", fake_post)
    out = chatbox.send_message("http://x", "s1", "hello", token="tok")
    assert out == "Xin chào!"
    assert seen["url"] == "http://x/api/chat"
    assert seen["json"]["include_latest_watcher_context"] is True   # spec §12.2 default
    assert seen["headers"] == {"Authorization": "Bearer tok"}
    assert seen["timeout"] == 180                                    # spec §14: 120-180s


def test_send_message_can_disable_context(monkeypatch):
    seen = {}

    def fake_post(url, json=None, **kw):
        seen["json"] = json
        return _FakeResp(200, {"status": "success", "reply": "ok"})

    monkeypatch.setattr(chatbox.requests, "post", fake_post)
    chatbox.send_message("http://x", "s1", "hi", include_context=False)
    assert seen["json"]["include_latest_watcher_context"] is False


def test_send_message_shows_api_error_without_traceback(monkeypatch):
    monkeypatch.setattr(chatbox.requests, "post", lambda *a, **kw: _FakeResp(
        200, {"status": "error", "error_code": "TIMEOUT",
              "message": "The AI request timed out."}))
    out = chatbox.send_message("http://x", "s1", "hi")
    assert "TIMEOUT" in out and "timed out" in out
    assert "Traceback" not in out                                    # FR10


def test_send_message_connection_error_is_friendly(monkeypatch):
    def boom(*a, **kw):
        raise requests.ConnectionError("refused")

    monkeypatch.setattr(chatbox.requests, "post", boom)
    out = chatbox.send_message("http://x", "s1", "hi")
    assert "Cannot reach the server" in out


def test_send_message_timeout_is_friendly(monkeypatch):
    def slow(*a, **kw):
        raise requests.Timeout()

    monkeypatch.setattr(chatbox.requests, "post", slow)
    out = chatbox.send_message("http://x", "s1", "hi")
    assert "too long" in out


def test_send_message_401_hints_reauth(monkeypatch):
    monkeypatch.setattr(chatbox.requests, "post", lambda *a, **kw: _FakeResp(401, {}))
    out = chatbox.send_message("http://x", "s1", "hi")
    assert "Not authenticated" in out


# ---------- unit: login ----------

def test_login_returns_token(monkeypatch):
    monkeypatch.setattr(chatbox.requests, "post",
                        lambda *a, **kw: _FakeResp(200, {"access_token": "jwt123"}))
    assert chatbox.login("http://x", "admin", "admin123") == "jwt123"


def test_login_failure_raises(monkeypatch):
    monkeypatch.setattr(chatbox.requests, "post", lambda *a, **kw: _FakeResp(
        401, {"detail": {"message": "Invalid username or password."}}))
    with pytest.raises(RuntimeError, match="Login failed"):
        chatbox.login("http://x", "admin", "wrong")


# ---------- integration: real HTTP server (mock AI, temp DB) ----------

@pytest.fixture
def live_server(tmp_path, monkeypatch):
    """Boot the real FastAPI app with uvicorn on a spare port: fresh temp DB
    (seeded admin/admin123) and ai.mock=true so no provider is called."""
    import uvicorn

    monkeypatch.setattr("app.config.DB_PATH", tmp_path / "test.db")
    from app.ai.chat_server import create_app
    app = create_app({"ai": {"mock": True}})

    cfg = uvicorn.Config(app, host="127.0.0.1", port=8765, log_level="warning")
    server = uvicorn.Server(cfg)
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    deadline = time.monotonic() + 15
    while not server.started:
        if time.monotonic() > deadline:
            pytest.fail("uvicorn did not start within 15s")
        time.sleep(0.05)
    yield "http://127.0.0.1:8765"
    server.should_exit = True
    t.join(timeout=5)


def test_notebook_flow_end_to_end(live_server):
    """The exact flow the notebook runs: /health -> login -> chat -> latest."""
    base = live_server

    r = requests.get(f"{base}/health", timeout=10)                   # FR01
    assert r.status_code == 200 and r.json()["status"] == "ok"

    token = chatbox.login(base, "admin", "admin123")                 # JWT auth
    assert token

    reply = chatbox.send_message(base, None, "Trạng thái watcher gần nhất là gì?",
                                 token=token)                        # FR02/FR06
    assert "[MOCK mode]" in reply                                    # mock AI answered

    r = requests.get(f"{base}/api/watcher/executions/latest",        # FR07
                     headers={"Authorization": f"Bearer {token}"}, timeout=10)
    assert r.status_code == 200
    assert r.json()["has_data"] is False                             # fresh DB: no runs yet


def test_wrong_password_rejected(live_server):
    with pytest.raises(RuntimeError, match="Login failed"):
        chatbox.login(live_server, "admin", "wrong-password")


def test_client_generated_uuid_session_accepted(live_server):
    """Regression: the widget generates its session id client-side — it must be
    a real UUID (the server 422s on things like 'nb-1a2b3c4d') and the same id
    must keep working across turns (conversation continuity)."""
    import uuid

    token = chatbox.login(live_server, "admin", "admin123")
    sid = str(uuid.uuid4())
    r1 = chatbox.send_message(live_server, sid, "hello", token=token)
    r2 = chatbox.send_message(live_server, sid, "again", token=token)
    assert "[MOCK mode]" in r1
    assert "[MOCK mode]" in r2
