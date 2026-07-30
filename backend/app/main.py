"""FastAPI app: one WebSocket endpoint streams live ticks/spikes, REST serves
settings and history backfill. Also serves frontend/ as static files so the
whole app is reachable at http://127.0.0.1:<port>/ during development."""

from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager
from dataclasses import asdict, replace
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import autostart, tray_state
from .detector import Detector
from .gamemode import is_foreground_fullscreen
from .history import History
from .notifier import Notifier
from .paths import ASSETS_DIR, FRONTEND_DIR
from .sampler import Sampler
from .settings import Settings, load_settings, save_settings
from .snapshot import ProcessTracker

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
    port: Optional[int] = None


class AppState:
    def __init__(self) -> None:
        self.settings: Settings = load_settings()
        # Registry is ground truth: Windows' own Task Manager > Startup tab can
        # toggle this outside the app, so don't trust a possibly-stale setting.
        self.settings.autostart = autostart.is_enabled()
        self.sampler = Sampler()
        self.detector = Detector(self.settings)
        self.tracker = ProcessTracker()
        self.history = History()
        self.notifier = Notifier()
        self.manager = ConnectionManager()
        self._task: Optional[asyncio.Task] = None
        self._last_prune = 0.0

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

            if tick["ts"] - self._last_prune > 3600:
                await asyncio.to_thread(self.history.prune, self.settings.retention_days)
                self._last_prune = tick["ts"]

            await asyncio.sleep(self.settings.poll_interval_s)


state = AppState()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await state.start()
    yield
    await state.stop()


app = FastAPI(title="PulseGuard", lifespan=lifespan)


@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket) -> None:
    await state.manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        state.manager.disconnect(websocket)


@app.get("/api/history")
async def get_history(range: str = "1h") -> dict:
    since_ts = time.time() - _parse_range(range)
    ticks = await asyncio.to_thread(state.history.query_ticks, since_ts)
    spikes = await asyncio.to_thread(state.history.query_spikes, since_ts)
    return {"ticks": ticks, "spikes": spikes}


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
