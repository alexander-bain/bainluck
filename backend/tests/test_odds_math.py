"""Tests for odds_math utilities."""

import pytest
from app.utils.odds_math import (
    aggregate_probabilities,
    aggregate_bookmaker_odds,
    detect_reversed_bookmakers,
    moneyline_to_probability,
    american_to_probability,
    remove_vig,
)


class TestAggregateProbabilities:
    """Tests for aggregate_probabilities function."""

    def test_single_probability(self):
        """Single probability returns as-is."""
        result = aggregate_probabilities([0.55])
        assert result == 0.55

    def test_mean_aggregation(self):
        """Mean aggregation calculates correctly."""
        result = aggregate_probabilities([0.50, 0.52, 0.54], method="mean")
        assert abs(result - 0.52) < 0.0001

    def test_median_aggregation(self):
        """Median aggregation returns middle value."""
        result = aggregate_probabilities([0.50, 0.55, 0.60], method="median")
        assert result == 0.55

    def test_median_even_count(self):
        """Median with even count returns average of middle two."""
        result = aggregate_probabilities([0.50, 0.52, 0.54, 0.56], method="median")
        assert abs(result - 0.53) < 0.0001

    def test_trimmed_mean(self):
        """Trimmed mean removes outliers."""
        # Should remove 0.40 and 0.70, average remaining 0.50, 0.52, 0.54
        result = aggregate_probabilities([0.40, 0.50, 0.52, 0.54, 0.70], method="trimmed_mean")
        assert abs(result - 0.52) < 0.0001

    def test_trimmed_mean_small_list(self):
        """Trimmed mean with < 3 items falls back to mean."""
        result = aggregate_probabilities([0.50, 0.60], method="trimmed_mean")
        assert abs(result - 0.55) < 0.0001

    def test_empty_list(self):
        """Empty list returns None."""
        result = aggregate_probabilities([])
        assert result is None

    def test_none_values_filtered(self):
        """None values are filtered out."""
        result = aggregate_probabilities([0.50, None, 0.54, None])
        assert abs(result - 0.52) < 0.0001

    def test_invalid_values_filtered(self):
        """Values outside 0-1 range are filtered."""
        result = aggregate_probabilities([0.50, 1.5, 0.54, -0.1])
        assert abs(result - 0.52) < 0.0001

    def test_all_invalid_returns_none(self):
        """All invalid values returns None."""
        result = aggregate_probabilities([None, 1.5, -0.1])
        assert result is None


class TestAggregateBookmakerOdds:
    """Tests for aggregate_bookmaker_odds function."""

    def test_empty_list(self):
        """Empty list returns None values."""
        result = aggregate_bookmaker_odds([])
        assert result["home_probability"] is None
        assert result["away_probability"] is None
        assert result["bookmaker_count"] == 0

    def test_single_bookmaker(self):
        """Single bookmaker data passes through."""
        snapshots = [{
            "home_win_probability": 0.55,
            "away_win_probability": 0.45,
            "over_under": 220.5,
            "home_spread": -3.5,
            "projected_home_score": 112.0,
            "projected_away_score": 108.5,
        }]
        result = aggregate_bookmaker_odds(snapshots)

        assert result["home_probability"] == 0.55
        assert result["away_probability"] == 0.45
        assert result["over_under"] == 220.5
        assert result["home_spread"] == -3.5
        assert result["bookmaker_count"] == 1
        assert result["min_home_probability"] == 0.55
        assert result["max_home_probability"] == 0.55

    def test_multiple_bookmakers(self):
        """Multiple bookmakers are averaged correctly."""
        snapshots = [
            {
                "home_win_probability": 0.54,
                "away_win_probability": 0.46,
                "over_under": 220.0,
                "home_spread": -3.5,
            },
            {
                "home_win_probability": 0.56,
                "away_win_probability": 0.44,
                "over_under": 221.0,
                "home_spread": -4.0,
            },
            {
                "home_win_probability": 0.55,
                "away_win_probability": 0.45,
                "over_under": 220.5,
                "home_spread": -3.5,
            },
        ]
        result = aggregate_bookmaker_odds(snapshots)

        assert result["bookmaker_count"] == 3
        assert abs(result["home_probability"] - 0.55) < 0.0001
        assert abs(result["away_probability"] - 0.45) < 0.0001
        assert abs(result["over_under"] - 220.5) < 0.1
        assert result["min_home_probability"] == 0.54
        assert result["max_home_probability"] == 0.56

    def test_handles_none_values(self):
        """Gracefully handles None values in some snapshots."""
        snapshots = [
            {
                "home_win_probability": 0.55,
                "away_win_probability": 0.45,
                "over_under": 220.0,
            },
            {
                "home_win_probability": None,
                "away_win_probability": None,
                "over_under": 221.0,
            },
            {
                "home_win_probability": 0.57,
                "away_win_probability": 0.43,
                "over_under": None,
            },
        ]
        result = aggregate_bookmaker_odds(snapshots)

        assert result["bookmaker_count"] == 2  # Only 2 valid home_probs
        assert abs(result["home_probability"] - 0.56) < 0.0001
        assert abs(result["over_under"] - 220.5) < 0.1  # Only 2 valid over/unders

    def test_works_with_objects(self):
        """Works with object attributes as well as dict keys."""
        class MockSnapshot:
            def __init__(self, home_prob, away_prob):
                self.home_win_probability = home_prob
                self.away_win_probability = away_prob
                self.over_under = None
                self.home_spread = None
                self.projected_home_score = None
                self.projected_away_score = None

        snapshots = [
            MockSnapshot(0.55, 0.45),
            MockSnapshot(0.57, 0.43),
        ]
        result = aggregate_bookmaker_odds(snapshots)

        assert result["bookmaker_count"] == 2
        assert abs(result["home_probability"] - 0.56) < 0.0001


class TestMoneylineToProbability:
    """Tests for moneyline_to_probability function."""

    def test_favorite_vs_underdog(self):
        """Favorite and underdog odds convert correctly."""
        home_prob, away_prob = moneyline_to_probability(-150, 130)
        # -150 implies ~60%, +130 implies ~43.5%, normalized to 100%
        assert 0.57 < home_prob < 0.62
        assert 0.38 < away_prob < 0.43
        assert abs(home_prob + away_prob - 1.0) < 0.0001

    def test_even_odds(self):
        """Even odds give ~50/50 probability."""
        home_prob, away_prob = moneyline_to_probability(-110, -110)
        assert abs(home_prob - 0.5) < 0.01
        assert abs(away_prob - 0.5) < 0.01

    def test_heavy_favorite(self):
        """Heavy favorite odds convert correctly."""
        home_prob, away_prob = moneyline_to_probability(-300, 250)
        assert home_prob > 0.7
        assert away_prob < 0.3

    def test_without_vig_removal(self):
        """Raw probabilities include vig (sum > 1)."""
        home_prob, away_prob = moneyline_to_probability(-150, 130, remove_juice=False)
        assert home_prob + away_prob > 1.0


class TestAmericanToProbability:
    """Tests for american_to_probability function."""

    def test_negative_odds(self):
        """Negative odds (favorite) convert correctly."""
        prob = american_to_probability(-150)
        assert abs(prob - 0.6) < 0.001

    def test_positive_odds(self):
        """Positive odds (underdog) convert correctly."""
        prob = american_to_probability(150)
        assert abs(prob - 0.4) < 0.001

    def test_even_odds(self):
        """Even money (-100/+100) gives 50%."""
        prob_neg = american_to_probability(-100)
        prob_pos = american_to_probability(100)
        assert abs(prob_neg - 0.5) < 0.001
        assert abs(prob_pos - 0.5) < 0.001


class TestRemoveVig:
    """Tests for remove_vig function."""

    def test_normalizes_to_100_percent(self):
        """Probabilities normalize to exactly 100%."""
        # 5% vig scenario
        home_prob, away_prob = remove_vig(0.55, 0.50)
        assert abs(home_prob + away_prob - 1.0) < 0.0001

    def test_preserves_ratio(self):
        """Relative ratio is preserved after normalization."""
        home_prob, away_prob = remove_vig(0.60, 0.50)
        # Original ratio: 0.60 / 0.50 = 1.2
        # Normalized ratio should be the same
        assert abs(home_prob / away_prob - 1.2) < 0.001


class TestDetectReversedBookmakers:
    """Tests for detect_reversed_bookmakers function."""

    def test_detects_reversed_bookmakers(self):
        """Detects bookmakers with clearly reversed home/away probabilities."""
        # 4 reversed books (~73% home) among 12 correct books (~33% home)
        snapshots = [
            {"bookmaker": "betus", "home_win_probability": 0.743},
            {"bookmaker": "lowvig", "home_win_probability": 0.737},
            {"bookmaker": "betonlineag", "home_win_probability": 0.735},
            {"bookmaker": "betanysports", "home_win_probability": 0.734},
            {"bookmaker": "fanduel", "home_win_probability": 0.330},
            {"bookmaker": "draftkings", "home_win_probability": 0.326},
            {"bookmaker": "betmgm", "home_win_probability": 0.326},
            {"bookmaker": "espnbet", "home_win_probability": 0.336},
            {"bookmaker": "fanatics", "home_win_probability": 0.353},
            {"bookmaker": "fliff", "home_win_probability": 0.331},
            {"bookmaker": "williamhill_us", "home_win_probability": 0.322},
            {"bookmaker": "hardrockbet", "home_win_probability": 0.301},
            {"bookmaker": "betrivers", "home_win_probability": 0.298},
            {"bookmaker": "ballybet", "home_win_probability": 0.296},
            {"bookmaker": "betparx", "home_win_probability": 0.292},
            {"bookmaker": "mybookieag", "home_win_probability": 0.375},
        ]
        reversed_bks = detect_reversed_bookmakers(snapshots)
        assert reversed_bks == {"betus", "lowvig", "betonlineag", "betanysports"}

    def test_no_reversal_when_consistent(self):
        """No bookmakers flagged when all probabilities are consistent."""
        snapshots = [
            {"bookmaker": "fanduel", "home_win_probability": 0.55},
            {"bookmaker": "draftkings", "home_win_probability": 0.53},
            {"bookmaker": "betmgm", "home_win_probability": 0.54},
            {"bookmaker": "espnbet", "home_win_probability": 0.56},
        ]
        reversed_bks = detect_reversed_bookmakers(snapshots)
        assert reversed_bks == set()

    def test_no_detection_near_fifty_fifty(self):
        """Skip detection when median is close to 50% (can't reliably detect)."""
        snapshots = [
            {"bookmaker": "a", "home_win_probability": 0.52},
            {"bookmaker": "b", "home_win_probability": 0.48},
            {"bookmaker": "c", "home_win_probability": 0.50},
            {"bookmaker": "d", "home_win_probability": 0.51},
        ]
        reversed_bks = detect_reversed_bookmakers(snapshots)
        assert reversed_bks == set()

    def test_too_few_bookmakers(self):
        """Need at least 3 bookmakers for detection."""
        snapshots = [
            {"bookmaker": "a", "home_win_probability": 0.30},
            {"bookmaker": "b", "home_win_probability": 0.70},
        ]
        reversed_bks = detect_reversed_bookmakers(snapshots)
        assert reversed_bks == set()

    def test_empty_list(self):
        """Empty list returns empty set."""
        assert detect_reversed_bookmakers([]) == set()

    def test_none_probabilities_ignored(self):
        """Snapshots with None probabilities are skipped."""
        snapshots = [
            {"bookmaker": "a", "home_win_probability": 0.33},
            {"bookmaker": "b", "home_win_probability": None},
            {"bookmaker": "c", "home_win_probability": 0.35},
            {"bookmaker": "d", "home_win_probability": 0.32},
        ]
        reversed_bks = detect_reversed_bookmakers(snapshots)
        assert reversed_bks == set()

    def test_safety_majority_reversed(self):
        """Don't flag if majority would be flagged (median is unreliable)."""
        # 4 out of 7 would be flagged — that's a majority, so suppress all flags
        snapshots = [
            {"bookmaker": "a", "home_win_probability": 0.70},
            {"bookmaker": "b", "home_win_probability": 0.72},
            {"bookmaker": "c", "home_win_probability": 0.68},
            {"bookmaker": "d", "home_win_probability": 0.30},
            {"bookmaker": "e", "home_win_probability": 0.32},
            {"bookmaker": "f", "home_win_probability": 0.28},
            {"bookmaker": "g", "home_win_probability": 0.31},
        ]
        reversed_bks = detect_reversed_bookmakers(snapshots)
        assert reversed_bks == set()

    def test_minority_correctly_flagged(self):
        """Minority of reversed books are flagged when majority agrees."""
        # 5 books agree on ~70%, 2 show ~30% — the 2 are reversed
        snapshots = [
            {"bookmaker": "a", "home_win_probability": 0.70},
            {"bookmaker": "b", "home_win_probability": 0.72},
            {"bookmaker": "c", "home_win_probability": 0.68},
            {"bookmaker": "d", "home_win_probability": 0.30},
            {"bookmaker": "e", "home_win_probability": 0.32},
            {"bookmaker": "f", "home_win_probability": 0.71},
            {"bookmaker": "g", "home_win_probability": 0.69},
        ]
        reversed_bks = detect_reversed_bookmakers(snapshots)
        assert reversed_bks == {"d", "e"}

    def test_works_with_objects(self):
        """Works with ORM-like objects (attribute access)."""
        class MockSnap:
            def __init__(self, bk, prob):
                self.bookmaker = bk
                self.home_win_probability = prob

        snapshots = [
            MockSnap("betus", 0.74),
            MockSnap("fanduel", 0.33),
            MockSnap("draftkings", 0.32),
            MockSnap("betmgm", 0.34),
            MockSnap("espnbet", 0.33),
        ]
        reversed_bks = detect_reversed_bookmakers(snapshots)
        assert reversed_bks == {"betus"}

    def test_away_team_favored_reversal(self):
        """Detects reversals when away team is the favorite (median > 0.62)."""
        snapshots = [
            {"bookmaker": "reversed1", "home_win_probability": 0.25},
            {"bookmaker": "correct1", "home_win_probability": 0.72},
            {"bookmaker": "correct2", "home_win_probability": 0.74},
            {"bookmaker": "correct3", "home_win_probability": 0.70},
            {"bookmaker": "correct4", "home_win_probability": 0.73},
        ]
        reversed_bks = detect_reversed_bookmakers(snapshots)
        assert reversed_bks == {"reversed1"}

    def test_single_reversed_among_many(self):
        """Detects a single reversed bookmaker among many correct ones."""
        snapshots = [
            {"bookmaker": "reversed", "home_win_probability": 0.75},
            {"bookmaker": "c1", "home_win_probability": 0.28},
            {"bookmaker": "c2", "home_win_probability": 0.30},
            {"bookmaker": "c3", "home_win_probability": 0.27},
            {"bookmaker": "c4", "home_win_probability": 0.29},
            {"bookmaker": "c5", "home_win_probability": 0.31},
            {"bookmaker": "c6", "home_win_probability": 0.28},
        ]
        reversed_bks = detect_reversed_bookmakers(snapshots)
        assert reversed_bks == {"reversed"}
