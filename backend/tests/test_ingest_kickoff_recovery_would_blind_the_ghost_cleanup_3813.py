"""An ingest-side kick-off recovery must never silently blind the ghost cleanup (#3813).

**SHIP this guards: a Segunda fixture that Kalshi lists three hours late stops
being a second card — and does not stop being one by becoming invisible to the
task that clears it.** (Pillar: MATCHING.)

──────────────────────────────────────────────────────────────────────────────
WHY THIS FILE EXISTS — A FIX THAT WAS RECORDED, AND MUST NOT BE BUILT AS WRITTEN
──────────────────────────────────────────────────────────────────────────────
lane1/328 recorded on #3813 (comment 5669098649) that the smallest safe upstream
fix for the +3h Kalshi soccer ghost was to run
``kalshi_occurrence_start.recover_kalshi_occurrence_starts`` — which already
recovers the real kick-off, is tested, and is idempotent — on the INGEST path,
so the row is minted at the fixture's real instant instead of at Kalshi's
expected-expiration instant.

Two code facts, both established by reading and the second reproduced by this
file, say that fix is wrong as recorded:

1. **It cannot prevent the CREATE.** The record's stated mechanism was that the
   matcher compares the wrong instants. It never compares them at all:
   ``event_registry._find_existing`` gates Step 3 on
   ``identity.claim.schedule_derived`` (ruling 048) and the Kalshi auto-create
   claim in ``prediction_market_matching`` sets that ``False`` deliberately and
   at length. The structured match is UNREACHABLE on that path, so the row's
   commence_time plays no part in whether a second row is minted. Correcting it
   "before the structured match" corrects an input to a comparison that does not
   happen.

2. **It would switch off the cleanup that handles these rows today.** That is
   what this file pins. ``soccer_ghost_twins.classify_block`` pairs a ghost to
   its canonical only when the ghost sits STRICTLY LATER:

       timedelta(0) < ghost.commence_time - canonical.commence_time <= MAX_GHOST_LAG

   The +3h offset is therefore not only the defect — it is the entire signal the
   cleanup keys on. Recover the kick-off at ingest and the lag collapses to zero
   (or to minus one minute, against an Odds-API canonical carrying the usual
   minute of jitter), the predicate is false, and authority's #5896 / #6177
   sweep stops seeing the family it was built for.

Measured on the seven pairs lane1/328 pinned against ESPN before reading any of
our rows (``artifacts-lane1-328/PIN-expected-fixture-set-1845Z.md``):
**7 of 7 are pairable today; 1 of 7 survives the recovery.**

──────────────────────────────────────────────────────────────────────────────
WHAT THIS FILE IS NOT
──────────────────────────────────────────────────────────────────────────────
🔴 **It does not assert that the +3h offset is correct, and it is not a vote to
keep it.** The stored time is wrong and a reader on a surface that does not call
the serve-time recovery is shown a kick-off three hours late. This file asserts
only the COUPLING: that the cleanup's reach depends on the stored offset, so the
two must move together or not at all.

So the expected failure mode is deliberate. A future ship that recovers the
kick-off at ingest SHOULD redden these tests, and when it does the answer is not
to relax them: it is to widen the pairing predicate in the same change — pairing
on ``abs(lag) <= _SAME_FIXTURE_MAX_SEPARATION`` for the same-instant case, the
way ``event_registry`` already separates a twin from a doubleheader — and then
to rewrite these expectations to the new contract. The failure is the point: it
converts a silent loss of cleanup reach into a red test that names its own
remedy.

``soccer_ghost_twins.py`` is AUTHORITY's module (#5896 / #6177) and nothing here
edits it. This is a new test file — "Green" under the Parallel Work Protocol —
and the widening above is authority's call to make, not lane1's.

Refs #3813, #5896, #5905, #6177. Ruling 048 / gotcha #32 unchanged.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.utils.kalshi_occurrence_start import KALSHI_EXPECTED_EXPIRATION_PAD
from app.utils.soccer_ghost_twins import (
    MAX_GHOST_LAG,
    NOT_A_TWIN,
    REFUSE_AMBIGUOUS,
    SoccerRow,
    classify_block,
)

#: Far from every fixture below, so :data:`soccer_ghost_twins.GHOST_KICKOFF_GRACE`
#: — the "it has only just kicked off" exemption — is never what decides a case
#: here. The clock must not be a hidden variable in a test about an offset.
NOW = datetime(2026, 9, 14, 19, 0, tzinfo=timezone.utc)

#: The seven Segunda pairs of 2026-09-12/13, as lane1/328 measured them: the
#: canonical's real kick-off (Odds API, ``external_id`` set, minute jitter and
#: all) against the instant Kalshi's row was actually stored at.
#:
#: The jitter is copied deliberately rather than rounded. 16:29 and 19:01 are
#: what makes the post-recovery lag NEGATIVE rather than zero, and a test that
#: tidied them to 16:30/19:00 would show a boundary case where production has an
#: unambiguous one.
MEASURED_PAIRS = [
    # (fixture, canonical kick-off, instant the Kalshi row was stored at)
    ("Andorra CF", "12:00", "15:00"),
    ("Granada CF", "16:29", "19:30"),
    ("Girona FC", "16:30", "19:30"),
    ("Cordoba CF", "19:01", "22:00"),
    ("Sporting Gijon", "12:01", "15:00"),
    ("Mallorca", "16:30", "19:30"),
    ("Tenerife", "19:01", "22:00"),
]


def _at(hhmm: str) -> datetime:
    hour, minute = (int(part) for part in hhmm.split(":"))
    return datetime(2026, 9, 12, hour, minute, tzinfo=timezone.utc)


def _canonical(commence: datetime, fixture: str) -> SoccerRow:
    """The row a schedule provider anchored: played, scored, fixture-anchored."""
    return SoccerRow(
        event_id=1,
        sport_key="soccer_spain_segunda",
        home_team_name=fixture,
        away_team_name="Opponent",
        commence_time=commence,
        status="completed",
        has_final_score=True,
        is_fixture_anchored=True,
    )


def _ghost(commence: datetime, fixture: str) -> SoccerRow:
    """The row Kalshi minted: still scheduled, no score, nothing anchoring it."""
    return SoccerRow(
        event_id=2,
        sport_key="soccer_spain_segunda",
        home_team_name=fixture,
        away_team_name="Opponent",
        commence_time=commence,
        status="scheduled",
        has_final_score=False,
        is_fixture_anchored=False,
    )


def _pairs(canonical_at: str, ghost_at: datetime, fixture: str) -> bool:
    """Does the cleanup get to act on this block at all?"""
    outcome, _tag, _why = classify_block(
        [_canonical(_at(canonical_at), fixture), _ghost(ghost_at, fixture)],
        now=NOW,
    )
    return outcome not in (NOT_A_TWIN, REFUSE_AMBIGUOUS)


@pytest.mark.parametrize("fixture,canonical_at,stored_at", MEASURED_PAIRS)
def test_the_stored_three_hour_offset_is_what_makes_the_pair_visible_today(
    fixture, canonical_at, stored_at
):
    """All seven measured pairs are actionable by the cleanup as they sit now.

    This is the control for the test below. Without it, "the recovery loses the
    pair" would be unfalsifiable — a block the cleanup could never act on in the
    first place also cannot be blinded, and the assertion would pass vacuously.
    """
    assert _pairs(canonical_at, _at(stored_at), fixture) is True


@pytest.mark.parametrize("fixture,canonical_at,stored_at", MEASURED_PAIRS)
def test_recovering_the_kickoff_at_ingest_would_cost_the_cleanup_the_pair(
    fixture, canonical_at, stored_at
):
    """Mint the row at its real kick-off and six of seven stop being pairable.

    Granada is the one survivor, and only by an accident of jitter: its canonical
    sits at 16:29 against a recovered 16:30, so the lag is +1 minute — still
    strictly positive, so still a pair. It is not a counter-example to the
    finding; it is the measure of how thin the margin is. One minute of
    disagreement between two writers is the whole reason the family is still
    reachable at all after a recovery, and nothing guarantees the next
    provider's minute falls that way.

    See this module's docstring before "fixing" a red here: the remedy is to
    widen the pairing predicate in the same change, not to soften this test.
    """
    recovered = _at(stored_at) - KALSHI_EXPECTED_EXPIRATION_PAD
    survives = fixture == "Granada CF"
    assert _pairs(canonical_at, recovered, fixture) is survives


def test_six_of_the_seven_measured_pairs_are_lost_counted_as_a_whole():
    """The headline, asserted as a count rather than only row by row.

    The parametrized tests above would still read green if the population
    shrank to one lucky row, so the aggregate is stated on its own: this is the
    number that decides whether the recorded fix is safe to build.
    """
    before = sum(
        _pairs(canonical_at, _at(stored_at), fixture)
        for fixture, canonical_at, stored_at in MEASURED_PAIRS
    )
    after = sum(
        _pairs(canonical_at, _at(stored_at) - KALSHI_EXPECTED_EXPIRATION_PAD, fixture)
        for fixture, canonical_at, stored_at in MEASURED_PAIRS
    )
    assert (before, after) == (7, 1)


def test_the_pairing_predicate_needs_a_strictly_positive_lag():
    """The mechanism behind the count above, isolated from the measured data.

    ``classify_block``'s pairing test opens at ``timedelta(0) <``, so a ghost
    sharing its canonical's instant — which is exactly what a successful
    kick-off recovery produces — is not a pair, while the same ghost one second
    later is. Pinned directly so a reader of this file does not have to take the
    seven-row count on trust, and so a change to that boundary is caught here
    with its reason attached rather than only as an arithmetic surprise.
    """
    kickoff = _at("19:00")
    assert _pairs("19:00", kickoff, "Boundary FC") is False
    assert _pairs("19:00", kickoff + timedelta(seconds=1), "Boundary FC") is True
    assert _pairs("19:00", kickoff - timedelta(minutes=1), "Boundary FC") is False


def test_a_ghost_beyond_the_lag_ceiling_is_not_pairable_either():
    """The other end of the same window, so the guard is not one-sided.

    A guard that only ever asserts the near edge cannot tell "the predicate is a
    window" from "the predicate is a floor" (gotcha: a one-directional guard
    leaves the reverse population live). The recovery moves rows toward zero, so
    the floor is the edge that matters for #3813 — but pinning both is what
    makes this a description of the predicate rather than of one defect.
    """
    kickoff = _at("19:00")
    assert _pairs("19:00", kickoff + MAX_GHOST_LAG, "Ceiling FC") is True
    assert _pairs("19:00", kickoff + MAX_GHOST_LAG + timedelta(minutes=1), "Ceiling FC") is False
