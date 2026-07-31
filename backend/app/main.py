"""FastAPI app: one WebSocket endpoint streams live ticks/spikes, REST serves
settings and history backfill. Also serves frontend/ as static files so the
whole app is reachable at http://127.0.0.1:<port>/ during development."""

from __future__ import annotations

import asyncio
import time
import traceback
from collections import deque
from contextlib import asynccontextmanager
from dataclasses import asdict, replace
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import __version__, autostart, tray_state
from .detector import Detector
from .gamemode import is_foreground_fullscreen
from .history import History
from .notifier import Notifier
from .paths import ASSETS_DIR, FRONTEND_DIR
from .sampler import Sampler
from .settings import Settings, load_settings, save_settings
from .snapshot import ProcessTracker
from .triggers import TriggerEngine

_RANGE_UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400}


def _parse_range(range_str: str) -> float:
    range_str = range_str.strip().lower()
    unit = range_str[-1]
    if unit not in _RANGE_UNITS or len(range_str) < 2:
        raise ValueError(f"unsupported range: {range_str!r}, expected e.g. '1h', '30m', '1d'")
    return float(range_str[:-1]) * _RANGE_UNITS[unit]


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._connections.add(ws)

    def disconnect(self, ws: WebSocket) -> None:
        self._connections.discard(ws)

    @property
    def count(self) -> int:
        return len(self._connections)

    async def broadcast(self, message: dict) -> None:
        dead = []
        for ws in self._connections:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


class SettingsUpdate(BaseModel):
    ram_pct_ceiling: Optional[float] = None
    ram_delta_gb: Optional[float] = None
    cpu_pct_ceiling: Optional[float] = None
    cpu_delta_pct: Optional[float] = None
    gpu_pct_ceiling: Optional[float] = None
    gpu_delta_pct: Optional[float] = None
    window_s: Optional[int] = None
    poll_interval_s: Optional[float] = None
    notifications_enabled: Optional[bool] = None
    autostart: Optional[bool] = None
    retention_days: Optional[int] = None
    chart_retention_minutes: Optional[int] = None
    color_warning_ratio: Optional[float] = None
    color_danger_margin_pct: Optional[float] = None
    triggers: Optional[list] = None
    port: Optional[int] = None


class AppState:
    def __init__(self) -> None:
        self.settings: Settings = load_settings()
        # Registry is ground truth: Windows' own Task Manager > Startup tab can
        # toggle this outside the app, so don't trust a possibly-stale setting.
        self.settings.autostart = autostart.is_enabled()
        self.sampler = Sampler()
        self.detector = Detector(self.settings)
        self.trigger_engine = TriggerEngine()
        self.tracker = ProcessTracker()
        self.history = History()
        self.notifier = Notifier()
        self.manager = ConnectionManager()
        self._task: Optional[asyncio.Task] = None
        self._last_prune = 0.0
        # Diagnostics for the frontend's Debug tab -- separate from the tick/
        # spike data path so it survives and reports on failures *of* that
        # path. loop_iterations/last_loop_ts is a heartbeat: polled over
        # plain REST (independent of the WebSocket), it tells the frontend
        # whether the backend's sampling loop itself is alive, vs. only the
        # WS connection having dropped -- two different failure modes that
        # look identical from the UI alone ("nothing is updating").
        self.debug_log: deque = deque(maxlen=200)
        self.loop_iterations = 0
        self.last_loop_ts = 0.0

    def log_debug(self, level: str, message: str) -> None:
        self.debug_log.append({"ts": time.time(), "level": level, "message": message})

    async def start(self) -> None:
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
        self.sampler.close()
        self.tracker.close()
        self.history.close()

    def apply_settings(self, settings: Settings) -> None:
        if settings.autostart != self.settings.autostart:
            autostart.set_enabled(settings.autostart)
        self.settings = settings
        self.detector.update_settings(settings)
        save_settings(settings)

    async def _loop(self) -> None:
        while True:
            # The whole iteration body used to run unguarded: any exception
            # here (a transient psutil/sqlite/NVML hiccup, a full disk, ...)
            # would propagate out of this coroutine and silently kill the
            # asyncio.Task forever -- monitoring would stop for good, and no
            # amount of the frontend reconnecting the WebSocket could ever
            # revive it, since reconnecting only reopens the socket, it
            # doesn't restart this loop. Catching here is what makes "always
            # live" actually true regardless of what specific error occurs.
            try:
                tick = await asyncio.to_thread(self.sampler.sample)
                await asyncio.to_thread(self.history.log_tick, tick)
                await asyncio.to_thread(self.tracker.snapshot, tick["ts"])
                await self.manager.broadcast({"type": "tick", "data": tick})

                for spike in self.detector.process(tick):
                    if spike["metric"] == "cpu":
                        spike["top"] = await asyncio.to_thread(self.tracker.top_cpu)
                    elif spike["metric"] == "gpu":
                        spike["top"] = await asyncio.to_thread(self.tracker.top_gpu)
                    else:
                        spike["top"] = await asyncio.to_thread(self.tracker.top_deltas, spike["window_start_ts"])
                    await asyncio.to_thread(self.history.log_spike, spike)
                    # Game mode: a fullscreen foreground app auto-silences the OS
                    # toast regardless of the user's own notifications_enabled
                    # toggle, so a spike doesn't pop over a game or video. The
                    # tray tooltip still updates either way -- it's passive
                    # (hover-only), not an interruption.
                    if self.settings.notifications_enabled and not await asyncio.to_thread(is_foreground_fullscreen):
                        self.notifier.notify(spike)
                    tray_state.notify_spike(spike)
                    await self.manager.broadcast({"type": "spike", "data": spike})

                for alert in self.trigger_engine.check(self.settings.triggers, tick):
                    unit = "%" if alert["metric"] in ("cpu", "gpu") else " GB"
                    title = f"PulseGuard - {alert['metric'].upper()} trigger"
                    message = f"{alert['metric'].upper()} at {alert['value']:.1f}{unit} (threshold {alert['threshold_value']:.1f}{unit})"
                    if self.settings.notifications_enabled and not await asyncio.to_thread(is_foreground_fullscreen):
                        self.notifier.notify_custom(title, message)
                    await self.manager.broadcast({"type": "trigger_alert", "data": alert})

                if tick["ts"] - self._last_prune > 3600:
                    await asyncio.to_thread(self.history.prune, self.settings.retention_days)
                    self._last_prune = tick["ts"]

                self.loop_iterations += 1
                self.last_loop_ts = tick["ts"]
            except Exception:
                self.log_debug("error", traceback.format_exc())

            await asyncio.sleep(self.settings.poll_interval_s)


state = AppState()


def _toggle_notifications() -> None:
    state.apply_settings(replace(state.settings, notifications_enabled=not state.settings.notifications_enabled))


tray_state.set_notifications_control(
    toggle_cb=_toggle_notifications,
    enabled_cb=lambda: state.settings.notifications_enabled,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await state.start()
    yield
    await state.stop()


app = FastAPI(title="PulseGuard", lifespan=lifespan)


@app.middleware("http")
async def _no_cache_static(request, call_next):
    # The packaged app always serves the frontend from the same origin
    # (127.0.0.1:<port>) across every version, and pywebview's WebView2
    # profile persists its HTTP cache between runs -- without this, a user
    # upgrading PulseGuard could keep seeing stale JS/CSS from the previous
    # version until that cache happened to expire on its own. Forcing
    # revalidation (rather than no-store) still lets ETag/304s save bandwidth.
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-cache"
    return response


@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket) -> None:
    await state.manager.connect(websocket)
    state.log_debug("info", f"WS connected (client {websocket.client}), {state.manager.count} total")
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        state.manager.disconnect(websocket)
        state.log_debug("info", f"WS disconnected (client {websocket.client}), {state.manager.count} remaining")


@app.get("/api/history")
async def get_history(range: str = "1h") -> dict:
    since_ts = time.time() - _parse_range(range)
    ticks = await asyncio.to_thread(state.history.query_ticks, since_ts)
    spikes = await asyncio.to_thread(state.history.query_spikes, since_ts)
    return {"ticks": ticks, "spikes": spikes}


@app.get("/api/processes/top")
async def get_top_processes(metric: str = "ram", limit: int = 5) -> dict:
    """Live top-N processes right now, independent of any spike -- backs the
    process panel's "Live" view (polled by the frontend only while that mode
    is active, rather than pushed over /ws on every tick)."""
    if metric == "cpu":
        top = await asyncio.to_thread(state.tracker.top_cpu, limit)
    elif metric == "gpu":
        top = await asyncio.to_thread(state.tracker.top_gpu, limit)
    else:
        top = await asyncio.to_thread(state.tracker.top_ram, limit)
    return {"metric": metric, "top": top}


@app.get("/api/version")
async def get_version() -> dict:
    return {"version": __version__}


@app.get("/api/debug")
async def get_debug() -> dict:
    """Backend health, polled over plain REST rather than the WebSocket so it
    still answers even if the WS connection itself is the thing that's
    broken -- lets the frontend's Debug tab tell "backend loop died" (loop_age_s
    keeps growing no matter what) apart from "just the socket dropped"
    (loop_age_s stays fresh, only the WS reconnect churns)."""
    now = time.time()
    return {
        "version": __version__,
        "loop_iterations": state.loop_iterations,
        "last_loop_ts": state.last_loop_ts,
        "loop_age_s": round(now - state.last_loop_ts, 1) if state.last_loop_ts else None,
        "ws_connections": state.manager.count,
        "log": list(state.debug_log),
    }


@app.get("/api/settings")
async def get_settings() -> dict:
    return asdict(state.settings)


@app.post("/api/settings")
async def update_settings(update: SettingsUpdate) -> dict:
    changes = {k: v for k, v in update.model_dump().items() if v is not None}
    state.apply_settings(replace(state.settings, **changes))
    return asdict(state.settings)


if ASSETS_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(ASSETS_DIR)), name="assets")

# Must be mounted last: "/" matches every path as a prefix, so any more specific
# mount (like /assets above) needs to be registered first or it's never reached.
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
