const TEMPLATE = `
<style>
  :host {
    display: block;
  }
  table {
    width: 100%;
    border-collapse: collapse;
    font-size: 13px;
  }
  th, td {
    text-align: left;
    padding: 8px 12px;
  }
  th {
    color: var(--pg-text-dim, #9aa4b8);
    font-weight: 500;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    font-size: 11px;
    border-bottom: 1px solid var(--pg-panel-border, rgba(255,255,255,0.08));
  }
  td {
    border-bottom: 1px solid rgba(255, 255, 255, 0.04);
  }
  td.name {
    font-family: var(--pg-font-mono, monospace);
  }
  td.delta {
    font-family: var(--pg-font-mono, monospace);
    color: var(--pg-danger, #e81123);
    font-variant-numeric: tabular-nums;
  }
  td.total {
    font-family: var(--pg-font-mono, monospace);
    color: var(--pg-text-dim, #9aa4b8);
    font-variant-numeric: tabular-nums;
  }
  .empty {
    padding: 24px 12px;
    color: var(--pg-text-dim, #9aa4b8);
    font-size: 13px;
  }
</style>
<table>
  <thead></thead>
  <tbody></tbody>
</table>
<div class="empty">No spikes detected yet.</div>
`;

// Per spike metric: which columns to render and how to build a row's cells
// from one entry in spike.top. RAM/GPU attribute by memory delta; CPU
// attributes by live usage (there's no baseline to diff against for a rate).
const SPIKE_COLUMNS = {
  cpu: {
    headers: ["Process", "PID", "CPU"],
    cells: (p) => [p.name, String(p.pid), `${p.cpu_pct.toFixed(1)}%`],
  },
  gpu: {
    headers: ["Process", "PID", "VRAM"],
    cells: (p) => [p.name, String(p.pid), `${p.vram_gb.toFixed(2)} GB`],
  },
  default: {
    headers: ["Process", "PID", "Delta", "Total"],
    cells: (p) => [p.name, String(p.pid), `+${p.delta_gb.toFixed(2)} GB`, `${p.total_gb.toFixed(2)} GB`],
  },
};

// The "Live" view has no baseline to diff against -- just the current
// absolute reading -- so it drops the Delta column the spike view has.
const LIVE_COLUMNS = {
  cpu: SPIKE_COLUMNS.cpu,
  gpu: SPIKE_COLUMNS.gpu,
  ram: {
    headers: ["Process", "PID", "Total"],
    cells: (p) => [p.name, String(p.pid), `${p.total_gb.toFixed(2)} GB`],
  },
};

export class ProcessList extends HTMLElement {
  connectedCallback() {
    if (this._built) return;
    this._built = true;
    const root = this.attachShadow({ mode: "open" });
    root.innerHTML = TEMPLATE;
    this._table = root.querySelector("table");
    this._thead = root.querySelector("thead");
    this._tbody = root.querySelector("tbody");
    this._empty = root.querySelector(".empty");
    this._setEmpty(true, "No spikes detected yet.");
  }

  _setEmpty(isEmpty, message) {
    this._table.style.display = isEmpty ? "none" : "table";
    this._empty.style.display = isEmpty ? "block" : "none";
    if (message) this._empty.textContent = message;
  }

  _render(cols, items) {
    const headRow = document.createElement("tr");
    headRow.append(...cols.headers.map((text) => {
      const th = document.createElement("th");
      th.textContent = text;
      return th;
    }));
    this._thead.replaceChildren(headRow);

    this._tbody.replaceChildren(
      ...items.map((p) => {
        const tr = document.createElement("tr");
        const values = cols.cells(p);
        const classNames = ["name", "", "delta", "total"];
        tr.append(
          ...values.map((text, i) => {
            const td = document.createElement("td");
            if (classNames[i]) td.className = classNames[i];
            td.textContent = text;
            return td;
          })
        );
        return tr;
      })
    );
  }

  showSpike(spike) {
    const top = spike.top || [];
    this._render(SPIKE_COLUMNS[spike.metric] || SPIKE_COLUMNS.default, top);
    this._setEmpty(top.length === 0, "No spikes detected yet.");
  }

  /** @param {"ram"|"cpu"|"gpu"} metric @param {Array} top */
  showLive(metric, top) {
    this._render(LIVE_COLUMNS[metric] || LIVE_COLUMNS.ram, top);
    this._setEmpty(top.length === 0, "No process data yet.");
  }
}

customElements.define("process-list", ProcessList);
