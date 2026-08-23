"""Ruling 110: the scoped `heavy` exception and its armed falsifier (#1609, LAT-P077).

The routing change and the falsifier ship in ONE commit because Fable's grant
is conditional — a conditional grant whose condition is not executable is an
unconditional grant with a promise attached.

The load-bearing test in this file is
``test_falsifier_actually_fires_on_a_degraded_beat``. This program has a live
ruling about guards that can only pass: LAT-P075 found
``test_live_beat_interval_is_not_unsafe`` had been moved by an unrelated change
into a state where it could no longer red on the case it was written to catch.
A falsifier that cannot return REVERT is not a falsifier.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.utils.heavy_routing_falsifier import (
    BASELINE_BY_TASK,
    CALIBRATION_HEAVY_BEATS,
    DEGRADE_P50_RATIO,
    HEAVY_MOVE_EXCEPTION,
    METRICS_NAME,
    MOVER_PRE_MOVE,
    PRE_MOVE_BASELINE,
    READ_SET,
    ROUTING_CHANGE_AT_EPOCH,
    RUN_COUNTER_WINDOW_S,
    grade_beat,
    grade_move,
    post_move_runs_lower_bound,
    summarize_movers,
)

TASKS_SRC = Path(__file__).resolve().parents[1] / "app" / "tasks" / "__init__.py"

# Horizons, stated as OFFSETS from the pinned routing change and never from the
# wall clock. Gotcha #44: an anchor that reads `time.time()` makes the suite a
# function of the hour it runs in, and this program has paid for that four
# times. `grade_move` takes `now_epoch` keyword-only precisely so every test
# here has to say which horizon it means.
PRE_HORIZON = ROUTING_CHANGE_AT_EPOCH + 7 * 60  # LAT-P078's real 6m55s read
AT_HORIZON = ROUTING_CHANGE_AT_EPOCH + RUN_COUNTER_WINDOW_S + 3600  # 25h after


def _obs(p50_s: float, *, runs: int = 20, n: int = 20):
    """An observation whose median duration is exactly ``p50_s`` seconds.

    ``runs`` defaults to ``n`` so the default observation clears the horizon
    when read at ``AT_HORIZON``: a fixture that silently sat below the
    post-move share would make every downstream assertion pass for the wrong
    reason.
    """
    return {
        "recent_durations_ms": [p50_s * 1000] * n,
        "successes_24h": runs,
        "failures_24h": 0,
    }


def _all_holding():
    """Observations that reproduce every baseline exactly -> ratio 1.0."""
    return {b.metrics_name: _obs(b.p50_s) for b in PRE_MOVE_BASELINE}


# ---------------------------------------------------------------------------
# The exception's SHAPE: two tasks, by name, not a class
# ---------------------------------------------------------------------------


def test_exception_is_exactly_two_tasks_by_name():
    """Ruling 110 named two tasks. A third is a new ruling, not a new line."""
    assert HEAVY_MOVE_EXCEPTION == {
        "app.tasks.backfill_market_shapes",
        "app.tasks.precompute_backfill_progress",
    }


def test_exception_does_not_leak_onto_the_calibration_family():
    """The exception must not overlap the beats it is supposed to protect."""
    assert not (HEAVY_MOVE_EXCEPTION & CALIBRATION_HEAVY_BEATS)


def test_exception_is_not_a_prefix_rule():
    """Sibling backfills stay on background — the exception is not 'backfills'."""
    from app.tasks import _HEAVY_KEEP_ON_BACKGROUND

    assert not (HEAVY_MOVE_EXCEPTION & _HEAVY_KEEP_ON_BACKGROUND)
    # the family the exception could have been mistaken for is still excluded
    for sibling in (
        "app.tasks.backfill_winners",
        "app.tasks.backfill_kalshi_history",
        "app.tasks.backfill_polymarket_history",
    ):
        assert sibling in _HEAVY_KEEP_ON_BACKGROUND
        assert sibling not in HEAVY_MOVE_EXCEPTION


# ---------------------------------------------------------------------------
# The routing actually applied — in the IMPORTED config, not just the source.
# LAT-P076 lost two attempts to a mutation that never applied and still
# reported "1 passed".
# ---------------------------------------------------------------------------


def test_exception_tasks_route_to_heavy_in_the_imported_config():
    from app.tasks import HEAVY_TASKS, celery_app

    assert HEAVY_MOVE_EXCEPTION <= HEAVY_TASKS
    for task in HEAVY_MOVE_EXCEPTION:
        assert celery_app.conf.task_routes[task] == {"queue": "heavy"}


def test_exception_beat_entries_dispatch_to_heavy():
    """Beat ``options`` override ``task_routes``, so both must agree."""
    from app.tasks import celery_app

    seen = set()
    for entry in celery_app.conf.beat_schedule.values():
        if entry.get("task") in HEAVY_MOVE_EXCEPTION:
            seen.add(entry["task"])
            assert entry.get("options", {}).get("queue") == "heavy"
    assert seen == HEAVY_MOVE_EXCEPTION, "a moved task lost its beat entry"


def test_exception_beat_literals_say_heavy_in_the_source():
    """The SOURCE TEXT must say heavy, not rely on the backstop loop.

    The backstop flips HEAVY_TASKS beat entries to heavy whatever they were
    authored with, so a literal reading `background` would dispatch correctly
    while telling every human reader the opposite. LAT-P067 paid for this
    lesson across nine entries; a revert must edit these literals too.
    """
    src = TASKS_SRC.read_text()
    for beat_name in ("backfill-market-shapes", "precompute-backfill-progress"):
        block = re.search(
            rf'"{re.escape(beat_name)}":\s*\{{(.*?)\n    \}},', src, re.S
        )
        assert block, f"beat entry {beat_name} not found"
        assert '"queue": "heavy"' in block.group(1), (
            f"{beat_name}'s literal options.queue does not say heavy"
        )


# ---------------------------------------------------------------------------
# #1800: the metrics identifier is NOT the task name, and getting that wrong
# blinded three of seven subjects while the falsifier reported itself armed.
# ---------------------------------------------------------------------------


def test_metrics_names_match_tracked_run_registrations():
    src = TASKS_SRC.read_text()
    for task, metrics_name in METRICS_NAME.items():
        short = task.rsplit(".", 1)[-1]
        decl = src.index(f'name="{task}"')
        window = src[decl : decl + 2000]
        m = re.search(r'_tracked_run\(\s*"([^"]+)"', window)
        assert m, f"no _tracked_run registration found for {short}"
        assert m.group(1) == metrics_name, (
            f"{short} registers metrics as {m.group(1)!r} but METRICS_NAME says "
            f"{metrics_name!r} — this is the #1800 split that produces a false "
            "NO DATA and a silently blind falsifier"
        )


def test_every_watched_beat_has_a_metrics_name():
    for beat in PRE_MOVE_BASELINE:
        assert beat.task in METRICS_NAME
        assert beat.metrics_name


def test_baseline_soft_limits_match_the_configured_tasks():
    """The censored marking derives from real limits, so it cannot rot."""
    from app.tasks import celery_app

    for beat in PRE_MOVE_BASELINE:
        configured = celery_app.tasks[beat.task].soft_time_limit
        assert configured == beat.soft_time_limit_s, (
            f"{beat.task}: baseline pins {beat.soft_time_limit_s}s but the task "
            f"is configured at {configured}s"
        )


# ---------------------------------------------------------------------------
# THE FALSIFIER CAN GO RED. This is the point of the file.
# ---------------------------------------------------------------------------


def test_falsifier_actually_fires_on_a_degraded_beat():
    obs = _all_holding()
    victim = BASELINE_BY_TASK["app.tasks.precompute_source_intelligence"]
    obs[victim.metrics_name] = _obs(victim.p50_s * (DEGRADE_P50_RATIO + 0.5))

    result = grade_move(obs, now_epoch=AT_HORIZON)
    assert result.verdict == "REVERT"
    assert result.must_revert is True
    assert "precompute_source_intelligence" in result.reason


def test_one_degraded_beat_is_enough():
    """The grant is conditional on ALL of them; any single failure revokes it."""
    obs = _all_holding()
    victim = BASELINE_BY_TASK["app.tasks.compute_fair_fight_comparison"]
    obs[victim.metrics_name] = _obs(victim.p50_s * 2.0)
    assert grade_move(obs, now_epoch=AT_HORIZON).verdict == "REVERT"


def test_unchanged_production_holds():
    assert grade_move(_all_holding(), now_epoch=AT_HORIZON).verdict == "HOLD"


def test_threshold_boundary_is_not_inverted():
    """Just under the ratio holds; just over it reverts."""
    victim = BASELINE_BY_TASK["app.tasks.precompute_source_intelligence"]

    under = _all_holding()
    under[victim.metrics_name] = _obs(victim.p50_s * (DEGRADE_P50_RATIO - 0.01))
    assert grade_move(under, now_epoch=AT_HORIZON).verdict == "HOLD"

    over = _all_holding()
    over[victim.metrics_name] = _obs(victim.p50_s * (DEGRADE_P50_RATIO + 0.01))
    assert grade_move(over, now_epoch=AT_HORIZON).verdict == "REVERT"


# ---------------------------------------------------------------------------
# ...and it must never read an ABSENCE as a pass (gotcha #53).
# ---------------------------------------------------------------------------


def test_no_observations_at_all_is_inconclusive_not_hold():
    result = grade_move({}, now_epoch=AT_HORIZON)
    assert result.verdict == "INCONCLUSIVE"
    assert result.verdict != "HOLD"
    assert "NOT evidence" in result.reason


def test_unreadable_beat_is_not_graded_as_holding():
    beat = BASELINE_BY_TASK["app.tasks.precompute_source_intelligence"]
    assert grade_beat(beat, None, age_since_move_s=RUN_COUNTER_WINDOW_S * 2).verdict == "unreadable"
    assert grade_beat(beat, {"recent_durations_ms": []}, age_since_move_s=RUN_COUNTER_WINDOW_S * 2).verdict == "unreadable"


def test_beat_that_has_not_run_is_not_graded_as_holding():
    beat = BASELINE_BY_TASK["app.tasks.precompute_source_intelligence"]
    v = grade_beat(beat, {"recent_durations_ms": [1000.0], "successes_24h": 0, "failures_24h": 0}, age_since_move_s=RUN_COUNTER_WINDOW_S * 2)
    assert v.verdict == "no_new_runs"


def test_censored_beats_cannot_manufacture_a_pass():
    """A beat whose GRADING statistic is pinned reports the same number however
    much worse it gets, so grading it would turn a saturated instrument into
    evidence of safety.

    🔴 NARROWED FROM TWO BEATS TO ONE by #2071 (LAT-P080B), and the narrowing is
    the fix rather than a relaxation. This used to censor on `p95`, and a 14 %
    clip rate pins any p95 by arithmetic — so
    `precompute_backfill_winners_status` was discarded over the 7 runs it could
    not read while its p50 (518.4 s, 86 % of the clamp, durations spanning two
    and a half orders of magnitude) sat there readable. The remaining exclusion
    is `compute_calibration_prices`, and it is censored against its OWN 540 s
    budget rather than the 600 s soft limit. Full argument and the
    observation-side mirror: `tests/test_falsifier_censoring_2071.py`.
    """
    censored = [b for b in PRE_MOVE_BASELINE if b.censored]
    assert {b.task for b in censored} == {"app.tasks.compute_calibration_prices"}
    for beat in censored:
        # even a catastrophic reading on a censored beat is reported as censored
        assert grade_beat(beat, _obs(beat.p50_s * 10), age_since_move_s=RUN_COUNTER_WINDOW_S * 2).verdict == "censored"

    # and a run in which ONLY censored beats are readable is INCONCLUSIVE
    obs = {b.metrics_name: _obs(b.p50_s) for b in censored}
    assert grade_move(obs, now_epoch=AT_HORIZON).verdict == "INCONCLUSIVE"


def test_all_watched_beats_appear_in_every_verdict():
    """A beat that drops out of the report is a beat nobody is watching."""
    for obs in ({}, _all_holding()):
        result = grade_move(obs, now_epoch=AT_HORIZON)
        assert {b.task for b in result.beats} == CALIBRATION_HEAVY_BEATS


@pytest.mark.parametrize("beat", PRE_MOVE_BASELINE, ids=lambda b: b.task.rsplit(".", 1)[-1])
def test_baseline_values_are_internally_consistent(beat):
    assert 0 < beat.p50_s <= beat.p95_s <= beat.max_s
    assert beat.samples > 0


# ---------------------------------------------------------------------------
# LAT-P079 DEFECT 1 — THE HORIZON GATE.
#
# The first production read said HOLD 6m55s after the move, over a 24h window
# that was ~99.5% pre-move data. A grade taken before its own horizon is the
# distribution compared against itself.
# ---------------------------------------------------------------------------


def test_a_grade_taken_before_the_horizon_is_inconclusive_not_hold():
    """LAT-P078's actual reading, replayed. It must no longer say HOLD."""
    result = grade_move(_all_holding(), now_epoch=PRE_HORIZON)
    assert result.verdict == "INCONCLUSIVE"
    assert result.verdict != "HOLD"
    assert "PRE-HORIZON" in result.reason
    assert "NOT evidence" in result.reason
    assert {b.verdict for b in result.beats} <= {"pre_horizon", "censored", "no_new_runs"}


def test_the_horizon_gate_CLEARS_and_is_not_a_gate_that_can_never_go_green():
    """🔴 The mirror of the defect being fixed, and it must be tested for.

    The staged fix ("movers[*].samples == 0 => INCONCLUSIVE") applied to the
    unrepaired read would have been TRUE FOREVER, converting a gate that could
    not go red into one that could not go green. Identical bytes on the
    dashboard, opposite meaning, same wrong-gate class. So the horizon gate is
    only correct if it demonstrably *opens*: same observations, later clock.
    """
    obs = _all_holding()
    assert grade_move(obs, now_epoch=PRE_HORIZON).verdict == "INCONCLUSIVE"
    assert grade_move(obs, now_epoch=AT_HORIZON).verdict == "HOLD"


def test_the_horizon_gate_does_not_suppress_a_real_revert_after_it_opens():
    """It delays the verdict; it must never disarm it."""
    obs = _all_holding()
    victim = BASELINE_BY_TASK["app.tasks.precompute_source_intelligence"]
    obs[victim.metrics_name] = _obs(victim.p50_s * 2.0)
    assert grade_move(obs, now_epoch=AT_HORIZON).verdict == "REVERT"


def test_a_pre_horizon_beat_cannot_fire_a_spurious_revert_either():
    """The gate protects the grant from false revocation, not only the lane
    from a false clean bill. A p50 drawn from pre-move samples can no more
    prove a regression than it can prove safety."""
    obs = _all_holding()
    victim = BASELINE_BY_TASK["app.tasks.precompute_source_intelligence"]
    obs[victim.metrics_name] = _obs(victim.p50_s * 10)
    result = grade_move(obs, now_epoch=PRE_HORIZON)
    assert result.verdict == "INCONCLUSIVE"
    assert not result.must_revert
    victim_verdict = next(b for b in result.beats if b.task == victim.task)
    assert victim_verdict.verdict == "pre_horizon"


def test_a_24h_counter_supplies_no_lower_bound_while_it_straddles_the_move():
    """The exact fact the gate rests on, asserted on its own.

    `successes_24h` covers [now-24h, now]. That window lies wholly after the
    move only once age >= 24h; before then every one of those runs could have
    predated it, so the honest answer is None, not an estimate.
    """
    assert post_move_runs_lower_bound(40, RUN_COUNTER_WINDOW_S - 1) is None
    assert post_move_runs_lower_bound(40, 0.0) is None
    assert post_move_runs_lower_bound(40, RUN_COUNTER_WINDOW_S) == 40
    assert post_move_runs_lower_bound(40, RUN_COUNTER_WINDOW_S * 3) == 40


def test_a_beat_whose_ring_is_mostly_pre_move_is_pre_horizon_even_past_24h():
    """Age alone is not the horizon — the RING has to have turned over.

    A beat running 4 times a day needs ~12 days to refresh a 50-deep ring. At
    25h its p50 is still 92% baseline, and grading it would read the baseline
    back as a result.
    """
    beat = BASELINE_BY_TASK["app.tasks.precompute_source_intelligence"]
    slow = grade_beat(
        beat,
        _obs(beat.p50_s, runs=4, n=50),
        age_since_move_s=RUN_COUNTER_WINDOW_S + 3600,
    )
    assert slow.verdict == "pre_horizon"
    assert slow.post_move_ring_share == 0.08

    fast = grade_beat(
        beat,
        _obs(beat.p50_s, runs=50, n=50),
        age_since_move_s=RUN_COUNTER_WINDOW_S + 3600,
    )
    assert fast.verdict == "hold"
    assert fast.post_move_ring_share == 1.0


# ---------------------------------------------------------------------------
# The EXACT path: the ring is timestamped, so post-move samples are counted,
# not estimated — and the grade runs on those samples alone.
# ---------------------------------------------------------------------------


def _stamped(pre_s: float, post_s: float, *, n_pre: int, n_post: int, runs: int = 40):
    """A ring with ``n_post`` post-move samples, newest-first as Redis stores it.

    Durations are given in SECONDS and stored in milliseconds, matching `_obs`
    and the real payload.
    """
    return {
        "recent_durations_ms": [post_s * 1000] * n_post + [pre_s * 1000] * n_pre,
        "recent_durations_at": (
            [ROUTING_CHANGE_AT_EPOCH + 60 * (i + 1) for i in range(n_post)]
            + [ROUTING_CHANGE_AT_EPOCH - 60 * (i + 1) for i in range(n_pre)]
        ),
        "successes_24h": runs,
        "failures_24h": 0,
    }


def test_a_stamped_ring_grades_on_its_post_move_samples_alone():
    """The whole point of exposing the stamps: a beat whose ring is mostly
    pre-move is still gradeable, on the part of it that is about the move.

    Under the counter estimate this beat waits for a 50-sample turnover — at
    its real cadence, weeks. Here it grades on 10 post-move samples, and the
    40 pre-move ones do not dilute the answer.
    """
    beat = BASELINE_BY_TASK["app.tasks.precompute_source_intelligence"]
    v = grade_beat(
        beat,
        _stamped(beat.p50_s, beat.p50_s * 2.0, n_pre=40, n_post=10),
        age_since_move_s=3600.0,  # ONE HOUR — no 24h wait needed
    )
    assert v.verdict == "degraded"
    assert v.observed_p50_s == pytest.approx(beat.p50_s * 2.0)
    assert v.post_move_ring_share == 0.2


def test_a_stamped_ring_below_the_minimum_is_pre_horizon():
    beat = BASELINE_BY_TASK["app.tasks.precompute_source_intelligence"]
    v = grade_beat(
        beat,
        _stamped(beat.p50_s, beat.p50_s * 5, n_pre=45, n_post=5),
        age_since_move_s=RUN_COUNTER_WINDOW_S * 5,
    )
    assert v.verdict == "pre_horizon"
    assert "post-move samples" in v.reason
    assert "5" in v.reason


def test_the_pre_move_samples_do_not_dilute_the_post_move_grade():
    """A regression hidden behind a wall of healthy pre-move samples is the
    exact failure the whole-ring p50 produced. It must not survive."""
    beat = BASELINE_BY_TASK["app.tasks.compute_fair_fight_comparison"]
    ring = _stamped(beat.p50_s, beat.p50_s * 3.0, n_pre=42, n_post=8)
    whole_ring_p50 = sorted(ring["recent_durations_ms"])[len(ring["recent_durations_ms"]) // 2]
    assert whole_ring_p50 == beat.p50_s * 1000, "fixture: whole-ring p50 looks healthy"

    v = grade_beat(beat, ring, age_since_move_s=7200.0)
    assert v.verdict == "degraded", "the regression was hidden by the pre-move majority"


def test_an_unstamped_ring_falls_back_and_SAYS_it_fell_back():
    """No stamps is a different fact from no post-move samples (#53)."""
    beat = BASELINE_BY_TASK["app.tasks.precompute_source_intelligence"]
    v = grade_beat(beat, _obs(beat.p50_s, runs=4, n=50), age_since_move_s=3600.0)
    assert v.verdict == "pre_horizon"
    assert "no timestamps" in v.reason


def test_a_legacy_unstamped_ENTRY_counts_as_pre_move_not_as_post_move():
    """`None` in the stamp list is a sample written before LAT-P040, so it is
    genuinely old. Treating it as post-move would fabricate the horizon."""
    beat = BASELINE_BY_TASK["app.tasks.precompute_source_intelligence"]
    ring = _stamped(beat.p50_s, beat.p50_s * 2, n_pre=0, n_post=10)
    ring["recent_durations_at"] = [None] * 5 + ring["recent_durations_at"][5:]
    v = grade_beat(beat, ring, age_since_move_s=3600.0)
    assert v.verdict == "pre_horizon", "unstamped entries were counted as post-move"


def test_grade_move_requires_its_clock_to_be_stated():
    """No default for `now_epoch`. A default is how the ungated read comes back,
    and it would make this whole suite a function of the wall clock (#44)."""
    with pytest.raises(TypeError):
        grade_move(_all_holding())  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# LAT-P079 DEFECT 2 — THE PANEL COULD NOT SEE ITS OWN SUBJECTS.
#
# The route read the seven protected beats and then asked that dict about the
# two movers, which were never in it. `movers[*].samples` was 0 by
# construction while both tasks ran 29 and 44 times a day.
# ---------------------------------------------------------------------------


def test_the_panel_reads_its_own_subjects():
    """THE test that would have caught it: the read set must contain every
    name the report speaks about, movers included."""
    for task in HEAVY_MOVE_EXCEPTION:
        assert METRICS_NAME[task] in READ_SET, (
            f"{task} is reported by the falsifier but its metrics name is not in "
            "READ_SET — the panel would answer about a task it never fetched"
        )
    for beat in PRE_MOVE_BASELINE:
        assert beat.metrics_name in READ_SET
    assert len(READ_SET) == len(set(READ_SET))


def test_the_route_reads_the_full_read_set_not_just_the_baseline():
    """Source-shape guard. The defect was in the ROUTE's read, so a module-level
    constant alone does not prevent its return."""
    route_src = (
        Path(__file__).resolve().parents[1] / "app" / "routes" / "admin_celery.py"
    ).read_text()
    fn = route_src[route_src.index("async def heavy_move_falsifier") :][:4000]
    assert "READ_SET" in fn
    assert "for b in PRE_MOVE_BASELINE" not in fn, (
        "the panel is building its read set from the protected beats again — "
        "that is exactly how the movers became invisible"
    )


def test_an_absent_mover_is_not_reported_as_a_zero():
    """gotcha #53. `samples: 0` and `successes_24h: null` was the rendering that
    a reader (this program) took for a measurement of a task that had not run."""
    movers = summarize_movers({}, age_since_move_s=RUN_COUNTER_WINDOW_S * 2)
    for task in HEAVY_MOVE_EXCEPTION:
        row = movers[task]
        assert row["observed"] is False
        assert row["samples"] is None, "an absent read must not render as 0 samples"
        assert row["runs_24h"] is None
        assert row["p4"] == "unreadable"


def test_an_observed_mover_reports_its_real_activity():
    obs = {
        METRICS_NAME["app.tasks.backfill_market_shapes"]: {
            "recent_durations_ms": [25_732.0] * 50,
            "successes_24h": 29,
            "failures_24h": 2,
        }
    }
    movers = summarize_movers(obs, age_since_move_s=RUN_COUNTER_WINDOW_S * 2)
    row = movers["app.tasks.backfill_market_shapes"]
    assert row["observed"] is True
    assert row["samples"] == 50
    assert row["runs_24h"] == 31
    # the other one is genuinely absent and says so, in the same payload
    assert movers["app.tasks.precompute_backfill_progress"]["observed"] is False


# ---------------------------------------------------------------------------
# P4 — LAT-P077's one prediction that could always discriminate the move.
# P1 (period p95 < 200s) and P2 (loss < 20%) were RETIRED by LAT-P079: the
# pre-move system already met both. See docs/audits/latency/lat-p079-*.md.
# ---------------------------------------------------------------------------


def test_p4_is_gated_by_the_same_horizon_as_everything_else():
    """A 24h run counter read minutes after the move is a fact about yesterday."""
    obs = {
        METRICS_NAME[t]: {
            "recent_durations_ms": [1000.0] * 50,
            "successes_24h": 90,
            "failures_24h": 0,
        }
        for t in HEAVY_MOVE_EXCEPTION
    }
    early = summarize_movers(obs, age_since_move_s=60.0)
    for task in HEAVY_MOVE_EXCEPTION:
        assert early[task]["p4"] == "pre_horizon"
        assert early[task]["observed"] is True  # readable, just not yet meaningful


def test_p4_can_pass_and_can_fail():
    """A prediction that cannot fail is the defect this cycle is about."""
    age = RUN_COUNTER_WINDOW_S * 2

    rose = summarize_movers(
        {
            METRICS_NAME[t]: {
                "recent_durations_ms": [1000.0] * 50,
                "successes_24h": MOVER_PRE_MOVE[t].scheduled_fires_24h,
                "failures_24h": 0,
            }
            for t in HEAVY_MOVE_EXCEPTION
        },
        age_since_move_s=age,
    )
    assert {rose[t]["p4"] for t in HEAVY_MOVE_EXCEPTION} == {"rose"}

    flat = summarize_movers(
        {
            METRICS_NAME[t]: {
                "recent_durations_ms": [1000.0] * 50,
                "successes_24h": MOVER_PRE_MOVE[t].runs_24h,
                "failures_24h": 0,
            }
            for t in HEAVY_MOVE_EXCEPTION
        },
        age_since_move_s=age,
    )
    assert {flat[t]["p4"] for t in HEAVY_MOVE_EXCEPTION} == {"flat_or_fell"}


def test_mover_pre_move_counts_match_the_ruling():
    """Ruling 110 and LAT-P077 §4 both quote 31/72 and 45/96."""
    assert MOVER_PRE_MOVE["app.tasks.backfill_market_shapes"].runs_24h == 31
    assert MOVER_PRE_MOVE["app.tasks.backfill_market_shapes"].scheduled_fires_24h == 72
    assert MOVER_PRE_MOVE["app.tasks.precompute_backfill_progress"].runs_24h == 45
    assert MOVER_PRE_MOVE["app.tasks.precompute_backfill_progress"].scheduled_fires_24h == 96
    assert set(MOVER_PRE_MOVE) == HEAVY_MOVE_EXCEPTION


def test_the_routing_change_epoch_is_pinned_not_derived():
    """Like the baseline: a horizon recomputed from live data is the change
    timing itself. v3882 / 0c7ccdf2, 2026-08-21T16:08:40Z."""
    import datetime as dt

    moved = dt.datetime.fromtimestamp(ROUTING_CHANGE_AT_EPOCH, tz=dt.timezone.utc)
    assert moved == dt.datetime(2026, 8, 21, 16, 8, 40, tzinfo=dt.timezone.utc)
