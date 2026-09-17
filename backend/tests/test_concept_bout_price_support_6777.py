"""#6777: a fight card may not lead with a probability its own book does not support.

WHAT A READER SAW. The Power Slap 23 card on Discover (rank 118 of 141, 2026-09-17)
led with "Brandon Wilson 50% · Brian Ellis 49.5%". Both rows quote 0.02/0.99 and
0.01/0.98. A quote pair that wide locates no price at 50%, and the card printed one
anyway while `_concept_can_render` correctly suppressed the two UFC cards beside it —
the asymmetry is the defect.

THIS FILE IS AUTHORITY'S HALF OF CODEX'S OWNER SPLIT (issue comment 19:26Z): the price
policy and the shared eligibility predicate. Discover owns the concept/feed
integration. `bout_price_is_supported` exists so that integration imports ONE rule
rather than growing a second parallel filter — "one correction, not two filters".

WHAT IS AND IS NOT CLAIMED. `volume` is NULL on all four specimen rows and this ship
reads no volume column: a NULL is unknown, not a zero (gotcha #53), so "never traded"
is not asserted here or anywhere in the fix. The claim is only that the book we hold
does not support the number we display. Equally, neither a 50% price nor a wide spread
alone refuses anything — `is_empty_book_midpoint` is a conjunction and
`TestNoNewRuleWasInvented` pins both halves of it firing separately.

THE ONE THING THIS ADDS TO THE SHIPPED PREDICATE IS THE QUANTIFIER, and
`TestOneRefusedSideRefusesThePair` is the arm that measures it. The six shipped call
sites drop a LEG; a bout cannot, because keeping one side of a two-sided question
prints "Brian Ellis 49.5%" as a leader — #5333's defect one surface over.

RED-FIRST, run rather than asserted. See the module's closing comment for the two
mutations and their exact counts.
"""

from __future__ import annotations

import pytest

from app.utils.feed_market_quality import (
    EMPTY_BOOK_MIDPOINT_TOLERANCE,
    EMPTY_BOOK_MIN_SPREAD,
    bout_price_is_supported,
    is_empty_book_midpoint,
)

# The specimen, read off production 2026-09-17 19:0xZ and quoted rather than
# paraphrased. `futures_markets` 61148613 / 61131225, source `polymarket`, status
# `open`, every leg ungraded (`resolution_source` NULL, `is_winner` NULL), `volume`
# NULL. Each entry is (outcome_id, name, probability, yes_bid, yes_ask).
WILSON = (229923170, "Brandon Wilson", 0.500000, 0.0200, 0.9900)
ELLIS = (229923171, "Brian Ellis", 0.495000, 0.0100, 0.9800)
# The same card's other stored market: a KO prop and a duplicate bout leg, both on the
# identical book. They are here because the concept adapter's `children` rail draws
# from the same rows the `primary` pair does.
KO_PROP = (229834506, "Ellis to win by KO/TKO?", 0.500000, 0.0200, 0.9900)
BOUT_LEG = (229923172, "Brandon Wilson vs. Brian Ellis", 0.500000, 0.0200, 0.9900)

#: The control named in #6777's own body: Dana White's Contender Series, Moran/Degli,
#: the one "priced" bout on a card the gate already suppresses. Same class, one cent
#: over, and it must be refused for the same reason or the gate stays asymmetric.
DWCS_MORAN = (0.500000, 0.0300, 0.9800)


def _side(row):
    """The (probability, bid, ask) triple the helper takes, from a specimen row."""
    return row[-3:]


class TestTheSpecimenIsRefused:
    """The four stored rows behind the card a reader complained about."""

    @pytest.mark.parametrize("row", [WILSON, ELLIS, KO_PROP, BOUT_LEG], ids=lambda r: r[1])
    def test_each_stored_leg_prices_an_empty_book(self, row):
        assert is_empty_book_midpoint(*_side(row)) is True

    def test_the_displayed_pair_may_not_show_numbers(self):
        assert bout_price_is_supported([_side(WILSON), _side(ELLIS)]) is False

    def test_the_dwcs_bout_named_in_the_issue_is_the_same_class(self):
        assert bout_price_is_supported([DWCS_MORAN]) is False


class TestControlsThatMustStayGreen:
    """The four classes codex named, plus the shapes the shipped predicate protects.

    Every one of these is a bout that KEEPS its numbers. They are the cost side of the
    ship: if any of them goes red the rule has stopped being the shipped one.
    """

    def test_a_genuinely_traded_tight_book_coin_flip_keeps_its_numbers(self):
        # 48c/52c on both sides. A real 50/50 is the commonest honest bout there is,
        # and refusing it would be the whole product.
        assert bout_price_is_supported([(0.50, 0.48, 0.52), (0.50, 0.48, 0.52)]) is True

    def test_a_merely_wide_two_sided_book_on_its_midpoint_keeps_its_numbers(self):
        # 0.40/0.60 is wide by `is_fabricated_midpoint`'s 0.20 bar and sits exactly on
        # its own midpoint — and is kept, because the empty-book rule needs 0.90.
        assert bout_price_is_supported([(0.50, 0.40, 0.60)]) is True

    def test_a_supported_lone_ask_keeps_its_number(self):
        # One-sided: an ask at 97c with no bid still carries information, and the
        # shipped predicate deliberately does not treat a missing side as the widest
        # quote on that side. Both orientations, because a bout has two.
        assert bout_price_is_supported([(0.50, None, 0.97), (0.50, 0.03, None)]) is True

    def test_a_model_priced_bout_with_no_book_at_all_keeps_its_numbers(self):
        # DataGolf / odds_api / a derived complement: no book, nothing to contradict.
        assert bout_price_is_supported([(0.50, None, None), (0.50, None, None)]) is True

    def test_settled_results_survive_a_stale_empty_book(self):
        # Settled means settled. A graded pair carries 1.0/0.0, a whole tolerance away
        # from any midpoint this rule can reach, so the result is kept BY CONSTRUCTION
        # — there is no `resolution_source` carve-out here and none is needed.
        assert bout_price_is_supported([(1.0, 0.02, 0.99), (0.0, 0.02, 0.99)]) is True

    def test_a_wide_book_priced_off_its_midpoint_keeps_its_number(self):
        # The class `is_empty_book_midpoint`'s condition 3 exists to protect: a price
        # far from the midpoint of a wide book came from somewhere the book is not.
        assert bout_price_is_supported([(0.88, 0.02, 0.99)]) is True

    def test_a_non_polymarket_bout_is_judged_by_the_same_three_columns(self):
        # The rule carries no venue term, by design — it reads three columns of one
        # write. An honest Kalshi moneyline keeps its numbers; a Kalshi row in the
        # specimen's shape is refused on the same evidence, and neither outcome turns
        # on where the row came from.
        assert bout_price_is_supported([(0.62, 0.61, 0.64), (0.38, 0.36, 0.39)]) is True
        assert bout_price_is_supported([(0.50, 0.02, 0.99)]) is False

    def test_an_unpriced_side_is_not_refused_by_this_rule(self):
        # A NULL probability is the caller's "half a bout is not a bout" question and
        # is deliberately left there, so the two causes stay separately measurable.
        assert bout_price_is_supported([(None, 0.02, 0.99)]) is True

    def test_a_bout_with_no_sides_is_not_refused_by_this_rule(self):
        # `_competitors` returns [] for a row whose outcomes are not the titled pair.
        # That is `venue_bout_is_priced`'s refusal, already shipped, not this one.
        assert bout_price_is_supported([]) is True


class TestOneRefusedSideRefusesThePair:
    """The quantifier is ANY. This is the only thing the helper adds to the predicate.

    #6727 proved the leg rule answers the same for a leg and its algebraic complement,
    and the specimen's two books ARE exact complements — so on today's rows the ANY and
    the ALL forms agree and this arm is the only place the difference is observable.
    The two sides of a venue bout are two separate rows written by two upserts, so
    nothing keeps them complementary; a mixed pair is the case that must not print one
    side alone.
    """

    def test_a_refused_side_beside_a_supported_one_refuses_the_pair(self):
        assert bout_price_is_supported([_side(WILSON), (0.49, 0.47, 0.51)]) is False

    def test_order_does_not_matter(self):
        assert bout_price_is_supported([(0.49, 0.47, 0.51), _side(WILSON)]) is False

    def test_the_all_form_would_have_kept_that_pair(self):
        # Stated as an explicit contrast so the choice is measured, not assumed: the
        # "every leg is a phantom" quantifier the ladder surfaces use
        # (`_futures_market_prices_only_empty_books`) says this pair is fine.
        mixed = [_side(WILSON), (0.49, 0.47, 0.51)]
        assert all(is_empty_book_midpoint(*s) for s in mixed) is False
        assert bout_price_is_supported(mixed) is False

    def test_the_specimen_pair_is_complementary_so_both_forms_agree_there(self):
        # Both sides quantised to the 4dp the two book columns are stored at, because
        # this compares a DERIVED complement against a STORED one: `1 - 0.99` is
        # 0.010000000000000009 and a bare `==` against the stored 0.0100 is false for
        # a pair that is in fact complementary. (The opposite rule holds when sweeping
        # a bound — `is_empty_book_midpoint`'s docstring — where tidying hides the
        # escaping class. Quantise when comparing to a stored value, not when probing
        # a boundary.)
        _, _, _, w_bid, w_ask = WILSON
        _, _, _, e_bid, e_ask = ELLIS
        assert (e_bid, e_ask) == (round(1 - w_ask, 4), round(1 - w_bid, 4))
        assert all(is_empty_book_midpoint(*_side(r)) for r in (WILSON, ELLIS))


class TestNoNewRuleWasInvented:
    """The helper is a delegation. It owns no constant and reads no fourth column.

    The two conditions of `is_empty_book_midpoint` are pinned firing SEPARATELY,
    because codex's constraint is exactly that neither one alone may refuse: a 50%
    price is not a refusal and a wide spread is not a refusal.
    """

    def test_a_wide_spread_alone_does_not_refuse(self):
        # Spread 0.97, comfortably past the bar — but the price is nowhere near the
        # midpoint, so nothing is refused.
        assert round(0.99 - 0.02, 4) >= EMPTY_BOOK_MIN_SPREAD
        assert bout_price_is_supported([(0.15, 0.02, 0.99)]) is True

    def test_a_fifty_percent_price_alone_does_not_refuse(self):
        # Sitting exactly on the midpoint, on a book that bounds the price tightly.
        assert round(0.52 - 0.48, 4) < EMPTY_BOOK_MIN_SPREAD
        assert bout_price_is_supported([(0.50, 0.48, 0.52)]) is True

    def test_it_agrees_with_the_shipped_leg_predicate_on_every_single_side(self):
        # The delegation itself: a one-sided call must be the leg rule, negated. A
        # second constant or a re-derived shape shows up here as a disagreement.
        grid = [
            (p / 20, b / 20, a / 20)
            for p in range(0, 21)
            for b in range(0, 21)
            for a in range(0, 21)
        ]
        disagreements = [
            s for s in grid if bout_price_is_supported([s]) is is_empty_book_midpoint(*s)
        ]
        assert disagreements == []

    def test_it_tracks_the_shipped_tolerance_rather_than_restating_it(self):
        # One tick outside the tolerance is kept; the boundary itself is refused.
        # Quantised to the 4dp the two book columns are stored at, because an
        # inclusive bound compared against float arithmetic is a strict one (the
        # `price_change_stamp.py` precision trap).
        mid = (0.02 + 0.99) / 2
        assert bout_price_is_supported([(mid, 0.02, 0.99)]) is False
        outside = round(mid + EMPTY_BOOK_MIDPOINT_TOLERANCE + 0.001, 4)
        assert bout_price_is_supported([(outside, 0.02, 0.99)]) is True


class TestTheContractTheConceptPathStillOwes:
    """What Discover's half has to do, pinned where it can be read rather than only
    written in a docstring. These are facts about TODAY's tree, so they redden the day
    the integration lands — which is the point: they are a handover, not a guard, and
    the integration replaces them with its own arms.
    """

    def test_the_envelope_builders_hold_the_book_and_can_ask(self):
        # `_competitors` and `_fight_outcomes` iterate ORM FuturesOutcome rows, so the
        # two columns the rule needs are already in hand and no read is added.
        from app.models import FuturesOutcome

        assert hasattr(FuturesOutcome, "current_yes_bid")
        assert hasattr(FuturesOutcome, "current_yes_ask")

    def test_the_cache_only_leader_cannot_ask_and_must_inherit(self):
        # `_resolve_concept_leader` reads a cached envelope whose competitor entries
        # carry name/probability/movement and no book at all. Widening that schema is
        # the invention this ship declines; the refusal belongs at the builder.
        from app.routes.feed import _bout_from_competitors

        envelope_pair = [
            {"name": "Brandon Wilson", "probability": 0.5},
            {"name": "Brian Ellis", "probability": 0.495},
        ]
        bout = _bout_from_competitors({"kind": "co_equal_list"}, envelope_pair)
        assert bout is not None
        assert all("yes_bid" not in c and "yes_ask" not in c for c in bout["competitors"])

    def test_the_attached_headline_bout_is_the_reader_the_envelope_does_not_cover(self):
        # `_attach_headline_bouts` reads futures_outcomes directly and its result WINS
        # over the envelope pair at `_concept_can_render`. Its contract is two more
        # columns in the SELECT it already runs — today it projects neither.
        import inspect

        from app.utils import event_combat

        src = inspect.getsource(event_combat._attach_headline_bouts)
        assert "FuturesOutcome.current_probability" in src
        assert "FuturesOutcome.current_yes_bid" not in src
        assert "FuturesOutcome.current_yes_ask" not in src


# RED-FIRST, both mutations applied to `bout_price_is_supported` and RUN on this tree
# (the applied line grepped back out each time before the run, because a mutation that
# did not apply reads exactly like a survivor):
#
#   1. quantifier flipped to ALL (`return not all(...)` over the sides) —
#      **4 failed, 22 passed**. All three `TestOneRefusedSideRefusesThePair` mixed-pair
#      arms redden, plus `test_a_bout_with_no_sides_is_not_refused_by_this_rule` — an
#      empty `all()` is vacuously true, so the no-sides bout flips to refused. That
#      fourth failure is the one worth keeping: the quantifier and the empty case are
#      the same decision, and the ALL form gets the empty case wrong too.
#
#   2. delegation replaced by a hand-rolled `spread >= EMPTY_BOOK_MIN_SPREAD` with no
#      midpoint term — **6 failed, 20 passed**: `test_a_wide_spread_alone_does_not_refuse`,
#      the grid-agreement arm, the tolerance arm, `test_a_wide_book_priced_off_its_
#      midpoint_keeps_its_number`, `test_an_unpriced_side_is_not_refused_by_this_rule`
#      and — the expensive one — `test_settled_results_survive_a_stale_empty_book`.
#      A second copy of this rule that drops condition 3 deletes results.
