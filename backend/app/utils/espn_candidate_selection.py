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

**Time is an AUTHORIZATION gate, not a tie-breaker** (amended by queue 385 after
codex ``C-2049-2050-REVIEW`` BLOCKed the tie-breaker-only version):

* candidates are filtered to those matching on names;
* the one **closest in time** to the listing's ``commence_time`` wins the tie;
* and the winner is then **authorized** — it stamps nothing unless its own date
  is present and within :data:`MAX_SAME_GAME_SECONDS` of ``commence_time``.

### Why the tie-breaker alone was not enough

The first version consulted time only once ``len(matches) >= 2`` and returned a
lone match unconditionally. Codex executed that selector and got two live
manufactures out of it:

* a sole candidate **24 hours** after the requested game → returned and stamped;
* a sole candidate with ``date=None`` → returned as ``(None, espn_id)``, an id
  with no time beside it at all.

Both are ordinary production shapes, not contrivances: a missing correct
scoreboard row, a same-city false accept (#2046), or a partial two-day fetch each
leave exactly one wrong candidate in the pool. **A tie-break picks the best
candidate; it does not make the best candidate correct.** So the gate runs on the
winner too, and on the one-candidate path, and on the missing-date path.

### The residual, stated rather than hidden

Within the bound the gate cannot distinguish a doubleheader's sibling when the
correct row is *absent* from the pool — the two halves are ~5.5h apart and both
authorize. Closest-wins resolves it whenever both are present, which is the
common case. Tightening the bound would trade that residual for refusing real
postponements; :data:`MAX_SAME_GAME_SECONDS` is deliberately the same number the
merge invariant uses so there is one bound in the codebase, not two.

A tie (two candidates equidistant) keeps the earlier one, so the function stays
deterministic for doubleheaders, which are a real same-day same-teams pair and
must not start depending on pool order either.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Iterable, Optional, Sequence

from app.utils.event_merge_invariant import MAX_ABSORPTION_SEPARATION_SECONDS
from app.utils.name_normalization import names_match

#: How far an ESPN scoreboard listing may sit from our ``commence_time`` and
#: still be believed to be **the same game**.
#:
#: Same value, and deliberately the same value, as
#: ``event_merge_invariant.MAX_ABSORPTION_SEPARATION_SECONDS``: both answer the
#: one question "are these two records the same real-world game?", and two
#: independently-tuned answers to one question is how the codebase grows a
#: contradiction. The merge module's own note measures the tightest true-series
#: pair in 60 days at **42.0h**, so 6h clears a genuine series by a wide margin
#: while refusing codex's 24.0h specimen.
#:
#: Lowering it is safe. Raising it re-opens the manufacturer.
MAX_SAME_GAME_SECONDS = MAX_ABSORPTION_SEPARATION_SECONDS


def _as_utc(value: Optional[datetime]) -> Optional[datetime]:
    """Production mixes tz-aware ESPN dates with naive DB timestamps.

    Subtracting one from the other raises ``TypeError``, and a gate that can
    crash the poll is not a gate. Naive values are read as UTC, which is what
    every timestamp in this codebase already is.
    """
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def authorize_espn_pair(
    espn_date: Optional[datetime],
    commence_time: Optional[datetime],
) -> tuple[bool, str]:
    """May a candidate starting at ``espn_date`` claim to be our game?

    Returns ``(authorized, reason)``. The reason is a short stable token so a
    caller can log *which* gate refused — gotcha #53: "nothing matched on names"
    and "matched on names but failed the same-game check" are different facts,
    and a rail that reports them identically cannot be debugged.
    """
    if commence_time is None:
        return (False, "no-commence-time")
    if espn_date is None:
        return (False, "candidate-has-no-date")

    gap = abs((_as_utc(espn_date) - _as_utc(commence_time)).total_seconds())
    if gap > MAX_SAME_GAME_SECONDS:
        return (False, f"separated-{gap / 3600:.1f}h")
    return (True, "ok")


def select_authorized_espn_candidate(
    candidates: Sequence[Any],
    commence_time: Optional[datetime],
    *,
    is_name_match: Callable[[Any], bool],
    exclude_ids: Optional[Iterable[str]] = None,
) -> tuple[Optional[Any], str]:
    """The shared primitive every ``espn_id`` writer selects through.

    Each sibling rail has its own flavour of name matching — ``names_match``,
    ``espn_team_matches``, substring+LLM, swapped-orientation — so the matcher
    comes in as a predicate and only the *authority* logic lives here. That is
    the point: five rails disagreeing about names is a quality problem, five
    rails disagreeing about whether time authorizes a stamp is #1980.

    Returns ``(candidate_or_None, reason)``.
    """
    excluded = {str(x) for x in (exclude_ids or ())}

    matches = [
        ee for ee in candidates
        if getattr(ee, "home_team", None) and getattr(ee, "away_team", None)
        and not (getattr(ee, "espn_id", None) and str(ee.espn_id) in excluded)
        and is_name_match(ee)
    ]
    if not matches:
        return (None, "no-name-match")

    def _distance(ee: Any):
        date = _as_utc(getattr(ee, "date", None))
        if date is None or commence_time is None:
            # Cannot be compared on the only axis that distinguishes it. Sort
            # last rather than crashing; the gate below refuses it anyway.
            return (1, 0.0)
        return (0, abs((date - _as_utc(commence_time)).total_seconds()))

    # `min` is stable, so an exact tie (a doubleheader) keeps the earlier one.
    best = min(matches, key=_distance)

    authorized, reason = authorize_espn_pair(getattr(best, "date", None), commence_time)
    if not authorized:
        return (None, reason)
    return (best, "ok")


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

    ``(None, None)`` when nothing matches on names **or** when the best match
    fails the same-game authorization gate — an unverifiable match stamps
    nothing. Callers wanting to know *which* of those two happened should use
    :func:`select_authorized_espn_candidate` and read its reason.

    See the module docstring for why time is the gate and not just the
    tie-breaker. ``candidates`` is the two-day pool; ``commence_time`` is the
    Odds API listing's start time, which is the only thing that can tell two
    games of the same series apart.
    """
    best, _reason = select_authorized_espn_candidate(
        candidates,
        commence_time,
        is_name_match=lambda ee: (
            names_match(home_team, _display(ee.home_team))
            and names_match(away_team, _display(ee.away_team))
        ),
    )
    if best is None:
        return (None, None)
    return (best.date, best.espn_id)
