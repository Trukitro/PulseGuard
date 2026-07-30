import {
  provideFluentDesignSystem,
  fluentButton,
  fluentCard,
  fluentTextField,
  baseLayerLuminance,
  StandardLuminance,
} from "../vendor/fluent-web-components.min.js";
import "./nav-guard.js";
import { WsClient } from "./ws-client.js";
import "./components/pulse-ring.js";
import "./components/spike-chart.js";
import "./components/process-list.js";
import "./components/alert-toast.js";

provideFluentDesignSystem().register(fluentButton(), fluentCard(), fluentTextField());
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
const fieldCeiling = document.getElementById("field-ceiling");
const fieldDelta = document.getElementById("field-delta");
const fieldPoll = document.getElementById("field-poll");

let settingsCache = { ram_pct_ceiling: 90, ram_delta_gb: 2, window_s: 20, poll_interval_s: 2 };
let spikeActiveUntilMs = 0;

async function loadSettings() {
  try {
    const res = await fetch("/api/settings");
    settingsCache = await res.json();
    fieldCeiling.value = settingsCache.ram_pct_ceiling;
    fieldDelta.value = settingsCache.ram_delta_gb;
    fieldPoll.value = settingsCache.poll_interval_s;
  } catch (err) {
    console.warn("settings fetch failed", err);
  }
}

async function saveSettings() {
  const body = {
    ram_pct_ceiling: Number(fieldCeiling.value),
    ram_delta_gb: Number(fieldDelta.value),
    poll_interval_s: Number(fieldPoll.value),
  };
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

function ramState(tick, nowMs) {
  if (nowMs < spikeActiveUntilMs) return "spike";
  if (tick.ram_pct >= settingsCache.ram_pct_ceiling * 0.9) return "warning";
  return "normal";
}

function pulseAll() {
  ringRam.pulse();
  ringCpu.pulse();
  ringGpu.pulse();
}

const ws = new WsClient("/ws");

ws.addEventListener("tick", (event) => {
  const tick = event.detail;
  const nowMs = tick.ts * 1000;

  ringRam.update({ pct: tick.ram_pct, display: `${tick.ram_gb.toFixed(1)} GB`, state: ramState(tick, nowMs) });

  const cpuAvg = tick.cpu_pct.length ? tick.cpu_pct.reduce((a, b) => a + b, 0) / tick.cpu_pct.length : 0;
  ringCpu.update({ pct: cpuAvg, display: `${cpuAvg.toFixed(0)}%` });

  if (tick.gpu_pct != null) {
    ringGpu.update({ pct: tick.gpu_pct, display: `${tick.gpu_pct.toFixed(0)}%` });
  } else {
    ringGpu.update({ pct: 0, display: "n/a" });
  }

  chart.pushTick(tick);
});

ws.addEventListener("spike", (event) => {
  const spike = event.detail;
  spikeActiveUntilMs = (spike.ts + spike.window_s) * 1000;
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
