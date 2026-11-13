"""A quiet market must not alternate between its book and an old trade."""

from __future__ import annotations

import pytest

from app.services.polymarket_api import PolymarketEvent, PolymarketMarket
from app.tasks.polymarket import (
    _parent_outcome_data,
    _resolve_market_probability_with_source,
)
from app.utils.polymarket_quote import current_polymarket_quote, quoted_price_change_value


def _leg(raw=0.71, *, bid=0.13, ask=0.17, last=0.71, **kwargs):
    return PolymarketMarket(
        condition_id="0xcolts65",
        question="Colts 6.5+ wins?",
        group_item_title="6.5+ Wins",
        outcome_prices=[raw, 1 - raw],
        outcomes=["Yes", "No"],
        best_bid=bid,
        best_ask=ask,
        last_trade_price=last,
        **kwargs,
    )


@pytest.mark.parametrize("raw", [0.15, 0.71, 0.155, 0.71])
def test_colts_repeated_tight_book_does_not_follow_old_raw_trade(raw):
    leg = _leg(raw)
    assert _resolve_market_probability_with_source(leg)[0] == pytest.approx(0.15)
    sibling = _leg(0.345, bid=0.32, ask=0.37).model_copy(
        update={"condition_id": "0xcolts55", "group_item_title": "5.5+ Wins"}
    )
    event = PolymarketEvent(id="912423", title="Colts Win Total", markets=[leg, sibling])
    rows = {row["external_id"]: row for row in _parent_outcome_data(event)}
    assert rows[leg.condition_id]["prob"] == pytest.approx(0.15)


@pytest.mark.parametrize(
    "bid,ask,last,raw",
    [
        (0.10, 0.78, 0.71, 0.71),  # retained Colts book; raw is reconstructed
        (0.10, 0.78, 0.71, 0.44),  # the other possible historical raw value
        (0.01, 0.60, 0.79, 0.79),  # reported Hall book and old trade
        (None, None, 0.71, 0.71),
        (0.0, 1.0, 0.71, 0.71),
    ],
)
def test_no_usable_book_does_not_publish_an_old_trade(bid, ask, last, raw):
    assert _resolve_market_probability_with_source(
        _leg(raw, bid=bid, ask=ask, last=last)
    ) == (None, None)


def test_a_real_near_certain_quote_survives_an_old_trade():
    assert _resolve_market_probability_with_source(
        _leg(0.17, bid=0.965, ask=0.975, last=0.17, volume_24h=5000)
    )[0] == pytest.approx(0.97)


def test_closed_market_keeps_its_settlement_value():
    assert _resolve_market_probability_with_source(
        _leg(1.0, bid=None, ask=None, last=1.0, closed=True)
    ) == (1.0, "outcome_prices")


@pytest.mark.parametrize(
    "bid,ask",
    [(None, 0.17), (0.13, None), (0.0, 0.17), (0.13, 1.0),
     (0.18, 0.17), (float("nan"), 0.17), (0.13, float("inf")),
     (-0.1, 0.1), (0.9, 1.1), ("bad", 0.17), (0.1, 0.3),
     (0.2, 0.4), (True, 0.17)],
)
def test_invalid_or_one_sided_book_cannot_invent_a_quote(bid, ask):
    assert current_polymarket_quote(bid, ask) is None


@pytest.mark.parametrize("old,bid,ask,expected", [
    (0.71, 0.13, 0.17, None),
    (0.71, 0.10, 0.78, None),
    (0.15, 0.13, 0.17, 0.01),
    (0.15, None, None, None),
    (None, 0.13, 0.17, None),
])
def test_a_change_of_price_basis_is_not_a_market_move(old, bid, ask, expected):
    value = quoted_price_change_value(old, bid, ask, 0.16)
    assert value == (None if expected is None else pytest.approx(expected))


@pytest.mark.parametrize("raw", ["[0.71, 0.29]", "[0.15, 0.85]", "[]"])
def test_live_writer_uses_the_same_quote_and_complement(raw):
    from app.tasks.prediction_market_matching import _live_polymarket_quote

    market = {"outcomePrices": raw, "outcomes": '["Colts", "Titans"]',
              "bestBid": 0.13, "bestAsk": 0.17, "lastTradePrice": 0.71}
    assert _live_polymarket_quote(market, "Colts") == pytest.approx((0.15, 0.13, 0.17, 0))
    assert _live_polymarket_quote(market, "Titans") == pytest.approx((0.85, 0.83, 0.87, 1))
    assert _live_polymarket_quote(market, "Bears") is None


@pytest.mark.parametrize("change", [
    {"bestAsk": 0.78}, {"bestBid": None}, {"closed": True},
    {"outcomes": "not JSON"}, {"outcomes": '["Colts", "Colts"]'},
])
def test_live_writer_refuses_an_unusable_or_unidentified_quote(change):
    from app.tasks.prediction_market_matching import _live_polymarket_quote

    market = {"outcomes": '["Colts", "Titans"]', "bestBid": 0.13,
              "bestAsk": 0.17, "lastTradePrice": 0.71, **change}
    assert _live_polymarket_quote(market, "Colts") is None


def test_a_refused_but_quoted_leg_keeps_the_existing_withdrawal_safeguard():
    from app.tasks.polymarket import _unpriced_leg_external_ids

    quoted = _leg().model_copy(update={"condition_id": "quoted"})
    wide = _leg(bid=0.10, ask=0.78).model_copy(update={"condition_id": "wide"})
    settled = _leg(1.0, bid=None, ask=None, closed=True).model_copy(update={"condition_id": "settled"})
    event = PolymarketEvent(id="912423", title="Colts Win Total", markets=[quoted, wide, settled])
    assert _unpriced_leg_external_ids(event) == []
    assert _unpriced_leg_external_ids(event.model_copy(update={"markets": [quoted]})) == []
