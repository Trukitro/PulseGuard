"""Native Windows toast for spike events, via winotify. Falls back to a console line
when winotify or its Windows dependency isn't available (e.g. running tests on non-Windows)."""

from __future__ import annotations

from .detector import Spike
from .paths import ICON_PATH as _ICON_PATH


class Notifier:
    def __init__(self) -> None:
        try:
            from winotify import Notification

            self._Notification = Notification
        except Exception:
            self._Notification = None

    def notify(self, spike: Spike) -> None:
        top = spike.get("top", [])
        metric = spike["metric"]

        if metric == "cpu":
            headline = f"{top[0]['name']} ({top[0]['cpu_pct']:.0f}%)" if top else "no single process stands out"
            unit = "%"
            title = "PulseGuard - CPU spike"
        elif metric == "gpu":
            headline = f"{top[0]['name']} ({top[0]['vram_gb']:.2f} GB VRAM)" if top else "no single process stands out"
            unit = "%"
            title = "PulseGuard - GPU spike"
        else:
            headline = f"{top[0]['name']} (+{top[0]['delta_gb']:.2f} GB)" if top else "no single process stands out"
            unit = " GB"
            title = "PulseGuard - RAM spike"

        message = (
            f"{spike['from_value']:.1f}{unit} -> {spike['to_value']:.1f}{unit} "
            f"in {spike['window_s']}s. Top: {headline}"
        )

        self.notify_custom(title, message)

    def notify_custom(self, title: str, message: str) -> None:
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
