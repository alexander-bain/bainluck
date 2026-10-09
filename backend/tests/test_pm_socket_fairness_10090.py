"""A cached quote burst must let ready probability-writing tasks run."""

import asyncio
import json

import pytest

from app.services.polymarket_ws import PolymarketWebSocket


class BufferedSocket:
    def __init__(self, frames):
        self.frames = frames
        self.read = 0
        self.drained = asyncio.Event()
        self.closed = False

    async def send(self, payload):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        self.closed = True

    def __aiter__(self):
        async def frames():
            for frame in self.frames:
                self.read += 1
                yield frame  # A buffered websocket receive need not suspend.
            self.drained.set()
            await asyncio.Event().wait()
        return frames()


@pytest.mark.asyncio
@pytest.mark.parametrize("async_handler", [False, True])
async def test_ready_stamp_runs_during_burst_with_order_and_all_quotes_preserved(
    monkeypatch, async_handler,
):
    frames = [json.dumps({"event_type": "best_bid_ask", "asset_id": "a", "n": n})
              for n in range(128)]
    socket = BufferedSocket(frames)
    monkeypatch.setattr("websockets.connect", lambda *a, **kw: socket)
    client = PolymarketWebSocket()
    delivered, sibling_at, siblings = [], [], []

    async def ready_stamp():
        sibling_at.append(len(delivered))

    def receive(message):
        delivered.append(message["n"])
        if len(delivered) == 1:
            siblings.append(asyncio.create_task(ready_stamp()))

    async def receive_async(message):
        receive(message)  # Like an uncontended buffer lock, no suspension.

    client.on_price = receive_async if async_handler else receive
    task = asyncio.create_task(client._run_one(["a"], 0))
    try:
        await asyncio.wait_for(socket.drained.wait(), 1)
        await asyncio.gather(*siblings)
        assert delivered == list(range(128))
        # A runnable writer gets control after the current callback, before
        # this shard consumes any more cached frames.
        assert sibling_at == [1]
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert socket.closed


@pytest.mark.asyncio
async def test_ignored_and_invalid_wire_frames_also_yield(monkeypatch):
    frames = ['PONG', '{bad', json.dumps({"event_type": "price_change"})] * 64
    socket = BufferedSocket(frames)
    monkeypatch.setattr("websockets.connect", lambda *a, **kw: socket)
    client = PolymarketWebSocket()
    first_read = asyncio.Event()
    original = socket.__class__.__aiter__

    def read_frames(self):
        async def frames():
            async for raw in original(self):
                first_read.set()
                yield raw
        return frames()

    monkeypatch.setattr(BufferedSocket, "__aiter__", read_frames)
    task = asyncio.create_task(client._run_one(["a"], 0))
    try:
        await asyncio.wait_for(first_read.wait(), 1)
        # wait_for's task/future wake can take several loop turns, but it must
        # get a turn before the entire cached burst has been drained.
        assert socket.read < len(frames)
        await asyncio.wait_for(socket.drained.wait(), 1)
        assert socket.read == len(frames)
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert socket.closed
