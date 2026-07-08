"""Optional audible alert service.

The configured Hugging Face GGUF model is treated as a local runtime dependency:
the app stores model metadata and can call a configured command when available.
If no command is configured, the service falls back to a short Windows beep so
rule processing never blocks on TTS setup.
"""

from __future__ import annotations

import logging
import os
import shlex
import subprocess
from dataclasses import dataclass

logger = logging.getLogger("screen_watcher.voice_alert")


DEFAULT_ALERT_TEXT = "anh ơi hệ thống chết toi rồi"
DEFAULT_MODEL_ID = "pnnbao-ump/VieNeu-TTS-0.3B-q4-gguf"


@dataclass
class VoiceAlertResult:
    attempted: bool
    played: bool
    detail: str


class VoiceAlertService:
    def __init__(self, cfg: dict | None = None):
        cfg = cfg or {}
        tts = cfg.get("tts", {}) if isinstance(cfg.get("tts", {}), dict) else {}
        self.enabled = bool(tts.get("enabled", False))
        self.provider = str(tts.get("provider", "huggingface_gguf"))
        self.model_id = str(tts.get("model_id", DEFAULT_MODEL_ID))
        self.model_path = str(tts.get("model_path", "") or "")
        command = tts.get("command") or []
        self.command = shlex.split(command) if isinstance(command, str) else list(command)
        self.alert_text = str(tts.get("alert_text", DEFAULT_ALERT_TEXT))
        self.timeout_seconds = int(tts.get("timeout_seconds", 20))
        self.fallback_beep = bool(tts.get("fallback_beep", True))

    def alert(self, severity: str = "", text: str | None = None) -> VoiceAlertResult:
        if not self.enabled:
            return VoiceAlertResult(False, False, "Voice alert disabled.")

        phrase = (text or self.alert_text).strip() or DEFAULT_ALERT_TEXT
        if self.command:
            return self._run_command(phrase)

        if self.fallback_beep:
            return self._beep(
                f"No TTS command configured for {self.model_id}; used fallback beep."
            )
        detail = (
            f"No TTS command configured. Configure tts.command to run local model "
            f"{self.model_id}."
        )
        logger.info(detail)
        return VoiceAlertResult(True, False, detail)

    def _run_command(self, text: str) -> VoiceAlertResult:
        model_path = self.model_path or os.environ.get("VIENEU_TTS_MODEL_PATH", "")
        args = [
            str(part)
            .replace("{text}", text)
            .replace("{model_id}", self.model_id)
            .replace("{model_path}", model_path)
            for part in self.command
        ]
        try:
            subprocess.run(args, check=True, timeout=self.timeout_seconds)
            return VoiceAlertResult(True, True, f"Voice alert played via {args[0]}.")
        except Exception as e:
            logger.warning("Voice alert command failed: %s", e)
            if self.fallback_beep:
                return self._beep(f"Voice alert command failed ({e}); used fallback beep.")
            return VoiceAlertResult(True, False, f"Voice alert command failed: {e}")

    def _beep(self, detail: str) -> VoiceAlertResult:
        try:
            import winsound

            for freq in (880, 660, 880):
                winsound.Beep(freq, 180)
            logger.info(detail)
            return VoiceAlertResult(True, True, detail)
        except Exception as e:
            logger.warning("Fallback beep failed: %s", e)
            return VoiceAlertResult(True, False, f"{detail} Fallback beep failed: {e}")
