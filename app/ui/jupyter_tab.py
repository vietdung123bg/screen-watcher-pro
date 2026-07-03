"""Jupyter Notebook tab: launch the Jupyter chatbox notebook from inside the app.

Starts `jupyter notebook` as a child process (isolated from the Tk GUI) serving
`notebooks/chatbox.ipynb` — the lightweight web client that talks to the REST API
(which auto-starts on the API Server tab). The Jupyter server URL (with its login
token) is scraped from the server log so the "Open notebook" button lands the user
straight on the chatbox. The process is terminated automatically when the app exits.
"""

from __future__ import annotations

import atexit
import re
import subprocess
import sys
import tkinter as tk
import webbrowser
from tkinter import ttk
from urllib.parse import parse_qs, urlsplit

from app import config

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8888
NOTEBOOK_REL = "notebooks/chatbox.ipynb"

# The line Jupyter prints once the server is up, e.g.
#   http://127.0.0.1:8888/tree?token=abcd...
_URL_RE = re.compile(r"http://(?:127\.0\.0\.1|localhost):\d+/\S*")
# Hints in the log that Jupyter itself is not installed / failed to import.
_MISSING_RE = re.compile(r"No module named|is not a Jupyter command|not recognized",
                         re.IGNORECASE)


def build_command(python_exe: str, notebook_path: str, host: str, port: str) -> list[str]:
    """The argv to launch the Jupyter server (no auto-browser — we open it ourselves)."""
    return [python_exe, "-m", "jupyter", "notebook", notebook_path,
            "--no-browser", f"--ip={host}", f"--port={port}"]


def notebook_url(server_url: str, notebook_rel: str) -> str:
    """Turn a scraped Jupyter server URL into one that opens a specific notebook,
    preserving the auth token. Falls back to the server URL if parsing fails."""
    try:
        parts = urlsplit(server_url)
        token = parse_qs(parts.query).get("token", [""])[0]
        q = f"?token={token}" if token else ""
        return f"{parts.scheme}://{parts.netloc}/notebooks/{notebook_rel}{q}"
    except Exception:
        return server_url


class JupyterTab(ttk.Frame):
    def __init__(self, master, ctx):
        super().__init__(master, padding=16)
        self.ctx = ctx
        self.proc: subprocess.Popen | None = None
        self._log = None
        self._log_path = None
        self._url: str | None = None          # scraped Jupyter server URL (with token)
        self._build()
        atexit.register(self._kill)           # never leave the server running after exit
        self._poll()

    # ---------- UI ----------
    def _build(self) -> None:
        ttk.Label(self, text="Jupyter Notebook — chatbox client",
                  font=("Segoe UI", 13, "bold")).pack(anchor="w")
        ttk.Label(
            self,
            text="Start a Jupyter server for notebooks/chatbox.ipynb — the notebook web "
                 "client that chats with the REST API (the API Server auto-starts on its "
                 "tab). Press Start, then Open notebook. Stop shuts the server down; it also "
                 "closes automatically when you exit the app.",
            foreground="#666", wraplength=760, justify="left",
        ).pack(anchor="w", pady=(2, 12))

        row = ttk.Frame(self)
        row.pack(fill="x", pady=4)
        ttk.Label(row, text="Host:").pack(side="left")
        self.host_var = tk.StringVar(value=DEFAULT_HOST)
        ttk.Entry(row, textvariable=self.host_var, width=14).pack(side="left", padx=(4, 12))
        ttk.Label(row, text="Port:").pack(side="left")
        self.port_var = tk.StringVar(value=str(DEFAULT_PORT))
        ttk.Entry(row, textvariable=self.port_var, width=7).pack(side="left", padx=4)

        btns = ttk.Frame(self)
        btns.pack(fill="x", pady=12)
        self.start_btn = ttk.Button(btns, text="▶  Start Jupyter", command=self._start)
        self.start_btn.pack(side="left")
        self.stop_btn = ttk.Button(btns, text="■  Stop", command=self._stop, state="disabled")
        self.stop_btn.pack(side="left", padx=6)
        self.open_btn = ttk.Button(btns, text="📓  Open notebook", command=self._open,
                                   state="disabled")
        self.open_btn.pack(side="left", padx=6)

        self.status = ttk.Label(self, text="○  Stopped", foreground="#a00",
                                font=("Segoe UI", 11, "bold"))
        self.status.pack(anchor="w", pady=(8, 4))
        self.url_lbl = ttk.Label(self, text="", foreground="#06c")
        self.url_lbl.pack(anchor="w")

        ttk.Label(
            self,
            text="Requires Jupyter (pip install notebook). In the notebook: log in as "
                 "admin / admin123, then run the cells to chat with the watcher API.",
            foreground="#888", wraplength=760, justify="left",
        ).pack(anchor="w", pady=(14, 0))

    # ---------- actions ----------
    def _notebook_path(self):
        return config.BASE_DIR / NOTEBOOK_REL

    def _start(self) -> None:
        if self._running():
            return
        port = self.port_var.get().strip()
        if not port.isdigit():
            self.status.config(text="✗  Invalid port", foreground="#a00")
            return
        nb = self._notebook_path()
        if not nb.exists():
            self.status.config(text=f"✗  Notebook not found: {NOTEBOOK_REL}", foreground="#a00")
            return
        config.ensure_dirs()
        self._url = None
        self._log_path = config.LOG_DIR / "jupyter.log"
        try:
            self._log = open(self._log_path, "w", encoding="utf-8")
            self.proc = subprocess.Popen(
                build_command(sys.executable, str(nb), self.host_var.get().strip(), port),
                cwd=str(config.BASE_DIR),
                stdout=self._log, stderr=subprocess.STDOUT,
            )
        except Exception as e:
            self.status.config(text=f"✗  Failed to start: {e}", foreground="#a00")
            return
        self.ctx.repo.add_audit(self.ctx.current_user.id, "jupyter.start", str(nb))
        self.status.config(text="●  Starting… (waiting for Jupyter URL)", foreground="#a60")
        self._refresh_state()

    def _stop(self) -> None:
        self._kill()
        self._url = None
        self._refresh_state()

    def _kill(self) -> None:
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.terminate()
                self.proc.wait(timeout=5)
            except Exception:
                try:
                    self.proc.kill()
                except Exception:
                    pass
        self.proc = None
        try:
            self._log.close()
        except Exception:
            pass

    def _open(self) -> None:
        if self._url:
            webbrowser.open(notebook_url(self._url, "chatbox.ipynb"))

    # ---------- status ----------
    def _running(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def _scan_log(self) -> None:
        """Scrape the Jupyter server URL (and detect a missing-Jupyter failure)."""
        if self._url or not self._log_path or not self._log_path.exists():
            return
        try:
            text = self._log_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return
        m = _URL_RE.search(text)
        if m:
            self._url = m.group(0)
        elif not self._running() and _MISSING_RE.search(text):
            self.status.config(
                text="✗  Jupyter is not installed — run: pip install notebook",
                foreground="#a00")

    def _refresh_state(self) -> None:
        self._scan_log()
        if self._running():
            self.stop_btn.config(state="normal")
            self.start_btn.config(state="disabled")
            if self._url:
                self.status.config(text="●  Running", foreground="#0a0")
                self.url_lbl.config(text=notebook_url(self._url, "chatbox.ipynb"))
                self.open_btn.config(state="normal")
            else:
                self.status.config(text="●  Starting… (waiting for Jupyter URL)",
                                   foreground="#a60")
                self.open_btn.config(state="disabled")
        else:
            # Keep a "not installed" message if _scan_log set one.
            if "not installed" not in self.status.cget("text"):
                self.status.config(text="○  Stopped", foreground="#a00")
            self.url_lbl.config(text="")
            self.start_btn.config(state="normal")
            self.stop_btn.config(state="disabled")
            self.open_btn.config(state="disabled")

    def _poll(self) -> None:
        self._refresh_state()
        self.after(1500, self._poll)
