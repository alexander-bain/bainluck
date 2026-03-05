"""Tests for market type classification."""

import pytest
from app.utils.market_classification import (
    MarketType,
    classify_market,
    is_award,
    is_game_market,
    is_not_championship,
    is_stat_prop,
)


# =============================================================================
# MarketType enum
# =============================================================================

class TestMarketTypeEnum:
    """Tests for the MarketType enum."""

    def test_string_values(self):
        assert MarketType.championship == "championship"
        assert MarketType.conference == "conference"
        assert MarketType.award == "award"
        assert MarketType.division == "division"
        assert MarketType.game == "game"
        assert MarketType.stat_prop == "stat_prop"
        assert MarketType.other == "other"

    def test_all_members(self):
        assert len(MarketType) == 7

    def test_is_str_subclass(self):
        assert isinstance(MarketType.championship, str)

    def test_from_string(self):
        assert MarketType("championship") == MarketType.championship
        assert MarketType("stat_prop") == MarketType.stat_prop

    def test_invalid_string_raises(self):
        with pytest.raises(ValueError):
            MarketType("invalid")


# =============================================================================
# is_stat_prop
# =============================================================================

class TestIsStatProp:
    """Tests for stat prop detection."""

    def test_points(self):
        assert is_stat_prop("Boston at Golden State: Points")

    def test_rebounds(self):
        assert is_stat_prop("Lakers at Celtics: Rebounds")

    def test_assists(self):
        assert is_stat_prop("Heat at Bucks: Assists")

    def test_three_pointers(self):
        assert is_stat_prop("Warriors at Suns: Three Pointers")
        assert is_stat_prop("Warriors at Suns: 3-Pointers")
        assert is_stat_prop("Warriors at Suns: 3 Pointers")

    def test_passing_yards(self):
        assert is_stat_prop("Chiefs at Ravens: Passing Yards")

    def test_rushing_yards(self):
        assert is_stat_prop("Cowboys at Eagles: Rushing Yards")

    def test_touchdowns(self):
        assert is_stat_prop("Packers at Bears: Touchdowns")

    def test_strikeouts(self):
        assert is_stat_prop("Yankees at Red Sox: Strikeouts")

    def test_home_runs(self):
        assert is_stat_prop("Dodgers at Giants: Home Runs")

    def test_goals(self):
        assert is_stat_prop("Rangers at Devils: Goals")

    def test_double_doubles(self):
        assert is_stat_prop("Nuggets at Lakers: Double Doubles")
        assert is_stat_prop("Nuggets at Lakers: Double Double")

    def test_triple_doubles(self):
        assert is_stat_prop("Thunder at Mavs: Triple Doubles")

    def test_not_stat_prop_championship(self):
        assert not is_stat_prop("NBA Championship 2025-26")

    def test_not_stat_prop_mvp(self):
        assert not is_stat_prop("NBA MVP Winner")

    def test_not_stat_prop_game(self):
        assert not is_stat_prop("Lakers vs. Celtics")


# =============================================================================
# is_game_market
# =============================================================================

class TestIsGameMarket:
    """Tests for game-level market detection."""

    def test_vs_dot(self):
        assert is_game_market("Lakers vs. Celtics")

    def test_vs_no_dot(self):
        assert is_game_market("Lakers vs Celtics")

    def test_en_dash(self):
        assert is_game_market("Lakers – Celtics")

    def test_more_markets(self):
        assert is_game_market("NBA: Lakers at Celtics - More Markets")

    def test_moneyline(self):
        assert is_game_market("Game 3 Moneyline")

    def test_game_number(self):
        assert is_game_market("Game 7")
        assert is_game_market("Game 1 - Series Winner")

    def test_at_matchup(self):
        assert is_game_market("Stanford at Miami")

    def test_not_game_championship(self):
        assert not is_game_market("NBA Championship 2025-26")

    def test_not_game_mvp(self):
        assert not is_game_market("NBA MVP Winner")


# =============================================================================
# is_award
# =============================================================================

class TestIsAward:
    """Tests for award market detection."""

    def test_mvp(self):
        assert is_award("NBA MVP")

    def test_finals_mvp(self):
        assert is_award("NBA Finals MVP")

    def test_wcf_mvp(self):
        assert is_award("WCF MVP")

    def test_ecf_mvp(self):
        assert is_award("ECF MVP")

    def test_rookie(self):
        assert is_award("NBA Rookie of the Year")

    def test_cy_young(self):
        assert is_award("AL Cy Young Award")
        assert is_award("NL CyYoung")

    def test_golden_boot(self):
        assert is_award("Premier League Golden Boot")

    def test_golden_glove(self):
        assert is_award("Gold Glove Award")  # "golden glove" pattern
        # Exact "golden glove"
        assert is_award("Golden Glove")

    def test_player_of_year(self):
        assert is_award("Defensive Player of the Year")
        assert is_award("Player of Year")

    def test_most_improved(self):
        assert is_award("Most Improved Player")

    def test_sixth_man(self):
        assert is_award("Sixth Man of the Year")
        assert is_award("6th Man")

    def test_all_star_mvp(self):
        assert is_award("All-Star MVP")
        assert is_award("All Star MVP")

    def test_scoring_leader(self):
        assert is_award("NBA Scoring Leader")

    def test_home_run_leader(self):
        assert is_award("Home Run Leader")

    def test_best_picture(self):
        assert is_award("Best Picture")

    def test_best_actor(self):
        assert is_award("Best Actor")

    def test_best_director(self):
        assert is_award("Best Director")

    def test_cover_of_2k(self):
        assert is_award("Cover of NBA 2K")
        assert is_award("NBA 2K Cover")

    def test_heisman(self):
        assert is_award("Heisman Trophy Winner")

    def test_hart_trophy(self):
        assert is_award("Hart Trophy")

    def test_vezina(self):
        assert is_award("Vezina Trophy Winner")

    def test_not_award_championship(self):
        assert not is_award("NBA Championship 2025-26")

    def test_not_award_game(self):
        assert not is_award("Lakers vs. Celtics")

    def test_per_game(self):
        assert is_award("Points Per Game Leader")

    def test_clutch(self):
        assert is_award("Clutch Player of the Year")


# =============================================================================
# is_not_championship
# =============================================================================

class TestIsNotChampionship:
    """Tests for NOT-championship detection (markets that shouldn't be hero cards)."""

    def test_win_total(self):
        assert is_not_championship("NBA Season Win Totals")

    def test_over_under(self):
        assert is_not_championship("Season Over/Under Wins")

    def test_regular_season_wins(self):
        assert is_not_championship("Regular Season Wins")

    def test_cover_of_2k(self):
        assert is_not_championship("Cover of NBA 2K")

    def test_2k(self):
        assert is_not_championship("NBA 2K Cover Athlete")

    def test_make_playoffs(self):
        assert is_not_championship("Make Playoffs?")

    def test_playoff_appearance(self):
        assert is_not_championship("Playoff Appearance")

    def test_playoff_berth(self):
        assert is_not_championship("Playoff Berth")

    def test_to_make(self):
        assert is_not_championship("Lakers To Make Playoffs")

    def test_seeding(self):
        assert is_not_championship("NBA Seeding Odds")

    def test_seed(self):
        assert is_not_championship("#1 Seed in East")

    def test_over_number(self):
        assert is_not_championship("Over 48.5 Wins")

    def test_under_number(self):
        assert is_not_championship("Under 48.5 Wins")

    def test_exact_wins(self):
        assert is_not_championship("Exact Wins 52")

    def test_real_championship_not_flagged(self):
        assert not is_not_championship("NBA Championship 2025-26")

    def test_real_super_bowl_not_flagged(self):
        assert not is_not_championship("Super Bowl Winner")


# =============================================================================
# classify_market — full pipeline
# =============================================================================

class TestClassifyMarket:
    """Tests for the main classify_market function."""

    # --- Stat props (highest priority) ---

    def test_stat_prop_points(self):
        assert classify_market("Boston at Golden State: Points") == MarketType.stat_prop

    def test_stat_prop_rebounds(self):
        assert classify_market("Lakers at Celtics: Rebounds") == MarketType.stat_prop

    def test_stat_prop_passing_yards(self):
        assert classify_market("Chiefs at Ravens: Passing Yards") == MarketType.stat_prop

    # --- Game markets ---

    def test_game_vs(self):
        assert classify_market("Lakers vs. Celtics") == MarketType.game

    def test_game_en_dash(self):
        assert classify_market("Lakers – Celtics") == MarketType.game

    def test_game_moneyline(self):
        assert classify_market("Game 3 Moneyline") == MarketType.game

    def test_game_at_matchup(self):
        assert classify_market("Stanford at Miami") == MarketType.game

    # --- Awards ---

    def test_award_mvp(self):
        assert classify_market("NBA MVP") == MarketType.award

    def test_award_rookie(self):
        assert classify_market("Rookie of the Year") == MarketType.award

    def test_award_heisman(self):
        assert classify_market("Heisman Trophy") == MarketType.award

    def test_award_best_picture(self):
        assert classify_market("Best Picture") == MarketType.award

    # --- NOT-championship guard ---

    def test_win_total_not_championship(self):
        assert classify_market("NBA Season Win Totals") == MarketType.other

    def test_make_playoffs_not_championship(self):
        assert classify_market("Make Playoffs?") == MarketType.other

    def test_seeding_not_championship(self):
        assert classify_market("NBA Seeding") == MarketType.other

    def test_over_wins_not_championship(self):
        assert classify_market("Over 48.5 Wins") == MarketType.other

    # --- Conference ---

    def test_conference_eastern(self):
        assert classify_market("Eastern Conference Champion") == MarketType.conference

    def test_conference_western(self):
        assert classify_market("Western Conference Winner") == MarketType.conference

    def test_conference_afc(self):
        assert classify_market("AFC Championship Winner") == MarketType.conference

    def test_conference_nfc(self):
        assert classify_market("NFC Championship") == MarketType.conference

    # --- Division ---

    def test_division_winner(self):
        assert classify_market("Division Winner") == MarketType.division

    def test_division_afc_east(self):
        assert classify_market("AFC East Winner") == MarketType.division

    def test_division_nl_central(self):
        assert classify_market("NL Central Champion") == MarketType.division

    # --- Championship ---

    def test_championship_nba(self):
        assert classify_market("NBA Championship 2025-26") == MarketType.championship

    def test_championship_super_bowl(self):
        assert classify_market("Super Bowl Winner") == MarketType.championship

    def test_championship_world_series(self):
        assert classify_market("World Series Winner") == MarketType.championship

    def test_championship_stanley_cup(self):
        assert classify_market("Stanley Cup Winner") == MarketType.championship

    def test_championship_march_madness(self):
        assert classify_market("March Madness Champion") == MarketType.championship

    # --- Backend tier fallback ---

    def test_tier_1_fallback(self):
        assert classify_market("Some unknown market", market_tier=1) == MarketType.championship

    def test_tier_2_fallback(self):
        assert classify_market("Some unknown market", market_tier=2) == MarketType.conference

    def test_tier_3_fallback(self):
        assert classify_market("Some unknown market", market_tier=3) == MarketType.award

    def test_tier_4_fallback(self):
        assert classify_market("Some unknown market", market_tier=4) == MarketType.division

    def test_tier_5_no_fallback(self):
        """Tier 5 (props) doesn't have a tier_map entry, falls through to other."""
        assert classify_market("Some unknown market", market_tier=5) == MarketType.other

    # --- Category string fallback ---

    def test_category_championship(self):
        assert classify_market("Random market", category="championship") == MarketType.championship

    def test_category_award(self):
        assert classify_market("Random market", category="award") == MarketType.award

    def test_category_invalid_ignored(self):
        assert classify_market("Random market", category="banana") == MarketType.other

    # --- Empty/None ---

    def test_empty_string(self):
        assert classify_market("") == MarketType.other

    # --- Priority order tests ---

    def test_stat_prop_beats_game(self):
        """A stat prop with 'at' should be stat_prop, not game."""
        assert classify_market("Boston at Golden State: Points") == MarketType.stat_prop

    def test_game_beats_award(self):
        """A game with 'vs' should be game even if it also has award-like words."""
        assert classify_market("MVP Candidate Team A vs. Team B") == MarketType.game

    def test_award_beats_championship(self):
        """An award market should be award, not championship, even with 'winner'."""
        assert classify_market("NBA MVP Winner") == MarketType.award

    def test_not_championship_beats_championship(self):
        """Win totals should NOT be championship even if they match championship patterns."""
        assert classify_market("NBA Championship Season Win Totals") == MarketType.other

    def test_pattern_beats_tier(self):
        """Pattern detection should override market_tier."""
        assert classify_market("NBA MVP", market_tier=1) == MarketType.award

    def test_pattern_beats_category(self):
        """Pattern detection should override category string."""
        assert classify_market("Lakers vs. Celtics", category="championship") == MarketType.game
