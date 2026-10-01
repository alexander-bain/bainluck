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

import inspect
import json
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
        assert kernel.paired_legs_sql() == kernel.paired_legs_sql(event_ids=None)
        assert "fm.event_id IN" not in kernel.paired_legs_sql()

    def test_supplied_it_adds_one_and_clause_and_nothing_else(self):
        bare = kernel.paired_legs_sql()
        filtered = kernel.paired_legs_sql(event_ids=":event_ids")
        added = "\n  AND fm.event_id IN :event_ids"
        assert filtered.count(added) == 1
        assert filtered.replace(added, "") == bare

    def test_the_feasibility_walk_is_unchanged(self):
        assert "fm.event_id IN" not in kernel.paired_feasibility_sql()


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
        for sql in (cpp.event_selection_sql(), kernel.paired_legs_sql(event_ids=":event_ids")):
            assert "fo.is_winner IS NOT NULL" in sql
            assert predicate in sql
            assert "fm.status = 'resolved'" in sql

    def test_event_selection_requires_a_reported_start_and_a_total_order(self):
        sql = cpp.event_selection_sql()
        assert kernel.start_is_reported_sql() in sql
        assert "e.commence_time_source IS NOT NULL" in sql
        assert sql.count("ORDER BY e.commence_time DESC, e.id DESC") == 1
        assert "ORDER BY ev.commence_time DESC, ev.id DESC" in sql


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


class TestTheBoundedSession:
    @pytest.mark.asyncio
    async def test_it_reads_one_read_only_snapshot_at_five_seconds(self, monkeypatch):
        import app.tasks.base as base

        events = _events(2) + [{"event_id": 7, "commence_time": T0 - 7 * H, "n_candidates": 4000}]
        session = _Session([[], events, _improving_rows(2)])
        seen: dict = {}
        monkeypatch.setattr(base, "get_task_session", _session_factory(session, seen))

        block = await cpp.build_paired_accuracy(generated_at="GEN", as_of=T0 + 48 * H)

        assert seen["kwargs"] == {"statement_timeout_ms": 5000}
        assert session.calls[0][0] == "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"
        assert session.calls[1][1] == {"as_of": T0 + 48 * H, "event_limit": 101}
        legs_params = session.calls[2][1]
        assert legs_params["event_ids"] == [1000, 1001]
        assert legs_params["scan"] == 2001 and legs_params["cursor"] == 0
        assert block["status"] == cpp.STATUS_INCOMPLETE
        assert block["generation_generated_at"] == "GEN"

    @pytest.mark.asyncio
    async def test_no_events_runs_no_legs_query(self, monkeypatch):
        import app.tasks.base as base

        session = _Session([[], []])
        monkeypatch.setattr(base, "get_task_session", _session_factory(session, {}))
        block = await cpp.build_paired_accuracy()
        assert len(session.calls) == 2
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

        session = _Session([[], _events(2)], raise_on=(3, exc))
        seen: dict = {}
        monkeypatch.setattr(base, "get_task_session", _session_factory(session, seen))

        block = await cpp.build_paired_accuracy(generated_at="GEN")

        assert seen["exit_exc"] is type(exc), "the session never saw the failure"
        assert block["status"] == cpp.STATUS_UNAVAILABLE and block["reason"] == reason
        assert block["market"] is None and block["model"] is None and block["sample"] is None
        assert block["generation_generated_at"] == "GEN"


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
    monkeypatch.setattr(gate, "_parse_generated_at", lambda s: None)

    def fake_envelope(**kw):
        captured["durable_payload"] = json.loads(json.dumps(kw["payload"]))
        return SimpleNamespace(generation=1)

    monkeypatch.setattr(dstate, "DurableEnvelope", SimpleNamespace(build=fake_envelope))

    async def fake_publish(envelope):
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

        async def fake_build(*, generated_at=None, as_of=None):
            calls.append(generated_at)
            return _assemble(_events(3), _improving_rows(3)) | {"generation_generated_at": generated_at}

        monkeypatch.setattr(cpp, "build_paired_accuracy", fake_build)
        summary = await pc._run_calibration_main_build()

        assert summary["status"] == "ok"
        assert calls == ["2026-10-01T17:00:00+00:00"]
        redis_payload = json.loads(captured["redis_json"])
        for payload in (captured["gate_saw"], captured["durable_payload"], redis_payload):
            block = payload["paired_accuracy"]
            assert block["schema"] == cpp.SCHEMA
            assert block["generation_generated_at"] == payload["generated_at"]
        assert captured["durable_payload"] == redis_payload

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

        before = pc._main_input_fingerprint()
        cpp.event_selection_sql()
        kernel.paired_legs_sql(event_ids=":event_ids")
        assert pc._main_input_fingerprint() == before

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
