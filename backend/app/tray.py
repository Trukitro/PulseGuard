"""System tray icon: shows PulseGuard is running in the background, offers
Open/Exit, and reflects the most recent spike via its tooltip (only when
notifications are enabled -- see tray_state.py) rather than firing a second,
redundant popup alongside the native winotify toast."""

from __future__ import annotations

import threading
from typing import Callable, Optional

import pystray
from PIL import Image

from . import tray_state
from .paths import ICON_PATH

_RUNNING_TITLE = "PulseGuard - running"
_SPIKE_HOLD_S = 15.0
_TOOLTIP_MAX_LEN = 127  # Windows NOTIFYICONDATA szTip limit


def _load_icon_image() -> Image.Image:
    if ICON_PATH.exists():
        return Image.open(ICON_PATH)
    # Never let a missing icon asset silently mean "no tray icon at all".
    return Image.new("RGBA", (32, 32), (40, 153, 245, 255))


class TrayIcon:
    def __init__(self, on_open: Callable[[], None], on_exit: Callable[[], None]) -> None:
        self._icon = pystray.Icon(
            "PulseGuard",
            icon=_load_icon_image(),
            title=_RUNNING_TITLE,
            menu=pystray.Menu(
                pystray.MenuItem("Open PulseGuard", lambda: on_open(), default=True),
                pystray.MenuItem(
                    "Notifications",
                    lambda: tray_state.toggle_notifications(),
                    checked=lambda _item: tray_state.notifications_enabled(),
                ),
                pystray.MenuItem("Exit", lambda: on_exit()),
            ),
        )
        self._revert_timer: Optional[threading.Timer] = None

    def run_detached(self) -> None:
        threading.Thread(target=self._icon.run, daemon=True).start()

    def show_spike(self, summary: str) -> None:
        self._icon.title = f"PulseGuard - {summary}"[:_TOOLTIP_MAX_LEN]
        if self._revert_timer is not None:
            self._revert_timer.cancel()
        self._revert_timer = threading.Timer(_SPIKE_HOLD_S, self._revert_title)
        self._revert_timer.daemon = True
        self._revert_timer.start()

    def _revert_title(self) -> None:
        self._icon.title = _RUNNING_TITLE

    def stop(self) -> None:
        if self._revert_timer is not None:
            self._revert_timer.cancel()
        self._icon.stop()
