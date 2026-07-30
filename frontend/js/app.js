import {
  provideFluentDesignSystem,
  fluentButton,
  fluentCard,
  fluentTextField,
  fluentDivider,
  baseLayerLuminance,
  StandardLuminance,
} from "../vendor/fluent-web-components.min.js";
import "./nav-guard.js";
import { WsClient } from "./ws-client.js";
import "./components/pulse-ring.js";
import "./components/spike-chart.js";
import "./components/process-list.js";
import "./components/alert-toast.js";

provideFluentDesignSystem().register(fluentButton(), fluentCard(), fluentTextField(), fluentDivider());
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
};

let settingsCache = {
  ram_pct_ceiling: 90,
  ram_delta_gb: 2,
  cpu_pct_ceiling: 90,
  cpu_delta_pct: 40,
  gpu_pct_ceiling: 90,
  gpu_delta_pct: 40,
  window_s: 20,
  poll_interval_s: 2,
};
const spikeActiveUntilMs = { ram: 0, cpu: 0, gpu: 0 };

async function loadSettings() {
  try {
    const res = await fetch("/api/settings");
    settingsCache = await res.json();
    for (const [key, field] of Object.entries(FIELDS)) {
      field.value = settingsCache[key];
    }
  } catch (err) {
    console.warn("settings fetch failed", err);
  }
}

async function saveSettings() {
  const body = {};
  for (const key of Object.keys(FIELDS)) {
    body[key] = Number(FIELDS[key].value);
  }
  const res = await fetch("/api/settings", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  settingsCache = await res.json();
}

async function backfill() {
  try {
    const res = await fetch("/api/history?range=1h");
    const { ticks, spikes } = await res.json();
    chart.backfill(ticks, spikes);
    if (spikes.length) processList.showSpike(spikes[spikes.length - 1]);
  } catch (err) {
    console.warn("history backfill failed", err);
  }
}

function metricState(metric, value, ceiling, nowMs) {
  if (nowMs < spikeActiveUntilMs[metric]) return "spike";
  if (ceiling != null && value >= ceiling * 0.9) return "warning";
  return "normal";
}

function pulseAll() {
  ringRam.pulse();
  ringCpu.pulse();
  ringGpu.pulse();
}

const RINGS = { ram: ringRam, cpu: ringCpu, gpu: ringGpu };

function selectMetric(metric) {
  for (const [key, ring] of Object.entries(RINGS)) {
    const isSelected = key === metric;
    ring.toggleAttribute("selected", isSelected);
    ring.setAttribute("aria-pressed", String(isSelected));
  }
  chart.setMetric(metric);
}

for (const [metric, ring] of Object.entries(RINGS)) {
  ring.addEventListener("click", () => selectMetric(metric));
}
selectMetric("ram");

const ws = new WsClient("/ws");

ws.addEventListener("tick", (event) => {
  const tick = event.detail;
  const nowMs = tick.ts * 1000;

  ringRam.update({
    pct: tick.ram_pct,
    display: `${tick.ram_gb.toFixed(1)} GB`,
    state: metricState("ram", tick.ram_pct, settingsCache.ram_pct_ceiling, nowMs),
  });

  const cpuAvg = tick.cpu_pct.length ? tick.cpu_pct.reduce((a, b) => a + b, 0) / tick.cpu_pct.length : 0;
  ringCpu.update({
    pct: cpuAvg,
    display: `${cpuAvg.toFixed(0)}%`,
    state: metricState("cpu", cpuAvg, settingsCache.cpu_pct_ceiling, nowMs),
  });

  if (tick.gpu_pct != null) {
    ringGpu.update({
      pct: tick.gpu_pct,
      display: `${tick.gpu_pct.toFixed(0)}%`,
      state: metricState("gpu", tick.gpu_pct, settingsCache.gpu_pct_ceiling, nowMs),
    });
  } else {
    ringGpu.update({ pct: 0, display: "n/a" });
  }

  chart.pushTick(tick);
});

ws.addEventListener("spike", (event) => {
  const spike = event.detail;
  spikeActiveUntilMs[spike.metric] = (spike.ts + spike.window_s) * 1000;
  pulseAll();
  chart.pushSpike(spike);
  processList.showSpike(spike);
  toast.show(spike);
});

settingsToggle.addEventListener("click", () => {
  settingsPanel.toggleAttribute("hidden");
});
settingsSave.addEventListener("click", () => {
  saveSettings().catch((err) => console.warn("settings save failed", err));
});

loadSettings();
backfill();
