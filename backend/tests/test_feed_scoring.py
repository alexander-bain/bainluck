"""Tests for utils/feed_scoring.py — the extracted feed ranking logic.

These tests verify scoring behavior that was previously untestable
because it was embedded inside a 466-line async function with DB access.
"""

from datetime import datetime, timezone

from app.utils.feed_scoring import compute_base_score, TAG_BOOSTS


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
