"""Shared AI data models. Kept provider-agnostic so the server and clients only
depend on this, never on the LLM SDK details."""

from __future__ import annotations

from dataclasses import dataclass, field

# ---- Result status / error codes ----
OK = "OK"
CONFIG_ERROR = "CONFIG_ERROR"        # missing API key / bad provider setup (set env & retry)
PROVIDER_ERROR = "PROVIDER_ERROR"    # LLM provider returned an error
TIMEOUT = "TIMEOUT"                  # request exceeded ai.timeout_seconds
RATE_LIMITED = "RATE_LIMITED"        # 429 from provider
TOOL_ERROR = "TOOL_ERROR"            # a tool the model called failed
INTERNAL_ERROR = "INTERNAL_ERROR"    # anything unexpected

# Which error codes are worth retrying (spec §10.3 `retryable`).
_RETRYABLE = {CONFIG_ERROR, PROVIDER_ERROR, TIMEOUT, RATE_LIMITED}


@dataclass
class AIResponse:
    """Uniform result of one chat turn.

    Serializes to the spec §10.2 (success) / §10.3 (error) shape via to_public_dict().
    """

    reply: str = ""
    ok: bool = True
    error_code: str = OK
    message: str = ""                  # human-readable error message (error case)
    latency_ms: int | None = None
    model: str = ""
    provider: str = ""
    session_id: str = ""
    execution_context_used: bool = False
    retryable: bool = False
    raw: str | None = None             # debug only — never sent to the client

    @classmethod
    def success(cls, reply: str, **kw) -> "AIResponse":
        return cls(reply=reply, ok=True, error_code=OK, **kw)

    @classmethod
    def failure(cls, error_code: str, message: str, **kw) -> "AIResponse":
        kw.setdefault("retryable", error_code in _RETRYABLE)
        return cls(ok=False, error_code=error_code, message=message, reply=message, **kw)

    def to_public_dict(self) -> dict:
        """What the HTTP layer returns. Drops `raw`; never leaks secrets."""
        if self.ok:
            return {
                "status": "success",
                "session_id": self.session_id,
                "reply": self.reply,
                "model": self.model,
                "provider": self.provider,
                "execution_context_used": self.execution_context_used,
                "latency_ms": self.latency_ms,
            }
        return {
            "status": "error",
            "session_id": self.session_id,
            "error_code": self.error_code,
            "message": self.message,
            "retryable": self.retryable,
            "model": self.model,
            "provider": self.provider,
        }


@dataclass
class ChatMessage:
    """One turn stored in the conversation store (F)."""

    role: str            # "user" | "assistant"
    content: str
    error_code: str = OK
    extra: dict = field(default_factory=dict)
