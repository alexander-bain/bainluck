"""Successful price transactions supply future bounds without another pool read."""
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.tasks.live_blend_refresh import HeldRowQuotes
from app.utils.kalshi_price_pipeline import PriceRunResult
from tests.test_held_quotes_idle_bound_10090 import Clock, FakeDB, _held, _mark
from tests.test_kalshi_game_isolation_10655 import rig
from tests.test_kalshi_pipelined_stamps_10090 import held_refresher


def stamp(value):
    return datetime.fromtimestamp(value, timezone.utc)


async def test_returned_clock_does_not_redate_inputs_or_clear_probe_failure():
    clock = Clock()
    held = _held(clock, events=())
    assert await held.sample_database_clock(FakeDB(clock))
    ticket = held.begin_write_clock()
    during = _mark()
    held.note_input(during)
    held._sample_failure_episode = True
    held._sample_failure_ordinal = ticket[0] - 1
    held._sample_backoff_until = 5.0
    assert held.publish_write_clock(ticket, stamp(1001))
    after = _mark(oid=102)
    held.note_input(after)
    assert held.bound_for(during) == 1000
    assert held.bound_for(after) == 1001
    assert held._sample_failure_episode and held._sample_backoff_until == 5.0
    assert held._graph_sample_ordinal == 0


async def test_older_write_ticket_cannot_replace_newer_read():
    clock = Clock()
    held = _held(clock, events=())
    ticket = held.begin_write_clock()
    clock.t = 2
    assert await held.sample_database_clock(FakeDB(clock))
    assert held.publish_write_clock(ticket, stamp(1001))
    assert held._database_bound == 1002
    assert not held.publish_write_clock(ticket, stamp(1003))
    assert held._database_bound == 1002
    held.close()
    assert not held.publish_write_clock(ticket, stamp(1004))


@pytest.mark.parametrize('failure', [None, 'rollback', 'cancel'])
async def test_consumer_adopts_returned_clock_only_after_session_exit(failure):
    r = rig()
    r.batch.pop(3)
    r.batch.pop(9)
    r.release.set()
    stamp_gate, calls = held_refresher(r, hold_ids=())
    held = HeldRowQuotes()
    held._database_bound = 1000.0
    r.ns['blend_refresher'].held_quotes = held
    samples = []

    async def unexpected_sample(_sessions):
        samples.append(True)
        return True

    held.sample_database_clock = unexpected_sample
    real_phase = r.ns['prices'].phase

    async def phase(session, values, **kwargs):
        async for result in real_phase(session, values, **kwargs):
            rows = tuple(SimpleNamespace(**vars(row), database_clock=stamp(1001))
                         for row in result.rows)
            yield PriceRunResult(result.attempted, rows)

    r.ns['prices'].phase = phase
    real_session = r.ns['get_task_session']
    exiting, release = asyncio.Event(), asyncio.Event()

    @asynccontextmanager
    async def session():
        async with real_session() as s:
            yield s
            exiting.set()
            await release.wait()
            if failure == 'rollback':
                raise RuntimeError('commit refused')
            if failure == 'cancel':
                raise asyncio.CancelledError()

    r.ns['get_task_session'] = session
    task = asyncio.create_task(r.flush())
    try:
        await asyncio.wait_for(exiting.wait(), 2)
        assert held._database_bound == 1000
        before_commit = _mark()
        held.note_input(before_commit)
        release.set()
        if failure == 'cancel':
            with pytest.raises(asyncio.CancelledError):
                await task
        else:
            assert await asyncio.wait_for(task, 2) is (failure is None)
        assert held._database_bound == (1001 if failure is None else 1000)
        assert held.bound_for(before_commit) == 1000
        assert samples == []
    finally:
        release.set()
        stamp_gate.set()
        await asyncio.gather(task, return_exceptions=True)
        await r.ns['prices'].join_stamp(r.ns['blend_refresher'])
        stopped = held.close()
        if stopped:
            await asyncio.gather(stopped, return_exceptions=True)
