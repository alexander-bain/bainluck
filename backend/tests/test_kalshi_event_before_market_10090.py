"""A committed event refresh must not wait for its MARKET invalidation ACK."""
import asyncio

import pytest

from tests.test_kalshi_coalesced_stamps_10090 import three_games
from tests.test_kalshi_pipelined_stamps_10090 import held_refresher

pytestmark = pytest.mark.asyncio


async def test_event_refresh_finishes_while_market_publication_is_held():
    r = three_games()
    gate, calls = held_refresher(r)
    gate.set()
    entered, release = asyncio.Event(), asyncio.Event()
    refresher = r.ns["blend_refresher"]
    original = refresher.publish_market_changes

    async def hold_market(session):
        await original(session)
        if session.rows == [1, 2]:
            entered.set()
            await release.wait()

    refresher.publish_market_changes = hold_market
    flush = asyncio.create_task(r.flush())
    try:
        await asyncio.wait_for(entered.wait(), 2)
        for _ in range(20):
            await asyncio.sleep(0)
        assert calls["finished"] == [(100,)]
        assert r.committed == [1, 2]
        assert not flush.done()
    finally:
        release.set()
        assert await asyncio.wait_for(flush, 2) is True
    assert sum(100 in ids for ids in calls["started"]) == 1
    assert calls["most_running"] == 1
    assert not r.batch
    assert len([x for x in r.trace if x[0] == "publish"]) == 4


async def test_cancel_during_market_joins_started_event_refresh():
    r = three_games()
    _, calls = held_refresher(r)
    entered = asyncio.Event()
    refresher = r.ns["blend_refresher"]
    original = refresher.publish_market_changes

    async def hold_market(session):
        await original(session)
        entered.set()
        await asyncio.Event().wait()

    refresher.publish_market_changes = hold_market
    flush = asyncio.create_task(r.flush())
    await asyncio.wait_for(entered.wait(), 2)
    assert calls["started"] == [(100,)]
    flush.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(flush, 2)
    assert calls["running"] == 0
    assert calls["cancelled"] == [(100,)]
    assert set().union(*calls["adopted"]) == {100}
    assert set(r.batch) == {1, 2, 3, 4, 9}


async def test_late_bridge_stages_only_its_new_event_receipts():
    r = three_games()
    r.events.pop(2)
    gate, calls = held_refresher(r)
    gate.set()
    refresher = r.ns["blend_refresher"]
    original = refresher.publish_market_changes

    async def admit_bridge(session):
        await original(session)
        if session.rows == [1, 2]:
            r.events[2] = 900

    refresher.publish_market_changes = admit_bridge
    assert await asyncio.wait_for(r.flush(), 2) is True
    stages = [entry[1] for entry in r.trace if entry[0] == "receipt"]
    assert stages[0] == (1, 2)
    assert stages[1] == (2,)
    assert sum(100 in ids for ids in calls["started"]) == 1
    assert any(900 in ids for ids in calls["finished"])
