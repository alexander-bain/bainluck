"""#6676, fourth writer: the tolerance's own boundary rows stop escaping it.

WHAT A READER SAW, measured on production 2026-09-17 over both venues' open
markets. ``EMPTY_BOOK_MIDPOINT_TOLERANCE`` is ``0.01`` and the comparison is
``<=``, so the rule reads "within a cent of the midpoint counts as ON it". In
IEEE754 the distance of exactly one cent is not always ``0.01``::

    abs(0.51 - (0.0000 + 1.0000) / 2)  ->  0.010000000000000009   > 0.01

So the rows sitting EXACTLY on the tolerance -- the ones it was written to catch
-- were the rows it let through. 25 outcomes were in that class and ALL 25
PASSED the guard, served and writable:

    Price of NVIDIA B200 compute by Dec 31, 2026? / Above $5.57
        51%  on a 0.0000 / 1.0000 book   <- no bid, no ask, the emptiest quote
                                            the column can hold
    Szczecin: Completed Match (market 61309451)
        Yes 51% / No 49%  on 0.0100 / 0.9900   <- both sides of the #6676 defect
                                                  at once, the phantom coin flip
                                                  the ship was opened for
    US headline CPI inflation in December 2031 / Above 2.0%
        49%  on a 0.0100 / 0.9900 book

TRIAGED, NOT ASSUMED. 11 of the 25 carry trade evidence, and on every one it is
MARKET-level ``volume_24h`` or our own ``price_changed_at`` -- which this repo's
delta-blind writers move -- never a leg-level quote. The Amgen Irish Open market
carries 24,360 of volume; the leg withdrawn is "Grant Forrest" at 49% on a
0.0000/1.0000 book, which is where that volume is not. Zero genuinely-quoted
rows are withdrawn by this cohort.

WHY THE OLD SWEEPS COULD NOT SEE IT, which is the part worth carrying forward.
#5247, #5333 and #6727 each swept BOOKS through ``complementary_book`` and held
the price fixed. Condition 3 is the only condition the price appears in, so no
sweep of that shape can find a condition-3 boundary, and #6727's docstring
recorded "0 disagreements" as if the invariance were proven. It was proven for
conditions 1-2 and assumed for 3. Swept over all 509,949 (bid, ask, price)
integer-cent TRIPLES the unrounded form disagrees with its own complement on 10,
and on 4 of them the ITEM passes while the derived no leg is the phantom -- the
exact split ``test_a_per_leg_guard_would_split_the_pair`` was left behind to
catch, reachable through ``futures_price_refresh``'s own producer rather than
through the hypothetical second one its docstring imagines.

THE FIX IS A ROUNDED COMPARE AT A PRECISION EXACT FOR BOTH OPERAND COLUMNS, not
a moved constant: no bound changes, and the rule simply starts meaning the
tolerance it already declares. See ``_MIDPOINT_DISTANCE_DECIMALS`` for why 6 and
not the book columns' 4.
"""

import pytest

from app.tasks.polymarket import complementary_book
from app.utils.feed_market_quality import (
    EMPTY_BOOK_MIDPOINT_TOLERANCE,
    EMPTY_BOOK_MIN_SPREAD,
    is_empty_book_midpoint,
)


class TestTheBoundaryRowsTheToleranceWasWrittenToCatch:
    """Each specimen is a production row, quoted to the digit from the sweep."""

    @pytest.mark.parametrize(
        "name,probability,yes_bid,yes_ask",
        [
            # The emptiest book the column can hold, and we printed 51% on it.
            ("NVIDIA B200 compute / Above $5.57", 0.51, 0.0000, 1.0000),
            # Market 61309451, both legs -- the phantom coin flip itself.
            ("Szczecin Completed Match / Yes", 0.51, 0.0100, 0.9900),
            ("Szczecin Completed Match / No", 0.49, 0.0100, 0.9900),
            # A 24,360-volume market whose withdrawn leg has no book at all.
            ("Amgen Irish Open / Grant Forrest", 0.49, 0.0000, 1.0000),
            ("CPI December 2031 / Above 2.0%", 0.49, 0.0100, 0.9900),
            ("La Liga Relegation / Racing Santander", 0.48, 0.0000, 0.9800),
            ("McDonald's Foot Traffic / Above 103", 0.47, 0.0000, 0.9600),
            ("Online Sportsbook Ad Spend / Above 134", 0.51, 0.0500, 0.9500),
        ],
    )
    def test_a_price_exactly_one_cent_off_an_empty_midpoint_is_refused(
        self, name, probability, yes_bid, yes_ask
    ):
        # Not an assumption -- the specimen is IN the class the tolerance names,
        # so a guard that spares it is disagreeing with its own constant.
        assert round(yes_ask - yes_bid, 4) >= EMPTY_BOOK_MIN_SPREAD, name
        exact_distance = abs(probability - (yes_bid + yes_ask) / 2)
        assert round(exact_distance, 6) == EMPTY_BOOK_MIDPOINT_TOLERANCE, name

        assert is_empty_book_midpoint(probability, yes_bid, yes_ask) is True, name

    def test_the_unrounded_compare_is_what_let_them_through(self):
        """The mutation, spelled out: this is the line the fix changes.

        Without it a reader cannot tell this file's specimens from any other
        empty-book row, and would not know which edit turns the module red.
        """
        raw = abs(0.51 - (0.0000 + 1.0000) / 2)
        assert raw > EMPTY_BOOK_MIDPOINT_TOLERANCE, (
            "the premise of this whole module: in IEEE754 an exactly-one-cent "
            "distance compares GREATER than a 0.01 tolerance"
        )
        assert round(raw, 6) <= EMPTY_BOOK_MIDPOINT_TOLERANCE


class TestTheRoundingDoesNotWidenTheRule:
    """Without these the module above is satisfied by a predicate that refuses
    every wide book, which would withdraw the honest longshot lines #5247
    measured and deliberately kept."""

    @pytest.mark.parametrize(
        "name,probability,yes_bid,yes_ask",
        [
            # Two cents off the midpoint: outside the tolerance, and stays there.
            ("two cents off an empty midpoint", 0.52, 0.0000, 1.0000),
            # #5247's kept control: an honest longshot on a wide book.
            ("honest longshot far from the midpoint", 0.28, 0.0100, 0.9900),
            # Kalshi's last-trade fallback on a blowout line.
            ("genuine blowout line", 0.995, 0.0000, 1.0000),
        ],
    )
    def test_a_price_outside_the_tolerance_is_still_spared(
        self, name, probability, yes_bid, yes_ask
    ):
        assert is_empty_book_midpoint(probability, yes_bid, yes_ask) is False, name

    def test_a_book_that_bounds_something_is_still_spared(self):
        """Condition 2 is untouched by this ship -- a real book keeps its price
        even when the price sits exactly on its midpoint."""
        assert is_empty_book_midpoint(0.425, 0.30, 0.55) is False

    def test_the_tolerance_constant_is_unchanged(self):
        """This ship moves no bound. If a later edit 'fixes' a boundary row by
        widening the tolerance instead, this is what says so."""
        assert EMPTY_BOOK_MIDPOINT_TOLERANCE == 0.01
        assert EMPTY_BOOK_MIN_SPREAD == 0.90


class TestTheComplementInvarianceIsTheCodesAndNotOnlyTheAlgebras:
    """THE CONTROL THE EARLIER SWEEPS COULD NOT BE. Read the module docstring:
    every prior sweep varied the book and held the price fixed, so none of them
    could see condition 3. This one varies all three."""

    def test_a_leg_and_its_derived_twin_get_the_same_verdict(self):
        disagreements = []
        for bid_cents in range(101):
            for ask_cents in range(bid_cents, 101):
                bid, ask = bid_cents / 100.0, ask_cents / 100.0
                # The writer's own arithmetic, not a tidied one: every caller
                # derives the complement this way and `1 - 0.95` is
                # `0.050000000000000044`. A sweep that `round()`s the complement
                # reports this class as empty and is wrong.
                no_bid, no_ask, _ = complementary_book(bid, ask, None)
                for price_cents in range(1, 100):
                    price = price_cents / 100.0
                    item = is_empty_book_midpoint(price, bid, ask)
                    leg = is_empty_book_midpoint(1.0 - price, no_bid, no_ask)
                    if item != leg:
                        disagreements.append((bid, ask, price, item, leg))

        assert disagreements == [], (
            f"{len(disagreements)} (bid, ask, price) triples give a leg and its "
            "derived twin different verdicts, so an item-level caller writes a "
            "phantom complement it never tested: "
            f"{disagreements[:4]}"
        )

    def test_the_sweep_is_wide_enough_to_have_found_the_defect(self):
        """A green sweep proves nothing if it never reached the boundary. This
        pins that the grid CONTAINS the four triples that used to split -- so
        the test above cannot go green by sweeping the wrong space."""
        for bid, ask, price in [
            (0.08, 0.98, 0.52),
            (0.08, 1.00, 0.53),
            (0.09, 0.99, 0.53),
            (0.10, 1.00, 0.54),
        ]:
            no_bid, no_ask, _ = complementary_book(bid, ask, None)
            # Both sides agree NOW; what is pinned is that this triple is in the
            # class at all -- the derived twin is an empty-book midpoint, so a
            # regression in the compare shows up here as a split.
            assert is_empty_book_midpoint(1.0 - price, no_bid, no_ask) is True
            assert is_empty_book_midpoint(price, bid, ask) is True
