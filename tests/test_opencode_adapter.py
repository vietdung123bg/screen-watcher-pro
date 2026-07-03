"""Unit tests for the OpenCode CLI adapter (spec §11).

Subprocess behavior (success / error exit / empty output / timeout / missing
binary) is exercised against the fake CLI from conftest — no real opencode, no
network. Command composition for the argv prompt mode is checked with a stubbed
subprocess.run.
"""

from __future__ import annotations

import subprocess
import time

import pytest

from app.ai import opencode_adapter as oa
from app.ai.models import CONFIG_ERROR, PROVIDER_ERROR, TIMEOUT, ChatMessage
from app.ai.opencode_adapter import OpenCodeAdapter, compose_prompt
from app.ai.provider_config import ProviderConfig, ResolvedProvider


def _snap(provider="azure_openai", model="gpt-4o-mini") -> ResolvedProvider:
    return ResolvedProvider(provider=provider, kind="azure", model=model,
                            api_key="", base_url=None, api_version="2024-06-01",
                            key_env="AZURE_OPENAI_API_KEY", key_optional=False)


def _adapter(timeout=30) -> OpenCodeAdapter:
    return OpenCodeAdapter(ProviderConfig(
        timeout_seconds=timeout, max_context_chars=6000, mock=False,
        default_provider="openrouter", engine="opencode"))


# ---------- prompt composition (spec §11.3) ----------

def test_compose_prompt_has_all_sections():
    p = compose_prompt("Máy có lỗi gì không?", "OCR text: ERROR 500\nMatched rules: r1")
    assert "System role:" in p
    assert "Bạn là AI assistant hỗ trợ vận hành Tool Watcher." in p
    assert "Watcher context:\nOCR text: ERROR 500" in p
    assert "User question:\nMáy có lỗi gì không?" in p
    assert "Instruction:" in p
    assert "Nếu dữ liệu không đủ, nói rõ là chưa đủ dữ liệu." in p


def test_compose_prompt_without_context():
    p = compose_prompt("hello", "")
    assert "(no watcher context provided)" in p


def test_compose_prompt_includes_recent_history_only():
    history = [ChatMessage(role="user", content=f"q{i}") for i in range(10)]
    p = compose_prompt("latest?", "ctx", history)
    assert "Conversation so far:" in p
    assert "User: q9" in p
    assert "User: q0" not in p           # older than MAX_HISTORY_TURNS is dropped


# ---------- model mapping ----------

@pytest.mark.parametrize("provider,model,expected", [
    ("azure_openai", "gpt-4o-mini", "azure/gpt-4o-mini"),
    ("openai", "gpt-4o-mini", "openai/gpt-4o-mini"),
    ("openrouter", "openai/gpt-4o-mini", "openrouter/openai/gpt-4o-mini"),
    ("local", "llama3.1", "ollama/llama3.1"),
])
def test_model_mapping(provider, model, expected):
    assert OpenCodeAdapter.model_for(_snap(provider, model)) == expected


def test_model_env_override_wins(monkeypatch):
    monkeypatch.setenv("OPENCODE_MODEL", "azure/my-deployment")
    assert OpenCodeAdapter.model_for(_snap("local", "llama3.1")) == "azure/my-deployment"


# ---------- subprocess execution against the fake CLI ----------

def test_run_success(fake_opencode, monkeypatch):
    monkeypatch.setenv("FAKE_OPENCODE_MODE", "ok")
    r = _adapter().run("hi", _snap(), session_id="s1", ctx_used=True)
    assert r.ok
    assert r.reply.startswith("FAKE-REPLY model=azure/gpt-4o-mini")
    assert r.provider == "opencode:azure_openai"
    assert r.execution_context_used is True
    assert r.latency_ms is not None
    assert r.session_id == "s1"


def test_run_passes_prompt_via_stdin(fake_opencode, monkeypatch):
    monkeypatch.setenv("FAKE_OPENCODE_MODE", "echo")
    prompt = "line one\nline two with \"quotes\" & <special> chars\ndòng ba tiếng Việt"
    r = _adapter().run(prompt, _snap(), session_id="s1", ctx_used=False)
    assert r.ok
    assert r.reply == prompt.strip()


def test_run_nonzero_exit_is_provider_error(fake_opencode, monkeypatch):
    monkeypatch.setenv("FAKE_OPENCODE_MODE", "err")
    r = _adapter().run("hi", _snap(), session_id="s1", ctx_used=False)
    assert not r.ok
    assert r.error_code == PROVIDER_ERROR
    assert r.retryable is True
    assert "exit 2" in r.message
    assert "AuthError" in r.message             # first stderr line is surfaced
    assert "frame.js" not in r.message          # internal frames are not leaked


def test_run_empty_stdout_is_provider_error(fake_opencode, monkeypatch):
    monkeypatch.setenv("FAKE_OPENCODE_MODE", "empty")
    r = _adapter().run("hi", _snap(), session_id="s1", ctx_used=False)
    assert not r.ok
    assert r.error_code == PROVIDER_ERROR
    assert "empty" in r.message.lower()


def test_run_timeout(fake_opencode, monkeypatch):
    monkeypatch.setenv("FAKE_OPENCODE_MODE", "sleep")   # fake sleeps 8s
    start = time.monotonic()
    r = _adapter(timeout=2).run("hi", _snap(), session_id="s1", ctx_used=False)
    assert not r.ok
    assert r.error_code == TIMEOUT
    assert r.retryable is True
    assert time.monotonic() - start < 15


def test_missing_binary_is_config_error(monkeypatch):
    monkeypatch.setenv("OPENCODE_BIN", r"C:\does\not\exist\opencode.exe")
    r = _adapter().run("hi", _snap(), session_id="s1", ctx_used=False)
    assert not r.ok
    assert r.error_code == CONFIG_ERROR


def test_not_installed_is_config_error(monkeypatch):
    monkeypatch.setattr(oa.shutil, "which", lambda _name: None)
    r = _adapter().run("hi", _snap(), session_id="s1", ctx_used=False)
    assert not r.ok
    assert r.error_code == CONFIG_ERROR
    assert "not installed" in r.message


# ---------- command composition (argv prompt mode, spec §11.2 literal form) ----------

def test_arg_prompt_mode_builds_spec_command(monkeypatch):
    monkeypatch.setenv("OPENCODE_BIN", "opencode-bin")
    monkeypatch.setenv("OPENCODE_PROMPT_MODE", "arg")
    seen = {}

    def fake_run(cmd, **kw):
        seen["cmd"], seen["input"] = cmd, kw.get("input")
        return subprocess.CompletedProcess(cmd, 0, stdout="ok reply", stderr="")

    monkeypatch.setattr(oa.subprocess, "run", fake_run)
    r = _adapter().run("<prompt>", _snap(), session_id="s1", ctx_used=False)
    assert r.ok and r.reply == "ok reply"
    assert seen["cmd"] == ["opencode-bin", "run", "--model", "azure/gpt-4o-mini", "<prompt>"]
    assert seen["input"] is None


def test_stdin_mode_omits_prompt_from_argv(monkeypatch):
    monkeypatch.setenv("OPENCODE_BIN", "opencode-bin")
    seen = {}

    def fake_run(cmd, **kw):
        seen["cmd"], seen["input"] = cmd, kw.get("input")
        return subprocess.CompletedProcess(cmd, 0, stdout="ok", stderr="")

    monkeypatch.setattr(oa.subprocess, "run", fake_run)
    _adapter().run("<prompt>", _snap(), session_id="s1", ctx_used=False)
    assert seen["cmd"] == ["opencode-bin", "run", "--model", "azure/gpt-4o-mini"]
    assert seen["input"] == "<prompt>"


def test_ansi_codes_are_stripped(monkeypatch):
    monkeypatch.setenv("OPENCODE_BIN", "opencode-bin")

    def fake_run(cmd, **kw):
        return subprocess.CompletedProcess(
            cmd, 0, stdout="\x1b[32mgreen reply\x1b[0m", stderr="")

    monkeypatch.setattr(oa.subprocess, "run", fake_run)
    r = _adapter().run("hi", _snap(), session_id="s1", ctx_used=False)
    assert r.reply == "green reply"
