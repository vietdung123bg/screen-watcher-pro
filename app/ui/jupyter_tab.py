"""Jupyter Notebook tab: launch the Jupyter chatbox notebook from inside the app.

Starts `jupyter notebook` as a child process (isolated from the Tk GUI) serving
`notebooks/chatbox.ipynb` — the lightweight web client that talks to the REST API
(which auto-starts on the API Server tab). The Jupyter server URL (with its login
token) is scraped from the server log so the "Open notebook" button lands the user
straight on the chatbox. The process is terminated automatically when the app exits.
"""

from __future__ import annotations

import atexit
import importlib.util
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
WEBVIEW_TITLE = "Jupyter — Screen Watcher Pro"

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


def build_webview_command(python_exe: str, url: str, title: str = WEBVIEW_TITLE) -> list[str]:
    """argv to open the app-managed WebView2 window (a separate process)."""
    return [python_exe, "-m", "app.ui.jupyter_webview", url, title]


def has_pywebview() -> bool:
    """True when pywebview is importable (the app can embed the Jupyter UI)."""
    return importlib.util.find_spec("webview") is not None


class JupyterTab(ttk.Frame):
    def __init__(self, master, ctx):
        super().__init__(master, padding=16)
        self.ctx = ctx
        self.proc: subprocess.Popen | None = None
        self.view_proc: subprocess.Popen | None = None   # app-managed WebView2 window
        self._log = None
        self._log_path = None
        self._url: str | None = None          # scraped Jupyter server URL (with token)
        self._auto_opened = False             # open the app window once per server start
        self._build()
        atexit.register(self._kill)           # never leave the server running after exit
        # Auto-start together with the app (like the API Server tab): the notebook
        # comes up and opens in the app window without pressing Start. After a manual
        # Stop the Start button re-enables. Deferred so the UI is realized first.
        self.after(700, self._autostart)
        self._poll()

    # ---------- UI ----------
    def _build(self) -> None:
        ttk.Label(self, text="Jupyter Notebook — chatbox client",
                  font=("Segoe UI", 13, "bold")).pack(anchor="w")
        ttk.Label(
            self,
            text="Start a Jupyter server for notebooks/chatbox.ipynb — the notebook web "
                 "client that chats with the REST API (the API Server auto-starts on its "
                 "tab). Press Start and the notebook opens in an app-managed window "
                 "(WebView2). Stop shuts the server + window down; both also close "
                 "automatically when you exit the app.",
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
        self.open_btn = ttk.Button(btns, text="📓  Open in app", command=self._open_in_app,
                                   state="disabled")
        self.open_btn.pack(side="left", padx=6)
        self.browser_btn = ttk.Button(btns, text="🌐  Browser", command=self._open_browser,
                                      state="disabled")
        self.browser_btn.pack(side="left", padx=6)

        self.status = ttk.Label(self, text="○  Stopped", foreground="#a00",
                                font=("Segoe UI", 11, "bold"))
        self.status.pack(anchor="w", pady=(8, 4))
        self.url_lbl = ttk.Label(self, text="", foreground="#06c")
        self.url_lbl.pack(anchor="w")

        ttk.Label(
            self,
            text="Requires Jupyter (pip install notebook) and, for the in-app window, "
                 "pywebview (pip install pywebview). Without pywebview the notebook opens "
                 "in your default browser instead. In the notebook: log in as admin / "
                 "admin123, then run the cells to chat with the watcher API.",
            foreground="#888", wraplength=760, justify="left",
        ).pack(anchor="w", pady=(14, 0))

    # ---------- actions ----------
    def _notebook_path(self):
        return config.BASE_DIR / NOTEBOOK_REL

    def _autostart(self) -> None:
        """Bring Jupyter up on app launch (best-effort; user can retry via Start)."""
        if not self._running():
            self._start()

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
        self._auto_opened = False
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

    @staticmethod
    def _terminate(proc: subprocess.Popen | None) -> None:
        if proc and proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass

    def _kill(self) -> None:
        self._terminate(self.view_proc)          # close the app-managed window first
        self.view_proc = None
        self._terminate(self.proc)               # then the Jupyter server
        self.proc = None
        try:
            self._log.close()
        except Exception:
            pass

    def _view_running(self) -> bool:
        return self.view_proc is not None and self.view_proc.poll() is None

    def _open_in_app(self) -> None:
        """Open (or re-open) the notebook in the app-managed WebView2 window."""
        if not self._url:
            return
        url = notebook_url(self._url, "chatbox.ipynb")
        if not has_pywebview():
            # No embedded engine available — fall back to the external browser.
            self.status.config(
                text="ℹ  pywebview not installed — opened in browser (pip install pywebview)",
                foreground="#a60")
            webbrowser.open(url)
            return
        if self._view_running():
            return                                # window already open
        try:
            self.view_proc = subprocess.Popen(
                build_webview_command(sys.executable, url),
                cwd=str(config.BASE_DIR))
        except Exception as e:
            self.status.config(text=f"✗  Cannot open app window: {e}", foreground="#a00")

    def _open_browser(self) -> None:
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
                self.browser_btn.config(state="normal")
                # Open the app-managed window once, as soon as the URL is known.
                if not self._auto_opened:
                    self._auto_opened = True
                    self._open_in_app()
            else:
                self.status.config(text="●  Starting… (waiting for Jupyter URL)",
                                   foreground="#a60")
                self.open_btn.config(state="disabled")
                self.browser_btn.config(state="disabled")
        else:
            # Keep a "not installed" message if _scan_log set one.
            if "not installed" not in self.status.cget("text"):
                self.status.config(text="○  Stopped", foreground="#a00")
            self.url_lbl.config(text="")
            self.start_btn.config(state="normal")
            self.stop_btn.config(state="disabled")
            self.open_btn.config(state="disabled")
            self.browser_btn.config(state="disabled")

    def _poll(self) -> None:
        self._refresh_state()
        self.after(1500, self._poll)
