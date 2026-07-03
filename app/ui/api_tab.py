"""API server tab: start/stop the FastAPI (uvicorn) server from inside the app.

Runs the server as a child process so it is fully isolated from the Tk GUI
(single worker — the chat conversation store is in-memory). The process is
terminated automatically when the app exits.
"""

from __future__ import annotations

import atexit
import subprocess
import sys
import tkinter as tk
import webbrowser
from tkinter import ttk

from app import config

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000


class ApiServerTab(ttk.Frame):
    def __init__(self, master, ctx):
        super().__init__(master, padding=16)
        self.ctx = ctx
        self.proc: subprocess.Popen | None = None
        self._build()
        atexit.register(self._kill)          # never leave the server running after exit
        # Auto-start together with the app: the user never has to press Start.
        # After a manual Stop (or a crash) the Start button re-enables so they can
        # restart it — see _refresh_state(). Deferred so the UI is realized first.
        self.after(400, self._autostart)
        self._poll()

    # ---------- UI ----------
    def _build(self) -> None:
        ttk.Label(self, text="AI Chat & Watcher API server",
                  font=("Segoe UI", 13, "bold")).pack(anchor="w")
        ttk.Label(
            self,
            text="The FastAPI server (REST API: JWT auth, AI chat, watcher) starts "
                 "automatically with the app — no need to press Start. Use Stop to shut it "
                 "down; Start becomes available again to bring it back up. "
                 "Runs a single worker and shares this app's database.",
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
        self.start_btn = ttk.Button(btns, text="▶  Start server", command=self._start)
        self.start_btn.pack(side="left")
        self.stop_btn = ttk.Button(btns, text="■  Stop", command=self._stop, state="disabled")
        self.stop_btn.pack(side="left", padx=6)
        self.docs_btn = ttk.Button(btns, text="🌐  Open API docs", command=self._open_docs,
                                   state="disabled")
        self.docs_btn.pack(side="left", padx=6)

        self.status = ttk.Label(self, text="○  Stopped", foreground="#a00",
                                font=("Segoe UI", 11, "bold"))
        self.status.pack(anchor="w", pady=(8, 4))
        self.url_lbl = ttk.Label(self, text="", foreground="#06c")
        self.url_lbl.pack(anchor="w")

        ttk.Label(
            self,
            text="Default login: admin / admin123. Open Swagger UI at /docs — click Authorize "
                 "and paste the access_token from POST /api/auth/login.",
            foreground="#888", wraplength=760, justify="left",
        ).pack(anchor="w", pady=(14, 0))

    # ---------- actions ----------
    def _base_url(self) -> str:
        return f"http://{self.host_var.get().strip()}:{self.port_var.get().strip()}"

    def _autostart(self) -> None:
        """Bring the server up on app launch (best-effort; user can retry via Start)."""
        if not self._running():
            self._start(auto=True)

    def _start(self, auto: bool = False) -> None:
        if self.proc and self.proc.poll() is None:
            return
        port = self.port_var.get().strip()
        if not port.isdigit():
            self.status.config(text="✗  Invalid port", foreground="#a00")
            return
        config.ensure_dirs()
        log_path = config.LOG_DIR / "api_server.log"
        try:
            self._log = open(log_path, "a", encoding="utf-8")
            self.proc = subprocess.Popen(
                [sys.executable, "-m", "uvicorn", "app.ai.chat_server:app",
                 "--host", self.host_var.get().strip(), "--port", port, "--workers", "1"],
                cwd=str(config.BASE_DIR),
                stdout=self._log, stderr=subprocess.STDOUT,
            )
        except Exception as e:
            self.status.config(text=f"✗  Failed to start: {e}", foreground="#a00")
            return
        self.ctx.repo.add_audit(self.ctx.current_user.id,
                                "api.autostart" if auto else "api.start", self._base_url())
        self._refresh_state()

    def _stop(self) -> None:
        self._kill()
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

    def _open_docs(self) -> None:
        webbrowser.open(f"{self._base_url()}/docs")

    # ---------- status ----------
    def _running(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def _refresh_state(self) -> None:
        if self._running():
            self.status.config(text="●  Running", foreground="#0a0")
            self.url_lbl.config(text=f"{self._base_url()}   (docs: {self._base_url()}/docs)")
            self.start_btn.config(state="disabled")
            self.stop_btn.config(state="normal")
            self.docs_btn.config(state="normal")
        else:
            self.status.config(text="○  Stopped", foreground="#a00")
            self.url_lbl.config(text="")
            self.start_btn.config(state="normal")
            self.stop_btn.config(state="disabled")
            self.docs_btn.config(state="disabled")

    def _poll(self) -> None:
        # Detect a server that died on its own and reset the buttons.
        self._refresh_state()
        self.after(1500, self._poll)
