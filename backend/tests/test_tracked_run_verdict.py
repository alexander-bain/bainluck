"""Queue 300H Item 1 — `_tracked_run` records what the summary actually says.

The defect this locks down (#1515, re-verified by r346 across three rounds):
every scheduled task recorded a SUCCESS for any invocation that returned
without raising, so a calibration task computing zero horizons, a sweep
stopping at its deadline, and a snapshot swallowing its own exception all
reported `health: healthy` while the rail behind them was dark.
"""

import asyncio

import pytest

from app.tasks import _tracked_run
from app.tasks import redis_state


class _Recorder:
    """Captures which recorder `_tracked_run` chose, and with what verdict."""

    def __init__(self):
        self.calls = []

    def success(self, task_name, duration_ms, result_summary=None,
                verdict="complete", verdict_reason=""):
        self.calls.append(("success", task_name, verdict, verdict_reason))

    def incomplete(self, task_name, duration_ms, verdict, verdict_reason,
                   result_summary=None):
        self.calls.append(("incomplete", task_name, verdict, verdict_reason))

    def failure(self, task_name, duration_ms, error, verdict="thrown",
                verdict_reason=""):
        self.calls.append(("failure", task_name, verdict, error))


@pytest.fixture
def recorder(monkeypatch):
    rec = _Recorder()
    monkeypatch.setattr(redis_state, "record_task_success", rec.success)
    monkeypatch.setattr(redis_state, "record_task_incomplete", rec.incomplete)
    monkeypatch.setattr(redis_state, "record_task_failure", rec.failure)
    monkeypatch.setattr(redis_state, "touch_worker_liveness", lambda *a, **k: None)
    return rec


def _returns(value):
    async def _fn():
        return value
    return _fn()


def _raises(exc):
    async def _fn():
        raise exc
    return _fn()


class TestEnforcedCalibrationTasks:

    def test_zero_of_four_horizons_is_not_a_success(self, recorder):
        result = _tracked_run(
            "compute_time_horizon_calibration",
            _returns({"status": "partial", "horizons_done": 0, "total": 4}),
        )
        assert result == {"status": "partial", "horizons_done": 0, "total": 4}
        kind, task, verdict, reason = recorder.calls[0]
        assert kind == "incomplete"
        assert verdict == "partial"
        assert reason == "units:horizons_done=0/4"

    def test_all_four_horizons_is_a_success(self, recorder):
        _tracked_run(
            "compute_time_horizon_calibration",
            _returns({"status": "ok", "horizons": 4, "total": 4}),
        )
        assert recorder.calls[0][0] == "success"
        assert recorder.calls[0][2] == "complete"

    def test_deadline_truncated_price_sweep_is_not_a_success(self, recorder):
        _tracked_run(
            "calibration_prices",
            _returns({"terminal": "partial", "stopped_at": "part_b", "errors": []}),
        )
        assert recorder.calls[0][0] == "incomplete"

    def test_swallowed_exception_is_recorded_as_a_failure(self, recorder):
        # coverage_metrics catches its own error and RETURNS terminal=failed.
        _tracked_run(
            "coverage_metrics",
            _returns({"terminal": "failed", "errors": ["timeout"], "published": False}),
        )
        kind, _task, verdict, _error = recorder.calls[0]
        assert kind == "failure"
        assert verdict == "failed"

    def test_complete_build_without_a_durable_generation_is_not_a_success(self, recorder):
        _tracked_run(
            "precompute_calibration_main",
            _returns({"phase_ledger": {"terminal": "complete", "health": "unknown"}}),
        )
        kind, _task, verdict, _reason = recorder.calls[0]
        assert kind == "incomplete"
        assert verdict == "unknown"

    def test_complete_and_green_build_is_a_success(self, recorder):
        _tracked_run(
            "precompute_calibration_main",
            _returns({"phase_ledger": {"terminal": "complete", "health": "green"}}),
        )
        assert recorder.calls[0][0] == "success"


class TestUnenforcedTasksAreUnchanged:
    """Blast radius: the ~100 tasks that predate the contract must record
    exactly as they did before, because `status` means "no live games" in most
    of this codebase, not a terminal."""

    @pytest.mark.parametrize("summary", [
        {"status": "no_live_games", "events": 0},
        {"status": "green", "red": [], "amber": []},
        {"status": "nothing_to_backfill"},
        {"synced": 12, "errors": 0},
        None,
        "ok",
    ])
    def test_recorded_as_an_unverified_success(self, recorder, summary):
        _tracked_run("espn_sync", _returns(summary))
        kind, _task, verdict, _reason = recorder.calls[0]
        assert kind == "success"
        assert verdict == "unverified"

    def test_scalar_return_is_wrapped_not_dropped(self, recorder):
        assert _tracked_run("espn_sync", _returns(7)) == 7


class TestThrownBehaviourPreserved:

    def test_exception_records_a_failure_and_propagates(self, recorder):
        with pytest.raises(RuntimeError, match="boom"):
            _tracked_run("poll_odds", _raises(RuntimeError("boom")))
        kind, _task, verdict, error = recorder.calls[0]
        assert kind == "failure"
        assert verdict == "thrown"
        assert "boom" in error

    def test_cancellation_records_a_terminal_before_propagating(self, recorder):
        # r346: an in-flight beat killed by a mid-run deploy used to vanish from
        # BOTH the ledger and the counters. CancelledError is a BaseException,
        # so the old `except Exception` never saw it.
        with pytest.raises(asyncio.CancelledError):
            _tracked_run("precompute_calibration_main", _raises(asyncio.CancelledError()))
        kind, _task, verdict, _error = recorder.calls[0]
        assert kind == "failure"
        assert verdict == "thrown"

    def test_bare_exception_message_falls_back_to_the_class_name(self, recorder):
        with pytest.raises(asyncio.CancelledError):
            _tracked_run("coverage_metrics", _raises(asyncio.CancelledError()))
        assert recorder.calls[0][3] == "CancelledError"
