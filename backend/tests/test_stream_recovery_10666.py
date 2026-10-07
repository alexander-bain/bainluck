"""Catch up a final lost quote only after restored Redis subscriptions exist."""

import asyncio
import contextlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
from unittest.mock import AsyncMock

import pytest

from app.routes import event_stream as route
from app.tasks import redis_state
from app.utils import live_fanout as fanout
from app.utils.live_push import event_channel


@pytest.mark.asyncio
async def test_rebuild_waits_for_every_ack_then_announces_once():
    hub = fanout.LiveFanout()
    subs = [fanout.Subscription(event_channel(i)) for i in (1, 2)]
    hub._subscribers = {s.channel: {s} for s in subs}
    pubsub = AsyncMock()
    hub._pubsub = pubsub
    hub._connect_locked = AsyncMock()
    # old is already retired; active handle still must restore all channels.
    assert await hub._rebuild(object()) is pubsub
    assert all(s._queue.empty() for s in subs)
    hub._confirm_recovery({"channel": event_channel(1).encode()})
    assert all(s._queue.empty() for s in subs)
    hub._confirm_recovery({"channel": event_channel(999)})
    assert all(s._queue.empty() for s in subs)
    hub._confirm_recovery({"channel": event_channel(2)})
    for s in subs:
        assert await s.next(0.01) == fanout.Recovery(1)
    hub._confirm_recovery({"channel": event_channel(2)})
    assert all(s._queue.empty() for s in subs)
    assert await hub._rebuild(object()) is pubsub
    hub._confirm_recovery({"channel": event_channel(2)})
    hub._confirm_recovery({"channel": event_channel(1)})
    for s in subs:
        assert await s.next(0.01) == fanout.Recovery(2)


@pytest.mark.asyncio
async def test_failed_rebuild_never_announces_recovery():
    hub = fanout.LiveFanout()
    sub = fanout.Subscription(event_channel(1))
    hub._subscribers = {sub.channel: {sub}}
    hub._connect_locked = AsyncMock(side_effect=ConnectionError("no redis"))
    hub._release_connection_locked = AsyncMock()
    assert await hub._rebuild(object()) is None
    assert not hub._recovery_pending
    assert sub._queue.empty()


@pytest.mark.asyncio
async def test_released_subscriber_is_not_notified_and_mailbox_is_bounded():
    hub = fanout.LiveFanout()
    old, active = [fanout.Subscription(event_channel(1)) for _ in range(2)]
    hub._subscribers = {active.channel: {old, active}}
    hub._recovery_pending = {active.channel}
    hub.release(old)
    for i in range(fanout.QUEUE_MAX):
        active.offer(str(i))
    hub._confirm_recovery({"channel": active.channel})
    assert old._queue.empty()
    assert active._queue.qsize() == fanout.QUEUE_MAX
    assert active.dropped == 1
    while active._queue.qsize() > 1:
        await active.next(0.01)
    assert await active.next(0.01) == fanout.Recovery(1)


class Request:
    async def is_disconnected(self):
        return False


@pytest.mark.asyncio
async def test_folded_stream_deduplicates_generation_and_preserves_quote(monkeypatch):
    class Hub:
        def __init__(self):
            self.subs = {}

        async def subscribe(self, channel):
            sub = fanout.Subscription(channel)
            self.subs[channel] = sub
            return sub

        def release(self, sub):
            self.subs.pop(sub.channel, None)

    hub = Hub()
    monkeypatch.setattr(fanout, "fanout", lambda: hub)
    stream = route._stream(1, Request(), contributor_ids=[1, 2])
    try:
        await anext(stream)
        await anext(stream)
        for sub in hub.subs.values():
            sub.offer(fanout.Recovery(1))
        assert "event: resync" in await asyncio.wait_for(anext(stream), 1)
        frame = {
            "event_id": 1,
            "p": 0.52,
            "source": "kalshi",
            "status": "live",
            "rev": {"1": 12},
        }
        hub.subs[event_channel(1)].offer(json.dumps(frame))
        chunk = await asyncio.wait_for(anext(stream), 1)
        assert "event: probability" in chunk
        assert json.loads(chunk.split("data: ")[1]) == frame
        hub.subs[event_channel(1)].offer(fanout.Recovery(2))
        assert '"generation": 2' in await asyncio.wait_for(anext(stream), 1)
    finally:
        await stream.aclose()
    assert not hub.subs


@pytest.fixture
def private_redis():
    binary = os.environ.get("STREAM_RECOVERY_REDIS_SERVER") or shutil.which(
        "redis-server"
    )
    if not binary:
        pytest.skip("private Redis binary not configured")
    with tempfile.TemporaryDirectory(prefix="stream-recovery-10666-") as tmp:
        sock = Path(tmp) / "r.sock"
        process = subprocess.Popen(
            [
                binary,
                "--port",
                "0",
                "--unixsocket",
                str(sock),
                "--save",
                "",
                "--appendonly",
                "no",
            ],
            stdout=subprocess.DEVNULL,
        )
        try:
            deadline = time.monotonic() + 3
            while not sock.exists():
                assert process.poll() is None and time.monotonic() < deadline
                time.sleep(0.01)
            yield str(sock)
        finally:
            process.terminate()
            process.wait(timeout=3)


@pytest.mark.asyncio
@pytest.mark.parametrize("protocol", [2, 3])
async def test_real_last_quote_gap_announces_recovery_without_another_quote(
    monkeypatch, private_redis, protocol
):
    from redis.asyncio import Redis

    def client():
        return Redis(
            unix_socket_path=private_redis,
            max_connections=1,
            decode_responses=True,
            protocol=protocol,
        )

    monkeypatch.setattr(redis_state, "get_async_redis_client", client)
    monkeypatch.setattr(fanout, "READ_TIMEOUT_S", 0.01)
    monkeypatch.setattr(route, "FRAME_WAIT_S", 0.02)
    entered, resume = asyncio.Event(), asyncio.Event()

    class Hub(fanout.LiveFanout):
        pause = False

        async def _release_connection_locked(self):
            await super()._release_connection_locked()
            if self.pause:
                self.pause = False
                entered.set()
                await resume.wait()

    hub = Hub()
    monkeypatch.setattr(fanout, "fanout", lambda: hub)
    chunks = []

    async def read():
        async for chunk in route._stream(1, Request()):
            chunks.append(chunk)

    async def until(predicate):
        async with asyncio.timeout(3):
            while not predicate():
                await asyncio.sleep(0.005)

    task = asyncio.create_task(read())
    writer = client()
    try:
        await until(lambda: any("event: open" in c for c in chunks))
        # Server receipt confirms subscription, rather than sleeping a guess.
        async with asyncio.timeout(3):
            while (await writer.pubsub_numsub(event_channel(1)))[0][1] != 1:
                await asyncio.sleep(0.005)
        first = {"event_id": 1, "p": 0.4, "status": "scheduled", "rev": {"1": 11}}
        await writer.publish(event_channel(1), json.dumps(first))
        await until(lambda: any("event: probability" in c for c in chunks))
        assert not any("event: resync" in c for c in chunks)
        original = hub._pubsub.get_message
        fail = True

        async def read_message(*args, **kwargs):
            nonlocal fail
            if fail:
                fail = False
                raise ConnectionError("controlled last-quote gap")
            return await original(*args, **kwargs)

        hub.pause = True
        hub._pubsub.get_message = read_message
        await asyncio.wait_for(entered.wait(), 3)
        assert (
            await writer.publish(
                event_channel(1), json.dumps({**first, "p": 0.52, "rev": {"1": 12}})
            )
            == 0
        )
        resume.set()
        await until(lambda: any("event: resync" in c for c in chunks))
        assert (await writer.pubsub_numsub(event_channel(1)))[0][1] == 1
        await asyncio.sleep(0.06)
        assert sum("event: resync" in c for c in chunks) == 1
        assert sum("event: probability" in c for c in chunks) == 1
        assert not any("event: reconnect" in c for c in chunks)
        assert hub.subscriber_count == 1 and not task.done()
    finally:
        resume.set()
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        await hub.aclose()
        await writer.aclose()
    assert hub.subscriber_count == 0 and hub.redis_connections == 0


@pytest.mark.asyncio
async def test_discarded_connection_clears_unfinished_recovery():
    hub = fanout.LiveFanout()
    hub._recovery_pending = {event_channel(1)}
    await hub._release_connection_locked()
    assert not hub._recovery_pending
    sub = fanout.Subscription(event_channel(1))
    hub._subscribers = {sub.channel: {sub}}
    hub._confirm_recovery({"channel": sub.channel})
    assert sub._queue.empty()
