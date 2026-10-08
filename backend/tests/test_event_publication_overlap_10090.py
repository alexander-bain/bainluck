"""A committed group's Redis wait cannot hold the next disjoint DB group."""

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from app.tasks.live_blend_refresh import LiveBlendRefresher
from tests.test_live_blend_refresh import _RecordingSession, _one_event_refresher


def rig(monkeypatch, *, count=12, block_db=False, fail_db=False):
    returned = {"polymarket": {"value": 0.9, "updated_at": "2026-10-08T18:00:00+00:00"}}
    r, _ = _one_event_refresher(monkeypatch, None, min_refresh_interval_s=0)
    r._last_snapshot_at = dict.fromkeys(range(1, count + 1), 1000)
    prepared = {
        eid: (SimpleNamespace(id=eid, home_team_name="Home", away_team_name="Away",
                              status="live", espn_win_prob_home=None,
                              opening_home_probability=None), [])
        for eid in range(1, count + 1)
    }
    begun, committed, publications, finished = [], [], [], []
    entered = asyncio.Event()
    second_db = asyncio.Event()
    ack = {i: asyncio.Event() for i in range(1, count + 1, 4)}
    cleaning, cleaned, release_cleanup = asyncio.Event(), asyncio.Event(), asyncio.Event()
    release_cleanup.set()

    async def prepare(event_ids):
        return prepared

    @asynccontextmanager
    async def factory():
        index = len(begun) + 1
        begun.append(index)
        if index == 2:
            second_db.set()
            if fail_db:
                raise RuntimeError("second DB transaction failed")
            if block_db:
                await asyncio.Event().wait()
        session = _RecordingSession([], [], returned)
        session.returned_rev = 42
        yield session
        committed.append(index)

    async def publish(frames):
        ids = [f["event_id"] for f in frames]
        assert len(committed) >= len(publications) + 1
        publications.append(ids)
        entered.set()
        try:
            await ack[ids[0]].wait()
            finished.append(ids)
        finally:
            if asyncio.current_task().cancelling():
                cleaning.set()
                await release_cleanup.wait()
                cleaned.set()

    r._prepare_groups = prepare
    r._session_factory = factory
    r._publish = publish
    return SimpleNamespace(**locals())


async def settle_until(predicate):
    async with asyncio.timeout(1):
        while not predicate():
            await asyncio.sleep(0)


async def test_next_db_commits_before_prior_ack_and_publication_stays_ordered(monkeypatch):
    x = rig(monkeypatch)
    task = asyncio.create_task(x.r.refresh(range(1, 13), flush_started=1000))
    try:
        await settle_until(lambda: x.committed == [1, 2] and x.publications)
        assert x.begun == [1, 2]
        assert x.publications == [[1, 2, 3, 4]]
        assert x.finished == []
        x.ack[1].set()
        await settle_until(lambda: x.committed == [1, 2, 3] and len(x.publications) == 2)
        assert x.publications == [[1, 2, 3, 4], [5, 6, 7, 8]]
        x.ack[5].set()
        await settle_until(lambda: len(x.publications) == 3)
        assert not task.done(), "refresh must join its final publication"
        x.ack[9].set()
        await asyncio.wait_for(task, 1)
        assert x.finished == [[1, 2, 3, 4], [5, 6, 7, 8], [9, 10, 11, 12]]
        assert x.r.stats["stamped"] == 12
        assert not x.r.pending_event_ids()
    finally:
        for ack in x.ack.values():
            ack.set()
        await asyncio.gather(task, return_exceptions=True)


async def test_failed_group_does_not_abandon_prior_sender_or_later_frames(monkeypatch):
    x = rig(monkeypatch, fail_db=True)
    task = asyncio.create_task(x.r.refresh(range(1, 13), flush_started=1000))
    try:
        await settle_until(lambda: x.committed == [1, 3] and x.publications)
        assert x.publications == [[1, 2, 3, 4]]
        x.ack[1].set()
        await settle_until(lambda: len(x.publications) == 2)
        assert x.publications[-1] == [9, 10, 11, 12]
        assert not task.done()
        x.ack[9].set()
        await asyncio.wait_for(task, 1)
        assert x.r.pending_event_ids() == frozenset(range(5, 9))
        assert x.r.stats["stamped"] == 8
    finally:
        for ack in x.ack.values():
            ack.set()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.parametrize("block_db", [True, False])
async def test_cancel_joins_sender_and_only_uncommitted_groups_remain_owed(monkeypatch, block_db):
    x = rig(monkeypatch, block_db=block_db)
    x.release_cleanup.clear()
    task = asyncio.create_task(x.r.refresh(range(1, 13), flush_started=1000))
    try:
        await x.entered.wait()
        await x.second_db.wait()
        if not block_db:
            await settle_until(lambda: x.committed == [1, 2])
        task.cancel()
        await asyncio.wait_for(x.cleaning.wait(), 1)
        assert not task.done()
        # A second consumer interruption must not interrupt socket cleanup.
        task.cancel()
        await asyncio.sleep(0)
        assert not x.cleaned.is_set() and not task.done()
        x.release_cleanup.set()
        if not block_db:
            await settle_until(lambda: len(x.publications) == 2)
            assert x.publications[-1] == [5, 6, 7, 8]
            assert not task.done(), "definitely-unsent committed frames must be joined"
            task.cancel()
            await asyncio.sleep(0)
            assert x.finished == []
            x.ack[5].set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 1)
        assert x.cleaned.is_set()
        assert x.publications == ([[1, 2, 3, 4]] if block_db else
                                  [[1, 2, 3, 4], [5, 6, 7, 8]])
        assert x.finished == ([] if block_db else [[5, 6, 7, 8]])
        assert x.r.pending_event_ids() == frozenset(range(5 if block_db else 9, 13))
    finally:
        x.release_cleanup.set()
        for ack in x.ack.values():
            ack.set()
        await asyncio.gather(task, return_exceptions=True)


async def test_one_group_still_awaits_its_publication_directly(monkeypatch):
    x = rig(monkeypatch, count=4)
    # The unchanged <=4 path performs its ordinary read in the write session.
    async def read(session, event_ids):
        return x.prepared
    x.r._read_groups = read
    task = asyncio.create_task(x.r.refresh(range(1, 5), flush_started=1000))
    try:
        await asyncio.wait_for(x.entered.wait(), 1)
        assert not task.done() and x.committed == [1]
        x.ack[1].set()
        await asyncio.wait_for(task, 1)
        assert x.finished == [[1, 2, 3, 4]]
    finally:
        x.ack[1].set()
        await asyncio.gather(task, return_exceptions=True)
