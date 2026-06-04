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
from app.utils.feed_market_quality import (
    apply_quality_score,
    classify_market_quality,
    diversify_discover_first_page,
    quality_score_adjustment,
)


def _market_item(
    item_id: int,
    *,
    name: str,
    category: str,
    score: int = 100,
    item_type: str = "futures",
    story_key: str | None = None,
) -> dict:
    return {
        "type": item_type,
        "score": score,
        "data": {
            "id": item_id,
            "name": name,
            "llm_sport_category": category,
        },
        "_quality_story_key": story_key,
    }


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


class TestDiscoverMarketQuality:
    """Test Discover futures quality adjustments used after base scoring."""

    def test_compelling_non_sports_market_gets_boost_and_can_reach_100(self):
        quality = classify_market_quality(
            "Will OpenAI announce GPT-5 before the end of June?",
            sport_category="tech",
        )

        assert quality.quality_class == "compelling"
        assert "compelling_topic" in quality.reasons
        assert quality_score_adjustment(quality) == 12
        assert apply_quality_score(92, quality) == 95

    def test_health_outbreak_gets_extra_compelling_boost(self):
        quality = classify_market_quality(
            "Will there be a measles outbreak in the United States this year?",
            sport_category="health",
        )

        assert quality.quality_class == "compelling"
        assert "health_outbreak" in quality.reasons
        assert quality_score_adjustment(quality) == 24

    def test_low_signal_sports_are_suppressed_below_normal_feed_cards(self):
        quality = classify_market_quality(
            "Will Lin Yun-Ju win the WTT table tennis final?",
            sport_category="table_tennis",
        )

        assert quality.quality_class == "low_quality"
        assert "low_signal_sport" in quality.reasons
        assert quality_score_adjustment(quality) == -35
        assert apply_quality_score(99, quality) == 64

    def test_social_filler_market_is_hard_suppressed(self):
        quality = classify_market_quality(
            'Will Donald Trump say "tariff" on Truth Social this week?',
            sport_category="politics",
        )

        assert quality.quality_class == "suppress"
        assert "social_filler" in quality.reasons
        assert apply_quality_score(100, quality) == 0

    def test_quality_score_boundaries_for_normal_and_low_quality_markets(self):
        normal_salient = classify_market_quality(
            "Will Nvidia launch a new chip before September?",
            sport_category="tech",
        )
        normal_generic = classify_market_quality(
            "Will a new app reach number one by Friday?",
            sport_category="tech",
        )
        low_quality = classify_market_quality(
            "Will WTI oil close above $75 on Friday?",
            sport_category="economics",
        )

        assert normal_salient.quality_class == "normal"
        assert apply_quality_score(99, normal_salient) == 88
        assert normal_generic.quality_class == "normal"
        assert apply_quality_score(99, normal_generic) == 82
        assert low_quality.quality_class == "low_quality"
        assert apply_quality_score(120, low_quality) == 65

    def test_sports_personnel_story_gets_sports_drama_boost(self):
        quality = classify_market_quality(
            "Will Steve Kerr be fired as Warriors coach before next season?",
            sport_category="basketball",
        )

        assert quality.quality_class == "compelling"
        assert "sports_personnel_story" in quality.reasons
        assert quality_score_adjustment(quality) == 22


class TestDiscoverFirstPageDiversity:
    """Test first-page category diversity for the Discover feed."""

    def test_first_page_caps_repeated_sports_items_when_other_categories_exist(self):
        sports = [
            _market_item(
                idx,
                item_type="event",
                name=f"NBA playoff game {idx}",
                category="basketball",
                score=100 - idx,
            )
            for idx in range(1, 8)
        ]
        politics = [
            _market_item(
                100 + idx,
                name=f"Will candidate {idx} win the presidential election?",
                category="politics",
                score=90 - idx,
            )
            for idx in range(1, 5)
        ]
        alternatives = [
            _market_item(
                201,
                name="Will OpenAI announce GPT-5?",
                category="tech",
                score=89,
            ),
            _market_item(
                202,
                name="Will the Fed cut rates?",
                category="economics",
                score=88,
            ),
            _market_item(
                203,
                name="Will Taylor Swift announce a new album?",
                category="entertainment",
                score=87,
            ),
        ]

        diversified = diversify_discover_first_page(
            sports + politics + alternatives,
            first_page_size=10,
        )
        first_page = diversified[:10]
        sports_count = sum(1 for item in first_page if item["type"] == "event")

        assert sports_count == 3
        assert len(first_page) == 10

    def test_first_page_keeps_non_political_cards_in_top_ten(self):
        political = [
            _market_item(
                idx,
                name=f"Will candidate {idx} win the presidential election?",
                category="politics",
                score=100,
            )
            for idx in range(1, 11)
        ]
        non_political = [
            _market_item(
                101,
                name="Will OpenAI announce GPT-5?",
                category="tech",
                score=95,
            ),
            _market_item(
                102,
                name="Will Nvidia beat earnings?",
                category="tech",
                score=94,
            ),
            _market_item(
                103,
                name="Will the Fed cut rates?",
                category="economics",
                score=93,
            ),
            _market_item(
                104,
                name="Will Taylor Swift announce a new album?",
                category="entertainment",
                score=92,
            ),
        ]

        diversified = diversify_discover_first_page(
            political + non_political,
            first_page_size=10,
        )
        top_ten = diversified[:10]
        non_political_count = sum(
            1
            for item in top_ten
            if item["data"]["llm_sport_category"] != "politics"
        )

        assert non_political_count >= 4

    def test_first_page_story_cap_limits_near_duplicate_markets(self):
        duplicate_story = [
            _market_item(
                idx,
                name=f"Will there be a ceasefire in Israel by month {idx}?",
                category="geopolitics",
                score=100 - idx,
                story_key="story:middle_east_conflict",
            )
            for idx in range(1, 7)
        ]
        alternatives = [
            _market_item(
                101,
                name="Will OpenAI announce GPT-5?",
                category="tech",
                score=90,
            ),
            _market_item(
                102,
                name="Will the Fed cut rates?",
                category="economics",
                score=89,
            ),
            _market_item(
                103,
                name="Will Taylor Swift announce a new album?",
                category="entertainment",
                score=88,
            ),
        ]

        diversified = diversify_discover_first_page(
            duplicate_story + alternatives,
            first_page_size=5,
        )
        first_page = diversified[:5]
        story_count = sum(
            1
            for item in first_page
            if item.get("_quality_story_key") == "story:middle_east_conflict"
        )

        assert story_count == 2


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
