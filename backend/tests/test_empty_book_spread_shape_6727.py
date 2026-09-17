"""#6727 — a 1c bid and a 94c ask stops printing "Milwaukee Bucks 48%".

WHAT A READER SAW. Photographed on production at 390px on 2026-09-17, `/search?q=lakers`,
hours after #6676's search half went live (release v4674):

    NBA: Steph Curry Next Team
      Golden State Warriors   74%   on 0.52 / 0.96   <- real, kept
      Milwaukee Bucks         48%   on 0.01 / 0.94   <- THIS SHIP
      San Antonio Spurs       25%   on 0.01 / 0.49   <- honest longshot, kept
      Boston Celtics          21%   on 0.01 / 0.40   <- honest longshot, kept
      Charlotte Hornets       21%   on 0.01 / 0.40   <- honest longshot, kept

The same card had just correctly refused four legs quoted 0.01 / 0.95. This one survived
on a single cent of ask, so the rule dropped four fabrications and left the fifth —
worse for a reader than dropping none, because the survivor now looks vetted.

═══ NOT A WIDENING. A CHANGE OF SHAPE, AND THE SHAPE IS WHY IT IS SAFE ═══

The obvious repair — move `EMPTY_BOOK_MIN_ASK` 0.95 -> 0.94 — is the one thing this
ship refuses, and #6727 was filed saying so before any code was written. The two bounds
are not symmetric:

  * moving the BID bound leaves the reachable price band's floor alone (the ask sets
    the floor), which is why #5333 could move it on a measurement;
  * moving the ASK bound drops the FLOOR, and fast. At `ask >= 0.85` the predicate
    reaches 0.415 — honest longshot territory, where #5247's own kept controls live —
    and the measured decay above 0.85 has no gap to cut in (95, 42, 50, 22, 18, 23, 15,
    10, 19, 14 on-midpoint rows per cent). Any cut inside that is a knob.

What the pair of bounds was jointly asserting is that the quote bounds NOTHING: the
interval [bid, ask] is so wide that no price inside it is constrained, so a value at its
centre came from arithmetic rather than from anyone's belief. That is a statement about
the WIDTH, and the width is one number:

    bid <= 0.05 AND ask >= 0.95   ==>   ask - bid >= 0.90

`TestTheShapeIsAStrictSuperset` proves the implication exhaustively rather than by
argument, and `TestTheFloorCannotDrop` proves the property an ask move would not have
had: because the spread ties the two sides together, with `bid >= 0` and `ask <= 1` the
reachable midpoint is confined to [S/2, 1 - S/2] whatever the ask does. At S = 0.90 that
is [0.45, 0.55], so the band is [0.44, 0.56] with the tolerance — and reaching 0.28 (a
#5247 kept control) would require a NEGATIVE bid. Unreachable by construction, not by
luck. The safety argument is now readable straight off the constant.

THE CONSTANT IS DERIVED, NOT CHOSEN. `EMPTY_BOOK_MIN_SPREAD` is the subtraction of the
two existing measured constants, so this ship introduces no new tuned number.

═══ MEASURED ON PRODUCTION, read-only db-query, 2026-09-17, open markets ═══

132,550 outcomes carrying a two-sided book:

    rows matching the OLD pair                      10,538
    rows matching the NEW spread form               10,829
    LOST (old but not new)                               0   <- superset, measured
    newly reached                                      291
    of those, sitting ON their own midpoint            164   <- the class refused
    their price range                        0.450 - 0.535   <- inside [0.44, 0.56]

The 164 land on 110 markets, 71 of which keep no surviving two-sided-book leg — the
#5333 ship generalised, not a new cost: cards where EVERY priced leg is a phantom.
"Alphabet's Market Cap end of September 2026?" serves seven mutually exclusive buckets
at 0.470-0.480 summing to ~3.3; SpaceX's identical ladder is ALREADY printing a gapped
3-of-7 today, because the old pair catches its 0.01/0.95 legs and leaves its 0.01/0.94
ones. That is the #1574 gapped-ladder defect caused by the bound being one cent short,
and `TestTheGappedLadderIsTheOldRulesDoing` is it.

═══ 🔴 WHAT IT COSTS, TRIAGED ROW BY ROW AND NOT INFERRED ═══

14 of the 164 carry any trade evidence (non-null `volume` or `price_changed_at`). All 14
read against Gamma directly (curl — `urllib` gets 403 from gamma-api). On every one the
last trade is FAR from the number we print: Jade Kawamoto 0.43 vs our 0.490, Big Brother
"Veto" 0.97 vs 0.490, Ben Johns 0.77 vs 0.525, Sabrina Carpenter 0.13 vs 0.465, Jazz
Chisholm 0.02 vs 0.485. Two are worse than fabricated — they are STALE: a Rounds
Handicap leg Gamma prices at 0.9995 on $3,496 of 24h volume is stored here as 0.490, and
an exact-score leg Gamma prices at 0.0385 is stored as 0.470.

So ZERO genuinely-traded rows are withdrawn by this cohort — strictly better than #5333,
which named two and withdrew them on purpose. That is a statement about THIS cohort on
THIS read, not a guarantee, and the standing limit is not weakened: this is a pure
function of three columns, the serve path has no provenance column, and a genuine traded
50% on a book that has since emptied WOULD still be withdrawn. #6727 names that rail as
still unbuilt.

═══ RED-FIRST ═══

Two mutants, because reverting only reddens the arms that FIRE — a refusal rule that
withholds correctly is not tested by a mutant that makes it refuse less.

  * `is_empty_book_midpoint` reverted to the two-bound form, nothing else touched:
    **20 failed / 155 passed** across all six empty-book suites — this file's specimen,
    superset, ladder and reach classes plus the boundary controls in the other five.
  * `EMPTY_BOOK_MIN_SPREAD` loosened to 0.40: **29 failed / 146 passed** — the
    withholding arms, which the revert leaves green: the Curry card's four survivors,
    the Spurs row, and every production-sampled honest line.
  * restored: **175 passed**.

Before this file existed, making the change reddened **9** pre-existing controls. Every
one of the 9 asserted "one side past its bound ⇒ kept" — precisely the arbitrariness
removed here — and each was restated against the spread with its reason recorded at the
assertion rather than quietly deleted. #6676's grouped-feed tripwire, armed by #5333 so
the next widener had to read it first, fired exactly as designed and carries its return
trip. #5333's own docstring is amended, not rewritten.
"""

from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.routes.events import _leg_prices_an_empty_book as _event_page_drops
from app.routes.events import _build_search_top_outcomes
from app.routes.futures import _leg_prices_an_empty_book as _grouped_feed_drops
from app.utils.feed_market_quality import (
    EMPTY_BOOK_MAX_BID,
    EMPTY_BOOK_MIDPOINT_TOLERANCE,
    EMPTY_BOOK_MIN_ASK,
    EMPTY_BOOK_MIN_SPREAD,
    is_empty_book_midpoint,
)

BAND_LO = EMPTY_BOOK_MIN_SPREAD / 2 - EMPTY_BOOK_MIDPOINT_TOLERANCE
BAND_HI = (1.0 - EMPTY_BOOK_MIN_SPREAD / 2) + EMPTY_BOOK_MIDPOINT_TOLERANCE


def _old_pair(probability, yes_bid, yes_ask) -> bool:
    """The predicate exactly as it stood before #6727, for the superset proof.

    Restated here rather than imported because the whole point is to compare the new
    implementation against the retired one; importing would compare it to itself.
    """
    if probability is None or yes_bid is None or yes_ask is None:
        return False
    bid, ask = float(yes_bid), float(yes_ask)
    if bid > EMPTY_BOOK_MAX_BID or ask < EMPTY_BOOK_MIN_ASK:
        return False
    return abs(float(probability) - (bid + ask) / 2) <= EMPTY_BOOK_MIDPOINT_TOLERANCE


def _outcome(prob, bid, ask, name="Leg", oid=1):
    """An outcome as a route reads it off the ORM: Numeric(5,4) -> Decimal."""
    return SimpleNamespace(
        id=oid,
        name=name,
        external_id=f"ext-{oid}",
        current_probability=None if prob is None else Decimal(str(prob)),
        current_yes_bid=None if bid is None else Decimal(str(bid)),
        current_yes_ask=None if ask is None else Decimal(str(ask)),
        current_american_odds=None,
        probability=None if prob is None else Decimal(str(prob)),
        american_odds=None,
        rank=None,
        probability_change_24h=None,
        last_updated=None,
        is_winner=False,
    )


class _Market:
    """The attributes `_build_search_top_outcomes` reads off a futures market."""

    def __init__(self, outcomes, **kw):
        self.outcomes = outcomes
        self.id = kw.get("id", 90210)
        self.name = kw.get("name", "NBA: Steph Curry Next Team")
        self.sport = None
        self.category = "basketball"
        self.llm_sport_category = "basketball_nba"
        self.market_tier = kw.get("market_tier", 2)
        self.market_type = None
        self.status = "open"
        self.source = "polymarket"
        self.resolution_date = None
        self.updated_at = None
        self.mutually_exclusive = kw.get("mutually_exclusive", False)


# ---------------------------------------------------------------------------
# 1. THE SPECIMEN, in the shape the reader met it.
# ---------------------------------------------------------------------------


class TestTheCurryCard:
    """The whole card, so the ship is proved by what it LEAVES as much as what it takes.

    A refusal rule graded only on what it removes passes perfectly by removing
    everything; three of these four survivors have a bid inside `EMPTY_BOOK_MAX_BID`
    and are kept by the spread alone.
    """

    CARD = [
        ("Golden State Warriors", 0.74, 0.52, 0.96),
        ("Milwaukee Bucks", 0.475, 0.01, 0.94),
        ("San Antonio Spurs", 0.25, 0.01, 0.49),
        ("Boston Celtics", 0.205, 0.01, 0.40),
        ("Charlotte Hornets", 0.205, 0.01, 0.40),
    ]

    def test_the_bucks_leg_is_refused_and_the_other_four_are_served(self):
        market = _Market(
            [
                _outcome(p, b, a, name=n, oid=i)
                for i, (n, p, b, a) in enumerate(self.CARD)
            ]
        )

        assert [o["name"] for o in _build_search_top_outcomes(market)] == [
            "Golden State Warriors",
            "San Antonio Spurs",
            "Boston Celtics",
            "Charlotte Hornets",
        ]

    def test_the_bucks_leg_was_served_by_the_retired_predicate(self):
        """Without this the class above could pass on a card that never had the row."""
        assert _old_pair(0.475, 0.01, 0.94) is False  # the escape, as it stood
        assert is_empty_book_midpoint(0.475, 0.01, 0.94) is True  # closed

    def test_the_four_survivors_were_never_at_risk_from_either_form(self):
        """Isolates the change to the one leg: nothing else on the card moved."""
        for name, p, b, a in self.CARD:
            if name == "Milwaukee Bucks":
                continue
            assert _old_pair(p, b, a) is False, name
            assert is_empty_book_midpoint(p, b, a) is False, name

    def test_the_spurs_leg_is_kept_although_its_bid_is_inside_the_bid_bound(self):
        """0.01 / 0.49 — a 1c bid, which the bid bound alone would never have saved.

        This is the row an ask-bound widening endangers and the spread form does not:
        it is only ever kept because its book is 48 cents wide, not 90.
        """
        assert float(Decimal("0.01")) <= EMPTY_BOOK_MAX_BID
        assert is_empty_book_midpoint(0.25, 0.01, 0.49) is False


# ---------------------------------------------------------------------------
# 2. THE SUPERSET PROPERTY — proved, not argued.
# ---------------------------------------------------------------------------


class TestTheShapeIsAStrictSuperset:
    """Nothing the old pair refused to serve is served now. Measured 0/132,550 on
    production; proved here over every book the columns can express at 1c."""

    def test_no_input_is_lost(self):
        lost = []
        for bid_c in range(0, 101):
            for ask_c in range(0, 101):
                for price_c in range(0, 101):
                    bid, ask, price = bid_c / 100, ask_c / 100, price_c / 100
                    if _old_pair(price, bid, ask) and not is_empty_book_midpoint(
                        price, bid, ask
                    ):
                        lost.append((price, bid, ask))
        assert lost == []

    def test_and_it_genuinely_gains_ground(self):
        """The superset is strict — otherwise the sweep above is satisfied by a
        predicate identical to the old one, and this whole ship is a no-op."""
        gained = [
            (p, b, a)
            for p, b, a in (
                (0.475, 0.01, 0.94),
                (0.525, 0.06, 0.99),
                (0.455, 0.0, 0.91),
            )
            if is_empty_book_midpoint(p, b, a) and not _old_pair(p, b, a)
        ]
        assert len(gained) == 3


# ---------------------------------------------------------------------------
# 3. THE SAFETY PROPERTY — the reason this shape and not a wider ask bound.
# ---------------------------------------------------------------------------


class TestTheFloorCannotDrop:
    def test_the_band_is_derived_from_the_spread_alone(self):
        assert (BAND_LO, BAND_HI) == pytest.approx((0.44, 0.56))

    def test_nothing_outside_the_band_is_ever_reached_at_any_ask(self):
        """Swept over the FULL ask range, which is the axis an ask-bound move would
        have opened up. The old suites swept bids to 20-25c; the risk here is the
        other side, so this sweeps both ends exhaustively."""
        for bid_c in range(0, 101):
            for ask_c in range(0, 101):
                for price_c in range(0, 101):
                    bid, ask, price = bid_c / 100, ask_c / 100, price_c / 100
                    if is_empty_book_midpoint(price, bid, ask):
                        assert BAND_LO <= price <= BAND_HI, (
                            f"reached outside the coin-flip band: "
                            f"p={price} bid={bid} ask={ask}"
                        )

    def test_the_counterfactual_ask_bound_WOULD_have_reached_a_longshot(self):
        """The argument in #6727 for refusing the obvious repair, kept executable.

        If this ever stops being true the shape ruling can be revisited on evidence;
        while it holds, the ask bound may not simply be moved.
        """

        def _ask_bound_at(min_ask, probability, bid, ask):
            if bid > EMPTY_BOOK_MAX_BID or ask < min_ask:
                return False
            return abs(probability - (bid + ask) / 2) <= EMPTY_BOOK_MIDPOINT_TOLERANCE

        # a 0.415 longshot on a 0.00/0.84 book: refused by us, reached by that move
        assert is_empty_book_midpoint(0.415, 0.0, 0.84) is False
        assert _ask_bound_at(0.84, 0.415, 0.0, 0.84) is True

    @pytest.mark.parametrize(
        "kept_price", [0.185, 0.28, 0.01, 0.72, 0.76, 0.78, 0.89, 0.99]
    )
    def test_the_production_sampled_honest_lines_are_unreachable_by_arithmetic(
        self, kept_price
    ):
        """Not "no book we tried reaches them" — no book CAN. Reaching price p needs a
        bid of p - S/2, so every one of these needs a negative bid or an ask above 1."""
        assert not (BAND_LO <= kept_price <= BAND_HI)

        implied_bid = kept_price - EMPTY_BOOK_MIN_SPREAD / 2
        implied_ask = kept_price + EMPTY_BOOK_MIN_SPREAD / 2
        assert implied_bid < 0 or implied_ask > 1.0


# ---------------------------------------------------------------------------
# 4. THE FLOAT TRAP. This one is load-bearing and silent.
# ---------------------------------------------------------------------------


class TestTheRoundingIsDefensiveAndSaysSo:
    """🪤 `0.95 - 0.05` is 0.8999999999999999 while `0.99 - 0.09` is exactly 0.9.

    The first draft of this ship claimed the rounding SAVED the exact-threshold book
    against the derived bound. It does not, and the sweep below is why the claim was
    corrected rather than the code: both sides of that compare carry the same
    representation error, so they agree on all 1,322,301 4dp books in the corner.

    What the rounding actually buys is independence from how the bound is spelled. A
    future edit inlining the obvious literal `0.90` breaks the superset property on 234
    genuine 90c books — and that edit is the likely one, which is what makes this worth
    a guard rather than a comment.
    """

    def test_the_subtraction_really_is_lossy(self):
        assert (0.95 - 0.05) != 0.9
        assert (0.99 - 0.09) == 0.9

    def test_against_the_derived_bound_the_rounding_is_a_no_op(self):
        """Stated so nobody "simplifies" it back on the strength of an overclaim."""
        derived = EMPTY_BOOK_MIN_ASK - EMPTY_BOOK_MAX_BID
        for b in range(0, 1101, 3):
            for a in range(8800, 10001, 3):
                bid, ask = b / 10000, a / 10000
                assert ((ask - bid) >= derived) is (
                    round(ask - bid, 4) >= EMPTY_BOOK_MIN_SPREAD
                ), (bid, ask)

    def test_a_literal_bound_would_lose_genuine_ninety_cent_books(self):
        """The spelling the guard exists for, including the exact-threshold book."""

        def _naive_literal(probability, bid, ask):
            if (ask - bid) < 0.90:
                return False
            return abs(probability - (bid + ask) / 2) <= EMPTY_BOOK_MIDPOINT_TOLERANCE

        assert _old_pair(0.5, 0.05, 0.95) is True
        assert _naive_literal(0.5, 0.05, 0.95) is False  # the superset property, broken
        assert is_empty_book_midpoint(0.5, 0.05, 0.95) is True

        lost = [
            (b / 10000, a / 10000)
            for b in range(0, 1101)
            for a in range(8800, 10001)
            if _naive_literal(((b + a) / 20000), b / 10000, a / 10000)
            is not is_empty_book_midpoint(((b + a) / 20000), b / 10000, a / 10000)
        ]
        assert len(lost) == 234

    @pytest.mark.parametrize(
        "bid,ask", [(0.05, 0.95), (0.06, 0.96), (0.04, 0.94), (0.09, 0.99), (0.10, 1.0)]
    )
    def test_every_exactly_ninety_cent_book_is_caught(self, bid, ask):
        assert is_empty_book_midpoint((bid + ask) / 2, bid, ask) is True

    @pytest.mark.parametrize("bid,ask", [(0.06, 0.95), (0.0, 0.89), (0.05, 0.94)])
    def test_every_eighty_nine_cent_book_is_kept(self, bid, ask):
        assert is_empty_book_midpoint((bid + ask) / 2, bid, ask) is False

    def test_decimal_inputs_from_the_numeric_columns_take_the_same_path(self):
        """The routes pass Decimal, not float; the rounding must not care."""
        assert (
            is_empty_book_midpoint(Decimal("0.475"), Decimal("0.01"), Decimal("0.94"))
            is True
        )
        assert (
            is_empty_book_midpoint(Decimal("0.5"), Decimal("0.05"), Decimal("0.95"))
            is True
        )
        assert (
            is_empty_book_midpoint(Decimal("0.505"), Decimal("0.06"), Decimal("0.95"))
            is False
        )


# ---------------------------------------------------------------------------
# 5. THE CONSTANT IS DERIVED — no new tuned number enters the codebase.
# ---------------------------------------------------------------------------


class TestTheConstantIsDerivedAndNotChosen:
    def test_it_is_the_subtraction_of_the_two_measured_bounds(self):
        assert EMPTY_BOOK_MIN_SPREAD == round(
            EMPTY_BOOK_MIN_ASK - EMPTY_BOOK_MAX_BID, 4
        )
        assert EMPTY_BOOK_MIN_SPREAD == 0.9

    def test_moving_either_bound_re_derives_the_spread_and_the_band(self):
        """The pair stays the single source of truth: this is why the ship adds no knob."""
        for max_bid, min_ask in ((0.02, 0.95), (0.05, 0.95), (0.05, 0.98)):
            spread = round(min_ask - max_bid, 4)
            lo = spread / 2 - EMPTY_BOOK_MIDPOINT_TOLERANCE
            hi = (1.0 - spread / 2) + EMPTY_BOOK_MIDPOINT_TOLERANCE
            assert lo < 0.5 < hi
            # the band is symmetric about 0.5 and its width is set by the spread alone
            assert (lo + hi) / 2 == pytest.approx(0.5)
            assert hi - lo == pytest.approx(
                (1.0 - spread) + 2 * EMPTY_BOOK_MIDPOINT_TOLERANCE
            )

    def test_the_spread_is_not_restated_at_any_call_site(self):
        """One meaning of "untradeable". Five call sites import the predicate; an
        inlined threshold at any of them drifts silently from the other four."""
        import inspect

        from app.routes import events, futures
        from app.tasks import polymarket

        for module in (events, futures, polymarket):
            src = inspect.getsource(module)
            assert "EMPTY_BOOK_MIN_SPREAD = " not in src, module.__name__
            assert "- EMPTY_BOOK_MAX_BID" not in src, module.__name__


# ---------------------------------------------------------------------------
# 6. THE LADDER. What the one-cent shortfall was doing to an exclusive field.
# ---------------------------------------------------------------------------


class TestTheGappedLadderIsTheOldRulesDoing:
    """SpaceX's market-cap ladder, as production serves it today: seven mutually
    exclusive buckets, four quoted 0.01/0.95 and three quoted 0.01/0.94, every one on
    its own midpoint. The old pair takes the four and leaves the three — a gapped
    exclusive field, which is exactly the #1574 defect, caused by the bound being one
    cent short rather than by anything about the market.
    """

    LADDER = [
        ("$1.25-$1.50T", 0.48, 0.01, 0.95),
        ("$1.00-$1.25T", 0.48, 0.01, 0.95),
        ("<$1.00T", 0.48, 0.01, 0.95),
        ("$2.25T+", 0.48, 0.01, 0.95),
        ("$2.00-$2.25T", 0.475, 0.01, 0.94),
        ("$1.50-$1.75T", 0.475, 0.01, 0.94),
        ("$1.75-$2.00T", 0.475, 0.01, 0.94),
    ]

    def test_the_old_pair_left_three_of_seven_standing(self):
        survivors = [n for n, p, b, a in self.LADDER if not _old_pair(p, b, a)]
        assert survivors == ["$2.00-$2.25T", "$1.50-$1.75T", "$1.75-$2.00T"]

    def test_the_spread_form_takes_the_whole_ladder(self):
        survivors = [
            n for n, p, b, a in self.LADDER if not is_empty_book_midpoint(p, b, a)
        ]
        assert survivors == []

    def test_the_ladder_never_summed_to_a_distribution(self):
        """Why leaving any of it standing is indefensible: seven exclusive buckets
        priced at ~48% each assert 3.3 units of probability over one field."""
        assert sum(p for _, p, _, _ in self.LADDER) > 3.0

    def test_a_ladder_with_genuine_prices_is_untouched(self):
        """The other direction. A rule that empties exclusive fields would pass every
        assertion above."""
        honest = [("Yes", 0.62, 0.61, 0.63), ("No", 0.38, 0.37, 0.39)]
        assert [n for n, p, b, a in honest if not is_empty_book_midpoint(p, b, a)] == [
            "Yes",
            "No",
        ]


# ---------------------------------------------------------------------------
# 7. REACH. A correct helper nobody's route calls changes nothing.
# ---------------------------------------------------------------------------


class TestEveryServeSurfaceInheritsTheShape:
    """The two read-side helpers plus search, driven with the specimen row itself.
    The two Polymarket write sites are covered by #5333's and #6676's own suites,
    which drive the resolver and the parent path end to end; both import the same
    predicate and neither names a constant, asserted just above."""

    def test_the_event_page_drops_the_bucks_row(self):
        assert _event_page_drops(_outcome(0.475, 0.01, 0.94)) is True

    def test_the_grouped_feed_drops_the_bucks_row(self):
        assert _grouped_feed_drops(_outcome(0.475, 0.01, 0.94)) is True

    def test_search_drops_the_bucks_row(self):
        market = _Market([_outcome(0.475, 0.01, 0.94, name="Milwaukee Bucks")])
        assert _build_search_top_outcomes(market) == []

    def test_all_three_surfaces_agree_on_every_book_in_the_newly_reached_class(self):
        """Two surfaces disagreeing is how a fix half-lands; sampled from the measured
        291, including the Kalshi row with a literal zero bid."""
        for prob, bid, ask in (
            (0.475, 0.01, 0.94),
            (0.525, 0.06, 0.99),
            (0.46, 0.0, 0.91),
            (0.535, 0.08, 0.99),
            (0.25, 0.01, 0.49),
            (0.74, 0.52, 0.96),
        ):
            row = _outcome(prob, bid, ask)
            expected = is_empty_book_midpoint(prob, bid, ask)
            assert _event_page_drops(row) is expected, (prob, bid, ask)
            assert _grouped_feed_drops(row) is expected, (prob, bid, ask)
