"""#10090 — a pre-game (bridged) price no longer queues behind side writes no blend reads.

PILLARS: TRUTH / FORMATTING. SHIP: a Polymarket price is saved within a second
or two of arriving, instead of 8-20 s later during bursts.

Production 2026-10-28 23:16Z: 24 pure bridged (pre-game) events' prices
received 23:16:24.6-35.2 were written in ONE bridged cohort that read the
buffer after 35.2 s, while live games' prices committed and stamped 0.3-2.2 s
after arrival. The bridged writer, the standalone legs' loop and the linked
props' loop take turns on one side connection (`side_writer`) in arrival order,
so a bridged cohort also waited for every side transaction queued ahead of it.

`PM_BRIDGED_SIDE_FIRST` (env, default off = today's `asyncio.Lock`) lets the
bridged writer take the side connection ahead of waiting side loops — behind
the transaction in flight, never pre-empting it. The writer's own side wait
and write time ride the open-contract minute line either way, so the switch's
effect is readable from production logs. Executed shipped classes; fake write
and publication boundaries — control flow, not production latency.
"""
import asyncio
import logging

import pytest

from app.tasks import polymarket_ws as pm

pytestmark = pytest.mark.asyncio


def _boundary(monkeypatch, on):
    monkeypatch.setattr(pm, "PM_BRIDGED_SIDE_FIRST", on, raising=False)
    return pm._PMCatalogFlushBoundary()


async def _hold(side_writer, name, order, entered, release):
    """A side loop's chunk: `async with catalog_boundary.side_writer:`."""
    async with side_writer:
        order.append(name)
        entered.set()
        await release.wait()


def _offer_bridged(boundary, order, buffer, *, write_seconds=0.0):
    async def write(chunk, *, start_market_publish=None):
        order.append("bridged")
        if write_seconds:
            await asyncio.sleep(write_seconds)
        if start_market_publish is not None:
            start_market_publish(object())
        return True

    async def publish(session):
        return 0

    boundary.bridges.offer(
        list(buffer), {7}, write=write, publish=publish,
        side_writer=boundary.side_writer, buffer_lock=asyncio.Lock(),
        price_buffer=buffer, input_marks={},
    )


async def _queued_behind_side_loops(monkeypatch, on):
    """Standalone chunk in flight, a prop chunk waiting, then a bridged cohort."""
    boundary = _boundary(monkeypatch, on)
    order = []
    standalone_in, standalone_go = asyncio.Event(), asyncio.Event()
    prop_in, prop_go = asyncio.Event(), asyncio.Event()
    standalone = asyncio.create_task(_hold(
        boundary.side_writer, "standalone", order, standalone_in, standalone_go,
    ))
    await asyncio.wait_for(standalone_in.wait(), 1)
    prop = asyncio.create_task(_hold(
        boundary.side_writer, "prop", order, prop_in, prop_go,
    ))
    await asyncio.sleep(0)
    _offer_bridged(boundary, order, {700: 0.4, 701: 0.6})
    await asyncio.sleep(0)
    standalone_go.set()
    prop_go.set()
    await asyncio.wait_for(asyncio.gather(standalone, prop), 1)
    await asyncio.wait_for(boundary.bridges.join(), 1)
    return order


async def test_on_bridged_cohort_goes_ahead_of_a_waiting_side_loop(monkeypatch):
    order = await _queued_behind_side_loops(monkeypatch, True)
    # Behind the standalone write in flight (never pre-empted), ahead of the
    # prop chunk that was already waiting.
    assert order == ["standalone", "bridged", "prop"]


async def test_off_is_todays_arrival_order(monkeypatch):
    order = await _queued_behind_side_loops(monkeypatch, False)
    assert order == ["standalone", "prop", "bridged"]


async def test_off_keeps_the_same_asyncio_lock(monkeypatch):
    assert type(_boundary(monkeypatch, False).side_writer) is asyncio.Lock
    assert type(_boundary(monkeypatch, True).side_writer) is pm._PMSideWriter


async def test_side_writer_waiters_keep_arrival_order_within_each_turn():
    writer = pm._PMSideWriter()
    order = []

    async def take(name, first):
        if first:
            async with writer.first():
                order.append(name)
                await asyncio.sleep(0)
        else:
            async with writer:
                order.append(name)
                await asyncio.sleep(0)

    await writer.acquire()
    tasks = []
    for name, first in (("a", False), ("F1", True), ("b", False), ("F2", True)):
        tasks.append(asyncio.create_task(take(name, first)))
        await asyncio.sleep(0)
    writer.release()
    await asyncio.wait_for(asyncio.gather(*tasks), 1)
    assert order == ["F1", "F2", "a", "b"]
    assert not writer.locked()


async def test_side_writer_cancelled_waiter_leaves_no_hold():
    writer = pm._PMSideWriter()
    await writer.acquire()
    waiting = asyncio.create_task(writer.acquire(first=True))
    await asyncio.sleep(0)
    waiting.cancel()
    await asyncio.gather(waiting, return_exceptions=True)
    writer.release()
    assert not writer.locked()


async def test_side_writer_cancelled_after_handover_passes_it_on():
    writer = pm._PMSideWriter()
    await writer.acquire()
    handed = asyncio.create_task(writer.acquire(first=True))
    behind = asyncio.create_task(writer.acquire())
    await asyncio.sleep(0)
    writer.release()  # handed to `handed`, which is cancelled before it runs
    handed.cancel()
    await asyncio.gather(handed, return_exceptions=True)
    assert await asyncio.wait_for(behind, 1) is True
    writer.release()
    assert not writer.locked()


async def test_minute_line_reads_the_bridged_side_wait_and_write(monkeypatch, caplog):
    boundary = _boundary(monkeypatch, False)
    order = []
    held_in, held_go = asyncio.Event(), asyncio.Event()
    holder = asyncio.create_task(_hold(
        boundary.side_writer, "standalone", order, held_in, held_go,
    ))
    await asyncio.wait_for(held_in.wait(), 1)
    _offer_bridged(boundary, order, {700: 0.4}, write_seconds=0.05)
    await asyncio.sleep(0.1)
    held_go.set()
    await asyncio.wait_for(asyncio.gather(holder, boundary.bridges.join()), 1)

    timing = boundary.bridges.take_timing()
    assert timing["bridged_cohorts"] == 1
    assert timing["bridged_side_wait_max_s"] >= 0.09
    assert timing["bridged_write_max_s"] >= 0.04
    assert timing["bridged_side_wait_s"] == timing["bridged_side_wait_max_s"]
    again = boundary.bridges.take_timing()
    assert again["bridged_side_wait_max_s"] == again["bridged_write_max_s"] == 0.0
    assert again["bridged_side_wait_s"] == timing["bridged_side_wait_s"]

    stats = {"open_contract_bridged_outcomes": 2, "open_contract_bridged_events": 1}
    stats.update(timing)
    with caplog.at_level(logging.INFO, logger=pm.logger.name):
        pm._log_open_contract_line(stats, {})
    line = caplog.records[-1].getMessage()
    assert "bridged=2/1 bridged_writes=1 side_wait=" in line
    side = line.split("side_wait=")[1].split("s ")[0]
    assert float(side.split("/")[1]) >= 0.09
    assert line.endswith("s")  # no bridge_error suffix


@pytest.mark.parametrize("raw,expected", [
    (None, False), ("", False), ("0", False), ("off", False),
    ("1", True), ("true", True), ("ON", True), ("yes", True),
])
async def test_env_reads_on_off(monkeypatch, raw, expected):
    if raw is None:
        monkeypatch.delenv("PM_BRIDGED_SIDE_FIRST", raising=False)
    else:
        monkeypatch.setenv("PM_BRIDGED_SIDE_FIRST", raw)
    assert pm._bridged_side_first_env() is expected


async def test_env_invalid_is_off_with_one_warning(monkeypatch, caplog):
    monkeypatch.setenv("PM_BRIDGED_SIDE_FIRST", "sometimes")
    with caplog.at_level(logging.WARNING, logger=pm.logger.name):
        assert pm._bridged_side_first_env() is False
    assert sum("PM_BRIDGED_SIDE_FIRST" in r.getMessage() for r in caplog.records) == 1
