"""Conversation store (FR09) — SQLite-backed, per user.

Persists chatbot conversations across restarts and processes (the API server and
the desktop tab share the same DB). Designed for heavy write volume:
  * only the user message + final assistant reply are stored (never tool/system chatter),
  * one turn = 2 inserts + 1 counter bump in a single transaction (repo.record_chat_turn),
  * context for the next prompt loads only the last N turns (not the whole history),
  * sessions carry denormalized counters + JSON metadata (provider/model/latency).
"""

from __future__ import annotations

from app.ai.models import OK, ChatMessage

# How many past messages to load as context for the next prompt (kept small on purpose).
CONTEXT_MESSAGES = 20


class ChatStore:
    def __init__(self, repo):
        self.repo = repo

    def ensure_session(self, user_id: str, session_id: str | None,
                       first_message: str = "") -> str:
        """Resolve the session id for this turn:
          * no session_id            -> create a new session (server-generated UUID),
          * UUID not in the DB        -> create a NEW session WITH that UUID (client-supplied),
          * UUID owned by the user    -> reuse it,
          * UUID owned by someone else / deleted -> PermissionError (caller returns 403).
        session_id must already be a valid UUID (validated at the API layer)."""
        title = (first_message or "New chat").strip()[:60] or "New chat"
        if not session_id:
            return self.repo.create_chat_session(user_id, title)
        s = self.repo.get_chat_session(session_id)
        if s is None:
            return self.repo.create_chat_session(user_id, title, session_id=session_id)
        if s["deleted_at"] or s["user_id"] != user_id:
            raise PermissionError("session not accessible")
        return session_id

    def recent(self, session_id: str, limit: int = CONTEXT_MESSAGES) -> list[ChatMessage]:
        """Last `limit` messages (chronological) to feed the model as context."""
        rows = self.repo.list_chat_messages(session_id, limit=limit, newest_first=True)
        return [ChatMessage(r["role"], r["content"], error_code=r["error_code"] or OK)
                for r in reversed(rows)]

    def record(self, session_id: str, user_id: str, user_text: str, result) -> None:
        """Persist one user+assistant turn with assistant metadata."""
        meta = {"model": result.model, "provider": result.provider,
                "latency_ms": result.latency_ms,
                "execution_context_used": result.execution_context_used}
        self.repo.record_chat_turn(session_id, user_id, user_text, result.reply,
                                   error_code=result.error_code, metadata=meta)
