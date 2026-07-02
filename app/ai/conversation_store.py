"""Conversation store (F, FR09 — Could): chat history per session_id.

MVP: in-memory dict. The interface (append / get_history / clear) is kept small
so a SQLite-backed store with a retention policy can drop in later without
touching callers.

Assumption: the server runs a SINGLE worker. An in-memory dict is NOT shared
across uvicorn workers — run `--workers 1` for the MVP, or switch to SQLite.
"""

from __future__ import annotations

import threading

from app.ai.models import ChatMessage

# Bound history so a long-lived session can't grow without limit (simple retention).
MAX_MESSAGES_PER_SESSION = 50


class ConversationStore:
    def __init__(self, max_messages: int = MAX_MESSAGES_PER_SESSION):
        self._sessions: dict[str, list[ChatMessage]] = {}
        self._max = max_messages
        self._lock = threading.Lock()

    def append(self, session_id: str, message: ChatMessage) -> None:
        with self._lock:
            history = self._sessions.setdefault(session_id, [])
            history.append(message)
            if len(history) > self._max:
                # Drop the oldest, keep the most recent `_max` turns.
                del history[: len(history) - self._max]

    def get_history(self, session_id: str) -> list[ChatMessage]:
        with self._lock:
            return list(self._sessions.get(session_id, []))

    def clear(self, session_id: str) -> None:
        with self._lock:
            self._sessions.pop(session_id, None)
