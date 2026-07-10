"""VoiceAlertService: provider routing, HF-TTS path, and graceful fallbacks.

The routing/fallback tests use no heavy ML deps (transformers is monkeypatched),
so they run everywhere. A real end-to-end synthesis test runs only when
transformers+torch are installed AND SW_TTS_REAL=1 (it downloads a model).
"""

from __future__ import annotations

import os
import wave

import pytest

from app.services import voice_alert_service as V
from app.services.voice_alert_service import VoiceAlertService


def test_disabled_returns_no_attempt():
    r = VoiceAlertService({"tts": {"enabled": False}}).alert()
    assert r.attempted is False and r.played is False


def test_transformers_success_path(monkeypatch):
    """provider=transformers + working synth -> played, no beep."""
    svc = VoiceAlertService({"tts": {"enabled": True, "provider": "transformers"}})
    monkeypatch.setattr(svc, "_synthesize_hf",
                        lambda text: V.VoiceAlertResult(True, True, f"HF spoke: {text[:10]}"))
    r = svc.alert(text="Cảnh báo hệ thống")
    assert r.attempted and r.played
    assert r.detail.startswith("HF spoke")


def test_transformers_failure_falls_back_to_beep(monkeypatch):
    svc = VoiceAlertService({"tts": {"enabled": True, "provider": "transformers",
                                     "fallback_beep": True}})

    def boom(text):
        raise RuntimeError("No module named 'torch'")

    monkeypatch.setattr(svc, "_synthesize_hf", boom)
    monkeypatch.setattr(svc, "_beep", lambda detail: V.VoiceAlertResult(True, True, detail))
    r = svc.alert(text="x")
    assert r.attempted and r.played
    assert "fallback beep" in r.detail


def test_transformers_failure_no_beep_when_disabled(monkeypatch):
    svc = VoiceAlertService({"tts": {"enabled": True, "provider": "transformers",
                                     "fallback_beep": False}})
    monkeypatch.setattr(svc, "_synthesize_hf",
                        lambda t: (_ for _ in ()).throw(RuntimeError("fail")))
    r = svc.alert(text="x")
    assert r.attempted and not r.played


def test_command_provider_path(monkeypatch):
    svc = VoiceAlertService({"tts": {"enabled": True, "provider": "huggingface_gguf",
                                     "command": ["echo", "{text}"]}})
    monkeypatch.setattr(svc, "_run_command",
                        lambda text: V.VoiceAlertResult(True, True, "ran command"))
    r = svc.alert(text="hello")
    assert r.played and r.detail == "ran command"


def test_no_provider_beeps(monkeypatch):
    svc = VoiceAlertService({"tts": {"enabled": True, "provider": "none",
                                     "fallback_beep": True}})
    monkeypatch.setattr(svc, "_beep", lambda detail: V.VoiceAlertResult(True, True, detail))
    r = svc.alert()
    assert r.played


def test_write_wav_is_valid_pcm16(tmp_path):
    np = pytest.importorskip("numpy")
    audio = (np.sin(np.linspace(0, 3.14 * 40, 16000)) * 0.5).astype("float32")
    path = VoiceAlertService._write_wav(audio, 16000)
    try:
        with wave.open(path, "rb") as w:
            assert w.getnchannels() == 1
            assert w.getsampwidth() == 2
            assert w.getframerate() == 16000
            assert w.getnframes() == 16000
    finally:
        os.remove(path)


@pytest.mark.skipif(not os.environ.get("SW_TTS_REAL"),
                    reason="set SW_TTS_REAL=1 to run the real HF model download+synth")
def test_real_hf_synthesis(tmp_path):
    pytest.importorskip("torch")
    pytest.importorskip("transformers")
    svc = VoiceAlertService({"tts": {"enabled": True, "provider": "transformers",
                                     "hf_model_id": "facebook/mms-tts-vie"}})
    monkeypatch_play = getattr(svc, "_play")
    svc._play = lambda path: True   # don't require an audio device in tests
    r = svc.alert(text="Xin chào, đây là cảnh báo hệ thống.")
    assert r.attempted and r.played
    assert "HF TTS" in r.detail
