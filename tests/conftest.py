"""Shared fixtures for the AI-chat tests.

The real `opencode` CLI is NOT required: `fake_opencode` installs a tiny Python
script behind a platform launcher (.cmd on Windows, shell script elsewhere) and
points env OPENCODE_BIN at it. Its behavior is selected with env
FAKE_OPENCODE_MODE: ok | echo | err | empty | sleep.
"""

from __future__ import annotations

import os
import stat
import sys

import pytest

# The fake CLI. Mirrors the adapter's contract:
#   argv: run --model <model> [prompt]   (prompt on stdin when not in argv)
FAKE_SCRIPT = """\
import os, sys, time

args = sys.argv[1:]                      # ["run", "--model", model, (prompt)]
model = args[2] if len(args) > 2 else "?"
prompt = args[3] if len(args) > 3 else sys.stdin.read()
mode = os.environ.get("FAKE_OPENCODE_MODE", "ok")

if mode == "ok":
    sys.stdout.write(f"FAKE-REPLY model={model} prompt_chars={len(prompt)}")
elif mode == "echo":
    sys.stdout.write(prompt)
elif mode == "err":
    sys.stderr.write("AuthError: no credentials configured for this provider\\n")
    sys.stderr.write("  at some/internal/frame.js:42\\n")
    sys.exit(2)
elif mode == "empty":
    pass
elif mode == "sleep":
    time.sleep(8)
    sys.stdout.write("too late")
sys.exit(0)
"""


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch, tmp_path):
    """Keep tests independent of the developer's real env/config:
    clear the adapter's env knobs and redirect DATA_DIR to a temp dir so the
    safe workdir is never created inside the project."""
    for var in ("OPENCODE_BIN", "OPENCODE_MODEL", "OPENCODE_PROMPT_MODE",
                "CHAT_ENGINE", "FAKE_OPENCODE_MODE"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr("app.config.DATA_DIR", tmp_path / "data")


@pytest.fixture
def fake_opencode(tmp_path, monkeypatch):
    """Install the fake `opencode` executable and point OPENCODE_BIN at it."""
    script = tmp_path / "fake_opencode.py"
    script.write_text(FAKE_SCRIPT, encoding="utf-8")
    if os.name == "nt":
        launcher = tmp_path / "opencode.cmd"
        launcher.write_text(f'@"{sys.executable}" "{script}" %*\r\n', encoding="utf-8")
    else:
        launcher = tmp_path / "opencode"
        launcher.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{script}" "$@"\n',
                            encoding="utf-8")
        launcher.chmod(launcher.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("OPENCODE_BIN", str(launcher))
    return launcher
