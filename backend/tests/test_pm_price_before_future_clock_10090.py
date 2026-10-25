"""A completed price starts display work before optional future-input sampling."""

import asyncio

import pytest

from app.tasks.live_blend_refresh import HeldRowQuotes
from tests.test_pm_pipelined_stamps_10090 import held_refresher
from tests.test_polymarket_withdrawal_speed_10651 import rig

pytestmark = pytest.mark.asyncio


def pending_clock(r):
    held = HeldRowQuotes()
    entered, release = asyncio.Event(), asyncio.Event()
    calls = []

    async def sample(sessions):
        calls.append(len(calls) + 1)
        entered.set()
        await release.wait()
        return True

    held.sample_database_clock = sample
    r.ns["blend_refresher"].held_quotes = held
    return entered, release, calls


async def test_completed_price_starts_display_before_future_clock_returns():
    r = rig(books={}, batch={1: 0.6, 2: 0.4}, mapping={1: 10, 2: 10})
    r.release.set()
    stamp_gate, stamps = held_refresher(r, hold_ids=())
    entered, release, samples = pending_clock(r)
    task = asyncio.create_task(r.ns["flush_prices"](flush_started=100))
    try:
        await asyncio.wait_for(entered.wait(), 2)
        assert ("write", [1, 2]) in r.trace
        assert stamps["started"] == [(10,)]
        assert samples == [1]
        assert not task.done()
    finally:
        release.set()
        stamp_gate.set()
        await asyncio.wait_for(task, 2)
        await r.ns["catalog_boundary"].join_stamps()
    assert r.marks == [1, 2]


async def test_clock_still_finishes_before_next_chunk_writes():
    r = rig(books={})
    r.release.set()
    stamp_gate, stamps = held_refresher(r, hold_ids=())
    entered, release, samples = pending_clock(r)
    task = asyncio.create_task(r.ns["flush_prices"](flush_started=100))
    try:
        await asyncio.wait_for(entered.wait(), 2)
        assert stamps["started"] == [(10,)]
        assert ("write", [900]) not in r.trace
    finally:
        release.set()
        stamp_gate.set()
        await asyncio.wait_for(task, 2)
        await r.ns["catalog_boundary"].join_stamps()
    assert samples == [1, 2]
    assert stamps["started"] == [(10,), (90,)]


async def test_failed_write_keeps_clock_before_any_display_work():
    r = rig(books={}, batch={1: 0.6, 2: 0.4}, mapping={1: 10, 2: 10}, failed_price=1)
    r.release.set()
    stamp_gate, stamps = held_refresher(r, hold_ids=())
    entered, release, samples = pending_clock(r)
    task = asyncio.create_task(r.ns["flush_prices"](flush_started=100))
    try:
        await asyncio.wait_for(entered.wait(), 2)
        assert stamps["started"] == []
        assert samples == [1]
        assert r.ns["price_buffer"] == {1: 0.6, 2: 0.4}
    finally:
        release.set()
        stamp_gate.set()
        await asyncio.wait_for(task, 2)
        await r.ns["catalog_boundary"].join_stamps()
    assert stamps["started"] == []


async def test_cancel_during_future_sample_joins_started_display_work():
    r = rig(books={}, batch={1: 0.6, 2: 0.4}, mapping={1: 10, 2: 10})
    r.release.set()
    stamp_gate, stamps = held_refresher(r)
    entered, release, samples = pending_clock(r)
    task = asyncio.create_task(r.ns["flush_prices"](flush_started=100))
    try:
        await asyncio.wait_for(entered.wait(), 2)
        assert stamps["started"] == [(10,)] and stamps["running"] == 1
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 2)
        assert stamps["running"] == 0
        assert stamps["cancelled"] == [(10,)]
        assert samples == [1]
    finally:
        release.set()
        stamp_gate.set()
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await r.ns["catalog_boundary"].join_stamps()
