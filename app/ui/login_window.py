"""Sign-in screen."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from app.context import AppContext
from app.ui import clear_widget


class LoginWindow:
    def __init__(self, root: tk.Tk, ctx: AppContext, on_success):
        self.root = root
        self.ctx = ctx
        self.on_success = on_success
        clear_widget(root)
        root.title("Screen Watcher Pro — Sign in")
        root.geometry("420x340")
        self._build()

    def _build(self) -> None:
        frame = ttk.Frame(self.root, padding=24)
        frame.pack(expand=True, fill="both")

        ttk.Label(frame, text="Screen Watcher Pro", font=("Segoe UI", 18, "bold")).pack(pady=(8, 2))
        ttk.Label(frame, text="Screenshot + OCR + Rule Engine + Email alerts",
                  foreground="#666").pack(pady=(0, 18))

        ttk.Label(frame, text="Username").pack(anchor="w")
        self.username = ttk.Entry(frame)
        self.username.pack(fill="x", pady=(0, 10))
        self.username.insert(0, "admin")

        ttk.Label(frame, text="Password").pack(anchor="w")
        self.password = ttk.Entry(frame, show="•")
        self.password.pack(fill="x", pady=(0, 16))

        btn = ttk.Button(frame, text="Sign in", command=self._do_login)
        btn.pack(fill="x")

        hint = ttk.Label(frame, text="Default: admin / admin123",
                         foreground="#999", font=("Segoe UI", 8))
        hint.pack(pady=(12, 0))

        self.password.bind("<Return>", lambda _e: self._do_login())
        self.username.bind("<Return>", lambda _e: self.password.focus_set())
        self.password.focus_set()

    def _do_login(self) -> None:
        try:
            user = self.ctx.auth.login(self.username.get(), self.password.get())
        except ValueError as e:
            messagebox.showerror("Sign-in failed", str(e))
            return
        except Exception as e:
            messagebox.showerror("Error", f"Unexpected error: {e}")
            return
        self.ctx.current_user = user
        self.on_success()
