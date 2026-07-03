"""Standalone WebView2 window that renders the Jupyter notebook UI.

Spawned by JupyterTab as a SEPARATE PROCESS:

    python -m app.ui.jupyter_webview <url> [title]

Kept in its own process on purpose: pywebview runs its own native GUI event
loop (Edge WebView2 on Windows) which cannot share the main thread with the
Tkinter mainloop. Running it as a child process gives a clean, app-managed
window with none of the threading conflicts, and lets the app close it by
terminating the process.
"""

from __future__ import annotations

import sys

DEFAULT_TITLE = "Jupyter — Screen Watcher Pro"


def main(argv: list[str]) -> int:
    if len(argv) < 1 or not argv[0].strip():
        sys.stderr.write("usage: python -m app.ui.jupyter_webview <url> [title]\n")
        return 2
    url = argv[0]
    title = argv[1] if len(argv) > 1 else DEFAULT_TITLE
    try:
        import webview  # pywebview — provides the Edge WebView2 window on Windows
    except Exception as e:                     # pywebview not installed / backend missing
        sys.stderr.write(f"pywebview unavailable: {e}\n")
        return 3
    webview.create_window(title, url, width=1200, height=820)
    webview.start()                             # blocks until the window is closed
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
