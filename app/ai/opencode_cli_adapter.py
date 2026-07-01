"""OpenCode CLI adapter (C, T04): prompt -> subprocess `opencode run` -> AIResponse.

Design rules (see trung1234.md):
  * The ONLY place that touches the CLI.
  * Never raises to callers — every failure becomes an AIResponse with an error_code.
  * The prompt is passed on STDIN (not as an argv), so long multilingual OCR text
    cannot hit arg-length limits or shell-escaping problems (shell=False always).
  * Never logs secrets or the full prompt (only its length + model + latency).
  * Mock mode returns a canned reply so the feature is testable without a real provider.
"""

from __future__ import annotations

import logging
import subprocess
import time

from app.ai.models import (
    AIResponse,
    OPENCODE_ERROR,
    OPENCODE_NOT_FOUND,
    OPENCODE_TIMEOUT,
    BAD_WORKING_DIR,
)
from app.ai.provider_config import ProviderConfig

logger = logging.getLogger("screen_watcher.ai.opencode")


class OpenCodeCLIAdapter:
    def __init__(self, config: ProviderConfig, binary: str = "opencode"):
        self.cfg = config
        self.binary = binary

    def run(self, prompt: str) -> AIResponse:
        if self.cfg.mock:
            return self._mock(prompt)

        cmd = [self.binary, "run", "--model", self.cfg.model_full]
        # NOTE: prompt goes on stdin, never on argv -> no secrets/args on the process line.
        logger.info("opencode run model=%s prompt_len=%d cwd=%s",
                    self.cfg.model_full, len(prompt), self.cfg.working_dir)

        start = time.monotonic()
        try:
            proc = subprocess.run(
                cmd,
                input=prompt,
                capture_output=True,
                text=True,
                shell=False,
                cwd=self.cfg.working_dir,
                timeout=self.cfg.timeout_seconds,
            )
        except subprocess.TimeoutExpired:
            logger.warning("opencode timed out after %ss", self.cfg.timeout_seconds)
            return AIResponse.failure(
                OPENCODE_TIMEOUT,
                reply=f"AI request timed out after {self.cfg.timeout_seconds}s.",
            )
        except FileNotFoundError:
            logger.error("opencode binary not found: %r", self.binary)
            return AIResponse.failure(
                OPENCODE_NOT_FOUND,
                reply="OpenCode CLI is not installed or not on PATH.",
            )
        except NotADirectoryError:
            return AIResponse.failure(
                BAD_WORKING_DIR,
                reply=f"Working directory is invalid: {self.cfg.working_dir!r}.",
            )

        latency_ms = int((time.monotonic() - start) * 1000)

        if proc.returncode != 0:
            # stderr kept in `raw` for debugging only; not sent to the client.
            logger.warning("opencode exit=%s latency=%dms", proc.returncode, latency_ms)
            return AIResponse.failure(
                OPENCODE_ERROR,
                reply="AI provider returned an error.",
                raw=(proc.stderr or "").strip(),
            )

        logger.info("opencode ok latency=%dms reply_len=%d", latency_ms, len(proc.stdout or ""))
        return AIResponse.ok_reply((proc.stdout or "").strip(), latency_ms=latency_ms)

    def _mock(self, prompt: str) -> AIResponse:
        """Canned reply for demo/testing when no real provider is available."""
        reply = (
            "[MOCK] AI is running in mock mode (ai.mock=true). "
            f"Received a prompt of {len(prompt)} chars for model "
            f"'{self.cfg.model_full}'. Set ai.mock=false and configure "
            f"{self.cfg.env_var_name} to use a real provider."
        )
        return AIResponse.ok_reply(reply, latency_ms=0)
