"""A buffered book dump must let an unrelated ready task make progress."""

import asyncio

import pytest

from app.services.polymarket_ws import PolymarketWebSocket, _snapshot_quotes


def books(count):
    return [
        dict(
            asset_id=f"asset-{i}",
            bids=[{"price": ".4"}],
            asks=[{"price": ".6"}],
            timestamp="1791346500000",
            market=f"market-{i}",
        )
        for i in range(count)
    ]


async def test_large_dump_allows_companion_before_all_books_finish():
    socket = PolymarketWebSocket(price_book_snapshots=True)
    seen, progress = [], []
    first = asyncio.Event()

    async def on_price(frame):  # An async callback need not actually suspend.
        seen.append(frame)
        first.set()

    async def companion():
        await first.wait()
        progress.append(len(seen))

    socket.on_price = on_price
    observer = asyncio.create_task(companion())
    await socket._price_snapshot(books(65))
    await observer
    assert 0 < progress[0] < 65
    assert seen == _snapshot_quotes(books(65))
    assert socket._book_snapshot_quotes == 65


async def test_cancellation_can_stop_a_large_dump_before_it_is_fully_dispatched():
    socket = PolymarketWebSocket(price_book_snapshots=True)
    seen = []
    first = asyncio.Event()

    def on_price(frame):
        seen.append(frame)
        first.set()

    socket.on_price = on_price
    task = asyncio.create_task(socket._price_snapshot(books(500)))
    await first.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert 0 < len(seen) < 500


@pytest.mark.parametrize("count", [0, 1, 31, 32, 33, 65])
async def test_snapshot_payloads_order_and_skips_match_existing_contract(count):
    socket = PolymarketWebSocket(price_book_snapshots=True)
    seen = []
    socket.on_price = seen.append
    data = [None, {}, *books(count), {"asset_id": "empty", "bids": [], "asks": []}]
    await socket._price_snapshot(data)
    assert seen == _snapshot_quotes(data)
    assert socket._book_snapshot_quotes == count


async def test_one_callback_failure_still_allows_later_books(caplog):
    socket = PolymarketWebSocket(price_book_snapshots=True)
    seen = []

    def on_price(frame):
        if frame["asset_id"] == "asset-1":
            raise ValueError("deliberate callback failure")
        seen.append(frame)

    socket.on_price = on_price
    await socket._price_snapshot(books(65))
    assert [frame["asset_id"] for frame in seen] == [
        f"asset-{i}" for i in range(65) if i != 1
    ]
    assert socket._book_snapshot_quotes == 65
    assert "Polymarket book snapshot price handler error" in caplog.text


async def test_unextractable_book_still_raises_after_earlier_batches_dispatch():
    # A side that is not iterable raises inside extraction, which never
    # swallowed it: the shard's receive loop reconnects, as before. Batching
    # only means the books ahead of the bad batch were already priced.
    socket = PolymarketWebSocket(price_book_snapshots=True)
    seen = []
    socket.on_price = seen.append
    data = [*books(40), {"asset_id": "bad", "bids": 5, "asks": []}]
    with pytest.raises(TypeError):
        await socket._price_snapshot(data)
    assert [frame["asset_id"] for frame in seen] == [f"asset-{i}" for i in range(32)]
    assert socket._book_snapshot_quotes == 32
