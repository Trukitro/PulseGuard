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

import webview

from . import tray_state
from .settings import load_settings
from .tray import TrayIcon

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


def _format_spike_summary(spike: dict) -> str:
    metric = spike["metric"]
    top = spike.get("top", [])
    label = {"ram": "RAM", "cpu": "CPU", "gpu": "GPU"}.get(metric, metric.upper())

    if metric == "cpu":
        unit = "%"
        attribution = f"{top[0]['name']} ({top[0]['cpu_pct']:.0f}%)" if top else ""
    elif metric == "gpu":
        unit = "%"
        attribution = f"{top[0]['name']} ({top[0]['vram_gb']:.2f} GB VRAM)" if top else ""
    else:
        unit = " GB"
        attribution = f"{top[0]['name']} (+{top[0]['delta_gb']:.2f} GB)" if top else ""

    base = f"{label} spike: {spike['from_value']:.1f}{unit} -> {spike['to_value']:.1f}{unit}"
    return f"{base} ({attribution})" if attribution else base


class JsApi:
    """Bridge exposed to the page as window.pywebview.api. Each window gets
    its own instance wired to only the transitions it should trigger: the
    main window's page can enter mini mode, the mini widget's page can exit
    it back to the main window."""

    def __init__(self, enter_mini=None, exit_mini=None) -> None:
        self._enter_mini = enter_mini
        self._exit_mini = exit_mini

    def open_external(self, url: str) -> None:
        """The one sanctioned way anything in this app reaches the user's
        real default browser -- explicit, opt-in links via nav-guard.js."""
        if url.startswith(("http://", "https://")):
            webbrowser.open(url)

    def enter_mini_mode(self) -> None:
        if self._enter_mini:
            self._enter_mini()

    def exit_mini_mode(self) -> None:
        if self._exit_mini:
            self._exit_mini()


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

    def _enter_mini_mode() -> None:
        window.hide()
        mini_window.show()

    def _exit_mini_mode() -> None:
        mini_window.hide()
        window.show()
        window.restore()

    window = webview.create_window(
        title=APP_TITLE,
        url=f"http://127.0.0.1:{port}",
        js_api=JsApi(enter_mini=_enter_mini_mode),
        width=1280,
        height=860,
        min_size=(960, 640),
        background_color="#0B0E14",
        maximized=True,
    )

    # Pre-created hidden rather than created on demand: pywebview's behavior
    # for creating a new window after webview.start() has begun is less
    # predictable across backends than toggling show()/hide() on a window
    # that already exists.
    mini_window = webview.create_window(
        title="PulseGuard Mini",
        url=f"http://127.0.0.1:{port}/?mode=mini",
        js_api=JsApi(exit_mini=_exit_mini_mode),
        width=480,
        height=200,
        resizable=False,
        frameless=True,
        easy_drag=True,
        on_top=True,
        hidden=True,
        background_color="#0B0E14",
    )

    exiting = False

    def _open_from_tray() -> None:
        mini_window.hide()
        window.show()
        window.restore()
        window.maximize()

    def _exit_from_tray() -> None:
        nonlocal exiting
        exiting = True
        tray_icon.stop()
        mini_window.destroy()
        window.destroy()

    tray_icon = TrayIcon(on_open=_open_from_tray, on_exit=_exit_from_tray)
    tray_icon.run_detached()
    tray_state.set_spike_listener(lambda spike: tray_icon.show_spike(_format_spike_summary(spike)))

    def _on_closing() -> bool:
        # window.destroy() (from the tray's Exit item) fires this same closing
        # event, same as clicking the X button -- without the `exiting` flag,
        # hiding here would swallow a genuine exit and the window would just
        # reappear-then-hide instead of the process actually ending.
        if exiting:
            return True
        # The tray icon is the only "is this still running" indicator once the
        # window's gone, so closing the window hides it instead of quitting --
        # only the tray's Exit item actually ends the process.
        window.hide()
        return False

    window.events.closing += _on_closing

    def _on_mini_closing() -> bool:
        # Frameless windows have no visible close button, but Alt+F4 (or
        # similar) can still send a close signal -- treat it the same as the
        # widget's own restore button rather than losing the window entirely.
        if exiting:
            return True
        _exit_mini_mode()
        return False

    mini_window.events.closing += _on_mini_closing

    # pywebview's `icon` start() param only does anything on the GTK/QT backends;
    # on Windows the window/taskbar icon comes from the exe's own icon resource,
    # which pulseguard.spec already embeds via PyInstaller's --icon.
    webview.start(debug=args.debug)
    tray_icon.stop()


if __name__ == "__main__":
    main()
