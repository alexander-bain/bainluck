"""A buffered Kalshi burst gives ready probability writers a loop turn."""

import asyncio
import json

import pytest
import websockets

from app.services import kalshi_ws as service


class BufferedSocket:
    def __init__(self, frames):
        self.frames = frames
        self.read = 0
        self.drained = asyncio.Event()
        self.closed = False
        self.first_read = None

    async def send(self, payload):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        self.closed = True

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self.read < len(self.frames):
            frame = self.frames[self.read]
            self.read += 1
            if self.read == 1 and self.first_read is not None:
                self.first_read()
            return frame  # Buffered receive and uncontended callbacks need not suspend.
        self.drained.set()
        await asyncio.Event().wait()
        raise StopAsyncIteration


def install(monkeypatch, socket):
    monkeypatch.setattr(websockets, "connect", lambda *a, **kw: socket)
    monkeypatch.setattr(service, "_load_rsa_key", lambda: object())
    monkeypatch.setattr(service, "_sign_ws_request", lambda *a: {})


async def stop(task, socket, client):
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert socket.closed and not client.is_connected


@pytest.mark.asyncio
@pytest.mark.parametrize("async_handler", [False, True])
async def test_ready_writer_runs_during_burst_with_all_callbacks_in_order(
    monkeypatch, async_handler,
):
    kinds = ("ticker", "market_lifecycle_v2", "trade")
    payloads = [
        {"market_ticker": "KXMLBGAME-26OCT08NYJBUF-BUF", "n": n,
         "yes_bid": 41, "yes_ask": 43, "kind": kinds[n % 3]}
        for n in range(128)
    ]
    socket = BufferedSocket([
        json.dumps({"type": payload["kind"], "msg": payload})
        for payload in payloads
    ])
    install(monkeypatch, socket)
    client = service.KalshiWebSocket()
    delivered, sibling_at, siblings = [], [], []

    async def ready_writer():
        sibling_at.append(len(delivered))

    def receive(payload):
        delivered.append(payload)
        if len(delivered) == 1:
            siblings.append(asyncio.create_task(ready_writer()))

    async def receive_async(payload):
        receive(payload)  # Like the buffer handler with an uncontended lock.

    callback = receive_async if async_handler else receive
    client.on_ticker = client.on_lifecycle = client.on_trade = callback
    task = asyncio.create_task(client.run([payloads[0]["market_ticker"]]))
    try:
        await asyncio.wait_for(socket.drained.wait(), 1)
        await asyncio.gather(*siblings)
        assert delivered == payloads
        assert 0 < sibling_at[0] <= 32, sibling_at
        assert client.stats["messages"] == 128
        assert task.get_coro().cr_frame.f_locals["raw"] is None
    finally:
        await stop(task, socket, client)


@pytest.mark.asyncio
async def test_ignored_and_invalid_frames_also_give_ready_writer_a_turn(monkeypatch):
    socket = BufferedSocket([
        "{bad", None, json.dumps({"type": "subscribed", "msg": {}}),
        json.dumps({"type": "unknown", "msg": {}}),
    ] * 32)
    install(monkeypatch, socket)
    client = service.KalshiWebSocket()
    sibling_at, siblings = [], []

    async def ready_writer():
        sibling_at.append(socket.read)

    socket.first_read = lambda: siblings.append(asyncio.create_task(ready_writer()))
    task = asyncio.create_task(client.run(["KXMLBGAME-26OCT08NYJBUF-BUF"]))
    try:
        await asyncio.wait_for(socket.drained.wait(), 1)
        await asyncio.gather(*siblings)
        assert socket.read == 128 and client.stats["messages"] == 128
        assert 0 < sibling_at[0] <= 32, sibling_at
        assert task.get_coro().cr_frame.f_locals["raw"] is None
    finally:
        await stop(task, socket, client)
