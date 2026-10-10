"""#10657 — a socket consumer's flush loop ends with its run, even when a
cancellation is lost.

Production 2026-10-07 02:53–02:56Z, worker-ws.1: every ~6 s
`live_blend_refresh[kalshi]: batch failed for 33 events` and `… for 9 events`,
`RuntimeError: kalshi: consumer sessions are closed; this run has drained`,
unchanged across a Kalshi recycle while the current run's blend read
`errors=0`. The 6 s is the 2 s cadence plus the 5 s failed-retry hold: the
flush loops of EARLIER runs were still calling `refresh_pending` on their own
closed sessions. The consumers stopped the loop with `flush_task.cancel()`
alone, and `run_flush_cadence` was `while True`, so one cancellation lost
inside a flush's dependencies left the loop running forever.

The consumer-level arms run the REAL Kalshi and Polymarket consumers with the
#9462 rig (socket and database faked) and a refresher that loses exactly one
cancellation — the premise is asserted, so the guard cannot pass vacuously.
"""

from __future__ import annotations

import asyncio
import logging
import time

import pytest

import app.tasks.live_blend_refresh as lbr
from tests.test_ws_admission_mapped_legs_9462 import (
    _arm,
    _install_quiet_socket,
    _install_session,
    _timing,
)
from tests.test_ws_flush_cadence_10090 import _FakeTime


# ------------------------------------------------- the cadence, unit ----


class TestTheCadenceHonoursStop:
    async def test_stop_set_during_a_flush_starts_no_other(self, monkeypatch):
        fake = _FakeTime(monkeypatch)
        stop = asyncio.Event()
        calls = []

        async def flush(started):
            calls.append(started)
            stop.set()  # the consumer stops the loop while this flush runs
            return True

        await asyncio.wait_for(lbr.run_flush_cadence(flush, 2.0, stop=stop), 1)
        assert len(calls) == 1
        assert fake.slept == [2.0]

    async def test_stop_set_during_the_sleep_flushes_nothing(self, monkeypatch):
        fake = _FakeTime(monkeypatch)
        stop = asyncio.Event()
        calls = []
        real_sleep = asyncio.sleep

        async def _sleep(seconds):
            fake.slept.append(seconds)
            fake.t += seconds
            stop.set()
            await real_sleep(0)

        monkeypatch.setattr(asyncio, "sleep", _sleep)

        async def flush(started):
            calls.append(started)
            return True

        await asyncio.wait_for(lbr.run_flush_cadence(flush, 2.0, stop=stop), 1)
        assert calls == []

    async def test_already_stopped_never_flushes(self, monkeypatch):
        _FakeTime(monkeypatch)
        stop = asyncio.Event()
        stop.set()
        calls = []

        async def flush(started):
            calls.append(started)
            return True

        await asyncio.wait_for(lbr.run_flush_cadence(flush, 2.0, stop=stop), 1)
        assert calls == []


class TestReapStoppedLoops:
    async def test_finished_tasks_reap_to_zero(self):
        async def quick():
            return None

        task = asyncio.create_task(quick())
        await asyncio.sleep(0)
        assert await lbr.reap_stopped_loops("kalshi", (task, None)) == 0

    async def test_a_loop_that_ignores_stop_is_reported_by_name(self, caplog):
        release = asyncio.Event()

        async def stubborn():
            while not release.is_set():
                try:
                    await asyncio.sleep(0.01)
                except asyncio.CancelledError:
                    continue  # the lost cancellation, every time

        task = asyncio.create_task(stubborn(), name="kalshi-flush-loop")
        await asyncio.sleep(0)
        task.cancel()
        with caplog.at_level(logging.ERROR, logger=lbr.logger.name):
            still = await lbr.reap_stopped_loops("kalshi", (task,), timeout_s=0.05)
        assert still == 1
        assert "kalshi-flush-loop" in caplog.text
        release.set()
        await asyncio.wait_for(task, 1)


# ------------------------------------------- the real consumers ----

PERIOD = 0.02
WORK = 0.05


class _LosesOneCancel(lbr.LiveBlendRefresher):
    """Every quiet flush reaches `refresh_pending`. The first cancellation
    that lands in it is swallowed — standing in for a dependency (a 3.11
    `wait_for`/`timeout` race) that loses one — and every later one is not."""

    instances: list = []

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.entered: list[float] = []
        self.swallowed = 0
        _LosesOneCancel.instances.append(self)

    async def refresh_pending(self, *, flush_started=None, defer_event_ids=()):
        self.entered.append(time.monotonic())
        try:
            await asyncio.sleep(WORK)
        except asyncio.CancelledError:
            if self.swallowed:
                raise
            self.swallowed += 1
        return self.stats


ARMS = pytest.mark.parametrize("arm", ["kalshi", "polymarket"])


class TestTheFlushLoopEndsWithItsRun:
    @ARMS
    async def test_a_lost_cancellation_does_not_outlive_the_run(
        self, monkeypatch, arm,
    ):
        module, consumer, slate = _arm(monkeypatch, arm)
        monkeypatch.setattr(_LosesOneCancel, "instances", [])
        monkeypatch.setattr(lbr, "LiveBlendRefresher", _LosesOneCancel)
        monkeypatch.setattr(module, "PRICE_FLUSH_SECONDS", PERIOD)
        _install_quiet_socket(monkeypatch)
        _timing(monkeypatch, module, refresh=0.3)
        _install_session(monkeypatch, slate, lambda n: [])

        stats = await asyncio.wait_for(consumer(), timeout=5)
        returned = time.monotonic()
        # Several cadence periods: the pre-#10657 loop re-entered here.
        await asyncio.sleep(10 * (PERIOD + WORK))

        (refresher,) = _LosesOneCancel.instances
        # Premise: the recycle's cancellation landed in a flush and was lost.
        assert refresher.swallowed == 1
        after = [t for t in refresher.entered if t > returned]
        assert after == [], f"flush loop ran {len(after)}x after its run returned"
        assert stats["loops_unreaped"] == 0
