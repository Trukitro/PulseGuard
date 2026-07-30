# Changelog

All notable changes to this project are documented here.
Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

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
