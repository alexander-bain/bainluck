"""A delayed Polymarket trade cannot replace its token's newer tight book."""

import json
from types import SimpleNamespace

import pytest

from tests.test_pm_idle_wake_10090 import callbacks
from tests.test_pm_repeat_skip_10090 import callbacks as repeat_callbacks
from tests.test_poly_ws_min_order_trade_9733 import YES_LEG, YES_TOKEN, _run


TRADE_TIME = "1720000123456"
BOOK_TIME = "1720000123457"


def _book(asset, time=BOOK_TIME, bid="0.14", ask="0.16"):
    return {
        "event_type": "best_bid_ask",
        "asset_id": asset,
        "best_bid": bid,
        "best_ask": ask,
        "timestamp": time,
    }


def _trade(asset, time=TRADE_TIME, price="0.71"):
    return {
        "event_type": "last_trade_price",
        "asset_id": asset,
        "price": price,
        "size": "10",
        "timestamp": time,
    }


async def test_a_delayed_fill_cannot_replace_the_midpoint_at_flush(monkeypatch):
    monkeypatch.setenv("POLYMARKET_WS_OPEN_CONTRACT_PRICES", "0")
    writes, stats = await _run(
        monkeypatch,
        [json.dumps(frame) for frame in (_book(YES_TOKEN), _trade(YES_TOKEN))],
    )
    assert writes == [(YES_LEG, pytest.approx(0.15))]
    assert stats["trade_updates"] == 0
    assert stats["trades_older_than_tight_book"] == 1


@pytest.mark.parametrize(
    ("asset", "expected"),
    [("yes", {1: 0.15, 2: 0.85}), ("open", {900: 0.15, 901: 0.85})],
)
async def test_newer_book_protects_the_buffer_and_complements(asset, expected):
    consumer, marks = callbacks()
    previews = {}
    consumer.ns["blend_refresher"].market_preview = SimpleNamespace(
        note=lambda _market, outcome, probability: previews.update({outcome: probability})
    )
    await consumer.ns["handle_price"](_book(asset, "1720000123455"))
    await consumer.ns["handle_price"](_book(asset))
    await consumer.ns["handle_trade"](_trade(asset))

    assert consumer.ns["price_buffer"] == pytest.approx(expected)
    assert previews == pytest.approx(expected)
    assert all(mark[3] == "price" for mark in marks)


async def test_an_unchanged_book_keeps_its_venue_clock_on_the_repeat_shortcut(monkeypatch):
    rig = repeat_callbacks(monkeypatch)
    await rig.ns["handle_price"](_book("yes", "1720000123455"))
    rig.clock.t += 0.1
    await rig.ns["handle_price"](_book("yes"))
    await rig.ns["handle_trade"](_trade("yes"))

    assert rig.ns["stats"]["repeats_skipped"] == 1
    assert rig.ns["price_buffer"] == pytest.approx({1: 0.15, 2: 0.85})


async def test_standalone_flush_stores_the_book_for_both_open_legs():
    consumer, _ = callbacks()
    flushed = {}
    write = consumer.ns["write_chunk"]

    async def record_write(chunk, **kwargs):
        flushed.update(chunk)
        return await write(chunk, **kwargs)

    consumer.ns["write_chunk"] = record_write
    await consumer.ns["handle_price"](_book("open"))
    await consumer.ns["handle_trade"](_trade("open"))
    assert await consumer.ns["flush_standalone"](flush_started=1000)
    assert flushed == pytest.approx({900: 0.15, 901: 0.85})


@pytest.mark.parametrize(
    ("book_time", "trade_time"),
    [
        (TRADE_TIME, BOOK_TIME),  # A newer genuine sweep still prices.
        (BOOK_TIME, BOOK_TIME),
        (BOOK_TIME, None),
        (BOOK_TIME, "1720000123"),
        (BOOK_TIME, True),
        (None, TRADE_TIME),
    ],
)
async def test_a_trade_without_a_provably_newer_book_keeps_its_existing_eligibility(
    book_time, trade_time,
):
    consumer, _ = callbacks()
    await consumer.ns["handle_price"](_book("open", book_time))
    await consumer.ns["handle_trade"](_trade("open", trade_time))

    assert consumer.ns["price_buffer"] == pytest.approx({900: 0.71, 901: 0.29})


@pytest.mark.parametrize(
    "new_book",
    [
        _book("open", time=None),
        _book("open", time="bad clock"),
        _book("open", bid="bad bid"),
        _book("open", bid=None),
        _book("open", bid="0.18", ask="0.16"),
    ],
)
async def test_ineligible_new_book_clears_the_dated_tight_witness(new_book):
    consumer, _ = callbacks()
    await consumer.ns["handle_price"](_book("open"))
    await consumer.ns["handle_price"](new_book)
    await consumer.ns["handle_trade"](_trade("open"))

    assert consumer.ns["price_buffer"] == pytest.approx({900: 0.71, 901: 0.29})


async def test_a_newer_wide_book_keeps_the_existing_trade_rule():
    consumer, _ = callbacks()
    await consumer.ns["handle_price"](_book("open", bid="0.12", ask="0.73"))
    await consumer.ns["handle_trade"](_trade("open", price="0.72"))

    assert consumer.ns["price_buffer"] == pytest.approx({900: 0.72, 901: 0.28})
