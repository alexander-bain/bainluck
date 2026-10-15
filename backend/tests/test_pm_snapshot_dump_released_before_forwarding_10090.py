"""#10090: a book dump is let go of before its quotes wait on the consumer.

A decoded 500-book dump measured 11-18 MB (~10x its 1.1-1.6 MB wire size, real
Polymarket dumps captured 2026-10-15); its quotes are a small fraction of that.
In the open receiver child every quote waits on the pipe to the parent, and at
startup every shard is forwarding its dump at once, so the receive loop must not
hold the dump — decoded or raw — while it forwards. These tests run the actual
`_run_one` receive loop and block `on_price` on the first quote, then look at
what is still alive. No RSS or latency claim is made here.
"""

import asyncio
import gc
import json
import weakref
from collections import deque

import pytest
import websockets

from app.services import polymarket_ws as svc


def books(count, prefix="asset"):
    return [
        {
            "event_type": "book",
            "asset_id": f"{prefix}-{i}",
            "market": f"market-{i}",
            "timestamp": "1791346500000",
            "bids": [{"price": f"0.{10 + j}", "size": "5"} for j in range(20)],
            "asks": [{"price": f"0.{60 + j}", "size": "5"} for j in range(20)],
        }
        for i in range(count)
    ]


class _Base:
    def __init__(self, frames):
        self.frames = deque(frames)
        self.quiet = asyncio.Event()
        self.forever = asyncio.Event()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_a):
        pass

    async def send(self, _value):
        pass

    async def _next(self):
        if self.frames:
            return self.frames.popleft()
        self.quiet.set()
        await self.forever.wait()
        raise StopAsyncIteration


class BytesSocket(_Base):
    """websockets >= 13: text frames received undecoded."""

    async def recv(self, decode=None):
        return await self._next()


class IterSocket(_Base):
    """The older iterator contract."""

    def __aiter__(self):
        return self

    async def __anext__(self):
        return await self._next()


def holders(obj):
    """Receive-loop frames that still reference ``obj``."""
    names = set()
    for ref in gc.get_referrers(obj):
        code = getattr(ref, "cr_code", None) or getattr(ref, "ag_code", None)
        if code is not None and code.co_name in ("_run_one", "_cooperative_messages"):
            names.add(code.co_name)
    return names


def observe_book_roots(monkeypatch):
    references = []
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
    return references


@pytest.mark.asyncio
@pytest.mark.parametrize("socket_cls,encode", [
    (BytesSocket, lambda s: s.encode()),
    (IterSocket, lambda s: s),
])
@pytest.mark.parametrize("bad_tail", [False, True])
async def test_dump_is_released_while_its_quotes_wait(monkeypatch, socket_cls, encode, bad_tail):
    dump = books(70) + ([{"asset_id": "bad", "bids": 5, "asks": []}] if bad_tail else [])
    raw = encode(json.dumps(dump))
    live = {"event_type": "best_bid_ask", "asset_id": "asset-3",
            "best_bid": "0.5", "best_ask": "0.52"}
    socket = socket_cls([raw, encode(json.dumps(live))])
    references = observe_book_roots(monkeypatch)
    # A redial (the `bad_tail` frame drops the shard, as before) parks on its
    # second connect instead of sleeping out a backoff.
    connections = iter([socket, _Parked(socket)])
    monkeypatch.setattr(websockets, "connect", lambda *_a, **_kw: next(connections))
    monkeypatch.setattr(svc, "_jittered", lambda _delay: 0)

    seen, entered, release = [], asyncio.Event(), asyncio.Event()

    async def on_price(quote):
        seen.append(quote)
        if len(seen) == 1:
            entered.set()
            await release.wait()

    client = svc.PolymarketWebSocket(price_book_snapshots=True)
    client.on_price = on_price
    task = asyncio.create_task(client._run_one(["asset-0"], 0))
    try:
        await asyncio.wait_for(entered.wait(), 2)
        gc.collect()
        # The first quote is waiting on the consumer: neither form of the dump
        # may still be alive behind it.
        assert len(references) == 1 and references[0]() is None
        assert holders(raw) == set()
        release.set()
        await asyncio.wait_for(socket.quiet.wait(), 2)
        expected = svc._snapshot_quotes(books(70))
        if bad_tail:
            # Extraction stopped at the bad book's batch: the batches before it
            # were priced, then the shard dropped and redials (as before).
            assert seen == expected[:64]
            assert client._book_snapshot_quotes == 64
        else:
            assert seen == expected + [live]
            assert client._book_snapshot_quotes == 70
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


class _Parked:
    def __init__(self, socket):
        self.socket = socket

    async def __aenter__(self):
        self.socket.quiet.set()
        await self.socket.forever.wait()

    async def __aexit__(self, *_a):
        pass


@pytest.mark.asyncio
async def test_a_fence_narrowed_while_a_quote_waits_still_applies(monkeypatch):
    socket = BytesSocket([json.dumps(books(40)).encode()])
    monkeypatch.setattr(websockets, "connect", lambda *_a, **_kw: socket)
    seen, entered, release = [], asyncio.Event(), asyncio.Event()

    async def on_price(quote):
        seen.append(quote["asset_id"])
        if len(seen) == 1:
            entered.set()
            await release.wait()

    client = svc.PolymarketWebSocket(price_book_snapshots=True)
    client.on_price = on_price
    client._shard_routed = {0: frozenset(f"asset-{i}" for i in range(40))}
    task = asyncio.create_task(client._run_one(["asset-0"], 0))
    try:
        await asyncio.wait_for(entered.wait(), 2)
        # The catalog dropped every odd token while the first quote waited.
        client._shard_routed = {0: frozenset(f"asset-{i}" for i in range(0, 40, 2))}
        release.set()
        await asyncio.wait_for(socket.quiet.wait(), 2)
        assert seen == [f"asset-{i}" for i in range(0, 40, 2)]
        assert client._book_snapshot_quotes == 20
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_a_quiet_socket_keeps_neither_the_dump_nor_its_quotes(monkeypatch):
    socket = BytesSocket([json.dumps(books(40)).encode()])
    references = observe_book_roots(monkeypatch)
    monkeypatch.setattr(websockets, "connect", lambda *_a, **_kw: socket)
    seen = []
    client = svc.PolymarketWebSocket(price_book_snapshots=True)
    client.on_price = seen.append
    task = asyncio.create_task(client._run_one(["asset-0"], 0))
    try:
        await asyncio.wait_for(socket.quiet.wait(), 2)
        gc.collect()
        assert len(seen) == 40 and references[0]() is None
        f_locals = task.get_coro().cr_frame.f_locals
        assert all(f_locals.get(k) is None for k in ("raw", "data", "quotes", "failure"))
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_extraction_still_yields_between_batches():
    """#10665's bound holds for extraction too, now that it runs first."""
    ticks = []

    async def companion():
        while True:
            ticks.append(1)
            await asyncio.sleep(0)

    task = asyncio.create_task(companion())
    await asyncio.sleep(0)
    before = len(ticks)
    quotes, failure = await svc._snapshot_quotes_cooperatively(books(100))
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    assert failure is None and quotes == svc._snapshot_quotes(books(100))
    assert len(ticks) - before >= 3  # 100 books = 4 batches of 32, 3 yields


@pytest.mark.asyncio
async def test_cancel_while_a_snapshot_quote_waits_stops_the_shard(monkeypatch):
    socket = BytesSocket([json.dumps(books(40)).encode()])
    monkeypatch.setattr(websockets, "connect", lambda *_a, **_kw: socket)
    seen, entered, unwound = [], asyncio.Event(), []

    async def on_price(quote):
        seen.append(quote["asset_id"])
        entered.set()
        try:
            await socket.forever.wait()
        except asyncio.CancelledError:
            unwound.append(quote["asset_id"])
            raise

    client = svc.PolymarketWebSocket(price_book_snapshots=True)
    client.on_price = on_price
    task = asyncio.create_task(client._run_one(["asset-0"], 0))
    await asyncio.wait_for(entered.wait(), 2)
    assert client.is_connected
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    # The waiting callback unwinds, no later quote is handed on, the shard is
    # down and the cancellation reached the caller (no redial).
    assert seen == unwound == ["asset-0"]
    assert client._book_snapshot_quotes == 1
    assert not client.is_connected
