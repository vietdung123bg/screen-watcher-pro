"""Forced change-password screen, shown right after sign-in when the account
still has the must_change_password flag set (e.g. the default admin on first login)."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from app.context import AppContext
from app.ui import clear_widget


class ChangePasswordWindow:
    def __init__(self, root: tk.Tk, ctx: AppContext, on_success):
        self.root = root
        self.ctx = ctx
        self.on_success = on_success
        clear_widget(root)
        root.title("Screen Watcher Pro — Change password")
        root.geometry("440x400")
        self._build()

    def _build(self) -> None:
        frame = ttk.Frame(self.root, padding=24)
        frame.pack(expand=True, fill="both")

        ttk.Label(frame, text="Change your password",
                  font=("Segoe UI", 16, "bold")).pack(pady=(4, 2))
        ttk.Label(frame,
                  text="For security you must set a new password before continuing.",
                  foreground="#666", wraplength=380).pack(pady=(0, 16))

        ttk.Label(frame, text="Current password").pack(anchor="w")
        self.current = ttk.Entry(frame, show="•")
        self.current.pack(fill="x", pady=(0, 10))

        ttk.Label(frame, text="New password (min 6 characters)").pack(anchor="w")
        self.new1 = ttk.Entry(frame, show="•")
        self.new1.pack(fill="x", pady=(0, 10))

        ttk.Label(frame, text="Confirm new password").pack(anchor="w")
        self.new2 = ttk.Entry(frame, show="•")
        self.new2.pack(fill="x", pady=(0, 16))

        ttk.Button(frame, text="Update password", command=self._do_change).pack(fill="x")

        self.current.bind("<Return>", lambda _e: self.new1.focus_set())
        self.new1.bind("<Return>", lambda _e: self.new2.focus_set())
        self.new2.bind("<Return>", lambda _e: self._do_change())
        self.current.focus_set()

    def _do_change(self) -> None:
        new1 = self.new1.get()
        if new1 != self.new2.get():
            messagebox.showerror("Mismatch", "The new passwords do not match.")
            return
        try:
            self.ctx.auth.change_password(self.ctx.current_user, self.current.get(), new1)
        except ValueError as e:
            messagebox.showerror("Cannot change password", str(e))
            return
        except Exception as e:
            messagebox.showerror("Error", f"Unexpected error: {e}")
            return
        messagebox.showinfo("Done", "Your password has been updated.")
        self.on_success()
