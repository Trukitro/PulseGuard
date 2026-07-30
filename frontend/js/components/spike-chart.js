/** Live RAM timeline. Relies on the global `Chart` from vendor/chart.umd.min.js,
 * loaded as a classic <script> before this module. */
const MAX_POINTS = 400;

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
    const root = this.attachShadow({ mode: "open" });
    root.innerHTML = TEMPLATE;
    const canvas = root.querySelector("canvas");

    this._chart = new Chart(canvas, {
      type: "line",
      data: {
        datasets: [
          {
            label: "RAM (GB)",
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

  backfill(ticks, spikes) {
    const ramData = ticks.map((t) => ({ x: t.ts * 1000, y: t.ram_gb }));
    const spikeData = spikes.map((s) => ({ x: s.ts * 1000, y: s.to_gb }));
    this._chart.data.datasets[0].data = ramData.slice(-MAX_POINTS);
    this._chart.data.datasets[1].data = spikeData;
    this._chart.update();
  }

  pushTick(tick) {
    const data = this._chart.data.datasets[0].data;
    data.push({ x: tick.ts * 1000, y: tick.ram_gb });
    if (data.length > MAX_POINTS) data.shift();
    this._chart.update("none");
  }

  pushSpike(spike) {
    this._chart.data.datasets[1].data.push({ x: spike.ts * 1000, y: spike.to_gb });
    this._chart.update("none");
  }
}

customElements.define("spike-chart", SpikeChart);
