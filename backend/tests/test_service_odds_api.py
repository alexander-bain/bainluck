"""Tests for Odds API service parsing methods.

Covers:
- _parse_events: market flattening across bookmakers (h2h, spreads, totals)
- _parse_futures: outrights parsing with american_to_probability conversion
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.services.odds_api import OddsAPIService


@pytest.fixture
def client():
    return OddsAPIService(api_key="test_dummy_key")


@pytest.fixture
def fixtures():
    path = Path(__file__).parent / "fixtures" / "odds_api_fixtures.json"
    with open(path) as f:
        return json.load(f)


# ── _parse_events ─────────────────────────────────────────────────────


class TestParseEvents:
    """Test event parsing with market flattening across bookmakers."""

    def test_multiple_bookmakers_produce_multiple_snapshots(self, client, fixtures):
        snapshots = client._parse_events(fixtures["events_all_markets"], "basketball_nba")
        assert len(snapshots) == 2
        bookmakers = {s.bookmaker for s in snapshots}
        assert bookmakers == {"fanduel", "draftkings"}

    def test_all_market_types_parsed(self, client, fixtures):
        snapshots = client._parse_events(fixtures["events_all_markets"], "basketball_nba")
        fanduel = next(s for s in snapshots if s.bookmaker == "fanduel")

        assert fanduel.home_moneyline == -180
        assert fanduel.away_moneyline == 150

        assert fanduel.home_spread == -4.5
        assert fanduel.home_spread_odds == -110
        assert fanduel.away_spread_odds == -110

        assert fanduel.over_under == 215.5
        assert fanduel.over_odds == -110
        assert fanduel.under_odds == -110

    def test_draftkings_values(self, client, fixtures):
        snapshots = client._parse_events(fixtures["events_all_markets"], "basketball_nba")
        dk = next(s for s in snapshots if s.bookmaker == "draftkings")

        assert dk.home_moneyline == -175
        assert dk.away_moneyline == 145
        assert dk.home_spread == -4.0
        assert dk.over_under == 216.0

    def test_common_fields(self, client, fixtures):
        snapshots = client._parse_events(fixtures["events_all_markets"], "basketball_nba")
        for s in snapshots:
            assert s.event_id == "abc123def456"
            assert s.sport_key == "basketball_nba"
            assert s.home_team == "Boston Celtics"
            assert s.away_team == "Los Angeles Lakers"
            assert isinstance(s.commence_time, datetime)

    def test_h2h_only_leaves_spread_total_none(self, client, fixtures):
        snapshots = client._parse_events(fixtures["event_h2h_only"], "icehockey_nhl")
        assert len(snapshots) == 1
        s = snapshots[0]
        assert s.home_moneyline == -200
        assert s.away_moneyline == 170
        assert s.home_spread is None
        assert s.home_spread_odds is None
        assert s.over_under is None

    def test_no_bookmakers_returns_empty(self, client, fixtures):
        snapshots = client._parse_events(fixtures["event_no_bookmakers"], "soccer_epl")
        assert snapshots == []

    def test_timestamp_z_suffix_parsed(self, client, fixtures):
        snapshots = client._parse_events(fixtures["events_all_markets"], "basketball_nba")
        ct = snapshots[0].commence_time
        assert ct.year == 2026
        assert ct.month == 4
        assert ct.day == 10
        assert ct.hour == 23
        assert ct.minute == 30

    def test_sport_key_propagated(self, client, fixtures):
        snapshots = client._parse_events(fixtures["event_h2h_only"], "icehockey_nhl")
        assert snapshots[0].sport_key == "icehockey_nhl"


# ── _parse_futures ────────────────────────────────────────────────────


class TestParseFutures:
    """Test futures/outrights parsing with probability conversion."""

    def test_outrights_parsed(self, client, fixtures):
        markets = client._parse_futures(fixtures["futures_outrights"], "basketball_nba_championship")
        assert len(markets) == 2

    def test_bookmaker_separated(self, client, fixtures):
        markets = client._parse_futures(fixtures["futures_outrights"], "basketball_nba_championship")
        bookmakers = {m.bookmaker for m in markets}
        assert bookmakers == {"fanduel", "draftkings"}

    def test_outcomes_have_probabilities(self, client, fixtures):
        markets = client._parse_futures(fixtures["futures_outrights"], "basketball_nba_championship")
        fanduel = next(m for m in markets if m.bookmaker == "fanduel")
        assert len(fanduel.outcomes) == 3

        celtics = next(o for o in fanduel.outcomes if o.name == "Boston Celtics")
        assert celtics.american_odds == 350
        assert 0 < celtics.probability < 1

    def test_market_name_from_sport_title(self, client, fixtures):
        markets = client._parse_futures(fixtures["futures_outrights"], "basketball_nba_championship")
        for m in markets:
            assert m.market_name == "NBA Championship Winner"
            assert m.sport_key == "basketball_nba_championship"

    def test_non_outrights_skipped(self, client, fixtures):
        markets = client._parse_futures(fixtures["futures_non_outrights"], "basketball_nba_championship")
        assert markets == []

    def test_empty_response(self, client):
        markets = client._parse_futures([], "basketball_nba_championship")
        assert markets == []

    def test_probability_reasonable_range(self, client, fixtures):
        """All probabilities should be between 0 and 1."""
        markets = client._parse_futures(fixtures["futures_outrights"], "basketball_nba_championship")
        for m in markets:
            for o in m.outcomes:
                assert 0 < o.probability < 1, f"{o.name}: {o.probability}"
