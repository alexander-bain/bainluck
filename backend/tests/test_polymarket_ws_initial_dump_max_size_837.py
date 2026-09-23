"""#837 — a subscribe can be answered with one WebSocket message bigger than
the `websockets` library's default receive ceiling, and that kills a shard
silently. These tests pin the ceiling we state instead of inheriting.

`websockets.connect` defaults `max_size` to 2**20 = 1,048,576 bytes; a message
over it closes the connection with 1009 "message too big" BEFORE the consumer
sees a byte of it (the loopback test below reproduces this without the venue).
The consumer then reconnects, resubscribes, receives the same oversized dump,
and is closed again — a shard whose books outgrow 1 MiB can never stream, and
nothing in `stats()` says why, because it counts as connected right up to each
close. That silence is the reason this is worth a constant.

⚠️ THE MODE IS LATENT, NOT LIVE, AND THE MOTIVATING MEASUREMENT IS EASY TO
MISREAD AS AN OUTAGE REPORT. The 1,286,965 – 1,372,376 byte figure (artifacts/
other-model-837-final-coverage/, 2026-09-23: ONE `list` of 460–496 book
snapshots) was taken over WHOLE-VENUE live books, not over the sports
subscription this client sends. Production the same night, at the shard shape
that figure calls fatal (worker-ws v4950, `shards=3/3`, two shards at the full
500 assets, `0:448/500 1:482/500`), had parsed 186,472 messages and delivered
3,611 prices with 0 errors and no 1009. So these tests guard a book that
deepens; they are not evidence that any shard is currently dark.

These tests are red on a client that leaves the library default in place.
"""

import asyncio

import pytest
import websockets

from app.services import polymarket_ws
from app.services.polymarket_ws import PolymarketWebSocket

#: The largest initial dump observed (D1_live500: 496 books, 2026-09-23T03:48:46Z).
LARGEST_MEASURED_DUMP_BYTES = 1_372_376
#: What `websockets.connect` uses when nobody says otherwise.
LIBRARY_DEFAULT_MAX_SIZE = 2**20


class _FakeSocket:
    def __init__(self):
        self.closed = False

    async def send(self, payload):
        pass

    def __aiter__(self):
        async def gen():
            await asyncio.sleep(3600)
            yield "never"

        return gen()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        self.closed = True
        return False


class TestTheReceiveCeilingIsRaisedAboveTheMeasuredDump:
    @pytest.mark.asyncio
    async def test_connect_is_told_a_max_size_the_venue_dump_fits_under(
        self, monkeypatch
    ):
        """Red on a client that omits `max_size`: the library default (1 MiB)
        is smaller than every dump measured for a 470–500 asset shard."""
        seen: list[dict] = []

        def connect(*args, **kwargs):
            seen.append(kwargs)
            return _FakeSocket()

        monkeypatch.setattr("websockets.connect", connect, raising=False)

        ws = PolymarketWebSocket()
        task = asyncio.create_task(
            ws.run(asset_ids=[str(10**76 + i) for i in range(3)])
        )
        await asyncio.sleep(0.2)
        task.cancel()
        with pytest.raises((asyncio.CancelledError, Exception)):
            await task

        assert seen, "sanity: the consumer connected at least once"
        for kwargs in seen:
            ceiling = kwargs.get("max_size", LIBRARY_DEFAULT_MAX_SIZE)
            assert ceiling is None or ceiling >= LARGEST_MEASURED_DUMP_BYTES, (
                f"websockets.connect was given max_size={ceiling!r}; the venue's "
                f"initial dump for a full shard measured {LARGEST_MEASURED_DUMP_BYTES} "
                "bytes and would be refused with 1009 before the consumer sees it"
            )

    def test_the_ceiling_constant_clears_the_measured_dump_with_margin(self):
        """A ceiling that only just fits tonight's dump is next week's outage:
        book depth is the venue's to choose. Two times the largest measurement
        is the least margin that means anything."""
        ceiling = getattr(polymarket_ws, "MAX_MESSAGE_BYTES", None)
        assert ceiling is not None, "polymarket_ws.MAX_MESSAGE_BYTES is not defined"
        assert ceiling >= 2 * LARGEST_MEASURED_DUMP_BYTES


class TestTheLibraryDefaultReallyDropsADumpSizedMessage:
    """Loopback, no venue: this is the failure class, reproduced locally."""

    @staticmethod
    def _dump(nbytes: int) -> str:
        body = ",".join(
            '{"asset_id":"x","bids":[],"asks":[]}' for _ in range(nbytes // 30)
        )
        return "[" + body[: nbytes - 2] + "]"

    @pytest.mark.asyncio
    async def test_default_ceiling_closes_with_1009_and_ours_receives_the_dump(self):
        dump = self._dump(1_299_598)  # L_repeat, 2026-09-23T03:50:21Z

        async def handler(sock):
            try:
                await sock.recv()
                await sock.send(dump)
                await sock.send('{"event_type":"price_change","price_changes":[]}')
                await asyncio.sleep(1)
            except Exception:
                pass

        async with websockets.serve(handler, "127.0.0.1", 0, max_size=None) as server:
            port = server.sockets[0].getsockname()[1]
            url = f"ws://127.0.0.1:{port}"

            with pytest.raises(websockets.exceptions.ConnectionClosedError) as exc:
                async with websockets.connect(url, ping_interval=None) as sock:
                    await sock.send('{"type": "market"}')
                    await sock.recv()
            assert exc.value.rcvd is None or exc.value.rcvd.code != 1000
            assert "1009" in str(exc.value) or "too big" in str(exc.value)

            async with websockets.connect(
                url, ping_interval=None, max_size=polymarket_ws.MAX_MESSAGE_BYTES
            ) as sock:
                await sock.send('{"type": "market"}')
                first = await sock.recv()
                second = await sock.recv()
            assert len(first) == len(dump)
            assert "price_change" in second
