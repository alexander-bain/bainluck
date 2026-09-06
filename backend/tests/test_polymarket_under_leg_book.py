"""The Under/No leg of a Polymarket pair has never had its book recorded.

CAL-P095's finding, measured population-wide before a line was written
(``artifacts/cal-p095/leg_book_coverage.json``, 0 irreducible shards):

    leg            n     n_bid    bid%     n_ask    ask%
    over      248702    191444  0.7698    246564  0.9914
    under     248702         0  0.0000         0  0.0000
    yes       258746    171624  0.6633    253653  0.9803
    no        244713         0  0.0000         0  0.0000

**493,415 Under/No legs. Zero books. Not one.** The cause is in
``app/tasks/polymarket.py``: the decomposed-pair path passes
``current_yes_bid=market.best_bid`` / ``current_yes_ask=market.best_ask`` on the
Over upsert, and neither column appears in the Under upsert's values or in its
``on_conflict_do_update`` set clause. No other writer touches these rows.

Two things follow, and the first is why this file exists rather than a comment.

**1. It invalidates an inference the program has already banked.** CAL-P094
attributed ``baseball/quantity``'s exact-0.5000 spike with
``fold_spike_provenance.py`` and read its largest verdict as a fact about the
market:

    ``no_book`` 924 ... every one of the 924 ``no_book`` legs is an UNDER leg
    with no book at all, and that is not a stale-book artifact: **a leg that
    never had a book never had one.**

CAL-P095 reproduced the identical shape in ``soccer/quantity`` — 992 legs, again
*all* Under, again zero bid and zero ask — which is what prompted reading the
writer. ``no_book`` is a property of the WRITER, uniform across the whole
population at every price and every outcome. It carries no information about
whether a market traded. That is gotcha #53 exactly: the emptier reading of one
response shape mistaken for a finding about the world.

**2. It is why the forward phantom guard reaches only half of a pair.**
``classify_fabricated_book`` (UX-P011 / #1574) and ``is_fabricated_midpoint``
(#1578) both judge an outcome from ``current_yes_bid`` / ``current_yes_ask``. On
a Polymarket binary they can see the Over leg and are structurally blind on the
Under leg — so when the Over leg is dropped as a manufactured midpoint, its Under
partner survives and can still lead the card, which is the exact failure #1574
was filed for ("it was naming the wrong leader").

The repair is a capture fix, not a price fix. In a binary CLOB the No token's
book IS the Yes token's book read from the other side — a bid for No at ``q`` is
the same resting order as an ask for Yes at ``1 - q``. Recording it is an
identity, not an estimate, which is what keeps it clear of the fail-closed rule
in :mod:`app.utils.pair_opening_coherence`: that rule governs **openings**, which
become published forecasts through ``calibration_probability``'s fallback. These
are evidence columns, and they are NULL-preserving here — a missing Yes-side
counterpart yields ``None``, never a manufactured zero.

DELIBERATELY NOT FIXED HERE, and recorded so the next reader knows it is known:
the Under **snapshot** (``FuturesOddsSnapshot``) omits ``yes_bid`` / ``yes_ask``
/ ``last_price`` the same way, and ``POLY_PLACEHOLDER_EXCLUDE`` in
``precompute_calibration.py`` reads exactly those columns. Measured, that filter
drops **95.09%** of Under legs in its [0.45, 0.55] band against **0.41%** of
Over legs — not 100%, because some other writer reaches 4.99% of them, and the
tidier number was the one a 1M-id probe reported first. Filling the columns
would move the published curve, so it needs a measured before/after and a staged
apply, not a drive-by: ``QUEUE-STAGED-CAL-UNDER-LEG-SNAPSHOT-BOOK.md``. See also
the CAL-P095 section of ``SUBCOHORT_DIAGNOSIS.md``.
"""

from __future__ import annotations

import inspect

import pytest

from app.tasks.polymarket import complementary_book
from app.utils.feed_market_quality import is_fabricated_midpoint


class TestTheMirrorIsAnIdentity:
    """A bid for No at ``q`` is an ask for Yes at ``1 - q``. Same order."""

    def test_an_ordinary_two_sided_book_flips(self):
        # Yes book 0.40 / 0.60 -> No book 0.40 / 0.60, which is the same book
        # seen from the other token.
        assert complementary_book(0.40, 0.60, None) == (
            pytest.approx(0.40),
            pytest.approx(0.60),
            None,
        )

    def test_an_asymmetric_book_flips_both_sides(self):
        bid, ask, last = complementary_book(0.10, 0.90, 0.15)
        assert bid == pytest.approx(0.10)
        assert ask == pytest.approx(0.90)
        assert last == pytest.approx(0.85)

    def test_the_spread_is_invariant(self):
        """``(1-bid) - (1-ask) == ask - bid``, so wide stays wide.

        This is what makes the mirror safe for every spread-based predicate: a
        book judged untradeable on the Yes side is judged untradeable on the No
        side, and neither leg can launder the other.
        """
        for yes_bid, yes_ask in ((0.01, 0.99), (0.45, 0.55), (0.0, 1.0), (0.3, 0.8)):
            no_bid, no_ask, _ = complementary_book(yes_bid, yes_ask, None)
            assert (no_ask - no_bid) == pytest.approx(yes_ask - yes_bid)

    def test_the_maximum_spread_sentinel_survives_the_flip(self):
        """``best_ask = 1.0`` means nobody is making a market. It must stay legible."""
        no_bid, no_ask, _ = complementary_book(0.0, 1.0, None)
        assert no_bid == pytest.approx(0.0), (
            "an ask of 1.0 is no offer at all; its mirror must be a bid of 0, "
            "not a positive number that reads as a live quote"
        )
        assert no_ask == pytest.approx(1.0)


class TestItNeverInventsFromNothing:
    """NULL-preserving in both directions — the fail-closed rule, applied to columns."""

    def test_a_missing_ask_yields_no_bid(self):
        assert complementary_book(0.40, None, None) == (None, pytest.approx(0.60), None)

    def test_a_missing_bid_yields_no_ask(self):
        assert complementary_book(None, 0.60, None) == (pytest.approx(0.40), None, None)

    def test_an_empty_book_stays_empty(self):
        assert complementary_book(None, None, None) == (None, None, None)

    def test_a_missing_trade_is_not_a_zero_trade(self):
        """``last_price > 0`` is a liquidity test elsewhere; 0 and NULL differ."""
        _, _, last = complementary_book(0.4, 0.6, None)
        assert last is None

    def test_a_degenerate_trade_at_one_mirrors_to_zero_not_to_none(self):
        _, _, last = complementary_book(0.4, 0.6, 1.0)
        assert last == pytest.approx(0.0)


class TestTheMirrorMakesThePhantomGuardSymmetric:
    """The payoff: #1578's predicate must reach both legs or neither."""

    @pytest.mark.parametrize(
        "yes_bid,yes_ask",
        [(0.01, 0.99), (0.05, 0.95), (0.40, 0.60), (0.49, 0.51)],
    )
    def test_a_leg_is_phantom_exactly_when_its_partner_is(self, yes_bid, yes_ask):
        yes_mid = (yes_bid + yes_ask) / 2
        no_bid, no_ask, _ = complementary_book(yes_bid, yes_ask, None)
        assert is_fabricated_midpoint(yes_mid, yes_bid, yes_ask) == (
            is_fabricated_midpoint(1 - yes_mid, no_bid, no_ask)
        ), (
            "the Under leg must inherit the same verdict as its Over partner; "
            "an asymmetric verdict is how a phantom survives to lead a card"
        )

    def test_the_untradeable_1c_99c_pair_is_refused_on_both_legs(self):
        """The #1574 specimen. Today the Under half of it is invisible."""
        no_bid, no_ask, _ = complementary_book(0.01, 0.99, None)
        assert is_fabricated_midpoint(0.50, 0.01, 0.99) is True
        assert is_fabricated_midpoint(0.50, no_bid, no_ask) is True


class TestTheWriterRecordsIt:
    """Structural pins on the Under upsert. Each fails on a revert."""

    @staticmethod
    def _under_block() -> str:
        from app.tasks import polymarket

        # #3613 moved the parent-leg build out of this function into
        # `_parent_outcome_data`, taking the old "# Also keep parent market
        # outcomes" end-marker with it. Slicing the POLL'S OWN source rather
        # than the module's makes both bounds unambiguous — a marker inside one
        # function cannot be shadowed by the same words elsewhere in the file —
        # and the CAL-P006 guard is a real construct rather than a comment kept
        # alive to be an anchor.
        src = inspect.getsource(polymarket._process_event_batch)
        start = src.index("# Create Under/No outcome if available")
        end = src.index("# CAL-P006 (#1527)")
        assert end > start
        return src[start:end]

    def test_the_insert_carries_both_book_columns(self):
        block = self._under_block()
        assert "current_yes_bid=under_best_bid," in block
        assert "current_yes_ask=under_best_ask," in block

    def test_the_conflict_update_carries_them_too(self):
        """An insert-only fix leaves every already-existing row NULL forever."""
        block = self._under_block()
        assert '"current_yes_bid": under_best_bid,' in block
        assert '"current_yes_ask": under_best_ask,' in block

    def test_the_arithmetic_lives_in_the_shared_helper(self):
        """Restated inline, the mirror and its tests drift apart."""
        block = self._under_block()
        assert "complementary_book(" in block
        assert "1 - market.best_ask" not in block
        assert "1 - market.best_bid" not in block

    def test_the_over_leg_still_records_its_own_book_unmirrored(self):
        """The mirror must not leak onto the leg that already had a real book."""
        from app.tasks import polymarket

        src = inspect.getsource(polymarket)
        start = src.index("# Create Over/Yes outcome")
        end = src.index("# Create Under/No outcome if available")
        over_block = src[start:end]
        assert "current_yes_bid=market.best_bid," in over_block
        assert "current_yes_ask=market.best_ask," in over_block
        assert "under_best_bid" not in over_block
