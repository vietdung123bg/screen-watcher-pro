"""Chụp một cửa sổ Windows cụ thể (Chrome / Edge / ...).

Tái sử dụng nguyên vẹn kỹ thuật từ main_qwen_ocr.py:
  - Tìm cửa sổ THẬT theo tiêu đề (loại cloaked / phantom).
  - Đưa cửa sổ lên foreground đáng tin cậy (AttachThreadInput + minimize/restore).
  - Chụp theo bbox thật (DwmGetWindowAttribute), DPI-aware.
  - Tùy chọn tự khởi chạy app nếu chưa mở.
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

# Khai báo argtypes để không bị truncate HANDLE trên Python 64-bit
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_k32 = ctypes.windll.kernel32
_k32.OpenProcess.restype = wintypes.HANDLE
_k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
_k32.QueryFullProcessImageNameW.argtypes = [
    wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
_k32.QueryFullProcessImageNameW.restype = wintypes.BOOL
_k32.CloseHandle.argtypes = [wintypes.HANDLE]


def _process_exe(hwnd: int) -> str:
    """Tên file tiến trình sở hữu cửa sổ, vd 'msedge.exe' (lowercase). '' nếu lỗi."""
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

# DwmGetWindowAttribute — lấy bbox thật (loại trừ shadow/invisible border của DWM)
DWMWA_EXTENDED_FRAME_BOUNDS = 9
# DWMWA_CLOAKED — phát hiện cửa sổ "ẩn" (virtual desktop khác / UWP suspended)
DWMWA_CLOAKED = 14
# Cửa sổ nhỏ hơn ngưỡng này coi là phantom/helper, bỏ qua
MIN_WINDOW_SIZE = 200

# Bật DPI awareness ngay từ đầu — không thì bbox sẽ lệch trên màn hình HiDPI / scale > 100%
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
except (AttributeError, OSError):
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except (AttributeError, OSError):
        pass


def enum_windows() -> list[tuple[int, str]]:
    """Trả về [(hwnd, title), ...] cho các cửa sổ visible có tiêu đề."""
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
    """True nếu cửa sổ bị DWM 'cloak' (đang ở virtual desktop khác / UWP suspended)."""
    cloaked = wintypes.DWORD()
    hr = ctypes.windll.dwmapi.DwmGetWindowAttribute(
        wintypes.HWND(hwnd),
        wintypes.DWORD(DWMWA_CLOAKED),
        ctypes.byref(cloaked),
        ctypes.sizeof(cloaked),
    )
    return hr == 0 and cloaked.value != 0


def _get_window_bbox(hwnd: int) -> tuple[int, int, int, int]:
    """Lấy bbox thật của cửa sổ (đã loại shadow của DWM, DPI-aware)."""
    rect = wintypes.RECT()
    hr = ctypes.windll.dwmapi.DwmGetWindowAttribute(
        wintypes.HWND(hwnd),
        wintypes.DWORD(DWMWA_EXTENDED_FRAME_BOUNDS),
        ctypes.byref(rect),
        ctypes.sizeof(rect),
    )
    if hr != 0:  # DWM API thất bại — fallback sang GetWindowRect
        return win32gui.GetWindowRect(hwnd)
    return rect.left, rect.top, rect.right, rect.bottom


def _effective_rect(hwnd: int) -> tuple[int, int, int, int]:
    """Rect để đánh giá kích thước. Nếu cửa sổ đang minimize thì bbox bị off-screen
    (vd 183x26), nên dùng kích thước lúc KHÔI PHỤC (GetWindowPlacement.rcNormalPosition)."""
    if win32gui.IsIconic(hwnd):
        try:
            return win32gui.GetWindowPlacement(hwnd)[4]  # rcNormalPosition
        except Exception:
            pass
    return _get_window_bbox(hwnd)


def find_window_by_process(process_name: str, quiet: bool = False) -> tuple[int, str] | None:
    """Tìm cửa sổ THẬT của tiến trình `process_name` (vd 'msedge.exe').

    Khớp theo TÊN TIẾN TRÌNH thay vì tiêu đề — tin cậy với trình duyệt vì Chrome/Edge
    bỏ hậu tố "- Google Chrome"/"- Microsoft Edge" khi mở nhiều tab.
    Bỏ qua cửa sổ cloaked / quá nhỏ; nếu nhiều cửa sổ thì chọn cái diện tích lớn nhất.
    `quiet=True` -> không log khi không tìm thấy (dùng lúc poll chờ app khởi chạy).
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
    """Ép cửa sổ lên foreground.

    aggressive=True: minimize rồi restore — Windows LUÔN kéo cửa sổ lên foreground
    khi restore, kể cả khi tiến trình console đang giữ foreground lock.
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

    # ALT-trick mở khóa cơ chế chống "steal focus" của Windows
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
    """Đưa cửa sổ lên foreground và XÁC NHẬN nó thực sự đã nổi lên.

    2 lần đầu thử nhẹ (AttachThreadInput), từ lần 3 escalate sang minimize/restore.
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
