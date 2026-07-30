"""Lets main.py's spike loop reach the tray icon (in shell.py) without the
two modules importing each other -- main.py runs standalone (dev server,
console) just as often as it runs under the tray-equipped desktop shell."""

from __future__ import annotations

from typing import Callable, Optional

from .detector import Spike

_listener: Optional[Callable[[Spike], None]] = None
_toggle_notifications_cb: Optional[Callable[[], None]] = None
_notifications_enabled_cb: Optional[Callable[[], bool]] = None


def set_spike_listener(callback: Optional[Callable[[Spike], None]]) -> None:
    global _listener
    _listener = callback


def notify_spike(spike: Spike) -> None:
    if _listener is not None:
        _listener(spike)


def set_notifications_control(toggle_cb: Callable[[], None], enabled_cb: Callable[[], bool]) -> None:
    """Lets the tray's "Notifications" menu item flip the same
    notifications_enabled setting the web UI's toggle controls, without
    tray.py depending on main.py's AppState directly."""
    global _toggle_notifications_cb, _notifications_enabled_cb
    _toggle_notifications_cb = toggle_cb
    _notifications_enabled_cb = enabled_cb


def toggle_notifications() -> None:
    if _toggle_notifications_cb is not None:
        _toggle_notifications_cb()


def notifications_enabled() -> bool:
    return _notifications_enabled_cb() if _notifications_enabled_cb is not None else True
