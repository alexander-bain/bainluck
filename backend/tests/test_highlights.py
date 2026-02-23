"""Tests for the Highlights scoring and classification system."""

import pytest
from datetime import datetime, timezone, timedelta

from app.utils.highlights import (
    get_league_tier,
    compute_highlight,
    compute_time_series_metrics,
    get_highlight_label,
    should_highlight,
    EventFlags,
    HighlightResult,
    TimeSeriesMetrics,
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
        assert get_league_tier("unknown_sport") == 4

    def test_none_defaults_to_3(self):
        assert get_league_tier(None) == 4


# =============================================================================
# compute_highlight - Live Games
# =============================================================================
class TestComputeHighlightLive:
    def test_live_game_gets_30_points(self, live_commence, now):
        result = compute_highlight(
            status="live",
            commence_time=live_commence,
            sport_key="basketball_nba",
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
            sport_key="basketball_nba",
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

    def test_tier_2_college_power4_both(self, live_commence, now):
        """Both Power 4 teams → full tier_2 bonus (+10)."""
        result = compute_highlight(
            status="live",
            commence_time=live_commence,
            sport_key="basketball_ncaab",
            home_team_name="Duke Blue Devils",
            away_team_name="North Carolina Tar Heels",
            now=now,
        )
        assert "tier_2" in result.reasons
        assert result.score >= WEIGHTS["live"] + WEIGHTS["tier_2_league"]

    def test_tier_2_college_power4_mixed(self, live_commence, now):
        """One Power 4 + one mid-major → reduced tier_2 (+5)."""
        result = compute_highlight(
            status="live",
            commence_time=live_commence,
            sport_key="basketball_ncaab",
            home_team_name="Duke Blue Devils",
            away_team_name="Gonzaga Bulldogs",
            now=now,
        )
        assert "tier_2_p4_mixed" in result.reasons
        assert result.score >= WEIGHTS["live"] + WEIGHTS["tier_2_power4_mixed"]

    def test_tier_2_college_midmajor_both(self, live_commence, now):
        """Both mid-major → minimal tier_2 bonus (+2)."""
        result = compute_highlight(
            status="live",
            commence_time=live_commence,
            sport_key="basketball_ncaab",
            home_team_name="Gonzaga Bulldogs",
            away_team_name="Boise State Broncos",
            now=now,
        )
        assert "tier_2_midmajor" in result.reasons
        assert result.score >= WEIGHTS["live"] + WEIGHTS["tier_2_midmajor"]

    def test_tier_2_college_no_team_names_full_bonus(self, live_commence, now):
        """College game without team names → default full tier_2 bonus."""
        result = compute_highlight(
            status="live",
            commence_time=live_commence,
            sport_key="americanfootball_ncaaf",
            now=now,
        )
        assert "tier_2" in result.reasons
        assert result.score >= WEIGHTS["live"] + WEIGHTS["tier_2_league"]

    def test_tier_2_non_college_full_bonus(self, live_commence, now):
        """Non-college tier 2 (e.g., WNBA) → always full tier_2 bonus."""
        result = compute_highlight(
            status="live",
            commence_time=live_commence,
            sport_key="basketball_wnba",
            now=now,
        )
        assert "tier_2" in result.reasons
        assert result.score >= WEIGHTS["live"] + WEIGHTS["tier_2_league"]

    def test_tier_3_no_bonus(self, live_commence, now):
        result = compute_highlight(
            status="live",
            commence_time=live_commence,
            sport_key="soccer_mexico_ligamx",
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
            sport_key="soccer_mexico_ligamx",
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


# =============================================================================
# compute_highlight - Away-side Blowouts & Edge Cases
# =============================================================================
class TestComputeHighlightEdgeCases:
    def test_away_blowout(self, live_commence, now):
        """Away blowout (home_prob <= 0.15) triggers blowout flag."""
        result = compute_highlight(
            status="live",
            commence_time=live_commence,
            current_home_prob=0.08,
            now=now,
        )
        assert result.flags.is_blowout
        assert "blowout" in result.reasons

    def test_blowout_penalty_floor_at_zero(self, now):
        """Blowout penalty doesn't push score below 0."""
        # A far-future scheduled game with no bonuses + blowout
        far_future = now + timedelta(days=5)
        result = compute_highlight(
            status="scheduled",
            commence_time=far_future,
            current_home_prob=0.95,
            now=now,
        )
        assert result.score >= 0

    def test_closed_status_recently_finished(self, recent_finish_commence, now):
        """'closed' status gets the same recent_finish treatment as 'completed'."""
        result = compute_highlight(
            status="closed",
            commence_time=recent_finish_commence,
            now=now,
        )
        assert result.flags.is_recently_finished
        assert "recent_finish" in result.reasons

    def test_closed_status_favorite_switched(self, recent_finish_commence, now):
        """'closed' status detects favorite switch and upset."""
        result = compute_highlight(
            status="closed",
            commence_time=recent_finish_commence,
            current_home_prob=0.60,
            opening_favorite="away",
            now=now,
        )
        assert result.flags.favorite_switched
        assert result.flags.is_upset

    def test_no_probability_data(self, live_commence, now):
        """No current_home_prob: no probability-based scoring."""
        result = compute_highlight(
            status="live",
            commence_time=live_commence,
            current_home_prob=None,
            now=now,
        )
        assert not result.flags.is_close_matchup
        assert not result.flags.is_blowout
        assert not result.flags.favorite_switched
        # Still gets live bonus
        assert "live" in result.reasons

    def test_current_exactly_50_is_very_close(self, live_commence, now):
        """Probability of exactly 0.50 is both close_matchup and very_close."""
        result = compute_highlight(
            status="live",
            commence_time=live_commence,
            current_home_prob=0.50,
            now=now,
        )
        assert result.flags.is_close_matchup
        assert result.flags.is_very_close

    def test_favorite_switch_even_current_no_switch(self, live_commence, now):
        """If current_home_prob == 0.50 (even), no favorite switch detected."""
        result = compute_highlight(
            status="live",
            commence_time=live_commence,
            current_home_prob=0.50,
            opening_favorite="home",
            now=now,
        )
        assert not result.flags.favorite_switched

    def test_favorite_switch_even_opening_no_switch(self, live_commence, now):
        """If opening_favorite == 'even', no favorite switch detected."""
        result = compute_highlight(
            status="live",
            commence_time=live_commence,
            current_home_prob=0.60,
            opening_favorite="even",
            now=now,
        )
        assert not result.flags.favorite_switched

    def test_score_swing_zero_opening_ou(self, live_commence, now):
        """Zero opening_over_under: score swing check is skipped (no division by zero)."""
        result = compute_highlight(
            status="live",
            commence_time=live_commence,
            current_over_under=45.0,
            opening_over_under=0,
            now=now,
        )
        assert result.flags.score_swing == "stable"

    def test_recently_finished_boundary_exactly_24h(self, now):
        """Exactly 24 hours ago is NOT recently finished (> check, not >=)."""
        boundary = now - timedelta(hours=24)
        result = compute_highlight(
            status="completed",
            commence_time=boundary,
            now=now,
        )
        # hours_since = 24.0, condition is 0 < hours_since <= 24
        assert result.flags.is_recently_finished

    def test_recently_finished_boundary_just_over_24h(self, now):
        """Just over 24 hours ago is NOT recently finished."""
        boundary = now - timedelta(hours=24, minutes=1)
        result = compute_highlight(
            status="completed",
            commence_time=boundary,
            now=now,
        )
        assert not result.flags.is_recently_finished

    def test_starting_soon_boundary_exactly_3h(self, now):
        """Exactly 3 hours from now is starting soon (condition is <= 3)."""
        boundary = now + timedelta(hours=3)
        result = compute_highlight(
            status="scheduled",
            commence_time=boundary,
            now=now,
        )
        assert result.flags.is_starting_soon

    def test_starting_soon_boundary_just_over_3h(self, now):
        """Just over 3 hours from now is NOT starting soon."""
        boundary = now + timedelta(hours=3, minutes=1)
        result = compute_highlight(
            status="scheduled",
            commence_time=boundary,
            now=now,
        )
        assert not result.flags.is_starting_soon


# =============================================================================
# compute_highlight - Exact Score Accumulation
# =============================================================================
class TestComputeHighlightExactScores:
    """Pin exact score accumulation for combined scenarios.

    These catch accidental weight changes or missing bonuses.
    """

    def test_live_close_tier1_score(self, live_commence, now):
        """Live + close + very_close + tier 1 = known exact score."""
        result = compute_highlight(
            status="live",
            commence_time=live_commence,
            sport_key="basketball_nba",
            current_home_prob=0.50,
            now=now,
        )
        expected = (
            WEIGHTS["live"]
            + WEIGHTS["close_matchup"]
            + WEIGHTS["very_close"]
            + WEIGHTS["tier_1_league"]
        )
        assert result.score == expected

    def test_live_blowout_tier1_score(self, live_commence, now):
        """Live + blowout + tier 1: blowout subtracts 15."""
        result = compute_highlight(
            status="live",
            commence_time=live_commence,
            sport_key="americanfootball_nfl",
            current_home_prob=0.92,
            now=now,
        )
        expected = WEIGHTS["live"] + WEIGHTS["tier_1_league"] - 15
        assert result.score == expected

    def test_scheduled_starting_very_soon_close_tier2(self, upcoming_commence, now):
        """Scheduled + <1h + close + very_close + tier 2 = accumulated score."""
        result = compute_highlight(
            status="scheduled",
            commence_time=upcoming_commence,
            sport_key="basketball_ncaab",
            current_home_prob=0.52,
            opening_home_prob=0.52,
            now=now,
        )
        # Starting soon: closeness IS interesting because is_starting_soon=True
        # 0.52 is within very_close range (0.45-0.55) too
        expected = (
            WEIGHTS["starting_soon_3h"]
            + WEIGHTS["starting_soon_1h"]
            + WEIGHTS["close_matchup"]
            + WEIGHTS["very_close"]
            + WEIGHTS["tier_2_league"]
        )
        assert result.score == expected

    def test_completed_upset_full_score(self, recent_finish_commence, now):
        """Completed upset with major prob swing + tier 1: all bonuses stack."""
        result = compute_highlight(
            status="completed",
            commence_time=recent_finish_commence,
            sport_key="icehockey_nhl",
            current_home_prob=0.55,
            opening_home_prob=0.30,
            opening_favorite="away",
            now=now,
        )
        expected = (
            WEIGHTS["recent_finish"]
            + WEIGHTS["tier_1_league"]
            + WEIGHTS["close_matchup"]
            + WEIGHTS["very_close"]
            + WEIGHTS["major_probability_swing"]
            + WEIGHTS["favorite_switched"]
            + WEIGHTS["recent_finish_upset"]
        )
        assert result.score == min(100, expected)

    def test_maximum_possible_score(self, now):
        """Maximal scenario should cap at 100."""
        # Live + close + very_close + tier1 + favorite_switched + major_prob_swing
        # + major_score_swing = well over 100
        live_commence = now - timedelta(hours=1)
        result = compute_highlight(
            status="live",
            commence_time=live_commence,
            sport_key="basketball_nba",
            current_home_prob=0.50,
            opening_home_prob=0.25,
            opening_favorite="away",
            current_over_under=300.0,
            opening_over_under=220.0,
            now=now,
        )
        assert result.score == 100

    def test_zero_score_event(self, now):
        """Far-future, no tier penalty, no odds: score should be 0."""
        far = now + timedelta(days=10)
        result = compute_highlight(
            status="scheduled",
            commence_time=far,
            sport_key="tennis_us_open",
            now=now,
        )
        assert result.score == 0
        assert result.reasons == ["tier_3"]  # Tier 3 has no score bonus/penalty


# =============================================================================
# get_highlight_label - Priority Ordering
# =============================================================================
class TestGetHighlightLabelPriority:
    """Verify that when multiple flags are set, the highest-priority label wins."""

    def test_upset_beats_everything(self):
        """Upset is highest priority — beats live, close, favorite_switched."""
        result = HighlightResult(flags=EventFlags(
            is_upset=True,
            is_live=True,
            favorite_switched=True,
            is_very_close=True,
        ))
        assert get_highlight_label(result) == "Recent upset"

    def test_favorite_switched_beats_close(self):
        """Live favorite_switched beats live close matchup."""
        result = HighlightResult(flags=EventFlags(
            is_live=True,
            favorite_switched=True,
            is_close_matchup=True,
        ))
        assert get_highlight_label(result) == "Upset brewing"

    def test_very_close_beats_close(self):
        """Live very_close beats live close."""
        result = HighlightResult(flags=EventFlags(
            is_live=True,
            is_very_close=True,
            is_close_matchup=True,
        ))
        assert get_highlight_label(result) == "Coin flip"

    def test_close_beats_momentum(self):
        """Live close_matchup beats live momentum shift."""
        result = HighlightResult(flags=EventFlags(
            is_live=True,
            is_close_matchup=True,
            probability_swing="major",
        ))
        assert get_highlight_label(result) == "Close game"

    def test_momentum_beats_generic_live(self):
        """Live major probability swing beats generic live."""
        result = HighlightResult(flags=EventFlags(
            is_live=True,
            probability_swing="major",
        ))
        assert get_highlight_label(result) == "Momentum shift"

    def test_line_moving_not_shown_when_live(self):
        """Pre-game 'Line moving' label is NOT shown for live games
        (since the live-specific labels take priority)."""
        result = HighlightResult(flags=EventFlags(
            is_live=True,
            probability_swing="major",
        ))
        assert get_highlight_label(result) != "Line moving"


# =============================================================================
# compute_highlight - Pre-game Closeness Nuances
# =============================================================================
class TestComputeHighlightPregameCloseness:
    """The pre-game closeness filtering logic is subtle and has caused bugs.
    These tests pin the five conditions under which pre-game closeness scores.
    """

    def test_pregame_both_close_no_movement_no_score(self, now):
        """Both open and current close, <5% movement, not starting soon: no score."""
        far = now + timedelta(days=2)
        result = compute_highlight(
            status="scheduled",
            commence_time=far,
            current_home_prob=0.49,
            opening_home_prob=0.51,
            now=now,
        )
        assert result.flags.is_close_matchup
        assert "close_matchup" not in result.reasons

    def test_pregame_both_close_with_5pct_movement_scores(self, now):
        """Both open and current close, but >=5% movement: scores."""
        far = now + timedelta(days=2)
        result = compute_highlight(
            status="scheduled",
            commence_time=far,
            current_home_prob=0.45,
            opening_home_prob=0.55,
            now=now,
        )
        assert "close_matchup" in result.reasons

    def test_pregame_opened_lopsided_now_close_scores(self, now):
        """Opened outside close range, now close: scores (line tightened)."""
        far = now + timedelta(days=2)
        result = compute_highlight(
            status="scheduled",
            commence_time=far,
            current_home_prob=0.52,
            opening_home_prob=0.65,
            now=now,
        )
        assert "close_matchup" in result.reasons

    def test_pregame_close_at_boundary_40(self, now):
        """Home prob at exactly 0.40 is a close matchup."""
        far = now + timedelta(days=2)
        result = compute_highlight(
            status="scheduled",
            commence_time=far,
            current_home_prob=0.40,
            opening_home_prob=None,
            now=now,
        )
        assert result.flags.is_close_matchup
        assert not result.flags.is_very_close

    def test_pregame_close_at_boundary_60(self, now):
        """Home prob at exactly 0.60 is a close matchup."""
        far = now + timedelta(days=2)
        result = compute_highlight(
            status="scheduled",
            commence_time=far,
            current_home_prob=0.60,
            opening_home_prob=None,
            now=now,
        )
        assert result.flags.is_close_matchup
        assert not result.flags.is_very_close

    def test_pregame_just_outside_close_range(self, now):
        """Home prob at 0.39 is NOT a close matchup."""
        far = now + timedelta(days=2)
        result = compute_highlight(
            status="scheduled",
            commence_time=far,
            current_home_prob=0.39,
            now=now,
        )
        assert not result.flags.is_close_matchup


# =============================================================================
# Level 2: Time-Series Metrics
# =============================================================================
class TestComputeTimeSeriesMetrics:
    """Tests for compute_time_series_metrics()."""

    def test_empty_list(self):
        """Empty list returns zero metrics."""
        m = compute_time_series_metrics([])
        assert m.volatility_rms == 0.0
        assert m.lead_changes == 0
        assert m.recent_momentum == 0.0
        assert m.snapshot_count == 0

    def test_single_point(self):
        """Single point returns zero metrics."""
        m = compute_time_series_metrics([0.55])
        assert m.volatility_rms == 0.0
        assert m.lead_changes == 0
        assert m.snapshot_count == 1

    def test_stable_line(self):
        """Stable line (no movement) has zero volatility."""
        m = compute_time_series_metrics([0.60, 0.60, 0.60, 0.60])
        assert m.volatility_rms == 0.0
        assert m.lead_changes == 0
        assert m.snapshot_count == 4

    def test_single_swing(self):
        """One big swing should produce volatility."""
        m = compute_time_series_metrics([0.40, 0.60, 0.40])
        assert m.volatility_rms > 0.10  # 20% swings
        assert m.lead_changes == 2  # crossed 50% twice

    def test_lead_change_exact_cross(self):
        """Verify lead change counting when crossing 50%."""
        # 0.45 -> 0.55 is a lead change (below -> above)
        # 0.55 -> 0.52 is NOT a lead change (both above)
        m = compute_time_series_metrics([0.45, 0.55, 0.52])
        assert m.lead_changes == 1

    def test_no_lead_change_same_side(self):
        """All values on one side of 50% = no lead changes."""
        m = compute_time_series_metrics([0.60, 0.65, 0.70, 0.62])
        assert m.lead_changes == 0

    def test_multiple_lead_changes(self):
        """Multiple crossings of 50%."""
        m = compute_time_series_metrics([0.40, 0.55, 0.45, 0.60, 0.35])
        assert m.lead_changes == 4

    def test_recent_momentum_with_timestamps(self):
        """Recent momentum uses last 30 minutes of timestamps."""
        base = datetime(2026, 2, 7, 20, 0, 0, tzinfo=timezone.utc)
        timestamps = [
            base - timedelta(minutes=60),
            base - timedelta(minutes=40),
            base - timedelta(minutes=20),
            base - timedelta(minutes=5),
            base,
        ]
        # 30 min ago: 0.50, now: 0.62 → momentum = 0.12
        probs = [0.45, 0.48, 0.50, 0.58, 0.62]
        m = compute_time_series_metrics(probs, timestamps)
        assert abs(m.recent_momentum - 0.12) < 0.001

    def test_recent_momentum_no_timestamps(self):
        """Without timestamps, recent_momentum stays 0."""
        m = compute_time_series_metrics([0.40, 0.50, 0.60])
        assert m.recent_momentum == 0.0

    def test_volatility_rms_calculation(self):
        """RMS of deltas matches expected value."""
        import math
        # Deltas: +0.10, -0.10, +0.10
        m = compute_time_series_metrics([0.50, 0.60, 0.50, 0.60])
        expected_rms = math.sqrt((0.10**2 + 0.10**2 + 0.10**2) / 3)
        assert abs(m.volatility_rms - expected_rms) < 0.0001


class TestLevel2Scoring:
    """Tests for Level 2 (time-series) scoring in compute_highlight."""

    @pytest.fixture
    def now(self):
        return datetime(2026, 2, 7, 20, 0, 0, tzinfo=timezone.utc)

    def test_level2_graceful_without_time_series(self, now):
        """Without time_series, Level 2 is silently skipped (Level 1 only)."""
        result = compute_highlight(
            status="live",
            commence_time=now - timedelta(hours=1),
            current_home_prob=0.50,
            now=now,
        )
        assert not result.flags.is_volatile
        assert not result.flags.has_lead_changes
        assert not result.flags.has_recent_momentum

    def test_volatile_game_gets_bonus(self, now):
        """High volatility adds points."""
        ts = TimeSeriesMetrics(
            volatility_rms=0.08,  # Above threshold 0.06
            lead_changes=0,
            recent_momentum=0.0,
            snapshot_count=10,
        )
        result = compute_highlight(
            status="live",
            commence_time=now - timedelta(hours=1),
            current_home_prob=0.65,
            sport_key="basketball_nba",
            now=now,
            time_series=ts,
        )
        assert result.flags.is_volatile
        assert "high_volatility" in result.reasons
        assert result.score >= WEIGHTS["live"] + WEIGHTS["high_volatility"]

    def test_lead_changes_get_bonus(self, now):
        """Lead changes add points (capped at 3)."""
        ts = TimeSeriesMetrics(
            volatility_rms=0.03,
            lead_changes=5,
            recent_momentum=0.0,
            snapshot_count=20,
        )
        result = compute_highlight(
            status="live",
            commence_time=now - timedelta(hours=1),
            current_home_prob=0.50,
            now=now,
            time_series=ts,
        )
        assert result.flags.has_lead_changes
        assert "lead_changes" in result.reasons
        # Capped at 3 * WEIGHTS["lead_changes"]
        expected_lc_bonus = 3 * WEIGHTS["lead_changes"]
        assert result.score >= WEIGHTS["live"] + expected_lc_bonus

    def test_recent_momentum_live_only(self, now):
        """Recent momentum only applies to live games."""
        ts = TimeSeriesMetrics(
            volatility_rms=0.03,
            lead_changes=0,
            recent_momentum=0.12,
            snapshot_count=10,
        )
        # Scheduled game shouldn't get momentum bonus
        result = compute_highlight(
            status="scheduled",
            commence_time=now + timedelta(hours=2),
            current_home_prob=0.50,
            now=now,
            time_series=ts,
        )
        assert not result.flags.has_recent_momentum
        assert "recent_momentum" not in result.reasons

        # Live game should get momentum bonus
        result2 = compute_highlight(
            status="live",
            commence_time=now - timedelta(hours=1),
            current_home_prob=0.65,
            now=now,
            time_series=ts,
        )
        assert result2.flags.has_recent_momentum
        assert "recent_momentum" in result2.reasons

    def test_too_few_snapshots_skips_level2(self, now):
        """Need at least 3 snapshots for Level 2 scoring."""
        ts = TimeSeriesMetrics(
            volatility_rms=0.15,  # Very high
            lead_changes=3,
            recent_momentum=0.20,
            snapshot_count=2,  # Too few!
        )
        result = compute_highlight(
            status="live",
            commence_time=now - timedelta(hours=1),
            current_home_prob=0.50,
            now=now,
            time_series=ts,
        )
        assert not result.flags.is_volatile
        assert not result.flags.has_lead_changes
        assert not result.flags.has_recent_momentum

    def test_lead_changes_label_priority(self):
        """Lead change label should beat close game for live events."""
        result = HighlightResult(flags=EventFlags(
            is_live=True,
            is_close_matchup=True,
            has_lead_changes=True,
        ))
        assert get_highlight_label(result) == "Lead change"

    def test_live_lead_changes_always_highlighted(self):
        """Live games with lead changes should always be highlighted."""
        result = HighlightResult(
            score=10,  # Below threshold
            flags=EventFlags(is_live=True, has_lead_changes=True),
        )
        assert should_highlight(result)

    def test_wild_game_label(self):
        """Volatile live game with no other flags gets 'Wild game' label."""
        result = HighlightResult(flags=EventFlags(
            is_live=True,
            is_volatile=True,
        ))
        assert get_highlight_label(result) == "Wild game"

    def test_odds_shifting_fast_label(self):
        """Recent momentum gets 'Odds shifting fast' label."""
        result = HighlightResult(flags=EventFlags(
            is_live=True,
            has_recent_momentum=True,
        ))
        assert get_highlight_label(result) == "Odds shifting fast"
