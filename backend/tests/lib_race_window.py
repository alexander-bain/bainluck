"""A calendar seam for a specimen that names a real, dated edition.

WHAT THIS IS FOR
================

Gotcha #44 says: derive the anchor from the clock, never a literal. Three test
files did exactly that and still went red together at 2026-09-14 00:00Z,
because the other half of the trap is not the anchor at all — it is **what the
anchor is measured against**.

A cycling specimen whose ``resolution_date`` is honestly ``now + 13 days`` still
derives the concept key ``event:cycling:vuelta-<year>``, and ``cycling_status``
asks ``majors_calendar.yaml`` where that edition sits (#4449 — "live" is a claim
the reader can check, so it is anchored on the race, not on a band before the
market's close date). The real Vuelta 2026 was ridden 2026-08-22 → 2026-09-13.
The moment the real race ended, every specimen naming that edition became
``settled`` — by the product's own correct answer — and a test asserting "a race
in progress surfaces" was asserting something no longer true of the race it
named. No commit caused it; the peloton crossed a finish line.

Note what is NOT the fix. The date in the yaml is right and stays right: the
race really did end on the 13th. Moving it forward would trade a red suite for a
wrong calendar, which is the product defect #4449 shipped to remove. The
specimen is what has to stop borrowing a real edition's real dates.

HOW TO USE IT
=============

Pin the window your specimen needs, anchored on the instant under test::

    pin_race_window(monkeypatch, "event:cycling:vuelta-2026", when=now)

Only the keys you name are overlaid; every other entry still comes from the real
yaml, so a test that wants the real calendar keeps it.

WHY THIS IS NOT A VACUOUS PASS
==============================

The overlay is keyed on the concept key the code under test DERIVES. If edition
derivation breaks, the derived key stops matching the pinned one, the overlay
never applies, the real calendar answers, and the suite goes red — which is the
behaviour those files exist to guard (#2482). The seam supplies the specimen's
own dates; it never supplies the answer.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

__all__ = ["race_window_entry", "pin_race_window"]


def race_window_entry(
    concept_key: str,
    when: datetime,
    *,
    started_days_ago: int = 5,
    ends_in_days: int = 8,
) -> dict[str, Any]:
    """A calendar entry whose race is mid-stage at ``when``.

    Both ends are offsets from the instant under test, so the entry describes a
    stage race in progress at whatever instant it is asked about. The defaults
    put ``when`` comfortably inside the window rather than on either boundary —
    ``calendar_window_state`` is inclusive of the end DAY and opens at the start
    day's 00:00 UTC, and a specimen sitting on a boundary would be testing the
    boundary instead of the thing it came to test.
    """
    day: date = when.astimezone(timezone.utc).date()
    return {
        "concept_key": concept_key,
        "start": day - timedelta(days=started_days_ago),
        "end": day + timedelta(days=ends_in_days),
        "domain": "cycling",
        "archetype": "winner_field",
        "marquee": True,
    }


def pin_race_window(
    monkeypatch,
    *concept_keys: str,
    when: datetime | None = None,
    started_days_ago: int = 5,
    ends_in_days: int = 8,
) -> dict[str, dict[str, Any]]:
    """Overlay clock-relative windows for ``concept_keys`` on the real calendar.

    Returns the overlay map, so a caller can assert against the dates it pinned.

    Every consumer imports ``calendar_entry_by_concept_key`` INSIDE the function
    that calls it (``event_cycling.cycling_status``, ``routes/feed.py`` twice),
    so patching the definition in ``majors_calendar`` reaches all of them — there
    is no module-level binding anywhere to miss.
    """
    from app.utils import majors_calendar

    at = when or datetime.now(timezone.utc)
    overlay = {
        k: race_window_entry(
            k, at, started_days_ago=started_days_ago, ends_in_days=ends_in_days
        )
        for k in concept_keys
    }
    real = majors_calendar.calendar_entry_by_concept_key

    def _with_overlay(*a, **k):
        merged = dict(real(*a, **k))
        merged.update(overlay)
        return merged

    monkeypatch.setattr(majors_calendar, "calendar_entry_by_concept_key", _with_overlay)
    return overlay
