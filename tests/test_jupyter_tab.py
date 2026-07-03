"""Unit tests for the Jupyter tab launch/URL helpers (no Tk, no real Jupyter)."""

from __future__ import annotations

from app.ui.jupyter_tab import build_command, notebook_url


def test_build_command_uses_no_browser_and_binds_host_port():
    cmd = build_command("py.exe", r"C:\proj\notebooks\chatbox.ipynb", "127.0.0.1", "8888")
    assert cmd[:4] == ["py.exe", "-m", "jupyter", "notebook"]
    assert r"C:\proj\notebooks\chatbox.ipynb" in cmd
    assert "--no-browser" in cmd
    assert "--ip=127.0.0.1" in cmd
    assert "--port=8888" in cmd


def test_notebook_url_preserves_token_and_targets_the_notebook():
    server = "http://127.0.0.1:8888/tree?token=deadbeef1234"
    url = notebook_url(server, "chatbox.ipynb")
    assert url == "http://127.0.0.1:8888/notebooks/chatbox.ipynb?token=deadbeef1234"


def test_notebook_url_without_token():
    url = notebook_url("http://127.0.0.1:8890/lab", "chatbox.ipynb")
    assert url == "http://127.0.0.1:8890/notebooks/chatbox.ipynb"


def test_notebook_url_preserves_localhost_host_and_port():
    url = notebook_url("http://localhost:9999/tree?token=abc", "chatbox.ipynb")
    assert url == "http://localhost:9999/notebooks/chatbox.ipynb?token=abc"
