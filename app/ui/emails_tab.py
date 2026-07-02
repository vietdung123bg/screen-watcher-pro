"""View & tab for sent emails (sent / simulated / failed) + a Resend button.

- EmailListView: reusable widget (table + content + Resend). Data is loaded via
  set_source(fn) — fn() returns a list of email records.
- EmailsTab: top-level tab using EmailListView, showing all emails within the user's scope.
"""

from __future__ import annotations

from tkinter import messagebox, scrolledtext, ttk

from app.context import AppContext
from app.services.notification_service import ACTION_LABELS


class EmailListView(ttk.Frame):
    """Email table + content box + Resend button. Data source is loaded via set_source()."""

    def __init__(self, parent, ctx: AppContext, title: str = "✉ Sent emails"):
        super().__init__(parent, padding=8)
        self.ctx = ctx
        self._source = lambda: []          # function returning a list of rows
        self._rows: dict[int, object] = {}
        self._build(title)

    def _build(self, title: str) -> None:
        bar = ttk.Frame(self)
        bar.pack(fill="x")
        ttk.Label(bar, text=title, font=("Segoe UI", 12, "bold")).pack(side="left")
        self.count_lbl = ttk.Label(bar, text="", foreground="#666")
        self.count_lbl.pack(side="left", padx=10)
        ttk.Button(bar, text="🔄 Refresh", command=self.refresh).pack(side="right")
        # Resend only for users who can capture/send
        self._can_send = self.ctx.current_user.can("capture.run")
        if self._can_send:
            self.resend_btn = ttk.Button(bar, text="✉ Resend selected email",
                                         command=self._resend, state="disabled")
            self.resend_btn.pack(side="right", padx=6)

        cols = ("time", "user", "target", "rule", "status", "recipients", "subject")
        self.tree = ttk.Treeview(self, columns=cols, show="headings", height=8)
        for c, (txt, w) in {
            "time": ("Time", 140), "user": ("Captured by", 95),
            "target": ("Browser", 80), "rule": ("Rule", 120),
            "status": ("Status", 120), "recipients": ("Recipients", 170),
            "subject": ("Subject", 230),
        }.items():
            self.tree.heading(c, text=txt)
            self.tree.column(c, width=w, anchor="w")
        self.tree.pack(fill="x", pady=(6, 0))
        self.tree.bind("<<TreeviewSelect>>", self._on_select)

        body_box = ttk.LabelFrame(self, text="Email content", padding=6)
        body_box.pack(fill="both", expand=True, pady=(8, 0))
        self.body = scrolledtext.ScrolledText(body_box, wrap="word", font=("Consolas", 12),
                                              state="disabled")
        self.body.pack(fill="both", expand=True)

    # ---------- load data ----------
    def set_source(self, source_fn) -> None:
        self._source = source_fn

    def refresh(self) -> None:
        rows = list(self._source() or [])
        self._rows = {r["id"]: r for r in rows}
        self.tree.delete(*self.tree.get_children())
        for nid, r in self._rows.items():
            self.tree.insert("", "end", iid=str(nid), values=(
                r["created_at"], r["username"] or "", r["target_app"],
                r["rule_id"], ACTION_LABELS.get(r["status"], r["status"]),
                (r["recipients"] or "")[:40], (r["subject"] or "")[:50],
            ))
        self.count_lbl.config(text=f"{len(self._rows)} emails")
        self._set_body("(Select an email above to view its content.)")
        if self._can_send:
            self.resend_btn.config(state="disabled")

    def _set_body(self, text: str) -> None:
        self.body.config(state="normal")
        self.body.delete("1.0", "end")
        self.body.insert("1.0", text)
        self.body.config(state="disabled")

    # ---------- interaction ----------
    def _selected_id(self) -> str | None:
        sel = self.tree.selection()
        return sel[0] if sel else None

    def _on_select(self, _event=None) -> None:
        nid = self._selected_id()
        if nid is None:
            return
        r = self._rows.get(nid)
        if r is None:
            return
        if self._can_send:
            self.resend_btn.config(state="normal")
        status = ACTION_LABELS.get(r["status"], r["status"])
        header = (
            f"Status     : {status}\n"
            f"Time       : {r['created_at']}\n"
            f"Source     : {r['target_app']} — {r['window_title'] or ''}\n"
            f"Rule       : {r['rule_id']} (owner: {r['owner_group'] or '—'})\n"
            f"Recipients : {r['recipients'] or '—'}\n"
            f"Subject    : {r['subject'] or '—'}\n"
            f"Reason     : {r['reason'] or ''}\n"
            f"{'=' * 64}\n"
        )
        self._set_body(header + (r["body"] or "(No email content.)"))

    def _resend(self) -> None:
        nid = self._selected_id()
        if nid is None:
            return
        r = self._rows.get(nid)
        subj = (r["subject"] if r else "") or "(no subject)"
        if not messagebox.askyesno(
                "Resend email",
                f"Resend this email?\n\nSubject: {subj}\nRecipients: "
                f"{(r['recipients'] if r else '') or '—'}\n\n"
                "(Cooldown is ignored. In DRY-RUN it is only simulated, not actually sent.)"):
            return
        status, detail = self.ctx.notification_service.resend(nid)
        label = ACTION_LABELS.get(status, status)
        if status in ("sent", "simulated"):
            messagebox.showinfo("Resend", f"{label}.\n\n{detail}")
        else:
            messagebox.showerror("Resend", f"{label}.\n\n{detail}")
        self.refresh()


class EmailsTab(ttk.Frame):
    """Top-level tab: shows all emails within the user's permission scope."""

    def __init__(self, parent, ctx: AppContext):
        super().__init__(parent, padding=6)
        self.ctx = ctx
        ttk.Label(self, foreground="#888",
                  text="Emails actually sent, simulated (DRY-RUN) or failed — "
                       "select a row to view content, or Resend.").pack(anchor="w")
        self.view = EmailListView(self, ctx, title="✉ All emails")
        self.view.pack(fill="both", expand=True)
        self.view.set_source(self._load)
        self.refresh()

    def _load(self):
        user = self.ctx.current_user
        scope_user = None if user.can("screenshot.view_all") else user.id
        return self.ctx.repo.list_emails(user_id=scope_user)

    def refresh(self) -> None:
        self.view.refresh()
