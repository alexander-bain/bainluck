"""#10090 — a reader leaving a live page releases its stream promptly.

THE SHIP, IN A READER'S WORDS: closing one of two tabs on the same live game
frees that tab's stream at once, and the tab that stayed keeps getting prices.

THE DEFECT. CPython 3.11's `asyncio.wait_for` — what production
(`runtime.txt` python-3.11.11) and CI run — returns the inner result and DROPS
the outer `CancelledError` when the cancel lands in the same loop turn as the
inner awaitable finishing (gh-86296; 3.12 rewrote `wait_for` on
`asyncio.timeout`). `_stream` waits through it twice: the opening replay MGET
(`latest_frames` -> `bounded_redis_call`) and the hub mailbox
(`Subscription.next`). A cancel lost there left the stream, and its hub
refcount, alive until `MAX_CONNECTION_S` (900 s): PR #10910's shard 6 sat 900.32 s
in `test_one_of_two_readers_on_one_game_leaving_keeps_the_other_fed`.

WHY THE STDLIB COPY. Dev boxes run 3.12, whose `wait_for` cannot drop the
cancel, so a test relying on the interpreter would be green there for the wrong
reason. `_wait_for_311` below is CPython 3.11.11's `wait_for` logic, pinned for
the race arms so they bite on every interpreter. It is an emulation, and
`TestTheRigCanSeeTheRace` proves it actually loses the cancel when the route's
guard is bypassed — a green row here is never the rig being blind.
"""

from __future__ import annotations

import asyncio
import functools
import json

import pytest
from starlette.requests import Request

from app.utils import live_fanout, request_cache
from app.utils.live_push import build_frame, event_channel
from tests._event_stream_legacy_view import install_legacy_view


@pytest.fixture(autouse=True)
def _legacy_wire_view(monkeypatch):
    """#10090: these tests predate the stream's owned coverage read and its
    reconcile controls; see tests/_event_stream_legacy_view.py."""
    install_legacy_view(monkeypatch)


pytestmark = pytest.mark.asyncio

STOCK_WAIT_FOR = asyncio.wait_for


# --- CPython 3.11.11 Lib/asyncio/tasks.py `wait_for` (logic verbatim) --------
def _release_waiter(waiter, *args):
    if not waiter.done():
        waiter.set_result(None)


async def _cancel_and_wait(fut, loop):
    waiter = loop.create_future()
    cb = functools.partial(_release_waiter, waiter)
    fut.add_done_callback(cb)
    try:
        fut.cancel()
        await waiter
    finally:
        fut.remove_done_callback(cb)


async def _wait_for_311(fut, timeout):
    loop = asyncio.get_running_loop()
    if timeout is None:
        return await fut
    if timeout <= 0:
        fut = asyncio.ensure_future(fut, loop=loop)
        if fut.done():
            return fut.result()
        await _cancel_and_wait(fut, loop=loop)
        try:
            return fut.result()
        except asyncio.CancelledError as exc:
            raise asyncio.TimeoutError() from exc
    waiter = loop.create_future()
    timeout_handle = loop.call_later(timeout, _release_waiter, waiter)
    cb = functools.partial(_release_waiter, waiter)
    fut = asyncio.ensure_future(fut, loop=loop)
    fut.add_done_callback(cb)
    try:
        try:
            await waiter
        except asyncio.CancelledError:
            if fut.done():
                return fut.result()  # <- 3.11 drops the outer cancel here
            fut.remove_done_callback(cb)
            await _cancel_and_wait(fut, loop=loop)
            raise
        if fut.done():
            return fut.result()
        fut.remove_done_callback(cb)
        await _cancel_and_wait(fut, loop=loop)
        try:
            return fut.result()
        except asyncio.CancelledError as exc:
            raise asyncio.TimeoutError() from exc
    finally:
        timeout_handle.cancel()


# --- rig: the real hub over a scripted pub/sub --------------------------------
class _ScriptedPubSub:
    def __init__(self):
        self.subscribed: list[str] = []
        self.unsubscribed: list[str] = []
        self._queue: asyncio.Queue = asyncio.Queue()

    async def subscribe(self, channel):
        self.subscribed.append(channel)

    async def unsubscribe(self, channel):
        self.unsubscribed.append(channel)

    async def aclose(self):
        pass

    def deliver(self, channel, data):
        self._queue.put_nowait({"type": "message", "channel": channel, "data": data})

    async def get_message(self, ignore_subscribe_messages=False, timeout=None):
        try:
            return await STOCK_WAIT_FOR(self._queue.get(), timeout or 0.01)
        except asyncio.TimeoutError:
            return None


class _ScriptedClient:
    def __init__(self, pubsub):
        self._pubsub = pubsub

    def pubsub(self):
        return self._pubsub

    async def aclose(self):
        pass


class _ReplayRedis:
    """The replay MGET; `on_reply` runs as its reply lands."""

    def __init__(self):
        self.on_reply = None
        self.replies = {}

    async def mget(self, keys):
        if self.on_reply is not None:
            self.on_reply()
        return [self.replies.get(key) for key in keys]


@pytest.fixture
async def rig(monkeypatch):
    from app.routes import event_stream as route

    pubsub = _ScriptedPubSub()
    redis = _ReplayRedis()
    monkeypatch.setattr(
        "app.tasks.redis_state.get_async_redis_client", lambda: _ScriptedClient(pubsub)
    )

    async def shared():
        return redis

    monkeypatch.setattr(request_cache, "get_shared_async_redis", shared)
    monkeypatch.setattr(route, "FRAME_WAIT_S", 0.05)
    # Long enough that a lost cancel cannot pass as prompt, short enough that a
    # regression fails in seconds rather than hanging the shard for 900.
    monkeypatch.setattr(route, "MAX_CONNECTION_S", 3.0)
    monkeypatch.setattr(live_fanout, "READ_TIMEOUT_S", 0.05)
    await live_fanout.reset_fanout()
    try:
        yield pubsub, redis
    finally:
        await live_fanout.reset_fanout()


@pytest.fixture
def py311_wait_for(monkeypatch):
    monkeypatch.setattr(asyncio, "wait_for", _wait_for_311)


class _Connected:
    async def is_disconnected(self):
        return False


class _Reader:
    def __init__(self, event_id: int, request=None):
        from app.routes import event_stream as route

        self.chunks: list[str] = []
        self._gen = route._stream(event_id, request or _Connected())
        self.task = asyncio.create_task(self._drain())

    async def _drain(self):
        async for chunk in self._gen:
            self.chunks.append(chunk)

    async def opened(self):
        assert await _until(lambda: any("event: open" in c for c in self.chunks))

    async def ended(self, within: float) -> str:
        """How the stream's task ended, waited without `wait_for` itself."""
        done, _ = await asyncio.wait({self.task}, timeout=within)
        if not done:
            return "still running"
        if self.task.cancelled():
            return "cancelled"
        exc = self.task.exception()
        return f"raised {exc!r}" if exc else "returned"

    def events(self, name: str) -> list:
        return [c for c in self.chunks if c.startswith(f"event: {name}")]

    async def stop(self):
        self.task.cancel()
        await asyncio.wait({self.task}, timeout=5)


async def _until(predicate, timeout: float = 2.0):
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        if predicate():
            return True
        await asyncio.sleep(0.005)
    return predicate()


async def _turns(n: int = 5):
    for _ in range(n):
        await asyncio.sleep(0)


def _live_frame(event_id: int, p: float = 0.61) -> str:
    from datetime import datetime, timezone

    return json.dumps(build_frame(
        event_id=event_id, probability=p, source="kalshi", source_value=p,
        updated_at=datetime.now(timezone.utc).isoformat(), status="live",
    ))


def _leave_in_the_replay_reply(redis, reader_box):
    redis.on_reply = lambda: asyncio.get_running_loop().call_soon(reader_box[0].task.cancel)


async def _leave_in_the_mailbox_turn(reader, event_id):
    await reader.opened()
    await _turns()
    # A frame lands in this reader's mailbox; the reader leaves the same turn.
    sub = next(iter(live_fanout.fanout()._subscribers[event_channel(event_id)]))
    sub.offer(_live_frame(event_id))
    reader.task.cancel()


# --- the arms -----------------------------------------------------------------
class TestALeavingReaderIsReleasedPromptly:
    async def test_leaving_as_the_replay_read_returns(self, rig, py311_wait_for):
        _, redis = rig
        box = []
        _leave_in_the_replay_reply(redis, box)
        box.append(_Reader(4700))
        assert await box[0].ended(within=1.0) == "cancelled"
        assert not box[0].events("reconnect"), "the stream ran to max_age"
        assert live_fanout.fanout().subscriber_count == 0

    async def test_leaving_as_a_frame_reaches_the_mailbox(self, rig, py311_wait_for):
        reader = _Reader(4701)
        await _leave_in_the_mailbox_turn(reader, 4701)
        assert await reader.ended(within=1.0) == "cancelled"
        assert not reader.events("reconnect"), "the stream ran to max_age"
        assert live_fanout.fanout().subscriber_count == 0

    async def test_the_reader_who_stays_keeps_getting_prices(self, rig, py311_wait_for):
        pubsub, _ = rig
        leaver, stayer = _Reader(4702), _Reader(4702)
        try:
            await stayer.opened()
            await _leave_in_the_mailbox_turn(leaver, 4702)
            assert await leaver.ended(within=1.0) == "cancelled"
            assert live_fanout.fanout().subscriber_count == 1
            await asyncio.sleep(0.2)  # several hub passes: not "not yet"
            assert event_channel(4702) not in pubsub.unsubscribed
            pubsub.deliver(event_channel(4702), _live_frame(4702, 0.64))
            assert await _until(lambda: any(
                json.loads(c.split("data: ", 1)[1]).get("p") == 0.64
                for c in stayer.events("probability")
            )), "the reader who stayed stopped receiving when the other left"
        finally:
            await stayer.stop()
        assert live_fanout.fanout().subscriber_count == 0


class TestAStreamNobodyLeftKeepsRunning:
    async def test_a_silent_market_still_heartbeats(self, rig, py311_wait_for, monkeypatch):
        """A wait that TIMES OUT is not a cancel: the stream must keep going."""
        from app.routes import event_stream as route

        monkeypatch.setattr(route, "HEARTBEAT_INTERVAL_S", 0.1)
        reader = _Reader(4703)
        try:
            assert await _until(lambda: len(reader.events("heartbeat")) >= 3)
            assert not reader.task.done()
        finally:
            await reader.stop()

    async def test_starlettes_disconnect_probe_is_not_mistaken_for_a_leave(self, rig):
        """`Request.is_disconnected` cancels-and-uncancels its own task every pass.

        A guard reading `cancelling()` as an absolute would end every real
        stream on its second pass. Drive a real Starlette request across many
        passes, then deliver a frame, then the real disconnect.
        """
        pubsub, _ = rig
        gone = asyncio.Event()

        async def receive():
            await gone.wait()
            return {"type": "http.disconnect"}

        request = Request(
            {"type": "http", "method": "GET", "headers": [], "query_string": b""}, receive,
        )
        reader = _Reader(4704, request)
        await reader.opened()
        await asyncio.sleep(0.4)  # ~8 passes, each probing the disconnect
        assert not reader.task.done()
        pubsub.deliver(event_channel(4704), _live_frame(4704, 0.66))
        assert await _until(lambda: reader.events("probability"))
        gone.set()
        assert await reader.ended(within=1.0) == "returned"
        assert live_fanout.fanout().subscriber_count == 0


class TestTheRigCanSeeTheRace:
    """Strawman: bypass the route's guard and the same arms must lose the cancel."""

    @pytest.fixture
    def unguarded(self, monkeypatch):
        from app.routes import event_stream as route

        async def plain(awaitable):
            return await awaitable

        monkeypatch.setattr(route, "_await_honouring_cancel", plain)

    async def test_replay_race_loses_the_cancel_without_the_guard(
        self, rig, py311_wait_for, unguarded,
    ):
        _, redis = rig
        box = []
        _leave_in_the_replay_reply(redis, box)
        box.append(_Reader(4710))
        assert await box[0].ended(within=0.5) == "still running"
        await box[0].stop()

    async def test_mailbox_race_loses_the_cancel_without_the_guard(
        self, rig, py311_wait_for, unguarded,
    ):
        reader = _Reader(4711)
        await _leave_in_the_mailbox_turn(reader, 4711)
        assert await reader.ended(within=0.5) == "still running"
        await reader.stop()

    async def test_owned_mailbox_releases_reader_even_with_guard_removed(
        self, rig, py311_wait_for, unguarded, monkeypatch,
    ):
        # While a coverage read is held the route owns the mailbox wait in a
        # task; that path must release the reader without the inline guard.
        from app.routes import event_stream as route

        held = asyncio.Event()

        async def coverage(event_id, ids):
            await held.wait()

        monkeypatch.setattr(route, "_current_reconcile", coverage)
        reader = _Reader(4712)
        try:
            await _leave_in_the_mailbox_turn(reader, 4712)
            assert await reader.ended(within=.5) == "cancelled"
            assert live_fanout.fanout().subscriber_count == 0
        finally:
            held.set()
            await reader.stop()  # port: a reader still running is never abandoned
