"""Capture & OCR tab: pick one browser (Chrome/Edge), optional auto-launch, runs in
the background.

After capturing it shows everything in this tab: image preview, OCR result, and the
email-decision explanation — no need to switch to the History tab.
"""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import scrolledtext, ttk

from app import config
from app.context import AppContext
from app.ui import explain
from app.ui.emails_tab import EmailListView
from app.ui.image_viewer import ZoomableImage, open_image_window


class CaptureTab(ttk.Frame):
    def __init__(self, parent, ctx: AppContext, on_done=None):
        super().__init__(parent, padding=16)
        self.ctx = ctx
        self.on_done = on_done          # callback để History tab refresh
        self._queue: queue.Queue = queue.Queue()
        self._running = False
        self._build()

    def _build(self) -> None:
        # --- Target selection (ONLY one browser) ---
        target_box = ttk.LabelFrame(self, text="Choose a browser to capture (pick one)", padding=12)
        target_box.pack(fill="x")

        keys = list(config.CAPTURE_TARGETS.keys())
        self.target_var = tk.StringVar(value=keys[0] if keys else "")
        for key, cfg in config.CAPTURE_TARGETS.items():
            ttk.Radiobutton(target_box, text=cfg["label"], value=key,
                            variable=self.target_var).pack(side="left", padx=12)

        # --- Options ---
        opt_box = ttk.Frame(self, padding=(0, 10))
        opt_box.pack(fill="x")
        self.launch_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(opt_box, text="Launch the app if it is not running",
                        variable=self.launch_var).pack(side="left")

        ttk.Label(opt_box, text="   Note:").pack(side="left")
        self.note_entry = ttk.Entry(opt_box, width=40)
        self.note_entry.pack(side="left", padx=6)

        # --- Run button ---
        action = ttk.Frame(self)
        action.pack(fill="x", pady=(4, 8))
        self.run_btn = ttk.Button(action, text="📸  Capture & OCR", command=self._on_run)
        self.run_btn.pack(side="left")
        self.progress = ttk.Progressbar(action, mode="indeterminate", length=180)
        self.progress.pack(side="left", padx=12)

        # --- Results area: multi-tab Notebook ---
        self.result_nb = ttk.Notebook(self)
        self.result_nb.pack(fill="both", expand=True, pady=(6, 0))

        # Tab 1: Log
        log_frame = ttk.Frame(self.result_nb, padding=4)
        self.log = scrolledtext.ScrolledText(log_frame, height=14, wrap="word",
                                             font=("Consolas", 12), state="disabled")
        self.log.pack(fill="both", expand=True)
        self.result_nb.add(log_frame, text="  📝 Log  ")

        # Tab 2: Screenshot (zoomable preview)
        self._preview_frame = ttk.Frame(self.result_nb, padding=4)
        prev_bar = ttk.Frame(self._preview_frame)
        prev_bar.pack(fill="x", pady=(0, 4))
        self._preview_path: str | None = None
        self.preview = ZoomableImage(self._preview_frame, on_double_click=self._open_preview_window)
        ttk.Button(prev_bar, text="➖ Zoom out", command=self.preview.zoom_out).pack(side="left", padx=2)
        ttk.Button(prev_bar, text="➕ Zoom in", command=self.preview.zoom_in).pack(side="left", padx=2)
        ttk.Button(prev_bar, text="⤢ Fit", command=self.preview.reset).pack(side="left", padx=2)
        ttk.Button(prev_bar, text="🔍 Open in new window",
                   command=self._open_preview_window).pack(side="left", padx=8)
        ttk.Label(prev_bar, text="Scroll to zoom · drag to pan · double-click to open in a new window",
                  foreground="#888").pack(side="left", padx=6)
        self.preview.pack(fill="both", expand=True)
        self.result_nb.add(self._preview_frame, text="  🖼 Screenshot  ")

        # Tab 3: OCR result
        ocr_frame = ttk.Frame(self.result_nb, padding=4)
        self.ocr_text = scrolledtext.ScrolledText(ocr_frame, wrap="word",
                                                  font=("Segoe UI", 12), state="disabled")
        self.ocr_text.pack(fill="both", expand=True)
        self.result_nb.add(ocr_frame, text="  📄 OCR result  ")

        # Tab 4: Email explanation
        explain_frame = ttk.Frame(self.result_nb, padding=4)
        self.explain = scrolledtext.ScrolledText(explain_frame, wrap="word",
                                                 font=("Consolas", 12), state="disabled")
        self.explain.pack(fill="both", expand=True)
        self.result_nb.add(explain_frame, text="  ✉ Email explanation  ")

        # Tab 5: Sent emails (for this capture)
        self.emails_view = EmailListView(self.result_nb, self.ctx,
                                        title="✉ Emails sent in this capture")
        self.result_nb.add(self.emails_view, text="  📧 Sent emails  ")

        if not self.ctx.current_user.can("capture.run"):
            self.run_btn.config(state="disabled")
            self._log("⚠ Your account does not have the 'capture.run' permission.")

    # ---------- logging ----------
    def _log(self, msg: str) -> None:
        self.log.config(state="normal")
        self.log.insert("end", msg + "\n")
        self.log.see("end")
        self.log.config(state="disabled")

    def _set_explain(self, text: str) -> None:
        self.explain.config(state="normal")
        self.explain.delete("1.0", "end")
        self.explain.insert("1.0", text)
        self.explain.config(state="disabled")

    def _set_ocr(self, text: str) -> None:
        self.ocr_text.config(state="normal")
        self.ocr_text.delete("1.0", "end")
        self.ocr_text.insert("1.0", text)
        self.ocr_text.config(state="disabled")

    def _show_preview(self, file_path: str | None) -> None:
        self._preview_path = file_path
        self.preview.set_image(file_path)

    def _open_preview_window(self) -> None:
        if self._preview_path:
            open_image_window(self, self._preview_path, title="Image viewer — Screen Watcher Pro")

    # ---------- run ----------
    def _on_run(self) -> None:
        if self._running:
            return
        choice = self.target_var.get()
        if not choice:
            self._log("⚠ Please choose a browser (Chrome or Edge).")
            return
        targets = [choice]

        self._running = True
        self.run_btn.config(state="disabled")
        self.progress.start(12)
        labels = ", ".join(config.CAPTURE_TARGETS[t]["label"] for t in targets)
        self._log(f"▶ Capturing: {labels} (auto-launch: {self.launch_var.get()})")

        worker = threading.Thread(
            target=self._worker,
            args=(targets, self.launch_var.get(), self.note_entry.get().strip()),
            daemon=True,
        )
        worker.start()
        self.after(150, self._poll_queue)

    def _worker(self, targets, launch, note) -> None:
        """Runs on a background thread — never touches Tk widgets, only the queue."""
        try:
            results = self.ctx.capture_service.capture_targets(
                self.ctx.current_user.id, targets, launch=launch, note=note,
            )
            self._queue.put(("done", results))
        except Exception as e:
            self._queue.put(("error", str(e)))

    def _poll_queue(self) -> None:
        try:
            while True:
                kind, payload = self._queue.get_nowait()
                if kind == "error":
                    self._log(f"✖ Error: {payload}")
                elif kind == "done":
                    explain_blocks = []
                    shown = None  # result used for preview + OCR
                    for r in payload:
                        if r.status == "success" and not r.error:
                            self._log(f"✔ {r.label}: '{r.window_title}' — OCR {r.char_count} chars "
                                      f"(screenshot #{r.screenshot_id})")
                            if r.outcome is not None:
                                self._log(f"   ➜ {r.outcome.summary}")
                            shown = r
                        elif r.status == "success" and r.error:
                            self._log(f"△ {r.label}: captured OK but {r.error}")
                            if shown is None:
                                shown = r
                        else:
                            self._log(f"✖ {r.label}: {r.error}")
                        if r.outcome is not None:
                            explain_blocks.append(
                                f"### {r.label} — {r.window_title}\n"
                                + explain.from_outcome(r.outcome))

                    # Show right inside the Capture tab: preview + OCR result
                    if shown is not None:
                        self._show_preview(shown.file_path)
                        if shown.error and not shown.ocr_text:
                            self._set_ocr(f"(No OCR result — {shown.error})")
                        else:
                            header = (f"Source: {shown.label} — {shown.window_title}\n"
                                      f"Characters: {shown.char_count}\n{'-' * 60}\n")
                            self._set_ocr(header + (shown.ocr_text or ""))
                    self._set_explain("\n\n".join(explain_blocks)
                                      if explain_blocks else "(No rule-evaluation data.)")

                    # Load emails sent in THIS capture into the sub-tab
                    ids = [r.screenshot_id for r in payload if r.screenshot_id]
                    self.emails_view.set_source(
                        lambda ids=ids: self.ctx.repo.list_emails(screenshot_ids=ids) if ids else [])
                    self.emails_view.refresh()

                    self._finish()
                    # Jump to the Screenshot tab so the user sees the result immediately
                    if shown is not None and shown.file_path:
                        self.result_nb.select(self._preview_frame)
                    if self.on_done:
                        self.on_done()
                    return
        except queue.Empty:
            pass
        self.after(150, self._poll_queue)

    def _finish(self) -> None:
        self._running = False
        self.progress.stop()
        self.run_btn.config(state="normal")
        self._log("■ Done.\n")
