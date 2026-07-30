"""Detects whether the foreground window is genuinely fullscreen (covers the
entire monitor, taskbar included) as a heuristic for "the user is in a game
or video and shouldn't be interrupted." Deliberately distinct from a merely
maximized window, whose bottom edge stops short of the taskbar."""

from __future__ import annotations

import ctypes

_user32 = ctypes.windll.user32

# Windows shell window classes -- never treat these as "fullscreen game",
# even though they can legitimately cover the whole monitor (e.g. desktop).
_IGNORED_CLASSES = {"Progman", "WorkerW", "Shell_TrayWnd"}


class _RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


class _MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.c_ulong),
        ("rcMonitor", _RECT),
        ("rcWork", _RECT),
        ("dwFlags", ctypes.c_ulong),
    ]


_MONITOR_DEFAULTTONEAREST = 2


def is_foreground_fullscreen() -> bool:
    try:
        hwnd = _user32.GetForegroundWindow()
        if not hwnd:
            return False

        class_name = ctypes.create_unicode_buffer(256)
        _user32.GetClassNameW(hwnd, class_name, 256)
        if class_name.value in _IGNORED_CLASSES:
            return False

        window_rect = _RECT()
        if not _user32.GetWindowRect(hwnd, ctypes.byref(window_rect)):
            return False

        monitor = _user32.MonitorFromWindow(hwnd, _MONITOR_DEFAULTTONEAREST)
        if not monitor:
            return False

        info = _MONITORINFO()
        info.cbSize = ctypes.sizeof(_MONITORINFO)
        if not _user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
            return False

        m = info.rcMonitor
        return (
            window_rect.left <= m.left
            and window_rect.top <= m.top
            and window_rect.right >= m.right
            and window_rect.bottom >= m.bottom
        )
    except Exception:
        # Never let a detection glitch block notifications outright.
        return False
