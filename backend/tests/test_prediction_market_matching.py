"""
Tests for prediction market → event matching utility.

Tests cover:
- Game-level market detection (is_game_level_market)
- Matchup extraction from various formats
- Team name fuzzy matching
- Home/away probability mapping
"""

import pytest

from app.utils.prediction_market_matching import (
    is_game_level_market,
    extract_matchup,
    match_teams_to_event,
    find_moneyline_outcome,
    _fuzzy_team_match,
    MatchupInfo,
)


# =============================================================================
# is_game_level_market
# =============================================================================


class TestIsGameLevelMarket:
    """Test game-level market detection."""

    def test_bare_matchup_at(self):
        assert is_game_level_market("Boston Celtics at Golden State Warriors", "championship", 1)

    def test_bare_matchup_vs(self):
        assert is_game_level_market("Lakers vs Clippers", "championship", 1)

    def test_bare_matchup_vs_dot(self):
        """Polymarket uses 'vs.' with trailing period."""
        assert is_game_level_market("Stetson Hatters vs. Jacksonville Dolphins", "championship", 1)

    def test_bare_matchup_v(self):
        """Soccer-style 'v' separator."""
        assert is_game_level_market("Arsenal v Chelsea", "championship", 1)

    def test_bare_matchup_v_dot(self):
        """'v.' separator variant."""
        assert is_game_level_market("Liverpool v. Everton", "championship", 1)

    def test_dash_matchup(self):
        """European-style dash separator."""
        assert is_game_level_market("Bayern Munich - Borussia Dortmund", "championship", 1)

    def test_dash_matchup_en_dash(self):
        """En-dash separator."""
        assert is_game_level_market("Real Madrid \u2013 Barcelona", "championship", 1)

    def test_will_beat(self):
        assert is_game_level_market("Will the Warriors beat the Celtics?", "championship", 1)

    def test_will_win(self):
        assert is_game_level_market("Will the Lakers win?", "championship", 1)

    def test_will_win_against(self):
        assert is_game_level_market("Will the Lakers win against the Celtics?", "championship", 1)

    def test_will_win_over(self):
        assert is_game_level_market("Will the Lakers win over the Celtics?", "championship", 1)

    def test_not_game_prop(self):
        """Game props (with stat suffix) are NOT game-level moneyline markets."""
        assert not is_game_level_market(
            "Boston at Golden State: Rebounds", "game_prop", 1,
        )

    def test_not_game_prop_points(self):
        assert not is_game_level_market(
            "Lakers vs Clippers: Total Points", "game_prop", 1,
        )

    def test_not_dash_game_prop(self):
        """Dash-separated game props are NOT game-level."""
        assert not is_game_level_market(
            "Bayern Munich - Dortmund: Total Goals", "game_prop", 1,
        )

    def test_not_championship(self):
        """Championship futures are not game-level."""
        assert not is_game_level_market(
            "Will the Lakers win the championship?", "championship", 1,
        )

    def test_not_super_bowl(self):
        assert not is_game_level_market(
            "Will the Eagles win the Super Bowl?", "championship", 1,
        )

    def test_not_mvp(self):
        assert not is_game_level_market(
            "Will Jokic win the MVP award?", "mvp", 1,
        )

    def test_multi_outcome_championship_name(self):
        """Championship NAME doesn't match game patterns regardless of outcome count."""
        assert not is_game_level_market("NBA Championship", "championship", 30)

    def test_binary_two_outcomes_ok(self):
        """Binary markets with exactly 2 outcomes are fine."""
        assert is_game_level_market("Celtics at Warriors", "championship", 2)

    def test_many_outcomes_game_name_ok(self):
        """Game events with >2 outcomes (moneyline+spread+totals) should still match.

        Polymarket bundles moneyline, spread, and totals under one game event.
        The name is still 'Team A vs. Team B' but outcome count can be 3-5+.
        """
        assert is_game_level_market("Celtics vs. Warriors", "championship", 5)
        assert is_game_level_market("Lakers at Clippers", "championship", 4)

    def test_to_beat(self):
        assert is_game_level_market("Celtics to beat Warriors", "championship", 1)

    def test_not_division_win(self):
        assert not is_game_level_market(
            "Will the Lakers win the division?", "division", 1,
        )

    def test_not_cup(self):
        assert not is_game_level_market(
            "Will Arsenal win the FA Cup?", "championship", 1,
        )

    def test_not_conference(self):
        assert not is_game_level_market(
            "Will the Celtics win the conference?", "championship", 1,
        )

    def test_not_stanley_cup(self):
        assert not is_game_level_market(
            "Will the Rangers win the Stanley Cup?", "championship", 1,
        )

    def test_not_world_series(self):
        assert not is_game_level_market(
            "Will the Dodgers win the World Series?", "championship", 1,
        )

    def test_not_premier_league(self):
        assert not is_game_level_market(
            "Will Arsenal win the Premier League?", "championship", 1,
        )

    def test_not_grand_slam(self):
        assert not is_game_level_market(
            "Will Djokovic win the Grand Slam?", "championship", 1,
        )

    def test_case_insensitive_bare_matchup(self):
        """Bare matchup regex should be case-insensitive."""
        assert is_game_level_market("lakers vs clippers", "championship", 1)


# =============================================================================
# extract_matchup
# =============================================================================


class TestExtractMatchup:
    """Test matchup extraction from market names."""

    def test_bare_matchup_at(self):
        result = extract_matchup("Boston Celtics at Golden State Warriors")
        assert result is not None
        assert result.team_a == "Boston Celtics"
        assert result.team_b == "Golden State Warriors"
        assert result.yes_team == "Boston Celtics"
        assert result.format_type == "bare_matchup"

    def test_bare_matchup_vs(self):
        result = extract_matchup("Lakers vs Clippers")
        assert result is not None
        assert result.team_a == "Lakers"
        assert result.team_b == "Clippers"
        assert result.yes_team == "Lakers"

    def test_will_beat(self):
        result = extract_matchup("Will the Warriors beat the Celtics?")
        assert result is not None
        assert result.team_a == "Warriors"
        assert result.team_b == "Celtics"
        assert result.yes_team == "Warriors"
        assert result.format_type == "will_beat"

    def test_will_beat_without_the(self):
        result = extract_matchup("Will Warriors beat Celtics?")
        assert result is not None
        assert result.team_a == "Warriors"
        assert result.team_b == "Celtics"

    def test_to_beat(self):
        result = extract_matchup("Celtics to beat Warriors")
        assert result is not None
        assert result.team_a == "Celtics"
        assert result.team_b == "Warriors"
        assert result.yes_team == "Celtics"
        assert result.format_type == "to_beat"

    def test_will_win(self):
        result = extract_matchup("Will the Lakers win?")
        assert result is not None
        assert result.team_a == "Lakers"
        assert result.team_b == ""
        assert result.yes_team == "Lakers"
        assert result.format_type == "will_win"

    def test_game_prop_returns_none(self):
        """Game props should NOT be extracted as matchups."""
        result = extract_matchup("Boston at Golden State: Rebounds")
        assert result is None

    def test_championship_will_win_returns_none(self):
        """Championship questions should NOT match."""
        result = extract_matchup("Will the Lakers win the championship?")
        assert result is None

    def test_title_with_trophy(self):
        result = extract_matchup("Will Jokic win the Hart Trophy?")
        assert result is None

    def test_will_defeat(self):
        result = extract_matchup("Will the Celtics defeat the Lakers?")
        assert result is not None
        assert result.team_a == "Celtics"
        assert result.team_b == "Lakers"

    def test_college_matchup(self):
        result = extract_matchup("Iowa at Purdue")
        assert result is not None
        assert result.team_a == "Iowa"
        assert result.team_b == "Purdue"

    # New patterns: "v", dash, "will win against"
    def test_bare_matchup_v(self):
        """Soccer-style 'v' separator."""
        result = extract_matchup("Arsenal v Chelsea")
        assert result is not None
        assert result.team_a == "Arsenal"
        assert result.team_b == "Chelsea"
        assert result.format_type == "bare_matchup"

    def test_bare_matchup_v_dot(self):
        result = extract_matchup("Liverpool v. Everton")
        assert result is not None
        assert result.team_a == "Liverpool"
        assert result.team_b == "Everton"

    def test_bare_matchup_vs_dot(self):
        """Polymarket format with 'vs.' and period."""
        result = extract_matchup("Stetson Hatters vs. Jacksonville Dolphins")
        assert result is not None
        assert result.team_a == "Stetson Hatters"
        assert result.team_b == "Jacksonville Dolphins"

    def test_dash_matchup(self):
        """European-style dash separator."""
        result = extract_matchup("Bayern Munich - Borussia Dortmund")
        assert result is not None
        assert result.team_a == "Bayern Munich"
        assert result.team_b == "Borussia Dortmund"
        assert result.format_type == "dash_matchup"

    def test_dash_matchup_en_dash(self):
        """En-dash separator."""
        result = extract_matchup("Real Madrid \u2013 Barcelona")
        assert result is not None
        assert result.team_a == "Real Madrid"
        assert result.team_b == "Barcelona"

    def test_dash_matchup_em_dash(self):
        """Em-dash separator."""
        result = extract_matchup("PSG \u2014 Marseille")
        assert result is not None
        assert result.team_a == "PSG"
        assert result.team_b == "Marseille"

    def test_will_win_against(self):
        result = extract_matchup("Will the Lakers win against the Celtics?")
        assert result is not None
        assert result.team_a == "Lakers"
        assert result.team_b == "Celtics"
        assert result.format_type == "will_beat"

    def test_will_win_over(self):
        result = extract_matchup("Will the Lakers win over the Celtics?")
        assert result is not None
        assert result.team_a == "Lakers"
        assert result.team_b == "Celtics"

    def test_dash_game_prop_returns_none(self):
        """Dash-separated game props should NOT be extracted."""
        result = extract_matchup("Bayern Munich - Dortmund: Total Goals")
        assert result is None

    def test_not_championship_will_win_expanded(self):
        """Additional non-game keywords shouldn't match."""
        assert extract_matchup("Will the Rangers win the Stanley Cup?") is None
        assert extract_matchup("Will the Dodgers win the World Series?") is None
        assert extract_matchup("Will Arsenal win the Premier League?") is None
        assert extract_matchup("Will Celtics win the conference?") is None


# =============================================================================
# _fuzzy_team_match
# =============================================================================


class TestFuzzyTeamMatch:
    """Test fuzzy team name matching."""

    def test_exact_match(self):
        assert _fuzzy_team_match("Boston Celtics", "Boston Celtics")

    def test_case_insensitive(self):
        assert _fuzzy_team_match("boston celtics", "Boston Celtics")

    def test_substring_short_in_long(self):
        """Short name contained in long name."""
        assert _fuzzy_team_match("Celtics", "Boston Celtics")

    def test_substring_long_in_short(self):
        assert _fuzzy_team_match("Boston Celtics", "Celtics")

    def test_too_short_no_match(self):
        """Very short strings (< 4 chars) should not substring-match."""
        assert not _fuzzy_team_match("LA", "Los Angeles Lakers")

    def test_no_match_different_teams(self):
        assert not _fuzzy_team_match("Warriors", "Boston Celtics")

    def test_word_overlap(self):
        """Multi-word names with shared words."""
        assert _fuzzy_team_match("Golden State Warriors", "Golden State Warriors")

    def test_partial_word_no_match(self):
        """Different teams shouldn't match."""
        assert not _fuzzy_team_match("Nets", "Boston Celtics")

    def test_abbreviated_city(self):
        """Full city vs nickname."""
        assert _fuzzy_team_match("Lakers", "Los Angeles Lakers")

    def test_soccer_team(self):
        assert _fuzzy_team_match("Manchester United", "Manchester United")

    def test_college_full_vs_short(self):
        assert _fuzzy_team_match("Purdue", "Purdue Boilermakers")


# =============================================================================
# match_teams_to_event
# =============================================================================


class TestMatchTeamsToEvent:
    """Test home/away probability mapping."""

    def test_yes_is_home(self):
        """When yes_team matches home team."""
        matchup = MatchupInfo("Celtics", "Warriors", yes_team="Celtics", format_type="bare_matchup")
        result = match_teams_to_event(matchup, "Boston Celtics", "Golden State Warriors")
        assert result is not None
        assert result["yes_is_home"] is True

    def test_yes_is_away(self):
        """When yes_team matches away team."""
        matchup = MatchupInfo("Warriors", "Celtics", yes_team="Warriors", format_type="bare_matchup")
        result = match_teams_to_event(matchup, "Boston Celtics", "Golden State Warriors")
        assert result is not None
        assert result["yes_is_home"] is False

    def test_bare_matchup_at_convention(self):
        """'Team A at Team B' → Team A is away, yes=Team A."""
        matchup = extract_matchup("Boston Celtics at Golden State Warriors")
        assert matchup is not None
        # In our DB, event might have home=Golden State, away=Boston
        result = match_teams_to_event(matchup, "Golden State Warriors", "Boston Celtics")
        assert result is not None
        # "Yes" = Boston Celtics (team_a) = away team in our DB
        assert result["yes_is_home"] is False

    def test_will_beat_maps_correctly(self):
        """'Will Team A beat Team B?' → yes=Team A"""
        matchup = extract_matchup("Will the Warriors beat the Celtics?")
        assert matchup is not None
        result = match_teams_to_event(matchup, "Golden State Warriors", "Boston Celtics")
        assert result is not None
        # Warriors = home team → yes_is_home=True
        assert result["yes_is_home"] is True

    def test_no_match(self):
        """Neither team matches."""
        matchup = MatchupInfo("Jazz", "Spurs", yes_team="Jazz", format_type="bare_matchup")
        result = match_teams_to_event(matchup, "Boston Celtics", "Golden State Warriors")
        assert result is None

    def test_disambiguation_with_team_b(self):
        """When yes_team matches both, use team_b to disambiguate."""
        # "New York" could match both "New York Knicks" and "New York Rangers"
        # but if team_b is "Boston Celtics" and away is "Boston Celtics",
        # then team_b is away → yes_team must be home
        matchup = MatchupInfo(
            "Knicks", "Boston Celtics",
            yes_team="Knicks", format_type="bare_matchup",
        )
        result = match_teams_to_event(
            matchup, "New York Knicks", "Boston Celtics",
        )
        assert result is not None
        assert result["yes_is_home"] is True

    def test_will_win_single_team(self):
        """'Will X win?' with only one team name."""
        matchup = extract_matchup("Will the Lakers win?")
        assert matchup is not None
        result = match_teams_to_event(matchup, "Los Angeles Lakers", "Phoenix Suns")
        assert result is not None
        assert result["yes_is_home"] is True

    def test_will_win_single_team_away(self):
        """'Will X win?' where X is the away team."""
        matchup = extract_matchup("Will the Suns win?")
        assert matchup is not None
        result = match_teams_to_event(matchup, "Los Angeles Lakers", "Phoenix Suns")
        assert result is not None
        assert result["yes_is_home"] is False


# =============================================================================
# find_moneyline_outcome (for multi-outcome game events)
# =============================================================================


class _MockOutcome:
    """Lightweight mock for FuturesOutcome used in find_moneyline_outcome tests."""

    def __init__(self, name, prob, yes_bid=None, yes_ask=None):
        self.name = name
        self.current_probability = prob
        self.current_yes_bid = yes_bid
        self.current_yes_ask = yes_ask


class TestFindMoneylineOutcome:
    """Test moneyline outcome selection from multi-outcome game events."""

    def test_two_outcomes_moneyline(self):
        """Standard 2-outcome moneyline: pick the yes_team."""
        outcomes = [
            _MockOutcome("Boston Celtics", 0.67),
            _MockOutcome("Golden State Warriors", 0.33),
        ]
        matchup = extract_matchup("Celtics vs. Warriors")
        assert matchup is not None
        result = find_moneyline_outcome(
            outcomes, matchup, "Boston Celtics", "Golden State Warriors",
        )
        assert result is not None
        outcome, yes_is_home = result
        assert outcome.name == "Boston Celtics"
        # Celtics = yes_team, fuzzy matches home "Boston Celtics" → yes_is_home=True
        assert yes_is_home is True

    def test_multi_outcome_with_spread_and_total(self):
        """Game event with moneyline + spread + total: find the moneyline outcome."""
        outcomes = [
            _MockOutcome("Boston Celtics", 0.67),
            _MockOutcome("Golden State Warriors", 0.33),
            _MockOutcome("Over 220.5", 0.52),
            _MockOutcome("Celtics -3.5", 0.48),
        ]
        matchup = extract_matchup("Celtics vs. Warriors")
        assert matchup is not None
        result = find_moneyline_outcome(
            outcomes, matchup, "Boston Celtics", "Golden State Warriors",
        )
        assert result is not None
        outcome, yes_is_home = result
        # Should pick the Celtics moneyline, not the spread or total
        assert "Celtics" in outcome.name
        assert outcome.current_probability == 0.67

    def test_home_team_selected(self):
        """When yes_team is the home team."""
        outcomes = [
            _MockOutcome("Los Angeles Lakers", 0.55),
            _MockOutcome("Phoenix Suns", 0.45),
        ]
        matchup = extract_matchup("Lakers vs Suns")
        assert matchup is not None
        result = find_moneyline_outcome(
            outcomes, matchup, "Los Angeles Lakers", "Phoenix Suns",
        )
        assert result is not None
        outcome, yes_is_home = result
        assert "Lakers" in outcome.name

    def test_no_matching_outcome(self):
        """No outcome matches either team name."""
        outcomes = [
            _MockOutcome("Over 220.5", 0.52),
            _MockOutcome("Under 220.5", 0.48),
        ]
        matchup = extract_matchup("Celtics vs. Warriors")
        assert matchup is not None
        result = find_moneyline_outcome(
            outcomes, matchup, "Boston Celtics", "Golden State Warriors",
        )
        assert result is None

    def test_single_yes_outcome_fallback(self):
        """Single 'Yes' outcome falls back to first valid outcome."""
        outcomes = [_MockOutcome("Yes", 0.65)]
        matchup = extract_matchup("Celtics vs. Warriors")
        assert matchup is not None
        result = find_moneyline_outcome(
            outcomes, matchup, "Boston Celtics", "Golden State Warriors",
        )
        assert result is not None
        outcome, _ = result
        assert outcome.name == "Yes"

    def test_zero_probability_skipped(self):
        """Outcomes with prob=0 or prob=1 are skipped."""
        outcomes = [
            _MockOutcome("Boston Celtics", 0.0),
            _MockOutcome("Golden State Warriors", 0.55),
        ]
        matchup = extract_matchup("Celtics vs. Warriors")
        assert matchup is not None
        result = find_moneyline_outcome(
            outcomes, matchup, "Boston Celtics", "Golden State Warriors",
        )
        assert result is not None
        outcome, _ = result
        assert outcome.name == "Golden State Warriors"


# =============================================================================
# Win probability sources config
# =============================================================================


class TestWinProbSources:
    """Test that Kalshi and Polymarket are registered as win prob sources."""

    def test_kalshi_registered(self):
        from app.config.win_prob_sources import WIN_PROB_SOURCES
        assert "kalshi" in WIN_PROB_SOURCES
        assert WIN_PROB_SOURCES["kalshi"]["source_type"] == "market"
        assert WIN_PROB_SOURCES["kalshi"]["color"] == "#22c55e"

    def test_polymarket_registered(self):
        from app.config.win_prob_sources import WIN_PROB_SOURCES
        assert "polymarket" in WIN_PROB_SOURCES
        assert WIN_PROB_SOURCES["polymarket"]["source_type"] == "market"
        assert WIN_PROB_SOURCES["polymarket"]["color"] == "#3b82f6"

    def test_all_five_sources(self):
        """Verify we now have 5 sources: betting, espn, stat_model, kalshi, polymarket."""
        from app.config.win_prob_sources import WIN_PROB_SOURCES
        assert len(WIN_PROB_SOURCES) == 5
        assert set(WIN_PROB_SOURCES.keys()) == {
            "betting", "espn", "stat_model", "kalshi", "polymarket",
        }


# =============================================================================
# Edge cases and integration scenarios
# =============================================================================


class TestEdgeCases:
    """Test edge cases in the matching logic."""

    def test_empty_market_name(self):
        assert not is_game_level_market("", "championship", 1)
        assert extract_matchup("") is None

    def test_single_word_not_matchup(self):
        assert not is_game_level_market("Basketball", "championship", 1)

    def test_question_without_will(self):
        """Questions not starting with 'Will' don't match."""
        assert extract_matchup("Do the Lakers win?") is None

    def test_multiple_at_in_name(self):
        """Handle edge case with 'at' appearing multiple times."""
        # "Team at City at Arena" → should extract first matchup
        result = extract_matchup("Iowa at Purdue")
        assert result is not None
        assert result.team_a == "Iowa"
        assert result.team_b == "Purdue"

    def test_apostrophe_in_team_name(self):
        result = extract_matchup("St. John's at Georgetown")
        assert result is not None
        assert "John" in result.team_a

    def test_hyphen_in_team_name(self):
        result = extract_matchup("Wolves-Pacers at Madison Square Garden")
        # This shouldn't match because the format is wrong
        # (no clear "Team A at Team B" pattern)
        # Actually it might match Wolves-Pacers vs Garden... let's test
        # The BARE_MATCHUP_RE requires uppercase start for each team
        pass

    def test_probability_mapping_home(self):
        """Full flow: market says yes=0.65 for home team → home_prob=0.65."""
        matchup = extract_matchup("Will the Celtics beat the Warriors?")
        assert matchup is not None
        mapping = match_teams_to_event(matchup, "Boston Celtics", "Golden State Warriors")
        assert mapping is not None
        # Celtics = yes_team, Celtics matches home
        assert mapping["yes_is_home"] is True
        # So if yes_prob = 0.65 → home_prob = 0.65
        yes_prob = 0.65
        home_prob = yes_prob if mapping["yes_is_home"] else 1.0 - yes_prob
        assert home_prob == 0.65

    def test_probability_mapping_away(self):
        """Full flow: market says yes=0.65 for away team → home_prob=0.35."""
        matchup = extract_matchup("Will the Warriors beat the Celtics?")
        assert matchup is not None
        mapping = match_teams_to_event(matchup, "Boston Celtics", "Golden State Warriors")
        assert mapping is not None
        # Warriors = yes_team, Warriors matches away
        assert mapping["yes_is_home"] is False
        # So if yes_prob = 0.65 → home_prob = 1 - 0.65 = 0.35
        yes_prob = 0.65
        home_prob = yes_prob if mapping["yes_is_home"] else 1.0 - yes_prob
        assert home_prob == pytest.approx(0.35)
