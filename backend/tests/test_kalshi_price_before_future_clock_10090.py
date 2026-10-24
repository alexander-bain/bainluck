"""Completed Kalshi cohorts need not wait for a future-input clock probe."""

import asyncio

import pytest

from app.tasks.live_blend_refresh import HeldRowQuotes
from tests.test_kalshi_game_isolation_10655 import rig
from tests.test_kalshi_pipelined_stamps_10090 import held_refresher

pytestmark = pytest.mark.asyncio


def setup_clock(r):
    held = HeldRowQuotes()
    entered, release = asyncio.Event(), asyncio.Event()
    samples = []

    async def sample(sessions):
        samples.append(tuple(r.committed))
        entered.set()
        await release.wait()
        return True

    held.sample_database_clock = sample
    r.ns["blend_refresher"].held_quotes = held
    return entered, release, samples


async def test_committed_game_starts_display_while_future_clock_is_pending():
    r = rig()
    r.release.set()
    gate, calls = held_refresher(r)
    entered, release, samples = setup_clock(r)
    task = asyncio.create_task(r.flush())
    try:
        await asyncio.wait_for(entered.wait(), 2)
        assert r.committed == [1, 2]
        assert calls["started"] == [(100,)]
        assert samples == [(1, 2)]
        assert ("write", 3) not in r.trace
        assert not task.done()
    finally:
        release.set()
        gate.set()
        await asyncio.wait_for(task, 2)
        await r.ns["prices"].join_stamp(r.ns["blend_refresher"])
    assert r.committed == [1, 2, 3, 9]
    assert len(samples) == 3


async def test_cancelling_future_clock_joins_started_display_and_keeps_debt():
    r = rig()
    r.release.set()
    gate, calls = held_refresher(r)
    entered, release, samples = setup_clock(r)
    task = asyncio.create_task(r.flush())
    try:
        await asyncio.wait_for(entered.wait(), 2)
        assert calls["started"] == [(100,)]
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        release.set()
        gate.set()
    assert calls["cancelled"] == [(100,)]
    assert calls["running"] == 0
    assert r.ns["prices"].stamping is None
    assert {1, 2}.issubset(r.ns["prices"].committed_outcome_ids)


async def test_failed_transaction_never_starts_display_or_samples_future_clock():
    r = rig(failed=1)
    r.release.set()
    gate, calls = held_refresher(r)
    entered, release, samples = setup_clock(r)
    release.set()
    assert await r.flush() is False
    assert calls["started"] == []
    assert samples == []
    assert not r.committed


async def test_final_drain_does_not_add_clock_sampling():
    r = rig()
    r.release.set()
    gate, calls = held_refresher(r, hold_ids=())
    entered, release, samples = setup_clock(r)
    release.set()
    assert await r.flush(final_drain=True) is True
    assert samples == []
    assert r.committed == [1, 2, 3, 9]


async def test_real_refresher_publishes_before_future_clock_completes(monkeypatch):
    from tests.test_kalshi_fresh_admission_10090 import _caller
    from tests.test_single_event_commit_10090 import settle_until

    x, r = _caller(monkeypatch, blocked=())
    entered, release, samples = setup_clock(r)
    task = asyncio.create_task(r.flush(1000.0))
    try:
        await asyncio.wait_for(entered.wait(), 2)
        await settle_until(lambda: 1 in x.published)
        assert 1 in x.committed
        assert r.committed == [1, 2]
        assert samples == [(1, 2)]
        assert not task.done()
    finally:
        release.set()
        x.release.set()
        await asyncio.wait_for(task, 2)
        await r.ns["prices"].join_stamp(x.r)
