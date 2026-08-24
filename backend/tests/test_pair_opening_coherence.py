"""CAL-P094 — the Polymarket pair-opening gate, and the writer sites that honour it.

RED-FIRST, PER SITE. Four production sites changed, and each has a test here that
fails if that site is reverted:

  1. ``_resolve_market_probability_with_source`` labels its source
     -> ``TestResolverNamesItsSource``
  2. the Over-leg gate refuses to stamp an incoherent pair
     -> ``TestWriterHonoursTheGate.test_over_leg_gate_is_wired``
  3. the Under-leg gate is ANDed with the same verdict
     -> ``TestWriterHonoursTheGate.test_under_leg_shares_the_pair_verdict``
  4. ``opening_american_odds`` / ``opening_captured_at`` on the Under leg are gated
     on the UNDER leg -> ``TestWriterHonoursTheGate.test_under_leg_columns_use_the_under_gate``

Sites 2-4 are asserted structurally (against ``inspect.getsource``) rather than by
driving ``poll_polymarket_markets``, for the reason the file's own history gives:
the sub-market writer is 200 lines inside a paginating async task with five upsert
paths, and a behavioural test of it mocks so much of the surrounding machinery
that it stops being evidence about production. The structural assertions each pin
an exact string, so a revert cannot pass them, and the behaviour they are standing
in for is fully covered on the pure gate below.
"""

from __future__ import annotations

import inspect

import pytest

from app.utils.pair_opening_coherence import (
    OK,
    PAIR_SUM_TOLERANCE,
    PAIRED_PRICE_SOURCE,
    REFUSAL_VERDICTS,
    REFUSED_IDENTICAL_LEGS,
    REFUSED_MISSING_LEG,
    REFUSED_SUM_OUT_OF_TOLERANCE,
    REFUSED_UNPAIRED_SOURCE,
    classify_pair_opening,
    pair_opening_allowed,
)


def _market(**kwargs):
    """A ``PolymarketMarket`` with sensible defaults, overridden by kwargs."""
    from app.services.polymarket_api import PolymarketMarket

    defaults = {
        "condition_id": "0xtest",
        "question": "Lakers vs Celtics O/U 213.5",
        "outcomes": ["Over", "Under"],
        "outcome_prices": [],
        "best_bid": None,
        "best_ask": None,
        "last_trade_price": None,
    }
    defaults.update(kwargs)
    return PolymarketMarket(**defaults)


class TestHealthyPairsPass:
    """The gate must not cost us the 72.10% of the population that is fine."""

    def test_ordinary_complementary_pair(self):
        assert classify_pair_opening(0.62, 0.38) == OK

    def test_float_noise_within_tolerance(self):
        assert classify_pair_opening(0.6200001, 0.3799999) == OK

    def test_the_measured_population_average_passes(self):
        # The `complementary` class averages sum 1.0001 over 339,587 markets.
        assert classify_pair_opening(0.5, 0.5001) == OK

    def test_extreme_but_complementary_pair(self):
        assert classify_pair_opening(0.02, 0.98) == OK

    def test_identical_legs_at_a_coin_flip_are_correct_not_the_defect(self):
        """The one case the broken writer got right by coincidence.

        A gate that matched on "both legs equal" alone would refuse this, and 0.5/0.5
        is the single most common honest price in a two-sided market. The defect is
        equal legs AWAY from 0.5, which is why the identical check carries the
        distance-from-0.5 conjunct.
        """
        assert classify_pair_opening(0.5, 0.5) == OK
        assert pair_opening_allowed(0.5, 0.5) is True


class TestTheDefectIsRefused:
    def test_the_original_specimen(self):
        """Purdue/UCLA O/U 143.5 — Over 0.040, Under 0.040, Under wins.

        The row that opened the whole line of enquiry (fp ``08318aba2a1385da``).
        """
        assert classify_pair_opening(0.040, 0.040) == REFUSED_IDENTICAL_LEGS

    def test_identical_legs_are_named_apart_from_a_generic_sum_failure(self):
        """0.04/0.04 also fails the sum check; it must report as ITSELF.

        This is the historical ``231e39c3`` class. A regression there has to be
        legible as that class rather than folded into a generic counter, or the
        18,875-row scar and a brand-new arithmetic bug would show up as one number.
        """
        verdict = classify_pair_opening(0.040, 0.040)
        assert verdict == REFUSED_IDENTICAL_LEGS
        assert verdict != REFUSED_SUM_OUT_OF_TOLERANCE

    @pytest.mark.parametrize("yes_p,no_p", [(0.40, 0.48), (0.60, 0.52), (0.75, 0.58)])
    def test_unequal_pairs_that_do_not_sum_to_one(self, yes_p, no_p):
        assert classify_pair_opening(yes_p, no_p) == REFUSED_SUM_OUT_OF_TOLERANCE

    def test_a_missing_partner_leg_is_refused_not_assumed(self):
        assert classify_pair_opening(0.62, None) == REFUSED_MISSING_LEG
        assert classify_pair_opening(None, 0.38) == REFUSED_MISSING_LEG

    def test_every_refusal_is_a_declared_verdict(self):
        """No refusal may arrive under a name the caller cannot count.

        The task increments ``stats[f"pair_opening_{verdict}"]`` — an unlisted verdict
        would create a stat key nobody reads, which is how a defect goes quiet.
        """
        for pair in [(0.04, 0.04), (0.40, 0.48), (0.62, None), (None, None)]:
            verdict = classify_pair_opening(*pair)
            assert verdict in REFUSAL_VERDICTS


class TestProvenanceIsCheckedBeforeArithmetic:
    """The mixed-source pair — the class that is STILL being written."""

    def test_a_midpoint_paired_with_the_raw_complement_is_refused(self):
        assert (
            classify_pair_opening(0.62, 0.38, price_source="bid_ask_midpoint")
            == REFUSED_UNPAIRED_SOURCE
        )

    def test_refused_even_when_the_numbers_happen_to_sum_to_one(self):
        """The whole reason provenance is tested first.

        A computed midpoint and a raw ``outcome_prices[1]`` can sum to exactly 1.00
        by coincidence. They are still two different instruments, and an arithmetic
        gate alone would wave them through — which is precisely how 5,566
        ``other_noncomp`` markets accumulated while a sum check would have looked
        satisfied on the subset that happened to balance.
        """
        assert classify_pair_opening(0.5, 0.5, price_source="last_trade_price") == (
            REFUSED_UNPAIRED_SOURCE
        )
        assert classify_pair_opening(0.7, 0.3, price_source="best_ask") == (
            REFUSED_UNPAIRED_SOURCE
        )

    def test_the_paired_source_is_the_only_one_that_passes(self):
        assert classify_pair_opening(0.7, 0.3, price_source=PAIRED_PRICE_SOURCE) == OK
        for source in ("bid_ask_midpoint", "last_trade_price", "best_ask", None, ""):
            assert classify_pair_opening(0.7, 0.3, price_source=source) != OK

    def test_a_missing_leg_outranks_an_unpaired_source(self):
        """Order matters at the top of the ladder too: with no partner leg there is
        nothing for provenance to be wrong ABOUT, so the more specific fact wins."""
        assert (
            classify_pair_opening(0.7, None, price_source="best_ask")
            == REFUSED_MISSING_LEG
        )


class TestToleranceIsShared:
    def test_just_inside_the_boundary_passes(self):
        """Deliberately not asserted AT the boundary.

        ``0.5 + (0.5 + 0.02)`` is 1.0200000000000000178 in float, so an
        exactly-at-tolerance pair lands on whichever side the representation error
        happens to fall — a test pinned there asserts the FPU, not the gate. The
        contract is that a pair inside the tolerance passes; the epsilon keeps the
        assertion about that contract.
        """
        assert classify_pair_opening(0.5, 0.5 + PAIR_SUM_TOLERANCE - 1e-9) == OK

    def test_just_past_the_boundary_is_refused(self):
        assert classify_pair_opening(0.5, 0.5 + PAIR_SUM_TOLERANCE + 1e-6) != OK

    def test_a_pair_far_outside_the_tolerance_is_refused_in_both_directions(self):
        assert classify_pair_opening(0.5, 0.9) != OK   # sums high
        assert classify_pair_opening(0.2, 0.2) != OK   # sums low

    def test_the_census_folds_import_this_constant_rather_than_restate_it(self):
        """A tolerance that drifted between writer and census would let the guard
        disagree with the measurement that justified it.

        The two fold scripts under ``backend/scripts`` are the evidence behind this
        module's docstring numbers. They must read the tolerance from here, not
        carry a literal that can be edited on one side only.
        """
        from pathlib import Path

        scripts = Path(__file__).resolve().parents[1] / "scripts"
        for name in ("fold_ou_pair_census.py", "fold_pairclass_ece.py"):
            src = (scripts / name).read_text()
            assert "PAIR_SUM_TOLERANCE" in src, (
                f"{name} restates the pair tolerance instead of importing "
                "PAIR_SUM_TOLERANCE from app.utils.pair_opening_coherence"
            )

    def test_caller_supplied_tolerance_is_honoured(self):
        assert classify_pair_opening(0.5, 0.6, tolerance=0.2) == OK
        assert classify_pair_opening(0.5, 0.6, tolerance=0.01) != OK


class TestResolverNamesItsSource:
    """Site 1 — the resolver must report WHICH price it returned."""

    def test_outcome_prices_path_is_labelled_paired(self):
        from app.tasks.polymarket import _resolve_market_probability_with_source

        m = _market(outcome_prices=[0.62, 0.38], best_bid=0.61, best_ask=0.63)
        prob, source = _resolve_market_probability_with_source(m)
        assert prob == pytest.approx(0.62)
        assert source == PAIRED_PRICE_SOURCE

    def test_midpoint_fallback_is_not_labelled_paired(self):
        from app.tasks.polymarket import _resolve_market_probability_with_source

        m = _market(outcome_prices=[], best_bid=0.55, best_ask=0.57)
        prob, source = _resolve_market_probability_with_source(m)
        assert prob == pytest.approx(0.56)
        assert source == "bid_ask_midpoint"
        assert source != PAIRED_PRICE_SOURCE

    def test_last_trade_fallback_is_not_labelled_paired(self):
        from app.tasks.polymarket import _resolve_market_probability_with_source

        m = _market(outcome_prices=[], best_bid=0.01, best_ask=0.99, last_trade_price=0.17)
        prob, source = _resolve_market_probability_with_source(m)
        assert prob == pytest.approx(0.17)
        assert source == "last_trade_price"
        assert source != PAIRED_PRICE_SOURCE

    def test_a_declined_price_carries_no_source(self):
        """A source label is only meaningful next to a price."""
        from app.tasks.polymarket import _resolve_market_probability_with_source

        m = _market(outcome_prices=[0.50], best_bid=None, best_ask=None)
        assert _resolve_market_probability_with_source(m) == (None, None)

    def test_the_plain_wrapper_still_returns_a_bare_float(self):
        """Every other call site reads the old name and must not see a tuple.

        A tuple is truthy, so `if prob is None or prob <= 0` would raise rather than
        skip — a wrapper regression here breaks paths this fix never touched.
        """
        from app.tasks.polymarket import _resolve_market_probability

        m = _market(outcome_prices=[0.62, 0.38], best_bid=0.61, best_ask=0.63)
        prob = _resolve_market_probability(m)
        assert isinstance(prob, float)
        assert prob == pytest.approx(0.62)


class TestWriterHonoursTheGate:
    """Sites 2-4, pinned structurally. Each assertion fails on a revert."""

    @staticmethod
    def _submarket_block() -> str:
        from app.tasks import polymarket

        src = inspect.getsource(polymarket)
        start = src.index("# Create Over/Yes outcome")
        end = src.index("# Also keep parent market outcomes")
        assert end > start
        return src[start:end]

    def test_the_gate_is_imported_not_reimplemented(self):
        from app.tasks import polymarket

        src = inspect.getsource(polymarket)
        assert "from app.utils.pair_opening_coherence import" in src, (
            "the writer must share the census's gate; a restated tolerance is how "
            "the guard and its evidence drift apart"
        )

    def test_over_leg_gate_is_wired(self):
        """Site 2 — the Over leg's opening is withheld on an incoherent pair."""
        block = self._submarket_block()
        assert "sub_pair_verdict = classify_pair_opening(" in block
        assert "price_source=prob_source" in block
        assert "if sub_pair_verdict != PAIR_OPENING_OK:" in block
        assert "sub_has_open = False" in block

    def test_under_leg_shares_the_pair_verdict(self):
        """Site 3 — one verdict governs BOTH legs, so a pair is never half-stamped."""
        block = self._submarket_block()
        assert "and sub_pair_verdict == PAIR_OPENING_OK" in block

    def test_under_leg_columns_use_the_under_gate(self):
        """Site 4 — the two columns that were gated on the wrong leg.

        ``opening_captured_at=sub_opening_at`` took the OVER leg's timestamp gate, and
        ``opening_american_odds=under_american if sub_has_trading`` took neither, so
        an Under leg could hold an opening with no capture time (breaking every
        capture-age read of it) or a timestamp and odds with no opening at all.
        """
        block = self._submarket_block()
        assert "opening_american_odds=sub_under_opening_am," in block
        assert "opening_captured_at=sub_under_opening_at," in block
        assert "opening_captured_at=sub_opening_at," not in block.split(
            "# Create Under/No outcome"
        )[-1], "the Under upsert still stamps the Over leg's capture timestamp"

    def test_refusals_are_counted_not_silent(self):
        """A zero-yield guard and an absent guard must not read the same (gotcha #53)."""
        block = self._submarket_block()
        assert 'stats["pair_opening_refused"]' in block
        assert 'stats[f"pair_opening_{sub_pair_verdict}"]' in block

    def test_the_gate_never_writes_a_price_it_invented(self):
        """gotcha #21 in its forward form: refuse, never repair, at ingestion.

        ``1 - prob`` would be indistinguishable from a real quote afterwards, and
        ``calibration_probability`` falls back to ``opening_probability`` — so an
        invented opening becomes a published forecast we are graded on.
        """
        block = self._submarket_block()
        for invented in ("1 - prob", "1.0 - prob", "1 - under_prob", "1.0 - under_prob"):
            assert invented not in block, (
                f"the writer computes {invented!r}; the gate refuses incoherent "
                "pairs, it does not synthesise the missing side"
            )
