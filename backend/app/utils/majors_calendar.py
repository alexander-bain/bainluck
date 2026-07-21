"""Shared loader for THE HORIZON CALENDAR (app/config/majors_calendar.yaml).

Queue #223. Both the Horizon Sentinel (Item 1 — early-warning) and the feed's
marquee-pinning pass (Item 2 — pin in-progress marquee concepts atop the sports
feed) read the calendar through here, so there is one parser and one file. Pure and
defensive: any failure returns [] / an empty set so a bad edit never crashes a beat
or empties the feed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

_CALENDAR_PATH = Path(__file__).resolve().parent.parent / "config" / "majors_calendar.yaml"


def load_calendar(path: str | Path | None = None) -> list[dict]:
    """Load and normalize the majors calendar. Returns [] on any failure."""
    p = Path(path) if path else _CALENDAR_PATH
    try:
        import yaml  # declared in requirements.txt (Queue #223)
    except Exception:  # pragma: no cover - dep guard
        return []
    try:
        with open(p, "r", encoding="utf-8") as fh:
            raw = yaml.safe_load(fh) or {}
    except Exception:
        return []
    entries = raw.get("majors") if isinstance(raw, dict) else raw
    if not isinstance(entries, list):
        return []
    return [e for e in entries if isinstance(e, dict) and e.get("slug")]


def marquee_concept_keys(path: str | Path | None = None) -> set[str]:
    """The set of concept_keys flagged marquee (Item 2 pins these when in progress).
    Only entries carrying a concept_key qualify — a marquee plain-event with no
    concept surface can't be pinned as a concept card."""
    keys: set[str] = set()
    for e in load_calendar(path):
        if e.get("marquee") and e.get("concept_key"):
            keys.add(str(e["concept_key"]))
    return keys


def calendar_entry_by_concept_key(path: str | Path | None = None) -> dict[str, dict[str, Any]]:
    """Map concept_key -> calendar entry (for entries that carry a concept_key)."""
    out: dict[str, dict[str, Any]] = {}
    for e in load_calendar(path):
        ck = e.get("concept_key")
        if ck:
            out[str(ck)] = e
    return out
