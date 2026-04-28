"""Tests for utils/feed_scoring.py — the extracted feed ranking logic.

These tests verify scoring behavior that was previously untestable
because it was embedded inside a 466-line async function with DB access.
"""

from datetime import datetime, timezone

from app.utils.feed_scoring import (
    compute_base_score,
    compute_content_richness_penalty,
    TAG_BOOSTS,
)


class TestComputeBaseScore:
    """Test the base score computation (no personalization)."""

    def test_returns_highlight_score_with_no_boosts(self):
        score, reasons = compute_base_score(
            highlight_score=50,
            highlight_reasons=["close_game"],
            home_champ_prob=0, away_champ_prob=0,
            sport_key=None, now=datetime.now(timezone.utc),
            event_tags=[], event_status="live", raw_ei=None,
        )
        assert score == 50
        assert "close_game" in reasons

    def test_championship_contender_boost(self):
        score, reasons = compute_base_score(
            highlight_score=50,
            highlight_reasons=[],
            home_champ_prob=0.20, away_champ_prob=0.01,
            sport_key=None, now=datetime.now(timezone.utc),
            event_tags=[], event_status="live", raw_ei=None,
        )
        assert score == 50 + 15
        assert "high_stakes" in reasons

    def test_fringe_contender_boost(self):
        score, _ = compute_base_score(
            highlight_score=50,
            highlight_reasons=[],
            home_champ_prob=0.07, away_champ_prob=0.02,
            sport_key=None, now=datetime.now(timezone.utc),
            event_tags=[], event_status="live", raw_ei=None,
        )
        assert score == 50 + 8

    def test_longshot_contender_boost(self):
        score, _ = compute_base_score(
            highlight_score=50,
            highlight_reasons=[],
            home_champ_prob=0.02, away_champ_prob=0.005,
            sport_key=None, now=datetime.now(timezone.utc),
            event_tags=[], event_status="live", raw_ei=None,
        )
        assert score == 50 + 3

    def test_no_contender_boost_for_zero_prob(self):
        score, _ = compute_base_score(
            highlight_score=50,
            highlight_reasons=[],
            home_champ_prob=0, away_champ_prob=0,
            sport_key=None, now=datetime.now(timezone.utc),
            event_tags=[], event_status="live", raw_ei=None,
        )
        assert score == 50

    def test_elimination_tag_boost(self):
        score, reasons = compute_base_score(
            highlight_score=50,
            highlight_reasons=[],
            home_champ_prob=0, away_champ_prob=0,
            sport_key=None, now=datetime.now(timezone.utc),
            event_tags=["stakes:elimination"],
            event_status="live", raw_ei=None,
        )
        assert score == 50 + 12
        assert "llm_tags" in reasons

    def test_multiple_tag_boosts_stack(self):
        score, _ = compute_base_score(
            highlight_score=50,
            highlight_reasons=[],
            home_champ_prob=0, away_champ_prob=0,
            sport_key=None, now=datetime.now(timezone.utc),
            event_tags=["stakes:elimination", "narrative:rivalry", "audience:national_interest"],
            event_status="live", raw_ei=None,
        )
        expected = 50 + 12 + 8 + 5
        assert score == expected

    def test_high_ei_boost_for_completed(self):
        score, reasons = compute_base_score(
            highlight_score=40,
            highlight_reasons=[],
            home_champ_prob=0, away_champ_prob=0,
            sport_key=None, now=datetime.now(timezone.utc),
            event_tags=[], event_status="completed", raw_ei=0.85,
        )
        assert score == 40 + 25
        assert "high_ei" in reasons

    def test_good_ei_boost(self):
        score, reasons = compute_base_score(
            highlight_score=40,
            highlight_reasons=[],
            home_champ_prob=0, away_champ_prob=0,
            sport_key=None, now=datetime.now(timezone.utc),
            event_tags=[], event_status="completed", raw_ei=0.65,
        )
        assert score == 40 + 15
        assert "good_ei" in reasons

    def test_no_ei_boost_for_live(self):
        score, _ = compute_base_score(
            highlight_score=40,
            highlight_reasons=[],
            home_champ_prob=0, away_champ_prob=0,
            sport_key=None, now=datetime.now(timezone.utc),
            event_tags=[], event_status="live", raw_ei=0.85,
        )
        assert score == 40

    def test_all_boosts_combine(self):
        score, reasons = compute_base_score(
            highlight_score=60,
            highlight_reasons=["upset"],
            home_champ_prob=0.25, away_champ_prob=0.03,
            sport_key=None, now=datetime.now(timezone.utc),
            event_tags=["stakes:must_win", "narrative:rivalry"],
            event_status="completed", raw_ei=0.90,
        )
        expected = 60 + 15 + 8 + 8 + 25
        assert score == expected
        assert "high_stakes" in reasons
        assert "llm_tags" in reasons
        assert "high_ei" in reasons

    def test_season_multiplier_applied_when_provided(self):
        score, _ = compute_base_score(
            highlight_score=50,
            highlight_reasons=[],
            home_champ_prob=0, away_champ_prob=0,
            sport_key="basketball_nba",
            now=datetime.now(timezone.utc),
            event_tags=[], event_status="live", raw_ei=None,
            get_season_multiplier_fn=lambda sk, n: 1.5,
            get_league_tier_fn=lambda sk: 1,
        )
        assert score == 50 + 10  # 20 * (1.5 - 1.0) = 10


class TestContentRichnessPenalty:
    """Test the content richness penalty for live events with thin/flat data."""

    # --- Signal A: Probability stasis (EI) ---

    def test_flat_ei_live_penalty(self):
        adj, reasons = compute_content_richness_penalty(
            event_status="live", raw_ei=0.0,
            home_score=3, away_score=2, source_count=3,
            game_progress=0.5, sport_key="basketball_nba",
        )
        assert adj == -10
        assert "flat_line" in reasons

    def test_flat_ei_none_penalty(self):
        adj, reasons = compute_content_richness_penalty(
            event_status="live", raw_ei=None,
            home_score=3, away_score=2, source_count=3,
            game_progress=0.5, sport_key="basketball_nba",
        )
        assert adj == -10
        assert "flat_line" in reasons

    def test_low_movement_penalty(self):
        adj, reasons = compute_content_richness_penalty(
            event_status="live", raw_ei=0.03,
            home_score=3, away_score=2, source_count=3,
            game_progress=0.5, sport_key="basketball_nba",
        )
        assert adj == -5
        assert "low_movement" in reasons

    def test_normal_ei_no_penalty(self):
        adj, reasons = compute_content_richness_penalty(
            event_status="live", raw_ei=0.10,
            home_score=3, away_score=2, source_count=3,
            game_progress=0.5, sport_key="basketball_nba",
        )
        assert adj == 0
        assert reasons == []

    def test_flat_ei_early_game_no_penalty(self):
        """EI is naturally 0 at game start — don't penalize until 25% through."""
        adj, _ = compute_content_richness_penalty(
            event_status="live", raw_ei=0.0,
            home_score=0, away_score=0, source_count=3,
            game_progress=0.15, sport_key="basketball_nba",
        )
        assert adj == 0

    def test_not_live_no_penalty(self):
        adj, _ = compute_content_richness_penalty(
            event_status="scheduled", raw_ei=None,
            home_score=None, away_score=None, source_count=0,
            game_progress=None, sport_key=None,
        )
        assert adj == 0

    def test_completed_no_penalty(self):
        adj, _ = compute_content_richness_penalty(
            event_status="completed", raw_ei=0.0,
            home_score=0, away_score=0, source_count=1,
            game_progress=1.0, sport_key="baseball_mlb",
        )
        assert adj == 0

    # --- Signal B: Score stasis ---

    def test_scoreless_deep_in_game(self):
        adj, reasons = compute_content_richness_penalty(
            event_status="live", raw_ei=0.10,
            home_score=0, away_score=0, source_count=3,
            game_progress=0.65, sport_key="baseball_mlb",
        )
        assert adj == -8
        assert "scoreless_stalemate" in reasons

    def test_scoreless_early_game_no_penalty(self):
        adj, _ = compute_content_richness_penalty(
            event_status="live", raw_ei=0.10,
            home_score=0, away_score=0, source_count=3,
            game_progress=0.3, sport_key="baseball_mlb",
        )
        assert adj == 0

    def test_scoreless_soccer_exempt(self):
        adj, reasons = compute_content_richness_penalty(
            event_status="live", raw_ei=0.10,
            home_score=0, away_score=0, source_count=3,
            game_progress=0.75, sport_key="soccer_epl",
        )
        assert adj == 0
        assert "scoreless_stalemate" not in reasons

    def test_scoreless_hockey_exempt(self):
        adj, reasons = compute_content_richness_penalty(
            event_status="live", raw_ei=0.10,
            home_score=0, away_score=0, source_count=3,
            game_progress=0.75, sport_key="icehockey_nhl",
        )
        assert adj == 0
        assert "scoreless_stalemate" not in reasons

    def test_has_scores_no_stalemate_penalty(self):
        adj, _ = compute_content_richness_penalty(
            event_status="live", raw_ei=0.10,
            home_score=3, away_score=2, source_count=3,
            game_progress=0.7, sport_key="baseball_mlb",
        )
        assert adj == 0

    # --- Signal C: Data thinness ---

    def test_zero_sources_penalty(self):
        adj, reasons = compute_content_richness_penalty(
            event_status="live", raw_ei=0.10,
            home_score=3, away_score=2, source_count=0,
            game_progress=0.5, sport_key="basketball_nba",
        )
        assert adj == -8
        assert "no_sources" in reasons

    def test_single_source_penalty(self):
        adj, reasons = compute_content_richness_penalty(
            event_status="live", raw_ei=0.10,
            home_score=3, away_score=2, source_count=1,
            game_progress=0.5, sport_key="basketball_nba",
        )
        assert adj == -5
        assert "thin_data" in reasons

    def test_two_sources_no_penalty(self):
        adj, _ = compute_content_richness_penalty(
            event_status="live", raw_ei=0.10,
            home_score=3, away_score=2, source_count=2,
            game_progress=0.5, sport_key="basketball_nba",
        )
        assert adj == 0

    def test_rich_data_bonus(self):
        adj, reasons = compute_content_richness_penalty(
            event_status="live", raw_ei=0.10,
            home_score=3, away_score=2, source_count=5,
            game_progress=0.5, sport_key="basketball_nba",
        )
        assert adj == 3
        assert "rich_data" in reasons

    # --- Combined / cap ---

    def test_combined_penalty_capped_at_minus_20(self):
        """All three penalties active: -10 (flat) + -8 (scoreless) + -8 (no sources) = -26 → capped at -20."""
        adj, reasons = compute_content_richness_penalty(
            event_status="live", raw_ei=0.0,
            home_score=0, away_score=0, source_count=0,
            game_progress=0.7, sport_key="baseball_mlb",
        )
        assert adj == -20
        assert "flat_line" in reasons
        assert "scoreless_stalemate" in reasons
        assert "no_sources" in reasons

    def test_combined_stacks_with_base_score(self):
        """Full pipeline: richness penalty reduces the base score."""
        score, reasons = compute_base_score(
            highlight_score=60,
            highlight_reasons=["close_game"],
            home_champ_prob=0, away_champ_prob=0,
            sport_key="baseball_mlb",
            now=datetime.now(timezone.utc),
            event_tags=[], event_status="live", raw_ei=0.0,
            home_score=0, away_score=0,
            source_count=0, game_progress=0.7,
        )
        # -20 cap from richness penalty
        assert score == 60 - 20
        assert "flat_line" in reasons

    def test_rich_data_bonus_not_included_in_penalty_cap(self):
        """The +3 bonus should apply even when penalties are at the -20 cap."""
        # This scenario: flat (-10) + scoreless (-8) + rich data (+3)
        # Penalty part: -10 + -8 = -18, within cap. Bonus: +3. Total: -15.
        adj, reasons = compute_content_richness_penalty(
            event_status="live", raw_ei=0.0,
            home_score=0, away_score=0, source_count=5,
            game_progress=0.7, sport_key="baseball_mlb",
        )
        assert adj == -18 + 3  # -15
        assert "flat_line" in reasons
        assert "scoreless_stalemate" in reasons
        assert "rich_data" in reasons


class TestTagBoostsCompleteness:
    """Verify the TAG_BOOSTS dict is consistent."""

    def test_all_tags_have_positive_values(self):
        for tag, value in TAG_BOOSTS.items():
            assert value > 0, f"Tag {tag} has non-positive value {value}"

    def test_stakes_tags_exist(self):
        stakes = [t for t in TAG_BOOSTS if t.startswith("stakes:")]
        assert len(stakes) >= 5

    def test_narrative_tags_exist(self):
        narrative = [t for t in TAG_BOOSTS if t.startswith("narrative:")]
        assert len(narrative) >= 5
