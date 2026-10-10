"""Actual receive loop releases processed payloads; no RSS/latency claim."""

import asyncio
from collections import deque
import json
import weakref
import pytest
import websockets
from app.services import polymarket_ws as svc


class Socket:
    def __init__(self, frames):
        self.frames = deque(frames)
        self.quiet = asyncio.Event()
        self.forever = asyncio.Event()
        self.exited = None
        self.task = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        self.exited = self.released()

    async def send(self, _value):
        pass

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self.frames:
            return self.frames.popleft()
        self.quiet.set()
        await self.forever.wait()
        raise StopAsyncIteration

    def released(self):
        return all(
            self.task.get_coro().cr_frame.f_locals.get(k) is None
            for k in ("raw", "data", "result")
        )

    async def stop(self):
        self.task.cancel()
        await asyncio.gather(self.task, return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("tail", [None, "PONG", "{malformed"])
@pytest.mark.parametrize("priced", [False, True])
async def test_processed_book_root_is_released(monkeypatch, tail, priced):
    message = [
        {
            "event_type": "book",
            "asset_id": "asset",
            "bids": [{"price": "0.4", "size": "20"}],
            "asks": [{"price": "0.6", "size": "30"}],
        }
    ]
    socket = Socket([json.dumps(message)] + ([] if tail is None else [tail]))
    references, quotes = [], []
    # The receive loop decodes with pydantic's `from_json` (abed7efea7), so
    # the book root is observed where it is actually built.
    decode = svc.from_json

    class BookRoot(list):
        pass

    def observe(raw, **kwargs):
        value = decode(raw, **kwargs)
        if isinstance(value, list):
            value = BookRoot(value)
            references.append(weakref.ref(value))
        return value

    monkeypatch.setattr(svc, "from_json", observe)
    monkeypatch.setattr(websockets, "connect", lambda *_a, **_kw: socket)
    consumer = svc.PolymarketWebSocket(price_book_snapshots=priced)
    consumer.on_price = quotes.append
    socket.task = asyncio.create_task(consumer._run_one(["asset"], 0))
    try:
        await asyncio.wait_for(socket.quiet.wait(), 2)
        assert len(references) == 1 and references[0]() is None
        assert socket.released()
        assert consumer._shard_wire[0] == {"asset"}
        assert consumer._message_count == (2 if tail == "{malformed" else 1)
        assert [(q["asset_id"], q["best_bid"], q["best_ask"]) for q in quotes] == (
            [("asset", "0.4", "0.6")] if priced else []
        )
        assert not socket.task.done()
    finally:
        await socket.stop()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kind", ["best_bid_ask", "last_trade_price", "market_resolved", "new_market"]
)
@pytest.mark.parametrize("raises", [False, True])
async def test_callback_payload_intact_but_frame_releases(monkeypatch, kind, raises):
    message = {"event_type": kind, "asset_id": "asset", "payload": [1, 2, 3]}
    socket, kept = Socket([json.dumps(message)]), []

    def callback(value):
        kept.append(value)
        if raises:
            raise ValueError("owned callback failure")
        return value

    monkeypatch.setattr(websockets, "connect", lambda *_a, **_kw: socket)
    consumer = svc.PolymarketWebSocket()
    for name in ("on_price", "on_trade", "on_resolved", "on_new_market"):
        setattr(consumer, name, callback)
    socket.task = asyncio.create_task(consumer._run_one(["asset"], 0))
    try:
        await asyncio.wait_for(socket.quiet.wait(), 2)
        assert kept == [message]
        assert socket.released()
        assert consumer._message_count == 1
        assert consumer._shard_wire[0] == {"asset"}
    finally:
        await socket.stop()


@pytest.mark.asyncio
async def test_cancel_unwinds_handler_before_cleanup(monkeypatch):
    message = {
        "event_type": "last_trade_price",
        "asset_id": "asset",
        "payload": [1, 2, 3],
    }
    socket = Socket([json.dumps(message)])
    entered, cancelled = asyncio.Event(), []

    async def handler(value):
        entered.set()
        try:
            await socket.forever.wait()
        except asyncio.CancelledError:
            cancelled.append(value == message)
            raise

    monkeypatch.setattr(websockets, "connect", lambda *_a, **_kw: socket)
    consumer = svc.PolymarketWebSocket()
    consumer.on_trade = handler
    socket.task = asyncio.create_task(consumer._run_one(["asset"], 0))
    try:
        await asyncio.wait_for(entered.wait(), 2)
        assert not socket.released()
        socket.task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await socket.task
        assert cancelled == [True] and socket.exited is True
        assert not consumer.is_connected
    finally:
        await socket.stop()
