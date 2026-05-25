"""Tests for the consolidated sport key translation module."""

import pytest

from app.utils.sport_keys import (
    SPORT_LEAGUE_MAP,
    ESPN_SPORT_MAPPING,
    STATPAL_SPORT_MAPPING,
    ODDS_API_TO_WIN_PROB_KEY,
    SPORT_PREFIX_TO_LLM_CATEGORY,
    LLM_CATEGORY_TO_SPORT_PREFIX,
    KALSHI_TICKER_TO_SPORT_KEY,
    KALSHI_GAME_TICKER_PREFIXES,
    KALSHI_LINK_RATE_GAME_TICKER_PREFIXES,
    KALSHI_TICKER_TO_DISPLAY_LABEL,
    KALSHI_FUTURES_TICKER_TO_SPORT_KEY,
    LLM_CATEGORY_TO_SPORT_KEYS,
    # accessor functions
    get_espn_path,
    normalize_to_win_prob_key,
    get_sport_prefix_for_category,
    get_sport_key_from_ticker,
    is_kalshi_game_ticker,
    get_sport_keys_for_category,
    get_llm_category_for_prefix,
)


# =============================================================================
# Dict sizes and sample entries
# =============================================================================

class TestDictContents:
    """Verify each dict has the expected size and a few key entries."""

    def test_sport_league_map_size(self):
        assert len(SPORT_LEAGUE_MAP) == 29

    def test_sport_league_map_sample_entries(self):
        assert SPORT_LEAGUE_MAP["basketball_nba"] == ("basketball", "nba")
        assert SPORT_LEAGUE_MAP["americanfootball_nfl"] == ("football", "nfl")
        assert SPORT_LEAGUE_MAP["icehockey_nhl"] == ("hockey", "nhl")
        assert SPORT_LEAGUE_MAP["soccer_epl"] == ("soccer", "eng.1")

    def test_espn_sport_mapping_size(self):
        assert len(ESPN_SPORT_MAPPING) == 26

    def test_espn_sport_mapping_sample(self):
        assert ESPN_SPORT_MAPPING["basketball_nba"] == "basketball/nba"
        assert ESPN_SPORT_MAPPING["americanfootball_nfl"] == "football/nfl"

    def test_statpal_sport_mapping_size(self):
        assert len(STATPAL_SPORT_MAPPING) == 14

    def test_statpal_sport_mapping_sample(self):
        assert STATPAL_SPORT_MAPPING["americanfootball_nfl"] == "nfl"
        assert STATPAL_SPORT_MAPPING["golf_pga"] == "pga"

    def test_odds_api_to_win_prob_key_size(self):
        assert len(ODDS_API_TO_WIN_PROB_KEY) == 3

    def test_odds_api_to_win_prob_key_sample(self):
        assert ODDS_API_TO_WIN_PROB_KEY["americanfootball_nfl"] == "football_nfl"
        assert ODDS_API_TO_WIN_PROB_KEY["icehockey_nhl"] == "hockey_nhl"

    def test_sport_prefix_to_llm_category_size(self):
        assert len(SPORT_PREFIX_TO_LLM_CATEGORY) >= 11

    def test_sport_prefix_to_llm_category_sample(self):
        assert SPORT_PREFIX_TO_LLM_CATEGORY["americanfootball"] == "football"
        assert SPORT_PREFIX_TO_LLM_CATEGORY["icehockey"] == "hockey"

    def test_llm_category_to_sport_prefix_size(self):
        assert len(LLM_CATEGORY_TO_SPORT_PREFIX) == 16

    def test_llm_category_to_sport_prefix_sample(self):
        assert LLM_CATEGORY_TO_SPORT_PREFIX["football"] == "americanfootball"
        assert LLM_CATEGORY_TO_SPORT_PREFIX["hockey"] == "icehockey"
        assert LLM_CATEGORY_TO_SPORT_PREFIX["motorsports"] == "motorsport"

    def test_kalshi_ticker_to_sport_key_size(self):
        assert len(KALSHI_TICKER_TO_SPORT_KEY) >= 200  # 205 game-level prefixes

    def test_kalshi_ticker_to_sport_key_sample(self):
        assert KALSHI_TICKER_TO_SPORT_KEY["kxnbagame"] == "basketball_nba"
        assert KALSHI_TICKER_TO_SPORT_KEY["kxnflgame"] == "americanfootball_nfl"
        assert KALSHI_TICKER_TO_SPORT_KEY["kxsosoccer"] == "soccer_olympics"
        # New game-level tickers
        assert KALSHI_TICKER_TO_SPORT_KEY["kxnflspread"] == "americanfootball_nfl"
        assert KALSHI_TICKER_TO_SPORT_KEY["kxnhlgoal"] == "icehockey_nhl"
        assert KALSHI_TICKER_TO_SPORT_KEY["kxmlbf5"] == "baseball_mlb"
        # Baseball/basketball fix
        assert KALSHI_TICKER_TO_SPORT_KEY["kxncaabbgame"] == "baseball_ncaa"

    def test_kalshi_game_ticker_prefixes_size(self):
        assert len(KALSHI_GAME_TICKER_PREFIXES) >= 200

    def test_kalshi_game_ticker_prefixes_is_tuple(self):
        assert isinstance(KALSHI_GAME_TICKER_PREFIXES, tuple)

    def test_kalshi_ticker_to_display_label_size(self):
        assert len(KALSHI_TICKER_TO_DISPLAY_LABEL) >= 190  # 194 display labels

    def test_kalshi_ticker_to_display_label_sample(self):
        assert KALSHI_TICKER_TO_DISPLAY_LABEL["kxnbagame"] == "NBA"
        assert KALSHI_TICKER_TO_DISPLAY_LABEL["kxlolgame"] == "LoL"
        assert KALSHI_TICKER_TO_DISPLAY_LABEL["kxnflspread"] == "NFL"
        assert KALSHI_TICKER_TO_DISPLAY_LABEL["kxncaabbgame"] == "NCAA Baseball"

    def test_llm_category_to_sport_keys_size(self):
        assert len(LLM_CATEGORY_TO_SPORT_KEYS) == 11

    def test_llm_category_to_sport_keys_sample(self):
        assert "basketball_nba" in LLM_CATEGORY_TO_SPORT_KEYS["basketball"]
        assert "americanfootball_nfl" in LLM_CATEGORY_TO_SPORT_KEYS["football"]


# =============================================================================
# Cross-consistency
# =============================================================================

class TestCrossConsistency:
    """Verify dicts are consistent with each other."""

    def test_espn_mapping_keys_are_subset_of_sport_league_map(self):
        """ESPN_SPORT_MAPPING keys should all be in SPORT_LEAGUE_MAP."""
        assert set(ESPN_SPORT_MAPPING.keys()).issubset(set(SPORT_LEAGUE_MAP.keys()))

    def test_kalshi_ticker_prefixes_subset_of_ticker_to_sport_key(self):
        """KALSHI_GAME_TICKER_PREFIXES should be a subset of KALSHI_TICKER_TO_SPORT_KEY
        (unsupported leagues like AHL/KHL/DEL are excluded from the link-rate denominator)."""
        assert set(KALSHI_GAME_TICKER_PREFIXES).issubset(set(KALSHI_TICKER_TO_SPORT_KEY.keys()))

    def test_display_label_keys_are_subset_of_ticker_to_sport_key(self):
        """KALSHI_TICKER_TO_DISPLAY_LABEL keys should all be in KALSHI_TICKER_TO_SPORT_KEY."""
        assert set(KALSHI_TICKER_TO_DISPLAY_LABEL.keys()).issubset(set(KALSHI_TICKER_TO_SPORT_KEY.keys()))

    def test_prefix_to_category_and_category_to_prefix_are_inverses(self):
        """For keys present in both, mappings should round-trip."""
        for prefix, category in SPORT_PREFIX_TO_LLM_CATEGORY.items():
            if category in LLM_CATEGORY_TO_SPORT_PREFIX:
                assert LLM_CATEGORY_TO_SPORT_PREFIX[category] == prefix


# =============================================================================
# Accessor functions
# =============================================================================

class TestGetEspnPath:
    def test_known_key(self):
        assert get_espn_path("basketball_nba") == ("basketball", "nba")

    def test_unknown_key(self):
        assert get_espn_path("unknown_sport") is None

    def test_empty_string(self):
        assert get_espn_path("") is None


class TestNormalizeToWinProbKey:
    def test_aliased_key(self):
        assert normalize_to_win_prob_key("americanfootball_nfl") == "football_nfl"

    def test_passthrough(self):
        assert normalize_to_win_prob_key("basketball_nba") == "basketball_nba"

    def test_unknown_passthrough(self):
        assert normalize_to_win_prob_key("curling") == "curling"


class TestGetSportPrefixForCategory:
    def test_known_category(self):
        assert get_sport_prefix_for_category("football") == "americanfootball"

    def test_unknown_category(self):
        assert get_sport_prefix_for_category("competitive_eating") is None

    def test_empty_string(self):
        assert get_sport_prefix_for_category("") is None


class TestGetSportKeyFromTicker:
    def test_nba_ticker(self):
        assert get_sport_key_from_ticker("KXNBAGAME-26FEB19BOSGSW") == "basketball_nba"

    def test_nfl_ticker(self):
        assert get_sport_key_from_ticker("KXNFLGAME-26FEB01KCBUF") == "americanfootball_nfl"

    def test_case_insensitive(self):
        assert get_sport_key_from_ticker("kxnhlgame-26FEB10TORMON") == "icehockey_nhl"

    def test_unknown_ticker(self):
        assert get_sport_key_from_ticker("RANDOMTICKER-123") is None

    def test_empty_string(self):
        assert get_sport_key_from_ticker("") is None

    def test_none(self):
        assert get_sport_key_from_ticker(None) is None

    @pytest.mark.parametrize(
        ("ticker", "expected_sport_key"),
        [
            ("KXNBASPREAD-26FEB19BOSGSW", "basketball_nba"),
            ("KXNBA2HTOTAL-26FEB19BOSGSW", "basketball_nba"),
            ("KXNFLPASSTDS-26SEP07KCBUF", "americanfootball_nfl"),
            ("KXNFLTEAMFIRSTTD-26SEP07KCBUF", "americanfootball_nfl"),
            ("KXNHLFIRSTGOAL-26MAR30BOSMON", "icehockey_nhl"),
            ("KXMLBF5TOTAL-26APR01NYYBOS", "baseball_mlb"),
            ("KXNCAAMB1HSPREAD-26JAN20DUKEUNC", "basketball_ncaab"),
            ("KXNCAABBSPREAD-26MAY30LSUTEX", "baseball_ncaa"),
            ("KXNCAAF2HTOTAL-26NOV28MICHOSU", "americanfootball_ncaaf"),
            ("KXMLSBTTS-26JUN14LAFSEA", "soccer_usa_mls"),
            ("KXSOCTOTAL-26DEC26ARSAVL", "soccer_epl"),
            ("KXATPGAMESPREAD-26JUL01SINNERALCARAZ", "tennis_atp"),
            ("KXUFCDISTANCE-26FEB20", "mma_mixed_martial_arts"),
            ("KXCS2MAPWINNER-26JUN10", "esports"),
        ],
    )
    def test_game_market_linking_tickers_resolve_to_expected_sports(
        self, ticker, expected_sport_key
    ):
        assert get_sport_key_from_ticker(ticker) == expected_sport_key
        assert is_kalshi_game_ticker(ticker) is True


class TestIsKalshiGameTicker:
    def test_nba_game(self):
        assert is_kalshi_game_ticker("KXNBAGAME-26FEB19BOSGSW") is True

    def test_ufc_fight(self):
        assert is_kalshi_game_ticker("KXUFCFIGHT-26FEB20") is True

    def test_non_game(self):
        assert is_kalshi_game_ticker("KXCPI-2026-05") is False

    def test_empty_string(self):
        assert is_kalshi_game_ticker("") is False

    def test_none(self):
        assert is_kalshi_game_ticker(None) is False

    def test_case_insensitive(self):
        assert is_kalshi_game_ticker("kxmlbgame-26MAR15NYYBOS") is True

    def test_nfl_spread_is_game_ticker(self):
        assert is_kalshi_game_ticker("KXNFLSPREAD-26SEP07KCBUF") is True

    def test_nhl_goal_is_game_ticker(self):
        assert is_kalshi_game_ticker("KXNHLGOAL-26MAR30BOSMON") is True

    def test_mlb_f5_is_game_ticker(self):
        assert is_kalshi_game_ticker("KXMLBF5-26APR01NYYBOS") is True

    def test_futures_not_game_ticker(self):
        """Futures tickers should NOT be classified as game tickers."""
        assert is_kalshi_game_ticker("KXNFLMVP-26") is False
        assert is_kalshi_game_ticker("KXNHLHART-26") is False
        assert is_kalshi_game_ticker("KXMLBWS-26") is False
        assert is_kalshi_game_ticker("KXWNBA-26") is False
        assert is_kalshi_game_ticker("KXNFLAFCCHAMP-26") is False


class TestFuturesTickerResolution:
    """Futures tickers resolve to sport via get_sport_key_from_ticker."""

    def test_nfl_mvp(self):
        assert get_sport_key_from_ticker("KXNFLMVP-26") == "americanfootball_nfl"

    def test_nhl_hart(self):
        assert get_sport_key_from_ticker("KXNHLHART-26") == "icehockey_nhl"

    def test_mlb_world_series(self):
        assert get_sport_key_from_ticker("KXMLBWS-26") == "baseball_mlb"

    def test_wnba_championship(self):
        assert get_sport_key_from_ticker("KXWNBA-26") == "basketball_wnba"

    def test_ncaaf_conference(self):
        assert get_sport_key_from_ticker("KXNCAAFSEC-26") == "americanfootball_ncaaf"

    def test_nfl_win_totals(self):
        assert get_sport_key_from_ticker("KXNFLWINS-KC") == "americanfootball_nfl"

    def test_ncaab_conference_tournament(self):
        assert get_sport_key_from_ticker("KXNCAAMBSEC-26") == "basketball_ncaab"

    def test_college_baseball_correctly_classified(self):
        assert get_sport_key_from_ticker("KXNCAABASEBALL-26") == "baseball_ncaa"

    def test_esports_world_cup_mlbb_is_esports_not_baseball(self):
        """KXEWCMLBB is Mobile Legends at Esports World Cup, NOT baseball."""
        assert get_sport_key_from_ticker("KXEWCMLBB-26") == "esports"


class TestGetSportKeysForCategory:
    def test_basketball(self):
        result = get_sport_keys_for_category("basketball")
        assert "basketball_nba" in result
        assert "basketball_wnba" in result

    def test_case_insensitive(self):
        assert get_sport_keys_for_category("FOOTBALL") == get_sport_keys_for_category("football")

    def test_unknown_category(self):
        assert get_sport_keys_for_category("curling") is None

    def test_none(self):
        assert get_sport_keys_for_category(None) is None

    def test_empty_string(self):
        assert get_sport_keys_for_category("") is None

    @pytest.mark.parametrize(
        ("category", "required_sport_keys"),
        [
            (
                "basketball",
                {
                    "basketball_nba",
                    "basketball_wnba",
                    "basketball_ncaab",
                    "basketball_wncaab",
                },
            ),
            ("football", {"americanfootball_nfl", "americanfootball_ncaaf"}),
            ("baseball", {"baseball_mlb"}),
            ("hockey", {"icehockey_nhl"}),
            ("soccer", {"soccer_epl", "soccer_usa_mls", "soccer_uefa_champs_league"}),
            ("tennis", {"tennis_atp", "tennis_wta"}),
            ("mma", {"mma_mixed_martial_arts"}),
        ],
    )
    def test_discover_sports_category_filters_include_core_sport_keys(
        self, category, required_sport_keys
    ):
        result = get_sport_keys_for_category(category)
        assert result is not None
        assert required_sport_keys.issubset(set(result))

    @pytest.mark.parametrize(
        ("category", "excluded_sport_keys"),
        [
            ("basketball", {"baseball_mlb", "americanfootball_nfl", "icehockey_nhl"}),
            ("football", {"basketball_nba", "baseball_mlb", "icehockey_nhl"}),
            ("baseball", {"basketball_nba", "americanfootball_nfl", "icehockey_nhl"}),
            ("hockey", {"basketball_nba", "americanfootball_nfl", "baseball_mlb"}),
        ],
    )
    def test_discover_sports_category_filters_do_not_cross_major_sports(
        self, category, excluded_sport_keys
    ):
        result = get_sport_keys_for_category(category)
        assert result is not None
        assert set(result).isdisjoint(excluded_sport_keys)


class TestGetLlmCategoryForPrefix:
    def test_known_prefix(self):
        assert get_llm_category_for_prefix("americanfootball") == "football"

    def test_passthrough(self):
        assert get_llm_category_for_prefix("unknown_prefix") == "unknown_prefix"

    @pytest.mark.parametrize(
        ("ticker", "expected_category"),
        [
            ("KXNFLMVP-26", "football"),
            ("KXNBAMVP-26", "basketball"),
            ("KXMLBWS-26", "baseball"),
            ("KXNCAABASEBALL-26", "baseball"),
            ("KXNHLHART-26", "hockey"),
            ("KXEPLTOP4-26", "soccer"),
            ("KXATPFINALS-26", "tennis"),
            ("KXUFCWHITEHOUSE-26", "mma"),
            ("KXEWCMLBB-26", "esports"),
            ("KXF1WDC-26", "motorsports"),
        ],
    )
    def test_discover_category_routing_for_representative_futures(
        self, ticker, expected_category
    ):
        sport_key = get_sport_key_from_ticker(ticker)
        assert sport_key is not None
        sport_prefix = sport_key.split("_", maxsplit=1)[0]
        assert get_llm_category_for_prefix(sport_prefix) == expected_category


# =============================================================================
# Backward-compatible re-exports
# =============================================================================

class TestBackwardCompatReExports:
    """Verify that imports from original locations still resolve."""

    def test_espn_sport_mapping_from_tasks_config(self):
        from app.tasks.config import ESPN_SPORT_MAPPING as m
        assert m is ESPN_SPORT_MAPPING

    def test_statpal_sport_mapping_from_tasks_config(self):
        from app.tasks.config import STATPAL_SPORT_MAPPING as m
        assert m is STATPAL_SPORT_MAPPING

    def test_sport_league_map_from_espn_api(self):
        from app.services.espn_api import SPORT_LEAGUE_MAP as m
        assert m is SPORT_LEAGUE_MAP

    def test_normalize_sport_key_from_win_probability(self):
        from app.utils.win_probability import _normalize_sport_key
        # Function re-exported via alias — should produce same results
        assert _normalize_sport_key("americanfootball_nfl") == "football_nfl"
        assert _normalize_sport_key("basketball_nba") == "basketball_nba"

    def test_sport_key_aliases_from_win_probability(self):
        from app.utils.win_probability import _SPORT_KEY_ALIASES
        assert _SPORT_KEY_ALIASES is ODDS_API_TO_WIN_PROB_KEY

    def test_is_kalshi_game_ticker_from_prediction_market(self):
        from app.utils.prediction_market_matching import is_kalshi_game_ticker as fn
        assert fn("KXNBAGAME-123") is True

    def test_get_sport_prefix_from_ticker_from_prediction_market(self):
        from app.utils.prediction_market_matching import get_sport_prefix_from_ticker
        assert get_sport_prefix_from_ticker("KXNBAGAME-123") == "basketball_nba"

    def test_sport_category_to_keys_from_team_linking(self):
        from app.utils.team_linking import SPORT_CATEGORY_TO_KEYS
        assert SPORT_CATEGORY_TO_KEYS is LLM_CATEGORY_TO_SPORT_KEYS

    def test_get_sport_keys_for_category_from_team_linking(self):
        from app.utils.team_linking import get_sport_keys_for_category as fn
        assert fn("basketball") is not None

    def test_kalshi_game_tickers_from_kalshi_task(self):
        from app.tasks.kalshi import _KALSHI_GAME_TICKERS
        assert _KALSHI_GAME_TICKERS is KALSHI_TICKER_TO_DISPLAY_LABEL

    def test_sport_prefix_to_llm_category_from_events(self):
        from app.routes.events import _SPORT_PREFIX_TO_LLM_CATEGORY
        assert _SPORT_PREFIX_TO_LLM_CATEGORY is SPORT_PREFIX_TO_LLM_CATEGORY


class TestGameFuturesMapSeparation:
    """Game-level and futures-level ticker maps must not overlap.

    Series/award/season tickers in the game map inflate the link-rate
    denominator with markets that can never link to individual game events.
    """

    def test_no_overlap_between_game_and_futures_maps(self):
        overlap = set(KALSHI_TICKER_TO_SPORT_KEY.keys()) & set(KALSHI_FUTURES_TICKER_TO_SPORT_KEY.keys())
        assert overlap == set(), f"Tickers in both game and futures maps: {overlap}"

    def test_series_tickers_not_in_game_prefixes(self):
        series_prefixes = [
            "kxnbaseries", "kxnhlseries", "kxmlbseries",
            "kxmlbseriesexact", "kxmlbseriesgametotal",
            "kxwnbaseries", "kxnflseries",
        ]
        for prefix in series_prefixes:
            assert prefix not in KALSHI_GAME_TICKER_PREFIXES, \
                f"{prefix} must be in futures map only, not game-level"
            assert is_kalshi_game_ticker(f"{prefix.upper()}-26FOOBAR") is False

    def test_series_tickers_resolve_via_futures_map(self):
        assert get_sport_key_from_ticker("KXNBASERIES-26MAY10BOSPHI") == "basketball_nba"
        assert get_sport_key_from_ticker("KXNHLSERIES-26MAY10FLORNG") == "icehockey_nhl"
        assert get_sport_key_from_ticker("KXMLBSERIES-26OCT15NYYATL") == "baseball_mlb"

    def test_link_rate_game_prefixes_are_game_prefix_subset(self):
        assert set(KALSHI_LINK_RATE_GAME_TICKER_PREFIXES).issubset(
            set(KALSHI_GAME_TICKER_PREFIXES)
        )

    def test_link_rate_prefixes_exclude_esports_and_futures(self):
        assert "kxlolgame" not in KALSHI_LINK_RATE_GAME_TICKER_PREFIXES
        assert "kxcs2game" not in KALSHI_LINK_RATE_GAME_TICKER_PREFIXES
        assert "kxvalorantgame" not in KALSHI_LINK_RATE_GAME_TICKER_PREFIXES
        assert "kxnbaseries" not in KALSHI_LINK_RATE_GAME_TICKER_PREFIXES
