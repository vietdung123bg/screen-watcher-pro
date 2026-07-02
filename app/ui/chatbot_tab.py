"""Chatbot tab: chat with the AI assistant from inside the desktop app.

Available to every signed-in user (user & admin). The assistant runs in-process
using the same ChatAgent as the REST API, so tools act with THIS user's permissions
(e.g. only an admin can soft-delete a user via chat). The LLM call runs on a
background thread so the UI never freezes.
"""

from __future__ import annotations

import threading
import tkinter as tk
from tkinter import ttk

from app.ai.chat_agent import ChatAgent
from app.ai.conversation_store import ChatStore
from app.ai.models import ChatMessage
from app.ai.provider_config import ProviderConfig
from app.ai.watcher_context_service import WatcherContextService


class ChatbotTab(ttk.Frame):
    def __init__(self, master, ctx):
        super().__init__(master, padding=10)
        self.ctx = ctx
        self._history: list[ChatMessage] = []
        self._busy = False
        self._agent = self._build_agent()
        self._store = ChatStore(ctx.repo)     # persist this conversation per user
        self._session_id: str | None = None
        self._build()

    def _build_agent(self) -> ChatAgent:
        provider = ProviderConfig.from_app_config(self.ctx.app_config)

        def capture_fn(user_id, targets, launch=False):
            results = self.ctx.capture_service.capture_targets(user_id, targets, launch=launch)
            return [{"target": r.target, "status": r.status, "execution_id": r.screenshot_id,
                     "char_count": r.char_count, "error": r.error} for r in results]

        return ChatAgent(provider, self.ctx.repo, WatcherContextService(), capture_fn=capture_fn)

    # ---------- UI ----------
    def _build(self) -> None:
        header = ttk.Frame(self)
        header.pack(fill="x")
        ttk.Label(header, text="AI Assistant", font=("Segoe UI", 13, "bold")).pack(side="left")
        ttk.Button(header, text="🆕  New chat", command=self._new_session).pack(side="right")
        self.provider_lbl = ttk.Label(header, text="", foreground="#888")
        self.provider_lbl.pack(side="right", padx=(0, 12))

        ttk.Label(
            self,
            text="Ask about the latest watcher result, executions or your account. "
                 "The assistant can act on the database within YOUR permissions.",
            foreground="#666", wraplength=780, justify="left",
        ).pack(anchor="w", pady=(2, 8))
        self._refresh_provider()

        self.view = tk.Text(self, wrap="word", height=20, state="disabled",
                            font=("Segoe UI", 11), background="#fafafa")
        self.view.pack(fill="both", expand=True)
        self.view.tag_configure("you", foreground="#06c", font=("Segoe UI", 11, "bold"))
        self.view.tag_configure("ai", foreground="#0a7", font=("Segoe UI", 11, "bold"))
        self.view.tag_configure("err", foreground="#a00")

        row = ttk.Frame(self)
        row.pack(fill="x", pady=(8, 0))
        self.entry = ttk.Entry(row)
        self.entry.pack(side="left", fill="x", expand=True)
        self.entry.bind("<Return>", lambda _e: self._send())
        self.send_btn = ttk.Button(row, text="Send", command=self._send)
        self.send_btn.pack(side="left", padx=(6, 0))

        self._append("ai", "Assistant", "Hi! How can I help with your watcher data today?")

    def _append(self, tag: str, who: str, text: str) -> None:
        self.view.config(state="normal")
        self.view.insert("end", f"{who}: ", tag)
        self.view.insert("end", text + "\n\n")
        self.view.config(state="disabled")
        self.view.see("end")

    def _refresh_provider(self) -> None:
        """Show the provider + model currently selected (resolved live from .env)."""
        try:
            snap = self._agent.cfg.resolve()
            txt = f"Provider: {snap.provider} · Model: {snap.model}"
            if self._agent.cfg.mock:
                txt += " (mock)"
        except Exception:
            txt = ""
        self.provider_lbl.config(text=txt)

    def _new_session(self) -> None:
        """Start a fresh conversation (new session on next send)."""
        if self._busy:
            return
        self._session_id = None
        self._history = []
        self.view.config(state="normal")
        self.view.delete("1.0", "end")
        self.view.config(state="disabled")
        self._refresh_provider()          # provider may have changed in .env
        self._append("ai", "Assistant", "Started a new conversation. How can I help?")

    # ---------- send ----------
    def _send(self) -> None:
        if self._busy:
            return
        text = self.entry.get().strip()
        if not text:
            return
        self.entry.delete(0, "end")
        self._append("you", "You", text)
        self._busy = True
        self.send_btn.config(state="disabled")
        self._append("ai", "Assistant", "…thinking…")
        threading.Thread(target=self._run, args=(text,), daemon=True).start()

    def _run(self, text: str) -> None:
        user = self.ctx.current_user
        try:
            if self._session_id is None:
                self._session_id = self._store.ensure_session(user.id, None, text)
            result = self._agent.chat(user, text, session_id=self._session_id,
                                      history=self._history)
            # Persist the turn (best-effort; never break the UI on a store error).
            try:
                self._store.record(self._session_id, user.id, text, result)
            except Exception:
                pass
        except Exception as e:  # never crash the UI thread
            result = None
            err = str(e)
        else:
            err = None
        self.after(0, self._show_result, text, result, err)

    def _show_result(self, user_text: str, result, err) -> None:
        # remove the temporary "…thinking…" line
        self.view.config(state="normal")
        self.view.delete("end-3l", "end-1l")
        self.view.config(state="disabled")

        self._busy = False
        self.send_btn.config(state="normal")
        self.entry.focus_set()

        if err is not None or result is None:
            self._append("err", "Error", err or "Unknown error.")
            return
        if result.ok:
            self._history.append(ChatMessage("user", user_text))
            self._history.append(ChatMessage("assistant", result.reply))
            self._append("ai", "Assistant", result.reply)
        else:
            self._append("err", "Error", f"{result.error_code}: {result.message}")
