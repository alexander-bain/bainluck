"""#10090 — a fresh-bearing flush's one old attempt reads only its own event.

After d5ee a flush carrying fresh events attempts one old stamp, but the
pending arm still read the WHOLE old population before trying it. When the
continuation already names the next old event, that read cannot change which
event is attempted, so the head now reads its own group in its own write
session. Without a continuation head, and on quiet/untimed flushes, the shared
read and live-first selection are unchanged.
"""

import asyncio

import pytest

from tests.test_single_event_commit_10090 import rig


def hold_preparation(x):
    """Every shared read waits until released; record what it was asked for."""
    calls, release = [], asyncio.Event()
    prepare = x.r._prepare_groups

    async def held(event_ids):
        calls.append(sorted(event_ids))
        await release.wait()
        return await prepare(event_ids)

    x.r._prepare_groups = held
    return calls, release


async def test_continuation_head_stamps_while_the_old_population_read_is_held(monkeypatch):
    x = rig(monkeypatch, count=5)
    x.r._lock_retry = {1, 2, 3, 4}
    x.r._pending_continuation = [2, 3]
    calls, _release = hold_preparation(x)
    # Parent: the old population's shared read is held, so the refresh never
    # reaches the head's stamp.
    async with asyncio.timeout(1):
        await x.r.refresh([5], flush_started=1000)
    assert calls == []
    assert x.committed == x.published == [5, 2]
    # Every other old event stays owed; the continuation keeps its order and
    # gains no guessed order for debt it did not carry.
    assert x.r.pending_event_ids() == frozenset({1, 3, 4})
    assert x.r._lock_retry == {1, 3, 4}
    assert x.r._pending_continuation == [3]
    assert not x.r._failed_hold_until
    # The same flush's later quiet call shares the spent allowance.
    await x.r.refresh_pending(flush_started=1000)
    assert x.committed == [5, 2]


async def test_quiet_flush_after_head_drains_in_the_parents_order(monkeypatch):
    # Parent order for this debt: head 2, continuation 3, then live-first 1, 4.
    x = rig(monkeypatch, count=5)
    x.r._lock_retry = {1, 2, 3, 4}
    x.r._pending_continuation = [2, 3]
    await x.r.refresh([5], flush_started=1000)
    await x.r.refresh_pending(flush_started=1002)
    assert x.committed == x.published == [5, 2, 3, 1, 4]
    assert not x.r.pending_event_ids()


async def test_head_read_failure_stays_with_the_head(monkeypatch):
    x = rig(monkeypatch, count=5)
    x.r._lock_retry = {1, 2, 3}
    x.r._pending_continuation = [2, 3]
    read_groups = x.r._read_groups

    async def failing_read(session, event_ids):
        if event_ids == [2]:
            raise RuntimeError("head read failed")
        return await read_groups(session, event_ids)

    x.r._read_groups = failing_read
    await x.r.refresh([5], flush_started=1000)
    assert x.committed == [5]
    assert x.r.pending_event_ids() == frozenset({1, 2, 3})
    assert x.r._pending_continuation == [3]


async def test_cancelled_head_stamp_keeps_the_head_and_the_rest_owed(monkeypatch):
    x = rig(monkeypatch, count=5, block=True, blocked=(2,))
    x.r._lock_retry = {1, 2, 3}
    x.r._pending_continuation = [2, 3]
    task = asyncio.create_task(x.r.refresh([5], flush_started=1000))
    async with asyncio.timeout(1):
        await x.second_stamp.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert x.committed == [5]
    assert x.r.pending_event_ids() == frozenset({1, 2, 3})
    assert x.r._pending_continuation == [3]
    assert not x.r._failed_hold_until


async def test_without_a_continuation_head_the_shared_read_still_picks_live_first(monkeypatch):
    x = rig(monkeypatch, count=5, statuses={
        1: "scheduled", 2: "scheduled", 3: "live", 4: "scheduled", 5: "live",
    })
    x.r._lock_retry = {1, 2, 3, 4}
    calls, release = hold_preparation(x)
    release.set()
    await x.r.refresh([5], flush_started=1000)
    assert calls == [[1, 2, 3, 4]]
    assert x.committed == [5, 3]
    assert x.r._pending_continuation == [1, 2, 4]


async def test_quiet_and_untimed_calls_keep_the_shared_read(monkeypatch):
    x = rig(monkeypatch, count=5)
    x.r._lock_retry = {1, 2, 3, 4}
    x.r._pending_continuation = [2, 3]
    calls, release = hold_preparation(x)
    release.set()
    await x.r.refresh_pending(flush_started=1000)
    assert calls == [[1, 2, 3, 4]]
    assert x.committed == [2, 3, 1, 4]

    y = rig(monkeypatch, count=5)
    y.r._lock_retry = {1, 2, 3, 4}
    y.r._pending_continuation = [2, 3]
    calls, release = hold_preparation(y)
    release.set()
    await y.r.refresh([5])
    assert calls == [[1, 2, 3, 4]]
    assert y.committed == [5, 2, 3, 1, 4]
