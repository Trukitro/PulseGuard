"""Lets main.py's spike loop reach the tray icon (in shell.py) without the
two modules importing each other -- main.py runs standalone (dev server,
console) just as often as it runs under the tray-equipped desktop shell."""

from __future__ import annotations

from typing import Callable, Optional

from .detector import Spike

_listener: Optional[Callable[[Spike], None]] = None


def set_spike_listener(callback: Optional[Callable[[Spike], None]]) -> None:
    global _listener
    _listener = callback


def notify_spike(spike: Spike) -> None:
    if _listener is not None:
        _listener(spike)
