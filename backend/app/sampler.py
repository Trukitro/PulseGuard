"""Polls psutil + pynvml for one system-wide tick."""

from __future__ import annotations

import time
from typing import Optional, TypedDict


class Tick(TypedDict):
    ts: float
    ram_gb: float
    ram_pct: float
    cpu_pct: list[float]
    gpu_pct: Optional[float]
    vram_gb: Optional[float]
    disk_read_bps: float
    disk_write_bps: float
    net_sent_bps: float
    net_recv_bps: float


class Sampler:
    def __init__(self) -> None:
        import psutil

        self._psutil = psutil
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

        psutil.cpu_percent(percpu=True)  # first call always returns 0.0, prime it

        # Disk/network counters are cumulative since boot; rates are a delta
        # over the time since the previous sample, so the very first tick
        # (no prior reading yet) reports 0 for all four rather than a spike
        # from a huge implicit "since boot" delta.
        self._prev_ts: Optional[float] = None
        self._prev_disk = psutil.disk_io_counters()
        self._prev_net = psutil.net_io_counters()

    def sample(self) -> Tick:
        psutil = self._psutil
        ts = time.time()
        vm = psutil.virtual_memory()
        cpu_pct = psutil.cpu_percent(percpu=True)

        gpu_pct: Optional[float] = None
        vram_gb: Optional[float] = None
        if self._nvml is not None and self._gpu_handle is not None:
            try:
                util = self._nvml.nvmlDeviceGetUtilizationRates(self._gpu_handle)
                mem = self._nvml.nvmlDeviceGetMemoryInfo(self._gpu_handle)
                gpu_pct = float(util.gpu)
                vram_gb = mem.used / (1024**3)
            except Exception:
                gpu_pct = None
                vram_gb = None

        disk = psutil.disk_io_counters()
        net = psutil.net_io_counters()
        dt = ts - self._prev_ts if self._prev_ts is not None else 0.0
        if dt > 0 and disk is not None and self._prev_disk is not None:
            disk_read_bps = max(0.0, (disk.read_bytes - self._prev_disk.read_bytes) / dt)
            disk_write_bps = max(0.0, (disk.write_bytes - self._prev_disk.write_bytes) / dt)
        else:
            disk_read_bps = 0.0
            disk_write_bps = 0.0
        if dt > 0 and net is not None and self._prev_net is not None:
            net_sent_bps = max(0.0, (net.bytes_sent - self._prev_net.bytes_sent) / dt)
            net_recv_bps = max(0.0, (net.bytes_recv - self._prev_net.bytes_recv) / dt)
        else:
            net_sent_bps = 0.0
            net_recv_bps = 0.0
        self._prev_ts = ts
        self._prev_disk = disk
        self._prev_net = net

        return {
            "ts": ts,
            "ram_gb": round(vm.used / (1024**3), 2),
            "ram_pct": round(vm.percent, 1),
            "cpu_pct": cpu_pct,
            "gpu_pct": round(gpu_pct, 1) if gpu_pct is not None else None,
            "vram_gb": round(vram_gb, 2) if vram_gb is not None else None,
            "disk_read_bps": round(disk_read_bps, 1),
            "disk_write_bps": round(disk_write_bps, 1),
            "net_sent_bps": round(net_sent_bps, 1),
            "net_recv_bps": round(net_recv_bps, 1),
        }

    def close(self) -> None:
        if self._nvml is not None:
            try:
                self._nvml.nvmlShutdown()
            except Exception:
                pass
