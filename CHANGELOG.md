# Changelog

All notable changes to this project are documented here.
Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.6.0] - 2026-07-30

### Added
- Notifications on/off setting (`notifications_enabled`, default on), toggled
  via a new "General" settings card. When off, spikes still stream over WS,
  log to history, and show in the UI (toast/process-list/chart) -- only the
  native winotify toast is suppressed.

## [0.5.0] - 2026-07-30

### Changed
- Settings panel: RAM/CPU/GPU threshold groups are now three separate
  `fluent-card` elements instead of divider-separated sections inside one
  card, matching the app's existing "quiet Fluent cards" visual language
  more literally.

## [0.4.0] - 2026-07-30

### Added
- GPU spike detection: detector.py tracks GPU utilization (`gpu_pct`) the
  same way it tracks CPU, with its own rolling window/cooldown/ceiling/delta.
  On machines without an NVIDIA GPU this metric is a permanent no-op
  (gpu_pct is treated as 0).
- GPU spike attribution is by per-process VRAM usage via NVML
  (`nvmlDeviceGetComputeRunningProcesses`), not utilization -- NVIDIA doesn't
  expose per-process GPU utilization, only per-process memory.
- Settings panel now has individual RAM/CPU/GPU sections (ceiling + delta
  threshold each), instead of only exposing RAM. CPU's fields existed in the
  backend since v0.3.0 but weren't reachable from the UI until now.
- process-list, alert-toast now render a GPU-specific VRAM column/message.

Verified: the real NVML per-process query runs cleanly against this
machine's actual NVIDIA GPU; the settings panel loads/saves all seven
fields (RAM/CPU/GPU ceiling+delta plus poll interval) round-trip correctly
through the REST API; and the full GPU-spike rendering path (process-list,
toast, chart) was verified live in a browser via the same component methods
the WS handler calls, plus GPU is selectable and switches the chart like
RAM/CPU already did.

## [0.3.0] - 2026-07-30

### Added
- CPU spike detection: detector.py now tracks RAM and CPU independently, each
  with its own rolling window/cooldown, so a sudden CPU spike is flagged the
  same way a RAM spike is.
- CPU spike attribution is a live top-N ranking by psutil's per-process
  cpu_percent() (a rate since the last sample), not a delta -- there's no
  "baseline" to diff a rate against the way there is for RAM's RSS.
- New settings: `cpu_pct_ceiling` (default 90%), `cpu_delta_pct` (default 40
  points) -- available via the REST API now; a settings-panel UI for them
  lands in v0.4.0 alongside GPU.
- process-list, alert-toast, and spike-chart are now metric-aware: CPU
  spikes render a "CPU %" column/message instead of RAM's "Delta/Total (GB)".

### Changed
- Spike records are now metric-agnostic: `from_gb`/`to_gb` renamed to
  `from_value`/`to_value` in the WS/REST contract and the SQLite schema.
  Existing `history.db` files from v0.1.x/v0.2.0 are migrated in place
  (new columns added and backfilled from the old ones; old columns are left
  alone).

## [0.2.0] - 2026-07-30

### Added
- Pulse rings are now clickable (and keyboard-focusable): selecting RAM/CPU/GPU
  switches the RAM timeline chart to that resource's own timeline, with its
  own y-axis scale and its own filtered spike markers.

### Fixed
- spike-chart crashed switching to the CPU metric on backfilled history data:
  `/api/history` ticks carry an already-averaged `cpu_pct_avg` while live
  WebSocket ticks carry a per-core `cpu_pct` array; the chart's CPU averaging
  only handled the array shape.

## [0.1.1] - 2026-07-30

### Fixed
- Installer Start Menu / Desktop shortcuts showed a generic blank icon.
  `IconFilename` pointed at `{app}\assets\icon.ico`, which doesn't exist
  post-install -- PyInstaller's onedir layout actually places it under
  `{app}\_internal\assets\icon.ico`. Shortcuts now point at the exe itself,
  which already carries the icon via PyInstaller's `--icon`.
- Removed a dead `icon=` argument to `webview.start()`: pywebview only
  supports it on the GTK/QT backends, not Windows' EdgeChromium.

## [Unreleased]

### Added
- Backend core: psutil/pynvml sampler, rolling-baseline spike detector,
  per-process RSS delta ranking, SQLite history log, winotify wrapper.
- FastAPI app: `/ws` tick/spike stream, `/api/history`, `/api/settings`.
- Frontend: native Web Components UI (pulse-ring, spike-chart, process-list,
  alert-toast) styled with Fluent 2 web components and Chart.js.
- pywebview desktop shell: chromeless native window, single-instance lock,
  nav-guard external-link handling.
- PyInstaller `--onedir` build and Inno Setup installer.
- GitHub Actions release pipeline on `v*.*.*` tags.
