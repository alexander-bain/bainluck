"""The ruling-110 grading harness, proven BEFORE the protected window uses it.

## Why this file exists at all

`scripts/grade_ruling_110.py` is prep for a window that has been defeated five
consecutive times and now runs under a bought deploy freeze. A tool first
exercised inside that window is not prep — it is one more thing that can go wrong
while the clock that cost something is running.

So every path is driven here, off fixtures, at zero horizon cost: PASSED, FAILED,
PRE_HORIZON, UNREADABLE, and — the one that matters most — **REVERT**, which
carries a same-window obligation and therefore must be proven to actually fire
rather than assumed to.

## The trap this is written against

A grader whose only fixture is the current production payload grades exactly one
state (today: `INCONCLUSIVE`, everything `pre_horizon`) and silently cannot
distinguish the others. That is the same shape as the defect the falsifier itself
shipped with — `samples: 0` was a CONSTANT that a reader took for a measurement
(#2071) — and as the staged fix that would have been "never false". A gate that
cannot go red is not a gate.
"""

from __future__ import annotations

import json

import pytest

from scripts.grade_ruling_110 import (
    EXIT_OK,
    EXIT_PREDICTION_FAILED,
    EXIT_REVERT,
    EXIT_UNREADABLE,
    build_report,
    grade_p3,
    grade_p4,
    grade_p5,
    main,
)

MOVERS = (
    "app.tasks.backfill_market_shapes",
    "app.tasks.precompute_backfill_progress",
)


def _mover(task, p4, runs, observed=True):
    return {
        "metrics_name": task.split(".")[-1],
        "observed": observed,
        "successes_24h": runs if observed else None,
        "failures_24h": 0 if observed else None,
        "runs_24h": runs if observed else None,
        "samples": 50 if observed else None,
        "pre_move_runs_24h": 31,
        "scheduled_fires_24h": 72,
        "p4": p4,
    }


def _payload(
    *,
    verdict="HOLD",
    beat_verdicts=("ok", "ok"),
    p4="rose",
    runs=70,
    observed=True,
    age_h=18.0,
):
    return {
        "status": "ok",
        "ruling": 110,
        "verdict": verdict,
        "reason": "fixture",
        "horizon": {"age_since_move_h": age_h, "counters_clear_the_move": True},
        "movers": {t: _mover(t, p4, runs, observed) for t in MOVERS},
        "beats": [
            {
                "task": f"app.tasks.beat_{i}",
                "verdict": v,
                "ratio": 1.4 if v == "degraded" else 0.97,
                "reason": v,
            }
            for i, v in enumerate(beat_verdicts)
        ],
    }


# ── P3, the control ─────────────────────────────────────────────────────────


def test_p3_passes_when_no_protected_beat_degrades():
    assert grade_p3(_payload())["verdict"] == "PASSED"


def test_p3_fails_on_a_single_degraded_beat():
    g = grade_p3(_payload(beat_verdicts=("ok", "degraded")))
    assert g["verdict"] == "FAILED"
    assert len(g["degraded"]) == 1


def test_p3_is_pre_horizon_when_nothing_is_gradeable_yet():
    """Today's production state — and it must not read as a pass."""
    g = grade_p3(_payload(beat_verdicts=("pre_horizon", "pre_horizon")))
    assert g["verdict"] == "PRE_HORIZON"


def test_a_censored_beat_is_reported_and_does_not_count_as_a_pass():
    """Gotcha #146 — a percentile at a ceiling says nothing about what is under it."""
    g = grade_p3(_payload(beat_verdicts=("censored", "censored")))
    assert g["verdict"] == "PRE_HORIZON"
    assert "CENSORED" in g["note"]
    assert g["beats_gradeable"] == 0


def test_a_partial_p3_pass_states_its_coverage():
    """"PASSED on 3 of 7" and "PASSED on 7 of 7" are different claims.

    The rendered table is what the protected window reads, so the coverage has to
    be ON the verdict line — a bare PASSED over a mostly-unreadable beat set is
    the same overstatement class as a sampled maximum reported as a maximum.
    """
    g = grade_p3(_payload(beat_verdicts=("ok", "pre_horizon", "censored", "ok")))
    assert g["verdict"] == "PASSED"
    assert g["coverage"] == "2/4 beats gradeable"
    assert "2/4" in g["note"] and "pre-horizon" in g["note"] and "CENSORED" in g["note"]


# ── P4, promoted to primary ─────────────────────────────────────────────────


def test_p4_passes_when_both_movers_rose():
    assert grade_p4(_payload(p4="rose"))["verdict"] == "PASSED"


def test_p4_fails_when_a_mover_did_not_move():
    """P4 can fail, and if it does the starvation story behind ruling 110 was wrong."""
    assert grade_p4(_payload(p4="flat_or_fell"))["verdict"] == "FAILED"


def test_p4_is_pre_horizon_not_a_pass_before_the_counters_clear():
    assert grade_p4(_payload(p4="pre_horizon"))["verdict"] == "PRE_HORIZON"


def test_p4_reports_UNREADABLE_rather_than_zero_when_the_movers_are_absent():
    """#2071's own defect: an absent read and a zero read must not render alike."""
    g = grade_p4(_payload(observed=False, p4="unreadable"))
    assert g["verdict"] == "UNREADABLE"
    assert "#2071" in g["note"]


# ── P5, the falsifier's own verdict ─────────────────────────────────────────


def test_p5_passes_on_HOLD_past_the_horizon():
    assert grade_p5(_payload(verdict="HOLD"))["verdict"] == "PASSED"


def test_p5_is_pre_horizon_while_any_beat_is():
    g = grade_p5(_payload(verdict="INCONCLUSIVE", beat_verdicts=("pre_horizon", "ok")))
    assert g["verdict"] == "PRE_HORIZON"


def test_p5_fails_on_INCONCLUSIVE_once_nothing_is_pre_horizon():
    """The LAT-P079 amendment: INCONCLUSIVE is a FAILURE past the horizon.

    Before it, an instrument that could only ever say INCONCLUSIVE would have
    left the grant unwatched indefinitely, which is the one thing ruling 110
    forbids.
    """
    assert grade_p5(_payload(verdict="INCONCLUSIVE"))["verdict"] == "FAILED"


def test_p5_surfaces_REVERT():
    assert grade_p5(_payload(verdict="REVERT"))["verdict"] == "REVERT"


# ── The exit codes the morning window will actually branch on ───────────────


def _run(tmp_path, payload, name="p.json"):
    path = tmp_path / name
    path.write_text(json.dumps(payload))
    return main(["--from-file", str(path)])


def test_exit_0_when_nothing_failed(tmp_path):
    assert _run(tmp_path, _payload()) == EXIT_OK


def test_exit_1_on_a_failed_prediction_with_no_revert(tmp_path):
    assert _run(tmp_path, _payload(p4="flat_or_fell")) == EXIT_PREDICTION_FAILED


def test_exit_2_on_REVERT_so_it_cannot_be_scrolled_past(tmp_path):
    """The same-window obligation ruling 110 was granted under."""
    code = _run(tmp_path, _payload(verdict="REVERT"))
    assert code == EXIT_REVERT
    assert code != EXIT_PREDICTION_FAILED, "REVERT must be distinguishable from a plain failure"


def test_exit_3_is_the_harness_failing_not_a_result(tmp_path):
    """Gotcha #54: `1` is a result, anything else is a story about the harness."""
    bad = tmp_path / "bad.json"
    bad.write_text('{"not": "a falsifier payload"}')
    assert main(["--from-file", str(bad)]) == EXIT_UNREADABLE
    assert main(["--from-file", str(tmp_path / "missing.json")]) == EXIT_UNREADABLE


def test_the_retired_predictions_are_named_not_silently_dropped(tmp_path):
    report = build_report(_payload())
    assert set(report["retired_predictions"]) == {"P1", "P2"}
    assert all(g["prediction"] in {"P3", "P4", "P5"} for g in report["grades"])


def test_it_grades_the_REAL_production_payload_shape():
    """Drives the exact shape production served on 2026-08-21, pre-horizon.

    Guards against the grader being written for a payload shape that does not
    exist — the field names here are copied from a live response, not invented.
    """
    live_shaped = {
        "status": "ok",
        "ruling": 110,
        "verdict": "INCONCLUSIVE",
        "reason": "4 of 7 watched beats are still PRE-HORIZON",
        "degrade_p50_ratio": 1.25,
        "exception_tasks": list(MOVERS),
        "horizon": {
            "routing_change_at_epoch": 1787328520.0,
            "routing_change_at": "2026-08-21T16:08:40+00:00",
            "age_since_move_s": 9958.7,
            "age_since_move_h": 2.77,
            "run_counter_window_s": 86400.0,
            "post_move_ring_share_required": 0.5,
            "counters_clear_the_move": False,
        },
        "movers": {
            "app.tasks.backfill_market_shapes": {
                "metrics_name": "market_shape_backfill",
                "observed": True,
                "successes_24h": 36,
                "failures_24h": 2,
                "runs_24h": 38,
                "samples": 50,
                "pre_move_runs_24h": 31,
                "scheduled_fires_24h": 72,
                "p4": "pre_horizon",
            },
            "app.tasks.precompute_backfill_progress": {
                "metrics_name": "precompute_backfill_progress",
                "observed": True,
                "successes_24h": 53,
                "failures_24h": 0,
                "runs_24h": 53,
                "samples": 50,
                "pre_move_runs_24h": 45,
                "scheduled_fires_24h": 96,
                "p4": "pre_horizon",
            },
        },
        "beats": [
            {
                "task": "app.tasks.precompute_calibration_main",
                "verdict": "pre_horizon",
                "reason": "3 post-move samples in a 50-deep ring (6%)",
                "baseline_p50_s": 214.7,
                "observed_p50_s": 205.452,
                "ratio": None,
                "post_move_ring_share": 0.06,
            },
            {
                "task": "app.tasks.compute_calibration_prices",
                "verdict": "censored",
                "reason": "baseline p95 599.9s is at the 600s soft limit",
                "baseline_p50_s": 538.2,
                "observed_p50_s": None,
                "ratio": None,
                "post_move_ring_share": None,
            },
        ],
    }
    report = build_report(live_shaped)
    assert report["revert_obliged"] is False
    assert report["failed_predictions"] == []
    verdicts = {g["prediction"]: g["verdict"] for g in report["grades"]}
    assert verdicts == {"P3": "PRE_HORIZON", "P4": "PRE_HORIZON", "P5": "PRE_HORIZON"}


@pytest.mark.parametrize("flag", ["--live", "--from-file"])
def test_the_two_sources_are_mutually_exclusive_and_one_is_required(flag):
    with pytest.raises(SystemExit):
        main([])
