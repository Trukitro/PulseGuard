/** Live timeline for RAM/CPU/GPU. Relies on the global `Chart` from
 * vendor/chart.umd.min.js, loaded as a classic <script> before this module.
 * Keeps its own history of every tick/spike so switching the displayed
 * metric (via setMetric) doesn't need a re-fetch from the server. */
const MAX_POINTS = 400;

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
  ram: { label: "RAM (GB)", tickValue: (t) => t.ram_gb, suggestedMin: undefined, suggestedMax: undefined },
  cpu: { label: "CPU (%)", tickValue: cpuAvg, suggestedMin: 0, suggestedMax: 100 },
  gpu: { label: "GPU (%)", tickValue: (t) => t.gpu_pct ?? 0, suggestedMin: 0, suggestedMax: 100 },
};

function fmtTime(ms) {
  return new Date(ms).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
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
    this._ticks = [];
    this._spikes = [];

    const root = this.attachShadow({ mode: "open" });
    root.innerHTML = TEMPLATE;
    const canvas = root.querySelector("canvas");

    this._chart = new Chart(canvas, {
      type: "line",
      data: {
        datasets: [
          {
            label: METRICS.ram.label,
            data: [],
            borderColor: "#2899f5",
            backgroundColor: "rgba(40,153,245,0.12)",
            fill: true,
            pointRadius: 0,
            borderWidth: 2,
            tension: 0.25,
          },
          {
            label: "Spikes",
            data: [],
            showLine: false,
            pointBackgroundColor: "#e81123",
            pointBorderColor: "#e81123",
            pointRadius: 6,
            pointHoverRadius: 7,
          },
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

  /** @param {"ram"|"cpu"|"gpu"} metric */
  setMetric(metric) {
    if (!METRICS[metric] || metric === this._metric) return;
    this._metric = metric;
    this._rebuild();
  }

  _rebuild() {
    const cfg = METRICS[this._metric];
    const ramData = this._ticks.slice(-MAX_POINTS).map((t) => ({ x: t.ts * 1000, y: cfg.tickValue(t) }));
    const spikeData = this._spikes
      .filter((s) => s.metric === this._metric)
      .map((s) => ({ x: s.ts * 1000, y: s.to_value }));

    this._chart.data.datasets[0].label = cfg.label;
    this._chart.data.datasets[0].data = ramData;
    this._chart.data.datasets[1].data = spikeData;
    this._chart.options.scales.y.suggestedMin = cfg.suggestedMin;
    this._chart.options.scales.y.suggestedMax = cfg.suggestedMax;
    this._chart.update();
  }

  backfill(ticks, spikes) {
    this._ticks = ticks.slice(-MAX_POINTS);
    this._spikes = spikes.slice();
    this._rebuild();
  }

  pushTick(tick) {
    this._ticks.push(tick);
    if (this._ticks.length > MAX_POINTS) this._ticks.shift();

    const cfg = METRICS[this._metric];
    const data = this._chart.data.datasets[0].data;
    data.push({ x: tick.ts * 1000, y: cfg.tickValue(tick) });
    if (data.length > MAX_POINTS) data.shift();
    this._chart.update("none");
  }

  pushSpike(spike) {
    this._spikes.push(spike);
    if (spike.metric === this._metric) {
      this._chart.data.datasets[1].data.push({ x: spike.ts * 1000, y: spike.to_value });
      this._chart.update("none");
    }
  }
}

customElements.define("spike-chart", SpikeChart);
