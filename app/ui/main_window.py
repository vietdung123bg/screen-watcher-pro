"""Main window after sign-in — contains tabs based on permissions."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from app.context import AppContext
from app.ui import clear_widget
from app.ui.api_tab import ApiServerTab
from app.ui.capture_tab import CaptureTab
from app.ui.chatbot_tab import ChatbotTab
from app.ui.emails_tab import EmailsTab
from app.ui.history_tab import HistoryTab
from app.ui.jupyter_tab import JupyterTab
from app.ui.rules_tab import RulesTab
from app.ui.users_tab import UsersTab


class MainWindow:
    def __init__(self, root: tk.Tk, ctx: AppContext, on_logout):
        self.root = root
        self.ctx = ctx
        self.on_logout = on_logout
        clear_widget(root)
        user = ctx.current_user
        root.title(f"Screen Watcher — {user.username} ({user.role_name})")
        root.geometry("1040x720")
        self._build()

    def _build(self) -> None:
        user = self.ctx.current_user

        # Title bar
        header = ttk.Frame(self.root, padding=(14, 10))
        header.pack(fill="x")
        ttk.Label(header, text="Screen Watcher", font=("Segoe UI", 14, "bold")).pack(side="left")
        ttk.Label(header,
                  text=f"   {user.full_name}  •  role: {user.role_name}",
                  foreground="#666").pack(side="left")
        ttk.Button(header, text="Sign out", command=self.on_logout).pack(side="right")

        ttk.Separator(self.root, orient="horizontal").pack(fill="x")

        # Notebook tab
        nb = ttk.Notebook(self.root)
        nb.pack(fill="both", expand=True, padx=8, pady=8)

        history = HistoryTab(nb, self.ctx)
        emails = EmailsTab(nb, self.ctx) if user.can("rule.view") else None

        def _after_capture() -> None:
            history.refresh()
            if emails is not None:
                emails.refresh()

        if user.can("capture.run"):
            capture = CaptureTab(nb, self.ctx, on_done=_after_capture)
            nb.add(capture, text="  📸  Capture & OCR  ")

        if user.can("screenshot.view"):
            nb.add(history, text="  🗂  History & Results  ")

        if user.can("rule.view"):
            nb.add(RulesTab(nb, self.ctx), text="  ⚙  Rules & Email  ")
            nb.add(emails, text="  📧  Sent Emails  ")

        # AI assistant — available to every signed-in user (tools respect their role)
        nb.add(ChatbotTab(nb, self.ctx), text="  💬  Chatbot  ")

        if user.can("user.manage"):
            nb.add(UsersTab(nb, self.ctx), text="  👥  User Management  ")

        # API server control (admin only — starts the REST API for external clients)
        if user.can("user.manage"):
            nb.add(ApiServerTab(nb, self.ctx), text="  🚀  API Server  ")

        # Jupyter notebook chatbox client (admin only — launches a local Jupyter server)
        if user.can("user.manage"):
            nb.add(JupyterTab(nb, self.ctx), text="  📓  Jupyter  ")

        # If no tab (no permissions) show a notice
        if not nb.tabs():
            ttk.Label(nb, text="Your account has no permissions assigned.",
                      padding=40).pack()
