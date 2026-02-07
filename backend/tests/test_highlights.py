"""Tests for the Highlights scoring and classification system."""

import pytest
from datetime import datetime, timezone, timedelta

from app.utils.highlights import (
    get_league_tier,
    compute_highlight,
    get_highlight_label,
    should_highlight,
    EventFlags,
    HighlightResult,
    WEIGHTS,
)


@pytest.fixture
def now():
    return datetime(2026, 2, 7, 20, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def live_commence(now):
    """Commence time 1 hour ago (game is live)."""
    return now - timedelta(hours=1)


@pytest.fixture
def upcoming_commence(now):
    """Commence time in 30 minutes (starting soon)."""
    return now + timedelta(minutes=30)


@pytest.fixture
def upcoming_2h_commence(now):
    """Commence time in 2 hours."""
    return now + timedelta(hours=2)


@pytest.fixture
def recent_finish_commence(now):
    """Commence time 4 hours ago (recently finished)."""
    return now - timedelta(hours=4)


@pytest.fixture
def far_future_commence(now):
    """Commence time 2 days from now."""
    return now + timedelta(days=2)


# =============================================================================
# get_league_tier
# =============================================================================
class TestGetLeagueTier:
    def test_tier_1_leagues(self):
        assert get_league_tier("basketball_nba") == 1
        assert get_league_tier("americanfootball_nfl") == 1
        assert get_league_tier("baseball_mlb") == 1
        assert get_league_tier("icehockey_nhl") == 1

    def test_tier_2_leagues(self):
        assert get_league_tier("americanfootball_ncaaf") == 2
        assert get_league_tier("basketball_ncaab") == 2
        assert get_league_tier("soccer_usa_mls") == 2

    def test_unknown_league_defaults_to_3(self):
        assert get_league_tier("unknown_sport") == 3

    def test_none_defaults_to_3(self):
        assert get_league_tier(None) == 3


# =============================================================================
# compute_highlight - Live Games
# =============================================================================
class TestComputeHighlightLive:
    def test_live_game_gets_30_points(self, live_commence, now):
        result = compute_highlight(
            status="live",
            commence_time=live_commence,
            now=now,
        )
        assert "live" in result.reasons
        assert result.score >= WEIGHTS["live"]

    def test_live_before_commence_not_live(self, now):
        """Status=live but commence_time in future = not treated as live."""
        future = now + timedelta(hours=1)
        result = compute_highlight(status="live", commence_time=future, now=now)
        assert "live" not in result.reasons
        assert not result.flags.is_live

    def test_live_close_game(self, live_commence, now):
        """Live + close game gets live + close_matchup points."""
        result = compute_highlight(
            status="live",
            commence_time=live_commence,
            current_home_prob=0.52,
            now=now,
        )
        assert result.flags.is_live
        assert result.flags.is_close_matchup
        assert result.score >= WEIGHTS["live"] + WEIGHTS["close_matchup"]

    def test_live_very_close_game(self, live_commence, now):
        """Live + very close game gets extra bonus."""
        result = compute_highlight(
            status="live",
            commence_time=live_commence,
            current_home_prob=0.50,
            now=now,
        )
        assert result.flags.is_very_close
        assert "very_close" in result.reasons

    def test_live_blowout_penalty(self, live_commence, now):
        """Live blowout gets score reduced by 15."""
        result = compute_highlight(
            status="live",
            commence_time=live_commence,
            current_home_prob=0.92,
            now=now,
        )
        assert result.flags.is_blowout
        assert "blowout" in result.reasons

    def test_live_favorite_switched(self, live_commence, now):
        """Live game with favorite switch gets upset bonus."""
        result = compute_highlight(
            status="live",
            commence_time=live_commence,
            current_home_prob=0.55,
            opening_favorite="away",
            now=now,
        )
        assert result.flags.favorite_switched
        assert "favorite_switched" in result.reasons
        assert result.score >= WEIGHTS["live"] + WEIGHTS["favorite_switched"]


# =============================================================================
# compute_highlight - Scheduled Games
# =============================================================================
class TestComputeHighlightScheduled:
    def test_starting_soon_3h(self, upcoming_2h_commence, now):
        """Game starting in 2 hours gets starting_soon bonus."""
        result = compute_highlight(
            status="scheduled",
            commence_time=upcoming_2h_commence,
            now=now,
        )
        assert result.flags.is_starting_soon
        assert "starting_soon" in result.reasons

    def test_starting_very_soon_1h(self, upcoming_commence, now):
        """Game starting in 30 min gets both starting_soon bonuses."""
        result = compute_highlight(
            status="scheduled",
            commence_time=upcoming_commence,
            now=now,
        )
        assert result.flags.is_starting_soon
        assert result.flags.is_starting_very_soon
        assert "starting_very_soon" in result.reasons

    def test_far_future_no_starting_soon(self, far_future_commence, now):
        """Game 2 days away gets no starting_soon bonus."""
        result = compute_highlight(
            status="scheduled",
            commence_time=far_future_commence,
            now=now,
        )
        assert not result.flags.is_starting_soon
        assert "starting_soon" not in result.reasons

    def test_pregame_closeness_no_points_without_movement(self, far_future_commence, now):
        """Pre-game close matchup without movement evidence doesn't score."""
        result = compute_highlight(
            status="scheduled",
            commence_time=far_future_commence,
            current_home_prob=0.51,
            opening_home_prob=0.50,
            now=now,
        )
        assert result.flags.is_close_matchup
        assert "close_matchup" not in result.reasons

    def test_pregame_closeness_with_movement_scores(self, far_future_commence, now):
        """Pre-game close matchup WITH significant movement gets points."""
        result = compute_highlight(
            status="scheduled",
            commence_time=far_future_commence,
            current_home_prob=0.50,
            opening_home_prob=0.60,
            now=now,
        )
        assert "close_matchup" in result.reasons

    def test_pregame_closeness_starting_soon_scores(self, upcoming_commence, now):
        """Pre-game close matchup starting soon gets points."""
        result = compute_highlight(
            status="scheduled",
            commence_time=upcoming_commence,
            current_home_prob=0.51,
            opening_home_prob=0.50,
            now=now,
        )
        assert "close_matchup" in result.reasons

    def test_pregame_tightened_from_lopsided_scores(self, far_future_commence, now):
        """Line tightened from lopsided to close gets points."""
        result = compute_highlight(
            status="scheduled",
            commence_time=far_future_commence,
            current_home_prob=0.52,
            opening_home_prob=0.70,
            now=now,
        )
        assert "close_matchup" in result.reasons

    def test_no_opening_data_gives_benefit_of_doubt(self, far_future_commence, now):
        """No opening odds data gives benefit of doubt for closeness."""
        result = compute_highlight(
            status="scheduled",
            commence_time=far_future_commence,
            current_home_prob=0.51,
            opening_home_prob=None,
            now=now,
        )
        assert "close_matchup" in result.reasons

    def test_favorite_switch_ignored_pregame(self, far_future_commence, now):
        """Pre-game favorite switch is ignored (just market noise)."""
        result = compute_highlight(
            status="scheduled",
            commence_time=far_future_commence,
            current_home_prob=0.55,
            opening_favorite="away",
            now=now,
        )
        assert not result.flags.favorite_switched


# =============================================================================
# compute_highlight - Completed Games
# =============================================================================
class TestComputeHighlightCompleted:
    def test_recently_finished(self, recent_finish_commence, now):
        """Recently finished game (< 24h) gets bonus."""
        result = compute_highlight(
            status="completed",
            commence_time=recent_finish_commence,
            now=now,
        )
        assert result.flags.is_recently_finished
        assert "recent_finish" in result.reasons

    def test_recently_finished_upset(self, recent_finish_commence, now):
        """Recently finished upset gets big bonus."""
        result = compute_highlight(
            status="completed",
            commence_time=recent_finish_commence,
            current_home_prob=0.55,
            opening_favorite="away",
            now=now,
        )
        assert result.flags.is_upset
        assert "upset" in result.reasons
        assert result.score >= WEIGHTS["recent_finish"] + WEIGHTS["recent_finish_upset"]

    def test_old_completed_no_recent_bonus(self, now):
        """Completed game > 24h ago gets no recent bonus."""
        old_commence = now - timedelta(hours=30)
        result = compute_highlight(
            status="completed",
            commence_time=old_commence,
            now=now,
        )
        assert not result.flags.is_recently_finished


# =============================================================================
# compute_highlight - Probability & Score Swings
# =============================================================================
class TestComputeHighlightSwings:
    def test_major_probability_swing(self, live_commence, now):
        result = compute_highlight(
            status="live",
            commence_time=live_commence,
            current_home_prob=0.70,
            opening_home_prob=0.50,
            now=now,
        )
        assert result.flags.probability_swing == "major"
        assert "major_prob_swing" in result.reasons

    def test_minor_probability_swing(self, live_commence, now):
        result = compute_highlight(
            status="live",
            commence_time=live_commence,
            current_home_prob=0.60,
            opening_home_prob=0.50,
            now=now,
        )
        assert result.flags.probability_swing == "minor"
        assert "major_prob_swing" not in result.reasons

    def test_stable_probability(self, live_commence, now):
        result = compute_highlight(
            status="live",
            commence_time=live_commence,
            current_home_prob=0.53,
            opening_home_prob=0.50,
            now=now,
        )
        assert result.flags.probability_swing == "stable"

    def test_major_score_swing(self, live_commence, now):
        result = compute_highlight(
            status="live",
            commence_time=live_commence,
            current_over_under=270.0,
            opening_over_under=220.0,
            now=now,
        )
        assert result.flags.score_swing == "major"
        assert "major_score_swing" in result.reasons

    def test_minor_score_swing(self, live_commence, now):
        result = compute_highlight(
            status="live",
            commence_time=live_commence,
            current_over_under=245.0,
            opening_over_under=220.0,
            now=now,
        )
        assert result.flags.score_swing == "minor"


# =============================================================================
# compute_highlight - League Tiers
# =============================================================================
class TestComputeHighlightLeagueTiers:
    def test_tier_1_bonus(self, live_commence, now):
        result = compute_highlight(
            status="live",
            commence_time=live_commence,
            sport_key="basketball_nba",
            now=now,
        )
        assert result.flags.league_tier == 1
        assert "tier_1" in result.reasons

    def test_tier_2_bonus(self, live_commence, now):
        result = compute_highlight(
            status="live",
            commence_time=live_commence,
            sport_key="basketball_ncaab",
            now=now,
        )
        assert result.flags.league_tier == 2
        assert "tier_2" in result.reasons

    def test_tier_3_no_bonus(self, live_commence, now):
        result = compute_highlight(
            status="live",
            commence_time=live_commence,
            sport_key="cricket_test",
            now=now,
        )
        assert result.flags.league_tier == 3
        assert "tier_1" not in result.reasons
        assert "tier_2" not in result.reasons


# =============================================================================
# compute_highlight - Score Cap & Primary Reason
# =============================================================================
class TestComputeHighlightMeta:
    def test_score_capped_at_100(self, live_commence, now):
        result = compute_highlight(
            status="live",
            commence_time=live_commence,
            sport_key="basketball_nba",
            current_home_prob=0.50,
            opening_home_prob=0.30,
            opening_favorite="away",
            now=now,
        )
        assert result.score <= 100

    def test_primary_reason_upset(self, recent_finish_commence, now):
        result = compute_highlight(
            status="completed",
            commence_time=recent_finish_commence,
            current_home_prob=0.55,
            opening_favorite="away",
            now=now,
        )
        assert result.primary_reason == "Recent upset"

    def test_primary_reason_favorite_switched(self, live_commence, now):
        result = compute_highlight(
            status="live",
            commence_time=live_commence,
            current_home_prob=0.55,
            opening_favorite="away",
            now=now,
        )
        assert result.primary_reason == "Possible upset"

    def test_primary_reason_very_close(self, live_commence, now):
        result = compute_highlight(
            status="live",
            commence_time=live_commence,
            current_home_prob=0.50,
            now=now,
        )
        assert result.primary_reason == "Coin flip"

    def test_primary_reason_close_matchup(self, live_commence, now):
        result = compute_highlight(
            status="live",
            commence_time=live_commence,
            current_home_prob=0.42,
            now=now,
        )
        assert result.primary_reason == "Close matchup"

    def test_primary_reason_big_line_movement(self, live_commence, now):
        result = compute_highlight(
            status="live",
            commence_time=live_commence,
            current_home_prob=0.70,
            opening_home_prob=0.50,
            now=now,
        )
        assert result.primary_reason == "Big line movement"

    def test_primary_reason_starting_soon(self, upcoming_commence, now):
        result = compute_highlight(
            status="scheduled",
            commence_time=upcoming_commence,
            now=now,
        )
        assert result.primary_reason == "Starting soon"

    def test_no_primary_reason_for_uninteresting(self, far_future_commence, now):
        result = compute_highlight(
            status="scheduled",
            commence_time=far_future_commence,
            now=now,
        )
        assert result.primary_reason is None

    def test_timezone_naive_commence_handled(self, now):
        naive_time = datetime(2026, 2, 7, 19, 0, 0)
        result = compute_highlight(
            status="live",
            commence_time=naive_time,
            now=now,
        )
        assert result.flags.is_live


# =============================================================================
# get_highlight_label
# =============================================================================
class TestGetHighlightLabel:
    def test_upset_label(self):
        result = HighlightResult(flags=EventFlags(is_upset=True))
        assert get_highlight_label(result) == "Recent upset"

    def test_live_favorite_switched(self):
        result = HighlightResult(flags=EventFlags(is_live=True, favorite_switched=True))
        assert get_highlight_label(result) == "Upset brewing"

    def test_live_very_close(self):
        result = HighlightResult(flags=EventFlags(is_live=True, is_very_close=True))
        assert get_highlight_label(result) == "Coin flip"

    def test_live_close(self):
        result = HighlightResult(flags=EventFlags(is_live=True, is_close_matchup=True))
        assert get_highlight_label(result) == "Close game"

    def test_live_momentum_shift(self):
        result = HighlightResult(flags=EventFlags(is_live=True, probability_swing="major"))
        assert get_highlight_label(result) == "Momentum shift"

    def test_starting_very_soon_close(self):
        result = HighlightResult(flags=EventFlags(
            is_starting_very_soon=True, is_close_matchup=True
        ))
        assert get_highlight_label(result) == "Close matchup"

    def test_starting_soon_close(self):
        result = HighlightResult(flags=EventFlags(
            is_starting_soon=True, is_close_matchup=True
        ))
        assert get_highlight_label(result) == "Close matchup"

    def test_live_generic(self):
        result = HighlightResult(flags=EventFlags(is_live=True))
        assert get_highlight_label(result) == "Live"

    def test_pregame_line_moving(self):
        result = HighlightResult(flags=EventFlags(probability_swing="major"))
        assert get_highlight_label(result) == "Line moving"

    def test_no_label_for_boring_event(self):
        result = HighlightResult(flags=EventFlags())
        assert get_highlight_label(result) is None


# =============================================================================
# should_highlight
# =============================================================================
class TestShouldHighlight:
    def test_live_close_always_highlighted(self):
        result = HighlightResult(score=20, flags=EventFlags(is_live=True, is_close_matchup=True))
        assert should_highlight(result) is True

    def test_live_upset_always_highlighted(self):
        result = HighlightResult(score=10, flags=EventFlags(is_live=True, favorite_switched=True))
        assert should_highlight(result) is True

    def test_recent_upset_always_highlighted(self):
        result = HighlightResult(score=15, flags=EventFlags(is_upset=True))
        assert should_highlight(result) is True

    def test_high_score_highlighted(self):
        result = HighlightResult(score=50, flags=EventFlags())
        assert should_highlight(result) is True

    def test_low_score_not_highlighted(self):
        result = HighlightResult(score=20, flags=EventFlags())
        assert should_highlight(result) is False

    def test_custom_min_score(self):
        result = HighlightResult(score=25, flags=EventFlags())
        assert should_highlight(result, min_score=20) is True
        assert should_highlight(result, min_score=30) is False

    def test_exactly_30_highlighted(self):
        result = HighlightResult(score=30, flags=EventFlags())
        assert should_highlight(result) is True

    def test_exactly_29_not_highlighted(self):
        result = HighlightResult(score=29, flags=EventFlags())
        assert should_highlight(result) is False
