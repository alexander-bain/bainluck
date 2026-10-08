"""An earlier game's committed frame survives a later game's stamp wait/failure."""

import asyncio
from contextlib import asynccontextmanager
from copy import copy
from types import SimpleNamespace

import pytest
from sqlalchemy.sql.dml import Update

from app.utils.repair_lock_budget import SET_LOCK_TIMEOUT_SQL
from tests.test_live_blend_refresh import (
    _LockTimeout, _RecordingSession, _event_and_market, _one_event_refresher,
)


def rig(monkeypatch, *, count=3, block=False, failure=None, statuses=None):
    event, market = _event_and_market()
    rows = []
    for eid in range(1, count + 1):
        e, m = copy(event), copy(market)
        e.id = m.event_id = eid
        if statuses is not None:
            e.status = statuses[eid]
        m.id = eid * 10
        rows.append((m, e))
    returned = {"polymarket": {"value": 0.9, "updated_at": "2026-10-08T18:00:00+00:00"}}
    r, frames = _one_event_refresher(monkeypatch, None, min_refresh_interval_s=0)
    r._inversion = dict.fromkeys(range(1, count + 1), (float("inf"), False))
    r._last_snapshot_at = dict.fromkeys(range(1, count + 1), 1000)
    sessions, committed, published, commands = [], [], [], []
    second_stamp, release = asyncio.Event(), asyncio.Event()

    class Session(_RecordingSession):
        def __init__(self):
            super().__init__(rows, [], returned)
            self.returned_rev = 42
            self.event_ids = []

        async def execute(self, statement, *args, **kwargs):
            if isinstance(statement, Update):
                eid = statement.compile().params["id_1"]
                self.event_ids.append(eid)
                commands.append("update")
                if eid == 2:
                    second_stamp.set()
                    if block:
                        await release.wait()
                    if failure == "lock":
                        raise _LockTimeout("canceling statement due to lock timeout")
            else:
                commands.append("budget" if statement is SET_LOCK_TIMEOUT_SQL else "read")
            return await super().execute(statement, *args, **kwargs)

    @asynccontextmanager
    async def factory():
        session = Session()
        sessions.append(session)
        yield session
        if failure == "commit" and session.event_ids == [2]:
            raise RuntimeError("second game's commit failed")
        committed.extend(session.event_ids)

    async def publish(batch):
        for frame in batch:
            assert frame["event_id"] in committed
            assert frame["rev"] == {str(frame["event_id"]): 42}
            published.append(frame["event_id"])
        frames.extend(batch)

    r._session_factory = factory
    r._publish = publish
    return SimpleNamespace(**locals())


async def settle_until(predicate):
    async with asyncio.timeout(1):
        while not predicate():
            await asyncio.sleep(0)


async def test_live_stamps_lead_within_fresh_and_pending_but_fresh_stays_first(monkeypatch):
    x = rig(monkeypatch, count=4, statuses={
        1: "scheduled", 2: "scheduled", 3: "live", 4: "live",
    })
    x.r._lock_retry = {2, 4}
    await x.r.refresh([1, 3], flush_started=1000)
    # Fresh live 3 precedes fresh scheduled 1; both still precede debt,
    # where live 4 precedes scheduled 2. No event is dropped or grouped.
    assert x.committed == x.published == [3, 1, 4, 2]
    assert [s.event_ids for s in x.sessions if s.event_ids] == [[3], [1], [4], [2]]
    assert x.r.stats["stamped"] == 4
    assert not x.r.pending_event_ids()


@pytest.mark.parametrize("outcome", ["release", "failure", "cancel"])
async def test_fresh_stamp_publishes_before_pending_preparation(monkeypatch, outcome):
    x = rig(monkeypatch)
    x.r._lock_retry = {1, 2}
    prepare = x.r._prepare_groups
    reads = []
    entered, release = asyncio.Event(), asyncio.Event()

    async def prepare_population(event_ids):
        reads.append(set(event_ids))
        if 1 in event_ids:
            entered.set()
            await release.wait()
            if outcome == "failure":
                raise RuntimeError("pending preparation failed")
        return await prepare(event_ids)

    x.r._prepare_groups = prepare_population
    task = asyncio.create_task(x.r.refresh([3], flush_started=1000))
    try:
        await asyncio.wait_for(entered.wait(), 1)
        await settle_until(lambda: x.published == [3])
        assert x.committed == [3]
        assert reads == [{3}, {1, 2}]
        if outcome == "cancel":
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        else:
            release.set()
            await asyncio.wait_for(task, 1)
        if outcome == "release":
            assert x.published == x.committed == [3, 1, 2]
            assert x.commands.count("read") == 2
            assert not x.r.pending_event_ids()
        else:
            assert x.published == x.committed == [3]
            assert x.r.pending_event_ids() == frozenset({1, 2})
            assert x.r._lock_retry == {1, 2}
            assert not x.r._failed_hold_until
            assert x.r.stats["errors"] == (outcome == "failure")
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)


async def test_fresh_preparation_failure_keeps_fresh_owed_and_attempts_pending(monkeypatch):
    x = rig(monkeypatch)
    x.r._lock_retry = {1, 2}
    prepare = x.r._prepare_groups

    async def prepare_population(event_ids):
        if 3 in event_ids:
            raise RuntimeError("fresh preparation failed")
        return await prepare(event_ids)

    x.r._prepare_groups = prepare_population
    await x.r.refresh([3], flush_started=1000)
    assert x.published == x.committed == [1, 2]
    assert x.r.pending_event_ids() == frozenset({3})
    assert x.r._failed_hold_until == {3: 1005}
    assert x.r.stats["errors"] == 1


@pytest.mark.parametrize("count", [2, 4, 5])
async def test_first_game_commits_and_publishes_while_second_stamp_waits(monkeypatch, count):
    x = rig(monkeypatch, count=count, block=True)
    task = asyncio.create_task(x.r.refresh(range(1, count + 1), flush_started=1000))
    try:
        await asyncio.wait_for(x.second_stamp.wait(), 1)
        await settle_until(lambda: x.published == [1])
        assert x.committed == [1]
        assert not task.done()
        assert x.r._last_written_value == {1: 0.9}
        x.release.set()
        await asyncio.wait_for(task, 1)
        assert x.published == x.committed == list(range(1, count + 1))
        assert x.r.stats["stamped"] == count
        assert not x.r.pending_event_ids()
    finally:
        x.release.set()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.parametrize("count", [1, 2, 4, 5])
async def test_shared_read_and_per_event_command_tradeoff(monkeypatch, count):
    x = rig(monkeypatch, count=count)
    await x.r.refresh(range(1, count + 1), flush_started=1000)
    assert x.commands.count("read") == 1
    assert x.commands.count("budget") == x.commands.count("update") == count
    assert len(x.sessions) == (1 if count == 1 else count + 1)
    assert not any(s.savepoints or s.rollbacks for s in x.sessions)
    assert x.published == list(range(1, count + 1))


@pytest.mark.parametrize("failure", ["lock", "commit"])
async def test_second_game_failure_keeps_its_debt_and_later_game_progresses(monkeypatch, failure):
    x = rig(monkeypatch, failure=failure)
    await x.r.refresh([1, 2, 3], flush_started=1000)
    assert x.published == [1, 3]
    assert x.r.stats["stamped"] == 2
    assert x.r._last_written_value == {1: 0.9, 3: 0.9}
    assert x.r.pending_event_ids() == frozenset({2})
    if failure == "lock":
        assert sum(s.rollbacks for s in x.sessions) == 1
        assert x.r._lock_retry == {2}
        assert 2 not in x.r._last_refresh_at
        assert x.r.stats["lock_skipped"] == 1
    else:
        assert set(x.r._failed_hold_until) == {2}
        assert x.r.stats["errors"] == 1


async def test_cancelled_later_stamp_joins_prior_sender_and_preserves_uncommitted_debt(monkeypatch):
    x = rig(monkeypatch, block=True)
    task = asyncio.create_task(x.r.refresh([1, 2, 3], flush_started=1000))
    try:
        await asyncio.wait_for(x.second_stamp.wait(), 1)
        await settle_until(lambda: x.published == [1])
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 1)
        assert x.published == x.committed == [1]
        assert x.r.pending_event_ids() == frozenset({2, 3})
        assert not x.r._failed_hold_until
        assert x.r._last_written_value == {1: 0.9}
    finally:
        x.release.set()
        await asyncio.gather(task, return_exceptions=True)


async def test_cancel_joins_active_sender_cleanup_before_returning(monkeypatch):
    x = rig(monkeypatch, block=True)
    entered, cleaning, cleaned, release_cleanup = (asyncio.Event() for _ in range(4))

    async def publish(frames):
        assert x.committed == [1]
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cleaning.set()
            await release_cleanup.wait()
            cleaned.set()

    x.r._publish = publish
    task = asyncio.create_task(x.r.refresh([1, 2, 3], flush_started=1000))
    try:
        await asyncio.wait_for(x.second_stamp.wait(), 1)
        await asyncio.wait_for(entered.wait(), 1)
        task.cancel()
        await asyncio.wait_for(cleaning.wait(), 1)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done() and not cleaned.is_set()
        release_cleanup.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 1)
        assert cleaned.is_set()
        assert x.r.pending_event_ids() == frozenset({2, 3})
        assert x.r._last_written_value == {1: 0.9}
    finally:
        release_cleanup.set()
        x.release.set()
        await asyncio.gather(task, return_exceptions=True)
