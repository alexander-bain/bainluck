"""Is a "live" event's probability series actually moving? (#5077)

A row reads ``live``, has no score, and its win probability has not changed in
hours. On a reader's phone that is a LIVE pill, a 20s refresh ticker, a hero at
99% and a dead-straight chart — a page promising liveness it cannot back. The
venue, meanwhile, settled every market on the match three hours ago.

This module holds the predicate that separates those rows from the ones that are
genuinely being played, plus the two floors it needs. It is stdlib-only on
purpose (the same reason ``app/utils/lifecycle.py`` is) so the serving route, a
task and a test can all share the one rule rather than re-derive it.

WHAT IT IS NOT
--------------
It does not decide the event is over and it never writes ``status``. The output
is a signal a surface may act on. Settlement is not a safe completion signal on
its own (live/143 refuted that with Millonarios–Cali) and neither is this; the
question it answers is the narrower and honest one, *"can we still back the live
claim we are making?"*.

WHY VALUE MOVEMENT AND NOT WRITE-AGE
------------------------------------
The obvious rule is "our own write is stale". Measured on production
2026-09-11 08:16Z across every ``status='live' AND completed_at IS NULL`` row
(n=22), minutes since the freshest ``win_probability_sources[*].updated_at``:

    7.7 min   13 events
    4.6 min    1
    0.4 min    1
    no sources at all   7

The polls are writing **on schedule**, and they write the same value for a
decided row as for a contested one. Every judgeable row is inside one poll
cycle, so no threshold on write-age has a cut point. A rule built on it ships
inert.

Value movement partitions the same 22 rows with no overlap at all — not a
threshold that wants tuning, a partition:

    A  flat     9 events   distinct values = 1   (8 of the 9 at exactly 0.01/0.99)
    B  moving   3 events   distinct values = 2 / 5 / 35
    C  no series 10 events

WHY THE FLOOR IS STATED IN OBSERVATIONS, NEVER IN ROWS
------------------------------------------------------
This is the part that is easy to get backwards, and a row-count floor was
measured to fire on **zero** of the target rows.

``app/tasks/snapshots.py`` does not write a row when the value is unchanged — it
bumps ``reading_count`` on the existing one. So a flat series' ROW COUNT is
manufactured by how often the poll reaches the event, not by how flat it is. And
the flat cohort is reached *less*: every member has zero open linked markets, so
the live poll has nothing to price. Measured 2026-09-11 13:10Z, cohort A
averaged 10.8 rows/2h against cohort B's 73.3 — a 7x gap in the wrong direction.

The floor and the target population are anti-correlated **through the same
cause**, so no value of N in rows works. ``N >= 25 rows`` passed 0 of 13 flat
events while ``readings >= 10 AND span >= 60min`` passed 13 of 13, thinnest real
member 13 readings over 66.3 minutes.

``SUM(reading_count)`` is how many times we LOOKED, which dedup preserves. The
codebase already had the idiom (``census_overlap_trading.py``); this is the
second caller.
"""

from __future__ import annotations

#: The slowest cadence at which the live poll has been measured to REACH one of
#: these events — 11.9 min/observation on the firing population, 2026-09-12
#: 00:40Z; live/146 measured ~8 min on 2026-09-11. Not a tuning knob: it is the
#: number the two floors below have to stay consistent with, and
#: ``test_the_two_floors_are_mutually_satisfiable`` is what enforces that.
SLOWEST_MEASURED_CADENCE_SECONDS = 12 * 60

#: How many *observations* — not rows — a series must carry before its flatness
#: means anything. ``SUM(reading_count)``.
#:
#: Deliberately NOT stated in rows: see the module docstring. The rejected
#: alternative was ``>= 25 rows``, which passed 0 of 13 flat events nine hours
#: after it was honestly measured at 24-25 rows each.
#:
#: WHY 5 AND NOT 10, which is what the derivation on the issue arrived at.
#: 10 was measured against a cohort carrying 13-27 observations per 2h. Measured
#: again on the firing population 2026-09-12 00:40Z, the same cohort carries
#: exactly **10** — the poll now reaches these events every 11.9 minutes, so ten
#: observations take 119 minutes to accumulate.
#:
#: That makes 10 quietly incoherent with the 60-minute span floor beside it: at
#: the measured cadence a 60-minute flat stretch produces ~5 observations, so
#: nothing could ever satisfy both and the span floor was decorative — the
#: observation floor was doing all the work, AS A CADENCE PROXY. Which is the
#: exact defect that disqualified the row floor, one level up and harder to see.
#: It was also one slower pass away from inert: at 13 min/observation the count
#: cannot reach 10 inside a 2-hour window at all, and the rule stops firing on
#: everything, permanently and silently.
#:
#: 5 is what the span floor can actually deliver at the slowest measured cadence.
#: Its job is only to reject a series we barely looked at; the span floor is the
#: substantive test. Measured both ways on the same 44-row live population: 5 and
#: 10 both fire on the same 10 events today, so this buys headroom, not reach.
MIN_OBSERVATIONS = 5

#: How long the series must have been flat FOR. Guards against calling a match
#: pinned during a genuine lull, and against a series that has only just started.
#:
#: 60 minutes against a measured thinnest real member of 66.3. A shorter span
#: starts admitting cohort B's quiet stretches; a longer one starts excluding
#: real members of cohort A.
MIN_SPAN_SECONDS = 60 * 60

#: Distinct probability values that count as "has not moved". Exactly one.
#:
#: Not "a small range" — the measured partition is on *count*, and the flat
#: cohort produces literally one value. Checked for micro-wiggle before choosing
#: it: ``COUNT(DISTINCT ROUND(p, 3))`` equals ``COUNT(DISTINCT p)`` on every row
#: of the flat cohort, and the dedup that creates rows compares at full
#: ``Numeric(5,4)`` precision, so a 4th-decimal wiggle would have created rows
#: and shown up here. It does not exist in this population.
_PINNED_DISTINCT_VALUES = 1


def probability_series_is_pinned(
    *,
    distinct_values: int,
    total_observations: int,
    span_seconds: float,
) -> bool:
    """True iff a win-probability series has not moved, long enough to mean it.

    Pure. All three arguments are aggregates over one event's
    ``win_prob_snapshots`` inside a caller-chosen window.

    ``distinct_values`` of 0 (cohort C — no series at all) is NOT pinned. That
    population is real and persistent but it is a different defect (#5158): an
    absent series is silence, and silence is not evidence the game is over.
    """
    if distinct_values != _PINNED_DISTINCT_VALUES:
        return False
    if total_observations < MIN_OBSERVATIONS:
        return False
    return span_seconds >= MIN_SPAN_SECONDS


def a_score_is_evidence_of_play(home_score, away_score) -> bool:
    """Is there a score on this row, and therefore a game visibly in progress?

    CERT-2669's BLOCK, and it is right. #5077 is "live, **with no score**, and the
    number has not moved" from its title down: every specimen ever filed on it
    carries `home_score` and `away_score` NULL, and the issue's own framing calls
    the absence of any score the second half of the defect. The predicate shipped
    without the term, so a live 1-0 event whose price happened to be pinned got
    the signal — measured on production 2026-09-12 01:40Z, **4 of 40** live
    anchorless rows carry a score, so this was a live population and not a
    hypothetical.

    A score is a positive signal that something is being played and reported, and
    it outranks a flat price: a genuine 1-0 grind with a market that has stopped
    moving is a quiet market, not an unbacked live claim. EITHER side being
    non-null is enough — a half-populated score is still a report of play, and
    requiring both would let a 1-`NULL` row through on the same reasoning this
    exists to refuse.

    0-0 is a score. It is `0`, not `None`, and the distinction is the whole point:
    `None` means nothing ever wrote one.
    """
    return home_score is not None or away_score is not None


def league_may_be_judged_by_flatness(
    *,
    league_has_espn_anchors: bool | None,
    event_has_espn_anchor: bool,
) -> bool:
    """May the flatness rule speak about an event in this league at all?

    Fable-5's ruling on #5077 (2026-09-11 18:13Z) scoped the rule to *leagues
    with no ESPN anchor coverage*, and the scoping is the load-bearing half.

    Two separate refusals, and they are not the same test:

    ``event_has_espn_anchor`` — if this row has an anchor, an authority can
    speak for it and a heuristic does not get to. Row-level.

    ``league_has_espn_anchors`` — the real discriminator. Anchorlessness on its
    own is a CONSTANT in the target cohort (112 of 112 live anchorless rows on
    2026-09-11), so it separates nothing; and aimed at a league where anchors
    normally exist it is actively harmful. In MLB, 66% ESPN-anchored, an
    anchorless live row is usually the ghost half of a twin (#2057 / #3622 /
    #5277) whose anchored copy is already correct — "resolving" it would mint a
    wrong final on the wrong row. MLB is out of scope for that reason, by this
    test and not by name.

    ``None`` means the caller could not determine coverage. That is a refusal,
    not a default: an unbacked live claim is a smaller defect than a wrong one.
    """
    if event_has_espn_anchor:
        return False
    if league_has_espn_anchors is None:
        return False
    return not league_has_espn_anchors
