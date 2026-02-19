"""Tests for futures market sport categorization (rules engine)."""

import pytest
from unittest.mock import patch

from app.utils.futures_categorization import categorize_by_rules, categorize_market


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
