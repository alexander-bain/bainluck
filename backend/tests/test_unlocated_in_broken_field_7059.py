"""#7059 — a print on a now-empty book is not a price, inside a field that cannot be one.

WHAT A READER SAW. ``/hub/boxing`` named three different men near-certain to hold
one belt on the *WBC Heavyweight Title on January 1, 2027* card — **Usyk 93% ·
Kabayel 87% · Itauma 79%**, with *Title is vacant* at 23% beneath them. The detail
door served sixteen priced legs summing to **299.5%** under a payload whose own
``mutually_exclusive`` flag reads true. Read from Kalshi directly (notice 26/27,
``event_ticker=KXWBCHEAVYWEIGHTTITLE-27``): ``volume_24h`` 0 and ``liquidity`` 0 on
all seventeen legs, no bid at all on fourteen, no trade since **2026-07-13**.

#6846 fixed the ask-only legs of a proved field and these survive it, because
``_is_ask_only_book`` needs ``last_price == 0`` and every one of them carries a real
past trade — ``current_probability`` equals the newest snapshot's ``last_price`` to
the cent on all seventeen. The trade is real; it is a PRINT on a book that is now
empty.

The rule guarded here is two halves, and the suite pins both as load-bearing:
a field that names two favourites cannot be a distribution, and inside such a field
a leg whose own book bounds nothing loses its number. Neither half alone is the
rule — measured on production 2026-09-18, the book test alone drops
*2027 US Open Men's Singles Winner* from a sum of 1.12 to 0.19.

Specimen values below are the production rows, read 2026-09-18 from
``futures_markets.id = 2951423`` (and 61056094 / 60616652 for the contrast cases).
"""

from types import SimpleNamespace

import pytest

from app.utils.feed_market_quality import (
    EMPTY_BOOK_MIN_SPREAD,
    book_bounds_nothing,
    is_empty_book_midpoint,
)
from app.utils.field_opening_coherence import MIN_FIELD_LEGS
from app.utils.futures_unsupported_price import (
    SECOND_FAVOURITE_CEILING,
    field_names_two_favourites,
    price_is_unlocated_in_broken_field,
)

#: The production shape verdict on the specimen market, verbatim from
#: ``market_metadata->'shape'``.
BELT_SHAPE = {
    "v": 2,
    "shape": "field",
    "evidence": [
        "exactly_one_structured",
        "expected_winners:1",
        "mutually_exclusive:true",
    ],
    "side_kind": "competitors",
    "confidence": "high",
    "exhaustive": True,
    "outcome_count": 17,
    "expected_winners": 1,
    "outcome_relation": "competitors",
    "classifier_version": 2,
}

#: The specimen's legs as production stores them: (name, probability, bid, ask).
#: Tyson Fury (0.97 on a 0.00/0.96 book) is deliberately ABSENT — he is already
#: refused by the #6532 live-book arm, so he is not part of the served column this
#: rule reasons about. That exclusion is itself asserted, below.
BELT_LEGS_SERVED = [
    ("Oleksandr Usyk", 0.93, 0.01, 0.93),
    ("Agit Kabayel", 0.87, 0.05, 0.88),
    ("Moses Itauma", 0.79, 0.00, 0.97),
    ("Title is vacant", 0.225, 0.01, 0.44),
    ("Anthony Joshua", 0.07, 0.00, 0.97),
    ("Andrii Novitskyi", 0.01, 0.00, 0.96),
    ("Fabio Wardley", 0.01, 0.00, 0.25),
    ("Lawrence Okolie", 0.01, 0.00, 0.96),
    ("Martin Bakole", 0.01, 0.00, 0.96),
    ("Daniel Dubois", 0.01, 0.00, 0.96),
    ("Deontay Wilder", 0.01, 0.00, 0.06),
    ("Derek Chisora", 0.01, 0.00, 0.06),
    ("Efe Ajagba", 0.01, 0.00, 0.96),
    ("Filip Hrgović", 0.01, 0.00, 0.94),
    ("Joseph Parker", 0.01, 0.00, 0.25),
    ("Murat Gassiev", 0.01, 0.00, 0.96),
]

KALSHI = "kalshi"
#: The specimen's grade on every leg. A RETRACTION, not a verdict (#6876) — so the
#: rows are still quotes and the rule may speak about them.
RETRACTED = "ungradeable_result"


def _withheld(legs):
    """The names this rule refuses, given a served column."""
    if not field_names_two_favourites([p for _, p, _, _ in legs]):
        return []
    return [
        name
        for name, _, bid, ask in legs
        if price_is_unlocated_in_broken_field(KALSHI, RETRACTED, bid, ask)
    ]


# --------------------------------------------------------------------------
# The field half: an arithmetic impossibility, not a measured band.
# --------------------------------------------------------------------------


def test_the_specimen_column_names_two_favourites():
    assert field_names_two_favourites([p for _, p, _, _ in BELT_LEGS_SERVED]) is True


def test_a_coherent_column_is_not_gated_however_wide_its_books():
    """The 2027 US Open shape: 24 legs summing 1.12, one favourite.

    This is the case the book test alone destroys (1.12 -> 0.19 on production), and
    the only thing standing between it and that outcome is this gate.
    """
    coherent = [0.44] + [0.03] * 23
    assert sum(coherent) == pytest.approx(1.13, abs=0.01)
    assert field_names_two_favourites(coherent) is False


def test_one_favourite_however_extreme_is_never_a_contradiction():
    assert field_names_two_favourites([0.99, 0.02, 0.01]) is False


def test_the_gate_is_strict_two_legs_at_exactly_one_half_sum_to_certainty():
    """0.50 + 0.50 == 1. Impossible starts strictly above it."""
    assert field_names_two_favourites([0.50, 0.50, 0.01]) is False
    assert field_names_two_favourites([0.51, 0.50, 0.01]) is False
    assert field_names_two_favourites([0.51, 0.51, 0.01]) is True


def test_the_ceiling_is_one_half_because_that_is_what_two_legs_can_share():
    assert SECOND_FAVOURITE_CEILING == 0.5


def test_a_field_below_the_minimum_leg_count_is_ordinary_overround():
    """CONCACAF Nations League B: two legs summing 1.24 is a vig story, not a lie.

    The floor is imported from #5539 rather than restated, and it is load-bearing
    for a reason of this rule's own: on a two-leg field "both above 0.5" is what
    ordinary overround looks like.
    """
    assert MIN_FIELD_LEGS == 3
    assert field_names_two_favourites([0.70, 0.54]) is False
    assert field_names_two_favourites([0.70, 0.54, 0.01]) is True


def test_unpriced_legs_are_ignored_not_counted_as_zero():
    """gotcha #53: "nobody is publishing a price" is not "the price is 0"."""
    assert field_names_two_favourites([0.93, 0.87, None]) is False
    assert field_names_two_favourites([0.93, 0.87, None, 0.01]) is True


def test_the_gate_does_not_depend_on_leg_order():
    legs = [p for _, p, _, _ in BELT_LEGS_SERVED]
    assert field_names_two_favourites(list(reversed(legs))) is True


def test_a_sum_rule_cannot_see_this_defect():
    """Why a COUNT. The specimen sums to 2.995 on a mean of 0.187.

    ``field_opening_coherence`` refuses only when the sum exceeds 3.0 AND the mean
    reaches 0.4; the twelve honest 1% legs dilute the mean far below it. The count
    is immune to that dilution, which is the whole reason it is a count.
    """
    from app.utils.field_opening_coherence import (
        FIELD_MEAN_CEILING,
        classify_field_openings,
        REFUSAL_VERDICTS,
    )

    priced = [p for _, p, _, _ in BELT_LEGS_SERVED]
    assert sum(priced) / len(priced) < FIELD_MEAN_CEILING
    assert classify_field_openings(priced, True) not in REFUSAL_VERDICTS
    # ... and yet:
    assert field_names_two_favourites(priced) is True

    # Adding honest longshots can never rescue a column from this rule.
    assert field_names_two_favourites(priced + [0.01] * 50) is True


# --------------------------------------------------------------------------
# The leg half: the book bounds nothing.
# --------------------------------------------------------------------------


def test_the_specimen_loses_its_two_impossible_favourites():
    withheld = _withheld(BELT_LEGS_SERVED)
    assert "Oleksandr Usyk" in withheld
    assert "Moses Itauma" in withheld


def test_the_honest_penny_longshots_keep_their_prices():
    """Wilder and Chisora read 1% on a 0.00/0.06 book. That book bounds them.

    This is the population the naive fix destroys: dropping the trade term inside
    proved fields refuses every zero-bid leg, which on production is 16,092 legs
    against this rule's 429.
    """
    withheld = _withheld(BELT_LEGS_SERVED)
    for name in ("Deontay Wilder", "Derek Chisora", "Joseph Parker", "Fabio Wardley"):
        assert name not in withheld


def test_a_leg_whose_book_still_bounds_it_survives_and_that_is_deliberate():
    """Kabayel: 0.05/0.88 is a spread of 0.83, under the house constant.

    Stated rather than quietly shipped — the specimen keeps ONE favourite, which is
    coherent for a one-winner field. Whether 87% off a July trade is itself honest
    is the staleness question this ship deliberately does not decide.
    """
    assert "Agit Kabayel" not in _withheld(BELT_LEGS_SERVED)


def test_the_column_left_behind_no_longer_names_two_favourites():
    withheld = set(_withheld(BELT_LEGS_SERVED))
    survivors = [p for n, p, _, _ in BELT_LEGS_SERVED if n not in withheld]
    assert sum(1 for p in survivors if p > SECOND_FAVOURITE_CEILING) == 1


def test_the_f1_card_is_spared_because_its_column_names_one_favourite():
    """Spanish GP Q3 Pole Position: 22 legs, every stored book 0.0000/1.0000.

    The loudest card in the stored data — **Lando Norris 99%** on a board where the
    venue quotes no book at all — and this rule does NOT touch it, because only one
    leg sits above a half. Measured through the route, its served column sums to
    exactly 1.00, so there is no impossibility to act on; the book test alone would
    take all 22 of its prices.

    Kept as a guard because it is the case a later widening would reach for first.
    """
    legs = [("Lando Norris", 0.99, 0.0, 1.0), ("Franco Colapinto", 0.10, 0.0, 1.0)] + [
        (f"driver{i}", 0.01, 0.0, 1.0) for i in range(20)
    ]
    assert field_names_two_favourites([p for _, p, _, _ in legs]) is False
    assert _withheld(legs) == []


def test_a_board_printing_fifteen_certainties_for_one_winner_loses_all_of_them():
    """"Most viewed movie on Netflix (April 17-23, 2026)" — 15 stored legs at 1.00.

    The predicate's answer on that shape, asserted for completeness. It costs no
    reader anything today: all 28 of those April-2026 boards already serve NO price,
    withheld in full by the four shipped arms — which is why the ship's measured
    reach is 12 legs and not the 429 a stored-row census reports.
    """
    legs = [(f"title{i}", 1.0, 0.0, 1.0) for i in range(15)]
    assert set(_withheld(legs)) == {name for name, _, _, _ in legs}


# --------------------------------------------------------------------------
# Scope and fail-open, inherited from `needs_trade_evidence` and restated nowhere.
# --------------------------------------------------------------------------


@pytest.mark.parametrize("source", ["polymarket", "odds_api", "", None])
def test_only_kalshi(source):
    assert price_is_unlocated_in_broken_field(source, RETRACTED, 0.0, 0.97) is False


def test_kalshi_is_matched_case_and_space_insensitively():
    assert price_is_unlocated_in_broken_field(" Kalshi ", RETRACTED, 0.0, 0.97) is True


@pytest.mark.parametrize(
    "grade", ["api_settlement", "did_not_play", "withdrew", "all_losers", "date_passed"]
)
def test_a_graded_row_is_never_touched_settled_means_settled(grade):
    assert price_is_unlocated_in_broken_field(KALSHI, grade, 0.0, 0.97) is False


def test_a_retraction_is_not_a_grade():
    """#6876. ``ungradeable_result`` asserts no winner, so the number is still a quote."""
    assert price_is_unlocated_in_broken_field(KALSHI, RETRACTED, 0.0, 0.97) is True
    assert price_is_unlocated_in_broken_field(KALSHI, None, 0.0, 0.97) is True


@pytest.mark.parametrize("bid,ask", [(None, 0.97), (0.0, None), (None, None)])
def test_an_absent_side_fails_open(bid, ask):
    """We never recorded a book. Absence is not evidence, here as everywhere else."""
    assert price_is_unlocated_in_broken_field(KALSHI, RETRACTED, bid, ask) is False


# --------------------------------------------------------------------------
# The factored book predicate, and that factoring it changed nothing.
# --------------------------------------------------------------------------


def test_the_width_bound_is_the_house_constant_not_a_new_one():
    assert EMPTY_BOOK_MIN_SPREAD == 0.90


@pytest.mark.parametrize(
    "bid,ask,expected",
    [
        (0.00, 0.90, True),  # exactly the bound, inclusive as it has always been
        (0.05, 0.95, True),  # the exact-threshold book #6727 names
        (0.01, 0.93, True),  # Usyk
        (0.05, 0.88, False),  # Kabayel — 0.83, the book still bounds him
        (0.00, 0.06, False),  # an honest penny longshot
        (0.00, 0.8999, False),
    ],
)
def test_book_bounds_nothing_boundaries(bid, ask, expected):
    assert book_bounds_nothing(bid, ask) is expected


@pytest.mark.parametrize("bid,ask", [(None, 0.97), (0.0, None), (None, None)])
def test_book_bounds_nothing_fails_open_on_an_absent_side(bid, ask):
    assert book_bounds_nothing(bid, ask) is False


@pytest.mark.parametrize(
    "prob,bid,ask,expected",
    [
        (0.50, 0.00, 1.00, True),  # the midpoint of an empty book
        (0.475, 0.00, 0.95, True),
        (0.48, 0.01, 0.94, True),  # the Milwaukee Bucks book #6727 closed
        (0.79, 0.00, 0.97, False),  # off-midpoint: condition 3 still spares it
        (0.50, 0.40, 0.60, False),  # a real book
        (None, 0.00, 1.00, False),
    ],
)
def test_is_empty_book_midpoint_is_unchanged_by_the_factoring(prob, bid, ask, expected):
    """The regression guard on the refactor. Condition 3 is untouched — which is
    exactly why Itauma at 0.79 on a 0.00/0.97 book needed a new rule at all."""
    assert is_empty_book_midpoint(prob, bid, ask) is expected


# --------------------------------------------------------------------------
# The route arm: the gate is counted over the column a reader is SHOWN.
# --------------------------------------------------------------------------


def _market(legs, shape=BELT_SHAPE, source=KALSHI):
    return SimpleNamespace(
        source=source,
        market_type="field",
        market_metadata={"shape": shape},
        outcomes=[
            SimpleNamespace(
                id=i,
                current_probability=p,
                current_yes_bid=bid,
                current_yes_ask=ask,
                resolution_source=RETRACTED,
                is_winner=None,
            )
            for i, (_, p, bid, ask) in enumerate(legs)
        ],
    )


def test_the_arm_counts_survivors_not_stored_rows():
    """A rule about what a page claims may not be measured on rows the page withholds.

    Two legs above a half, one of them already refused upstream: the column a reader
    sees names ONE favourite, so this arm must not fire.
    """
    from app.routes.futures import _unlocated_in_broken_field_outcome_ids

    market = _market(
        [
            ("already refused", 0.97, 0.00, 0.96),
            ("the only favourite", 0.93, 0.01, 0.93),
            ("longshot", 0.01, 0.00, 0.06),
        ]
    )
    assert _unlocated_in_broken_field_outcome_ids(market, {0}) == set()
    # ... and with nothing refused upstream, the same market IS gated.
    assert _unlocated_in_broken_field_outcome_ids(market, set()) == {0, 1}


def test_the_arm_fires_on_the_specimen():
    from app.routes.futures import _unlocated_in_broken_field_outcome_ids

    market = _market(BELT_LEGS_SERVED)
    withheld = _unlocated_in_broken_field_outcome_ids(market, set())
    names = {BELT_LEGS_SERVED[i][0] for i in withheld}
    assert "Oleksandr Usyk" in names and "Moses Itauma" in names
    assert "Deontay Wilder" not in names and "Agit Kabayel" not in names


def test_the_arm_never_withholds_a_leg_that_has_no_price_to_withhold():
    from app.routes.futures import _unlocated_in_broken_field_outcome_ids

    legs = list(BELT_LEGS_SERVED) + [("never priced", None, 0.00, 1.00)]
    market = _market(legs)
    assert (len(legs) - 1) not in _unlocated_in_broken_field_outcome_ids(market, set())


@pytest.mark.parametrize(
    "shape",
    [
        {**BELT_SHAPE, "exhaustive": False},
        {**BELT_SHAPE, "expected_winners": 2},
        {**BELT_SHAPE, "outcome_relation": "cumulative_thresholds"},
        {**BELT_SHAPE, "outcome_relation": "independent_participation"},
        {**BELT_SHAPE, "outcome_relation": "unknown"},
        {},
        None,
    ],
)
def test_a_market_whose_shape_is_not_proved_exclusive_never_reaches_the_gate(shape):
    """Fails closed on absent or unproved metadata, exactly as #6846's call site does."""
    from app.routes.futures import _unlocated_in_broken_field_outcome_ids

    market = _market(BELT_LEGS_SERVED, shape=shape)
    assert _unlocated_in_broken_field_outcome_ids(market, set()) == set()


@pytest.mark.asyncio
async def test_the_composition_hands_this_arm_the_ids_the_four_above_refused():
    """The arm reading survivors is only true if the UNION actually passes them in.

    Pinned at :func:`_withheld_price_outcome_ids` rather than at the arm, because a
    composition that hands it ``set()`` is indistinguishable from a correct one when
    the arm is tested alone — the mutant that makes that substitution survived every
    direct test in this file.

    🪤 THE SPECIMEN USED TO NEED NO DATABASE AND NO LONGER DOES (#7747). The original
    premise was that every leg carries a bid above zero, so none is a candidate for
    ``needs_trade_evidence`` (its ask-only screen requires a zero bid), and ``db`` was
    passed as ``None`` to prove the arms returned before querying. #7747 added a
    second screen to that same candidate list — ``needs_unbacked_ask_evidence``, which
    asks whether the book LOCATES the price rather than whether it is empty — and legs
    A and B both serve their own 0.93 ask across a 0.92 spread, so both are now
    candidates and the trade read is reached. That is a real widening, not a test
    artifact, so the fixture gains a session instead of being bent back into shape.

    The session returns NO trade rows, which is the honest way to hold this test on
    its own subject: ``has_trade_evidence`` is then False for both legs, #7747's arm
    fails OPEN (gotcha #53 — "we never looked" is not "it never traded"), and the
    composition's answer is unchanged. #7747's own file owns the case where a trade
    row exists.

    Leg A serves 0.97 above its own 0.93 ask and is refused by the #6532 arm. The
    column a reader is shown is B and C, which names ONE favourite — so this arm must
    stay silent and B must keep its price. Counting stored rows instead would see A
    and B as two favourites and take B's number away.
    """
    from app.routes.futures import _withheld_price_outcome_ids

    class _NoTrades:
        async def execute(self, statement):
            return SimpleNamespace(all=lambda: [])

    market = _market(
        [
            ("refuted by its own book", 0.97, 0.01, 0.93),
            ("the only favourite shown", 0.93, 0.01, 0.93),
            ("longshot on a real book", 0.01, 0.01, 0.06),
        ]
    )
    assert await _withheld_price_outcome_ids(_NoTrades(), market) == {0}


def test_the_arm_is_one_pass_and_does_not_iterate_to_coherence():
    """Its own refusals do not re-open the gate. Withholding, never chasing a sum."""
    from app.routes.futures import _unlocated_in_broken_field_outcome_ids

    market = _market(BELT_LEGS_SERVED)
    first = _unlocated_in_broken_field_outcome_ids(market, set())
    second = _unlocated_in_broken_field_outcome_ids(market, first)
    assert second == set()
