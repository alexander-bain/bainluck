"""Committed event frames batch without replaying uncertain Redis writes.

Unit protocol controls run everywhere. Real Redis controls use a disposable
UNIX-socket server when EVENT_FRAME_REDIS_SERVER names a binary (or redis-server
is on PATH); they never reuse a database/Redis service or install anything.
"""

import asyncio
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from redis.asyncio import Redis
from redis.exceptions import ConnectionError, ResponseError

from app.tasks.live_blend_refresh import LiveBlendRefresher
from app.utils.live_push import build_frame


def frames(n):
    return [
        build_frame(
            event_id=i + 1,
            probability=0.6,
            source="polymarket",
            source_value=0.7,
            updated_at="2026-10-07T07:00:00+00:00",
            status="live",
            rev=i + 2,
        )
        for i in range(n)
    ]


class ProtocolRedis:
    def __init__(self, replies=None):
        self.commands = []
        self.batch_sizes = []
        self.reads_before_send = []
        self.replies = iter(replies) if replies is not None else None
        self.connection = SimpleNamespace(
            pack_commands=Mock(side_effect=list),
            send_packed_command=AsyncMock(side_effect=self.send),
            read_response=AsyncMock(side_effect=self.read),
            disconnect=AsyncMock(),
        )
        self.connection_pool = SimpleNamespace(
            get_connection=AsyncMock(return_value=self.connection),
            release=AsyncMock(),
        )

    async def send(self, commands):
        self.commands.extend(commands)
        self.batch_sizes.append(len(commands))
        self.reads_before_send.append(self.connection.read_response.await_count)

    async def read(self):
        reply = next(self.replies) if self.replies is not None else 0
        if isinstance(reply, BaseException):
            raise reply
        return reply


def refresher(client):
    r = LiveBlendRefresher("polymarket")
    r._redis = client
    return r


async def test_empty_input_never_acquires_a_client(monkeypatch):
    r = refresher(None)
    get_client = Mock(side_effect=AssertionError("empty publication"))
    monkeypatch.setattr(r, "_client", get_client)
    await r._publish([])
    get_client.assert_not_called()
    assert r.stats["published"] == r.stats["publish_errors"] == 0


@pytest.mark.parametrize("n", [1, 8, 32, 33, 128])
async def test_exact_frames_order_zero_listener_success_and_bounded_sends(n):
    client = ProtocolRedis()
    r = refresher(client)
    batch = frames(n)
    await r._publish(batch)
    assert client.commands == [
        ("PUBLISH", f'live:event:{f["event_id"]}', json.dumps(f)) for f in batch
    ]
    assert client.batch_sizes == [min(32, n - start) for start in range(0, n, 32)]
    assert client.reads_before_send == list(range(0, n, 32))
    assert r.stats["published"] == n and r.stats["publish_errors"] == 0
    assert r._redis is client
    client.connection.disconnect.assert_not_awaited()
    client.connection_pool.release.assert_awaited_once_with(client.connection)


async def test_client_construction_and_checkout_failures_are_counted(monkeypatch):
    r = refresher(None)
    monkeypatch.setattr(r, "_client", Mock(side_effect=RuntimeError("no Redis URL")))
    await r._publish(frames(8))
    assert r.stats["publish_errors"] == 8 and r._redis is None
    client = ProtocolRedis()
    client.connection_pool.get_connection.side_effect = ConnectionError(
        "pool exhausted"
    )
    r = refresher(client)
    await r._publish(frames(8))
    assert r.stats["publish_errors"] == 8 and r.stats["published"] == 0
    assert r._redis is None
    client.connection_pool.release.assert_not_awaited()


async def test_serialization_and_command_faults_preserve_siblings_and_context(caplog):
    client = ProtocolRedis([0, ResponseError("one event denied"), 0])
    r = refresher(client)
    batch = frames(4)
    batch[1]["invalid"] = object()
    await r._publish(batch)
    assert [json.loads(cmd[2])["event_id"] for cmd in client.commands] == [1, 3, 4]
    assert r.stats["published"] == 2 and r.stats["publish_errors"] == 2
    assert r._redis is client
    assert (
        "polymarket" in caplog.text
        and "event 2" in caplog.text
        and "event 3" in caplog.text
    )
    client.connection.disconnect.assert_not_awaited()


async def test_all_commands_refused_reset_client_after_draining_every_reply():
    client = ProtocolRedis([ResponseError("denied")] * 8)
    r = refresher(client)
    await r._publish(frames(8))
    assert client.connection.read_response.await_count == 8
    assert r.stats["publish_errors"] == 8 and r.stats["published"] == 0
    assert r._redis is None
    client.connection_pool.release.assert_awaited_once()


async def test_uncertain_send_disconnects_and_never_replays():
    client = ProtocolRedis()

    async def uncertain_send(commands):
        await client.send(commands)
        raise ConnectionError("write may already have reached Redis")

    client.connection.send_packed_command.side_effect = uncertain_send
    r = refresher(client)
    await r._publish(frames(128))
    assert client.batch_sizes == [32]
    client.connection.send_packed_command.assert_awaited_once()
    client.connection.disconnect.assert_awaited_once()
    client.connection_pool.release.assert_awaited_once()
    assert r._redis is None and r.stats["publish_errors"] == 128


@pytest.mark.parametrize("bad_reply", [True, -1, "0", None])
async def test_invalid_acknowledgment_is_uncertain_and_not_replayed(bad_reply):
    client = ProtocolRedis([0, bad_reply])
    r = refresher(client)
    await r._publish(frames(8))
    assert r.stats["published"] == 1 and r.stats["publish_errors"] == 7
    client.connection.send_packed_command.assert_awaited_once()
    client.connection.disconnect.assert_awaited_once()
    client.connection_pool.release.assert_awaited_once()


@pytest.mark.parametrize("legacy", [False, True])
async def test_checkout_accepts_modern_and_redis_5_0_pool_signatures(legacy):
    client = ProtocolRedis()
    calls = []
    if legacy:

        async def get_connection(command_name, *keys, **options):
            calls.append(command_name)
            return client.connection

    else:

        async def get_connection(*args):
            calls.append(args)
            return client.connection

    client.connection_pool.get_connection = get_connection
    r = refresher(client)
    await r._publish(frames(1))
    assert calls == (["PUBLISH"] if legacy else [()])
    assert r.stats["published"] == 1 and r.stats["publish_errors"] == 0


@pytest.fixture
def private_redis_socket():
    binary = os.environ.get("EVENT_FRAME_REDIS_SERVER") or shutil.which("redis-server")
    if not binary:
        pytest.skip(
            "set EVENT_FRAME_REDIS_SERVER for private real-Redis event publication controls"
        )
    with tempfile.TemporaryDirectory(prefix="event-frame-10659-") as tmp:
        sock = Path(tmp) / "redis.sock"
        with (Path(tmp) / "redis.log").open("w") as log:
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
                stdout=log,
                stderr=subprocess.STDOUT,
            )
            try:
                deadline = time.monotonic() + 3
                while not sock.exists():
                    if process.poll() is not None:
                        pytest.fail((Path(tmp) / "redis.log").read_text())
                    if time.monotonic() > deadline:
                        pytest.fail("private Redis startup timed out")
                    time.sleep(0.01)
                yield sock
            finally:
                process.terminate()
                process.wait(timeout=5)


class WireConnection:
    def __init__(self, connection, fault, entered):
        self.connection = connection
        self.fault = fault
        self.entered = entered
        self.sends = 0
        self.reads = 0
        self.disconnected = False

    def pack_commands(self, commands):
        if self.fault == "command":
            commands = list(commands)
            commands[2] = ("EVENT_FRAME_TEST_INVALID_COMMAND",)
        return self.connection.pack_commands(commands)

    async def send_packed_command(self, *args, **kwargs):
        self.sends += 1
        await self.connection.send_packed_command(*args, **kwargs)

    async def read_response(self):
        self.reads += 1
        if self.reads == 3 and self.fault == "transport":
            raise ConnectionError("lost acknowledgement after real send")
        if self.reads == 3 and self.fault in ("cancel", "timeout"):
            self.entered.set()
            await asyncio.Event().wait()
        return await self.connection.read_response()

    async def disconnect(self):
        self.disconnected = True
        await self.connection.disconnect()


class WirePool:
    def __init__(self, pool, fault, entered):
        self.pool = pool
        self.fault = fault
        self.entered = entered
        self.connection = None
        self.released = False

    async def get_connection(self, *args, **kwargs):
        self.connection = WireConnection(
            await self.pool.get_connection(*args, **kwargs), self.fault, self.entered
        )
        return self.connection

    async def release(self, connection):
        self.released = True
        await self.pool.release(connection.connection)


async def test_real_redis_zero_listeners_still_count_publication(private_redis_socket):
    client = Redis(unix_socket_path=str(private_redis_socket))
    try:
        r = refresher(client)
        await r._publish(frames(8))
        assert r.stats["published"] == 8 and r.stats["publish_errors"] == 0
    finally:
        await client.aclose()


@pytest.mark.parametrize(
    "n,fault",
    [
        (1, None),
        (33, None),
        (128, None),
        (8, "serialize"),
        (8, "command"),
        (8, "transport"),
        (8, "cancel"),
        (8, "timeout"),
    ],
)
async def test_real_wire_content_siblings_uncertain_writes_and_cleanup(
    private_redis_socket, n, fault
):
    client = Redis(unix_socket_path=str(private_redis_socket))
    subscriber = Redis(unix_socket_path=str(private_redis_socket))
    pubsub = subscriber.pubsub()
    await client.ping()
    await pubsub.psubscribe("live:event:*")
    await pubsub.get_message(timeout=1)
    batch = frames(n)
    if fault == "serialize":
        batch[2]["invalid"] = object()
    expected = [
        json.dumps(f).encode()
        for i, f in enumerate(batch)
        if not (fault in ("serialize", "command") and i == 2)
    ]
    entered = asyncio.Event()
    pool = WirePool(client.connection_pool, fault, entered)
    r = refresher(SimpleNamespace(connection_pool=pool))

    async def receive():
        messages = []
        while len(messages) < len(expected):
            msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1)
            if msg:
                messages.append(msg)
        return messages

    reader = asyncio.create_task(receive())
    publisher = asyncio.create_task(r._publish(batch))
    try:
        if fault == "cancel":
            await asyncio.wait_for(entered.wait(), 3)
            publisher.cancel()
            with pytest.raises(asyncio.CancelledError):
                await publisher
        else:
            await asyncio.wait_for(publisher, 7)
        received = await asyncio.wait_for(reader, 3)
        assert [msg["data"] for msg in received] == expected
        assert [msg["channel"].decode() for msg in received] == [
            f'live:event:{f["event_id"]}'
            for i, f in enumerate(batch)
            if not (fault in ("serialize", "command") and i == 2)
        ]
        if fault in ("transport", "cancel", "timeout"):
            # All commands ran once; only two replies were acknowledged.
            assert r.stats["published"] == 2
            assert r.stats["publish_errors"] == (0 if fault == "cancel" else n - 2)
            assert (
                pool.connection.sends == 1
                and pool.connection.disconnected
                and pool.released
            )
            assert r._redis is None
        else:
            assert r.stats["published"] == len(expected)
            assert r.stats["publish_errors"] == n - len(expected)
            assert pool.connection.sends == (n + 31) // 32
            assert pool.released and not pool.connection.disconnected
        # Drain any duplicate publication instead of inferring no replay from
        # the expected prefix alone, then prove a fresh checkout stays clean.
        assert (
            await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.02)
            is None
        )
        r._redis = client
        recovery = frames(1)
        recovery[0]["event_id"] = 999
        recovery[0]["rev"] = {"999": 1}
        await r._publish(recovery)
        message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1)
        assert message["data"] == json.dumps(recovery[0]).encode()
        assert message["channel"] == b"live:event:999"
    finally:
        for task in (publisher, reader):
            if not task.done():
                task.cancel()
        await asyncio.gather(publisher, reader, return_exceptions=True)
        await pubsub.aclose()
        await client.aclose()
        await subscriber.aclose()
