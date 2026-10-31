"""#10090 — a PM catalog handover holds every game flush only for the stamps
already running, not for the queue behind them.

Ship: a live game's Polymarket price stops freezing for 5-7 s each time the
Polymarket catalog refreshes. Production 2026-10-31 00:46-01:36Z: the
handover's `stamps` phase (every game flush held by `changing`) was
1.37-3.96 s of `blocked` 1.49-4.15 s, because it closed the stamp call's door
and then drained everything still QUEUED in it. With `PM_HANDOVER_SHED_QUEUED`
on (the default) queued, unstarted attempts go back to debt at once, the way a
cancelled close leaves an admitted attempt whose worker never ran; `=0` is
today's join of the whole queue. Source/progress controls, not timing.
"""
import asyncio
import logging

import pytest

from app.tasks import polymarket_ws as task
from tests.test_kalshi_fresh_admission_10090 import _held_reads
from tests.test_pm_catalog_handover_phases_10090 import Rig
from tests.test_pm_open_cycle_lifetime_10090 import until
from tests.test_single_event_commit_10090 import rig as refresher_rig, settle_until

pytestmark = pytest.mark.asyncio


async def _call_with_queue(monkeypatch):
    """Call on game 1 held in its UPDATE; 2, 3, 4 admitted and held in their
    reads on the three stamp workers; 5 and 6 admitted with no free worker."""
    x = refresher_rig(monkeypatch, count=6, block=True, blocked=(1,))
    holds = _held_reads(x, 2, 3, 4)
    running = asyncio.create_task(x.r.refresh([1], flush_started=1000))
    await settle_until(lambda: "update" in x.commands)
    for event_id, at in ((2, 1002), (3, 1004), (4, 1006), (5, 1008), (6, 1010)):
        assert x.r.admit_fresh([event_id], flush_started=at) == {event_id}
    window = x.r._admission
    await settle_until(lambda: list(window.queue) == [5, 6])
    return x, holds, running, window


def _release(x, holds):
    x.release.set()
    for hold in holds.values():
        hold.set()


async def test_shed_hands_queued_attempts_back_to_debt_and_running_ones_finish(
    monkeypatch,
):
    x, holds, running, window = await _call_with_queue(monkeypatch)
    try:
        assert x.r.shed_queued() == {5, 6}
        assert window.closed and not window.queue and not window.live_queue
        assert x.r.holding_event_ids() == frozenset({1, 2, 3, 4})
        assert x.r.pending_event_ids() == frozenset({5, 6})
        assert not x.r._failed_hold_until  # owed now, never held 5 s
        assert x.r.admit_fresh([5], flush_started=1012) == frozenset()
        assert not running.done()  # the running attempts are not cancelled
    finally:
        _release(x, holds)
    await asyncio.wait_for(running, 2)
    assert sorted(x.published) == [1, 2, 3, 4]
    assert x.r.pending_event_ids() == frozenset({5, 6})
    assert x.r._admission is None and x.r.stats["errors"] == 0
    # The next call stamps the shed events on the board as it is then.
    await asyncio.wait_for(x.r.refresh_pending(flush_started=1020), 2)
    assert sorted(x.published) == [1, 2, 3, 4, 5, 6]
    assert x.r.pending_event_ids() == frozenset()


async def test_shed_with_no_call_or_an_empty_queue_changes_nothing(monkeypatch):
    x = refresher_rig(monkeypatch, count=2, block=True, blocked=(1,))
    assert x.r.shed_queued() == frozenset()
    running = asyncio.create_task(x.r.refresh([1], flush_started=1000))
    try:
        await settle_until(lambda: "update" in x.commands)
        assert x.r.shed_queued() == frozenset()
        assert not x.r.admitting()  # the door still closes
    finally:
        x.release.set()
    await asyncio.wait_for(running, 2)
    assert x.published == [1] and x.r.pending_event_ids() == frozenset()


async def _handover_over_queued_call(monkeypatch, caplog):
    """The real boundary's `stamps` phase over the real refresher's call. The
    settle is stubbed: it is unchanged here and the queue under test is the
    one admitted after its frontier."""
    x, holds, running, _window = await _call_with_queue(monkeypatch)
    boundary = task._PMCatalogFlushBoundary()
    owner = boundary.stamp_owner(x.r)
    owner.task, owner.events = running, {1}

    async def settled():
        return None

    boundary._settle_stamp = settled
    timing = task._PMCatalogHandoverTiming(None)
    entered = asyncio.Event()

    async def handover():
        async with boundary.updating(timing):
            entered.set()

    caplog.set_level(logging.INFO, logger="app.tasks.polymarket_ws")
    run = asyncio.create_task(handover())
    await until(lambda: timing.phase == "stamps")
    await asyncio.sleep(0)
    return x, holds, run, entered


async def test_handover_stamps_phase_waits_only_for_running_attempts(
    monkeypatch, caplog,
):
    monkeypatch.delenv("PM_HANDOVER_SHED_QUEUED", raising=False)
    x, holds, run, entered = await _handover_over_queued_call(monkeypatch, caplog)
    try:
        assert x.r.pending_event_ids() == frozenset({5, 6})
        assert not entered.is_set()  # 1-4 are still running
    finally:
        _release(x, holds)
    await asyncio.wait_for(run, 2)
    assert entered.is_set() and sorted(x.published) == [1, 2, 3, 4]
    assert x.r.pending_event_ids() == frozenset({5, 6})
    assert any(
        r.getMessage().startswith("Polymarket WS handover shed: 2 queued")
        for r in caplog.records
    )


async def test_switch_off_restores_the_join_of_the_whole_queue(monkeypatch, caplog):
    monkeypatch.setenv("PM_HANDOVER_SHED_QUEUED", "0")
    x, holds, run, entered = await _handover_over_queued_call(monkeypatch, caplog)
    try:
        assert x.r.pending_event_ids() == frozenset()
        assert not entered.is_set()
    finally:
        _release(x, holds)
    await asyncio.wait_for(run, 2)
    assert entered.is_set() and sorted(x.published) == [1, 2, 3, 4, 5, 6]
    assert not any(
        r.getMessage().startswith("Polymarket WS handover shed:")
        for r in caplog.records
    )


@pytest.mark.parametrize(
    "raw, on",
    [(None, True), ("", True), ("1", True), ("on", True),
     ("0", False), ("false", False), (" OFF ", False), ("no", False)],
)
async def test_switch_reading(monkeypatch, raw, on):
    if raw is None:
        monkeypatch.delenv("PM_HANDOVER_SHED_QUEUED", raising=False)
    else:
        monkeypatch.setenv("PM_HANDOVER_SHED_QUEUED", raw)
    assert task._handover_shed_queued_enabled() is on


async def test_shed_runs_in_the_stamps_phase_before_the_join_closes_the_door(
    monkeypatch,
):
    # The fenced boundary's order is unchanged: settle, drain, then (stamps)
    # shed, the join's own door close, the wait. A refresher without the
    # method (older rigs, Kalshi) is joined exactly as before.
    monkeypatch.delenv("PM_HANDOVER_SHED_QUEUED", raising=False)
    rig = Rig()
    order = []
    rig.owner.refresher.shed_queued = lambda: order.append("shed") or frozenset()
    rig.stop_admitting = lambda: order.append("stop")
    rig.owner.refresher.stop_admitting = rig.stop_admitting
    await rig.start()
    timing = rig.timing()
    handover = rig.handover(timing)
    await until(lambda: timing.phase == "fence")
    rig.stamp_release.set()
    await until(lambda: rig.boundary.changing)
    assert order == []  # no shed while games still flow
    rig.successor()
    rig.flush_release.set()
    await until(lambda: timing.phase == "stamps")
    assert order == ["shed", "stop"]
    rig.successor_release.set()
    await asyncio.wait_for(handover, 5)
    await rig.flush
    assert not rig.boundary.changing
