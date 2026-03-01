"""Tests for event taxonomy tag computation.

Covers:
- compute_event_tags: sport, league, tier, class, level, gender, importance,
  status, signals, timing, EI label
- compute_market_tags: sport, league, tier, category, level, gender,
  market_status, source
- validate_tag: namespace:value format and vocabulary
- Expanded vocabulary: new sports, leagues, prefixes
- LEAGUE_CLASS gap fills
- compute_aggregate_probability: shared utility
"""

from datetime import datetime, timezone, timedelta

import pytest

from app.utils.event_taxonomy import (
    ALLOWED_TAGS,
    _SPORT_KEY_TO_LEAGUE,
    _EXTRA_SPORT_PREFIXES,
    compute_event_tags,
    compute_market_tags,
    validate_tag,
    _extract_sport,
    _extract_league,
    _ei_label,
)
from app.utils.highlights import EventFlags, HighlightResult
from app.utils.league_classification import LEAGUE_CLASS


# ── Fixtures ─────────────────────────────────────────────────────────

@pytest.fixture
def weekend_primetime():
    """Saturday at 8pm Eastern (01:00 UTC Sunday)."""
    return datetime(2026, 3, 1, 1, 0, tzinfo=timezone.utc)


@pytest.fixture
def weekday_afternoon():
    """Tuesday at 2pm Eastern (19:00 UTC)."""
    return datetime(2026, 3, 3, 19, 0, tzinfo=timezone.utc)


@pytest.fixture
def base_flags():
    return EventFlags(
        is_close_matchup=False,
        is_very_close=False,
        is_upset=False,
        favorite_switched=False,
        probability_swing="none",
        is_volatile=False,
        has_lead_changes=False,
        has_recent_momentum=False,
        is_blowout=False,
        is_starting_soon=False,
    )


@pytest.fixture
def base_highlight(base_flags):
    return HighlightResult(
        score=50,
        reasons=["live"],
        flags=base_flags,
    )


# ══════════════════════════════════════════════════════════════════════
# validate_tag
# ══════════════════════════════════════════════════════════════════════

class TestValidateTag:
    def test_valid_tag(self):
        assert validate_tag("sport:basketball") is True

    def test_invalid_no_colon(self):
        assert validate_tag("basketball") is False

    def test_invalid_namespace(self):
        assert validate_tag("foo:bar") is False

    def test_invalid_value(self):
        assert validate_tag("sport:curling_league") is False

    def test_valid_tier(self):
        assert validate_tag("tier:1") is True

    def test_invalid_tier(self):
        assert validate_tag("tier:5") is False

    def test_valid_market_status(self):
        assert validate_tag("market_status:open") is True

    def test_valid_source(self):
        assert validate_tag("source:kalshi") is True

    def test_valid_category(self):
        assert validate_tag("category:championship") is True


# ══════════════════════════════════════════════════════════════════════
# _extract_sport
# ══════════════════════════════════════════════════════════════════════

class TestExtractSport:
    def test_basketball(self):
        assert _extract_sport("basketball_nba") == "basketball"

    def test_american_football(self):
        assert _extract_sport("americanfootball_nfl") == "football"

    def test_ice_hockey(self):
        assert _extract_sport("icehockey_nhl") == "hockey"

    def test_soccer(self):
        assert _extract_sport("soccer_epl") == "soccer"

    def test_mma(self):
        assert _extract_sport("mma_mixed_martial_arts") == "mma"

    def test_rugby_league(self):
        assert _extract_sport("rugbyleague_nrl") == "rugby"

    def test_rugby_union(self):
        assert _extract_sport("rugbyunion_six_nations") == "rugby"

    def test_aussierules(self):
        assert _extract_sport("aussierules_afl") == "aussierules"

    def test_lacrosse(self):
        assert _extract_sport("lacrosse_pll") == "lacrosse"

    def test_motorsport(self):
        assert _extract_sport("motorsport_f1") == "motorsports"

    def test_horse_racing(self):
        assert _extract_sport("horseracing_uk") == "horse_racing"

    def test_esports(self):
        assert _extract_sport("esports_lol") == "esports"

    def test_field_hockey(self):
        assert _extract_sport("fieldhockey_olympics") == "hockey"

    def test_curling(self):
        assert _extract_sport("curling_olympics") == "olympics"

    def test_empty_string(self):
        assert _extract_sport("") is None

    def test_unknown_sport(self):
        assert _extract_sport("underwater_polo") is None


# ══════════════════════════════════════════════════════════════════════
# _extract_league
# ══════════════════════════════════════════════════════════════════════

class TestExtractLeague:
    def test_nba(self):
        assert _extract_league("basketball_nba", None) == "nba"

    def test_llm_league_preferred(self):
        assert _extract_league("basketball_nba", "EPL") == "epl"

    def test_llm_league_with_spaces(self):
        assert _extract_league("unknown_key", "Champions League") == "champions_league"

    def test_fallback_to_sport_key(self):
        assert _extract_league("soccer_efl_champ", None) == "efl_champ"

    def test_invalid_llm_league_fallback(self):
        assert _extract_league("basketball_nba", "Something Unknown") == "nba"

    def test_unknown_both(self):
        assert _extract_league("unknown_key", "Unknown League") is None

    def test_olympics(self):
        assert _extract_league("icehockey_olympics", None) == "olympics"

    def test_cricket(self):
        assert _extract_league("cricket_t20_world_cup", None) == "t20_world_cup"

    def test_tennis_grand_slam(self):
        assert _extract_league("tennis_wimbledon", None) == "wimbledon"

    def test_golf_major(self):
        assert _extract_league("golf_masters_tournament_winner", None) == "masters"


# ══════════════════════════════════════════════════════════════════════
# _ei_label
# ══════════════════════════════════════════════════════════════════════

class TestEILabel:
    def test_incredible(self):
        assert _ei_label(95) == "incredible"

    def test_must_watch(self):
        assert _ei_label(85) == "must_watch"

    def test_exciting(self):
        assert _ei_label(75) == "exciting"

    def test_flat(self):
        assert _ei_label(10) == "flat"

    def test_boundary_90(self):
        assert _ei_label(90) == "incredible"

    def test_boundary_89(self):
        assert _ei_label(89) == "must_watch"


# ══════════════════════════════════════════════════════════════════════
# compute_event_tags — basics
# ══════════════════════════════════════════════════════════════════════

class TestComputeEventTags:
    def test_basic_nba_live(self, weekday_afternoon):
        tags = compute_event_tags(
            sport_key="basketball_nba",
            status="live",
            commence_time=weekday_afternoon,
        )
        assert "sport:basketball" in tags
        assert "league:nba" in tags
        assert "tier:1" in tags
        assert "class:pro_major" in tags
        assert "status:live" in tags

    def test_nfl_scheduled(self, weekend_primetime):
        tags = compute_event_tags(
            sport_key="americanfootball_nfl",
            status="scheduled",
            commence_time=weekend_primetime,
        )
        assert "sport:football" in tags
        assert "league:nfl" in tags
        assert "status:scheduled" in tags
        assert "timing:weekend" in tags

    def test_completed_with_ei(self, weekday_afternoon):
        tags = compute_event_tags(
            sport_key="basketball_nba",
            status="completed",
            commence_time=weekday_afternoon,
            raw_ei=0.85,
        )
        assert "ei:must_watch" in tags
        assert "status:completed" in tags

    def test_importance_playoff(self, weekday_afternoon):
        tags = compute_event_tags(
            sport_key="basketball_nba",
            status="live",
            commence_time=weekday_afternoon,
            llm_importance="playoff",
        )
        assert "importance:playoff" in tags

    def test_gender_women(self, weekday_afternoon):
        tags = compute_event_tags(
            sport_key="basketball_wnba",
            status="scheduled",
            commence_time=weekday_afternoon,
            llm_gender="women",
        )
        assert "gender:women" in tags

    def test_level_college(self, weekday_afternoon):
        tags = compute_event_tags(
            sport_key="basketball_ncaab",
            status="scheduled",
            commence_time=weekday_afternoon,
            llm_level="college",
        )
        assert "level:college" in tags

    def test_llm_league_override(self, weekday_afternoon):
        tags = compute_event_tags(
            sport_key="basketball_nba",
            status="live",
            commence_time=weekday_afternoon,
            llm_league="Champions League",
        )
        assert "league:champions_league" in tags

    def test_tags_sorted(self, weekday_afternoon):
        tags = compute_event_tags(
            sport_key="basketball_nba",
            status="live",
            commence_time=weekday_afternoon,
        )
        assert tags == sorted(tags)

    def test_tags_validated(self, weekday_afternoon):
        """All returned tags must pass validation."""
        tags = compute_event_tags(
            sport_key="basketball_nba",
            status="live",
            commence_time=weekday_afternoon,
            llm_importance="playoff",
            raw_ei=0.72,
        )
        for tag in tags:
            assert validate_tag(tag), f"Invalid tag: {tag}"

    def test_unknown_sport_key_gets_tier4(self, weekday_afternoon):
        tags = compute_event_tags(
            sport_key="underwater_polo_league",
            status="scheduled",
            commence_time=weekday_afternoon,
        )
        assert "tier:4" in tags
        assert "class:other" in tags
        # No sport tag for unknown
        assert not any(t.startswith("sport:") for t in tags)


# ══════════════════════════════════════════════════════════════════════
# compute_event_tags — signals
# ══════════════════════════════════════════════════════════════════════

class TestEventTagSignals:
    def test_close_matchup_signal(self, weekday_afternoon, base_flags):
        base_flags.is_close_matchup = True
        hr = HighlightResult(score=50, reasons=["live"], flags=base_flags)
        tags = compute_event_tags(
            sport_key="basketball_nba",
            status="live",
            commence_time=weekday_afternoon,
            highlight_result=hr,
        )
        assert "signal:close_matchup" in tags

    def test_upset_signal(self, weekday_afternoon, base_flags):
        base_flags.is_upset = True
        hr = HighlightResult(score=50, reasons=["live"], flags=base_flags)
        tags = compute_event_tags(
            sport_key="basketball_nba",
            status="live",
            commence_time=weekday_afternoon,
            highlight_result=hr,
        )
        assert "signal:upset" in tags

    def test_line_moving_signal(self, weekday_afternoon, base_flags):
        base_flags.probability_swing = "major"
        hr = HighlightResult(score=50, reasons=["live"], flags=base_flags)
        tags = compute_event_tags(
            sport_key="basketball_nba",
            status="live",
            commence_time=weekday_afternoon,
            highlight_result=hr,
        )
        assert "signal:line_moving" in tags

    def test_blowout_signal(self, weekday_afternoon, base_flags):
        base_flags.is_blowout = True
        hr = HighlightResult(score=50, reasons=["live"], flags=base_flags)
        tags = compute_event_tags(
            sport_key="basketball_nba",
            status="live",
            commence_time=weekday_afternoon,
            highlight_result=hr,
        )
        assert "signal:blowout" in tags

    def test_no_signals_without_highlight(self, weekday_afternoon):
        tags = compute_event_tags(
            sport_key="basketball_nba",
            status="live",
            commence_time=weekday_afternoon,
        )
        assert not any(t.startswith("signal:") for t in tags)


# ══════════════════════════════════════════════════════════════════════
# compute_event_tags — timing
# ══════════════════════════════════════════════════════════════════════

class TestEventTagTiming:
    def test_weekend(self):
        # Saturday 3pm Eastern = 20:00 UTC
        sat = datetime(2026, 2, 28, 20, 0, tzinfo=timezone.utc)
        tags = compute_event_tags(
            sport_key="americanfootball_nfl",
            status="scheduled",
            commence_time=sat,
        )
        assert "timing:weekend" in tags

    def test_primetime(self):
        # 8pm Eastern = 01:00 UTC next day
        prime = datetime(2026, 3, 4, 1, 0, tzinfo=timezone.utc)
        tags = compute_event_tags(
            sport_key="americanfootball_nfl",
            status="scheduled",
            commence_time=prime,
        )
        assert "timing:primetime" in tags

    def test_national_tv_espn(self):
        tags = compute_event_tags(
            sport_key="basketball_nba",
            status="live",
            commence_time=datetime(2026, 3, 3, 1, 0, tzinfo=timezone.utc),
            broadcast_info="ESPN, ESPN+",
        )
        assert "timing:national_tv" in tags

    def test_national_tv_amazon(self):
        tags = compute_event_tags(
            sport_key="americanfootball_nfl",
            status="live",
            commence_time=datetime(2026, 3, 3, 1, 0, tzinfo=timezone.utc),
            broadcast_info="Amazon Prime Video",
        )
        assert "timing:national_tv" in tags

    def test_no_broadcast_no_national_tv(self):
        tags = compute_event_tags(
            sport_key="basketball_nba",
            status="live",
            commence_time=datetime(2026, 3, 3, 1, 0, tzinfo=timezone.utc),
        )
        assert "timing:national_tv" not in tags


# ══════════════════════════════════════════════════════════════════════
# compute_market_tags
# ══════════════════════════════════════════════════════════════════════

class TestComputeMarketTags:
    def test_championship_basketball(self):
        tags = compute_market_tags(
            llm_sport_category="basketball",
            llm_league="NBA",
            market_tier=1,
            status="open",
            source="odds_api",
        )
        assert "sport:basketball" in tags
        assert "league:nba" in tags
        assert "tier:1" in tags
        assert "category:championship" in tags
        assert "market_status:open" in tags
        assert "source:odds_api" in tags

    def test_mvp_category(self):
        tags = compute_market_tags(
            llm_sport_category="basketball",
            category="mvp",
        )
        assert "category:mvp" in tags

    def test_category_from_tier(self):
        tags = compute_market_tags(
            market_tier=3,
        )
        assert "category:awards" in tags

    def test_explicit_category_over_tier(self):
        tags = compute_market_tags(
            market_tier=1,
            category="mvp",
        )
        assert "category:mvp" in tags
        assert "category:championship" not in tags

    def test_politics_sport(self):
        tags = compute_market_tags(
            llm_sport_category="politics",
        )
        assert "sport:politics" in tags

    def test_entertainment_sport(self):
        tags = compute_market_tags(
            llm_sport_category="entertainment",
        )
        assert "sport:entertainment" in tags

    def test_kalshi_source(self):
        tags = compute_market_tags(source="kalshi")
        assert "source:kalshi" in tags

    def test_polymarket_source(self):
        tags = compute_market_tags(source="polymarket")
        assert "source:polymarket" in tags

    def test_resolved_status(self):
        tags = compute_market_tags(status="resolved")
        assert "market_status:resolved" in tags

    def test_level_and_gender(self):
        tags = compute_market_tags(
            llm_level="professional",
            llm_gender="men",
        )
        assert "level:professional" in tags
        assert "gender:men" in tags

    def test_league_normalization(self):
        tags = compute_market_tags(llm_league="Champions League")
        assert "league:champions_league" in tags

    def test_empty_returns_empty(self):
        tags = compute_market_tags()
        assert tags == []

    def test_invalid_sport_skipped(self):
        tags = compute_market_tags(llm_sport_category="underwater_polo")
        assert not any(t.startswith("sport:") for t in tags)

    def test_invalid_source_skipped(self):
        tags = compute_market_tags(source="betfair")
        assert not any(t.startswith("source:") for t in tags)

    def test_tier_5_not_in_allowed(self):
        """Tier 5 is not in ALLOWED_TAGS, but category:prop is derived from it."""
        tags = compute_market_tags(market_tier=5)
        assert "category:prop" in tags
        assert not any(t.startswith("tier:") for t in tags)

    def test_tags_sorted(self):
        tags = compute_market_tags(
            llm_sport_category="basketball",
            llm_league="NBA",
            market_tier=1,
            status="open",
            source="odds_api",
        )
        assert tags == sorted(tags)


# ══════════════════════════════════════════════════════════════════════
# Market tag validation
# ══════════════════════════════════════════════════════════════════════

class TestMarketTagValidation:
    def test_all_market_tags_valid(self):
        tags = compute_market_tags(
            llm_sport_category="basketball",
            llm_league="NBA",
            llm_gender="men",
            llm_level="professional",
            market_tier=1,
            category="championship",
            status="open",
            source="odds_api",
        )
        for tag in tags:
            assert validate_tag(tag), f"Invalid tag: {tag}"

    def test_new_namespaces_exist(self):
        assert "category" in ALLOWED_TAGS
        assert "source" in ALLOWED_TAGS
        assert "market_status" in ALLOWED_TAGS

    def test_market_status_values(self):
        assert ALLOWED_TAGS["market_status"] == {"open", "suspended", "resolved"}


# ══════════════════════════════════════════════════════════════════════
# Expanded vocabulary
# ══════════════════════════════════════════════════════════════════════

class TestExpandedVocabulary:
    def test_entertainment_sport(self):
        assert "entertainment" in ALLOWED_TAGS["sport"]

    def test_politics_sport(self):
        assert "politics" in ALLOWED_TAGS["sport"]

    def test_poker_sport(self):
        assert "poker" in ALLOWED_TAGS["sport"]

    def test_chess_sport(self):
        assert "chess" in ALLOWED_TAGS["sport"]

    def test_darts_sport(self):
        assert "darts" in ALLOWED_TAGS["sport"]

    def test_boxing_league(self):
        assert "boxing" in ALLOWED_TAGS["league"]

    def test_copa_libertadores_league(self):
        assert "copa_libertadores" in ALLOWED_TAGS["league"]

    def test_olympics_league(self):
        assert "olympics" in ALLOWED_TAGS["league"]

    def test_eredivisie_league(self):
        assert "eredivisie" in ALLOWED_TAGS["league"]

    def test_liiga_league(self):
        assert "liiga" in ALLOWED_TAGS["league"]

    def test_aussierules_prefix(self):
        assert _extract_sport("aussierules_afl") == "aussierules"

    def test_all_sport_key_to_league_values_in_allowed(self):
        """Every league in _SPORT_KEY_TO_LEAGUE must be in ALLOWED_TAGS."""
        for sport_key, league in _SPORT_KEY_TO_LEAGUE.items():
            assert league in ALLOWED_TAGS["league"], (
                f"League '{league}' (from sport_key '{sport_key}') not in ALLOWED_TAGS"
            )

    def test_all_extra_prefixes_in_allowed(self):
        """Every sport in _EXTRA_SPORT_PREFIXES must be in ALLOWED_TAGS."""
        for prefix, sport in _EXTRA_SPORT_PREFIXES.items():
            assert sport in ALLOWED_TAGS["sport"], (
                f"Sport '{sport}' (from prefix '{prefix}') not in ALLOWED_TAGS"
            )


# ══════════════════════════════════════════════════════════════════════
# LEAGUE_CLASS gap fills
# ══════════════════════════════════════════════════════════════════════

class TestLeagueClassGaps:
    def test_fifa_world_cup_international(self):
        assert LEAGUE_CLASS["soccer_fifa_world_cup"] == "international"

    def test_boxing_pro_major(self):
        assert LEAGUE_CLASS["boxing_boxing"] == "pro_major"

    def test_golf_masters_pro_major(self):
        assert LEAGUE_CLASS["golf_masters_tournament_winner"] == "pro_major"

    def test_tennis_wimbledon_pro_major(self):
        assert LEAGUE_CLASS["tennis_wimbledon"] == "pro_major"

    def test_rugby_nrl_international(self):
        assert LEAGUE_CLASS["rugby_nrl"] == "international"

    def test_cricket_international(self):
        assert LEAGUE_CLASS["cricket_t20_world_cup"] == "international"

    def test_aussierules_international(self):
        assert LEAGUE_CLASS["aussierules_afl"] == "international"

    def test_lower_hockey_pro_minor(self):
        assert LEAGUE_CLASS["icehockey_liiga"] == "pro_minor"

    def test_lower_english_soccer_pro_minor(self):
        assert LEAGUE_CLASS["soccer_england_league1"] == "pro_minor"

    def test_europa_conference_international(self):
        assert LEAGUE_CLASS["soccer_uefa_europa_conference_league"] == "international"

    def test_olympics_international(self):
        assert LEAGUE_CLASS["icehockey_olympics"] == "international"
        assert LEAGUE_CLASS["basketball_olympics"] == "international"
        assert LEAGUE_CLASS["soccer_olympics"] == "international"


# ══════════════════════════════════════════════════════════════════════
# compute_aggregate_probability (shared utility)
# ══════════════════════════════════════════════════════════════════════

class TestComputeAggregateProbability:
    def test_win_probability_sources_tier(self):
        from app.utils.aggregation import compute_aggregate_probability

        class MockEvent:
            win_probability_sources = {"betting": 0.65, "espn": 0.70}
            espn_win_prob_home = None
            opening_home_probability = None

        result = compute_aggregate_probability(MockEvent())
        assert result is not None
        assert 0.6 < result < 0.8

    def test_espn_fallback(self):
        from app.utils.aggregation import compute_aggregate_probability

        class MockEvent:
            win_probability_sources = {}
            espn_win_prob_home = 0.55
            opening_home_probability = None

        result = compute_aggregate_probability(MockEvent())
        assert result == 0.55

    def test_opening_fallback(self):
        from app.utils.aggregation import compute_aggregate_probability

        class MockEvent:
            win_probability_sources = {}
            espn_win_prob_home = None
            opening_home_probability = 0.40

        result = compute_aggregate_probability(MockEvent())
        assert result == 0.4

    def test_none_when_no_data(self):
        from app.utils.aggregation import compute_aggregate_probability

        class MockEvent:
            win_probability_sources = {}
            espn_win_prob_home = None
            opening_home_probability = None

        result = compute_aggregate_probability(MockEvent())
        assert result is None
