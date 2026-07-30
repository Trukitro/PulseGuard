"""Locates frontend/ and assets/ whether running from source (two levels
above this file, i.e. the repo root) or from a frozen PyInstaller build
(bundled directly under sys._MEIPASS per pulseguard.spec's `datas`)."""

from __future__ import annotations

import sys
from pathlib import Path


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).resolve().parents[2]


FRONTEND_DIR = _base_dir() / "frontend"
ASSETS_DIR = _base_dir() / "assets"
ICON_PATH = ASSETS_DIR / "icon.ico"
