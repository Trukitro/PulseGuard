import {
  provideFluentDesignSystem,
  fluentButton,
  fluentCard,
  fluentTextField,
  fluentDivider,
  fluentSwitch,
  baseLayerLuminance,
  StandardLuminance,
} from "../vendor/fluent-web-components.min.js";
import "./nav-guard.js";
import { WsClient } from "./ws-client.js";
import "./components/pulse-ring.js";
import "./components/spike-chart.js";
import "./components/process-list.js";
import "./components/alert-toast.js";

provideFluentDesignSystem().register(
  fluentButton(),
  fluentCard(),
  fluentTextField(),
  fluentDivider(),
  fluentSwitch()
);
baseLayerLuminance.setValueFor(document.body, StandardLuminance.DarkMode);

const ringRam = document.getElementById("ring-ram");
const ringCpu = document.getElementById("ring-cpu");
const ringGpu = document.getElementById("ring-gpu");
const chart = document.getElementById("chart");
const processList = document.getElementById("process-list");
const toast = document.getElementById("toast");
const settingsPanel = document.getElementById("settings-panel");
const settingsToggle = document.getElementById("settings-toggle");
const settingsSave = document.getElementById("settings-save");
const liveIndicator = document.getElementById("live-indicator");
const liveLabel = liveIndicator.querySelector(".label");
const reconnectBtn = document.getElementById("reconnect-btn");
const combinedToggle = document.getElementById("combined-toggle");
const miniModeToggle = document.getElementById("mini-mode-toggle");
const miniRestore = document.getElementById("mini-restore");
const liveViewToggle = document.getElementById("live-view-toggle");
const processPanelTitle = document.getElementById("process-panel-title");
const diskReadEl = document.getElementById("disk-read");
const diskWriteEl = document.getElementById("disk-write");
const netRecvEl = document.getElementById("net-recv");
const netSentEl = document.getElementById("net-sent");
const gpuTempEl = document.getElementById("gpu-temp");
const gpuPowerEl = document.getElementById("gpu-power");
const gpuThrottleEl = document.getElementById("gpu-throttle");
const historyToggle = document.getElementById("history-toggle");
const historyPanel = document.getElementById("history-panel");
const historyChart = document.getElementById("history-chart");
const historyRangeButtons = document.getElementById("history-range-buttons");
const historySpikesTbody = document.querySelector("#history-spikes-table tbody");
const historySpikesEmpty = document.getElementById("history-spikes-empty");
const helpToggle = document.getElementById("help-toggle");
const helpPanel = document.getElementById("help-panel");
const drawerBackdrop = document.getElementById("drawer-backdrop");
const triggersList = document.getElementById("triggers-list");
const triggerAddBtn = document.getElementById("trigger-add");
const debugToggle = document.getElementById("debug-toggle");
const debugPanel = document.getElementById("debug-panel");
const debugLogRam = document.getElementById("debug-log-ram");
const debugLogCpu = document.getElementById("debug-log-cpu");
const debugLogGpu = document.getElementById("debug-log-gpu");
const debugVersionEl = document.getElementById("debug-version");
const debugLoopIterationsEl = document.getElementById("debug-loop-iterations");
const debugLoopAgeEl = document.getElementById("debug-loop-age");
const debugWsConnectionsEl = document.getElementById("debug-ws-connections");
const debugErrorsLogEl = document.getElementById("debug-errors-log");
const debugEventsLogEl = document.getElementById("debug-events-log");
const crashEventsList = document.getElementById("crash-events-list");
const crashEventsUnavailable = document.getElementById("crash-events-unavailable");
const crashEventsRefreshBtn = document.getElementById("crash-events-refresh");

const DRAWERS = [helpPanel, historyPanel, debugPanel];

function openDrawer(panel) {
  for (const d of DRAWERS) d.classList.toggle("open", d === panel);
  drawerBackdrop.classList.add("open");
}
function closeDrawers() {
  for (const d of DRAWERS) d.classList.remove("open");
  drawerBackdrop.classList.remove("open");
}
function toggleDrawer(panel) {
  if (panel.classList.contains("open")) closeDrawers();
  else openDrawer(panel);
}
drawerBackdrop.addEventListener("click", closeDrawers);

// Debug tab: raw per-metric tick log plus backend health, for diagnosing the
// "reconnect does nothing, everything froze" failure mode -- the goal is to
// tell apart "the backend loop itself died" (loop age keeps growing no
// matter what) from "just the WS socket dropped" (loop age stays fresh).
function appendDebugLine(container, text) {
  const line = document.createElement("div");
  line.textContent = text;
  container.appendChild(line);
  while (container.childElementCount > 40) container.removeChild(container.firstChild);
}

function logDebugEvent(text) {
  appendDebugLine(debugEventsLogEl, `${new Date().toLocaleTimeString()}  ${text}`);
}

function logDebugTick(tick) {
  const time = new Date(tick.ts * 1000).toLocaleTimeString();
  appendDebugLine(debugLogRam, `${time}  ${tick.ram_pct.toFixed(1)}%  ${tick.ram_gb.toFixed(2)} GB`);
  appendDebugLine(debugLogCpu, `${time}  ${tickCpuAvg(tick).toFixed(1)}%`);
  if (tick.gpu_pct != null) {
    const temp = tick.gpu_temp_c != null ? `${tick.gpu_temp_c.toFixed(0)}C` : "?C";
    const power = tick.gpu_power_w != null ? `${tick.gpu_power_w.toFixed(0)}W` : "?W";
    const throttle = tick.gpu_throttle?.length ? ` !${tick.gpu_throttle.length}` : "";
    appendDebugLine(
      debugLogGpu,
      `${time}  ${tick.gpu_pct.toFixed(1)}%  ${(tick.vram_gb ?? 0).toFixed(2)} GB  ${temp}  ${power}${throttle}`
    );
  } else {
    appendDebugLine(debugLogGpu, `${time}  n/a`);
  }
}

async function pollDebug() {
  try {
    const res = await fetch("/api/debug");
    const data = await res.json();
    debugVersionEl.textContent = data.version;
    debugLoopIterationsEl.textContent = data.loop_iterations;
    debugLoopAgeEl.textContent =
      data.loop_age_s != null ? `${data.loop_age_s}s ago` : "never (loop hasn't completed an iteration)";
    debugWsConnectionsEl.textContent = data.ws_connections;
    debugErrorsLogEl.replaceChildren();
    for (const entry of data.log) {
      if (entry.level !== "error") continue;
      const line = document.createElement("div");
      line.textContent = `${new Date(entry.ts * 1000).toLocaleTimeString()}  ${entry.message.trim().split("\n").pop()}`;
      debugErrorsLogEl.appendChild(line);
    }
  } catch (err) {
    console.warn("debug fetch failed", err);
  }
}

function formatCrashTickSummary(tick) {
  if (!tick) return "No PulseGuard data from around that time.";
  const parts = [`RAM ${tick.ram_pct.toFixed(0)}%`, `CPU ${tick.cpu_pct_avg.toFixed(0)}%`];
  if (tick.gpu_pct != null) parts.push(`GPU ${tick.gpu_pct.toFixed(0)}%`);
  if (tick.gpu_temp_c != null) parts.push(`${tick.gpu_temp_c.toFixed(0)}C`);
  if (tick.gpu_power_w != null) parts.push(`${tick.gpu_power_w.toFixed(0)}W`);
  if (tick.gpu_throttle?.length) parts.push(`throttle: ${tick.gpu_throttle.join(", ")}`);
  return `Last known reading (${new Date(tick.ts * 1000).toLocaleTimeString()}): ${parts.join(" · ")}`;
}

async function pollCrashEvents() {
  try {
    const res = await fetch("/api/events?days=14");
    const { available, events } = await res.json();
    crashEventsUnavailable.style.display = available ? "none" : "block";
    if (!events.length) {
      crashEventsList.replaceChildren(
        Object.assign(document.createElement("div"), {
          id: "crash-events-empty",
          textContent: available ? "No unexpected shutdowns or hardware errors in the last 14 days." : "",
        })
      );
      return;
    }
    crashEventsList.replaceChildren(
      ...events.map((e) => {
        const row = document.createElement("div");
        row.className = "crash-event-row";
        const time = document.createElement("div");
        time.className = "crash-event-time";
        time.textContent = new Date(e.ts * 1000).toLocaleString([], { dateStyle: "medium", timeStyle: "medium" });
        const summary = document.createElement("div");
        summary.className = "crash-event-summary";
        summary.textContent = `${e.summary} (${e.source}, event ${e.event_id})`;
        const tickLine = document.createElement("div");
        tickLine.className = "crash-event-tick";
        tickLine.textContent = formatCrashTickSummary(e.last_tick);
        row.append(time, summary, tickLine);
        return row;
      })
    );
  } catch (err) {
    console.warn("crash events fetch failed", err);
  }
}

debugToggle.addEventListener("click", () => {
  toggleDrawer(debugPanel);
  if (debugPanel.classList.contains("open")) {
    pollDebug();
    pollCrashEvents();
  }
});
crashEventsRefreshBtn.addEventListener("click", () => pollCrashEvents());
setInterval(() => {
  if (debugPanel.classList.contains("open")) pollDebug();
}, 3000);

function formatBps(bytesPerSec) {
  if (bytesPerSec == null) return "-";
  const units = ["B/s", "KB/s", "MB/s", "GB/s"];
  let value = bytesPerSec;
  let i = 0;
  while (value >= 1024 && i < units.length - 1) {
    value /= 1024;
    i++;
  }
  return `${value.toFixed(i > 0 && value < 10 ? 1 : 0)} ${units[i]}`;
}

if (new URLSearchParams(location.search).get("mode") === "mini") {
  document.body.classList.add("mini-mode");
}

miniModeToggle.addEventListener("click", () => {
  if (window.pywebview?.api?.enter_mini_mode) {
    window.pywebview.api.enter_mini_mode();
  } else {
    console.warn("[mini-mode] no pywebview bridge available (dev-mode browser tab)");
  }
});

miniRestore.addEventListener("click", () => {
  if (window.pywebview?.api?.exit_mini_mode) {
    window.pywebview.api.exit_mini_mode();
  } else {
    console.warn("[mini-mode] no pywebview bridge available (dev-mode browser tab)");
  }
});

// Maps a settings key to its field element, one entry per threshold this
// panel edits. poll_interval_s is the one shared (non-per-resource) field.
const FIELDS = {
  ram_pct_ceiling: document.getElementById("field-ram-ceiling"),
  ram_delta_gb: document.getElementById("field-ram-delta"),
  cpu_pct_ceiling: document.getElementById("field-cpu-ceiling"),
  cpu_delta_pct: document.getElementById("field-cpu-delta"),
  gpu_pct_ceiling: document.getElementById("field-gpu-ceiling"),
  gpu_delta_pct: document.getElementById("field-gpu-delta"),
  poll_interval_s: document.getElementById("field-poll"),
  chart_retention_minutes: document.getElementById("field-chart-retention"),
  color_danger_margin_pct: document.getElementById("field-color-danger"),
};

// Boolean settings, bound via fluent-switch's .checked rather than .value.
const SWITCH_FIELDS = {
  notifications_enabled: document.getElementById("field-notifications"),
  autostart: document.getElementById("field-autostart"),
};

// color_warning_ratio is stored as a fraction (0.5) but shown as a percent
// (50) -- the one field that needs unit conversion, so it's kept out of the
// generic FIELDS map rather than special-casing that map's loop.
const colorWarningField = document.getElementById("field-color-warning");

let settingsCache = {
  ram_pct_ceiling: 90,
  ram_delta_gb: 2,
  cpu_pct_ceiling: 90,
  cpu_delta_pct: 40,
  gpu_pct_ceiling: 90,
  gpu_delta_pct: 40,
  window_s: 20,
  poll_interval_s: 2,
  notifications_enabled: true,
  autostart: false,
  chart_retention_minutes: 60,
  color_warning_ratio: 0.5,
  color_danger_margin_pct: 12,
  triggers: [],
};
const spikeActiveUntilMs = { ram: 0, cpu: 0, gpu: 0 };

const TRIGGER_METRIC_UNIT = { ram: "GB", cpu: "%", gpu: "%" };

function createTriggerRow(trigger) {
  const row = document.createElement("div");
  row.className = "trigger-row";
  row.dataset.id = trigger.id || crypto.randomUUID();

  const top = document.createElement("div");
  top.className = "trigger-row-top";

  const metricSelect = document.createElement("select");
  metricSelect.className = "trigger-metric";
  for (const [value, label] of Object.entries({ ram: "RAM (GB)", cpu: "CPU (%)", gpu: "GPU (%)" })) {
    const opt = document.createElement("option");
    opt.value = value;
    opt.textContent = label;
    metricSelect.appendChild(opt);
  }
  metricSelect.value = trigger.metric || "ram";

  const enabledSwitch = document.createElement("fluent-switch");
  enabledSwitch.className = "trigger-enabled";
  enabledSwitch.checked = trigger.enabled !== false;

  const removeBtn = document.createElement("button");
  removeBtn.type = "button";
  removeBtn.className = "trigger-remove";
  removeBtn.title = "Remove trigger";
  removeBtn.textContent = "×";
  removeBtn.addEventListener("click", () => row.remove());

  top.append(metricSelect, enabledSwitch, removeBtn);

  const thresholdLabel = document.createElement("label");
  const thresholdUnit = document.createElement("span");
  thresholdUnit.className = "trigger-threshold-unit";
  const setThresholdLabel = () => {
    thresholdLabel.firstChild.textContent = `Alert at (${TRIGGER_METRIC_UNIT[metricSelect.value]})`;
  };
  thresholdLabel.append(document.createTextNode(""), (() => {
    const field = document.createElement("fluent-text-field");
    field.className = "trigger-threshold";
    field.type = "number";
    field.value = trigger.threshold_value ?? 0;
    return field;
  })());
  setThresholdLabel();
  metricSelect.addEventListener("change", setThresholdLabel);

  const intervalLabel = document.createElement("label");
  intervalLabel.append(document.createTextNode("Remind every (min)"), (() => {
    const field = document.createElement("fluent-text-field");
    field.className = "trigger-interval";
    field.type = "number";
    field.value = Math.round((trigger.remind_interval_s ?? 300) / 60) || 1;
    return field;
  })());

  const topConsumersBtn = document.createElement("button");
  topConsumersBtn.type = "button";
  topConsumersBtn.className = "trigger-top-consumers";
  topConsumersBtn.textContent = "View top consumers";
  topConsumersBtn.addEventListener("click", () => viewTopConsumers(metricSelect.value));

  row.append(top, thresholdLabel, intervalLabel, topConsumersBtn);
  return row;
}

function renderTriggers(triggers) {
  triggersList.replaceChildren(...(triggers || []).map(createTriggerRow));
}

function collectTriggers() {
  return [...triggersList.querySelectorAll(".trigger-row")].map((row) => ({
    id: row.dataset.id,
    metric: row.querySelector(".trigger-metric").value,
    threshold_value: Number(row.querySelector(".trigger-threshold").value),
    remind_interval_s: Math.max(Number(row.querySelector(".trigger-interval").value) * 60, 60),
    enabled: row.querySelector(".trigger-enabled").checked,
  }));
}

triggerAddBtn.addEventListener("click", () => {
  triggersList.appendChild(
    createTriggerRow({ id: crypto.randomUUID(), metric: "ram", threshold_value: 0, remind_interval_s: 300, enabled: true })
  );
});

function viewTopConsumers(metric) {
  settingsPanel.setAttribute("hidden", "");
  selectMetric(metric);
  if (!liveViewToggle.checked) {
    liveViewToggle.checked = true;
    liveViewToggle.dispatchEvent(new Event("change"));
  }
  processList.scrollIntoView({ behavior: "smooth", block: "center" });
}

async function loadSettings() {
  try {
    const res = await fetch("/api/settings");
    settingsCache = await res.json();
    for (const [key, field] of Object.entries(FIELDS)) {
      field.value = settingsCache[key];
    }
    for (const [key, field] of Object.entries(SWITCH_FIELDS)) {
      field.checked = settingsCache[key];
    }
    colorWarningField.value = Math.round(settingsCache.color_warning_ratio * 100);
    renderTriggers(settingsCache.triggers);
    chart.setRetention(settingsCache.chart_retention_minutes, settingsCache.poll_interval_s);
    liveIndicator.title = `Refreshing every ${settingsCache.poll_interval_s}s`;
  } catch (err) {
    console.warn("settings fetch failed", err);
  }
}

async function saveSettings() {
  const body = {};
  for (const key of Object.keys(FIELDS)) {
    body[key] = Number(FIELDS[key].value);
  }
  for (const key of Object.keys(SWITCH_FIELDS)) {
    body[key] = SWITCH_FIELDS[key].checked;
  }
  body.color_warning_ratio = Number(colorWarningField.value) / 100;
  body.triggers = collectTriggers();
  const res = await fetch("/api/settings", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  settingsCache = await res.json();
  chart.setRetention(settingsCache.chart_retention_minutes, settingsCache.poll_interval_s);
  liveIndicator.title = `Refreshing every ${settingsCache.poll_interval_s}s`;
  backfill();
}

// /api/history ticks store an already-averaged cpu_pct_avg; live WS ticks
// carry a per-core cpu_pct array. Both shapes need to feed the same ring.
function tickCpuAvg(tick) {
  if (typeof tick.cpu_pct_avg === "number") return tick.cpu_pct_avg;
  if (Array.isArray(tick.cpu_pct) && tick.cpu_pct.length) {
    return tick.cpu_pct.reduce((a, b) => a + b, 0) / tick.cpu_pct.length;
  }
  return 0;
}

let lastTickTs = 0;

function applyTick(tick) {
  const nowMs = tick.ts * 1000;
  lastTickTs = tick.ts;

  ringRam.update({
    pct: tick.ram_pct,
    display: `${tick.ram_pct.toFixed(0)}%`,
    secondary: `${tick.ram_gb.toFixed(1)} GB`,
    state: metricState("ram", tick.ram_pct, settingsCache.ram_pct_ceiling, nowMs),
  });

  const cpuAvg = tickCpuAvg(tick);
  ringCpu.update({
    pct: cpuAvg,
    display: `${cpuAvg.toFixed(0)}%`,
    state: metricState("cpu", cpuAvg, settingsCache.cpu_pct_ceiling, nowMs),
  });

  if (tick.gpu_pct != null) {
    ringGpu.update({
      pct: tick.gpu_pct,
      display: `${tick.gpu_pct.toFixed(0)}%`,
      secondary: tick.vram_gb != null ? `${tick.vram_gb.toFixed(1)} GB` : "",
      state: metricState("gpu", tick.gpu_pct, settingsCache.gpu_pct_ceiling, nowMs),
    });
  } else {
    ringGpu.update({ pct: 0, display: "n/a" });
  }

  diskReadEl.textContent = formatBps(tick.disk_read_bps);
  diskWriteEl.textContent = formatBps(tick.disk_write_bps);
  netRecvEl.textContent = formatBps(tick.net_recv_bps);
  netSentEl.textContent = formatBps(tick.net_sent_bps);

  gpuTempEl.textContent = tick.gpu_temp_c != null ? `${tick.gpu_temp_c.toFixed(0)} C` : "-";
  gpuPowerEl.textContent = tick.gpu_power_w != null ? `${tick.gpu_power_w.toFixed(0)} W` : "-";
  const throttle = tick.gpu_throttle || [];
  gpuThrottleEl.textContent = throttle.length ? throttle.join(", ") : "None";
  gpuThrottleEl.toggleAttribute("data-active", throttle.length > 0);
}

// Also used as the WebView-throttling "catch-up": when the window was
// minimized or unfocused long enough for WebView2 to throttle/freeze
// rendering, the chart and gauges can go stale relative to real usage.
// Re-running this on visibilitychange/focus re-hydrates from the server's
// (unaffected -- it's a separate Python asyncio loop) ground truth instead
// of waiting for the next live tick to arrive.
async function backfill() {
  try {
    const res = await fetch(`/api/history?range=${settingsCache.chart_retention_minutes}m`);
    const { ticks, spikes } = await res.json();
    chart.backfill(ticks, spikes);
    if (spikes.length) processList.showSpike(spikes[spikes.length - 1]);
    if (ticks.length) applyTick(ticks[ticks.length - 1]);
  } catch (err) {
    console.warn("history backfill failed", err);
  }
}

let lastCatchUpAt = 0;
// force=true bypasses both the visibility check and the debounce -- used by
// the manual Reconnect button, since document.visibilityState can read
// "hidden" in pywebview's WebView2 in cases that don't match the user's own
// sense of whether the window is visible (an explicit click means they want
// it to try regardless of what that check says).
function catchUp(force = false) {
  if (!force && document.visibilityState !== "visible") return;
  const now = Date.now();
  if (!force && now - lastCatchUpAt < 2000) return; // debounce rapid focus/visibility events
  lastCatchUpAt = now;
  backfill();
}

// Proactive traffic-light coloring based on proximity to the configured
// ceiling -- not just whether an actual spike is currently firing. An actual
// detected spike still forces red for its full window regardless of these
// thresholds (metricState is called every tick, so it'd naturally read as
// red anyway near-ceiling, but this guarantees it during the spike's cooldown
// even if the value has since dipped back down).
function metricState(metric, value, ceiling, nowMs) {
  if (nowMs < spikeActiveUntilMs[metric]) return "spike";
  if (ceiling == null) return "normal";
  if (value >= ceiling - settingsCache.color_danger_margin_pct) return "spike";
  if (value >= ceiling * settingsCache.color_warning_ratio) return "warning";
  return "normal";
}

function pulseAll() {
  ringRam.pulse();
  ringCpu.pulse();
  ringGpu.pulse();
}

const RINGS = { ram: ringRam, cpu: ringCpu, gpu: ringGpu };
let selectedMetric = "ram";

function selectMetric(metric) {
  selectedMetric = metric;
  for (const [key, ring] of Object.entries(RINGS)) {
    const isSelected = key === metric;
    ring.toggleAttribute("selected", isSelected);
    ring.setAttribute("aria-pressed", String(isSelected));
  }
  // Picking a specific resource implies "focus on this one", including its
  // accurate per-metric spike markers -- exit the combined %-based overview.
  combinedToggle.checked = false;
  chart.setCombined(false);
  chart.setMetric(metric);
  updateProcessPanelTitle();
  if (liveViewToggle.checked) fetchLiveProcesses();
}

for (const [metric, ring] of Object.entries(RINGS)) {
  ring.addEventListener("click", () => selectMetric(metric));
}
selectMetric("ram");

combinedToggle.addEventListener("change", () => {
  chart.setCombined(combinedToggle.checked);
});

const METRIC_LABELS = { ram: "RAM", cpu: "CPU", gpu: "GPU" };

function updateProcessPanelTitle() {
  processPanelTitle.textContent = liveViewToggle.checked
    ? `Live processes (${METRIC_LABELS[selectedMetric]})`
    : "Top processes at last spike";
}

let liveViewTimer = null;

async function fetchLiveProcesses() {
  try {
    const res = await fetch(`/api/processes/top?metric=${selectedMetric}`);
    const { metric, top } = await res.json();
    processList.showLive(metric, top);
  } catch (err) {
    console.warn("live process fetch failed", err);
  }
}

liveViewToggle.addEventListener("change", () => {
  updateProcessPanelTitle();
  clearInterval(liveViewTimer);
  if (liveViewToggle.checked) {
    fetchLiveProcesses();
    liveViewTimer = setInterval(fetchLiveProcesses, 2000);
  }
});

function flashHeartbeat() {
  liveIndicator.removeAttribute("data-flash");
  void liveIndicator.offsetWidth; // restart the CSS animation even if already running
  liveIndicator.setAttribute("data-flash", "");
}

let wsConnected = false;

function updateLiveIndicator() {
  if (!wsConnected) {
    liveIndicator.dataset.state = "disconnected";
    liveLabel.textContent = "Disconnected";
    return;
  }
  const ageS = lastTickTs ? Date.now() / 1000 - lastTickTs : Infinity;
  const staleAfterS = Math.max(settingsCache.poll_interval_s * 3, 6);
  if (ageS > staleAfterS) {
    liveIndicator.dataset.state = "stale";
    liveLabel.textContent = `Stale (${Math.round(ageS)}s)`;
  } else {
    liveIndicator.dataset.state = "live";
    liveLabel.textContent = "Live";
  }
}
setInterval(updateLiveIndicator, 1000);

const ws = new WsClient("/ws");

reconnectBtn.addEventListener("click", () => {
  reconnectBtn.disabled = true;
  liveLabel.textContent = "Reconnecting...";
  logDebugEvent("manual Reconnect clicked");
  ws.reconnectNow();
  catchUp(true); // don't wait on the WS "open" handler to chain into this -- fetch fresh data right away too
  setTimeout(() => {
    reconnectBtn.disabled = false;
  }, 1500);
});

// Self-healing watchdog: reconnecting/catching-up only on visibilitychange
// or focus events assumes those fire reliably for a minimized-then-restored
// native window, which isn't guaranteed across every pywebview/WebView2
// version. This periodic check is a safety net that doesn't depend on any
// single transition event -- if the window is visible but data has gone
// meaningfully stale, force a reconnect regardless of how it got that way.
setInterval(() => {
  if (document.visibilityState !== "visible") return;
  const ageS = lastTickTs ? Date.now() / 1000 - lastTickTs : Infinity;
  const staleAfterS = Math.max(settingsCache.poll_interval_s * 3, 6);
  if (ageS > staleAfterS * 2) {
    logDebugEvent(`watchdog forced reconnect (data was ${Math.round(ageS)}s stale)`);
    ws.reconnectNow();
    catchUp(true);
  }
}, 5000);

ws.addEventListener("open", () => {
  wsConnected = true;
  updateLiveIndicator();
  logDebugEvent("WS open");
  catchUp(); // reconnecting after a drop is exactly the same staleness risk as a throttled resume
});
ws.addEventListener("close", () => {
  wsConnected = false;
  updateLiveIndicator();
  logDebugEvent("WS closed");
});

ws.addEventListener("tick", (event) => {
  applyTick(event.detail);
  chart.pushTick(event.detail);
  logDebugTick(event.detail);
  flashHeartbeat();
});

ws.addEventListener("spike", (event) => {
  const spike = event.detail;
  spikeActiveUntilMs[spike.metric] = (spike.ts + spike.window_s) * 1000;
  pulseAll();
  chart.pushSpike(spike);
  if (!liveViewToggle.checked) processList.showSpike(spike);
  toast.show(spike);
});

ws.addEventListener("trigger_alert", (event) => {
  const alert = event.detail;
  const unit = METRIC_UNIT[alert.metric] || "";
  RINGS[alert.metric]?.pulse();
  toast.showCustom(
    `${METRIC_LABELS[alert.metric] || alert.metric} trigger`,
    `Now at ${alert.value.toFixed(1)}${unit} (threshold ${alert.threshold_value.toFixed(1)}${unit})`
  );
});

const METRIC_UNIT = { cpu: "%", gpu: "%", ram: " GB" };

function formatSpikeAttribution(spike) {
  const top = spike.top?.[0];
  if (!top) return "-";
  if (spike.metric === "cpu") return `${top.name} (${top.cpu_pct.toFixed(1)}%)`;
  if (spike.metric === "gpu") return `${top.name} (${top.vram_gb.toFixed(2)} GB VRAM)`;
  return `${top.name} (+${top.delta_gb.toFixed(2)} GB)`;
}

function renderHistorySpikes(spikes) {
  const table = historySpikesTbody.closest("table");
  historySpikesTbody.replaceChildren(
    ...spikes
      .slice()
      .reverse()
      .map((s) => {
        const tr = document.createElement("tr");
        const unit = METRIC_UNIT[s.metric] || "";
        const cells = [
          new Date(s.ts * 1000).toLocaleString([], { dateStyle: "short", timeStyle: "short" }),
          METRIC_LABELS[s.metric] || s.metric,
          `${s.from_value.toFixed(1)}${unit} -> ${s.to_value.toFixed(1)}${unit}`,
          formatSpikeAttribution(s),
        ];
        tr.append(
          ...cells.map((text) => {
            const td = document.createElement("td");
            td.textContent = text;
            return td;
          })
        );
        return tr;
      })
  );
  historySpikesEmpty.style.display = spikes.length ? "none" : "block";
  table.style.display = spikes.length ? "table" : "none";
}

let historyChartInitialized = false;
async function loadHistoryRange(range) {
  try {
    const res = await fetch(`/api/history?range=${range}`);
    const { ticks, spikes } = await res.json();
    if (!historyChartInitialized) {
      historyChart.setCombined(true);
      historyChartInitialized = true;
    }
    historyChart.backfill(ticks, spikes);
    renderHistorySpikes(spikes);
  } catch (err) {
    console.warn("history range fetch failed", err);
  }
}

historyRangeButtons.addEventListener("click", (event) => {
  const btn = event.target.closest("fluent-button[data-range]");
  if (!btn) return;
  for (const b of historyRangeButtons.querySelectorAll("fluent-button")) {
    b.toggleAttribute("data-active", b === btn);
  }
  loadHistoryRange(btn.dataset.range);
});

let historyLoadedOnce = false;
historyToggle.addEventListener("click", () => {
  toggleDrawer(historyPanel);
  if (historyPanel.classList.contains("open") && !historyLoadedOnce) {
    historyLoadedOnce = true;
    historyRangeButtons.querySelector('fluent-button[data-range="24h"]')?.toggleAttribute("data-active", true);
    loadHistoryRange("24h");
  }
});

helpToggle.addEventListener("click", () => {
  toggleDrawer(helpPanel);
});

settingsToggle.addEventListener("click", () => {
  settingsPanel.toggleAttribute("hidden");
});
settingsSave.addEventListener("click", () => {
  saveSettings().catch((err) => console.warn("settings save failed", err));
});

document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible") catchUp();
});
// Not `window.addEventListener("focus", catchUp)` directly -- that would pass
// the FocusEvent through as catchUp's `force` parameter, and since an Event
// object is truthy, it would silently bypass the visibility/debounce guards
// on every focus event.
window.addEventListener("focus", () => catchUp());

fetch("/api/version")
  .then((res) => res.json())
  .then(({ version }) => {
    document.getElementById("app-version").textContent = `v${version}`;
  })
  .catch((err) => console.warn("version fetch failed", err));

loadSettings().then(backfill);
