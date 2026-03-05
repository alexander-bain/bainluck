"""Tests for series win probability computation."""

import pytest
from app.utils.series_probability import compute_series_win_prob, series_state_label


# =============================================================================
# compute_series_win_prob — basic cases
# =============================================================================


class TestSeriesWinProbBasic:
    """Basic best-of-7 series scenarios."""

    def test_even_series_coin_flip(self):
        """Tied series with 50% game win prob → 50% series win prob."""
        result = compute_series_win_prob(0.5, 0, 0, games_to_win=4)
        assert abs(result - 0.5) < 0.001

    def test_tied_2_2_coin_flip(self):
        """Tied 2-2 with 50% → still 50%."""
        result = compute_series_win_prob(0.5, 2, 2, games_to_win=4)
        assert abs(result - 0.5) < 0.001

    def test_tied_3_3_coin_flip(self):
        """Tied 3-3 (Game 7) with 50% → 50%."""
        result = compute_series_win_prob(0.5, 3, 3, games_to_win=4)
        assert abs(result - 0.5) < 0.001

    def test_already_won(self):
        """Team already has 4 wins → 100%."""
        result = compute_series_win_prob(0.5, 4, 2, games_to_win=4)
        assert result == 1.0

    def test_already_lost(self):
        """Opponent already has 4 wins → 0%."""
        result = compute_series_win_prob(0.5, 2, 4, games_to_win=4)
        assert result == 0.0


class TestSeriesWinProbLeading:
    """Series where one team leads."""

    def test_lead_3_1_coin_flip(self):
        """Leading 3-1 with 50% game prob → ~81.25% series prob."""
        result = compute_series_win_prob(0.5, 3, 1, games_to_win=4)
        # Need 1 win in up to 3 games: 1 - (0.5)^3 = 0.875
        assert abs(result - 0.875) < 0.001

    def test_lead_3_0_coin_flip(self):
        """Leading 3-0 with 50% → ~93.75%."""
        result = compute_series_win_prob(0.5, 3, 0, games_to_win=4)
        # Need 1 win in up to 4 games: 1 - (0.5)^4 = 0.9375
        assert abs(result - 0.9375) < 0.001

    def test_trail_1_3_coin_flip(self):
        """Trailing 1-3 with 50% → ~12.5%."""
        result = compute_series_win_prob(0.5, 1, 3, games_to_win=4)
        # Need 3 wins in 3 games: (0.5)^3 = 0.125
        assert abs(result - 0.125) < 0.001

    def test_trail_0_3_coin_flip(self):
        """Trailing 0-3 with 50% → ~6.25%."""
        result = compute_series_win_prob(0.5, 0, 3, games_to_win=4)
        # Need 4 wins in 4 games: (0.5)^4 = 0.0625
        assert abs(result - 0.0625) < 0.001

    def test_lead_2_1_coin_flip(self):
        """Leading 2-1 with 50% → ~68.75%."""
        result = compute_series_win_prob(0.5, 2, 1, games_to_win=4)
        assert abs(result - 0.6875) < 0.001


class TestSeriesWinProbNonCoinFlip:
    """Series with non-50% game probabilities."""

    def test_strong_favorite_0_0(self):
        """Strong favorite (70% per game) from 0-0."""
        result = compute_series_win_prob(0.7, 0, 0, games_to_win=4)
        assert result > 0.87  # Should be well above 50%

    def test_strong_underdog_0_0(self):
        """Underdog (30% per game) from 0-0."""
        result = compute_series_win_prob(0.3, 0, 0, games_to_win=4)
        assert result < 0.13  # Mirror of above

    def test_favorite_and_underdog_sum_to_one(self):
        """P(team wins) + P(opponent wins) should equal 1.0."""
        p = 0.65
        team_prob = compute_series_win_prob(p, 1, 2, games_to_win=4)
        opp_prob = compute_series_win_prob(1 - p, 2, 1, games_to_win=4)
        assert abs(team_prob + opp_prob - 1.0) < 0.0001

    def test_game_7_equals_game_prob(self):
        """In Game 7 (3-3), series prob equals single game prob."""
        p = 0.62
        result = compute_series_win_prob(p, 3, 3, games_to_win=4)
        assert abs(result - p) < 0.0001

    def test_certain_winner(self):
        """100% game win prob → 100% series win."""
        result = compute_series_win_prob(1.0, 0, 0, games_to_win=4)
        assert result == 1.0

    def test_certain_loser(self):
        """0% game win prob → 0% series win."""
        result = compute_series_win_prob(0.0, 0, 0, games_to_win=4)
        assert result == 0.0


class TestSeriesWinProbBestOf:
    """Different series lengths."""

    def test_best_of_3(self):
        """Best-of-3: games_to_win=2."""
        result = compute_series_win_prob(0.5, 0, 0, games_to_win=2)
        assert abs(result - 0.5) < 0.001

    def test_best_of_5(self):
        """Best-of-5: games_to_win=3."""
        result = compute_series_win_prob(0.5, 0, 0, games_to_win=3)
        assert abs(result - 0.5) < 0.001

    def test_best_of_1(self):
        """Best-of-1: games_to_win=1, prob equals game prob."""
        p = 0.65
        result = compute_series_win_prob(p, 0, 0, games_to_win=1)
        assert abs(result - p) < 0.0001

    def test_best_of_5_leading_2_1(self):
        """Best-of-5 leading 2-1 with 50%."""
        result = compute_series_win_prob(0.5, 2, 1, games_to_win=3)
        # Need 1 win in up to 2 games: 1 - (0.5)^2 = 0.75
        assert abs(result - 0.75) < 0.001


class TestSeriesWinProbValidation:
    """Input validation tests."""

    def test_negative_prob_raises(self):
        with pytest.raises(ValueError, match="between 0 and 1"):
            compute_series_win_prob(-0.1, 0, 0)

    def test_prob_above_one_raises(self):
        with pytest.raises(ValueError, match="between 0 and 1"):
            compute_series_win_prob(1.1, 0, 0)

    def test_negative_games_won_raises(self):
        with pytest.raises(ValueError, match="cannot be negative"):
            compute_series_win_prob(0.5, -1, 0)

    def test_negative_opponent_games_raises(self):
        with pytest.raises(ValueError, match="cannot be negative"):
            compute_series_win_prob(0.5, 0, -1)

    def test_zero_games_to_win_raises(self):
        with pytest.raises(ValueError, match="at least 1"):
            compute_series_win_prob(0.5, 0, 0, games_to_win=0)


class TestSeriesWinProbSymmetry:
    """Symmetry and consistency checks."""

    def test_symmetric_at_50_percent(self):
        """Leading X-Y at 50% should be the complement of trailing Y-X at 50%."""
        lead = compute_series_win_prob(0.5, 3, 1, games_to_win=4)
        trail = compute_series_win_prob(0.5, 1, 3, games_to_win=4)
        assert abs(lead + trail - 1.0) < 0.0001

    def test_higher_game_prob_means_higher_series_prob(self):
        """A higher per-game probability should yield a higher series probability."""
        low = compute_series_win_prob(0.45, 2, 2, games_to_win=4)
        high = compute_series_win_prob(0.55, 2, 2, games_to_win=4)
        assert high > low

    def test_more_wins_means_higher_series_prob(self):
        """Leading in the series should increase series win probability."""
        tied = compute_series_win_prob(0.5, 2, 2, games_to_win=4)
        leading = compute_series_win_prob(0.5, 3, 2, games_to_win=4)
        assert leading > tied


# =============================================================================
# series_state_label
# =============================================================================


class TestSeriesStateLabel:
    """Tests for human-readable series state labels."""

    def test_tied_0_0(self):
        assert series_state_label(0, 0) == "Series tied 0-0"

    def test_tied_2_2(self):
        assert series_state_label(2, 2) == "Series tied 2-2"

    def test_leading_with_name(self):
        assert series_state_label(3, 1, team_name="Lakers") == "Lakers lead 3-1"

    def test_trailing_with_name(self):
        assert series_state_label(1, 3, team_name="Lakers") == "Lakers trail 1-3"

    def test_won_series(self):
        assert series_state_label(4, 2, team_name="Celtics") == "Celtics win series 4-2"

    def test_lost_series(self):
        assert series_state_label(2, 4, team_name="Celtics") == "Celtics lose series 2-4"

    def test_default_team_name(self):
        assert series_state_label(3, 1) == "Team lead 3-1"

    def test_best_of_5(self):
        assert series_state_label(3, 1, games_to_win=3, team_name="Nets") == "Nets win series 3-1"

    def test_trailing_default_name(self):
        assert series_state_label(0, 2) == "Team trail 0-2"
