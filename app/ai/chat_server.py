"""Chat server: FastAPI app exposing POST /chat.

The backbone that C, D, E and F plug into:
  D provider_config  -> validated at STARTUP (fail fast; server won't boot on bad config)
  E watcher_context  -> latest OCR/rule/email data injected into every prompt
  F conversation_store -> per-session history
  C opencode adapter -> runs the CLI, returns AIResponse

Run (single worker — see conversation_store.py):
    uvicorn app.ai.chat_server:app --host 127.0.0.1 --port 8000 --workers 1
"""

from __future__ import annotations

import logging

from fastapi import FastAPI
from pydantic import BaseModel

from app import config
from app.ai.conversation_store import ConversationStore
from app.ai.models import AIResponse, ChatMessage, OK
from app.ai.opencode_cli_adapter import OpenCodeCLIAdapter
from app.ai.provider_config import ProviderConfig
from app.ai.watcher_context_service import WatcherContextService

logger = logging.getLogger("screen_watcher.ai.server")

SYSTEM_PREAMBLE = (
    "You are the assistant of Screen Watcher Pro. Answer the user's question using "
    "the latest watcher result below (OCR text + matched rules + email decisions). "
    "If the answer is not in the context, say so plainly. Be concise."
)


class ChatBody(BaseModel):
    message: str
    session_id: str = "default"


def build_prompt(context_block: str, history: list[ChatMessage], message: str) -> str:
    parts = [SYSTEM_PREAMBLE, "", "=== LATEST WATCHER RESULT ===", context_block, ""]
    if history:
        parts.append("=== CONVERSATION SO FAR ===")
        for m in history:
            parts.append(f"{m.role}: {m.content}")
        parts.append("")
    parts.append("=== USER QUESTION ===")
    parts.append(message)
    return "\n".join(parts)


def create_app(app_config: dict | None = None) -> FastAPI:
    """App factory. Validates provider config eagerly (fail fast)."""
    app_config = app_config if app_config is not None else config.load_app_config()

    # D: fail fast — raises ProviderConfigError if the config is wrong.
    provider = ProviderConfig.from_app_config(app_config)
    logger.info("AI provider config OK: %s", provider.safe_summary())

    adapter = OpenCodeCLIAdapter(provider)
    context_service = WatcherContextService()
    store = ConversationStore()

    app = FastAPI(title="Screen Watcher Pro — AI Chat")

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "provider": provider.safe_summary()}

    @app.post("/chat")
    def chat(body: ChatBody) -> dict:
        history = store.get_history(body.session_id)
        context = context_service.latest()
        prompt = build_prompt(context.to_prompt_block(), history, body.message)

        result: AIResponse = adapter.run(prompt)

        # Record the turn (user + assistant) so the next request has context.
        store.append(body.session_id, ChatMessage("user", body.message))
        store.append(
            body.session_id,
            ChatMessage("assistant", result.reply, error_code=result.error_code),
        )
        return result.to_public_dict()

    return app


# Module-level app for `uvicorn app.ai.chat_server:app`.
# Import-time creation makes a bad provider config fail the server boot (fail fast).
app = create_app()
