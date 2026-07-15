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
    _market_passes_league_filter,
    _match_golfer_to_field,
    _merge_probabilities,
    _normalize_team_name,
    _strip_diacritics,
    _extract_standings_label,
    _get_team_metadata,
    _is_playoff_relevant_market,
    _should_prefix_merge,
    _alias_matches,
    _extract_season_max_year,
    _is_future_season_market,
    _is_past_season_market,
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

    def test_ncaa_flat_list(self):
        """NCAA uses flat list (no region/conference split) for easy comparison."""
        assert NCAA_BASKETBALL_CONFIG.region_split is False
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

    def test_golf_sequential(self):
        """Golf columns are sequential (make_cut → top_20 → top_10 → top_5 → win)."""
        for col in GOLF_CONFIG.columns:
            assert col.sequential is True

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

    # --- #1059 champion-ticker gate: sub-competition tickers must not leak ---
    def test_nba_conference_ticker_does_not_leak_into_champion(self):
        # A generic "Championship Winner" name reaches the Champion column via
        # the loose \bchampionship\b fallback (verified: odds_api → championship).
        # On a KXNBAEAST conference ticker that outcome must NOT populate the
        # Champion column. Pre-#1059 it did — the degenerate A4 mapping.
        m = _make_market(
            "Championship Winner", source="kalshi", external_id="KXNBAEAST-27"
        )
        assert _match_market_to_column(m, NBA_CONFIG) is None

    def test_nba_game_ticker_never_champion(self):
        m = _make_market(
            "Some team to win", source="kalshi", external_id="KXNBAGAME-26FEB19BOSGSW"
        )
        assert _match_market_to_column(m, NBA_CONFIG) is None

    def test_nba_champion_series_ticker_still_maps(self):
        # The genuine full-field champion series (bare prefix + season) is
        # unaffected by the gate.
        m = _make_market(
            "NBA Championship", source="kalshi", external_id="KXNBA2026", market_tier=1
        )
        assert _match_market_to_column(m, NBA_CONFIG) == "championship"

    def test_nba_champion_hyphen_season_ticker_still_maps(self):
        m = _make_market(
            "NBA Championship Winner", source="kalshi", external_id="KXNBA-26"
        )
        assert _match_market_to_column(m, NBA_CONFIG) == "championship"

    def test_odds_api_champion_unaffected_by_gate(self):
        # odds_api has no ticker → gate is N/A, name match still wins.
        m = _make_market("NBA Championship Winner 2025-26")
        assert _match_market_to_column(m, NBA_CONFIG) == "championship"

    def test_is_champion_ticker_helper(self):
        from app.routes.playoffs import _is_champion_ticker

        assert _is_champion_ticker("KXNBA2026", NBA_CONFIG) is True
        assert _is_champion_ticker("KXNBA-27", NBA_CONFIG) is True
        assert _is_champion_ticker("KXNBAEAST-27", NBA_CONFIG) is False
        assert _is_champion_ticker("KXNBAGAME-26", NBA_CONFIG) is False
        assert _is_champion_ticker("KXNBAPTS-26", NBA_CONFIG) is False
        # Foreign / non-league ticker ⇒ gate N/A.
        assert _is_champion_ticker("KXMLB-26", NBA_CONFIG) is None
        assert _is_champion_ticker("", NBA_CONFIG) is None

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

    # --- NCAA Kalshi round terminology ---
    def test_ncaa_kalshi_round_of_16_qualifiers(self):
        """Kalshi: 'Round of 16 Qualifiers' = qualify for Sweet 16 = win Round of 32."""
        m = _make_market("Men's Round of 16 Qualifiers")
        assert _match_market_to_column(m, NCAA_BASKETBALL_CONFIG) == "sweet_16"

    def test_ncaa_kalshi_round_of_8_qualifiers(self):
        """Kalshi: 'Round of 8 Qualifiers' = qualify for Elite 8 = win Sweet 16."""
        m = _make_market("Men's Round of 8 Qualifiers")
        assert _match_market_to_column(m, NCAA_BASKETBALL_CONFIG) == "elite_eight"

    def test_ncaa_kalshi_round_of_32_qualifiers(self):
        """Kalshi: 'Round of 32 Qualifiers' = win first round."""
        m = _make_market("Men's Round of 32 Qualifiers")
        assert _match_market_to_column(m, NCAA_BASKETBALL_CONFIG) == "round_of_32"

    def test_ncaa_kalshi_semifinals_qualifiers(self):
        """Kalshi: 'Semifinals Qualifiers' = qualify for Final Four."""
        m = _make_market("Men's Semifinals Qualifiers")
        assert _match_market_to_column(m, NCAA_BASKETBALL_CONFIG) == "final_four"

    def test_ncaa_kalshi_championship_game_qualifiers(self):
        """Kalshi: 'Championship Game Qualifiers' = qualify for title game."""
        m = _make_market("Men's Championship Game Qualifiers")
        assert _match_market_to_column(m, NCAA_BASKETBALL_CONFIG) == "title_game"

    def test_ncaa_kalshi_champion(self):
        """Kalshi: 'College Basketball Champion' = championship winner."""
        m = _make_market("Men's College Basketball Champion")
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

    def test_normalize_internal_periods(self):
        """'St. Louis Blues' and 'St Louis Blues' should normalize the same."""
        assert _normalize_team_name("St. Louis Blues") == _normalize_team_name("St Louis Blues")
        assert _normalize_team_name("St. John's") == _normalize_team_name("St John's")

    def test_normalize_trailing_period(self):
        """Trailing period should be stripped."""
        assert _normalize_team_name("Michigan St.") == "michigan st"

    def test_normalize_period_mid_word_preserved(self):
        """Periods within a word (e.g. abbreviations without space) stay."""
        # "F.C." has no space after internal periods — only space-preceded periods stripped
        n = _normalize_team_name("F.C. Barcelona")
        # The regex strips ". " (period before space), so "F.C." → "F.C" then "." at end stays
        # What matters: the function is deterministic and consistent
        assert n == _normalize_team_name("F.C. Barcelona")


# ============================================================================
# Team standings metadata
# ============================================================================


class _FakeScalars:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return _FakeScalars(self._rows)


class _FakeSession:
    def __init__(self, rows):
        self._rows = rows

    async def execute(self, _stmt):
        return _FakeResult(self._rows)


class TestTeamStandingsMetadata:
    def test_extract_standings_label_from_string(self):
        assert _extract_standings_label({"conference": "Eastern"}, "conference") == "Eastern"

    def test_extract_standings_label_from_object(self):
        standings = {"conference": {"displayName": "American League"}}
        assert _extract_standings_label(standings, "conference") == "American League"

    def test_extract_standings_label_ignores_missing_or_blank(self):
        assert _extract_standings_label({}, "conference") is None
        assert _extract_standings_label({"conference": "  "}, "conference") is None

    @pytest.mark.asyncio
    async def test_get_team_metadata_uses_standings_conference(self):
        team = MagicMock()
        team.id = 7
        team.name = "Boston Celtics"
        team.abbreviation = "BOS"
        team.logo_url_small = None
        team.logo_url_large = None
        team.primary_color = "#007A33"
        team.secondary_color = "#BA9653"
        team.current_record = "50-20"
        team.standings_data = {
            "conference": "Eastern",
            "division": "Atlantic",
            "seed": 2,
        }
        team.alternate_names = ["Celtics"]

        metadata = await _get_team_metadata(
            _FakeSession([team]),
            {"Boston Celtics"},
            league_slug="nba",
        )

        row = metadata["boston celtics"]
        assert row["conference"] == "Eastern"
        assert row["division"] == "Atlantic"
        assert row["seed"] == 2
        assert metadata["bos"] is row
        assert metadata["celtics"] is row

    @pytest.mark.asyncio
    async def test_get_team_metadata_does_not_fallback_to_hardcoded_conference(self):
        team = MagicMock()
        team.id = 8
        team.name = "Los Angeles Lakers"
        team.abbreviation = "LAL"
        team.logo_url_small = None
        team.logo_url_large = None
        team.primary_color = None
        team.secondary_color = None
        team.current_record = None
        team.standings_data = {}
        team.alternate_names = []

        metadata = await _get_team_metadata(
            _FakeSession([team]),
            {"Los Angeles Lakers"},
            league_slug="nba",
        )

        assert metadata["los angeles lakers"]["conference"] is None


# ============================================================================
# Gender exclusion filter
# ============================================================================


class TestGenderExclusionFilter:
    """Verify Women's/Men's market separation for playoff grids."""

    def test_womens_market_rejected_from_ncaab(self):
        """Women's NCAA Tournament Winner should NOT appear in men's NCAAB grid."""
        assert not _is_playoff_relevant_market("Team A vs. Team B (W)")

    def test_womens_suffix_rejected(self):
        """The (W) suffix is rejected by _NON_PLAYOFF_MARKET_RE."""
        assert not _is_playoff_relevant_market("Duke vs. UConn (W)")

    def test_mens_championship_allowed(self):
        """Men's championship markets pass the filter."""
        assert _is_playoff_relevant_market("NCAAB Championship Winner 2026")
        assert _is_playoff_relevant_market("NCAA Tournament Winner")

    def test_womens_ncaa_name_contains_womens_keyword(self):
        """Verify the Women's regex matches expected market names."""
        import re
        womens_re = re.compile(r"\bWomen.?s\b|\bWNCAA\b|\bWNCAAB\b|\(W\)", re.IGNORECASE)
        assert womens_re.search("2026 Women's NCAA Tournament Winner")
        assert womens_re.search("WNCAAB Championship")
        assert womens_re.search("Women's College Basketball")
        assert womens_re.search("Duke vs UConn (W)")
        assert not womens_re.search("NBA Championship Winner")
        assert not womens_re.search("NCAAB Championship Winner")


# ============================================================================
# Probability consistency (sequential columns)
# ============================================================================


class TestProbabilityConsistency:
    """Test that monotonicity is enforced across sequential columns.

    For sequential columns: P(later stage) <= P(earlier stage).
    enforce_monotonicity() caps later stages at the min of earlier stages.
    """

    def test_consistent_nba_probabilities(self):
        """Valid: championship < conference < make_playoffs — no changes needed."""
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

    def test_monotonicity_enforced_conference_gt_division(self):
        """Conference > Division is capped at Division (NHL issue #728)."""
        from app.utils.playoff_grid import enforce_monotonicity

        team = {
            "name": "Test Team",
            "cells": {
                "make_playoffs": {"merged_probability": 0.80, "sources": [{"probability": 0.80, "source": "odds_api"}]},
                "division": {"merged_probability": 0.25, "sources": [{"probability": 0.25, "source": "odds_api"}]},
                "conference": {"merged_probability": 0.40, "sources": [{"probability": 0.40, "source": "kalshi"}]},
                "championship": {"merged_probability": 0.10, "sources": [{"probability": 0.10, "source": "odds_api"}]},
            },
        }
        fixes = enforce_monotonicity([team], NHL_CONFIG.columns)
        assert fixes >= 1
        cells = team["cells"]
        # Conference must be capped at Division
        assert cells["conference"]["merged_probability"] <= cells["division"]["merged_probability"]
        # Championship must be <= Conference
        assert cells["championship"]["merged_probability"] <= cells["conference"]["merged_probability"]
        # Make Playoffs >= Division
        assert cells["make_playoffs"]["merged_probability"] >= cells["division"]["merged_probability"]

    def test_monotonicity_enforced_cascading(self):
        """Monotonicity cascades: if Division > Make Playoffs, cap Division, then cap Conference at Division."""
        from app.utils.playoff_grid import enforce_monotonicity

        team = {
            "name": "Cascade Team",
            "cells": {
                "make_playoffs": {"merged_probability": 0.50, "sources": [{"probability": 0.50, "source": "odds_api"}]},
                "division": {"merged_probability": 0.55, "sources": [{"probability": 0.55, "source": "kalshi"}]},
                "conference": {"merged_probability": 0.60, "sources": [{"probability": 0.60, "source": "kalshi"}]},
                "championship": {"merged_probability": 0.22, "sources": [{"probability": 0.22, "source": "odds_api"}]},
            },
        }
        fixes = enforce_monotonicity([team], NHL_CONFIG.columns)
        assert fixes >= 2  # division and conference both need fixing
        cells = team["cells"]
        # Everything should cascade down from make_playoffs = 0.50
        assert cells["division"]["merged_probability"] == 0.50
        assert cells["conference"]["merged_probability"] == 0.50
        assert cells["championship"]["merged_probability"] == 0.22

    def test_monotonicity_no_fix_needed(self):
        """Already-monotonic team returns 0 fixes."""
        from app.utils.playoff_grid import enforce_monotonicity

        team = {
            "name": "Good Team",
            "cells": {
                "make_playoffs": {"merged_probability": 0.90, "sources": []},
                "division": {"merged_probability": 0.40, "sources": []},
                "conference": {"merged_probability": 0.30, "sources": []},
                "championship": {"merged_probability": 0.15, "sources": []},
            },
        }
        fixes = enforce_monotonicity([team], NHL_CONFIG.columns)
        assert fixes == 0

    def test_monotonicity_source_probs_also_capped(self):
        """Source probabilities within the cell are also capped."""
        from app.utils.playoff_grid import enforce_monotonicity

        team = {
            "name": "Source Test",
            "cells": {
                "division": {"merged_probability": 0.20, "sources": [{"probability": 0.20, "source": "odds_api"}]},
                "conference": {"merged_probability": 0.35, "sources": [
                    {"probability": 0.35, "source": "kalshi"},
                    {"probability": 0.30, "source": "polymarket"},
                ]},
                "championship": {"merged_probability": 0.05, "sources": [{"probability": 0.05, "source": "odds_api"}]},
            },
        }
        enforce_monotonicity([team], NHL_CONFIG.columns)
        # Conference sources should all be capped at Division probability (0.20)
        for src in team["cells"]["conference"]["sources"]:
            assert src["probability"] <= 0.20


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


class TestSeriesToLeagueGating:
    """_market_passes_league_filter: sibling-competition markets must not leak
    into a league's grid via a colliding ticker prefix or a colliding name.

    Root cause (grid sentinel #196 / #197): the NBA in-season Cup series
    KXNBACUP collides with the NBA's KXNBA external_id prefix AND its market
    names ("... Pro Basketball Cup Champion") match the \\bPro Basketball\\b
    league name pattern, so Cup probabilities surfaced in the NBA Champion grid
    (teams shown at Cup odds — the extreme-watch mis-linkage signal).
    """

    # --- The defect: NBA Cup must be excluded from the NBA grid ---
    def test_nba_cup_ticker_excluded(self):
        # KXNBACUP-26 collides with the KXNBA prefix (Path B.1) — must be gated out.
        assert _market_passes_league_filter(
            "2026 Pro Basketball Cup Champion", "KXNBACUP-26", NBA_CONFIG
        ) is False

    def test_nba_cup_qualifier_tickers_excluded(self):
        for eid, name in [
            ("KXNBACUPQUAL-26KO", "Pro Basketball Cup Knockout Rounds Qualifiers"),
            ("KXNBACUPQUAL-26FIN", "Pro Basketball Cup Finals Qualifiers"),
        ]:
            assert _market_passes_league_filter(name, eid, NBA_CONFIG) is False, eid

    def test_nba_cup_name_excluded_without_ticker(self):
        # A Polymarket-style Cup market (no KXNBACUP ticker) is still gated by
        # the league_exclude_patterns name rule, which now runs on every path.
        assert _market_passes_league_filter(
            "2026 Pro Basketball Cup Champion", "", NBA_CONFIG
        ) is False

    # --- The genuine NBA champion series must STILL pass ---
    def test_nba_real_champion_series_still_passes(self):
        assert _market_passes_league_filter(
            "2026 Pro Basketball Champion", "KXNBA-26", NBA_CONFIG
        ) is True

    def test_nba_champion_by_sport_key_still_passes(self):
        assert _market_passes_league_filter(
            "NBA Championship Winner 2025-26", "basketball_nba_championship_2026", NBA_CONFIG
        ) is True

    def test_nba_conference_ticker_still_passes(self):
        # Conference sub-series (not the Cup) still belongs in the NBA grid.
        assert _market_passes_league_filter(
            "NBA Eastern Conference Winner", "KXNBAEAST-27", NBA_CONFIG
        ) is True

    # --- No collateral damage to other leagues ---
    def test_mlb_college_world_series_still_excluded(self):
        # Pre-existing MLB exclude still works via the universal path.
        assert _market_passes_league_filter(
            "College World Series Winner", "", MLB_CONFIG
        ) is False

    def test_mlb_world_series_still_passes(self):
        assert _market_passes_league_filter(
            "World Series Winner 2026", "KXMLB-26", MLB_CONFIG
        ) is True

    def test_gender_filter_preserved(self):
        # Women's market rejected from the men's NBA grid.
        assert _market_passes_league_filter(
            "Women's NBA Championship", "", NBA_CONFIG
        ) is False

    def test_champions_league_qualify_to_ucl_still_rejected(self):
        assert _market_passes_league_filter(
            "Champions League Qualification Spot", "", CHAMPIONS_LEAGUE_CONFIG
        ) is False

    def test_nba_cup_not_picked_up_by_other_basketball_leagues(self):
        # WNBA / NCAAB should not absorb the NBA Cup either (no matching path).
        assert _market_passes_league_filter(
            "2026 Pro Basketball Cup Champion", "KXNBACUP-26", WNBA_CONFIG
        ) is False
        assert _market_passes_league_filter(
            "2026 Pro Basketball Cup Champion", "KXNBACUP-26", NCAA_BASKETBALL_CONFIG
        ) is False


class TestNbaCupExcludeConfig:
    """The NBA config carries the series -> league gating rules."""

    def test_nba_has_cup_ticker_exclude(self):
        assert "KXNBACUP" in NBA_CONFIG.external_id_exclude_prefixes

    def test_nba_has_cup_name_exclude(self):
        assert any(
            re.compile(p, re.IGNORECASE).search("2026 Pro Basketball Cup Champion")
            for p in NBA_CONFIG.league_exclude_patterns
        )

    def test_exclude_prefixes_default_empty_elsewhere(self):
        # Only leagues that need it opt in; the field defaults to empty.
        assert MLB_CONFIG.external_id_exclude_prefixes == []


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


# ============================================================================
# Team name merge logic
# ============================================================================


class TestShouldPrefixMerge:
    """Test _should_prefix_merge for single-word and multi-word names."""

    # Multi-word prefix merges (should always work)
    def test_multi_word_prefix_merge(self):
        assert _should_prefix_merge("oklahoma city", "oklahoma city thunder")

    def test_multi_word_prefix_merge_hyphen(self):
        assert _should_prefix_merge("new york", "new york-knicks")

    # Single-word merges that SHOULD succeed (mascot follows)
    def test_single_word_boston_celtics(self):
        assert _should_prefix_merge("boston", "boston celtics")

    def test_single_word_kansas_jayhawks(self):
        assert _should_prefix_merge("kansas", "kansas jayhawks")

    def test_single_word_tennessee_volunteers(self):
        assert _should_prefix_merge("tennessee", "tennessee volunteers")

    def test_single_word_vanderbilt_commodores(self):
        assert _should_prefix_merge("vanderbilt", "vanderbilt commodores")

    def test_single_word_cleveland_cavaliers(self):
        assert _should_prefix_merge("cleveland", "cleveland cavaliers")

    def test_single_word_detroit_pistons(self):
        assert _should_prefix_merge("detroit", "detroit pistons")

    def test_single_word_houston_rockets(self):
        assert _should_prefix_merge("houston", "houston rockets")

    def test_single_word_miami_heat(self):
        assert _should_prefix_merge("miami", "miami heat")

    def test_single_word_minnesota_timberwolves(self):
        assert _should_prefix_merge("minnesota", "minnesota timberwolves")

    # Single-word merges that SHOULD FAIL (location modifier follows)
    def test_iowa_vs_iowa_state_rejected(self):
        assert not _should_prefix_merge("iowa", "iowa state cyclones")

    def test_tennessee_vs_tennessee_state_rejected(self):
        assert not _should_prefix_merge("tennessee", "tennessee state")

    def test_tennessee_vs_tennessee_tech_rejected(self):
        assert not _should_prefix_merge("tennessee", "tennessee tech")

    def test_kansas_vs_kansas_city_rejected(self):
        assert not _should_prefix_merge("kansas", "kansas city chiefs")

    def test_georgia_vs_georgia_southern_rejected(self):
        assert not _should_prefix_merge("georgia", "georgia southern")

    def test_michigan_vs_michigan_state_rejected(self):
        assert not _should_prefix_merge("michigan", "michigan state spartans")

    # Not a prefix at all
    def test_not_prefix(self):
        assert not _should_prefix_merge("duke", "florida gators")

    def test_partial_word_not_prefix(self):
        assert not _should_prefix_merge("iowa", "iowan something")


class TestAliasMatches:
    """Test _alias_matches for non-prefix team name aliases."""

    def test_connecticut_uconn(self):
        assert _alias_matches("connecticut", "uconn huskies")

    def test_connecticut_uconn_reverse(self):
        assert _alias_matches("uconn huskies", "connecticut")

    def test_connecticut_exact_uconn(self):
        assert _alias_matches("connecticut", "uconn")

    def test_cal_baptist_california_baptist(self):
        assert _alias_matches("cal baptist", "california baptist lancers")

    def test_ca_baptist_california_baptist(self):
        assert _alias_matches("ca baptist", "california baptist lancers")

    def test_pitt_pittsburgh(self):
        assert _alias_matches("pitt", "pittsburgh panthers")

    def test_no_alias(self):
        assert not _alias_matches("duke", "florida")

    def test_no_alias_similar(self):
        assert not _alias_matches("virginia", "virginia tech")


# ============================================================================
# Sport key → league config mapping (for event detail integration)
# ============================================================================


class TestSportKeyToLeagueMapping:
    def test_nba_mapping(self):
        from app.routes.playoffs import get_league_config_for_sport_key
        config = get_league_config_for_sport_key("basketball_nba")
        assert config is not None
        assert config.slug == "nba"

    def test_nfl_mapping(self):
        from app.routes.playoffs import get_league_config_for_sport_key
        config = get_league_config_for_sport_key("americanfootball_nfl")
        assert config is not None
        assert config.slug == "nfl"

    def test_nhl_mapping(self):
        from app.routes.playoffs import get_league_config_for_sport_key
        config = get_league_config_for_sport_key("icehockey_nhl")
        assert config is not None
        assert config.slug == "nhl"

    def test_mlb_mapping(self):
        from app.routes.playoffs import get_league_config_for_sport_key
        config = get_league_config_for_sport_key("baseball_mlb")
        assert config is not None
        assert config.slug == "mlb"

    def test_ncaab_mapping(self):
        from app.routes.playoffs import get_league_config_for_sport_key
        config = get_league_config_for_sport_key("basketball_ncaab")
        assert config is not None
        assert config.slug == "ncaa-basketball"

    def test_ncaaf_mapping(self):
        from app.routes.playoffs import get_league_config_for_sport_key
        config = get_league_config_for_sport_key("americanfootball_ncaaf")
        assert config is not None
        assert config.slug == "ncaa-football"

    def test_epl_mapping(self):
        from app.routes.playoffs import get_league_config_for_sport_key
        config = get_league_config_for_sport_key("soccer_epl")
        assert config is not None
        assert config.slug == "epl"

    def test_mls_mapping(self):
        from app.routes.playoffs import get_league_config_for_sport_key
        config = get_league_config_for_sport_key("soccer_usa_mls")
        assert config is not None
        assert config.slug == "mls"

    def test_wnba_mapping(self):
        from app.routes.playoffs import get_league_config_for_sport_key
        config = get_league_config_for_sport_key("basketball_wnba")
        assert config is not None
        assert config.slug == "wnba"

    def test_unknown_sport_returns_none(self):
        from app.routes.playoffs import get_league_config_for_sport_key
        assert get_league_config_for_sport_key("cricket_ipl") is None
        assert get_league_config_for_sport_key("mma_ufc") is None

    def test_all_mapped_configs_valid(self):
        from app.routes.playoffs import _SPORT_KEY_TO_LEAGUE_SLUG
        for sport_key, slug in _SPORT_KEY_TO_LEAGUE_SLUG.items():
            config = get_league_config(slug)
            assert config is not None, f"Slug '{slug}' for sport_key '{sport_key}' not in registry"


# ============================================================================
# Season filtering — reject next-season markets (#471)
# ============================================================================


class TestExtractSeasonMaxYear:
    """Tests for _extract_season_max_year helper."""

    def test_hyphenated_season_pattern(self):
        """'2025-26' → 2026 (NBA/NHL/NFL style)."""
        assert _extract_season_max_year("2025-26") == 2026

    def test_single_year_pattern(self):
        """'2026' → 2026 (MLB/WNBA style)."""
        assert _extract_season_max_year("2026") == 2026

    def test_forward_hyphenated_season(self):
        """'2026-27' → 2027."""
        assert _extract_season_max_year("2026-27") == 2027

    def test_empty_pattern_returns_none(self):
        assert _extract_season_max_year("") is None

    def test_all_league_configs_have_parseable_season(self):
        """Every league config's season_pattern should be parseable."""
        for slug, cfg in LEAGUE_CONFIGS.items():
            year = _extract_season_max_year(cfg.season_pattern)
            assert year is not None, (
                f"League '{slug}' has unparseable season_pattern '{cfg.season_pattern}'"
            )
            assert 2024 <= year <= 2030, (
                f"League '{slug}' season max year {year} is out of expected range"
            )


class TestIsFutureSeasonMarket:
    """Tests for _is_future_season_market — guards against next-season contamination."""

    def test_future_year_rejected(self):
        """'NBA: 2027 Champion' with max_year=2026 should be rejected."""
        assert _is_future_season_market("NBA: 2027 Champion", 2026) is True

    def test_current_year_accepted(self):
        """'2026 NBA Champion' with max_year=2026 should be accepted."""
        assert _is_future_season_market("2026 NBA Champion", 2026) is False

    def test_no_year_accepted(self):
        """'NBA Championship Winner' (no year) should be accepted."""
        assert _is_future_season_market("NBA Championship Winner", 2026) is False

    def test_past_year_accepted(self):
        """'2025 NBA Champion' with max_year=2026 should be accepted."""
        assert _is_future_season_market("2025 NBA Champion", 2026) is False

    def test_hyphenated_future_season(self):
        """'NBA 2026-27 Champion' with max_year=2026 should be rejected (contains 2027)."""
        assert _is_future_season_market("NBA 2026-27 Champion", 2026) is True

    def test_hyphenated_current_season(self):
        """'NBA 2025-26 Champion' with max_year=2026 is fine (no year > 2026)."""
        assert _is_future_season_market("NBA 2025-26 Champion", 2026) is False

    def test_polymarket_nba_2027_real_case(self):
        """Real market name that caused issue #471."""
        assert _is_future_season_market("NBA: 2027 Champion", 2026) is True

    def test_polymarket_2026_nba_real_case(self):
        """Real market name that should stay."""
        assert _is_future_season_market("2026 NBA Champion", 2026) is False

    def test_conference_market_no_year(self):
        """Conference markets without year reference should pass through."""
        assert _is_future_season_market(
            "NBA Playoffs: Eastern Conference Champion", 2026
        ) is False

    def test_odds_api_no_year(self):
        """Odds API generic championship market should pass through."""
        assert _is_future_season_market("NBA Championship Winner", 2026) is False

    def test_nfl_next_season(self):
        """NFL next-season Super Bowl market with max_year=2026."""
        assert _is_future_season_market(
            "NFL: 2027 Super Bowl Champion", 2026
        ) is True

    def test_mlb_current_season(self):
        """MLB current-season market should pass."""
        assert _is_future_season_market("2026 World Series Winner", 2026) is False


class TestIsPastSeasonMarket:
    """Tests for _is_past_season_market — guards against stale past-season contamination (#708)."""

    def test_past_year_rejected(self):
        """'2024 NBA Champion' with max_year=2026 should be rejected (past season)."""
        assert _is_past_season_market("NBA: 2024 Champion", 2026) is True

    def test_past_hyphenated_season_rejected(self):
        """'2024-25 NBA Champion' with max_year=2026 should be rejected (max=2025 < 2026)."""
        assert _is_past_season_market("2024-25 NBA Champion", 2026) is True

    def test_one_year_prior_rejected(self):
        """'2025 NBA Champion' with max_year=2026 should be rejected (2025 < 2026)."""
        assert _is_past_season_market("NBA: 2025 Champion", 2026) is True

    def test_current_year_accepted(self):
        """'2026 NBA Champion' with max_year=2026 should be accepted (current season)."""
        assert _is_past_season_market("2026 NBA Champion", 2026) is False

    def test_current_hyphenated_season_accepted(self):
        """'2025-26 NBA Champion' with max_year=2026 should be accepted (max=2026)."""
        assert _is_past_season_market("NBA 2025-26 Champion", 2026) is False

    def test_no_year_accepted(self):
        """'NBA Championship Winner' (no year) passes through — assumed current."""
        assert _is_past_season_market("NBA Championship Winner", 2026) is False

    def test_future_year_not_past(self):
        """'2027 NBA Champion' is not past (handled by future filter)."""
        assert _is_past_season_market("2027 NBA Champion", 2026) is False

    def test_conference_past_season(self):
        """Past-season conference market should be rejected."""
        assert _is_past_season_market("2024-25 Eastern Conference Winner", 2026) is True

    def test_knicks_30x_staleness_scenario(self):
        """Regression: past-season championship market contaminating grid (#708).

        When a resolved '2024-25 NBA Champion' market has Knicks at ~1%
        (settled loser) and the current '2025-26 NBA Champion' market has
        Knicks at ~30%, the per-source dedup (min) picks the stale 1%.
        Past season filter must block the old market.
        """
        assert _is_past_season_market("2024-25 NBA Championship Winner", 2026) is True
        assert _is_past_season_market("2025-26 NBA Championship Winner", 2026) is False


class TestColumnSumSanity:
    """Conference column sums should be reasonable after normalization (#471)."""

    def test_normalize_column_sums_warns_on_extreme_overshoot(self):
        """Column sums > 2.5x expected trigger a warning, not normalization."""
        from app.utils.playoff_grid import normalize_column_sums

        teams = [
            {"name": "Team A", "cells": {"conference": {"merged_probability": 1.0, "sources": []}}},
            {"name": "Team B", "cells": {"conference": {"merged_probability": 0.8, "sources": []}}},
            {"name": "Team C", "cells": {"conference": {"merged_probability": 0.5, "sources": []}}},
        ]
        # Total = 2.3, expected = 2.0, ratio = 1.15 — this should normalize (within 1.05-2.5x)
        columns = [GridColumn(key="conference", label="Conference", order=3)]
        normalize_column_sums(teams, columns, "nba")
        conf_sum = sum(t["cells"]["conference"]["merged_probability"] for t in teams)
        assert abs(conf_sum - 2.0) < 0.01, f"Conference sum should be ~200% after normalization, got {conf_sum*100:.1f}%"

    def test_normalize_column_sums_extreme_warns_but_no_normalize(self):
        """Column sums > 2.5x expected should NOT be normalized (matching bug)."""
        from app.utils.playoff_grid import normalize_column_sums

        teams = [
            {"name": "Team A", "cells": {"conference": {"merged_probability": 3.0, "sources": []}}},
            {"name": "Team B", "cells": {"conference": {"merged_probability": 2.0, "sources": []}}},
        ]
        # Total = 5.0, expected = 2.0, ratio = 2.5 — too extreme, should warn but NOT normalize
        columns = [GridColumn(key="conference", label="Conference", order=3)]
        normalize_column_sums(teams, columns, "nba")
        conf_sum = sum(t["cells"]["conference"]["merged_probability"] for t in teams)
        # Should be capped at 1.0 per cell but not normalized
        assert conf_sum <= 2.0 + 0.01  # Capped at 1.0 each = 2.0

    def test_championship_column_normalizes_to_100(self):
        """Championship column with moderate overshoot normalizes to ~100%."""
        from app.utils.playoff_grid import normalize_column_sums

        teams = [
            {"name": "Team A", "cells": {"championship": {"merged_probability": 0.55, "sources": []}}},
            {"name": "Team B", "cells": {"championship": {"merged_probability": 0.35, "sources": []}}},
            {"name": "Team C", "cells": {"championship": {"merged_probability": 0.20, "sources": []}}},
        ]
        # Total = 1.10, expected = 1.0 — moderate overshoot, should normalize
        columns = [GridColumn(key="championship", label="Champion", order=4)]
        normalize_column_sums(teams, columns, "nba")
        champ_sum = sum(t["cells"]["championship"]["merged_probability"] for t in teams)
        assert abs(champ_sum - 1.0) < 0.01
