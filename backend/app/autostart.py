"""Reads/writes the HKCU Run registry entry so autostart can be toggled at
runtime from the in-app setting, not just at install time via the Inno Setup
checkbox. The registry is treated as ground truth (see is_enabled()) since
it's also what Windows' own Task Manager > Startup tab reflects/controls."""

from __future__ import annotations

import sys
from pathlib import Path

try:
    import winreg
except ImportError:
    winreg = None  # non-Windows dev environment

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_VALUE_NAME = "PulseGuard"


def _executable_command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    # Dev mode: the Run key has no "working directory" the way a .lnk shortcut
    # does, so `-m app.shell` would only work if launched from backend/. Point
    # at run.py by absolute path instead -- Python adds a script's own
    # directory to sys.path, so `app` resolves regardless of the caller's cwd.
    run_py = Path(__file__).resolve().parent.parent / "run.py"
    return f'"{sys.executable}" "{run_py}"'


def is_enabled() -> bool:
    if winreg is None:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
            winreg.QueryValueEx(key, _VALUE_NAME)
            return True
    except FileNotFoundError:
        return False


def set_enabled(enabled: bool) -> None:
    if winreg is None:
        return
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, _VALUE_NAME, 0, winreg.REG_SZ, _executable_command())
        else:
            try:
                winreg.DeleteValue(key, _VALUE_NAME)
            except FileNotFoundError:
                pass
