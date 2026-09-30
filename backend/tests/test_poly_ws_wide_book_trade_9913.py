"""#9913 — a trade that sweeps past the edge of a wide book does not set a price.

WHAT A READER SAW. ``/events/15321782`` (PHI @ ATL, Wild Card G2, live, 390 px,
2026-09-30 19:11Z): the Polymarket series card read Phillies 89% / Braves 11%
beside Kalshi's Atlanta 71%.

WHY. Market 63348823's Braves token had a book of 0.12 × 5 / 0.11 × 394 bid and
0.73 ask. At 18:54:15Z a 20-share SELL printed at 0.1125 — 0.12 × 5 plus
0.11 × 15, averaged. It cleared #9733's 5-share floor, so ``handle_trade`` wrote
Braves 0.1125 and ``with_complements`` wrote Phillies 0.8875.

THE RULE. A trade prints at the edge of the book it hits, or beyond it when it
eats more than the top level. Beyond the edge of a book wider than the #1578 bar
is not a price. The venue does not promise whether the post-trade book (0.11
bid, which 0.1125 sits inside) arrives before or after the trade, so both
orderings are driven here.

Drives the REAL consumer with only the socket and the slate faked (the
``test_poly_ws_side1_leg_pairing_8403.py`` harness, via #9733's binary setup).
That rig is the game slate, which proves no complement pairs, so only the traded
leg is written; the refusal sits before ``with_complements``, so a refused trade
reaches neither leg on either arm.
"""

import json

import pytest

from app.tasks.polymarket_ws import trade_prints_outside_wide_book
from tests.test_poly_ws_min_order_trade_9733 import (
    NO_TOKEN as PHILLIES_TOKEN,
    YES_LEG as BRAVES_LEG,
    YES_TOKEN as BRAVES_TOKEN,
    _run,
    _trade,
)


def _book(token, bid, ask):
    return json.dumps(
        {
            "event_type": "best_bid_ask",
            "asset_id": token,
            "best_bid": bid,
            "best_ask": ask,
        }
    )


PRE_TRADE_BOOK = _book(BRAVES_TOKEN, "0.12", "0.73")
POST_TRADE_BOOK = _book(BRAVES_TOKEN, "0.11", "0.73")
THE_SWEEP = _trade(BRAVES_TOKEN, "0.1125", "20")


class TestTheSpecimenTape:
    async def test_the_sweep_does_not_flip_the_series_card(self, monkeypatch):
        """THE REGRESSION. Pre-fix: Braves 0.1125 and Phillies 0.8875."""
        writes, stats = await _run(monkeypatch, [PRE_TRADE_BOOK, THE_SWEEP])
        assert writes == [], writes
        assert stats["trades_outside_wide_book"] == 1, stats
        assert stats["trade_updates"] == 0, stats

    async def test_refused_when_the_post_trade_book_arrives_first(self, monkeypatch):
        """The latest book (0.11 bid) holds 0.1125; the one before it did not."""
        writes, stats = await _run(
            monkeypatch, [PRE_TRADE_BOOK, POST_TRADE_BOOK, THE_SWEEP]
        )
        assert writes == [], writes
        assert stats["trades_outside_wide_book"] == 1, stats

    async def test_a_repeated_book_does_not_push_out_the_pre_trade_one(
        self, monkeypatch
    ):
        """The venue can send the same top of book twice (a ``book`` frame and
        a ``best_bid_ask``); only a CHANGE shifts the remembered pair."""
        writes, stats = await _run(
            monkeypatch,
            [PRE_TRADE_BOOK, POST_TRADE_BOOK, POST_TRADE_BOOK, THE_SWEEP],
        )
        assert writes == [], writes
        assert stats["trades_outside_wide_book"] == 1, stats


class TestTradesThatStillPrice:
    async def test_no_book_seen_behaves_as_before(self, monkeypatch):
        writes, stats = await _run(monkeypatch, [THE_SWEEP])
        assert writes == [(BRAVES_LEG, pytest.approx(0.1125))], writes
        assert stats["trades_outside_wide_book"] == 0, stats

    async def test_a_trade_at_the_edge_of_a_wide_book_still_prices(
        self, monkeypatch
    ):
        """Gotcha #19: in a wide book the trade stream is what moves an
        illiquid market. A fill at the resting bid is inside the book."""
        writes, stats = await _run(
            monkeypatch, [PRE_TRADE_BOOK, _trade(BRAVES_TOKEN, "0.12", "5")]
        )
        assert writes == [(BRAVES_LEG, pytest.approx(0.12))], writes
        assert stats["trades_outside_wide_book"] == 0, stats

    async def test_a_sweep_through_a_tight_book_still_prices(self, monkeypatch):
        """A tight book's midpoint is written, and a trade just past it is a
        real price move, not an emptied book."""
        writes, stats = await _run(
            monkeypatch,
            [_book(BRAVES_TOKEN, "0.72", "0.74"), _trade(BRAVES_TOKEN, "0.745", "40")],
        )
        assert writes[-1] == (BRAVES_LEG, pytest.approx(0.745)), writes
        assert stats["trades_outside_wide_book"] == 0, stats

    async def test_a_book_that_came_back_tight_is_not_second_guessed(
        self, monkeypatch
    ):
        """Wide, then tight: the old wide book is not consulted, so a buy that
        lifts the new ask prices."""
        writes, stats = await _run(
            monkeypatch,
            [
                PRE_TRADE_BOOK,
                _book(BRAVES_TOKEN, "0.88", "0.90"),
                _trade(BRAVES_TOKEN, "0.905", "25"),
            ],
        )
        assert writes[-1] == (BRAVES_LEG, pytest.approx(0.905)), writes
        assert stats["trades_outside_wide_book"] == 0, stats

    async def test_the_other_tokens_book_does_not_judge_this_one(self, monkeypatch):
        """Books are per token: a wide Phillies book says nothing about a
        Braves print."""
        writes, stats = await _run(
            monkeypatch,
            [_book(PHILLIES_TOKEN, "0.26", "0.88"), THE_SWEEP],
        )
        assert (BRAVES_LEG, pytest.approx(0.1125)) in writes, writes
        assert stats["trades_outside_wide_book"] == 0, stats


@pytest.mark.parametrize(
    "prob, books, expected",
    [
        (0.1125, (), False),
        (0.1125, ((0.12, 0.73), None), True),
        (0.74, ((0.12, 0.73), None), True),
        (0.12, ((0.12, 0.73), None), False),
        (0.73, ((0.12, 0.73), None), False),
        (0.1125, ((0.11, 0.73), (0.12, 0.73)), True),
        # Latest tight: never refused, whatever the older book said.
        (0.1125, ((0.10, 0.12), (0.12, 0.73)), False),
        # Latest wide, previous tight: only the latest judges.
        (0.1125, ((0.11, 0.73), (0.12, 0.13)), False),
        (0.745, ((0.72, 0.74), None), False),
    ],
)
def test_trade_prints_outside_wide_book(prob, books, expected):
    assert trade_prints_outside_wide_book(prob, books) is expected


def test_the_refusal_counts_reach_the_minute_line(caplog):
    """A refusal counted and never emitted is invisible on production."""
    import logging

    from app.tasks.polymarket_ws import _log_stats_line

    stats = {
        "price_updates": 0, "trade_updates": 0, "resolutions": 0, "errors": 0,
        "trades_below_min_order": 4, "trades_outside_wide_book": 7,
    }
    blend = {"stamped": 0, "no_reading": 0, "throttled": 0, "errors": 0}
    with caplog.at_level(logging.INFO):
        _log_stats_line(stats, {}, blend)
    assert "trades refused below_min=4 outside_wide_book=7" in caplog.text


def test_the_minute_line_survives_stats_without_the_counters(caplog):
    """The shadow consumer shares the line: absent keys print 0, never raise."""
    import logging

    from app.tasks.polymarket_ws import _log_stats_line

    stats = {"price_updates": 0, "trade_updates": 0, "resolutions": 0, "errors": 0}
    blend = {"stamped": 0, "no_reading": 0, "throttled": 0, "errors": 0}
    with caplog.at_level(logging.INFO):
        _log_stats_line(stats, {}, blend)
    assert "below_min=0 outside_wide_book=0" in caplog.text
