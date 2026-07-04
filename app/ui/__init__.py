"""Desktop UI (Tkinter)."""


def clear_widget(widget) -> None:
    """Remove all children of a widget (used when switching screens within the same root)."""
    for child in widget.winfo_children():
        child.destroy()


def center_window(win, width: int | None = None, height: int | None = None) -> None:
    """Size (optional) and center a Tk window on the screen it is on.

    Pass width/height to also resize; otherwise the window's current size is used.
    """
    win.update_idletasks()
    w = width or win.winfo_width()
    h = height or win.winfo_height()
    screen_w = win.winfo_screenwidth()
    screen_h = win.winfo_screenheight()
    x = max(0, (screen_w - w) // 2)
    y = max(0, (screen_h - h) // 2)
    win.geometry(f"{w}x{h}+{x}+{y}")
