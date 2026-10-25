"""A newly opened stream catches the latest quote even when no later quote comes.

#10090. ``_stream`` subscribes, emits ``open`` and reads the retained latest
frame at once. ``PubSub.subscribe`` returns once SUBSCRIBE is written to the
hub's socket, not once Redis has registered it, and the replay MGET travels on
a different connection. When the SUBSCRIBE segment reaches Redis late (a
retransmit on one flow is enough), a quote published in between is in neither
place: the MGET ran before it was retained and the channel was not yet
subscribed when it was published. With a quiet market nothing repairs it, and
the route's own heartbeats keep the page looking live.

The rig is the real route, the real hub and a private real Redis. The hub's
connection runs through a byte-level proxy that can hold ONE direction for the
named channel's SUBSCRIBE:

* ``up``   holds the command before Redis sees it — the delivery delay that can
           lose a publish (the race);
* ``down`` holds only Redis' ACK after Redis registered the channel — the null
           control: Redis already delivers, so nothing can be lost.
"""
import asyncio
import contextlib
import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from redis.asyncio import Redis

from app.routes import event_stream as route
from app.tasks import redis_state
from app.utils import live_fanout, live_push, request_cache
from tests import test_event_frame_batching_10659 as publication_tests
from tests._event_stream_legacy_view import install_legacy_view


@pytest.fixture(autouse=True)
def _legacy_wire_view(monkeypatch):
    """#10090: these tests predate the stream's owned coverage read and its
    reconcile controls; see tests/_event_stream_legacy_view.py."""
    install_legacy_view(monkeypatch)


private_redis_socket = publication_tests.private_redis_socket


class Request:
    async def is_disconnected(self):
        return False


class SubscribeGate:
    """Unix-socket proxy that holds one direction of one channel's SUBSCRIBE."""

    def __init__(self, upstream: Path, path: Path):
        self.upstream, self.path = str(upstream), str(path)
        self.direction = None
        self.channel = b""
        self.held = asyncio.Event()
        self.release = asyncio.Event()
        self.server = None
        self.pumps = set()

    def arm(self, direction: str, channel: str):
        self.direction, self.channel = direction, channel.encode() + b"\r\n"
        self.held.clear()
        self.release.clear()

    async def __aenter__(self):
        self.server = await asyncio.start_unix_server(self._accept, path=self.path)
        return self

    async def __aexit__(self, *exc):
        self.release.set()
        self.server.close()
        for pump in self.pumps:
            pump.cancel()
        await asyncio.gather(*self.pumps, return_exceptions=True)

    async def _accept(self, client_r, client_w):
        server_r, server_w = await asyncio.open_unix_connection(self.upstream)
        for args in ((client_r, server_w, "up", b"SUBSCRIBE"),
                     (server_r, client_w, "down", b"subscribe")):
            pump = asyncio.create_task(self._pump(*args))
            self.pumps.add(pump)

    async def _pump(self, reader, writer, direction, verb):
        try:
            while chunk := await reader.read(65536):
                if (self.direction == direction and not self.held.is_set()
                        and verb in chunk and self.channel in chunk):
                    self.held.set()
                    await self.release.wait()
                writer.write(chunk)
                await writer.drain()
        except (ConnectionError, asyncio.CancelledError):
            pass
        finally:
            writer.close()


def quote(event_id, rev, p):
    return live_push.build_frame(
        event_id=event_id, probability=p, source="kalshi", source_value=p,
        updated_at=datetime.now(timezone.utc).isoformat(), status="live", rev=rev,
    )


async def until(predicate, timeout=3):
    async with asyncio.timeout(timeout):
        while not predicate():
            await asyncio.sleep(0.005)


def probabilities(chunks):
    return [json.loads(c.split("data: ", 1)[1]) for c in chunks
            if c.startswith("event: probability")]


@pytest.fixture
async def rig(private_redis_socket, monkeypatch, tmp_path):
    gate_path = Path(private_redis_socket).parent / "gate.sock"
    async with SubscribeGate(private_redis_socket, gate_path) as gate:
        direct = Redis(unix_socket_path=str(private_redis_socket))
        monkeypatch.setattr(redis_state, "get_async_redis_client",
                            lambda: Redis(unix_socket_path=str(gate_path)))
        monkeypatch.setattr(request_cache, "get_shared_async_redis",
                            AsyncMock(return_value=direct))
        monkeypatch.setattr(live_fanout, "READ_TIMEOUT_S", 0.01)
        monkeypatch.setattr(route, "FRAME_WAIT_S", 0.02)
        monkeypatch.setattr(route, "HEARTBEAT_INTERVAL_S", 0.05)
        hub = live_fanout.LiveFanout()
        monkeypatch.setattr(live_fanout, "fanout", lambda: hub)
        replayed = {}
        real_latest = route.latest_frames

        async def spy(ids):
            result = await real_latest(ids)
            replayed.setdefault(ids[0], asyncio.Event()).set()
            return result

        monkeypatch.setattr(route, "latest_frames", spy)
        tasks = []

        def open_stream(event_id):
            chunks = []
            replayed.setdefault(event_id, asyncio.Event())

            async def read():
                async for chunk in route._stream(event_id, Request()):
                    chunks.append(chunk)

            tasks.append(asyncio.create_task(read()))
            return chunks

        try:
            yield gate, direct, hub, open_stream, replayed
        finally:
            gate.release.set()
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            await hub.aclose()
            await direct.aclose()
        assert hub.subscriber_count == 0 and hub.redis_connections == 0


async def numsub(redis, event_id):
    return (await redis.pubsub_numsub(live_push.event_channel(event_id)))[0][1]


async def publish(redis, frame):
    return await redis.execute_command(*live_push.frame_publish_command(frame))


async def race(rig, direction, event_id, warm_hub):
    gate, direct, hub, open_stream, replayed = rig
    if warm_hub:
        # Another page already holds the shared connection open.
        other = open_stream(7)
        await until(lambda: any("event: open" in c for c in other))
        await until(lambda: hub._reader is not None)
        async with asyncio.timeout(3):
            while await numsub(direct, 7) != 1:
                await asyncio.sleep(0.005)
    # The page already rendered rev 40 before it opened.
    assert await publish(direct, quote(event_id, 40, 0.30)) == 0
    gate.arm(direction, live_push.event_channel(event_id))
    chunks = open_stream(event_id)
    await asyncio.wait_for(gate.held.wait(), 3)
    await asyncio.wait_for(replayed[event_id].wait(), 3)
    # The open-time replay ran and caught rev 40, not rev 41.
    assert [f["rev"] for f in probabilities(chunks)] in ([], [{str(event_id): 40}])
    receivers = await publish(direct, quote(event_id, 41, 0.62))
    gate.release.set()
    async with asyncio.timeout(3):
        while await numsub(direct, event_id) != 1:
            await asyncio.sleep(0.005)
    # The market stays quiet: no further quote is ever published.
    await asyncio.sleep(0.4)
    return receivers, chunks


@pytest.mark.asyncio
@pytest.mark.parametrize("warm_hub", [False, True], ids=["first_reader", "running_hub"])
async def test_a_late_subscribe_still_delivers_the_quote_published_meanwhile(rig, warm_hub):
    receivers, chunks = await race(rig, "up", 42, warm_hub)
    # Redis really had no subscriber when the quote was published.
    assert receivers == 0
    assert sum(c.startswith("event: heartbeat") for c in chunks) >= 2
    revs = [f["rev"] for f in probabilities(chunks)]
    assert revs[-1:] == [{"42": 41}], revs
    assert probabilities(chunks)[-1]["p"] == 0.62
    assert revs.count({"42": 41}) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("warm_hub", [False, True], ids=["first_reader", "running_hub"])
async def test_a_late_ack_alone_cannot_lose_the_quote(rig, warm_hub):
    receivers, chunks = await race(rig, "down", 42, warm_hub)
    # Redis had already registered the channel, so it delivered the quote.
    assert receivers == 1
    revs = [f["rev"] for f in probabilities(chunks)]
    assert revs[-1:] == [{"42": 41}], revs
    assert revs.count({"42": 41}) == 1


@pytest.mark.asyncio
async def test_a_second_page_joining_before_redis_registers_the_channel_also_catches_up(rig):
    gate, direct, hub, open_stream, replayed = rig
    assert await publish(direct, quote(42, 40, 0.30)) == 0
    gate.arm("up", live_push.event_channel(42))
    first = open_stream(42)
    await asyncio.wait_for(gate.held.wait(), 3)
    await asyncio.wait_for(replayed[42].wait(), 3)
    # The second page sends no SUBSCRIBE of its own: the channel is joined.
    replayed[42].clear()
    second = open_stream(42)
    await asyncio.wait_for(replayed[42].wait(), 3)
    assert hub.subscriber_count == 2
    assert await publish(direct, quote(42, 41, 0.62)) == 0
    gate.release.set()
    async with asyncio.timeout(3):
        while await numsub(direct, 42) != 1:
            await asyncio.sleep(0.005)
    await asyncio.sleep(0.3)
    for chunks in (first, second):
        assert [f["rev"] for f in probabilities(chunks)] == [{"42": 40}, {"42": 41}]


@pytest.mark.asyncio
async def test_an_ordinary_open_sends_the_retained_quote_once(rig):
    gate, direct, hub, open_stream, replayed = rig
    assert await publish(direct, quote(42, 40, 0.30)) == 0
    chunks = open_stream(42)
    async with asyncio.timeout(3):
        while await numsub(direct, 42) != 1:
            await asyncio.sleep(0.005)
    await until(lambda: not hub._awaiting_ack)
    await asyncio.sleep(0.2)
    # Confirmation's catch-up read found only what the open already sent.
    assert [f["rev"] for f in probabilities(chunks)] == [{"42": 40}]
    assert await publish(direct, quote(42, 41, 0.62)) == 1
    await until(lambda: len(probabilities(chunks)) == 2)
    assert probabilities(chunks)[-1]["rev"] == {"42": 41}


def test_confirmation_counts_every_owed_reply_and_skips_served_channels():
    hub = live_fanout.LiveFanout()
    channel = live_push.event_channel(42)
    waiting, served, left = (live_fanout.Subscription(channel) for _ in range(3))
    hub._subscribers = {channel: {waiting, left}}
    # A re-join while the earlier SUBSCRIBE is still in flight owes two replies.
    hub._owe_ack(channel)
    hub._owe_ack(channel)
    hub.watch_confirmation(waiting)
    hub.watch_confirmation(left)
    hub.release(left)
    hub._confirm_subscription({"type": "subscribe", "channel": channel.encode()})
    assert waiting._queue.empty()
    hub._confirm_subscription({"type": "subscribe", "channel": channel})
    assert waiting._queue.get_nowait() is live_fanout.CONFIRMED
    assert left._queue.empty() and not hub._awaiting_ack
    # Redis already serves the channel: nothing is owed, nothing is offered.
    hub._subscribers[channel].add(served)
    hub.watch_confirmation(served)
    hub._confirm_subscription({"type": "subscribe", "channel": channel})
    assert served._queue.empty() and waiting._queue.empty()


@pytest.mark.asyncio
async def test_a_discarded_connection_owes_no_reply():
    hub = live_fanout.LiveFanout()
    hub._owe_ack(live_push.event_channel(42))
    await hub._release_connection_locked()
    assert not hub._awaiting_ack


@pytest.mark.asyncio
async def test_a_folded_contributor_confirmation_reads_only_that_contributor(monkeypatch):
    from tests.test_folded_event_stream_invalidation_837 import Hub

    hub = Hub()
    hub.watch_confirmation = lambda sub: None
    monkeypatch.setattr(live_fanout, "fanout", lambda: hub)
    own, sibling, newer = quote(42, 7, 0.4), quote(43, 7, 0.5), quote(43, 8, 0.55)
    reads = []

    async def latest(ids):
        reads.append(list(ids))
        if len(reads) == 1:
            hub.subscriptions[live_push.event_channel(43)].offer(live_fanout.CONFIRMED)
            hub.subscriptions[live_push.event_channel(42)].offer(live_fanout.CONFIRMED)
            return [(42, json.dumps(own)), (43, json.dumps(sibling))]
        return [(43, json.dumps(newer))] if ids == [43] else [(42, json.dumps(own))]

    monkeypatch.setattr(route, "latest_frames", latest)
    stream = route._stream(42, Request(), [42, 43])
    try:
        sent = []
        while len(sent) < 3:
            chunk = await asyncio.wait_for(anext(stream), 1)
            if chunk.startswith("event: probability"):
                sent.append(json.loads(chunk.split("data: ", 1)[1]))
        assert sent[0] == own
        assert sent[1]["invalidation"] and sent[1]["rev"] == {"43": 7}
        assert sent[2]["invalidation"] and sent[2]["rev"] == {"43": 8}
        with pytest.raises(asyncio.TimeoutError):
            while True:
                chunk = await asyncio.wait_for(anext(stream), 0.2)
                assert not chunk.startswith("event: probability"), chunk
    finally:
        await stream.aclose()
    assert sorted(reads[1:]) == [[42], [43]]


@pytest.mark.asyncio
async def test_a_replayed_quote_also_arriving_live_is_sent_once(monkeypatch):
    from tests.test_folded_event_stream_invalidation_837 import Hub

    hub = Hub()
    monkeypatch.setattr(live_fanout, "fanout", lambda: hub)
    retained, newer = quote(42, 41, 0.62), quote(42, 42, 0.64)

    async def latest(ids):
        channel = hub.subscriptions[live_push.event_channel(42)]
        for live in (retained, retained, newer):
            channel.offer(json.dumps(live))
        return [(42, json.dumps(retained))]

    monkeypatch.setattr(route, "latest_frames", latest)
    stream = route._stream(42, Request())
    try:
        sent = []
        while len(sent) < 3:
            try:
                chunk = await asyncio.wait_for(anext(stream), 0.3)
            except asyncio.TimeoutError:
                break
            if chunk.startswith("event: probability"):
                sent.append(json.loads(chunk.split("data: ", 1)[1]))
    finally:
        await stream.aclose()
    # Only the first live copy is the in-flight twin of the replay; a later
    # repeat is the publisher's, and is passed through as before.
    assert [f["rev"] for f in sent] == [{"42": 41}, {"42": 41}, {"42": 42}]


# --- the same race with no Redis binary: a scripted protocol peer -------------
# The private-Redis arms above skip where no ``redis-server`` is installed (CI).
# This arm runs everywhere. It drives the real route and the real hub — the
# hub's own ``_read_loop`` consumes the ACK and ``_FoldSubscription.subscribe``
# arms the watch — over a scripted peer that keeps Redis' one relevant rule:
# a channel delivers only once Redis has READ its SUBSCRIBE, and the ACK is
# queued on the hub's connection at that moment. The test decides when Redis
# reads it (``up``), or lets Redis read it at once and holds only the ACK
# (``down``, the null control).
from tests.test_event_stream_lost_cancel_10090 import (  # noqa: E402
    _Reader, _ScriptedClient, _ScriptedPubSub,
)


class _ScriptedRedis(_ScriptedPubSub):
    """One hub connection plus the shared store, ordered as Redis orders them."""

    def __init__(self):
        super().__init__()
        self.registered: set[str] = set()
        self.retained: dict[str, str] = {}
        self.unread: list[str] = []
        self.held_ack: list[str] = []
        self.hold: dict[str, str] = {}
        self.mgets: list[list[str]] = []

    async def subscribe(self, channel):
        await super().subscribe(channel)
        self.unread.append(channel)
        if self.hold.get(channel) != "up":
            self.redis_reads_subscribe(channel)

    def redis_reads_subscribe(self, channel):
        self.unread.remove(channel)
        self.registered.add(channel)
        if self.hold.get(channel) == "down":
            self.held_ack.append(channel)
        else:
            self.ack(channel)

    def ack(self, channel):
        self._queue.put_nowait({"type": "subscribe", "channel": channel.encode(),
                                "data": len(self.registered)})

    async def unsubscribe(self, channel):
        await super().unsubscribe(channel)
        self.registered.discard(channel)

    def publish(self, frame) -> int:
        """RETAIN_AND_PUBLISH: keep a newer revision, deliver to registered."""
        key, channel = live_push.latest_frame_key(frame["event_id"]), live_push.event_channel(frame["event_id"])
        prior = json.loads(self.retained[key]) if key in self.retained else None
        rev = frame["rev"][str(frame["event_id"])]
        if prior is None or prior["rev"][str(frame["event_id"])] < rev:
            self.retained[key] = json.dumps(frame)
        if channel not in self.registered:
            return 0
        self.deliver(channel.encode(), json.dumps(frame).encode())
        return 1

    async def mget(self, keys):
        self.mgets.append(list(keys))
        return [self.retained.get(key) for key in keys]


@pytest.fixture
async def scripted(monkeypatch):
    redis = _ScriptedRedis()
    monkeypatch.setattr(redis_state, "get_async_redis_client",
                        lambda: _ScriptedClient(redis))
    monkeypatch.setattr(request_cache, "get_shared_async_redis",
                        AsyncMock(return_value=redis))
    monkeypatch.setattr(live_fanout, "READ_TIMEOUT_S", 0.01)
    monkeypatch.setattr(route, "FRAME_WAIT_S", 0.02)
    monkeypatch.setattr(route, "HEARTBEAT_INTERVAL_S", 0.05)
    await live_fanout.reset_fanout()
    readers = []
    try:
        yield redis, readers
    finally:
        for reader in readers:
            await reader.stop()
        hub = live_fanout.fanout()
        await live_fanout.reset_fanout()
    assert hub.subscriber_count == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("warm_hub", [False, True], ids=["first_reader", "running_hub"])
@pytest.mark.parametrize("direction", ["up", "down"], ids=["late_subscribe", "late_ack_control"])
async def test_scripted_redis_the_sole_quote_published_before_redis_reads_subscribe_arrives(
    scripted, direction, warm_hub
):
    redis, readers = scripted
    if warm_hub:
        # Another page already holds the shared connection open...
        readers.append(_Reader(7))
        await readers[-1].opened()
        # ...and the hub's reader has already taken channel 7's ACK.
        await until(lambda: live_fanout.fanout()._reader is not None
                    and redis._queue.empty())
    channel = live_push.event_channel(42)
    # The page already rendered rev 40 before it opened.
    assert redis.publish(quote(42, 40, 0.30)) == 0
    redis.hold[channel] = direction
    reader = _Reader(42)
    readers.append(reader)
    await until(lambda: [live_push.latest_frame_key(42)] in redis.mgets)
    assert channel in redis.subscribed
    # The open-time replay ran and caught rev 40, not rev 41.
    assert [f["rev"] for f in probabilities(reader.chunks)] in ([], [{"42": 40}])
    receivers = redis.publish(quote(42, 41, 0.62))
    if direction == "up":
        assert receivers == 0  # Redis has not read SUBSCRIBE: nobody receives it
        redis.redis_reads_subscribe(channel)
    else:
        assert receivers == 1  # Redis already serves the channel
        redis.ack(redis.held_ack.pop())
    # The market stays quiet: no further quote is ever published.
    await asyncio.sleep(0.3)
    assert len(reader.events("heartbeat")) >= 2
    sent = probabilities(reader.chunks)
    revs = [f["rev"] for f in sent]
    assert revs[-1:] == [{"42": 41}], revs
    assert sent[-1]["p"] == 0.62
    assert revs.count({"42": 41}) == 1
    # The hub's own reader consumed the ACK.
    assert not live_fanout.fanout()._awaiting_ack
