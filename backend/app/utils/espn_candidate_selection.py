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

### The residual queue 385 wrote down — and FF1 closed (queue 387)

385 stated its own residual honestly: *"within the bound the gate cannot
distinguish a doubleheader's sibling when the correct row is absent — the two
halves are ~5.5h apart and both authorize."* Codex (``C-2058-REVIEW``, P1)
executed that sentence against the real live path and got
``matched_id='espn-game-2', method='name'``, with the writer compiling
``espn_id='espn-game-2'`` and adding it to ``claimed``.

The defect underneath the number: **the gate read a fact about what we happened
to fetch as a fact about which game this is.** Absence of the correct scoreboard
half converted the wrong half into an authorized identity. No threshold can fix
that, because a lone row 4h out and a lone row 5.5h out are the same epistemic
situation — which is why five prior certification rounds each moved a threshold
and each produced a new specimen class.

So the rule is now about **evidence**, not distance:

* **Uncorroborated, name-only** selection is authoritative only inside
  :data:`MAX_SAME_GAME_SECONDS`, which is the doubleheader boundary — the gap
  below which no two same-teams games can both exist.
* **Corroborated** selection reaches out to
  :data:`MAX_CORROBORATED_SAME_GAME_SECONDS` (the merge window). Corroboration
  is one of exactly two things, both of them positive evidence:

  1. a **provider anchor** — the candidate's ``espn_id`` is the id our row
     already holds, so identity comes from ESPN, not from a clock;
  2. a **present-and-rejected sibling** — another same-teams row was in the
     pool and lost the distance comparison. The pool therefore contained the
     slate's same-teams rows and the winner is not "the only row we fetched".

  Codex's line, kept verbatim because it is the whole rule: *the correct half
  being present and rejected is real evidence; the correct half being absent is
  not.*

* Everything else **refuses**, and says which gate refused (gotcha #53).

### The self-contradiction this resolves

``prediction_market_matching._ticker_date_conflicts_with_event`` — an
independent guard on an independent rail — calls anything beyond **±3h** of a
known start time a DIFFERENT game (Q439 retired the sibling helper this used to
name; the ±3h is unchanged, only the instant it measures from was corrected).
That ±3h is measured, not chosen: a 1,000-row systematic production sample
(2026-08-12) put 744 linked MLB markets at exactly 0h once the ticker's Eastern
clock was read correctly, and the ±3h rule reproduced the independently
measured 24.4% wrong-game rate almost exactly.

385 set the espn_id gate to the 6h **merge** window instead, so the repository
held two answers to one question. They are resolved here in favour of the
conservative one, because they are not actually the same question:

* **merge** asks *may these two rows be absorbed into one?* — and ruling 048
  already requires an id anchor for that, so its window is never the sole
  evidence;
* **identity** asks *may this scoreboard row BECOME this event's espn_id?* — a
  wrong answer is neither visible nor reversible (#1980 measured ±15/±30 id
  offsets sitting against a perfectly correct ``commence_time``).

Nothing about the merge invariant changed: ``MAX_ABSORPTION_SEPARATION_SECONDS``
is untouched and still reachable here, as
:data:`MAX_CORROBORATED_SAME_GAME_SECONDS`, once there is evidence beside it.

### The declared cost

Fail-closed means some real games stop getting an ``espn_id`` from a name match
— ESPN "TBD" placeholder times, long rain delays, a genuinely lone late row.
That cost is bounded and reversible: the id arrives on the next sync once ESPN
posts a real time, or via arm 1 once anything anchors it, and a missing stamp is
visible. A wrong stamp is neither (gotcha #32's standing trade).

A tie (two candidates equidistant) keeps the earlier one, so the function stays
deterministic for doubleheaders, which are a real same-day same-teams pair and
must not start depending on pool order either.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Iterable, Optional, Sequence

from app.utils.event_merge_invariant import MAX_ABSORPTION_SEPARATION_SECONDS
from app.utils.name_normalization import names_match

#: The **merge** window, reachable here only WITH corroboration.
#:
#: ``event_merge_invariant.MAX_ABSORPTION_SEPARATION_SECONDS`` answers "may
#: these two records be absorbed into one?" — a question ruling 048 already
#: requires an id anchor to answer, so this number is never that rail's sole
#: evidence either. Queue 385 imported it as the *identity* bound as well, on
#: the reasoning that one question deserves one number. FF1's correction is
#: that they are two questions (see the module docstring), and only the
#: corroborated arm of the identity question may borrow the merge answer.
MAX_CORROBORATED_SAME_GAME_SECONDS = MAX_ABSORPTION_SEPARATION_SECONDS

#: The **doubleheader boundary**: how far a *name-only, uncorroborated* ESPN
#: scoreboard listing may sit from our ``commence_time`` and still be believed
#: to be the same game.
#:
#: This is the repository's own already-measured number, not a new one.
#: ``prediction_market_matching._EVENT_DATE_MAX_DIFF_HOURS`` treats ±3h around
#: a known start time as "same game" and anything beyond as a DIFFERENT game,
#: separating doubleheaders ~5h apart. Its docstring block records
#: the measurement: a 1,000-row systematic production sample (2026-08-12) put
#: 744 linked MLB markets at exactly 0h once the ticker's Eastern clock was read
#: correctly, and the ±3h rule reproduced the independently measured 24.4%
#: wrong-game rate almost exactly.
#:
#: **Deliberate divergence, stated rather than silent:** this is now SMALLER
#: than ``MAX_ABSORPTION_SEPARATION_SECONDS``, which FF1 did not touch. Two
#: rails, two questions, and identity is the stricter of the two because a wrong
#: ``espn_id`` is neither visible nor reversible. If you are here to reconcile
#: them again, reconcile the merge rail DOWN, never this one up.
#:
#: Lowering it is safe. Raising it re-opens the manufacturer.
NAME_ONLY_SAME_GAME_SECONDS = 3 * 60 * 60

#: Back-compatible name for the bound that applies when nothing corroborates the
#: match — which is the default, and the only bound the five sibling rails hit
#: today. Kept as the exported name because every caller and test that says
#: "the same-game bound" means the uncorroborated one.
MAX_SAME_GAME_SECONDS = NAME_ONLY_SAME_GAME_SECONDS


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
    *,
    corroboration: Optional[str] = None,
) -> tuple[bool, str]:
    """May a candidate starting at ``espn_date`` claim to be our game?

    ``corroboration`` is a short token naming *positive evidence of identity*
    that exists independently of the clock — ``"provider-anchor"`` or
    ``"slate-sibling-rejected"`` (see :func:`select_authorized_espn_candidate`).
    Passing one widens the bound from the doubleheader boundary to the merge
    window; passing ``None`` — the default, and what every caller with no such
    evidence must pass — keeps the tight bound.

    It is deliberately a *token*, not a bool: a caller that cannot name its
    evidence does not have any, and a log line reading ``ok-corroborated`` with
    no source would be exactly the kind of unfalsifiable green gotcha #53 is
    about.

    Returns ``(authorized, reason)``. The reason is a short stable token so a
    caller can log *which* gate refused — "nothing matched on names", "matched
    on names but is too far to be this game", and "matched on names, close
    enough to be a doubleheader sibling, and nothing else says otherwise" are
    three different facts, and a rail that reports them identically cannot be
    debugged.
    """
    if commence_time is None:
        return (False, "no-commence-time")
    if espn_date is None:
        return (False, "candidate-has-no-date")

    gap = abs((_as_utc(espn_date) - _as_utc(commence_time)).total_seconds())
    if gap > MAX_CORROBORATED_SAME_GAME_SECONDS:
        return (False, f"separated-{gap / 3600:.1f}h")
    if gap <= NAME_ONLY_SAME_GAME_SECONDS:
        return (True, "ok")
    if corroboration:
        return (True, f"ok-corroborated:{corroboration}")
    # Inside the merge window but outside the doubleheader boundary, with no
    # evidence beside the clock. This is codex's specimen: the row may be this
    # game, or the other half of a doubleheader whose correct half simply is not
    # in the pool, and nothing here can tell those apart. Refuse.
    return (False, f"unverifiable-{gap / 3600:.1f}h-sibling-possible")


def select_authorized_espn_candidate(
    candidates: Sequence[Any],
    commence_time: Optional[datetime],
    *,
    is_name_match: Callable[[Any], bool],
    exclude_ids: Optional[Iterable[str]] = None,
    anchor_espn_id: Optional[str] = None,
) -> tuple[Optional[Any], str]:
    """The shared primitive every ``espn_id`` writer selects through.

    Each sibling rail has its own flavour of name matching — ``names_match``,
    ``espn_team_matches``, substring+LLM, swapped-orientation — so the matcher
    comes in as a predicate and only the *authority* logic lives here. That is
    the point: five rails disagreeing about names is a quality problem, five
    rails disagreeing about whether time authorizes a stamp is #1980.

    ``anchor_espn_id`` is the id our own row already holds, if any. A candidate
    carrying that same id is anchored by ESPN's own identity rather than by a
    name and a clock, so it corroborates (see the module docstring). Pass it
    whenever the caller has it; passing nothing simply means no anchor.

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

    # ── corroboration: positive evidence of identity, not a wider clock ──────
    corroboration: Optional[str] = None
    best_id = getattr(best, "espn_id", None)
    if anchor_espn_id and best_id and str(best_id) == str(anchor_espn_id):
        # ESPN's own id, already on our row. Identity is not being derived from
        # the name at all — the name match merely located a row we already own.
        corroboration = "provider-anchor"
    elif len(matches) > 1:
        # A same-teams sibling was PRESENT in the pool and lost the distance
        # comparison. That is a fact about ESPN's slate, not about our fetch:
        # the pool did contain the other same-teams rows, so the winner is not
        # "the only row we happened to have". Codex's own distinction — the
        # correct half being present and rejected is evidence; absent is not.
        corroboration = "slate-sibling-rejected"

    authorized, reason = authorize_espn_pair(
        getattr(best, "date", None), commence_time, corroboration=corroboration,
    )
    if not authorized:
        return (None, reason)
    return (best, reason)


def _display(team: Any) -> str:
    """ESPN team display name, with the same fallback chain the caller used."""
    return (getattr(team, "display_name", None) or getattr(team, "name", None) or "")


def select_espn_candidate(
    candidates: Sequence[Any],
    home_team: str,
    away_team: str,
    commence_time: datetime,
    *,
    anchor_espn_id: Optional[str] = None,
) -> tuple[Optional[datetime], Optional[str]]:
    """Return ``(espn_commence_time, espn_id)`` for the best-matching game.

    ``(None, None)`` when nothing matches on names **or** when the best match
    fails the same-game authorization gate — an unverifiable match stamps
    nothing. Callers wanting to know *which* of those two happened should use
    :func:`select_authorized_espn_candidate` and read its reason.

    See the module docstring for why time is an authorization gate rather than a
    tie-breaker, and why the uncorroborated bound is the doubleheader boundary.
    ``candidates`` is the two-day pool; ``commence_time`` is the Odds API
    listing's start time, which is the only thing that can tell two games of the
    same series apart.
    """
    best, _reason = select_authorized_espn_candidate(
        candidates,
        commence_time,
        is_name_match=lambda ee: (
            names_match(home_team, _display(ee.home_team))
            and names_match(away_team, _display(ee.away_team))
        ),
        anchor_espn_id=anchor_espn_id,
    )
    if best is None:
        return (None, None)
    return (best.date, best.espn_id)
