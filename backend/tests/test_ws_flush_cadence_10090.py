"""#10090 — a venue price waits for the flush period, not the period PLUS the work.

Production 2026-10-06 16:01:37→16:02:37Z, the Kalshi socket's own stats line:
29→37 flushes in 60 s while ~4,600 updates were buffered, i.e. one flush per
~7.5 s on a 2 s setting. Both sockets slept `PRICE_FLUSH_SECONDS` AFTER each
flush returned, so every second the flush spent writing and stamping was added
to the interval, and a tick that just missed a batch waited for both.

The repair has two halves and each has its own guard here:

1. The cadence (`run_flush_cadence`): flushes start a period apart, start to
   start; a slow flush is followed at once by the next, never overlapped by it;
   a failed write still waits a full period before its retry.
2. The per-event floor read on the FLUSH-START clock. Spacing flushes by their
   starts makes the moments `refresh` runs uneven (each trails its flush's
   write), so on the call-time clock a slow write followed by a fast one put
   two refreshes under the 2 s floor and deferred the second flush's committed
   price a whole extra flush. Starts are a period apart by construction.

The consumer-level arms run the REAL Kalshi and Polymarket consumers (socket
and database faked, as in the #9462 rig) so the guard reads the shipped loops,
not a copy of their shape.
"""

from __future__ import annotations

import ast
import asyncio
import inspect
import time
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

import app.tasks.kalshi_ws as kalshi_task
import app.tasks.live_blend_refresh as lbr
import app.tasks.polymarket_ws as poly_task
from tests.test_pm_same_flush_fresh_admission_10090 import cadence_redis  # noqa: F401
from tests.test_event_frame_batching_10659 import private_redis_socket  # noqa: F401
from tests.test_ws_admission_mapped_legs_9462 import (
    _arm,
    _install_quiet_socket,
    _install_session,
    _timing,
)


# ------------------------------------------------- the cadence, unit ----


class _FakeTime:
    """Drives `run_flush_cadence` through the refresher's one clock seam."""

    def __init__(self, monkeypatch, t: float = 1_000_000.1):
        self.t = t
        self.slept: list[float] = []
        monkeypatch.setattr(lbr, "_mono", lambda: self.t)
        real_sleep = asyncio.sleep

        async def _sleep(seconds):
            self.slept.append(seconds)
            self.t += seconds
            await real_sleep(0)

        monkeypatch.setattr(asyncio, "sleep", _sleep)


class _Enough(Exception):
    pass


async def _drive(fake: _FakeTime, works, *, period=2.0, results=None):
    """Run the cadence over flushes costing `works[i]` seconds; returns each
    flush's (passed start, clock at entry, clock at exit)."""
    calls: list[tuple[float, float, float]] = []
    in_flight = {"n": 0}

    async def flush(started):
        in_flight["n"] += 1
        assert in_flight["n"] == 1, "two flushes in flight"
        entered = fake.t
        fake.t += works[len(calls)]
        calls.append((started, entered, fake.t))
        in_flight["n"] -= 1
        if len(calls) == len(works):
            raise _Enough
        return True if results is None else results[len(calls) - 1]

    with pytest.raises(_Enough):
        await lbr.run_flush_cadence(flush, period)
    return calls


class TestTheCadenceIsStartToStart:
    async def test_work_is_not_added_to_the_interval(self, monkeypatch):
        fake = _FakeTime(monkeypatch)
        t0 = fake.t
        calls = await _drive(fake, [0.5, 0.5, 0.5, 0.5])
        starts = [c[0] - t0 for c in calls]
        # Pre-#10090: 2.0, 4.5, 7.0, 9.5 — the 0.5 s of work rode every cycle.
        assert starts == pytest.approx([2.0, 4.0, 6.0, 8.0])

    async def test_a_slow_flush_is_followed_at_once_never_overlapped(
        self, monkeypatch,
    ):
        """The production shape: ~5.5 s of work on a 2 s period."""
        fake = _FakeTime(monkeypatch)
        t0 = fake.t
        calls = await _drive(fake, [5.5, 5.5, 5.5])
        # Each starts the moment the last returned: 7.5 s → 5.5 s per cycle.
        assert [c[1] - t0 for c in calls] == pytest.approx([2.0, 7.5, 13.0])
        for (_, _, done), (_, entered, _) in zip(calls, calls[1:]):
            assert entered >= done
        # The ceiling: starts are never closer than one period.
        starts = [c[0] for c in calls]
        assert all(b - a >= 2.0 - 1e-9 for a, b in zip(starts, starts[1:]))

    async def test_a_failed_write_still_waits_a_full_period(self, monkeypatch):
        """The period is also the retry interval (Q491): a database in trouble
        is not asked again any sooner than before."""
        fake = _FakeTime(monkeypatch)
        t0 = fake.t
        calls = await _drive(
            fake, [3.0, 0.1, 0.1], results=[False, True, True],
        )
        entries = [c[1] - t0 for c in calls]
        # Failed at 5.0 → retried at 7.0 (not at once, though 3 s > period).
        assert entries == pytest.approx([2.0, 7.0, 9.0])

    async def test_the_first_flush_waits_one_period(self, monkeypatch):
        fake = _FakeTime(monkeypatch)
        t0 = fake.t
        calls = await _drive(fake, [0.1])
        assert calls[0][1] - t0 == pytest.approx(2.0)


# --------------------------------------- the floor on the flush clock ----


class _Recording(lbr.LiveBlendRefresher):
    def __init__(self, **kw):
        super().__init__("kalshi", **kw)
        self.batches: list[tuple[list[int], float]] = []

    async def _refresh_batch(
        self, event_ids, now, *, prepared=None, on_committed=None, publish_committed=None
    ):
        self.batches.append((sorted(event_ids), now))
        for event_id in event_ids:
            self._last_refresh_at[event_id] = now
        if on_committed is not None:
            on_committed(event_ids)


class TestTheFloorReadsTheFlushStart:
    @pytest.fixture
    def clock(self, monkeypatch):
        c = {"t": 1000.0}
        monkeypatch.setattr(lbr, "_mono", lambda: c["t"])
        return c

    async def test_grouped_recording_accepts_preparation_and_commit_callback(self, clock):
        r = _Recording()

        async def prepared(event_ids):
            assert set(event_ids) == set(range(1, 9))
            return {}

        r._prepare_groups = prepared
        clock["t"] = 1001.5
        await r.refresh(range(1, 9), flush_started=1000.0)
        # e0b52e11ed: two or more due events commit one event per transaction;
        # every one still reads the flush start, not the call-time clock.
        assert sorted(r.batches) == [([event_id], 1000.0) for event_id in range(1, 9)]
        assert r.stats["errors"] == 0
        assert r._failed_hold_until == {}
        assert r._last_refresh_at == {event_id: 1000.0 for event_id in range(1, 9)}

    async def test_a_slow_write_then_a_fast_one_stamps_both_flushes(
        self, clock,
    ):
        r = _Recording()
        clock["t"] = 1001.5          # flush 1 started 1000.0; its write took 1.5 s
        await r.refresh([1], flush_started=1000.0)
        clock["t"] = 1002.1          # flush 2 started 1002.0; its write took 0.1 s
        await r.refresh([1], flush_started=1002.0)
        assert [b[0] for b in r.batches] == [[1], [1]]
        assert r._throttle_deferred == set()

    async def test_control_the_call_time_clock_defers_that_flush(self, clock):
        """The defect the half above closes, on the unchanged no-argument path:
        refreshes 0.6 s apart on the call-time clock fall under the floor."""
        r = _Recording()
        clock["t"] = 1001.5
        await r.refresh([1])
        clock["t"] = 1002.1
        await r.refresh([1])
        assert [b[0] for b in r.batches] == [[1]]
        assert r._throttle_deferred == {1}

    async def test_once_per_floor_inside_one_flush(self, clock):
        """Two refreshes inside one flush (Polymarket's chunked path) share its
        start: the second, still inside the floor, waits.

        #10090 Argon Rank 2 changed the rest of this test's old contract
        ("still once per flush, even when the flush ran past the floor"): a
        Kalshi main flush runs 3-7 s, and a live game stamped once in it then
        waited for the NEXT flush (15338515, held_s 4.300). Past the floor —
        the newest clock this refresher was handed, advanced by the time since
        — the second refresh of one flush stamps again."""
        r = _Recording()
        clock["t"] = 1000.4
        await r.refresh([1], flush_started=1000.0)
        clock["t"] = 1000.45
        await r.refresh([1], flush_started=1000.0)
        assert [b[0] for b in r.batches] == [[1]]
        assert r._throttle_deferred == {1}
        clock["t"] = 1002.5
        await r.refresh([1], flush_started=1000.0)
        assert [b[0] for b in r.batches] == [[1], [1]]
        assert r._throttle_deferred == set()
        # lane1's R1 on 0b2a452d: that stamp is recorded on the flush's start
        # (1000.0), but the floor runs from the stamp, so a quarter-second
        # later, still in the same flush, it waits.
        clock["t"] = 1002.75
        await r.refresh([1], flush_started=1000.0)
        assert [b[0] for b in r.batches] == [[1], [1]]
        assert r._throttle_deferred == {1}

    async def test_starts_a_period_apart_at_uptime_magnitude_are_due(
        self, clock,
    ):
        """`(t + p) - t` can come back short of `p` (`WS_PRICE_FLUSH_SECONDS`
        is an env knob): at t = 1,000,000.1 and p = 0.1 it is
        0.09999999997671694, which would throttle the flush the floor admits."""
        r = _Recording(min_refresh_interval_s=0.1)
        t = 1_000_000.1
        assert (t + 0.1) - t < 0.1  # the specimen really is short
        clock["t"] = t + 0.01
        await r.refresh([1], flush_started=t)
        clock["t"] = t + 0.11
        await r.refresh([1], flush_started=t + 0.1)
        assert len(r.batches) == 2

    async def test_the_failed_hold_is_on_the_same_clock(self, clock):
        r = _Recording()

        async def _boom(event_ids, now):
            raise RuntimeError("db down")

        r._refresh_batch = _boom
        clock["t"] = 1001.0
        await r.refresh([1], flush_started=1000.0)
        assert r._failed_hold_until == {1: 1000.0 + r.failed_retry_interval_s}


# ------------------------------------------- the real consumers ----

PERIOD = 0.05
WORK = 0.10


class _SlowFlush(lbr.LiveBlendRefresher):
    """Every quiet flush reaches `refresh_pending`; making it cost WORK stands
    in for the write + stamp a busy flush spends."""

    instances: list = []
    #: Set once OBSERVED periodic flushes have finished (the test's own).
    observed: asyncio.Event

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.calls: list[tuple[float, float, float | None]] = []
        _SlowFlush.instances.append(self)

    async def refresh_pending(self, *, flush_started=None, defer_event_ids=()):
        entered = time.monotonic()
        await asyncio.sleep(WORK)
        self.calls.append((entered, time.monotonic(), flush_started))
        if sum(c[2] is not None for c in self.calls) >= OBSERVED:
            _SlowFlush.observed.set()
        return self.stats


ARMS = pytest.mark.parametrize("arm", ["kalshi", "polymarket"])

#: The run ends once this many periodic flushes have finished, not on a
#: wall-clock timer. A fixed 0.7 s run counted whatever fit in it: one
#: ~0.5 s stall of the runner's loop before the first flush (PR #11083's
#: backend shard, CI 38837110373, both attempts, on a tree whose only change
#: from a green parent was two ci.yml lines) left room for ONE, and a
#: cadence that never flushed at all failed the same way as a busy runner.
OBSERVED = 3
#: Ample for OBSERVED flushes of WORK each, plus a stall; reaching it is the
#: failure "the consumer stopped flushing", reported with what it did see.
OBSERVE_BOUND_S = 5.0
#: The run's own recycle timer, set beyond the bound so it never ends the
#: observation; the test ends the run itself once it has seen enough.
NO_RECYCLE_S = 60.0


def _install_cadence_session(monkeypatch, slate):
    """Extend the existing empty-debt DB seam with its owner transaction.

    Ownership queries are not slate reads and must not consume positional
    slate answers or fail/retry during the cadence measurement.
    """
    from app.tasks import base
    from sqlalchemy.sql.dml import Insert

    state = _install_session(monkeypatch, slate, lambda n: [])
    factory = base.get_task_session
    state["owner_claims"] = 0

    @asynccontextmanager
    async def session(*args, **kwargs):
        async with factory(*args, **kwargs) as db:
            original = db.execute

            async def execute(statement, parameters=None):
                sql = str(statement)
                owner = poly_task.PM_WITHDRAWAL_DEBT_SOURCE + "_owner"
                if sql == "SELECT pg_try_advisory_xact_lock(hashtextextended(:key, 0))":
                    assert parameters == {"key": owner}
                    return SimpleNamespace(scalar_one=lambda: True)
                assert parameters is None
                values = statement.compile().params
                if values.get("source_1") == owner and sql.startswith("SELECT owed_chart_points.id"):
                    return SimpleNamespace(scalar_one_or_none=lambda: None)
                if isinstance(statement, Insert) and values.get("source") == owner:
                    state["owner_claims"] += 1
                    return SimpleNamespace(scalar_one=lambda: 1)
                return await original(statement)

            async def commit():
                pass  # the empty-debt fixture acknowledges only its owner row

            db.execute, db.commit = execute, commit
            yield db

    monkeypatch.setattr(base, "get_task_session", session)
    return state


@pytest.mark.usefixtures("cadence_redis")
class TestTheRealConsumersFlushStartToStart:
    @ARMS
    async def test_the_next_flush_does_not_sleep_after_a_slow_one(
        self, monkeypatch, arm,
    ):
        module, consumer, slate = _arm(monkeypatch, arm)
        monkeypatch.setattr(_SlowFlush, "instances", [])
        monkeypatch.setattr(_SlowFlush, "observed", asyncio.Event(), raising=False)
        monkeypatch.setattr(lbr, "LiveBlendRefresher", _SlowFlush)
        monkeypatch.setattr(module, "PRICE_FLUSH_SECONDS", PERIOD)
        _install_quiet_socket(monkeypatch)
        _timing(monkeypatch, module, refresh=NO_RECYCLE_S)
        db_state = _install_cadence_session(monkeypatch, slate)

        run = asyncio.create_task(consumer())
        seen = asyncio.create_task(_SlowFlush.observed.wait())
        try:
            await asyncio.wait(
                {run, seen}, timeout=OBSERVE_BOUND_S,
                return_when=asyncio.FIRST_COMPLETED,
            )
        finally:
            seen.cancel()
            # Shutdown, as the runner stops it: the consumer's own final drain
            # runs (the one call with no start), then the cancellation travels.
            run.cancel()
            (ended,) = await asyncio.wait_for(
                asyncio.gather(run, return_exceptions=True), timeout=5,
            )
        if isinstance(ended, Exception):
            raise ended

        (refresher,) = _SlowFlush.instances
        assert refresher.preview is True
        if arm == "polymarket":
            assert db_state["owner_claims"] == 1
        # The final drain passes no start; the periodic flushes all do.
        periodic = [c for c in refresher.calls if c[2] is not None]
        assert len(periodic) >= 3, refresher.calls
        gaps = [
            nxt[0] - prev[1] for prev, nxt in zip(periodic, periodic[1:])
        ]
        # Pre-#10090 every gap was the full PERIOD sleep (0.05 s) after WORK.
        assert max(gaps) < PERIOD / 2, gaps
        starts = [c[2] for c in periodic]
        assert all(
            b - a >= PERIOD - 1e-6 for a, b in zip(starts, starts[1:])
        ), starts


class TestEveryFlushRefreshCarriesTheFlushStart:
    """The quiet-socket arm above reaches only `refresh_pending`. A price-
    carrying flush reaches `refresh`, from one site in the Kalshi flush and
    three in the Polymarket one (which also has two quiet arms); a site that drops the start reads the
    call-time clock and reopens the deferral. The SET of sites is pinned, so
    a new one is a red test until it is checked too."""

    EXPECTED = {
        "_run_kalshi_ws_consumer": {"refresh": 1, "refresh_pending": 1},
        # bd506333e8: a second quiet arm stamps a cohort an earlier chunk's
        # stamp excluded; it passes the flush start like the first. #10090: a
        # committed bridged cohort's stamp starts at the top of a timed flush.
        "_run_polymarket_ws_consumer": {"refresh": 3, "refresh_pending": 2},
    }

    @pytest.mark.parametrize(
        "module, consumer",
        [(kalshi_task, "_run_kalshi_ws_consumer"),
         (poly_task, "_run_polymarket_ws_consumer")],
    )
    def test_each_site_passes_flush_started(self, module, consumer):
        tree = ast.parse(inspect.getsource(module))
        (outer,) = [
            n for n in ast.walk(tree)
            if isinstance(n, ast.AsyncFunctionDef) and n.name == consumer
        ]
        # 81fc5dba42: Polymarket's `flush_prices` enters the catalog boundary
        # and awaits `_flush_prices`, the body that holds the sites.
        nested = {
            n.name: n for n in ast.walk(outer) if isinstance(n, ast.AsyncFunctionDef)
        }
        flush = nested.get("_flush_prices") or nested["flush_prices"]
        counts: dict[str, int] = {}
        for call in ast.walk(flush):
            if not (
                isinstance(call, ast.Call)
                and isinstance(call.func, ast.Attribute)
                and isinstance(call.func.value, ast.Name)
                and call.func.value.id == "blend_refresher"
                and call.func.attr in ("refresh", "refresh_pending")
            ):
                continue
            counts[call.func.attr] = counts.get(call.func.attr, 0) + 1
            passed = {
                kw.arg: kw.value for kw in call.keywords if kw.arg is not None
            }
            assert "flush_started" in passed, (consumer, ast.unparse(call))
            assert ast.unparse(passed["flush_started"]) == "flush_started"
        assert counts == self.EXPECTED[consumer]
