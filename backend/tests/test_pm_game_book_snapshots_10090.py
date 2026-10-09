"""Game reconnect snapshots reach the real consumer's existing quote guards.

Only database reads, transport and persistence scheduling are faked. The
consumer, service decoding/dispatch, callback, routing and input marks are real.
Buffer observation happens when the service requests its next wire frame,
after it has dispatched the preceding frame. No later trade or quote rescues
the changed reconnect book. This proves buffering, not production delivery.
"""

import asyncio
import json
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
import websockets

import app.services.polymarket_ws as service
import app.tasks.live_blend_refresh as blend
import app.tasks.polymarket_ws as task


def _cells(callback):
    return dict(zip(callback.__code__.co_freevars, callback.__closure__))


def _book(asset="111", bids=(".60", ".20"), asks=(".90", ".62")):
    return dict(
        event_type="book", asset_id=asset, market="0xabc",
        bids=[{"price": p, "size": "100"} for p in bids],
        asks=[{"price": p, "size": "100"} for p in asks],
        timestamp="1791576000123",
    )


async def _reconnect(monkeypatch, frame, *, flag="1", stale=False):
    monkeypatch.setenv("POLYMARKET_WS_BOOK_SNAPSHOT_PRICES", flag)
    monkeypatch.setenv("POLYMARKET_WS_OPEN_CONTRACT_PRICES", "0")
    monkeypatch.setattr(task, "SUBSCRIPTION_REFRESH_SECONDS", 30)
    monkeypatch.setattr(service, "_jittered", lambda _: 0)
    stop, completed = asyncio.Event(), asyncio.Event()
    clients, observations, subscriptions = [], [], []

    class ObservedClient(service.PolymarketWebSocket):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            clients.append(self)

    monkeypatch.setattr(service, "PolymarketWebSocket", ObservedClient)

    # Suspend writes: the subject is admission into the existing game buffer.
    # At the persistence boundary below the observed buffers are cleared so
    # shutdown cannot write them through this read-only database fixture.
    async def hold_flush(_flush, _period, *, stop, **_kwargs):
        await stop.wait()

    monkeypatch.setattr(blend, "run_flush_cadence", hold_flush)

    slate = iter([
        [(71, 7, "0xabc_yes", "0xabc", 900),
         (72, 7, "0xabc_no", "0xabc", 900)],
        [(7, "0xabc", {"clob_token_ids": ["111", "222"]}, "scheduled")],
        [(71, 7, "0xabc_yes"), (72, 7, "0xabc_no")],
    ])

    class Session:
        async def execute(self, _statement):
            rows = next(slate, [])
            return SimpleNamespace(all=lambda: rows)

    @asynccontextmanager
    async def session():
        yield Session()

    def observe():
        cells = _cells(clients[0].on_price)
        marks = _cells(cells["_mark_input"].cell_contents)["input_marks"].cell_contents
        observations.append(dict(
            prices=dict(cells["price_buffer"].cell_contents),
            withdrawals=dict(cells["withdraw_buffer"].cell_contents),
            marks=dict(marks),
        ))
        return cells

    connections = 0

    class Socket:
        def __init__(self, number):
            self.number, self.sent = number, False

        async def send(self, payload):
            if payload != "PING":
                subscriptions.append(json.loads(payload))

        def __aiter__(self):
            return self

        async def __anext__(self):
            if not self.sent:
                self.sent = True
                if self.number == 1:
                    return json.dumps(dict(
                        event_type="best_bid_ask", asset_id="111",
                        best_bid=".40", best_ask=".42", timestamp="1791576000000",
                    ))
                if stale:
                    cells = _cells(clients[0].on_price)
                    lock = cells["buffer_lock"].cell_contents
                    await lock.acquire()

                    async def handover():
                        # Dispatch starts inline until the old generation waits
                        # on this lock; a catalog handover wins that wait.
                        cells["routing_generation"].cell_contents += 1
                        lock.release()

                    asyncio.create_task(handover())
                return json.dumps(frame)
            cells = observe()
            if self.number == 1:
                # A real clean close makes _run_one reconnect its own shard.
                raise StopAsyncIteration
            cells["price_buffer"].cell_contents.clear()
            cells["withdraw_buffer"].cell_contents.clear()
            completed.set()
            stop.set()
            await asyncio.Event().wait()

    @asynccontextmanager
    async def connect(*_args, **_kwargs):
        nonlocal connections
        connections += 1
        yield Socket(connections)

    monkeypatch.setattr(websockets, "connect", connect)
    consumer = asyncio.create_task(task._run_polymarket_ws_consumer.__wrapped__(
        sessions=SimpleNamespace(session=session), stop=stop,
    ))
    try:
        await asyncio.wait_for(completed.wait(), 5)
        result = await asyncio.wait_for(consumer, 5)
    finally:
        if not consumer.done():
            consumer.cancel()
            await asyncio.gather(consumer, return_exceptions=True)
    assert connections == 2
    assert [s["assets_ids"] for s in subscriptions] == [["111", "222"]] * 2
    assert clients[0].stats["messages"] == 2
    assert result["status"] == "stopped"
    assert observations[0]["prices"] == {71: pytest.approx(.41)}
    return observations[-1], clients[0]


async def test_reconnect_book_catches_up_without_a_later_tick(monkeypatch):
    observed, client = await _reconnect(
        monkeypatch, [_book(), _book("222", (".38",), (".40",))],
    )
    assert observed["prices"] == {71: pytest.approx(.61), 72: pytest.approx(.39)}
    assert observed["withdrawals"] == {}
    assert {mark.venue_ts_ms for mark in observed["marks"].values()} == {1791576000123}
    assert client.stats["book_snapshot_quotes"] == 2


async def test_flag_off_keeps_the_previous_game_price(monkeypatch):
    observed, client = await _reconnect(monkeypatch, [_book()], flag="0")
    assert observed["prices"] == {71: pytest.approx(.41)}
    assert client.stats["book_snapshot_quotes"] == 0


@pytest.mark.parametrize("frame", [
    [_book(asks=())],
    [_book(bids=("bad",))],
    [_book(bids=("1.0",), asks=("1.0",))],
    [_book("unmapped")],
])
async def test_invalid_or_unmapped_snapshot_does_not_price_a_game(monkeypatch, frame):
    observed, _ = await _reconnect(monkeypatch, frame)
    assert observed["prices"] == {71: pytest.approx(.41)}
    assert observed["marks"][71].venue_ts_ms == 1791576000000


async def test_wide_snapshot_uses_existing_withdrawal_policy(monkeypatch):
    observed, _ = await _reconnect(monkeypatch, [_book(bids=(".1",), asks=(".9",))])
    assert observed["prices"] == {71: pytest.approx(.41)}
    assert observed["withdrawals"] == {71: (.1, .9)}
    assert observed["marks"][71].venue_ts_ms == 1791576000000


async def test_snapshot_waiting_on_old_routing_cannot_price_new_catalog(monkeypatch):
    observed, _ = await _reconnect(monkeypatch, [_book()], stale=True)
    assert observed["prices"] == {71: pytest.approx(.41)}
    assert observed["marks"][71].venue_ts_ms == 1791576000000
