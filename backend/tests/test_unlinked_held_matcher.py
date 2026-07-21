"""Precision tests for the unlinked-held matchup matcher (Queue #223 Item 4).

_matchup_matches_event requires BOTH market teams to correspond to the event's two
teams (either orientation) — stricter than match_teams_to_event's one-side fire — so
a filed miss is a real matcher failure, not a coincidental one-name overlap."""

from types import SimpleNamespace

from app.routes.admin_matching import _matchup_matches_event


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
