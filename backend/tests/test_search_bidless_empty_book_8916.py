"""A search card stops printing a bid-less leg's manufactured 50%. #8916.

WHAT A READER SAW (production `0beffa76`, 2026-09-26, `/search?q=ohio state`):
market 61844344 *Ohio State vs. Iowa* ranked

    Ohio State      84%   on 0.81 / 0.87
    Spread -20.5    50%   on NULL / 0.99
    Spread -5.5     50%   on NULL / 0.99

Two different spreads cannot both be a coin flip. Each 0.50 is Polymarket's midpoint
of ``(0, 0.99)``: nobody bids, so the missing bid IS the zero side. #5247's
`is_empty_book_midpoint` passes a missing side on purpose, so search served them.

The new predicate is #5247's question asked of ``[0, ask]`` with #5247's constants,
so its reach is confined to ``[0.44, 0.51]`` and a bid-less longshot stays served.
"""

from types import SimpleNamespace

import pytest

from app.routes.events import (
    _build_search_top_outcomes,
    _futures_card_has_no_answer,
    _futures_market_prices_only_empty_books,
    _leg_prices_an_empty_book,
)
from app.utils.feed_market_quality import (
    EMPTY_BOOK_MIN_SPREAD,
    is_bidless_empty_book_midpoint,
    is_empty_book_midpoint,
)


class _Outcome:
    def __init__(self, oid, name, prob, bid, ask):
        self.id = oid
        self.name = name
        self.current_probability = prob
        self.current_yes_bid = bid
        self.current_yes_ask = ask
        self.current_american_odds = None
        self.rank = None
        self.probability_change_24h = None
        self.last_updated = None
        self.external_id = f"ext-{oid}"
        self.is_winner = False
        self.resolution_source = None


class _Market:
    def __init__(self, outcomes, **kw):
        self.outcomes = outcomes
        self.id = kw.get("id", 61844344)
        self.name = kw.get("name", "Ohio State vs. Iowa")
        self.sport = None
        self.category = "football"
        self.llm_sport_category = "football_ncaaf"
        self.market_tier = 1
        self.market_type = kw.get("market_type", "field")
        self.status = "open"
        self.source = "polymarket"
        self.resolution_date = None
        self.updated_at = None
        self.mutually_exclusive = kw.get("mutually_exclusive", False)


def _ohio_state_iowa():
    """Market 61844344's three stored legs, 2026-09-26."""
    return _Market(
        [
            _Outcome(233603272, "Ohio State", 0.84, 0.81, 0.87),
            _Outcome(233279667, "Spread -20.5", 0.5, None, 0.99),
            _Outcome(233279668, "Spread -5.5", 0.5, None, 0.99),
        ]
    )


class TestTheSpecimen:
    def test_the_two_spread_coin_flips_leave_the_card(self):
        names = [o["name"] for o in _build_search_top_outcomes(_ohio_state_iowa())]

        assert names == ["Ohio State"]

    def test_the_old_rule_passed_them_which_is_the_defect(self):
        """Condition 1 of #5247 needs both sides; a NULL bid is not refused there."""
        assert is_empty_book_midpoint(0.5, None, 0.99) is False
        assert is_bidless_empty_book_midpoint(0.5, None, 0.99) is True

    def test_a_card_holding_only_the_spread_leg_withdraws(self):
        """'Oregon State vs. Colorado State' (61844324): one leg, 0.50 on NULL/0.99."""
        market = _Market(
            [_Outcome(1, "Spread -2.5", 0.5, None, 0.99)],
            id=61844324,
            name="Oregon State vs. Colorado State",
            market_type="unshaped",
        )

        assert _futures_market_prices_only_empty_books(market) is True
        assert _futures_card_has_no_answer(market) is True
        assert _build_search_top_outcomes(market) == []


class TestWhatStaysServed:
    @pytest.mark.parametrize(
        "prob, ask",
        [
            (0.18, 0.36),  # the bid-less longshot #5247 kept
            (0.37, 0.74),  # the highest on-midpoint price below the spread bound
            (0.445, 0.89),  # one cent under the spread bound, on its midpoint
        ],
    )
    def test_a_bidless_ask_under_the_spread_bound_is_kept(self, prob, ask):
        assert is_bidless_empty_book_midpoint(prob, None, ask) is False
        assert _leg_prices_an_empty_book(_Outcome(1, "Leg", prob, None, ask)) is False

    def test_a_bidless_price_off_its_midpoint_is_kept(self):
        """A traded print on an emptied book — Platense's last trade was 0.01."""
        assert is_bidless_empty_book_midpoint(0.62, None, 0.99) is False

    def test_a_model_price_with_no_book_at_all_is_kept(self):
        assert is_bidless_empty_book_midpoint(0.5, None, None) is False

    def test_a_recorded_bid_is_left_to_5247s_rule_alone(self):
        """A zero bid is a two-sided book; the new predicate never judges it."""
        assert is_bidless_empty_book_midpoint(0.495, 0.0, 0.99) is False
        assert is_empty_book_midpoint(0.495, 0.0, 0.99) is True

    def test_unpriced_leg_is_not_this_rule(self):
        assert is_bidless_empty_book_midpoint(None, None, 0.99) is False


class TestTheBand:
    def test_the_spread_bound_is_5247s_constant(self):
        edge = EMPTY_BOOK_MIN_SPREAD
        assert is_bidless_empty_book_midpoint(edge / 2, None, edge) is True
        assert is_bidless_empty_book_midpoint(edge / 2, None, edge - 0.01) is False

    def test_nothing_below_044_or_above_051_is_reachable_at_any_ask(self):
        reached = [
            p / 1000
            for p in range(0, 1001)
            for a in range(0, 101)
            if is_bidless_empty_book_midpoint(p / 1000, None, a / 100)
        ]

        assert reached
        assert min(reached) >= 0.44
        assert max(reached) <= 0.51


class TestSearchIsTheOnlyCaller:
    def test_the_shared_5247_predicate_is_unchanged_for_its_writers(self):
        """The writers import `is_empty_book_midpoint`; it must still pass a NULL bid."""
        for prob, ask in ((0.5, 0.99), (0.495, 1.0), (0.46, 0.92)):
            assert is_empty_book_midpoint(prob, None, ask) is False

    def test_decimal_columns_take_the_same_path(self):
        from decimal import Decimal

        leg = SimpleNamespace(
            current_probability=Decimal("0.500000"),
            current_yes_bid=None,
            current_yes_ask=Decimal("0.9900"),
        )
        assert _leg_prices_an_empty_book(leg) is True
