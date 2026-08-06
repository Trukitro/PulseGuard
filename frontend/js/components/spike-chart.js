/** Live timeline for RAM/CPU/GPU. Relies on the global `Chart` from
 * vendor/chart.umd.min.js, loaded as a classic <script> before this module.
 * Keeps its own history of every tick/spike so switching the displayed
 * metric (via setMetric) doesn't need a re-fetch from the server.
 *
 * Two display modes share the same six-dataset chart, toggled via the
 * `hidden` flag rather than swapping dataset arrays:
 *   - single-metric (default): datasets 0/1, driven by setMetric(). RAM
 *     shows its absolute value in GB with spike markers.
 *   - combined (setCombined(true)): datasets 2/3/4, RAM/CPU/GPU all shown as
 *     a 0-100% share of ceiling so they can share one axis. No spike
 *     markers here -- RAM spikes are recorded in GB, not %, so plotting them
 *     against this axis would be misleading; switch to single-metric mode
 *     (click a ring) for accurate per-metric spike markers. */
const DEFAULT_MAX_POINTS = 400;

// Live WS ticks carry cpu_pct as a per-core array; backfilled history ticks
// (from /api/history, which stores an already-averaged cpu_pct_avg) don't.
function cpuAvg(tick) {
  if (typeof tick.cpu_pct_avg === "number") return tick.cpu_pct_avg;
  if (Array.isArray(tick.cpu_pct) && tick.cpu_pct.length) {
    return tick.cpu_pct.reduce((a, b) => a + b, 0) / tick.cpu_pct.length;
  }
  return 0;
}

const METRICS = {
  ram: {
    label: "RAM (GB)",
    tickValue: (t) => t.ram_gb,
    combinedValue: (t) => t.ram_pct,
    suggestedMin: undefined,
    suggestedMax: undefined,
    color: "#2899f5",
  },
  cpu: {
    label: "CPU (%)",
    tickValue: cpuAvg,
    combinedValue: cpuAvg,
    suggestedMin: 0,
    suggestedMax: 100,
    color: "#00b294",
  },
  gpu: {
    label: "GPU (%)",
    tickValue: (t) => t.gpu_pct ?? 0,
    combinedValue: (t) => t.gpu_pct ?? 0,
    suggestedMin: 0,
    suggestedMax: 100,
    color: "#b146c2",
  },
};

function fmtTime(ms) {
  return new Date(ms).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function lineDataset(label, color, extra = {}) {
  return {
    label,
    data: [],
    borderColor: color,
    pointRadius: 0,
    borderWidth: 2,
    tension: 0.25,
    ...extra,
  };
}

const TEMPLATE = `
<style>
  :host {
    display: block;
    position: relative;
    height: 220px;
  }
</style>
<canvas></canvas>
`;

export class SpikeChart extends HTMLElement {
  connectedCallback() {
    if (this._built) return;
    this._built = true;
    this._metric = "ram";
    this._combined = false;
    this._maxPoints = DEFAULT_MAX_POINTS;
    this._ticks = [];
    this._spikes = [];

    const root = this.attachShadow({ mode: "open" });
    root.innerHTML = TEMPLATE;
    const canvas = root.querySelector("canvas");

    this._chart = new Chart(canvas, {
      type: "line",
      data: {
        datasets: [
          lineDataset(METRICS.ram.label, METRICS.ram.color, {
            backgroundColor: "rgba(40,153,245,0.12)",
            fill: true,
          }),
          {
            label: "Spikes",
            data: [],
            showLine: false,
            pointBackgroundColor: "#e81123",
            pointBorderColor: "#e81123",
            pointRadius: 6,
            pointHoverRadius: 7,
          },
          lineDataset("RAM (%)", METRICS.ram.color, { hidden: true }),
          lineDataset(METRICS.cpu.label, METRICS.cpu.color, { hidden: true }),
          lineDataset(METRICS.gpu.label, METRICS.gpu.color, { hidden: true }),
        ],
      },
      options: {
        animation: false,
        responsive: true,
        maintainAspectRatio: false,
        interaction: { intersect: false, mode: "index" },
        scales: {
          x: {
            type: "linear",
            ticks: { color: "#9aa4b8", callback: (v) => fmtTime(v) },
            grid: { color: "rgba(255,255,255,0.06)" },
          },
          y: {
            ticks: { color: "#9aa4b8" },
            grid: { color: "rgba(255,255,255,0.06)" },
          },
        },
        plugins: {
          legend: { labels: { color: "#eef1f7" } },
          tooltip: { callbacks: { title: (items) => fmtTime(items[0].parsed.x) } },
        },
      },
    });
  }

  /** How many ticks to keep in memory, roughly retentionMinutes worth at the
   * given poll interval. Re-derived whenever either setting changes, since
   * a slower poll interval means fewer points cover the same time span. */
  setRetention(retentionMinutes, pollIntervalS) {
    const points = Math.ceil((retentionMinutes * 60) / Math.max(pollIntervalS, 0.1));
    this._maxPoints = Math.max(10, points);
    this._ticks = this._ticks.slice(-this._maxPoints);
    for (const ds of this._chart.data.datasets) {
      if (ds.data.length > this._maxPoints) ds.data = ds.data.slice(-this._maxPoints);
    }
    this._chart.update();
  }

  /** @param {"ram"|"cpu"|"gpu"} metric */
  setMetric(metric) {
    if (!METRICS[metric] || metric === this._metric) return;
    this._metric = metric;
    this._rebuildSingle();
  }

  /** Toggles between the single-metric detail view and the combined %-based
   * overview. The two share one chart instance; only dataset visibility and
   * axis bounds change. */
  setCombined(enabled) {
    if (enabled === this._combined) return;
    this._combined = enabled;
    this._chart.data.datasets[0].hidden = enabled;
    this._chart.data.datasets[1].hidden = enabled;
    this._chart.data.datasets[2].hidden = !enabled;
    this._chart.data.datasets[3].hidden = !enabled;
    this._chart.data.datasets[4].hidden = !enabled;
    if (enabled) {
      this._chart.options.scales.y.suggestedMin = 0;
      this._chart.options.scales.y.suggestedMax = 100;
    } else {
      const cfg = METRICS[this._metric];
      this._chart.options.scales.y.suggestedMin = cfg.suggestedMin;
      this._chart.options.scales.y.suggestedMax = cfg.suggestedMax;
    }
    this._chart.update();
  }

  _rebuildSingle() {
    const cfg = METRICS[this._metric];
    const data = this._ticks.slice(-this._maxPoints).map((t) => ({ x: t.ts * 1000, y: cfg.tickValue(t) }));
    const spikeData = this._spikes
      .filter((s) => s.metric === this._metric)
      .map((s) => ({ x: s.ts * 1000, y: s.to_value }));

    this._chart.data.datasets[0].label = cfg.label;
    this._chart.data.datasets[0].data = data;
    this._chart.data.datasets[1].data = spikeData;
    if (!this._combined) {
      this._chart.options.scales.y.suggestedMin = cfg.suggestedMin;
      this._chart.options.scales.y.suggestedMax = cfg.suggestedMax;
    }
    this._chart.update();
  }

  _rebuildCombined() {
    const points = this._ticks.slice(-this._maxPoints);
    this._chart.data.datasets[2].data = points.map((t) => ({ x: t.ts * 1000, y: METRICS.ram.combinedValue(t) }));
    this._chart.data.datasets[3].data = points.map((t) => ({ x: t.ts * 1000, y: METRICS.cpu.combinedValue(t) }));
    this._chart.data.datasets[4].data = points.map((t) => ({ x: t.ts * 1000, y: METRICS.gpu.combinedValue(t) }));
  }

  backfill(ticks, spikes) {
    this._ticks = ticks.slice(-this._maxPoints);
    this._spikes = spikes.slice();
    this._rebuildSingle();
    this._rebuildCombined();
    this._chart.update();
  }

  pushTick(tick) {
    this._ticks.push(tick);
    if (this._ticks.length > this._maxPoints) this._ticks.shift();

    const cfg = METRICS[this._metric];
    const single = this._chart.data.datasets[0].data;
    single.push({ x: tick.ts * 1000, y: cfg.tickValue(tick) });
    if (single.length > this._maxPoints) single.shift();

    for (const [i, key] of [[2, "ram"], [3, "cpu"], [4, "gpu"]]) {
      const combinedData = this._chart.data.datasets[i].data;
      combinedData.push({ x: tick.ts * 1000, y: METRICS[key].combinedValue(tick) });
      if (combinedData.length > this._maxPoints) combinedData.shift();
    }

    this._chart.update("none");
  }

  pushSpike(spike) {
    this._spikes.push(spike);
    if (spike.metric === this._metric) {
      this._chart.data.datasets[1].data.push({ x: spike.ts * 1000, y: spike.to_value });
      this._chart.update("none");
    }
  }

  /** Opt-in wheel-zoom + drag-pan on the time axis, via chartjs-plugin-zoom
   * (registered globally once its vendor script loads, but inert on any
   * chart that doesn't explicitly configure it here) -- used by the History
   * page's chart only, not the compact dashboard Timeline. */
  enableZoomPan() {
    this._chart.options.plugins.zoom = {
      pan: { enabled: true, mode: "x" },
      zoom: {
        wheel: { enabled: true },
        pinch: { enabled: false },
        mode: "x",
      },
      limits: { x: { minRange: 60_000 } },
    };
    this._chart.update();
  }

  resetZoom() {
    this._chart.resetZoom?.();
  }
}

customElements.define("spike-chart", SpikeChart);
