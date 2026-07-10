"""Optional audible alert / Text-to-Speech service (offline, CPU-only).

Three ways to speak an alert, chosen by `tts.provider` in config/rules.yaml:

  * transformers   — REAL Hugging Face TTS via `transformers` (VITS/MMS-TTS).
                     Default model `facebook/mms-tts-vie` speaks Vietnamese, runs
                     on CPU, and works offline after the model is cached on first
                     use. This is the recommended local voice.
  * huggingface_gguf / command
                   — shell out to a user-provided runner for a local GGUF model
                     (e.g. VieNeu-TTS); placeholders {text}/{model_id}/{model_path}.
  * (any)          — if synthesis is unavailable or fails, fall back to a short
                     Windows beep so rule processing never blocks on TTS setup.

The heavy ML dependencies (torch/transformers) are NOT required to run the app;
they live in requirements-ml.txt and are imported lazily only when the
transformers provider is actually used.
"""

from __future__ import annotations

import logging
import os
import shlex
import subprocess
import sys
from dataclasses import dataclass

logger = logging.getLogger("screen_watcher.voice_alert")


DEFAULT_ALERT_TEXT = "anh ơi hệ thống chết toi rồi"
DEFAULT_MODEL_ID = "pnnbao-ump/VieNeu-TTS-0.3B-q4-gguf"
DEFAULT_HF_MODEL = "facebook/mms-tts-vie"   # Vietnamese VITS, CPU-friendly, offline after cache


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
        self.provider = str(tts.get("provider", "huggingface_gguf")).strip().lower()
        self.model_id = str(tts.get("model_id", DEFAULT_MODEL_ID))
        self.model_path = str(tts.get("model_path", "") or "")
        self.hf_model_id = str(tts.get("hf_model_id", DEFAULT_HF_MODEL))
        self.hf_cache_dir = str(tts.get("hf_cache_dir", "") or "") or None
        command = tts.get("command") or []
        self.command = shlex.split(command) if isinstance(command, str) else list(command)
        self.alert_text = str(tts.get("alert_text", DEFAULT_ALERT_TEXT))
        self.timeout_seconds = int(tts.get("timeout_seconds", 20))
        self.fallback_beep = bool(tts.get("fallback_beep", True))
        self._hf_model = None      # lazily loaded transformers model + tokenizer
        self._hf_tok = None

    def alert(self, severity: str = "", text: str | None = None) -> VoiceAlertResult:
        if not self.enabled:
            return VoiceAlertResult(False, False, "Voice alert disabled.")

        phrase = (text or self.alert_text).strip() or DEFAULT_ALERT_TEXT

        # 1) Real Hugging Face TTS (transformers).
        if self.provider in ("transformers", "huggingface", "hf"):
            try:
                return self._synthesize_hf(phrase)
            except Exception as e:
                logger.warning("HF TTS unavailable/failed (%s).", e)
                if self.fallback_beep:
                    return self._beep(f"HF TTS failed ({e}); used fallback beep.")
                return VoiceAlertResult(True, False, f"HF TTS failed: {e}")

        # 2) External command / GGUF runner.
        if self.command:
            return self._run_command(phrase)

        # 3) Fallback beep.
        if self.fallback_beep:
            return self._beep(
                f"No TTS runner configured for provider '{self.provider}'; used fallback beep.")
        detail = (f"No TTS runner configured. Set tts.provider=transformers (HF) or "
                  f"configure tts.command for {self.model_id}.")
        logger.info(detail)
        return VoiceAlertResult(True, False, detail)

    # ---------- Hugging Face transformers (VITS / MMS-TTS) ----------
    def _synthesize_hf(self, text: str) -> VoiceAlertResult:
        """Synthesize speech with a Hugging Face VITS model on CPU and play it.
        Raises if transformers/torch are not installed (caller handles fallback)."""
        import numpy as np
        import torch
        from transformers import AutoTokenizer, VitsModel

        if self._hf_model is None:
            logger.info("Loading HF TTS model '%s' (CPU, first load may download once)…",
                        self.hf_model_id)
            self._hf_model = VitsModel.from_pretrained(self.hf_model_id, cache_dir=self.hf_cache_dir)
            self._hf_tok = AutoTokenizer.from_pretrained(self.hf_model_id, cache_dir=self.hf_cache_dir)
            self._hf_model.to("cpu").eval()

        inputs = self._hf_tok(text, return_tensors="pt")
        with torch.no_grad():
            waveform = self._hf_model(**inputs).waveform  # (1, num_samples), float32
        audio = waveform.squeeze().cpu().numpy().astype("float32")
        sr = int(self._hf_model.config.sampling_rate)
        path = self._write_wav(audio, sr)
        played = self._play(path)
        secs = len(audio) / float(sr or 1)
        detail = f"HF TTS '{self.hf_model_id}' spoke {secs:.1f}s @ {sr} Hz"
        logger.info(detail)
        return VoiceAlertResult(True, played, detail)

    @staticmethod
    def _write_wav(audio, sample_rate: int) -> str:
        """Write a mono float waveform to a temp 16-bit PCM WAV (stdlib only)."""
        import tempfile
        import wave

        import numpy as np
        pcm = (np.clip(audio, -1.0, 1.0) * 32767.0).astype("<i2")
        fd, path = tempfile.mkstemp(suffix=".wav", prefix="sw_tts_")
        os.close(fd)
        with wave.open(path, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(int(sample_rate))
            w.writeframes(pcm.tobytes())
        return path

    def _play(self, path: str) -> bool:
        """Play a WAV file. Windows uses winsound; other OSes try aplay/afplay."""
        try:
            if sys.platform.startswith("win"):
                import winsound
                winsound.PlaySound(path, winsound.SND_FILENAME)
                return True
            player = "afplay" if sys.platform == "darwin" else "aplay"
            subprocess.run([player, path], check=True, timeout=self.timeout_seconds)
            return True
        except Exception as e:
            logger.warning("Could not play TTS audio (%s).", e)
            return False

    # ---------- external command runner (GGUF etc.) ----------
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
