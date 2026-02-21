"""Tests for futures market highlight scoring."""

from datetime import datetime, timezone, timedelta
import pytest
from app.utils.futures_highlights import (
    compute_futures_highlight,
    should_highlight_futures,
    is_minor_league_market,
    MAJOR_MOVEMENT_THRESHOLD,
    MODERATE_MOVEMENT_THRESHOLD,
)


class TestComputeFuturesHighlight:
    """Tests for compute_futures_highlight()."""

    def test_empty_market_returns_low_score(self):
        """A market with no data gets a minimal score from its tier."""
        result = compute_futures_highlight()
        assert result.score >= 0
        assert result.score <= 10  # Only tier weight
        assert result.primary_reason is None

    def test_championship_tier_scores_higher(self):
        """Tier 1 (championship) markets score higher than tier 5."""
        tier1 = compute_futures_highlight(market_tier=1)
        tier5 = compute_futures_highlight(market_tier=5)
        assert tier1.score > tier5.score
        assert tier1.flags.is_high_tier is True
        assert tier5.flags.is_high_tier is False

    def test_major_league_bonus(self):
        """Major sport categories get a league bonus."""
        basketball = compute_futures_highlight(sport_category="basketball")
        other = compute_futures_highlight(sport_category="darts")
        assert basketball.score > other.score
        assert basketball.flags.league_tier == 1
        assert other.flags.league_tier == 3

    def test_major_movement_detected(self):
        """Large 24h probability changes are flagged."""
        outcomes = [
            {"name": "Team A", "probability": 0.30, "probability_change_24h": 0.08,
             "rank": 1, "rank_change_24h": 0, "opening_probability": 0.22},
        ]
        result = compute_futures_highlight(outcomes=outcomes)
        assert result.flags.has_major_movement is True
        assert "major_movement_24h" in result.reasons
        assert result.top_mover_name == "Team A"

    def test_moderate_movement_detected(self):
        """Moderate 24h probability changes are flagged."""
        outcomes = [
            {"name": "Team A", "probability": 0.25, "probability_change_24h": 0.03,
             "rank": 1, "rank_change_24h": 0, "opening_probability": 0.22},
        ]
        result = compute_futures_highlight(outcomes=outcomes)
        assert result.flags.has_moderate_movement is True
        assert "moderate_movement_24h" in result.reasons

    def test_leader_change_detected(self):
        """When the #1 rank has changed, it's detected."""
        outcomes = [
            {"name": "Team B", "probability": 0.30, "probability_change_24h": 0.10,
             "rank": 1, "rank_change_24h": 2, "opening_probability": 0.20},
            {"name": "Team A", "probability": 0.28, "probability_change_24h": -0.05,
             "rank": 2, "rank_change_24h": -1, "opening_probability": 0.33},
        ]
        result = compute_futures_highlight(outcomes=outcomes)
        assert result.flags.leader_changed is True
        assert result.primary_reason == "New favorite"

    def test_rank_shakeup_with_multiple_changes(self):
        """Multiple rank changes in top 5 = shakeup."""
        outcomes = [
            {"name": "A", "probability": 0.30, "probability_change_24h": 0.01,
             "rank": 1, "rank_change_24h": 2, "opening_probability": 0.29},
            {"name": "B", "probability": 0.25, "probability_change_24h": 0.01,
             "rank": 2, "rank_change_24h": -1, "opening_probability": 0.24},
            {"name": "C", "probability": 0.20, "probability_change_24h": 0.01,
             "rank": 3, "rank_change_24h": 1, "opening_probability": 0.19},
        ]
        result = compute_futures_highlight(outcomes=outcomes)
        assert result.flags.has_rank_shakeup is True

    def test_resolving_soon_7d(self):
        """Markets resolving within 7 days get a bonus."""
        now = datetime(2026, 2, 20, 12, 0, tzinfo=timezone.utc)
        resolution = now + timedelta(days=5)
        result = compute_futures_highlight(resolution_date=resolution, now=now)
        assert result.flags.is_resolving_soon is True
        assert "resolving_soon_7d" in result.reasons

    def test_resolving_soon_30d(self):
        """Markets resolving within 30 days get a smaller bonus."""
        now = datetime(2026, 2, 20, 12, 0, tzinfo=timezone.utc)
        resolution = now + timedelta(days=20)
        result = compute_futures_highlight(resolution_date=resolution, now=now)
        assert result.flags.is_resolving_soon is True
        assert "resolving_soon_30d" in result.reasons

    def test_multi_source_bonus(self):
        """Markets tracked by 2+ sources get a bonus."""
        single = compute_futures_highlight(source_count=1)
        multi = compute_futures_highlight(source_count=3)
        assert multi.score > single.score
        assert multi.flags.has_multi_source is True
        assert single.flags.has_multi_source is False

    def test_source_divergence(self):
        """Sources disagreeing by >5% is flagged."""
        result = compute_futures_highlight(
            source_count=2,
            max_source_divergence=0.08,
        )
        assert result.flags.has_source_divergence is True
        assert "source_divergence" in result.reasons

    def test_score_capped_at_100(self):
        """Score should never exceed 100."""
        # Create a scenario with everything interesting
        now = datetime(2026, 2, 20, 12, 0, tzinfo=timezone.utc)
        outcomes = [
            {"name": "A", "probability": 0.30, "probability_change_24h": 0.15,
             "rank": 1, "rank_change_24h": 3, "opening_probability": 0.15},
            {"name": "B", "probability": 0.25, "probability_change_24h": -0.10,
             "rank": 2, "rank_change_24h": -2, "opening_probability": 0.35},
            {"name": "C", "probability": 0.20, "probability_change_24h": 0.05,
             "rank": 3, "rank_change_24h": 1, "opening_probability": 0.15},
        ]
        result = compute_futures_highlight(
            market_tier=1,
            sport_category="basketball",
            resolution_date=now + timedelta(days=3),
            outcomes=outcomes,
            source_count=3,
            max_source_divergence=0.10,
            now=now,
        )
        assert result.score <= 100

    def test_combined_scoring(self):
        """Test a realistic championship market scenario."""
        now = datetime(2026, 2, 20, 12, 0, tzinfo=timezone.utc)
        outcomes = [
            {"name": "Celtics", "probability": 0.22, "probability_change_24h": -0.05,
             "rank": 1, "rank_change_24h": 0, "opening_probability": 0.27},
            {"name": "Thunder", "probability": 0.18, "probability_change_24h": 0.03,
             "rank": 2, "rank_change_24h": 1, "opening_probability": 0.15},
        ]
        result = compute_futures_highlight(
            market_tier=1,
            sport_category="basketball",
            outcomes=outcomes,
            source_count=2,
            now=now,
        )
        # Should score reasonably well: tier 1 + major league + major movement + multi-source
        assert result.score >= 50
        assert result.flags.has_major_movement is True
        assert result.flags.has_multi_source is True


class TestShouldHighlightFutures:
    """Tests for should_highlight_futures()."""

    def test_leader_change_always_highlighted(self):
        """Leader changes are always highlighted regardless of score."""
        result = compute_futures_highlight(
            outcomes=[
                {"name": "A", "probability": 0.30, "probability_change_24h": 0.01,
                 "rank": 1, "rank_change_24h": 1, "opening_probability": 0.29},
            ]
        )
        result.flags.leader_changed = True
        assert should_highlight_futures(result) is True

    def test_source_divergence_always_highlighted(self):
        """Source divergence is always highlighted."""
        result = compute_futures_highlight(
            source_count=2,
            max_source_divergence=0.08,
        )
        assert should_highlight_futures(result) is True

    def test_low_score_not_highlighted(self):
        """Low-scoring markets are not highlighted."""
        result = compute_futures_highlight()
        result.score = 10
        assert should_highlight_futures(result) is False


class TestMinorLeagueDetection:
    """Tests for minor league market detection and feed penalty."""

    def test_ahl_detected_as_minor(self):
        """AHL championship futures should be flagged as minor league."""
        assert is_minor_league_market("AHL Calder Cup Winner") is True

    def test_echl_detected_as_minor(self):
        assert is_minor_league_market("ECHL Kelly Cup Winner") is True

    def test_khl_detected_as_minor(self):
        assert is_minor_league_market("KHL Gagarin Cup") is True

    def test_ligue_2_detected_as_minor(self):
        assert is_minor_league_market("Ligue 2 Winner 2025-26") is True

    def test_serie_b_detected_as_minor(self):
        assert is_minor_league_market("Serie B Winner") is True

    def test_efl_championship_detected_as_minor(self):
        """English EFL Championship (tier 2) is minor for our purposes."""
        assert is_minor_league_market("EFL Championship Winner") is True

    def test_g_league_detected_as_minor(self):
        assert is_minor_league_market("NBA G-League Winner") is True

    def test_nhl_not_minor(self):
        """NHL Stanley Cup should NOT be detected as minor."""
        assert is_minor_league_market("NHL Stanley Cup Winner") is False

    def test_nba_championship_not_minor(self):
        assert is_minor_league_market("NBA Championship 2025-26") is False

    def test_nfl_mvp_not_minor(self):
        assert is_minor_league_market("NFL MVP 2025-26") is False

    def test_epl_not_minor(self):
        assert is_minor_league_market("English Premier League Winner") is False

    def test_minor_league_gets_score_penalty(self):
        """Minor league futures should score significantly lower."""
        nhl = compute_futures_highlight(
            market_tier=1, sport_category="hockey",
            market_name="NHL Stanley Cup Winner",
        )
        ahl = compute_futures_highlight(
            market_tier=1, sport_category="hockey",
            market_name="AHL Calder Cup Winner",
        )
        assert nhl.score > ahl.score
        assert "minor_league" in ahl.reasons
        assert "major_league" in nhl.reasons

    def test_minor_league_hockey_loses_major_bonus(self):
        """AHL gets penalty, not major_league bonus, even though hockey is tier 1."""
        result = compute_futures_highlight(
            market_tier=1, sport_category="hockey",
            market_name="AHL Calder Cup Winner",
        )
        assert "major_league" not in result.reasons
        assert "minor_league" in result.reasons
        # Score should be quite low: tier_1 weight (15) + minor penalty (-15) = 0
        assert result.score <= 5

    def test_minor_league_below_anonymous_threshold(self):
        """A minor league championship resolving soon should still score low."""
        now = datetime(2026, 2, 20, 12, 0, tzinfo=timezone.utc)
        result = compute_futures_highlight(
            market_tier=1,
            sport_category="hockey",
            resolution_date=now + timedelta(days=5),
            source_count=2,
            now=now,
            market_name="AHL Calder Cup Winner",
        )
        # tier 1 (15) + minor penalty (-15) + resolving_soon (15) + multi_source (10) = 25
        # This is borderline — but much lower than NHL championship (40+)
        assert result.score <= 30


class TestFeedReasons:
    """Tests for feed reason generation."""

    def test_event_upset_reason(self):
        from app.utils.feed_reasons import generate_event_reason

        reason = generate_event_reason(
            home_team="Lakers",
            away_team="Celtics",
            status="completed",
            highlight_reasons=["upset", "recent_finish"],
            home_score=95,
            away_score=110,
        )
        assert "Celtics" in reason
        assert "upset" in reason.lower() or "110" in reason

    def test_event_live_close_reason(self):
        from app.utils.feed_reasons import generate_event_reason

        reason = generate_event_reason(
            home_team="Lakers",
            away_team="Celtics",
            status="live",
            highlight_reasons=["live", "very_close"],
            home_probability=0.48,
            away_probability=0.52,
            home_score=88,
            away_score=90,
        )
        assert "Celtics" in reason or "Lakers" in reason
        assert "even" in reason.lower() or "48" in reason

    def test_futures_leader_change_reason(self):
        from app.utils.feed_reasons import generate_futures_reason

        reason = generate_futures_reason(
            market_name="NBA Championship 2025-26",
            highlight_reasons=["leader_change"],
            leader_name="Thunder",
            leader_probability=0.22,
        )
        assert "Thunder" in reason
        assert "favorite" in reason.lower() or "New" in reason

    def test_futures_major_movement_reason(self):
        from app.utils.feed_reasons import generate_futures_reason

        reason = generate_futures_reason(
            market_name="NFL MVP",
            highlight_reasons=["major_movement_24h"],
            top_mover_name="Patrick Mahomes",
            top_mover_change=0.08,
        )
        assert "Mahomes" in reason
        assert "8" in reason  # 8% movement

    def test_futures_fallback_reason(self):
        from app.utils.feed_reasons import generate_futures_reason

        reason = generate_futures_reason(
            market_name="NBA Championship",
            highlight_reasons=[],
            leader_name="Celtics",
            leader_probability=0.22,
        )
        assert "Celtics" in reason
        assert "22%" in reason
