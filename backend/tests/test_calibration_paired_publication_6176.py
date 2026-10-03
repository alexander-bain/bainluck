"""#6176 (October 1 scope) — the paired early/final accuracy block on the main payload.

What is pinned here, and why each one bends a published number if it breaks:

* the kernel's new ``event_ids`` filter is additive and absent by default;
* valid, reconfirmed-unchanged and CONTRARY pairs are all scored and reported;
* mixed books, stale/absent legs and non-independent results are named
  exclusions, never scored;
* model forecasts never pool with market prices;
* the margin is withheld below 30 events and the raw SE is not published;
* the candidate cap admits whole events and says ``incomplete``;
* no pairs / timeout / failure is a typed ``unavailable`` — never a 0;
* the block publishes in the same bytes and generation as the curve, and its
  failure cannot block the curve;
* ``_main_input_fingerprint`` does not move, so the staged-futures bank survives.

Rows fed to the assembler are produced by the kernel's own
:func:`classify_pair`, so these tests exercise the kernel's semantics rather
than a hand-written imitation of them.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.tasks import calibration_paired_publication as cpp
from app.utils import calibration_paired_prestart as kernel
from app.utils.resolution_authority import calibration_truth_eligible_sql

T0 = datetime(2026, 9, 20, 19, 0, tzinfo=timezone.utc)
H = timedelta(hours=1)


class _Event:
    def __init__(self, commence=T0, source="espn"):
        self.commence_time = commence
        self.commence_time_source = source
        self.created_at = commence - timedelta(days=5)
        self.completed_at = None


def _snap(at, p, *, book="kalshi", valid_until=None):
    return (at, p, None, None, book, valid_until)


def _row(outcome_id, event_id, snaps, *, is_winner, source="kalshi", start=T0,
         eligible_sources=None, resolution_source=None):
    """One row in the exact shape ``paired_legs_sql`` emits, classed by the kernel."""
    klass, early, final = kernel.classify_pair(
        snaps,
        event=_Event(start),
        market_source=source,
        is_winner=is_winner,
        resolution_source=resolution_source,
        eligible_sources=eligible_sources,
    )
    paired = klass in kernel.PAIRED_CLASSES
    return {
        "outcome_id": outcome_id,
        "source": source,
        "forecast_kind": kernel.forecast_kind(source),
        "cluster_id": event_id,
        "category": "football",
        "is_winner": is_winner,
        "bookmaker": source if paired else None,
        "early_probability": early,
        "early_captured_at": None,
        "final_probability": final,
        "final_captured_at": None,
        "pair_class": klass,
    }


def _two_leg(early_p, final_p, *, book="kalshi"):
    return [_snap(T0 - 26 * H, early_p, book=book), _snap(T0 - 2 * H, final_p, book=book)]


def _events(n, *, candidates=2):
    return [
        {"event_id": 1000 + i, "commence_time": T0 - i * H, "n_candidates": candidates}
        for i in range(n)
    ]


def _assemble(events, rows):
    return cpp.assemble(events, cpp.admit_events(events), rows, generated_at="GEN")


def _improving_rows(n_events, *, early=0.55, final=0.80, source="kalshi"):
    """Each event: a winner and a loser whose final legs both moved toward truth."""
    rows = []
    for i in range(n_events):
        ev = 1000 + i
        rows.append(_row(2 * i, ev, _two_leg(early, final, book=source), is_winner=True, source=source))
        rows.append(_row(2 * i + 1, ev, _two_leg(1 - early, 1 - final, book=source), is_winner=False, source=source))
    return rows


# ---------------------------------------------------------------------------
# The kernel filter
# ---------------------------------------------------------------------------


class TestTheKernelEventFilterIsAdditive:
    def test_omitted_it_emits_the_statement_it_always_did(self):
        assert kernel.paired_legs_sql() == kernel.paired_legs_sql(outcome_ids=None)
        assert "fo.id IN" not in kernel.paired_legs_sql()

    def test_supplied_it_adds_one_and_clause_and_nothing_else(self):
        bare = kernel.paired_legs_sql()
        filtered = kernel.paired_legs_sql(outcome_ids=":outcome_ids")
        added = "\n  AND fo.id IN :outcome_ids"
        assert filtered.count(added) == 1
        assert filtered.replace(added, "") == bare

    def test_the_id_restriction_is_on_the_base_row_not_inside_a_lateral(self):
        """The ids bound the WORK, not just the rows returned: the restriction is
        a predicate on ``futures_outcomes`` in the outer WHERE — after every
        LATERAL block and before the trailing ORDER BY/LIMIT — so the planner
        applies it to the base scan, and no outcome outside the set reaches a
        snapshot or book seek."""
        sql = kernel.paired_legs_sql(outcome_ids=":outcome_ids")
        restriction = sql.index("AND fo.id IN :outcome_ids")
        assert sql.rindex("LATERAL") < sql.rindex("\nWHERE ") < restriction
        assert restriction < sql.rindex("ORDER BY fo.id ASC") < sql.rindex("LIMIT")

    def test_the_feasibility_walk_is_unchanged(self):
        assert "fo.id IN" not in kernel.paired_feasibility_sql()


# ---------------------------------------------------------------------------
# Scoring: valid, unchanged, contrary
# ---------------------------------------------------------------------------


class TestPairsAreScoredOnTheSameOutcomes:
    def test_valid_pairs_that_improved_report_a_positive_delta_with_a_margin(self):
        rows = _improving_rows(30)
        block = _assemble(_events(30), rows)

        assert block["status"] == cpp.STATUS_AVAILABLE and block["reason"] is None
        market = block["market"]
        assert market["status"] == cpp.STATUS_AVAILABLE
        assert market["paired"] == 60 and market["paired_events"] == 30
        result = market["result"]
        assert result["mean_delta"] > 0
        assert result["final_brier"] < result["early_brier"]
        assert result["events_improved"] == 30 and result["events_worse"] == 0
        assert result["margin"] is not None and result["margin_withheld"] is False

    def test_a_contrary_finding_is_published_not_dropped(self):
        rows = _improving_rows(30, early=0.80, final=0.55)
        block = _assemble(_events(30), rows)

        result = block["market"]["result"]
        assert block["status"] == cpp.STATUS_AVAILABLE
        assert result["mean_delta"] < 0
        assert result["events_worse"] == 30 and result["events_improved"] == 0

    def test_a_reconfirmed_flat_price_is_a_pair_and_counts_as_unchanged(self):
        flat = [_snap(T0 - 30 * H, 0.6, valid_until=T0 - 3 * H)]
        rows = [
            _row(1, 1000, flat, is_winner=True),
            _row(2, 1001, flat, is_winner=False),
        ]
        assert {r["pair_class"] for r in rows} == {kernel.PAIR_PAIRED_UNCHANGED}

        block = _assemble(_events(2), rows)
        market = block["market"]
        assert market["paired"] == 2 and market["paired_unchanged"] == 2
        assert market["result"]["mean_delta"] == 0.0
        assert market["result"]["events_unchanged"] == 2

    def test_below_thirty_events_the_margin_is_withheld_and_no_raw_se_ships(self):
        block = _assemble(_events(5), _improving_rows(5))
        result = block["market"]["result"]
        assert result["n_events"] == 5
        assert result["margin"] is None and result["margin_withheld"] is True
        assert result["log_loss"]["margin"] is None
        flat = json.dumps(block)
        assert "cluster_se" not in flat and '"se"' not in flat


# ---------------------------------------------------------------------------
# Exclusions are named, never scored
# ---------------------------------------------------------------------------


class TestExclusionsAreNamed:
    def test_legs_from_two_books_are_never_stitched_into_a_pair(self):
        stitched = [_snap(T0 - 26 * H, 0.5, book="draftkings"), _snap(T0 - 2 * H, 0.8, book="fanduel")]
        rows = _improving_rows(3) + [_row(99, 1003, stitched, is_winner=True, source="odds_api")]
        block = _assemble(_events(4), rows)

        assert block["market"]["paired"] == 6
        assert {
            "forecast_kind": "market", "source": "odds_api",
            "pair_class": kernel.PAIR_LEGS_FROM_DIFFERENT_BOOKS, "n": 1, "n_events": 1,
        } in block["exclusions"]

    def test_timing_failures_are_their_own_classes(self):
        stale_final = [_snap(T0 - 26 * H, 0.5), _snap(T0 - 10 * H, 0.8)]
        only_inside_lead = [_snap(T0 - 3 * H, 0.8)]
        rows = _improving_rows(2) + [
            _row(90, 1002, stale_final, is_winner=True),
            _row(91, 1002, only_inside_lead, is_winner=True),
        ]
        block = _assemble(_events(3), rows)
        classes = {e["pair_class"] for e in block["exclusions"]}
        assert classes == {kernel.PAIR_NO_FINAL_STALE, kernel.PAIR_NO_EARLY_NONE_BEFORE}
        assert block["market"]["paired"] == 4 and block["market"]["candidates"] == 6

    def test_a_result_that_is_not_independent_is_excluded_by_the_kernel(self):
        row = _row(
            1, 1000, _two_leg(0.5, 0.9), is_winner=True,
            resolution_source="price_derived", eligible_sources={"espn"},
        )
        assert row["pair_class"] == kernel.PAIR_RESULT_NOT_INDEPENDENT
        block = _assemble(_events(1), [row])
        assert block["status"] == cpp.STATUS_UNAVAILABLE and block["reason"] == cpp.REASON_NO_PAIRS
        assert block["market"]["result"] is None

    def test_both_statements_keep_the_graded_truth_eligible_population(self):
        predicate = calibration_truth_eligible_sql(source_col="fo.resolution_source")
        for sql in (
            cpp.event_selection_sql(),
            cpp.candidate_ids_sql(),
            kernel.paired_legs_sql(outcome_ids=":outcome_ids"),
        ):
            assert "fo.is_winner IS NOT NULL" in sql
            assert predicate in sql
            assert "fm.status = 'resolved'" in sql

    def test_event_selection_requires_a_reported_start_and_a_total_order(self):
        sql = cpp.event_selection_sql()
        assert kernel.start_is_reported_sql() in sql
        assert "e.commence_time_source IS NOT NULL" in sql
        assert sql.count("ORDER BY e.commence_time DESC, e.id DESC") == 1
        assert "ORDER BY ev.commence_time DESC, ev.id DESC" in sql


class TestTheKernelBoundariesHold:
    def test_an_in_game_price_is_never_the_final_leg(self):
        snaps = _two_leg(0.55, 0.60) + [_snap(T0, 0.97), _snap(T0 + H, 0.99)]
        row = _row(1, 1000, snaps, is_winner=True)
        assert row["pair_class"] == kernel.PAIR_PAIRED
        assert row["final_probability"] == 0.60

    def test_no_opening_or_stored_close_can_pose_as_a_leg(self):
        sql = kernel.paired_legs_sql(outcome_ids=":outcome_ids")
        assert "opening_probability" not in sql
        assert "calibration_probability" not in sql
        assert "FROM futures_odds_snapshots" in sql

    def test_a_stand_in_start_refuses_before_any_leg_is_read(self):
        row = _row(1, 1000, _two_leg(0.5, 0.9), is_winner=True)
        ticker = kernel.classify_pair(
            _two_leg(0.5, 0.9), event=_Event(source="kalshi_ticker"), is_winner=True
        )
        assert row["pair_class"] == kernel.PAIR_PAIRED
        assert ticker == (kernel.PAIR_START_NOT_REPORTED, None, None)


class TestModelForecastsStaySeparate:
    def test_datagolf_gets_its_own_block_and_never_enters_the_market_number(self):
        market_only = _assemble(_events(4), _improving_rows(4))
        model_rows = [
            _row(500 + i, 2000 + i, _two_leg(0.3, 0.1, book="datagolf"), is_winner=False, source="datagolf")
            for i in range(3)
        ]
        both = _assemble(_events(7), _improving_rows(4) + model_rows)

        assert both["market"]["result"] == market_only["market"]["result"]
        assert both["model"]["status"] == cpp.STATUS_AVAILABLE
        assert both["model"]["paired"] == 3 and both["model"]["result"]["mean_delta"] > 0
        assert market_only["model"]["status"] == cpp.STATUS_UNAVAILABLE
        assert market_only["model"]["reason"] == cpp.REASON_NO_PAIRS


# ---------------------------------------------------------------------------
# Caps and the honest absence
# ---------------------------------------------------------------------------


class TestTheSampleIsBoundedAndSaysSo:
    def test_an_event_over_the_cap_is_skipped_whole_and_the_walk_continues(self):
        events = [
            {"event_id": 1, "commence_time": T0, "n_candidates": 1500},
            {"event_id": 2, "commence_time": T0 - H, "n_candidates": 900},
            {"event_id": 3, "commence_time": T0 - 2 * H, "n_candidates": 400},
        ]
        admission = cpp.admit_events(events)
        assert [e["event_id"] for e in admission["admitted"]] == [1, 3]
        assert admission["skipped"] == [{"event_id": 2, "candidates": 900}]
        assert admission["candidates"] == 1900 <= cpp.CANDIDATE_CAP

    def test_a_cap_skip_with_pairs_is_incomplete_not_available(self):
        events = _events(3) + [{"event_id": 9, "commence_time": T0 - 9 * H, "n_candidates": 5000}]
        block = _assemble(events, _improving_rows(3))
        assert block["status"] == cpp.STATUS_INCOMPLETE
        assert block["reason"] == cpp.REASON_CANDIDATE_CAP
        assert block["sample"]["events_skipped_for_cap"] == [{"event_id": 9, "candidates": 5000}]
        assert block["market"]["result"] is not None

    def test_only_the_newest_hundred_are_considered_and_older_ones_are_flagged(self):
        admission = cpp.admit_events(_events(101, candidates=1))
        assert admission["events_considered"] == 100
        assert len(admission["admitted"]) == 100
        assert admission["older_events_not_sampled"] is True
        assert 1100 not in {e["event_id"] for e in admission["admitted"]}

    def test_every_event_over_the_cap_is_unavailable_with_the_cap_named(self):
        events = [{"event_id": 1, "commence_time": T0, "n_candidates": 2500}]
        block = _assemble(events, [])
        assert block["status"] == cpp.STATUS_UNAVAILABLE
        assert block["reason"] == cpp.REASON_CANDIDATE_CAP
        assert block["market"] is None

    @pytest.mark.parametrize("events,reason", [([], cpp.REASON_NO_ELIGIBLE_EVENTS)])
    def test_no_events_is_unavailable(self, events, reason):
        block = _assemble(events, [])
        assert (block["status"], block["reason"]) == (cpp.STATUS_UNAVAILABLE, reason)

    def test_one_pair_is_not_a_result(self):
        rows = [_row(1, 1000, _two_leg(0.5, 0.9), is_winner=True)]
        block = _assemble(_events(1), rows)
        assert block["status"] == cpp.STATUS_UNAVAILABLE
        assert block["market"]["reason"] == cpp.REASON_INSUFFICIENT_PAIRS
        assert block["market"]["result"] is None and block["market"]["calibration"] is None


# ---------------------------------------------------------------------------
# The bounded session: success, timeout, failure
# ---------------------------------------------------------------------------


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def mappings(self):
        return self

    def all(self):
        return list(self._rows)


class _Session:
    def __init__(self, answers, raise_on=None):
        self.answers = list(answers)
        self.raise_on = raise_on
        self.calls = []

    async def execute(self, statement, params=None):
        self.calls.append((str(statement), params))
        if self.raise_on is not None and len(self.calls) == self.raise_on[0]:
            raise self.raise_on[1]
        return _Result(self.answers.pop(0) if self.answers else [])


def _session_factory(session, seen):
    class _Ctx:
        async def __aenter__(self):
            return session

        async def __aexit__(self, exc_type, exc, tb):
            seen["exit_exc"] = exc_type
            return False

    def factory(**kwargs):
        seen["kwargs"] = kwargs
        return _Ctx()

    return factory


class _QueryCanceledError(Exception):
    pass


def _ids(n):
    return [{"outcome_id": i} for i in range(n)]


class TestTheBoundedSession:
    @pytest.mark.asyncio
    async def test_ids_are_materialised_and_bound_before_the_legs_run(self, monkeypatch):
        import app.tasks.base as base

        events = _events(2) + [{"event_id": 7, "commence_time": T0 - 7 * H, "n_candidates": 4000}]
        session = _Session([[], [], events, _ids(4), _improving_rows(2)])
        seen: dict = {}
        monkeypatch.setattr(base, "get_task_session", _session_factory(session, seen))

        block = await cpp.build_paired_accuracy(generated_at="GEN", as_of=T0 + 48 * H)

        assert seen["kwargs"] == {"statement_timeout_ms": 5000}
        sql = [c[0] for c in session.calls]
        params = [c[1] for c in session.calls]
        assert sql[0] == "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"
        assert sql[1] == "SET LOCAL idle_in_transaction_session_timeout = 5000"
        assert params[2] == {"as_of": T0 + 48 * H, "event_limit": 101}
        # The ids statement sees ONLY the admitted events (7 was over the cap) ...
        assert "AND fm.event_id IN" in sql[3] and "LATERAL" not in sql[3]
        assert params[3] == {"event_ids": [1000, 1001], "limit": 2001}
        # ... and the legs statement sees ONLY the ids it returned.
        assert "AND fo.id IN" in sql[4]
        assert params[4] == {"cursor": 0, "scan": 2001, "outcome_ids": [0, 1, 2, 3]}
        assert len(session.calls) == 5

        assert block["status"] == cpp.STATUS_INCOMPLETE
        assert block["published_with_generated_at"] == "GEN"
        collector = block["collector"]
        assert collector["collected_at"] == (T0 + 48 * H).isoformat()
        assert collector["consistency"] == "one_repeatable_read_read_only_transaction"
        assert collector["statement_timeout_ms"] == 5000 and collector["wall_budget_s"] == 15.0
        assert isinstance(collector["collection_ms"], int)

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "answers,message",
        [
            ([[], [], _events(2), _ids(3)], "candidate ids returned 3 for 4 admitted"),
            ([[], [], _events(2), _ids(4), _improving_rows(2)[:3]], "legs returned 3 rows for 4"),
        ],
    )
    async def test_a_disagreement_with_the_admitted_denominator_is_refused(
        self, monkeypatch, answers, message
    ):
        import app.tasks.base as base

        session = _Session(answers)
        monkeypatch.setattr(base, "get_task_session", _session_factory(session, {}))
        block = await cpp.build_paired_accuracy()
        assert block["status"] == cpp.STATUS_UNAVAILABLE and block["reason"] == cpp.REASON_FAILED
        assert message in block["detail"]
        assert block["market"] is None

    @pytest.mark.asyncio
    async def test_no_events_runs_no_ids_or_legs_query(self, monkeypatch):
        import app.tasks.base as base

        session = _Session([[], [], []])
        monkeypatch.setattr(base, "get_task_session", _session_factory(session, {}))
        block = await cpp.build_paired_accuracy()
        assert len(session.calls) == 3
        assert block["reason"] == cpp.REASON_NO_ELIGIBLE_EVENTS

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "exc,reason",
        [
            (_QueryCanceledError("canceling statement due to statement timeout"), cpp.REASON_TIMEOUT),
            (RuntimeError("relation does not exist"), cpp.REASON_FAILED),
        ],
    )
    async def test_a_failing_read_is_a_typed_absence_and_rolls_back(self, monkeypatch, exc, reason):
        import app.tasks.base as base

        session = _Session([[], [], _events(2), _ids(4)], raise_on=(5, exc))
        seen: dict = {}
        monkeypatch.setattr(base, "get_task_session", _session_factory(session, seen))

        block = await cpp.build_paired_accuracy(generated_at="GEN")

        assert seen["exit_exc"] is type(exc), "the session never saw the failure"
        assert block["status"] == cpp.STATUS_UNAVAILABLE and block["reason"] == reason
        assert block["market"] is None and block["model"] is None and block["sample"] is None
        assert block["published_with_generated_at"] == "GEN"


# ---------------------------------------------------------------------------
# The wall is WHOLE: the REAL get_task_session, its teardown made slow
# ---------------------------------------------------------------------------


class _RealSessionHarness:
    """Keeps the REAL ``get_task_session`` and replaces only database I/O.

    Sol's review reproduction (artifacts/calibration/sol-original-ship-diagnosis-
    20261001T1714Z/6176-REVIEW-ca93839f6a-cleanup-repro.py) showed the first cut's
    ``asyncio.wait_for`` waiting out a slow ``session.close()`` and
    ``engine.dispose()``. These tests run that teardown for real.

    The two ``SET`` statements answer at once; the first read hangs. The
    session hands out a driver whose ``terminate()`` is logged, the way an
    asyncpg connection's is reached through ``get_raw_connection()``.
    """

    def __init__(self, monkeypatch, *, hang_s=10.0, close_s=0.0, dispose_s=0.0, driver=True):
        import app.tasks.base as base

        self.log: list[str] = []
        harness = self

        class _Driver:
            def terminate(self):
                harness.log.append("terminate")

        class _Raw:
            driver_connection = _Driver()

        class _Connection:
            async def get_raw_connection(self):
                return _Raw()

        class _Engine:
            async def dispose(self):
                await asyncio.sleep(dispose_s)
                harness.log.append("dispose")

        class _Session:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                return False

            async def execute(self, statement, *a, **k):
                if str(statement).startswith("SET "):
                    harness.log.append("set")
                    return _Result([])
                harness.log.append("execute")
                await asyncio.sleep(hang_s)

            async def close(self):
                await asyncio.sleep(close_s)
                harness.log.append("close")

            async def rollback(self):
                harness.log.append("rollback")

            async def commit(self):
                harness.log.append("commit")

        if driver:

            async def connection(self):
                return _Connection()

            _Session.connection = connection

        monkeypatch.setattr(base, "_get_task_engine", lambda **kw: _Engine())
        monkeypatch.setattr(base, "async_sessionmaker", lambda *a, **k: _Session)

    async def drain(self, timeout=5.0):
        pending = list(cpp._ABANDONED)
        if pending:
            await asyncio.wait(pending, timeout=timeout)


class TestTheWallIncludesTheTeardown:
    @pytest.mark.asyncio
    async def test_a_slow_teardown_is_cut_and_reaped_not_left_running(self, monkeypatch):
        harness = _RealSessionHarness(monkeypatch, close_s=1.0, dispose_s=1.0)
        monkeypatch.setattr(cpp, "COLLECT_BUDGET_S", 0.05)
        monkeypatch.setattr(cpp, "CLEANUP_BUDGET_S", 0.05)

        loop = asyncio.get_running_loop()
        started = loop.time()
        block = await cpp.build_paired_accuracy(generated_at="GEN")
        elapsed = loop.time() - started

        assert block["status"] == cpp.STATUS_UNAVAILABLE and block["reason"] == cpp.REASON_TIMEOUT
        assert elapsed < 0.5, f"the publish waited {elapsed:.2f}s on a 0.10s wall"
        assert "connection cut and teardown reaped" in block["detail"]
        assert harness.log == ["set", "set", "execute", "terminate"], "the socket was not cut"

        # Reaped, not abandoned: the 1s close AND the 1s dispose behind it are
        # both cancelled within a few ticks. One cancellation would interrupt
        # the close and then wait out the whole dispose.
        await harness.drain(timeout=0.25)
        assert not cpp._ABANDONED, "the teardown outlived its reap"
        assert loop.time() - started < 0.5
        assert harness.log == ["set", "set", "execute", "terminate"], "it queried or waited on"

    @pytest.mark.asyncio
    async def test_without_a_driver_the_repeated_cancel_still_bounds_it(self, monkeypatch):
        harness = _RealSessionHarness(monkeypatch, close_s=1.0, dispose_s=1.0, driver=False)
        monkeypatch.setattr(cpp, "COLLECT_BUDGET_S", 0.05)
        monkeypatch.setattr(cpp, "CLEANUP_BUDGET_S", 0.05)

        started = asyncio.get_running_loop().time()
        block = await cpp.build_paired_accuracy()
        await harness.drain(timeout=0.25)

        assert block["reason"] == cpp.REASON_TIMEOUT
        assert not cpp._ABANDONED
        assert asyncio.get_running_loop().time() - started < 0.5
        assert harness.log == ["set", "set", "execute"]

    @pytest.mark.asyncio
    async def test_a_prompt_teardown_finishes_inside_the_wall(self, monkeypatch):
        harness = _RealSessionHarness(monkeypatch)
        monkeypatch.setattr(cpp, "COLLECT_BUDGET_S", 0.05)
        monkeypatch.setattr(cpp, "CLEANUP_BUDGET_S", 1.0)

        block = await cpp.build_paired_accuracy()

        assert block["reason"] == cpp.REASON_TIMEOUT
        assert "session closed" in block["detail"]
        assert harness.log == ["set", "set", "execute", "close", "dispose"], "closed before returning"
        assert not cpp._ABANDONED

    @pytest.mark.asyncio
    async def test_a_cancelled_caller_propagates_and_stops_the_queries(self, monkeypatch):
        harness = _RealSessionHarness(monkeypatch, close_s=0.05, dispose_s=0.05)

        task = asyncio.ensure_future(cpp.build_paired_accuracy())
        await asyncio.sleep(0.02)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        await harness.drain()
        assert harness.log == ["set", "set", "execute", "close", "dispose"], (
            "the collection kept querying, or was never closed, after its caller left"
        )
        assert not cpp._ABANDONED

    @pytest.mark.asyncio
    async def test_a_cancelled_callers_slow_teardown_is_reaped_after_its_share(self, monkeypatch):
        harness = _RealSessionHarness(monkeypatch, close_s=1.0, dispose_s=1.0)
        monkeypatch.setattr(cpp, "CLEANUP_BUDGET_S", 0.1)

        loop = asyncio.get_running_loop()
        task = asyncio.ensure_future(cpp.build_paired_accuracy())
        await asyncio.sleep(0.02)
        cancelled_at = loop.time()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert loop.time() - cancelled_at < 0.05, "the cancelled caller was held"

        await harness.drain(timeout=0.5)
        assert not cpp._ABANDONED
        assert loop.time() - cancelled_at < 0.4, "teardown outlived cleanup + reap"
        assert harness.log == ["set", "set", "execute", "terminate"]


class TestTheCutClosesTheSocket:
    """``_cut`` against the asyncpg shapes measured on a real local Postgres."""

    class _Transport:
        def __init__(self):
            self.closing = False
            self.aborts = 0

        def is_closing(self):
            return self.closing

        def abort(self):
            self.aborts += 1
            self.closing = True

    def test_a_terminate_that_closes_the_transport_is_not_doubled(self):
        transport = self._Transport()
        driver = SimpleNamespace(_transport=transport, terminate=transport.abort)
        cpp._cut(driver)
        assert transport.aborts == 1

    def test_a_terminate_that_is_a_no_op_mid_close_still_closes_the_socket(self):
        # asyncpg: once a graceful close() has begun, Protocol.abort() returns
        # without touching the transport, so terminate() leaves it ESTABLISHED.
        transport = self._Transport()
        driver = SimpleNamespace(_transport=transport, terminate=lambda: None)
        cpp._cut(driver)
        assert transport.aborts == 1 and transport.is_closing()

    def test_no_driver_and_a_failing_driver_never_raise(self):
        cpp._cut(None)

        def boom():
            raise RuntimeError("already gone")

        cpp._cut(SimpleNamespace(terminate=boom))


# ---------------------------------------------------------------------------
# The boundary the review found: the REAL ``run_async`` (``asyncio.run``), as
# the Celery task calls it. On loop exit ``asyncio.run`` cancels each leftover
# task ONCE and waits for it; a teardown merely abandoned at the wall then
# interrupted ``session.close`` and waited out ``engine.dispose`` in full —
# 0.706s on a 0.10s wall (EXACT-HEAD-REVIEW-a46554934c.md, loop_exit_probe).
# ---------------------------------------------------------------------------


def _run_task_boundary(main):
    from app.tasks import base

    started = time.monotonic()
    result = base.run_async(main())
    return result, time.monotonic() - started


class TestTheRealRunAsyncBoundary:
    @pytest.mark.parametrize(
        "close_s,dispose_s",
        [(0.6, 0.6), (0.0, 0.6), (0.6, 0.0)],
        ids=["slow-close-and-dispose", "slow-dispose", "slow-close"],
    )
    def test_the_task_returns_inside_the_wall_with_its_connection_cut(
        self, monkeypatch, close_s, dispose_s
    ):
        harness = _RealSessionHarness(monkeypatch, close_s=close_s, dispose_s=dispose_s)
        monkeypatch.setattr(cpp, "COLLECT_BUDGET_S", 0.05)
        monkeypatch.setattr(cpp, "CLEANUP_BUDGET_S", 0.05)
        published = []

        async def build_then_publish():
            block = await cpp.build_paired_accuracy(generated_at="GEN")
            published.append(block["reason"])
            return block

        block, elapsed = _run_task_boundary(build_then_publish)

        assert published == [cpp.REASON_TIMEOUT], "the core coroutine did not reach its publish"
        assert block["status"] == cpp.STATUS_UNAVAILABLE
        assert elapsed < 0.3, f"run_async returned {elapsed:.3f}s on a 0.10s wall"
        assert not cpp._ABANDONED
        assert harness.log.count("execute") == 1, "a query ran after the wall"
        assert harness.log.count("terminate") == 1, "the connection was not cut exactly once"
        if close_s:
            # The slow close was interrupted; a prompt dispose may still finish.
            assert harness.log[:4] == ["set", "set", "execute", "terminate"]
            assert "close" not in harness.log
        else:
            # The close finished inside its share; the slow dispose behind it did not.
            assert harness.log == ["set", "set", "execute", "close", "terminate"]

    def test_a_cancelled_caller_then_loop_exit_returns_inside_the_wall(self, monkeypatch):
        """Two cancellations: the caller's, then ``asyncio.run``'s own at exit."""
        harness = _RealSessionHarness(monkeypatch, close_s=0.6, dispose_s=0.6)
        monkeypatch.setattr(cpp, "CLEANUP_BUDGET_S", 0.1)

        async def caller_leaves():
            task = asyncio.ensure_future(cpp.build_paired_accuracy())
            await asyncio.sleep(0.02)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                return "cancelled"
            return "not cancelled"

        outcome, elapsed = _run_task_boundary(caller_leaves)

        assert outcome == "cancelled"
        assert elapsed < 0.35, f"run_async returned {elapsed:.3f}s; cancel + 0.10s cleanup"
        assert not cpp._ABANDONED
        assert harness.log.count("execute") == 1, "the collection queried after its caller left"
        assert harness.log == ["set", "set", "execute", "terminate"]

    def test_control_a_prompt_teardown_closes_gracefully_and_is_never_cut(self, monkeypatch):
        harness = _RealSessionHarness(monkeypatch)
        monkeypatch.setattr(cpp, "COLLECT_BUDGET_S", 0.05)
        monkeypatch.setattr(cpp, "CLEANUP_BUDGET_S", 0.5)

        async def build():
            return await cpp.build_paired_accuracy()

        block, elapsed = _run_task_boundary(build)

        assert block["reason"] == cpp.REASON_TIMEOUT
        assert elapsed < 0.3
        assert harness.log == ["set", "set", "execute", "close", "dispose"]
        assert not cpp._ABANDONED

    def test_a_finished_collection_is_never_cut(self, monkeypatch):
        """A healthy read returns through the graceful close; the cut is not armed."""
        import app.tasks.base as base

        terminated = []
        session = _Session([[], [], []])
        session.connection = None  # set below: a real-shaped driver handle

        class _Raw:
            class driver_connection:  # noqa: N801 — attribute shape of a fairy
                @staticmethod
                def terminate():
                    terminated.append(True)

        async def connection():
            class _C:
                async def get_raw_connection(self):
                    return _Raw()

            return _C()

        session.connection = connection
        monkeypatch.setattr(base, "get_task_session", _session_factory(session, {}))

        block, elapsed = _run_task_boundary(lambda: cpp.build_paired_accuracy())

        assert block["reason"] == cpp.REASON_NO_ELIGIBLE_EVENTS
        assert len(session.calls) == 3, "reading the driver issued a statement"
        assert terminated == []
        assert not cpp._ABANDONED


class TestThePublishDeadline:
    @pytest.mark.asyncio
    async def test_too_little_time_left_skips_without_opening_a_session(self, monkeypatch):
        import app.tasks.base as base

        def refuse(**kw):
            raise AssertionError("a session was opened with no time to use it")

        monkeypatch.setattr(base, "get_task_session", refuse)
        block = await cpp.build_paired_accuracy(generated_at="GEN", deadline_s=100.0)
        assert block["status"] == cpp.STATUS_UNAVAILABLE
        assert block["reason"] == cpp.REASON_PUBLISH_DEADLINE
        assert block["market"] is None

    @pytest.mark.asyncio
    async def test_the_wall_shrinks_to_leave_the_publish_its_reserve(self, monkeypatch):
        import app.tasks.base as base

        session = _Session([[], [], []])
        monkeypatch.setattr(base, "get_task_session", _session_factory(session, {}))
        block = await cpp.build_paired_accuracy(deadline_s=130.0)
        # 130 - 120 reserve - 3 cleanup = 7s to collect, + 3s teardown.
        assert block["collector"]["wall_budget_s"] == 10.0

    def test_the_deadline_is_read_off_the_runners_own_clock(self):
        from app.tasks.calibration_main_build import NULL_RUNNER

        runner = SimpleNamespace(
            ledger=SimpleNamespace(remaining_ms=lambda *, elapsed_ms: 900_000 - elapsed_ms),
            elapsed_ms=lambda: 300_000,
        )
        assert cpp.remaining_publish_s(runner) == 600.0
        assert cpp.remaining_publish_s(NULL_RUNNER) is None


# ---------------------------------------------------------------------------
# Same-generation publication through the real wrapper
# ---------------------------------------------------------------------------


@pytest.fixture
def wrapper(monkeypatch):
    """The REAL ``_run_calibration_main_build`` with its I/O boundaries stubbed."""
    import app.services.durable_snapshots as ds
    import app.tasks.base as base
    import app.tasks.redis_state as rs
    import app.tasks.task_checkpoint as tc
    import app.utils.calibration_publish_gate as gate
    import app.utils.durable_state as dstate
    from app.tasks import precompute_calibration as pc

    captured: dict = {}

    class _BuildSession:
        async def execute(self, statement, params=None):
            return _Result([])

        async def commit(self):
            return None

    class _BuildCtx:
        async def __aenter__(self):
            return _BuildSession()

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr(base, "get_task_session", lambda **kw: _BuildCtx())

    async def _true(*a, **k):
        return True

    async def _none(*a, **k):
        return None

    monkeypatch.setattr(tc, "try_acquire_overlap_lock", _true)
    monkeypatch.setattr(tc, "release_overlap_lock", _none)
    monkeypatch.setattr(rs, "get_redis_client", lambda: object())

    async def fake_compute(db, runner=None):
        return {
            "buckets": [{"bucket_idx": 1, "n": 10}],
            "total_outcomes": 10,
            "generated_at": "2026-10-01T17:00:00+00:00",
        }

    monkeypatch.setattr(pc, "compute_calibration_payload", fake_compute)
    monkeypatch.setattr(pc, "_read_published_baseline", lambda rc: None)

    def fake_redis_publish(rc, payload_json):
        captured["redis_json"] = payload_json
        return {"main": "ok"}

    monkeypatch.setattr(pc, "_publish_calibration_main", fake_redis_publish)

    verdict = SimpleNamespace(
        ok=True, first_publish=True, version_bumped=False, codes=[], fingerprint="fp",
        candidate={}, published={}, baseline_source="cold_start", baseline_probe={},
        observation_codes=[], observations=[], summary=lambda: "ok",
    )

    def fake_gate(response, baseline, **_):
        captured["gate_saw"] = json.loads(json.dumps(response))
        return verdict

    monkeypatch.setattr(gate, "evaluate_publish", fake_gate)
    monkeypatch.setattr(gate, "gate_ledger_record", lambda v: {})

    # The REAL DurableEnvelope and generation stamp: the block has to survive
    # the envelope the durable store actually receives, checksum and all.
    async def fake_publish(envelope):
        captured["envelope"] = envelope
        captured["durable_payload"] = json.loads(json.dumps(envelope.payload))
        return {"status": "ok"}

    monkeypatch.setattr(ds, "publish_snapshot_standalone", fake_publish)

    async def fake_durable_read(identity, **kw):
        return dstate.EnvelopeRead(status="missing", tier="durable")

    monkeypatch.setattr(ds, "read_snapshot_standalone", fake_durable_read)
    return pc, captured


class TestSameGenerationPublication:
    @pytest.mark.asyncio
    async def test_the_block_is_judged_and_published_in_the_curves_bytes(self, wrapper, monkeypatch):
        pc, captured = wrapper
        calls = []

        async def fake_build(*, generated_at=None, as_of=None, deadline_s=None):
            calls.append(generated_at)
            return _assemble(_events(3), _improving_rows(3)) | {"published_with_generated_at": generated_at}

        monkeypatch.setattr(cpp, "build_paired_accuracy", fake_build)
        summary = await pc._run_calibration_main_build()

        assert summary["status"] == "ok"
        assert calls == ["2026-10-01T17:00:00+00:00"]
        redis_payload = json.loads(captured["redis_json"])
        for payload in (captured["gate_saw"], captured["durable_payload"], redis_payload):
            block = payload["paired_accuracy"]
            assert block["schema"] == cpp.SCHEMA
            assert block["published_with_generated_at"] == payload["generated_at"]
        assert captured["durable_payload"] == redis_payload
        envelope = captured["envelope"]
        from app.utils import durable_state as dstate

        assert envelope.checksum == dstate.checksum_payload(envelope.payload)
        assert envelope.generated_at == datetime(2026, 10, 1, 17, tzinfo=timezone.utc)

    @pytest.mark.asyncio
    async def test_the_samples_own_clock_is_not_the_curves(self, wrapper, monkeypatch):
        """The real builder over a stubbed session: collected_at is its own instant."""
        import app.tasks.base as base

        pc, captured = wrapper
        build_ctx = base.get_task_session
        session = _Session([[], [], _events(3), _ids(6), _improving_rows(3)])

        def factory(**kw):
            if kw.get("statement_timeout_ms") == cpp.STATEMENT_TIMEOUT_MS:
                return _session_factory(session, {})(**kw)
            return build_ctx(**kw)

        monkeypatch.setattr(base, "get_task_session", factory)
        await pc._run_calibration_main_build()

        payload = json.loads(captured["redis_json"])
        block = payload["paired_accuracy"]
        assert block["status"] == cpp.STATUS_AVAILABLE
        assert block["published_with_generated_at"] == payload["generated_at"]
        assert block["collector"]["collected_at"] != payload["generated_at"]
        assert "staged_at" not in json.dumps(block)

    @pytest.mark.asyncio
    async def test_a_broken_producer_cannot_block_the_curve(self, wrapper, monkeypatch):
        """The real builder, its session failing: the curve still publishes."""
        import app.tasks.base as base

        pc, captured = wrapper
        build_ctx = base.get_task_session

        def session(**kw):
            if kw.get("statement_timeout_ms") == cpp.STATEMENT_TIMEOUT_MS:
                raise RuntimeError("pool exhausted")
            return build_ctx(**kw)

        monkeypatch.setattr(base, "get_task_session", session)
        summary = await pc._run_calibration_main_build()

        assert summary["status"] == "ok"
        block = json.loads(captured["redis_json"])["paired_accuracy"]
        assert block["status"] == cpp.STATUS_UNAVAILABLE and block["reason"] == cpp.REASON_FAILED
        assert block["market"] is None

    def test_the_stamp_precedes_the_gate_and_serialisation(self):
        from app.tasks import precompute_calibration as pc

        source = inspect.getsource(pc._run_calibration_main_build)
        stamp = source.index("response[PAIRED_ACCURACY_KEY] = await build_paired_accuracy(")
        assert source.index("runner.begin(PHASE_PUBLISH)") < stamp
        assert stamp < source.index('with runner.stage("baseline_read")')
        assert stamp < source.index("evaluate_publish(")
        assert stamp < source.index("payload_json = json.dumps(response)")
        assert stamp < source.index("DurableEnvelope.build(")


# ---------------------------------------------------------------------------
# The bank survives; no GET-time SQL
# ---------------------------------------------------------------------------


class TestTheBankAndTheRouteAreUntouched:
    def test_the_build_input_fingerprint_does_not_move(self):
        from app.tasks import precompute_calibration as pc

        prints = (
            pc._main_input_fingerprint,
            pc.population_predicate_fingerprint,
            pc.staged_unit_fingerprint,
        )
        before = [fn() for fn in prints]
        cpp.event_selection_sql()
        cpp.candidate_ids_sql()
        kernel.paired_legs_sql(outcome_ids=":outcome_ids")
        assert [fn() for fn in prints] == before

        hashed = "".join(
            inspect.getsource(fn)
            for fn in (
                pc.compute_calibration_payload,
                pc._calibration_population_ctes,
                pc._virtual_market_ctes,
                pc._main_futures_sql,
                pc._roster_pushdown_predicates,
                pc._main_input_fingerprint,
            )
        )
        for symbol in ("paired_accuracy", "calibration_paired", "PAIRED_ACCURACY_KEY"):
            assert symbol not in hashed, f"{symbol} reached a fingerprinted function"

    def test_the_route_runs_no_paired_query(self):
        import app.routes.calibration as route

        source = inspect.getsource(route)
        assert "calibration_paired_publication" not in source
        assert "paired_legs_sql" not in source


class TestTheRouteServesTheBlockFromTheCacheOnly:
    """GET never computes; whatever tier answers carries the block verbatim."""

    @pytest.fixture(autouse=True)
    def _fresh_route_process(self):
        from tests.test_calibration_availability_envelope_324 import _fresh_process

        yield from _fresh_process.__wrapped__()

    def _payload_with_block(self):
        from tests.test_calibration_availability_envelope_324 import _payload

        payload = _payload()
        payload["paired_accuracy"] = _assemble(_events(3), _improving_rows(3)) | {
            "published_with_generated_at": payload["generated_at"]
        }
        return payload

    @pytest.mark.asyncio
    async def test_the_redis_main_tier(self, monkeypatch, healthy_staged_bank):
        from app.routes import calibration
        from tests.test_calibration_availability_envelope_324 import _FakeRedis, _no_compute, _use

        payload = self._payload_with_block()
        _use(monkeypatch, _FakeRedis(main=json.dumps(payload)))
        _no_compute(monkeypatch)

        out = await calibration.public_calibration(db=object())
        assert out["paired_accuracy"] == json.loads(json.dumps(payload["paired_accuracy"]))

    @pytest.mark.asyncio
    async def test_the_durable_tier(self, monkeypatch):
        from app.routes import calibration
        from tests.test_calibration_availability_envelope_324 import (
            _DeadRedis,
            _durable_db,
            _no_compute,
            _use,
        )

        payload = self._payload_with_block()
        _use(monkeypatch, _DeadRedis())
        _no_compute(monkeypatch)

        out = await calibration.public_calibration(db=_durable_db(payload))
        assert out["provenance"]["source"] == "durable"
        assert out["paired_accuracy"] == payload["paired_accuracy"]
