"""Tests for binary contract → implied spread/total utilities."""

import pytest
from app.utils.binary_spread import (
    binary_to_implied_spread,
    binary_to_implied_total,
    projected_final_score,
    extract_spread_threshold,
    extract_total_threshold,
)


class TestBinaryToImpliedSpread:
    """Tests for binary_to_implied_spread()."""

    def test_standard_nba_spread(self):
        """Real-world NBA example: BOS favored by ~10 over MIN."""
        contracts = [
            {"threshold": 1.0, "probability": 0.87},
            {"threshold": 3.5, "probability": 0.76},
            {"threshold": 5.5, "probability": 0.66},
            {"threshold": 7.5, "probability": 0.60},
            {"threshold": 10.5, "probability": 0.48},
            {"threshold": 14.5, "probability": 0.26},
        ]
        result = binary_to_implied_spread(contracts)
        assert result is not None
        # Should be around -10 (between 7.5 and 10.5)
        assert -12 < result.spread < -8
        assert result.lower_threshold == 7.5
        assert result.upper_threshold == 10.5

    def test_close_game(self):
        """Nearly even game — spread near 0."""
        contracts = [
            {"threshold": 1.0, "probability": 0.52},
            {"threshold": 3.5, "probability": 0.38},
            {"threshold": 5.5, "probability": 0.25},
        ]
        result = binary_to_implied_spread(contracts)
        assert result is not None
        assert -3 < result.spread < 0

    def test_massive_favorite(self):
        """All contracts above 50% — extrapolate."""
        contracts = [
            {"threshold": 5.5, "probability": 0.90},
            {"threshold": 10.5, "probability": 0.80},
            {"threshold": 14.5, "probability": 0.65},
        ]
        result = binary_to_implied_spread(contracts)
        assert result is not None
        assert result.spread < -14  # Beyond the highest threshold
        assert result.confidence < 0.5  # Low confidence extrapolation

    def test_big_underdog(self):
        """All contracts below 50% — team unlikely to win by any margin."""
        contracts = [
            {"threshold": 1.0, "probability": 0.40},
            {"threshold": 3.5, "probability": 0.25},
            {"threshold": 5.5, "probability": 0.15},
        ]
        result = binary_to_implied_spread(contracts)
        assert result is not None
        assert result.confidence < 0.5

    def test_insufficient_data(self):
        """Need at least 2 contracts."""
        assert binary_to_implied_spread([]) is None
        assert binary_to_implied_spread([{"threshold": 5.5, "probability": 0.60}]) is None

    def test_unsorted_input(self):
        """Contracts can arrive in any order."""
        contracts = [
            {"threshold": 10.5, "probability": 0.48},
            {"threshold": 1.0, "probability": 0.87},
            {"threshold": 7.5, "probability": 0.60},
        ]
        result = binary_to_implied_spread(contracts)
        assert result is not None
        assert -12 < result.spread < -8

    def test_polymarket_two_thresholds(self):
        """Polymarket often has just 2 thresholds (e.g., 9.5 and 10.5)."""
        contracts = [
            {"threshold": 9.5, "probability": 0.55},
            {"threshold": 10.5, "probability": 0.45},
        ]
        result = binary_to_implied_spread(contracts)
        assert result is not None
        assert -11 < result.spread < -9


class TestBinaryToImpliedTotal:
    """Tests for binary_to_implied_total()."""

    def test_standard_nba_total(self):
        """Real-world NBA: total around 222."""
        contracts = [
            {"threshold": 210, "probability": 0.85},
            {"threshold": 220, "probability": 0.55},
            {"threshold": 222, "probability": 0.48},
            {"threshold": 230, "probability": 0.25},
        ]
        result = binary_to_implied_total(contracts)
        assert result is not None
        assert 219 < result.total < 223

    def test_polymarket_tight_thresholds(self):
        """Polymarket: 219.5, 220.5, 221.5, 222.5."""
        contracts = [
            {"threshold": 219.5, "probability": 0.58},
            {"threshold": 220.5, "probability": 0.52},
            {"threshold": 221.5, "probability": 0.46},
            {"threshold": 222.5, "probability": 0.40},
        ]
        result = binary_to_implied_total(contracts)
        assert result is not None
        assert 220 < result.total < 222

    def test_insufficient_data(self):
        assert binary_to_implied_total([]) is None
        assert binary_to_implied_total([{"threshold": 220, "probability": 0.55}]) is None


class TestProjectedFinalScore:
    """Tests for projected_final_score()."""

    def test_basic_projection(self):
        """BOS -10, total 222 → BOS 116, MIN 106."""
        result = projected_final_score(spread=-10, total=222)
        assert result.home_score == 116
        assert result.away_score == 106

    def test_even_game(self):
        """Spread 0, total 200 → 100-100."""
        result = projected_final_score(spread=0, total=200)
        assert result.home_score == 100
        assert result.away_score == 100

    def test_away_favorite(self):
        """Home is underdog: spread positive."""
        result = projected_final_score(spread=7, total=200)
        # home_score = (200 - 7) / 2 = 96.5
        # away_score = (200 + 7) / 2 = 103.5
        assert result.home_score == 96.5
        assert result.away_score == 103.5

    def test_half_point_spread(self):
        """Fractional spread."""
        result = projected_final_score(spread=-3.5, total=45)
        # home = (45 + 3.5) / 2 = 24.25
        assert result.home_score == 24.2  # rounded to 1dp
        assert result.away_score == 20.8


class TestExtractSpreadThreshold:
    """Tests for extract_spread_threshold()."""

    def test_wins_by_pattern(self):
        assert extract_spread_threshold("BOS wins by 9.5+") == 9.5
        assert extract_spread_threshold("Team wins by 14+") == 14.0

    def test_plus_minus_pattern(self):
        assert extract_spread_threshold("Boston Celtics -9.5") == 9.5
        assert extract_spread_threshold("+4.5") == 4.5

    def test_spread_keyword(self):
        assert extract_spread_threshold("Spread 7.5") == 7.5

    def test_no_match(self):
        assert extract_spread_threshold("Boston Celtics") is None
        assert extract_spread_threshold("Over 220.5") is None


class TestExtractTotalThreshold:
    """Tests for extract_total_threshold()."""

    def test_over_pattern(self):
        assert extract_total_threshold("Over 220.5") == 220.5
        assert extract_total_threshold("Total exceeds 219.5") == 219.5

    def test_ou_pattern(self):
        assert extract_total_threshold("O/U 222") == 222.0

    def test_no_match(self):
        assert extract_total_threshold("Boston Celtics -9.5") is None
        assert extract_total_threshold("Moneyline") is None
