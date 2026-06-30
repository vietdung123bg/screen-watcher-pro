"""User management tab (only shown when the user has user.manage)."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from app.context import AppContext
from app.services.auth import hash_password


class UsersTab(ttk.Frame):
    def __init__(self, parent, ctx: AppContext):
        super().__init__(parent, padding=12)
        self.ctx = ctx
        self._build()
        self.refresh()

    def _build(self) -> None:
        bar = ttk.Frame(self)
        bar.pack(fill="x", pady=(0, 8))
        ttk.Button(bar, text="➕ Add user", command=self._add_user).pack(side="left")
        ttk.Button(bar, text="🔑 Change role", command=self._change_role).pack(side="left", padx=4)
        ttk.Button(bar, text="♺ Reset password", command=self._reset_pwd).pack(side="left", padx=4)
        ttk.Button(bar, text="⏻ Enable/disable", command=self._toggle_active).pack(side="left", padx=4)
        ttk.Button(bar, text="🗑 Delete", command=self._delete_user).pack(side="left", padx=4)
        ttk.Button(bar, text="⟳ Refresh", command=self.refresh).pack(side="left", padx=4)

        cols = ("id", "username", "full_name", "role", "active")
        self.tree = ttk.Treeview(self, columns=cols, show="headings", height=14)
        for c, (txt, w) in {
            "id": ("ID", 50), "username": ("Username", 140),
            "full_name": ("Full name", 200), "role": ("Role", 120),
            "active": ("Active", 90),
        }.items():
            self.tree.heading(c, text=txt)
            self.tree.column(c, width=w, anchor="w")
        self.tree.pack(fill="both", expand=True)

    def refresh(self) -> None:
        self.tree.delete(*self.tree.get_children())
        for u in self.ctx.repo.list_users():
            self.tree.insert("", "end", iid=str(u["id"]), values=(
                u["id"], u["username"], u["full_name"] or "",
                u["role_name"] or "", "✔" if u["is_active"] else "✖",
            ))

    def _selected_id(self) -> int | None:
        sel = self.tree.selection()
        return int(sel[0]) if sel else None

    def _add_user(self) -> None:
        UserDialog(self, self.ctx, on_saved=self.refresh)

    def _change_role(self) -> None:
        uid = self._selected_id()
        if uid is None:
            return
        roles = self.ctx.repo.list_roles()
        dlg = tk.Toplevel(self)
        dlg.title("Change role")
        dlg.geometry("280x130")
        dlg.transient(self.winfo_toplevel())
        ttk.Label(dlg, text="Choose a new role:", padding=10).pack(anchor="w")
        var = tk.StringVar(value=roles[0]["name"])
        combo = ttk.Combobox(dlg, values=[r["name"] for r in roles], textvariable=var,
                             state="readonly")
        combo.pack(fill="x", padx=10)

        def save():
            role = self.ctx.repo.get_role_by_name(var.get())
            self.ctx.repo.update_user_role(uid, role["id"])
            dlg.destroy()
            self.refresh()

        ttk.Button(dlg, text="Save", command=save).pack(pady=12)

    def _reset_pwd(self) -> None:
        uid = self._selected_id()
        if uid is None:
            return
        from tkinter import simpledialog
        pwd = simpledialog.askstring("Reset password", "New password:", show="•", parent=self)
        if not pwd:
            return
        h, s = hash_password(pwd)
        # Force the user to set their own password on the next sign-in.
        self.ctx.repo.update_user_password(uid, h, s, must_change_password=True)
        self.ctx.repo.add_audit(self.ctx.current_user.id, "user.reset_password", str(uid))
        messagebox.showinfo(
            "Done", "Password has been reset. The user must change it at next sign-in.")

    def _toggle_active(self) -> None:
        uid = self._selected_id()
        if uid is None:
            return
        if uid == self.ctx.current_user.id:
            messagebox.showwarning("Not allowed", "You cannot disable your own account.")
            return
        user = self.ctx.repo.get_user(uid)
        self.ctx.repo.set_user_active(uid, not user["is_active"])
        self.refresh()

    def _delete_user(self) -> None:
        uid = self._selected_id()
        if uid is None:
            return
        if uid == self.ctx.current_user.id:
            messagebox.showwarning("Not allowed", "You cannot delete your own account.")
            return
        if messagebox.askyesno("Confirm", "Delete this user?"):
            self.ctx.repo.delete_user(uid)
            self.refresh()


class UserDialog(tk.Toplevel):
    """Dialog to create a new user."""

    def __init__(self, parent, ctx: AppContext, on_saved):
        super().__init__(parent)
        self.ctx = ctx
        self.on_saved = on_saved
        self.title("Add user")
        self.geometry("340x300")
        self.transient(parent.winfo_toplevel())
        self.grab_set()
        self._build()

    def _build(self) -> None:
        frm = ttk.Frame(self, padding=16)
        frm.pack(fill="both", expand=True)

        ttk.Label(frm, text="Username").pack(anchor="w")
        self.username = ttk.Entry(frm)
        self.username.pack(fill="x", pady=(0, 8))

        ttk.Label(frm, text="Full name").pack(anchor="w")
        self.full_name = ttk.Entry(frm)
        self.full_name.pack(fill="x", pady=(0, 8))

        ttk.Label(frm, text="Password").pack(anchor="w")
        self.password = ttk.Entry(frm, show="•")
        self.password.pack(fill="x", pady=(0, 8))

        ttk.Label(frm, text="Role").pack(anchor="w")
        roles = [r["name"] for r in self.ctx.repo.list_roles()]
        self.role_var = tk.StringVar(value="viewer" if "viewer" in roles else roles[0])
        ttk.Combobox(frm, values=roles, textvariable=self.role_var,
                     state="readonly").pack(fill="x", pady=(0, 14))

        ttk.Button(frm, text="Create", command=self._save).pack()

    def _save(self) -> None:
        username = self.username.get().strip()
        password = self.password.get()
        if not username or not password:
            messagebox.showwarning("Missing info", "Username and password are required.")
            return
        if self.ctx.repo.get_user_by_username(username):
            messagebox.showerror("Duplicate", "This username already exists.")
            return
        role = self.ctx.repo.get_role_by_name(self.role_var.get())
        h, s = hash_password(password)
        self.ctx.repo.create_user(username, h, s, self.full_name.get().strip(), role["id"])
        self.ctx.repo.add_audit(self.ctx.current_user.id, "user.create", username)
        self.on_saved()
        self.destroy()
