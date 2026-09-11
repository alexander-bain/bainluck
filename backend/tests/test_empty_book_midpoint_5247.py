"""#5247 — an empty book's midpoint is not a probability, and is not served.

THE SPECIMEN. On 2026-09-11 the men's US Open semifinal page (`/events/15309206`,
Zverev–Khachanov) served a card reading "Not Completed 50%" for a match that was about
to be played. The 50% was `(0.02 + 0.99) / 2` — the midpoint of a Polymarket book with
a 2c bid and a 99c ask, nine snapshots deep and never once traded. `game-markets`
carries no bid/ask, so no client could tell that number from a real coin flip.

WHAT THIS FILE PINS, and why it is mostly a table of rows that must SURVIVE. The
obvious fix — reuse `is_fabricated_midpoint`, whose spread test is 0.20 — was measured
against production before it was written and rejected: on the same window it matches
3,657 Kalshi outcomes across 159 events, nearly all of them honest lines like "Auburn
over 19.5 points scored" (0.79 bid / 0.99 ask). A bid at 79c is a buyer. So the
keep-cases below are the real subject of this file; the drop-case is one row.

The discriminator is that BOTH sides sit at the extremes, so the quote bounds nothing.
"""

import pytest

from app.utils.feed_market_quality import (
    EMPTY_BOOK_MAX_BID,
    EMPTY_BOOK_MIN_ASK,
    is_empty_book_midpoint,
    is_fabricated_midpoint,
)


class TestTheSpecimen:
    def test_the_zverev_khachanov_not_completed_card_is_refused(self):
        """The exact production row: outcome 227146499, market 60658901."""
        assert is_empty_book_midpoint(0.505, 0.02, 0.99) is True

    def test_its_sibling_on_the_same_page_is_refused(self):
        """"Set 2 O/U 8.5" on event 15309206 — 0.01 / 0.99 -> 0.50."""
        assert is_empty_book_midpoint(0.50, 0.01, 0.99) is True

    def test_a_three_leg_question_each_leg_at_fifty_is_refused(self):
        """Waterford/Dundalk 2H result: three legs at 50% sum to 150%.

        The clearest proof in the population that no book priced any of them.
        """
        for leg in ("Waterford FC", "Dundalk FC", "Draw"):
            assert is_empty_book_midpoint(0.50, 0.02, 0.98) is True, leg

    def test_the_liquidity_rule_alone_would_have_kept_the_specimen(self):
        """Why the obvious rule is not the rule.

        The #940 calibration liquidity test is `yes_bid > 0 OR last_price > 0`. The
        specimen's bid is 0.02, which IS > 0, so that rule keeps it. The bid being
        *near* the floor rather than *at* it is the whole difficulty of this defect.
        """
        specimen_bid = 0.02
        assert specimen_bid > 0
        assert is_empty_book_midpoint(0.505, specimen_bid, 0.99) is True


class TestRowsThatMustSurvive:
    """Every case here was sampled from production on 2026-09-11 (events -1d..+3d)."""

    def test_a_wide_book_with_a_real_bid_is_kept(self):
        """"Auburn over 19.5 points scored" — 0.79 / 0.99 -> 0.89.

        The 3,657-row class. Lopsided, thinly quoted, and entirely honest.
        """
        assert is_empty_book_midpoint(0.89, 0.79, 0.99) is False

    def test_a_one_sided_book_with_a_real_ask_is_kept(self):
        """"DAL Cowboys wins 2H by over 9.5 points" — 0.01 / 0.36 -> 0.185.

        No buyer, but the ask bounds the price at 36c. That is information.
        """
        assert is_empty_book_midpoint(0.185, 0.01, 0.36) is False

    def test_a_settled_or_degenerate_quote_is_left_to_its_own_family(self):
        """0.00 / 1.00 carrying 0.99 is an empty book whose price is NOT the midpoint.

        It got 0.99 from a trade or a stale capture — the #4845 family, not this one.
        Requiring the midpoint equality is what keeps the two apart.
        """
        assert is_empty_book_midpoint(0.99, 0.0, 1.0) is False
        assert is_empty_book_midpoint(0.01, 0.0, 1.0) is False

    def test_a_model_price_with_no_book_is_kept(self):
        """DataGolf / odds_api / a derived complement quote no book at all."""
        assert is_empty_book_midpoint(0.50, None, None) is False

    def test_a_one_sided_book_is_not_widened_into_an_empty_one(self):
        """Unlike `is_fabricated_midpoint`, a missing side is NOT the widest quote.

        This is the deliberate divergence between the two predicates. A null bid with
        a 0.93 ask is a real bound; treating the null as 0.0 would manufacture an
        "empty" book out of a one-sided one.
        """
        assert is_empty_book_midpoint(0.465, None, 0.93) is False
        assert is_fabricated_midpoint(0.465, None, 0.93) is True

    def test_an_even_money_market_with_a_tight_book_is_kept(self):
        """A genuine 50/50 quoted 0.49/0.51 is the case a naive "refuse 50%" breaks."""
        assert is_empty_book_midpoint(0.50, 0.49, 0.51) is False


class TestTheBoundaries:
    def test_a_bid_one_tick_above_the_floor_is_kept(self):
        assert is_empty_book_midpoint(0.51, EMPTY_BOOK_MAX_BID + 0.01, 0.99) is False

    def test_an_ask_one_tick_below_the_ceiling_is_kept(self):
        assert is_empty_book_midpoint(0.485, 0.02, EMPTY_BOOK_MIN_ASK - 0.01) is False

    def test_both_sides_exactly_at_the_threshold_are_refused(self):
        mid = (EMPTY_BOOK_MAX_BID + EMPTY_BOOK_MIN_ASK) / 2
        assert is_empty_book_midpoint(mid, EMPTY_BOOK_MAX_BID, EMPTY_BOOK_MIN_ASK) is True

    def test_a_price_off_the_midpoint_is_kept_even_on_an_empty_book(self):
        assert is_empty_book_midpoint(0.30, 0.01, 0.99) is False

    def test_a_null_probability_is_not_a_fabrication(self):
        assert is_empty_book_midpoint(None, 0.01, 0.99) is False

    @pytest.mark.parametrize("bid,ask", [(0.02, 0.99), (0.0, 1.0), (0.01, 0.98)])
    def test_decimal_inputs_from_the_numeric_columns_are_handled(self, bid, ask):
        """`current_yes_bid`/`current_yes_ask` arrive as `Decimal` from Numeric(5,4)."""
        from decimal import Decimal

        mid = Decimal(str((bid + ask) / 2))
        assert is_empty_book_midpoint(mid, Decimal(str(bid)), Decimal(str(ask))) is True


class TestTheServePathApplication:
    """The predicate is only worth anything where `game-markets` draws its rows."""

    def test_the_build_filters_outcomes_before_the_empty_market_guard(self):
        """Order is load-bearing: filter, THEN `if not market_outcomes: continue`.

        That ordering is what makes a market whose legs are ALL empty-book lose its
        card via the existing empty-state path, while a market with real legs beside
        unpriced ones keeps them. Reversed, the specimen's card would still render.
        """
        import inspect

        from app.routes import events

        src = inspect.getsource(events._build_game_markets)
        filter_at = src.index("is_empty_book_midpoint(")
        guard_at = src.index("if not market_outcomes:")
        assert filter_at < guard_at, (
            "the empty-book filter must run BEFORE the empty-market guard, "
            "or a market whose only leg is a phantom still renders a card"
        )

    def test_the_filter_is_applied_once_and_not_per_section(self):
        """One rule at the source covers totals, spreads, props and other."""
        import inspect

        from app.routes import events

        src = inspect.getsource(events._build_game_markets)
        assert src.count("is_empty_book_midpoint(") == 1
