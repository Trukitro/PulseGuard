"""Rolling-baseline spike detection: flags a sudden RAM increase, not just a high total."""

from __future__ import annotations

from collections import deque
from typing import Optional, TypedDict

from .sampler import Tick
from .settings import Settings


class Spike(TypedDict):
    ts: float
    metric: str
    from_gb: float
    to_gb: float
    window_s: int
    window_start_ts: float


class _RollingWindow:
    def __init__(self, window_s: float) -> None:
        self.window_s = window_s
        self._samples: deque[tuple[float, float]] = deque()

    def add(self, ts: float, value: float) -> None:
        self._samples.append((ts, value))
        cutoff = ts - self.window_s
        while self._samples and self._samples[0][0] < cutoff:
            self._samples.popleft()

    def min_value(self) -> Optional[float]:
        return min(v for _, v in self._samples) if self._samples else None

    def earliest_ts(self) -> Optional[float]:
        return self._samples[0][0] if self._samples else None


class Detector:
    """Flags a RAM spike when either the absolute % ceiling is breached or the
    delta-GB-per-window threshold is crossed. A cooldown suppresses re-firing
    every tick while the RAM level stays elevated."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._ram_window = _RollingWindow(settings.window_s)
        self._cooldown_until: float = 0.0

    def update_settings(self, settings: Settings) -> None:
        self.settings = settings
        self._ram_window.window_s = settings.window_s

    def process(self, tick: Tick) -> Optional[Spike]:
        ts = tick["ts"]
        self._ram_window.add(ts, tick["ram_gb"])

        if ts < self._cooldown_until:
            return None

        baseline = self._ram_window.min_value()
        if baseline is None:
            return None

        delta = tick["ram_gb"] - baseline
        ceiling_hit = tick["ram_pct"] >= self.settings.ram_pct_ceiling
        delta_hit = delta >= self.settings.ram_delta_gb
        if not (ceiling_hit or delta_hit):
            return None

        self._cooldown_until = ts + self.settings.window_s
        return {
            "ts": ts,
            "metric": "ram",
            "from_gb": round(baseline, 2),
            "to_gb": tick["ram_gb"],
            "window_s": self.settings.window_s,
            "window_start_ts": self._ram_window.earliest_ts() or ts,
        }
