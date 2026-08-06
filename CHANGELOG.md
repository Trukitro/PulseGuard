# Changelog

All notable changes to this project are documented here.
Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.31.0] - 2026-08-06

### Fixed
- **Spike logging has been silently failing on any database created under
  the original v0.1.x/v0.2.0 schema, since v0.3.0.** That schema's `spikes`
  table had `from_gb`/`to_gb` columns with a `NOT NULL` constraint. v0.3.0
  widened spike detection past RAM-only and added metric-agnostic
  `from_value`/`to_value` columns instead, but `_migrate_spikes_table`
  deliberately left the old columns in place (to preserve existing spike
  history) without dropping their `NOT NULL` constraint -- and
  `log_spike()`'s INSERT never filled them in. Every spike insert on such a
  database has been throwing `sqlite3.IntegrityError: NOT NULL constraint
  failed: spikes.from_gb` ever since. Before v0.26.0's loop-resilience fix,
  this would silently kill the whole monitoring loop the moment any spike
  fired -- a very plausible root cause (or contributor) to the original
  "reconnect does nothing, everything freezes" reports, since gaming
  sessions are exactly when a RAM/CPU/GPU spike is likely. After v0.26.0 it
  became a spammed-but-caught error instead, visible in the Debug tab.
  `History` now detects the legacy columns at startup and populates them
  alongside the new ones on every insert, satisfying the old constraint
  without touching existing data. Verified against a simulated legacy
  schema, a fresh schema, and a copy of the reporter's real database (which
  did have this exact broken schema).

### Why
Found while investigating a real gaming session's Debug tab: `Backend
errors` was spammed with this exact IntegrityError, and the session's
History chart showed clear RAM/CPU/GPU spikes with "No spikes in this
range" -- direct confirmation the bug was live and actively eating spike
data during the crash investigation itself.

## [0.30.0] - 2026-08-06

### Added
- GPU temperature, power draw, and driver-reported throttle state (NVIDIA/
  NVML), sampled every tick alongside utilization/VRAM. A new "GPU health"
  card on the dashboard shows all three live; "Throttle" reads "None"
  normally and turns red listing the active reason(s) -- HW slowdown, HW
  power brake, HW/SW thermal slowdown, SW power cap, sync boost -- when the
  GPU itself reports something external is constraining it right now.
  These are persisted to history (`ticks.gpu_temp_c`, `gpu_power_w`,
  `gpu_throttle_json`, migrated in for existing databases) and included in
  `/api/history`. Debug tab's GPU column includes them per tick too.
- Crash/shutdown event detector: a new "Recent shutdown / crash events"
  section in the Debug tab reads Windows' own Event Log for unexpected
  shutdowns (Kernel-Power 41), hardware errors (WHEA-Logger -- CPU/memory/
  PCIe), and the paired EventLog 6008, going back 14 days. Each event is
  paired with PulseGuard's own last known tick from right before it
  happened (RAM/CPU/GPU/temp/power/throttle), when PulseGuard was running
  at the time. New `GET /api/events` endpoint; `crash_events.py` uses
  pywin32's `win32evtlog` (added to requirements + PyInstaller
  hiddenimports).
- Help panel documents both.

### Why
Motivated by intermittent full-system freezes during gaming (monitors go
black, fans spike to 100%, audio keeps running briefly, then the whole
machine hangs) that look GPU/power related but weren't visible anywhere in
the app, and can't be observed by *any* running software once the machine
actually hangs -- Windows itself only records what happened after the fact,
on the next boot. Verified against the reporter's real machine: the crash
detector immediately surfaced 32 real events in the last 30 days, including
a Kernel-Power 41 unexpected shutdown paired with a WHEA hardware error on
the GPU's PCI Express root port ~11 seconds apart -- consistent with a
PCIe-link/power issue rather than a driver crash (zero
"display driver stopped responding and recovered" events were found, which
is what a pure software/TDR issue would normally log).

(v0.29.0 was skipped: its tag push failed to trigger a release build due to
a one-off CI issue, so its changes -- the GPU health tracking above -- were
folded into this version instead. A `workflow_dispatch` fallback trigger
was added to the Release workflow so a future occurrence can be retried
without needing to delete and re-push a tag.)

## [0.28.0] - 2026-07-31

### Added
- The running app version (from the v0.26.0 `/api/version` endpoint) is now
  shown next to the logo in the header, e.g. "v0.28.0" -- so it's always
  visible which build you're on without opening the Debug tab or Help.

## [0.27.0] - 2026-07-31

### Added
- Debug tab: a new hidden drawer (toggle button next to History/Help) with
  a live raw data log split into three columns -- RAM, CPU, GPU -- one line
  per incoming tick with a timestamp and the exact raw value, so you can
  see at a glance whether ticks are still arriving at all and what they
  actually contain.
- A "Backend" section in the same tab polls the `/api/debug` endpoint
  (added in v0.26.0) every 3s while open: current version, loop iteration
  count, how long ago the backend's sampling loop last completed a cycle,
  current WS connection count, and the most recent backend errors (with
  traceback) if any occurred.
- A "Connection events" log records every WS open/close and every
  Reconnect click (manual or the self-healing watchdog's automatic one)
  with a timestamp, client-side, for this window's session.
- Together, this is meant to answer the exact question this tab was asked
  for: if a freeze happens again, "Loop last tick" tells you whether the
  backend loop itself is still alive (should no longer be possible to kill
  after v0.26.0's fix, but this is the way to confirm it) versus the
  problem being only in the WebSocket layer -- two failure modes that look
  identical from the main dashboard alone.
- Help panel documents the Debug tab.

## [0.26.0] - 2026-07-31

### Fixed
- **Likely root cause of the recurring "reconnect does nothing, all
  monitoring freezes" bug.** The backend's sampling loop (`AppState._loop`)
  ran its entire per-tick body -- psutil sampling, SQLite writes, process
  snapshotting, notifications -- with zero exception handling. Any single
  transient failure in any of those (a psutil hiccup, an NVML error, a
  locked SQLite file, ...) propagated out of the loop's `asyncio.Task` and
  killed it *permanently* -- monitoring stopped for good, silently, with
  nothing in the console beyond asyncio's one-line "Task exception was
  never retrieved". Reconnecting the WebSocket afterward could never fix
  it: reconnecting only reopens the socket, it doesn't restart the dead
  loop, so no new ticks would ever arrive again regardless of how many
  times Reconnect was clicked -- exactly the symptom reported. The loop
  body is now wrapped in try/except: a failed iteration is logged (with
  full traceback) and skipped, and monitoring keeps ticking on the next
  cycle no matter what went wrong. Verified with an isolated test that
  injects a mid-iteration exception and confirms the loop logs it and
  keeps running afterward.

### Added
- Backend diagnostics: an in-memory ring buffer (`AppState.debug_log`,
  last 200 entries) now records every loop error (with traceback) and every
  WS connect/disconnect, and a heartbeat (`loop_iterations`,
  `last_loop_ts`) tracks whether the sampling loop itself is alive.
- `GET /api/debug`: exposes the above (plus current WS connection count)
  over plain REST -- deliberately independent of the WebSocket, so it can
  answer even when the WS is the thing that's broken, and can tell apart
  "backend loop died" (heartbeat age keeps growing no matter what) from
  "only the socket dropped" (heartbeat stays fresh). This is the data feed
  behind the frontend Debug tab landing in the next version.
- `GET /api/version`: current app version, for both the debug endpoint and
  the frontend version display landing in a future version.

## [0.25.0] - 2026-07-30

### Added
- Custom trigger alarms (frontend): a new "Triggers" card in Settings lets
  you define your own absolute-value alarms -- pick a metric (RAM in GB, or
  CPU/GPU in %), a threshold, and how often (in minutes) to keep reminding
  you while the value stays at or above it. Add/remove triggers freely;
  they persist through the existing Settings save/load round-trip.
- Each trigger has a "View top consumers" link that closes Settings,
  switches the ring/timeline selection to that trigger's metric, turns on
  the process panel's Live view, and scrolls it into view -- so you can
  immediately see what's actually using the resource that just alarmed.
- Trigger alerts now show as a toast (reusing the existing alert-toast
  component via a new generic `showCustom()`) and pulse the corresponding
  ring, the same visual language as spike detection.
- Help panel documents the new Triggers feature.

## [0.24.0] - 2026-07-30

### Added
- Custom trigger alarms (backend): user-defined absolute-value alerts,
  independent of the existing %-ceiling spike detector -- e.g. "notify me
  when RAM crosses 28 GB", with a configurable repeat-reminder interval
  while the condition holds. New `TriggerEngine` (`triggers.py`) tracks
  per-trigger last-fired times in memory, fires again once the reminder
  interval elapses, and forgets the last-fired time the instant the value
  drops back below threshold so the next crossing alerts immediately
  instead of waiting out a stale interval.
- `Settings.triggers`: a list of `{id, metric, threshold_value,
  remind_interval_s, enabled}` entries, persisted and round-tripped through
  the existing generic `/api/settings` GET/POST (no new endpoints needed).
- `Notifier.notify_custom(title, message)`: generic toast helper extracted
  from `notify()` so trigger alerts reuse the same winotify/console-fallback
  path as spike notifications, instead of duplicating it.
- The tick loop now checks every enabled trigger each cycle, sends a toast
  (respecting `notifications_enabled` and game-mode auto-silence, same as
  spikes) when one crosses, and broadcasts a new `{"type": "trigger_alert",
  "data": {...}}` WebSocket message for the frontend to consume.

### Note
This release ships the backend engine and data model only. The Settings UI
for creating/editing triggers, the "top consumers for this resource" view,
and the Help documentation update land together in the next version
(v0.25.0).

## [0.23.0] - 2026-07-30

### Fixed
- Clicking Reconnect while Stale/Disconnected did nothing in the real
  packaged app. Root cause: `catchUp()` was gated by
  `document.visibilityState`, which can read "hidden" in pywebview's
  WebView2 even when the window is genuinely visible/foreground -- a
  mismatch between what the API reports and what the user can plainly see.
  `catchUp(force)` now lets the manual Reconnect button bypass that check
  (and the debounce) entirely.
- Along the way, found and fixed a real bug introduced by that same change:
  `window.addEventListener("focus", catchUp)` passed the FocusEvent object
  through as catchUp's `force` parameter, and since an Event object is
  truthy, it silently bypassed the visibility/debounce guards on every
  focus event -- defeating their purpose for the automatic listener path.
  Fixed by wrapping it in `() => catchUp()`.

### Added
- Self-healing watchdog: every 5s while the page is visible, if data has
  gone meaningfully stale, force a reconnect + catch-up regardless of
  whether any visibilitychange/focus event fired -- not every pywebview/
  WebView2 version is guaranteed to deliver those transitions reliably for
  a minimized-then-restored native window. This is what makes monitoring
  "siempre live y constante": the backend's sampling loop already never
  stops recording regardless of GUI state (it's an independent asyncio
  task, unaffected by whether the window is visible), and now the frontend
  reliably catches back up instead of depending on a single event or a
  single manual click succeeding.

Verified: with `document.visibilityState` mocked to "hidden", the
automatic focus listener now correctly stays blocked (confirming the
Event-as-force bug is fixed), while the manual Reconnect button correctly
still fetches immediately regardless (confirming the intended bypass
works).

## [0.22.0] - 2026-07-30

### Changed
- Help and History are now left-side slide-out drawers (hamburger-menu
  style) instead of inline blocks that pushed the whole dashboard down.
  Opening one closes the other (mutually exclusive), and a click on the
  backdrop closes whichever is open. Still hidden by default, toggled by
  their header buttons.

Verified: opening Help correctly shows it and hides History if it was open;
opening History correctly hides Help; clicking the backdrop closes
whichever drawer is open. The underlying CSS transform/specificity was also
independently verified correct via direct stylesheet inspection (rule
presence, order, and specificity), since this session's browser tool
couldn't reliably report live layout for these particular elements (the
same "pane not composited" limitation noted earlier in this session).

## [0.21.0] - 2026-07-30

### Added
- "Help" panel: a new in-app reference explaining what PulseGuard does, what
  the ring colors/percentages/secondary amounts mean, the Timeline chart
  (single-metric vs. combined "Show all" mode), Disk/Network cards, the
  process panel's Spikes-vs-Live-view toggle, the live indicator's
  Live/Stale/Disconnected states and Reconnect action, Mini mode, History,
  the system tray, and what each setting controls. Purely static content --
  no backend changes.

Verified live: all 10 help sections render with the correct headings, and
the RAM/CPU/GPU color-meaning swatches render with the exact green/amber/red
colors matching the real ring tokens (rgb(108, 203, 95) / rgb(255, 185, 0) /
rgb(232, 17, 35)).

## [0.20.0] - 2026-07-30

### Added
- "History" view: a new panel with 24h/7 days/30 days preset buttons showing
  a combined RAM/CPU/GPU timeline (reusing spike-chart's existing combined
  mode) plus a table of every spike in the selected range (when, metric,
  from -> to, top process), so a user can review what happened with their
  PC's resources in previous sessions rather than only the live dashboard.
  No backend changes needed -- the existing /api/history endpoint already
  accepted arbitrary d/h/m/s range strings.

Verified live: opening History and switching between range presets
correctly re-fetches and re-renders both the chart and the spike table,
including genuinely old spike data (from RAM spikes manufactured much
earlier in this project's development) still present in the SQLite history
and rendering with correct formatting and process attribution.

## [0.19.0] - 2026-07-30

### Added
- Tray menu gained a checkable "Notifications" item that flips the same
  notifications_enabled setting the web UI's toggle controls, without
  tray.py depending on main.py's AppState directly -- routed through
  tray_state.py's existing decoupling pattern (the same one that lets the
  spike listener reach the tray icon). A "Force RAM cleanup" action was
  considered and deliberately dropped: on modern Windows the OS already
  manages memory well, and forcing a trim has limited real value and can
  cause temporary extra paging.

Verified against the real pystray classes (not just a mock): instantiating
the actual TrayIcon and invoking the real MenuItem's callable toggles
notifications_enabled and its `checked` property reflects the new state
correctly, staying in sync with main.state.settings across repeated toggles.

## [0.18.0] - 2026-07-30

### Changed
- Ring color scheme is now a proactive traffic-light model instead of only
  reacting to an actual detected spike: green below a configurable warning
  ratio of ceiling (default 50%), amber from there up to the danger margin,
  red within a configurable number of percentage points of ceiling (default
  12) -- or still red for an actual spike's full window regardless. New
  shared settings (not per-resource, to avoid sprawl): "Warning past (% of
  ceiling)" and "Red within (points of ceiling)".
- Normal-state ring color changed from blue to green (new `--pg-good` token)
  to match the traffic-light convention the new thresholds imply.
- RAM and GPU rings now show both the percentage (primary) and the absolute
  amount (secondary, smaller text) -- e.g. "63%" over "20.1 GB" -- so it's
  clear how close a %-based ceiling is without doing mental math against
  total system RAM/VRAM. CPU is unchanged (no natural absolute unit).

Verified live with real data: ring colors and thresholds behave correctly
against actual RAM/CPU/GPU readings, the settings round-trip (including the
one field that converts between a stored fraction and a displayed percent)
works both via REST and in the browser, and the green default color was
confirmed via computed style (`rgb(108, 203, 95)`, matching `--pg-good`
exactly). pulse-ring's secondary-display logic additionally verified in an
isolated test.

## [0.17.0] - 2026-07-30

### Added
- Manual "Reconnect" link next to the live indicator, visible only when its
  state is Stale or Disconnected -- lets the user force an immediate
  reconnect attempt instead of waiting out the exponential backoff.
  ws-client.js gained `reconnectNow()`: cancels any pending scheduled
  reconnect, resets the backoff delay, and immediately opens a fresh
  connection (tearing down the old socket's `onclose` handler first so it
  can't also schedule a redundant reconnect).
- The live indicator's tooltip now shows the current refresh cadence (e.g.
  "Refreshing every 2s"), kept in sync with the poll_interval_s setting.

Verified in an isolated test (mocked WebSocket): reconnectNow() immediately
opens a new connection, resets the backoff delay to 1000ms, and correctly
cancels the old scheduled reconnect (no duplicate connection appears when
the original backoff window elapses). Button visibility/click wiring and
the tooltip text verified live in a browser.

## [0.16.0] - 2026-07-30

### Added
- "Chart history (minutes)" setting controls how much historical data the
  timeline chart backfills and keeps in memory, separate from the backend's
  existing `retention_days` (SQLite pruning). spike-chart.js's fixed
  `MAX_POINTS = 400` is now `setRetention(minutes, pollIntervalS)`, deriving
  the actual point cap from the desired time span and current poll rate
  (so a slower poll interval doesn't quietly cover less time), re-applied
  whenever either setting changes and immediately trimming any buffers that
  are now oversized.

Verified in an isolated test: 60min at a 2s poll interval correctly derives
1800 points, 5min derives 150; pushing past the cap correctly trims from the
front; and shrinking retention after data has accumulated immediately trims
existing buffers down to the new cap rather than waiting for it to age out
naturally. Also verified the REST round-trip (load default 60, save 30,
persisted correctly) and that /api/history accepts the resulting range.

## [0.15.0] - 2026-07-30

### Added
- Disk I/O and Network I/O metrics: sampler.py now computes read/write and
  up/down byte rates as a delta over psutil's cumulative disk/network
  counters since the previous tick (the first tick after startup reports 0
  rather than a spike from the implicit since-boot delta). New "Disk" and
  "Network" stat cards show live formatted rates (B/s -> KB/s -> MB/s ->
  GB/s). Display only in this version -- no spike detection or chart
  integration yet, consistent with how RAM/CPU/GPU started before their own
  detection was added.
- history.py's `ticks` table gained the four new rate columns, migrated in
  place for existing databases (existing rows just have no reading for
  them, not a data transformation).

Verified live: real disk/network activity from this dev session showed up
correctly formatted (hundreds of MB/s during heavy disk I/O, hundreds of
KB/s of background network traffic) in both the REST history payload and
the rendered stat cards.

## [0.14.0] - 2026-07-30

### Added
- "Live view" toggle on the process panel: continuously shows the current
  top-N processes for whichever resource is selected (RAM/CPU/GPU), polled
  every 2s via a new `/api/processes/top` endpoint, instead of only showing
  processes at the last spike. Switching rings while live view is on
  immediately re-fetches for the newly selected metric. `ProcessTracker`
  gained `top_ram()` (a live ranking by absolute RSS, no baseline needed --
  unlike the delta-based `top_deltas()` spike attribution uses).

### Fixed
- `top_cpu()` (used by both CPU spike attribution and the new Live view)
  was including PID 0, the System Idle Process. psutil reports its
  cpu_percent() as accumulated *idle* time, the inverse of "usage" -- it
  can read in the thousands of percent on a quiet multi-core machine and
  would dominate any top-N-by-usage list with a number that means the
  opposite of what it looks like. Now excluded.
- Added a `Cache-Control: no-cache` middleware to all responses. The
  packaged app always serves the frontend from the same origin
  (127.0.0.1:<port>) across every version, and pywebview's WebView2 profile
  persists its HTTP cache between runs -- without this, a user upgrading
  PulseGuard could keep seeing stale JS/CSS from the previous version.
  Revalidation (not no-store) still lets ETag/304s save bandwidth.

Verified: the REST endpoint returns correct top-N data for all three
metrics; the idle-process fix confirmed by direct before/after comparison
against this machine's real process list; the full column-mapping/render
logic (spike vs. live, all three metrics, both empty states) verified in
an isolated Node-based test since a stale module cache in the test browser
tab made in-browser verification of process-list.js unreliable; and the
toggle-driven fetch/title-update/metric-switch wiring verified live in a
real browser tab.

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
