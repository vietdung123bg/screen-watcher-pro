"""Entry point: initialize the DB and open the Screen Watcher desktop UI.

Run:  python run.py
"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox

from app import config
from app.context import AppContext
from app.db.database import Database
from app.db.repository import Repository
from app.services.auth import AuthService
from app.services.capture_service import CaptureService
from app.services.notification_service import NotificationService
from app.ui.login_window import LoginWindow
from app.ui.main_window import MainWindow


def _configure_fonts(root: tk.Tk) -> None:
    """Enlarge the app-wide default fonts for readability."""
    from tkinter import font as tkfont

    sizes = {
        "TkDefaultFont": 12,    # label, button, checkbox, radio
        "TkTextFont": 12,       # entry, text
        "TkHeadingFont": 12,    # Treeview column headings
        "TkMenuFont": 12,
        "TkTooltipFont": 11,
        "TkIconFont": 12,
        "TkSmallCaptionFont": 11,
    }
    for name, size in sizes.items():
        try:
            tkfont.nametofont(name).configure(size=size)
        except tk.TclError:
            pass

    # Taller Treeview rows to balance the larger font
    try:
        from tkinter import ttk
        style = ttk.Style()
        style.configure("Treeview", rowheight=30, font=("Segoe UI", 12))
        style.configure("Treeview.Heading", font=("Segoe UI", 12, "bold"))
        style.configure("TNotebook.Tab", font=("Segoe UI", 12))
    except tk.TclError:
        pass


def build_context() -> AppContext:
    config.ensure_dirs()
    app_config = config.load_app_config()
    db = Database()
    db.init_schema()
    repo = Repository(db)
    notifier = NotificationService(repo, app_config)
    return AppContext(
        db=db,
        repo=repo,
        auth=AuthService(repo),
        capture_service=CaptureService(repo, notifier),
        notification_service=notifier,
        app_config=app_config,
    )


def main() -> int:
    logger = config.setup_logging()
    logger.info("Starting Screen Watcher Pro")

    try:
        ctx = build_context()
    except Exception as e:
        logger.exception("Failed to initialize the app: %s", e)
        # Show an error dialog if Tk is available
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("Startup error", str(e))
        return 1

    root = tk.Tk()
    try:
        root.call("tk", "scaling", 1.45)
    except tk.TclError:
        pass
    _configure_fonts(root)

    def show_login() -> None:
        ctx.current_user = None
        LoginWindow(root, ctx, on_success=show_main)

    def show_main() -> None:
        MainWindow(root, ctx, on_logout=show_login)

    show_login()
    root.mainloop()

    ctx.db.close()
    logger.info("Application exited.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
