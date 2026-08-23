"""#2071 — a statistic that SATURATES must be reported as CENSORED, not as a value.

Ruling 110's falsifier excluded two of its seven watched beats as "censored at
their 600 s soft limit with ZERO successes in 24 h ... already failing before
the move". LAT-P078 read both from production on 2026-08-21 at a 15.6 h horizon
and found **one of those two factual claims false and the other true with the
wrong mechanism attached**:

* `precompute_backfill_winners_status` — "zero successes in 24 h" is **FALSE**:
  18 successes, 2 failures. Its durations span two and a half orders of
  magnitude (1 run in 10-100 s, 20 in 100-500 s, 22 in 500-598 s, **7 of 50 —
  14 % — at or over the 598 s ceiling**), p50 518.4 s. It carries exactly the
  signal the falsifier wants and was thrown away anyway.
* `compute_calibration_prices` — 0 successes in 24 h is true and is **by
  design**: `_compute_calibration_prices` sets its own `_CAL_DEADLINE_S = 540.0`
  ("soft_time_limit=600, keep a 60 s margin"), is a cursor-resuming bounded
  sweep, and returns `partial`, which `task_verdict` documents as *not a
  failure*. Its cursor advances monotonically. 35 of 40 runs stop on the 540 s
  clock the task owns; only 3 of 40 ever reach 600 s.

🔴 **THE ARITHMETIC THAT MAKES THE OLD RULE WRONG.** `CENSOR_FRACTION_OF_SOFT_
LIMIT = 0.98` was applied to **p95**. A distribution with a 14 % clip rate has a
p95 at the ceiling *by arithmetic, whatever the other 86 % do* — any clip rate
above 5 % saturates a p95. The rule therefore discarded a beat on the strength
of the 7 runs it cannot read while ignoring the 43 it can.

🔴 **AND THE MIRROR, WHICH #2071 DID NOT NAME AND THIS FILE DOES.** The rule was
applied to the BASELINE only. Nothing censored the OBSERVATION. So a beat whose
post-move p50 has newly pinned at its clamp — every run now hitting the ceiling,
the worst outcome the falsifier exists to catch — graded
``600.0 / 518.4 = 1.16x``, under the 1.25x threshold, and returned **HOLD**. A
saturated instrument read as evidence of safety, which is the exact shape
ruling 110's three-valued design exists to refuse.

**THE FIX IS ONE IDEA, NOT TWO PATCHES: censor the STATISTIC, not the beat.**
A percentile that sits at a clamp is not a number, it is a bound, and it is
returned as a `Reading` whose `for_grading()` is `None`. A beat is excluded only
when the statistic actually used to grade it (the p50) is the censored one — so
`precompute_backfill_winners_status` becomes gradeable with its p95 reported as
CENSORED beside it, and an observation that pins can no longer produce a HOLD.

**AND THE CLAMP IS THE EFFECTIVE ONE, NOT THE CONFIGURED ONE.** That is #2071's
"true with the wrong mechanism attached", made executable: `calibration_prices`
is clamped at the 540 s budget it sets for itself, not at the 600 s soft limit,
so it is censored at 540 and stays excluded — for its own stated reason.

Zero new measurement was needed for any of this. Every clip-rate fact below is
DERIVED from numbers already pinned in `PRE_MOVE_BASELINE` (see
`test_five_baselines_have_provably_zero_clipping`), which matters because the
pre-move rings have long since rolled and the baseline is, correctly, never
recomputed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.utils.heavy_routing_falsifier import (
    BASELINE_BY_TASK,
    CENSOR_FRACTION_OF_SOFT_LIMIT,
    DEGRADE_P50_RATIO,
    PRE_MOVE_BASELINE,
    ROUTING_CHANGE_AT_EPOCH,
    RUN_COUNTER_WINDOW_S,
    Reading,
    grade_beat,
    grade_move,
)

AT_HORIZON = ROUTING_CHANGE_AT_EPOCH + RUN_COUNTER_WINDOW_S + 3600

BACKFILL_WINNERS = "app.tasks.precompute_backfill_winners_status"
CAL_PRICES = "app.tasks.compute_calibration_prices"


def _obs(p50_s: float, *, runs: int = 20, n: int = 20, spread: list[float] | None = None):
    """An observation whose post-move median is `p50_s`, fully post-move.

    Every sample is stamped after the routing change, so the horizon gate opens
    and the verdict under test is about censoring and nothing else.
    """
    durations = spread if spread is not None else [p50_s * 1000] * n
    return {
        "recent_durations_ms": durations,
        "recent_durations_at": [ROUTING_CHANGE_AT_EPOCH + 60.0] * len(durations),
        "successes_24h": runs,
        "failures_24h": 0,
    }


def _all_holding():
    return {b.metrics_name: _obs(b.p50_s) for b in PRE_MOVE_BASELINE}


# ---------------------------------------------------------------------------
# THE HEADLINE — coverage was understated, and by how much.
# ---------------------------------------------------------------------------


def test_the_backfill_winners_beat_is_no_longer_thrown_away_by_a_saturated_p95():
    """Its p50 is 518.4 s against a 600 s clamp. It is readable; read it.

    Excluding it discarded 43 readable runs on the strength of 7 unreadable
    ones — and did so on the statistic (`p95`) that a 14 % clip rate pins by
    arithmetic no matter what the rest of the distribution does.
    """
    beat = BASELINE_BY_TASK[BACKFILL_WINNERS]

    assert beat.p95.censored, "its p95 IS at the clamp — that fact does not go away"
    assert not beat.p50.censored, "...but its p50 is 86% of the clamp and readable"
    assert not beat.censored, "so the BEAT is gradeable"

    v = grade_beat(beat, _obs(beat.p50_s), age_since_move_s=RUN_COUNTER_WINDOW_S * 2)
    assert v.verdict == "hold", v.reason


def test_effective_coverage_is_four_of_seven_not_three():
    """#2071's 'Consequence for ruling 110's guarantee', as a number.

    Reconstructed from the PRODUCTION shape, not from an all-holding fixture:
    two of the seven carry zero runs in the pinned baseline
    (`compute_time_horizon_calibration`, `snapshot_coverage_metrics`) and
    correctly grade `no_new_runs`, which is why the ruling's own count was 3 of
    7 rather than 5. An all-holding fixture would silently give every beat runs
    it does not have and make this assertion pass for the wrong reason.
    """
    obs = {
        b.metrics_name: _obs(b.p50_s, runs=b.successes_24h + b.failures_24h)
        for b in PRE_MOVE_BASELINE
    }
    result = grade_move(obs, now_epoch=AT_HORIZON)
    by_verdict: dict[str, list[str]] = {}
    for b in result.beats:
        by_verdict.setdefault(b.verdict, []).append(b.task)

    assert len(by_verdict.get("hold", [])) == 4, by_verdict
    assert by_verdict.get("censored") == [CAL_PRICES], by_verdict
    assert len(by_verdict.get("no_new_runs", [])) == 2, by_verdict
    assert BACKFILL_WINNERS in by_verdict["hold"], (
        "the beat #2071 is about must be one of the four"
    )
    assert result.verdict == "HOLD"


def test_calibration_prices_is_still_excluded_but_for_its_OWN_budget():
    """True claim, wrong mechanism — now the right one.

    Ruling 110 said it is clamped at its 600 s timeout. It is not: it stops on
    the 540 s deadline it sets for itself and returns `partial`. The reason
    string has to say so, because the distinction is load-bearing — a
    budget-bounded beat WOULD show contention, just not in `duration`.
    """
    beat = BASELINE_BY_TASK[CAL_PRICES]

    assert beat.effective_clamp_s == 540.0
    assert beat.effective_clamp_s < beat.soft_time_limit_s
    assert beat.censored, "p50 538.2s is pinned against its own 540s budget"

    v = grade_beat(beat, _obs(beat.p50_s), age_since_move_s=RUN_COUNTER_WINDOW_S * 2)
    assert v.verdict == "censored"
    assert "540" in v.reason
    assert "budget" in v.reason.lower(), v.reason


def test_the_budget_deadline_this_baseline_pins_still_reads_540_in_the_task():
    """A pinned constant that drifts is a baseline quietly grading the wrong thing.

    Same discipline as `test_baseline_soft_limits_match_the_configured_tasks`,
    reached by source because `_CAL_DEADLINE_S` is a function-local and cannot
    be imported.
    """
    src = (
        Path(__file__).resolve().parents[1] / "app" / "tasks" / "backfill_winners.py"
    ).read_text()
    assert "_CAL_DEADLINE_S = 540.0" in src, (
        "compute_calibration_prices' self-imposed budget moved; "
        "`effective_clamp_s` in heavy_routing_falsifier.py must move with it"
    )


# ---------------------------------------------------------------------------
# 🔴 THE MIRROR: a censored OBSERVATION used to grade as a pass.
# ---------------------------------------------------------------------------


def test_an_observation_pinned_at_the_clamp_cannot_grade_as_HOLD():
    """The worst thing the falsifier exists to catch, previously read as safe.

    `precompute_backfill_winners_status` at a post-move p50 of 600 s means every
    run now hits the ceiling. Against a 518.4 s baseline that is a ratio of
    1.157 — under the 1.25x threshold — so the old code returned HOLD on a beat
    that had completely saturated.
    """
    beat = BASELINE_BY_TASK[BACKFILL_WINNERS]
    pinned = beat.effective_clamp_s

    # the arithmetic that made this a pass, stated so the test cannot drift
    assert pinned / beat.p50_s < DEGRADE_P50_RATIO

    v = grade_beat(beat, _obs(pinned), age_since_move_s=RUN_COUNTER_WINDOW_S * 2)
    assert v.verdict == "censored", v.reason
    assert v.verdict != "hold"
    assert v.censored_side == "observation"


def test_that_same_pinned_observation_also_cannot_fire_a_spurious_REVERT():
    """Symmetry with the horizon gate, which this file inherits deliberately.

    `grade_beat`'s docstring: a gate that refuses to certify safety must equally
    refuse to revoke the grant on a reading it cannot see. An unobservable
    statistic is not evidence in either direction.
    """
    beat = BASELINE_BY_TASK[BACKFILL_WINNERS]
    v = grade_beat(
        beat,
        _obs(beat.effective_clamp_s * 5),  # catastrophic, and still unreadable
        age_since_move_s=RUN_COUNTER_WINDOW_S * 2,
    )
    assert v.verdict == "censored"
    assert v.verdict != "degraded"


def test_a_newly_censored_observation_is_NAMED_in_the_move_reason():
    """It is the one censored state that is evidence of something.

    A baseline that was always censored tells a reader nothing new. A beat that
    was readable before the move and is pinned after it is the loudest fact on
    the panel, and burying it in a per-beat reason would make INCONCLUSIVE look
    like an ordinary quiet night.
    """
    obs = _all_holding()
    beat = BASELINE_BY_TASK[BACKFILL_WINNERS]
    obs[beat.metrics_name] = _obs(beat.effective_clamp_s)

    result = grade_move(obs, now_epoch=AT_HORIZON)
    assert "precompute_backfill_winners_status" in result.reason
    assert "SATURATED" in result.reason, result.reason


def test_an_all_saturated_read_is_INCONCLUSIVE_and_says_it_is_not_a_pass():
    obs = {b.metrics_name: _obs(b.effective_clamp_s) for b in PRE_MOVE_BASELINE}
    result = grade_move(obs, now_epoch=AT_HORIZON)

    assert result.verdict == "INCONCLUSIVE"
    assert result.verdict != "HOLD"
    assert "NOT evidence" in result.reason


# ---------------------------------------------------------------------------
# The reporting shape itself: a censored reading is not a number.
# ---------------------------------------------------------------------------


def test_a_censored_reading_refuses_to_hand_back_a_gradeable_value():
    """The whole directive, in one assertion.

    `seconds` is still there — a reader wants to know the bound — but the value
    used for grading is `None`, so a censored read cannot be compared into a
    pass or a fail by a caller who did not think about it.
    """
    censored = Reading(seconds=601.0, clamp_s=600.0, quantile=0.95, label="p95")
    observed = Reading(seconds=518.4, clamp_s=600.0, quantile=0.5, label="p50")

    assert censored.censored is True
    assert censored.state == "censored"
    assert censored.for_grading() is None
    assert censored.seconds == 601.0  # the bound is still reported

    assert observed.censored is False
    assert observed.state == "observed"
    assert observed.for_grading() == 518.4


def test_a_reading_cannot_be_ordered_against_a_number_by_accident():
    """No `__lt__`, no `__float__`. The type must not silently coerce.

    A `Reading` that compared like a float would be a censored value grading as
    a pass with extra steps.
    """
    r = Reading(seconds=601.0, clamp_s=600.0, quantile=0.95, label="p95")
    with pytest.raises(TypeError):
        _ = r < 700.0
    with pytest.raises(TypeError):
        _ = float(r)


def test_the_clip_rate_a_saturated_percentile_IMPLIES_is_arithmetic_not_measured():
    """`1 - quantile` is the whole derivation, and it is a LOWER bound.

    A p95 at the clamp proves >= 5 % of runs are clipped and nothing more; a p50
    at the clamp proves >= 50 %. Reporting either as "the clip rate" would be
    inventing precision the percentile does not carry.
    """
    p95_pinned = Reading(seconds=601.0, clamp_s=600.0, quantile=0.95, label="p95")
    p50_pinned = Reading(seconds=601.0, clamp_s=600.0, quantile=0.5, label="p50")
    free = Reading(seconds=100.0, clamp_s=600.0, quantile=0.95, label="p95")

    assert p95_pinned.implied_min_clip_rate == pytest.approx(0.05)
    assert p50_pinned.implied_min_clip_rate == pytest.approx(0.50)
    assert free.implied_min_clip_rate == 0.0


def test_five_baselines_have_provably_zero_clipping_from_pinned_numbers_alone():
    """No re-measurement was possible and none was needed.

    `max_s` below the censor threshold proves the clip rate is EXACTLY zero. The
    pre-move rings rolled weeks ago and the baseline is deliberately never
    recomputed, so a rule that needed a fresh clip-rate read could not have been
    applied to the pinned set at all.
    """
    zero_clip = [
        b.task
        for b in PRE_MOVE_BASELINE
        if b.max_s < CENSOR_FRACTION_OF_SOFT_LIMIT * b.effective_clamp_s
    ]
    assert len(zero_clip) == 5
    assert CAL_PRICES not in zero_clip
    assert BACKFILL_WINNERS not in zero_clip


def test_the_observed_clip_rate_IS_measured_exactly_because_the_ring_is_there():
    """The asymmetry, on purpose: bounds for the baseline, a count for the ring.

    The observation carries every sample, so the clip rate is a count and not a
    bound. Reporting it as a bound would be throwing away data we hold.
    """
    beat = BASELINE_BY_TASK[BACKFILL_WINNERS]
    clamp_ms = beat.effective_clamp_s * 1000
    spread = [100_000.0] * 8 + [clamp_ms] * 2  # 20% clipped, p50 far below

    v = grade_beat(beat, _obs(0, spread=spread), age_since_move_s=RUN_COUNTER_WINDOW_S * 2)
    assert v.verdict == "hold", v.reason
    assert v.observed_clip_rate == pytest.approx(0.2)


# ---------------------------------------------------------------------------
# ...and the new rule must not be a tautology in either direction.
# ---------------------------------------------------------------------------


def test_the_censoring_rule_still_lets_a_real_degradation_through():
    """A gate that could not go red is the defect LAT-P079 minted and caught."""
    obs = _all_holding()
    victim = BASELINE_BY_TASK["app.tasks.precompute_source_intelligence"]
    obs[victim.metrics_name] = _obs(victim.p50_s * (DEGRADE_P50_RATIO + 0.5))

    assert grade_move(obs, now_epoch=AT_HORIZON).verdict == "REVERT"


def test_the_censoring_rule_still_lets_a_clean_run_go_green():
    """...and the mirror: it must demonstrably OPEN, not merely refuse."""
    assert grade_move(_all_holding(), now_epoch=AT_HORIZON).verdict == "HOLD"


def test_a_beat_just_below_its_clamp_grades_rather_than_censoring():
    """The boundary is not inverted, tested from the readable side."""
    beat = BASELINE_BY_TASK[BACKFILL_WINNERS]
    threshold = CENSOR_FRACTION_OF_SOFT_LIMIT * beat.effective_clamp_s

    under = grade_beat(beat, _obs(threshold - 1.0), age_since_move_s=RUN_COUNTER_WINDOW_S * 2)
    over = grade_beat(beat, _obs(threshold + 1.0), age_since_move_s=RUN_COUNTER_WINDOW_S * 2)

    assert under.verdict != "censored"
    assert over.verdict == "censored"


def test_every_baseline_carries_an_effective_clamp_at_or_under_its_soft_limit():
    """A clamp ABOVE the soft limit would censor nothing and read as a fix."""
    for beat in PRE_MOVE_BASELINE:
        assert 0 < beat.effective_clamp_s <= beat.soft_time_limit_s


def test_the_horizon_gate_still_runs_before_the_censoring_of_an_observation():
    """Ordering, because both gates return a non-grading verdict.

    A pre-horizon ring must report PRE_HORIZON, not `censored`: "too early to
    say" and "cannot be seen" are different facts and collapsing them would hide
    a horizon that is simply not reached yet (gotcha #53).
    """
    beat = BASELINE_BY_TASK[BACKFILL_WINNERS]
    obs = {
        "recent_durations_ms": [beat.effective_clamp_s * 1000] * 20,
        "recent_durations_at": [ROUTING_CHANGE_AT_EPOCH - 60.0] * 20,  # all PRE-move
        "successes_24h": 20,
        "failures_24h": 0,
    }
    v = grade_beat(beat, obs, age_since_move_s=600.0)
    assert v.verdict == "pre_horizon", v.reason
