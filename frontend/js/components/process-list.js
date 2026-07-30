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
  <thead>
    <tr><th>Process</th><th>PID</th><th>Delta</th><th>Total</th></tr>
  </thead>
  <tbody></tbody>
</table>
<div class="empty">No spikes detected yet.</div>
`;

export class ProcessList extends HTMLElement {
  connectedCallback() {
    if (this._built) return;
    this._built = true;
    const root = this.attachShadow({ mode: "open" });
    root.innerHTML = TEMPLATE;
    this._table = root.querySelector("table");
    this._tbody = root.querySelector("tbody");
    this._empty = root.querySelector(".empty");
    this._setEmpty(true);
  }

  _setEmpty(isEmpty) {
    this._table.style.display = isEmpty ? "none" : "table";
    this._empty.style.display = isEmpty ? "block" : "none";
  }

  showSpike(spike) {
    const top = spike.top || [];
    this._tbody.replaceChildren(
      ...top.map((p) => {
        const tr = document.createElement("tr");
        const cell = (text, className) => {
          const td = document.createElement("td");
          if (className) td.className = className;
          td.textContent = text;
          return td;
        };
        tr.append(
          cell(p.name, "name"),
          cell(String(p.pid)),
          cell(`+${p.delta_gb.toFixed(2)} GB`, "delta"),
          cell(`${p.total_gb.toFixed(2)} GB`, "total")
        );
        return tr;
      })
    );
    this._setEmpty(top.length === 0);
  }
}

customElements.define("process-list", ProcessList);
