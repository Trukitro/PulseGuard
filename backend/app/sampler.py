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

    def sample(self) -> Tick:
        psutil = self._psutil
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

        return {
            "ts": time.time(),
            "ram_gb": round(vm.used / (1024**3), 2),
            "ram_pct": round(vm.percent, 1),
            "cpu_pct": cpu_pct,
            "gpu_pct": round(gpu_pct, 1) if gpu_pct is not None else None,
            "vram_gb": round(vram_gb, 2) if vram_gb is not None else None,
        }

    def close(self) -> None:
        if self._nvml is not None:
            try:
                self._nvml.nvmlShutdown()
            except Exception:
                pass
