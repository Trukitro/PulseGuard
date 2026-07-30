"""User-configurable thresholds, persisted to a JSON file in %LOCALAPPDATA%\\PulseGuard."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path


def get_config_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home())
    path = Path(base) / "PulseGuard"
    path.mkdir(parents=True, exist_ok=True)
    return path


SETTINGS_PATH = get_config_dir() / "settings.json"


@dataclass
class Settings:
    ram_pct_ceiling: float = 90.0
    ram_delta_gb: float = 2.0
    cpu_pct_ceiling: float = 90.0
    cpu_delta_pct: float = 40.0
    gpu_pct_ceiling: float = 90.0
    gpu_delta_pct: float = 40.0
    window_s: int = 20
    poll_interval_s: float = 2.0
    autostart: bool = False
    retention_days: int = 30
    port: int = 8731


def load_settings(path: Path = SETTINGS_PATH) -> Settings:
    defaults = Settings()
    if not path.exists():
        return defaults
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return defaults
    merged = {**asdict(defaults), **data}
    return Settings(**{k: merged[k] for k in asdict(defaults)})


def save_settings(settings: Settings, path: Path = SETTINGS_PATH) -> None:
    path.write_text(json.dumps(asdict(settings), indent=2), encoding="utf-8")
