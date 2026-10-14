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
    decode = service._decode_text_frame_bytes
    raw_types = []

    def record(raw):
        raw_types.append(type(raw))
        return decode(raw)

    monkeypatch.setattr(service, "_decode_text_frame_bytes", record)
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


def text_path_outcome(decode, raw):
    try:
        return ("value", decode(raw))
    except Exception as error:
        return ("error", type(error))


@pytest.mark.parametrize("raw", [
    json.dumps({"n": 10**100 + 17, "label": "é 🎾"}, ensure_ascii=False).encode(),
    '{"a":1}'.encode("utf-16"),
    '{"a":1}'.encode("utf-16-le"),
    '{"a":1}'.encode("utf-32"),
    b'\xef\xbb\xbf{"a":1}',
    b'{"a":"\xed\xa0\x80"}',
    b'{"a":"x\xffy"}',
    b'["\\ud800"]',
    b"{bad",
])
def test_raw_text_frame_decodes_exactly_as_the_old_text_path(raw):
    # The old path: the library decoded the text frame strictly, then parsed.
    old = text_path_outcome(lambda b: service._decode_message(b.decode("utf-8")), raw)
    assert text_path_outcome(service._decode_text_frame_bytes, raw) == old


class RecoveryClock:
    """The service's asyncio, with its reconnect wait recorded and not slept.

    Yields stay real; the 8 s heartbeat keeps its real sleep (it never fires
    inside this test), so the only wait taken off the wall clock is the one
    under test and the test's own one-second runaway guard stays honest.
    """

    def __init__(self, events):
        self.events = events

    def __getattr__(self, name):
        return getattr(asyncio, name)

    async def sleep(self, delay, *args, **kwargs):
        if delay in (0, 8):
            return await asyncio.sleep(delay, *args, **kwargs)
        self.events.append(("wait", delay))
        return await asyncio.sleep(0)


@pytest.mark.parametrize("draw", [0.0, 0.999998])  # both ends of random()
async def test_utf16_frame_drops_its_connection_and_the_next_connection_delivers(
    monkeypatch, draw,
):
    # Strict UTF-8: the bad frame raises out of the decoder, so its connection
    # is abandoned (never skipped in place) and the quote arrives on a NEW one.
    stale = dict(event_type="best_bid_ask", asset_id="a", n=0)
    message = dict(event_type="best_bid_ask", asset_id="a", n=1)
    failed = BytesSocket([json.dumps(message).encode("utf-16"),
                          json.dumps(stale).encode()])
    recovered = BytesSocket([json.dumps(message).encode()])
    sockets, events = [failed, recovered], []

    def connect(*_args, **_kwargs):
        if not sockets:
            pytest.fail("dialled a third connection")
        events.append("dial")
        return sockets.pop(0)

    monkeypatch.setattr("websockets.connect", connect)
    monkeypatch.setattr(service.random, "random", lambda: draw)
    monkeypatch.setattr(service, "asyncio", RecoveryClock(events))
    client = service.PolymarketWebSocket()
    delivered = []
    client.on_price = delivered.append
    task = asyncio.create_task(client._run_one(["a"], 0))
    try:
        await asyncio.wait_for(recovered.drained.wait(), 1)
        wait = service.INITIAL_BACKOFF_SECONDS * (0.5 + draw / 2)
        assert events == ["dial", ("wait", wait), "dial"]
        assert delivered == [message]
        assert failed.closed and failed.read == 1 and not failed.drained.is_set()
        assert failed.decode_calls == [False]
        assert recovered.decode_calls == [False, False]
        assert client.stats["messages"] == 2
        assert client.stats["reconnects"] == 2
        assert client._shards_connected == {0}
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert recovered.closed
    assert client._shards_connected == set()
    assert delivered == [message]
