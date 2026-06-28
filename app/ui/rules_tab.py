"""Rules tab: show rules loaded from rules.yaml + email status + a Send-test button."""

from __future__ import annotations

import threading
import tkinter as tk
from tkinter import messagebox, scrolledtext, ttk

from app.context import AppContext


class RulesTab(ttk.Frame):
    def __init__(self, parent, ctx: AppContext):
        super().__init__(parent, padding=12)
        self.ctx = ctx
        self._build()

    def _build(self) -> None:
        cfg = self.ctx.app_config
        email = self.ctx.notification_service.email.cfg  # resolved (provider preset applied)
        owners = cfg.get("owners", {})
        rules = cfg.get("rules", [])

        # --- configuration status ---
        status = ttk.LabelFrame(self, text="Configuration status (config/rules.yaml)", padding=8)
        status.pack(fill="x")

        err = cfg.get("_error")
        if err:
            ttk.Label(status, text=f"⚠ {err}", foreground="#c0392b").pack(anchor="w")

        mode = "REAL SEND" if email.get("enabled") else "DRY-RUN (simulate, not actually sent)"
        rows = [
            ("Email mode", mode),
            ("Provider", email.get("provider", "—")),
            ("SMTP host", f"{email.get('smtp_host','—')}:{email.get('smtp_port','—')}"),
            ("Sender", email.get("from", "—")),
            ("Password env", email.get("password_env", "—")),
            ("Rules", str(len(rules))),
            ("Owner groups", ", ".join(f"{k} ({len(v.get('emails', []))} email)"
                                       for k, v in owners.items()) or "—"),
            ("Default cooldown", f"{cfg.get('cooldown', {}).get('default_minutes', 15)} min"),
        ]
        for k, v in rows:
            line = ttk.Frame(status)
            line.pack(fill="x", pady=1)
            ttk.Label(line, text=f"{k}:", width=16, foreground="#555").pack(side="left")
            ttk.Label(line, text=v).pack(side="left")

        # --- send a test email ---
        if self.ctx.current_user.can("capture.run"):
            test = ttk.LabelFrame(self, text="Send a test email (verify SMTP)", padding=8)
            test.pack(fill="x", pady=(10, 0))
            ttk.Label(test, text="To:").pack(side="left")
            self.test_to = ttk.Entry(test, width=34)
            default_to = email.get("from") or email.get("username") or ""
            self.test_to.insert(0, default_to)
            self.test_to.pack(side="left", padx=6)
            self.test_btn = ttk.Button(test, text="✉ Send test email", command=self._send_test)
            self.test_btn.pack(side="left", padx=6)
            self.test_status = ttk.Label(test, text="", foreground="#666")
            self.test_status.pack(side="left", padx=8)
            ttk.Label(test, foreground="#888",
                      text="(forces a real send even in DRY-RUN; needs the password env var)"
                      ).pack(side="left")

        # --- rule list ---
        rule_box = ttk.LabelFrame(self, text="Rules", padding=6)
        rule_box.pack(fill="both", expand=True, pady=(10, 0))

        cols = ("id", "name", "type", "condition", "severity", "owner", "cooldown")
        tree = ttk.Treeview(rule_box, columns=cols, show="headings", height=7)
        for c, (txt, w) in {
            "id": ("ID", 130), "name": ("Name", 200), "type": ("Type", 100),
            "condition": ("Condition", 260), "severity": ("Severity", 70),
            "owner": ("Owner", 110), "cooldown": ("Cooldown", 70),
        }.items():
            tree.heading(c, text=txt)
            tree.column(c, width=w, anchor="w")
        tree.pack(fill="both", expand=True)

        for r in rules:
            tree.insert("", "end", values=(
                r.get("id", ""), r.get("name", ""), r.get("type", ""),
                self._describe_condition(r), r.get("severity", ""),
                r.get("owner_group", ""), f"{r.get('cooldown_minutes', '')}m",
            ))

        note = scrolledtext.ScrolledText(self, height=4, wrap="word", font=("Segoe UI", 11))
        note.pack(fill="x", pady=(8, 0))
        note.insert("1.0",
                    "Edit rules/owners/email in config/rules.yaml, then restart the app. "
                    "Set email.enabled=true (and the password env var in .env) to send real "
                    "emails; false runs DRY-RUN (simulated) — decisions and cooldown are still recorded.")
        note.config(state="disabled")

    # ---------- send test ----------
    def _send_test(self) -> None:
        to = self.test_to.get().strip()
        if not to:
            messagebox.showwarning("Send test email", "Please enter a recipient address.")
            return
        self.test_btn.config(state="disabled")
        self.test_status.config(text="Sending…", foreground="#666")

        def worker():
            res = self.ctx.notification_service.email.send_test(to)
            self.after(0, lambda: self._test_done(res))

        threading.Thread(target=worker, daemon=True).start()

    def _test_done(self, res) -> None:
        self.test_btn.config(state="normal")
        if res.sent:
            self.test_status.config(text="✔ Sent", foreground="#1a7f37")
            messagebox.showinfo("Send test email", res.detail)
        else:
            self.test_status.config(text="✖ Failed", foreground="#c0392b")
            messagebox.showerror("Send test email", res.detail)

    @staticmethod
    def _describe_condition(r: dict) -> str:
        t = r.get("type")
        if t in ("contains", "not_contains"):
            return f'value = "{r.get("value", "")}"'
        if t == "regex":
            return f'pattern = /{r.get("pattern", "")}/'
        if t in ("all_keywords", "any_keywords"):
            return f'keywords = {r.get("keywords", [])}'
        return ""
