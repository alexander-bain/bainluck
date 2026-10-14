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

    async def start(self):
        async def flush():
            async with self.boundary.flushing():
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

    async def later_flush_admitted(self):
        async def later():
            async with self.boundary.flushing():
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
    await until(lambda: rig.boundary.changing)
    assert timing.phase == "drain" and timing.flushes == 1

    rig.clock.now += 2.0  # the active flush's remaining write
    rig.flush_release.set()
    await until(lambda: timing.phase == "stamps")
    assert rig.stopped == 1  # the join closed the door before waiting
    rig.clock.now += 3.0  # the running stamp
    rig.stamp_release.set()
    await until(lambda: timing.phase == "lock")
    assert rig.boundary.changing  # flushes are still held behind the lock
    rig.clock.now += 0.5  # buffer-lock holder
    rig.buffer_lock.release()
    await asyncio.wait_for(handover, 5)
    await rig.flush

    assert timing.durations == pytest.approx(
        {"drain": 2.0, "stamps": 3.0, "lock": 0.5, "map": 0.05, "open": 0.01}
    )
    assert timing.blocked_s == pytest.approx(5.56)
    assert sum(timing.durations.values()) == pytest.approx(timing.blocked_s)
    assert handover_lines(caplog) == [
        PREFIX + "reason=timer outcome=ok slate_read=0.400s open_read=1.200s "
        "drain=2.000s stamps=3.000s lock=0.500s map=0.050s open=0.010s "
        "blocked=5.560s flushes_at_start=1"
    ]
    assert not rig.boundary.changing and rig.boundary.stamps.task is None
    assert rig.adopted == []  # a completed stamp keeps its committed cohort
    assert await rig.later_flush_admitted()


@pytest.mark.asyncio
async def test_cancel_during_drain_releases_and_logs_once(caplog):
    caplog.set_level(logging.INFO, logger=LOGGER)
    rig = Rig()
    await rig.start()
    timing = rig.timing()
    handover = rig.handover(timing)
    await until(lambda: rig.boundary.changing)
    rig.clock.now += 1.25
    handover.cancel()
    with pytest.raises(asyncio.CancelledError):
        await handover

    assert not rig.boundary.changing
    assert rig.boundary.stamps.task is not None  # drain never reached the join
    assert rig.stopped == 0
    (line,) = handover_lines(caplog)
    assert "outcome=cancelled@drain" in line
    assert "drain=1.250s stamps=- lock=- map=- open=-" in line
    assert "blocked=1.250s" in line
    # The flush it was waiting on, and a later one, still run.
    rig.flush_release.set()
    await rig.flush
    assert await rig.later_flush_admitted()
    rig.stamp_release.set()
    await rig.owner.task


@pytest.mark.asyncio
async def test_cancel_during_stamp_join_adopts_debt_releases_and_logs_once(caplog):
    caplog.set_level(logging.INFO, logger=LOGGER)
    rig = Rig()
    await rig.start()
    timing = rig.timing()
    handover = rig.handover(timing)
    await until(lambda: rig.boundary.changing)
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
        await until(lambda: rig.catalog_reads >= 4)
        stop.set()

    stopper = asyncio.create_task(stop_after_refreshes())
    stats = await asyncio.wait_for(task._run_polymarket_ws_consumer(stop=stop), 5)
    await stopper

    lines = handover_lines(caplog)
    initial = [line for line in lines if "reason=initial " in line]
    timer = [line for line in lines if "reason=timer " in line]
    assert len(initial) == 1 and "slate_read=- " in initial[0]
    assert stats["catalog_refreshes"] >= 2
    assert len(timer) == stats["catalog_refreshes"] == len(lines) - 1
    for line in lines:
        assert "outcome=ok " in line
        fields = dict(part.split("=", 1) for part in line[len(PREFIX) :].split())
        assert set(fields) == {
            "reason",
            "outcome",
            "slate_read",
            "open_read",
            "drain",
            "stamps",
            "lock",
            "map",
            "open",
            "blocked",
            "flushes_at_start",
        }
        for name in ("drain", "stamps", "lock", "map", "open", "blocked"):
            assert fields[name].endswith("s") and float(fields[name][:-1]) >= 0
    for line in timer:
        fields = dict(part.split("=", 1) for part in line[len(PREFIX) :].split())
        assert fields["slate_read"] != "-" and fields["open_read"] != "-"
