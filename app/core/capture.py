"""Capture a specific Windows window (Chrome / Edge / ...).

Reuses the exact technique from main_qwen_ocr.py:
  - Find the REAL window by title (excluding cloaked / phantom ones).
  - Reliably bring the window to the foreground (AttachThreadInput + minimize/restore).
  - Capture using the true bbox (DwmGetWindowAttribute), DPI-aware.
  - Optionally auto-launch the app if it is not already open.
"""

from __future__ import annotations

import ctypes
import logging
import subprocess
import time
from ctypes import wintypes

import win32con
import win32gui
import win32process
from PIL import Image, ImageGrab

logger = logging.getLogger("screen_watcher.capture")

# Declare argtypes so the HANDLE is not truncated on 64-bit Python
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_k32 = ctypes.windll.kernel32
_k32.OpenProcess.restype = wintypes.HANDLE
_k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
_k32.QueryFullProcessImageNameW.argtypes = [
    wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
_k32.QueryFullProcessImageNameW.restype = wintypes.BOOL
_k32.CloseHandle.argtypes = [wintypes.HANDLE]


def _process_exe(hwnd: int) -> str:
    """File name of the process that owns the window, e.g. 'msedge.exe' (lowercase). '' on error."""
    try:
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        if not pid:
            return ""
        handle = _k32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return ""
        try:
            buf = ctypes.create_unicode_buffer(1024)
            size = wintypes.DWORD(1024)
            if not _k32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
                return ""
            return buf.value.split("\\")[-1].lower()
        finally:
            _k32.CloseHandle(handle)
    except Exception:
        return ""

# DwmGetWindowAttribute — get the true bbox (excluding DWM shadow/invisible border)
DWMWA_EXTENDED_FRAME_BOUNDS = 9
# DWMWA_CLOAKED — detect "hidden" windows (on another virtual desktop / UWP suspended)
DWMWA_CLOAKED = 14
# Windows smaller than this threshold are treated as phantom/helper and skipped
MIN_WINDOW_SIZE = 200

# Enable DPI awareness up front — otherwise the bbox will be off on HiDPI screens / scale > 100%
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
except (AttributeError, OSError):
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except (AttributeError, OSError):
        pass


def enum_windows() -> list[tuple[int, str]]:
    """Return [(hwnd, title), ...] for visible windows that have a title."""
    results: list[tuple[int, str]] = []

    def callback(hwnd: int, _: object) -> bool:
        if not win32gui.IsWindowVisible(hwnd):
            return True
        title = win32gui.GetWindowText(hwnd)
        if title.strip():
            results.append((hwnd, title))
        return True

    win32gui.EnumWindows(callback, None)
    return results


def _is_cloaked(hwnd: int) -> bool:
    """True if the window is 'cloaked' by DWM (on another virtual desktop / UWP suspended)."""
    cloaked = wintypes.DWORD()
    hr = ctypes.windll.dwmapi.DwmGetWindowAttribute(
        wintypes.HWND(hwnd),
        wintypes.DWORD(DWMWA_CLOAKED),
        ctypes.byref(cloaked),
        ctypes.sizeof(cloaked),
    )
    return hr == 0 and cloaked.value != 0


def _get_window_bbox(hwnd: int) -> tuple[int, int, int, int]:
    """Get the true bbox of the window (DWM shadow removed, DPI-aware)."""
    rect = wintypes.RECT()
    hr = ctypes.windll.dwmapi.DwmGetWindowAttribute(
        wintypes.HWND(hwnd),
        wintypes.DWORD(DWMWA_EXTENDED_FRAME_BOUNDS),
        ctypes.byref(rect),
        ctypes.sizeof(rect),
    )
    if hr != 0:  # DWM API failed — fall back to GetWindowRect
        return win32gui.GetWindowRect(hwnd)
    return rect.left, rect.top, rect.right, rect.bottom


def _effective_rect(hwnd: int) -> tuple[int, int, int, int]:
    """Rect used to assess size. If the window is minimized its bbox is off-screen
    (e.g. 183x26), so use the RESTORED size (GetWindowPlacement.rcNormalPosition)."""
    if win32gui.IsIconic(hwnd):
        try:
            return win32gui.GetWindowPlacement(hwnd)[4]  # rcNormalPosition
        except Exception:
            pass
    return _get_window_bbox(hwnd)


def find_window_by_process(process_name: str, quiet: bool = False) -> tuple[int, str] | None:
    """Find the REAL window of the process `process_name` (e.g. 'msedge.exe').

    Matches by PROCESS NAME rather than title — reliable for browsers because Chrome/Edge
    drop the "- Google Chrome"/"- Microsoft Edge" suffix when many tabs are open.
    Skips cloaked / too-small windows; if there are several, pick the one with the largest area.
    `quiet=True` -> do not log when nothing is found (used while polling for the app to launch).
    """
    want = process_name.lower()
    candidates: list[tuple[int, str, int]] = []  # (hwnd, title, area)

    for hwnd, title in enum_windows():
        if _process_exe(hwnd) != want:
            continue
        if _is_cloaked(hwnd):
            continue
        left, top, right, bottom = _effective_rect(hwnd)
        w, h = right - left, bottom - top
        if w < MIN_WINDOW_SIZE or h < MIN_WINDOW_SIZE:
            continue
        candidates.append((hwnd, title, w * h))

    if not candidates:
        if not quiet:
            logger.error("No real window found for process %r.", process_name)
        return None

    candidates.sort(key=lambda c: c[2], reverse=True)
    hwnd, title, _ = candidates[0]
    logger.info("Selected window: '%s' (hwnd=%d, %s)", title, hwnd, process_name)
    return hwnd, title


def launch_app(launch_cmd: str, process_name: str, wait_sec: float = 15.0) -> tuple[int, str] | None:
    """Launch the app, then poll until a window of `process_name` appears."""
    logger.info("Launching app: %s", launch_cmd)
    try:
        subprocess.Popen(launch_cmd, shell=True)
    except Exception as e:
        logger.error("Could not launch %r: %s", launch_cmd, e)
        return None

    deadline = time.perf_counter() + wait_sec
    poll = 0
    while time.perf_counter() < deadline:
        poll += 1
        time.sleep(0.7)
        match = find_window_by_process(process_name, quiet=True)
        if match is not None:
            logger.info("Window appeared after %d checks.", poll)
            time.sleep(0.8)  # let the app finish rendering its initial content
            return match
    logger.error("Timed out after %.0fs waiting for a %r window to appear.", wait_sec, process_name)
    return None


def _force_foreground(hwnd: int, aggressive: bool = False) -> None:
    """Force the window to the foreground.

    aggressive=True: minimize then restore — Windows ALWAYS pulls the window to the
    foreground on restore, even when a console process is holding the foreground lock.
    """
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32

    if aggressive:
        win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)
        time.sleep(0.12)
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        time.sleep(0.12)

    fg_hwnd = user32.GetForegroundWindow()
    cur_thread = kernel32.GetCurrentThreadId()
    fg_thread = user32.GetWindowThreadProcessId(fg_hwnd, None)
    target_thread = user32.GetWindowThreadProcessId(hwnd, None)

    # ALT trick to unlock Windows' anti-"steal focus" mechanism
    user32.keybd_event(0x12, 0, 0, 0)   # ALT down
    user32.keybd_event(0x12, 0, 2, 0)   # ALT up

    attached_fg = fg_thread not in (0, cur_thread)
    attached_target = target_thread not in (0, cur_thread, fg_thread)
    if attached_fg:
        user32.AttachThreadInput(cur_thread, fg_thread, True)
    if attached_target:
        user32.AttachThreadInput(cur_thread, target_thread, True)
    try:
        win32gui.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
        user32.SetActiveWindow(hwnd)
        win32gui.SetWindowPos(
            hwnd, win32con.HWND_TOP, 0, 0, 0, 0,
            win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_SHOWWINDOW,
        )
    finally:
        if attached_target:
            user32.AttachThreadInput(cur_thread, target_thread, False)
        if attached_fg:
            user32.AttachThreadInput(cur_thread, fg_thread, False)


def _bring_to_foreground(hwnd: int) -> bool:
    """Bring the window to the foreground and CONFIRM it actually came up.

    The first 2 attempts try gently (AttachThreadInput); from the 3rd, escalate to minimize/restore.
    """
    try:
        if win32gui.IsIconic(hwnd):
            logger.info("Window is minimized, restoring...")
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        else:
            win32gui.ShowWindow(hwnd, win32con.SW_SHOW)

        for attempt in range(1, 7):
            aggressive = attempt >= 3
            _force_foreground(hwnd, aggressive=aggressive)
            time.sleep(0.15)
            if win32gui.GetForegroundWindow() == hwnd:
                logger.info("Window brought to foreground (after %d attempt(s)%s).",
                            attempt, ", minimize/restore" if aggressive else "")
                return True
            logger.info("Foreground not correct yet, retrying (%d/6)%s...",
                        attempt, " [minimize/restore]" if aggressive else "")

        logger.warning(
            "Could NOT bring the window to the foreground after 6 attempts. "
            "Another app may be holding focus (fullscreen game, UAC...)."
        )
        return False
    except Exception as e:
        logger.warning("Error bringing window to foreground: %s", e)
        return False


def capture_window(hwnd: int) -> Image.Image:
    """Capture a window via bring-to-foreground + ImageGrab over its bbox.

    Works reliably with Chrome / Edge / Electron / UWP — GPU-composited apps for
    which PrintWindow usually returns an empty bitmap.
    """
    if not _bring_to_foreground(hwnd):
        raise RuntimeError(
            "Could not bring the window to the foreground, so capture was cancelled "
            "(to avoid capturing the wrong window). Click the target window and try again."
        )
    time.sleep(0.5)  # wait for DWM animation + repaint

    if win32gui.GetForegroundWindow() != hwnd:
        raise RuntimeError("Foreground changed right before capture — cancelled to avoid a wrong shot.")

    left, top, right, bottom = _get_window_bbox(hwnd)
    width, height = right - left, bottom - top
    if width <= 0 or height <= 0:
        raise RuntimeError(f"Invalid window size: {width}x{height}")

    logger.info("Window bbox: (%d,%d)-(%d,%d) = %dx%d", left, top, right, bottom, width, height)
    return ImageGrab.grab(bbox=(left, top, right, bottom), all_screens=True)


def capture_target(process_name: str, label: str | None = None,
                   launch_cmd: str | None = None,
                   launch_wait: float = 15.0) -> tuple[Image.Image, str]:
    """High-level: find (or launch) the `process_name` window, then capture it.

    Returns (PIL image, window title). Raises if it cannot find/capture.
    """
    friendly = label or process_name
    match = find_window_by_process(process_name)
    if match is None and launch_cmd:
        match = launch_app(launch_cmd, process_name, launch_wait)
    if match is None:
        raise RuntimeError(
            f"No {friendly} window found ({process_name}). "
            f"Open the app first, or enable the auto-launch option."
        )
    hwnd, title = match
    img = capture_window(hwnd)
    return img, title
