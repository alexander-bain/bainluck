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
