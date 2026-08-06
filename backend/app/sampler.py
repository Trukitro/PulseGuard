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
    gpu_temp_c: Optional[float]
    gpu_power_w: Optional[float]
    gpu_throttle: list[str]
    disk_read_bps: float
    disk_write_bps: float
    net_sent_bps: float
    net_recv_bps: float


# Only the flags that indicate something is actively constraining the GPU --
# GpuIdle/UserDefinedClocks/ApplicationsClocksSetting etc. are normal/expected
# states, not diagnostically interesting for "is my card in trouble". HwSlowdown
# and HwPowerBrakeSlowdown in particular are asserted by an external hardware
# signal -- classic symptom of a struggling PSU or a bad power connection, the
# exact kind of thing a user chasing random shutdowns under load wants to see.
_THROTTLE_REASON_LABELS: dict[str, str] = {
    "nvmlClocksThrottleReasonHwSlowdown": "HW slowdown (power/thermal protection signal)",
    "nvmlClocksThrottleReasonHwPowerBrakeSlowdown": "HW power brake (PSU/power connector protection)",
    "nvmlClocksThrottleReasonHwThermalSlowdown": "HW thermal slowdown",
    "nvmlClocksThrottleReasonSwThermalSlowdown": "SW thermal slowdown",
    "nvmlClocksThrottleReasonSwPowerCap": "SW power cap",
    "nvmlClocksThrottleReasonSyncBoost": "Sync boost",
}


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
        gpu_temp_c: Optional[float] = None
        gpu_power_w: Optional[float] = None
        gpu_throttle: list[str] = []
        if self._nvml is not None and self._gpu_handle is not None:
            # Each metric gets its own try/except -- some driver/GPU combos
            # support utilization but not power draw (or vice versa), and one
            # unsupported query shouldn't blank out the others.
            try:
                util = self._nvml.nvmlDeviceGetUtilizationRates(self._gpu_handle)
                mem = self._nvml.nvmlDeviceGetMemoryInfo(self._gpu_handle)
                gpu_pct = float(util.gpu)
                vram_gb = mem.used / (1024**3)
            except Exception:
                gpu_pct = None
                vram_gb = None
            try:
                gpu_temp_c = float(
                    self._nvml.nvmlDeviceGetTemperature(self._gpu_handle, self._nvml.NVML_TEMPERATURE_GPU)
                )
            except Exception:
                gpu_temp_c = None
            try:
                gpu_power_w = self._nvml.nvmlDeviceGetPowerUsage(self._gpu_handle) / 1000.0
            except Exception:
                gpu_power_w = None
            try:
                reasons = self._nvml.nvmlDeviceGetCurrentClocksThrottleReasons(self._gpu_handle)
                gpu_throttle = [
                    label
                    for attr, label in _THROTTLE_REASON_LABELS.items()
                    if reasons & getattr(self._nvml, attr, 0)
                ]
            except Exception:
                gpu_throttle = []

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
            "gpu_temp_c": round(gpu_temp_c, 1) if gpu_temp_c is not None else None,
            "gpu_power_w": round(gpu_power_w, 1) if gpu_power_w is not None else None,
            "gpu_throttle": gpu_throttle,
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
