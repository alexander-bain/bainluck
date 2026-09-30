"""#9558: the /economics CPI card labelled every bar one rung low.

Read at 390px on production 2026-09-29 05:34Z, under "Inflation releases":

    CPI in September          0.4% 28.5   0.5% 40    0.6% 15.5   (modal 0.5%)
    CPI core in September     0.0% 12     0.1% 45    0.2% 25.5   (modal 0.1%)

Kalshi's rule (KXCPICORE-26SEP-T0.2, read from the venue): "...increases by
above 0.2%, then the market resolves to Yes." BLS prints to one decimal, so
"above 0.2%, not above 0.3%" is a print of exactly 0.3%. `_cumulative_to_discrete`
named that difference "0.2%" — the LOWER threshold — and never drew the bottom
bucket, 1 - P(above lowest).

The second method that confirms it: Kalshi's combo market on the same card
(KXCPICOMBO-26SEP, legs worded "Exactly 0.4%" / "0.5% or above") put headline
>=0.5% at 85.5%. Summed off the old labels, the headline card said 58%; relabelled
by the upper threshold it says 88% (= P(above 0.4%)).

The legs below are the markets' stored legs, verbatim from /api/futures at
05:4xZ, in stored order (unsorted, which is how the helper receives them).
"""

from types import SimpleNamespace

import pytest

from app.routes.economics import _cumulative_to_discrete, _modal_bracket, _print_grid_step


def _legs(pairs):
    return [SimpleNamespace(name=n, current_probability=p) for n, p in pairs]


# market 364212
KXCPI_26SEP = [
    ("Above 0.0%", 0.995), ("Above -0.1%", 0.995), ("Above -0.2%", 0.995),
    ("Above -0.4%", 0.995), ("Above -0.3%", 0.995), ("Above 0.1%", 0.985),
    ("Above 0.2%", 0.95), ("Above 0.3%", 0.95), ("Above 0.4%", 0.88),
    ("Above 0.5%", 0.595), ("Above 0.6%", 0.195), ("Above 0.7%", 0.04),
]
# market 55686485
KXCPICORE_26SEP = [
    ("Above 0.0%", 0.92), ("Above 0.1%", 0.8), ("Above 0.2%", 0.35),
    ("Above 0.3%", 0.095), ("Above 0.9%", 0.01), ("Above 0.4%", 0.01),
    ("Above 0.5%", 0.01), ("Above 0.6%", 0.01), ("Above 0.7%", 0.01),
    ("Above 0.8%", 0.01), ("Above 1.0%", 0.01),
]
# market 55686484 — 2.7% and 3.2% are not listed, so the ladder has holes.
KXCPICOREYOY_26SEP = [
    ("Above 2.1%", 0.985), ("Above 2.2%", 0.95), ("Above 2.3%", 0.785),
    ("Above 2.4%", 0.465), ("Above 2.5%", 0.14), ("Above 2.6%", 0.03),
    ("Above 3.1%", 0.01), ("Above 3.0%", 0.01), ("Above 3.4%", 0.01),
    ("Above 2.8%", 0.01), ("Above 2.9%", 0.01), ("Above 3.3%", 0.01),
]
# market 61484991 — thresholds 0.10 apart but written (and printed) to two
# decimals, so each difference is ten prints wide: NOT a print grid.
KXBRAZILINF_26SEP = [
    ("Above 3.60%", 0.945), ("Above 4.00%", 0.94), ("Above 3.90%", 0.94),
    ("Above 3.70%", 0.94), ("Above 3.80%", 0.94), ("Above 4.10%", 0.93),
    ("Above 4.20%", 0.87), ("Above 4.30%", 0.8), ("Above 4.40%", 0.56),
    ("Above 4.50%", 0.26), ("Above 4.60%", 0.155),
]


class TestTheCpiCardNamesThePrint:
    def test_headline_modal_is_the_06_print(self):
        brackets = _cumulative_to_discrete(_legs(KXCPI_26SEP), max_buckets=6)
        assert brackets == [
            [3.5, "0.2%"], [7.0, "0.4%"], [28.5, "0.5%"],
            [40.0, "0.6%"], [15.5, "0.7%"], [4.0, "0.8%+"],
        ]
        _, prob, label = _modal_bracket(brackets)
        assert (label, prob) == ("0.6%", 40.0)

    def test_headline_agrees_with_the_combo_market(self):
        """The independent method: Kalshi's combo prices headline >=0.5% at 85.5%."""
        brackets = _cumulative_to_discrete(_legs(KXCPI_26SEP), max_buckets=10)
        at_or_above_05 = sum(
            p for p, label in brackets if label in ("0.5%", "0.6%", "0.7%", "0.8%+")
        )
        assert at_or_above_05 == 88.0  # the combo: 85.5; the old labels: 58.0

    def test_core_draws_the_bottom_bucket_and_names_02(self):
        brackets = _cumulative_to_discrete(_legs(KXCPICORE_26SEP), max_buckets=6)
        by_label = {label: p for p, label in brackets}
        assert by_label["≤0.0%"] == 8.0
        assert by_label["0.1%"] == 12.0
        assert by_label["0.2%"] == 45.0
        assert by_label["0.3%"] == 25.5
        assert _modal_bracket(brackets)[2] == "0.2%"

    def test_a_missing_rung_reads_as_a_run(self):
        brackets = _cumulative_to_discrete(_legs(KXCPICOREYOY_26SEP), max_buckets=6)
        by_label = {label: p for p, label in brackets}
        # P(above 2.6) - P(above 2.8): a print of 2.7% or 2.8%.
        assert by_label["2.7–2.8%"] == 2.0
        assert by_label["2.5%"] == 32.5

    def test_the_grid_conserves_probability(self):
        """With the bottom bucket drawn, a full grid ladder sums to 100."""
        brackets = _cumulative_to_discrete(_legs(KXCPICORE_26SEP), max_buckets=20)
        assert round(sum(p for p, _ in brackets), 1) == 100.0

    def test_no_negative_zero(self):
        brackets = _cumulative_to_discrete(
            _legs([("Above -0.2%", 0.99), ("Above -0.1%", 0.9), ("Above 0.0%", 0.5)]),
        )
        labels = [label for _, label in brackets]
        assert "0.0%" in labels
        assert not any("-0.0" in label for label in labels), labels


class TestOffTheGridLaddersKeepTheirLabels:
    @pytest.mark.parametrize(
        "pairs",
        [
            KXBRAZILINF_26SEP,
            # Fed: 0.25 apart on two decimals — "4.00%" names a target range by its floor.
            [("Above 3.75%", 0.97), ("Above 4.00%", 0.69), ("Above 4.25%", 0.2), ("Above 4.50%", 0.05)],
            # GDP: 0.5 apart on one decimal.
            [("Above 1.0%", 0.9), ("Above 1.5%", 0.7), ("Above 2.0%", 0.4), ("Above 2.5%", 0.1)],
            # whole-number rungs.
            [("Above -5%", 0.95), ("Above -4%", 0.6), ("Above -3%", 0.2)],
            # dollars.
            [("Above $3.10", 0.9), ("Above $3.20", 0.5), ("Above $3.30", 0.2)],
        ],
    )
    def test_labels_are_the_lower_threshold_as_before(self, pairs):
        brackets = _cumulative_to_discrete(_legs(pairs), max_buckets=20)
        thresholds = {n.replace("Above ", "") for n, _ in pairs}
        for _, label in brackets:
            assert label in thresholds, label

    def test_grid_detection(self):
        assert _print_grid_step(["0.1%", "0.2%", "0.3%"], [0.1, 0.2, 0.3]) == (1, 0.1)
        assert _print_grid_step(["0.1%", "0.3%"], [0.1, 0.3]) is None
        assert _print_grid_step(["4.10%", "4.20%"], [4.1, 4.2]) is None
        assert _print_grid_step(["3%", "4%"], [3.0, 4.0]) is None
        assert _print_grid_step(["$3.1", "$3.2"], [3.1, 3.2]) is None
        # a tie (two legs, one threshold) is not a grid.
        assert _print_grid_step(["0.1%", "0.1%", "0.2%"], [0.1, 0.1, 0.2]) is None
