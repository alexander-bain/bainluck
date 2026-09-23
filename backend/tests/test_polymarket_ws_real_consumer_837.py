"""#837 — the raised receive ceiling actually DISPATCHES an oversized dump.

WHY THIS EXISTS ALONGSIDE ``test_polymarket_ws_initial_dump_max_size_837.py``.
That file proves the bytes are received: its loopback dump is built by slicing
a JSON string to an exact length, which lands mid-object and is not parseable.
So it can show the socket no longer closes with 1009 — and cannot show that the
consumer then does anything with the message. Those are different claims, and
#837's ship is the second one: a price reaching the reader, not a byte reaching
a buffer. A ceiling could be raised correctly and the dump still be dropped by
a parse error, an event-type mismatch or a serve-accounting bug, and every
assertion in the sibling file would stay green.

This guard sends VALID book-shaped JSON over 1 MiB through the REAL
``PolymarketWebSocket.run`` and asserts the ``best_bid_ask`` that follows it
reaches ``on_price`` — plus the subscription identity, the served-token
accounting and the message count, so a regression that swallows the dump and
resubscribes cannot pass by staying silent.

Provenance: written independently by the Codex review of candidate 48fe7bb
(``artifacts/other-model-837-final-coverage/CODEX-test-real-consumer.py``),
which ran it 5-red on the unpatched base and green on the candidate. Adopted
here rather than relying on the byte-only loopback alone.
"""

import asyncio
import json

import pytest
import websockets

from app.services import polymarket_ws

#: The largest initial dump measured against the public CLOB socket on
#: 2026-09-23 (D1_live500: 496 books). The synthetic dump below must exceed it,
#: or this test is not exercising the class that broke.
LARGEST_MEASURED_DUMP_BYTES = 1_372_376


@pytest.mark.asyncio
async def test_real_consumer_dispatches_after_valid_large_book_list(monkeypatch):
    """Red on a client that leaves `max_size` at the library default: the dump
    is refused with 1009 and the `best_bid_ask` behind it never arrives."""
    token = "12345"
    # Valid book-shaped JSON — 500 records, each deep enough that the whole
    # list clears the measured dump. Parseable, unlike a sliced string.
    book = {
        "asset_id": token,
        "bids": [{"price": "0.40", "size": "100.00"}] * 90,
        "asks": [],
    }
    dump = json.dumps([book] * 500)
    # The upper bound is the LITERAL 8 MiB, deliberately not
    # `polymarket_ws.MAX_MESSAGE_BYTES`: on a client that has not been fixed yet
    # that attribute does not exist, and reading it here would make this test
    # red with an AttributeError on line one — before the consumer is ever
    # started. It would then "fail on base" while proving nothing whatever about
    # dispatch, which is the single claim this file is here to make.
    # `test_message_ceiling_remains_bounded` below owns the constant's value.
    assert (
        LARGEST_MEASURED_DUMP_BYTES < len(dump.encode()) < 8 * 1024 * 1024
    ), "the synthetic dump must sit above the measured dump and under the ceiling"

    delivered = asyncio.Event()
    observed: list[dict] = []
    subscriptions: list[dict] = []

    async def handler(sock):
        subscriptions.append(json.loads(await sock.recv()))
        try:
            await sock.send(dump)
            await sock.send(
                json.dumps(
                    {
                        "event_type": "best_bid_ask",
                        "asset_id": token,
                        "best_bid": "0.40",
                        "best_ask": "0.42",
                    }
                )
            )
            await sock.wait_closed()
        except websockets.exceptions.ConnectionClosed:
            pass

    async with websockets.serve(handler, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        monkeypatch.setattr(polymarket_ws, "WS_URL", f"ws://127.0.0.1:{port}")

        consumer = polymarket_ws.PolymarketWebSocket()

        def on_price(frame):
            observed.append(frame)
            delivered.set()

        consumer.on_price = on_price
        task = asyncio.create_task(consumer.run(asset_ids=[token]))
        try:
            await asyncio.wait_for(delivered.wait(), 10)
            assert observed[0]["best_bid"] == "0.40"
            assert token in consumer._shard_served[0]
            assert consumer._message_count >= 2
            assert subscriptions[0]["assets_ids"] == [token]
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


def test_message_ceiling_remains_bounded():
    """The ceiling clears the measured dump AND stays finite: `max_size=None`
    would also make this suite's sibling green while letting one hostile
    message grow the process without bound."""
    ceiling = getattr(polymarket_ws, "MAX_MESSAGE_BYTES", None)
    assert isinstance(ceiling, int)
    assert LARGEST_MEASURED_DUMP_BYTES < ceiling <= 8 * 1024 * 1024
