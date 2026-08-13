"""The game window: the interval in which an event's *in-game state* can exist (#1828).

Pure logic, imports nothing from the app (same discipline as ``sport_keys.py``)
so it stays circular-import safe and is trivially testable.

WHY THIS EXISTS
---------------
On 2026-08-13 Alex followed Red Sox @ Blue Jays (event ``15192596``, first pitch
19:07 UTC) and the page contradicted itself in four separate places. Every one of
those four traced back to a single fact about the data:

    the event carried 27 period markers, 5 ESPN rows and ~60 stat_model rows
    captured between 2026-08-12T23:35 and 2026-08-13T01:37 — a *different game*,
    played the previous night.

A census of that day's MLB slate found **14 of 14 events** carrying period-bearing
win-prob snapshots more than two hours before their own first pitch. This is not
an outlier; it is the steady state.

The existing guard cannot see it. Gotcha #46 asserts ``completed_at >=
commence_time``, and here that holds comfortably (21:35 > 19:07) — the corruption
is entirely *inside* the accepted range, at the front.

WHAT THE READERS DID WITH IT
----------------------------
Three independent consumers all dedup "by first occurrence of a label", so the
previous night's rows won every tie and the current game's rows were discarded as
duplicates:

* ``SegmentBreakdown`` (iOS Game Segments) ordered its columns off the stale rows
  and rendered ``2 4 8`` for a nine-inning game.
* ``extractPeriodMarkers`` (iOS chart) took each inning's *first-seen* timestamp
  from the previous night, then the domain filter dropped those markers as
  out-of-range — leaving unexplained one- and two-chip strips.
* ``sharedChartDomain`` took ``min(scheduledStart, firstEspnRow)`` and so opened
  the x-axis at 2026-08-12T23:33 — a **22-hour axis for a 2.5-hour game**, which
  is what made the timestamps illegible on a phone.

THE INVARIANT
-------------
    A snapshot that carries in-game state (a period, an inning, a clock) cannot
    predate its own event's first pitch.

That is a statement about baseball, not about our pipeline, which is exactly why
it is safe to enforce on read.

DELIBERATELY NARROW, SO IT IS MONOTONE
--------------------------------------
A row is dropped only when it is **both** state-bearing **and** outside the
window. Rows with no in-game state are never touched — pre-game odds history is
legitimately days old and is what the chart's "All" range is made of. An event
with no ``commence_time`` yields no window and nothing is filtered. So on clean
data this module is the identity function, and over-filtering is unrepresentable
rather than merely unintended.

This is a READ-side repair: it stops every consumer from seeing rows that belong
to another game. It does not fix the writer that mis-attributed them (filed
separately) — and it must not be mistaken for having done so.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Optional

__all__ = [
    "PREGAME_GRACE",
    "POSTGAME_GRACE",
    "MAX_GAME_DURATION",
    "game_state_window",
    "has_in_game_state",
    "is_in_game_window",
    "filter_state_bearing_rows",
]

# A row stamped slightly before the scheduled first pitch is normal: warmups,
# lineup cards, and a clock that starts on the broadcast rather than the pitch.
# One hour is far more room than any of those need, and still ~19 hours short of
# the contamination this guards against.
PREGAME_GRACE = timedelta(hours=1)

# ``completed_at`` is a backend processing timestamp, not a game-end time
# (gotcha #22), so it already trails the final out. The grace is only for rows
# that land between the last out and that stamp.
POSTGAME_GRACE = timedelta(hours=1)

# Ceiling for a live/unfinished event with no ``completed_at`` to bound it.
# Generous enough for an extra-innings marathon or a long rain delay, tight
# enough to exclude the next day's game.
MAX_GAME_DURATION = timedelta(hours=12)

# Keys under which a snapshot's in-game state is recorded. A row carrying any of
# these is making a claim about a game in progress.
_STATE_KEYS = ("period", "inning", "clock", "game_clock")


def _as_aware(value: Any) -> Optional[datetime]:
    """Coerce a datetime or ISO string to a tz-aware UTC datetime, or None."""
    if value is None:
        return None
    dt: Optional[datetime]
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def game_state_window(
    commence_time: Any,
    completed_at: Any = None,
) -> Optional[tuple[datetime, datetime]]:
    """The interval in which this event's in-game state may legitimately fall.

    Returns ``None`` when there is no ``commence_time`` — with no first pitch
    there is no claim to test, so callers must filter nothing.
    """
    start = _as_aware(commence_time)
    if start is None:
        return None

    lower = start - PREGAME_GRACE
    end = _as_aware(completed_at)
    if end is not None and end >= start:
        upper = end + POSTGAME_GRACE
    else:
        # No usable completion stamp (live, or an inverted one — see gotcha #46).
        # Fall back to the duration ceiling rather than leaving it open-ended.
        upper = start + MAX_GAME_DURATION
    return lower, upper


def has_in_game_state(row: Any) -> bool:
    """True when ``row`` claims to describe a game in progress.

    Accepts either a mapping carrying the state keys directly (an ESPN history
    row) or one nesting them under ``game_state`` (a win-prob snapshot row).
    A key present but empty/None is not a claim.
    """
    if not isinstance(row, dict):
        return False

    def _claims(d: Any) -> bool:
        if not isinstance(d, dict):
            return False
        for key in _STATE_KEYS:
            value = d.get(key)
            if value is None:
                continue
            if isinstance(value, str) and not value.strip():
                continue
            # An inning of 0 is "not started", not a claim about a live inning.
            if isinstance(value, (int, float)) and not isinstance(value, bool) and value <= 0:
                continue
            return True
        return False

    return _claims(row) or _claims(row.get("game_state"))


def is_in_game_window(
    timestamp: Any,
    window: Optional[tuple[datetime, datetime]],
) -> bool:
    """True when ``timestamp`` falls inside ``window``.

    An absent window, or an unparseable timestamp, returns True: this guard
    refuses to drop a row it cannot positively convict.
    """
    if window is None:
        return True
    ts = _as_aware(timestamp)
    if ts is None:
        return True
    lower, upper = window
    return lower <= ts <= upper


def filter_state_bearing_rows(
    rows: Iterable[dict],
    window: Optional[tuple[datetime, datetime]],
    *,
    timestamp_key: str = "timestamp",
) -> tuple[list[dict], int]:
    """Drop rows that carry in-game state from outside the game window.

    Returns ``(kept, dropped_count)``. Rows with no in-game state are always
    kept, whatever their timestamp — pre-game odds history is legitimate and is
    what the chart's "All" range is built from.
    """
    rows = list(rows)
    if window is None:
        return rows, 0

    kept: list[dict] = []
    dropped = 0
    for row in rows:
        if has_in_game_state(row) and not is_in_game_window(
            row.get(timestamp_key) if isinstance(row, dict) else None, window
        ):
            dropped += 1
            continue
        kept.append(row)
    return kept, dropped
