"""Custom user-defined absolute-value alarms (distinct from the %-ceiling
spike detection in detector.py) -- e.g. "alert me if RAM crosses 28 GB",
repeating every N seconds while the condition holds, and stopping the moment
it drops back below threshold."""

from __future__ import annotations

from typing import Optional, TypedDict

from .sampler import Tick


class Trigger(TypedDict):
    id: str
    metric: str  # "ram" | "cpu" | "gpu"
    threshold_value: float
    remind_interval_s: float
    enabled: bool


class TriggerAlert(TypedDict):
    trigger_id: str
    metric: str
    value: float
    threshold_value: float


def _metric_value(tick: Tick, metric: str) -> Optional[float]:
    if metric == "ram":
        return tick["ram_gb"]
    if metric == "cpu":
        cpu_pct = tick["cpu_pct"]
        return sum(cpu_pct) / len(cpu_pct) if cpu_pct else 0.0
    if metric == "gpu":
        return tick["gpu_pct"]
    return None


class TriggerEngine:
    def __init__(self) -> None:
        # In-memory only -- deliberately not persisted. A restart re-arming
        # every trigger's reminder clock is the right default (matches the
        # detector's own cooldown, which also doesn't survive a restart).
        self._last_fired: dict[str, float] = {}

    def check(self, triggers: list[Trigger], tick: Tick) -> list[TriggerAlert]:
        alerts: list[TriggerAlert] = []
        now = tick["ts"]
        active_ids = set()

        for trig in triggers:
            if not trig.get("enabled", True):
                continue
            value = _metric_value(tick, trig["metric"])
            if value is None or value < trig["threshold_value"]:
                continue

            active_ids.add(trig["id"])
            last_fired = self._last_fired.get(trig["id"], 0.0)
            interval_s = max(trig.get("remind_interval_s", 300), 5)
            if now - last_fired >= interval_s:
                self._last_fired[trig["id"]] = now
                alerts.append(
                    {
                        "trigger_id": trig["id"],
                        "metric": trig["metric"],
                        "value": round(value, 2),
                        "threshold_value": trig["threshold_value"],
                    }
                )

        # Once a trigger's condition clears, forget its last-fired time so
        # the next crossing alerts immediately instead of waiting out
        # whatever was left of the old reminder interval.
        for trig_id in list(self._last_fired):
            if trig_id not in active_ids:
                del self._last_fired[trig_id]

        return alerts
