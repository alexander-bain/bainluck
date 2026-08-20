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
    PRE_MOVE_BASELINE,
    grade_beat,
    grade_move,
)

TASKS_SRC = Path(__file__).resolve().parents[1] / "app" / "tasks" / "__init__.py"


def _obs(p50_s: float, *, runs: int = 5, n: int = 20):
    """An observation whose median duration is exactly ``p50_s`` seconds."""
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

    result = grade_move(obs)
    assert result.verdict == "REVERT"
    assert result.must_revert is True
    assert "precompute_source_intelligence" in result.reason


def test_one_degraded_beat_is_enough():
    """The grant is conditional on ALL of them; any single failure revokes it."""
    obs = _all_holding()
    victim = BASELINE_BY_TASK["app.tasks.compute_fair_fight_comparison"]
    obs[victim.metrics_name] = _obs(victim.p50_s * 2.0)
    assert grade_move(obs).verdict == "REVERT"


def test_unchanged_production_holds():
    assert grade_move(_all_holding()).verdict == "HOLD"


def test_threshold_boundary_is_not_inverted():
    """Just under the ratio holds; just over it reverts."""
    victim = BASELINE_BY_TASK["app.tasks.precompute_source_intelligence"]

    under = _all_holding()
    under[victim.metrics_name] = _obs(victim.p50_s * (DEGRADE_P50_RATIO - 0.01))
    assert grade_move(under).verdict == "HOLD"

    over = _all_holding()
    over[victim.metrics_name] = _obs(victim.p50_s * (DEGRADE_P50_RATIO + 0.01))
    assert grade_move(over).verdict == "REVERT"


# ---------------------------------------------------------------------------
# ...and it must never read an ABSENCE as a pass (gotcha #53).
# ---------------------------------------------------------------------------


def test_no_observations_at_all_is_inconclusive_not_hold():
    result = grade_move({})
    assert result.verdict == "INCONCLUSIVE"
    assert result.verdict != "HOLD"
    assert "NOT evidence" in result.reason


def test_unreadable_beat_is_not_graded_as_holding():
    beat = BASELINE_BY_TASK["app.tasks.precompute_source_intelligence"]
    assert grade_beat(beat, None).verdict == "unreadable"
    assert grade_beat(beat, {"recent_durations_ms": []}).verdict == "unreadable"


def test_beat_that_has_not_run_is_not_graded_as_holding():
    beat = BASELINE_BY_TASK["app.tasks.precompute_source_intelligence"]
    v = grade_beat(beat, {"recent_durations_ms": [1000.0], "successes_24h": 0, "failures_24h": 0})
    assert v.verdict == "no_new_runs"


def test_censored_beats_cannot_manufacture_a_pass():
    """Two beats sit at their 600s soft limit with 0 successes/24h.

    A beat clamped at its own timeout reports the same number however much
    worse it gets, so grading it would turn a saturated instrument into
    evidence of safety.
    """
    censored = [b for b in PRE_MOVE_BASELINE if b.censored]
    assert {b.task for b in censored} == {
        "app.tasks.compute_calibration_prices",
        "app.tasks.precompute_backfill_winners_status",
    }
    for beat in censored:
        # even a catastrophic reading on a censored beat is reported as censored
        assert grade_beat(beat, _obs(beat.p50_s * 10)).verdict == "censored"

    # and a run in which ONLY censored beats are readable is INCONCLUSIVE
    obs = {b.metrics_name: _obs(b.p50_s) for b in censored}
    assert grade_move(obs).verdict == "INCONCLUSIVE"


def test_all_watched_beats_appear_in_every_verdict():
    """A beat that drops out of the report is a beat nobody is watching."""
    for obs in ({}, _all_holding()):
        result = grade_move(obs)
        assert {b.task for b in result.beats} == CALIBRATION_HEAVY_BEATS


@pytest.mark.parametrize("beat", PRE_MOVE_BASELINE, ids=lambda b: b.task.rsplit(".", 1)[-1])
def test_baseline_values_are_internally_consistent(beat):
    assert 0 < beat.p50_s <= beat.p95_s <= beat.max_s
    assert beat.samples > 0
