"""FastAPI app: one WebSocket endpoint streams live ticks/spikes, REST serves
settings and history backfill. Also serves frontend/ as static files so the
whole app is reachable at http://127.0.0.1:<port>/ during development."""

from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager
from dataclasses import asdict, replace
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .detector import Detector
from .history import History
from .notifier import Notifier
from .sampler import Sampler
from .settings import Settings, load_settings, save_settings
from .snapshot import ProcessTracker

FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"

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
    window_s: Optional[int] = None
    poll_interval_s: Optional[float] = None
    autostart: Optional[bool] = None
    retention_days: Optional[int] = None
    port: Optional[int] = None


class AppState:
    def __init__(self) -> None:
        self.settings: Settings = load_settings()
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
        self.history.close()

    def apply_settings(self, settings: Settings) -> None:
        self.settings = settings
        self.detector.update_settings(settings)
        save_settings(settings)

    async def _loop(self) -> None:
        while True:
            tick = await asyncio.to_thread(self.sampler.sample)
            await asyncio.to_thread(self.history.log_tick, tick)
            await asyncio.to_thread(self.tracker.snapshot, tick["ts"])
            await self.manager.broadcast({"type": "tick", "data": tick})

            spike = self.detector.process(tick)
            if spike is not None:
                spike["top"] = await asyncio.to_thread(self.tracker.top_deltas, spike["window_start_ts"])
                await asyncio.to_thread(self.history.log_spike, spike)
                self.notifier.notify(spike)
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


if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
