"""Optional real-protocol gates; only a new private Unix-socket Redis is used."""

import asyncio
import os
from pathlib import Path
import subprocess
import time
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from datetime import datetime, timezone

import pytest
from redis.asyncio import Redis, ConnectionPool
from redis.asyncio.connection import UnixDomainSocketConnection
from redis.asyncio.retry import Retry
from redis.backoff import NoBackoff
from redis.exceptions import ConnectionError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.utils import market_quote_push as push

STAMP = datetime(2026, 10, 7, tzinfo=timezone.utc)


@pytest.fixture
def redis_socket(tmp_path):
    binary = os.environ.get("MARKET_QUOTE_REDIS_SERVER")
    if not binary:
        pytest.skip("Set MARKET_QUOTE_REDIS_SERVER to run disposable Redis gates")
    with TemporaryDirectory(prefix="bl10659-", dir="/tmp") as directory, (
        tmp_path / "redis.log"
    ).open("w") as log:
        socket = Path(directory) / "redis.sock"
        process = subprocess.Popen(
            [
                "nice",
                "-n",
                "10",
                binary,
                "--port",
                "0",
                "--unixsocket",
                str(socket),
                "--unixsocketperm",
                "700",
                "--save",
                "",
                "--appendonly",
                "no",
                "--maxmemory",
                "64mb",
            ],
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        try:
            deadline = time.monotonic() + 5
            while (
                not socket.exists()
                and process.poll() is None
                and time.monotonic() < deadline
            ):
                time.sleep(0.02)
            assert socket.exists(), (tmp_path / "redis.log").read_text()
            yield str(socket)
        finally:
            if process.poll() is None:
                process.terminate()
            process.wait(timeout=5)


def committed(count):
    engine = create_engine("sqlite://")
    sync = Session(engine)
    session = SimpleNamespace(sync_session=sync, info=sync.info)
    with sync.begin():
        for mid in range(1, count + 1):
            push.queue_market_change(
                session,
                market_id=mid,
                source="kalshi",
                outcome_observed_at={mid: STAMP},
            )
    sync.close()
    engine.dispose()
    return session


async def messages(subscription, count):
    result = []
    async with asyncio.timeout(3):
        while len(result) < count:
            message = await subscription.get_message(
                ignore_subscribe_messages=True, timeout=0.05
            )
            if message is not None:
                result.append(message)
    return result


async def test_real_redis_receives_all_chunks_in_order_with_exact_frames(redis_socket):
    async with Redis(unix_socket_path=redis_socket, max_connections=2) as client:
        async with client.pubsub() as sub:
            await sub.psubscribe("live:market:*")
            await sub.get_message(
                timeout=1
            )  # Server has acknowledged the subscription.
            assert (
                await push.publish_committed_market_changes(committed(65), client) == 65
            )
            received = await messages(sub, 65)
            frames = [push.parse_market_frame(m["data"]) for m in received]
            assert [f["market_id"] for f in frames] == list(range(1, 66))
            assert all(
                f["updated_at"] == STAMP.isoformat() and f["terminal"] is False
                for f in frames
            )
            assert [m["channel"].decode() for m in received] == [
                f"live:market:{n}" for n in range(1, 66)
            ]
            assert await client.ping()  # Same pool remains usable after all replies.


async def test_real_redis_zero_listeners_is_success(redis_socket):
    async with Redis(unix_socket_path=redis_socket) as client:
        assert await push.publish_committed_market_changes(committed(1), client) == 1
        assert await push.publish_committed_market_changes(committed(0), client) == 0


async def test_real_command_error_does_not_hide_healthy_siblings(redis_socket):
    async with Redis(unix_socket_path=redis_socket) as admin:
        await admin.execute_command(
            "ACL",
            "SETUSER",
            "publisher",
            "reset",
            "on",
            "nopass",
            "+publish",
            "+ping",
            "+client|setinfo",
            "&live:market:1",
            "&live:market:3",
        )
        async with admin.pubsub() as sub:
            await sub.psubscribe("live:market:*")
            await sub.get_message(timeout=1)
            async with Redis(
                unix_socket_path=redis_socket, username="publisher"
            ) as client:
                assert (
                    await push.publish_committed_market_changes(committed(3), client)
                    == 2
                )
                received = await messages(sub, 2)
                assert [
                    push.parse_market_frame(m["data"])["market_id"] for m in received
                ] == [1, 3]
                assert await client.ping()


async def test_real_partial_reply_failure_does_not_replay_even_with_client_retries(
    redis_socket,
):
    class LostReplyConnection(UnixDomainSocketConnection):
        publish_replies = None
        injected = False

        async def send_packed_command(self, command, **kwargs):
            packed = [command] if isinstance(command, bytes) else command
            if any(b"\r\nPUBLISH\r\n" in chunk for chunk in packed):
                self.publish_replies = 0
            return await super().send_packed_command(command, **kwargs)

        async def read_response(self, **kwargs):
            reply = await super().read_response(**kwargs)
            if self.publish_replies is not None and not self.injected:
                self.publish_replies += 1
                if self.publish_replies == 2:
                    self.injected = True
                    self.publish_replies = None
                    await self.disconnect()
                    raise ConnectionError(
                        "injected loss after server processed the batch"
                    )
            return reply

    pool = ConnectionPool(
        connection_class=LostReplyConnection,
        path=redis_socket,
        retry=Retry(NoBackoff(), 3),
        max_connections=1,
    )
    try:
        async with Redis(connection_pool=pool) as client:
            assert (
                await push.publish_committed_market_changes(committed(65), client) == 1
            )
            assert await client.ping()
            stats = await client.info("commandstats")
            # Only the first32 were sent. No retry and no next chunk after loss.
            assert stats["cmdstat_publish"]["calls"] == 32
            assert pool.connection_kwargs["retry"].get_retries() == 3
    finally:
        await pool.aclose()
