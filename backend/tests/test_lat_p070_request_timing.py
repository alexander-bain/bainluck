"""Guards for the router-queue / app / DB split (#1917, LAT-P070).

This instrument was built because LAT-P069 **measured** that the golf probe's
premise was false: `X-Request-Start` had 0 hits in `backend/app/` and
`debug_timing` 0 hits in `routes/golf.py`, so both terms of the requested split
were unreachable and "the header is free" was not the same claim as "the
measurement is free".

The registered prediction these guards protect (LAT-P069 §4): of the ~12.8 s p90
excess on `/api/golf/tournaments/{slug}`, **DB > 70 %**, app 10–25 %, **router
< 10 %**, with a HALT at router > 30 %. A prediction graded against a broken
instrument is worse than no read, so what is pinned here is the instrument's
*honesty* — units, unusable-vs-zero, and the propagation mechanism — never a
wall-clock number. LAT-P005's lesson stands: a timing assertion in CI is the
canonical guard that goes red on a correct change.

No local Postgres exists in this sandbox, so the DB-listener proofs run against
a real **sqlite** engine and against SQLAlchemy's own `greenlet_spawn`. Both are
the actual mechanisms, not descriptions of them.
"""

from __future__ import annotations

import math

import pytest
from sqlalchemy import create_engine, text

from app.utils.latency_stats import build_slow_event, parse_slow_event
from app.utils.request_timing import (
    MAX_CLOCK_SKEW_S,
    MAX_PLAUSIBLE_QUEUE_S,
    REQUEST_START_HEADER,
    SPLIT_HEADER,
    DbTiming,
    begin_db_timing,
    build_split,
    current_db_timing,
    end_db_timing,
    format_split_header,
    install_request_db_timer,
    parse_request_start,
    record_query,
    router_queue_ms,
)

NOW = 1_787_000_000.0  # a fixed, plausible 2026 epoch second — never the wall clock


@pytest.fixture
def timing_ctx():
    """A request-scoped accumulator, always torn down."""
    token = begin_db_timing()
    try:
        yield current_db_timing()
    finally:
        end_db_timing(token)


class TestParseRequestStart:
    """A unit misread is a 1000x error in the one number the probe publishes."""

    def test_heroku_milliseconds(self):
        assert parse_request_start("1787000000123") == pytest.approx(NOW + 0.123)

    def test_t_prefixed_form(self):
        assert parse_request_start("t=1787000000123") == pytest.approx(NOW + 0.123)

    def test_plain_seconds(self):
        assert parse_request_start("1787000000.5") == pytest.approx(NOW + 0.5)

    def test_microseconds(self):
        assert parse_request_start("1787000000123456") == pytest.approx(NOW + 0.123456)

    def test_chained_proxy_list_takes_the_outermost_hop(self):
        # `t=A, t=B` — A is the first proxy to see the request, so A is the one
        # that bounds the true queue. Taking B would under-report it.
        assert parse_request_start("t=1787000000000, t=1787000005000") == pytest.approx(NOW)

    def test_bytes_are_accepted(self):
        assert parse_request_start(b"1787000000000") == pytest.approx(NOW)

    def test_numeric_input_is_accepted(self):
        assert parse_request_start(1787000000000) == pytest.approx(NOW)

    @pytest.mark.parametrize(
        "bad",
        [None, "", "   ", "abc", "t=", "t=abc", "nan", "inf", "-inf", "0", "-5", [], {}],
    )
    def test_unusable_is_none_never_a_number(self, bad):
        # `None` is the whole point: gotcha #53. A caller handed 0.0 concludes
        # "the router took no time"; a caller handed None knows it cannot say.
        assert parse_request_start(bad) is None

    def test_a_1970_timestamp_is_refused_not_scaled(self):
        # 12345 is not a plausible epoch in any unit this fleet emits. Scaling it
        # by guesswork would mint a 56-year queue.
        assert parse_request_start("12345") is None


class TestRouterQueueMs:
    def test_a_real_queue(self):
        assert router_queue_ms("1787000000000", now=NOW + 1.5) == pytest.approx(1500.0)

    def test_absent_header_is_unusable(self):
        assert router_queue_ms(None, now=NOW) is None

    def test_small_negative_delta_is_clock_skew_and_clamps_to_zero(self):
        # LAT-P068's S4 capture measured ~5.2 s of skew between two clocks in
        # this same system. A router stamp a second "in the future" is that, not
        # a time machine.
        assert router_queue_ms("1787000001000", now=NOW) == 0.0

    def test_large_negative_delta_is_refused_not_clamped(self):
        far_future = NOW + MAX_CLOCK_SKEW_S + 60
        assert router_queue_ms(str(int(far_future * 1000)), now=NOW) is None

    def test_implausibly_old_header_is_refused(self):
        stale = NOW - (MAX_PLAUSIBLE_QUEUE_S + 60)
        assert router_queue_ms(str(int(stale * 1000)), now=NOW) is None

    def test_the_bound_sits_well_above_the_phenomenon(self):
        # The worst golf observation on record is 26.714 s. A bound that censored
        # a real 30 s queue would delete the finding it exists to catch.
        assert MAX_PLAUSIBLE_QUEUE_S > 10 * 26.714
        assert router_queue_ms(str(int((NOW - 30) * 1000)), now=NOW) == pytest.approx(30_000.0)


class TestDbTimingAccumulator:
    def test_records_sum_count_and_max(self):
        acc = DbTiming()
        acc.record(10.0)
        acc.record(250.0)
        acc.record(5.0)
        assert acc.queries == 3
        assert acc.total_ms == pytest.approx(265.0)
        # One 250 ms query and 25 x 10 ms queries are different bugs with
        # different owners; a sum alone cannot tell them apart.
        assert acc.max_query_ms == pytest.approx(250.0)

    @pytest.mark.parametrize("bad", [-1.0, float("nan"), float("inf")])
    def test_refuses_impossible_durations(self, bad):
        acc = DbTiming()
        acc.record(bad)
        assert acc.queries == 0
        assert acc.total_ms == 0.0

    def test_record_query_outside_a_request_is_a_no_op(self):
        # Celery tasks share the process-wide listener. "No accumulator" is how
        # background DB work stays out of a user's request timing.
        assert current_db_timing() is None
        record_query(500.0)  # must not raise
        assert current_db_timing() is None

    def test_end_tolerates_a_foreign_token(self, timing_ctx):
        # BaseHTTPMiddleware can run dispatch and the downstream app in different
        # contexts; a reset that raises would leak the accumulator into the next
        # request this worker serves.
        other = begin_db_timing()
        end_db_timing(other)
        end_db_timing(other)  # already reset — must not raise


class TestBuildSplit:
    def test_app_is_the_residual_and_the_terms_reconcile(self):
        split = build_split(
            wall_ms=1000.0, db=_acc(total_ms=800.0, queries=12), router_ms=50.0
        )
        assert split["db_ms"] == 800.0
        assert split["app_ms"] == 200.0
        # wall = app + db. router is NOT inside wall — the app cannot observe
        # time it did not yet have the request for.
        assert split["app_ms"] + split["db_ms"] == pytest.approx(split["wall_ms"])
        assert split["edge_ms"] == pytest.approx(1050.0)
        assert split["db_share"] == pytest.approx(0.8)

    def test_router_is_never_folded_into_wall(self):
        # The failure this pins: a reader adding all four terms and reporting a
        # router share that arithmetic invented.
        split = build_split(wall_ms=1000.0, db=_acc(total_ms=1000.0), router_ms=9000.0)
        assert split["wall_ms"] == 1000.0
        assert split["db_share"] == pytest.approx(1.0)

    def test_db_over_wall_is_reported_not_hidden(self):
        # Concurrent statements on one request genuinely overlap. Clamping db to
        # wall would erase a real concurrency finding.
        split = build_split(wall_ms=100.0, db=_acc(total_ms=250.0), router_ms=None)
        assert split["db_ms"] == 250.0
        assert split["app_ms"] == 0.0  # residual floored, never negative
        assert split["db_share"] == pytest.approx(1.0)

    def test_no_router_reading_yields_none_not_zero(self):
        split = build_split(wall_ms=100.0, db=_acc(total_ms=10.0), router_ms=None)
        assert split["router_queue_ms"] is None
        assert split["edge_ms"] is None

    def test_no_queries_is_a_finding_not_a_gap(self):
        split = build_split(wall_ms=100.0, db=DbTiming(), router_ms=None)
        assert split["queries"] == 0
        assert split["db_ms"] == 0.0
        assert split["app_ms"] == 100.0

    def test_missing_accumulator_does_not_crash_the_split(self):
        split = build_split(wall_ms=100.0, db=None, router_ms=None)
        assert split["db_ms"] == 0.0 and split["app_ms"] == 100.0


class TestSplitHeaderFormat:
    def test_unusable_router_renders_na_never_zero(self):
        header = format_split_header(
            build_split(wall_ms=100.0, db=_acc(total_ms=10.0), router_ms=None)
        )
        assert "router=na" in header
        assert "router=0" not in header

    def test_a_real_router_reading_renders_the_number(self):
        header = format_split_header(
            build_split(wall_ms=100.0, db=_acc(total_ms=10.0), router_ms=42.4)
        )
        assert "router=42.4" in header

    def test_carries_every_term_the_prediction_is_graded_on(self):
        header = format_split_header(
            build_split(wall_ms=1000.0, db=_acc(total_ms=800.0, queries=12), router_ms=5.0)
        )
        for term in ("wall=", "db=", "app=", "q=", "maxq=", "router="):
            assert term in header


class TestSlowEventCarriesTheSplit:
    def test_round_trip_preserves_the_attribution(self):
        split = build_split(
            wall_ms=15260.0, db=_acc(total_ms=12000.0, queries=40), router_ms=120.0
        )
        rec = parse_slow_event(
            build_slow_event(
                timestamp=NOW,
                path="/api/golf/tournaments/{slug}",
                duration_ms=15260.0,
                cache_bucket="miss",
                split=split,
            )
        )
        assert rec["db_ms"] == 12000.0
        assert rec["app_ms"] == 3260.0
        assert rec["router_queue_ms"] == 120.0
        assert rec["queries"] == 40

    def test_unusable_router_survives_as_null_not_as_absent(self):
        split = build_split(wall_ms=9000.0, db=_acc(total_ms=8000.0), router_ms=None)
        rec = parse_slow_event(
            build_slow_event(
                timestamp=NOW, path="/api/feed", duration_ms=9000.0,
                cache_bucket="miss", split=split,
            )
        )
        assert "router_queue_ms" in rec
        assert rec["router_queue_ms"] is None

    def test_legacy_events_without_a_split_still_parse(self):
        rec = parse_slow_event(
            build_slow_event(
                timestamp=NOW, path="/api/feed", duration_ms=9000.0, cache_bucket="miss"
            )
        )
        assert rec["ms"] == 9000.0
        assert "db_ms" not in rec


class TestEngineListener:
    """The listener wiring, against a real engine rather than a mock of one."""

    def test_real_queries_accumulate(self, timing_ctx):
        engine = create_engine("sqlite://")
        assert install_request_db_timer(engine) is True
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            conn.execute(text("SELECT 2"))
        acc = current_db_timing()
        assert acc.queries == 2
        assert acc.total_ms > 0
        assert acc.unfinished == 0

    def test_install_is_idempotent(self, timing_ctx):
        engine = create_engine("sqlite://")
        assert install_request_db_timer(engine) is True
        # A second install returning True would double-count every query in the
        # fleet, and the doubling would look exactly like real contention.
        assert install_request_db_timer(engine) is False
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        assert current_db_timing().queries == 1

    def test_queries_outside_a_request_are_not_attributed(self):
        engine = create_engine("sqlite://")
        install_request_db_timer(engine)
        assert current_db_timing() is None
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        # Nothing to attribute to, and nothing raised.
        assert current_db_timing() is None

    def test_an_async_engine_is_unwrapped_to_its_sync_engine(self):
        # install() must reach `.sync_engine`; attaching to the AsyncEngine
        # wrapper would silently never fire.
        class _FakeAsync:
            def __init__(self, inner):
                self.sync_engine = inner

        inner = create_engine("sqlite://")
        assert install_request_db_timer(_FakeAsync(inner)) is True
        assert install_request_db_timer(inner) is False  # same engine, already marked


class TestContextPropagation:
    """Both boundaries the accumulator crosses, measured against the real thing.

    The first draft of the module docstring blamed the greenlet for requiring a
    mutable accumulator. These guards refuted that: the greenlet shares the
    Context outright, and it is the **asyncio task** boundary inside
    `BaseHTTPMiddleware` that actually forces the design. The wrong reason is
    kept out of the code, and the right one is pinned here.
    """

    async def test_a_mutation_inside_greenlet_spawn_is_visible_outside(self, timing_ctx):
        from sqlalchemy.util.concurrency import greenlet_spawn

        def _inside_the_driver():
            record_query(37.5)
            record_query(2.5)

        await greenlet_spawn(_inside_the_driver)

        acc = current_db_timing()
        assert acc.queries == 2
        assert acc.total_ms == pytest.approx(40.0)

    async def test_greenlet_spawn_shares_the_context_on_the_pinned_versions(self, timing_ctx):
        # MEASURED, and deliberately NOT depended on: a rebind inside the
        # greenlet DOES propagate out here (SQLAlchemy 2.0.50 / greenlet 3.5.1).
        # Recorded so the next reader does not re-derive it, and so a library
        # change that flips it is announced by a red test rather than by a
        # silently wrong `db_ms`.
        from sqlalchemy.util.concurrency import greenlet_spawn

        outer = current_db_timing()

        def _rebind():
            begin_db_timing()
            record_query(999.0)

        await greenlet_spawn(_rebind)
        assert current_db_timing() is not outer
        assert outer.total_ms == 0.0

    async def test_a_rebind_across_an_asyncio_task_does_NOT_propagate(self, timing_ctx):
        # THIS is the boundary `call_next` crosses, and this is why the
        # accumulator must be mutated rather than rebound. A rebind here loses
        # every query — and it would under-report DB time, i.e. falsely clear
        # the database of the golf tail.
        import asyncio

        outer = current_db_timing()

        async def _rebind_downstream():
            begin_db_timing()
            record_query(999.0)

        await asyncio.create_task(_rebind_downstream())
        assert current_db_timing() is outer
        assert outer.total_ms == 0.0

    async def test_a_mutation_across_an_asyncio_task_DOES_propagate(self, timing_ctx):
        import asyncio

        async def _query_downstream():
            record_query(12.0)

        await asyncio.create_task(_query_downstream())
        assert current_db_timing().total_ms == pytest.approx(12.0)


class TestMiddlewareIntegration:
    """End to end through Starlette, because the ContextVar crosses a task there."""

    @staticmethod
    def _client(handler=None, **kwargs):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from app.middleware.latency import LatencyMiddleware

        app = FastAPI()
        app.add_middleware(LatencyMiddleware)

        @app.get("/api/probe")
        async def _probe():  # pragma: no cover - exercised through the client
            if handler is not None:
                handler()
            return {"ok": True}

        return TestClient(app, **kwargs)

    def test_the_split_header_is_emitted(self):
        resp = self._client().get("/api/probe")
        assert resp.status_code == 200
        assert SPLIT_HEADER.lower() in {k.lower() for k in resp.headers}
        header = resp.headers[SPLIT_HEADER]
        assert "wall=" in header and "db=" in header and "app=" in header

    def test_a_router_stamp_is_read_and_reported(self):
        import time as _time

        stamp = str(int((_time.time() - 0.25) * 1000))
        resp = self._client().get("/api/probe", headers={REQUEST_START_HEADER: stamp})
        header = resp.headers[SPLIT_HEADER]
        assert "router=na" not in header
        router = float(header.split("router=")[1].split(";")[0])
        # Bounded, not exact: a wall-clock equality assertion is the guard that
        # goes red on a correct change. 250 ms was stamped; anything from there
        # to a slow CI second is a correct reading.
        assert 100.0 <= router <= 5000.0

    def test_no_router_stamp_reports_na(self):
        resp = self._client().get("/api/probe")
        assert "router=na" in resp.headers[SPLIT_HEADER]

    def test_db_work_inside_the_request_is_attributed(self):
        engine = create_engine("sqlite://")
        install_request_db_timer(engine)

        def _do_queries():
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
                conn.execute(text("SELECT 2"))
                conn.execute(text("SELECT 3"))

        resp = self._client(handler=_do_queries).get("/api/probe")
        header = resp.headers[SPLIT_HEADER]
        # The whole point of the instrument: the queries the request actually
        # ran are counted against the request that ran them, across the
        # BaseHTTPMiddleware task boundary.
        assert "q=3" in header

    def test_the_rail_never_fails_a_request(self, monkeypatch):
        import app.utils.request_timing as rt

        def _boom(*a, **k):
            raise RuntimeError("instrument exploded")

        monkeypatch.setattr(rt, "router_queue_ms", _boom)
        monkeypatch.setattr(rt, "build_split", _boom)
        resp = self._client().get("/api/probe")
        # Observability must never be the reason a user's request fails.
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}

    def test_the_kill_switch_removes_the_header(self, monkeypatch):
        import app.middleware.latency as mod

        monkeypatch.setattr(mod, "TIMING_SPLIT_ENABLED", False)
        resp = self._client().get("/api/probe")
        assert SPLIT_HEADER.lower() not in {k.lower() for k in resp.headers}

    def test_non_api_paths_are_untouched(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from app.middleware.latency import LatencyMiddleware

        app = FastAPI()
        app.add_middleware(LatencyMiddleware)

        @app.get("/healthz")
        async def _h():  # pragma: no cover
            return {"ok": True}

        resp = TestClient(app).get("/healthz")
        assert SPLIT_HEADER.lower() not in {k.lower() for k in resp.headers}


class TestWiring:
    """Guards that the instrument stays connected to the thing it measures."""

    def test_the_engine_timer_is_installed_at_startup(self):
        import inspect

        import app.main as main

        source = inspect.getsource(main.lifespan)
        # The CALL, not the name. A mutation that replaced the call with `pass`
        # left the `from ... import install_request_db_timer` line in place, so a
        # bare substring check stayed green against a startup that installed
        # nothing — the guard agreed with the defect (ruling 072's shape).
        assert "install_request_db_timer(" in source, (
            "the DB half of the split is a no-op unless the listener is attached "
            "to the request path's engine at startup"
        )
        assert "from app.services.database import engine" in source, (
            "installing the timer on any engine other than the request path's is "
            "a rail that measures nothing"
        )

    def test_the_middleware_reads_the_header_before_call_next(self):
        import inspect

        from app.middleware.latency import LatencyMiddleware

        source = inspect.getsource(LatencyMiddleware.dispatch)
        header_at = source.index("router_queue_ms(")
        # rindex, not index: dispatch's FIRST `await call_next(request)` is the
        # early return for non-/api paths, which the timing block correctly sits
        # after. Anchoring on that one made this guard pass for the wrong reason.
        call_at = source.rindex("await call_next(request)")
        assert source.count("await call_next(request)") == 2
        # Reading the stamp after the handler ran would fold the app's own
        # service time into "queue time" — the exact mis-attribution the HALT
        # condition (router > 30 % of the excess) is graded on.
        assert header_at < call_at

    def test_the_prediction_and_its_halt_are_registered_in_the_docs(self):
        from pathlib import Path

        doc = Path(__file__).resolve().parents[2] / "docs/audits/latency/lat-p069-turbo-collapse-budget.md"
        text_ = doc.read_text()
        # A probe whose prediction is registered AFTER the read is not a
        # prediction. This pins that the registration outlives a refactor.
        assert "HALT: router-queue time > 30 %" in text_
        assert "> 70 %" in text_


def _acc(*, total_ms: float = 0.0, queries: int = 1, max_query_ms: float | None = None):
    acc = DbTiming()
    acc.total_ms = total_ms
    acc.queries = queries
    acc.max_query_ms = total_ms if max_query_ms is None else max_query_ms
    return acc


def test_no_non_finite_can_reach_the_header():
    # allow_nan=False in build_slow_event raises on a NaN, which would take out
    # the tail ring write for the very request worth keeping.
    split = build_split(wall_ms=float("nan"), db=None, router_ms=None)
    assert math.isfinite(split["wall_ms"])
    build_slow_event(
        timestamp=NOW, path="/api/feed", duration_ms=1.0, cache_bucket="miss", split=split
    )
