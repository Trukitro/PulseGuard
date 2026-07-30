"""Tracks per-process RSS over time so a spike can be attributed to a process."""

from __future__ import annotations

from collections import deque
from typing import TypedDict


class ProcessDelta(TypedDict):
    name: str
    pid: int
    delta_gb: float
    total_gb: float


class ProcessTracker:
    def __init__(self, history_s: float = 120.0) -> None:
        import psutil

        self._psutil = psutil
        self.history_s = history_s
        self._snapshots: deque[tuple[float, dict[int, tuple[str, int]]]] = deque()

    def snapshot(self, ts: float) -> None:
        psutil = self._psutil
        procs: dict[int, tuple[str, int]] = {}
        for p in psutil.process_iter(["pid", "name", "memory_info"]):
            try:
                info = p.info
                rss = info["memory_info"].rss if info["memory_info"] else 0
                procs[info["pid"]] = (info["name"] or "?", rss)
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue

        self._snapshots.append((ts, procs))
        cutoff = ts - self.history_s
        while self._snapshots and self._snapshots[0][0] < cutoff:
            self._snapshots.popleft()

    def top_deltas(self, since_ts: float, top_n: int = 5) -> list[ProcessDelta]:
        if not self._snapshots:
            return []

        latest_ts, latest = self._snapshots[-1]
        baseline = {}
        for ts, procs in self._snapshots:
            if ts <= since_ts:
                baseline = procs
            else:
                break

        deltas: list[ProcessDelta] = []
        for pid, (name, rss) in latest.items():
            base_rss = baseline.get(pid, (name, 0))[1]
            delta = rss - base_rss
            if delta <= 0:
                continue
            deltas.append(
                {
                    "name": name,
                    "pid": pid,
                    "delta_gb": round(delta / (1024**3), 3),
                    "total_gb": round(rss / (1024**3), 3),
                }
            )

        deltas.sort(key=lambda d: d["delta_gb"], reverse=True)
        return deltas[:top_n]
