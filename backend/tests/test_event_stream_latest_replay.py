"""Opening after a publication catches up without waiting for the next trade."""
import asyncio
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from redis.asyncio import Redis

from app.routes import event_stream as route
from app.utils import live_push, live_fanout, request_cache
from tests import test_event_frame_batching_10659 as publication_tests

from tests.test_folded_event_stream_invalidation_837 import Hub, Request

private_redis_socket = publication_tests.private_redis_socket


def frame(event_id=42, rev=7, age=0):
    return live_push.build_frame(
        event_id=event_id, probability=0.61, source='kalshi', source_value=0.7,
        updated_at=(datetime.now(timezone.utc) - timedelta(seconds=age)).isoformat(),
        status='live', rev=rev,
    )


@pytest.mark.asyncio
async def test_only_fresh_identical_revisioned_frames_replay(monkeypatch):
    good = frame()
    missing_stamp = frame(45)
    del missing_stamp['updated_at']
    rows = [good, frame(43, age=31), frame(44, rev=None), missing_stamp,
            frame(999), frame(47, age=-60)]
    redis = AsyncMock()
    redis.mget.return_value = [json.dumps(f) for f in rows]
    monkeypatch.setattr(request_cache, 'get_shared_async_redis', AsyncMock(return_value=redis))
    result = await live_push.latest_frames([42,43,44,45,46,47,42])
    assert [(i,json.loads(raw)) for i,raw in result] == [(42,good)]
    assert len(redis.mget.call_args.args[0]) == 6


@pytest.mark.asyncio
async def test_replay_read_failure_does_not_end_stream(monkeypatch):
    redis = AsyncMock()
    redis.mget.side_effect = ConnectionError('gone')
    monkeypatch.setattr(request_cache, 'get_shared_async_redis', AsyncMock(return_value=redis))
    assert await live_push.latest_frames([42]) == []


@pytest.mark.asyncio
async def test_subscribe_then_replay_then_live_preserves_fold_invalidation(monkeypatch):
    hub = Hub()
    monkeypatch.setattr(live_fanout, 'fanout', lambda: hub)
    own, sibling, next_frame = frame(42), frame(43), frame(42, rev=8)
    async def snapshot(ids):
        assert set(hub.subscriptions) == {'live:event:42','live:event:43'}
        hub.subscriptions['live:event:42'].offer(json.dumps(next_frame))
        return [(42,json.dumps(own)), (43,json.dumps(sibling))]
    monkeypatch.setattr(route, 'latest_frames', snapshot)
    stream = route._stream(42, Request(), [42,43])
    try:
        assert 'retry:' in await anext(stream)
        assert 'event: open' in await anext(stream)
        first = json.loads((await asyncio.wait_for(anext(stream), 0.2)).split('data: ')[1])
        assert first == own
        second = json.loads((await anext(stream)).split('data: ')[1])
        assert second['invalidation'] is True and second['p'] is None
        assert second['rev'] == {'43':7}
        third = json.loads((await anext(stream)).split('data: ')[1])
        assert third == next_frame
    finally:
        await stream.aclose()
    assert len(hub.released) == 2


@pytest.mark.asyncio
async def test_real_redis_packed_and_generic_publish_retain_only_latest_revision(private_redis_socket, monkeypatch):
    redis = Redis(unix_socket_path=str(private_redis_socket))
    monkeypatch.setattr(request_cache, 'get_shared_async_redis', AsyncMock(return_value=redis))
    try:
        newer, older = frame(rev=12), frame(rev=11)
        r = publication_tests.refresher(redis)
        await r._publish([newer, older])
        assert r.stats['published'] == 2 and r.stats['publish_errors'] == 0
        result = await live_push.latest_frames([42])
        assert json.loads(result[0][1]) == newer
        assert 0 < await redis.ttl(live_push.latest_frame_key(42)) <= 30
        assert await live_push.publish_frame(redis, frame(rev=13))
        result = await live_push.latest_frames([42])
        assert json.loads(result[0][1])['rev'] == {'42':13}
        assert await live_push.publish_frame(redis, frame(rev=None))
        result = await live_push.latest_frames([42])
        assert json.loads(result[0][1])['rev'] == {'42':13}
    finally:
        await redis.aclose()
