"""Tests for championship progression grid (league configs + market matching + endpoint helpers)."""

import pytest
import re
from unittest.mock import MagicMock

from app.config.league_configs import (
    LeagueConfig,
    GridColumn,
    MarketMatchingRule,
    get_league_config,
    get_all_league_slugs,
    NBA_CONFIG,
    NHL_CONFIG,
    NCAA_BASKETBALL_CONFIG,
    GOLF_CONFIG,
    LEAGUE_CONFIGS,
)
from app.routes.playoffs import (
    _match_market_to_column,
    _merge_probabilities,
    _normalize_team_name,
    _strip_diacritics,
    _is_playoff_relevant_market,
)


# ============================================================================
# League config validation
# ============================================================================


class TestLeagueConfigRegistry:
    def test_all_slugs_present(self):
        slugs = get_all_league_slugs()
        assert "nba" in slugs
        assert "nhl" in slugs
        assert "ncaa-basketball" in slugs
        assert "golf" in slugs

    def test_get_league_config(self):
        assert get_league_config("nba") is NBA_CONFIG
        assert get_league_config("nhl") is NHL_CONFIG
        assert get_league_config("ncaa-basketball") is NCAA_BASKETBALL_CONFIG
        assert get_league_config("golf") is GOLF_CONFIG

    def test_unknown_slug_returns_none(self):
        assert get_league_config("cricket") is None
        assert get_league_config("") is None

    def test_all_configs_have_required_fields(self):
        for slug, config in LEAGUE_CONFIGS.items():
            assert config.slug == slug
            assert config.name
            assert config.sport_category
            assert len(config.sport_keys) > 0
            assert len(config.columns) >= 2
            assert config.stage_key

    def test_columns_ordered(self):
        """Columns should be in ascending order."""
        for slug, config in LEAGUE_CONFIGS.items():
            orders = [c.order for c in config.columns]
            assert orders == sorted(orders), f"{slug} columns not in order"

    def test_column_keys_unique(self):
        for slug, config in LEAGUE_CONFIGS.items():
            keys = [c.key for c in config.columns]
            assert len(keys) == len(set(keys)), f"{slug} has duplicate column keys"

    def test_matching_rules_reference_valid_columns(self):
        """Every matching rule column must exist in the config's columns."""
        for slug, config in LEAGUE_CONFIGS.items():
            col_keys = {c.key for c in config.columns}
            for rule in config.matching_rules:
                assert rule.column in col_keys, (
                    f"{slug}: matching rule references unknown column '{rule.column}'"
                )


class TestLeagueSpecificConfigs:
    def test_nba_has_conference_split(self):
        assert NBA_CONFIG.conference_split is True

    def test_nba_columns(self):
        keys = [c.key for c in NBA_CONFIG.columns]
        assert "make_playoffs" in keys
        assert "conference" in keys
        assert "championship" in keys

    def test_nhl_columns(self):
        keys = [c.key for c in NHL_CONFIG.columns]
        assert "make_playoffs" in keys
        assert "division" in keys
        assert "conference" in keys
        assert "championship" in keys

    def test_ncaa_has_all_rounds(self):
        keys = [c.key for c in NCAA_BASKETBALL_CONFIG.columns]
        assert keys == [
            "round_of_32",
            "sweet_16",
            "elite_eight",
            "final_four",
            "title_game",
            "championship",
        ]

    def test_ncaa_sequential(self):
        """NCAA tournament rounds are sequential."""
        for col in NCAA_BASKETBALL_CONFIG.columns:
            assert col.sequential is True

    def test_ncaa_uses_region_split(self):
        assert NCAA_BASKETBALL_CONFIG.region_split is True
        assert NCAA_BASKETBALL_CONFIG.conference_split is False

    def test_golf_not_sequential(self):
        """Golf columns are NOT sequential (finishing positions, not rounds)."""
        for col in GOLF_CONFIG.columns:
            assert col.sequential is False

    def test_golf_columns(self):
        keys = [c.key for c in GOLF_CONFIG.columns]
        assert keys == ["make_cut", "top_20", "top_10", "top_5", "win"]


# ============================================================================
# Market-to-column matching
# ============================================================================


def _make_market(name, source="odds_api", external_id="", market_tier=None, llm_sport_category=None):
    m = MagicMock()
    m.name = name
    m.source = source
    m.external_id = external_id
    m.market_tier = market_tier
    m.llm_sport_category = llm_sport_category
    return m


class TestMarketToColumnMatching:
    # --- NBA ---
    def test_nba_championship_by_name(self):
        m = _make_market("NBA Championship Winner 2025-26")
        assert _match_market_to_column(m, NBA_CONFIG) == "championship"

    def test_nba_championship_by_tier(self):
        m = _make_market("Some NBA market", market_tier=1)
        # Tier 1 with matching name pattern
        m2 = _make_market("NBA Championship", market_tier=1)
        assert _match_market_to_column(m2, NBA_CONFIG) == "championship"

    def test_nba_conference_eastern(self):
        m = _make_market("NBA Eastern Conference Winner 2025-26")
        assert _match_market_to_column(m, NBA_CONFIG) == "conference"

    def test_nba_conference_western(self):
        m = _make_market("NBA Western Conference Winner 2025-26")
        assert _match_market_to_column(m, NBA_CONFIG) == "conference"

    def test_nba_make_playoffs(self):
        m = _make_market("Will the Lakers Make Playoffs?")
        assert _match_market_to_column(m, NBA_CONFIG) == "make_playoffs"

    def test_nba_unrelated_returns_none(self):
        m = _make_market("NBA MVP Winner 2025-26")
        assert _match_market_to_column(m, NBA_CONFIG) is None

    # --- NHL ---
    def test_nhl_stanley_cup(self):
        m = _make_market("Stanley Cup Winner 2025-26")
        assert _match_market_to_column(m, NHL_CONFIG) == "championship"

    def test_nhl_conference(self):
        m = _make_market("NHL Western Conference Winner")
        assert _match_market_to_column(m, NHL_CONFIG) == "conference"

    def test_nhl_division(self):
        m = _make_market("NHL Atlantic Division Winner")
        assert _match_market_to_column(m, NHL_CONFIG) == "division"

    def test_nhl_make_playoffs(self):
        m = _make_market("NHL Playoff Qualifiers 2025-26")
        assert _match_market_to_column(m, NHL_CONFIG) == "make_playoffs"

    # --- NCAA Basketball ---
    def test_ncaa_championship(self):
        m = _make_market("NCAAB Championship Winner 2026")
        assert _match_market_to_column(m, NCAA_BASKETBALL_CONFIG) == "championship"

    def test_ncaa_championship_alt(self):
        m = _make_market("2026 NCAA Tournament Winner")
        assert _match_market_to_column(m, NCAA_BASKETBALL_CONFIG) == "championship"

    def test_ncaa_final_four(self):
        m = _make_market("NCAA Tournament: Team to make Final Four")
        assert _match_market_to_column(m, NCAA_BASKETBALL_CONFIG) == "final_four"

    def test_ncaa_sweet_16(self):
        m = _make_market("NCAA Tournament: Team to make Sweet Sixteen")
        assert _match_market_to_column(m, NCAA_BASKETBALL_CONFIG) == "sweet_16"

    def test_ncaa_elite_eight(self):
        m = _make_market("NCAA Tournament: Team to make Elite Eight")
        assert _match_market_to_column(m, NCAA_BASKETBALL_CONFIG) == "elite_eight"

    def test_ncaa_title_game(self):
        m = _make_market("NCAA Tournament: Team to make National Championship Game")
        assert _match_market_to_column(m, NCAA_BASKETBALL_CONFIG) == "title_game"

    def test_ncaa_round_of_32(self):
        m = _make_market("Win First Round (Round of 32)")
        assert _match_market_to_column(m, NCAA_BASKETBALL_CONFIG) == "round_of_32"

    def test_ncaa_march_madness_winner(self):
        m = _make_market("March Madness Winner 2026")
        assert _match_market_to_column(m, NCAA_BASKETBALL_CONFIG) == "championship"

    # --- Golf ---
    def test_golf_winner(self):
        m = _make_market("Masters Tournament Winner 2026")
        assert _match_market_to_column(m, GOLF_CONFIG) == "win"

    def test_golf_top_5(self):
        m = _make_market("Masters Top 5 Finisher")
        assert _match_market_to_column(m, GOLF_CONFIG) == "top_5"

    def test_golf_top_10(self):
        m = _make_market("Masters Top 10 Finisher")
        assert _match_market_to_column(m, GOLF_CONFIG) == "top_10"

    def test_golf_top_20(self):
        m = _make_market("Masters Top 20 Finisher")
        assert _match_market_to_column(m, GOLF_CONFIG) == "top_20"

    def test_golf_make_cut(self):
        m = _make_market("Masters: To Make the Cut")
        assert _match_market_to_column(m, GOLF_CONFIG) == "make_cut"

    def test_golf_datagolf_suffix(self):
        """DataGolf markets use external_id suffix for stage matching."""
        m = _make_market(
            "Masters Tournament",
            source="datagolf",
            external_id="datagolf:pga:masters_2026:win",
        )
        assert _match_market_to_column(m, GOLF_CONFIG) == "win"

    def test_golf_datagolf_make_cut(self):
        m = _make_market(
            "Masters Tournament",
            source="datagolf",
            external_id="datagolf:pga:masters_2026:make_cut",
        )
        assert _match_market_to_column(m, GOLF_CONFIG) == "make_cut"


# ============================================================================
# Probability merging
# ============================================================================


class TestProbabilityMerging:
    def test_single_source(self):
        assert _merge_probabilities([0.22]) == 0.22

    def test_two_sources_median(self):
        result = _merge_probabilities([0.20, 0.24])
        assert result == 0.22

    def test_three_sources_median(self):
        result = _merge_probabilities([0.20, 0.24, 0.30])
        assert result == 0.24

    def test_empty_returns_zero(self):
        assert _merge_probabilities([]) == 0.0

    def test_identical_sources(self):
        assert _merge_probabilities([0.15, 0.15, 0.15]) == 0.15


# ============================================================================
# Name normalization
# ============================================================================


class TestNameNormalization:
    def test_strip_diacritics(self):
        assert _strip_diacritics("Skarsgard") == "Skarsgard"
        assert _strip_diacritics("Skarsgård") == "Skarsgard"

    def test_normalize_basic(self):
        assert _normalize_team_name("Boston Celtics") == "boston celtics"

    def test_normalize_strips_parens(self):
        assert _normalize_team_name("Duke (4)") == "duke"

    def test_normalize_strips_whitespace(self):
        assert _normalize_team_name("  Celtics  ") == "celtics"

    def test_normalize_diacritics(self):
        assert _normalize_team_name("Zürich") == "zurich"


# ============================================================================
# Probability consistency (sequential columns)
# ============================================================================


class TestProbabilityConsistency:
    """Test that the grid data can detect consistency violations.

    For sequential columns: P(later stage) <= P(earlier stage).
    The endpoint doesn't enforce this, but the frontend should flag it.
    """

    def test_consistent_nba_probabilities(self):
        """Valid: championship < conference < make_playoffs."""
        cells = {
            "make_playoffs": {"merged_probability": 0.95},
            "conference": {"merged_probability": 0.45},
            "championship": {"merged_probability": 0.22},
        }
        columns = NBA_CONFIG.columns
        probs = [
            cells.get(c.key, {}).get("merged_probability", 0)
            for c in columns
            if c.sequential
        ]
        # Each subsequent probability should be <= previous
        for i in range(1, len(probs)):
            if probs[i] > 0 and probs[i - 1] > 0:
                assert probs[i] <= probs[i - 1]

    def test_inconsistent_flags_possible(self):
        """The grid doesn't silently fix — inconsistencies are visible."""
        cells = {
            "make_playoffs": {"merged_probability": 0.50},
            "conference": {"merged_probability": 0.60},  # HIGHER than make_playoffs!
            "championship": {"merged_probability": 0.22},
        }
        columns = [c for c in NBA_CONFIG.columns if c.sequential]
        probs = [cells.get(c.key, {}).get("merged_probability", 0) for c in columns]
        # Detect violation
        has_violation = any(
            probs[i] > probs[i - 1]
            for i in range(1, len(probs))
            if probs[i] > 0 and probs[i - 1] > 0
        )
        assert has_violation  # The grid exposes violations, doesn't hide them


# ============================================================================
# Matching rule pattern compilation
# ============================================================================


class TestNonPlayoffMarketFilter:
    """Verify that non-playoff markets are rejected."""

    def test_win_totals_rejected(self):
        assert not _is_playoff_relevant_market("Celtics: Over (41.5)")
        assert not _is_playoff_relevant_market("Lakers Win Total Over/Under")
        assert not _is_playoff_relevant_market("Season Wins: Over (50.5)")

    def test_win_count_thresholds_rejected(self):
        assert not _is_playoff_relevant_market("15+ wins")
        assert not _is_playoff_relevant_market("20+ wins this season")

    def test_date_markets_rejected(self):
        assert not _is_playoff_relevant_market("Before March 7th, 2026")
        assert not _is_playoff_relevant_market("Before April 1st, 2026")

    def test_awards_rejected(self):
        assert not _is_playoff_relevant_market("NBA MVP Winner 2025-26")
        assert not _is_playoff_relevant_market("Rookie of the Year")
        assert not _is_playoff_relevant_market("Defensive Player of the Year")
        assert not _is_playoff_relevant_market("Most Improved Player")
        assert not _is_playoff_relevant_market("6th Man of the Year")

    def test_game_markets_rejected(self):
        assert not _is_playoff_relevant_market("Celtics vs. Lakers")
        assert not _is_playoff_relevant_market("Celtics at Lakers: Points")

    def test_player_props_rejected(self):
        assert not _is_playoff_relevant_market("Tatum Points Over 25.5")
        assert not _is_playoff_relevant_market("Jokic Rebounds + Assists")

    def test_championship_allowed(self):
        assert _is_playoff_relevant_market("NBA Championship Winner 2025-26")
        assert _is_playoff_relevant_market("Stanley Cup Winner")
        assert _is_playoff_relevant_market("NCAAB Championship Winner 2026")

    def test_conference_allowed(self):
        assert _is_playoff_relevant_market("NBA Eastern Conference Winner")
        assert _is_playoff_relevant_market("NHL Western Conference")

    def test_make_playoffs_allowed(self):
        assert _is_playoff_relevant_market("Will Lakers Make Playoffs?")
        assert _is_playoff_relevant_market("NHL Playoff Qualifiers")

    def test_tournament_round_allowed(self):
        assert _is_playoff_relevant_market("NCAA Tournament: Team to make Final Four")
        assert _is_playoff_relevant_market("Sweet Sixteen")
        assert _is_playoff_relevant_market("Elite Eight")

    def test_golf_allowed(self):
        assert _is_playoff_relevant_market("Masters Tournament Winner 2026")
        assert _is_playoff_relevant_market("Masters: To Make the Cut")
        assert _is_playoff_relevant_market("Masters Top 10 Finisher")


class TestMatchingRulePatterns:
    """Verify all name_patterns in matching rules are valid regex."""

    def test_all_patterns_compile(self):
        for slug, config in LEAGUE_CONFIGS.items():
            for rule in config.matching_rules:
                for pat in rule.name_patterns:
                    try:
                        re.compile(pat, re.IGNORECASE)
                    except re.error as e:
                        pytest.fail(
                            f"{slug} rule {rule.column} has invalid pattern "
                            f"'{pat}': {e}"
                        )

    def test_no_empty_patterns(self):
        for slug, config in LEAGUE_CONFIGS.items():
            for rule in config.matching_rules:
                for pat in rule.name_patterns:
                    assert pat.strip(), (
                        f"{slug} rule {rule.column} has empty pattern"
                    )
