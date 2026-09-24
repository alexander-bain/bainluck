"""#7641 — a cumulative ladder is not a distribution, so the card does not divide it.

PILLAR: TRUTH. SHIP: a Discover card stops printing 58% for a market whose own
page prints 96.5%.

`_feed_display_scale` divides every visible percent on a futures card by the
all-outcome sum when that sum lands in (threshold, 2.0]. On a CUMULATIVE ladder —
"Above 175" contains "Above 200" contains "Above 225" — the rungs are nested, so
their sum is not a total and the quotient is not a probability.

MEASURED on the deployed feed 2026-09-21, every futures card cross-read against
its own `/api/futures/{id}`; the card/page split is exactly the divisor:

    Traffic through the Panama Canal?  `Above 175`  .965 / 1.65 -> .5848  (38.0 pts)
    Paramount+ App Downloads           `Above 83`   .660 / 1.58 -> .4177  (24.2 pts)

═══ WHY THE GATE IS NESTEDNESS AND NOT `mutually_exclusive` ═══

The first build of this fix refused the divisor whenever
`futures_markets.mutually_exclusive` was `False`. That is too wide, and CI caught
it: an independent-binary field is ALSO non-exclusive, and dividing that one is
the entire reason `_feed_display_scale` exists (gotcha #58). #4079's
`test_7_display_normalized_card_serves_no_feed_number_while_raw_detail_serves_the_dated_move`
pinned a 1.40-sum independent field that must keep dividing, and the wide gate made
its precondition unreachable. (#7586 later ruled the other way for a FLAGGED
non-exclusive field — the page never divided it — and that test is now `test_7`'s
non-exclusive / `test_7c`'s exclusive pair. The nestedness reasoning here stands:
it still decides for `True` and unknown exclusivity.)

So `test_the_4079_independent_field_still_divides` below is not decoration — it is
the control that failed, reproduced here at unit scale where it runs without a
Postgres. A local band cannot see the real one: that module is `skipif`-gated on
`MOVEMENT_ACCEPTANCE_DATABASE_URL` and SKIPS, and a skip reads exactly like a pass.
"""

import pytest

from app.routes.feed import (
    _feed_display_scale,
    _leader_is_ladder_rung,
    _normalize_feed_probabilities,
    _outcomes_are_cumulative_ladder,
)


class _Outcome:
    """The two shapes `_feed_display_scale` sees agree on these two attributes:
    a live ORM `FuturesOutcome` and a rebuilt snapshot row. `name` is in
    `OUTCOME_COLUMNS`, so the cached path carries it too — which is why this fix
    needs no snapshot schema bump.
    """

    def __init__(self, name, probability):
        self.name = name
        self.current_probability = probability


def _scale(pairs):
    return _feed_display_scale([_Outcome(n, p) for n, p in pairs])


#: The live specimen in the issue title. Sums to 1.65 — under the 2.0 arm that
#: was meant to catch ladders, which is the whole defect.
PANAMA = [
    ("Above 175", 0.965),
    ("Above 200", 0.42),
    ("Above 225", 0.18),
    ("Above 250", 0.06),
    ("Above 275", 0.025),
]

#: #4079 test_7's fixture, to the leg. Independent (non-exclusive) studios, any
#: number of which may announce a delay; sums to 1.40 and MUST keep dividing.
INDEPENDENT_4079 = [
    ("Studio Aster", 0.60),
    ("Studio Birch", 0.50),
    ("Studio Cedar", 0.30),
]

#: A real mutually-exclusive field from the same feed read. Sums to 1.22 of
#: overround; normalizing it is correct and this fix must not touch it.
EXCLUSIVE_FIELD = [
    ("Spain", 0.355),
    ("USA", 0.30),
    ("Brazil", 0.28),
    ("England", 0.285),
]


def test_the_panama_ladder_is_not_divided_by_its_own_rungs():
    """THE SHIP. 0.965 must survive to the card as 0.965, not 0.5848."""
    assert _scale(PANAMA) == 1.0, (
        "a cumulative ladder was divided by the sum of its own nested rungs"
    )


def test_the_4079_independent_field_still_divides():
    """THE CONTROL THAT FAILED IN CI ON THE FIRST BUILD.

    A non-exclusive field that is NOT nested keeps its 1.40 divisor. If this
    reads 1.0, the gate has been widened from "nested" back to "non-exclusive"
    and #4079's real-Postgres acceptance is red again.
    """
    assert _scale(INDEPENDENT_4079) == pytest.approx(1.40)


def test_an_exclusive_field_is_untouched():
    assert _scale(EXCLUSIVE_FIELD) == pytest.approx(1.22)


def test_a_long_ladder_keeps_the_answer_the_2_0_arm_already_gave():
    """The pre-existing arm is not replaced, only completed: a ladder long
    enough to sum past 2.0 was already refused and still is."""
    assert _scale([("Above 1", 0.95), ("Above 2", 0.9), ("Above 3", 0.8),
                   ("Above 4", 0.7)]) == 1.0


def test_one_unparseable_leg_fails_CLOSED_to_todays_behaviour():
    """`cumulative_outcome_ladder` demands EVERY leg parse. A field that is
    mostly rungs plus one prose leg is not proven nested, so it keeps today's
    divisor rather than being guessed at."""
    mixed = [("Above 175", 0.60), ("Above 200", 0.45), ("Something else", 0.35)]
    assert _scale(mixed) == pytest.approx(1.40)


def test_a_single_leg_is_never_a_ladder():
    assert _outcomes_are_cumulative_ladder([_Outcome("Above 10", 0.5)]) is False
    assert _scale([("Above 10", 0.5)]) == 1.0


def test_date_shaped_rungs_are_now_IN_SCOPE_via_7650():
    """THE FLIP THIS TEST WAS WRITTEN TO MAKE DELIBERATE.

    Until #7650 this pinned the opposite assertion — `is False`, divisor 1.42 —
    so that widening the grammar could not happen silently. #7650 measured the
    widening at all four sites `cumulative_outcome_ladder` feeds before wiring
    it (2 card numbers move, 0 bars change, 0 fields collapse, 0 captions are
    withheld) and the pin is now the other way round. The live prices are
    `59693686`'s own, so the 1.42 below is the divisor a reader was actually
    served, not an invented one.
    """
    dates = [("Before Jan 1, 2027", 0.455), ("Before Dec 1, 2026", 0.405),
             ("Before Nov 1, 2026", 0.355), ("Before Oct 1, 2026", 0.205)]
    assert sum(p for _, p in dates) == pytest.approx(1.42), (
        "the specimen no longer reproduces the 1.42 divisor it was chosen for"
    )
    assert _outcomes_are_cumulative_ladder([_Outcome(n, p) for n, p in dates]) is True
    assert _scale(dates) == 1.0


def test_the_mini_list_shares_the_distribution_basis_on_a_ladder():
    """#7016: one outcome must not render at two numbers on one card. The
    divisor is decided in ONE place and `_normalize_feed_probabilities`
    delegates to it, so the mini-list cannot squeeze a ladder the distribution
    left raw."""
    outcomes = [_Outcome(n, p) for n, p in PANAMA]
    top = [{"name": n, "probability": p} for n, p in PANAMA[:3]]
    out = _normalize_feed_probabilities(top, outcomes)
    assert [o["probability"] for o in out] == [0.965, 0.42, 0.18]


def test_both_ladder_predicates_answer_the_same_field_the_same_way():
    """Two helpers, one question — the failure mode is that they drift and the
    card calls a field a ladder for its COPY (#4640) and a distribution for its
    NUMBERS. Both delegate to `cumulative_outcome_ladder`; this pins it.
    """
    for field in (PANAMA, INDEPENDENT_4079, EXCLUSIVE_FIELD):
        dicts = [{"name": n} for n, _ in field]
        objects = [_Outcome(n, p) for n, p in field]
        assert _leader_is_ladder_rung(dicts) == _outcomes_are_cumulative_ladder(objects)


def test_the_gate_is_armed_and_not_a_no_op():
    """Anti-vacuity: the two fields differ ONLY in nestedness, and the function
    must answer them differently. A gate that returned the sum for both, or 1.0
    for both, passes every assertion above that looks at one field alone.
    """
    assert _scale(PANAMA) != _scale(INDEPENDENT_4079)
