"""Shared AI data models. Kept provider-agnostic so the server and the client
only ever depend on this, never on subprocess/CLI details."""

from __future__ import annotations

from dataclasses import dataclass, field


# ---- Error codes returned by the CLI adapter (C). ----
# The adapter NEVER raises to callers; every failure is one of these codes.
OK = "OK"
OPENCODE_TIMEOUT = "OPENCODE_TIMEOUT"        # subprocess exceeded the timeout
OPENCODE_NOT_FOUND = "OPENCODE_NOT_FOUND"    # `opencode` binary is not installed / not on PATH
OPENCODE_ERROR = "OPENCODE_ERROR"            # CLI ran but exited non-zero
BAD_WORKING_DIR = "BAD_WORKING_DIR"          # ai.working_dir is missing / not a directory


@dataclass
class AIResponse:
    """Uniform result of one AI turn. `ok=False` -> read `error_code`."""

    reply: str
    ok: bool = True
    error_code: str = OK
    latency_ms: int | None = None
    raw: str | None = None          # raw stderr/stdout, for debugging only (never shown to user)

    @classmethod
    def ok_reply(cls, reply: str, latency_ms: int | None = None) -> "AIResponse":
        return cls(reply=reply, ok=True, error_code=OK, latency_ms=latency_ms)

    @classmethod
    def failure(cls, error_code: str, reply: str = "", raw: str | None = None) -> "AIResponse":
        return cls(reply=reply, ok=False, error_code=error_code, raw=raw)

    def to_public_dict(self) -> dict:
        """What the HTTP layer sends to the client. Deliberately drops `raw`
        (may contain internal paths / stderr) and never leaks secrets."""
        return {
            "reply": self.reply,
            "ok": self.ok,
            "error_code": self.error_code,
            "latency_ms": self.latency_ms,
        }


@dataclass
class ChatRequest:
    """Body of POST /chat."""

    message: str
    session_id: str = "default"


@dataclass
class ChatMessage:
    """One turn stored in the conversation store (F)."""

    role: str            # "user" | "assistant"
    content: str
    error_code: str = OK
    extra: dict = field(default_factory=dict)
