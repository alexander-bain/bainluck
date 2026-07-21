"""Precision tests for the unlinked-held matchup matcher (Queue #223 Item 4).

_matchup_matches_event requires BOTH market teams to correspond to the event's two
teams (either orientation) — stricter than match_teams_to_event's one-side fire — so
a filed miss is a real matcher failure, not a coincidental one-name overlap."""

from types import SimpleNamespace

from app.routes.admin_matching import (
    _is_non_game_winner_derivative,
    _matchup_matches_event,
)


def _mu(a, b):
    return SimpleNamespace(team_a=a, team_b=b, yes_team=a)


class TestMatcher:
    def test_both_teams_match_either_orientation(self):
        mu = _mu("Red Sox", "Rays")
        assert _matchup_matches_event(mu, "Boston Red Sox", "Tampa Bay Rays", None)
        # reversed orientation
        assert _matchup_matches_event(mu, "Tampa Bay Rays", "Boston Red Sox", None)

    def test_only_one_team_matches_is_rejected(self):
        mu = _mu("Red Sox", "Yankees")
        # Yankees is not in this event — only Red Sox overlaps → reject (high precision)
        assert not _matchup_matches_event(mu, "Boston Red Sox", "Tampa Bay Rays", None)

    def test_no_team_matches_is_rejected(self):
        mu = _mu("Dodgers", "Padres")
        assert not _matchup_matches_event(mu, "Boston Red Sox", "Tampa Bay Rays", None)

    def test_ticker_fallback_when_names_generic(self):
        # Generic market name (no teams), but the Kalshi ticker encodes them.
        mu = _mu("Yes", "No")
        ext = "KXNBAGAME-26APR24BOSPHI"  # BOS away, PHI home (Kalshi convention)
        assert _matchup_matches_event(mu, "Philadelphia 76ers", "Boston Celtics", ext)

    def test_empty_matchup_is_rejected(self):
        mu = _mu(None, None)
        assert not _matchup_matches_event(mu, "Boston Red Sox", "Tampa Bay Rays", None)


class TestDerivativeExclusion:
    """#224: the check is defined as game-WINNER (moneyline) misses. Derivative /
    prop sub-markets carry both team names but are not the moneyline — they must be
    excluded so the metric stays honest and the Flow Sentinel doesn't cry wolf.
    The production regression this guards: 9/10 flagged 'misses' were Player Props
    or First-5-Innings-Winner derivatives, not game-winner gaps."""

    def test_pure_moneylines_are_not_excluded(self):
        for name in [
            "Botafogo vs Santos",                              # the genuine kalshi soccer miss
            "New York Mets vs. Milwaukee Brewers",
            "Los Angeles Dodgers vs. San Diego Padres",
            "Real Madrid vs Barcelona",
            "Kansas City Chiefs vs. Buffalo Bills",
        ]:
            assert not _is_non_game_winner_derivative(name), name

    def test_player_props_excluded(self):
        for name in [
            "New York Mets vs. Milwaukee Brewers - Player Props",
            "Miami Marlins vs. Houston Astros - Player Props",
        ]:
            assert _is_non_game_winner_derivative(name), name

    def test_first_n_innings_winner_excluded(self):
        for name in [
            "Washington Nationals vs. Colorado Rockies - First 5 Innings Winner",
            "Cincinnati Reds vs. Seattle Mariners - First 5 Innings Winner",
        ]:
            assert _is_non_game_winner_derivative(name), name

    def test_other_derivative_families_excluded(self):
        for name in [
            "Team A vs. Team B - Total Runs",
            "Team A vs. Team B - Run Line",
            "Team A vs. Team B - First Half",
            "Team A vs. Team B - Correct Score",
            "Team A vs. Team B - Winning Margin",
        ]:
            assert _is_non_game_winner_derivative(name), name
