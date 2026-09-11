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
    EMPTY_BOOK_MIDPOINT_TOLERANCE,
    EMPTY_BOOK_MIN_ASK,
    is_empty_book_midpoint,
    is_fabricated_midpoint,
)


class TestTheSpecimen:
    def test_the_zverev_khachanov_not_completed_card_is_refused(self):
        """The exact production row: outcome 227146499, market 60658901."""
        assert is_empty_book_midpoint(0.505, 0.02, 0.99) is True

    def test_the_same_row_after_the_book_moved_is_still_refused(self):
        """THE ESCAPE. The first cut of this fix shipped at 19:39Z and lost the
        specimen twenty minutes later.

        At 19:19Z the book moved to 0.01 / 0.97 carrying 0.495. Against the shipped
        `ask >= 0.98` and a 0.0005 tolerance that is a miss on BOTH clauses — by one
        cent and by half of one — and the card stayed on the page through the release
        that was supposed to remove it. An empty book is not less empty at 97c.
        """
        assert is_empty_book_midpoint(0.495, 0.01, 0.97) is True

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

    def test_a_traded_price_on_a_both_extremes_book_is_kept(self):
        """"Aaron Rodgers: 17+ passing completions" — 0.00 / 0.98 carrying 0.76.

        THE REASON THE MIDPOINT CLAUSE SURVIVES. Kalshi's ingest falls back to
        `last_price` on a wide book, so a both-extremes quote can still carry a real
        traded price. Widening this predicate to "both extremes + any mid-range price"
        was measured and pulls in 305 outcomes, including this whole class.
        """
        assert is_empty_book_midpoint(0.76, 0.0, 0.98) is False
        # same class, sampled the same minute
        assert is_empty_book_midpoint(0.83, 0.0, 0.98) is False
        assert is_empty_book_midpoint(0.75, 0.0, 1.0) is False
        assert is_empty_book_midpoint(0.09, 0.0, 1.0) is False

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

    def test_the_tolerance_clears_the_populated_buckets(self):
        """The mass sits at |price - midpoint| of 0.000 and 0.005; the real-price tail
        starts an order of magnitude further out. The cut must clear 0.005 (or it
        loses the specimen, which is how the first cut failed) and stay well short of
        the tail.
        """
        assert 0.005 < EMPTY_BOOK_MIDPOINT_TOLERANCE < 0.05

    def test_the_reach_is_confined_to_the_coin_flip_band(self):
        """THE SAFETY PROPERTY, and the reason the ask bound could move 3c.

        The three constants together make this predicate incapable of dropping
        anything that is not a near-coin-flip. Derived from the constants rather than
        hardcoded, so widening ANY of them re-derives the band and this test still
        states the true guarantee -- while the sampled honest lines below pin that the
        band never grows far enough to reach them.
        """
        band_lo = EMPTY_BOOK_MIN_ASK / 2 - EMPTY_BOOK_MIDPOINT_TOLERANCE
        band_hi = (EMPTY_BOOK_MAX_BID + 1.0) / 2 + EMPTY_BOOK_MIDPOINT_TOLERANCE
        assert (band_lo, band_hi) == pytest.approx((0.465, 0.52))

        # Dense sweep: nothing outside the derived band may ever be refused. Bids run
        # to 20c -- far past EMPTY_BOOK_MAX_BID and past any plausible widening of it,
        # so the sweep still covers the whole accepting region if that constant moves.
        for bid_c in range(0, 21):
            for ask_c in range(0, 101):
                for price_c in range(0, 101):
                    bid, ask, price = bid_c / 100, ask_c / 100, price_c / 100
                    if is_empty_book_midpoint(price, bid, ask):
                        assert band_lo <= price <= band_hi, (
                            f"reached outside the coin-flip band: "
                            f"p={price} bid={bid} ask={ask}"
                        )

        # the honest lines the ship is afraid of, each sampled from production, are
        # outside the band by construction -- not by luck
        for real_price in (0.76, 0.72, 0.89, 0.99, 0.185, 0.01):
            assert not (band_lo <= real_price <= band_hi)

    def test_a_price_just_inside_and_just_outside_the_tolerance(self):
        mid = (0.01 + 0.97) / 2  # 0.49
        assert is_empty_book_midpoint(mid + 0.005, 0.01, 0.97) is True
        assert is_empty_book_midpoint(mid + 0.05, 0.01, 0.97) is False

    def test_the_tolerance_is_not_the_shared_phantom_constant(self):
        """Widening the shared one would move calibration and ingest populations."""
        from app.utils import feed_market_quality as fmq

        assert EMPTY_BOOK_MIDPOINT_TOLERANCE != fmq._PHANTOM_MIDPOINT_TOLERANCE
        # the SQL mirror and the calibration closing line still read the tight one
        assert "0.0005" in fmq.fabricated_midpoint_sql("p", "b", "a")

    def test_a_null_probability_is_not_a_fabrication(self):
        assert is_empty_book_midpoint(None, 0.01, 0.99) is False

    @pytest.mark.parametrize("bid,ask", [(0.02, 0.99), (0.0, 1.0), (0.01, 0.98)])
    def test_decimal_inputs_from_the_numeric_columns_are_handled(self, bid, ask):
        """`current_yes_bid`/`current_yes_ask` arrive as `Decimal` from Numeric(5,4)."""
        from decimal import Decimal

        mid = Decimal(str((bid + ask) / 2))
        assert is_empty_book_midpoint(mid, Decimal(str(bid)), Decimal(str(ask))) is True


class TestTheServePathApplication:
    """A correct helper nobody calls changes nothing — so drive the actual route.

    CERT-2633's follow-up (`5247-ROUTE-BEHAVIOR-AND-PRICE-PROVENANCE-GUARD`) asked for
    exactly this: the first version of this class asserted on `inspect.getsource`
    ordering, which pins text rather than behaviour. These drive
    `GET /api/events/{id}/game-markets` end to end instead.
    """

    def test_the_filter_is_applied_once_and_not_per_section(self):
        """One rule at the source, so totals/spreads/props/other cannot drift apart."""
        import inspect

        from app.routes import events

        src = inspect.getsource(events._build_game_markets)
        assert src.count("is_empty_book_midpoint(") == 1

    @pytest.mark.asyncio
    async def test_the_specimens_card_leaves_and_the_real_market_keeps_its_legs(
        self, empty_book_client
    ):
        payload = (
            await empty_book_client.get("/api/events/15309206/game-markets")
        ).json()
        rows = (payload.get("other") or []) + (payload.get("spreads") or [])
        names = {r["outcome_name"] for r in rows}

        # 1. the whole card leaves: its only leg was an empty-book midpoint, so the
        #    market falls through the existing `if not market_outcomes` guard.
        assert "Not Completed" not in names, (
            "the specimen's card is still being served: " f"{sorted(names)}"
        )
        assert not any(
            r["market_name"].endswith("Exact Score") for r in rows
        ), "the single-leg market should have left entirely, not rendered empty"

        # 2. the market with real legs beside a phantom keeps the real ones — a LEG
        #    is dropped, not a market. This is the half that makes the fix safe.
        assert "Alexander Zverev" in names
        assert "Karen Khachanov" in names
        assert "Set 2 O/U 8.5" not in names

    @pytest.mark.asyncio
    async def test_no_served_row_carries_an_empty_book_midpoint(
        self, empty_book_client
    ):
        """The property, stated over the whole payload rather than named rows."""
        payload = (
            await empty_book_client.get("/api/events/15309206/game-markets")
        ).json()
        for key in ("other", "spreads", "totals", "player_props"):
            for row in payload.get(key) or []:
                assert row.get("outcome_name") not in {"Not Completed", "Set 2 O/U 8.5"}


@pytest.fixture
async def empty_book_client():
    """The specimen page, rebuilt: one all-phantom market and one mixed market.

    Bid/ask are set EXPLICITLY on every outcome. `_make_outcome` returns a MagicMock,
    and an unset `current_yes_bid` floats to 1.0 rather than raising — which would
    silently spare every row and make this file pass for the wrong reason.
    """
    from unittest.mock import AsyncMock, patch

    from httpx import ASGITransport, AsyncClient

    from app.dependencies.auth import get_optional_user
    from app.main import app
    from app.routes.events import _game_markets_cache
    from app.services.database import get_db, get_db_rw
    from tests.integration.test_route_events_seeded import (
        _make_event,
        _make_event_detail_session,
        _make_futures_market,
        _make_outcome,
    )

    _game_markets_cache.clear()

    event = _make_event(
        id=15309206,
        home_team="Alexander Zverev",
        away_team="Karen Khachanov",
        status="scheduled",
    )

    def _book(outcome, bid, ask):
        outcome.current_yes_bid = bid
        outcome.current_yes_ask = ask
        return outcome

    # The specimen market: one leg, an empty book at the values that ESCAPED the
    # first cut (0.01 / 0.97 -> 0.495).
    exact = _make_futures_market(
        id=60658901,
        name="Alexander Zverev vs. Karen Khachanov - Exact Score",
        source="polymarket",
    )
    exact.status = "open"
    exact.event_id = event.id

    # A real market carrying one phantom leg beside two honest ones.
    match = _make_futures_market(
        id=60644431, name="Zverev vs Khachanov", source="kalshi"
    )
    match.status = "open"
    match.event_id = event.id

    outcomes = [
        _book(
            _make_outcome(
                id=227146499,
                market_id=60658901,
                name="Not Completed",
                probability=0.495,
            ),
            0.01,
            0.97,
        ),
        _book(
            _make_outcome(
                id=1, market_id=60644431, name="Alexander Zverev", probability=0.82
            ),
            0.81,
            0.83,
        ),
        _book(
            _make_outcome(
                id=2, market_id=60644431, name="Karen Khachanov", probability=0.18
            ),
            0.17,
            0.19,
        ),
        _book(
            _make_outcome(
                id=3, market_id=60644431, name="Set 2 O/U 8.5", probability=0.50
            ),
            0.01,
            0.99,
        ),
    ]

    mock_session = _make_event_detail_session(
        event=event, futures=[exact, match], outcomes=outcomes
    )

    async def _mock_get_db():
        yield mock_session

    async def _mock_get_optional_user():
        return None

    app.dependency_overrides[get_db] = _mock_get_db
    app.dependency_overrides[get_db_rw] = _mock_get_db
    app.dependency_overrides[get_optional_user] = _mock_get_optional_user

    with patch("app.main.init_db", new_callable=AsyncMock):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield ac

    _game_markets_cache.clear()
    app.dependency_overrides.clear()
