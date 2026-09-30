"""#9938 — during play, a Kalshi print its own live book does not anchor is not a price.

THE SPECIMENS, production 2026-09-30.

1. `/events/15321782` (PHI @ ATL, Wild Card Game 2, Bottom 10th, PHI 4–3, hero ATL
   18%). Series Exact Score `62898792` printed "ATL wins 2-0 52%". Stored, 21:14Z:

       ATL wins 2-0   0.72   bid 0.01 / ask 0.81   (a 20:59Z print, Atlanta leading)
       ATL wins 2-1   0.34   bid 0.02 / ask 0.58
       PHI wins 2-1   0.40   bid 0.37 / ask 0.43   <- the only tradeable leg

2. `/events/15321836` (CWS @ HOU, live, CWS 4–3). Series Exact Score `62898789`
   printed CWS 2-0 76% · CWS 2-1 24% · HOU 2-1 1% while the same rail's Kalshi
   Series Winner priced Houston 21.5%. Stored, 23:10Z:

       CWS wins 2-0   0.81   0.00 / 0.99
       CWS wins 2-1   0.25   0.00 / 0.58
       HOU wins 2-1   0.01   0.00 / 0.54
       Series Total Games "Yes" (Over 2.5)   0.51   0.00 / 0.58

The controls are from the same live rail: 1% legs sitting on a live 1¢ bid, 0.1%
legs on a sub-cent book, ask-only longshots, and every tight book.
"""

import pytest

from app.utils.futures_unsupported_price import (
    LIVE_PLAY_WIDE_BOOK_SPREAD,
    print_is_unanchored_during_live_play,
)


def _fires(p, bid, ask, *, source="kalshi", resolution_source=None):
    return print_is_unanchored_during_live_play(source, resolution_source, p, bid, ask)


class TestTheSpecimensAreWithheld:
    @pytest.mark.parametrize(
        "name,p,bid,ask",
        [
            ("ATL wins 2-0", 0.72, 0.01, 0.81),
            ("ATL wins 2-1", 0.34, 0.02, 0.58),
        ],
    )
    def test_phi_atl_prints_inside_wide_books(self, name, p, bid, ask):
        assert _fires(p, bid, ask), name

    def test_phi_atl_the_tradeable_leg_keeps_its_price(self):
        assert not _fires(0.40, 0.37, 0.43)

    @pytest.mark.parametrize(
        "name,p,bid,ask",
        [
            ("CWS wins 2-0", 0.81, 0.0, 0.99),
            ("CWS wins 2-1", 0.25, 0.0, 0.58),
            ("HOU wins 2-1", 0.01, 0.0, 0.54),
            ("Over 2.5 total games", 0.51, 0.0, 0.58),
        ],
    )
    def test_cws_hou_prints_on_books_nobody_bids_into(self, name, p, bid, ask):
        assert _fires(p, bid, ask), name


class TestControlsFromTheSameLiveRail:
    def test_tight_book_midpoint(self):
        assert not _fires(0.80, 0.79, 0.81)  # Series Winner, CWS

    def test_a_print_on_a_standing_bid_is_a_current_price(self):
        # Pro Baseball Championship Series MVP legs: 0.01 on 0.01 / 0.985.
        assert not _fires(0.01, 0.01, 0.985)

    def test_a_sub_cent_book_locates_its_longshot(self):
        # Houston vs Chicago Championship Series Matchup: 0.001 on 0.00 / 0.009.
        assert not _fires(0.001, 0.0, 0.009)

    def test_a_trusted_longshot_ask_is_the_writers_rule_3(self):
        assert not _fires(0.04, 0.0, 0.04)
        assert not _fires(0.50, 0.0, 0.50)

    def test_an_ask_above_the_trusted_max_is_not_an_anchor(self):
        # The writer never takes an ask above 0.50 as a price, so a print that
        # happens to equal one anchors nothing.
        assert _fires(0.81, 0.0, 0.81)


class TestBoundaries:
    def test_the_spread_line_is_the_writers_midpoint_line(self):
        from app.tasks.kalshi import _KALSHI_TIGHT_SPREAD_MAX

        assert LIVE_PLAY_WIDE_BOOK_SPREAD == _KALSHI_TIGHT_SPREAD_MAX

    def test_exactly_fifty_cents_wide_is_wide(self):
        # The writer's rule 1 is `spread < 0.50`, so 0.25 / 0.75 got no midpoint.
        assert _fires(0.40, 0.25, 0.75)

    def test_forty_nine_cents_wide_is_not(self):
        assert not _fires(0.40, 0.26, 0.75)

    def test_a_price_outside_the_book_still_fires(self):
        # The book arm withholds it too; answering True here is harmless overlap.
        assert _fires(0.92, 0.28, 0.91)


class TestFailOpenAndScope:
    def test_polymarket_is_not_asked(self):
        assert not _fires(0.72, 0.01, 0.81, source="polymarket")

    def test_a_graded_row_is_a_result(self):
        assert not _fires(0.72, 0.01, 0.81, resolution_source="api_settlement")

    def test_a_retraction_is_still_a_quote(self):
        assert _fires(0.72, 0.01, 0.81, resolution_source="ungradeable_result")

    @pytest.mark.parametrize(
        "p,bid,ask",
        [(None, 0.01, 0.81), (0.72, None, 0.81), (0.72, 0.01, None)],
    )
    def test_an_unrecorded_value_answers_false(self, p, bid, ask):
        assert not _fires(p, bid, ask)

    @pytest.mark.parametrize("p", [0.0, 1.0])
    def test_terminal_prices_are_settlements_business(self, p):
        assert not _fires(p, 0.0, 1.0)

    def test_numeric_columns_arrive_as_decimals(self):
        from decimal import Decimal

        assert _fires(Decimal("0.720000"), Decimal("0.0100"), Decimal("0.8100"))
        assert not _fires(Decimal("0.010000"), Decimal("0.0100"), Decimal("0.9850"))
