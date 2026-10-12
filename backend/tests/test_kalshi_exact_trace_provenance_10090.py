"""#10090 — the exact trace links a quote's original receipt to the object the
handler actually read, or says it cannot.

Production trace `72d3b6d2` (exact-input-aftercheck, 10/11) logged 272
DECISION rows with `receive_id: UNAVAILABLE` beside 9 that kept it: with the
order book on, a ticker summary reaches `handle_ticker` as `_overlay_ticker`'s
COPY, and a book-derived best quote reaches it with no receipt at all. The
receipt map was keyed by `id()` without holding the object, so a pending entry
outlived its frame and a later object at the recycled address could inherit
another frame's receipt and prices. Here the actual service, book and handler
run with the trace on and off.
"""

import asyncio
from contextlib import asynccontextmanager
import json

import pytest
import websockets

import app.services.kalshi_ws as service
from tests.test_kalshi_changed_scope_continuity_10090 import _until
from tests.test_kalshi_direct_book_10090 import Wire, _delta, _snapshot
from tests.test_kalshi_exact_trace_10702 import TICKER, handler, trace_for


def ticking_trace():
    """`trace_for` with a monotonic clock that advances on every read, so a
    receipt stamped at arrival is distinguishable from the decision."""
    trace, records, clock = trace_for(limit=256)
    ticks = iter(range(10, 10**6))
    trace.mono = lambda: next(ticks)
    trace.deadline = 10**9
    return trace, records


async def run_socket(monkeypatch, trace, script):
    monkeypatch.setenv("KALSHI_API_KEY_ID", "control")
    monkeypatch.setattr(service, "_load_rsa_key", lambda: object())
    monkeypatch.setattr(service, "_sign_ws_request", lambda *_: {})
    wires = []

    @asynccontextmanager
    async def connect(*_args, **_kwargs):
        wire = Wire()
        wires.append(wire)
        try:
            yield wire
        finally:
            wire.closed = True

    monkeypatch.setattr(websockets, "connect", connect)
    ns = handler(trace)
    sock = service.KalshiWebSocket()
    sock.exact_trace = trace
    sock.on_ticker = ns["handle_ticker"]
    sock.book_tickers = frozenset({TICKER})
    running = asyncio.create_task(sock.run(market_tickers=[TICKER]))
    try:
        await _until(lambda: wires and len(wires[0].commands) == 3, "subscriptions")
        wire = wires[0]
        book = wire.book_subscribe()
        await _until(lambda: sock.is_subscribed, "the price channels' ACK")
        await wire.respond(book, "subscribed")
        await script(wire, book["id"], ns)
    finally:
        running.cancel()
        with pytest.raises(asyncio.CancelledError):
            await running
    return ns


async def _settled(ns, count):
    await _until(lambda: ns["tail_receipts"]._seq >= count, f"{count} accepted quotes")


async def script(wire, sid, ns):
    # 1. A book snapshot: the changed best quote 84/85, straight from the book.
    await wire.frame(_snapshot(1, sid=sid, ticker=TICKER))
    await _settled(ns, 1)
    # 2. A delayed summary 80/90: its trade stands, the book's BBO overlays it.
    await wire.deliver("ticker", {"market_ticker": TICKER, "price_dollars": "0.84",
                                  "yes_bid_dollars": "0.80", "yes_ask_dollars": "0.90",
                                  "ts": 1791532615})
    await _settled(ns, 2)
    # 3. Deep-book churn moves no best quote: nothing dispatched.
    await wire.frame(_delta(2, "0.80", "12", sid=sid, ticker=TICKER))
    # 4. The bid leaves 0.84: book-derived 83/85 with the genuine last trade.
    await wire.frame(_delta(3, "0.84", "-3", sid=sid, ticker=TICKER))
    await _settled(ns, 3)


def by_receipt(records):
    received = {r["receive_id"]: r for r in records if r["stage"] == "RECEIVED"}
    decisions = [r for r in records if r["stage"] == "DECISION"]
    return received, decisions


async def test_every_dispatched_quote_keeps_its_own_original_receipt(monkeypatch):
    trace, records = ticking_trace()
    ns = await run_socket(monkeypatch, trace, script)
    received, decisions = by_receipt(records)

    assert [d["reason"] for d in decisions] == ["ACCEPTED"] * 3
    assert all(d["receive_id"] != "UNAVAILABLE" for d in decisions), decisions
    assert [d["dispatch"] for d in decisions] == [
        "ORDERBOOK_DERIVED", "TICKER_BOOK_OVERLAY", "ORDERBOOK_DERIVED",
    ]
    snap, summary, delta = (received[d["receive_id"]] for d in decisions)

    # A book frame's receipt is a book frame, never a ticker price.
    assert snap["source"] == delta["source"] == "ORDERBOOK_FRAME"
    assert (snap["book_kind"], snap["seq"]) == ("orderbook_snapshot", 1)
    assert (delta["book_kind"], delta["seq"]) == ("orderbook_delta", 3)
    assert snap["prices"] == delta["prices"] == {}
    assert delta["vendor_clock"] == {"ts_ms": 1791532615415}
    assert decisions[0]["dispatched_prices"] == {
        "yes_bid_dollars": 0.84, "yes_ask_dollars": 0.85,
    }
    assert decisions[2]["dispatched_prices"] == {
        "yes_bid_dollars": 0.83, "yes_ask_dollars": 0.85, "price_dollars": 0.84,
    }
    # The summary's receipt keeps what arrived; the decision shows the overlay.
    assert summary["source"] == "TICKER"
    assert summary["prices"] == {"price_dollars": 0.84, "yes_bid_dollars": 0.8,
                                 "yes_ask_dollars": 0.9}
    assert summary["vendor_clock"] == {"ts": 1791532615}
    assert decisions[1]["dispatched_prices"] == {
        "price_dollars": 0.84, "yes_bid_dollars": 0.84, "yes_ask_dollars": 0.85,
    }
    # Receipt clocks are the arrival's, before the decision; ids are distinct.
    for decision in decisions:
        assert received[decision["receive_id"]]["receive_mono"] < decision["receive_mono"]
    assert len({d["receive_id"] for d in decisions}) == 3
    # The accepted-input mark joins the same receipt.
    marks = ns["tail_receipts"]
    assert decisions[-1]["input_seq"] == marks._seq
    # Churn that dispatched nothing leaves no pending receipt behind.
    assert not trace.receives


async def test_trace_changes_no_price_mark_or_callback(monkeypatch):
    trace, _ = ticking_trace()
    on = await run_socket(monkeypatch, trace, script)
    off = await run_socket(monkeypatch, None, script)
    assert on["price_buffer"] == off["price_buffer"]
    assert on["tail_receipts"]._seq == off["tail_receipts"]._seq == 3
    assert set(on["winner_quoted_at"]) == set(off["winner_quoted_at"]) == {900}
    assert [
        (m.outcome_id, m.probability) for m in on["input_marks"].values()
    ] == [(m.outcome_id, m.probability) for m in off["input_marks"].values()]


async def test_a_refused_book_quote_is_recorded_with_its_book_receipt():
    trace, records = ticking_trace()
    ns = handler(trace)
    frame = _snapshot(1, sid=1, ticker=TICKER, yes=(("0.10", "1"),), no=(("0.10", "1"),))
    trace.book_received("socket", frame)
    quote = {"market_ticker": TICKER, "yes_bid_dollars": "0.10", "yes_ask_dollars": "0.90"}
    trace.derived(frame, quote, "ORDERBOOK_DERIVED")
    await ns["handle_ticker"](quote)
    received, decisions = by_receipt(records)
    assert decisions[-1]["reason"] == "PRICE_POLICY_REFUSED"
    assert decisions[-1]["dispatch"] == "ORDERBOOK_DERIVED"
    assert received[decisions[-1]["receive_id"]]["source"] == "ORDERBOOK_FRAME"
    assert not ns["price_buffer"]


def test_a_quote_with_no_exact_receipt_is_unavailable_never_borrowed():
    trace, records = ticking_trace()
    # A summary received, then copied: the copy dies undecided.
    original = {"market_ticker": TICKER, "price_dollars": "0.84"}
    stale = id(original)
    trace.received("socket", original)
    del original
    # A later object at the recycled address must not inherit that receipt.
    kept, collided = [], None
    for _ in range(2000):
        candidate = {"market_ticker": TICKER, "yes_bid_dollars": "0.10"}
        if id(candidate) == stale:
            collided = candidate
            break
        kept.append(candidate)
    later = collided or {"market_ticker": TICKER, "yes_bid_dollars": "0.10"}
    trace.decided(later, reason="UNMAPPED")
    decision = records[-1]
    assert decision["stage"] == "DECISION" and decision["reason"] == "UNMAPPED"
    assert decision["receive_id"] == "UNAVAILABLE", (
        f"borrowed receipt (address recycled: {collided is not None})"
    )
    assert (decision["source"], decision["dispatch"]) == ("UNAVAILABLE", "UNAVAILABLE")


def test_book_frames_for_other_tickers_or_no_quote_retain_nothing():
    trace, records = ticking_trace()
    other = _snapshot(1, sid=1, ticker="OTHER-TICKER")
    trace.book_received("socket", other)
    assert not trace.receives
    frame = _snapshot(2, sid=1, ticker=TICKER)
    trace.book_received("socket", frame)
    trace.derived(frame, None, "ORDERBOOK_DERIVED")
    assert not trace.receives
    assert [r["stage"] for r in records] == ["START"]  # receipts cost no lines


def test_pending_receipts_are_bounded_and_erased_on_stop():
    trace, records = ticking_trace()
    frames = [_snapshot(n, sid=1, ticker=TICKER) for n in range(100)]
    for frame in frames:
        trace.book_received("socket", frame)
    assert len(trace.receives) <= 64
    trace.expiry = 0
    assert not trace.active()
    assert not trace.receives and records[-1]["stage"] == "STOP"
