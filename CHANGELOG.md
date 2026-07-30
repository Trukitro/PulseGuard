# Changelog

All notable changes to this project are documented here.
Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.13.0] - 2026-07-30

### Added
- Game-mode auto-silence: gamemode.py detects whether the foreground window
  genuinely covers the entire monitor (taskbar included) -- distinct from a
  merely maximized window, whose bottom edge stops short of the taskbar.
  When true, spike notifications (the OS toast) are automatically
  suppressed regardless of the user's own notifications_enabled toggle, so
  a spike doesn't pop up over a game or fullscreen video. The tray tooltip
  still updates either way since it's passive (hover-only, not an
  interruption).

Verified: a genuinely fullscreen test window correctly returns True, while
an otherwise-identical maximized (non-fullscreen) window correctly returns
False -- confirming the core maximized-vs-fullscreen distinction the
heuristic depends on.

## [0.12.0] - 2026-07-30

### Added
- Mini-widget mode: a "Mini mode" button collapses the app into a small
  (480x200), frameless, always-on-top floating window showing just the
  three rings, for passive monitoring. A small restore button (top-right,
  visible only in mini mode) returns to the full maximized main window.
  Implemented as a second pre-created (hidden) pywebview window loading the
  same page with `?mode=mini`, toggled via show()/hide() rather than
  created on demand -- creating a new window after `webview.start()` has
  begun is less predictable across pywebview's backends than toggling one
  that already exists. Alt+F4 on the frameless mini widget restores the
  main window rather than losing it entirely.

Verified: the `?mode=mini` page correctly hides everything but the ring
cluster and shows the restore button; both buttons correctly call the
pywebview bridge (and gracefully warn instead of erroring in a plain
dev-mode browser tab with no bridge); and an isolated two-window test
confirmed pywebview's hidden/frameless/on_top creation plus show()/hide()
toggling runs without error end to end.

## [0.11.0] - 2026-07-30

### Added
- "Show all" toggle above the timeline: displays RAM/CPU/GPU simultaneously
  as a 0-100% share of ceiling (RAM as `ram_pct` rather than absolute GB, so
  all three share one axis), with Chart.js's built-in legend click-to-hide
  per line. Selecting a specific ring exits combined mode and returns to the
  single-metric detail view with accurate spike markers -- RAM spikes are
  recorded in GB, not %, so they're deliberately not plotted in combined
  mode to avoid a misleading scale.

Verified live: combined mode shows correct %-based values for all three
resources on a shared 0-100 axis, and clicking any ring correctly exits
combined mode and restores accurate single-metric spike markers.

## [0.10.0] - 2026-07-30

### Changed
- Main window now opens maximized by default, both on cold start and when
  reopened from the system tray.

Verified with an isolated pywebview window via Win32 `IsZoomed()`: the
window genuinely opens maximized, not just visually large.

## [0.9.1] - 2026-07-30

### Fixed
- WebView2 throttles/freezes JS execution and rendering while the window is
  minimized or unfocused for a while, so the timeline chart and gauges could
  go stale and no longer match real system usage once the window was
  restored. The backend's sampling loop is unaffected (it's a separate
  Python asyncio task, not page JS), and native winotify toasts still fire
  normally during that period -- only the in-app visual state was stale.
  Fixed by re-fetching `/api/history` and snapping the gauges/chart to the
  latest real data on `visibilitychange`/`focus` (and on WS reconnect),
  instead of waiting for the next live tick.

### Added
- Live/heartbeat indicator next to the logo: pulses on every real tick and
  reads "Live", "Stale (Xs)", or "Disconnected" so the user can tell at a
  glance whether the app is actually reporting in real time.

Verified: the catch-up fetch-and-apply path runs correctly and updates the
gauges from fresh server data; the live indicator correctly reports "Stale"
once ticks stop landing. The underlying throttling behavior itself was
observed directly in a long-hidden browser tab during testing -- a real
analog of the reported bug, not just a theoretical one.

## [0.9.0] - 2026-07-30

### Changed
- Settings cards (RAM/CPU/GPU/General/footer) now lay out horizontally in a
  wrapping row instead of stacking in one narrow column, so they use the
  available width and wrap to the next row once they no longer fit.

Verified at both the app's default (1280px) and minimum (960px) window
widths: cards flow left-to-right and wrap correctly at both sizes.

## [0.8.0] - 2026-07-30

### Added
- System tray icon (pystray): PulseGuard now shows a persistent tray icon
  while running, with an "Open PulseGuard" / "Exit" menu. Closing the main
  window hides it to the tray instead of quitting -- only the tray's Exit
  item actually ends the process, so the tray icon is a real "is this still
  running" indicator, not just decoration.
- The tray icon's tooltip reflects the most recent spike (only when
  notifications are enabled, mirroring the native toast) for ~15s before
  reverting to "PulseGuard - running" -- a passive indicator alongside the
  toast, not a second popup.

### Fixed
- A real bug caught during testing: `window.destroy()` (from the tray's Exit
  item) fires the same `closing` event as clicking the window's X button.
  Without tracking an explicit exiting flag, the close-to-tray handler would
  swallow a genuine exit request and just hide the window again instead of
  letting the process end.

Verified with a dedicated test harness exercising the real TrayIcon/
tray_state code: close-to-tray, spike-driven tooltip updates, reopen from
tray, and clean exit-from-tray (process actually terminates) all confirmed
working, plus a full rebuild/run of the packaged exe and installer with the
new pystray/Pillow dependencies.

## [0.7.0] - 2026-07-30

### Added
- Startup-with-Windows is now toggleable from the in-app settings ("General"
  card), not just at install time via the Inno Setup checkbox. autostart.py
  reads/writes the `HKCU\...\Run` registry entry directly. On startup, the
  app treats the registry as ground truth and syncs the in-memory setting to
  it, since Windows' own Task Manager > Startup tab can also toggle this
  outside the app.

Verified: toggling via both the REST API and the UI switch actually adds/
removes the real registry value (checked with a separate process reading
it back), and the app starts up correctly reflecting whatever the registry
currently says.

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
