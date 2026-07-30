"""Native Windows toast for spike events, via winotify. Falls back to a console line
when winotify or its Windows dependency isn't available (e.g. running tests on non-Windows)."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from .detector import Spike

_ICON_PATH = Path(__file__).resolve().parents[2] / "assets" / "icon.ico"


class Notifier:
    def __init__(self) -> None:
        try:
            from winotify import Notification

            self._Notification = Notification
        except Exception:
            self._Notification = None

    def notify(self, spike: Spike) -> None:
        top = spike.get("top", [])
        headline = (
            f"{top[0]['name']} (+{top[0]['delta_gb']:.2f} GB)"
            if top
            else "no single process stands out"
        )
        title = "PulseGuard — RAM spike"
        message = f"{spike['from_gb']:.1f} -> {spike['to_gb']:.1f} GB in {spike['window_s']}s. Top: {headline}"

        if self._Notification is None:
            print(f"[notify] {title}: {message}")
            return

        try:
            icon = str(_ICON_PATH) if _ICON_PATH.exists() else ""
            toast = self._Notification(
                app_id="PulseGuard",
                title=title,
                msg=message,
                icon=icon,
            )
            toast.show()
        except Exception as exc:
            print(f"[notify:fallback] {title}: {message} ({exc})")
