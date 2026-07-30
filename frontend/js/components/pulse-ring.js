const CIRCUMFERENCE = 2 * Math.PI * 52;

const TEMPLATE = `
<style>
  :host {
    display: inline-flex;
    flex-direction: column;
    align-items: center;
    gap: 8px;
    cursor: pointer;
    border-radius: 16px;
    padding: 8px;
    transition: background 0.2s ease;
    --ring-color: var(--pg-accent, #2899f5);
    --ring-glow: var(--pg-accent-glow, rgba(40,153,245,0.55));
  }
  :host(:hover) {
    background: rgba(255, 255, 255, 0.04);
  }
  :host([selected]) {
    background: rgba(255, 255, 255, 0.07);
  }
  :host([selected]) .label {
    color: var(--pg-text, #eef1f7);
  }
  :host([state="warning"]) {
    --ring-color: var(--pg-warn, #ffb900);
    --ring-glow: var(--pg-warn-glow, rgba(255,185,0,0.55));
  }
  :host([state="spike"]) {
    --ring-color: var(--pg-danger, #e81123);
    --ring-glow: var(--pg-danger-glow, rgba(232,17,35,0.6));
  }
  svg {
    width: 128px;
    height: 128px;
    overflow: visible;
  }
  .track {
    fill: none;
    stroke: rgba(255, 255, 255, 0.08);
    stroke-width: 10;
  }
  .progress {
    fill: none;
    stroke: var(--ring-color);
    stroke-width: 10;
    stroke-linecap: round;
    transform: rotate(-90deg);
    transform-origin: 60px 60px;
    stroke-dasharray: ${CIRCUMFERENCE};
    transition: stroke-dashoffset 0.4s ease, stroke 0.3s ease;
    filter: drop-shadow(0 0 6px var(--ring-glow));
  }
  :host([spiking]) .progress {
    animation: pg-ring-pulse 1.1s ease-in-out 2;
  }
  @keyframes pg-ring-pulse {
    0%, 100% { filter: drop-shadow(0 0 6px var(--ring-glow)); }
    50% { filter: drop-shadow(0 0 18px var(--ring-glow)) drop-shadow(0 0 6px var(--ring-glow)); }
  }
  .center {
    position: absolute;
    inset: 0;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    pointer-events: none;
  }
  .wrap {
    position: relative;
    width: 128px;
    height: 128px;
  }
  .value {
    font-family: var(--pg-font-mono, monospace);
    font-variant-numeric: tabular-nums;
    font-size: 18px;
    color: var(--pg-text, #eef1f7);
  }
  .label {
    font-size: 11px;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--pg-text-dim, #9aa4b8);
    margin-top: 12px;
  }
</style>
<div class="wrap">
  <svg viewBox="0 0 120 120">
    <circle class="track" cx="60" cy="60" r="52"></circle>
    <circle class="progress" cx="60" cy="60" r="52" stroke-dashoffset="${CIRCUMFERENCE}"></circle>
  </svg>
  <div class="center">
    <span class="value">--</span>
  </div>
</div>
<span class="label"></span>
`;

export class PulseRing extends HTMLElement {
  static get observedAttributes() {
    return ["label"];
  }

  connectedCallback() {
    if (this._built) return;
    this._built = true;
    const root = this.attachShadow({ mode: "open" });
    root.innerHTML = TEMPLATE;
    this._progress = root.querySelector(".progress");
    this._value = root.querySelector(".value");
    this._labelEl = root.querySelector(".label");
    this._labelEl.textContent = this.getAttribute("label") || "";

    this.tabIndex = 0;
    this.setAttribute("role", "button");
    this.setAttribute("aria-pressed", "false");
    this.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        this.click();
      }
    });
  }

  attributeChangedCallback(name, _old, value) {
    if (name === "label" && this._labelEl) {
      this._labelEl.textContent = value || "";
    }
  }

  /** @param {{ pct: number, display: string, state?: "normal"|"warning"|"spike" }} data */
  update({ pct, display, state = "normal" }) {
    const clamped = Math.max(0, Math.min(100, pct));
    if (this._progress) {
      this._progress.setAttribute("stroke-dashoffset", String(CIRCUMFERENCE * (1 - clamped / 100)));
    }
    if (this._value) this._value.textContent = display;
    this.setAttribute("state", state);
  }

  /** Briefly intensifies the glow animation -- called when a real spike fires. */
  pulse() {
    this.removeAttribute("spiking");
    void this.offsetWidth; // restart the CSS animation even if already running
    this.setAttribute("spiking", "");
  }
}

customElements.define("pulse-ring", PulseRing);
