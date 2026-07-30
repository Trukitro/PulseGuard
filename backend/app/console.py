"""Phase 1 console runner: exercises sampler -> detector -> snapshot -> history
with no server/UI, so the backend core can be validated on its own.

    python -m app.console
    python -m app.console --simulate-spike
"""

from __future__ import annotations

import argparse
import threading
import time

from .detector import Detector
from .history import History
from .notifier import Notifier
from .sampler import Sampler
from .settings import load_settings
from .snapshot import ProcessTracker


def _simulate_spike(delay_s: float, hold_s: float, mb: int) -> None:
    time.sleep(delay_s)
    print(f"[simulate] allocating {mb} MB to trigger a real RAM spike...")
    block = bytearray(mb * 1024 * 1024)
    for i in range(0, len(block), 4096):
        block[i] = 1  # touch each page so RSS actually grows, not just a virtual reservation
    time.sleep(hold_s)
    print("[simulate] releasing allocation")
    del block


def main() -> None:
    parser = argparse.ArgumentParser(description="PulseGuard backend console runner")
    parser.add_argument("--simulate-spike", action="store_true", help="manufacture a real RAM spike to test detection")
    parser.add_argument("--simulate-delay", type=float, default=8.0)
    parser.add_argument("--simulate-hold", type=float, default=15.0)
    parser.add_argument("--simulate-mb", type=int, default=800)
    args = parser.parse_args()

    cfg = load_settings()
    sampler = Sampler()
    detector = Detector(cfg)
    tracker = ProcessTracker()
    history = History()
    notifier = Notifier()

    if args.simulate_spike:
        threading.Thread(
            target=_simulate_spike,
            args=(args.simulate_delay, args.simulate_hold, args.simulate_mb),
            daemon=True,
        ).start()

    print(f"PulseGuard console - polling every {cfg.poll_interval_s}s. Ctrl+C to stop.")
    try:
        while True:
            tick = sampler.sample()
            history.log_tick(tick)
            tracker.snapshot(tick["ts"])

            cpu_avg = sum(tick["cpu_pct"]) / len(tick["cpu_pct"]) if tick["cpu_pct"] else 0.0
            gpu_str = f'{tick["gpu_pct"]}%' if tick["gpu_pct"] is not None else "n/a"
            print(
                f'[{time.strftime("%H:%M:%S")}] RAM {tick["ram_gb"]:.2f} GB ({tick["ram_pct"]:.1f}%)'
                f'  CPU {cpu_avg:.1f}%  GPU {gpu_str}'
            )

            for spike in detector.process(tick):
                if spike["metric"] == "cpu":
                    spike["top"] = tracker.top_cpu()
                    top_line = ", ".join(
                        f'{p["name"]} ({p["cpu_pct"]:.1f}%)' for p in spike["top"]
                    ) or "no per-process usage available"
                    unit = "%"
                elif spike["metric"] == "gpu":
                    spike["top"] = tracker.top_gpu()
                    top_line = ", ".join(
                        f'{p["name"]} ({p["vram_gb"]:.2f} GB VRAM)' for p in spike["top"]
                    ) or "no per-process VRAM usage available"
                    unit = "%"
                else:
                    spike["top"] = tracker.top_deltas(spike["window_start_ts"])
                    top_line = ", ".join(
                        f'{p["name"]} (+{p["delta_gb"]:.2f} GB)' for p in spike["top"]
                    ) or "no per-process delta available"
                    unit = " GB"
                history.log_spike(spike)
                notifier.notify(spike)
                print(
                    f'  !! SPIKE {spike["metric"]}: {spike["from_value"]:.2f}{unit} -> {spike["to_value"]:.2f}{unit}'
                    f' over {spike["window_s"]}s - {top_line}'
                )

            time.sleep(cfg.poll_interval_s)
    except KeyboardInterrupt:
        print("\nStopping.")
    finally:
        sampler.close()
        tracker.close()
        history.close()


if __name__ == "__main__":
    main()
