"""Tests for Economics page probability normalization (M8 fix).

Distribution markets (CPI, Fed rates, GDP, energy) assemble bracket
probabilities from independent binary markets.  These can sum well over 100%.
Both _brackets_from_outcomes and _cumulative_to_discrete must normalize when
the total exceeds 105%.
"""

from types import SimpleNamespace

from app.routes.economics import (
    _brackets_from_outcomes,
    _cumulative_to_discrete,
    _modal_bracket,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_outcome(name: str, prob: float, rank: int = 0):
    return SimpleNamespace(
        id=1, name=name, current_probability=prob, rank=rank,
    )


def _make_market(name: str, outcomes: list, source: str = "kalshi", external_id: str = "kxcpi"):
    return SimpleNamespace(
        id=1, name=name, source=source, external_id=external_id, outcomes=outcomes,
    )


# ---------------------------------------------------------------------------
# _brackets_from_outcomes — multi-outcome market normalization
# ---------------------------------------------------------------------------


class TestBracketsFromOutcomes:
    """_brackets_from_outcomes should normalize when probabilities sum > 105%."""

    def test_normal_distribution_unchanged(self):
        outcomes = [
            _make_outcome("2.5% - 3.0%", 0.35, rank=1),
            _make_outcome("3.0% - 3.5%", 0.30, rank=2),
            _make_outcome("2.0% - 2.5%", 0.20, rank=3),
            _make_outcome("3.5% - 4.0%", 0.15, rank=4),
        ]
        market = _make_market("CPI Year-over-Year", outcomes)
        brackets = _brackets_from_outcomes(market)
        total = sum(b[0] for b in brackets)
        assert 99.0 <= total <= 101.0, f"Sum should be ~100%, got {total}%"
        assert brackets[0][0] == 35.0

    def test_inflated_distribution_normalized(self):
        """Independent binary markets whose probs sum >> 100% get normalized."""
        outcomes = [
            _make_outcome("2.5% - 3.0%", 0.55, rank=1),
            _make_outcome("3.0% - 3.5%", 0.45, rank=2),
            _make_outcome("2.0% - 2.5%", 0.35, rank=3),
            _make_outcome("3.5% - 4.0%", 0.25, rank=4),
        ]
        market = _make_market("CPI Year-over-Year", outcomes)
        brackets = _brackets_from_outcomes(market)
        total = sum(b[0] for b in brackets)
        # Raw sum is 160%; should be normalized down to ~100%
        assert total <= 101.0, f"Sum should be <=101%, got {total}%"
        assert brackets[0][0] < 55.0

    def test_exactly_105_not_normalized(self):
        """Threshold is strictly > 105; sum of exactly 105 is left alone."""
        outcomes = [
            _make_outcome("Low", 0.55, rank=1),
            _make_outcome("High", 0.50, rank=2),
        ]
        market = _make_market("Rate Level", outcomes)
        brackets = _brackets_from_outcomes(market)
        assert brackets[0][0] == 55.0
        assert brackets[1][0] == 50.0

    def test_normalize_false_skips(self):
        outcomes = [
            _make_outcome("A", 0.80, rank=1),
            _make_outcome("B", 0.60, rank=2),
        ]
        market = _make_market("Test", outcomes)
        brackets = _brackets_from_outcomes(market, normalize=False)
        assert brackets[0][0] == 80.0
        assert brackets[1][0] == 60.0

    def test_preserves_labels(self):
        outcomes = [
            _make_outcome("2.0% - 2.5%", 0.60, rank=1),
            _make_outcome("2.5% - 3.0%", 0.50, rank=2),
            _make_outcome("3.0% - 3.5%", 0.30, rank=3),
        ]
        market = _make_market("CPI", outcomes)
        brackets = _brackets_from_outcomes(market)
        labels = [b[1] for b in brackets]
        assert labels == ["2.0% - 2.5%", "2.5% - 3.0%", "3.0% - 3.5%"]

    def test_empty_outcomes(self):
        market = _make_market("Empty", [])
        assert _brackets_from_outcomes(market) == []

    def test_severe_overround(self):
        """6 brackets each at ~40% (sum 240%) should normalize correctly."""
        outcomes = [_make_outcome(f"Bracket {i}", 0.40, rank=i) for i in range(6)]
        market = _make_market("Inflated", outcomes)
        brackets = _brackets_from_outcomes(market)
        total = sum(b[0] for b in brackets)
        assert 99.0 <= total <= 101.0, f"Sum should be ~100%, got {total}%"


# ---------------------------------------------------------------------------
# _cumulative_to_discrete — cumulative "Above X" normalization
# ---------------------------------------------------------------------------


class TestCumulativeToDiscrete:
    """_cumulative_to_discrete should normalize when discrete probs sum > 105%."""

    def test_well_behaved_cumulative(self):
        outcomes = [
            _make_outcome("Above 2.0%", 0.95),
            _make_outcome("Above 2.5%", 0.80),
            _make_outcome("Above 3.0%", 0.50),
            _make_outcome("Above 3.5%", 0.20),
            _make_outcome("Above 4.0%", 0.05),
        ]
        brackets = _cumulative_to_discrete(outcomes)
        total = sum(b[0] for b in brackets)
        assert total <= 105.0, f"Sum should be <=105%, got {total}%"
        assert len(brackets) > 0

    def test_above_labels_stripped(self):
        outcomes = [
            _make_outcome("Above 2.0%", 0.80),
            _make_outcome("Above 3.0%", 0.50),
            _make_outcome("Above 4.0%", 0.20),
        ]
        brackets = _cumulative_to_discrete(outcomes)
        labels = [b[1] for b in brackets]
        assert all("Above" not in lbl for lbl in labels)

    def test_empty_outcomes(self):
        assert _cumulative_to_discrete([]) == []

    def test_max_buckets_respected(self):
        outcomes = [_make_outcome(f"Above {i}", 0.95 - i * 0.08) for i in range(10)]
        brackets = _cumulative_to_discrete(outcomes, max_buckets=4)
        assert len(brackets) <= 4

    def test_normalization_guard_fires(self):
        """Verify the normalization guard catches sums > 105%.

        For well-formed monotonic cumulative data, discrete sums can't exceed
        the first cumulative value (so max ~100%).  The guard is defensive,
        protecting against edge cases and upstream data quality issues.
        It should not make things worse for normal data.
        """
        outcomes = [
            _make_outcome("Above 100", 0.90),
            _make_outcome("Above 200", 0.70),
            _make_outcome("Above 300", 0.40),
            _make_outcome("Above 400", 0.10),
        ]
        brackets = _cumulative_to_discrete(outcomes)
        total = sum(b[0] for b in brackets)
        # 20 + 30 + 30 + 10 = 90 — well under threshold
        assert total <= 105.0


class TestCumulativeSignedThresholds:
    """#7081 — the threshold sort key must read the minus sign.

    An unsigned `[\\d.]+` key reads "Above -0.4%" as 0.4. Nothing about the
    output *shape* gives that away: the ladder still comes back as brackets
    that sum sensibly, so these assert the label a probability is PAIRED WITH,
    never merely the ordering.
    """

    # The September CPI print, verbatim from market_id 364212 — the specimen
    # that was live on /economics.
    _CPI_SEPTEMBER = [
        ("Above -0.4%", 0.950), ("Above -0.3%", 0.945), ("Above -0.2%", 0.925),
        ("Above -0.1%", 0.925), ("Above 0.0%", 0.915), ("Above 0.1%", 0.905),
        ("Above 0.2%", 0.900), ("Above 0.3%", 0.675), ("Above 0.4%", 0.480),
        ("Above 0.5%", 0.440), ("Above 0.6%", 0.360),
    ]

    def test_mixed_sign_ladder_pairs_mass_with_the_right_label(self):
        """The two biggest non-modal brackets belong to +0.2% and +0.3%.

        Before the fix they were served as -0.3% and -0.4% — 42 points of
        probability shown against deflation.
        """
        outcomes = [_make_outcome(n, p) for n, p in self._CPI_SEPTEMBER]
        brackets = _cumulative_to_discrete(outcomes, max_buckets=6)
        by_label = {lbl: prob for prob, lbl in brackets}

        assert by_label.get("0.2%") == 22.5
        assert by_label.get("0.3%") == 19.5
        # The mass must not appear on the deflation legs at all.
        assert by_label.get("-0.3%") != 22.5
        assert by_label.get("-0.4%") != 19.5
        # The modal bar was always right; it must stay right.
        assert by_label.get("0.6%") == 36.0

    def test_mixed_sign_ladder_is_ascending_by_threshold(self):
        outcomes = [_make_outcome(n, p) for n, p in self._CPI_SEPTEMBER]
        labels = [lbl for _, lbl in _cumulative_to_discrete(outcomes, max_buckets=6)]
        vals = [float(lbl.rstrip("%")) for lbl in labels]
        assert vals == sorted(vals), f"ladder not ascending: {labels}"

    def test_all_negative_ladder_does_not_collapse_to_one_bar(self):
        """Germany's 2026 budget balance — 7 legs, every threshold negative.

        The unsigned key reversed the ladder, which made the cumulatives
        ascending, which made the monotonicity clamp flatten every leg to the
        first one's value; every difference then rounded to zero and was
        dropped. The card became a single bar.
        """
        legs = [
            ("Above -5.0% of GDP", 0.955), ("Above -4.5% of GDP", 0.895),
            ("Above -4.0% of GDP", 0.580), ("Above -3.5% of GDP", 0.155),
            ("Above -3.0% of GDP", 0.070), ("Above -2.5% of GDP", 0.040),
            ("Above -2.0% of GDP", 0.035),
        ]
        brackets = _cumulative_to_discrete(
            [_make_outcome(n, p) for n, p in legs], max_buckets=6
        )
        assert len(brackets) > 1, f"collapsed to {brackets}"
        by_label = {lbl: prob for prob, lbl in brackets}
        # The distribution is centred on -4.0%, not on the outermost leg.
        assert by_label.get("-4.0% of GDP") == 42.5
        assert by_label.get("-4.5% of GDP") == 31.5
        modal_idx, _, modal_label = _modal_bracket(brackets)
        assert modal_label == "-4.0% of GDP"

    def test_all_negative_ladder_survives_the_max_buckets_resort(self):
        """The post-truncation re-sort must key on threshold, not on label.

        8 legs into max_buckets=6 forces the `len(discrete) > max_buckets`
        path. Sorting the survivors by label string yields "-3%" before "-4%".
        """
        legs = [
            ("Above -10%", 0.920), ("Above -9%", 0.905), ("Above -8%", 0.860),
            ("Above -7%", 0.730), ("Above -6%", 0.570), ("Above -5%", 0.410),
            ("Above -4%", 0.220), ("Above -3%", 0.095),
        ]
        brackets = _cumulative_to_discrete(
            [_make_outcome(n, p) for n, p in legs], max_buckets=6
        )
        assert len(brackets) == 6
        vals = [float(lbl.rstrip("%")) for _, lbl in brackets]
        assert vals == sorted(vals), f"ladder not ascending: {vals}"

    def test_hyphen_inside_a_word_is_not_read_as_a_sign(self):
        """`(?<!\\w)` guard: only a leading hyphen is a minus."""
        legs = [("Above COVID-19 cases 5%", 0.80), ("Above COVID-19 cases 7%", 0.30)]
        brackets = _cumulative_to_discrete([_make_outcome(n, p) for n, p in legs])
        # Parsed as 19 for both (unchanged by the fix); the point is that
        # neither becomes -19, which would silently reorder the pair.
        assert len(brackets) == 2

    def test_malformed_numeric_token_does_not_raise(self):
        """`float('1.2.3')` would 500 the whole /economics route."""
        legs = [("Above 1.2.3", 0.80), ("Above 2.0", 0.30)]
        brackets = _cumulative_to_discrete([_make_outcome(n, p) for n, p in legs])
        assert brackets  # returned rather than raised

    def test_returned_rows_are_pairs(self):
        """The threshold is carried internally but must not reach the payload."""
        outcomes = [_make_outcome(n, p) for n, p in self._CPI_SEPTEMBER]
        for row in _cumulative_to_discrete(outcomes, max_buckets=6):
            assert len(row) == 2, f"row leaked its sort key: {row}"


# ---------------------------------------------------------------------------
# _modal_bracket
# ---------------------------------------------------------------------------


class TestModalBracket:
    def test_finds_highest(self):
        brackets = [[25.0, "Low"], [45.0, "Mid"], [30.0, "High"]]
        idx, prob, label = _modal_bracket(brackets)
        assert idx == 1
        assert prob == 45.0
        assert label == "Mid"

    def test_empty(self):
        idx, prob, label = _modal_bracket([])
        assert idx == 0
        assert prob == 0.0
        assert label == ""
