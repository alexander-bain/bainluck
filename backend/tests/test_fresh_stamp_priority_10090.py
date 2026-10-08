"""A committed live quote reaches publication before older queued stamp work."""

import asyncio

import pytest

from tests.test_ws_flush_cadence_10090 import _Recording


async def prepared(event_ids):
    return {}


async def test_fresh_stamp_commits_before_a_blocked_pending_group():
    r = _Recording(min_refresh_interval_s=0)
    r._prepare_groups = prepared
    r.adopt_pending(range(1, 9))
    entered_pending = asyncio.Event()
    release_pending = asyncio.Event()
    original = r._refresh_batch

    async def block_pending(event_ids, now, **kwargs):
        if set(event_ids).intersection(range(1, 9)):
            entered_pending.set()
            await release_pending.wait()
        await original(event_ids, now, **kwargs)

    r._refresh_batch = block_pending
    task = asyncio.create_task(r.refresh([99], flush_started=1000))
    try:
        await asyncio.wait_for(entered_pending.wait(), 1)
        assert r.batches == [([99], 1000)]
        assert r._last_refresh_at[99] == 1000
        release_pending.set()
        await asyncio.wait_for(task, 1)
        assert [ids for ids, _ in r.batches] == [
            [99], [1, 2, 3, 4], [5, 6, 7, 8],
        ]
        assert set(r._last_refresh_at) == {*range(1, 9), 99}
        assert not r.pending_event_ids()
    finally:
        release_pending.set()
        await asyncio.gather(task, return_exceptions=True)


async def test_cancellation_after_fresh_commit_keeps_every_pending_stamp_owed():
    r = _Recording(min_refresh_interval_s=0)
    r._prepare_groups = prepared
    r.adopt_pending(range(1, 9))
    original = r._refresh_batch

    async def cancel_pending(event_ids, now, **kwargs):
        if 99 not in event_ids:
            raise asyncio.CancelledError
        await original(event_ids, now, **kwargs)

    r._refresh_batch = cancel_pending
    with pytest.raises(asyncio.CancelledError):
        await r.refresh([99], flush_started=1000)
    assert r.batches == [([99], 1000)]
    assert r.pending_event_ids() == frozenset(range(1, 9))


async def test_retry_only_refresh_retains_existing_grouping():
    r = _Recording(min_refresh_interval_s=0)
    r._prepare_groups = prepared
    r.adopt_pending(range(1, 10))
    await r.refresh_pending(flush_started=1000)
    assert [ids for ids, _ in r.batches] == [[1, 2, 3, 4], [5, 6, 7, 8], [9]]
