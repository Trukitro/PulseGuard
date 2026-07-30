"""Rolling-baseline spike detection: flags a sudden RAM or CPU increase, not
just a high total. Each metric tracks its own rolling window/cooldown so a
RAM spike and a CPU spike can fire independently in the same tick."""

from __future__ import annotations

from collections import deque
from typing import Callable, Optional, TypedDict

from .sampler import Tick
from .settings import Settings


class Spike(TypedDict):
    ts: float
    metric: str
    from_value: float
    to_value: float
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


def _cpu_avg(tick: Tick) -> float:
    cpu_pct = tick["cpu_pct"]
    return sum(cpu_pct) / len(cpu_pct) if cpu_pct else 0.0


def _gpu_pct(tick: Tick) -> float:
    # 0.0 on machines with no NVIDIA GPU (sampler reports gpu_pct=None there),
    # which keeps this metric a permanent no-op rather than a crash.
    return tick["gpu_pct"] if tick["gpu_pct"] is not None else 0.0


class _MetricDetector:
    """Flags a spike when either the absolute ceiling is breached or the
    delta-per-window threshold is crossed. A cooldown suppresses re-firing
    every tick while the value stays elevated."""

    def __init__(
        self,
        metric: str,
        window_s: float,
        ceiling: float,
        delta: float,
        window_value_fn: Callable[[Tick], float],
        ceiling_value_fn: Optional[Callable[[Tick], float]] = None,
    ) -> None:
        self.metric = metric
        self.window = _RollingWindow(window_s)
        self.window_s = window_s
        self.ceiling = ceiling
        self.delta = delta
        self._window_value_fn = window_value_fn
        self._ceiling_value_fn = ceiling_value_fn or window_value_fn
        self._cooldown_until = 0.0

    def process(self, tick: Tick) -> Optional[Spike]:
        ts = tick["ts"]
        value = self._window_value_fn(tick)
        self.window.add(ts, value)

        if ts < self._cooldown_until:
            return None

        baseline = self.window.min_value()
        if baseline is None:
            return None

        delta = value - baseline
        ceiling_hit = self._ceiling_value_fn(tick) >= self.ceiling
        delta_hit = delta >= self.delta
        if not (ceiling_hit or delta_hit):
            return None

        self._cooldown_until = ts + self.window_s
        return {
            "ts": ts,
            "metric": self.metric,
            "from_value": round(baseline, 2),
            "to_value": round(value, 2),
            "window_s": self.window_s,
            "window_start_ts": self.window.earliest_ts() or ts,
        }


class Detector:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._metrics = [
            _MetricDetector(
                "ram",
                settings.window_s,
                settings.ram_pct_ceiling,
                settings.ram_delta_gb,
                window_value_fn=lambda t: t["ram_gb"],
                ceiling_value_fn=lambda t: t["ram_pct"],
            ),
            _MetricDetector(
                "cpu",
                settings.window_s,
                settings.cpu_pct_ceiling,
                settings.cpu_delta_pct,
                window_value_fn=_cpu_avg,
            ),
            _MetricDetector(
                "gpu",
                settings.window_s,
                settings.gpu_pct_ceiling,
                settings.gpu_delta_pct,
                window_value_fn=_gpu_pct,
            ),
        ]

    def update_settings(self, settings: Settings) -> None:
        self.settings = settings
        for m in self._metrics:
            m.window.window_s = settings.window_s
            m.window_s = settings.window_s
            if m.metric == "ram":
                m.ceiling = settings.ram_pct_ceiling
                m.delta = settings.ram_delta_gb
            elif m.metric == "cpu":
                m.ceiling = settings.cpu_pct_ceiling
                m.delta = settings.cpu_delta_pct
            elif m.metric == "gpu":
                m.ceiling = settings.gpu_pct_ceiling
                m.delta = settings.gpu_delta_pct

    def process(self, tick: Tick) -> list[Spike]:
        spikes = []
        for m in self._metrics:
            spike = m.process(tick)
            if spike is not None:
                spikes.append(spike)
        return spikes
