/** Reconnecting WebSocket that re-dispatches server messages as typed events
 * (e.g. { type: "tick", data } becomes a "tick" CustomEvent with `detail = data`). */
export class WsClient extends EventTarget {
  constructor(path = "/ws") {
    super();
    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    this._url = `${proto}//${location.host}${path}`;
    this._closedByUser = false;
    this._reconnectDelayMs = 1000;
    this._ws = null;
    this._connect();
  }

  _connect() {
    const ws = new WebSocket(this._url);
    this._ws = ws;

    ws.onopen = () => {
      this._reconnectDelayMs = 1000;
      this.dispatchEvent(new Event("open"));
    };

    ws.onmessage = (event) => {
      let msg;
      try {
        msg = JSON.parse(event.data);
      } catch {
        return;
      }
      if (msg && typeof msg.type === "string") {
        this.dispatchEvent(new CustomEvent(msg.type, { detail: msg.data }));
      }
    };

    ws.onclose = () => {
      this.dispatchEvent(new Event("close"));
      if (this._closedByUser) return;
      setTimeout(() => this._connect(), this._reconnectDelayMs);
      this._reconnectDelayMs = Math.min(this._reconnectDelayMs * 2, 15000);
    };

    ws.onerror = () => ws.close();
  }

  close() {
    this._closedByUser = true;
    this._ws?.close();
  }
}
