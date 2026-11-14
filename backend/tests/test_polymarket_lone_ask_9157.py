"""#9157 — a Polymarket leg with no bid and no trade is not priced at its ask.

What a reader saw: ``/futures/62289535`` (Presidents Cup 2026: Points Leader)
printed 20 of 21 golfers at 19%, and ``/events/15313655`` printed a Correct Score
card at 47% on every score line. Every one of those legs was written by the hourly
resolver's ask-only fallback from a Gamma leg reading ``outcomePrices ["0","1"]``,
no bid, no trade, and a lone ask.

These drive the production parser and resolver on the specimen's own encoding
(Gamma event 1078378, read 2026-09-28 ~05Z). #12658 now bounds a missing bid by
zero: a spread below 20 points prices at its midpoint, never at the lone ask or
an undated trade. Wider books remain refused.
"""

from __future__ import annotations

import json

from app.services.polymarket_api import PolymarketAPIService
from app.tasks.polymarket import (
    _parent_outcome_data,
    _resolve_market_probability_with_source,
)


def _gamma(name, prices, bid, ask, last=None, vol24=None, cond="0x9157"):
    """A raw Gamma market dict in the venue's own encoding (stringified arrays)."""
    return {
        "conditionId": cond,
        "question": f"Will {name} be the top points scorer at the 2026 Presidents Cup?",
        "groupItemTitle": name,
        "outcomes": json.dumps(["Yes", "No"]),
        "outcomePrices": json.dumps(prices) if prices is not None else None,
        "clobTokenIds": json.dumps([f"{cond}-y", f"{cond}-n"]),
        "bestBid": bid,
        "bestAsk": ask,
        "lastTradePrice": last,
        "volume24hr": vol24,
        "active": True,
        "closed": False,
        "acceptingOrders": True,
        "negRisk": True,
    }


def _select(raw):
    market = PolymarketAPIService()._parse_market(raw)
    assert market is not None, "the production parser refused the payload"
    return _resolve_market_probability_with_source(market)


#: The stored specimen: Scottie Scheffler on Gamma 1078378.
SPECIMEN = dict(prices=["0", "1"], bid=None, ask=0.19)


class TestTheLoneAskIsNeverThePrice:
    def test_the_presidents_cup_specimen_uses_the_bounded_midpoint(self):
        """The 19-point book prices at 9.5%, not the old 19% ask fallback."""
        assert _select(_gamma("Scottie Scheffler", **SPECIMEN)) == (0.095, "bid_ask_midpoint")

    def test_the_correct_score_specimen_is_not_priced(self):
        """Market 62400489: explicit zero bid, 0.47 ask, no trade. Was ``(0.47, 'best_ask')``."""
        assert _select(_gamma("AE Prat 1-0", ["0", "1"], 0, 0.47)) == (None, None)

    def test_absent_outcome_prices_do_not_reopen_the_fallback(self):
        """A missing raw price still uses the book, never the lone ask."""
        assert _select(_gamma("Adam Scott", None, None, 0.19)) == (0.095, "bid_ask_midpoint")

    def test_a_field_of_lone_asks_uses_the_same_bounded_midpoint(self):
        """The negRisk parent path uses the same rule on every carried leg."""
        names = ["Scottie Scheffler", "Xander Schauffele", "Justin Thomas", "Adam Scott"]
        event = PolymarketAPIService()._parse_event({
            "id": "1078378",
            "title": "Presidents Cup 2026: Points Leader",
            "negRisk": True,
            "active": True,
            "markets": [
                _gamma(n, **SPECIMEN, cond=f"0x{i}") for i, n in enumerate(names)
            ],
        })
        assert event is not None
        rows = _parent_outcome_data(event)
        assert {row["external_id"] for row in rows} == {f"0x{i}" for i in range(len(names))}
        assert all(row["prob"] == 0.095 for row in rows)


class TestWhatStillPrices:
    """Controls: each differs from the specimen by exactly the evidence it lacks."""

    def test_a_tight_two_sided_book(self):
        assert _select(_gamma("Control", ["0.42", "0.58"], 0.40, 0.44)) == (
            0.42, "outcome_prices"
        )

    def test_a_bid_on_the_same_ask_prices_off_the_midpoint(self):
        """Same ask, same placeholder outcomePrices, plus a real bid: priced."""
        prob, source = _select(_gamma("Bid", ["0", "1"], 0.15, 0.19))
        assert (round(prob, 6), source) == (0.17, "bid_ask_midpoint")

    def test_a_trade_on_the_same_book_cannot_replace_the_midpoint(self):
        """An undated trade inside the book does not change its midpoint."""
        assert _select(_gamma("Traded", ["0", "1"], None, 0.19, last=0.12)) == (
            0.095, "bid_ask_midpoint"
        )

    def test_a_raw_venue_price_cannot_replace_the_bounded_midpoint(self):
        assert _select(_gamma("Venue", ["0.1", "0.9"], None, 0.19)) == (
            0.095, "bid_ask_midpoint"
        )
