"""Desktop UI (Tkinter)."""


def clear_widget(widget) -> None:
    """Remove all children of a widget (used when switching screens within the same root)."""
    for child in widget.winfo_children():
        child.destroy()
