"""Pick which ESPN scoreboard game an Odds API listing refers to (#1980).

This module exists because the selection it performs was, until now, six
inlined lines in the middle of ``discover_events`` — and those six lines are
the ``espn_id`` MANUFACTURER that #1980's repair rail has been cleaning up
after.

## The defect, stated once

``app/tasks/sports.py`` pre-fetches ESPN scoreboards into ``espn_events_by_date``
and then builds a candidate pool spanning **two calendar days**::

    date_str  = commence_time.strftime("%Y%m%d")
    prev_date = (commence_time - timedelta(days=1)).strftime("%Y%m%d")
    espn_candidates = (espn_events_by_date.get(date_str, [])
                       + espn_events_by_date.get(prev_date, []))

The two-day pool is **correct and deliberate**: ESPN buckets its scoreboard by
US Eastern date, so a 10pm ET game on Aug 18 has a UTC timestamp of Aug 19 and
would be missed by a single-day lookup. The widening is the fix to a real bug.

What was missing is the other half. Having widened the pool to two days, the
loop then selected with **no time discrimination whatsoever** — it matched on
team names alone and ``break``-ed on the first hit::

    for ee in espn_candidates:
        if names_match(home, espn_home) and names_match(away, espn_away):
            espn_commence_time = ee.date
            espn_event_id = ee.espn_id
            break

For any sport where the same two clubs meet on consecutive days — an MLB series
(3–4 games), an NBA/NHL back-to-back, any playoff series — **both days' games
are in the pool and both match the names**. The loop takes whichever the
concatenation presents first, which is the ``date_str`` bucket. For a late/West
Coast game that bucket is *the following day's slate*, so the id stamped is
systematically the NEXT game of the series.

That is the observed signature. ESPN allocates game ids in schedule order, and
an MLB slate is ~15 games, so "one day off in the same series" shows up as an
``espn_id`` off by **±15**, and two days off as **±30** — which is exactly what
#1980's review found: ±15/±30 offsets on 15 of 17 rows, against a
``commence_time`` that was *correct*.

## Why the time stayed right while the id went wrong

The asymmetry is in ``event_registry``. The claim is made in ``odds_api``'s name
(``sports.py`` builds ``EventClaim("odds_api", ...)`` even when the *time* came
from ESPN), so ``_update_fields_by_priority`` compares ``odds_api`` (priority 1)
against a row already sourced ``espn`` (priority 3), and **refuses** to move
``commence_time``. The ``espn_id`` stamp that runs immediately afterwards has no
such gate. The time is protected; the id is not.

## Why the #2017 collision guard does not catch it

``espn_id_stamp.stamp_espn_id_if_unheld`` refuses only when **another row already
holds** the id. The neighbouring day's game is usually a future fixture we do
not hold yet, so the wrong id is *unheld* and the stamp proceeds. That guard is
a collision guard, not a correctness guard — its own docstring already names
this path as deriving the id "by matching TEAM NAMES against a scoreboard
listing" (ruling 042), but it can only block the subset that collides.

## The rule implemented here

**Deliberately the narrowest change that removes the ambiguity:**

* exactly one name-matching candidate → return it, unchanged from today;
* two or more → return the one **closest in time** to the listing's
  ``commence_time``.

The single-match path is bit-for-bit the old behaviour, so this cannot regress
the case the two-day pool was widened to fix. Only the genuinely ambiguous case
— the one that was previously decided by dict ordering — changes, and it is
decided by the only signal that actually distinguishes the two games.

A tie (two candidates equidistant) keeps the earlier one, so the function stays
deterministic for doubleheaders, which are a real same-day same-teams pair and
must not start depending on pool order either.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional, Sequence

from app.utils.name_normalization import names_match


def _display(team: Any) -> str:
    """ESPN team display name, with the same fallback chain the caller used."""
    return (getattr(team, "display_name", None) or getattr(team, "name", None) or "")


def select_espn_candidate(
    candidates: Sequence[Any],
    home_team: str,
    away_team: str,
    commence_time: datetime,
) -> tuple[Optional[datetime], Optional[str]]:
    """Return ``(espn_commence_time, espn_id)`` for the best-matching game.

    ``(None, None)`` when nothing matches on names.

    See the module docstring for why "best" must consider time and not just
    names. ``candidates`` is the two-day pool; ``commence_time`` is the Odds API
    listing's start time, which is the only thing that can tell two games of the
    same series apart.
    """
    matches = []
    for ee in candidates:
        if not ee.home_team or not ee.away_team:
            continue
        if names_match(home_team, _display(ee.home_team)) and names_match(
            away_team, _display(ee.away_team)
        ):
            matches.append(ee)

    if not matches:
        return (None, None)

    if len(matches) == 1:
        return (matches[0].date, matches[0].espn_id)

    # 2+ candidates share these team names inside the two-day window. This is
    # the series/back-to-back case the old code resolved by dict ordering.
    # `min` is stable, so an exact tie (a doubleheader) keeps the earlier one.
    def _distance(ee: Any):
        if ee.date is None:
            # A candidate with no date cannot be compared on the only axis that
            # distinguishes it. Sort it last rather than crashing the poll.
            return (1, 0.0)
        return (0, abs((ee.date - commence_time).total_seconds()))

    best = min(matches, key=_distance)
    return (best.date, best.espn_id)
