"""Fresh siblings progress with fixed stamp workers and one committed-frame sender."""

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


def rig(monkeypatch, *, count=3, block=False, failure=None, statuses=None, blocked=(2,)):
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
                if block and eid in blocked:
                    await release.wait()
                if eid == 2:
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

    read_groups = r._read_groups

    async def filtered_read(session, event_ids):
        # The fake session answers every read with all rows; the real query
        # filters by event id. A queued fresh stamp rereads only its own event.
        grouped = await read_groups(session, event_ids)
        return {eid: group for eid, group in grouped.items() if eid in event_ids}

    r._read_groups = filtered_read
    r._session_factory = factory
    r._publish = publish
    return SimpleNamespace(**locals())


async def settle_until(predicate):
    async with asyncio.timeout(1):
        while not predicate():
            await asyncio.sleep(0)


async def test_pending_budget_frees_next_fresh_flush_and_fairly_resumes_old_debt(monkeypatch):
    from app.tasks import live_blend_refresh as module

    clock = [1000.0]
    monkeypatch.setattr(module, "_mono", lambda: clock[0])
    x = rig(monkeypatch, count=7, failure="lock", statuses={
        1: "scheduled", 2: "live", 3: "live", 4: "live",
        5: "live", 6: "live", 7: "live",
    })
    x.r._lock_retry = set(range(1, 7))
    attempt = x.r._refresh_batch
    attempted = []

    async def slow_stamp(ids, *args, **kwargs):
        attempted.extend(ids)
        if ids != [7]:
            clock[0] += 0.6
        await attempt(ids, *args, **kwargs)

    x.r._refresh_batch = slow_stamp
    await x.r.refresh([7], flush_started=1000)
    assert attempted == [7, 2, 3]
    assert x.published == [7, 3]
    assert x.r.pending_event_ids() == frozenset({1, 2, 4, 5, 6})
    assert not x.r._failed_hold_until

    # More callbacks in the SAME producer flush must not buy another budget.
    reads = x.commands.count("read")
    await x.r.refresh_pending(flush_started=1000)
    assert attempted == [7, 2, 3] and x.commands.count("read") == reads
    await x.r.refresh([7], flush_started=1000)
    assert attempted == [7, 2, 3, 7]  # fresh remains admitted

    # Newly arrived fresh work leads, but repeatedly locked live2 cannot jump
    # ahead of the untouched debt left by the previous flush, including1.
    await x.r.refresh([7], flush_started=1002)
    assert attempted[-3:] == [7, 4, 5]
    await x.r.refresh_pending(flush_started=1004)
    assert attempted[-2:] == [6, 1]
    assert x.r.pending_event_ids() == frozenset({2})
    await x.r.refresh_pending(flush_started=1006)
    assert attempted[-1] == 2  # quiet singleton still retries
    assert set(x.published) == {1, 3, 4, 5, 6, 7}


async def test_final_drain_attempts_all_pending_after_periodic_budget_exhausted(monkeypatch):
    from app.tasks import live_blend_refresh as module

    clock = [1000.0]
    monkeypatch.setattr(module, "_mono", lambda: clock[0])
    x = rig(monkeypatch, count=5)
    x.r._throttle_deferred = set(range(1, 6))
    attempt = x.r._refresh_batch

    async def slow_stamp(ids, *args, **kwargs):
        clock[0] += 1.1
        await attempt(ids, *args, **kwargs)

    x.r._refresh_batch = slow_stamp
    await x.r.refresh_pending(flush_started=1000)
    assert x.published == [1]
    assert x.r.pending_event_ids() == frozenset({2, 3, 4, 5})
    await x.r.refresh_pending()  # ordinary final-drain calling convention
    assert x.published == [1, 2, 3, 4, 5]
    assert not x.r.pending_event_ids() and not x.r._pending_continuation


async def test_fresh_work_spending_residual_budget_skips_later_pending_read(monkeypatch):
    from app.tasks import live_blend_refresh as module

    clock = [1000.0]
    monkeypatch.setattr(module, "_mono", lambda: clock[0])
    x = rig(monkeypatch, count=4, failure="lock")
    x.r._lock_retry = {2}
    attempt, prepare = x.r._refresh_batch, x.r._prepare_groups
    second_call = False
    reads = []

    async def slow_stamp(ids, *args, **kwargs):
        if ids == [2]:
            clock[0] += 0.6
        elif second_call:
            clock[0] += 0.3
        await attempt(ids, *args, **kwargs)

    async def read(ids):
        reads.append(set(ids))
        return await prepare(ids)

    x.r._refresh_batch, x.r._prepare_groups = slow_stamp, read
    await x.r.refresh([4], flush_started=1000)
    assert x.r._lock_retry == {2}
    second_call = True
    await x.r.refresh([3, 4], flush_started=1000)
    assert reads == [{4}, {2}, {3, 4}]
    assert 3 in x.committed and 3 in x.published
    assert x.r.pending_event_ids() == frozenset({2})
    assert not x.r._failed_hold_until


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
        # Independent fresh games publish in completion order (ruling A).
        ready = [1, *range(3, count + 1)]
        await settle_until(lambda: sorted(x.published) == ready)
        assert x.committed == x.published
        assert not task.done()
        assert x.r._last_written_value == dict.fromkeys(ready, 0.9)
        x.release.set()
        await asyncio.wait_for(task, 1)
        assert x.published == x.committed and x.published[-1] == 2
        assert sorted(x.published) == list(range(1, count + 1))
        assert x.r.stats["stamped"] == count
        assert not x.r.pending_event_ids()
    finally:
        x.release.set()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.parametrize("count", [1, 2, 4, 5])
async def test_shared_read_and_per_event_command_tradeoff(monkeypatch, count):
    from app.tasks.live_blend_refresh import FRESH_STAMP_WORKERS

    x = rig(monkeypatch, count=count)
    await x.r.refresh(range(1, count + 1), flush_started=1000)
    # One shared prepared read, plus one current reread per queued fresh event.
    assert x.commands.count("read") == 1 + max(0, count - FRESH_STAMP_WORKERS)
    assert x.commands.count("budget") == x.commands.count("update") == count
    assert len(x.sessions) == (1 if count == 1 else count + 1)
    assert not any(s.savepoints or s.rollbacks for s in x.sessions)
    assert x.published == x.committed
    assert sorted(x.published) == list(range(1, count + 1))


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
        await settle_until(lambda: x.published == [1, 3])
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 1)
        assert x.published == x.committed == [1, 3]
        assert x.r.pending_event_ids() == frozenset({2})
        assert not x.r._failed_hold_until
        assert x.r._last_written_value == {1: 0.9, 3: 0.9}
    finally:
        x.release.set()
        await asyncio.gather(task, return_exceptions=True)


async def test_cancel_joins_active_sender_cleanup_before_returning(monkeypatch):
    x = rig(monkeypatch, block=True)
    entered, cleaning, cleaned, release_cleanup = (asyncio.Event() for _ in range(4))

    async def publish(frames):
        assert all(frame["event_id"] in x.committed for frame in frames)
        if frames[0]["event_id"] != 1:
            return
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
        await settle_until(lambda: x.committed == [1, 3])
        task.cancel()
        await asyncio.wait_for(cleaning.wait(), 1)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done() and not cleaned.is_set()
        release_cleanup.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 1)
        assert cleaned.is_set()
        assert x.r.pending_event_ids() == frozenset({2})
        assert x.r._last_written_value == {1: 0.9, 3: 0.9}
    finally:
        release_cleanup.set()
        x.release.set()
        await asyncio.gather(task, return_exceptions=True)


async def test_blocked_first_fresh_stamp_does_not_hold_sibling_publication(monkeypatch):
    x = rig(monkeypatch, block=True)
    task = asyncio.create_task(x.r.refresh([2, 3], flush_started=1000))
    try:
        await asyncio.wait_for(x.second_stamp.wait(), 1)
        await settle_until(lambda: x.published == [3])
        assert x.committed == [3] and not task.done()
        assert x.commands.count("read") == 1
        x.release.set()
        await asyncio.wait_for(task, 1)
        assert x.published == x.committed == [3, 2]
        assert not x.r.pending_event_ids()
    finally:
        x.release.set()
        await asyncio.gather(task, return_exceptions=True)


async def test_third_ready_game_publishes_while_two_stamps_wait_on_rows(monkeypatch):
    x = rig(monkeypatch, count=3, block=True, blocked=(1, 2))
    task = asyncio.create_task(x.r.refresh([1, 2, 3], flush_started=1000))
    try:
        await settle_until(
            lambda: {eid for s in x.sessions for eid in s.event_ids} >= {1, 2}
        )
        # Two disjoint stamps hold their sessions on row waits; the third
        # ready game still commits and publishes before either is released.
        await settle_until(lambda: x.published == [3])
        assert x.committed == [3] and not task.done()
        assert x.commands.count("read") == 1
        x.release.set()
        await asyncio.wait_for(task, 1)
        assert x.published == x.committed == [3, 1, 2]
        assert not x.r.pending_event_ids()
    finally:
        x.release.set()
        await asyncio.gather(task, return_exceptions=True)


async def test_fresh_population_uses_only_fixed_stamp_workers(monkeypatch):
    from app.tasks.live_blend_refresh import FRESH_STAMP_WORKERS

    x = rig(monkeypatch, count=9)
    stamp = x.r._refresh_batch
    entered, release = asyncio.Event(), asyncio.Event()
    active = maximum = 0
    owners = set()

    async def gated_stamp(ids, *args, **kwargs):
        nonlocal active, maximum
        owners.add(asyncio.current_task())
        active += 1
        maximum = max(maximum, active)
        if active == FRESH_STAMP_WORKERS:
            entered.set()
        try:
            await release.wait()
            await stamp(ids, *args, **kwargs)
        finally:
            active -= 1

    x.r._refresh_batch = gated_stamp
    task = asyncio.create_task(x.r.refresh(range(1, 10), flush_started=1000))
    try:
        await asyncio.wait_for(entered.wait(), 1)
        await asyncio.sleep(0)
        assert active == maximum == len(owners) == FRESH_STAMP_WORKERS == 3
        release.set()
        await asyncio.wait_for(task, 1)
        assert maximum == len(owners) == FRESH_STAMP_WORKERS and active == 0
        assert all(owner.done() for owner in owners)
        # One prepared read, plus one current reread per queued fresh event.
        assert x.commands.count("read") == 1 + 9 - FRESH_STAMP_WORKERS
        assert set(x.published) == set(x.committed) == set(range(1, 10))
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)


async def test_cancel_preserves_both_waiting_committed_groups_and_one_sender(monkeypatch):
    x = rig(monkeypatch, count=6)
    entered, cleaning, release_cleanup, cleanup_send, release_send = (
        asyncio.Event() for _ in range(5)
    )
    active = maximum = 0
    submitted, delivered = [], []

    async def publish(frames):
        nonlocal active, maximum
        ids = [frame["event_id"] for frame in frames]
        assert set(ids).issubset(x.committed)
        submitted.append(ids)
        active += 1
        maximum = max(maximum, active)
        try:
            if ids == [1]:
                entered.set()
                try:
                    await asyncio.Event().wait()
                finally:
                    cleaning.set()
                    await release_cleanup.wait()
            else:
                cleanup_send.set()
                await release_send.wait()
                delivered.extend(ids)
        finally:
            active -= 1

    x.r._publish = publish
    task = asyncio.create_task(x.r.refresh(range(1, 7), flush_started=1000))
    try:
        await asyncio.wait_for(entered.wait(), 1)
        # Event 1 plus one stamp per fixed worker commit (a queued event
        # rereads its own row, 6d8b493900); then every worker waits on the
        # one sender, so 2..4 form the second waiting group.
        await settle_until(lambda: sorted(x.committed) == [1, 2, 3, 4])
        task.cancel()
        await asyncio.wait_for(cleaning.wait(), 1)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
        release_cleanup.set()
        await asyncio.wait_for(cleanup_send.wait(), 1)
        assert [submitted[0], sorted(submitted[1])] == [[1], [2, 3, 4]]
        assert len(submitted) == 2
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done() and active == maximum == 1
        release_send.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 1)
        assert sorted(delivered) == [2, 3, 4] and active == 0 and maximum == 1
        assert x.r.pending_event_ids() == frozenset({5, 6})
        assert not x.r._failed_hold_until
        assert set(x.r._last_written_value) == {1, 2, 3, 4}
    finally:
        release_cleanup.set()
        release_send.set()
        task.cancel()  # a failed wait must fail, not hang on publish([1])
        await asyncio.gather(task, return_exceptions=True)


async def test_repeated_cancel_joins_every_stamp_worker_before_debt(monkeypatch):
    x = rig(monkeypatch, count=5, block=True)
    stamp = x.r._refresh_batch
    entered, release_cleanup = set(), asyncio.Event()
    cleaning, cleaned = set(), set()
    owners = set()

    async def stamp_with_cleanup(ids, *args, **kwargs):
        if ids == [1]:
            return await stamp(ids, *args, **kwargs)
        eid = ids[0]
        owners.add(asyncio.current_task())
        try:
            if eid in (3, 4):
                entered.add(eid)
                await asyncio.Event().wait()
            await stamp(ids, *args, **kwargs)
        finally:
            cleaning.add(eid)
            await release_cleanup.wait()
            cleaned.add(eid)

    x.r._refresh_batch = stamp_with_cleanup
    task = asyncio.create_task(x.r.refresh(range(1, 6), flush_started=1000))
    try:
        await asyncio.wait_for(x.second_stamp.wait(), 1)
        await settle_until(lambda: entered == {3, 4})
        await settle_until(lambda: x.published == [1])
        task.cancel()
        await settle_until(lambda: cleaning == {2, 3, 4})
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done() and not cleaned
        release_cleanup.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 1)
        assert cleaned == {2, 3, 4} and all(owner.done() for owner in owners)
        assert x.committed == x.published == [1]
        assert x.r.pending_event_ids() == frozenset({2, 3, 4, 5})
        assert not x.r._failed_hold_until
    finally:
        release_cleanup.set()
        x.release.set()
        task.cancel()  # a failed wait must fail, not hang on the held stamps
        await asyncio.gather(task, return_exceptions=True)
