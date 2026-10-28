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


async def test_withdrawal_during_the_ambiguity_read_drops_the_event_and_still_samples():
    r, held, accepted, gate, calls, entered, release, samples = held_clock_rig()

    async def stored(_sessions, quotes):
        # A wide book lands while the held read is outside the buffer lock.
        r.ns['withdraw_buffer'][1] = (.1, .9)
        return set()

    held.stored_at_or_after = stored
    task = asyncio.create_task(r.ns['flush_prices'](flush_started=100))
    try:
        await asyncio.wait_for(entered.wait(), 2)
        assert calls['started'] == [] and 1 not in held
    finally:
        release.set()
        gate.set()
        await asyncio.wait_for(task, 2)
        await r.ns['catalog_boundary'].join_stamps()
    assert samples == [100.0] and held.bound_for(accepted) == 100.0
    assert r.ns['price_buffer'] == {1: .82}


async def test_failed_write_samples_without_any_held_delivery():
    r, held, accepted, gate, calls, entered, release, samples = held_clock_rig()
    reads = []

    async def failed(_chunk, **_kwargs):
        return False

    async def stored(_sessions, quotes):
        reads.append(quotes)
        return set()

    r.ns['write_chunk'] = failed
    held.stored_at_or_after = stored
    task = asyncio.create_task(r.ns['flush_prices'](flush_started=100))
    try:
        await asyncio.wait_for(entered.wait(), 2)
        assert calls['started'] == [] and 1 not in held and not reads
    finally:
        release.set()
        gate.set()
        await asyncio.wait_for(task, 2)
        await r.ns['catalog_boundary'].join_stamps()
    assert samples == [100.0] and not reads
    assert r.ns['price_buffer'] == {1: .82}


async def test_final_drain_neither_samples_nor_holds():
    r, held, accepted, gate, calls, entered, release, samples = held_clock_rig()
    release.set()
    gate.set()
    await asyncio.wait_for(r.ns['flush_prices'](final=True), 2)
    await r.ns['catalog_boundary'].join_stamps()
    assert samples == [] and 1 not in held and calls['started'] == []
    assert held.bound_for(accepted) == 100.0


async def test_a_failed_later_chunk_samples_before_its_events_stamp_starts():
    # Event 10 spans two chunks: [1, 2] lands, [3] fails. Its stamp becomes
    # ready in the failed chunk; a failed write keeps the sample first.
    r = rig(batch={1: .6, 2: .4, 3: .7}, mapping={1: 10, 2: 10, 3: 10}, books={})
    gate, calls = held_refresher(r)
    held = HeldRowQuotes()
    held._database_bound = 100.0
    marks = {oid: mark(oid=oid, value=value) for oid, value in ((1, .6), (2, .4), (3, .7))}
    for accepted in marks.values():
        held.note_input(accepted)
    r.ns['input_marks'] = marks
    r.ns['blend_refresher'].held_quotes = held
    entered, release = asyncio.Event(), asyncio.Event()
    started_at_sample = []

    async def sample(_sessions):
        started_at_sample.append(list(calls['started']))
        if len(started_at_sample) == 2:  # the failed chunk's sample
            entered.set()
            await release.wait()
        return True

    async def write(chunk, **_kwargs):
        if 3 in chunk:
            return False
        for oid in chunk:
            r.ns['price_buffer'].pop(oid, None)
        return True

    held.sample_database_clock = sample
    r.ns['write_chunk'] = write
    task = asyncio.create_task(r.ns['flush_prices'](flush_started=100))
    try:
        await asyncio.wait_for(entered.wait(), 2)
        assert started_at_sample == [[], []]
    finally:
        release.set()
        gate.set()
        await asyncio.wait_for(task, 2)
        await r.ns['catalog_boundary'].join_stamps()
    assert calls['started'] == [(10,)]
    assert r.ns['price_buffer'] == {3: .7}
