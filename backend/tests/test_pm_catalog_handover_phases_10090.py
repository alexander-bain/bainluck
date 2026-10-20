"""#10090 — one compact line says where a PM catalog handover's blocked time went.

While `changing` is set every PM flush waits, so a slow handover delays every
game's next price. The line separates the active-flush drain, the stamp join,
buffer-lock acquisition, the map body and the open-socket handoff, reports the
pre-boundary reads beside them, and still lands — once — when the handover is
cancelled or fails. Lifecycle semantics (changing released, stamp debt adopted,
later flushes admitted) are unchanged.
"""

import asyncio
import json
import logging
from types import SimpleNamespace

import pytest
import websockets

from app.tasks import live_blend_refresh as blend
from app.tasks import polymarket_ws as task
from tests.test_pm_open_cycle_lifetime_10090 import CatalogRig, until
from tests.test_ws_consumer_session_lifetime_2471 import _install
from tests.test_ws_flush_retry_q491 import POLY_SLATE_LIVE

LOGGER = "app.tasks.polymarket_ws"
PREFIX = "Polymarket WS catalog handover: "


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


def handover_lines(caplog):
    return [r.getMessage() for r in caplog.records if r.getMessage().startswith(PREFIX)]


class Rig:
    """A real boundary with one held flush and one held stamp task."""

    def __init__(self):
        self.boundary = task._PMCatalogFlushBoundary()
        self.clock = Clock()
        self.flush_release = asyncio.Event()
        self.stamp_release = asyncio.Event()
        self.buffer_lock = asyncio.Lock()
        self.adopted = []
        self.stopped = 0
        refresher = SimpleNamespace(
            adopt_pending=lambda fresh: self.adopted.append(set(fresh)),
            stop_admitting=self.stop_admitting,
        )
        self.owner = self.boundary.stamp_owner(refresher)
        self.owner.fresh = {7}

    def stop_admitting(self):
        self.stopped += 1

    def successor(self):
        """#10090 settle: the one call the flush in flight when games are
        fenced may start, which the handover joins under the fence."""
        self.successor_release = asyncio.Event()
        self.owner.task = asyncio.create_task(self.successor_release.wait())
        self.owner.events = {7}

    async def start(self, standalone=False):
        async def flush():
            async with self.boundary.flushing(standalone=standalone):
                await self.flush_release.wait()

        self.flush = asyncio.create_task(flush())
        self.owner.task = asyncio.create_task(self.stamp_release.wait())
        self.owner.events = {7}
        await until(lambda: self.boundary.active == 1)

    def timing(self):
        return task._PMCatalogHandoverTiming(
            "timer", slate_read_s=0.4, open_read_s=1.2, clock=self.clock
        )

    def handover(self, timing, fail_in=None):
        async def run():
            async with self.boundary.updating(timing):
                timing.enter("lock")
                async with self.buffer_lock:
                    timing.enter("map")
                    self.clock.now += 0.05
                    if fail_in == "map":
                        raise RuntimeError("map body broke")
                timing.enter("open")
                self.clock.now += 0.01

        return asyncio.create_task(run())

    async def later_flush_admitted(self, standalone=False):
        async def later():
            async with self.boundary.flushing(standalone=standalone):
                return True

        return await asyncio.wait_for(later(), 5)


@pytest.mark.asyncio
async def test_each_phase_owns_its_induced_wait_and_one_line_lands(caplog):
    caplog.set_level(logging.INFO, logger=LOGGER)
    rig = Rig()
    await rig.start()
    await rig.buffer_lock.acquire()
    timing = rig.timing()
    handover = rig.handover(timing)
    # #10090 settle: the running stamp returns with games still flowing and
    # its door open — `fence` time, outside `blocked`.
    await until(lambda: timing.phase == "fence")
    await asyncio.sleep(0.01)
    assert not rig.boundary.changing and rig.stopped == 0
    assert await rig.later_flush_admitted()  # a game flush runs beside it
    rig.clock.now += 3.0  # the running stamp
    rig.stamp_release.set()
    await until(lambda: rig.boundary.changing)
    assert timing.phase == "drain" and timing.flushes == 1

    rig.successor()  # the flush in flight starts the next call
    rig.clock.now += 2.0  # the active flush's remaining write
    rig.flush_release.set()
    await until(lambda: timing.phase == "stamps")
    assert rig.stopped == 1  # the join closed the door before waiting
    rig.clock.now += 1.5  # the successor stamp
    rig.successor_release.set()
    await until(lambda: timing.phase == "lock")
    assert rig.boundary.changing  # flushes are still held behind the lock
    rig.clock.now += 0.5  # buffer-lock holder
    rig.buffer_lock.release()
    await asyncio.wait_for(handover, 5)
    await rig.flush

    assert timing.durations == pytest.approx(
        {
            "fence": 3.0,
            "drain": 2.0,
            "stamps": 1.5,
            "lock": 0.5,
            "map": 0.05,
            "open": 0.01,
        }
    )
    assert timing.blocked_s == pytest.approx(4.06)
    assert sum(timing.durations.values()) - timing.durations["fence"] == pytest.approx(
        timing.blocked_s
    )
    assert handover_lines(caplog) == [
        PREFIX + "reason=timer outcome=ok slate_read=0.400s open_read=1.200s "
        "fence=3.000s drain=2.000s stamps=1.500s lock=0.500s map=0.050s open=0.010s "
        "blocked=4.060s flushes_at_start=1"
    ]
    assert not rig.boundary.changing and rig.boundary.stamps.task is None
    assert rig.adopted == []  # a completed stamp keeps its committed cohort
    assert await rig.later_flush_admitted()


@pytest.mark.asyncio
async def test_cancel_during_drain_releases_and_logs_once(caplog):
    caplog.set_level(logging.INFO, logger=LOGGER)
    rig = Rig()
    await rig.start()
    rig.stamp_release.set()  # the settled call has returned
    timing = rig.timing()
    handover = rig.handover(timing)
    await until(lambda: rig.boundary.changing)
    rig.successor()  # started by the flush the drain waits on
    rig.clock.now += 1.25
    handover.cancel()
    with pytest.raises(asyncio.CancelledError):
        await handover

    assert not rig.boundary.changing
    assert rig.boundary.stamps.task is not None  # drain never reached the join
    assert rig.stopped == 0
    (line,) = handover_lines(caplog)
    assert "outcome=cancelled@drain" in line
    assert "fence=0.000s" in line
    assert "drain=1.250s stamps=- lock=- map=- open=-" in line
    assert "blocked=1.250s" in line
    # The flush it was waiting on, and a later one, still run.
    rig.flush_release.set()
    await rig.flush
    assert await rig.later_flush_admitted()
    rig.successor_release.set()
    await rig.owner.task


@pytest.mark.asyncio
async def test_cancel_during_stamp_join_adopts_debt_releases_and_logs_once(caplog):
    caplog.set_level(logging.INFO, logger=LOGGER)
    rig = Rig()
    await rig.start()
    rig.stamp_release.set()  # the settled call has returned
    timing = rig.timing()
    handover = rig.handover(timing)
    await until(lambda: rig.boundary.changing)
    rig.successor()  # the flush in flight starts the next call
    rig.clock.now += 0.25
    rig.flush_release.set()
    await until(lambda: timing.phase == "stamps")
    rig.clock.now += 4.0
    handover.cancel()
    with pytest.raises(asyncio.CancelledError):
        await handover

    assert not rig.boundary.changing and rig.boundary.stamps.task is None
    assert rig.adopted == [{7}]  # the cancelled stamp's cohort stays owed
    (line,) = handover_lines(caplog)
    assert "outcome=cancelled@stamps" in line
    assert "drain=0.250s stamps=4.000s lock=- map=- open=-" in line
    assert "blocked=4.250s" in line
    assert await rig.later_flush_admitted()


@pytest.mark.asyncio
async def test_cancel_during_the_stamp_settle_adopts_debt_releases_and_logs_once(caplog):
    """#10090 settle: cancelled while the running stamp settles (games still
    flowing), the call is cancelled and joined as in the stamps phase — door
    closed first, its cohort kept owed — and the line names `fence`."""
    caplog.set_level(logging.INFO, logger=LOGGER)
    rig = Rig()
    await rig.start()
    timing = rig.timing()
    handover = rig.handover(timing)
    await until(lambda: timing.phase == "fence")
    await asyncio.sleep(0.01)
    rig.clock.now += 1.5
    handover.cancel()
    with pytest.raises(asyncio.CancelledError):
        await handover

    assert not rig.boundary.changing and not rig.boundary.standalone_fenced
    assert rig.boundary.stamps.task is None and rig.stopped == 1
    assert rig.adopted == [{7}]  # the cancelled stamp's cohort stays owed
    (line,) = handover_lines(caplog)
    assert "outcome=cancelled@fence" in line
    assert "fence=1.500s drain=- stamps=-" in line
    assert "blocked=0.000s" in line
    assert await rig.later_flush_admitted(standalone=True)
    rig.flush_release.set()
    await rig.flush


@pytest.mark.asyncio
async def test_failure_in_the_map_body_is_named_and_releases(caplog):
    caplog.set_level(logging.INFO, logger=LOGGER)
    rig = Rig()
    await rig.start()
    rig.flush_release.set()
    rig.stamp_release.set()
    timing = rig.timing()
    with pytest.raises(RuntimeError, match="map body broke"):
        await rig.handover(timing, fail_in="map")

    assert not rig.boundary.changing and not rig.buffer_lock.locked()
    (line,) = handover_lines(caplog)
    assert "outcome=failed:RuntimeError@map" in line
    assert "map=0.050s open=-" in line
    assert await rig.later_flush_admitted()


@pytest.mark.asyncio
async def test_a_standalone_write_is_fenced_time_and_game_flushes_keep_running(caplog):
    """#10090 candidate: the held flush is a STANDALONE write. Its remaining
    time is `fence` — reported beside `blocked`, not inside it — and a game
    flush enters and leaves during it while a later standalone flush waits."""
    caplog.set_level(logging.INFO, logger=LOGGER)
    rig = Rig()
    await rig.start(standalone=True)
    rig.stamp_release.set()
    timing = rig.timing()
    handover = rig.handover(timing)
    await until(lambda: timing.phase == "fence")
    assert rig.boundary.standalone_fenced and not rig.boundary.changing
    assert await rig.later_flush_admitted()  # a game flush runs beside it
    held = asyncio.create_task(rig.later_flush_admitted(standalone=True))
    await asyncio.sleep(0.01)
    assert not held.done(), "a new standalone write entered the fence"
    rig.clock.now += 2.0  # the standalone write's remaining UPDATE
    rig.flush_release.set()
    await asyncio.wait_for(handover, 5)
    assert await held  # re-admitted once the maps changed

    assert timing.durations["fence"] == pytest.approx(2.0)
    assert timing.durations["drain"] == pytest.approx(0.0)
    assert timing.blocked_s == pytest.approx(0.06)
    (line,) = handover_lines(caplog)
    assert "outcome=ok " in line and "fence=2.000s drain=0.000s " in line
    assert "blocked=0.060s flushes_at_start=1" in line
    assert not rig.boundary.standalone_fenced and not rig.boundary.changing


@pytest.mark.asyncio
async def test_cancel_during_fence_releases_both_kinds_and_logs_once(caplog):
    caplog.set_level(logging.INFO, logger=LOGGER)
    rig = Rig()
    await rig.start(standalone=True)
    timing = rig.timing()
    handover = rig.handover(timing)
    await until(lambda: timing.phase == "fence")
    rig.clock.now += 0.75
    handover.cancel()
    with pytest.raises(asyncio.CancelledError):
        await handover

    assert not rig.boundary.standalone_fenced and not rig.boundary.changing
    (line,) = handover_lines(caplog)
    assert "outcome=cancelled@fence" in line
    assert "fence=0.750s drain=- stamps=-" in line
    assert "blocked=0.000s" in line
    assert await rig.later_flush_admitted(standalone=True)
    rig.flush_release.set()
    await rig.flush
    rig.stamp_release.set()
    await rig.owner.task


@pytest.mark.asyncio
async def test_an_untimed_boundary_stays_silent(caplog):
    caplog.set_level(logging.INFO, logger=LOGGER)
    boundary = task._PMCatalogFlushBoundary()
    async with boundary.updating():
        pass
    assert handover_lines(caplog) == []
    assert not boundary.changing


@pytest.mark.asyncio
async def test_real_consumer_writes_one_line_per_catalog_handover(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=LOGGER)
    rig, stop, sockets = CatalogRig(), asyncio.Event(), []
    # #10090 attempt156: the rig answers every slate read with this slate, the
    # stored-live read included, so its event must be stored live.
    rig.slate = POLY_SLATE_LIVE

    class Socket:
        def __init__(self):
            self.queue = asyncio.Queue()
            sockets.append(self)

        async def send(self, payload):
            if payload != "PING":
                json.loads(payload)

        def __aiter__(self):
            return self

        async def __anext__(self):
            return await self.queue.get()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return None

    class Refresher(blend.LiveBlendRefresher):
        async def refresh(self, *args, **kwargs):
            return None

        async def refresh_pending(self, **kwargs):
            return None

    _install(monkeypatch, rig)
    monkeypatch.setattr(websockets, "connect", lambda *args, **kwargs: Socket())
    monkeypatch.setattr(blend, "LiveBlendRefresher", Refresher)
    monkeypatch.setattr(task, "SUBSCRIPTION_REFRESH_SECONDS", 0.02)
    monkeypatch.setattr(task, "PRICE_FLUSH_SECONDS", 10)
    monkeypatch.delenv("PM_WS_PRICE_FLUSH_SECONDS", raising=False)
    monkeypatch.setenv("POLYMARKET_WS_OPEN_CONTRACT_PRICES", "1")
    monkeypatch.setenv("WS_OPEN_CONTRACT_PRICES", "1")

    async def stop_after_refreshes():
        # #10090 attempt156: one more slate read than before, the stored-live
        # subset ahead of the startup full read, so the same three timer reads.
        await until(lambda: rig.catalog_reads >= 5)
        stop.set()

    stopper = asyncio.create_task(stop_after_refreshes())
    stats = await asyncio.wait_for(task._run_polymarket_ws_consumer(stop=stop), 5)
    await stopper

    lines = handover_lines(caplog)
    initial = [line for line in lines if "reason=initial " in line]
    timer = [line for line in lines if "reason=timer " in line]
    # #10090 attempt156: exactly one startup-games handover, the full slate
    # installed after the stored-live subset and before any open read.
    startup = [line for line in lines if "reason=startup-games " in line]
    assert len(initial) == 1 and "slate_read=- " in initial[0]
    assert len(startup) == 1 and "open_read=- " in startup[0]
    assert "slate_read=- " not in startup[0]
    assert stats["catalog_refreshes"] >= 2
    assert len(timer) == stats["catalog_refreshes"] == len(lines) - 2
    for line in lines:
        assert "outcome=ok " in line
        fields = dict(part.split("=", 1) for part in line[len(PREFIX) :].split())
        assert set(fields) == {
            "reason",
            "outcome",
            "slate_read",
            "open_read",
            "fence",
            "drain",
            "stamps",
            "lock",
            "map",
            "open",
            "blocked",
            "flushes_at_start",
        }
        for name in ("fence", "drain", "stamps", "lock", "map", "open", "blocked"):
            assert fields[name].endswith("s") and float(fields[name][:-1]) >= 0
    for line in timer:
        fields = dict(part.split("=", 1) for part in line[len(PREFIX) :].split())
        assert fields["slate_read"] != "-" and fields["open_read"] != "-"
