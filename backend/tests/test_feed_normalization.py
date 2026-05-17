"""Tests for _normalize_feed_probabilities (BR57/58 equal-odds fix)."""
from types import SimpleNamespace

from app.routes.feed import _normalize_feed_probabilities


def _make_outcome(prob):
    """Create a mock ORM outcome with current_probability."""
    return SimpleNamespace(current_probability=prob)


class TestNormalizeFeedProbabilities:
    def test_no_normalization_when_sum_under_threshold(self):
        """Outcomes summing to ~100% should pass through unchanged."""
        top = [
            {"name": "A", "probability": 0.50},
            {"name": "B", "probability": 0.30},
            {"name": "C", "probability": 0.15},
        ]
        all_outcomes = [_make_outcome(0.50), _make_outcome(0.30), _make_outcome(0.15), _make_outcome(0.05)]
        result = _normalize_feed_probabilities(top, all_outcomes)
        assert result[0]["probability"] == 0.50
        assert result[1]["probability"] == 0.30
        assert result[2]["probability"] == 0.15

    def test_threshold_cumulative_outcomes_not_normalized(self):
        """Threshold/cumulative outcomes (sum >> 200%) must NOT be normalized.

        This is the BR57/58 bug: a market like "Where will BE HER rank?"
        with outcomes "3+" (81%), "4+" (78%), "5+" (75%) — normalizing these
        flattens an 81% leader to ~33%.
        """
        top = [
            {"name": "3", "probability": 0.81},
            {"name": "4", "probability": 0.78},
            {"name": "5", "probability": 0.75},
        ]
        # 10 threshold outcomes summing to well over 200%
        all_outcomes = [
            _make_outcome(0.99), _make_outcome(0.95), _make_outcome(0.81),
            _make_outcome(0.78), _make_outcome(0.75), _make_outcome(0.60),
            _make_outcome(0.40), _make_outcome(0.20), _make_outcome(0.10),
            _make_outcome(0.05),
        ]
        result = _normalize_feed_probabilities(top, all_outcomes)
        # Probabilities must stay unchanged — no flattening
        assert result[0]["probability"] == 0.81
        assert result[1]["probability"] == 0.78
        assert result[2]["probability"] == 0.75

    def test_independent_binary_markets_normalized(self):
        """Independent binary markets summing to 120% should be normalized.

        Gotcha #58: Kalshi creates separate "Will X win?" markets for each
        candidate. Probabilities can sum over 100%.
        """
        top = [
            {"name": "Lakers", "probability": 0.40},
            {"name": "Celtics", "probability": 0.35},
            {"name": "Knicks", "probability": 0.20},
        ]
        all_outcomes = [
            _make_outcome(0.40), _make_outcome(0.35), _make_outcome(0.20),
            _make_outcome(0.10), _make_outcome(0.05), _make_outcome(0.05),
            _make_outcome(0.03), _make_outcome(0.02),
        ]
        # all_sum = 1.20 — between 1.05 and 2.0
        result = _normalize_feed_probabilities(top, all_outcomes)
        # Each should be divided by 1.20
        assert result[0]["probability"] == round(0.40 / 1.20, 4)
        assert result[1]["probability"] == round(0.35 / 1.20, 4)
        assert result[2]["probability"] == round(0.20 / 1.20, 4)

    def test_binary_market_stricter_threshold(self):
        """Two-outcome markets use a 1.01 threshold, not 1.05."""
        top = [
            {"name": "Yes", "probability": 0.55},
            {"name": "No", "probability": 0.48},
        ]
        all_outcomes = [_make_outcome(0.55), _make_outcome(0.48)]
        # all_sum = 1.03 — above 1.01 for binary, should normalize
        result = _normalize_feed_probabilities(top, all_outcomes)
        assert result[0]["probability"] == round(0.55 / 1.03, 4)
        assert result[1]["probability"] == round(0.48 / 1.03, 4)

    def test_empty_probabilities_pass_through(self):
        """Outcomes with no probability values should pass through."""
        top = [
            {"name": "A", "probability": None},
            {"name": "B", "probability": None},
        ]
        all_outcomes = [_make_outcome(None), _make_outcome(None)]
        result = _normalize_feed_probabilities(top, all_outcomes)
        assert result[0]["probability"] is None
        assert result[1]["probability"] is None

    def test_mixed_none_probabilities(self):
        """Outcomes with a mix of None and real values handle correctly."""
        top = [
            {"name": "A", "probability": 0.60},
            {"name": "B", "probability": None},
            {"name": "C", "probability": 0.50},
        ]
        all_outcomes = [_make_outcome(0.60), _make_outcome(None), _make_outcome(0.50), _make_outcome(0.10)]
        # all_sum = 1.20, between 1.05 and 2.0 -> normalize
        result = _normalize_feed_probabilities(top, all_outcomes)
        assert result[0]["probability"] == round(0.60 / 1.20, 4)
        assert result[1]["probability"] is None  # None stays None
        assert result[2]["probability"] == round(0.50 / 1.20, 4)
