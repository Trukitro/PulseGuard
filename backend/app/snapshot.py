"""Tracks per-process RSS, CPU usage, and GPU VRAM over time so a spike can be
attributed to a process. RAM/GPU attribution is a delta or live ranking by
memory (VRAM); CPU attribution is a live ranking by psutil's per-process
cpu_percent() (a rate since the last sample -- there's no separate "baseline"
to diff against). NVML has no per-process GPU *utilization* API, only
per-process memory, so GPU attribution is VRAM-based rather than %-based."""

from __future__ import annotations

from collections import deque
from typing import TypedDict


class ProcessDelta(TypedDict):
    name: str
    pid: int
    delta_gb: float
    total_gb: float


class ProcessCpuUsage(TypedDict):
    name: str
    pid: int
    cpu_pct: float


class ProcessGpuUsage(TypedDict):
    name: str
    pid: int
    vram_gb: float


class ProcessTracker:
    def __init__(self, history_s: float = 120.0) -> None:
        import psutil

        self._psutil = psutil
        self.history_s = history_s
        self._snapshots: deque[tuple[float, dict[int, tuple[str, int]]]] = deque()
        self._latest_cpu: dict[int, tuple[str, float]] = {}

        self._nvml = None
        self._gpu_handle = None
        try:
            import pynvml

            pynvml.nvmlInit()
            self._nvml = pynvml
            self._gpu_handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        except Exception:
            self._nvml = None
            self._gpu_handle = None

    def snapshot(self, ts: float) -> None:
        psutil = self._psutil
        procs: dict[int, tuple[str, int]] = {}
        latest_cpu: dict[int, tuple[str, float]] = {}
        # Reusing process_iter's internal per-pid Process cache across calls is what
        # makes this non-blocking cpu_percent() meaningful (rate since the previous
        # snapshot) instead of always reporting 0.
        for p in psutil.process_iter(["pid", "name", "memory_info", "cpu_percent"]):
            try:
                info = p.info
                name = info["name"] or "?"
                rss = info["memory_info"].rss if info["memory_info"] else 0
                procs[info["pid"]] = (name, rss)
                latest_cpu[info["pid"]] = (name, info["cpu_percent"] or 0.0)
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue

        self._snapshots.append((ts, procs))
        cutoff = ts - self.history_s
        while self._snapshots and self._snapshots[0][0] < cutoff:
            self._snapshots.popleft()
        self._latest_cpu = latest_cpu

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

    def top_cpu(self, top_n: int = 5) -> list[ProcessCpuUsage]:
        usage: list[ProcessCpuUsage] = [
            {"name": name, "pid": pid, "cpu_pct": round(cpu_pct, 1)}
            for pid, (name, cpu_pct) in self._latest_cpu.items()
            if cpu_pct > 0
        ]
        usage.sort(key=lambda d: d["cpu_pct"], reverse=True)
        return usage[:top_n]

    def top_gpu(self, top_n: int = 5) -> list[ProcessGpuUsage]:
        if self._nvml is None or self._gpu_handle is None:
            return []
        try:
            gpu_procs = self._nvml.nvmlDeviceGetComputeRunningProcesses(self._gpu_handle)
        except Exception:
            return []

        usage: list[ProcessGpuUsage] = []
        for p in gpu_procs:
            used = p.usedGpuMemory or 0
            try:
                name = self._psutil.Process(p.pid).name()
            except (self._psutil.NoSuchProcess, self._psutil.AccessDenied):
                name = "?"
            usage.append({"name": name, "pid": p.pid, "vram_gb": round(used / (1024**3), 3)})

        usage.sort(key=lambda d: d["vram_gb"], reverse=True)
        return usage[:top_n]

    def close(self) -> None:
        if self._nvml is not None:
            try:
                self._nvml.nvmlShutdown()
            except Exception:
                pass
