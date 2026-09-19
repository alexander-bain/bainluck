"""#4976 — a pre-kickoff chart stops printing moves that no source made.

THE DEFECT, IN THE SHAPE PRODUCTION SERVED IT. Event 15313430 (Stearns v
Stephens), the served `aggregate_line` across one minute on 2026-09-16:

    18:08Z  0.360
    18:10Z  0.615      a 25.5pp move

and what the three sources were saying across that same minute:

    betting     0.6169   said 17:00Z, an hour earlier   — flat
    polymarket  0.6150   said 13:23Z, five hours earlier — flat
    kalshi      0.36 → 0.525                            — moved 16.5pp

Betting and polymarket had been decayed out of the pool, so the chart printed
kalshi ALONE as the blend and then printed the pool again two minutes later.
Nobody moved 25.5pp. The reader also got told so in words: the plunge crossed
the 50% line twice, and `OddsChart.tsx`'s `crossingCount` turned that into a
**"Odds flipped (2)"** chip on a match that had not started.

#1999 settled this for the hero — a pre-game event does not decay, because
before the start nothing is moving and a quote from this morning is still the
market's answer. #6461 put the chart on the hero's recency RULE but not on its
GATE. `pregame_boundary` + `pregame_until` close that gap.

THE STRAWMAN IS FIRST AND IT IS LOAD-BEARING. Every assertion below is also run
with `pregame_until=None`, where it must FAIL — otherwise the fixture is too
weak to have caught the bug it was written for and the guards are decoration.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.utils.aggregation import (
    TimestampedProb,
    compute_aggregated_probability,
    pregame_boundary,
)

KICK = datetime(2026, 9, 18, 0, 30, tzinfo=timezone.utc)


def _the_15313430_shape():
    """Two sources quoting slowly and one quoting fast, all pre-kickoff.

    Deliberately NOT the raw production rows: the defect needs only the cadence
    mismatch, and a fixture that carries 251 real points hides which property is
    doing the work. Betting and polymarket are FLAT for the whole window, so any
    blend point outside [0.36, 0.62] is arithmetic of ours, not news.
    """
    start = KICK - timedelta(hours=12)
    betting = [
        TimestampedProb(timestamp=start, home_probability=0.6169),
        TimestampedProb(timestamp=start + timedelta(hours=5), home_probability=0.6169),
    ]
    polymarket = [
        TimestampedProb(timestamp=start + timedelta(hours=1), home_probability=0.615),
    ]
    # The fast source, moving for real — 0.36 then 0.525, kalshi's actual step.
    kalshi = [
        TimestampedProb(
            timestamp=start + timedelta(hours=6, minutes=2 * i),
            home_probability=0.36 if i < 30 else 0.525,
        )
        for i in range(60)
    ]
    return {"betting": betting, "polymarket": polymarket, "kalshi": kalshi}


def _with_an_in_play_tail(sources):
    """Extend the fixture past kickoff SO THAT DECAY CHANGES THE ANSWER THERE.

    🔴 THE OBVIOUS VERSION OF THIS IS VACUOUS AND I SHIPPED IT FIRST. Appending
    one point of the same value to all three sources gives an in-play segment
    where every source is fresh and agrees, so the weighted median is that value
    whether decay runs or not — and a mutant that exempts EVERY bucket, in-play
    included, passed all fourteen tests. The in-play tail has to be a segment
    where the two rules disagree: kalshi quoting fast at 0.80 while betting and
    polymarket sit stale at 0.6169/0.615. Under the in-play rule the stale pair
    decays out and the line follows kalshi; under a wrongly-applied exemption
    they keep full weight and hold it down.
    """
    sources["kalshi"] += [
        TimestampedProb(
            timestamp=KICK + timedelta(minutes=2 * i), home_probability=0.80
        )
        for i in range(1, 25)
    ]
    return sources


def _biggest_step(series):
    if len(series) < 2:
        return 0.0
    return max(
        abs(b.home_probability - a.home_probability)
        for a, b in zip(series, series[1:])
    )


def _run(pregame_until):
    return compute_aggregated_probability(
        _the_15313430_shape(), bucket_seconds=60, pregame_until=pregame_until
    )


# ── The defect, and the strawman that proves the fixture can see it ──────────


def test_the_blend_stops_printing_a_move_no_source_made():
    """The largest step in the blend may not exceed the largest step any source
    actually made. 16.5pp is kalshi's real move; 25.5pp was ours."""
    biggest_source_move = 0.525 - 0.36
    served = _run(pregame_boundary("scheduled", KICK, KICK - timedelta(hours=3)))
    assert _biggest_step(served) <= biggest_source_move + 1e-9, (
        f"blend stepped {_biggest_step(served) * 100:.2f}pp where the biggest "
        f"source move was {biggest_source_move * 100:.2f}pp"
    )


def test_STRAWMAN_without_the_boundary_the_blend_does_print_it():
    """🔴 DO NOT 'FIX' THIS TEST. It is the red-first arm of the test above and
    the only thing standing between that assertion and vacuity: if the pre-game
    exemption is ever removed, or the fixture stops reproducing the cadence
    mismatch, this fails and says which."""
    biggest_source_move = 0.525 - 0.36
    unfixed = _run(None)
    assert _biggest_step(unfixed) > biggest_source_move + 1e-9, (
        "the fixture no longer reproduces #4976: with decay ON the blend's "
        f"largest step is {_biggest_step(unfixed) * 100:.2f}pp, within what the "
        "sources themselves did"
    )


def test_the_blend_never_leaves_the_range_its_sources_quoted():
    """Every source sits in [0.36, 0.6169]. A weighted median cannot truthfully
    land outside that, and before the fix the pre-kickoff line did."""
    served = _run(pregame_boundary("scheduled", KICK, KICK - timedelta(hours=3)))
    lo = min(p.home_probability for p in served)
    hi = max(p.home_probability for p in served)
    assert 0.36 - 1e-9 <= lo and hi <= 0.6169 + 1e-9, f"blend ranged [{lo}, {hi}]"


# ── The safety property: the record of the game itself is untouched ──────────


def test_an_in_play_bucket_is_bit_identical_to_the_unfixed_line():
    """MEASURED ON PRODUCTION BEFORE IT WAS ASSERTED HERE: 0 of 846 in-play
    points moved across five started events (live/355 — 15313146, 15313117,
    15312937, 15313390, 15313771). This is that property as a guard, because a
    fix to the pre-game segment that quietly redrew the GAME would be a far
    worse defect than the one it repairs."""
    sources = _with_an_in_play_tail(_the_15313430_shape())
    fixed = compute_aggregated_probability(
        sources, bucket_seconds=60, pregame_until=KICK
    )
    unfixed = compute_aggregated_probability(sources, bucket_seconds=60)
    fixed_inplay = {p.timestamp: p.home_probability for p in fixed if p.timestamp >= KICK}
    unfixed_inplay = {
        p.timestamp: p.home_probability for p in unfixed if p.timestamp >= KICK
    }
    assert fixed_inplay, "fixture produced no in-play buckets — the guard is vacuous"
    assert fixed_inplay == unfixed_inplay


def test_the_bucket_containing_kickoff_already_runs_the_in_play_rule():
    """The boundary is `limit <= pregame_epoch`, NOT `bucket_ts <=`.

    Those two differ on exactly one bucket — the one that STARTS at kickoff,
    whose `bucket_ts` equals the boundary but whose `limit` is a minute past it.
    Under `bucket_ts <=` that bucket is exempted and the first minute of every
    game is drawn under the pre-game rule.

    🔴 THE FIRST VERSION OF THIS TEST WAS VACUOUS AND A MUTANT PROVED IT: it
    looked for a bucket at `KICK`, found none (the fixture jumped from pre-match
    straight to KICK+2m), and passed on an `if straddling:` that never ran. So
    the kickoff-minute reading is now placed deliberately, its existence is
    asserted, and the two rules are made to disagree there — betting and
    polymarket are hours stale at ~0.615 while kalshi quotes 0.80 at the bell,
    so decay-on and decay-off cannot give the same answer.
    """
    sources = _with_an_in_play_tail(_the_15313430_shape())
    sources["kalshi"].append(TimestampedProb(timestamp=KICK, home_probability=0.80))
    sources["kalshi"].sort(key=lambda p: p.timestamp)

    fixed = compute_aggregated_probability(
        sources, bucket_seconds=60, pregame_until=KICK
    )
    unfixed = compute_aggregated_probability(sources, bucket_seconds=60)

    at_kick = [p for p in fixed if p.timestamp == KICK]
    assert at_kick, "no bucket starts at kickoff — this guard would be vacuous"
    baseline = [p for p in unfixed if p.timestamp == KICK]
    assert baseline
    assert at_kick[0].home_probability == baseline[0].home_probability, (
        "the bucket that starts at kickoff was exempted from decay: it belongs "
        "to the game, not to the pre-match segment"
    )


def test_the_last_bucket_that_ENDS_at_kickoff_is_still_pre_game():
    """The other side of the same `<=`, and a mutant to `<` survives without it.

    A bucket running KICK-60s → KICK lies entirely before the start, so it is
    pre-game and must be exempt. `limit <= pregame_epoch` says so; `limit <`
    would hand the last minute before the bell to the in-play rule. The two
    are made to disagree the same way as above: a kalshi quote of 0.80 one
    minute out against betting/polymarket hours stale at ~0.615.
    """
    sources = _the_15313430_shape()
    sources["kalshi"].append(
        TimestampedProb(timestamp=KICK - timedelta(seconds=60), home_probability=0.80)
    )
    last_pregame = KICK - timedelta(seconds=60)

    exempt = compute_aggregated_probability(
        sources, bucket_seconds=60, pregame_until=KICK
    )
    decayed = compute_aggregated_probability(sources, bucket_seconds=60)

    mine = [p for p in exempt if p.timestamp == last_pregame]
    theirs = [p for p in decayed if p.timestamp == last_pregame]
    assert mine and theirs, "no bucket ends exactly at kickoff — guard is vacuous"
    assert mine[0].home_probability != theirs[0].home_probability, (
        "the two rules agree on the last pre-kickoff minute, so this guard "
        "cannot tell them apart — strengthen the fixture, do not delete it"
    )
    # And the exempt answer is the one that keeps the stale pair in the pool.
    assert mine[0].home_probability < theirs[0].home_probability


def test_pregame_until_None_is_bit_for_bit_the_previous_behaviour():
    """The parameter defaults to `None` and every existing caller omits it, so
    this is the back-compatibility contract for `compute_aggregated_probability`'s
    other callers (the hero, calibration, the sentinels)."""
    sources = _the_15313430_shape()
    explicit_none = compute_aggregated_probability(
        sources, bucket_seconds=60, pregame_until=None
    )
    omitted = compute_aggregated_probability(sources, bucket_seconds=60)
    assert [(p.timestamp, p.home_probability) for p in explicit_none] == [
        (p.timestamp, p.home_probability) for p in omitted
    ]


# ── `pregame_boundary`'s truth table ─────────────────────────────────────────


@pytest.mark.parametrize(
    "status,expected_is_kickoff",
    [
        ("live", True),
        ("completed", True),
        ("suspended", True),
        ("closed", True),
        # `postponed` is NOT in `_PREGAME_STATUSES`, so it takes the started
        # branch and decays past a kickoff that never happened. Named here
        # because it is the case this ship does NOT repair — identical to the
        # hero, which is the bar.
        ("postponed", True),
    ],
)
def test_a_started_event_is_pregame_only_before_its_listed_kickoff(
    status, expected_is_kickoff
):
    assert pregame_boundary(status, KICK, KICK + timedelta(hours=3)) == KICK


def test_a_scheduled_event_is_pregame_all_the_way_to_now():
    """Including past a slipped `commence_time` — a delayed fixture sits at
    `scheduled` with a kickoff in the past, and the hero is not decaying it, so
    neither may the line."""
    now = KICK + timedelta(hours=2)
    assert pregame_boundary("scheduled", KICK, now) == now


def test_an_unknown_status_that_has_started_is_pregame_before_its_listed_kickoff():
    """An unreadable status on an event whose start HAS passed keeps the started
    branch: the buckets after kickoff decay, so the edge the hero renders is on
    the in-play rule and the two agree. This is the half of the old
    "deliberate divergence" that survived CERT-3112."""
    assert pregame_boundary(None, KICK, KICK + timedelta(hours=3)) == KICK


@pytest.mark.parametrize("status", [None, "", "   ", "postponed", "wat"])
def test_a_status_the_hero_decays_takes_NO_exemption_before_its_listed_start(status):
    """🔴 CERT-3112, and the reason this ship was blocked.

    The hero decays every status outside `_PREGAME_STATUSES`. While the listed
    start is still ahead of `now`, EVERY bucket drawn so far is "before the
    listed start" — so the started branch would exempt the newest bucket too and
    the chart's right edge would stop agreeing with the big number above it.
    `None` keeps the whole line on the in-play rule, which is what the hero is
    doing. The route-level proof that this is one number and not two lives in
    `test_pregame_hero_chart_lockstep_4976.py`.
    """
    now = KICK - timedelta(hours=1)  # kickoff has NOT arrived
    assert pregame_boundary(status, KICK, now) is None


def test_a_scheduled_event_before_its_start_still_exempts_everything():
    """The refusal above is keyed on the HERO's gate, not on the clock alone: a
    `scheduled` event is equally un-started, and there the hero is not decaying
    either, so the exemption is parity rather than a divergence."""
    now = KICK - timedelta(hours=1)
    # `max(commence_time, now)` — the boundary is kickoff, which is already
    # later than every bucket that exists, so the whole line is exempt.
    assert pregame_boundary("scheduled", KICK, now) == KICK


def test_no_commence_time_means_no_boundary():
    assert pregame_boundary("scheduled", None, KICK) is None
