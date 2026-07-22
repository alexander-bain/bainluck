"""Shared loader for THE HORIZON CALENDAR (app/config/majors_calendar.yaml).

Queue #223. Both the Horizon Sentinel (Item 1 — early-warning) and the feed's
marquee-pinning pass (Item 2 — pin in-progress marquee concepts atop the sports
feed) read the calendar through here, so there is one parser and one file. Pure and
defensive: any failure returns [] / an empty set so a bad edit never crashes a beat
or empties the feed.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
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


def _as_utc_date(value: Any) -> date | None:
    """Coerce a YAML date field (date, datetime, or 'YYYY-MM-DD' str) to a date."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value.strip()[:10])
        except ValueError:
            return None
    return None


def marquee_pin_state(
    concept_key: str,
    now: datetime,
    entries: dict[str, dict[str, Any]] | None = None,
    post_settlement_hours: int = 36,
) -> str | None:
    """Return the marquee-pin state for a concept_key at ``now``.

    Purely calendar-date driven (source-independent — Kalshi settled markets stay
    status='open', gotcha #33, and the odds_api winner-field can fizzle without ever
    flipping to settled, so market/event state is an unreliable window anchor).

    Windows, anchored on the calendar entry's inclusive end DAY (settlement = the
    UTC midnight AFTER the ``end`` date, so the whole finish day still counts live):
      - "live"    while  start 00:00 UTC  <=  now  <  settlement
      - "whathit" while  settlement       <=  now  <  settlement + post_settlement_hours
      - None      otherwise (not yet a marquee window, or the pin has expired)

    Only entries flagged ``marquee: true`` with a ``concept_key`` are pinnable;
    everything else returns None. Defensive: bad/missing dates return None.
    """
    if entries is None:
        entries = calendar_entry_by_concept_key()
    entry = entries.get(str(concept_key))
    if not entry or not entry.get("marquee"):
        return None
    start_d = _as_utc_date(entry.get("start"))
    end_d = _as_utc_date(entry.get("end"))
    if start_d is None or end_d is None:
        return None
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    start_dt = datetime.combine(start_d, time.min, tzinfo=timezone.utc)
    # Settlement = midnight after the end day, so the finish day itself reads "live".
    settlement_dt = datetime.combine(end_d, time.min, tzinfo=timezone.utc) + timedelta(days=1)
    whathit_end = settlement_dt + timedelta(hours=post_settlement_hours)
    if start_dt <= now < settlement_dt:
        return "live"
    if settlement_dt <= now < whathit_end:
        return "whathit"
    return None
