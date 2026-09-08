"""lane1/193 (#4035): the least informative input available scored the maximum confidence.

`GET /api/events/{id}/history` serves `pm_spread_data.implied_totals`, and
`select_projection_source` feeds the projected final from whichever arm states the
highest `confidence`. On production 2026-09-08 event 15307194 (Minnesota Twins @
Detroit Tigers) served a Polymarket implied **total of 10.5 at `confidence: 1.0`**
— the maximum the formula can emit — beside a clean Kalshi ladder reading 8.2 at
0.9. The 1.0 arm won, and it earned its score by being maximally uninformative.

Three Polymarket ladders are linked to that one event, so the pool holds duplicate
thresholds. At 10.5 it held three rungs:

    thr=10.5  p=1.0000
    thr=10.5  p=1.0000
    thr=10.5  p=0.4900     <- a different ladder, same line

The walk takes the first adjacent pair straddling 50%. `(10.5, 1.00) -> (10.5, 0.49)`
straddles, so:

    bracket_width = 10.5 - 10.5 = 0.0
    confidence    = 1.0 - (0.0 / 10.0) = 1.0

**A bracket of zero width is not a tight bracket.** One ladder's own rungs can
never share a threshold, so zero width means two ladders were pooled onto one
event and they disagree about that line. The formula reads "how tightly do the
bracketing rungs sit around 50%", and a contradiction is its best possible score.

## The second defect, found while building the fix and not in the filing

Sorting on threshold alone leaves rungs that share one threshold in whatever order
the rows arrived in, and **no query guarantees that order**. The same three
production rows answered two different ways:

    rows ordered 1.00 first -> total=10.5  confidence=1.0   (width 0, contradiction)
    rows ordered 0.49 first -> total=11.1  confidence=0.9   (0.49 rung silently dropped)

That is why the filing measured 1.0 and a re-read an hour later measured 0.9 on the
same event. `_threshold_order` pins it: threshold ascending, price descending
within a threshold — which also keeps the walk's "price falls as the threshold
rises" assumption true across the tie.

## The boundary that makes this a scope rule and not a suppression

Zero width is only a contradiction when the two prices **disagree**. Two ladders
that both price one line at 50% AGREE the line is a coin flip — the best evidence
available — and must keep the maximum score. `TestAgreementAtOneLineStaysHigh` is
the control: a blanket "zero width scores low" passes every other test here and
fails only that one.
"""

import pytest

from app.utils.binary_spread import (
    _CONTRADICTION_CONFIDENCE,
    binary_to_implied_spread,
    binary_to_implied_total,
    select_projection_source,
)


# The production pool from the filing, read off event 15307194's Polymarket arms.
CONTRADICTION_POOL = [
    {"threshold": 10.5, "probability": 1.00},
    {"threshold": 10.5, "probability": 0.49},
    {"threshold": 11.5, "probability": 0.20},
]

# Kalshi's clean ladder on the same event: rungs a point apart bracketing 8.1.
CLEAN_TOTAL_LADDER = [
    {"threshold": 7.5, "probability": 0.545},
    {"threshold": 8.5, "probability": 0.465},
]


class TestContradictionIsNotConfidence:
    """The filed bug: a same-line disagreement scored 1.0."""

    def test_duplicate_threshold_does_not_score_maximum(self):
        implied = binary_to_implied_total(CONTRADICTION_POOL)

        assert implied is not None, "the arm must survive — this is a score fix, not a suppression"
        assert implied.confidence == _CONTRADICTION_CONFIDENCE
        assert implied.confidence < 1.0

    def test_contradiction_never_outscores_a_genuinely_narrow_bracket(self):
        """The acceptance criterion, stated as the comparison it is about."""
        contradiction = binary_to_implied_total(CONTRADICTION_POOL)
        genuine = binary_to_implied_total(CLEAN_TOTAL_LADDER)

        assert contradiction.confidence < genuine.confidence

    def test_the_clean_kalshi_arm_now_wins_the_selection(self):
        """The ship: the projected final stops being fed by the contradiction."""
        contradiction = binary_to_implied_total(CONTRADICTION_POOL)
        clean = binary_to_implied_total(CLEAN_TOTAL_LADDER)

        implied = {
            "polymarket": {"total": contradiction.total, "confidence": contradiction.confidence},
            "kalshi": {"total": clean.total, "confidence": clean.confidence},
        }

        assert select_projection_source(implied) == "kalshi"

    def test_the_spread_arm_shares_the_shape_and_the_fix(self):
        """`binary_to_implied_spread` has the same exposure whenever spreads pool."""
        implied = binary_to_implied_spread(
            [
                {"threshold": 1.5, "probability": 0.90},
                {"threshold": 1.5, "probability": 0.30},
            ]
        )

        assert implied is not None
        assert implied.confidence == _CONTRADICTION_CONFIDENCE


class TestRowOrderCannotChangeTheAnswer:
    """The second defect: one pool, two answers, decided by row order."""

    @pytest.mark.parametrize(
        "order",
        [
            pytest.param([0, 1, 2], id="1.00-first"),
            pytest.param([1, 0, 2], id="0.49-first"),
            pytest.param([2, 1, 0], id="reversed"),
            pytest.param([2, 0, 1], id="high-threshold-first"),
        ],
    )
    def test_every_row_order_gives_one_answer(self, order):
        implied = binary_to_implied_total([CONTRADICTION_POOL[i] for i in order])

        assert implied.total == 10.5
        assert implied.confidence == _CONTRADICTION_CONFIDENCE


class TestAgreementAtOneLineStaysHigh:
    """🔴 The control. A blanket "zero width scores low" fails only here.

    Two ladders pricing one line at the same probability are not contradicting
    each other — they agree, and that is the strongest evidence the pool can
    carry. Scoring it as a contradiction would throw away the good case with the
    bad one.
    """

    def test_two_ladders_agreeing_a_line_is_a_coin_flip_keeps_the_maximum(self):
        implied = binary_to_implied_total(
            [
                {"threshold": 8.5, "probability": 0.50},
                {"threshold": 8.5, "probability": 0.50},
                {"threshold": 9.5, "probability": 0.20},
            ]
        )

        assert implied.total == 8.5
        assert implied.confidence == 1.0


class TestUncontaminatedLaddersAreUntouched:
    """Narrowness control: pools with no duplicate threshold must not move."""

    def test_the_clean_total_ladder_is_unchanged(self):
        implied = binary_to_implied_total(CLEAN_TOTAL_LADDER)

        assert implied.total == 8.1
        assert implied.confidence == 0.9

    def test_a_clean_spread_ladder_is_unchanged(self):
        implied = binary_to_implied_spread(
            [
                {"threshold": 1.0, "probability": 0.87},
                {"threshold": 10.5, "probability": 0.48},
            ]
        )

        assert implied.confidence == round(1.0 - (9.5 / 20.0), 2)
