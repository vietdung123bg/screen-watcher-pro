"""Jupyter chatbox client (G, FR06, T06): a lightweight chat UI that logs in,
then POSTs to /api/chat and shows the reply. Contains NO AI logic — it only does
HTTP + display.

Usage in a notebook cell:
    from app.ai.chatbox import launch_chatbox
    launch_chatbox("http://127.0.0.1:8000", username="admin", password="admin123")

The API requires a JWT: launch_chatbox() logs in (username/password) to obtain a
token, or you can pass an existing token=... directly.
If ipywidgets is unavailable/broken, it falls back to an input() REPL loop.
"""

from __future__ import annotations

import uuid

import requests

DEFAULT_BASE_URL = "http://127.0.0.1:8000"
REQUEST_TIMEOUT = 180        # spec §12.2/§14: AI turns may take up to 120-180s


def _friendly_error(exc: Exception) -> str:
    if isinstance(exc, requests.ConnectionError):
        return ("⚠ Cannot reach the server. Is it running? "
                "Start it with: uvicorn app.ai.chat_server:app --port 8000 --workers 1")
    if isinstance(exc, requests.Timeout):
        return "⚠ The server took too long to respond (timeout)."
    return f"⚠ Request error: {exc}"


def login(base_url: str, username: str, password: str) -> str:
    """POST /api/auth/login and return the JWT access token. Raises on failure."""
    resp = requests.post(
        f"{base_url.rstrip('/')}/api/auth/login",
        json={"username": username, "password": password},
        timeout=REQUEST_TIMEOUT,
    )
    if resp.status_code != 200:
        detail = resp.json().get("detail", {}) if resp.headers.get(
            "content-type", "").startswith("application/json") else {}
        msg = detail.get("message", resp.text[:200]) if isinstance(detail, dict) else resp.text[:200]
        raise RuntimeError(f"Login failed (HTTP {resp.status_code}): {msg}")
    return resp.json()["access_token"]


def send_message(base_url: str, session_id: str, message: str,
                 token: str | None = None, include_context: bool = True) -> str:
    """POST /api/chat and return a display string (reply or a friendly error).

    include_context (spec §12.2 `include_latest_watcher_context`, default True):
    ask the server to inject the latest watcher result into the AI prompt.
    """
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    try:
        resp = requests.post(
            f"{base_url.rstrip('/')}/api/chat",
            json={"message": message, "session_id": session_id,
                  "include_latest_watcher_context": include_context},
            headers=headers,
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException as exc:
        return _friendly_error(exc)

    if resp.status_code == 401:
        return "⚠ Not authenticated (token missing/expired). Re-run launch_chatbox to log in."
    if resp.status_code != 200:
        return f"⚠ Server returned HTTP {resp.status_code}: {resp.text[:200]}"

    data = resp.json()
    if data.get("status") == "success":
        return data.get("reply", "")
    # Surface the error_code + message, not a traceback.
    return f"⚠ AI error ({data.get('error_code')}): {data.get('message', '')}"


def launch_chatbox(base_url: str = DEFAULT_BASE_URL, session_id: str | None = None,
                   token: str | None = None, username: str | None = None,
                   password: str | None = None):
    """Render the ipywidgets chat UI. Falls back to a text REPL on failure.

    Auth: pass an existing `token`, OR `username`/`password` to log in automatically.
    """
    # Must be a real UUID: the server validates session_id and starts a new
    # conversation for a UUID it has not seen yet.
    session_id = session_id or str(uuid.uuid4())

    if token is None and username and password:
        try:
            token = login(base_url, username, password)
        except (requests.RequestException, RuntimeError) as exc:
            print(f"⚠ Could not log in: {exc}")
            return

    try:
        import ipywidgets as widgets  # noqa: F401
        from IPython.display import display
    except Exception:
        print("ipywidgets not available — falling back to text input loop.")
        return _repl_fallback(base_url, session_id, token)

    if token is None:
        print("⚠ No token — pass username/password (or token) to launch_chatbox to authenticate.")

    history = widgets.HTML(value="<i>Ask something about the latest watcher result…</i>")
    box = widgets.Text(placeholder="Type a message and press Enter / Send")
    send_btn = widgets.Button(description="Send", button_style="primary")
    ctx_toggle = widgets.Checkbox(value=True, indent=False,
                                  description="Include latest watcher context")
    log: list[str] = []

    def _on_send(_=None):
        text = box.value.strip()
        if not text:
            return
        box.value = ""
        log.append(f"<b>You:</b> {text}")
        history.value = "<br>".join(log) + "<br><i>…thinking…</i>"
        reply = send_message(base_url, session_id, text, token,
                             include_context=ctx_toggle.value)
        log.append(f"<b>AI:</b> {reply}")
        history.value = "<br>".join(log)

    send_btn.on_click(_on_send)
    box.on_submit(_on_send)  # Enter key
    display(widgets.VBox([history, widgets.HBox([box, send_btn]), ctx_toggle]))


def _repl_fallback(base_url: str, session_id: str, token: str | None = None) -> None:
    print(f"Chatbox (text mode). Server: {base_url}. Type 'exit' to quit.")
    while True:
        try:
            text = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if text.lower() in {"exit", "quit"}:
            break
        if not text:
            continue
        print("AI:", send_message(base_url, session_id, text, token))
