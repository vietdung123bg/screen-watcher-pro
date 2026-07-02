"""Jupyter chatbox client (G, FR06, T06): a lightweight chat UI that POSTs to
/chat and shows the reply. Contains NO AI logic — it only does HTTP + display.

Usage in a notebook cell:
    from app.ai.chatbox import launch_chatbox
    launch_chatbox("http://127.0.0.1:8000")

If ipywidgets is unavailable/broken, it falls back to an input() REPL loop.
"""

from __future__ import annotations

import uuid

import requests

DEFAULT_BASE_URL = "http://127.0.0.1:8000"
REQUEST_TIMEOUT = 90


def _friendly_error(exc: Exception) -> str:
    if isinstance(exc, requests.ConnectionError):
        return ("⚠ Cannot reach the chat server. Is it running? "
                "Start it with: uvicorn app.ai.chat_server:app --port 8000 --workers 1")
    if isinstance(exc, requests.Timeout):
        return "⚠ The server took too long to respond (timeout)."
    return f"⚠ Request error: {exc}"


def send_message(base_url: str, session_id: str, message: str) -> str:
    """POST /chat and return a display string (reply or a friendly error)."""
    try:
        resp = requests.post(
            f"{base_url.rstrip('/')}/chat",
            json={"message": message, "session_id": session_id},
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException as exc:
        return _friendly_error(exc)

    if resp.status_code != 200:
        return f"⚠ Server returned HTTP {resp.status_code}: {resp.text[:200]}"

    data = resp.json()
    if not data.get("ok", False):
        # Surface the error_code, not a traceback.
        return f"⚠ AI error ({data.get('error_code')}): {data.get('reply', '')}"
    return data.get("reply", "")


def launch_chatbox(base_url: str = DEFAULT_BASE_URL, session_id: str | None = None):
    """Render the ipywidgets chat UI. Falls back to a text REPL on failure."""
    session_id = session_id or f"nb-{uuid.uuid4().hex[:8]}"
    try:
        import ipywidgets as widgets  # noqa: F401
        from IPython.display import display
    except Exception:
        print("ipywidgets not available — falling back to text input loop.")
        return _repl_fallback(base_url, session_id)

    history = widgets.HTML(value="<i>Ask something about the latest watcher result…</i>")
    box = widgets.Text(placeholder="Type a message and press Enter / Send")
    send_btn = widgets.Button(description="Send", button_style="primary")
    log: list[str] = []

    def _on_send(_=None):
        text = box.value.strip()
        if not text:
            return
        box.value = ""
        log.append(f"<b>You:</b> {text}")
        history.value = "<br>".join(log) + "<br><i>…thinking…</i>"
        reply = send_message(base_url, session_id, text)
        log.append(f"<b>AI:</b> {reply}")
        history.value = "<br>".join(log)

    send_btn.on_click(_on_send)
    box.on_submit(_on_send)  # Enter key
    display(widgets.VBox([history, widgets.HBox([box, send_btn])]))


def _repl_fallback(base_url: str, session_id: str) -> None:
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
        print("AI:", send_message(base_url, session_id, text))
