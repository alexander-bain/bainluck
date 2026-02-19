"""Tests for the LLM service (classify, gender, level, importance, league)."""

import pytest
from unittest.mock import patch, MagicMock

from app.services.llm import (
    classify,
    classify_futures_market,
    classify_gender,
    classify_level,
    classify_league,
    classify_importance,
    classify_open_ended,
    generate_tags_via_llm,
    _normalize_open_ended_category,
    SPORT_CATEGORIES,
    GENDER_CATEGORIES,
    LEVEL_CATEGORIES,
    IMPORTANCE_CATEGORIES,
)


@pytest.fixture
def mock_openai_response():
    """Factory for creating mock OpenAI API responses."""
    def _make(content):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = content
        return mock_response
    return _make


# =============================================================================
# classify - Core Classification
# =============================================================================
class TestClassify:
    @patch("app.services.llm._get_client")
    def test_exact_match(self, mock_get_client, mock_openai_response):
        client = MagicMock()
        client.chat.completions.create.return_value = mock_openai_response("basketball")
        mock_get_client.return_value = client
        result = classify("NBA Finals", ["football", "basketball", "baseball"])
        assert result == "basketball"

    @patch("app.services.llm._get_client")
    def test_case_insensitive_match(self, mock_get_client, mock_openai_response):
        client = MagicMock()
        client.chat.completions.create.return_value = mock_openai_response("Basketball")
        mock_get_client.return_value = client
        result = classify("NBA Finals", ["football", "basketball", "baseball"])
        assert result == "basketball"

    @patch("app.services.llm._get_client")
    def test_partial_match(self, mock_get_client, mock_openai_response):
        client = MagicMock()
        client.chat.completions.create.return_value = mock_openai_response("I think it's basketball")
        mock_get_client.return_value = client
        result = classify("NBA Finals", ["football", "basketball", "baseball"])
        assert result == "basketball"

    @patch("app.services.llm._get_client")
    def test_common_mapping_nfl(self, mock_get_client, mock_openai_response):
        client = MagicMock()
        client.chat.completions.create.return_value = mock_openai_response("nfl")
        mock_get_client.return_value = client
        result = classify("Super Bowl", SPORT_CATEGORIES)
        assert result == "football"

    @patch("app.services.llm._get_client")
    def test_common_mapping_american_football(self, mock_get_client, mock_openai_response):
        client = MagicMock()
        client.chat.completions.create.return_value = mock_openai_response("american football")
        mock_get_client.return_value = client
        result = classify("Super Bowl", SPORT_CATEGORIES)
        assert result == "football"

    @patch("app.services.llm._get_client")
    def test_common_mapping_nba(self, mock_get_client, mock_openai_response):
        client = MagicMock()
        client.chat.completions.create.return_value = mock_openai_response("nba")
        mock_get_client.return_value = client
        result = classify("Finals MVP", SPORT_CATEGORIES)
        assert result == "basketball"

    @patch("app.services.llm._get_client")
    def test_common_mapping_ufc(self, mock_get_client, mock_openai_response):
        client = MagicMock()
        client.chat.completions.create.return_value = mock_openai_response("ufc")
        mock_get_client.return_value = client
        result = classify("Heavyweight Champion", SPORT_CATEGORIES)
        assert result == "mma"

    @patch("app.services.llm._get_client")
    def test_common_mapping_horse_racing(self, mock_get_client, mock_openai_response):
        client = MagicMock()
        client.chat.completions.create.return_value = mock_openai_response("horse racing")
        mock_get_client.return_value = client
        result = classify("Kentucky Derby", SPORT_CATEGORIES)
        assert result == "horse_racing"

    @patch("app.services.llm._get_client")
    def test_common_mapping_motorsport(self, mock_get_client, mock_openai_response):
        client = MagicMock()
        client.chat.completions.create.return_value = mock_openai_response("motorsport")
        mock_get_client.return_value = client
        result = classify("F1 Championship", SPORT_CATEGORIES)
        assert result == "motorsports"

    @patch("app.services.llm._get_client")
    def test_no_match_returns_fallback(self, mock_get_client, mock_openai_response):
        client = MagicMock()
        client.chat.completions.create.return_value = mock_openai_response("definitely_not_a_category")
        mock_get_client.return_value = client
        result = classify("unknown", ["football", "basketball"], fallback="other")
        assert result == "other"

    @patch("app.services.llm._get_client")
    def test_api_error_returns_fallback(self, mock_get_client):
        client = MagicMock()
        client.chat.completions.create.side_effect = Exception("API Error")
        mock_get_client.return_value = client
        result = classify("NBA", ["football", "basketball"], fallback="other")
        assert result == "other"

    @patch("app.services.llm._get_client")
    def test_client_unavailable_returns_fallback(self, mock_get_client):
        mock_get_client.return_value = None
        result = classify("NBA", ["football", "basketball"], fallback="other")
        assert result == "other"

    @patch("app.services.llm._get_client")
    def test_no_fallback_returns_none(self, mock_get_client):
        mock_get_client.return_value = None
        result = classify("NBA", ["football", "basketball"])
        assert result is None


# =============================================================================
# classify_futures_market
# =============================================================================
class TestClassifyFuturesMarket:
    @patch("app.services.llm._get_client")
    def test_always_returns_string(self, mock_get_client, mock_openai_response):
        client = MagicMock()
        client.chat.completions.create.return_value = mock_openai_response("basketball")
        mock_get_client.return_value = client
        result = classify_futures_market("NBA Championship")
        assert isinstance(result, str)
        assert result == "basketball"

    @patch("app.services.llm._get_client")
    def test_fallback_to_other(self, mock_get_client):
        mock_get_client.return_value = None
        result = classify_futures_market("Something Unknown")
        assert result == "other"


# =============================================================================
# classify_gender
# =============================================================================
class TestClassifyGender:
    def test_wnba_is_women(self):
        assert classify_gender("WNBA Championship") == "women"

    def test_wta_is_women(self):
        assert classify_gender("WTA Finals", "tennis_wta") == "women"

    def test_lpga_is_women(self):
        assert classify_gender("LPGA Championship") == "women"

    def test_women_keyword(self):
        assert classify_gender("Women's Soccer Final") == "women"

    def test_mixed_doubles(self):
        assert classify_gender("Mixed Doubles Final") == "mixed"

    def test_nfl_is_men(self):
        assert classify_gender("Super Bowl", "americanfootball_nfl") == "men"

    def test_nba_is_men(self):
        assert classify_gender("NBA Finals", "basketball_nba") == "men"

    def test_mlb_is_men(self):
        assert classify_gender("World Series", "baseball_mlb") == "men"

    def test_ufc_is_men(self):
        assert classify_gender("Heavyweight Championship", "mma_ufc") == "men"

    def test_women_ufc(self):
        assert classify_gender("Women's Bantamweight", "mma_ufc") == "women"

    def test_soccer_is_men(self):
        assert classify_gender("EPL Winner", "soccer_epl") == "men"

    def test_sport_key_wncaab(self):
        assert classify_gender("Championship", "basketball_wncaab") == "women"


# =============================================================================
# classify_level
# =============================================================================
class TestClassifyLevel:
    def test_ncaa_is_college(self):
        assert classify_level("March Madness", "basketball_ncaab") == "college"

    def test_college_keyword(self):
        assert classify_level("College Football Playoff") == "college"

    def test_nfl_is_professional(self):
        assert classify_level("Super Bowl", "americanfootball_nfl") == "professional"

    def test_nba_is_professional(self):
        assert classify_level("NBA Finals", "basketball_nba") == "professional"

    def test_ufc_is_professional(self):
        assert classify_level("Heavyweight Title", "mma_ufc") == "professional"

    def test_epl_is_professional(self):
        assert classify_level("League Winner", "soccer_epl") == "professional"

    def test_boxing_is_professional(self):
        assert classify_level("World Title", "boxing_boxing") == "professional"

    def test_pga_is_professional(self):
        assert classify_level("Tour Championship", "golf_pga") == "professional"


# =============================================================================
# classify_league
# =============================================================================
class TestClassifyLeague:
    def test_nfl_from_sport_key(self):
        assert classify_league("any", "americanfootball_nfl") == "NFL"

    def test_nba_from_sport_key(self):
        assert classify_league("any", "basketball_nba") == "NBA"

    def test_mlb_from_sport_key(self):
        assert classify_league("any", "baseball_mlb") == "MLB"

    def test_nhl_from_sport_key(self):
        assert classify_league("any", "icehockey_nhl") == "NHL"

    def test_epl_from_sport_key(self):
        assert classify_league("any", "soccer_epl") == "EPL"

    def test_ufc_from_sport_key(self):
        assert classify_league("any", "mma_ufc") == "UFC"

    def test_ncaaf_from_sport_key(self):
        assert classify_league("any", "americanfootball_ncaaf") == "NCAAF"

    def test_ncaab_from_sport_key(self):
        assert classify_league("any", "basketball_ncaab") == "NCAAB"

    def test_wnba_from_sport_key(self):
        assert classify_league("any", "basketball_wnba") == "WNBA"

    def test_unknown_soccer_league_fallback(self):
        result = classify_league("any", "soccer_chile_primera")
        assert result == "Chile Primera"


# =============================================================================
# classify_importance
# =============================================================================
class TestClassifyImportance:
    def test_super_bowl_championship(self):
        assert classify_importance("Super Bowl LX") == "championship"

    def test_world_series_championship(self):
        assert classify_importance("World Series Game 7") == "championship"

    def test_stanley_cup_championship(self):
        assert classify_importance("Stanley Cup Finals") == "championship"

    def test_nba_finals_championship(self):
        assert classify_importance("NBA Finals Game 5") == "championship"

    def test_title_fight_championship(self):
        assert classify_importance("UFC Title Fight") == "championship"

    def test_playoff(self):
        assert classify_importance("Playoff Game 3") == "playoff"

    def test_wild_card(self):
        assert classify_importance("Wild Card Round") == "playoff"

    def test_preseason_exhibition(self):
        assert classify_importance("Preseason Game") == "exhibition"

    def test_all_star_exhibition(self):
        assert classify_importance("All-Star Game") == "exhibition"

    def test_pro_bowl_exhibition(self):
        assert classify_importance("Pro Bowl") == "exhibition"

    def test_qualifier(self):
        assert classify_importance("Qualifying Round") == "qualifier"

    def test_play_in(self):
        assert classify_importance("Play-In Tournament") == "qualifier"

    def test_mma_regular_season(self):
        assert classify_importance("Main Event", "mma_ufc") == "regular_season"

    def test_soccer_regular_season(self):
        assert classify_importance("Matchday 15", "soccer_epl") == "regular_season"

    def test_soccer_cup_playoff(self):
        """Soccer cup competitions are playoff format."""
        # "Quarter Final" contains "final" which matches championship_terms,
        # but the cup check runs before that via sport_key
        result = classify_importance("Round of 16", "soccer_england_efl_cup")
        assert result == "playoff"


# =============================================================================
# _normalize_open_ended_category - Unit Tests
# =============================================================================
class TestNormalizeOpenEndedCategory:
    """Test the normalization of LLM-generated free-text categories."""

    def test_known_category_direct(self):
        assert _normalize_open_ended_category("basketball") == "basketball"

    def test_known_category_case_insensitive(self):
        assert _normalize_open_ended_category("Basketball") == "basketball"

    def test_normalize_american_football(self):
        assert _normalize_open_ended_category("american_football") == "football"

    def test_normalize_college_football(self):
        assert _normalize_open_ended_category("college_football") == "football"

    def test_normalize_cryptocurrency(self):
        assert _normalize_open_ended_category("cryptocurrency") == "crypto"

    def test_normalize_digital_assets(self):
        assert _normalize_open_ended_category("digital_assets") == "crypto"

    def test_normalize_artificial_intelligence(self):
        assert _normalize_open_ended_category("artificial_intelligence") == "tech"

    def test_normalize_international_relations(self):
        assert _normalize_open_ended_category("international_relations") == "geopolitics"

    def test_normalize_reality_tv(self):
        assert _normalize_open_ended_category("reality_tv") == "entertainment"

    def test_normalize_mixed_martial_arts(self):
        assert _normalize_open_ended_category("mixed_martial_arts") == "mma"

    def test_novel_category_passthrough(self):
        """Genuinely novel categories are passed through as-is."""
        assert _normalize_open_ended_category("ai_safety") == "ai_safety"

    def test_novel_category_real_estate(self):
        assert _normalize_open_ended_category("real_estate") == "real_estate"

    def test_novel_category_education(self):
        assert _normalize_open_ended_category("education") == "education"

    def test_novel_category_energy(self):
        assert _normalize_open_ended_category("energy") == "energy"

    def test_cleans_quotes_and_periods(self):
        assert _normalize_open_ended_category('"basketball."') == "basketball"

    def test_spaces_to_underscores(self):
        assert _normalize_open_ended_category("horse racing") == "horse_racing"

    def test_hyphens_to_underscores(self):
        assert _normalize_open_ended_category("e-sports") == "esports"

    def test_empty_string(self):
        assert _normalize_open_ended_category("") == "other"

    def test_other_stays_other(self):
        assert _normalize_open_ended_category("other") == "other"

    def test_partial_match_motorsports(self):
        """'motorsport' partially matches 'motorsports'."""
        assert _normalize_open_ended_category("motorsport") == "motorsports"

    def test_normalize_ice_hockey(self):
        assert _normalize_open_ended_category("ice_hockey") == "hockey"

    def test_normalize_stock_market(self):
        assert _normalize_open_ended_category("stock_market") == "economics"


# =============================================================================
# classify_open_ended - Open-ended LLM Classification
# =============================================================================
class TestClassifyOpenEnded:
    """Test open-ended (unconstrained) LLM classification."""

    @patch("app.services.llm._get_client")
    def test_known_category(self, mock_get_client, mock_openai_response):
        """LLM returns a known category — normalized correctly."""
        client = MagicMock()
        client.chat.completions.create.return_value = mock_openai_response("basketball")
        mock_get_client.return_value = client
        result = classify_open_ended("NBA MVP Award")
        assert result == "basketball"

    @patch("app.services.llm._get_client")
    def test_known_synonym(self, mock_get_client, mock_openai_response):
        """LLM returns a synonym — normalized to canonical."""
        client = MagicMock()
        client.chat.completions.create.return_value = mock_openai_response("cryptocurrency")
        mock_get_client.return_value = client
        result = classify_open_ended("Bitcoin Price Above $100K?")
        assert result == "crypto"

    @patch("app.services.llm._get_client")
    def test_novel_category(self, mock_get_client, mock_openai_response):
        """LLM returns a novel category — passed through as-is."""
        client = MagicMock()
        client.chat.completions.create.return_value = mock_openai_response("ai_safety")
        mock_get_client.return_value = client
        result = classify_open_ended("Will GPT-5 pass the bar exam?")
        assert result == "ai_safety"

    @patch("app.services.llm._get_client")
    def test_novel_category_real_estate(self, mock_get_client, mock_openai_response):
        client = MagicMock()
        client.chat.completions.create.return_value = mock_openai_response("real_estate")
        mock_get_client.return_value = client
        result = classify_open_ended("US Housing Price Index Above 300?")
        assert result == "real_estate"

    @patch("app.services.llm._get_client")
    def test_with_outcome_names(self, mock_get_client, mock_openai_response):
        """Outcome names are included in the prompt."""
        client = MagicMock()
        client.chat.completions.create.return_value = mock_openai_response("basketball")
        mock_get_client.return_value = client
        result = classify_open_ended(
            "MVP Winner?",
            outcome_names=["Shai Gilgeous-Alexander", "Nikola Jokic"],
        )
        assert result == "basketball"
        # Verify outcome names were in the prompt
        call_args = client.chat.completions.create.call_args
        user_msg = call_args[1]["messages"][1]["content"]
        assert "Shai Gilgeous-Alexander" in user_msg

    @patch("app.services.llm._get_client")
    def test_no_client_returns_other(self, mock_get_client):
        """Returns 'other' when LLM client unavailable."""
        mock_get_client.return_value = None
        result = classify_open_ended("Some Market")
        assert result == "other"

    @patch("app.services.llm._get_client")
    def test_api_error_returns_other(self, mock_get_client):
        """Returns 'other' on API errors."""
        client = MagicMock()
        client.chat.completions.create.side_effect = Exception("API down")
        mock_get_client.return_value = client
        result = classify_open_ended("Some Market")
        assert result == "other"

    @patch("app.services.llm._get_client")
    def test_cleans_formatting(self, mock_get_client, mock_openai_response):
        """Strips quotes and normalizes formatting."""
        client = MagicMock()
        client.chat.completions.create.return_value = mock_openai_response('"Horse Racing"')
        mock_get_client.return_value = client
        result = classify_open_ended("Kentucky Derby Winner")
        assert result == "horse_racing"


# =============================================================================
# generate_tags_via_llm - LLM Tag Generation
# =============================================================================
class TestGenerateTagsViaLLM:
    """Test LLM-powered tag generation."""

    @patch("app.services.llm._get_client")
    def test_basic_tag_generation(self, mock_get_client, mock_openai_response):
        client = MagicMock()
        client.chat.completions.create.return_value = mock_openai_response(
            "nba, basketball, mvp, lebron_james"
        )
        mock_get_client.return_value = client
        result = generate_tags_via_llm("NBA MVP 2025-26")
        assert "nba" in result
        assert "basketball" in result
        assert "mvp" in result
        assert "lebron_james" in result

    @patch("app.services.llm._get_client")
    def test_preserves_existing_tags(self, mock_get_client, mock_openai_response):
        """Existing tags are preserved and not duplicated."""
        client = MagicMock()
        client.chat.completions.create.return_value = mock_openai_response(
            "nba, basketball, lakers"
        )
        mock_get_client.return_value = client
        result = generate_tags_via_llm(
            "Lakers Championship Odds",
            existing_tags=["basketball", "nba"],
        )
        assert "basketball" in result
        assert "nba" in result
        assert "lakers" in result
        # No duplicates
        assert len(result) == len(set(result))

    @patch("app.services.llm._get_client")
    def test_with_outcome_names(self, mock_get_client, mock_openai_response):
        client = MagicMock()
        client.chat.completions.create.return_value = mock_openai_response(
            "nba, basketball, mvp, shai_gilgeous_alexander, thunder"
        )
        mock_get_client.return_value = client
        result = generate_tags_via_llm(
            "MVP Winner?",
            outcome_names=["Shai Gilgeous-Alexander", "Nikola Jokic"],
        )
        assert "nba" in result
        # Verify outcomes were in prompt
        call_args = client.chat.completions.create.call_args
        user_msg = call_args[1]["messages"][1]["content"]
        assert "Shai Gilgeous-Alexander" in user_msg

    @patch("app.services.llm._get_client")
    def test_filters_short_tags(self, mock_get_client, mock_openai_response):
        """Tags shorter than 2 chars are filtered out."""
        client = MagicMock()
        client.chat.completions.create.return_value = mock_openai_response(
            "a, nba, basketball, x"
        )
        mock_get_client.return_value = client
        result = generate_tags_via_llm("NBA Game")
        assert "a" not in result
        assert "x" not in result
        assert "nba" in result

    @patch("app.services.llm._get_client")
    def test_no_client_returns_existing(self, mock_get_client):
        mock_get_client.return_value = None
        result = generate_tags_via_llm("Some Market", existing_tags=["politics"])
        assert result == ["politics"]

    @patch("app.services.llm._get_client")
    def test_no_client_returns_empty(self, mock_get_client):
        mock_get_client.return_value = None
        result = generate_tags_via_llm("Some Market")
        assert result == []

    @patch("app.services.llm._get_client")
    def test_api_error_returns_existing(self, mock_get_client):
        client = MagicMock()
        client.chat.completions.create.side_effect = Exception("API error")
        mock_get_client.return_value = client
        result = generate_tags_via_llm("Market", existing_tags=["crypto"])
        assert result == ["crypto"]

    @patch("app.services.llm._get_client")
    def test_normalizes_spaces_to_underscores(self, mock_get_client, mock_openai_response):
        client = MagicMock()
        client.chat.completions.create.return_value = mock_openai_response(
            "horse racing, kentucky derby, triple crown"
        )
        mock_get_client.return_value = client
        result = generate_tags_via_llm("Kentucky Derby Winner")
        assert "horse_racing" in result
        assert "kentucky_derby" in result

    @patch("app.services.llm._get_client")
    def test_sorted_output(self, mock_get_client, mock_openai_response):
        client = MagicMock()
        client.chat.completions.create.return_value = mock_openai_response(
            "zebra, apple, mango"
        )
        mock_get_client.return_value = client
        result = generate_tags_via_llm("Some Market")
        assert result == sorted(result)
