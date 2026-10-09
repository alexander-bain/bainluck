"""#10090 — a newly committed Kalshi cohort joins the running blend refresh.

Ship: a new eligible Kalshi probability reaches its event headline while an
unrelated older stamp is still waiting. The decisive control runs the real
`flush_prices` with the real `LiveBlendRefresher`: game 1's stamp is held in
its UPDATE; game 2's whole cohort then commits, and its event frame must be
committed AND published before game 1's stamp is released. On the parent the
cohort waited in the flush until the held refresh returned.

Cross-flush: the refresh is the run's (`prices.stamping`), so the flush that
started it returns without waiting for it. The NEXT timed flush's committed
cohort joins it on that flush's own clock and publishes before the earlier
flush's held stamp is released. On e3e3f8df06 the first flush never returned
while its stamp was held, so the next flush could not begin.

The rest bound the change: fenced events are refused, never stamped twice;
admitted sessions share the call's FRESH_STAMP_WORKERS slots; cancellation
leaves every admitted event that did not commit owed. Source/progress
controls, not production timing.
"""
import asyncio
from contextlib import asynccontextmanager

import pytest

from tests.test_kalshi_game_isolation_10655 import rig as flush_rig
from tests.test_single_event_commit_10090 import rig as refresher_rig, settle_until

pytestmark = pytest.mark.asyncio


def _caller(monkeypatch, *, blocked):
    """The real flush (outcomes 1,2 -> game 1; 3 -> game 2; 9 standalone)
    driving the real refresher, whose UPDATEs for ``blocked`` games wait."""
    x = refresher_rig(monkeypatch, count=2, block=True, blocked=blocked)
    r = flush_rig()
    r.events.clear()
    r.events.update({1: 1, 2: 1, 3: 2})
    r.release.set()  # the flush's own price writes are not held

    async def market_changes(session):
        r.trace.append(("publish", tuple(session.rows)))

    x.r.publish_market_changes = market_changes
    r.ns["blend_refresher"] = x.r
    return x, r


async def test_new_cohort_is_committed_and_published_while_older_stamp_is_held(
    monkeypatch,
):
    x, r = _caller(monkeypatch, blocked=(1,))
    flush = asyncio.create_task(r.flush(1000.0))
    try:
        await settle_until(lambda: 2 in x.published)
        assert r.committed[:3] == [1, 2, 3]
        assert 2 in x.committed and 1 not in x.committed, "game 1 still held"
        # The flush no longer waits for the run's held refresh.
        assert await asyncio.wait_for(flush, 2) is True
        assert r.ns["prices"].stamping is not None and 1 not in x.committed
    finally:
        x.release.set()
    await asyncio.wait_for(r.ns["prices"].join_stamp(x.r), 2)
    assert sorted(x.published) == sorted(x.committed) == [1, 2]
    assert not x.r.pending_event_ids() and x.r._admission is None
    assert x.r.stats["errors"] == 0


async def test_cancelled_join_leaves_admitted_and_held_games_owed(monkeypatch):
    # The flush returned with both stamps held; the consumer joins the run's
    # refresh before a scope swap or its final drain. A cancellation landing
    # on that join cancels and joins the refresh: nothing escapes, and every
    # committed game that did not stamp stays owed with no failed-retry hold.
    x, r = _caller(monkeypatch, blocked=(1, 2))
    assert await asyncio.wait_for(r.flush(1000.0), 2) is True
    await settle_until(lambda: x.commands.count("update") == 2)
    join = asyncio.create_task(r.ns["prices"].join_stamp(x.r))
    await asyncio.sleep(0)
    join.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(join, 2)
    assert r.ns["prices"].stamping is None
    assert x.committed == [] and x.published == []
    assert x.r.pending_event_ids() == frozenset({1, 2})
    assert not x.r._failed_hold_until and x.r._admission is None


async def test_fenced_or_foreign_cohorts_are_refused_and_left_to_the_caller(
    monkeypatch,
):
    x = refresher_rig(monkeypatch, count=3, block=True, blocked=(1,))
    running = asyncio.create_task(x.r.refresh([1], flush_started=1000))
    await settle_until(lambda: "update" in x.commands)
    admit = x.r.admit_fresh
    assert admit([1], flush_started=1000) == frozenset(), "same event in flight"
    assert admit([2], flush_started=999) == frozenset(), "an earlier flush"
    assert admit([2], flush_started=None) == frozenset(), "final drain"
    assert admit([2, 3], flush_started=1000, defer_event_ids=[3]) == {2}
    assert admit([2], flush_started=1000) == frozenset(), "already admitted"
    await settle_until(lambda: 2 in x.published)
    assert 1 not in x.committed
    x.release.set()
    await asyncio.wait_for(running, 2)
    assert admit([3], flush_started=1000) == frozenset(), "closed with its call"
    assert sorted(x.published) == [1, 2]
    assert x.r.pending_event_ids() == frozenset()


async def test_later_waves_publish_after_earlier_admitted_workers_finished(
    monkeypatch,
):
    # More than FRESH_STAMP_WORKERS separately completed waves while the
    # running call's own stamp is held: each finished worker must give its
    # place back, or wave 5 is accepted, queued with no worker, and only
    # returned to debt once game 1 is released.
    x = refresher_rig(monkeypatch, count=6, block=True, blocked=(1,))
    running = asyncio.create_task(x.r.refresh([1], flush_started=1000))
    try:
        await settle_until(lambda: "update" in x.commands)
        for event_id in (2, 3, 4, 5, 6):
            assert x.r.admit_fresh([event_id], flush_started=1000) == {event_id}
            await settle_until(lambda: event_id in x.published)
            await settle_until(
                lambda: all(t.done() for t in x.r._admission.workers)
            )
        assert x.published == [2, 3, 4, 5, 6] and 1 not in x.committed
        assert not running.done(), "the call still joins the held stamp"
    finally:
        x.release.set()
    await asyncio.wait_for(running, 2)
    assert x.published == [2, 3, 4, 5, 6, 1]
    assert not x.r.pending_event_ids() and x.r._admission is None
    assert x.r.stats["errors"] == 0


async def test_admitted_stamp_waits_for_a_free_slot_within_the_same_call(
    monkeypatch,
):
    x = refresher_rig(monkeypatch, count=4, block=True, blocked=(1, 2, 3))
    factory, open_now, most = x.r._session_factory, [0], [0]

    @asynccontextmanager
    async def counted():
        open_now[0] += 1
        most[0] = max(most[0], open_now[0])
        try:
            async with factory() as session:
                yield session
        finally:
            open_now[0] -= 1

    x.r._session_factory = counted
    running = asyncio.create_task(x.r.refresh([1, 2, 3], flush_started=1000))
    await settle_until(lambda: x.commands.count("update") == 3)
    assert x.r.admit_fresh([4], flush_started=1000) == {4}
    for _ in range(20):
        await asyncio.sleep(0)
    assert open_now[0] == 3 and 4 not in x.committed, "no fourth session"
    x.release.set()
    await asyncio.wait_for(running, 2)
    assert sorted(x.published) == [1, 2, 3, 4]
    assert most[0] == 3


async def test_cancel_before_admitted_first_turn_or_during_publication_keeps_debt(
    monkeypatch,
):
    # Admitted while a cancel is already on its way: the running call's
    # wake-up is ahead of the new worker's first turn, which never comes.
    x = refresher_rig(monkeypatch, count=2, block=True, blocked=(1,))
    running = asyncio.create_task(x.r.refresh([1], flush_started=1000))
    await settle_until(lambda: "update" in x.commands)
    running.cancel()
    assert x.r.admit_fresh([2], flush_started=1000) == {2}
    with pytest.raises(asyncio.CancelledError):
        await running
    assert x.commands.count("update") == 1, "game 2's worker never ran"
    assert x.r.pending_event_ids() == frozenset({1, 2})
    assert not x.r._failed_hold_until and x.r._admission is None

    # Cancelled while the running call's own frame is being sent and the
    # admitted stamp has not committed: the admitted event stays owed.
    y = refresher_rig(monkeypatch, count=2, block=True, blocked=(2,))
    sending, publish = asyncio.Event(), y.r._publish

    async def held_send(frames):
        if any(frame["event_id"] == 1 for frame in frames):
            sending.set()
            await asyncio.Event().wait()
        await publish(frames)

    y.r._publish = held_send
    running = asyncio.create_task(y.r.refresh([1], flush_started=1000))
    await asyncio.wait_for(sending.wait(), 1)
    assert y.r.admit_fresh([2], flush_started=1000) == {2}
    await settle_until(lambda: y.commands.count("update") == 2)
    running.cancel()
    with pytest.raises(asyncio.CancelledError):
        await running
    assert 1 in y.committed and 2 not in y.committed
    assert 2 in y.r.pending_event_ids()
    assert y.r._admission is None


async def test_next_flush_cohort_publishes_while_an_earlier_flush_stamp_is_held(
    monkeypatch,
):
    # The actual call path, two timed flushes: flush 1000.0 commits game 1 and
    # returns while game 1's stamp is held; game 2's input arrives; flush
    # 1002.0 commits game 2's whole cohort, whose event must COMMIT and
    # PUBLISH before game 1's stamp is released.
    x, r = _caller(monkeypatch, blocked=(1,))
    later = r.batch.pop(3)
    del r.batch[9]
    try:
        assert await asyncio.wait_for(r.flush(1000.0), 2) is True
        await settle_until(lambda: "update" in x.commands)
        assert r.committed == [1, 2] and x.committed == []
        r.batch[3] = later
        assert await asyncio.wait_for(r.flush(1002.0), 2) is True
        await settle_until(lambda: 2 in x.published)
        assert r.committed == [1, 2, 3]
        assert x.committed == [2] and 1 not in x.published, "game 1 still held"
        # Stamped on its own flush's clock, not the running call's.
        assert x.r._last_refresh_at[2] == 1002.0
    finally:
        x.release.set()
    await asyncio.wait_for(r.ns["prices"].join_stamp(x.r), 2)
    assert x.published == [2, 1]
    assert x.r._last_refresh_at[1] == 1000.0
    assert not x.r.pending_event_ids() and x.r._admission is None
    assert x.r.stats["errors"] == 0


async def test_later_flush_is_admitted_on_its_clock_only_while_own_stamps_run(
    monkeypatch,
):
    # Bounded: a later flush joins while the call's own stamp is unfinished.
    # Once it has returned the call only drains what it admitted, so a later
    # flush is refused and stays with its caller.
    x = refresher_rig(monkeypatch, count=3, block=True, blocked=(1,))
    hold_two, read_groups = asyncio.Event(), x.r._read_groups

    async def held_read(session, event_ids):
        if event_ids == [2]:
            await hold_two.wait()
        return await read_groups(session, event_ids)

    x.r._read_groups = held_read
    running = asyncio.create_task(x.r.refresh([1], flush_started=1000))
    try:
        await settle_until(lambda: "update" in x.commands)
        assert x.r.admit_fresh([2], flush_started=1002) == {2}
        assert x.r._admission.clocks == {2: 1002}
        x.release.set()
        await settle_until(lambda: 1 in x.published)
        assert x.r._admission.own_done and not running.done()
        assert x.r.admit_fresh([3], flush_started=1004) == frozenset()
    finally:
        x.release.set()
        hold_two.set()
    await asyncio.wait_for(running, 2)
    assert x.published == [1, 2]
    assert x.r._last_refresh_at == {1: 1000, 2: 1002}
    assert x.r.pending_event_ids() == frozenset() and x.r._admission is None
