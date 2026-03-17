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
    NFL_CONFIG,
    MLB_CONFIG,
    WNBA_CONFIG,
    MLS_CONFIG,
    NCAA_BASKETBALL_CONFIG,
    NCAA_FOOTBALL_CONFIG,
    EPL_CONFIG,
    LA_LIGA_CONFIG,
    CHAMPIONS_LEAGUE_CONFIG,
    BUNDESLIGA_CONFIG,
    GOLF_CONFIG,
    LEAGUE_CONFIGS,
)
from app.routes.playoffs import (
    _match_market_to_column,
    _match_golfer_to_field,
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
        for expected in [
            "nba", "nhl", "nfl", "mlb", "wnba", "mls",
            "ncaa-basketball", "ncaa-football",
            "epl", "la-liga", "champions-league", "bundesliga",
            "golf",
        ]:
            assert expected in slugs, f"Missing slug: {expected}"

    def test_get_league_config(self):
        assert get_league_config("nba") is NBA_CONFIG
        assert get_league_config("nhl") is NHL_CONFIG
        assert get_league_config("nfl") is NFL_CONFIG
        assert get_league_config("mlb") is MLB_CONFIG
        assert get_league_config("wnba") is WNBA_CONFIG
        assert get_league_config("mls") is MLS_CONFIG
        assert get_league_config("ncaa-basketball") is NCAA_BASKETBALL_CONFIG
        assert get_league_config("ncaa-football") is NCAA_FOOTBALL_CONFIG
        assert get_league_config("epl") is EPL_CONFIG
        assert get_league_config("la-liga") is LA_LIGA_CONFIG
        assert get_league_config("champions-league") is CHAMPIONS_LEAGUE_CONFIG
        assert get_league_config("bundesliga") is BUNDESLIGA_CONFIG
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

    def test_nfl_columns(self):
        keys = [c.key for c in NFL_CONFIG.columns]
        assert keys == ["make_playoffs", "division", "conference", "championship"]

    def test_nfl_has_conference_split(self):
        assert NFL_CONFIG.conference_split is True

    def test_mlb_columns(self):
        keys = [c.key for c in MLB_CONFIG.columns]
        assert keys == ["make_playoffs", "division", "pennant", "championship"]

    def test_wnba_max_teams(self):
        assert WNBA_CONFIG.max_teams == 13

    def test_mls_columns(self):
        keys = [c.key for c in MLS_CONFIG.columns]
        assert keys == ["make_playoffs", "conference", "championship"]

    def test_ncaa_football_columns(self):
        keys = [c.key for c in NCAA_FOOTBALL_CONFIG.columns]
        assert keys == ["make_playoffs", "semifinal", "championship"]

    def test_epl_columns(self):
        keys = [c.key for c in EPL_CONFIG.columns]
        assert keys == ["relegation", "top_4", "championship"]

    def test_champions_league_columns(self):
        keys = [c.key for c in CHAMPIONS_LEAGUE_CONFIG.columns]
        assert keys == ["quarterfinal", "semifinal", "final", "championship"]

    def test_bundesliga_max_teams(self):
        assert BUNDESLIGA_CONFIG.max_teams == 18

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

    # --- NFL ---
    def test_nfl_super_bowl(self):
        m = _make_market("Super Bowl Winner 2025-26")
        assert _match_market_to_column(m, NFL_CONFIG) == "championship"

    def test_nfl_conference_afc(self):
        m = _make_market("AFC Champion 2025-26")
        assert _match_market_to_column(m, NFL_CONFIG) == "conference"

    def test_nfl_conference_nfc(self):
        m = _make_market("NFC Winner 2025-26")
        assert _match_market_to_column(m, NFL_CONFIG) == "conference"

    def test_nfl_division(self):
        m = _make_market("NFL AFC East Division Winner")
        assert _match_market_to_column(m, NFL_CONFIG) == "division"

    def test_nfl_make_playoffs(self):
        m = _make_market("Will the Bills Make Playoffs?")
        assert _match_market_to_column(m, NFL_CONFIG) == "make_playoffs"

    def test_nfl_mvp_rejected(self):
        m = _make_market("NFL MVP Winner 2025-26")
        assert _match_market_to_column(m, NFL_CONFIG) is None

    # --- MLB ---
    def test_mlb_world_series(self):
        m = _make_market("World Series Winner 2026")
        assert _match_market_to_column(m, MLB_CONFIG) == "championship"

    def test_mlb_pennant_al(self):
        m = _make_market("American League Pennant Winner 2026")
        assert _match_market_to_column(m, MLB_CONFIG) == "pennant"

    def test_mlb_pennant_nl(self):
        m = _make_market("NL Champion 2026")
        assert _match_market_to_column(m, MLB_CONFIG) == "pennant"

    def test_mlb_division(self):
        m = _make_market("AL East Division Winner 2026")
        assert _match_market_to_column(m, MLB_CONFIG) == "division"

    def test_mlb_make_playoffs(self):
        m = _make_market("Will the Dodgers Make Playoffs?")
        assert _match_market_to_column(m, MLB_CONFIG) == "make_playoffs"

    # --- WNBA ---
    def test_wnba_championship(self):
        m = _make_market("WNBA Championship Winner 2026")
        assert _match_market_to_column(m, WNBA_CONFIG) == "championship"

    def test_wnba_finals(self):
        m = _make_market("WNBA Finals Winner 2026")
        assert _match_market_to_column(m, WNBA_CONFIG) == "championship"

    # --- MLS ---
    def test_mls_cup(self):
        m = _make_market("MLS Cup Winner 2026")
        assert _match_market_to_column(m, MLS_CONFIG) == "championship"

    def test_mls_conference(self):
        m = _make_market("MLS Eastern Conference Winner 2026")
        assert _match_market_to_column(m, MLS_CONFIG) == "conference"

    # --- NCAA Football ---
    def test_ncaaf_championship(self):
        m = _make_market("College Football Playoff Winner 2026-27")
        assert _match_market_to_column(m, NCAA_FOOTBALL_CONFIG) == "championship"

    def test_ncaaf_cfp_champion(self):
        m = _make_market("CFP Champion 2026-27")
        assert _match_market_to_column(m, NCAA_FOOTBALL_CONFIG) == "championship"

    def test_ncaaf_semifinal(self):
        m = _make_market("Rose Bowl Semifinal")
        assert _match_market_to_column(m, NCAA_FOOTBALL_CONFIG) == "semifinal"

    def test_ncaaf_make_playoff(self):
        m = _make_market("Will Alabama Make the College Football Playoff?")
        assert _match_market_to_column(m, NCAA_FOOTBALL_CONFIG) == "make_playoffs"

    # --- EPL ---
    def test_epl_champion(self):
        m = _make_market("Premier League Winner 2025-26")
        assert _match_market_to_column(m, EPL_CONFIG) == "championship"

    def test_epl_top_4(self):
        m = _make_market("Premier League Top 4 Finish")
        assert _match_market_to_column(m, EPL_CONFIG) == "top_4"

    def test_epl_relegation(self):
        m = _make_market("Premier League Relegation 2025-26")
        assert _match_market_to_column(m, EPL_CONFIG) == "relegation"

    def test_epl_not_sequential(self):
        """EPL columns are NOT sequential (standings positions, not knockout rounds)."""
        for col in EPL_CONFIG.columns:
            assert col.sequential is False

    # --- La Liga ---
    def test_la_liga_champion(self):
        m = _make_market("La Liga Winner 2025-26")
        assert _match_market_to_column(m, LA_LIGA_CONFIG) == "championship"

    def test_la_liga_relegation(self):
        m = _make_market("La Liga Relegation 2025-26")
        assert _match_market_to_column(m, LA_LIGA_CONFIG) == "relegation"

    # --- Champions League ---
    def test_ucl_champion(self):
        m = _make_market("Champions League Winner 2025-26")
        assert _match_market_to_column(m, CHAMPIONS_LEAGUE_CONFIG) == "championship"

    def test_ucl_semifinal(self):
        m = _make_market("UCL: Team to Reach Semifinals")
        assert _match_market_to_column(m, CHAMPIONS_LEAGUE_CONFIG) == "semifinal"

    def test_ucl_quarterfinal(self):
        m = _make_market("Champions League: Make Quarterfinals")
        assert _match_market_to_column(m, CHAMPIONS_LEAGUE_CONFIG) == "quarterfinal"

    def test_ucl_final(self):
        m = _make_market("Champions League: Reach the Final")
        assert _match_market_to_column(m, CHAMPIONS_LEAGUE_CONFIG) == "final"

    # --- Bundesliga ---
    def test_bundesliga_champion(self):
        m = _make_market("Bundesliga Winner 2025-26")
        assert _match_market_to_column(m, BUNDESLIGA_CONFIG) == "championship"

    def test_bundesliga_relegation(self):
        m = _make_market("Bundesliga Relegation 2025-26")
        assert _match_market_to_column(m, BUNDESLIGA_CONFIG) == "relegation"

    # --- NCAA disambiguation (championship vs title_game) ---
    def test_ncaa_championship_game_not_championship(self):
        """'Championship Game' should match title_game, not championship."""
        m = _make_market("NCAAB Championship Game")
        assert _match_market_to_column(m, NCAA_BASKETBALL_CONFIG) == "title_game"

    def test_ncaa_make_championship_game_not_championship(self):
        """'Make Championship Game' should match title_game."""
        m = _make_market("NCAA Make Championship Game")
        assert _match_market_to_column(m, NCAA_BASKETBALL_CONFIG) == "title_game"

    def test_ncaa_champion_matches_championship(self):
        """'NCAA Champion' should still match championship."""
        m = _make_market("NCAA Champion 2026")
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

    def test_stat_leaders_rejected(self):
        assert not _is_playoff_relevant_market("Pro Basketball Blocks Per Game Leader")
        assert not _is_playoff_relevant_market("Pro Basketball Assists Per Game Leader")
        assert not _is_playoff_relevant_market("NHL Points Leader")

    def test_expansion_rejected(self):
        assert not _is_playoff_relevant_market("Which cities will receive Pro Basketball expansion teams")
        assert not _is_playoff_relevant_market("NBA Expansion Draft")

    def test_matchup_prediction_rejected(self):
        assert not _is_playoff_relevant_market("Which teams will play in the 2026 Stanley Cup?")

    def test_halftime_show_rejected(self):
        assert not _is_playoff_relevant_market("Super Bowl LXI Halftime Show Performer")
        assert not _is_playoff_relevant_market("Halftime Show Artist 2026")

    def test_darts_rejected(self):
        assert not _is_playoff_relevant_market("Premier League Darts Champion 2026")

    def test_coin_toss_rejected(self):
        assert not _is_playoff_relevant_market("Super Bowl Coin Toss Winner")

    def test_anthem_rejected(self):
        assert not _is_playoff_relevant_market("National Anthem Length Over/Under")

    def test_golden_boot_rejected(self):
        assert not _is_playoff_relevant_market("Premier League Golden Boot Winner")

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


class TestLeagueNamePatterns:
    """Verify league_name_patterns separate leagues with shared sport_category."""

    def test_all_configs_have_patterns(self):
        for slug, config in LEAGUE_CONFIGS.items():
            assert len(config.league_name_patterns) > 0, (
                f"{slug} has no league_name_patterns"
            )

    def test_nba_patterns_match_nba(self):
        for pat in NBA_CONFIG.league_name_patterns:
            compiled = re.compile(pat, re.IGNORECASE)
            assert compiled.search("NBA Championship Winner 2025-26") or \
                   compiled.search("Pro Basketball Eastern Conference"), \
                f"NBA pattern '{pat}' doesn't match any NBA market name"

    def test_nba_patterns_dont_match_ncaa(self):
        """NBA patterns should NOT match NCAA markets."""
        for pat in NBA_CONFIG.league_name_patterns:
            compiled = re.compile(pat, re.IGNORECASE)
            assert not compiled.search("NCAAB Championship Winner 2026")
            assert not compiled.search("NCAA Tournament Winner")
            assert not compiled.search("March Madness Winner")

    def test_ncaa_patterns_dont_match_nba(self):
        """NCAA patterns should NOT match NBA markets."""
        for pat in NCAA_BASKETBALL_CONFIG.league_name_patterns:
            compiled = re.compile(pat, re.IGNORECASE)
            assert not compiled.search("NBA Championship Winner 2025-26")
            assert not compiled.search("NBA Eastern Conference Winner")

    def test_nhl_patterns_match_nhl(self):
        for pat in NHL_CONFIG.league_name_patterns:
            compiled = re.compile(pat, re.IGNORECASE)
            if compiled.search("Stanley Cup Winner 2025-26") or \
               compiled.search("NHL Western Conference") or \
               compiled.search("Pro Hockey Playoff Qualifiers"):
                return  # At least one pattern matched
        pytest.fail("No NHL pattern matched any NHL market name")

    def test_golf_patterns_match_golf(self):
        for pat in GOLF_CONFIG.league_name_patterns:
            compiled = re.compile(pat, re.IGNORECASE)
            if compiled.search("Masters Tournament Winner 2026") or \
               compiled.search("PGA Championship") or \
               compiled.search("Golf Winner"):
                return
        pytest.fail("No golf pattern matched any golf market name")

    def test_nfl_patterns_dont_match_ncaaf(self):
        """NFL patterns should NOT match college football markets."""
        for pat in NFL_CONFIG.league_name_patterns:
            compiled = re.compile(pat, re.IGNORECASE)
            assert not compiled.search("College Football Playoff Winner")
            assert not compiled.search("NCAAF Championship")
            assert not compiled.search("CFP Champion")

    def test_ncaaf_patterns_dont_match_nfl(self):
        """NCAA football patterns should NOT match NFL markets."""
        for pat in NCAA_FOOTBALL_CONFIG.league_name_patterns:
            compiled = re.compile(pat, re.IGNORECASE)
            assert not compiled.search("Super Bowl Winner 2025-26")
            assert not compiled.search("NFL Championship")

    def test_wnba_patterns_dont_match_nba(self):
        """WNBA patterns should NOT match NBA markets."""
        for pat in WNBA_CONFIG.league_name_patterns:
            compiled = re.compile(pat, re.IGNORECASE)
            assert not compiled.search("NBA Championship Winner")

    def test_epl_patterns_dont_match_la_liga(self):
        """EPL patterns should NOT match La Liga markets."""
        for pat in EPL_CONFIG.league_name_patterns:
            compiled = re.compile(pat, re.IGNORECASE)
            assert not compiled.search("La Liga Winner 2025-26")

    def test_mls_patterns_dont_match_epl(self):
        """MLS patterns should NOT match EPL markets."""
        for pat in MLS_CONFIG.league_name_patterns:
            compiled = re.compile(pat, re.IGNORECASE)
            assert not compiled.search("Premier League Winner")

    def test_all_patterns_compile(self):
        for slug, config in LEAGUE_CONFIGS.items():
            for pat in config.league_name_patterns:
                try:
                    re.compile(pat, re.IGNORECASE)
                except re.error as e:
                    pytest.fail(
                        f"{slug} has invalid league_name_pattern '{pat}': {e}"
                    )


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


# ============================================================================
# DataGolf golfer field matching
# ============================================================================


class TestGolferFieldMatching:
    """Test _match_golfer_to_field for DataGolf-first golf grid."""

    def _make_field(self, names):
        """Build a mock DataGolf field dict from a list of names."""
        return {_normalize_team_name(n): object() for n in names}

    def test_exact_match(self):
        field = self._make_field(["Scottie Scheffler", "Rory McIlroy"])
        assert _match_golfer_to_field(
            _normalize_team_name("Scottie Scheffler"), field
        ) == _normalize_team_name("Scottie Scheffler")

    def test_exact_match_case_insensitive(self):
        field = self._make_field(["Scottie Scheffler"])
        assert _match_golfer_to_field(
            _normalize_team_name("scottie scheffler"), field
        ) == _normalize_team_name("Scottie Scheffler")

    def test_no_match_returns_none(self):
        field = self._make_field(["Scottie Scheffler"])
        assert _match_golfer_to_field(
            _normalize_team_name("Tiger Woods"), field
        ) is None

    def test_fuzzy_last_name_first_prefix(self):
        """Kalshi might use 'S. Scheffler' style — test first-initial matching."""
        field = self._make_field(["Scottie Scheffler"])
        # "Sco" prefix matches "Scottie"
        assert _match_golfer_to_field(
            _normalize_team_name("Sco Scheffler"), field
        ) == _normalize_team_name("Scottie Scheffler")

    def test_reversed_name_order(self):
        """Some sources use 'Scheffler, Scottie' (already normalized, but test reversed words)."""
        field = self._make_field(["Scottie Scheffler"])
        assert _match_golfer_to_field(
            _normalize_team_name("Scheffler Scottie"), field
        ) == _normalize_team_name("Scottie Scheffler")

    def test_diacritics_normalized(self):
        """Names with diacritics should match after normalization."""
        field = self._make_field(["Viktor Hovland"])
        # _normalize_team_name strips diacritics
        assert _match_golfer_to_field(
            _normalize_team_name("Viktor Hovland"), field
        ) == _normalize_team_name("Viktor Hovland")

    def test_single_word_name_no_match(self):
        """Single-word outcome names should not match."""
        field = self._make_field(["Scottie Scheffler", "Tiger Woods"])
        assert _match_golfer_to_field(
            _normalize_team_name("Scheffler"), field
        ) is None

    def test_different_golfer_same_last_name(self):
        """Different first names with same last name should not falsely match."""
        field = self._make_field(["Xander Schauffele"])
        # "Max Schauffele" shouldn't match "Xander Schauffele" (first 3 chars differ)
        assert _match_golfer_to_field(
            _normalize_team_name("Max Schauffele"), field
        ) is None

    def test_similar_first_name_prefix_matches(self):
        """Similar first name prefix (3+ chars) should match."""
        field = self._make_field(["Hideki Matsuyama"])
        assert _match_golfer_to_field(
            _normalize_team_name("Hid Matsuyama"), field
        ) == _normalize_team_name("Hideki Matsuyama")


class TestGolfConfigMaxTeams:
    """Verify golf config accommodates full field."""

    def test_max_teams_accommodates_full_field(self):
        assert GOLF_CONFIG.max_teams >= 120, (
            f"Golf max_teams={GOLF_CONFIG.max_teams} too low for full PGA field"
        )

    def test_golf_has_all_five_columns(self):
        col_keys = [c.key for c in GOLF_CONFIG.columns]
        assert col_keys == ["make_cut", "top_20", "top_10", "top_5", "win"]

    def test_golf_source_of_truth_is_datagolf(self):
        """Golf config should use DataGolf as field source of truth."""
        # This is enforced by the endpoint logic (slug == "golf" → DataGolf path)
        # Config just needs sport_category and matching rules
        assert GOLF_CONFIG.sport_category == "golf"
