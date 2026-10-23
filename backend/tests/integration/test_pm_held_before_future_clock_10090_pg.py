"""A held price's correct observation publishes before future clock work."""

import asyncio
import time

import pytest

from tests.integration.test_pm_held_price_row_stamps_received_quote_11138_pg import (
    DB_URL, build, consumer, hold_price_row, rig, stored, wait_for, wire_held_quotes,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.skipif(
    not DB_URL, reason='requires disposable SEARCH_TEST_DATABASE_URL',
)]


async def test_held_price_publishes_while_future_clock_is_unanswered(rig, consumer, monkeypatch):
    t = await build(rig, consumer, monkeypatch, trace=True, lock_ms=500)
    held = await wire_held_quotes(t, consumer)
    initial_bound = held._database_bound
    holder, tx = await hold_price_row(rig, 1)
    entered, release = asyncio.Event(), asyncio.Event()

    async def pending_clock(_sessions):
        entered.set()
        await release.wait()
        return False

    held.sample_database_clock = pending_clock
    started = time.monotonic()
    accepted = t.accept(1, .82)
    task = asyncio.create_task(t.tracked_flush(started))
    try:
        await asyncio.wait_for(entered.wait(), 3)
        await wait_for(lambda: any(value == .82 for _, _, value, _ in t.pubs), timeout=2)
        publication = next(at for at, _, value, _ in t.pubs if value == .82)
        assert publication - started < 1
        assert not task.done()
        assert not release.is_set()
        assert held.bound_for(accepted) == initial_bound
        assert await stored(rig) == (.7, .82)
        print('HELD_BEFORE_CLOCK', {'input_to_publication_s': publication - started})
    finally:
        release.set()
        await asyncio.wait_for(task, 5)
        await tx.rollback()
        await holder.close()
        await t.boundary.join_stamps()
        await t.r.drain_history()
        held.close()
