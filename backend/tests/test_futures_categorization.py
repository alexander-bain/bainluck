"""Tests for futures market sport categorization (rules engine)."""

import pytest
from datetime import datetime, timezone
from unittest.mock import patch

from app.utils.futures_categorization import (
    categorize_by_rules, categorize_market,
    detect_league, detect_season, compute_canonical_market_key,
    infer_sport_from_league, extract_olympic_discipline,
    detect_game_prop_sport, is_game_prop, generate_category_tags,
    LEAGUE_TO_SPORT_CATEGORY,
)


# =============================================================================
# Prefix Matching (sport_key)
# =============================================================================
class TestPrefixMatching:
    def test_football_prefix(self):
        assert categorize_by_rules("Any market", "americanfootball_nfl_super_bowl") == "football"

    def test_basketball_prefix(self):
        assert categorize_by_rules("Any market", "basketball_nba_championship") == "basketball"

    def test_baseball_prefix(self):
        assert categorize_by_rules("Any market", "baseball_mlb_world_series") == "baseball"

    def test_hockey_prefix(self):
        assert categorize_by_rules("Any market", "icehockey_nhl_stanley_cup") == "hockey"

    def test_mma_prefix(self):
        assert categorize_by_rules("Any market", "mma_ufc") == "mma"

    def test_boxing_prefix(self):
        assert categorize_by_rules("Any market", "boxing_boxing") == "boxing"

    def test_golf_prefix(self):
        assert categorize_by_rules("Any market", "golf_pga_tour") == "golf"

    def test_tennis_prefix(self):
        assert categorize_by_rules("Any market", "tennis_atp_us_open") == "tennis"

    def test_soccer_prefix(self):
        assert categorize_by_rules("Any market", "soccer_epl") == "soccer"

    def test_politics_prefix(self):
        assert categorize_by_rules("Any market", "politics_us_election") == "politics"

    def test_esports_prefix(self):
        assert categorize_by_rules("Any market", "esports_lol") == "esports"

    def test_motorsport_prefix(self):
        assert categorize_by_rules("Any market", "motorsport_f1") == "motorsports"

    def test_lacrosse_prefix(self):
        assert categorize_by_rules("Any market", "lacrosse_pll") == "lacrosse"

    def test_cricket_prefix(self):
        assert categorize_by_rules("Any market", "cricket_ipl") == "cricket"

    def test_rugby_league_prefix(self):
        assert categorize_by_rules("Any market", "rugbyleague_nrl") == "rugby"

    def test_rugby_union_prefix(self):
        assert categorize_by_rules("Any market", "rugbyunion_six_nations") == "rugby"

    def test_aussie_rules_prefix(self):
        assert categorize_by_rules("Any market", "aussierules_afl") == "aussierules"

    def test_horse_racing_prefix(self):
        assert categorize_by_rules("Any market", "horseracing_belmont") == "horse_racing"


# =============================================================================
# Baseball Patterns
# =============================================================================
class TestBaseballPatterns:
    def test_mlb(self):
        assert categorize_by_rules("MLB World Series Winner") == "baseball"

    def test_world_series(self):
        assert categorize_by_rules("2026 World Series") == "baseball"

    def test_al_mvp(self):
        assert categorize_by_rules("AL MVP Award Winner") == "baseball"

    def test_nl_cy_young(self):
        assert categorize_by_rules("NL Cy Young Award Winner") == "baseball"

    def test_cy_young_award(self):
        assert categorize_by_rules("Cy Young Award Winner") == "baseball"

    def test_american_league(self):
        assert categorize_by_rules("American League Pennant Winner") == "baseball"

    def test_national_league(self):
        assert categorize_by_rules("National League MVP") == "baseball"

    def test_home_run_derby(self):
        assert categorize_by_rules("Home Run Derby Winner") == "baseball"


# =============================================================================
# Football Patterns
# =============================================================================
class TestFootballPatterns:
    def test_nfl(self):
        assert categorize_by_rules("NFL MVP Winner") == "football"

    def test_super_bowl(self):
        assert categorize_by_rules("Super Bowl LX Winner") == "football"

    def test_college_football(self):
        assert categorize_by_rules("College Football Playoff Winner") == "football"

    def test_heisman(self):
        assert categorize_by_rules("Heisman Trophy Winner") == "football"

    def test_afc_championship(self):
        assert categorize_by_rules("AFC Championship Winner") == "football"

    def test_nfc_east(self):
        assert categorize_by_rules("NFC East Winner") == "football"

    def test_sec_football_championship(self):
        assert categorize_by_rules("SEC Championship Football Winner") == "football"

    def test_rose_bowl(self):
        assert categorize_by_rules("Rose Bowl Winner") == "football"

    def test_sugar_bowl(self):
        assert categorize_by_rules("Sugar Bowl Winner") == "football"

    def test_cfp(self):
        assert categorize_by_rules("CFP National Champion") == "football"

    def test_pro_bowl(self):
        assert categorize_by_rules("Pro Bowl MVP") == "football"

    def test_offensive_player_of_year(self):
        assert categorize_by_rules("Offensive Player of the Year") == "football"

    def test_defensive_player_of_year(self):
        assert categorize_by_rules("Defensive Player of the Year") == "football"

    def test_nfl_mvp(self):
        assert categorize_by_rules("NFL MVP 2026") == "football"


# =============================================================================
# Basketball Patterns
# =============================================================================
class TestBasketballPatterns:
    def test_nba(self):
        assert categorize_by_rules("NBA Championship Winner") == "basketball"

    def test_ncaab(self):
        assert categorize_by_rules("NCAAB March Madness Winner") == "basketball"

    def test_wnba(self):
        assert categorize_by_rules("WNBA Championship") == "basketball"

    def test_march_madness(self):
        assert categorize_by_rules("March Madness Champion") == "basketball"

    def test_eastern_conference(self):
        assert categorize_by_rules("Eastern Conference Winner") == "basketball"

    def test_western_conference(self):
        assert categorize_by_rules("Western Conference Winner") == "basketball"

    def test_final_four(self):
        assert categorize_by_rules("Final Four Teams") == "basketball"

    def test_sweet_sixteen(self):
        assert categorize_by_rules("Sweet Sixteen") == "basketball"

    def test_nba_mvp(self):
        assert categorize_by_rules("NBA MVP Award") == "basketball"

    def test_finals_mvp(self):
        assert categorize_by_rules("Finals MVP") == "basketball"

    def test_sixth_man(self):
        assert categorize_by_rules("Sixth Man of the Year") == "basketball"

    def test_dunk_contest(self):
        assert categorize_by_rules("Slam Dunk Contest Winner") == "basketball"

    def test_ncaa_tournament(self):
        assert categorize_by_rules("NCAA Tournament Winner") == "basketball"


# =============================================================================
# Hockey Patterns
# =============================================================================
class TestHockeyPatterns:
    def test_nhl(self):
        assert categorize_by_rules("NHL Regular Season Winner") == "hockey"

    def test_stanley_cup(self):
        assert categorize_by_rules("Stanley Cup Champion") == "hockey"

    def test_hart_trophy(self):
        assert categorize_by_rules("Hart Trophy Winner") == "hockey"

    def test_vezina(self):
        assert categorize_by_rules("Vezina Trophy Winner") == "hockey"

    def test_calder(self):
        assert categorize_by_rules("Calder Trophy Winner") == "hockey"

    def test_conn_smythe(self):
        assert categorize_by_rules("Conn Smythe Trophy") == "hockey"

    def test_norris_trophy(self):
        assert categorize_by_rules("Norris Trophy Winner") == "hockey"

    def test_rocket_richard(self):
        assert categorize_by_rules("Rocket Richard Trophy") == "hockey"


# =============================================================================
# Golf Patterns
# =============================================================================
class TestGolfPatterns:
    def test_pga(self):
        assert categorize_by_rules("PGA Championship Winner") == "golf"

    def test_masters(self):
        assert categorize_by_rules("2026 Masters Tournament Winner") == "golf"

    def test_the_open(self):
        assert categorize_by_rules("The Open Championship Winner") == "golf"

    def test_british_open(self):
        assert categorize_by_rules("British Open Winner") == "golf"

    def test_ryder_cup(self):
        assert categorize_by_rules("Ryder Cup Winner") == "golf"

    def test_lpga(self):
        assert categorize_by_rules("LPGA Tour Championship") == "golf"

    def test_liv_golf(self):
        assert categorize_by_rules("LIV Golf Invitational Winner") == "golf"

    def test_us_womens_open(self):
        assert categorize_by_rules("US Women's Open Winner") == "golf"

    def test_known_golfer(self):
        assert categorize_by_rules("Scottie Scheffler to win US Open") == "golf"

    def test_known_golfer_bryson(self):
        assert categorize_by_rules("Bryson DeChambeau next major") == "golf"


# =============================================================================
# Tennis Patterns
# =============================================================================
class TestTennisPatterns:
    def test_wimbledon(self):
        assert categorize_by_rules("Wimbledon Winner") == "tennis"

    def test_french_open(self):
        assert categorize_by_rules("French Open Champion") == "tennis"

    def test_australian_open(self):
        assert categorize_by_rules("Australian Open Winner") == "tennis"

    def test_atp(self):
        assert categorize_by_rules("ATP Finals Winner") == "tennis"

    def test_wta(self):
        assert categorize_by_rules("WTA Tour Championship") == "tennis"

    def test_davis_cup(self):
        assert categorize_by_rules("Davis Cup Winner") == "tennis"

    def test_known_tennis_player(self):
        assert categorize_by_rules("Novak Djokovic to win Grand Slam") == "tennis"

    def test_known_tennis_player_alcaraz(self):
        assert categorize_by_rules("Carlos Alcaraz next major") == "tennis"


# =============================================================================
# Soccer Patterns
# =============================================================================
class TestSoccerPatterns:
    def test_epl(self):
        assert categorize_by_rules("EPL Champion") == "soccer"

    def test_premier_league(self):
        assert categorize_by_rules("Premier League Winner") == "soccer"

    def test_champions_league(self):
        assert categorize_by_rules("Champions League Winner") == "soccer"

    def test_mls(self):
        assert categorize_by_rules("MLS Cup Winner") == "soccer"

    def test_world_cup(self):
        assert categorize_by_rules("World Cup Winner") == "soccer"

    def test_ballon_dor(self):
        assert categorize_by_rules("Ballon d'Or Winner") == "soccer"

    def test_copa_america(self):
        assert categorize_by_rules("Copa America Winner") == "soccer"

    def test_golden_boot(self):
        assert categorize_by_rules("Golden Boot Award") == "soccer"

    def test_europa_league(self):
        assert categorize_by_rules("Europa League Winner") == "soccer"


# =============================================================================
# Other Sports Patterns
# =============================================================================
class TestOtherSportsPatterns:
    def test_ufc(self):
        assert categorize_by_rules("UFC Heavyweight Champion") == "mma"

    def test_boxing(self):
        assert categorize_by_rules("Boxing World Championship") == "boxing"

    def test_f1(self):
        assert categorize_by_rules("F1 World Championship") == "motorsports"

    def test_nascar(self):
        assert categorize_by_rules("NASCAR Cup Series Winner") == "motorsports"

    def test_daytona_500(self):
        assert categorize_by_rules("Daytona 500 Winner") == "motorsports"

    def test_kentucky_derby(self):
        assert categorize_by_rules("Kentucky Derby Winner") == "horse_racing"

    def test_triple_crown(self):
        assert categorize_by_rules("Triple Crown Winner") == "horse_racing"

    def test_ipl(self):
        assert categorize_by_rules("IPL Winner") == "cricket"

    def test_six_nations(self):
        assert categorize_by_rules("Six Nations Winner") == "rugby"

    def test_afl(self):
        assert categorize_by_rules("AFL Premiership") == "aussierules"

    def test_olympics(self):
        assert categorize_by_rules("Olympic Gold Medals") == "olympics"

    # Kalshi Olympics winter sports (names don't contain "Olympic")
    def test_curling(self):
        assert categorize_by_rules("Women's Curling: Gold Medal Country") == "olympics"

    def test_figure_skating(self):
        assert categorize_by_rules("Figure Skating Women's Singles: Medal Winner") == "olympics"

    def test_speed_skating(self):
        assert categorize_by_rules("Speed Skating Men's 1500m: Gold Medal Country") == "olympics"

    def test_freestyle_skiing(self):
        assert categorize_by_rules("Freestyle Skiing: Gold Medal Winner") == "olympics"

    def test_ski_mountaineering(self):
        assert categorize_by_rules("Ski Mountaineering: Medal Winner") == "olympics"

    def test_nordic_combined(self):
        assert categorize_by_rules("Nordic Combined: Gold Medal Winner") == "olympics"

    def test_biathlon(self):
        assert categorize_by_rules("Biathlon Mixed Relay: Medal Winner") == "olympics"

    def test_bobsled(self):
        assert categorize_by_rules("Bobsled 2-Man: Gold Medal Country") == "olympics"

    def test_gold_medal_generic(self):
        assert categorize_by_rules("Men's Curling: Gold Medal Country") == "olympics"

    def test_election(self):
        assert categorize_by_rules("Presidential Election Winner") == "politics"

    def test_house_race(self):
        assert categorize_by_rules("Which party will win the House race for FL-15?") == "politics"

    def test_which_party(self):
        assert categorize_by_rules("Which party will win the House race for KY-06?") == "politics"

    def test_gubernatorial(self):
        assert categorize_by_rules("Gubernatorial Election Winner") == "politics"

    def test_oscar(self):
        assert categorize_by_rules("Oscar Best Picture") == "entertainment"

    def test_csgo(self):
        assert categorize_by_rules("CSGO Major Winner") == "esports"

    def test_lacrosse(self):
        assert categorize_by_rules("Premier Lacrosse League") == "lacrosse"

    def test_chess(self):
        assert categorize_by_rules("Chess World Championship") == "chess"

    def test_wsop(self):
        assert categorize_by_rules("WSOP Main Event Winner") == "poker"


# =============================================================================
# Case Insensitivity
# =============================================================================
class TestCaseInsensitivity:
    def test_lowercase(self):
        assert categorize_by_rules("nba championship") == "basketball"

    def test_uppercase(self):
        assert categorize_by_rules("NBA CHAMPIONSHIP") == "basketball"

    def test_mixed_case(self):
        assert categorize_by_rules("Nba Championship") == "basketball"


# =============================================================================
# No Match
# =============================================================================
class TestNoMatch:
    def test_ambiguous_returns_none(self):
        assert categorize_by_rules("MVP Winner?") is None

    def test_gibberish_returns_none(self):
        assert categorize_by_rules("xyzzy foobar") is None

    def test_empty_string(self):
        assert categorize_by_rules("") is None


# =============================================================================
# categorize_market (full pipeline)
# =============================================================================
class TestCategorizeMarket:
    def test_rules_match_returns_immediately(self):
        result = categorize_market("NBA Championship Winner", use_llm=False)
        assert result == "basketball"

    def test_no_match_without_llm_returns_other(self):
        result = categorize_market("xyzzy foobar", use_llm=False)
        assert result == "other"

    @patch("app.utils.futures_categorization.llm")
    def test_llm_fallback(self, mock_llm):
        mock_llm.is_available.return_value = True
        mock_llm.classify_futures_market.return_value = "basketball"
        result = categorize_market("Some Ambiguous Market")
        assert result == "basketball"

    @patch("app.utils.futures_categorization.llm")
    def test_llm_returns_other(self, mock_llm):
        mock_llm.is_available.return_value = True
        mock_llm.classify_futures_market.return_value = "other"
        result = categorize_market("Completely Unknown Thing")
        assert result == "other"

    @patch("app.utils.futures_categorization.llm")
    def test_llm_unavailable_fallback(self, mock_llm):
        mock_llm.is_available.return_value = False
        result = categorize_market("Some Ambiguous Market")
        assert result == "other"


# =============================================================================
# League Detection (sport_key prefix)
# =============================================================================
class TestLeagueDetectionFromSportKey:
    def test_nba_from_sport_key(self):
        assert detect_league("Any market", "basketball_nba_championship_winner") == "NBA"

    def test_nfl_from_sport_key(self):
        assert detect_league("Any market", "americanfootball_nfl_super_bowl_winner") == "NFL"

    def test_mlb_from_sport_key(self):
        assert detect_league("Any market", "baseball_mlb_world_series_winner") == "MLB"

    def test_nhl_from_sport_key(self):
        assert detect_league("Any market", "icehockey_nhl_championship_winner") == "NHL"

    def test_epl_from_sport_key(self):
        assert detect_league("Any market", "soccer_epl") == "EPL"

    def test_pga_from_sport_key(self):
        assert detect_league("Any market", "golf_pga") == "PGA"

    def test_atp_from_sport_key(self):
        assert detect_league("Any market", "tennis_atp") == "ATP"

    def test_ufc_from_sport_key(self):
        assert detect_league("Any market", "mma_mixed_martial_arts") == "UFC"

    def test_ncaaf_from_sport_key(self):
        assert detect_league("Any market", "americanfootball_ncaaf") == "NCAAF"

    def test_ncaab_from_sport_key(self):
        assert detect_league("Any market", "basketball_ncaab") == "NCAAB"

    def test_f1_from_sport_key(self):
        assert detect_league("Any market", "motorsport_f1") == "F1"

    def test_nascar_from_sport_key(self):
        assert detect_league("Any market", "motorsport_nascar") == "NASCAR"

    def test_mls_from_sport_key(self):
        assert detect_league("Any market", "soccer_usa_mls") == "MLS"


# =============================================================================
# League Detection (market name patterns)
# =============================================================================
class TestLeagueDetectionFromName:
    def test_nba_championship(self):
        assert detect_league("NBA Championship Winner") == "NBA"

    def test_nba_finals(self):
        assert detect_league("NBA Finals MVP") == "NBA"

    def test_nfl_super_bowl(self):
        assert detect_league("Super Bowl LX Winner") == "NFL"

    def test_nfl_mvp(self):
        assert detect_league("NFL MVP 2026") == "NFL"

    def test_afc_championship(self):
        assert detect_league("AFC Championship Winner") == "NFL"

    def test_nfc_east(self):
        assert detect_league("NFC East Winner") == "NFL"

    def test_mlb_world_series(self):
        assert detect_league("World Series Winner") == "MLB"

    def test_al_mvp(self):
        assert detect_league("AL MVP Award") == "MLB"

    def test_nhl(self):
        assert detect_league("NHL Regular Season Winner") == "NHL"

    def test_stanley_cup(self):
        assert detect_league("Stanley Cup Winner") == "NHL"

    def test_hart_trophy(self):
        assert detect_league("Hart Trophy Winner") == "NHL"

    def test_epl_premier_league(self):
        assert detect_league("Premier League Winner") == "EPL"

    def test_champions_league(self):
        assert detect_league("Champions League Winner") == "UCL"

    def test_la_liga(self):
        assert detect_league("La Liga Winner") == "LA_LIGA"

    def test_bundesliga(self):
        assert detect_league("Bundesliga Champion") == "BUNDESLIGA"

    def test_mls_cup(self):
        assert detect_league("MLS Cup Winner") == "MLS"

    def test_pga_championship(self):
        assert detect_league("PGA Championship Winner") == "PGA"

    def test_wimbledon(self):
        assert detect_league("Wimbledon Winner") == "ATP"

    def test_ncaab_march_madness(self):
        assert detect_league("March Madness Winner") == "NCAAB"

    def test_ncaaf_college_football(self):
        assert detect_league("College Football Playoff Winner") == "NCAAF"

    def test_heisman(self):
        assert detect_league("Heisman Trophy Winner") == "NCAAF"

    def test_ufc(self):
        assert detect_league("UFC Heavyweight Champion") == "UFC"

    def test_f1(self):
        assert detect_league("Formula 1 World Championship") == "F1"

    def test_nascar_daytona(self):
        assert detect_league("Daytona 500 Winner") == "NASCAR"

    def test_olympics(self):
        assert detect_league("Olympic Gold Medal Count") == "OLYMPICS"

    def test_no_league_ambiguous(self):
        assert detect_league("MVP Winner?") is None

    def test_no_league_gibberish(self):
        assert detect_league("xyzzy foobar") is None


# =============================================================================
# Season Detection
# =============================================================================
class TestSeasonDetection:
    def test_explicit_split_year(self):
        assert detect_season("NBA Championship 2025-26") == "2025-26"

    def test_explicit_split_year_with_slash(self):
        assert detect_season("EPL Winner 2025/26") == "2025-26"

    def test_explicit_single_year_nfl(self):
        assert detect_season("NFL MVP 2025", league="NFL") == "2025"

    def test_explicit_year_split_league(self):
        # "NBA Championship 2026" means the 2025-26 season
        assert detect_season("NBA Championship 2026", league="NBA") == "2025-26"

    def test_explicit_year_split_league_nhl(self):
        assert detect_season("Stanley Cup Winner 2026", league="NHL") == "2025-26"

    def test_explicit_year_single_league(self):
        assert detect_season("World Series Winner 2026", league="MLB") == "2026"

    def test_no_year_resolution_date_split(self):
        # NBA resolves in June = 2025-26 season
        resolution = datetime(2026, 6, 15, tzinfo=timezone.utc)
        assert detect_season("NBA Championship", league="NBA", resolution_date=resolution) == "2025-26"

    def test_no_year_resolution_date_single(self):
        # NFL resolves in February
        resolution = datetime(2026, 2, 15, tzinfo=timezone.utc)
        assert detect_season("Super Bowl Winner", league="NFL", resolution_date=resolution) == "2026"

    def test_no_year_resolution_date_fall_split(self):
        # EPL starts in September = 2025-26 season
        resolution = datetime(2026, 5, 20, tzinfo=timezone.utc)
        assert detect_season("EPL Winner", league="EPL", resolution_date=resolution) == "2025-26"

    def test_no_info_returns_none(self):
        assert detect_season("Some Market") is None

    def test_no_league_with_year(self):
        assert detect_season("Something 2026") == "2026"

    def test_politics_year(self):
        assert detect_season("Presidential Election 2028", league="US") == "2028"


# =============================================================================
# Canonical Market Key
# =============================================================================
class TestCanonicalMarketKey:
    def test_full_key(self):
        key = compute_canonical_market_key("basketball", "NBA", "championship", "2025-26")
        assert key == "basketball:NBA:championship:2025-26"

    def test_football_nfl(self):
        key = compute_canonical_market_key("football", "NFL", "mvp", "2025")
        assert key == "football:NFL:mvp:2025"

    def test_hockey_nhl(self):
        key = compute_canonical_market_key("hockey", "NHL", "championship", "2025-26")
        assert key == "hockey:NHL:championship:2025-26"

    def test_missing_league(self):
        key = compute_canonical_market_key("basketball", None, "championship", "2025-26")
        assert key == "basketball::championship:2025-26"

    def test_missing_season(self):
        key = compute_canonical_market_key("basketball", "NBA", "championship", None)
        assert key == "basketball:NBA:championship:"

    def test_missing_sport_returns_none(self):
        key = compute_canonical_market_key(None, "NBA", "championship", "2025-26")
        assert key is None

    def test_missing_category_returns_none(self):
        key = compute_canonical_market_key("basketball", "NBA", None, "2025-26")
        assert key is None

    def test_politics(self):
        key = compute_canonical_market_key("politics", "US", "prediction", "2026")
        assert key == "politics:US:prediction:2026"

    def test_case_normalization(self):
        key = compute_canonical_market_key("Basketball", "nba", "Championship", "2025-26")
        assert key == "basketball:NBA:championship:2025-26"

    def test_whitespace_stripped(self):
        key = compute_canonical_market_key(" basketball ", " NBA ", " championship ", " 2025-26 ")
        assert key == "basketball:NBA:championship:2025-26"


# =============================================================================
# Integration: League + Season + Canonical Key from market name
# =============================================================================
class TestCrossSourceMatching:
    """Test that the same conceptual market produces matching canonical keys
    regardless of source-specific naming."""

    def test_nba_championship_odds_api(self):
        """Odds API: sport_key provides league, market name provides name."""
        league = detect_league("NBA Championship Winner 2025-26", "basketball_nba_championship_winner")
        season = detect_season("NBA Championship Winner 2025-26", league)
        key = compute_canonical_market_key("basketball", league, "championship", season)
        assert key == "basketball:NBA:championship:2025-26"

    def test_nba_championship_kalshi(self):
        """Kalshi: league and season from market name only."""
        league = detect_league("NBA Championship")
        # Kalshi has resolution_date
        resolution = datetime(2026, 6, 20, tzinfo=timezone.utc)
        season = detect_season("NBA Championship", league, resolution)
        key = compute_canonical_market_key("basketball", league, "championship", season)
        assert key == "basketball:NBA:championship:2025-26"

    def test_nba_championship_polymarket(self):
        """Polymarket: league from title, season from end date."""
        league = detect_league("2025-26 NBA Championship Winner")
        season = detect_season("2025-26 NBA Championship Winner", league)
        key = compute_canonical_market_key("basketball", league, "championship", season)
        assert key == "basketball:NBA:championship:2025-26"

    def test_nfl_mvp_matches_across_sources(self):
        # Odds API
        league1 = detect_league("NFL MVP", "americanfootball_nfl_mvp")
        season1 = detect_season("NFL MVP", league1, datetime(2026, 2, 10, tzinfo=timezone.utc))
        key1 = compute_canonical_market_key("football", league1, "mvp", season1)

        # Kalshi
        league2 = detect_league("NFL MVP Winner")
        season2 = detect_season("NFL MVP Winner", league2, datetime(2026, 2, 10, tzinfo=timezone.utc))
        key2 = compute_canonical_market_key("football", league2, "mvp", season2)

        assert key1 == key2
        assert key1 == "football:NFL:mvp:2026"

    def test_epl_winner_matches(self):
        league1 = detect_league("EPL Winner", "soccer_epl")
        season1 = detect_season("EPL Winner 2025-26", league1)
        key1 = compute_canonical_market_key("soccer", league1, "championship", season1)

        league2 = detect_league("Premier League Winner 2025-26")
        season2 = detect_season("Premier League Winner 2025-26", league2)
        key2 = compute_canonical_market_key("soccer", league2, "championship", season2)

        assert key1 == key2
        assert key1 == "soccer:EPL:championship:2025-26"


# =============================================================================
# League → Sport Category inference
# =============================================================================
class TestLeagueToSportInference:
    """Test that league abbreviations map to correct sport categories."""

    def test_nba_to_basketball(self):
        assert infer_sport_from_league("NBA") == "basketball"

    def test_nfl_to_football(self):
        assert infer_sport_from_league("NFL") == "football"

    def test_mlb_to_baseball(self):
        assert infer_sport_from_league("MLB") == "baseball"

    def test_nhl_to_hockey(self):
        assert infer_sport_from_league("NHL") == "hockey"

    def test_epl_to_soccer(self):
        assert infer_sport_from_league("EPL") == "soccer"

    def test_ucl_to_soccer(self):
        assert infer_sport_from_league("UCL") == "soccer"

    def test_pga_to_golf(self):
        assert infer_sport_from_league("PGA") == "golf"

    def test_atp_to_tennis(self):
        assert infer_sport_from_league("ATP") == "tennis"

    def test_ufc_to_mma(self):
        assert infer_sport_from_league("UFC") == "mma"

    def test_f1_to_motorsports(self):
        assert infer_sport_from_league("F1") == "motorsports"

    def test_nascar_to_motorsports(self):
        assert infer_sport_from_league("NASCAR") == "motorsports"

    def test_ipl_to_cricket(self):
        assert infer_sport_from_league("IPL") == "cricket"

    def test_afl_to_aussierules(self):
        assert infer_sport_from_league("AFL") == "aussierules"

    def test_none_returns_none(self):
        assert infer_sport_from_league(None) is None

    def test_empty_returns_none(self):
        assert infer_sport_from_league("") is None

    def test_unknown_league_returns_none(self):
        assert infer_sport_from_league("XYZZY") is None

    def test_case_insensitive(self):
        assert infer_sport_from_league("nba") == "basketball"
        assert infer_sport_from_league("Nfl") == "football"

    def test_all_leagues_have_sport(self):
        """Every league in the mapping should return a non-None sport."""
        for league, sport in LEAGUE_TO_SPORT_CATEGORY.items():
            result = infer_sport_from_league(league)
            assert result == sport, f"League {league} expected {sport}, got {result}"

    def test_politics_league(self):
        assert infer_sport_from_league("US") == "politics"

    def test_awards_league(self):
        assert infer_sport_from_league("AWARDS") == "entertainment"


# =============================================================================
# Non-sports pattern matching (new categories)
# =============================================================================
class TestNonSportsPatterns:
    """Test expanded non-sports SPORT_PATTERNS."""

    # -- Crypto / Digital Assets --
    def test_bitcoin(self):
        assert categorize_by_rules("Bitcoin to reach $100K?") == "crypto"

    def test_ethereum(self):
        assert categorize_by_rules("Ethereum price above $5000") == "crypto"

    def test_solana(self):
        assert categorize_by_rules("Solana market cap doubles") == "crypto"

    def test_crypto(self):
        assert categorize_by_rules("Crypto market recovery") == "crypto"

    # -- Economics / Finance --
    def test_fed_rate(self):
        assert categorize_by_rules("Fed rate cut in March") == "economics"

    def test_inflation(self):
        assert categorize_by_rules("US inflation above 3%") == "economics"

    def test_gdp(self):
        assert categorize_by_rules("GDP growth exceeds 4%") == "economics"

    def test_recession(self):
        assert categorize_by_rules("Will there be a recession in 2026?") == "economics"

    def test_unemployment(self):
        assert categorize_by_rules("Unemployment rate falls below 4%") == "economics"

    def test_tariff(self):
        assert categorize_by_rules("New tariff on Chinese imports") == "economics"

    def test_stock_market(self):
        assert categorize_by_rules("S&P 500 reaches new high") == "economics"

    # -- Tech / Science / AI --
    def test_openai(self):
        assert categorize_by_rules("OpenAI releases GPT-5") == "tech"

    def test_spacex(self):
        assert categorize_by_rules("SpaceX Starship lands successfully") == "tech"

    def test_quantum_computing(self):
        assert categorize_by_rules("Quantum computing breakthrough") == "tech"

    # -- Weather / Climate --
    def test_hurricane(self):
        assert categorize_by_rules("Hurricane hits Florida") == "weather"

    def test_temperature(self):
        assert categorize_by_rules("Temperature records broken") == "weather"

    def test_earthquake(self):
        assert categorize_by_rules("Major earthquake in California") == "weather"

    # -- Health --
    def test_pandemic(self):
        assert categorize_by_rules("Next pandemic declaration") == "health"

    def test_fda_approval(self):
        assert categorize_by_rules("FDA approval of new drug") == "health"

    def test_bird_flu(self):
        assert categorize_by_rules("Bird flu outbreak spreads") == "health"

    # -- Geopolitics --
    def test_ukraine(self):
        assert categorize_by_rules("Ukraine ceasefire agreement") == "geopolitics"

    def test_nato(self):
        assert categorize_by_rules("NATO expansion decision") == "geopolitics"

    def test_china_taiwan(self):
        assert categorize_by_rules("China-Taiwan tensions escalate") == "geopolitics"

    def test_middle_east(self):
        assert categorize_by_rules("Middle East peace deal") == "geopolitics"

    def test_sanctions(self):
        assert categorize_by_rules("New sanctions on Russia") == "geopolitics"

    # -- Legal / Regulatory --
    def test_supreme_court(self):
        assert categorize_by_rules("Supreme Court rules on case") == "legal"

    def test_indictment(self):
        assert categorize_by_rules("Federal indictment announced") == "legal"

    def test_antitrust(self):
        assert categorize_by_rules("Antitrust case against Google") == "legal"

    # -- Culture / Social --
    def test_tiktok_ban(self):
        # TikTok matches the entertainment pattern (tv/tiktok/influencer)
        assert categorize_by_rules("TikTok ban upheld") == "entertainment"

    def test_nobel_prize(self):
        assert categorize_by_rules("Nobel Prize in Physics") == "culture"

    # -- Existing categories still work --
    def test_politics_still_works(self):
        assert categorize_by_rules("2028 Presidential election") == "politics"

    def test_entertainment_still_works(self):
        assert categorize_by_rules("Oscar Best Picture winner") == "entertainment"

    def test_esports_still_works(self):
        assert categorize_by_rules("League of Legends World Championship") == "esports"


# =============================================================================
# League inference upgrading "other" markets
# =============================================================================
class TestLeagueInferenceUpgrade:
    """Test that league detection can upgrade 'other' markets to proper categories."""

    def test_stanley_cup_upgrades_via_league(self):
        """Market mentions Stanley Cup → NHL → hockey, even if rules somehow missed it."""
        league = detect_league("Stanley Cup Winner 2026")
        assert league == "NHL"
        sport = infer_sport_from_league(league)
        assert sport == "hockey"

    def test_super_bowl_upgrades_via_league(self):
        league = detect_league("Super Bowl LXI Champion")
        assert league == "NFL"
        sport = infer_sport_from_league(league)
        assert sport == "football"

    def test_wimbledon_upgrades_via_league(self):
        league = detect_league("Wimbledon 2026 Winner")
        assert league == "ATP"
        sport = infer_sport_from_league(league)
        assert sport == "tennis"

    def test_premier_league_upgrades_via_league(self):
        league = detect_league("Premier League Top Scorer")
        assert league == "EPL"
        sport = infer_sport_from_league(league)
        assert sport == "soccer"

    def test_champions_league_upgrades_via_league(self):
        league = detect_league("Champions League Winner")
        assert league == "UCL"
        sport = infer_sport_from_league(league)
        assert sport == "soccer"

    def test_ipl_upgrades_via_league(self):
        league = detect_league("IPL 2026 Champion")
        assert league == "IPL"
        sport = infer_sport_from_league(league)
        assert sport == "cricket"

    def test_masters_upgrades_via_league(self):
        league = detect_league("The Masters 2026 Winner")
        assert league == "PGA"
        sport = infer_sport_from_league(league)
        assert sport == "golf"

    def test_sport_key_provides_league(self):
        """Odds API sport_key can provide league even when name is ambiguous."""
        league = detect_league("Regular Season Wins", "basketball_nba_championship")
        assert league == "NBA"
        sport = infer_sport_from_league(league)
        assert sport == "basketball"


# =============================================================================
# Olympic discipline extraction
# =============================================================================
class TestOlympicDisciplineExtraction:
    """Test extraction of specific Olympic disciplines from market names."""

    def test_curling(self):
        assert extract_olympic_discipline("Who wins Curling Gold Medal?") == "curling"

    def test_figure_skating(self):
        assert extract_olympic_discipline("2026 Winter Olympics Figure Skating") == "figure_skating"

    def test_speed_skating(self):
        assert extract_olympic_discipline("Speed Skating 1000m Winner") == "speed_skating"

    def test_alpine_skiing(self):
        assert extract_olympic_discipline("Alpine Skiing Downhill Gold") == "alpine_skiing"

    def test_bobsled(self):
        assert extract_olympic_discipline("Bobsled 4-Man Gold Medal") == "bobsled"

    def test_ice_hockey(self):
        assert extract_olympic_discipline("Ice Hockey Gold Medal Winner") == "ice_hockey"

    def test_swimming(self):
        assert extract_olympic_discipline("Swimming 100m Butterfly Final") == "swimming"

    def test_gymnastics(self):
        assert extract_olympic_discipline("Gymnastics All-Around Gold") == "gymnastics"

    def test_track_and_field(self):
        assert extract_olympic_discipline("Track and Field 100m") == "track_and_field"

    def test_no_discipline(self):
        assert extract_olympic_discipline("2026 Winter Olympics Medal Count") is None

    def test_generic_olympics_no_match(self):
        assert extract_olympic_discipline("Most Gold Medals 2026") is None

    def test_biathlon(self):
        assert extract_olympic_discipline("Biathlon Sprint Winner") == "biathlon"

    def test_cross_country(self):
        assert extract_olympic_discipline("Cross-Country Skiing 50km") == "cross_country_skiing"


# =============================================================================
# Cross-source Olympic matching
# =============================================================================
class TestCrossSourceOlympicMatching:
    """Test that Olympic events match across Kalshi and Polymarket."""

    def test_curling_matches_across_sources(self):
        """Both sources should produce the same canonical key for curling."""
        # Kalshi-style market (usually includes "Olympics" in title)
        name1 = "2026 Winter Olympics Men's Curling Gold Medal"
        league1 = detect_league(name1)
        season1 = detect_season(name1, league1,
                                datetime(2026, 2, 28, tzinfo=timezone.utc))
        discipline1 = extract_olympic_discipline(name1)
        key1 = compute_canonical_market_key("olympics", league1, discipline1 or "championship", season1)

        # Polymarket-style market
        name2 = "2026 Winter Olympics Curling Gold Medal"
        league2 = detect_league(name2)
        season2 = detect_season(name2, league2)
        discipline2 = extract_olympic_discipline(name2)
        key2 = compute_canonical_market_key("olympics", league2, discipline2 or "championship", season2)

        assert key1 == key2
        assert discipline1 == "curling"
        assert discipline2 == "curling"
        assert "curling" in key1
        assert league1 == "OLYMPICS"
        assert league2 == "OLYMPICS"

    def test_figure_skating_matches(self):
        """Figure skating should match across sources."""
        discipline1 = extract_olympic_discipline("Figure Skating Gold Medal Winner")
        discipline2 = extract_olympic_discipline("2026 Olympics Figure Skating Champion")
        assert discipline1 == discipline2 == "figure_skating"


# =============================================================================
# Additional sports patterns (coach, awards, misspellings)
# =============================================================================
class TestAdditionalSportsPatterns:
    """Test newly added sports patterns for common uncategorized markets."""

    # Coach/manager awards
    def test_nba_coach(self):
        assert categorize_by_rules("NBA Coach of the Year") == "basketball"

    def test_nfl_coach(self):
        assert categorize_by_rules("NFL Coach of the Year") == "football"

    def test_mlb_manager(self):
        assert categorize_by_rules("MLB Manager of the Year") == "baseball"

    def test_nhl_jack_adams(self):
        assert categorize_by_rules("NHL Jack Adams Award") == "hockey"

    def test_generic_coach(self):
        # Without league context, defaults to football (most common)
        assert categorize_by_rules("Coach of the Year") == "football"

    def test_generic_manager(self):
        assert categorize_by_rules("Manager of the Year") == "baseball"

    # Crypto misspellings
    def test_etherium_misspelling(self):
        assert categorize_by_rules("Price of Etherium above $5000") == "crypto"

    def test_doge_coin_split(self):
        assert categorize_by_rules("Doge Coin reaches $1") == "crypto"

    def test_litecoin(self):
        assert categorize_by_rules("Litecoin price prediction") == "crypto"

    def test_polkadot(self):
        assert categorize_by_rules("Polkadot market cap") == "crypto"

    def test_price_of_bitcoin(self):
        assert categorize_by_rules("Price of Bitcoin above $200K") == "crypto"

    # Football stats
    def test_rushing_leader(self):
        assert categorize_by_rules("Rushing Yards Leader 2026") == "football"

    def test_passing_touchdown(self):
        assert categorize_by_rules("Passing Touchdown Leader") == "football"

    # Baseball stats
    def test_home_run_leader(self):
        assert categorize_by_rules("Home Run Leader 2026") == "baseball"

    def test_no_hitter(self):
        assert categorize_by_rules("Next No-Hitter thrown") == "baseball"

    # Swimming/athletics → olympics
    def test_swimming_to_olympics(self):
        assert categorize_by_rules("Swimming 100m butterfly winner") == "olympics"

    def test_100m_dash(self):
        assert categorize_by_rules("100m World Record broken") == "olympics"

    def test_marathon(self):
        assert categorize_by_rules("Marathon world record 2026") == "olympics"

    # Existing patterns still work
    def test_nba_mvp_still_works(self):
        assert categorize_by_rules("NBA MVP Winner 2026") == "basketball"

    def test_super_bowl_still_works(self):
        assert categorize_by_rules("Super Bowl LXI Winner") == "football"

    def test_stanley_cup_still_works(self):
        assert categorize_by_rules("Stanley Cup Champion") == "hockey"


# =============================================================================
# Game Prop Detection
# =============================================================================
class TestGamePropDetection:
    """Test detection of game prop markets (Team at Team: Stat)."""

    def test_basketball_rebounds(self):
        assert detect_game_prop_sport("Boston at Golden State: Rebounds") == "basketball"

    def test_basketball_points(self):
        assert detect_game_prop_sport("Detroit at New York: Points") == "basketball"

    def test_basketball_assists(self):
        assert detect_game_prop_sport("Lakers at Celtics: Assists") == "basketball"

    def test_basketball_3pointers(self):
        assert detect_game_prop_sport("Miami at Chicago: 3-Pointers") == "basketball"

    def test_basketball_blocks(self):
        assert detect_game_prop_sport("Denver at Portland: Blocks") == "basketball"

    def test_basketball_steals(self):
        assert detect_game_prop_sport("Phoenix at Dallas: Steals") == "basketball"

    def test_basketball_free_throws(self):
        assert detect_game_prop_sport("Milwaukee at Indiana: Free Throws") == "basketball"

    def test_football_passing_yards(self):
        assert detect_game_prop_sport("Kansas City at Buffalo: Passing Yards") == "football"

    def test_football_rushing_yards(self):
        assert detect_game_prop_sport("Dallas at Philadelphia: Rushing Yards") == "football"

    def test_football_touchdowns(self):
        assert detect_game_prop_sport("Green Bay at Chicago: Touchdowns") == "football"

    def test_football_sacks(self):
        assert detect_game_prop_sport("Pittsburgh at Baltimore: Sacks") == "football"

    def test_hockey_saves(self):
        assert detect_game_prop_sport("Montreal at Toronto: Saves") == "hockey"

    def test_hockey_shots_on_goal(self):
        assert detect_game_prop_sport("Edmonton at Vancouver: Shots on Goal") == "hockey"

    def test_baseball_strikeouts(self):
        assert detect_game_prop_sport("Yankees at Red Sox: Strikeouts") == "baseball"

    def test_baseball_home_runs(self):
        assert detect_game_prop_sport("Dodgers at Giants: Home Runs") == "baseball"

    def test_soccer_corners(self):
        assert detect_game_prop_sport("Arsenal at Chelsea: Corners") == "soccer"

    def test_ambiguous_spread_uses_seasonal(self):
        """Spread is ambiguous — uses seasonal inference as tiebreaker."""
        result = detect_game_prop_sport("Orlando at Sacramento: Spread")
        # Returns seasonal sport (basketball in Feb-Apr, football in Aug-Oct, None in Nov-Jan)
        assert result in ("basketball", "football", "baseball", None)

    def test_ambiguous_total_uses_seasonal(self):
        result = detect_game_prop_sport("Phoenix at San Antonio: Total")
        assert result in ("basketball", "football", "baseball", None)

    def test_not_a_game_prop(self):
        assert detect_game_prop_sport("NBA Championship 2025-26") is None

    def test_is_game_prop_true(self):
        assert is_game_prop("Boston at Golden State: Rebounds") is True

    def test_is_game_prop_false(self):
        assert is_game_prop("NBA MVP 2025-26") is False

    def test_vs_format(self):
        assert detect_game_prop_sport("Boston vs Golden State: Rebounds") == "basketball"

    def test_game_prop_flows_through_categorize_by_rules(self):
        """Game prop detection should be used by categorize_by_rules."""
        assert categorize_by_rules("Boston at Golden State: Rebounds") == "basketball"
        assert categorize_by_rules("Detroit at New York: Points") == "basketball"
        assert categorize_by_rules("Kansas City at Buffalo: Passing Yards") == "football"


# =============================================================================
# Category Tag Generation
# =============================================================================
class TestCategoryTagGeneration:
    """Test multi-category tag generation."""

    def test_basic_sport_tag(self):
        tags = generate_category_tags("NBA Championship", "basketball", "NBA", "championship")
        assert "basketball" in tags
        assert "nba" in tags

    def test_crypto_tags(self):
        tags = generate_category_tags("Bitcoin price above $100K", "crypto", None, None)
        assert "crypto" in tags
        assert "bitcoin" in tags

    def test_cross_category_politics_crypto(self):
        """Market about Trump + Bitcoin gets both tags."""
        tags = generate_category_tags("Will Trump create a Bitcoin reserve?", "politics", None, None)
        assert "politics" in tags
        assert "trump" in tags
        assert "bitcoin" in tags
        assert "crypto" in tags

    def test_game_prop_tag(self):
        tags = generate_category_tags("Boston at Golden State: Rebounds", "basketball", "NBA", "game_prop")
        assert "game_prop" in tags
        assert "basketball" in tags

    def test_super_bowl_tag(self):
        tags = generate_category_tags("Super Bowl LXI Winner", "football", "NFL", "championship")
        assert "super_bowl" in tags
        assert "football" in tags

    def test_mvp_tag(self):
        tags = generate_category_tags("NBA MVP Winner", "basketball", "NBA", "mvp")
        assert "mvp" in tags
        assert "basketball" in tags

    def test_love_is_blind_tag(self):
        tags = generate_category_tags("Love Is Blind Season 9 winner", "entertainment", None, None)
        assert "entertainment" in tags
        assert "love_is_blind" in tags

    def test_other_category_not_tagged(self):
        """Primary category 'other' should NOT be added as a tag."""
        tags = generate_category_tags("Unknown Market XYZ", "other", None, None)
        assert "other" not in tags

    def test_sorted_output(self):
        """Tags should be sorted alphabetically."""
        tags = generate_category_tags("Super Bowl Bitcoin bet", "football", "NFL", "championship")
        assert tags == sorted(tags)

    def test_elon_musk_tag(self):
        tags = generate_category_tags("Will Elon Musk buy TikTok?", "tech", None, None)
        assert "elon_musk" in tags


# =============================================================================
# New Pattern Tests
# =============================================================================
class TestNewPatterns:
    """Test newly added categorization patterns."""

    def test_nascar_400_winner(self):
        assert categorize_by_rules("Autotrader 400 Winner?") == "motorsports"

    def test_nascar_250_winner(self):
        assert categorize_by_rules("Bennett Transportation & Logistics 250 Winner?") == "motorsports"

    def test_nascar_500_winner(self):
        assert categorize_by_rules("Daytona 500 Winner?") == "motorsports"

    def test_love_is_blind(self):
        assert categorize_by_rules("Love Is Blind Season 9: Who gets engaged?") == "entertainment"

    def test_survivor(self):
        assert categorize_by_rules("Survivor Season 50 winner") == "entertainment"

    def test_overall_pick(self):
        assert categorize_by_rules("#1 overall pick in 2026?") == "football"

    def test_first_pick(self):
        assert categorize_by_rules("Who is the first pick?") == "football"

    def test_powell(self):
        assert categorize_by_rules("What will Powell say at the press conference?") == "economics"

    def test_sol_price(self):
        assert categorize_by_rules("SOL price above $200?") == "crypto"

    def test_ada_price(self):
        assert categorize_by_rules("ADA price above $1?") == "crypto"

    def test_xfinity_series(self):
        assert categorize_by_rules("Xfinity Series race winner") == "motorsports"

    def test_big_brother(self):
        assert categorize_by_rules("Big Brother Season 28 winner") == "entertainment"

    def test_the_voice(self):
        assert categorize_by_rules("The Voice Season 30 winner") == "entertainment"

    def test_love_island(self):
        assert categorize_by_rules("Love Island UK winner") == "entertainment"

    def test_engagement_on_show(self):
        """Reality TV engagement markets should be entertainment."""
        assert categorize_by_rules("Will they get engaged on Love Is Blind Season 9?") == "entertainment"
