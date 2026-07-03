"""Chatbot tab: chat with the AI assistant from inside the desktop app.

Available to every signed-in user (user & admin). The assistant runs in-process
using the same ChatAgent as the REST API, so tools act with THIS user's permissions
(e.g. only an admin can soft-delete a user via chat). The LLM call runs on a
background thread so the UI never freezes.

A left-hand history panel lists the user's own chat sessions so they can reopen and
CONTINUE any of them. An admin additionally sees EVERY user's sessions (read-only for
other people's conversations) but can only continue their own — the same rule the
REST API enforces via ChatStore.ensure_session().
"""

from __future__ import annotations

import threading
import tkinter as tk
from tkinter import ttk

from app.ai.api_auth import is_admin
from app.ai.chat_agent import ChatAgent
from app.ai.conversation_store import ChatStore
from app.ai.models import OK, ChatMessage
from app.ai.provider_config import ProviderConfig
from app.ai.watcher_context_service import WatcherContextService


class ChatbotTab(ttk.Frame):
    def __init__(self, master, ctx):
        super().__init__(master, padding=10)
        self.ctx = ctx
        self._history: list[ChatMessage] = []
        self._busy = False
        self._readonly = False               # True while viewing another user's session
        self._suppress_select = False        # guard: programmatic tree selection
        self._is_admin = is_admin(ctx.current_user)
        self._sessions_by_id: dict = {}
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
        ).pack(anchor="w", pady=(2, 6))
        self._refresh_provider()

        # Read-only banner (shown only when an admin opens someone else's conversation).
        self.readonly_lbl = ttk.Label(self, text="", foreground="#a60",
                                      font=("Segoe UI", 10, "bold"))
        self.readonly_lbl.pack(anchor="w")

        body = ttk.Frame(self)
        body.pack(fill="both", expand=True, pady=(4, 0))

        self._build_history_panel(body)

        right = ttk.Frame(body)
        right.pack(side="left", fill="both", expand=True, padx=(10, 0))

        self.view = tk.Text(right, wrap="word", height=20, state="disabled",
                            font=("Segoe UI", 11), background="#fafafa")
        self.view.pack(fill="both", expand=True)
        self.view.tag_configure("you", foreground="#06c", font=("Segoe UI", 11, "bold"))
        self.view.tag_configure("ai", foreground="#0a7", font=("Segoe UI", 11, "bold"))
        self.view.tag_configure("err", foreground="#a00")

        row = ttk.Frame(right)
        row.pack(fill="x", pady=(8, 0))
        self.entry = ttk.Entry(row)
        self.entry.pack(side="left", fill="x", expand=True)
        self.entry.bind("<Return>", lambda _e: self._send())
        self.send_btn = ttk.Button(row, text="Send", command=self._send)
        self.send_btn.pack(side="left", padx=(6, 0))

        self._append("ai", "Assistant", "Hi! How can I help with your watcher data today?")
        self._load_sessions()

    def _build_history_panel(self, parent) -> None:
        left = ttk.Frame(parent, width=320 if self._is_admin else 260)
        left.pack(side="left", fill="y")
        left.pack_propagate(False)

        top = ttk.Frame(left)
        top.pack(fill="x")
        ttk.Label(top, text="Chat history", font=("Segoe UI", 11, "bold")).pack(side="left")
        ttk.Button(top, text="⟳", width=3, command=self._load_sessions).pack(side="right")

        note = ("All users' sessions. You can continue only your own chats; "
                "others are read-only.") if self._is_admin else "Your saved conversations."
        ttk.Label(left, text=note, foreground="#888", wraplength=310 if self._is_admin else 250,
                  justify="left", font=("Segoe UI", 9)).pack(anchor="w", pady=(0, 4))

        holder = ttk.Frame(left)
        holder.pack(fill="both", expand=True)
        if self._is_admin:
            cols, headings, widths = (("owner", "title", "when"),
                                      ("User", "Conversation", "Last activity"),
                                      (75, 150, 90))
        else:
            cols, headings, widths = (("title", "when"),
                                      ("Conversation", "Last activity"),
                                      (180, 90))
        self.tree = ttk.Treeview(holder, columns=cols, show="headings", selectmode="browse")
        for c, h, w in zip(cols, headings, widths):
            self.tree.heading(c, text=h)
            self.tree.column(c, width=w, anchor="w", stretch=(c == "title"))
        self.tree.tag_configure("other", foreground="#999")   # not-continuable (admin view)
        vs = ttk.Scrollbar(holder, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vs.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vs.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self._on_select_session)

    def _append(self, tag: str, who: str, text: str) -> None:
        self.view.config(state="normal")
        self.view.insert("end", f"{who}: ", tag)
        self.view.insert("end", text + "\n\n")
        self.view.config(state="disabled")
        self.view.see("end")

    def _clear_view(self) -> None:
        self.view.config(state="normal")
        self.view.delete("1.0", "end")
        self.view.config(state="disabled")

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

    # ---------- session history ----------
    def _load_sessions(self) -> None:
        """(Re)load the session list from the store and repopulate the tree."""
        user = self.ctx.current_user
        rows = self._store.list_all_sessions() if self._is_admin \
            else self._store.list_sessions(user.id)
        self._sessions_by_id = {}
        self.tree.delete(*self.tree.get_children())
        for r in rows:
            sid = r["id"]
            self._sessions_by_id[sid] = r
            title = (r["title"] or "New chat").strip() or "New chat"
            when = (r["last_message_at"] or r["updated_at"] or "")[:16].replace("T", " ")
            if self._is_admin:
                owner = r["owner_username"] if "owner_username" in r.keys() else "?"
                mine = r["user_id"] == user.id
                self.tree.insert("", "end", iid=sid, values=(owner, title, when),
                                 tags=() if mine else ("other",))
            else:
                self.tree.insert("", "end", iid=sid, values=(title, when))
        # Keep the current conversation highlighted if it is still in the list.
        self._select_in_tree(self._session_id)

    def _select_in_tree(self, sid: str | None) -> None:
        if sid and self.tree.exists(sid):
            self._suppress_select = True
            self.tree.selection_set(sid)
            self.tree.see(sid)
            self._suppress_select = False

    def _on_select_session(self, _event=None) -> None:
        if self._suppress_select or self._busy:
            return
        sel = self.tree.selection()
        if not sel:
            return
        sid = sel[0]
        row = self._sessions_by_id.get(sid)
        if row is None:
            return
        own = row["user_id"] == self.ctx.current_user.id
        msgs = self._store.transcript(sid)
        self._clear_view()
        if not msgs:
            self._append("ai", "Assistant", "(No messages in this conversation yet.)")
        for m in msgs:
            if m.role == "user":
                self._append("you", "You", m.content)
            elif m.error_code and m.error_code != OK:
                self._append("err", "Error", m.content)
            else:
                self._append("ai", "Assistant", m.content)

        if own:
            # Reopen for continuation: reload the recent context the model will see.
            self._session_id = sid
            self._history = self._store.recent(sid)
            self._set_readonly(False)
        else:
            # Admin viewing another user's conversation — read-only, cannot continue.
            self._session_id = None
            self._history = []
            owner = row["owner_username"] if "owner_username" in row.keys() else "another user"
            self._set_readonly(True, owner)

    def _set_readonly(self, readonly: bool, owner: str = "") -> None:
        self._readonly = readonly
        if readonly:
            self.entry.delete(0, "end")
            self.entry.config(state="disabled")
            self.send_btn.config(state="disabled")
            self.readonly_lbl.config(
                text=f"🔒  Read-only: viewing {owner}'s conversation. "
                     "You can only continue your own chats.")
        else:
            self.entry.config(state="normal")
            self.send_btn.config(state="normal")
            self.readonly_lbl.config(text="")

    def _new_session(self) -> None:
        """Start a fresh conversation (new session on next send)."""
        if self._busy:
            return
        self._session_id = None
        self._history = []
        self._set_readonly(False)
        if self.tree.selection():
            self.tree.selection_remove(self.tree.selection())
        self._clear_view()
        self._refresh_provider()          # provider may have changed in .env
        self._append("ai", "Assistant", "Started a new conversation. How can I help?")

    # ---------- send ----------
    def _send(self) -> None:
        if self._busy or self._readonly:
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
        # Reflect the new/updated session in the history list (title, timestamp, order).
        self._load_sessions()
