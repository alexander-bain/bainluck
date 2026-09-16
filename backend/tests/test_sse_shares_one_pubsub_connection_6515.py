"""#6515 — N open SSE streams hold ONE Redis connection, not N.

THE SHIP, IN A READER'S WORDS: opening a live game page keeps its number moving
without taking the connection budget away from everything else on the site.

THE DEFECT. `routes/event_stream.py` called the deliberately-uncached
`get_async_redis_client()` inside `_stream`, so every open stream built its own
pool and its `PubSub` held a real socket for up to `MAX_CONNECTION_S` (900 s).
`SSE_MAX_CONNECTIONS` is 200 per uvicorn worker; the Heroku plan limit is 80 for
every process of BOTH apps. So at roughly 80 concurrent live-event readers
fleet-wide the server began refusing connections — and not only to SSE: the next
Redis connect from anywhere in that process (`utils/request_cache.py`, the rate
limiter, the feed cache) failed too, while the 503 capacity gate that exists to
refuse loudly sat 120 readers away from firing.

No per-pool cap can bound that, which is why #1197's envelope guard does not
already cover it: each stream's own pool sat at 1 of its cap and never queued.
The bound has to come from there being ONE pool.

WHY THESE TESTS ARE MOSTLY SOCKET TESTS. The claim is about connections at the
server, and only the server can count those. A fake pubsub can prove the hub's
bookkeeping and nothing about the budget — so the arms below drive the real
`_stream` through the real client against a toy Redis that counts what it
accepted, under both RESP protocols. The negative control is the arm that
matters most: `test_the_pre_hub_shape_opens_one_socket_per_stream` builds what
the route used to build and watches the same rig report 12 sockets, so a green
row here is never the rig being blind.
"""

from __future__ import annotations

import ast
import asyncio
import inspect
import json
import pathlib
import socket
import threading
from datetime import datetime, timezone

import pytest

from app.tasks import redis_state
from app.utils import live_fanout
from app.utils.live_push import build_frame, event_channel

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# A toy Redis that speaks just enough pub/sub, and counts its sockets.
# ---------------------------------------------------------------------------


class _TinyPubSubServer:
    """Answers HELLO/SUBSCRIBE/UNSUBSCRIBE, fans out, counts connections.

    It has to answer `HELLO` and it has to frame pub/sub replies as RESP3 PUSH
    types when the client asked for protocol 3 — redis-py's parsers are
    different code paths per protocol, and a server that only speaks RESP2
    passes locally and proves nothing wherever the library's default has moved.
    `redis>=5.0.1` is unpinned here, so both are exercised.
    """

    def __init__(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(128)
        self.port = self.sock.getsockname()[1]
        self.accepted = 0
        self.concurrent = 0
        self.peak_concurrent = 0
        self.subscriptions: dict[bytes, set] = {}
        self._protocol: dict = {}
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._acceptor = threading.Thread(target=self._accept_loop, daemon=True)
        self._acceptor.start()

    # -- the wire -----------------------------------------------------------

    def _accept_loop(self):
        while not self._stop.is_set():
            try:
                conn, _ = self.sock.accept()
            except OSError:
                return
            with self._lock:
                self.accepted += 1
                self.concurrent += 1
                self.peak_concurrent = max(self.peak_concurrent, self.concurrent)
                self._protocol[conn] = 2
            threading.Thread(target=self._serve, args=(conn,), daemon=True).start()

    def _serve(self, conn):
        buf = b""
        try:
            while not self._stop.is_set():
                chunk = conn.recv(4096)
                if not chunk:
                    return
                buf += chunk
                while True:
                    parsed = _parse_resp_command(buf)
                    if parsed is None:
                        break
                    consumed, args = parsed
                    buf = buf[consumed:]
                    for reply in self._replies_to(conn, args):
                        with self._lock:
                            conn.sendall(reply)
        except OSError:
            return
        finally:
            with self._lock:
                self.concurrent -= 1
                self._protocol.pop(conn, None)
                for subscribers in self.subscriptions.values():
                    subscribers.discard(conn)
            try:
                conn.close()
            except OSError:
                pass

    def _replies_to(self, conn, args):
        verb = args[0].upper() if args else b""
        if verb == b"HELLO":
            proto = int(args[1]) if len(args) > 1 else 3
            with self._lock:
                self._protocol[conn] = proto
            return [_hello_reply(proto)]
        if verb in (b"SUBSCRIBE", b"UNSUBSCRIBE"):
            replies = []
            channels = args[1:]
            with self._lock:
                proto = self._protocol.get(conn, 2)
                if verb == b"UNSUBSCRIBE" and not channels:
                    channels = [
                        ch for ch, subs in self.subscriptions.items() if conn in subs
                    ]
                for channel in channels:
                    subscribers = self.subscriptions.setdefault(channel, set())
                    if verb == b"SUBSCRIBE":
                        subscribers.add(conn)
                    else:
                        subscribers.discard(conn)
                    count = sum(
                        1 for subs in self.subscriptions.values() if conn in subs
                    )
                    replies.append(
                        _pubsub_reply(
                            proto,
                            [verb.lower(), channel],
                            trailer=b":" + str(count).encode() + b"\r\n",
                        )
                    )
            return replies
        return [b"+PONG\r\n"]

    # -- what a test does with it -------------------------------------------

    def publish(self, channel: str, payload: str) -> int:
        """Deliver to every connection subscribed to `channel`."""
        encoded = channel.encode()
        with self._lock:
            targets = list(self.subscriptions.get(encoded, ()))
            for conn in targets:
                proto = self._protocol.get(conn, 2)
                frame = _pubsub_reply(
                    proto, [b"message", encoded, payload.encode()]
                )
                try:
                    conn.sendall(frame)
                except OSError:
                    pass
        return len(targets)

    def subscriber_count(self, channel: str) -> int:
        with self._lock:
            return len(self.subscriptions.get(channel.encode(), ()))

    def drop_connections(self) -> int:
        """Hang up on every client, the way an idle-reap or a TLS blip does.

        The subscription bookkeeping is dropped HERE, under the lock, rather
        than left to each serving thread's `finally`. Otherwise a test that
        waits for "the channel is subscribed again" can be answered by the dead
        connection's leftover entry and read a reconnect that has not happened.
        """
        with self._lock:
            conns = list(self._protocol)
            for subscribers in self.subscriptions.values():
                for conn in conns:
                    subscribers.discard(conn)
        for conn in conns:
            try:
                conn.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                conn.close()
            except OSError:
                pass
        return len(conns)

    def close(self):
        self._stop.set()
        try:
            self.sock.close()
        except OSError:
            pass


def _hello_reply(proto: int) -> bytes:
    return (
        b"%3\r\n"
        b"$6\r\nserver\r\n$5\r\nredis\r\n"
        b"$7\r\nversion\r\n$5\r\n7.4.0\r\n"
        b"$5\r\nproto\r\n:" + str(proto).encode() + b"\r\n"
    )


def _pubsub_reply(proto: int, items: list, trailer: bytes = b"") -> bytes:
    """A pub/sub payload: a RESP3 push when the client asked for protocol 3."""
    count = len(items) + (1 if trailer else 0)
    head = b">" if proto == 3 else b"*"
    out = head + str(count).encode() + b"\r\n"
    for item in items:
        out += b"$" + str(len(item)).encode() + b"\r\n" + item + b"\r\n"
    return out + trailer


def _parse_resp_command(buf: bytes):
    """`(bytes consumed, [args])` for the first complete command, or None."""
    if not buf.startswith(b"*"):
        return None
    end = buf.find(b"\r\n")
    if end == -1:
        return None
    try:
        argc = int(buf[1:end])
    except ValueError:
        return None
    pos = end + 2
    args = []
    for _ in range(argc):
        if not buf[pos:].startswith(b"$"):
            return None
        end = buf.find(b"\r\n", pos)
        if end == -1:
            return None
        try:
            size = int(buf[pos + 1 : end])
        except ValueError:
            return None
        start = end + 2
        pos = start + size + 2
        if len(buf) < pos:
            return None
        args.append(buf[start : start + size])
    return pos, args


# ---------------------------------------------------------------------------
# Rig
# ---------------------------------------------------------------------------


@pytest.fixture
def pubsub_server():
    server = _TinyPubSubServer()
    try:
        yield server
    finally:
        server.close()


@pytest.fixture(params=["2", "3"], ids=lambda p: f"resp{p}")
async def wired(request, pubsub_server, monkeypatch):
    """The production path pointed at the toy server, on both protocols."""
    from app.routes import event_stream as route

    monkeypatch.setattr(
        redis_state,
        "REDIS_URL",
        f"redis://127.0.0.1:{pubsub_server.port}/0?protocol={request.param}",
    )
    # The loop's tick, not a delivery deadline — a frame that arrives mid-wait
    # ends the wait. Short so these tests take milliseconds, not seconds. The
    # hub's own tick is shortened for the same reason: it is the interval at
    # which a released channel's UNSUBSCRIBE and idle teardown are noticed.
    monkeypatch.setattr(route, "FRAME_WAIT_S", 0.05)
    monkeypatch.setattr(live_fanout, "READ_TIMEOUT_S", 0.05)
    await live_fanout.reset_fanout()
    try:
        yield pubsub_server
    finally:
        await live_fanout.reset_fanout()


class _ConnectedRequest:
    """A client that never goes away, so the stream ends when we cancel it."""

    async def is_disconnected(self):
        return False


class _Reader:
    """One open SSE stream, drained into a list by its own task."""

    def __init__(self, event_id: int):
        from app.routes import event_stream as route

        self.event_id = event_id
        self.chunks: list[str] = []
        self._gen = route._stream(event_id, _ConnectedRequest())
        self._task = asyncio.create_task(self._drain())

    async def _drain(self):
        async for chunk in self._gen:
            self.chunks.append(chunk)

    async def opened(self, timeout: float = 5.0) -> None:
        await _until(lambda: any("event: open" in c for c in self.chunks), timeout)

    async def stop(self) -> None:
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass

    @property
    def probability_frames(self) -> list:
        return [
            json.loads(chunk.split("data: ", 1)[1])
            for chunk in self.chunks
            if chunk.startswith("event: probability")
        ]


async def _until(predicate, timeout: float = 5.0, interval: float = 0.01):
    """Wait for a condition the hub reaches on its own reader's next pass."""
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        if predicate():
            return True
        await asyncio.sleep(interval)
    return predicate()


def _live_frame(event_id: int) -> str:
    return json.dumps(
        build_frame(
            event_id=event_id,
            probability=0.61,
            source="kalshi",
            source_value=0.61,
            updated_at=datetime.now(timezone.utc).isoformat(),
            status="live",
        )
    )


# ---------------------------------------------------------------------------
# The ship, counted at the server.
# ---------------------------------------------------------------------------


class TestTheBudgetHoldsAcrossConcurrentStreams:
    async def test_many_concurrent_streams_share_one_connection(self, wired):
        """THE SHIP. Twelve readers on a live match, one socket.

        Before the hub this was twelve sockets — each held for up to 900 s —
        and twelve is already a seventh of the 80 the whole fleet shares.
        """
        readers = [_Reader(4000 + n) for n in range(12)]
        try:
            for reader in readers:
                await reader.opened()
            assert wired.accepted == 1, (
                f"{wired.accepted} connections accepted for 12 streams — the "
                "SSE path is building a pool per stream again"
            )
            assert wired.peak_concurrent == 1
            assert live_fanout.fanout().subscriber_count == 12
            assert live_fanout.fanout().redis_connections == 1
        finally:
            for reader in readers:
                await reader.stop()

    async def test_the_pre_hub_shape_opens_one_socket_per_stream(self, wired):
        """THE NEGATIVE CONTROL, and the reason to believe the arm above.

        This is exactly what `_stream` used to do, run twelve times: the
        uncached factory, a pubsub off it, a subscribe. If the rig could not
        see the defect, the ship's own test would be measuring nothing.
        """
        from app.tasks.redis_state import get_async_redis_client

        clients = []
        try:
            for n in range(12):
                client = get_async_redis_client()
                clients.append(client)
                pubsub = client.pubsub()
                await pubsub.subscribe(event_channel(5000 + n))
                clients.append(pubsub)
            assert wired.accepted == 12, (
                "the old shape did not open a socket per stream in this rig, "
                "so the one-socket result above proves nothing"
            )
        finally:
            for closeable in reversed(clients):
                await closeable.aclose()

    async def test_a_single_stream_still_receives_its_own_frame(self, wired):
        """Delivery, end to end: a published frame reaches the wire."""
        reader = _Reader(4100)
        try:
            await reader.opened()
            await _until(lambda: wired.subscriber_count(event_channel(4100)) == 1)
            assert wired.publish(event_channel(4100), _live_frame(4100)) == 1
            await _until(lambda: reader.probability_frames)
            assert [f["event_id"] for f in reader.probability_frames] == [4100]
            assert reader.probability_frames[0]["p"] == 0.61
        finally:
            await reader.stop()

    async def test_each_stream_receives_only_its_own_events_frames(self, wired):
        """One connection for many channels is only correct if it ROUTES.

        The failure this catches is the one a shared connection invites: every
        reader seeing every live match's numbers, which on a game page is a
        wrong probability rather than a missing one.
        """
        one, two = _Reader(4201), _Reader(4202)
        try:
            await one.opened()
            await two.opened()
            await _until(lambda: wired.subscriber_count(event_channel(4202)) == 1)
            wired.publish(event_channel(4202), _live_frame(4202))
            await _until(lambda: two.probability_frames)
            await asyncio.sleep(0.1)  # time for a misrouted frame to show up
            assert [f["event_id"] for f in two.probability_frames] == [4202]
            assert one.probability_frames == []
        finally:
            await one.stop()
            await two.stop()

    async def test_two_streams_on_one_event_both_get_the_frame(self, wired):
        """Two people watching the same game share a channel, not a frame."""
        one, two = _Reader(4300), _Reader(4300)
        try:
            await one.opened()
            await two.opened()
            await _until(lambda: wired.subscriber_count(event_channel(4300)) == 1)
            wired.publish(event_channel(4300), _live_frame(4300))
            await _until(
                lambda: one.probability_frames and two.probability_frames
            )
            assert one.probability_frames and two.probability_frames
            # One SUBSCRIBE at the server, not two: the second reader joins a
            # channel the process already holds.
            assert wired.subscriber_count(event_channel(4300)) == 1
        finally:
            await one.stop()
            await two.stop()

    async def test_the_last_stream_leaving_gives_the_connection_back(
        self, wired
    ):
        """Cleanup. A web dyno with nobody watching holds no SSE connection.

        Leak this and the fix is only a slower version of the defect: the
        process would accumulate one idle pub/sub connection per burst of
        readers and the budget would drain over hours instead of minutes.
        """
        reader = _Reader(4400)
        await reader.opened()
        assert live_fanout.fanout().redis_connections == 1
        await reader.stop()
        assert await _until(
            lambda: live_fanout.fanout().redis_connections == 0
        ), "the hub kept its connection after the last stream ended"
        assert await _until(lambda: wired.concurrent == 0)
        assert wired.accepted == 1

    async def test_a_reader_returning_reopens_the_connection(self, wired):
        """The other half of idle teardown: it must not be one-shot."""
        first = _Reader(4500)
        await first.opened()
        await first.stop()
        await _until(lambda: live_fanout.fanout().redis_connections == 0)

        second = _Reader(4501)
        try:
            await second.opened()
            await _until(lambda: wired.subscriber_count(event_channel(4501)) == 1)
            wired.publish(event_channel(4501), _live_frame(4501))
            await _until(lambda: second.probability_frames)
            assert second.probability_frames, "the rebuilt hub delivers nothing"
            assert wired.accepted == 2  # one per generation, not one per stream
        finally:
            await second.stop()

    async def test_a_dropped_connection_reconnects_without_ending_anyones_stream(
        self, wired
    ):
        """ONE CONNECTION IS NOT A SINGLE POINT OF FAILURE — measured, not hoped.

        The obvious objection to sharing: a blip now hits every reader on the
        dyno at once instead of one. It does not, because redis-py retries the
        read on the client's retry policy and its `on_connect` callback
        re-subscribes every channel the `PubSub` holds. This kills the
        connection under two live readers and watches them keep receiving —
        without the `reconnect` frame the unrecoverable path emits.
        """
        one, two = _Reader(4801), _Reader(4802)
        try:
            await one.opened()
            await two.opened()
            await _until(lambda: wired.subscriber_count(event_channel(4802)) == 1)
            assert wired.drop_connections() == 1

            assert await _until(
                lambda: wired.subscriber_count(event_channel(4802)) == 1
                and wired.subscriber_count(event_channel(4801)) == 1,
                timeout=10,
            ), "the shared connection did not come back with its channels"
            assert wired.accepted == 2  # one reconnect, not one per reader

            wired.publish(event_channel(4801), _live_frame(4801))
            wired.publish(event_channel(4802), _live_frame(4802))
            assert await _until(
                lambda: one.probability_frames and two.probability_frames,
                timeout=10,
            ), "a blip on the shared connection cost the readers their stream"
            assert not any("event: reconnect" in c for c in one.chunks)
        finally:
            await one.stop()
            await two.stop()

    async def test_one_of_two_readers_on_one_game_leaving_keeps_the_other_fed(
        self, wired
    ):
        """THE REFCOUNT, where it is reader-visible and silent.

        Two people watching the same match share one channel on one
        connection. If the hub unsubscribed when the FIRST of them closed a
        tab, the other's number would simply stop moving — no error, no
        reconnect, a live page frozen on a stale price. Nothing above catches
        it: the two-different-events arm releases a channel nobody else wants,
        and the two-readers arm never has one leave.
        """
        leaver, stayer = _Reader(4700), _Reader(4700)
        try:
            await leaver.opened()
            await stayer.opened()
            await _until(lambda: wired.subscriber_count(event_channel(4700)) == 1)
            await leaver.stop()
            # Long enough for several of the hub reader's passes, so this is
            # "it did not unsubscribe", not "it has not got round to it".
            await asyncio.sleep(0.3)
            assert wired.subscriber_count(event_channel(4700)) == 1, (
                "the hub unsubscribed a channel another reader is still on"
            )
            wired.publish(event_channel(4700), _live_frame(4700))
            await _until(lambda: stayer.probability_frames)
            assert stayer.probability_frames, (
                "the reader who stayed stopped receiving when the other left"
            )
        finally:
            await stayer.stop()

    async def test_one_stream_leaving_does_not_unsubscribe_another(self, wired):
        """The refcount, at the server: releasing one channel keeps the rest."""
        one, two = _Reader(4601), _Reader(4602)
        try:
            await one.opened()
            await two.opened()
            await _until(lambda: wired.subscriber_count(event_channel(4602)) == 1)
            await one.stop()
            assert await _until(
                lambda: wired.subscriber_count(event_channel(4601)) == 0
            ), "the released channel is still subscribed at the server"
            assert wired.subscriber_count(event_channel(4602)) == 1
            wired.publish(event_channel(4602), _live_frame(4602))
            await _until(lambda: two.probability_frames)
            assert two.probability_frames, "the surviving stream stopped hearing"
        finally:
            await two.stop()


# ---------------------------------------------------------------------------
# The hub's own contract, where a socket cannot show it.
# ---------------------------------------------------------------------------


class _ScriptedPubSub:
    def __init__(self):
        self.subscribed: list[str] = []
        self.unsubscribed: list[str] = []
        self.closed = False
        self.fail = False
        self._queue: asyncio.Queue = asyncio.Queue()

    async def subscribe(self, channel):
        self.subscribed.append(channel)

    async def unsubscribe(self, channel):
        self.unsubscribed.append(channel)

    async def aclose(self):
        self.closed = True

    def deliver(self, channel, data):
        self._queue.put_nowait({"type": "message", "channel": channel, "data": data})

    async def get_message(self, ignore_subscribe_messages=False, timeout=None):
        if self.fail:
            raise ConnectionError("the shared pub/sub connection dropped")
        try:
            return await asyncio.wait_for(self._queue.get(), timeout or 0.01)
        except asyncio.TimeoutError:
            return None


class _ScriptedClient:
    def __init__(self, pubsub):
        self._pubsub = pubsub
        self.closed = False

    def pubsub(self):
        return self._pubsub

    async def aclose(self):
        self.closed = True


@pytest.fixture
async def scripted(monkeypatch):
    pubsub = _ScriptedPubSub()
    monkeypatch.setattr(
        "app.tasks.redis_state.get_async_redis_client",
        lambda: _ScriptedClient(pubsub),
    )
    await live_fanout.reset_fanout()
    try:
        yield pubsub
    finally:
        await live_fanout.reset_fanout()


class TestTheHubsContract:
    async def test_release_is_synchronous_and_that_is_the_point(self):
        """A stream releases from a `finally` that runs under cancellation.

        There, the first `await` re-raises `CancelledError` and nothing after
        it executes — so an async release would silently strand the subscriber,
        the hub would never go idle, and its channel would keep being delivered
        to nobody. This is a shape assertion because the bug it prevents cannot
        be seen from the outside until the leak has already accumulated.
        """
        assert not inspect.iscoroutinefunction(live_fanout.LiveFanout.release)

    async def test_a_cancelled_stream_leaves_no_subscriber_behind(
        self, scripted, monkeypatch
    ):
        from app.routes import event_stream as route

        monkeypatch.setattr(route, "FRAME_WAIT_S", 0.05)
        reader = _Reader(4700)
        await reader.opened()
        assert live_fanout.fanout().subscriber_count == 1
        await reader.stop()
        assert live_fanout.fanout().subscriber_count == 0

    async def test_a_slow_stream_drops_its_oldest_frame_not_the_newest(self):
        """A frame is a snapshot, so the NEWEST is the one worth keeping.

        Blocking the hub on a wedged client instead would stall delivery to
        every other reader on the dyno; growing the mailbox without bound would
        turn one stuck browser into a memory leak.
        """
        sub = live_fanout.Subscription("live:event:1")
        for n in range(live_fanout.QUEUE_MAX + 3):
            sub.offer(f"frame-{n}")
        assert sub.dropped == 3
        assert await sub.next(timeout=0.01) == "frame-3"

    async def test_a_dead_reader_is_announced_to_every_stream(
        self, scripted, monkeypatch
    ):
        """THE SILENT FAILURE THIS FIX COULD HAVE INTRODUCED.

        The heartbeat is generated by the route, so a stream on a dead shared
        reader would keep looking alive while its number froze — indefinitely,
        because the client's watchdog sees traffic. Every subscriber is handed
        `CLOSED`, and the route turns that into the `reconnect` the client
        already treats as a rollover.
        """
        from app.routes import event_stream as route

        monkeypatch.setattr(route, "FRAME_WAIT_S", 0.05)
        reader = _Reader(4800)
        await reader.opened()
        scripted.fail = True
        assert await _until(
            lambda: any("event: reconnect" in c for c in reader.chunks)
        ), "a dead shared reader left the stream looking healthy"
        assert '"reason": "upstream"' in "".join(reader.chunks)
        await reader.stop()
        # And the hub is left rebuildable rather than wedged.
        assert live_fanout.fanout().redis_connections == 0

    async def test_a_read_that_never_awaits_does_not_starve_the_loop(
        self, monkeypatch
    ):
        """The shared reader runs on the loop that also serves `/api/feed`.

        A `get_message` that returns without ever awaiting — a stubbed client,
        a transport in a state redis-py answers synchronously — would spin this
        one task and starve every other coroutine in the process, which is the
        single failure this whole file exists to avoid. The reader hands the
        loop back once per pass unconditionally, so the canary below still
        runs. Deliberately driven from another THREAD with its own loop and a
        relief valve: if the guard is gone the loop never returns, and a test
        that hangs proves nothing and jams the suite.
        """
        relief = threading.Event()

        class _NeverAwaitingPubSub:
            subscribed: list = []

            async def subscribe(self, channel):
                pass

            async def unsubscribe(self, channel):
                pass

            async def aclose(self):
                pass

            async def get_message(self, ignore_subscribe_messages=False, timeout=None):
                if relief.is_set():  # let the thread finish once we know
                    await asyncio.sleep(0.01)
                return None

        pubsub = _NeverAwaitingPubSub()
        monkeypatch.setattr(
            redis_state, "get_async_redis_client", lambda: _ScriptedClient(pubsub)
        )

        result = {}

        async def _scenario():
            hub = live_fanout.LiveFanout()
            await hub.subscribe("live:event:1")
            try:
                # Only completes if the reader yields: a timer cannot fire on a
                # starved loop.
                await asyncio.sleep(0.05)
                return True
            finally:
                await hub.aclose()

        def _run():
            loop = asyncio.new_event_loop()
            try:
                result["canary"] = loop.run_until_complete(_scenario())
            finally:
                loop.close()

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()
        thread.join(timeout=2)
        # SNAPSHOT BEFORE THE RELIEF VALVE. Opening the valve lets a starved
        # loop recover and finish, which would then record a pass — the verdict
        # has to be taken while the valve is still shut.
        verdict = result.get("canary")
        relief.set()
        thread.join(timeout=5)
        assert verdict is True, (
            "the hub's reader never handed the loop back — every other "
            "coroutine in the process, `/api/feed` included, was starved"
        )

    async def test_the_hub_is_rebuilt_on_a_new_event_loop(self, scripted):
        """Its lock, mailboxes and reader task all belong to one loop.

        A web dyno has one loop per worker, so this never fires in production —
        but a hub carried onto a second loop raises deep inside `asyncio`
        rather than failing in a way anyone could read.
        """
        first = live_fanout.fanout()
        assert live_fanout.fanout() is first

        def _other_loop():
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(_hub_id())
            finally:
                loop.close()

        async def _hub_id():
            return id(live_fanout.fanout())

        assert await asyncio.to_thread(_other_loop) != id(first)


# ---------------------------------------------------------------------------
# Every pool-building site is counted, so the next one is noticed.
# ---------------------------------------------------------------------------


def _app_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parent.parent / "app"


def _async_pool_sites() -> dict:
    """Modules that call `get_async_redis_client`, and how often.

    Every one of those calls builds a `ConnectionPool` — the factory is
    uncached by design — so this is the census of async pool-building sites.
    """
    sites: dict = {}
    for path in sorted(_app_root().rglob("*.py")):
        tree = ast.parse(path.read_text())
        count = 0
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = (
                func.id
                if isinstance(func, ast.Name)
                else getattr(func, "attr", None)
            )
            if name == "get_async_redis_client":
                count += 1
        if count:
            sites[str(path.relative_to(_app_root()))] = count
    return sites


#: The census as it stood when #6515 shipped. Recorded, not asserted about,
#: except in the two directions below: the SSE route holds none, and the set
#: does not grow without someone reading this comment.
#:
#: THREE KINDS OF SITE, and only the first is bounded:
#:   * `utils/live_fanout.py` — ONE pool for the whole process, for every SSE
#:     stream. That is this ship.
#:   * `utils/request_cache.py`, `utils/rate_limit.py` — one long-lived client
#:     each, held in a module global for the life of the process.
#:   * everything else — a pool per CALL, on request and task paths. Those
#:     pools are lazy and short-lived (one op, then dropped for the garbage
#:     collector), so they are a churn cost rather than a 900-second hold like
#:     SSE was, but they are outside #1197's `envelope x cap` arithmetic and
#:     nobody should read that arithmetic as covering them. Named here so the
#:     residual is a number rather than an impression.
_RECORDED_ASYNC_POOL_SITES = {
    "routes/admin_analytics.py": 2,
    "routes/admin_engagement.py": 2,
    "routes/admin_label_pass.py": 2,
    "routes/economics.py": 2,
    "routes/entertainment.py": 2,
    "routes/futures.py": 1,
    "routes/golf.py": 2,
    "routes/oscars.py": 1,
    "routes/playoffs.py": 8,
    "routes/politics.py": 2,
    "routes/tournaments.py": 3,
    "routes/weather.py": 1,
    "services/ws_shadow.py": 3,
    "tasks/__init__.py": 1,
    "tasks/enrich_markets.py": 1,
    "tasks/kalshi_resolution_sweep.py": 2,
    "tasks/live_blend_refresh.py": 1,
    "tasks/tournament_matchup_linker.py": 3,
    "tasks/tournament_price_refresh.py": 2,
    "utils/feed_cache.py": 1,
    "utils/live_fanout.py": 1,
    "utils/rate_limit.py": 1,
    "utils/request_cache.py": 1,
}


class TestEveryPoolBuildingSiteIsCounted:
    async def test_the_sse_route_builds_no_pool_of_its_own(self):
        """The regression that would quietly undo the ship.

        A future edit reaching for `get_async_redis_client()` inside the stream
        route would restore a pool per reader, and nothing user-facing would
        look different until the plan limit was hit.
        """
        assert "routes/event_stream.py" not in _async_pool_sites()

    async def test_the_census_is_not_vacuous(self):
        """If the AST walk stopped finding calls, the guard above passes on
        every tree, including a broken one."""
        assert len(_async_pool_sites()) >= 20

    async def test_no_new_async_pool_site_appears_unnoticed(self):
        """#1197's envelope counts processes; this counts POOLS.

        A pool per process is what that arithmetic bounds, and #6515 is what
        happens when a path builds one per caller instead. A new entry here is
        not automatically wrong — it is a claim that needs the comment above
        read before it lands.
        """
        assert _async_pool_sites() == _RECORDED_ASYNC_POOL_SITES

    async def test_the_hub_holds_exactly_one_of_them(self):
        """The whole fix, as a number: one construction site, called once per
        process because the hub connects lazily and keeps what it built."""
        assert _RECORDED_ASYNC_POOL_SITES["utils/live_fanout.py"] == 1
        source = inspect.getsource(live_fanout.LiveFanout._connect_locked)
        assert "if self._pubsub is not None:" in source
