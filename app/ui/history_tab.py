"""History tab: screenshot list -> image preview + OCR text + explanation."""

from __future__ import annotations

from tkinter import scrolledtext, ttk

from app.context import AppContext
from app.ui import explain
from app.ui.image_viewer import ZoomableImage, open_image_window


class HistoryTab(ttk.Frame):
    def __init__(self, parent, ctx: AppContext):
        super().__init__(parent, padding=10)
        self.ctx = ctx
        self._preview_imgtk = None  # keep a reference to avoid GC
        self._build()
        self.refresh()

    def _build(self) -> None:
        bar = ttk.Frame(self)
        bar.pack(fill="x", pady=(0, 6))
        ttk.Button(bar, text="⟳ Refresh", command=self.refresh).pack(side="left")
        self.count_lbl = ttk.Label(bar, text="", foreground="#666")
        self.count_lbl.pack(side="left", padx=10)

        # List table
        cols = ("id", "time", "user", "target", "title", "status", "chars")
        self.tree = ttk.Treeview(self, columns=cols, show="headings", height=9)
        headings = {
            "id": ("ID", 50), "time": ("Time", 140), "user": ("User", 90),
            "target": ("App", 70), "title": ("Window title", 260),
            "status": ("Status", 80), "chars": ("Chars", 70),
        }
        for c, (txt, w) in headings.items():
            self.tree.heading(c, text=txt)
            self.tree.column(c, width=w, anchor="w")
        self.tree.pack(fill="x")
        self.tree.bind("<<TreeviewSelect>>", self._on_select)

        # Detail area: left = image, right = OCR text / explanation
        detail = ttk.Panedwindow(self, orient="horizontal")
        detail.pack(fill="both", expand=True, pady=(8, 0))

        left = ttk.LabelFrame(detail, text="Screenshot preview", padding=6)
        prev_bar = ttk.Frame(left)
        prev_bar.pack(fill="x", pady=(0, 4))
        self._preview_path: str | None = None
        self.viewer = ZoomableImage(left, on_double_click=self._open_preview_window)
        ttk.Button(prev_bar, text="➖", width=3, command=self.viewer.zoom_out).pack(side="left", padx=2)
        ttk.Button(prev_bar, text="➕", width=3, command=self.viewer.zoom_in).pack(side="left", padx=2)
        ttk.Button(prev_bar, text="⤢ Fit", command=self.viewer.reset).pack(side="left", padx=2)
        ttk.Button(prev_bar, text="🔍 New window",
                   command=self._open_preview_window).pack(side="left", padx=8)
        ttk.Label(prev_bar, text="(double-click to enlarge)", foreground="#888").pack(side="left")
        self.viewer.pack(fill="both", expand=True)
        detail.add(left, weight=1)

        # Right = notebook: [OCR result] + [Email explanation]
        right = ttk.Notebook(detail)
        ocr_frame = ttk.Frame(right, padding=4)
        self.ocr_text = scrolledtext.ScrolledText(ocr_frame, wrap="word", font=("Segoe UI", 12))
        self.ocr_text.pack(fill="both", expand=True)
        right.add(ocr_frame, text="  OCR result  ")

        explain_frame = ttk.Frame(right, padding=4)
        self.explain_text = scrolledtext.ScrolledText(explain_frame, wrap="word",
                                                      font=("Consolas", 12))
        self.explain_text.pack(fill="both", expand=True)
        right.add(explain_frame, text="  Why email sent / not sent  ")
        detail.add(right, weight=1)

    # ---------- data ----------
    def refresh(self) -> None:
        user = self.ctx.current_user
        # view_all -> see everyone; otherwise own only
        scope_user = None if user.can("screenshot.view_all") else user.id
        rows = self.ctx.repo.list_screenshots(user_id=scope_user)

        self.tree.delete(*self.tree.get_children())
        for r in rows:
            self.tree.insert("", "end", iid=str(r["id"]), values=(
                r["id"], r["captured_at"], r["username"] or "", r["target_app"],
                (r["window_title"] or "")[:60], r["status"],
                r["char_count"] if r["char_count"] is not None else "",
            ))
        scope = "all users" if scope_user is None else "yours"
        self.count_lbl.config(text=f"{len(rows)} screenshots ({scope})")
        self._clear_detail()

    def _on_select(self, _event=None) -> None:
        sel = self.tree.selection()
        if not sel:
            return
        screenshot_id = int(sel[0])
        shot = self.ctx.repo.get_screenshot(screenshot_id)
        if shot is None:
            return
        self._show_image(shot["file_path"])
        self._show_ocr(screenshot_id, shot)
        self._show_explain(screenshot_id)

    def _show_image(self, file_path: str | None) -> None:
        self._preview_path = file_path
        self.viewer.set_image(file_path)

    def _open_preview_window(self) -> None:
        if self._preview_path:
            open_image_window(self, self._preview_path, title="Image viewer — Screen Watcher Pro")

    def _show_ocr(self, screenshot_id: int, shot) -> None:
        self.ocr_text.delete("1.0", "end")
        if not self.ctx.current_user.can("ocr.view"):
            self.ocr_text.insert("1.0", "(You do not have permission to view OCR text.)")
            return
        ocr = self.ctx.repo.get_ocr_for_screenshot(screenshot_id)
        if ocr is None:
            note = shot["error"] or "(No OCR result for this screenshot yet.)"
            self.ocr_text.insert("1.0", note)
            return
        header = (f"Model: {ocr['model']}    |    {ocr['char_count']} chars    |    "
                  f"{ocr['duration_ms']} ms\n{'-' * 70}\n")
        self.ocr_text.insert("1.0", header + (ocr["text"] or ""))

    def _show_explain(self, screenshot_id: int) -> None:
        self.explain_text.delete("1.0", "end")
        if not self.ctx.current_user.can("rule.view"):
            self.explain_text.insert("1.0", "(You do not have permission to view rule/email info.)")
            return
        self.explain_text.insert("1.0", explain.from_db(self.ctx.repo, screenshot_id))

    def _clear_detail(self) -> None:
        self._preview_path = None
        self.viewer.set_image(None)
        self.ocr_text.delete("1.0", "end")
        self.explain_text.delete("1.0", "end")
