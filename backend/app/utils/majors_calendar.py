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


# A pinned FIXTURE's window, and BOTH ENDS ARE ANCHORED ON THE KICKOFF.
#
# Neither end may be anchored on a calendar DAY, and each end proves it
# differently — CERT-2432 caught the second one after the first had been fixed.
#
# The TAIL cannot be the concept window (midnight after the `end` day, then
# +36h), because a game is over in three hours and the day it sits in is not:
# the NFL opener kicks off 00:20 UTC, so a day-anchored tail would hold the top
# of the Sports tab for thirteen hours after the final whistle.
#
# The LEAD cannot be the `start` day's 00:00 UTC either, and this is subtler,
# because that boundary looks like it opens the window EARLY. For a US primetime
# game it opens it LATE. The opener is Wednesday evening in America and
# 2026-09-10 in UTC, so a midnight-UTC lead opens at 5:00pm PT — twenty minutes
# before kickoff. #4541's own headline specimen is the game buried at 23:31Z,
# **49 minutes before kickoff and 29 minutes before that midnight**, so the first
# version of this window missed the exact measurement the issue was filed on.
# The UTC-day trap that the calendar entry's note warns about cuts both ways: it
# moves a US evening game FORWARD a day, which is right for identifying the
# fixture and wrong for opening its window.
#
# So the dates on the entry identify WHICH fixture is meant, and the kickoff
# alone decides WHEN the pin is live. There is no midnight in the window maths.
#
# 6.0 tail is `feed_scoring.COMPLETED_DECAY_HOURS` — the hour at which the
# freshness model has finished decaying a completed game and calls the result
# yesterday's news. The pin releasing on the same clock that stops crediting the
# result is one decision rather than two that can drift apart.
#
# 6.0 lead is Fable-5's T-6h (note of 2026-09-09 6:05pm PT, endorsing the bus's
# marquee ask: a sole-national-TV game "leads from T-6h"). It is deliberately far
# wider than the 49 minutes the specimen needs — a marquee game is the thing a
# reader opens the tab for on the afternoon of, not only once it is nearly on.
FIXTURE_PIN_LEAD_HOURS = 6.0
FIXTURE_PIN_TAIL_HOURS = 6.0


def marquee_fixture_entries(path: str | Path | None = None) -> list[dict[str, Any]]:
    """Calendar entries that name a single FIXTURE rather than a concept surface.

    An entry qualifies when it is flagged ``marquee`` and carries a ``fixture``
    block with a ``sport_key``. These are the entries that can pin a
    ``type: "event"`` card — a marquee GAME, as opposed to the multi-day
    tournament concepts ``marquee_concept_keys`` serves.
    """
    out: list[dict[str, Any]] = []
    for e in load_calendar(path):
        if not e.get("marquee"):
            continue
        fixture = e.get("fixture")
        if isinstance(fixture, dict) and fixture.get("sport_key"):
            out.append(e)
    return out


def fixture_marquee_pinned(
    sport_key: str | None,
    commence_time: datetime | None,
    now: datetime,
    entries: list[dict[str, Any]] | None = None,
    lead_hours: float = FIXTURE_PIN_LEAD_HOURS,
    tail_hours: float = FIXTURE_PIN_TAIL_HOURS,
) -> bool:
    """Is this game inside a calendar-declared marquee pin window?

    Returns a plain bool rather than the ``"live"``/``"whathit"`` vocabulary
    ``marquee_pin_state`` uses. Those states exist because a settled concept's
    WHAT-HIT window drives champion resolution; nothing downstream of a fixture
    pin asks which half of the window it is in, and inventing a "whathit" for a
    game would mean inventing a per-sport game length to place the boundary.
    One honest question, one honest answer.

    The entry's dates decide WHICH fixture is meant; the kickoff decides WHEN.
    A fixture matches an entry when its ``sport_key`` is the entry's and its
    kickoff falls on one of the entry's UTC dates. The window is then
    ``[commence_time - lead_hours, commence_time + tail_hours)`` — no calendar
    midnight appears in it, for the reasons on the constants above.

    ⚠️ THE ENTRY'S DATES ARE UTC, AND A US PRIMETIME KICKOFF IS THE NEXT UTC DAY.
    The 2026 NFL opener is Wednesday evening in America and ``2026-09-10`` here.
    Dating such an entry by its local day silently matches nothing — and note
    that this shifts the MATCH forward a day while the pre-game window the reader
    cares about is still on the previous UTC day, which is why the window is not
    allowed to key on the date (CERT-2432).

    Pure and defensive: anything unusable returns False, never an exception —
    a bad calendar edit must not be able to empty or crash the feed.
    """
    if not sport_key or commence_time is None:
        return False
    if entries is None:
        entries = marquee_fixture_entries()
    if commence_time.tzinfo is None:
        commence_time = commence_time.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    kickoff_date = commence_time.date()
    for entry in entries:
        fixture = entry.get("fixture")
        if not isinstance(fixture, dict) or fixture.get("sport_key") != sport_key:
            continue
        start_d = _as_utc_date(entry.get("start"))
        end_d = _as_utc_date(entry.get("end"))
        if start_d is None or end_d is None:
            continue
        if not (start_d <= kickoff_date <= end_d):
            continue
        window_open = commence_time - timedelta(hours=lead_hours)
        window_close = commence_time + timedelta(hours=tail_hours)
        if window_open <= now < window_close:
            return True
    return False


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


def calendar_window_state(
    entry: dict[str, Any] | None,
    now: datetime,
    post_settlement_hours: int = 36,
) -> str | None:
    """Where ``now`` sits in a calendar ENTRY's window: the one clock.

    Returns "upcoming" / "live" / "whathit" / "past", or None when the entry is
    missing or its dates are unusable.

    Windows, anchored on the entry's inclusive end DAY (settlement = the UTC
    midnight AFTER the ``end`` date, so the whole finish day still counts live):
      - "upcoming" while  now       <  start 00:00 UTC
      - "live"     while  start     <= now <  settlement
      - "whathit"  while  settlement<= now <  settlement + post_settlement_hours
      - "past"     once   now       >= settlement + post_settlement_hours

    Split out of `marquee_pin_state` (#4449) because that function answers a
    PIN question and collapses "not yet" and "long over" into the same None —
    fine for a pin, useless to a caller deciding upcoming-vs-settled. Two very
    different states behind one empty answer is gotcha #53, so the discriminating
    read gets its own name and `marquee_pin_state` keeps its exact contract by
    delegating here. The date math lives once.

    Pure and defensive; naive ``now`` is read as UTC.
    """
    if not entry:
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
    if now < start_dt:
        return "upcoming"
    if now < settlement_dt:
        return "live"
    if now < whathit_end:
        return "whathit"
    return "past"


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
    state = calendar_window_state(entry, now, post_settlement_hours)
    return state if state in ("live", "whathit") else None
