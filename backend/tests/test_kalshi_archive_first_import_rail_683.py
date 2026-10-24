"""#683 first attended import rail: the operational bounds, proven without a server.

PILLAR: TRUTH. SHIP: a settled Kalshi question with missing history gains its
real recoverable older probability journey on web and native, with explicit
archive provenance.

What these cases hold (the real-Postgres half — startup settings across commit
and reconnect, the 500 ms lock bound, the identity fence, lost COMMIT
acknowledgements, restore — is in ``tests/integration/test_kalshi_archive_store_683_pg.py``):

* strict stop-on-first-429: zero extra requests, ``Retry-After: 0`` included,
  and an unreadable shared cooldown refuses instead of proceeding;
* response bytes are counted while streamed, before buffering: declared,
  streamed and run-total overflows stop HELD, never as an absence or a 429;
* the planner's deadline is inclusive of the database read, cancelling a
  request that ignores cancellation, and closing the client;
* console and artifact caps are active, and an over-cap artifact is never
  written; a held, overflowing or wall-cut run never exits 0;
* the importer refuses a plan larger than the invocation named, never calls a
  partial or zero-point plan ``applied``, and reports a COMMIT whose answer was
  lost as uncertain, never as nothing written.

Every provider and database edge is a fake or an ``httpx.MockTransport``.
"""

from __future__ import annotations

import asyncio
import gc
import inspect
import json
import subprocess
import sys
import textwrap
import time
from pathlib import Path
from contextlib import asynccontextmanager, contextmanager
from types import SimpleNamespace

import httpx
import pytest

from app.services import kalshi_archive_apply as imp
from app.services import kalshi_archive_bounds as bounds
from app.services import kalshi_archive_recovery as rec
from app.services.kalshi_api import KalshiAPIService
from tests.test_kalshi_archive_recovery_683 import (
    E1,
    T1,
    T2,
    TIPOFF,
    Clock,
    FakeService,
    FakeSession,
    _429,
    _good_candles,
    _listed,
    _plan,
    _row,
    candle,
)
from tests.test_kalshi_archive_store_683 import _load_script

CUTOFF_BODY = {"market_settled_ts": "2026-08-16T00:00:00Z"}


def _candle_calls(svc):
    return [c for c in svc.calls if c[0] == "candles"]


def _real_service(handler) -> KalshiAPIService:
    svc = KalshiAPIService(api_key="")
    svc.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return svc


class _Streamed(httpx.AsyncByteStream):
    """A body that arrives as a stream, like a network response (not pre-read)."""

    def __init__(self, blob: bytes, chunk: int = 64):
        self.blob, self.chunk = blob, chunk

    async def __aiter__(self):
        for i in range(0, len(self.blob), self.chunk):
            yield self.blob[i : i + self.chunk]


def _json_stream(body, status=200, headers=None):
    blob = json.dumps(body).encode()
    return httpx.Response(
        status,
        headers={"Content-Type": "application/json", **(headers or {})},
        stream=_Streamed(blob),
    )


def _archive_handler(seen, *, candles=None, listing=None):
    """Answers the three archive routes like Kalshi's documented bodies, streamed."""

    def handler(request: httpx.Request):
        seen.append(request)
        path = request.url.path
        if path.endswith("/historical/cutoff"):
            return _json_stream(CUTOFF_BODY)
        if path.endswith("/historical/markets"):
            return _json_stream(listing or {"cursor": "", "markets": [_listed(T1, E1)]})
        return _json_stream(
            {"ticker": T1, "candlesticks": _good_candles() if candles is None else candles}
        )

    return handler


def _factory(session):
    @asynccontextmanager
    async def factory():
        yield session

    return factory


# ── the session bound ──────────────────────────────────────────────────────


class TestSessionBound:
    def test_both_default_factories_open_the_bounded_archive_session(self, monkeypatch):
        seen = []

        @asynccontextmanager
        async def fake_task_session(**kw):
            seen.append(kw)
            yield SimpleNamespace()

        monkeypatch.setattr("app.tasks.base.get_task_session", fake_task_session)
        for factory in (rec._default_session_factory, imp._default_session_factory):
            cm = factory()
            assert cm.__class__.__name__ == "_AsyncGeneratorContextManager"
            assert cm.gen.__qualname__ == "archive_session"
        assert bounds.ARCHIVE_STATEMENT_TIMEOUT_MS == 10_000
        assert bounds.ARCHIVE_LOCK_TIMEOUT_MS == 500

    async def test_the_session_asks_for_both_bounds_and_verifies_them(self, monkeypatch):
        seen, executed = [], []

        class S:
            async def execute(self, clause, params=None):
                executed.append(str(clause))
                return SimpleNamespace(
                    fetchall=lambda: [("statement_timeout", "10000"), ("lock_timeout", "500")]
                )

        @asynccontextmanager
        async def fake_task_session(**kw):
            seen.append(kw)
            yield S()

        monkeypatch.setattr("app.tasks.base.get_task_session", fake_task_session)
        async with bounds.archive_session():
            pass
        assert seen == [{"statement_timeout_ms": 10_000, "lock_timeout_ms": 500}]
        assert executed == [bounds.SESSION_BUDGET_SQL]

    @pytest.mark.parametrize(
        "rows",
        [
            [("statement_timeout", "1800000"), ("lock_timeout", "0")],  # house default
            [("statement_timeout", "10000"), ("lock_timeout", "0")],
            [("statement_timeout", "10000")],
            [],
        ],
    )
    async def test_an_unarmed_session_is_refused_before_any_work(self, rows):
        class S:
            async def execute(self, clause, params=None):
                return SimpleNamespace(fetchall=lambda: rows)

        with pytest.raises(bounds.ArchiveSessionUnarmed):
            await bounds.verify_session_budget(S())

    def test_the_bounds_ride_the_connection_startup_channel(self):
        from app.services.database import build_connect_args

        url = "postgresql+asyncpg://u@localhost/db"
        args = build_connect_args(
            url,
            statement_timeout_ms=bounds.ARCHIVE_STATEMENT_TIMEOUT_MS,
            lock_timeout_ms=bounds.ARCHIVE_LOCK_TIMEOUT_MS,
        )
        assert args["server_settings"] == {"statement_timeout": "10000", "lock_timeout": "500"}

    def test_no_global_default_changed(self):
        from app.services.database import DB_STATEMENT_TIMEOUT_MS, build_connect_args
        from app.tasks.base import get_task_session

        args = build_connect_args("postgresql+asyncpg://u@localhost/db")
        assert args["server_settings"] == {"statement_timeout": str(DB_STATEMENT_TIMEOUT_MS)}
        sig = inspect.signature(get_task_session)
        assert sig.parameters["statement_timeout_ms"].default is None
        assert sig.parameters["lock_timeout_ms"].default is None

    def test_no_bare_set_of_either_guc_in_the_rail(self):
        for mod in (rec, imp, bounds):
            src = inspect.getsource(mod).upper()
            assert "SET STATEMENT_TIMEOUT" not in src and "SET LOCK_TIMEOUT" not in src


# ── strict stop-on-first-429 ───────────────────────────────────────────────


class TestStrict429:
    async def test_retry_after_zero_gets_no_second_request_in_strict_mode(self):
        svc = FakeService({}, {}, script=[_429("0")])
        clock = Clock()
        report = await _plan(
            FakeSession([_row(1)]), svc, clock=clock, stop_on_first_429=True
        )
        assert svc.calls == [("cutoff",)] and report["requests_sent"] == 1
        assert report["terminal"] == "rate_limited" and report["rate_limit_waits"] == 0
        assert report["stopped_on_cooldown_s"] == 0.0 and clock.sleeps == []

    async def test_control_the_default_mode_does_retry_retry_after_zero(self):
        svc = FakeService({E1: [([_listed(T1, E1)], None)]}, {T1: _good_candles()}, script=[_429("0")])
        report = await _plan(FakeSession([_row(1)]), svc)
        assert report["rate_limit_waits"] == 1 and svc.calls[:2] == [("cutoff",), ("cutoff",)]

    async def test_a_429_mid_outcome_holds_it_with_its_carry_and_does_not_advance(self):
        svc = FakeService(
            {E1: [([_listed(T1, E1)], None)]},
            {T1: _good_candles()},
            script=[None, None, _429("0")],
        )
        report = await _plan(
            FakeSession([_row(1)]), svc, stop_on_first_429=True, max_requests=10
        )
        assert report["requests_sent"] == 3 and len(_candle_calls(svc)) == 1
        assert report["terminal"] == "rate_limited"
        assert report["held_outcome"]["outcome_id"] == 1
        assert report["held_outcome"]["stage"] == "candles"
        assert report["next_after_id"] == 0 and report["plans"] == []

    async def test_an_unreadable_shared_cooldown_refuses_with_zero_requests(self):
        svc = FakeService({}, {})
        report = await _plan(
            FakeSession([_row(1)]), svc, cooldown=None, stop_on_first_429=True
        )
        assert report["terminal"] == "cooldown_unknown" and svc.calls == []
        assert report["shared_cooldown_s"] == "unreadable"

    async def test_control_default_mode_still_proceeds_on_an_unreadable_cooldown(self):
        svc = FakeService({E1: [([_listed(T1, E1)], None)]}, {T1: _good_candles()})
        report = await _plan(FakeSession([_row(1)]), svc, cooldown=None)
        assert report["terminal"] == "complete" and svc.calls[0] == ("cutoff",)

    async def test_an_unknown_429_policy_stops_honestly(self):
        svc = FakeService({}, {}, script=[_429("5")])

        def broken(exc):
            raise RuntimeError("policy helper unavailable")

        report = await rec.plan_archive_recovery(
            session_factory=_factory(FakeSession([_row(1)])),
            service_factory=lambda: svc,
            cooldown_reader=lambda: 0.0,
            rate_limit_wait=broken,
            sleep=Clock().sleep,
            monotonic=Clock().monotonic,
            stop_on_first_429=True,
        )
        assert report["terminal"] == "rate_limited" and report["requests_sent"] == 1
        assert report["stopped_on_cooldown_s"] == "unknown"

    async def test_real_client_retry_after_zero_reaches_the_transport_once(self):
        seen = []

        def handler(request):
            seen.append(request)
            return httpx.Response(429, headers={"Retry-After": "0"})

        report = await rec.plan_archive_recovery(
            session_factory=_factory(FakeSession([_row(1)])),
            service_factory=lambda: _real_service(handler),
            cooldown_reader=lambda: 0.0,
            stop_on_first_429=True,
            byte_budget=bounds.ArchiveByteBudget(response_cap=1 << 20, total_cap=3 << 20),
            pace_seconds=0.5,
            deadline_seconds=5,
            hard_deadline_seconds=6,
        )
        assert len(seen) == 1 and report["terminal"] == "rate_limited"


# ── bytes are counted before they are buffered ────────────────────────────


def _bounded(handler, response_cap=1 << 20, total_cap=3 << 20):
    budget = bounds.ArchiveByteBudget(response_cap=response_cap, total_cap=total_cap)
    return bounds.BoundedArchiveService(_real_service(handler), budget), budget


class TestBoundedResponses:
    async def test_a_declared_oversize_body_is_refused_unread(self):
        touched = []

        async def body():
            touched.append(1)
            yield b"{}"

        svc, budget = _bounded(
            lambda r: httpx.Response(200, headers={"Content-Length": "2000000"}, content=body())
        )
        with pytest.raises(bounds.ArchiveBudgetExceeded) as info:
            await svc.get_historical_cutoff()
        assert info.value.reason == "response_bytes" and touched == []
        assert budget.received == 0

    async def test_a_streamed_oversize_body_is_abandoned_mid_stream(self):
        sent = []

        async def body():
            for _ in range(1000):
                sent.append(1)
                yield b"x" * 1024

        svc, budget = _bounded(lambda r: httpx.Response(200, content=body()), response_cap=8192)
        with pytest.raises(bounds.ArchiveBudgetExceeded) as info:
            await svc.get_historical_cutoff()
        assert info.value.reason == "response_bytes"
        assert len(sent) <= 10 and budget.received <= 8192 + 1024

    async def test_the_run_total_stops_the_response_that_crosses_it(self):
        seen = []
        svc, budget = _bounded(_archive_handler(seen), total_cap=150)
        await svc.get_historical_cutoff()
        with pytest.raises(bounds.ArchiveBudgetExceeded) as info:
            await svc.get_historical_markets(event_ticker=E1)
        assert info.value.reason == "total_bytes" and budget.received > 0

    async def test_identity_is_asked_for_and_a_compressed_answer_is_refused(self):
        seen = []

        def handler(request):
            seen.append(request.headers.get("accept-encoding"))
            return httpx.Response(200, headers={"Content-Encoding": "gzip"}, content=b"\x1f\x8b")

        svc, _ = _bounded(handler)
        with pytest.raises(bounds.ArchiveResponseRefused):
            await svc.get_historical_cutoff()
        assert seen == ["identity"]

    async def test_a_non_2xx_raises_before_any_body_is_read(self):
        touched = []

        async def body():
            touched.append(1)
            yield b"slow down"

        svc, budget = _bounded(
            lambda r: httpx.Response(429, headers={"Retry-After": "7"}, content=body())
        )
        with pytest.raises(httpx.HTTPStatusError) as info:
            await svc.get_historical_cutoff()
        from app.tasks.kalshi import _kalshi_trade_429_wait

        assert _kalshi_trade_429_wait(info.value) == 7.0 and touched == []

    async def test_an_already_buffered_body_is_still_held_to_the_caps(self):
        svc, budget = _bounded(
            lambda r: httpx.Response(200, json={"pad": "x" * 500}), response_cap=100
        )
        with pytest.raises(bounds.ArchiveBudgetExceeded) as info:
            await svc.get_historical_cutoff()
        assert info.value.reason == "response_bytes"

    async def test_the_bounded_read_parses_exactly_as_the_service_does(self):
        seen = []
        handler = _archive_handler(seen)
        plain = _real_service(handler)
        svc, _ = _bounded(handler)
        assert await svc.get_historical_cutoff() == await plain.get_historical_cutoff()
        assert await svc.get_historical_markets(event_ticker=E1, limit=999) == (
            await plain.get_historical_markets(event_ticker=E1, limit=999)
        )
        a = await svc.get_historical_market_candlesticks_payload(
            T1, period_interval=60, start_ts=1, end_ts=2
        )
        b = await plain.get_historical_market_candlesticks_payload(
            T1, period_interval=60, start_ts=1, end_ts=2
        )
        assert (a.raw_body, a.raw_sha256, a.candles, a.echoed_ticker) == (
            b.raw_body,
            b.raw_sha256,
            b.candles,
            b.echoed_ticker,
        )
        # Same routes and params on the wire.
        assert [(r.url.path, sorted(r.url.params.items())) for r in seen[0::2]] == [
            (r.url.path, sorted(r.url.params.items())) for r in seen[1::2]
        ]

    async def test_a_byte_stop_holds_the_outcome_and_is_never_a_429(self):
        # A cap of 429 bytes puts the digits "429" in the stop's own message.
        seen = []
        report = await rec.plan_archive_recovery(
            session_factory=_factory(FakeSession([_row(1), _row(2, ticker=T2)])),
            service_factory=lambda: _real_service(_archive_handler(seen)),
            cooldown_reader=lambda: 0.0,
            byte_budget=bounds.ArchiveByteBudget(response_cap=429, total_cap=3 << 20),
            sleep=Clock().sleep,
            monotonic=Clock().monotonic,
        )
        assert report["terminal"] == "partial" and report["budget_stop"] == "response_bytes"
        assert report["rate_limit_waits"] == 0 and "stopped_on_cooldown_s" not in report
        assert report["held_outcome"]["outcome_id"] == 1
        assert report["next_after_id"] == 0 and report["plans"] == []
        assert report["plan_digest"] == rec.plan_digest([])

    async def test_a_total_stop_after_a_read_window_carries_that_window(self):
        seen = []
        probe = bounds.ArchiveByteBudget(response_cap=1 << 20, total_cap=1 << 30)
        await rec.plan_archive_recovery(
            session_factory=_factory(FakeSession([_row(1)])),
            service_factory=lambda: _real_service(_archive_handler(seen)),
            cooldown_reader=lambda: 0.0,
            byte_budget=probe,
            sleep=Clock().sleep,
            monotonic=Clock().monotonic,
        )
        # A run allowed exactly what one whole run took, minus one byte.
        report = await rec.plan_archive_recovery(
            session_factory=_factory(FakeSession([_row(1)])),
            service_factory=lambda: _real_service(_archive_handler([])),
            cooldown_reader=lambda: 0.0,
            byte_budget=bounds.ArchiveByteBudget(
                response_cap=1 << 20, total_cap=probe.received - 1
            ),
            sleep=Clock().sleep,
            monotonic=Clock().monotonic,
        )
        assert report["budget_stop"] == "total_bytes"
        assert report["held_outcome"]["stage"] == "candles"
        assert report["continuation"] is None  # nothing read yet ⇒ nothing carried
        assert report["response_bytes"]["received"] <= probe.received


# ── the planner's deadline is inclusive ───────────────────────────────────


class SlowSession(FakeSession):
    def __init__(self, *a, delay=10.0, **kw):
        super().__init__(*a, **kw)
        self.delay = delay

    async def execute(self, clause, params=None):
        if "FROM futures_outcomes fo" in str(clause):
            await asyncio.sleep(self.delay)
        return await super().execute(clause, params)


class TestInclusiveDeadline:
    async def _run(self, session, svc, **kw):
        return await rec.plan_archive_recovery(
            session_factory=_factory(session),
            service_factory=lambda: svc,
            cooldown_reader=lambda: 0.0,
            pace_seconds=0.5,
            **kw,
        )

    async def test_a_slow_candidate_read_is_cancelled_and_nothing_advances(self):
        svc = FakeService({E1: [([_listed(T1, E1)], None)]}, {T1: _good_candles()})
        t0 = time.monotonic()
        report = await self._run(
            SlowSession([_row(1)]), svc, deadline_seconds=0.3, hard_deadline_seconds=0.6
        )
        assert time.monotonic() - t0 < 1.5
        assert report["terminal"] == "partial" and report["budget_stop"] == "deadline"
        assert report["candidates"] == 0 and report["next_after_id"] == 0
        assert report["plans"] == [] and svc.closed

    async def test_control_without_the_hard_deadline_the_read_is_awaited(self):
        svc = FakeService({E1: [([_listed(T1, E1)], None)]}, {T1: _good_candles()})
        report = await self._run(
            SlowSession([_row(1)], delay=0.05), svc, deadline_seconds=30
        )
        assert report["terminal"] == "complete"

    async def test_a_get_that_ignores_cancellation_is_abandoned_at_the_hard_end(self):
        class Stubborn(FakeService):
            async def get_historical_cutoff(self):
                self.calls.append(("cutoff",))
                try:
                    await asyncio.sleep(10)
                except asyncio.CancelledError:
                    await asyncio.sleep(10)  # refuses to unwind promptly
                return CUTOFF_BODY

        svc = Stubborn({}, {})
        t0 = time.monotonic()
        report = await self._run(
            FakeSession([_row(1)]), svc, deadline_seconds=0.2, hard_deadline_seconds=0.5
        )
        assert time.monotonic() - t0 < 1.5
        assert report["budget_stop"] == "deadline"
        assert report["cancel_unacknowledged"] == ["request"]

    async def test_a_close_that_hangs_is_reported_and_bounded(self):
        class SlowClose(FakeService):
            async def close(self):
                await asyncio.sleep(10)

        svc = SlowClose({E1: [([_listed(T1, E1)], None)]}, {T1: _good_candles()})
        t0 = time.monotonic()
        report = await self._run(
            FakeSession([_row(1)]), svc, deadline_seconds=0.3, hard_deadline_seconds=0.6,
            sleep=Clock().sleep,
        )
        assert time.monotonic() - t0 < 1.5
        assert report["client_close"] == "unacknowledged"

    async def test_a_trickling_response_is_cut_off_at_the_deadline(self):
        async def trickle():
            for _ in range(100):
                yield b" "
                await asyncio.sleep(0.05)

        t0 = time.monotonic()
        report = await self._run(
            FakeSession([_row(1)]),
            _real_service(lambda r: httpx.Response(200, content=trickle())),
            deadline_seconds=0.3,
            hard_deadline_seconds=0.6,
            byte_budget=bounds.ArchiveByteBudget(response_cap=1 << 20, total_cap=3 << 20),
        )
        assert time.monotonic() - t0 < 1.5
        assert report["terminal"] == "partial" and report["budget_stop"] == "deadline"
        assert report["requests_sent"] == 1 and report["archive_cutoff"] is None

    async def test_progress_holds_the_live_report(self):
        progress: dict = {}
        svc = FakeService({E1: [([_listed(T1, E1)], None)]}, {T1: _good_candles()})
        report = await _plan(FakeSession([_row(1)]), svc, progress=progress)
        assert progress["report"] is report and progress["phase"] == "close"


# ── the operation wall ─────────────────────────────────────────────────────


class TestOperationWall:
    def test_a_synchronous_loop_is_interrupted_at_the_wall(self):
        wall = bounds.OperationWall(0.3, reserve=0.0)
        t0 = time.monotonic()
        with pytest.raises(bounds.WallExpired) as info:
            with wall.sync_phase("decode"):
                while True:
                    pass
        assert info.value.phase == "decode" and time.monotonic() - t0 < 1.0

    def test_the_alarm_is_disarmed_after_a_phase(self):
        import signal

        wall = bounds.OperationWall(5)
        with wall.sync_phase("quick"):
            pass
        assert signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0)

    def test_work_that_overruns_without_yielding_still_fails_the_check(self):
        clock = Clock()
        wall = bounds.OperationWall(1.0, reserve=0.0, monotonic=clock.monotonic)
        with pytest.raises(bounds.WallExpired):
            with wall.sync_phase("serialize"):
                clock.t += 2.0

    async def test_expiry_cancels_and_keeps_the_running_receipt(self):
        progress = {"committed_outcomes": [{"outcome_id": 7}]}

        async def work():
            progress["phase"] = "outcome:8"
            await asyncio.sleep(10)

        wall = bounds.OperationWall(0.3)
        with pytest.raises(bounds.WallExpired) as info:
            await bounds.run_within_wall(work, wall=wall, progress=progress)
        assert info.value.phase == "outcome:8"
        assert progress["cancel"] == "acknowledged"
        assert progress["committed_outcomes"] == [{"outcome_id": 7}]

    async def test_a_task_that_ignores_cancel_is_reported_unacknowledged(self):
        progress: dict = {}

        async def work():
            try:
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                await asyncio.sleep(10)

        wall = bounds.OperationWall(0.3, reserve=0.1)
        t0 = time.monotonic()
        with pytest.raises(bounds.WallExpired):
            await bounds.run_within_wall(work, wall=wall, progress=progress)
        assert progress["cancel"] == "unacknowledged" and time.monotonic() - t0 < 1.0

    def test_the_bounded_loop_does_not_wait_on_a_stubborn_straggler(self):
        async def main():
            async def stubborn():
                while True:
                    try:
                        await asyncio.sleep(10)
                    except asyncio.CancelledError:
                        continue

            asyncio.ensure_future(stubborn())
            await asyncio.sleep(0)
            return "done"

        t0 = time.monotonic()
        assert bounds.run_bounded_loop(main(), straggler_grace=0.2) == "done"
        assert time.monotonic() - t0 < 2.0

    def test_a_wall_must_be_positive(self):
        for bad in (0, -1):
            with pytest.raises(ValueError):
                bounds.OperationWall(bad)


# ── the loop's shutdown: real async generators, in a child process ─────────

BACKEND = Path(__file__).resolve().parents[1]

#: Root's 85a probe (artifacts/683-first-import-offline-20261016/
#: ROOT-85A-BOUNDED-CLEANUP): the operation returns, then a real async
#: generator's ``finally`` awaits forever and swallows every cancellation. Run
#: in a child so a regression is a killed child and a red test, never a hung
#: suite.
_SHUTDOWN_PROBE = textwrap.dedent(
    """
    import asyncio, json, sys, time
    sys.path.insert(0, sys.argv[1])
    from app.services import kalshi_archive_bounds as bounds

    mode, grace, close_in = sys.argv[2], float(sys.argv[3]), sys.argv[4]
    HELD = []

    async def stubborn():
        try:
            yield 1
        finally:
            while True:
                try:
                    await asyncio.sleep(3600)
                except asyncio.CancelledError:
                    continue

    async def polite():
        try:
            yield 1
        finally:
            await asyncio.sleep(0)
            print("FINALLY_RAN", flush=True)

    async def operation():
        gen = (polite if mode == "polite" else stubborn)()
        if mode != "dropped":
            HELD.append(gen)  # still open at shutdown: shutdown_asyncgens owns it
        await gen.__anext__()
        print("OPERATION_COMPLETE_BEFORE_CLOSE", flush=True)
        return "done"

    report = {}
    close_by = None if close_in == "none" else time.monotonic() + float(close_in)
    t0 = time.monotonic()
    out = bounds.run_bounded_loop(
        operation(), straggler_grace=grace, close_by=close_by, shutdown=report
    )
    print("RESULT " + json.dumps(
        {"out": out, "seconds": time.monotonic() - t0, "shutdown": report}
    ), flush=True)
    """
)

OUTER_LIMIT_S = 15


def _shutdown_probe(mode: str, grace: float, close_in: str = "none") -> tuple:
    try:
        done = subprocess.run(
            [sys.executable, "-c", _SHUTDOWN_PROBE, str(BACKEND), mode, str(grace), close_in],
            capture_output=True,
            text=True,
            timeout=OUTER_LIMIT_S,
        )
    except subprocess.TimeoutExpired as e:  # the child is killed by subprocess.run
        pytest.fail(f"run_bounded_loop held the process past {OUTER_LIMIT_S}s: {e.stdout!r}")
    assert done.returncode == 0, done.stderr
    line = [x for x in done.stdout.splitlines() if x.startswith("RESULT ")]
    assert line, done.stdout + done.stderr
    return json.loads(line[0][len("RESULT "):]), done.stdout, done.stderr


class TestBoundedShutdown:
    def test_a_generator_cleanup_that_ignores_cancel_is_abandoned_and_counted(self):
        got, out, err = _shutdown_probe("held", 0.3)
        assert "OPERATION_COMPLETE_BEFORE_CLOSE" in out and got["out"] == "done"
        assert got["seconds"] < 0.3 + 1.0
        sd = got["shutdown"]
        assert sd["asyncgens"] == "unacknowledged" and sd["clean"] is False
        assert sd["abandoned"] >= 1
        # Counted on the receipt, never an uncontrolled line at collection.
        assert "Task was destroyed but it is pending" not in err

    def test_a_dropped_generator_finalised_as_a_task_is_bounded_too(self):
        got, _, err = _shutdown_probe("dropped", 0.3)
        assert got["seconds"] < 0.3 + 1.0
        sd = got["shutdown"]
        assert sd["clean"] is False and sd["tasks_unacknowledged"] + sd["abandoned"] >= 1
        assert "Task was destroyed but it is pending" not in err

    def test_the_shutdown_ends_at_the_walls_close_instant_not_the_grace(self):
        got, _, _ = _shutdown_probe("held", 30.0, close_in="0")
        assert got["seconds"] < 2.0 and got["shutdown"]["clean"] is False

    def test_control_a_cleanup_that_finishes_is_awaited_and_clean(self):
        got, out, err = _shutdown_probe("polite", 0.3)
        assert "FINALLY_RAN" in out
        sd = got["shutdown"]
        assert sd == {**sd, "clean": True, "asyncgens": "closed", "abandoned": 0}
        assert sd["tasks_unacknowledged"] == 0 and got["seconds"] < 1.0
        assert "Task was destroyed" not in err

    def test_an_ignored_task_is_counted_unacknowledged(self):
        async def main():
            async def stubborn():
                while True:
                    try:
                        await asyncio.sleep(10)
                    except asyncio.CancelledError:
                        continue

            asyncio.ensure_future(stubborn())
            await asyncio.sleep(0)
            return "done"

        report: dict = {}
        assert bounds.run_bounded_loop(main(), straggler_grace=0.2, shutdown=report) == "done"
        assert report["tasks_cancelled"] == 1 and report["tasks_unacknowledged"] == 1
        assert report["clean"] is False and report["asyncgens"] == "closed"


# ── output caps ────────────────────────────────────────────────────────────


class TestOutputCaps:
    def test_the_console_cap_drops_everything_past_it_and_says_so(self, capsys):
        cap = bounds.ConsoleCap(400).install()
        try:
            import sys

            print("a" * 100)
            print("b" * 300, file=sys.stderr)
            print("c")
        finally:
            cap.restore()
        out, err = capsys.readouterr()
        assert out == "a" * 100 + "\n" and "bbb" not in err and "c" not in out
        assert cap.overflowed and err.startswith("OUTPUT_CAP_EXCEEDED")
        assert len(out.encode()) + len(err.encode()) <= 400

    def test_an_artifact_is_written_whole_or_not_at_all(self, tmp_path):
        path = tmp_path / "plan.json"
        with pytest.raises(bounds.ArtifactOverflow):
            bounds.write_bounded_artifact(str(path), {"x": "y" * 500}, 100)
        assert not path.exists() and list(tmp_path.iterdir()) == []
        n = bounds.write_bounded_artifact(str(path), {"x": 1}, 100)
        assert json.loads(path.read_text()) == {"x": 1} and n == path.stat().st_size

    def test_an_artifact_never_overwrites(self, tmp_path):
        path = tmp_path / "plan.json"
        path.write_text("sealed")
        with pytest.raises(FileExistsError):
            bounds.write_bounded_artifact(str(path), {"x": 1}, 100)
        assert path.read_text() == "sealed"

    def test_an_input_over_its_cap_is_refused_before_decoding(self, tmp_path, monkeypatch):
        path = tmp_path / "plan.json"
        path.write_text(json.dumps({"x": "y" * 500}))
        decoded = []
        monkeypatch.setattr(bounds.json, "loads", lambda *a, **k: decoded.append(1))
        with pytest.raises(bounds.InputTooLarge):
            bounds.read_bounded_json(str(path), 100)
        assert decoded == []


# ── planner CLI ────────────────────────────────────────────────────────────


PROFILE = [
    "--outcome-ids", "1", "--limit", "1", "--max-requests", "3", "--pace", "2",
    "--deadline", "120", "--stop-on-429",
    "--max-response-bytes", "1048576", "--max-total-bytes", "3145728",
    "--max-artifact-bytes", "262144", "--max-console-bytes", "262144",
]


@pytest.fixture
def planner_cli(monkeypatch):
    mod = _load_script("kalshi_archive_recovery_dry_run.py")

    def run(argv, *, handler=None, session=None):
        seen: list = []
        h = handler or _archive_handler(seen)
        code = mod.main(
            argv,
            service_factory=lambda: _real_service(h),
            session_factory=_factory(session or FakeSession([_row(1)])),
        )
        return code, seen

    # The real pace would make the profile run take seconds; the bound is unchanged.
    real = rec.plan_archive_recovery

    async def fast(**kw):
        kw["sleep"] = Clock().sleep
        kw["cooldown_reader"] = lambda: 0.0  # no Redis here; strict would refuse
        return await real(**kw)

    monkeypatch.setattr(rec, "plan_archive_recovery", fast)
    return run


class TestPlannerCli:
    def test_the_first_sample_profile_runs_and_seals_its_plan(self, planner_cli, tmp_path, capsys):
        out = tmp_path / "P.json"
        code, seen = planner_cli(PROFILE + ["--output", str(out)])
        assert code == 0 and len(seen) == 3
        plan = json.loads(out.read_text())
        assert plan["terminal"] == "complete" and plan["stop_on_first_429"] is True
        assert plan["response_bytes"]["received"] <= 3 << 20
        summary = json.loads(capsys.readouterr().out)
        assert summary["artifact_bytes"] == out.stat().st_size <= 262144

    def test_a_429_with_retry_after_zero_exits_without_a_second_request(self, planner_cli):
        seen = []

        def handler(r):
            seen.append(r)
            return httpx.Response(429, headers={"Retry-After": "0"})

        code, _ = planner_cli(PROFILE, handler=handler)
        assert code == 1 and len(seen) == 1

    def test_an_artifact_over_its_cap_is_not_written_and_exits_held(
        self, planner_cli, tmp_path, capsys
    ):
        out = tmp_path / "P.json"
        argv = [a if a != "262144" else "300" for a in PROFILE[:-2]] + [
            "--max-console-bytes", "262144", "--output", str(out),
        ]
        code, _ = planner_cli(argv)
        assert code == 3 and not out.exists()
        assert "artifact_overflow" in json.loads(capsys.readouterr().out)["artifact_refused"]

    def test_console_overflow_never_exits_zero(self, planner_cli, capsys):
        argv = PROFILE[:-1] + ["400"]
        code, _ = planner_cli(argv)
        assert code == 3
        out, err = capsys.readouterr()
        assert "OUTPUT_CAP_EXCEEDED" in err and len((out + err).encode()) <= 400

    def test_an_existing_output_is_refused_untouched(self, planner_cli, tmp_path):
        out = tmp_path / "P.json"
        out.write_text("sealed")
        code, seen = planner_cli(PROFILE + ["--output", str(out)])
        assert code == 2 and out.read_text() == "sealed" and seen == []

    def test_a_held_budget_stop_exits_three(self, planner_cli, capsys):
        argv = PROFILE[:PROFILE.index("--max-requests") + 1] + ["2"] + PROFILE[
            PROFILE.index("--max-requests") + 2 :
        ]
        code, seen = planner_cli(argv)
        summary = json.loads(capsys.readouterr().out)
        assert code == 3 and summary["budget_stop"] == "requests" and len(seen) == 2
        assert summary["held_outcome"]["outcome_id"] == 1

    @pytest.mark.parametrize("straggler", [False, True])
    def test_a_planner_shutdown_that_abandoned_work_holds_the_exit(
        self, planner_cli, capsys, monkeypatch, straggler
    ):
        fast = rec.plan_archive_recovery

        async def stubborn():
            while True:
                try:
                    await asyncio.sleep(10)
                except asyncio.CancelledError:
                    continue

        async def with_straggler(**kw):
            if straggler:
                asyncio.ensure_future(stubborn())
            return await fast(**kw)

        monkeypatch.setattr(rec, "plan_archive_recovery", with_straggler)
        code, _ = planner_cli(PROFILE)
        summary = json.loads(capsys.readouterr().out)
        assert summary["terminal"] == "complete"
        assert summary["shutdown"]["clean"] is (not straggler)
        assert code == (3 if straggler else 0)

    def test_the_outer_wall_receipt_claims_nothing(self, planner_cli, capsys):
        class Frozen(FakeSession):
            async def execute(self, clause, params=None):
                if "FROM futures_outcomes fo" in str(clause):
                    while True:  # ignores cancellation entirely
                        try:
                            await asyncio.sleep(10)
                        except asyncio.CancelledError:
                            continue
                return await super().execute(clause, params)

        argv = PROFILE[: PROFILE.index("--deadline") + 1] + ["0.6"] + PROFILE[
            PROFILE.index("--deadline") + 2 :
        ]
        t0 = time.monotonic()
        code, _ = planner_cli(argv, session=Frozen([_row(1)]))
        assert time.monotonic() - t0 < 3.0 and code == 3
        summary = json.loads(capsys.readouterr().out)
        assert summary["budget_stop"] in ("deadline", "wall")
        assert summary["plan_digest"] in (None, rec.plan_digest([]))
        assert summary["importable_points"] == 0 and summary["next_after_id"] is None


# ── importer: caps, completeness, receipts ─────────────────────────────────


async def _a_plan(**kw):
    svc = FakeService({E1: [([_listed(T1, E1)], None)]}, {T1: _good_candles()})
    return json.loads(
        json.dumps(await _plan(FakeSession([_row(1)]), svc, **kw), default=str)
    )


def _never_called():
    raise AssertionError("no session may open before the plan is admitted")


def _reviewed(report, **over):
    """A sealed input-versions document for every importable outcome of ``report``."""
    plans = imp.verify_plan_document(report, report["plan_digest"])
    outcomes = [
        {
            "outcome_id": int(p["outcome_id"]), "ticker": p["ticker"],
            "event_ticker": p["event_ticker"], "market_id": 10, "event_id": 20,
            "input_fingerprint": p["input_fingerprint"],
            "outcome_xmin": "101", "market_xmin": "102", "event_xmin": "103",
            **over,
        }
        for p in plans
    ]
    return imp.seal_input_versions(report["plan_digest"], outcomes)


def _attended_argv(tmp_path, report):
    """The CLI arguments an attended ``--write`` now requires."""
    doc = _reviewed(report)
    path = tmp_path / "V.json"
    path.write_text(json.dumps(doc))
    return ["--input-versions", str(path), "--expected-input-digest", doc["digest"]]


class TestImportAdmission:
    async def test_a_plan_with_more_outcomes_than_named_is_refused_before_any_session(self):
        report = await _a_plan()
        with pytest.raises(imp.PlanRefused) as info:
            await imp.apply_archive_plan(
                report,
                expected_digest=report["plan_digest"],
                max_outcomes=0,
                session_factory=_never_called,
            )
        assert info.value.reason.startswith("plan_exceeds_max_outcomes:1>0")

    async def test_a_plan_with_more_points_than_named_is_refused(self):
        report = await _a_plan()
        n = report["importable_points"]
        with pytest.raises(imp.PlanRefused) as info:
            await imp.apply_archive_plan(
                report,
                expected_digest=report["plan_digest"],
                max_outcomes=1,
                max_points=n - 1,
                session_factory=_never_called,
            )
        assert info.value.reason == f"plan_exceeds_max_points:{n}>{n - 1}"

    async def test_completeness_names_every_reason_a_plan_is_not_whole(self):
        report = await _a_plan()
        plans = imp.verify_plan_document(report, report["plan_digest"])
        assert imp.plan_completeness(report, plans) == []
        partial = dict(report, terminal="partial", owed_ids=[3], budget_stop="requests",
                       held_outcome={"outcome_id": 4})
        assert imp.plan_completeness(partial, plans) == [
            "plan_terminal:partial",
            "plan_owed_ids",
            "plan_held_outcome",
            "plan_budget_stop:requests",
        ]
        gap = [dict(plans[0], owed_windows=[{"start_ts": 1}])]
        assert imp.plan_completeness(report, gap) == ["outcome_coverage_incomplete:1"]
        assert imp.plan_completeness(report, []) == ["plan_has_no_importable_points"]

    async def test_a_validation_loop_past_the_wall_is_interrupted(self, monkeypatch):
        report = await _a_plan()

        def spin(*a, **k):
            while True:
                pass

        monkeypatch.setattr(imp, "verify_plan_document", spin)
        progress: dict = {}
        with pytest.raises(bounds.WallExpired) as info:
            await imp.apply_archive_plan(
                report,
                expected_digest=report["plan_digest"],
                wall=bounds.OperationWall(0.3, reserve=0.0),
                progress=progress,
                session_factory=_never_called,
            )
        assert info.value.phase == "verify_plan" and progress["phase"] == "verify_plan"


class _LockedRowSession:
    """Answers only the write path's two locking reads; any later statement fails.

    So a refusal that reaches no other statement (and no COMMIT) is proven to
    come straight after the locks, before any evidence or interval write.
    """

    def __init__(self, head, event):
        self.head, self.event, self.seen, self.committed = head, event, [], False

    async def execute(self, clause, params=None):
        sql = str(clause)
        self.seen.append(sql)
        if "FOR SHARE OF fo, fm" in sql:
            return SimpleNamespace(first=lambda: self.head)
        if "FROM events e" in sql and "FOR SHARE" in sql:
            return SimpleNamespace(first=lambda: self.event)
        raise AssertionError(f"a refused outcome reached {sql[:60]}")

    async def commit(self):
        self.committed = True

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


def _locked(report, **over):
    """The stored row exactly as reviewed by :func:`_reviewed` (ids 501/900)."""
    row = _row(1)
    head = SimpleNamespace(
        outcome_id=1, ticker=row.ticker, event_ticker=row.event_ticker,
        market_id=501, event_id=900, resolution_source=None,
        outcome_xmin="101", market_xmin="102",
    )
    event = SimpleNamespace(
        commence_time=row.commence_time, commence_time_source=row.commence_time_source,
        created_at=row.created_at, completed_at=None, event_xmin="103",
    )
    for k, v in over.items():
        setattr(event if k in vars(event) else head, k, v)
    return head, event


class TestAttendedInputFence:
    """The reviewed identity + row-version document, refused loose or drifted."""

    async def test_the_attended_write_without_a_document_is_refused_before_any_session(self):
        report = await _a_plan()
        for doc, digest in ((None, None), (_reviewed(report), None), (None, "x")):
            with pytest.raises(imp.PlanRefused) as info:
                await imp.apply_archive_plan(
                    report, expected_digest=report["plan_digest"], write=True,
                    input_versions=doc, expected_input_digest=digest,
                    require_input_versions=True, session_factory=_never_called,
                )
            assert info.value.reason == "input_versions_missing"

    @pytest.mark.parametrize(
        "edit,reason",
        [
            (lambda d: d.update(kind="other"), "input_versions_malformed"),
            (lambda d: d.update(extra=1), "input_versions_malformed"),
            (lambda d: d["outcomes"][0].update(outcome_xmin="1"),
             "input_versions_digest_mismatch"),
        ],
    )
    async def test_an_unsealed_or_edited_document_is_refused(self, edit, reason):
        report = await _a_plan()
        doc = _reviewed(report)
        digest = doc["digest"]
        edit(doc)
        with pytest.raises(imp.PlanRefused) as info:
            imp.verify_input_versions(
                doc, digest, imp.verify_plan_document(report, report["plan_digest"]),
                report["plan_digest"],
            )
        assert info.value.reason == reason

    @pytest.mark.parametrize(
        "over,reason",
        [
            ({"outcome_xmin": 101}, "input_versions_malformed:xmin"),
            ({"market_xmin": ""}, "input_versions_malformed:xmin"),
            ({"outcome_id": True}, "input_versions_malformed:ids"),
            ({"input_fingerprint": "A" * 64}, "input_versions_malformed:input_fingerprint"),
            ({"event_xmin": None}, "input_versions_malformed:event"),
            ({"event_id": None}, "input_versions_malformed:event_xmin_without_event"),
            ({"ticker": "KX-OTHER"}, "input_versions_identity_mismatch:1"),
            ({"input_fingerprint": "0" * 64}, "input_versions_identity_mismatch:1"),
        ],
    )
    async def test_a_sealed_document_that_is_malformed_or_names_another_outcome_is_refused(
        self, over, reason
    ):
        report = await _a_plan()
        doc = _reviewed(report, **over)
        with pytest.raises(imp.PlanRefused) as info:
            imp.verify_input_versions(
                doc, doc["digest"], imp.verify_plan_document(report, report["plan_digest"]),
                report["plan_digest"],
            )
        assert info.value.reason == reason

    async def test_the_document_names_exactly_the_plans_outcomes_and_its_digest(self):
        report = await _a_plan()
        plans = imp.verify_plan_document(report, report["plan_digest"])
        good = _reviewed(report)
        assert imp.verify_input_versions(good, good["digest"], plans, report["plan_digest"])
        extra = imp.seal_input_versions(
            report["plan_digest"], good["outcomes"] + [dict(good["outcomes"][0], outcome_id=2)]
        )
        twice = imp.seal_input_versions(report["plan_digest"], good["outcomes"] * 2)
        none = imp.seal_input_versions(report["plan_digest"], [])
        other = imp.seal_input_versions("f" * 64, good["outcomes"])
        for doc, reason in (
            (extra, "input_versions_outcomes_mismatch"),
            (twice, "input_versions_duplicate_outcome"),
            (none, "input_versions_outcomes_mismatch"),
            (other, "input_versions_plan_mismatch"),
        ):
            with pytest.raises(imp.PlanRefused) as info:
                imp.verify_input_versions(doc, doc["digest"], plans, report["plan_digest"])
            assert info.value.reason == reason, reason
        with pytest.raises(imp.PlanRefused) as info:
            imp.verify_input_versions(good, "0" * 64, plans, report["plan_digest"])
        assert info.value.reason == "expected_input_digest_mismatch"

    @pytest.mark.parametrize(
        "over,reason",
        [
            ({}, None),
            ({"outcome_xmin": "999"}, "input_version_drift:outcome"),
            ({"market_xmin": "999"}, "input_version_drift:market"),
            ({"event_xmin": "999"}, "input_version_drift:event"),
            ({"market_id": 777}, "input_identity_drift"),
            ({"completed_at": TIPOFF}, "input_drift"),
        ],
    )
    async def test_the_fence_compares_the_locked_row_and_writes_nothing_on_drift(
        self, over, reason
    ):
        report = await _a_plan()
        doc = _reviewed(report, market_id=501, event_id=900)
        session = _LockedRowSession(*_locked(report, **over))
        out = await imp._apply_outcome(
            report["plans"][0], archive_cutoff=report["archive_cutoff"], write=True,
            import_id=41, session_factory=lambda: session,
            expected_input=doc["outcomes"][0],
        ) if reason else None
        if reason is None:
            row = await imp._locked_input(session, 1)
            assert imp.input_version_refusal(row, doc["outcomes"][0]) is None
            return
        assert out["refused"] == reason
        assert len(session.seen) == 2 and not session.committed

    async def test_a_present_event_that_is_gone_is_refused_and_absent_is_never_a_wildcard(self):
        report = await _a_plan()
        expected = _reviewed(report, market_id=501, event_id=900)["outcomes"][0]
        head, event = _locked(report)
        gone = await imp._locked_input(_LockedRowSession(head, None), 1)
        assert imp.input_version_refusal(gone, expected) == "input_event_missing"
        no_event = dict(expected, event_id=None, event_xmin=None)
        present = await imp._locked_input(_LockedRowSession(head, event), 1)
        assert imp.input_version_refusal(present, no_event) == "input_identity_drift"

    def test_the_cli_write_requires_the_document_and_dry_run_does_not(self, tmp_path, capsys):
        report = asyncio.run(_a_plan())
        plan = tmp_path / "P.json"
        plan.write_text(json.dumps(report))
        mod = _load_script("kalshi_archive_import.py")
        base = ["apply", "--plan", str(plan), "--expected-digest", report["plan_digest"],
                "--max-outcomes", "1", "--max-points", "26", "--deadline", "5"]

        def refuse():
            raise AssertionError("a refused attended write opened a session")

        code = mod.main(base + ["--write"], session_factory=refuse)
        assert code == 2 and "REFUSED: input_versions_missing" in capsys.readouterr().err
        doc = _reviewed(report)
        (tmp_path / "V.json").write_text(json.dumps(doc))
        code = mod.main(
            base + ["--input-versions", str(tmp_path / "V.json"),
                    "--expected-input-digest", "0" * 64, "--write"],
            session_factory=refuse,
        )
        assert code == 2 and "expected_input_digest_mismatch" in capsys.readouterr().err


class _CommitSession:
    """Answers the apply's first two steps; COMMIT behaves as ``on_commit`` says."""

    def __init__(self, on_commit):
        self.on_commit = on_commit

    async def execute(self, clause, params=None):
        sql = str(clause)
        if "to_regclass" in sql:
            return SimpleNamespace(scalar=lambda: True)
        if "INSERT INTO kalshi_archive_imports" in sql:
            return SimpleNamespace(scalar_one=lambda: 41)
        if "SET TRANSACTION READ ONLY" in sql:
            return SimpleNamespace()
        raise AssertionError(f"unexpected SQL {sql}")

    async def commit(self):
        await self.on_commit()


class _HeldClock:
    """The wall's clock: real time until :meth:`hold`, then that instant for good."""

    def __init__(self):
        self.held_at = None

    def __call__(self) -> float:
        return time.monotonic() if self.held_at is None else self.held_at

    def hold(self) -> None:
        if self.held_at is None:
            self.held_at = time.monotonic()


def _record_walls(monkeypatch) -> list:
    """Every OperationWall the CLI builds, unchanged: real clock, real alarm."""
    walls: list = []

    class SeenWall(bounds.OperationWall):
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            walls.append(self)

    monkeypatch.setattr(bounds, "OperationWall", SeenWall)
    return walls


def _full_collections() -> int:
    """Full (generation-2) collections this process has run. Read only."""
    return gc.get_stats()[2]["collections"]


class TestCommitAcknowledgement:
    async def test_a_lost_create_import_ack_stops_and_claims_nothing(self):
        report = await _a_plan()

        async def lost():
            raise ConnectionResetError("connection lost after COMMIT was sent")

        result = await imp.apply_archive_plan(
            report,
            expected_digest=report["plan_digest"],
            write=True,
            session_factory=_factory(_CommitSession(lost)),
        )
        assert result["stopped"] == "commit_unacknowledged:create_import"
        assert result["import_row"] == "unknown" and result["import_id"] is None
        assert result["status"] == "partial" and result["inserted"] == 0
        assert result["uncertain_commits"][0]["step"] == "create_import"
        assert result["readback_owed"]["durability"] == "unknown"
        assert result["import_key"] in result["readback_owed"]["commands"][0]

    @pytest.mark.parametrize("artifact_stall", [0.0, 0.1])
    def test_import_cli_wall_during_a_commit_reports_it_in_flight(
        self, tmp_path, capsys, monkeypatch, artifact_stall
    ):
        """The real 0.8 s wall expires while COMMIT is in flight; the receipt says so.

        The wall's clock holds still from the instant the COMMIT is sent
        (``_HeldClock``). The work still expires on real time: the event loop
        waits out the real work slice, then cancels the hanging COMMIT. What the
        hold removes is the race this case never meant to test. Without it the
        receipt file had to be sealed in the 20-60 ms between the cancel
        (0.72 s) and ``artifact_deadline`` (0.78 s), against a real alarm, and a
        loaded runner sometimes lost that slice (#683, three master/PR reds,
        missing R.json). Writing the receipt inside the wall on real time is
        ``test_import_cli_timeout_receipt_is_written_inside_the_wall``'s job.
        ``artifact_stall`` 0.1 stalls the artifact write past the old slice:
        without the hold that always loses R.json, so it proves the race is gone.
        """
        report = asyncio.run(_a_plan())
        plan = tmp_path / "P.json"
        plan.write_text(json.dumps(report))
        out = tmp_path / "R.json"
        clock = _HeldClock()
        walls = []
        real_wall = bounds.OperationWall

        def held_wall(seconds, **kw):
            walls.append(real_wall(seconds, monotonic=clock, **kw))
            return walls[-1]

        monkeypatch.setattr(bounds, "OperationWall", held_wall)
        real_fsync = bounds.os.fsync

        def slow_fsync(fd):
            time.sleep(artifact_stall)
            return real_fsync(fd)

        monkeypatch.setattr(bounds.os, "fsync", slow_fsync)
        cancelled_at = []

        async def hang():
            clock.hold()
            try:
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                cancelled_at.append(time.monotonic())
                raise

        mod = _load_script("kalshi_archive_import.py")
        t0 = time.monotonic()
        code = mod.main(
            [
                "apply", "--plan", str(plan), "--expected-digest", report["plan_digest"],
                "--max-outcomes", "1", "--max-points", "26", "--deadline", "0.8",
                *_attended_argv(tmp_path, report), "--write", "--output", str(out),
            ],
            session_factory=_factory(_CommitSession(hang)),
        )
        assert time.monotonic() - t0 < 3.0 and code == 3
        # Precondition: the COMMIT was in flight and the REAL work slice ran
        # out before the wall cancelled it (1 ms: the loop's timer tolerance).
        # The hold changed no expiry.
        (wall,) = walls
        assert wall.seconds == 0.8 and clock.held_at is not None
        assert len(cancelled_at) == 1 and cancelled_at[0] >= wall.work_deadline - 1e-3
        receipt = json.loads(out.read_text())
        assert receipt["status"] == "incomplete"
        assert receipt["stopped"] == "wall_expired:create_import"
        assert receipt["uncertain_commits"][-1]["error"] == "acknowledgement_not_received"
        assert receipt["readback_owed"]["never"] == [
            "retry the apply", "restore automatically", "assume zero rows"
        ]

    @pytest.mark.parametrize("artifact_delay", [0.0, 0.6])
    def test_import_cli_timeout_receipt_is_written_inside_the_wall(
        self, tmp_path, capsys, monkeypatch, artifact_delay
    ):
        """CERT-4172's 683-KEEP-TIMEOUT-RECEIPT-WITHIN-THE-OPERATION-WALL.

        0.0 is the control: the receipt is written whole inside the wall. 0.6
        delays only the local artifact write past the wall: the process still
        ends at the wall, the artifact is reported unavailable, and the
        console summary keeps the uncertain COMMIT and its readback.
        """
        report = asyncio.run(_a_plan())
        plan = tmp_path / "P.json"
        plan.write_text(json.dumps(report))
        out = tmp_path / "R.json"
        real_fsync = bounds.os.fsync

        def slow_fsync(fd):
            # Inside the writer, with its temporary file open: a slow disk.
            end = time.monotonic() + artifact_delay
            while time.monotonic() < end:
                time.sleep(0.01)
            return real_fsync(fd)

        monkeypatch.setattr(bounds.os, "fsync", slow_fsync)
        walls = _record_walls(monkeypatch)
        cancelled_at = []

        async def hang():
            try:
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                cancelled_at.append(time.monotonic())
                raise

        mod = _load_script("kalshi_archive_import.py")
        deadline = 0.8
        # The wall stays real (no held clock): only the pytest heap's full
        # collection is kept out of the receipt slice, which is what took
        # +0.09-0.11 s from this case and two 0.8 s siblings in PR #11504's CI.
        with _a_collection_scans_only_the_cli():
            full_before = _full_collections()
            t0 = time.monotonic()
            code = mod.main(
                [
                    "apply", "--plan", str(plan), "--expected-digest", report["plan_digest"],
                    "--max-outcomes", "1", "--max-points", "26", "--deadline", str(deadline),
                    *_attended_argv(tmp_path, report), "--write", "--output", str(out),
                ],
                session_factory=_factory(_CommitSession(hang)),
            )
            elapsed = time.monotonic() - t0
            full_during = _full_collections() - full_before
        assert code == 3 and elapsed < deadline + 0.15
        # Precondition: one real 0.8 s wall, and the COMMIT was cancelled no
        # sooner than its work deadline (1 ms: the loop's timer tolerance).
        (wall,) = walls
        assert wall.seconds == deadline
        assert len(cancelled_at) == 1 and cancelled_at[0] >= wall.work_deadline - 1e-3
        console = capsys.readouterr().out
        assert console, (
            f"no console receipt after {elapsed:.3f}s; R.json present {out.exists()}; "
            f"full collections during the call {full_during} (frozen heap)"
        )
        summary = json.loads(console)
        assert summary["stopped"] == "wall_expired:create_import"
        assert summary["uncertain_commits"][-1]["error"] == "acknowledgement_not_received"
        assert summary["readback_owed"]["never"] == [
            "retry the apply", "restore automatically", "assume zero rows"
        ]
        assert summary["shutdown"]["clean"] is True
        if artifact_delay:
            assert not out.exists() and summary["artifact"] is None
            assert summary["artifact_refused"] == "wall_expired:serialize"
            assert not list(tmp_path.glob(".R.json.*.tmp"))
        else:
            receipt = json.loads(out.read_text())
            assert receipt["stopped"] == "wall_expired:create_import"
            assert summary["artifact_bytes"] == out.stat().st_size

    def test_an_artifact_linked_just_before_the_alarm_is_reported_present(
        self, tmp_path, capsys, monkeypatch
    ):
        real = bounds.write_bounded_artifact

        def linked_then_alarm(path, payload, cap):
            real(path, payload, cap)
            raise bounds.WallExpired("serialize")

        monkeypatch.setattr(bounds, "write_bounded_artifact", linked_then_alarm)

        async def fake_apply(report, **kw):
            return {"status": "applied", "import_key": "k", "committed_outcomes": []}

        monkeypatch.setattr(imp, "apply_archive_plan", fake_apply)
        plan = tmp_path / "P.json"
        plan.write_text("{}")
        out = tmp_path / "R.json"
        code = _load_script("kalshi_archive_import.py").main(
            [
                "apply", "--plan", str(plan), "--expected-digest", "d",
                "--max-outcomes", "1", "--max-points", "1", "--deadline", "30",
                "--output", str(out),
            ]
        )
        summary = json.loads(capsys.readouterr().out)
        assert code == 3 and out.exists()
        assert summary["artifact"] == str(out) and summary["artifact_written_at_wall"] is True
        assert "artifact_refused" not in summary

    @pytest.mark.parametrize("straggler", [False, True])
    def test_import_cli_work_the_shutdown_abandoned_never_exits_applied(
        self, tmp_path, capsys, monkeypatch, straggler
    ):
        async def stubborn():
            while True:
                try:
                    await asyncio.sleep(10)
                except asyncio.CancelledError:
                    continue

        async def fake_apply(report, **kw):
            if straggler:
                asyncio.ensure_future(stubborn())
                await asyncio.sleep(0)
            return {
                "status": "applied",
                "import_key": "k",
                "committed_outcomes": [{"outcome_id": 7}],
            }

        monkeypatch.setattr(imp, "apply_archive_plan", fake_apply)
        plan = tmp_path / "P.json"
        plan.write_text("{}")
        code = _load_script("kalshi_archive_import.py").main(
            [
                "apply", "--plan", str(plan), "--expected-digest", "d",
                "--max-outcomes", "1", "--max-points", "1", "--deadline", "30",
            ]
        )
        summary = json.loads(capsys.readouterr().out)
        assert summary["status"] == "applied"  # what WAS durable is unchanged
        if straggler:
            assert code == 3 and summary["shutdown"]["clean"] is False
            assert summary["shutdown"]["tasks_unacknowledged"] == 1
            assert summary["readback_owed"]["durability"] == "unknown"
        else:
            assert code == 0 and summary["shutdown"]["clean"] is True
            assert "readback_owed" not in summary

    def test_import_cli_requires_an_explicit_wall_on_every_subcommand(self):
        mod = _load_script("kalshi_archive_import.py")
        for argv in (
            ["apply", "--plan", "p", "--expected-digest", "d", "--max-outcomes", "1",
             "--max-points", "1"],
            ["apply", "--plan", "p", "--expected-digest", "d", "--deadline", "30"],
            ["restore", "--import-key", "k"],
            ["cohort", "--outcome-ids", "1"],
        ):
            with pytest.raises(SystemExit):
                mod._parse(argv)

    def test_an_over_cap_plan_file_is_refused_before_decoding(self, tmp_path, capsys):
        plan = tmp_path / "P.json"
        plan.write_text(json.dumps({"mode": "dry_run", "pad": "x" * 2000}))
        mod = _load_script("kalshi_archive_import.py")
        code = mod.main(
            [
                "apply", "--plan", str(plan), "--expected-digest", "d",
                "--max-outcomes", "1", "--max-points", "26", "--deadline", "30",
                "--max-plan-bytes", "1000",
            ],
            session_factory=_never_called,
        )
        assert code == 2 and "input_too_large" in capsys.readouterr().err


# ── the console is delivered inside the wall ───────────────────────────────


@pytest.fixture
def slow_console(monkeypatch):
    """Delay only the real sinks' writes that start with ``prefix`` (a stalled pipe or terminal).

    The default prefix is the receipt's opening brace on stdout. ``handed``
    keeps each such write as the sink received it, delivered or not, with the
    instant it arrived: a stalled console still shows what the receipt said.
    """
    state = {"delay": 0.0, "refuse": None, "prefix": "{", "handed": []}
    original_install = bounds.ConsoleCap.install

    class SlowSink:
        def __init__(self, real):
            self.real = real

        def write(self, s):
            if s.startswith(state["prefix"]):
                state["handed"].append((time.monotonic(), s))
                if state["refuse"] is not None:
                    raise state["refuse"]
                time.sleep(state["delay"])
            return self.real.write(s)

        def flush(self):
            return self.real.flush()

        def __getattr__(self, k):
            return getattr(self.real, k)

    def install(self):
        self._real_out, self._real_err = SlowSink(self._real_out), SlowSink(self._real_err)
        return original_install(self)

    monkeypatch.setattr(bounds.ConsoleCap, "install", install)
    return state


def _hanging_apply(tmp_path, deadline):
    report = asyncio.run(_a_plan())
    plan = tmp_path / "P.json"
    plan.write_text(json.dumps(report))

    async def hang():
        await asyncio.sleep(60)

    argv = [
        "apply", "--plan", str(plan), "--expected-digest", report["plan_digest"],
        "--max-outcomes", "1", "--max-points", "26", "--deadline", str(deadline),
        *_attended_argv(tmp_path, report), "--write", "--output", str(tmp_path / "R.json"),
    ]
    return argv, _factory(_CommitSession(hang))


@contextmanager
def _a_collection_scans_only_the_cli():
    """Keep the pytest process's own heap out of a sub-second wall.

    A long CI shard holds ~0.6M tracked objects, and one automatic full
    collection over them took 0.11-0.15 s locally. It is C-level, so it defers
    the wall's ``SIGALRM``, and it lands where the CLI allocates: after the idle
    wait, inside the 0.8 s wall's receipt slice (work ends 0.72 s, artifact
    sealed by 0.78 s). Missing R.json in CI (#683) is that shape. ``gc.freeze``
    moves what exists now into the permanent generation. It prevents no
    collection: the CLI's own allocations are collected as in a fresh attended
    process.

    One collection runs first, before the caller starts its clock. It settles
    the heap's pending promotions, so no full collection falls due inside the
    frozen window or just after it. One inside would be cheap, but CPython
    would then size the old generation by the few objects it scanned, and the
    next full collection, over the whole unfrozen heap, would fall due within
    about ten young collections: inside a sibling's wall.
    """
    gc.collect()
    gc.freeze()
    try:
        yield
    finally:
        gc.unfreeze()


def _slice_named_by_the_receipt(handed, t0):
    """Where a missed receipt slice went, from the summary the stalled sink was handed.

    A console slower than the wall swallows the summary, so a missing artifact
    reads ``console ''`` and names no phase. The summary still reached the
    sink: ``elapsed_s`` (wall clock when the receipt was built, after the
    loop's shutdown) late means the slice went before serialising; on time,
    with ``artifact_refused``, it went inside it. Read only, after the run.
    """
    if not handed:
        return "nothing handed to the sink"
    at, text = handed[-1]
    try:
        summary = json.loads(text)
    except ValueError:
        return {"handed_after_s": round(at - t0, 3), "text": text[-300:]}
    keys = ("stopped", "elapsed_s", "cancel", "shutdown", "artifact", "artifact_refused")
    return {"handed_after_s": round(at - t0, 3), **{k: summary.get(k) for k in keys}}


class TestConsoleInsideTheWall:
    @pytest.mark.parametrize("deadline,delay", [(0.8, 0.0), (0.8, 0.6), (30.0, 3.0)])
    def test_the_import_receipt_reaches_the_console_inside_the_wall_or_not_at_all(
        self, tmp_path, capsys, slow_console, deadline, delay
    ):
        """CERT-4175's 683-KEEP-CONSOLE-RECEIPT-WITHIN-THE-OPERATION-WALL, the reviewer's witness.

        The one-outcome / 26-point profile; only the console sink is slow.
        ``delay`` 0 is the control: the summary is delivered, exit 3 for the
        uncertain COMMIT. A console slower than the wall (0.8 s and the
        commissioned 30 s) stops AT the wall: no summary, exit 3, and the
        artifact written before it keeps the uncertain COMMIT.
        """
        slow_console["delay"] = delay
        argv, factory = _hanging_apply(tmp_path, deadline)
        with _a_collection_scans_only_the_cli():
            t0 = time.monotonic()
            code = _load_script("kalshi_archive_import.py").main(argv, session_factory=factory)
            elapsed = time.monotonic() - t0
        out = capsys.readouterr().out
        assert (tmp_path / "R.json").exists(), (
            f"no artifact after {elapsed:.3f}s; console {out[-600:]!r}; "
            f"the receipt's own slice {_slice_named_by_the_receipt(slow_console['handed'], t0)}"
        )
        receipt = json.loads((tmp_path / "R.json").read_text())
        assert code == 3 and elapsed < deadline + 0.15
        assert receipt["uncertain_commits"][-1]["error"] == "acknowledgement_not_received"
        assert receipt["readback_owed"]["durability"] == "unknown"
        if delay:
            assert out == ""  # nothing half-sent, nothing claimed
        else:
            summary = json.loads(out)
            assert summary["uncertain_commits"] == receipt["uncertain_commits"]
            assert summary["artifact_bytes"] == (tmp_path / "R.json").stat().st_size

    def test_a_clean_apply_whose_console_is_too_slow_exits_three_not_applied(
        self, tmp_path, capsys, monkeypatch, slow_console
    ):
        async def fake_apply(report, **kw):
            return {"status": "applied", "import_key": "k", "committed_outcomes": [{"outcome_id": 7}]}

        monkeypatch.setattr(imp, "apply_archive_plan", fake_apply)
        plan = tmp_path / "P.json"
        plan.write_text("{}")
        out = tmp_path / "R.json"
        argv = [
            "apply", "--plan", str(plan), "--expected-digest", "d", "--max-outcomes", "1",
            "--max-points", "1", "--deadline", "0.8", "--output", str(out),
        ]
        mod = _load_script("kalshi_archive_import.py")
        assert mod.main(argv) == 0  # control: the same apply, a console that keeps up
        assert json.loads(capsys.readouterr().out)["status"] == "applied"
        out.unlink()
        slow_console["delay"] = 3.0
        walls = []

        class SeenWall(bounds.OperationWall):
            def __init__(self, *a, **kw):
                super().__init__(*a, **kw)
                walls.append(self)

        monkeypatch.setattr(bounds, "OperationWall", SeenWall)
        gc_pauses, gc_started = [], {}

        def on_gc(phase, info):  # the test process's heap, not the CLI's
            if phase == "start":
                gc_started["t"] = time.monotonic()
            elif "t" in gc_started and time.monotonic() - gc_started["t"] >= 0.01:
                gc_pauses.append((info["generation"], round(time.monotonic() - gc_started["t"], 3)))

        gc.callbacks.append(on_gc)
        try:
            t0 = time.monotonic()
            code = mod.main(argv)
            ended = time.monotonic()
        finally:
            gc.callbacks.remove(on_gc)
        # The record and the console first, then the clock split at the wall's
        # start: a late finish names whether the artifact, the wall or the time
        # before the wall existed was late, and any collection that ran. Same
        # bounds as one clock from t0.
        assert capsys.readouterr().out == ""
        assert json.loads(out.read_text())["committed_outcomes"] == [{"outcome_id": 7}]
        (wall,) = walls
        assert code == 3 and ended - wall.started < 0.8 + 0.15, (
            f"inside the wall {ended - wall.started:.3f}s, gc pauses >= 10 ms (generation, s) {gc_pauses}"
        )
        assert ended - t0 < 0.8 + 0.15, (
            f"before the wall started {wall.started - t0:.3f}s, gc pauses >= 10 ms (generation, s) {gc_pauses}"
        )

    @pytest.mark.parametrize("delay", [0.0, 3.0])
    def test_a_line_written_while_working_cannot_hold_the_import_past_the_wall(
        self, tmp_path, capsys, monkeypatch, slow_console, delay
    ):
        """A log line mid-operation is bounded by the work deadline, leaving the reserve.

        The wall's clock holds still from the instant the line is written
        (``_HeldClock``). The line is still cut on real time: the console's
        alarm is armed for the real rest of the work slice, so a stalled sink
        returns at the real work deadline, and the cut is asserted on both
        sides. What the hold removes is the race this case never meant to
        test: the receipt file had to be sealed in the 60 ms between the cut
        (0.72 s) and ``artifact_deadline`` (0.78 s), against a real alarm, and
        a runner that stalled ~80 ms after the cut lost R.json (#11582).
        Writing the receipt inside the wall on real time is
        ``test_import_cli_timeout_receipt_is_written_inside_the_wall``'s job.
        """
        slow_console.update(delay=delay, prefix="PROGRESS")
        returned_at = []
        clock = _HeldClock()
        walls = []
        real_wall = bounds.OperationWall

        def held_wall(seconds, **kw):
            walls.append(real_wall(seconds, monotonic=clock, **kw))
            return walls[-1]

        async def fake_apply(report, **kw):
            clock.hold()
            print("PROGRESS one outcome", file=sys.stderr)
            returned_at.append(time.monotonic())
            return {"status": "applied", "import_key": "k", "committed_outcomes": [{"outcome_id": 7}]}

        monkeypatch.setattr(imp, "apply_archive_plan", fake_apply)
        monkeypatch.setattr(bounds, "OperationWall", held_wall)
        plan = tmp_path / "P.json"
        plan.write_text("{}")
        out = tmp_path / "R.json"
        # Real alarm; only the pytest heap's full collection is kept out of the
        # cut (a C-level collection defers the SIGALRM; see the timeout-receipt case).
        with _a_collection_scans_only_the_cli():
            full_before = _full_collections()
            t0 = time.monotonic()
            code = _load_script("kalshi_archive_import.py").main(
                [
                    "apply", "--plan", str(plan), "--expected-digest", "d", "--max-outcomes", "1",
                    "--max-points", "1", "--deadline", "0.8", "--output", str(out),
                ]
            )
            elapsed = time.monotonic() - t0
            full_during = _full_collections() - full_before
        (wall,) = walls
        assert wall.seconds == 0.8 and len(returned_at) == 1 and clock.held_at is not None
        assert out.exists(), (  # the reserve was left for the artifact
            f"no artifact after {elapsed:.3f}s (exit {code}); the line returned "
            f"{returned_at[0] - wall.started:.3f}s into the wall; "
            f"full collections during the call {full_during} (frozen heap)"
        )
        if delay:
            # The stalled line was cut AT the work deadline: not before it, and
            # by the work deadline's alarm, not the hard deadline's, which
            # cannot fire before ``deadline`` (1 ms: the alarm's tolerance).
            assert wall.work_deadline - 1e-3 <= returned_at[0] < wall.deadline - 1e-3, (
                f"the line returned {returned_at[0] - wall.started:.3f}s into the wall; "
                f"full collections during the call {full_during} (frozen heap)"
            )
            assert code == 3 and elapsed < 0.8 + 0.15
            assert capsys.readouterr().out == ""  # a lost console is not tried again
        else:
            assert code == 0 and json.loads(capsys.readouterr().out)["status"] == "applied"

    @pytest.mark.parametrize("delay", [0.0, 3.0])
    def test_a_line_written_while_planning_cannot_hold_the_planner_past_the_wall(
        self, planner_cli, tmp_path, capsys, slow_console, delay
    ):
        slow_console.update(delay=delay, prefix="PROGRESS")
        seen: list = []
        archive = _archive_handler(seen)

        def handler(request):
            print("PROGRESS one request", file=sys.stderr)
            return archive(request)

        out = tmp_path / "P.json"
        argv = PROFILE[: PROFILE.index("--deadline") + 1] + ["1.0"] + PROFILE[
            PROFILE.index("--deadline") + 2 :
        ]
        with _a_collection_scans_only_the_cli():
            t0 = time.monotonic()
            code, _ = planner_cli(argv + ["--output", str(out)], handler=handler)
            elapsed = time.monotonic() - t0
        assert out.exists()
        if delay:
            assert code == 3 and elapsed < 1.0 + 0.15
        else:
            assert code == 0 and json.loads(capsys.readouterr().out)["artifact"] == str(out)

    def test_a_sink_that_refuses_is_unavailable_never_a_traceback(
        self, tmp_path, capsys, slow_console
    ):
        slow_console["refuse"] = BrokenPipeError("reader went away")
        argv, factory = _hanging_apply(tmp_path, 0.8)
        code = _load_script("kalshi_archive_import.py").main(argv, session_factory=factory)
        out, err = capsys.readouterr()
        assert code == 3 and out == "" and "Traceback" not in err
        assert json.loads((tmp_path / "R.json").read_text())["uncertain_commits"]

    @pytest.mark.parametrize("delay", [0.0, 3.0])
    def test_the_planner_summary_is_delivered_inside_the_wall_too(
        self, planner_cli, tmp_path, capsys, slow_console, delay
    ):
        slow_console["delay"] = delay
        out = tmp_path / "P.json"
        argv = PROFILE[: PROFILE.index("--deadline") + 1] + ["1.0"] + PROFILE[
            PROFILE.index("--deadline") + 2 :
        ]
        t0 = time.monotonic()
        code, _ = planner_cli(argv + ["--output", str(out)])
        elapsed = time.monotonic() - t0
        assert json.loads(out.read_text())["terminal"] == "complete"  # sealed first
        printed = capsys.readouterr().out
        if delay:
            assert code == 3 and elapsed < 1.0 + 0.15 and printed == ""
        else:
            assert code == 0 and json.loads(printed)["artifact"] == str(out)

    def test_no_console_write_starts_past_the_wall(self):
        sent = []

        class Sink:
            def write(self, s):
                sent.append(s)

            def flush(self):
                sent.append("<flush>")

        cap = bounds.ConsoleCap(10_000)
        wall = bounds.OperationWall(0.01, reserve=0.0)
        cap.bind(wall).receipt()
        time.sleep(0.03)
        cap._write(Sink(), "late receipt\n")
        assert sent == [] and cap.unavailable == "wall_expired:console"
        assert cap.undelivered == len("late receipt\n")

    def test_every_bound_write_is_flushed_so_nothing_waits_for_the_exit_flush(self):
        sent = []

        class Sink:
            def write(self, s):
                sent.append(s)

            def flush(self):
                sent.append("<flush>")

        cap = bounds.ConsoleCap(10_000).bind(bounds.OperationWall(30))
        cap._write(Sink(), "receipt\n")
        assert sent == ["receipt\n", "<flush>"] and cap.unavailable is None

    def test_a_slow_serialisation_is_cut_by_the_same_alarm_as_a_slow_sink(self, capsys):
        cap = bounds.ConsoleCap(10_000).install()
        try:
            cap.bind(bounds.OperationWall(0.3, reserve=0.1))

            def slow_render():
                time.sleep(3)
                return "{}"

            t0 = time.monotonic()
            delivered = cap.deliver_receipt(slow_render)
            elapsed = time.monotonic() - t0
        finally:
            cap.restore()
        assert delivered is False and elapsed < 0.3 + 0.15
        assert cap.unavailable == "wall_expired:console" and capsys.readouterr().out == ""

    def test_a_slow_disk_and_a_stalled_console_still_end_at_the_wall_and_claim_nothing(
        self, tmp_path, capsys, monkeypatch, slow_console
    ):
        """Neither record could be made: exit 3 alone, durability UNKNOWN, never "nothing written"."""
        real_fsync = bounds.os.fsync

        def slow_fsync(fd):
            end = time.monotonic() + 3.0
            while time.monotonic() < end:
                time.sleep(0.01)
            return real_fsync(fd)

        monkeypatch.setattr(bounds.os, "fsync", slow_fsync)
        slow_console["delay"] = 3.0
        argv, factory = _hanging_apply(tmp_path, 0.8)
        t0 = time.monotonic()
        code = _load_script("kalshi_archive_import.py").main(argv, session_factory=factory)
        assert code == 3 and time.monotonic() - t0 < 0.8 + 0.15
        assert capsys.readouterr().out == ""
        assert not (tmp_path / "R.json").exists() and not list(tmp_path.glob(".R.json.*.tmp"))

    def test_a_console_lost_once_is_never_sent_to_again(self):
        """A stalled sink may hold a cut buffer: neither a later write nor a flush retries it."""
        sent = []

        class Sink:
            def __init__(self):
                self.fail = True

            def write(self, s):
                if self.fail:
                    self.fail = False
                    raise BrokenPipeError("reader went away")
                sent.append(s)

            def flush(self):
                sent.append("<flush>")

        cap = bounds.ConsoleCap(10_000).bind(bounds.OperationWall(30))
        stream = bounds._CappedStream(cap, Sink())
        stream.write("first\n")
        assert cap.unavailable == "sink_error:BrokenPipeError"
        stream.write("second\n")
        stream.flush()
        assert sent == [] and cap.undelivered == len("first\nsecond\n")


# The real process, its real stdout pipe, its real exit. The pipe is filled
# before the child starts and never read, so any byte the child sends blocks
# in the kernel: the backpressure of a stalled ``| tee`` or a frozen terminal.
# The wall's start is stamped by the child (``time.monotonic`` is system-wide)
# so the bound excludes interpreter start and imports. Run in a child so a
# regression is a killed child and a red test, never a hung suite.
_CONSOLE_PROBE = textwrap.dedent(
    """
    import asyncio, runpy, sys
    from contextlib import asynccontextmanager
    from types import SimpleNamespace

    backend, stamp, mode = sys.argv[1], sys.argv[2], sys.argv[3]
    sys.path.insert(0, backend)
    if mode == "strawman":
        # The rig's own check: an ordinary block-buffered print of the receipt
        # into this pipe returns at once and the INTERPRETER'S EXIT FLUSH then
        # waits on the pipe. This must be killed, or the rig proves nothing.
        print("{" + "x" * 2048 + "}")
        sys.exit(3)
    from app.services import kalshi_archive_apply as imp
    from app.services import kalshi_archive_bounds as bounds

    class StampedWall(bounds.OperationWall):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            with open(stamp, "w") as fh:
                fh.write(repr(self.started))

    bounds.OperationWall = StampedWall

    class HangingCommit:
        async def execute(self, clause, params=None):
            sql = str(clause)
            if "to_regclass" in sql:
                return SimpleNamespace(scalar=lambda: True)
            if "INSERT INTO kalshi_archive_imports" in sql:
                return SimpleNamespace(scalar_one=lambda: 41)
            return SimpleNamespace()

        async def commit(self):
            await asyncio.sleep(3600)

    @asynccontextmanager
    async def factory():
        yield HangingCommit()

    real = imp.apply_archive_plan
    imp.apply_archive_plan = lambda report, **kw: real(report, session_factory=factory, **kw)
    sys.argv = [backend + "/scripts/kalshi_archive_import.py"] + sys.argv[4:]
    runpy.run_path(sys.argv[0], run_name="__main__")  # the script's own exit path
    """
)

PROBE_DEADLINE_S = 3.0


def _full_pipe():
    import fcntl
    import os

    r, w = os.pipe()
    flags = fcntl.fcntl(w, fcntl.F_GETFL)
    fcntl.fcntl(w, fcntl.F_SETFL, flags | os.O_NONBLOCK)
    filled = 0
    for chunk in (4096, 1):
        while True:
            try:
                filled += os.write(w, b"f" * chunk)
            except BlockingIOError:
                break
    fcntl.fcntl(w, fcntl.F_SETFL, flags)
    return r, w, filled


def _console_probe(tmp_path, mode: str, *, stalled: bool) -> dict:
    import os

    report = asyncio.run(_a_plan())
    plan = tmp_path / "P.json"
    plan.write_text(json.dumps(report))
    stamp, out = tmp_path / "wall.started", tmp_path / "R.json"
    args = [
        "apply", "--plan", str(plan), "--expected-digest", report["plan_digest"],
        "--max-outcomes", "1", "--max-points", "26", "--deadline", str(PROBE_DEADLINE_S),
        *_attended_argv(tmp_path, report), "--write", "--output", str(out),
    ]
    cmd = [sys.executable, "-c", _CONSOLE_PROBE, str(BACKEND), str(stamp), mode, *args]
    if not stalled:
        done = subprocess.run(cmd, capture_output=True, text=True, timeout=OUTER_LIMIT_S)
        return {"code": done.returncode, "stdout": done.stdout, "stderr": done.stderr,
                "receipt": out, "stamp": stamp}
    r, w, filled = _full_pipe()
    try:
        child = subprocess.Popen(cmd, stdout=w, stderr=subprocess.PIPE)
        os.close(w)
        try:
            code = child.wait(timeout=OUTER_LIMIT_S)
            ended, killed = time.monotonic(), False
        except subprocess.TimeoutExpired:
            child.kill()
            code, ended, killed = child.wait(), time.monotonic(), True
        stderr = child.stderr.read().decode(errors="replace")
        child.stderr.close()
        os.set_blocking(r, False)
        drained = 0
        while True:
            try:
                chunk = os.read(r, 65536)
            except BlockingIOError:
                break
            if not chunk:
                break
            drained += len(chunk)
    finally:
        os.close(r)
    started = float(stamp.read_text()) if stamp.exists() else None
    return {"code": code, "killed": killed, "stderr": stderr, "receipt": out,
            "past_wall": None if started is None else ended - started,
            "console_bytes": drained - filled}


class TestConsoleWallInARealProcess:
    def test_a_stalled_stdout_pipe_ends_the_process_at_the_wall(self, tmp_path):
        got = _console_probe(tmp_path, "import", stalled=True)
        assert not got["killed"], f"held past {OUTER_LIMIT_S}s: {got['stderr']}"
        assert got["code"] == 3, got["stderr"]
        assert got["past_wall"] < PROBE_DEADLINE_S + 0.5
        assert got["console_bytes"] == 0  # the stalled console got nothing, not a cut line
        receipt = json.loads(got["receipt"].read_text())
        assert receipt["uncertain_commits"][-1]["error"] == "acknowledgement_not_received"
        assert receipt["readback_owed"]["never"] == [
            "retry the apply", "restore automatically", "assume zero rows"
        ]
        assert "Traceback" not in got["stderr"]

    def test_control_a_drained_pipe_gets_the_whole_receipt_and_the_same_exit(self, tmp_path):
        got = _console_probe(tmp_path, "import", stalled=False)
        assert got["code"] == 3, got["stderr"]
        summary = json.loads(got["stdout"])
        receipt = json.loads(got["receipt"].read_text())
        assert summary["uncertain_commits"] == receipt["uncertain_commits"]
        assert summary["artifact_bytes"] == got["receipt"].stat().st_size

    def test_control_the_pipe_really_holds_an_ordinary_exit_flush(self, tmp_path):
        got = _console_probe(tmp_path, "strawman", stalled=True)
        assert got["killed"] and got["console_bytes"] == 0


class TestStatic:
    def test_the_write_path_fences_identity_and_the_dry_run_cannot(self):
        assert "FOR SHARE OF fo, fm" in imp.CURRENT_INPUT_LOCK_SQL
        assert "FOR SHARE" in imp.EVENT_LOCK_SQL
        assert "FOR SHARE" not in imp.CURRENT_INPUT_SQL  # read-only transactions refuse it
        src = inspect.getsource(imp._apply_outcome)
        assert "_locked_input(session, oid)" in src

    def test_the_fence_fields_are_the_fingerprint_fields(self):
        from app.utils.kalshi_archive_history import FINGERPRINT_FIELDS

        src = inspect.getsource(imp._locked_input)
        for name in FINGERPRINT_FIELDS:
            assert f"{name}=" in src, name

    def test_the_rail_writes_nothing_beyond_the_archive_store(self):
        src = inspect.getsource(imp).upper()
        assert "FUTURES_ODDS_SNAPSHOTS" not in src.replace("FROM FUTURES_ODDS_SNAPSHOTS", "")
        for table in ("INSERT INTO FUTURES", "UPDATE FUTURES", "UPDATE EVENTS", "DELETE FROM FUTURES"):
            assert table not in src
        assert "INSERT" not in inspect.getsource(bounds).upper()

    def test_the_archive_forecast_flag_is_still_false(self):
        from app.utils import kalshi_archive_forecast as fc

        flags = [v for k, v in vars(fc).items() if k.isupper() and isinstance(v, bool)]
        assert flags and not any(flags)
