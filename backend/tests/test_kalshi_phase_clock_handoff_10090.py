"""Independent prices precede one bounded clock sample; flush completion does not."""
import asyncio

import pytest

from tests.test_held_quotes_idle_bound_10090 import Clock, FakeDB, _held, _mark, _settle
from tests.test_kalshi_game_isolation_10655 import rig
from tests.test_kalshi_pipelined_stamps_10090 import held_refresher


@pytest.mark.parametrize('failed', [None, 3])
async def test_flush_samples_after_independent_prices_even_on_partial_failure(failed):
    clock = Clock()
    db = FakeDB(clock)
    held = _held(clock, events=())
    assert await held.sample_database_clock(db)
    clock.t = 0.1
    before = _mark()
    held.note_input(before)
    gate = asyncio.Event()
    db.gates.append(gate)
    real_sample = held.sample_database_clock

    async def sample(_sessions):
        return await real_sample(db)

    held.sample_database_clock = sample
    r = rig(failed=failed)
    r.release.set()
    stamp_gate, calls = held_refresher(r, hold_ids=())
    r.ns['blend_refresher'].held_quotes = held
    task = asyncio.create_task(r.flush())
    try:
        for _ in range(100):
            await asyncio.sleep(0)
            if db.active:
                break
        assert db.active == 1
        assert ('write', 3) in r.trace, 'independent price must run before optional clock IO'
        assert r.committed == ([1, 2] if failed else [1, 2, 3, 9])
        assert calls['started']
        assert not task.done(), 'completed flush must pay its post-write sample'
        during = _mark(oid=102)
        held.note_input(during)
        assert held.bound_for(before) == held.bound_for(during) == 1000.0
        gate.set()
        assert await asyncio.wait_for(task, 2) is (failed is None)
        after = _mark(oid=103)
        held.note_input(after)
        assert held.bound_for(after) == 1000.1
        assert held.bound_for(before) == held.bound_for(during) == 1000.0
        assert db.calls == 2, 'one startup sample plus one coalesced post-write sample'
        assert db.max_active == 1
    finally:
        gate.set()
        stamp_gate.set()
        await asyncio.gather(task, return_exceptions=True)
        await r.ns['prices'].join_stamp(r.ns['blend_refresher'])
        stopped = held.close()
        if stopped:
            await asyncio.gather(stopped, return_exceptions=True)
