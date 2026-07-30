"""pywebview bootstrap: runs the FastAPI app in a background thread and wraps
it in a native, chromeless-free (but browser-chrome-free) window -- no
address bar, tabs, or bookmarks, and the taskbar entry carries the app's own
title/icon rather than the browser engine's. See PulseGuard-project-plan.md
sections 7 and 8 for the native-app requirements this file implements."""

from __future__ import annotations

import argparse
import ctypes
import socket
import sys
import threading
import webbrowser
from pathlib import Path

import webview

from .settings import load_settings

ASSETS_DIR = Path(__file__).resolve().parents[2] / "assets"
ICON_PATH = ASSETS_DIR / "icon.ico"

APP_TITLE = "PulseGuard"
_MUTEX_NAME = "Local\\PulseGuardSingleInstance"
_ERROR_ALREADY_EXISTS = 183

# Keeps the mutex handle alive for the process lifetime; Windows releases the
# lock once every handle to it is closed (or the process exits).
_mutex_handle = None


def _acquire_single_instance_lock() -> bool:
    """Returns True if this is the only running instance."""
    global _mutex_handle
    _mutex_handle = ctypes.windll.kernel32.CreateMutexW(None, False, _MUTEX_NAME)
    return ctypes.windll.kernel32.GetLastError() != _ERROR_ALREADY_EXISTS


def _focus_existing_window() -> None:
    user32 = ctypes.windll.user32
    hwnd = user32.FindWindowW(None, APP_TITLE)
    if hwnd:
        SW_RESTORE = 9
        user32.ShowWindow(hwnd, SW_RESTORE)
        user32.SetForegroundWindow(hwnd)


def _port_is_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


def _find_available_port(preferred: int) -> int:
    port = preferred
    while not _port_is_free(port):
        port += 1
    return port


def _wait_until_serving(port: int, timeout_s: float = 10.0) -> bool:
    import time

    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if not _port_is_free(port):
            return True
        time.sleep(0.1)
    return False


def _start_server(port: int) -> None:
    import uvicorn

    from .main import app

    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()


class JsApi:
    """Bridge for frontend/js/nav-guard.js's explicit, opt-in external links --
    the only sanctioned way anything in this app reaches the user's real
    default browser."""

    def open_external(self, url: str) -> None:
        if url.startswith(("http://", "https://")):
            webbrowser.open(url)


def main() -> None:
    parser = argparse.ArgumentParser(description="PulseGuard desktop shell")
    parser.add_argument("--debug", action="store_true", help="enable WebView2 DevTools (dev only)")
    args = parser.parse_args()

    if not _acquire_single_instance_lock():
        _focus_existing_window()
        sys.exit(0)

    settings = load_settings()
    port = _find_available_port(settings.port)
    _start_server(port)
    if not _wait_until_serving(port):
        print("PulseGuard backend failed to start", file=sys.stderr)
        sys.exit(1)

    webview.create_window(
        title=APP_TITLE,
        url=f"http://127.0.0.1:{port}",
        js_api=JsApi(),
        width=1280,
        height=860,
        min_size=(960, 640),
        background_color="#0B0E14",
    )
    webview.start(debug=args.debug, icon=str(ICON_PATH) if ICON_PATH.exists() else None)


if __name__ == "__main__":
    main()
