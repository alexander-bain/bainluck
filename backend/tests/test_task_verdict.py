"""Queue 300H — the returned-summary verdict contract.

Every shape in ``TestFrozenProductionShapes`` is copied from what the task
actually returns in production (see the r346 ops read), so a future refactor of
those tasks that changes the summary shape breaks a test here rather than
silently restoring the false GREEN.
"""

import pytest

from app.utils.task_verdict import (
    COMPLETE,
    ENFORCED_TASKS,
    FAILED,
    PARTIAL,
    UNKNOWN,
    classify_summary,
    verdict_for,
)


class TestLegacyAndPoisonShapes:
    """A summary that carries no terminal truth proves nothing — and can never
    crash the task that produced it."""

    @pytest.mark.parametrize("result", [
        None,
        "done",
        42,
        [],
        {"result": "None"},                    # the _tracked_run scalar shim
        {"events_synced": 12, "errors": 0},    # a bare legacy counter dict
        {},
    ])
    def test_no_terminal_truth_is_non_authoritative_unknown(self, result):
        verdict = classify_summary(result)
        assert verdict.verdict == UNKNOWN
        assert verdict.authoritative is False
        # Legacy unknowns keep the pre-300H recording path.
        assert verdict.blocks_success is False

    @pytest.mark.parametrize("result", [
        {"terminal": None},
        {"terminal": 17},
        {"status": ["partial"]},
        {"status": "ok", "horizons_done": "many", "total": 4},
        {"status": "ok", "total": 0, "horizons_done": 0},
    ])
    def test_poison_shapes_never_raise(self, result):
        assert classify_summary(result).verdict in {COMPLETE, PARTIAL, FAILED, UNKNOWN}

    def test_boolean_units_are_not_counts(self):
        # bool is an int subclass; True/False are a poisoned unit pair, not 1/0.
        verdict = classify_summary({"status": "ok", "done": False, "total": True})
        assert verdict.verdict == COMPLETE


class TestFrozenProductionShapes:
    """The exact summaries the four adapter tasks return."""

    def test_time_horizon_deadline_guard_zero_of_four(self):
        # r346: reproduced every 6h, recorded as a success, health "healthy".
        verdict = classify_summary(
            {"status": "partial", "horizons_done": 0, "total": 4}
        )
        assert verdict.verdict == PARTIAL
        assert verdict.authoritative is True
        assert verdict.blocks_success is True

    def test_time_horizon_exit_path_partial(self):
        verdict = classify_summary({"status": "partial", "horizons": 3, "total": 4})
        assert verdict.verdict == PARTIAL

    def test_time_horizon_all_four_is_complete(self):
        verdict = classify_summary({"status": "ok", "horizons": 4, "total": 4})
        assert verdict.verdict == COMPLETE
        assert verdict.is_green is True

    def test_unit_shortfall_beats_an_optimistic_status(self):
        # A task that says ok while reporting 2/4 units is still partial.
        assert classify_summary(
            {"status": "ok", "horizons": 2, "total": 4}
        ).verdict == PARTIAL

    def test_calibration_prices_deadline_truncated(self):
        # Returns cleanly with stopped_at set — "registers SUCCESS" was the bug.
        verdict = classify_summary({
            "terminal": "partial", "stopped_at": "part_b",
            "reset": 0, "with_commence": 120, "errors": [],
        })
        assert verdict.verdict == PARTIAL

    def test_calibration_prices_exhausted_run_is_complete(self):
        verdict = classify_summary({
            "terminal": "complete", "stopped_at": None,
            "with_commence": 4200, "errors": [],
        })
        assert verdict.verdict == COMPLETE

    def test_complete_terminal_with_errors_is_downgraded(self):
        verdict = classify_summary({
            "terminal": "complete", "stopped_at": None, "errors": ["boom"],
        })
        assert verdict.verdict == PARTIAL
        assert "errors" in verdict.reason

    def test_coverage_metrics_swallowed_exception(self):
        # The task catches its own exception and RETURNS terminal=failed.
        verdict = classify_summary({
            "terminal": "failed", "errors": ["statement timeout"],
            "published": False, "snapshots": 0,
        })
        assert verdict.verdict == FAILED

    def test_coverage_metrics_overlap_skip_banks_nothing(self):
        verdict = classify_summary({
            "terminal": "partial", "skipped": "overlap_lock_not_acquired",
            "published": False,
        })
        assert verdict.verdict == PARTIAL

    def test_coverage_metrics_published_sweep_is_complete(self):
        verdict = classify_summary({
            "terminal": "complete", "published": True, "snapshots": 88,
            "failed_chunks": [], "errors": [],
        })
        assert verdict.verdict == COMPLETE

    def test_complete_terminal_without_publish_is_partial(self):
        verdict = classify_summary({
            "terminal": "complete", "published": False, "errors": [],
        })
        assert verdict.verdict == PARTIAL

    def test_coverage_metrics_failed_chunks_downgrade(self):
        verdict = classify_summary({
            "terminal": "complete", "published": True,
            "failed_chunks": ["120000-140000"], "errors": [],
        })
        assert verdict.verdict == PARTIAL


class TestPhaseLedgerAdapter:
    """``precompute_calibration_main`` — terminal AND durable generation."""

    def test_complete_and_green_is_the_only_success(self):
        verdict = classify_summary(
            {"phase_ledger": {"terminal": "complete", "health": "green"}}
        )
        assert verdict.verdict == COMPLETE

    def test_complete_without_green_is_authoritative_unknown(self):
        # Every phase ran; the ledger write failed or no artifact generation
        # landed. The build happened; the artifact operators read did not.
        verdict = classify_summary(
            {"phase_ledger": {"terminal": "complete", "health": "unknown"}}
        )
        assert verdict.verdict == UNKNOWN
        assert verdict.authoritative is True
        assert verdict.blocks_success is True

    def test_partial_terminal(self):
        verdict = classify_summary(
            {"phase_ledger": {"terminal": "partial", "health": "unknown"}}
        )
        assert verdict.verdict == PARTIAL

    def test_cancelled_terminal_is_partial_not_failed(self):
        # Cancellation is recorded, but partial progress is not relabelled as a
        # thrown failure.
        verdict = classify_summary(
            {"phase_ledger": {"terminal": "cancelled", "health": "unknown"}}
        )
        assert verdict.verdict == PARTIAL

    def test_red_health_is_failed(self):
        verdict = classify_summary(
            {"phase_ledger": {"terminal": "failed", "health": "red"}}
        )
        assert verdict.verdict == FAILED

    def test_overlap_refused_banks_nothing(self):
        verdict = classify_summary(
            {"phase_ledger": {"terminal": "overlap_refused", "health": "unknown"}}
        )
        assert verdict.verdict == UNKNOWN
        assert verdict.blocks_success is True

    def test_checkpoint_leased_early_return(self):
        # The wrapper's REFUSE path returns before any build.
        verdict = classify_summary({
            "status": "skipped", "reason": "checkpoint_leased",
            "owner": "abc:12", "ledger_write": "ok",
        })
        assert verdict.verdict == UNKNOWN
        assert verdict.authoritative is True

    def test_ledger_adapter_wins_over_a_sibling_status_key(self):
        verdict = classify_summary({
            "status": "ok",
            "phase_ledger": {"terminal": "partial", "health": "unknown"},
        })
        assert verdict.verdict == PARTIAL


class TestEnforcementScope:
    """Only the four named adapters gate health. Everything else records as
    before — a ``status`` key means "no live games" in most of this codebase."""

    def test_the_four_calibration_tasks_are_enforced(self):
        assert ENFORCED_TASKS == {
            "calibration_prices",
            "compute_time_horizon_calibration",
            "precompute_calibration_main",
            "coverage_metrics",
        }

    def test_enforced_task_partial_blocks_success(self):
        verdict = verdict_for(
            "compute_time_horizon_calibration",
            {"status": "partial", "horizons_done": 0, "total": 4},
        )
        assert verdict.verdict == PARTIAL
        assert verdict.blocks_success is True

    @pytest.mark.parametrize("summary", [
        {"status": "no_live_games", "events": 0},        # espn_sync, empty slate
        {"status": "green", "red": [], "amber": []},     # data_quality_watchdog finding
        {"status": "nothing_to_backfill"},               # kalshi/polymarket backfills
        {"status": "degraded", "cached": False},         # source intelligence
        {"status": "partial_budget_guard"},              # backfill_winners
    ])
    def test_unenforced_tasks_are_untouched(self, summary):
        verdict = verdict_for("espn_sync", summary)
        assert verdict.verdict == UNKNOWN
        assert verdict.authoritative is False
        assert verdict.blocks_success is False
        assert verdict.reason.startswith("not_enforced(")

    def test_unenforced_reason_carries_what_the_contract_would_have_said(self):
        verdict = verdict_for("espn_sync", {"terminal": "partial"})
        assert "partial" in verdict.reason
