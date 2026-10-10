"""A committed group's Redis wait cannot hold the next disjoint DB group.

e0b52e11ed: every due event now commits in its own write transaction (the
groups of four this file was written against are gone), and since
6d8b493900 / fe0aa54fbf a queued fresh event rereads in its own session. The
invariants are unchanged and asserted per event: a later transaction commits
while an earlier frame's publication waits; one publication is in flight at
a time, each after its own commit; a failed transaction leaves only its event
owed; a cancelled refresh joins its sender and its committed-but-unsent
frames, and only uncommitted events stay owed.
"""

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

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
    committed_events = []  # the event each committed transaction stamped
    entered = asyncio.Event()
    second_db = asyncio.Event()
    ack = {i: asyncio.Event() for i in range(1, count + 1)}
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
        committed_events.extend(
            statement.compile().params["id_1"] for statement in session.updates
        )

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

    async def read(_session, event_ids):
        # 6d8b493900 / fe0aa54fbf: a queued fresh event rereads its current
        # quotes in its own write session; the rig's database is `prepared`.
        return {eid: prepared[eid] for eid in event_ids if eid in prepared}

    r._prepare_groups = prepare
    r._read_groups = read
    r._session_factory = factory
    r._publish = publish
    return SimpleNamespace(**locals())


async def settle_until(predicate):
    async with asyncio.timeout(1):
        while not predicate():
            await asyncio.sleep(0)


async def _ack_each_publication_in_turn(x, task):
    """Release each frame's ack only once it is the one publication in flight."""
    sent = 0
    while True:
        await settle_until(lambda: task.done() or len(x.publications) > sent)
        if len(x.publications) <= sent:
            return
        assert len(x.publications) == sent + 1 and len(x.finished) == sent, (
            "one publication in flight at a time"
        )
        x.ack[x.publications[sent][0]].set()
        sent += 1
        await settle_until(lambda: task.done() or len(x.finished) >= sent)


def _published(x):
    return [event_id for frame in x.publications for event_id in frame]


async def test_next_db_commits_before_prior_ack_and_publication_stays_ordered(monkeypatch):
    x = rig(monkeypatch)
    task = asyncio.create_task(x.r.refresh(range(1, 13), flush_started=1000))
    try:
        # Event 1's frame waits for its ack while a later transaction commits.
        await settle_until(lambda: x.publications == [[1]] and len(x.committed) >= 2)
        assert x.finished == []
        await _ack_each_publication_in_turn(x, task)
        await asyncio.wait_for(task, 1)
        assert x.finished == x.publications
        assert sorted(_published(x)) == list(range(1, 13))
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
        await settle_until(lambda: x.publications == [[1]] and x.second_db.is_set())
        await _ack_each_publication_in_turn(x, task)
        await asyncio.wait_for(task, 1)
        assert x.finished[0] == [1], "the earlier sender finished despite the failure"
        failed = set(range(1, 13)) - set(_published(x))
        assert len(failed) == 1 and failed.isdisjoint(x.committed_events)
        assert x.r.pending_event_ids() == frozenset(failed)
        assert x.r.stats["stamped"] == 11
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
        await settle_until(lambda: len(x.committed) >= 2)
        task.cancel()
        await asyncio.wait_for(x.cleaning.wait(), 1)
        assert not task.done()
        # A second consumer interruption must not interrupt socket cleanup.
        task.cancel()
        await asyncio.sleep(0)
        assert not x.cleaned.is_set() and not task.done()
        x.release_cleanup.set()
        unsent = set(x.committed_events) - {1}
        assert unsent, "a committed frame was still unsent at cancellation"
        await settle_until(lambda: len(x.publications) == 2)
        assert set(x.publications[-1]) == unsent
        assert not task.done(), "definitely-unsent committed frames must be joined"
        task.cancel()
        await asyncio.sleep(0)
        assert x.finished == []
        x.ack[x.publications[-1][0]].set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 1)
        assert x.cleaned.is_set()
        assert x.publications[0] == [1]
        assert x.finished == [x.publications[-1]]
        assert x.r.pending_event_ids() == frozenset(
            set(range(1, 13)) - set(x.committed_events)
        )
    finally:
        x.release_cleanup.set()
        for ack in x.ack.values():
            ack.set()
        await asyncio.gather(task, return_exceptions=True)


async def test_one_group_still_awaits_its_publication_directly(monkeypatch):
    # e0b52e11ed: the single-event path now keeps the direct read/write; one
    # event is what still owns the whole refresh and awaits its own frame.
    x = rig(monkeypatch, count=1)
    task = asyncio.create_task(x.r.refresh([1], flush_started=1000))
    try:
        await asyncio.wait_for(x.entered.wait(), 1)
        assert not task.done() and x.committed == [1]
        x.ack[1].set()
        await asyncio.wait_for(task, 1)
        assert x.finished == [[1]]
    finally:
        x.ack[1].set()
        await asyncio.gather(task, return_exceptions=True)
