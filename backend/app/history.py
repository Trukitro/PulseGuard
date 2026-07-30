"""SQLite-backed tick/spike log, queryable for chart backfill and prunable by retention."""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Optional

from .detector import Spike
from .sampler import Tick
from .settings import get_config_dir

DB_PATH = get_config_dir() / "history.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS ticks (
    ts REAL PRIMARY KEY,
    ram_gb REAL NOT NULL,
    ram_pct REAL NOT NULL,
    cpu_pct_avg REAL NOT NULL,
    gpu_pct REAL,
    vram_gb REAL
);
CREATE TABLE IF NOT EXISTS spikes (
    ts REAL NOT NULL,
    metric TEXT NOT NULL,
    from_gb REAL NOT NULL,
    to_gb REAL NOT NULL,
    window_s INTEGER NOT NULL,
    top_json TEXT NOT NULL
);
"""


class History:
    def __init__(self, db_path: Path = DB_PATH) -> None:
        # check_same_thread=False: callers dispatch each method via asyncio.to_thread,
        # which can land on a different worker thread per call; access is never concurrent.
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def log_tick(self, tick: Tick) -> None:
        cpu_pct_avg = sum(tick["cpu_pct"]) / len(tick["cpu_pct"]) if tick["cpu_pct"] else 0.0
        self._conn.execute(
            "INSERT OR REPLACE INTO ticks (ts, ram_gb, ram_pct, cpu_pct_avg, gpu_pct, vram_gb) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (tick["ts"], tick["ram_gb"], tick["ram_pct"], cpu_pct_avg, tick["gpu_pct"], tick["vram_gb"]),
        )
        self._conn.commit()

    def log_spike(self, spike: Spike) -> None:
        self._conn.execute(
            "INSERT INTO spikes (ts, metric, from_gb, to_gb, window_s, top_json) VALUES (?, ?, ?, ?, ?, ?)",
            (
                spike["ts"],
                spike["metric"],
                spike["from_gb"],
                spike["to_gb"],
                spike["window_s"],
                json.dumps(spike.get("top", [])),
            ),
        )
        self._conn.commit()

    def query_ticks(self, since_ts: float) -> list[dict]:
        rows = self._conn.execute(
            "SELECT ts, ram_gb, ram_pct, cpu_pct_avg, gpu_pct, vram_gb FROM ticks WHERE ts >= ? ORDER BY ts",
            (since_ts,),
        ).fetchall()
        cols = ["ts", "ram_gb", "ram_pct", "cpu_pct_avg", "gpu_pct", "vram_gb"]
        return [dict(zip(cols, row)) for row in rows]

    def query_spikes(self, since_ts: float) -> list[dict]:
        rows = self._conn.execute(
            "SELECT ts, metric, from_gb, to_gb, window_s, top_json FROM spikes WHERE ts >= ? ORDER BY ts",
            (since_ts,),
        ).fetchall()
        result = []
        for ts, metric, from_gb, to_gb, window_s, top_json in rows:
            result.append(
                {
                    "ts": ts,
                    "metric": metric,
                    "from_gb": from_gb,
                    "to_gb": to_gb,
                    "window_s": window_s,
                    "top": json.loads(top_json),
                }
            )
        return result

    def prune(self, retention_days: int) -> None:
        cutoff = time.time() - retention_days * 86400
        self._conn.execute("DELETE FROM ticks WHERE ts < ?", (cutoff,))
        self._conn.execute("DELETE FROM spikes WHERE ts < ?", (cutoff,))
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()
