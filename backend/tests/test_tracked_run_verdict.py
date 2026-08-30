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
        # CAL-P040: summaries live in their own list so the 4-tuple unpacking
        # every existing test does keeps working.
        self.summaries = []

    def success(self, task_name, duration_ms, result_summary=None,
                verdict="complete", verdict_reason=""):
        self.calls.append(("success", task_name, verdict, verdict_reason))
        self.summaries.append(("success", result_summary))

    def incomplete(self, task_name, duration_ms, verdict, verdict_reason,
                   result_summary=None):
        self.calls.append(("incomplete", task_name, verdict, verdict_reason))
        self.summaries.append(("incomplete", result_summary))

    def failure(self, task_name, duration_ms, error, verdict="thrown",
                verdict_reason="", result_summary=None):
        # #2222: the failure recorder takes a summary too. It was the only one
        # that did not, and it is the one that fires for a task returning
        # `terminal: failed` — so the run whose account you most need was the
        # one run whose account was discarded.
        self.calls.append(("failure", task_name, verdict, error))
        self.summaries.append(("failure", result_summary))


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

    def test_a_returned_failure_keeps_its_own_summary(self, recorder):
        """#2222 — the failing run's account must reach the recorder.

        `futures_price_refresh` returned `terminal: failed` on every run for a
        month while its summary held the answer, and the summary went nowhere.
        Diagnosing it needed a live re-run with the task's Redis markers cleared
        by hand, to recover a number the failing run had already computed.

        Driven through the real `_tracked_run` rather than asserted against its
        source, so a future refactor that stops passing it fails here.
        """
        summary = {
            "terminal": "failed",
            "markets_attempted": 19,
            "snapshots_written": 0,
            "venue_settled": 18,
            "not_found": 1,
        }
        _tracked_run("futures_price_refresh", _returns(summary))
        kind, captured = recorder.summaries[0]
        assert kind == "failure"
        assert captured == summary, "the failed path must forward the summary verbatim"

    def test_a_thrown_failure_has_no_summary_to_forward(self, recorder):
        """The control. A raise has no returned account, and inventing one would
        make an exception indistinguishable from a task reporting on itself."""

        def _raises():
            raise RuntimeError("boom")

        async def _async_raises():
            _raises()

        # `_tracked_run` records a terminal and then RE-RAISES, which is the
        # long-standing contract for a thrown failure and is not changed here.
        with pytest.raises(RuntimeError):
            _tracked_run("coverage_metrics", _async_raises())
        kind, _task, verdict, _error = recorder.calls[0]
        assert kind == "failure"
        assert verdict == "thrown"
        assert recorder.summaries == [("failure", None)], (
            "a thrown failure must not fabricate a summary"
        )

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


class TestStagedFuturesIncompleteIsNotAFailure:
    """CAL-P040, from codex C283's BLOCK on CAL-P038.

    CAL-P038 made the calibration build stop cleanly at a unit boundary and
    raise ``StagedFuturesIncomplete`` instead of letting Postgres cancel its
    last unit. That fix worked. It was then recorded as a thrown failure by
    ``_tracked_run``, because every raise reached the generic handler — one
    boundary above where CAL-P038's own unit tests stopped.

    Production stated the defect precisely and for a long time:
    ``incompletes_24h`` **0** against ``consecutive_failures`` **201**, with a
    phase ledger whose own ``terminal`` already read ``cancelled``. Two
    boundaries, one event, two contradictory verdicts. These tests pin the
    boundary that was missing, so the counter cannot silently go back to lying.
    """

    def _incomplete(self):
        from app.tasks.calibration_main_build import StagedFuturesIncomplete

        return StagedFuturesIncomplete(
            "futures generation incomplete — units banked, nothing published"
        )

    def test_records_exactly_one_incomplete_and_zero_failures(self, recorder):
        _tracked_run("precompute_calibration_main", _raises(self._incomplete()))

        kinds = [c[0] for c in recorder.calls]
        assert kinds.count("incomplete") == 1, recorder.calls
        assert kinds.count("failure") == 0, recorder.calls
        assert kinds.count("success") == 0, recorder.calls

        _kind, task, verdict, reason = recorder.calls[0]
        assert task == "precompute_calibration_main"
        assert verdict == "partial"
        assert reason == "StagedFuturesIncomplete"

    def test_returns_the_summary_instead_of_propagating(self, recorder):
        # The scheduler contract half. Re-raising would move the counter
        # correctly and then mark the Celery task FAILURE and emit a Sentry
        # event for behaviour the design calls correct — putting the false RED
        # back one layer up from the one being removed. Nothing retries this
        # task, so returning costs no signal.
        result = _tracked_run(
            "precompute_calibration_main", _raises(self._incomplete())
        )
        assert isinstance(result, dict)
        assert result["status"] == "incomplete"
        assert result["terminal"] == "cancelled"
        assert "units banked" in result["reason"]

    def test_the_returned_summary_is_the_recorded_summary(self, recorder):
        result = _tracked_run(
            "precompute_calibration_main", _raises(self._incomplete())
        )
        kind, recorded = recorder.summaries[0]
        assert kind == "incomplete"
        assert recorded == result

    def test_the_recorded_summary_classifies_as_partial_through_the_contract(
        self, recorder
    ):
        # The self-consistency invariant, and the reason ``terminal`` is spelled
        # ``cancelled`` rather than something decorative: ``cancelled`` is in
        # ``task_verdict._TERMINAL_PARTIAL``, so if this summary is ever fed back
        # through the classifier the two paths agree about the same event. A
        # future refactor that routes this dict through ``verdict_for`` must not
        # be able to turn it into a success.
        from app.utils.task_verdict import PARTIAL, verdict_for

        _tracked_run("precompute_calibration_main", _raises(self._incomplete()))
        _kind, recorded = recorder.summaries[0]

        verdict = verdict_for("precompute_calibration_main", recorded)
        assert verdict.verdict == PARTIAL
        assert verdict.authoritative is True

    def test_a_subclass_is_also_an_incomplete(self, recorder):
        # isinstance, not type equality — the build is free to raise a more
        # specific reason without silently reverting to "failure".
        from app.tasks.calibration_main_build import StagedFuturesIncomplete

        class _MoreSpecific(StagedFuturesIncomplete):
            pass

        _tracked_run("precompute_calibration_main", _raises(_MoreSpecific("x")))
        assert recorder.calls[0][0] == "incomplete"

    def test_a_plain_runtime_error_from_the_same_task_still_fails_and_propagates(
        self, recorder
    ):
        # The guard must be NARROW. StagedFuturesIncomplete subclasses
        # RuntimeError, and the calibration build raises real RuntimeErrors for
        # real defects; catching by the base class would silence them into
        # "partial" and hide a genuine break behind a healthy-looking counter.
        with pytest.raises(RuntimeError, match="genuinely broken"):
            _tracked_run(
                "precompute_calibration_main",
                _raises(RuntimeError("genuinely broken")),
            )
        kind, _task, verdict, _error = recorder.calls[0]
        assert kind == "failure"
        assert verdict == "thrown"

    def test_cancellation_is_still_a_failure(self, recorder):
        # r346's behaviour is untouched: a warm-shutdown kill is NOT the
        # designed partial, and must keep leaving a thrown terminal.
        with pytest.raises(asyncio.CancelledError):
            _tracked_run(
                "precompute_calibration_main", _raises(asyncio.CancelledError())
            )
        assert recorder.calls[0][0] == "failure"


class TestIncompleteDetectorDegradesSafely:

    def test_an_unimportable_marker_class_does_not_mask_the_live_exception(
        self, monkeypatch
    ):
        # The detector runs while an exception is already in flight. If its
        # import ever raised, the real terminal would be replaced by an
        # ImportError — losing exactly the thing we came to record. It must
        # degrade to the previous behaviour instead.
        import builtins

        from app.tasks import _is_staged_futures_incomplete

        real_import = builtins.__import__

        def _boom(name, *args, **kwargs):
            if name == "app.tasks.calibration_main_build":
                raise ImportError("simulated")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", _boom)
        assert _is_staged_futures_incomplete(RuntimeError("x")) is False

    def test_it_recognises_the_real_production_type(self):
        # Pins the detector against the ACTUAL class the build raises, not a
        # double. A double would keep passing if the type were moved or renamed.
        from app.tasks import _is_staged_futures_incomplete
        from app.tasks.calibration_main_build import StagedFuturesIncomplete

        assert _is_staged_futures_incomplete(StagedFuturesIncomplete("x")) is True
        assert _is_staged_futures_incomplete(RuntimeError("x")) is False
        assert _is_staged_futures_incomplete(asyncio.CancelledError()) is False
