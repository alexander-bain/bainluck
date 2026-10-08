"""Later whole-game commits progress while one earlier refresh is held."""

import asyncio

import pytest

from tests.test_kalshi_game_isolation_10655 import rig
from tests.test_kalshi_pipelined_stamps_10090 import held_refresher

pytestmark = pytest.mark.asyncio


def three_games(*, failed=None):
    r = rig(failed=failed)
    r.batch[4] = (.8, .79, .81)
    r.ns["market_id_by_outcome"][4] = 30
    r.events[4] = 300
    r.ns["input_marks"][4] = 4
    r.release.set()
    return r


async def wait_committed(r, expected):
    for _ in range(100):
        if r.committed == expected:
            return
        await asyncio.sleep(0)
    assert r.committed == expected


async def test_two_later_games_commit_and_coalesce_without_overlapping_refresh():
    r = three_games()
    gate, calls = held_refresher(r)
    flush = asyncio.create_task(r.flush())
    try:
        await wait_committed(r, [1, 2, 3, 4, 9])
        assert calls["started"] == [(100,)] and calls["finished"] == []
        assert not flush.done()
        assert [t for t in r.trace if t[0] == "receipt"] == [("receipt", (1, 2))]
        assert ("publish", (3,)) in r.trace and ("publish", (4,)) in r.trace
    finally:
        gate.set()
        assert await asyncio.wait_for(flush, 2) is True
    assert calls["started"] == [(100,), (200, 300)]
    assert calls["finished"] == calls["started"]
    assert calls["most_running"] == 1 and not r.batch
    assert ("receipt", (3, 4)) in r.trace


async def test_failed_later_write_still_drains_all_earlier_committed_debt():
    r = three_games(failed=4)
    gate, calls = held_refresher(r)
    flush = asyncio.create_task(r.flush())
    try:
        await wait_committed(r, [1, 2, 3])
        assert not flush.done() and calls["started"] == [(100,)]
    finally:
        gate.set()
        assert await asyncio.wait_for(flush, 2) is False
    assert calls["finished"] == [(100,), (200,)]
    assert calls["most_running"] == 1 and set(r.batch) == {4, 9}
    assert ("receipt", (3,)) in r.trace


async def test_cancel_adopts_both_never_started_games_and_joins_active_refresh():
    r = three_games()
    _, calls = held_refresher(r)
    flush = asyncio.create_task(r.flush())
    await wait_committed(r, [1, 2, 3, 4, 9])
    flush.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(flush, 2)
    assert calls["cancelled"] == [(100,)]
    assert calls["running"] == 0 and calls["most_running"] == 1
    assert set().union(*calls["adopted"]) == {100, 200, 300}
    assert not r.batch


@pytest.mark.parametrize("implicit", [False, True])
async def test_late_bridge_respects_active_explicit_and_implicit_event_fence(implicit):
    r = three_games()
    gate, calls = held_refresher(r)
    refresher = r.ns["blend_refresher"]
    # Initial implicit debt is quiet (no price in this snapshot), so the
    # existing planner legitimately separates the game phases.
    refresher.pending_event_ids = lambda: frozenset({999}) if implicit else frozenset()
    original_publish = refresher.publish_market_changes

    async def late_bridge(session):
        await original_publish(session)
        if session.rows == [3]:
            r.events[4] = 999 if implicit else 100

    refresher.publish_market_changes = late_bridge
    flush = asyncio.create_task(r.flush())
    try:
        await wait_committed(r, [1, 2, 3])
        for _ in range(20):
            await asyncio.sleep(0)
        assert 4 not in r.committed and calls["started"] == [(100,)]
    finally:
        gate.set()
        assert await asyncio.wait_for(flush, 2) is True
    assert calls["most_running"] == 1
    assert (999 if implicit else 100) in calls["finished"][-1]


async def test_postcommit_publication_cancel_keeps_registered_game_owed():
    r = three_games()
    _, calls = held_refresher(r)
    refresher = r.ns["blend_refresher"]
    publish_entered = asyncio.Event()
    original_publish = refresher.publish_market_changes

    async def hold_second_publication(session):
        await original_publish(session)
        if session.rows == [3]:
            publish_entered.set()
            await asyncio.Event().wait()

    refresher.publish_market_changes = hold_second_publication
    flush = asyncio.create_task(r.flush())
    await asyncio.wait_for(publish_entered.wait(), 2)
    flush.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(flush, 2)
    assert r.committed == [1, 2, 3]
    assert calls["running"] == 0
    assert set().union(*calls["adopted"]) == {100, 200}
    assert set(r.batch) == {3, 4, 9}


async def test_repeated_cancel_joins_cleanup_and_preserves_queued_debt():
    r = three_games()
    _, calls = held_refresher(r)
    refresher = r.ns["blend_refresher"]
    cleanup_entered, cleanup_release = asyncio.Event(), asyncio.Event()
    cancelled = []

    async def refresh(ids, **kwargs):
        calls["started"].append(tuple(sorted(ids)))
        calls["running"] += 1
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.append(set(ids))
            cleanup_entered.set()
            await cleanup_release.wait()
            raise
        finally:
            calls["running"] -= 1

    refresher.refresh = refresh
    flush = asyncio.create_task(r.flush())
    await wait_committed(r, [1, 2, 3, 4, 9])
    flush.cancel()
    await asyncio.wait_for(cleanup_entered.wait(), 2)
    flush.cancel()
    for _ in range(20):
        await asyncio.sleep(0)
    assert not flush.done() and cancelled == [{100}]
    cleanup_release.set()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(flush, 2)
    assert calls["running"] == 0
    assert set().union(*calls["adopted"]) == {100, 200, 300}


async def test_refresh_cancelled_before_first_turn_keeps_emergency_fresh_ids(monkeypatch):
    r = three_games()
    _, calls = held_refresher(r)
    create_task = asyncio.create_task

    def cancelled_task(coro):
        task = create_task(coro)
        task.cancel()
        return task

    monkeypatch.setattr(asyncio, "create_task", cancelled_task)
    assert await r.flush() is True
    assert calls["started"] == [] and calls["running"] == 0
    assert set().union(*calls["adopted"]) == {100, 200, 300}


async def test_unknown_bridge_admitted_during_publication_still_triggers_refresh():
    r = three_games()
    gate, calls = held_refresher(r)
    refresher = r.ns["blend_refresher"]
    original_publish = refresher.publish_market_changes

    async def admit_bridge(session):
        await original_publish(session)
        if session.rows == [9]:
            r.events[9] = 900

    refresher.publish_market_changes = admit_bridge
    flush = asyncio.create_task(r.flush())
    try:
        await wait_committed(r, [1, 2, 3, 4, 9])
        assert calls["started"] == [(100,)]
    finally:
        gate.set()
        assert await asyncio.wait_for(flush, 2) is True
    assert calls["finished"] == [(100,), (200, 300, 900)]
    assert ("receipt", (3, 4, 9)) in r.trace
