"""Tests for futures outcome → team linking and market tier assignment."""

import pytest
from unittest.mock import patch

from app.utils.team_linking import (
    compute_market_tier,
    compute_relevance_score,
    _normalize_name,
    _names_match,
    match_outcome_to_team,
    get_sport_keys_for_category,
)


# =============================================================================
# Market Tier Assignment
# =============================================================================
class TestComputeMarketTier:
    """Test market tier classification (1=championship, 2=conference, 3=awards, 4=division, 5=other)."""

    # Tier 1: Championship
    def test_nba_championship(self):
        assert compute_market_tier("NBA Championship Winner") == 1

    def test_super_bowl_winner(self):
        assert compute_market_tier("Super Bowl LXI Winner") == 1

    def test_world_series(self):
        assert compute_market_tier("World Series Champion") == 1

    def test_stanley_cup(self):
        assert compute_market_tier("Stanley Cup Winner") == 1

    def test_championship_category_override(self):
        """Even generic name, if category is championship → tier 1."""
        assert compute_market_tier("Some Market", category="championship") == 1

    def test_generic_winner_market(self):
        assert compute_market_tier("Premier League Winner") == 1

    # Tier 2: Conference
    def test_eastern_conference(self):
        assert compute_market_tier("Eastern Conference Winner") == 2

    def test_western_conference(self):
        assert compute_market_tier("Western Conference Winner") == 2

    def test_afc_winner(self):
        assert compute_market_tier("AFC Championship Winner") == 2

    def test_nfc_winner(self):
        assert compute_market_tier("NFC Championship Winner") == 2

    def test_american_league_pennant(self):
        assert compute_market_tier("American League Pennant Winner") == 2

    def test_national_league(self):
        assert compute_market_tier("National League Winner") == 2

    # Tier 3: Awards / MVP
    def test_nba_mvp(self):
        assert compute_market_tier("NBA MVP Award") == 3

    def test_mvp_category(self):
        assert compute_market_tier("Some MVP Market", category="mvp") == 3

    def test_heisman(self):
        assert compute_market_tier("Heisman Trophy Winner") == 3

    def test_cy_young(self):
        assert compute_market_tier("AL Cy Young Award") == 3

    def test_hart_trophy(self):
        assert compute_market_tier("Hart Trophy Winner") == 3

    def test_defensive_player(self):
        assert compute_market_tier("Defensive Player of the Year") == 3

    def test_rookie_of_year(self):
        assert compute_market_tier("Rookie of the Year") == 3

    def test_ballon_dor(self):
        assert compute_market_tier("Ballon d'Or Winner") == 3

    def test_conn_smythe(self):
        assert compute_market_tier("Conn Smythe Trophy") == 3

    # Tier 4: Division
    def test_al_east(self):
        assert compute_market_tier("AL East Division Winner") == 4

    def test_nfc_south(self):
        assert compute_market_tier("NFC South Winner") == 4

    def test_atlantic_division(self):
        assert compute_market_tier("Atlantic Division Winner") == 4

    def test_pacific_division(self):
        assert compute_market_tier("Pacific Division Winner") == 4

    def test_central_division(self):
        assert compute_market_tier("Central Division Winner") == 4

    # Tier 5: Other / Props
    def test_unknown_market(self):
        assert compute_market_tier("Something Random") == 5

    def test_prop_bet(self):
        assert compute_market_tier("Total Regular Season Wins") == 5

    def test_empty_name(self):
        assert compute_market_tier("") == 5


# =============================================================================
# Name Normalization
# =============================================================================
class TestNormalizeName:
    def test_lowercase(self):
        assert _normalize_name("Boston Celtics") == "boston celtics"

    def test_strip_accents(self):
        assert _normalize_name("Montréal Canadiens") == "montreal canadiens"

    def test_unify_apostrophes(self):
        # Smart apostrophe → ASCII
        assert _normalize_name("Hawai\u2018i Warriors") == "hawai'i warriors"

    def test_strip_whitespace(self):
        assert _normalize_name("  Lakers  ") == "lakers"


# =============================================================================
# Names Match
# =============================================================================
class TestNamesMatch:
    def test_exact_match(self):
        assert _names_match("Boston Celtics", "Boston Celtics") is True

    def test_case_insensitive(self):
        assert _names_match("boston celtics", "Boston Celtics") is True

    def test_alt_name_exact(self):
        assert _names_match("Celtics", "Boston Celtics", ["Celtics", "BOS"]) is True

    def test_no_match(self):
        assert _names_match("Los Angeles Lakers", "Boston Celtics") is False

    def test_substring_long_enough(self):
        """Substring match works when both strings are >= 8 chars."""
        assert _names_match("Boston Celtics", "The Boston Celtics Team", ["Celtics"]) is True

    def test_short_name_no_substring(self):
        """Short names (< 8 chars) only match exactly, to prevent false positives."""
        assert _names_match("LA", "Los Angeles Lakers", ["LA Lakers"]) is False

    def test_short_exact_still_works(self):
        """Short names can still match via exact match."""
        assert _names_match("BOS", "Boston Celtics", ["BOS"]) is True

    def test_accent_normalization(self):
        assert _names_match("Montreal Canadiens", "Montréal Canadiens") is True

    def test_empty_candidate(self):
        assert _names_match("", "Boston Celtics") is False

    def test_none_alt_names(self):
        assert _names_match("Boston Celtics", "Boston Celtics", None) is True

    def test_yes_outcome_excluded(self):
        """'Yes' is a generic outcome name, should not match any team."""
        # match_outcome_to_team handles this, but _names_match alone would
        # not match "Yes" to any team name
        assert _names_match("Yes", "Boston Celtics") is False


# =============================================================================
# Match Outcome to Team
# =============================================================================
class TestMatchOutcomeToTeam:
    """Test the full matching pipeline."""

    TEAMS = [
        {"id": 1, "name": "Boston Celtics", "alternate_names": ["Celtics", "BOS"]},
        {"id": 2, "name": "Los Angeles Lakers", "alternate_names": ["Lakers", "LA Lakers"]},
        {"id": 3, "name": "Golden State Warriors", "alternate_names": ["Warriors", "GSW"]},
        {"id": 4, "name": "Los Angeles Clippers", "alternate_names": ["Clippers", "LAC"]},
    ]

    def test_exact_full_name(self):
        assert match_outcome_to_team("Boston Celtics", self.TEAMS) == 1

    def test_exact_alt_name(self):
        assert match_outcome_to_team("Celtics", self.TEAMS) == 1

    def test_case_insensitive_match(self):
        assert match_outcome_to_team("boston celtics", self.TEAMS) == 1

    def test_lakers_not_clippers(self):
        """Ensure 'Los Angeles Lakers' matches Lakers, not Clippers."""
        assert match_outcome_to_team("Los Angeles Lakers", self.TEAMS) == 2

    def test_clippers_match(self):
        assert match_outcome_to_team("Los Angeles Clippers", self.TEAMS) == 4

    def test_no_match(self):
        assert match_outcome_to_team("Miami Heat", self.TEAMS) is None

    def test_yes_outcome_returns_none(self):
        assert match_outcome_to_team("Yes", self.TEAMS) is None

    def test_no_outcome_returns_none(self):
        assert match_outcome_to_team("No", self.TEAMS) is None

    def test_over_outcome_returns_none(self):
        assert match_outcome_to_team("Over", self.TEAMS) is None

    def test_under_outcome_returns_none(self):
        assert match_outcome_to_team("Under", self.TEAMS) is None

    def test_empty_returns_none(self):
        assert match_outcome_to_team("", self.TEAMS) is None

    def test_empty_teams_list(self):
        assert match_outcome_to_team("Boston Celtics", []) is None

    def test_warriors_full_name(self):
        assert match_outcome_to_team("Golden State Warriors", self.TEAMS) == 3


# =============================================================================
# Sport Category → Sport Keys
# =============================================================================
class TestGetSportKeysForCategory:
    def test_basketball(self):
        keys = get_sport_keys_for_category("basketball")
        assert "basketball_nba" in keys
        assert "basketball_wnba" in keys

    def test_football(self):
        keys = get_sport_keys_for_category("football")
        assert "americanfootball_nfl" in keys

    def test_hockey(self):
        keys = get_sport_keys_for_category("hockey")
        assert "icehockey_nhl" in keys

    def test_unknown_returns_none(self):
        assert get_sport_keys_for_category("underwater_polo") is None

    def test_none_returns_none(self):
        assert get_sport_keys_for_category(None) is None

    def test_case_insensitive(self):
        keys = get_sport_keys_for_category("Basketball")
        assert keys is not None
        assert "basketball_nba" in keys


# =============================================================================
# LLM Player-Team Classification (mocked)
# =============================================================================
class TestLLMPlayerTeamClassification:
    @patch("app.services.llm._get_client")
    def test_classify_player_team(self, mock_get_client):
        """Test LLM returns a team name for a known player."""
        mock_client = mock_get_client.return_value
        mock_response = type("Response", (), {
            "choices": [type("Choice", (), {
                "message": type("Message", (), {"content": "Boston Celtics"})()
            })()]
        })()
        mock_client.chat.completions.create.return_value = mock_response

        from app.services.llm import classify_player_team
        result = classify_player_team("Jaylen Brown", "basketball", "NBA MVP 2025-26")
        assert result == "Boston Celtics"

    @patch("app.services.llm._get_client")
    def test_classify_unknown_player(self, mock_get_client):
        """Test LLM returns None for unknown name."""
        mock_client = mock_get_client.return_value
        mock_response = type("Response", (), {
            "choices": [type("Choice", (), {
                "message": type("Message", (), {"content": "UNKNOWN"})()
            })()]
        })()
        mock_client.chat.completions.create.return_value = mock_response

        from app.services.llm import classify_player_team
        result = classify_player_team("Random Person", "basketball")
        assert result is None

    @patch("app.services.llm._get_client")
    def test_classify_player_no_client(self, mock_get_client):
        """Test graceful fallback when LLM client is not available."""
        mock_get_client.return_value = None

        from app.services.llm import classify_player_team
        result = classify_player_team("Jaylen Brown", "basketball")
        assert result is None


# =============================================================================
# Edge Cases: Market Tier
# =============================================================================
class TestMarketTierEdgeCases:
    def test_division_before_winner(self):
        """'Division Winner' should be tier 4, not tier 1 (even though 'winner' matches)."""
        assert compute_market_tier("NFC East Division Winner") == 4

    def test_conference_before_championship(self):
        """'Conference Championship' should be tier 2, not tier 1."""
        assert compute_market_tier("Eastern Conference Champion") == 2

    def test_mvp_award_is_tier_3(self):
        """MVP markets are awards, not championships."""
        assert compute_market_tier("NFL MVP Award Winner") == 3

    def test_sixth_man_award(self):
        assert compute_market_tier("Sixth Man of the Year Award") == 3

    def test_most_improved(self):
        assert compute_market_tier("Most Improved Player") == 3

    def test_vezina_trophy(self):
        assert compute_market_tier("Vezina Trophy Winner") == 3

    def test_golden_boot(self):
        assert compute_market_tier("Golden Boot Award") == 3

    def test_nba_finals_is_championship(self):
        assert compute_market_tier("NBA Finals Winner") == 1


# =============================================================================
# Relevance Scoring
# =============================================================================
class TestComputeRelevanceScore:
    """Test the contextual relevance scoring formula."""

    def test_returns_score_and_reason(self):
        score, reason = compute_relevance_score(
            market_tier=1, probability=0.30,
            probability_change_24h=0.01, days_to_resolution=60,
        )
        assert isinstance(score, float)
        assert isinstance(reason, str)
        assert 0 <= score <= 100

    def test_championship_scores_higher_than_prop(self):
        """Tier 1 (championship) should score higher than tier 5 (prop), all else equal."""
        champ_score, _ = compute_relevance_score(
            market_tier=1, probability=0.25,
            probability_change_24h=0.0, days_to_resolution=90,
        )
        prop_score, _ = compute_relevance_score(
            market_tier=5, probability=0.25,
            probability_change_24h=0.0, days_to_resolution=90,
        )
        assert champ_score > prop_score

    def test_moving_market_scores_higher(self):
        """A market moving 3% today should score higher than one that's flat."""
        moving_score, moving_reason = compute_relevance_score(
            market_tier=1, probability=0.30,
            probability_change_24h=0.03, days_to_resolution=90,
        )
        flat_score, flat_reason = compute_relevance_score(
            market_tier=1, probability=0.30,
            probability_change_24h=0.0, days_to_resolution=90,
        )
        assert moving_score > flat_score
        assert moving_reason == "moving today"

    def test_near_threshold_bonus(self):
        """49% probability (near 50%) should score higher than 37%."""
        near_50, reason_50 = compute_relevance_score(
            market_tier=1, probability=0.49,
            probability_change_24h=0.0, days_to_resolution=90,
        )
        at_37, _ = compute_relevance_score(
            market_tier=1, probability=0.37,
            probability_change_24h=0.0, days_to_resolution=90,
        )
        assert near_50 > at_37

    def test_very_low_probability_scores_low(self):
        """< 1% probability should contribute nothing to prob score."""
        low_score, _ = compute_relevance_score(
            market_tier=1, probability=0.005,
            probability_change_24h=0.0, days_to_resolution=90,
        )
        moderate_score, _ = compute_relevance_score(
            market_tier=1, probability=0.25,
            probability_change_24h=0.0, days_to_resolution=90,
        )
        assert moderate_score > low_score

    def test_urgency_resolves_soon(self):
        """Market resolving in 7 days should score higher than one in 180 days."""
        soon_score, soon_reason = compute_relevance_score(
            market_tier=3, probability=0.15,
            probability_change_24h=0.0, days_to_resolution=7,
        )
        far_score, _ = compute_relevance_score(
            market_tier=3, probability=0.15,
            probability_change_24h=0.0, days_to_resolution=180,
        )
        assert soon_score > far_score
        assert soon_reason == "resolves soon"

    def test_reason_moving_today(self):
        _, reason = compute_relevance_score(
            market_tier=1, probability=0.30,
            probability_change_24h=0.025, days_to_resolution=90,
        )
        assert reason == "moving today"

    def test_reason_shifting(self):
        _, reason = compute_relevance_score(
            market_tier=1, probability=0.30,
            probability_change_24h=0.008, days_to_resolution=90,
        )
        assert reason == "shifting"

    def test_reason_championship_context(self):
        """Flat championship market should say 'championship context'."""
        _, reason = compute_relevance_score(
            market_tier=1, probability=0.30,
            probability_change_24h=0.0, days_to_resolution=90,
        )
        assert reason == "championship context"

    def test_reason_award_watch(self):
        _, reason = compute_relevance_score(
            market_tier=3, probability=0.15,
            probability_change_24h=0.0, days_to_resolution=90,
        )
        assert reason == "award watch"

    def test_none_values_handled(self):
        """All None values should not crash."""
        score, reason = compute_relevance_score(
            market_tier=None, probability=None,
            probability_change_24h=None, days_to_resolution=None,
        )
        assert score >= 0
        assert isinstance(reason, str)

    def test_high_liquidity_bonus(self):
        """More bookmakers should give slightly higher score."""
        high_liq, _ = compute_relevance_score(
            market_tier=1, probability=0.30,
            probability_change_24h=0.0, days_to_resolution=90,
            bookmaker_count=10,
        )
        low_liq, _ = compute_relevance_score(
            market_tier=1, probability=0.30,
            probability_change_24h=0.0, days_to_resolution=90,
            bookmaker_count=1,
        )
        assert high_liq > low_liq

    def test_negative_change_treated_as_movement(self):
        """Negative probability change should still count as movement."""
        score, reason = compute_relevance_score(
            market_tier=1, probability=0.30,
            probability_change_24h=-0.03, days_to_resolution=90,
        )
        assert reason == "moving today"


# =============================================================================
# Related Futures Name Matching Helpers
# =============================================================================
class TestRelatedFuturesHelpers:
    """Test the name matching helpers used by the related-futures endpoint."""

    def test_escape_like_plain_text(self):
        from app.routes.events import _escape_like
        assert _escape_like("Boston Celtics") == "Boston Celtics"

    def test_escape_like_underscore(self):
        from app.routes.events import _escape_like
        assert _escape_like("Team_A") == "Team\\_A"

    def test_escape_like_percent(self):
        from app.routes.events import _escape_like
        assert _escape_like("100%") == "100\\%"

    def test_team_name_patterns_basic(self):
        from app.routes.events import _team_name_patterns
        patterns = _team_name_patterns("Boston Celtics")
        assert "Boston Celtics" in patterns
        assert "Celtics" in patterns
        assert len(patterns) == 2

    def test_team_name_patterns_short_last_word(self):
        """Short last words (< 4 chars) should be excluded."""
        from app.routes.events import _team_name_patterns
        patterns = _team_name_patterns("Phoenix Sun")
        # "Sun" is only 3 chars, should not be included as separate pattern
        assert "Phoenix Sun" in patterns
        assert len(patterns) == 1

    def test_team_name_patterns_single_word(self):
        from app.routes.events import _team_name_patterns
        patterns = _team_name_patterns("Arsenal")
        assert "Arsenal" in patterns
        assert len(patterns) == 1

    def test_team_name_patterns_empty(self):
        from app.routes.events import _team_name_patterns
        assert _team_name_patterns("") == []
        assert _team_name_patterns(None) == []

    def test_team_name_patterns_three_word_name(self):
        from app.routes.events import _team_name_patterns
        patterns = _team_name_patterns("New England Patriots")
        assert "New England Patriots" in patterns
        assert "Patriots" in patterns
        assert len(patterns) == 2

    def test_sport_prefix_to_llm_category(self):
        from app.routes.events import _SPORT_PREFIX_TO_LLM_CATEGORY
        assert _SPORT_PREFIX_TO_LLM_CATEGORY["americanfootball"] == "football"
        assert _SPORT_PREFIX_TO_LLM_CATEGORY["icehockey"] == "hockey"
        assert _SPORT_PREFIX_TO_LLM_CATEGORY["basketball"] == "basketball"
        assert _SPORT_PREFIX_TO_LLM_CATEGORY["baseball"] == "baseball"

    def test_team_name_patterns_la_clippers(self):
        """Verify multi-word city names don't produce short patterns."""
        from app.routes.events import _team_name_patterns
        patterns = _team_name_patterns("LA Clippers")
        assert "LA Clippers" in patterns
        assert "Clippers" in patterns
        # "LA" should NOT be a separate pattern (< 4 chars)
        assert len(patterns) == 2
