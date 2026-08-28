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
    """Only the named adapters gate health. Everything else records as
    before — a ``status`` key means "no live games" in most of this codebase.

    Membership is pinned exactly so that enrolling a task stays a deliberate,
    test-visible act. Enrolling one makes its verdict AUTHORITATIVE, which can
    turn a previously-green surface red — that is the point, and it should never
    happen as a side effect of an unrelated edit.
    """

    def test_the_enforced_adapters_are_exactly_these(self):
        assert ENFORCED_TASKS == {
            "calibration_prices",
            "compute_time_horizon_calibration",
            "precompute_calibration_main",
            "coverage_metrics",
            # CAL-P008 (#683): enrolled after a measured false GREEN — 500 markets
            # fetched, 500 empty, 0 snapshots created, recorded as a success every
            # 6h for ten weeks. Terminal comes from `_trade_backfill_terminal`.
            "kalshi_trades",
            # CAL-P051 (#1835): enrolled after a measured TOTAL SILENCE — the
            # writer sat behind backfill_winners' first budget guard and never
            # ran (`stopped_before: "bookmaker_closing"`, successes_24h 0), its
            # 24h Redis key expired, and the `odds_api_bookmaker` source simply
            # left the published payload. Three causes, one identical silence.
            # Terminal comes from `_precompute_bookmaker_calibration` itself.
            "bookmaker_calibration",
            # #1586 (queue 355): the Kalshi cliff drain, enrolled at BIRTH
            # rather than after an incident — the only member so far. Its
            # cohort expires upstream (~7,800 markets/week), so "fetched
            # nothing" and "nothing left to fetch" are outwardly identical and
            # mean opposite things; that is precisely the kalshi_trades failure
            # above, and there is no reason to wait ten weeks to learn it twice.
            # Terminal comes from `kalshi_cliff._terminal`.
            "kalshi_cliff_drain",
            # #1798 (queue 364): the ruling-048 reconciliation drain, the SECOND
            # enrolled at birth. Enrolling it is not a formality — this task's
            # entire purpose is to make an accepted-but-unmeasured cost visible,
            # so a GREEN run of it that reconciled nothing would restore exactly
            # the blindness it was built to end. Measured on its first census:
            # 500 unanchored rows, 0 reconciled, and all 500 classified
            # NO_ANCHOR_CHANNEL — their creating provider has no id column on
            # `events`, so the id that ruling 048's bounding clause waits for has
            # nowhere to land. `terminal` is `no_work` on any zero and `failed`
            # with `measured: false` when the census itself could not run.
            "reconcile_unanchored_events",
            # #1912 (CAL-P065): the two halves of the Polymarket ownership
            # hole, enrolled TOGETHER because separately each one looked fine.
            # The Gamma rail discarded 9,748 markets a run as
            # `unsupported_lookup` — "counted here, owned there" — to a CLOB
            # rail whose scheduled cohort predicate (`bool_or(resolution_source
            # = ANY(...))` over all-NULL sources) could not select them at all.
            # Both reported `health: healthy`, `failures_24h: 0`,
            # `last_verdict: unverified`, while 25,264 fully venue-addressable
            # markets went ungraded. This is the kalshi_trades shape again, one
            # rail over, and this time the handoff made it look deliberate.
            #
            # Note the trap these two are the specimen for: adding a name here
            # is NOT the fix. A summary with no `terminal` classifies as the
            # non-authoritative legacy unknown, whose `blocks_success` is
            # False, so enrolment alone would have left both green. Terminals
            # come from `gamma_terminal` / `clob_terminal` in
            # `app/utils/pm_market_ownership.py` and ship in the same change.
            "polymarket_winners",
            "clob_resolve_drain",
            # #1866 (LAT-P067): Option D's typeahead index builder and its D4
            # sentinel. Enrolled at BIRTH, joining kalshi_cliff_drain as the
            # second and third members to be added before an incident rather
            # than after one.
            #
            # The builder is a bounded resumable sweep, so it has kalshi_trades'
            # exact ambiguity: "caught up" and "ran out of budget a third of the
            # way in" are outwardly identical and mean opposite things. Its
            # terminal is `complete` only when every family reached its end,
            # `partial` on a budget stop, and `failed` when the cursor could not
            # be persisted — progress made, silently unresumable.
            #
            # The sentinel guards a SECOND COPY OF TRUTH, which is a strictly
            # worse failure than a slow query: a stale denormalised index is
            # wrong, where the query it replaced was merely slow. It returns
            # `failed` above the drift threshold so a drifting index cannot read
            # GREEN, and `no_work` on an empty index, because the backfill not
            # having run yet is not drift.
            #
            # Terminals come from `app.tasks.typeahead_index`.
            "rebuild_typeahead_index",
            "typeahead_index_sentinel",
            # #2007 (CAL-P080): Gate 0's in-dyno DB-direct twin — the fourth
            # member enrolled at BIRTH. It belongs here on the strongest version
            # of the argument, because its single failure mode IS the false
            # GREEN this set exists for and there is no other one worth naming:
            # the gate's pass value is `agrees`, and a fold that read NOTHING
            # agrees with everything. A run that errored, a run whose published
            # payload was unreadable, and a run whose SELECT returned zero rows
            # against a population of hundreds of thousands all reach that same
            # comfortable answer unless something stops them.
            #
            # So `terminal` is `complete` only for a real `agrees`/`disagrees`
            # and `failed` for every `unmeasurable`. `disagrees` terminating
            # complete is deliberate and is the distinction the whole set turns
            # on: the gate finding a problem is the gate WORKING, and only "I
            # could not measure" is a failed run.
            #
            # Terminal comes from `build_artifact` in
            # `app/tasks/calibration_published_twin_worker.py`, in this same
            # change — per the trap documented at `polymarket_winners` above,
            # adding the name alone would have been a no-op.
            "calibration_published_twin",
            # #2007 (CAL-P084): the beat gauge sampler — the fifth enrolled at
            # BIRTH, and the purest instance of what this set is for. A
            # SAMPLER's failure mode is not an error, it is running forever and
            # capturing nothing, which is `kalshi_trades` exactly. It exists
            # because the phase ledger keeps ONE row per identity and is
            # overwritten every beat, so the bound's first descent was captured
            # only by a previous window's leftover shell process; an instrument
            # written to end that blindness must not be able to go blind
            # quietly.
            #
            # `complete` only when the current beat is in the ring, `failed` on
            # an unreadable ledger / an absent required gauge / a failed write
            # (for a sampler the RECORD is the product, so losing it is the run
            # failing, not a lesser mishap), and `partial` when the ledger reads
            # fine but no beat has landed in two periods — the sampler working
            # over a stopped producer is the one state that would otherwise be
            # indistinguishable from health.
            #
            # UX-P134: the tournament register drift sentinel, enrolled at
            # BIRTH. Its two outcomes are outwardly identical and mean opposite
            # things — a run that compared zero registered identities returns
            # exactly as quietly as a run that compared 211 and found nothing
            # wrong. On a page whose entire correctness rests on a pinned
            # register during a live tournament, "the sentinel ran" must not be
            # readable as "the register is fine".
            "tournament_register_sentinel",
            # Terminal comes from `decide_terminal` in
            # `app/tasks/calibration_beat_gauge_sampler.py`, in this same change.
            "calibration_beat_gauge_sampler",
            # #2199: the futures price refresher, enrolled at BIRTH. It is the
            # remedy for a measured false GREEN — two discovery polls reported
            # success while 900 of 907 high-value tier-1 open futures markets
            # went uncaptured for up to 32 days, including every marquee
            # championship field. A remedy that inherited that blindness would
            # be worse than none, so a run that attempted markets and wrote zero
            # snapshots returns `failed`. Terminal comes from
            # `futures_price_refresh._terminal`.
            "futures_price_refresh",
            # UX-P143, from CERT C-UX-P139-GRID-REGISTER-1 [P2]: the two rails
            # that keep `/tournaments/{slug}` current. They shipped calling
            # `_tracked_run` with no `terminal` at all — the exact no-op trap
            # documented at `polymarket_winners` above — so both classified as
            # the non-authoritative legacy unknown and read GREEN whatever they
            # did.
            #
            # Their failure is silent BY CONSTRUCTION, which is the argument for
            # enrolling them rather than a formality: a dead price refresh does
            # not blank the grid, it lets every number on it age behind whatever
            # freshness word the gates award; a dead results sync does not show a
            # wrong score, it shows none. The page looks the same either way, and
            # this rail was written precisely because the grid had silently gone
            # 27 hours old once already.
            #
            # Terminals come from `_refresh_terminal` / `_results_terminal` in
            # `app/tasks/tournament_price_refresh.py`, in this same change.
            "tournament_price_refresh",
            "tournament_results_sync",
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
