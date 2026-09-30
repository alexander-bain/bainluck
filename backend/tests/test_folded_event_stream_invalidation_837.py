"""A venue-only twin must wake the canonical page without supplying its raw price."""
import asyncio
import json
from datetime import datetime, timezone

import pytest

from app.routes import event_stream as route
from app.utils import live_fanout


class Request:
    async def is_disconnected(self):
        return False


class Hub:
    def __init__(self):
        self.subscriptions = {}
        self.released = []

    async def subscribe(self, channel):
        sub = live_fanout.Subscription(channel)
        self.subscriptions[channel] = sub
        return sub

    def release(self, sub):
        self.released.append(sub.channel)


@pytest.mark.asyncio
async def test_twin_price_wakes_canonical_without_relabeling_raw_price(monkeypatch):
    hub = Hub()
    monkeypatch.setattr(live_fanout, "fanout", lambda: hub)
    stream = route._stream(15316464, Request(), contributor_ids=[15316464, 15312629])
    try:
        await anext(stream)  # retry
        await anext(stream)  # open
        frame = {"event_id": 15312629, "p": 0.06, "source": "polymarket",
                 "source_value": 0.065, "rev": {"15312629": 1098},
                 "updated_at": datetime.now(timezone.utc).isoformat(), "status": "live"}
        hub.subscriptions["live:event:15312629"].offer(json.dumps(frame))
        chunk = await asyncio.wait_for(anext(stream), timeout=1)
        payload = json.loads(chunk.split("data: ")[1].strip())
        assert payload["event_id"] == 15316464
        assert payload["origin_event_id"] == 15312629
        assert payload["invalidation"] is True
        assert payload["rev"] == {"15312629": 1098}
        assert payload["p"] is payload["source"] is payload["source_value"] is None
    finally:
        await stream.aclose()
    assert set(hub.released) == {"live:event:15316464", "live:event:15312629"}


def frame(event_id=2, **overrides):
    return {"event_id": event_id, "p": 0.85, "source": "kalshi",
            "source_value": 0.85, "rev": {str(event_id): 12},
            "updated_at": datetime.now(timezone.utc).isoformat(), "status": "live",
            **overrides}


@pytest.mark.asyncio
async def test_own_frame_is_unchanged_and_twin_terminal_does_not_close(monkeypatch):
    hub = Hub()
    monkeypatch.setattr(live_fanout, "fanout", lambda: hub)
    stream = route._stream(1, Request(), [1, 2, 2])
    try:
        await anext(stream)
        await anext(stream)
        hub.subscriptions["live:event:2"].offer(json.dumps(frame(status="completed")))
        sibling = await asyncio.wait_for(anext(stream), 1)
        assert '"status"' not in sibling and 'event: closed' not in sibling
        own = frame(1, status="completed")
        hub.subscriptions["live:event:1"].offer(json.dumps(own))
        chunk = await asyncio.wait_for(anext(stream), 1)
        assert json.loads(chunk.split('data: ')[1]) == own
        assert 'event: closed' in await anext(stream)
    finally:
        await stream.aclose()
    assert len(hub.released) == 2


@pytest.mark.asyncio
async def test_unrelated_malformed_and_old_frames_cannot_wake_or_supply_price(monkeypatch):
    hub = Hub()
    monkeypatch.setattr(live_fanout, "fanout", lambda: hub)
    stream = route._stream(1, Request(), [1, 2])
    try:
        await anext(stream)
        await anext(stream)
        sub = hub.subscriptions["live:event:2"]
        for bad in [frame(999), frame(rev={"1": 50}), frame(rev={"2": True}),
                    frame(updated_at="2000-01-01T00:00:00+00:00")]:
            sub.offer(json.dumps(bad))
        sub.offer(json.dumps(frame(rev={"2": 13}, source_value=None, p=None)))
        chunk = await asyncio.wait_for(anext(stream), 1)
        payload = json.loads(chunk.split('data: ')[1])
        assert payload['rev'] == {"2": 13}
        assert payload['p'] is payload['source_value'] is None
    finally:
        await stream.aclose()


@pytest.mark.asyncio
async def test_cancel_releases_every_channel_and_pending_read(monkeypatch):
    hub = Hub()
    monkeypatch.setattr(live_fanout, "fanout", lambda: hub)
    stream = route._stream(1, Request(), [1, 2])
    await anext(stream)
    await anext(stream)
    task = asyncio.create_task(anext(stream))
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert set(hub.released) == {"live:event:1", "live:event:2"}


@pytest.mark.asyncio
async def test_closed_contributor_requests_reconnect(monkeypatch):
    hub = Hub()
    monkeypatch.setattr(live_fanout, "fanout", lambda: hub)
    stream = route._stream(1, Request(), [1, 2])
    try:
        await anext(stream)
        await anext(stream)
        hub.subscriptions["live:event:2"].offer(live_fanout.CLOSED)
        assert 'event: reconnect' in await asyncio.wait_for(anext(stream), 1)
    finally:
        await stream.aclose()
    assert len(hub.released) == 2


@pytest.mark.asyncio
async def test_connect_discovery_uses_existing_orientation_safe_fold(monkeypatch):
    from unittest.mock import AsyncMock, MagicMock
    from types import SimpleNamespace
    from app.utils import proven_duplicates, serve_fold_absorbed
    event = SimpleNamespace(id=1)
    absorbed = [SimpleNamespace(id=3)]
    db = SimpleNamespace(execute=AsyncMock(return_value=MagicMock()))
    db.execute.return_value.scalar_one_or_none.return_value = event
    find_absorbed = AsyncMock(return_value=absorbed)
    fold_ids = AsyncMock(return_value=[1, 2, 3])
    monkeypatch.setattr(serve_fold_absorbed, 'serve_fold_absorbed_rows', find_absorbed)
    monkeypatch.setattr(proven_duplicates, 'folded_series_event_ids', fold_ids)
    assert await route._fold_stream_ids(db, 1) == [1, 2, 3]
    find_absorbed.assert_awaited_once_with(db, event)
    fold_ids.assert_awaited_once_with(db, 1, absorbed)


@pytest.mark.asyncio
async def test_partial_subscribe_failure_releases_already_opened_channel(monkeypatch):
    class FailingHub(Hub):
        async def subscribe(self, channel):
            if channel == 'live:event:2':
                raise ConnectionError('bounded test failure')
            return await super().subscribe(channel)

    hub = FailingHub()
    monkeypatch.setattr(live_fanout, 'fanout', lambda: hub)
    before = route._open_connections
    stream = route._stream(1, Request(), [1, 2])
    with pytest.raises(StopAsyncIteration):
        await anext(stream)
    assert hub.released == ['live:event:1']
    assert route._open_connections == before
