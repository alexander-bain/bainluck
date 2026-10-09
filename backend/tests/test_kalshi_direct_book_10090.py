"""#10090 — a changed Kalshi best quote enters the writer from the order book,
before the batched ticker summary that would carry it ~0.5–0.8 s later.

Zverev–Wu, 10/09 07:56Z (Root's same-socket read): the 83/84 quote was in the
reconstructed book 812 ms before the ticker summary carried it. Here the actual
service subscribes the live winner legs' books, a book change reaches the
ordered price callback with the genuine last trade (never an invented one), a
delayed summary cannot overwrite the newer book, a gap asks for a snapshot and
falls back to the summary meanwhile, membership follows the population, and a
rejected book never blocks readiness.
"""

import asyncio
import json
from contextlib import asynccontextmanager

import pytest
import websockets

import app.services.kalshi_ws as service
import app.tasks.kalshi_ws as task
from tests.test_kalshi_changed_scope_continuity_10090 import (
    GAME_A, Scope, Socket, _rig, _stop, _until,
)

ZVE = "KXATPMATCH-26OCT09ZVEYIB-ZVE"


def _snapshot(seq, *, sid, ticker=ZVE, yes=(("0.83", "10"), ("0.84", "3")), no=(("0.15", "5"),)):
    return {"type": "orderbook_snapshot", "sid": sid, "seq": seq, "msg": {
        "market_ticker": ticker,
        "yes_dollars_fp": [list(level) for level in yes],
        "no_dollars_fp": [list(level) for level in no],
    }}


def _delta(seq, price, quantity, side="yes", *, sid, ticker=ZVE):
    return {"type": "orderbook_delta", "sid": sid, "seq": seq, "msg": {
        "market_ticker": ticker, "side": side, "price_dollars": price,
        "delta_fp": quantity, "ts_ms": 1791532615415,
    }}


class Wire(Socket):
    """Kalshi's socket: acknowledges the price channels; the control answers
    the order book subscription itself."""

    async def send(self, raw):
        command = json.loads(raw)
        self.commands.append(command)
        if command["cmd"] == "subscribe" and command["params"]["channels"] != ["orderbook_delta"]:
            await self.respond(command, "subscribed")

    async def frame(self, envelope):
        await self._put(json.dumps(envelope))
        target = self.queued
        await _until(lambda: self.done >= target, f"{envelope['type']} to be processed")

    def book_subscribe(self):
        return next(c for c in self.commands
                    if c["params"].get("channels") == ["orderbook_delta"])

    def updates(self, action):
        return [c["params"] for c in self.commands
                if c["cmd"] == "update_subscription" and c["params"]["action"] == action]


async def _service(monkeypatch, book_tickers):
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
    seen = []

    async def on_ticker(payload):
        seen.append(dict(payload))

    sock = service.KalshiWebSocket()
    sock.on_ticker = on_ticker
    sock.book_tickers = frozenset(book_tickers)
    run = asyncio.create_task(sock.run(market_tickers=[ZVE]))
    await _until(lambda: wires and len(wires[0].commands) == 3, "three subscriptions")
    return sock, run, wires[0], seen


@pytest.mark.asyncio
async def test_book_quote_reaches_the_price_callback_before_the_summary(monkeypatch):
    sock, run, wire, seen = await _service(monkeypatch, {ZVE})
    try:
        book = wire.book_subscribe()
        assert book["params"]["market_tickers"] == [ZVE]
        await _until(lambda: sock.is_subscribed, "the price channels' ACK")
        await wire.respond(book, "subscribed")  # sid = the command id
        sid = book["id"]

        await wire.frame(_snapshot(1, sid=sid))
        assert seen[-1] == {"market_ticker": ZVE, "yes_bid_dollars": "0.84",
                            "yes_ask_dollars": "0.85"}  # no trade invented
        # A summary: its genuine trade stands, its BBO is the book's.
        await wire.deliver("ticker", {"market_ticker": ZVE, "price_dollars": "0.84",
                                      "yes_bid_dollars": "0.84", "yes_ask_dollars": "0.85"})
        assert seen[-1]["price_dollars"] == "0.84"

        # The 83/84 quote: from the book, now, with the genuine last trade.
        await wire.frame(_delta(2, "0.84", "-3", sid=sid))
        await wire.frame(_delta(3, "0.16", "4", side="no", sid=sid))
        assert seen[-1] == {"market_ticker": ZVE, "yes_bid_dollars": "0.83",
                            "yes_ask_dollars": "0.84", "ts_ms": 1791532615415,
                            "price_dollars": "0.84"}
        # Deep-book churn moves nothing.
        count = len(seen)
        await wire.frame(_delta(4, "0.80", "12", sid=sid))
        assert len(seen) == count
        # The delayed summary still showing 84/85 cannot overwrite the book.
        await wire.deliver("ticker", {"market_ticker": ZVE, "price_dollars": "0.84",
                                      "yes_bid_dollars": "0.84", "yes_ask_dollars": "0.85"})
        assert (seen[-1]["yes_bid_dollars"], seen[-1]["yes_ask_dollars"]) == ("0.83", "0.84")

        # A sequence gap: a snapshot is requested and the summary stands alone.
        await wire.frame(_delta(9, "0.84", "1", sid=sid))
        assert wire.updates("get_snapshot") == [
            {"sids": [sid], "market_tickers": [ZVE], "action": "get_snapshot"},
        ]
        await wire.deliver("ticker", {"market_ticker": ZVE, "price_dollars": "0.85",
                                      "yes_bid_dollars": "0.85", "yes_ask_dollars": "0.86"})
        assert seen[-1]["yes_bid_dollars"] == "0.85"
        await wire.frame(_snapshot(10, sid=sid, yes=(("0.86", "1"),), no=(("0.13", "2"),)))
        assert seen[-1]["yes_bid_dollars"] == "0.86" and seen[-1]["price_dollars"] == "0.85"

        # Membership follows the population: a departed ticker is forgotten.
        await sock.set_book_tickers(set())
        assert wire.updates("delete_markets") == [
            {"sids": [sid], "market_tickers": [ZVE], "action": "delete_markets"},
        ]
        # A snapshot already queued before deletion cannot recreate an overlay.
        count = len(seen)
        await wire.frame(_snapshot(11, sid=sid))
        assert len(seen) == count
        await wire.deliver("ticker", {"market_ticker": ZVE, "price_dollars": "0.85",
                                      "yes_bid_dollars": "0.80", "yes_ask_dollars": "0.82"})
        assert seen[-1]["yes_bid_dollars"] == "0.80"
        assert sock.stats["book_quotes"] == 4 and sock.stats["book_resnapshots"] == 1
    finally:
        run.cancel()
        await asyncio.gather(run, return_exceptions=True)


@pytest.mark.asyncio
async def test_rejected_membership_update_discards_cached_book_overlay(monkeypatch):
    sock, run, wire, seen = await _service(monkeypatch, {ZVE})
    try:
        book = wire.book_subscribe()
        await wire.respond(book, "subscribed")
        await wire.frame(_snapshot(1, sid=book["id"]))
        await sock.set_book_tickers({ZVE, "GAME-B"})
        command = wire.commands[-1]
        assert command["params"]["action"] == "add_markets"
        await wire.respond(command, "error")
        summary = {"market_ticker": ZVE, "price_dollars": "0.91",
                   "yes_bid_dollars": "0.90", "yes_ask_dollars": "0.92"}
        await wire.deliver("ticker", summary)
        assert seen[-1] == summary
        assert sock.is_subscribed
    finally:
        run.cancel()
        await asyncio.gather(run, return_exceptions=True)


@pytest.mark.asyncio
async def test_a_rejected_book_leaves_ticker_summaries_and_readiness_alone(monkeypatch):
    sock, run, wire, seen = await _service(monkeypatch, {ZVE})
    try:
        await wire.respond(wire.book_subscribe(), "error")
        await _until(lambda: sock.is_subscribed, "readiness without the book")
        summary = {"market_ticker": ZVE, "price_dollars": "0.84",
                   "yes_bid_dollars": "0.84", "yes_ask_dollars": "0.85"}
        await wire.deliver("ticker", dict(summary))
        await wire.frame(_snapshot(1, sid=99))
        assert seen == [summary]
        assert not sock.subscription_failed(0)
    finally:
        run.cancel()
        await asyncio.gather(run, return_exceptions=True)


@pytest.mark.asyncio
async def test_the_live_winner_legs_book_quote_is_written(monkeypatch):
    """The actual consumer: the live event's winner leg gets a book (none
    while the switch is off), and the book's midpoint is what the writer
    stores even after a delayed summary."""
    monkeypatch.setenv("KALSHI_WS_DIRECT_BOOK", "1")
    scope = Scope()
    running, sockets, _acking, socket_for, opened_sockets = _rig(monkeypatch, scope)
    try:
        await _until(lambda: opened_sockets() == 3, "startup sockets")
        game = socket_for({GAME_A})

        def book_command():
            return next((c for c in game.commands
                         if c["params"].get("channels") == ["orderbook_delta"]), None)

        await _until(lambda: book_command() is not None, "the live leg's book")
        assert book_command()["params"]["market_tickers"] == [GAME_A]
        sid = 41
        await game._put(json.dumps({"id": book_command()["id"], "type": "subscribed",
                                    "msg": {"channel": "orderbook_delta", "sid": sid}}))
        await game.deliver("ticker", {"market_ticker": GAME_A, "price_dollars": "0.60",
                                      "yes_bid_dollars": "0.59", "yes_ask_dollars": "0.61"})
        snapshot = _snapshot(1, sid=sid, ticker=GAME_A,
                             yes=(("0.65", "10"),), no=(("0.33", "10"),))
        await game._put(json.dumps(snapshot))
        await game.deliver("ticker", {"market_ticker": GAME_A, "price_dollars": "0.60",
                                      "yes_bid_dollars": "0.59", "yes_ask_dollars": "0.61"})

        monkeypatch.setenv("WS_OPEN_CONTRACT_SETTLEMENT", "0")
        stats = await asyncio.wait_for(running, 10)
        assert stats["book_tickers"] == 1
        assert scope.written[71][0] == pytest.approx(0.66)  # the book's 65/67
        assert all(s.closed for s in sockets)
    finally:
        await _stop(running)


def test_population_switch_is_off_by_default(monkeypatch):
    monkeypatch.delenv("KALSHI_WS_DIRECT_BOOK", raising=False)
    assert task.kalshi_direct_book_enabled() is False
    monkeypatch.setenv("KALSHI_WS_DIRECT_BOOK", "1")
    assert task.kalshi_direct_book_enabled() is True
    monkeypatch.setenv("KALSHI_WS_BOOK_MAX_TICKERS", "nope")
    assert task.kalshi_book_max_tickers() == 200
