/** Reconnecting WebSocket that re-dispatches server messages as typed events
 * (e.g. { type: "tick", data } becomes a "tick" CustomEvent with `detail = data`). */
export class WsClient extends EventTarget {
  constructor(path = "/ws") {
    super();
    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    this._url = `${proto}//${location.host}${path}`;
    this._closedByUser = false;
    this._reconnectDelayMs = 1000;
    this._reconnectTimer = null;
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
      this._reconnectTimer = setTimeout(() => this._connect(), this._reconnectDelayMs);
      this._reconnectDelayMs = Math.min(this._reconnectDelayMs * 2, 15000);
    };

    ws.onerror = () => ws.close();
  }

  /** Forces an immediate reconnect attempt, bypassing whatever's left of the
   * exponential backoff -- for the UI's manual "Reconnect" action, so a user
   * who notices "Stale"/"Disconnected" doesn't have to just wait it out. */
  reconnectNow() {
    if (this._reconnectTimer !== null) {
      clearTimeout(this._reconnectTimer);
      this._reconnectTimer = null;
    }
    this._reconnectDelayMs = 1000;
    if (this._ws) {
      this._ws.onclose = null; // avoid double-scheduling a reconnect from the old socket's close
      try {
        this._ws.close();
      } catch {
        /* already closed */
      }
    }
    this._connect();
  }

  close() {
    this._closedByUser = true;
    if (this._reconnectTimer !== null) clearTimeout(this._reconnectTimer);
    this._ws?.close();
  }
}
