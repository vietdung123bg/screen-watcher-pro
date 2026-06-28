"""UI desktop (Tkinter)."""


def clear_widget(widget) -> None:
    """Xóa toàn bộ con của một widget (dùng khi chuyển màn hình trong cùng root)."""
    for child in widget.winfo_children():
        child.destroy()
