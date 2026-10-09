"""Raw PM frames reach the existing decoder without losing reader fairness."""
import asyncio
import json

import pytest
from websockets.exceptions import ConnectionClosedError, ConnectionClosedOK
from websockets.frames import Close

from app.services import polymarket_ws as service
from tests.test_pm_socket_fairness_10090 import BufferedSocket


class BytesSocket(BufferedSocket):
    def __init__(self, frames):
        super().__init__(frames)
        self.decode_calls = []

    async def recv(self, decode=None):
        self.decode_calls.append(decode)
        if self.read == len(self.frames):
            self.drained.set()
            await asyncio.Event().wait()
        frame = self.frames[self.read]
        self.read += 1
        return frame

    def __aiter__(self):
        raise AssertionError("modern connection must avoid text iteration")


async def test_bytes_reach_decoder_with_quote_order_pong_and_fairness(monkeypatch):
    messages = [dict(event_type="best_bid_ask", asset_id="a", n=n,
                     large=10**100 + 17, label="é 🎾") for n in range(32)]
    socket = BytesSocket([b"PONG", b"{bad", *[
        json.dumps(m, ensure_ascii=False).encode() for m in messages
    ]])
    monkeypatch.setattr("websockets.connect", lambda *a, **kw: socket)
    decode = service._decode_message
    raw_types = []

    def record(raw):
        raw_types.append(type(raw))
        return decode(raw)

    monkeypatch.setattr(service, "_decode_message", record)
    client = service.PolymarketWebSocket()
    delivered, progress, companions = [], [], []

    async def companion():
        progress.append(len(delivered))

    def receive(message):
        delivered.append(message)
        if len(delivered) == 1:
            companions.append(asyncio.create_task(companion()))

    client.on_price = receive
    task = asyncio.create_task(client._run_one(["a"], 0))
    try:
        await asyncio.wait_for(socket.drained.wait(), 1)
        await asyncio.gather(*companions)
        assert delivered == messages
        assert progress == [1]
        assert set(raw_types) == {bytes}
        assert socket.decode_calls and not any(socket.decode_calls)
        assert client.stats["messages"] == 33
        assert client._shard_wire == {0: {"a"}}
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert socket.closed


@pytest.mark.parametrize("normal", [True, False])
async def test_raw_receive_keeps_normal_close_and_error_distinct(normal):
    exception = ConnectionClosedOK if normal else ConnectionClosedError
    close = Close(1000 if normal else 1008, "")

    class Socket:
        async def recv(self, decode=None):
            raise exception(close, close, True)

    if normal:
        assert [raw async for raw in service._cooperative_messages(Socket())] == []
    else:
        with pytest.raises(ConnectionClosedError):
            _ = [raw async for raw in service._cooperative_messages(Socket())]
