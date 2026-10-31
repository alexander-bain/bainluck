"""#10090 — Kalshi "skip what changes nothing" (`KALSHI_WS_REPEAT_SKIP_MS`).

A book observation (a delta that left the best prices where they were) or a
ticker input whose reading repeats what the consumer last fully handled for the
ticker, on the same connection and inside the window, feeds only "confirmed
at". Everything a reader can see is already in place. `0` is today's path.
"""
import ast
import asyncio
import contextlib
import logging
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock

import pytest

import app.tasks.kalshi_ws as consumer
import app.tasks.live_blend_refresh as lbr
from app.services.kalshi_ws import KalshiWebSocket
from app.tasks.live_blend_refresh import TailReceipts
from app.utils.kalshi_orderbook import KalshiOrderBook
from app.utils.kalshi_primary_quote import PrimaryQuoteCustody
from tests.test_fresh_observation_preview_10090 import preview_enabled  # noqa: F401

SOURCE = Path(consumer.__file__)
TICKER = "KXNFLGAME-26OCT30AAABBB-AAA"
W = 0.25


def _nested(names, ns):
    tree = ast.parse(SOURCE.read_text())
    nodes = [n for n in ast.walk(tree)
             if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in names]
    assert {n.name for n in nodes} == set(names) and len(nodes) == len(names)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(SOURCE), "exec"), ns)


class Confirmed:
    """`ConfirmedAt`'s socket side, recorded."""

    def __init__(self):
        self.notes = []

    def note_input(self, event_id, outcome_id, probability, recv_wall):
        self.notes.append((event_id, outcome_id, probability, recv_wall))

    def note_mark(self, mark):
        if mark is not None:
            self.note_input(mark.event_id, mark.outcome_id, mark.probability, mark.recv_wall)


class Clock:
    def __init__(self, monkeypatch):
        self.mono, self.wall = lbr._mono(), lbr._wall()
        monkeypatch.setattr(lbr, "_mono", lambda: self.mono)
        monkeypatch.setattr(lbr, "_wall", lambda: self.wall)

    def advance(self, seconds):
        self.mono += seconds
        self.wall += seconds


def ticker_rig(monkeypatch, *, window=W, preview=False):
    clock = Clock(monkeypatch)
    receipts = TailReceipts("kalshi")
    receipts.confirmed = Confirmed()
    client = NS(sock=NS(_connected_at=1.0, _retiring=False), predecessor=None,
                tickers=frozenset({TICKER}))
    refresher = NS(preview_events={1} if preview else set(), held_quotes=None)
    from app.tasks.kalshi import _kalshi_yes_probability

    ns = dict(vars(consumer), _kalshi_yes_probability=_kalshi_yes_probability)
    ns.update(
        tail_receipts=receipts, ticker_owner={TICKER: client},
        ticker_to_ids={TICKER: (10, 11)}, open_contract_ids={},
        event_id_by_outcome={11: 1}, non_blend_outcome_ids=set(),
        prices=NS(settled_market_ids=set()), primary_quote_custody=PrimaryQuoteCustody(),
        price_buffer={}, input_marks={}, blend_refresher=refresher,
        observation_continuity={}, buffer_lock=asyncio.Lock(), flush_wake=asyncio.Event(),
        winner_quoted_at={}, live_event_ids={1}, admission_wake=asyncio.Event(),
        stats={"repeats_skipped": 0, "observations_skipped": 0},
        repeat_skip_s=window, ticker_memo={}, observation_memo={},
    )
    # Continuity keyed only on what this rig varies (the real one also reads
    # the connection's book signature).
    signature = {"value": object()}
    ns["observation_signature"] = lambda ticker: signature["value"]
    _nested(("handle_ticker", "_parse_dollar", "_skip_ticker_repeat", "_connection_epoch",
             "_same_connection",
             "_forget_repeats", "note_observation_continuity"), ns)
    return NS(ns=ns, clock=clock, receipts=receipts, client=client, signature=signature,
              confirmed=receipts.confirmed)


def quote(bid="0.6100", ask="0.6300", **extra):
    return {"market_ticker": TICKER, "yes_bid_dollars": bid, "yes_ask_dollars": ask, **extra}


async def send(rig, msg=None, *, client=None):
    rig.ns["flush_wake"].clear()
    await rig.ns["handle_ticker"](dict(msg or quote()), client or rig.client)


# ── the switch ───────────────────────────────────────────────────────────────


@pytest.mark.parametrize("raw,expected", [
    (None, 0.25), ("", 0.25), ("  ", 0.25), ("500", 0.5), ("250", 0.25),
    ("0", 0.0), ("-5", 0.0), ("nan", 0.0), ("inf", 0.0), ("abc", 0.0),
])
def test_switch_parses_with_default_on_and_zero_off(monkeypatch, caplog, raw, expected):
    if raw is None:
        monkeypatch.delenv("KALSHI_WS_REPEAT_SKIP_MS", raising=False)
    else:
        monkeypatch.setenv("KALSHI_WS_REPEAT_SKIP_MS", raw)
    with caplog.at_level(logging.WARNING, logger=consumer.logger.name):
        assert consumer._repeat_skip_window_s() == expected
    assert ("not a number" in caplog.text) is (raw == "abc")


# ── ticker inputs ────────────────────────────────────────────────────────────


async def test_a_repeated_ticker_inside_the_window_feeds_only_confirmed_at(monkeypatch):
    rig = ticker_rig(monkeypatch)
    await send(rig)
    assert rig.receipts.stats["inputs"] == 1 and rig.ns["flush_wake"].is_set()
    mark = rig.ns["input_marks"][11]
    rig.clock.advance(0.1)
    rig.ns["winner_quoted_at"][1] = 0.0
    await send(rig)
    assert rig.ns["stats"]["repeats_skipped"] == 1
    # No receipt, mark, wake or re-buffer; the buffered price is the same one.
    assert rig.receipts.stats["inputs"] == 1 and rig.ns["input_marks"][11] is mark
    assert not rig.ns["flush_wake"].is_set()
    assert rig.ns["price_buffer"][11] == (0.62, 0.61, 0.63)
    # "Confirmed at" is fed at this receipt, exactly as the mark would.
    first, second = rig.confirmed.notes
    assert first[:3] == second[:3] == (1, 11, 0.62)
    assert second[3] == rig.clock.wall
    # The winner-quote evidence moves too.
    assert rig.ns["winner_quoted_at"][1] > 0.0


async def test_switch_zero_is_todays_path(monkeypatch):
    rig = ticker_rig(monkeypatch, window=0.0)
    for _ in range(3):
        await send(rig)
        assert rig.ns["flush_wake"].is_set()
    assert rig.receipts.stats["inputs"] == 3
    assert rig.ns["stats"]["repeats_skipped"] == 0 and not rig.ns["ticker_memo"]


async def test_the_window_is_measured_from_the_last_full_handling(monkeypatch):
    rig = ticker_rig(monkeypatch)
    await send(rig)
    rig.clock.advance(0.2)
    await send(rig)  # skipped
    rig.clock.advance(0.05)  # 0.25 after the full handling
    await send(rig)
    assert rig.receipts.stats["inputs"] == 2 and rig.ns["stats"]["repeats_skipped"] == 1
    rig.clock.advance(0.1)
    await send(rig)  # inside the refreshed window
    assert rig.receipts.stats["inputs"] == 2 and rig.ns["stats"]["repeats_skipped"] == 2


@pytest.mark.parametrize("change", [
    "reading", "trade", "snapshot", "connection", "client", "buffer", "settled",
    "identity", "custody", "contract", "continuity", "preview-on",
])
async def test_anything_a_repeat_would_touch_takes_the_full_path(monkeypatch, change):
    rig = ticker_rig(monkeypatch, preview=change == "continuity")
    await send(rig)
    msg = quote()
    client = None
    if change == "reading":
        msg = quote(bid="0.6000")
    elif change == "trade":
        # A wide book whose price is the trade: a new trade is a new reading.
        rig.ns["ticker_memo"].clear()
        await send(rig, quote(bid="0.1000", ask="0.9000", price_dollars="0.5000"))
        msg = quote(bid="0.1000", ask="0.9000", price_dollars="0.5100")
    elif change == "snapshot":
        msg = quote(_book_snapshot=True)
    elif change == "connection":
        rig.client.sock._connected_at = 2.0
    elif change == "client":
        client = NS(sock=NS(_connected_at=1.0), predecessor=rig.client,
                    tickers=frozenset({TICKER}))
    elif change == "buffer":
        rig.ns["price_buffer"][11] = (0.7, 0.69, 0.71)
    elif change == "settled":
        rig.ns["prices"].settled_market_ids.add(10)
    elif change == "identity":
        msg = quote(_primary_quote_identity=("g", 1, "book"), _primary_quote_probability=0.62)
    elif change == "custody":
        rig.ns["primary_quote_custody"].received[11] = (("g", 1, "book"), 0.62)
    elif change == "contract":
        rig.ns["ticker_to_ids"][TICKER] = (10, 12)
        rig.ns["event_id_by_outcome"][12] = 1
    elif change == "continuity":
        rig.ns["observation_continuity"].pop(11)
    elif change == "preview-on":
        rig.ns["blend_refresher"].preview_events = {1}
    before = rig.receipts.stats["inputs"]
    rig.clock.advance(0.05)
    await send(rig, msg, client=client)
    assert rig.receipts.stats["inputs"] == before + 1
    assert rig.ns["stats"]["repeats_skipped"] == 0


async def test_a_preview_leg_with_its_continuity_in_place_is_skipped(monkeypatch):
    rig = ticker_rig(monkeypatch, preview=True)
    await send(rig)
    token = rig.ns["observation_continuity"][11]
    await send(rig)
    assert rig.ns["stats"]["repeats_skipped"] == 1
    assert rig.ns["observation_continuity"][11] is token


async def test_a_snapshot_and_the_input_after_it_are_both_handled(monkeypatch):
    rig = ticker_rig(monkeypatch)
    await send(rig)
    await send(rig, quote(_book_snapshot=True))
    await send(rig)
    assert rig.receipts.stats["inputs"] == 3
    await send(rig)
    assert rig.ns["stats"]["repeats_skipped"] == 1


async def test_a_written_and_gone_price_is_still_a_repeat(monkeypatch):
    rig = ticker_rig(monkeypatch)
    await send(rig)
    rig.ns["price_buffer"].clear()  # the flush wrote it
    await send(rig)
    assert rig.ns["stats"]["repeats_skipped"] == 1 and not rig.ns["price_buffer"]


async def test_a_refused_price_forgets_the_reading(monkeypatch):
    rig = ticker_rig(monkeypatch)
    await send(rig)
    await send(rig, quote(bid=None, ask=None))  # no price
    await send(rig)
    assert rig.receipts.stats["inputs"] == 2 and rig.ns["stats"]["repeats_skipped"] == 0


async def test_an_armed_exact_trace_sees_every_input(monkeypatch):
    rig = ticker_rig(monkeypatch)
    decided = []
    rig.receipts.exact_trace = NS(decided=lambda msg, **kw: decided.append(kw["reason"]))
    await send(rig)
    await send(rig)
    assert decided == ["ACCEPTED", "ACCEPTED"] and rig.ns["stats"]["repeats_skipped"] == 0


async def test_a_skipped_repeat_still_wakes_admission_for_a_not_live_winner(monkeypatch):
    rig = ticker_rig(monkeypatch)
    rig.ns["live_event_ids"].clear()
    await send(rig)
    assert rig.ns["admission_wake"].is_set()
    rig.ns["admission_wake"].clear()
    rig.ns["winner_quoted_at"].pop(1)  # the evidence aged out
    await send(rig)
    assert rig.ns["stats"]["repeats_skipped"] == 1
    assert rig.ns["admission_wake"].is_set() and 1 in rig.ns["winner_quoted_at"]
    assert not rig.ns["flush_wake"].is_set()


async def test_a_non_blend_leg_repeat_feeds_no_confirmed_at(monkeypatch):
    rig = ticker_rig(monkeypatch)
    rig.ns["non_blend_outcome_ids"].add(11)
    await send(rig)
    await send(rig)
    assert rig.ns["stats"]["repeats_skipped"] == 1 and not rig.confirmed.notes


async def test_an_accepted_price_input_clears_the_observation_memo(monkeypatch):
    rig = ticker_rig(monkeypatch)
    rig.ns["observation_memo"][TICKER] = ("anything",)
    await send(rig)
    assert TICKER not in rig.ns["observation_memo"]


# ── book observations ────────────────────────────────────────────────────────


def observation_rig(monkeypatch, *, window=W):
    from tests.test_kalshi_book_observation_10090 import consumer_rig

    rig = consumer_rig(monkeypatch)
    rig.clock = Clock(monkeypatch)
    rig.ns.update(repeat_skip_s=window, observation_memo={}, ticker_memo={},
                  contextlib=contextlib,
                  stats={"repeats_skipped": 0, "observations_skipped": 0})
    _nested(("_connection_epoch", "_same_connection"), rig.ns)
    rig.client.sock._connected_at = 1.0
    rig.client.sock._retiring = False
    rig.confirmed = rig.ns["tail_receipts"].confirmed = Confirmed()
    return rig


async def observe(rig, rounds=1):
    for _ in range(rounds):
        for payload in rig.payloads:
            await rig.ns["handle_book_observation"](dict(payload), rig.client)


async def test_repeated_observations_inside_the_window_feed_only_confirmed_at(monkeypatch):
    from tests.test_blend_preview_display_before_persist_195 import _blends

    rig = observation_rig(monkeypatch)
    legs = len(rig.payloads)
    await observe(rig, rounds=10)
    receipts = rig.ns["tail_receipts"]
    assert receipts.stats["inputs"] == legs
    assert rig.ns["stats"]["observations_skipped"] == 9 * legs
    # Each skipped observation still confirmed its leg at its own receipt.
    assert len(rig.confirmed.notes) == 10 * legs
    assert {n[:2] for n in rig.confirmed.notes} == {(1, row.id) for row in rig.rows}
    # What the observation publishes is unchanged: one coalesced preview.
    assert len(rig.ns["book_observation_pending"]) == legs
    await rig.ns["flush_book_observations"]()
    assert len(_blends(rig.frames)) == 1
    assert not rig.session.updates and not rig.committed


async def test_observation_switch_zero_is_todays_path(monkeypatch):
    rig = observation_rig(monkeypatch, window=0.0)
    await observe(rig, rounds=4)
    assert rig.ns["tail_receipts"].stats["inputs"] == 4 * len(rig.payloads)
    assert rig.ns["stats"]["observations_skipped"] == 0 and not rig.ns["observation_memo"]


@pytest.mark.parametrize("change", [
    "window", "book", "connection", "client", "retiring", "price-input", "rescope",
])
async def test_an_observation_takes_the_full_path_after_any_change(monkeypatch, change):
    rig = observation_rig(monkeypatch)
    await observe(rig)
    client = rig.client
    payloads = rig.payloads
    if change == "window":
        rig.clock.advance(W)
    elif change == "book":
        payloads = [dict(p, yes_bid_dollars=str(float(p["yes_bid_dollars"]) - .01),
                         yes_ask_dollars=str(float(p["yes_ask_dollars"]) + .01))
                    for p in payloads]
    elif change == "connection":
        client.sock._connected_at = 2.0
    elif change == "client":
        client = NS(sock=client.sock)
        for ticker in rig.ns["ticker_owner"]:
            rig.ns["ticker_owner"][ticker] = client
    elif change == "retiring":
        client.sock._retiring = True
    elif change == "price-input":
        for p in payloads:
            rig.ns["observation_memo"].pop(p["market_ticker"])
    elif change == "rescope":
        rig.ns["observation_memo"].clear()
    for payload in payloads:
        await rig.ns["handle_book_observation"](dict(payload), client)
    assert rig.ns["tail_receipts"].stats["inputs"] == 2 * len(rig.payloads)
    assert rig.ns["stats"]["observations_skipped"] == 0


async def test_a_refused_observation_is_never_remembered(monkeypatch):
    rig = observation_rig(monkeypatch)
    # The live book refutes the quote (midpoint moved), so nothing is accepted.
    rig.client.sock.current_book_midpoint = lambda ticker: None
    await observe(rig, rounds=3)
    assert not rig.ns["observation_memo"] and not rig.ns["book_observation_pending"]
    assert rig.ns["stats"]["observations_skipped"] == 0


# ── the service tags snapshots; lifecycle, re-scope and new clients forget ──


async def test_the_socket_tags_a_snapshot_quote_and_never_a_delta():
    from tests.test_kalshi_book_observation_10090 import retained

    fixture = retained()
    seed = fixture["seed"][0]
    ticker = seed["msg"]["market_ticker"]
    sock = KalshiWebSocket()
    sock._book = KalshiOrderBook()
    sock.book_tickers = frozenset({ticker})
    sock._request_resnapshots = AsyncMock()
    delivered = []

    class Dispatch:
        async def submit(self, callback, payload, label, **kw):
            delivered.append(payload)

    sock.on_ticker = delivered.append
    await sock._handle_book_frame(None, deepcopy(seed), Dispatch())
    [snap] = delivered
    assert snap["_book_snapshot"] is True and snap["market_ticker"] == ticker
    # A delta that moves the best bid is a price, not a snapshot.
    best = max(level[0] for level in seed["msg"]["yes_dollars_fp"])
    delta = {"type": "orderbook_delta", "sid": seed["sid"], "seq": seed["seq"] + 1,
             "msg": {"market_ticker": ticker, "price_dollars": best,
                     "delta_fp": "-100000000", "side": "yes"}}
    level = dict(seed["msg"]["yes_dollars_fp"])[best]
    delta["msg"]["delta_fp"] = "-" + level
    await sock._handle_book_frame(None, delta, Dispatch())
    assert len(delivered) == 2 and "_book_snapshot" not in delivered[1]


def _function(name):
    tree = ast.parse(SOURCE.read_text())
    return next(n for n in ast.walk(tree)
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name)


@pytest.mark.parametrize("name", ["handle_lifecycle", "handle_shard_lifecycle"])
def test_a_lifecycle_frame_forgets_its_tickers_repeats_before_anything_else(name):
    """A settle, close or status change is never skipped past."""
    fn = _function(name)
    calls = [n for n in ast.walk(fn) if isinstance(n, ast.Call)
             and getattr(n.func, "id", None) == "_forget_repeats"]
    assert len(calls) == 1
    # Before any await in the handler.
    first_await = min((n.lineno for n in ast.walk(fn) if isinstance(n, ast.Await)),
                      default=10**9)
    assert calls[0].lineno < first_await


@pytest.mark.parametrize("name", ["start_client", "apply_scope"])
def test_a_new_client_and_a_rescope_forget_every_repeat(name):
    # `apply_scope` refills the routing maps in place: a new routing generation.
    fn = _function(name)
    cleared = {n.func.value.id for n in ast.walk(fn) if isinstance(n, ast.Call)
               and isinstance(n.func, ast.Attribute) and n.func.attr == "clear"
               and isinstance(n.func.value, ast.Name)}
    assert {"ticker_memo", "observation_memo"} <= cleared


def test_the_minute_line_reports_both_skip_counts():
    text = SOURCE.read_text()
    assert "repeats_skipped=%d " in text and '"observations_skipped=%d"' in text
