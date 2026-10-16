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
import inspect
import json
import time
from contextlib import asynccontextmanager
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

    def test_import_cli_wall_during_a_commit_reports_it_in_flight(self, tmp_path, capsys):
        report = asyncio.run(_a_plan())
        plan = tmp_path / "P.json"
        plan.write_text(json.dumps(report))
        out = tmp_path / "R.json"

        async def hang():
            await asyncio.sleep(10)

        mod = _load_script("kalshi_archive_import.py")
        t0 = time.monotonic()
        code = mod.main(
            [
                "apply", "--plan", str(plan), "--expected-digest", report["plan_digest"],
                "--max-outcomes", "1", "--max-points", "26", "--deadline", "0.8",
                "--write", "--output", str(out),
            ],
            session_factory=_factory(_CommitSession(hang)),
        )
        assert time.monotonic() - t0 < 3.0 and code == 3
        receipt = json.loads(out.read_text())
        assert receipt["status"] == "incomplete"
        assert receipt["stopped"] == "wall_expired:create_import"
        assert receipt["uncertain_commits"][-1]["error"] == "acknowledgement_not_received"
        assert receipt["readback_owed"]["never"] == [
            "retry the apply", "restore automatically", "assume zero rows"
        ]

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
