"""A held PM quote reaches delivery before a future-input clock probe returns."""

import asyncio

import pytest

from app.tasks.live_blend_refresh import HeldRowQuotes
from tests.test_pm_held_row_quotes_11138 import mark
from tests.test_pm_pipelined_stamps_10090 import held_refresher
from tests.test_polymarket_withdrawal_speed_10651 import rig

pytestmark = pytest.mark.asyncio


def held_clock_rig(*, bound=100.0, ambiguous=False):
    r = rig(batch={1: .82}, mapping={1: 10}, books={})
    gate, calls = held_refresher(r)
    held = HeldRowQuotes()
    held._database_bound = bound
    accepted = mark(oid=1, value=.82)
    held.note_input(accepted)
    r.ns['input_marks'] = {1: accepted}
    r.ns['blend_refresher'].held_quotes = held
    entered, release = asyncio.Event(), asyncio.Event()
    samples = []

    async def sample(_sessions):
        samples.append(held.bound_for(accepted))
        entered.set()
        await release.wait()
        held._database_bound = 200.0
        return True

    async def stored(_sessions, quotes):
        assert quotes == {1: (.82, 100.0)}
        return {1} if ambiguous else set()

    async def deferred(_chunk, **_kwargs):
        return None

    held.sample_database_clock = sample
    held.stored_at_or_after = stored
    r.ns['write_chunk'] = deferred
    return r, held, accepted, gate, calls, entered, release, samples


async def test_eligible_held_quote_starts_before_future_clock_and_keeps_frozen_bound():
    r, held, accepted, gate, calls, entered, release, samples = held_clock_rig()
    task = asyncio.create_task(r.ns['flush_prices'](flush_started=100))
    try:
        await asyncio.wait_for(entered.wait(), 2)
        assert calls['started'] == [(10,)]
        assert held._quotes[1] == (.82, 100.0)
        assert samples == [100.0]
        assert not task.done()
    finally:
        release.set()
        gate.set()
        await asyncio.wait_for(task, 2)
        await r.ns['catalog_boundary'].join_stamps()
    assert held.bound_for(accepted) == 100.0
    assert held._database_bound == 200.0
    assert r.ns['price_buffer'] == {1: .82}


@pytest.mark.parametrize('bound,ambiguous', [(None, False), (100.0, True)])
async def test_unproven_quote_is_not_delivered_or_redated_by_later_sample(bound, ambiguous):
    r, held, accepted, gate, calls, entered, release, samples = held_clock_rig(
        bound=bound, ambiguous=ambiguous,
    )
    task = asyncio.create_task(r.ns['flush_prices'](flush_started=100))
    try:
        await asyncio.wait_for(entered.wait(), 2)
        assert calls['started'] == []
        assert 1 not in held
    finally:
        release.set()
        gate.set()
        await asyncio.wait_for(task, 2)
        await r.ns['catalog_boundary'].join_stamps()
    assert held.bound_for(accepted) == bound
    assert r.ns['price_buffer'] == {1: .82}


async def test_cancellation_during_clock_joins_started_stamp_and_retains_price():
    r, held, accepted, gate, calls, entered, release, samples = held_clock_rig()
    task = asyncio.create_task(r.ns['flush_prices'](flush_started=100))
    try:
        await asyncio.wait_for(entered.wait(), 2)
        assert calls['started'] == [(10,)]
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        release.set()
        gate.set()
    assert calls['cancelled'] == [(10,)]
    assert calls['running'] == 0
    assert r.ns['price_buffer'] == {1: .82}
    assert held.bound_for(accepted) == 100.0
