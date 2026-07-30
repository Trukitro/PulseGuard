const TEMPLATE = `
<style>
  :host {
    position: fixed;
    top: 16px;
    right: 16px;
    z-index: 1000;
    display: block;
    transform: translateY(-16px);
    opacity: 0;
    pointer-events: none;
    transition: transform 0.25s ease, opacity 0.25s ease;
  }
  :host([open]) {
    transform: translateY(0);
    opacity: 1;
    pointer-events: auto;
  }
  .banner {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 12px 16px;
    border-radius: var(--pg-radius, 12px);
    background: rgba(20, 10, 12, 0.85);
    border: 1px solid var(--pg-danger, #e81123);
    box-shadow: 0 0 24px var(--pg-danger-glow, rgba(232, 17, 35, 0.6));
    backdrop-filter: blur(var(--pg-blur, 20px));
    max-width: 360px;
  }
  .dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--pg-danger, #e81123);
    flex: none;
  }
  .title {
    font-weight: 600;
    font-size: 13px;
  }
  .body {
    font-size: 12px;
    color: var(--pg-text-dim, #9aa4b8);
    font-family: var(--pg-font-mono, monospace);
  }
</style>
<div class="banner">
  <span class="dot"></span>
  <div>
    <div class="title"></div>
    <div class="body"></div>
  </div>
</div>
`;

const METRIC_LABELS = { ram: "RAM", cpu: "CPU", gpu: "GPU" };

export class AlertToast extends HTMLElement {
  connectedCallback() {
    if (this._built) return;
    this._built = true;
    const root = this.attachShadow({ mode: "open" });
    root.innerHTML = TEMPLATE;
    this._title = root.querySelector(".title");
    this._body = root.querySelector(".body");
  }

  show(spike, durationMs = 6000) {
    const top = spike.top?.[0];
    const unit = spike.metric === "cpu" ? "%" : " GB";
    const attribution =
      spike.metric === "cpu"
        ? top && `${top.name} (${top.cpu_pct.toFixed(1)}%)`
        : top && `${top.name} +${top.delta_gb.toFixed(2)} GB`;

    this._title.textContent = `${METRIC_LABELS[spike.metric] || spike.metric} spike detected`;
    this._body.textContent =
      `${spike.from_value.toFixed(1)}${unit} -> ${spike.to_value.toFixed(1)}${unit} ` +
      `in ${spike.window_s}s -- ${attribution || "no single process stands out"}`;

    clearTimeout(this._hideTimer);
    this.setAttribute("open", "");
    this._hideTimer = setTimeout(() => this.removeAttribute("open"), durationMs);
  }
}

customElements.define("alert-toast", AlertToast);
