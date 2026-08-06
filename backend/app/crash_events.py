"""Detects likely crash/shutdown signatures from the Windows Event Log --
Kernel-Power 41 (unexpected shutdown), WHEA-Logger hardware errors (CPU/
memory/PCIe), and the classic paired EventLog 6008. PulseGuard's own process
can't observe anything once the machine has actually hung or lost power, so
this is the only source of truth for "what happened right before it died" --
Windows itself writes these records on the *next* boot, after the fact."""

from __future__ import annotations

import re
import time
from datetime import datetime
from typing import Optional, TypedDict

try:
    import win32evtlog

    _AVAILABLE = True
except Exception:
    _AVAILABLE = False


class CrashEvent(TypedDict):
    ts: float
    source: str
    event_id: int
    summary: str


# (provider, event_id or None for "any", human summary). WHEA-Logger has no
# single fixed ID worth hardcoding -- 17 (PCI Express/AER), 18/19, 1, 46/47
# all indicate different hardware error classes, so any event from that
# provider is worth surfacing rather than guessing which IDs matter.
_QUERIES: list[tuple[str, Optional[int], str]] = [
    ("Microsoft-Windows-Kernel-Power", 41, "Unexpected shutdown (system did not shut down cleanly)"),
    ("Microsoft-Windows-WHEA-Logger", None, "Hardware error reported (WHEA -- CPU/memory/PCIe)"),
    ("EventLog", 6008, "Previous system shutdown was unexpected"),
]

_TIME_RE = re.compile(r"<TimeCreated SystemTime='([^']+)'")
_EVENTID_RE = re.compile(r"<EventID>(\d+)</EventID>")


def is_available() -> bool:
    return _AVAILABLE


def _parse_time_created(xml: str) -> Optional[float]:
    m = _TIME_RE.search(xml)
    if not m:
        return None
    raw = m.group(1)
    # SystemTime carries up to 7 fractional digits; fromisoformat wants <= 6.
    raw = re.sub(r"(\.\d{6})\d*Z$", r"\1Z", raw).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(raw).timestamp()
    except ValueError:
        return None


def _query_one(provider: str, event_id: Optional[int], summary: str, limit: int) -> list[CrashEvent]:
    cond = f"Provider[@Name='{provider}']"
    if event_id is not None:
        cond = f"({cond} and (EventID={event_id}))"
    query = f"*[System[{cond}]]"
    out: list[CrashEvent] = []
    try:
        handle = win32evtlog.EvtQuery(
            "System", win32evtlog.EvtQueryChannelPath | win32evtlog.EvtQueryReverseDirection, query
        )
        batch = win32evtlog.EvtNext(handle, limit)
    except Exception:
        return out
    for ev in batch:
        try:
            xml = win32evtlog.EvtRender(ev, win32evtlog.EvtRenderEventXml)
        except Exception:
            continue
        ts = _parse_time_created(xml)
        if ts is None:
            continue
        eid_match = _EVENTID_RE.search(xml)
        eid = int(eid_match.group(1)) if eid_match else (event_id or 0)
        out.append({"ts": ts, "source": provider, "event_id": eid, "summary": summary})
    return out


def query_recent(days: float = 14.0, limit_per_type: int = 20) -> list[CrashEvent]:
    if not _AVAILABLE:
        return []
    cutoff_ts = time.time() - days * 86400
    results: list[CrashEvent] = []
    for provider, event_id, summary in _QUERIES:
        results.extend(_query_one(provider, event_id, summary, limit_per_type))
    results = [e for e in results if e["ts"] >= cutoff_ts]
    results.sort(key=lambda e: e["ts"], reverse=True)
    return results
