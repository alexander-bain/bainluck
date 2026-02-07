"""Extended tests for odds_math utilities.

Covers functions not tested in the original test_odds_math.py:
- project_scores
- calculate_gei
- format_probability
- probability_to_american
- Edge cases and round-trip conversions
"""

import pytest
from app.utils.odds_math import (
    american_to_probability,
    decimal_to_probability,
    remove_vig,
    moneyline_to_probability,
    project_scores,
    calculate_gei,
    format_probability,
    probability_to_american,
    aggregate_probabilities,
)


# =============================================================================
# project_scores
# =============================================================================
class TestProjectScores:
    def test_home_favored(self):
        """Negative spread = home favored, home score should be higher."""
        home, away = project_scores(-14.5, 226)
        assert home > away
        assert abs(home - away - 14.5) < 0.1
        assert abs(home + away - 226) < 0.1

    def test_away_favored(self):
        """Positive spread = away favored, away score should be higher."""
        home, away = project_scores(3.5, 45)
        assert away > home
        assert abs(away - home - 3.5) < 0.2
        assert abs(home + away - 45) < 0.2

    def test_even_spread(self):
        """Zero spread means equal projected scores."""
        home, away = project_scores(0, 44)
        assert home == away == 22.0

    def test_scores_sum_to_total(self):
        """Projected scores always sum to over/under."""
        home, away = project_scores(-7.0, 48.5)
        assert abs(home + away - 48.5) < 0.2

    def test_nba_typical(self):
        home, away = project_scores(-5.5, 220.5)
        assert home == 113.0
        assert away == 107.5


# =============================================================================
# calculate_gei
# =============================================================================
class TestCalculateGei:
    def test_close_game_high_scoring(self):
        """50/50 game with high scoring should have high GEI."""
        gei = calculate_gei(0.50, 230, "basketball_nba")
        assert gei > 70

    def test_blowout_low_gei(self):
        """85% favorite should have lower GEI than even matchup."""
        gei_blowout = calculate_gei(0.85, 220, "basketball_nba")
        gei_even = calculate_gei(0.50, 220, "basketball_nba")
        assert gei_blowout < gei_even

    def test_perfectly_even(self):
        """50/50 matchup has maximum closeness component."""
        gei = calculate_gei(0.50, 220, "basketball_nba")
        assert gei >= 80

    def test_certain_outcome(self):
        """Probability near 1.0 has near-zero closeness."""
        gei = calculate_gei(0.99, 220, "basketball_nba")
        assert gei < 40

    def test_unknown_sport_uses_default(self):
        """Unknown sport key uses default average total."""
        gei = calculate_gei(0.50, 100, "unknown_sport")
        assert 0 <= gei <= 100

    def test_scoring_factor_capped(self):
        """Very high total doesn't make GEI infinitely large."""
        gei_high = calculate_gei(0.50, 1000, "basketball_nba")
        gei_normal = calculate_gei(0.50, 220, "basketball_nba")
        # With cap at 150%, high total shouldn't be much higher
        assert gei_high < gei_normal * 1.5

    def test_range(self):
        """GEI values should be non-negative."""
        for prob in [0.01, 0.25, 0.50, 0.75, 0.99]:
            for ou in [5, 50, 200, 500]:
                gei = calculate_gei(prob, ou, "basketball_nba")
                assert gei >= 0


# =============================================================================
# format_probability
# =============================================================================
class TestFormatProbability:
    def test_percent_format(self):
        assert format_probability(0.593) == "59%"

    def test_percent_format_round_up(self):
        assert format_probability(0.555) == "56%"

    def test_percent_format_even(self):
        assert format_probability(0.50) == "50%"

    def test_percent_format_zero(self):
        assert format_probability(0.0) == "0%"

    def test_percent_format_one(self):
        assert format_probability(1.0) == "100%"

    def test_decimal_format(self):
        assert format_probability(0.593, style="decimal") == "0.59"

    def test_decimal_format_even(self):
        assert format_probability(0.50, style="decimal") == "0.50"


# =============================================================================
# probability_to_american
# =============================================================================
class TestProbabilityToAmerican:
    def test_favorite(self):
        odds = probability_to_american(0.6)
        assert odds == -150

    def test_underdog(self):
        odds = probability_to_american(0.4)
        assert odds == 150

    def test_even_money(self):
        odds = probability_to_american(0.5)
        assert odds == -100 or odds == 100

    def test_heavy_favorite(self):
        odds = probability_to_american(0.9)
        assert odds == -900

    def test_heavy_underdog(self):
        odds = probability_to_american(0.1)
        assert odds == 900


# =============================================================================
# Round-trip Conversions
# =============================================================================
class TestRoundTripConversions:
    def test_american_round_trip_favorite(self):
        original = -150
        prob = american_to_probability(original)
        recovered = probability_to_american(prob)
        assert recovered == original

    def test_american_round_trip_underdog(self):
        original = 200
        prob = american_to_probability(original)
        recovered = probability_to_american(prob)
        assert recovered == original

    def test_american_round_trip_even(self):
        prob = american_to_probability(-100)
        assert abs(prob - 0.5) < 0.001
        recovered = probability_to_american(prob)
        assert recovered == -100

    def test_prob_round_trip(self):
        for prob in [0.2, 0.4, 0.6, 0.8]:
            odds = probability_to_american(prob)
            recovered = american_to_probability(odds)
            assert abs(recovered - prob) < 0.02


# =============================================================================
# decimal_to_probability
# =============================================================================
class TestDecimalToProbability:
    def test_even_odds(self):
        assert decimal_to_probability(2.0) == 0.5

    def test_heavy_favorite(self):
        prob = decimal_to_probability(1.1)
        assert abs(prob - 0.909) < 0.01

    def test_heavy_underdog(self):
        prob = decimal_to_probability(10.0)
        assert abs(prob - 0.1) < 0.001


# =============================================================================
# Edge Cases
# =============================================================================
class TestEdgeCases:
    def test_aggregate_single_value(self):
        assert aggregate_probabilities([0.75]) == 0.75

    def test_aggregate_all_same(self):
        result = aggregate_probabilities([0.60, 0.60, 0.60])
        assert abs(result - 0.60) < 0.0001

    def test_remove_vig_already_normalized(self):
        home, away = remove_vig(0.60, 0.40)
        assert abs(home - 0.60) < 0.001
        assert abs(away - 0.40) < 0.001

    def test_remove_vig_high_juice(self):
        home, away = remove_vig(0.60, 0.50)
        assert abs(home + away - 1.0) < 0.0001
