"""OpenCode CLI adapter (spec §11): run one chat turn through the `opencode` CLI
subprocess instead of calling a provider SDK directly.

Selected with `ai.engine: opencode` in config/rules.yaml, or dynamically with
env CHAT_ENGINE=opencode (same hot-swap pattern as PROVIDER). Responsibilities:

    * compose the prompt (system role + watcher context + history + question),
    * build the command  `opencode run --model <provider/model>`,
    * run it as a subprocess in a safe (empty) working directory with a timeout,
    * capture stdout, stderr and the exit code,
    * normalize everything into an AIResponse — this module never raises.

The prompt is sent on STDIN rather than as the last argv (the spec's
`opencode run --model X "<prompt>"` form): on Windows the npm `opencode.cmd`
shim re-parses argv through cmd.exe, which mangles multiline prompts, and argv
is capped at ~32k chars. Set OPENCODE_PROMPT_MODE=arg to force the argv form.

API keys are NOT passed by this adapter — the OpenCode CLI reads its own auth
store / env (`opencode auth login`), so the SDK-path `snap.usable()` key check
does not apply here.

Env knobs (all optional):
    OPENCODE_BIN          path to the opencode executable (default: PATH lookup)
    OPENCODE_MODEL        full `provider/model` override, e.g. azure/gpt-4o-mini
    OPENCODE_PROMPT_MODE  "stdin" (default) or "arg"
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import time

from app import config
from app.ai.models import (AIResponse, CONFIG_ERROR, PROVIDER_ERROR, TIMEOUT,
                           ChatMessage)
from app.ai.provider_config import ProviderConfig, ResolvedProvider

logger = logging.getLogger("screen_watcher.ai.opencode")

# Internal provider name -> opencode model prefix (opencode addresses models as
# `provider/model`; for openrouter the model id itself may contain another '/').
_MODEL_PREFIX = {
    "openai": "openai",
    "azure_openai": "azure",
    "openrouter": "openrouter",
    "local": "ollama",
}

_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")

# How many past turns to replay into the one-shot prompt (opencode run is
# stateless from our point of view — we keep the session history ourselves).
MAX_HISTORY_TURNS = 6

OUT_OF_SCOPE_REPLY = (
    "Câu hỏi này nằm ngoài phạm vi hỗ trợ của Tool Watcher Assistant. "
    "Vui lòng hỏi về kết quả giám sát, OCR, rule hoặc trạng thái hệ thống."
)

PROMPT_TEMPLATE = """System role:
Bạn là AI assistant hỗ trợ vận hành Tool Watcher.

Watcher context:
{context}
{history}
User question:
{message}

Instruction:
Trả lời ngắn gọn, dựa trên dữ liệu được cung cấp.
Nếu dữ liệu không đủ, nói rõ là chưa đủ dữ liệu.
Chỉ trả lời câu hỏi liên quan vận hành Tool Watcher (kết quả giám sát, OCR, rule, email, hệ thống).
Nếu câu hỏi ngoài phạm vi đó (ví dụ nấu ăn, thể thao, kiến thức chung), trả lời đúng một câu: "{out_of_scope}"
"""


def compose_prompt(message: str, ctx_block: str,
                   history: list[ChatMessage] | None = None) -> str:
    """Render the spec §11.3 prompt. `ctx_block` may be empty (context off)."""
    context = ctx_block.strip() or "(no watcher context provided)"
    hist_text = ""
    turns = [m for m in (history or [])
             if m.role in ("user", "assistant") and m.content][-MAX_HISTORY_TURNS:]
    if turns:
        lines = "\n".join(f"{'User' if m.role == 'user' else 'Assistant'}: {m.content}"
                          for m in turns)
        hist_text = f"\nConversation so far:\n{lines}\n"
    return PROMPT_TEMPLATE.format(context=context, history=hist_text, message=message,
                                  out_of_scope=OUT_OF_SCOPE_REPLY)


class OpenCodeAdapter:
    def __init__(self, cfg: ProviderConfig):
        self.cfg = cfg

    # ---- resolution helpers (env-driven, evaluated per request) ----
    @staticmethod
    def binary() -> str | None:
        exe = os.environ.get("OPENCODE_BIN", "").strip()
        return exe or shutil.which("opencode")

    @staticmethod
    def model_for(snap: ResolvedProvider) -> str:
        override = os.environ.get("OPENCODE_MODEL", "").strip()
        if override:
            return override
        prefix = _MODEL_PREFIX.get(snap.provider, snap.provider)
        return f"{prefix}/{snap.model}"

    @staticmethod
    def _workdir() -> str:
        """A dedicated empty directory so the CLI never runs inside the project
        (opencode scans its cwd for context/config)."""
        d = config.DATA_DIR / "opencode_workdir"
        d.mkdir(parents=True, exist_ok=True)
        return str(d)

    # ---- execution ----
    def run(self, prompt: str, snap: ResolvedProvider, session_id: str,
            ctx_used: bool) -> AIResponse:
        """Execute one `opencode run` and normalize the outcome. Never raises."""
        model = self.model_for(snap)
        provider = f"opencode:{snap.provider}"
        exe = self.binary()
        if not exe:
            return AIResponse.failure(
                CONFIG_ERROR,
                "OpenCode CLI is not installed (or set OPENCODE_BIN to its path).",
                model=model, provider=provider, session_id=session_id)

        cmd = [exe, "run", "--model", model]
        stdin_input: str | None = prompt
        if os.environ.get("OPENCODE_PROMPT_MODE", "").strip().lower() == "arg":
            cmd.append(prompt)
            stdin_input = None

        timeout = self.cfg.timeout_seconds
        logger.info("opencode RUN model=%s timeout=%ss bin=%s", model, timeout, exe)
        start = time.monotonic()
        try:
            proc = subprocess.run(
                cmd, input=stdin_input, cwd=self._workdir(),
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=timeout)
        except subprocess.TimeoutExpired:
            logger.warning("opencode TIMEOUT after %ss (model=%s)", timeout, model)
            return AIResponse.failure(
                TIMEOUT, "The AI request timed out. Please try again.",
                model=model, provider=provider, session_id=session_id)
        except FileNotFoundError:
            return AIResponse.failure(
                CONFIG_ERROR,
                f"OpenCode CLI executable not found: {exe}",
                model=model, provider=provider, session_id=session_id)
        except OSError as e:
            logger.warning("opencode failed to start: %s", e)
            return AIResponse.failure(
                CONFIG_ERROR, f"OpenCode CLI could not be started: {e}",
                model=model, provider=provider, session_id=session_id)

        latency = int((time.monotonic() - start) * 1000)
        stdout = _ANSI_RE.sub("", proc.stdout or "").strip()
        stderr = _ANSI_RE.sub("", proc.stderr or "").strip()

        if proc.returncode != 0:
            # Log the full stderr for diagnosis; return only its first line (FR10:
            # no raw dumps/stack traces to the client).
            logger.warning("opencode EXIT %d (%dms) stderr: %.600s",
                           proc.returncode, latency, stderr)
            first_line = (stderr.splitlines() or ["no error output"])[0][:200]
            return AIResponse.failure(
                PROVIDER_ERROR,
                f"OpenCode CLI failed (exit {proc.returncode}): {first_line}",
                model=model, provider=provider, session_id=session_id,
                latency_ms=latency)

        if not stdout:
            logger.warning("opencode exit 0 but EMPTY stdout (%dms)", latency)
            return AIResponse.failure(
                PROVIDER_ERROR, "OpenCode CLI returned an empty reply.",
                model=model, provider=provider, session_id=session_id,
                latency_ms=latency)

        logger.info("opencode REPLY (%dms, %d chars)", latency, len(stdout))
        return AIResponse.success(stdout, model=model, provider=provider,
                                  session_id=session_id,
                                  execution_context_used=ctx_used,
                                  latency_ms=latency)
