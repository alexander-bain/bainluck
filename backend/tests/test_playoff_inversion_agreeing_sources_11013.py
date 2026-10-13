"""#11013 — two sources that AGREE near 50% are not one inverted source.

The WNBA Finals grid served Golden State's Polymarket price as 0.4715 (the No
side of the venue's 0.5285) because 0.5305 + 0.515 sums to within 0.05 of 1.0.
The headline read 49% instead of ~52%. A pair that sums to ~1.0 is evidence of
an inversion only when the two sources also disagree.
"""

import pytest

from app.routes.playoffs import (
    _INVERSION_MIN_GAP,
    _correct_inverted_probs,
    _merge_probabilities,
)


class TestAgreeingPairIsNotInverted:
    def test_golden_state_specimen_keeps_both_yes_prices(self):
        # Production 10/13: Polymarket GSV 0.5305, Kalshi 0.515.
        assert _correct_inverted_probs([0.5305, 0.515]) == [0.5305, 0.515]
        assert _correct_inverted_probs([0.515, 0.5305]) == [0.515, 0.5305]

    def test_golden_state_headline_stays_above_half(self):
        merged = _merge_probabilities([0.5285, 0.515])
        assert merged == pytest.approx(0.52175)
        assert merged > 0.5

    def test_identical_pair_just_below_half_is_not_flipped(self):
        # Atlanta's 0.475 + 0.475 sat just outside the band; 0.476 + 0.476
        # would have been flipped to a 52% favourite.
        assert _correct_inverted_probs([0.476, 0.476]) == [0.476, 0.476]

    def test_pair_exactly_at_the_gap_is_left_alone(self):
        a, b = 0.55, 0.55 - _INVERSION_MIN_GAP
        assert _correct_inverted_probs([a, b]) == [a, b]


class TestDisagreeingPairIsStillInverted:
    def test_no_side_price_is_inverted(self):
        # True ~0.30; one venue shows the No side 0.71.
        assert _correct_inverted_probs([0.71, 0.30]) == pytest.approx([0.29, 0.30])
        assert _correct_inverted_probs([0.30, 0.71]) == pytest.approx([0.30, 0.29])

    def test_merged_reads_the_corrected_pair(self):
        assert _merge_probabilities([0.71, 0.30]) == pytest.approx(0.295)

    def test_disagreeing_pair_not_summing_to_one_is_untouched(self):
        assert _correct_inverted_probs([0.40, 0.20]) == [0.40, 0.20]


def test_three_source_rule_unchanged():
    assert _correct_inverted_probs([0.30, 0.32, 0.70]) == pytest.approx(
        [0.30, 0.32, 0.30]
    )
    assert _correct_inverted_probs([0.52, 0.50, 0.49]) == [0.52, 0.50, 0.49]
