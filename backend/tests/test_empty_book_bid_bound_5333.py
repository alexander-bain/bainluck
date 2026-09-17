"""#5333 — an empty book's complement stops surviving alone at 51%.

WHAT A READER SAW. A two-leg market with BOTH legs on empty books, one dropped by
#5247/#6676 and the other left standing as a phantom coin flip with nothing beside
it to give the reader a clue:

    IK Sirius vs Degerfors: O/U 12.5 Total Corners
        Over    0.490   bid 0.02 / ask 0.97   <- dropped
        Under   0.510   bid 0.03 / ask 0.98   <- SURVIVED, read "Under 51%"

`Under 51%` was exactly as fabricated as the `Over 49%` beside it. Its bid was 3c,
one cent over `EMPTY_BOOK_MAX_BID = 0.02`.

═══ THE CONSTANT MOVED, AND IT IS THE ONLY THING THAT MOVED ═══

`EMPTY_BOOK_MAX_BID` 0.02 -> 0.05 in `app/utils/feed_market_quality.py`. No
predicate is re-written, no call site changes, no second spelling of "untradeable"
is introduced: five call sites (two Polymarket write sites, `game-markets`, search,
the grouped feed) import the one helper and inherited the move.

MEASURED ON PRODUCTION, read-only, 2026-09-17, open markets — the cohort the move
newly reaches:

    bid cent   both-extreme rows   of those, ON their midpoint
      0.03            898                  824
      0.04            239                  200
      0.05            125                   95
                                   -----------
                                         1,119   price range 0.490 - 0.525

Inside the derived band [0.465, 0.535]. The stop is at 0.05 because that is the
constant #5333 measured and argued; past it the decay is smooth (45 rows at 6c, 17
at 7c, 9 at 8c) with no empty band to cut in, so a wider bound would be a knob.

═══ 🔴 WHAT IT COSTS, AND THE CLAIM NOBODY MAY MAKE ═══

42 of the 1,119 carry any trade evidence (non-null `volume` or `price_changed_at`).
Triaged against Gamma one by one rather than inferred from the stored row — the
stored `volume` column is Gamma's LIFETIME `volume`, not `volume24hr`, so it is not
evidence about the price being served:

  * 29 last traded FAR from the number we print ("Bryce Harper on the cover of MLB
    The Show 27" traded at 0.07 while we served 0.500; the Joe Rogan "Tesla" market
    at 0.031 while we served 0.515). Refusing those is the fix working.
  * 2 are a genuinely traded 0.500 on a now-empty book — Kovalova Daria vs Dronova
    Uliana, both legs, `lastTradePrice` 0.500 on $93.70 of 24h volume — and the
    SERVE path withdraws them.

`TestATradedFiftyOnAWideBook` is that case on the actual routes, and it asserts what
really happens rather than what would be nice. The writer preserves it (substituting
`last_trade_price` for the midpoint); the reader cannot, because the serve path has
no provenance column and this is a pure function of three. The honest sentence for
the serve surfaces is "no current quote supports this number" — never "this number
was never real".

RED-FIRST, with the constant reverted to 0.02 and nothing else touched: **17
failed, 14 passed, exit 1** (fixed: 31 passed, exit 0). The 14 that pass unfixed
are the survival controls and the two writer-side traded-50% cases — they are
controls precisely because they must not move. Reverting the CONSTANT alone is
the right mutant here: the ship is one number, so a mutation that touches
anything else would be testing a change nobody made.
"""
import json
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.routes.events import _build_search_top_outcomes
from app.routes.futures import _leg_prices_an_empty_book as _grouped_feed_drops
from app.services.polymarket_api import PolymarketAPIService
from app.tasks.polymarket import (
    _parent_outcome_data,
    _resolve_market_probability_with_source,
)
from app.utils.feed_market_quality import (
    EMPTY_BOOK_MAX_BID,
    EMPTY_BOOK_MIDPOINT_TOLERANCE,
    EMPTY_BOOK_MIN_ASK,
    is_empty_book_midpoint,
)


# ---------------------------------------------------------------------------
# The four real entry points. Each surface is driven through the function the
# route actually calls, not through the shared helper — a fix that moved a
# constant the helper reads and a surface that stopped reading the helper would
# pass every assertion written against the helper alone.
# ---------------------------------------------------------------------------


def _row(prob, bid, ask, name="Under", oid=1):
    """An outcome in the shape a route reads it off the ORM: Numeric -> Decimal."""
    return SimpleNamespace(
        id=oid,
        name=name,
        external_id=f"ext-{oid}",
        current_probability=None if prob is None else Decimal(str(prob)),
        current_yes_bid=None if bid is None else Decimal(str(bid)),
        current_yes_ask=None if ask is None else Decimal(str(ask)),
        current_american_odds=None,
        rank=None,
        probability_change_24h=None,
        last_updated=None,
        is_winner=False,
    )


class _Market:
    """The attributes `_build_search_top_outcomes` reads off a futures market."""

    def __init__(self, outcomes, **kw):
        self.outcomes = outcomes
        self.id = kw.get("id", 61254969)
        self.name = kw.get("name", "IK Sirius vs Degerfors: O/U 12.5 Total Corners")
        self.sport = None
        self.category = "soccer"
        self.llm_sport_category = "soccer_sweden_allsvenskan"
        self.market_tier = kw.get("market_tier", 3)
        self.market_type = None
        self.status = "open"
        self.source = "polymarket"
        self.resolution_date = None
        self.updated_at = None
        self.mutually_exclusive = kw.get("mutually_exclusive", False)


def _search_names(*outcomes, **kw):
    return [o["name"] for o in _build_search_top_outcomes(_Market(list(outcomes)), **kw)]


def _gamma(question, prices, bid, ask, last=None, vol24=None, cond="0xtest", **extra):
    """A raw Gamma market dict in the venue's own encoding (stringified arrays)."""
    raw = {
        "conditionId": cond,
        "question": question,
        "outcomes": json.dumps(["Over", "Under"]),
        "outcomePrices": json.dumps([str(p) for p in prices]) if prices is not None else None,
        "clobTokenIds": json.dumps(["1", "2"]),
        "bestBid": bid,
        "bestAsk": ask,
        "lastTradePrice": last,
        "volume24hr": vol24,
        "active": True,
        "closed": False,
        "acceptingOrders": True,
        "negRisk": False,
    }
    raw.update(extra)
    return raw


def _submarket(raw):
    """The resolver write site — `_resolve_market_probability_with_source`."""
    market = PolymarketAPIService()._parse_market(raw)
    assert market is not None, "the production parser refused the payload"
    return _resolve_market_probability_with_source(market)


def _parent(*markets, title="IK Sirius vs Degerfors - Total Corners"):
    """The parent write site — the non-negRisk multi-market branch."""
    event = PolymarketAPIService()._parse_event(
        {"id": "1035459", "title": title, "negRisk": False, "active": True,
         "markets": list(markets)}
    )
    assert event is not None, "the production parser refused the event"
    return {leg["external_id"]: leg["prob"] for leg in _parent_outcome_data(event)}


# ---------------------------------------------------------------------------
# 1. THE SPECIMEN, in the direction it actually failed: the lone survivor.
# ---------------------------------------------------------------------------


class TestTheSiblingComplement:
    """#5333's named acceptance case. Both legs of one binary sit on empty books
    a cent apart; before this, the 2c leg dropped and the 3c leg stood alone.
    """

    def test_neither_leg_of_the_specimen_reaches_a_search_card(self):
        assert _search_names(
            _row(0.490, 0.02, 0.97, name="Over", oid=1),
            _row(0.510, 0.03, 0.98, name="Under", oid=2),
        ) == []

    def test_neither_leg_of_the_specimen_reaches_the_grouped_feed(self):
        assert _grouped_feed_drops(_row(0.490, 0.02, 0.97, name="Over")) is True
        assert _grouped_feed_drops(_row(0.510, 0.03, 0.98, name="Under")) is True

    def test_the_survivor_was_the_one_the_old_bound_could_not_see(self):
        """Direction matters: the 2c leg was already refused, so a test that only
        asserts "both are refused" would pass against the old bound if the fake
        happened to carry two 2c legs. This one names which leg moved."""
        assert 0.02 <= EMPTY_BOOK_MAX_BID, "the 2c leg must still be refused"
        assert is_empty_book_midpoint(0.510, 0.03, 0.98) is True

    def test_a_lone_phantom_leg_no_longer_stands_beside_a_dropped_twin(self):
        """The reader-visible shape: one number where there should be none."""
        assert _search_names(
            _row(0.490, 0.02, 0.97, name="Over", oid=1),
            _row(0.510, 0.03, 0.98, name="Under", oid=2),
        ) != ["Under"]


# ---------------------------------------------------------------------------
# 2. THE COHORT, on the real stored shapes the measurement found.
# ---------------------------------------------------------------------------


class TestTheMeasuredCohort:
    @pytest.mark.parametrize(
        "prob,bid,ask,why",
        [
            (0.500, 0.03, 0.97, "824 rows at 3c, the modal shape"),
            (0.495, 0.03, 0.96, "Bournemouth vs Brentford - Second Half"),
            (0.505, 0.04, 0.97, "Will 'Trump' be said 10+ times"),
            (0.515, 0.05, 0.98, "the Joe Rogan 'Tesla' NO leg, top of the band"),
            (0.490, 0.03, 0.95, "the ask bound's own edge, inside the cohort"),
        ],
    )
    def test_each_surface_withholds_the_cohort(self, prob, bid, ask, why):
        assert is_empty_book_midpoint(prob, bid, ask) is True, why
        assert _grouped_feed_drops(_row(prob, bid, ask)) is True, why
        assert _search_names(_row(prob, bid, ask, name="Leg")) == [], why

    #: The half-cent skew, which is what makes these two writer cases #5333's and
    #: not #6676's. On an EXACT midpoint (0.5 on 0.03/0.97) `is_fabricated_midpoint`
    #: already declines, so the bid bound decides nothing; on 0.03/0.98 the book's
    #: own mid is 0.505, past that predicate's 0.0005 tolerance, and only this
    #: bound can reach it. It is also the live specimen (Gamma 4630453, 03:43Z).
    SKEWED = dict(prices=[0.5, 0.5], bid=0.03, ask=0.98)

    def test_the_writer_declines_the_cohort_at_the_submarket_site(self):
        assert _submarket(_gamma("O/U 12.5 Corners", **self.SKEWED)) == (None, None)

    def test_the_writer_declines_the_cohort_at_the_parent_site(self):
        legs = _parent(
            _gamma("O/U 12.5 Corners", cond="0xa", **self.SKEWED),
            _gamma("O/U 13.5 Corners", [0.28, 0.72], 0.25, 0.31, cond="0xb"),
        )
        # the control leg must still be written beside it, or the pass would only
        # say "the branch dropped everything"
        assert legs == {"0xb": pytest.approx(0.28)}


# ---------------------------------------------------------------------------
# 3. 🔴 THE LIMIT. The control Codex required, asserting what happens — not
#    what one would prefer to be able to claim.
# ---------------------------------------------------------------------------


class TestATradedFiftyOnAWideBook:
    """A genuine traded 0.500 whose book is 0.03/0.97 RIGHT NOW.

    Kovalova Daria vs Dronova Uliana, both legs, read off Gamma 2026-09-17:
    `lastTradePrice` 0.500 on `volume24hr` 93.7, `bestBid` 0.03, `bestAsk` 0.97.
    2 rows of the 1,119 this bound move newly reaches.

    The writer and the reader answer DIFFERENTLY, and that asymmetry is the
    finding, not an oversight to be papered over:

      * the writer has provenance (Gamma's `volume24hr` and `lastTradePrice`) and
        SUBSTITUTES the trade price for the midpoint, so 0.500 is stored with the
        honest source label;
      * the reader has three numeric columns and no provenance at all — the
        writer's label is consumed by `classify_pair_opening` and never persisted
        on `futures_outcomes` — so it withdraws the row.

    A provenance rail (a column, a migration, every writer) would close it. That
    is not this ship, and until it exists no page, PR or reader-facing sentence
    may say the serve path preserves a traded 50%.

    The two writer cases below already passed before this change — on this book the
    price is the EXACT midpoint, so `is_fabricated_midpoint` reached it without the
    bid bound. They are controls, and they are here so the asymmetry is asserted as
    one fact rather than described in two places: the whole of the change on this
    specimen lands on the reader.
    """

    TRADED = dict(prices=[0.5, 0.5], bid=0.03, ask=0.97, last=0.5, vol24=93.7)

    def test_the_submarket_writer_preserves_it_as_a_trade_price(self):
        assert _submarket(
            _gamma("Kovalova Daria vs. Dronova Uliana", **self.TRADED)
        ) == (0.5, "last_trade_price")

    def test_the_parent_writer_preserves_it_too(self):
        legs = _parent(
            _gamma("Kovalova vs Dronova", cond="0xk", **self.TRADED),
            _gamma("control", [0.28, 0.72], 0.25, 0.31, cond="0xcontrol"),
        )
        assert legs == {"0xk": pytest.approx(0.5), "0xcontrol": pytest.approx(0.28)}

    def test_search_WITHDRAWS_it_and_this_is_the_measured_cost(self):
        assert _search_names(_row(0.5, 0.03, 0.97, name="Kovalova Daria")) == []

    def test_the_grouped_feed_WITHDRAWS_it_too(self):
        assert _grouped_feed_drops(_row(0.5, 0.03, 0.97)) is True

    def test_the_serve_path_has_no_provenance_to_read(self):
        """The reason, stated as a property rather than as a comment: the two rows
        the serve path can distinguish a traded 0.5 by are identical."""
        traded = _row(0.5, 0.03, 0.97, name="traded at 0.500")
        phantom = _row(0.5, 0.03, 0.97, name="never traded")

        assert _grouped_feed_drops(traded) is _grouped_feed_drops(phantom)

    def test_a_market_traded_FAR_from_our_number_is_corrected_not_kept(self):
        """The other 29 of the 42. The Joe Rogan 'Tesla' market: real 24h volume,
        and the trade is at 3.1c while the stored row served 0.515. The writer's
        volume-gated exception substitutes the trade price — it does not hand the
        fabricated midpoint back because the market happens to be traded."""
        assert _submarket(
            _gamma("Will 'Tesla' be said", [0.4965, 0.5035], 0.033, 0.96,
                   last=0.031, vol24=455.6)
        ) == (pytest.approx(0.031), "last_trade_price")

    def test_a_stale_print_with_no_recent_volume_is_still_declined(self):
        """Q428, unchanged by this ship. 'Bryce Harper on the cover of MLB The
        Show 27': lifetime volume 558, `volume24hr` null, last trade 0.07 — and
        we were serving 0.500."""
        assert _submarket(
            _gamma("Bryce Harper cover", [0.5, 0.5], 0.03, 0.97, last=0.07, vol24=None)
        ) == (None, None)


# ---------------------------------------------------------------------------
# 4. WHAT MUST SURVIVE. Every one of these passes before the change too.
# ---------------------------------------------------------------------------


class TestGenuinePricesSurvive:
    def test_a_tight_forty_nine_fifty_one_quote_is_untouched(self):
        """A DIFFERENT control from the one above, and deliberately so: this is a
        real two-sided market at even money, not a traded price on a dead book.
        No bid bound this ship could plausibly reach comes near a 49c bid."""
        assert is_empty_book_midpoint(0.50, 0.49, 0.51) is False
        assert _grouped_feed_drops(_row(0.50, 0.49, 0.51)) is False
        assert _search_names(_row(0.50, 0.49, 0.51, name="Even money")) == ["Even money"]

    def test_the_live_twenty_eight_control_is_untouched(self):
        """Outcome 61260583: 0.28 on 25c/31c, never traded. No trade is not no quote."""
        assert _grouped_feed_drops(_row(0.28, 0.25, 0.31)) is False
        assert _search_names(_row(0.28, 0.25, 0.31, name="W15 Sao Luis")) == [
            "W15 Sao Luis"
        ]

    def test_a_real_game_line_on_a_real_book_is_untouched(self):
        """Golden State 0.74 on 0.52/0.96 — the one honest rung that shared the
        Curry card with four phantoms."""
        assert _grouped_feed_drops(_row(0.74, 0.52, 0.96)) is False
        assert _search_names(_row(0.74, 0.52, 0.96, name="Golden State Warriors")) == [
            "Golden State Warriors"
        ]

    def test_a_model_price_with_no_book_is_untouched(self):
        """DataGolf, odds_api, a derived complement: both book columns NULL. A
        source outage must not turn a last good price into a withdrawal."""
        assert _grouped_feed_drops(_row(0.5, None, None)) is False
        assert _search_names(_row(0.5, None, None, name="Model 50")) == ["Model 50"]

    def test_a_one_sided_real_ask_is_untouched(self):
        """'Cowboys 2H by 9.5+', 0.185 on a null bid and a 0.36 ask. A missing
        side is not the widest quote on that side."""
        assert _grouped_feed_drops(_row(0.185, None, 0.36)) is False

    def test_a_longshot_on_a_wide_book_is_untouched(self):
        """'Manchester United vs Manchester City: 7+ corners', 0.78 on 0.08/0.97 —
        named in #5333 as one of the 13 that must stay kept. Its bid is past the
        new bound AND its price is far from the midpoint: two independent reasons,
        which is what makes it a safe control."""
        assert _grouped_feed_drops(_row(0.78, 0.08, 0.97)) is False

    def test_a_settled_row_is_untouched(self):
        """The #4845 family: 0.99 on 0.00/1.00. Price is not the midpoint."""
        assert _grouped_feed_drops(_row(0.99, 0.0, 1.0)) is False


# ---------------------------------------------------------------------------
# 5. THE BOUND ITSELF, and the safety property re-derived at its new value.
# ---------------------------------------------------------------------------


class TestTheBound:
    def test_the_constant_is_five_cents(self):
        assert EMPTY_BOOK_MAX_BID == 0.05

    def test_the_bound_is_inclusive_and_the_next_cent_is_out(self):
        """Both rows sit exactly on their own midpoint, so the tolerance cannot be
        what separates them — only the bid bound can."""
        assert is_empty_book_midpoint((0.05 + 0.97) / 2, 0.05, 0.97) is True
        assert is_empty_book_midpoint((0.06 + 0.97) / 2, 0.06, 0.97) is False

    def test_the_reach_is_still_confined_to_the_coin_flip_band(self):
        """THE SAFETY PROPERTY at the new constant. Derived, then swept.

        #5247's own suite pins the same property; it is re-derived here because a
        constant move is exactly the edit that can break it, and a ship that moves
        a constant should carry its own proof rather than borrow one.
        """
        band_lo = EMPTY_BOOK_MIN_ASK / 2 - EMPTY_BOOK_MIDPOINT_TOLERANCE
        band_hi = (EMPTY_BOOK_MAX_BID + 1.0) / 2 + EMPTY_BOOK_MIDPOINT_TOLERANCE
        assert (band_lo, band_hi) == pytest.approx((0.465, 0.535))

        for bid_c in range(0, 26):
            for ask_c in range(0, 101):
                for price_c in range(0, 101):
                    bid, ask, price = bid_c / 100, ask_c / 100, price_c / 100
                    if is_empty_book_midpoint(price, bid, ask):
                        assert band_lo <= price <= band_hi, (
                            f"reached outside the coin-flip band: "
                            f"p={price} bid={bid} ask={ask}"
                        )

    def test_the_measured_cohort_sits_inside_the_band_with_headroom(self):
        """0.490 - 0.525 measured, against a band top of 0.535. A cohort pressed
        against its own bound is a cohort that will spill past it next week."""
        band_hi = (EMPTY_BOOK_MAX_BID + 1.0) / 2 + EMPTY_BOOK_MIDPOINT_TOLERANCE
        assert 0.525 < band_hi
        assert band_hi - 0.525 >= 0.01

    def test_the_honest_lines_are_outside_the_band_by_construction(self):
        band_lo = EMPTY_BOOK_MIN_ASK / 2 - EMPTY_BOOK_MIDPOINT_TOLERANCE
        band_hi = (EMPTY_BOOK_MAX_BID + 1.0) / 2 + EMPTY_BOOK_MIDPOINT_TOLERANCE
        for real_price in (0.76, 0.72, 0.89, 0.99, 0.78, 0.185, 0.28, 0.01):
            assert not (band_lo <= real_price <= band_hi), real_price

    def test_the_constant_is_not_restated_anywhere(self):
        """One meaning of "untradeable" in this codebase. Five call sites import
        the predicate; if a future edit inlines the threshold at any of them, the
        writer and the readers drift and nothing catches it."""
        import inspect

        from app.routes import events, futures
        from app.tasks import polymarket

        for module in (events, futures, polymarket):
            src = inspect.getsource(module)
            assert "EMPTY_BOOK_MAX_BID = " not in src, module.__name__
            assert "EMPTY_BOOK_MIN_ASK = " not in src, module.__name__
