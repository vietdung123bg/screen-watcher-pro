"""Canvas xem ảnh có zoom in/out + pan, và cửa sổ ảnh riêng (Toplevel)."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import ttk

from PIL import Image, ImageTk

ZOOM_STEP = 1.25
MAX_SCALE = 8.0


class ZoomableImage(ttk.Frame):
    """Canvas hiển thị ảnh: cuộn chuột để zoom, kéo chuột để di chuyển, có scrollbar."""

    def __init__(self, parent, bg: str = "#202020", on_double_click=None):
        super().__init__(parent)
        self._on_double_click = on_double_click

        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0)
        hbar = ttk.Scrollbar(self, orient="horizontal", command=self.canvas.xview)
        vbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(xscrollcommand=hbar.set, yscrollcommand=vbar.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        vbar.grid(row=0, column=1, sticky="ns")
        hbar.grid(row=1, column=0, sticky="ew")
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

        self._orig: Image.Image | None = None
        self._scale = 1.0
        self._fit_scale = 1.0
        self._imgtk = None
        self._fitted = False

        self.canvas.bind("<MouseWheel>", self._on_wheel)        # Windows / macOS
        self.canvas.bind("<Button-4>", lambda e: self._zoom(ZOOM_STEP))    # Linux up
        self.canvas.bind("<Button-5>", lambda e: self._zoom(1 / ZOOM_STEP))  # Linux down
        self.canvas.bind("<ButtonPress-1>", lambda e: self.canvas.scan_mark(e.x, e.y))
        self.canvas.bind("<B1-Motion>", lambda e: self.canvas.scan_dragto(e.x, e.y, gain=1))
        self.canvas.bind("<Configure>", self._on_configure)
        if on_double_click:
            self.canvas.bind("<Double-Button-1>", lambda e: on_double_click())

    # ---------- public ----------
    def set_image(self, path: str | None) -> None:
        if not path or not Path(path).exists():
            self._orig = None
            self.canvas.delete("all")
            self._imgtk = None
            self.canvas.create_text(20, 20, anchor="nw", fill="#bbb",
                                    text="(No image yet — click “Capture & OCR”.)")
            return
        try:
            self._orig = Image.open(path).convert("RGB")
        except Exception as e:
            self._orig = None
            self.canvas.delete("all")
            self.canvas.create_text(20, 20, anchor="nw", fill="#e57",
                                    text=f"(Could not open image: {e})")
            return
        self._fitted = False
        self._fit()

    def zoom_in(self) -> None:
        self._zoom(ZOOM_STEP)

    def zoom_out(self) -> None:
        self._zoom(1 / ZOOM_STEP)

    def reset(self) -> None:
        """Về mức vừa khung."""
        if self._orig is not None:
            self._scale = self._fit_scale
            self._render()

    def zoom_label(self) -> str:
        return f"{int(self._scale * 100)}%"

    # ---------- internal ----------
    def _on_configure(self, _e) -> None:
        if self._orig is not None and not self._fitted:
            self._fit()

    def _fit(self) -> None:
        if self._orig is None:
            return
        cw = self.canvas.winfo_width()
        ch = self.canvas.winfo_height()
        if cw < 10 or ch < 10:
            return  # chưa layout xong -> đợi <Configure>
        ow, oh = self._orig.size
        self._fit_scale = min(cw / ow, ch / oh)
        self._scale = self._fit_scale
        self._fitted = True
        self._render()

    def _min_scale(self) -> float:
        if self._orig is None:
            return 0.05
        ow, oh = self._orig.size
        return min(50 / ow, 50 / oh, self._fit_scale or 1.0)

    def _zoom(self, factor: float) -> str:
        if self._orig is None:
            return "break"
        new = max(self._min_scale(), min(self._scale * factor, MAX_SCALE))
        if abs(new - self._scale) > 1e-6:
            self._scale = new
            self._render()
        return "break"

    def _render(self) -> None:
        if self._orig is None:
            return
        ow, oh = self._orig.size
        dw, dh = max(1, int(ow * self._scale)), max(1, int(oh * self._scale))
        disp = self._orig.resize((dw, dh), Image.LANCZOS)
        self._imgtk = ImageTk.PhotoImage(disp)
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, anchor="nw", image=self._imgtk)
        self.canvas.configure(scrollregion=(0, 0, dw, dh))

    def _on_wheel(self, e) -> str:
        return self._zoom(ZOOM_STEP if e.delta > 0 else 1 / ZOOM_STEP)


def open_image_window(parent, path: str | None, title: str = "Image viewer") -> tk.Toplevel | None:
    """Open the image in a separate window with a zoom toolbar."""
    if not path or not Path(path).exists():
        return None
    win = tk.Toplevel(parent)
    win.title(title)
    win.geometry("1024x720")

    toolbar = ttk.Frame(win, padding=6)
    toolbar.pack(fill="x")
    viewer = ZoomableImage(win)

    pct = ttk.Label(toolbar, text="100%", width=6)

    def upd():
        pct.config(text=viewer.zoom_label())

    ttk.Button(toolbar, text="➖ Zoom out",
               command=lambda: (viewer.zoom_out(), upd())).pack(side="left", padx=3)
    ttk.Button(toolbar, text="➕ Zoom in",
               command=lambda: (viewer.zoom_in(), upd())).pack(side="left", padx=3)
    ttk.Button(toolbar, text="⤢ Fit",
               command=lambda: (viewer.reset(), upd())).pack(side="left", padx=3)
    pct.pack(side="left", padx=8)
    ttk.Label(toolbar, text="Scroll to zoom · drag to pan",
              foreground="#888").pack(side="left", padx=8)

    viewer.pack(fill="both", expand=True)
    viewer.set_image(path)
    win.after(120, upd)
    win.transient(parent)
    win.lift()
    return win
