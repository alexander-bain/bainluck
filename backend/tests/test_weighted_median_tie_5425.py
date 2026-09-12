"""#5425 — an exact weighted-median tie is averaged, not resolved downwards.

`_weighted_median` walked values ascending and returned the first whose
cumulative weight reached half the total. With two equal weights the cumulative
reaches EXACTLY half at the first value, so the published number was
``min(a, b)`` — for every two-venue event, always, by construction.

That is not a tail case. #1999 switched the pre-game recency decay off, which
made "two market sources at their equal base weight of 0.8" the ordinary
pre-game shape, and the old rule quoted the pessimistic end of the pair every
time.

MEASURED on production, 2026-09-12 04:55Z, the shipped aggregator replayed over
the raw `win_probability_sources` of 1,639 rows: 59 rows move, EVERY ONE
UPWARD, none downward, 13 two-source rows unchanged because the venues agree
exactly. All 210 rows carrying three or more sources are bit-for-bit unchanged.

The tests below are ordered as the argument runs: the tie is averaged, the bias
it removes was one-directional, everything that is not an exact tie is
untouched, and the degenerate inputs still behave.
"""

import random

import pytest

from app.utils.aggregation import (
    SOURCE_WEIGHTS,
    _weighted_median,
    effective_source_weights,
)


def _lower_value_tie_rule(values, weights):
    """The pre-#5425 implementation, kept so the tests can state the delta.

    Any test that asserts "unchanged" must compare against the real old code;
    asserting a value it computed itself would pass against a mutant that broke
    both paths the same way.
    """
    if len(values) == 1:
        return values[0]
    paired = sorted(zip(values, weights), key=lambda x: x[0])
    total = sum(w for _, w in paired)
    if total <= 0:
        vals = [v for v, _ in paired]
        return vals[len(vals) // 2]
    half = total / 2.0
    cumulative = 0.0
    for value, weight in paired:
        cumulative += weight
        if cumulative >= half:
            return value
    return paired[-1][0]


class TestTheExactTieIsAveraged:
    def test_two_equal_weights_return_the_midpoint_not_the_lower_value(self):
        assert _weighted_median([0.42, 0.46], [0.8, 0.8]) == pytest.approx(0.44)

    def test_the_production_specimen_moves_to_the_midpoint(self):
        """Event 15308240 (NCAAF FCS), the largest mover on the 2026-09-12 board.

        kalshi 0.8050 and polymarket 0.8900, both at the 0.8 base weight with
        the pre-game decay off. Production published 0.8050 — the lower venue,
        4.25 points below the middle of a pair it trusts equally.
        """
        assert _weighted_median([0.8050, 0.8900], [0.8, 0.8]) == pytest.approx(0.84750)

    def test_the_order_the_sources_arrive_in_cannot_change_the_answer(self):
        """The tie branch reads a sorted pair, so the caller's order is inert.

        Worth pinning because `effective_source_weights` returns dict order,
        which is insertion order of the JSONB, which the writers control.
        """
        assert _weighted_median([0.89, 0.805], [0.8, 0.8]) == pytest.approx(
            _weighted_median([0.805, 0.89], [0.8, 0.8])
        )

    def test_an_exact_tie_at_a_weight_other_than_0_8_is_still_averaged(self):
        """`w + w` is exact in binary floating point for ANY w, so the branch
        is not a property of the 0.8 constant and must not be written as one."""
        for w in (0.1, 0.3, 1.0, 1.5, 3.0, 0.7734375):
            assert _weighted_median([0.2, 0.6], [w, w]) == pytest.approx(0.4), w

    def test_a_NEAR_tie_is_not_a_tie_and_the_heavier_source_wins_outright(self):
        """The tie test is exact equality on purpose; this is what forbids an
        epsilon.

        With weights 0.8 and 0.8000000001 the second source is strictly
        heavier, so the median is strictly its value — there is no ambiguity to
        split. A tolerance of any size would average here instead, moving the
        published number half the spread away from the answer, and it would do
        so on exactly the near-misses a decayed weight produces.
        """
        assert _weighted_median([0.2, 0.6], [0.8, 0.8000000001]) == pytest.approx(0.6)
        assert _weighted_median([0.2, 0.6], [0.8000000001, 0.8]) == pytest.approx(0.2)

    def test_two_venues_that_agree_publish_that_agreed_value(self):
        """The 13 rows in the production count that do not move. The midpoint of
        a pair that agrees is the value both stated, so no reader sees a number
        neither venue said."""
        assert _weighted_median([0.61, 0.61], [0.8, 0.8]) == pytest.approx(0.61)


class TestTheBiasItRemovesWasOneDirectional:
    def test_the_old_rule_returned_the_minimum_for_every_equal_weight_pair(self):
        """The defect stated as the property it actually was: not "sometimes
        low" but "the lower one, always"."""
        rng = random.Random(5425)
        for _ in range(500):
            a, b = rng.random(), rng.random()
            assert _lower_value_tie_rule([a, b], [0.8, 0.8]) == min(a, b)

    def test_the_new_rule_never_moves_the_published_number_down(self):
        """59 of 59 production movers went up. That is structural, not a
        property of Friday's board: the midpoint of a pair is never below its
        minimum, so the fix can only ever correct upward."""
        rng = random.Random(54250)
        for _ in range(500):
            a, b = rng.random(), rng.random()
            assert _weighted_median([a, b], [0.8, 0.8]) >= _lower_value_tie_rule(
                [a, b], [0.8, 0.8]
            )

    def test_the_midpoint_lies_between_the_two_venues(self):
        """A blend must stay inside the range its sources stated. Guards against
        a tie branch that averages the wrong pair (e.g. the sorted-ascending
        index off by one), which would leave the interval entirely."""
        rng = random.Random(2677)
        for _ in range(500):
            a, b = rng.random(), rng.random()
            out = _weighted_median([a, b], [0.8, 0.8])
            assert min(a, b) <= out <= max(a, b)


class TestNonTiesAreUntouched:
    def test_unequal_weights_match_the_old_implementation_exactly(self):
        """The blast radius claim, as a property rather than a sample.

        The two implementations differ only where cumulative weight lands
        exactly on half; with weights drawn at random that effectively never
        happens, so every one of these must agree bit-for-bit.
        """
        rng = random.Random(1999)
        for _ in range(2000):
            n = rng.randint(2, 5)
            values = [rng.random() for _ in range(n)]
            weights = [rng.uniform(0.1, 3.0) for _ in range(n)]
            if _is_exact_tie(weights):
                continue
            assert _weighted_median(values, weights) == _lower_value_tie_rule(
                values, weights
            )

    def test_a_clear_majority_source_still_wins_outright(self):
        """betting at 3.0 against one 0.8 market holds more than half the weight,
        so it is the median outright and no averaging may happen."""
        assert _weighted_median([0.30, 0.70], [3.0, 0.8]) == pytest.approx(0.30)
        assert _weighted_median([0.70, 0.30], [3.0, 0.8]) == pytest.approx(0.70)

    def test_the_real_three_source_shapes_are_bit_for_bit_unchanged(self):
        """All 210 production rows with 3+ sources were unchanged. This is why:
        the live weight combinations do not land on half exactly.

        Built from `SOURCE_WEIGHTS` rather than hard-coded numbers, so that
        re-weighting a source re-aims this test instead of leaving it asserting
        a table that no longer exists.
        """
        combos = [
            ("betting", "espn", "kalshi"),
            ("betting", "kalshi", "polymarket"),
            ("betting", "espn", "stat_model"),
            ("espn", "kalshi", "polymarket"),
            ("betting", "espn", "kalshi", "polymarket"),
        ]
        rng = random.Random(4988)
        for combo in combos:
            weights = [SOURCE_WEIGHTS[s] for s in combo]
            for _ in range(200):
                values = [rng.random() for _ in range(len(combo))]
                assert _weighted_median(values, weights) == _lower_value_tie_rule(
                    values, weights
                ), combo

    def test_a_three_source_shape_that_DOES_tie_exactly_is_averaged(self):
        """The converse control, so the test above is read as "these weights do
        not tie" and never as "three sources are exempt".

        3.0 against 1.5 + 1.5 reaches exactly half at the first value. It
        reaches no production row today — no live combination has that shape —
        but the branch is general and a future re-weighting could create it.
        """
        assert _weighted_median([0.2, 0.6, 0.9], [3.0, 1.5, 1.5]) == pytest.approx(0.4)


class TestDegenerateInputs:
    def test_empty_still_raises(self):
        with pytest.raises(ValueError):
            _weighted_median([], [])

    def test_a_single_value_is_returned_whatever_its_weight(self):
        assert _weighted_median([0.37], [0.0]) == pytest.approx(0.37)
        assert _weighted_median([0.37], [3.0]) == pytest.approx(0.37)

    def test_all_zero_weights_keep_the_simple_median_fallback(self):
        assert _weighted_median([0.1, 0.2, 0.3], [0.0, 0.0, 0.0]) == pytest.approx(0.2)

    def test_a_zero_weight_neighbour_is_not_the_edge_of_the_tie_interval(self):
        """With weights 1.0 / 0.0 / 1.0 the ambiguous interval is [0.2, 0.9] —
        the zero-weight 0.5 costs nothing to move across, so it is not an
        endpoint. Averaging against it would report a narrower ambiguity than
        the data has and would quietly let a weightless source steer the hero.
        """
        assert _weighted_median([0.2, 0.5, 0.9], [1.0, 0.0, 1.0]) == pytest.approx(0.55)

    def test_a_trailing_zero_weight_source_cannot_pull_the_answer(self):
        """DISCLOSURE: this does NOT exercise the tie branch, and an earlier
        draft of it was named as though it did.

        With weights 1.0 / 0.0 the cumulative passes half strictly at the first
        value, so the `> half` arm returns before any tie is considered. The
        "nothing after this carries weight" case inside the tie branch is
        unreachable when the total is positive — see the proof in
        `_weighted_median` — so there is no test that can reach it, and the
        implementation writes it as a default rather than an arm for exactly
        that reason. What this does pin is that a weightless source is never
        the answer.
        """
        assert _weighted_median([0.2, 0.9], [1.0, 0.0]) == pytest.approx(0.2)


class TestItReachesTheHeroThroughTheRealWeightPath:
    def test_a_pregame_two_venue_event_publishes_the_midpoint(self):
        """End-to-end through `effective_source_weights`, because a unit test on
        `_weighted_median` alone cannot show that the equal weights the branch
        needs actually arrive. Pre-game, so #1999's gate leaves both at 0.8.
        """

        class _Event:
            espn_win_prob_home = None
            opening_home_probability = None
            status = "scheduled"
            win_probability_sources = {
                "kalshi": {"value": 0.805, "updated_at": "2026-09-12T03:20:31+00:00"},
                "polymarket": {
                    "value": 0.890,
                    "updated_at": "2026-09-12T01:08:03+00:00",
                },
            }

        keys, values, weights = effective_source_weights(_Event(), "scheduled")
        assert sorted(keys) == ["kalshi", "polymarket"]
        assert weights[0] == weights[1], "the tie branch needs the decay to be off"
        assert _weighted_median(values, weights) == pytest.approx(0.8475)


def _is_exact_tie(weights):
    """True when some prefix of the value-sorted weights lands exactly on half.

    Used only to exclude the (vanishingly rare) random tie from the
    "non-ties are untouched" property, so that test cannot fail for the one
    reason it is not about.
    """
    total = sum(weights)
    if total <= 0:
        return True
    half = total / 2.0
    for perm_prefix in range(1, len(weights)):
        for subset in _prefixes(weights, perm_prefix):
            if subset == half:
                return True
    return False


def _prefixes(weights, k):
    """Every k-element sum — the sort order is by value, which is independent of
    the weights, so any subset could be the prefix."""
    from itertools import combinations

    return [sum(c) for c in combinations(weights, k)]
