"""Tests for Odds API service parsing methods.

Covers:
- _parse_events: market flattening across bookmakers (h2h, spreads, totals)
- _parse_futures: outrights parsing with american_to_probability conversion
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest

from app.services.odds_api import OddsAPIService


class StubAsyncClient:
    def __init__(self, response: httpx.Response):
        self.response = response
        self.calls: list[dict] = []

    async def get(self, url: str, params: dict):
        self.calls.append({"url": url, "params": params})
        return self.response


def odds_api_response(
    payload: list | dict,
    *,
    headers: dict | None = None,
    status_code: int = 200,
) -> httpx.Response:
    return httpx.Response(
        status_code,
        json=payload,
        headers=headers or {},
        request=httpx.Request("GET", "https://api.the-odds-api.com/v4/test"),
    )


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

    def test_incomplete_market_outcomes_leave_only_missing_fields_none(self, client):
        event = {
            "id": "partial123",
            "commence_time": "2026-04-10T23:30:00Z",
            "home_team": "Boston Celtics",
            "away_team": "Los Angeles Lakers",
            "bookmakers": [
                {
                    "key": "fanduel",
                    "markets": [
                        {
                            "key": "h2h",
                            "outcomes": [
                                {"name": "Boston Celtics", "price": -180},
                            ],
                        },
                        {
                            "key": "spreads",
                            "outcomes": [
                                {
                                    "name": "Los Angeles Lakers",
                                    "price": -110,
                                    "point": 4.5,
                                },
                            ],
                        },
                        {
                            "key": "totals",
                            "outcomes": [
                                {"name": "Under", "price": -105, "point": 215.5},
                            ],
                        },
                        {
                            "key": "player_points",
                            "outcomes": [
                                {"name": "Jayson Tatum", "price": -110, "point": 28.5},
                            ],
                        },
                    ],
                }
            ],
        }

        snapshots = client._parse_events([event], "basketball_nba")

        assert len(snapshots) == 1
        snapshot = snapshots[0]
        assert snapshot.home_moneyline == -180
        assert snapshot.away_moneyline is None
        assert snapshot.home_spread is None
        assert snapshot.home_spread_odds is None
        assert snapshot.away_spread_odds == -110
        assert snapshot.over_under is None
        assert snapshot.over_odds is None
        assert snapshot.under_odds == -105


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

    def test_outcomes_without_prices_do_not_create_empty_markets(self, client):
        api_response = [
            {
                "sport_title": "NBA Championship Winner",
                "bookmakers": [
                    {
                        "key": "fanduel",
                        "markets": [
                            {
                                "key": "outrights",
                                "outcomes": [
                                    {"name": "Boston Celtics", "price": 350},
                                    {"name": "Denver Nuggets"},
                                ],
                            }
                        ],
                    },
                    {
                        "key": "draftkings",
                        "markets": [
                            {
                                "key": "outrights",
                                "outcomes": [
                                    {"name": "Los Angeles Lakers", "price": None},
                                ],
                            }
                        ],
                    },
                ],
            }
        ]

        markets = client._parse_futures(api_response, "basketball_nba_championship")

        assert len(markets) == 1
        assert markets[0].bookmaker == "fanduel"
        assert [outcome.name for outcome in markets[0].outcomes] == ["Boston Celtics"]


# ── Request behavior and graceful fallback ─────────────────────────────


class TestRequestBehavior:
    """Guard quota-sensitive request params, quota capture, and fallback paths."""

    @pytest.mark.asyncio
    async def test_get_odds_uses_full_default_params_and_captures_quota(self, client):
        response = odds_api_response(
            [{"id": "event123"}],
            headers={
                "x-requests-remaining": "49999",
                "x-requests-used": "101",
            },
        )
        stub = StubAsyncClient(response)
        await client.close()
        client.client = stub

        data = await client.get_odds("basketball_nba")

        assert data == [{"id": "event123"}]
        assert stub.calls == [
            {
                "url": f"{client.BASE_URL}/sports/basketball_nba/odds",
                "params": {
                    "apiKey": "test_dummy_key",
                    "regions": "us,us2",
                    "markets": "h2h,spreads,totals",
                    "oddsFormat": "american",
                },
            }
        ]
        assert client.last_requests_remaining == 49999
        assert client.last_requests_used == 101

    @pytest.mark.asyncio
    async def test_get_futures_odds_requests_only_outrights(self, client):
        response = odds_api_response([])
        stub = StubAsyncClient(response)
        await client.close()
        client.client = stub

        data = await client.get_futures_odds("basketball_nba_championship")

        assert data == []
        assert stub.calls[0]["params"] == {
            "apiKey": "test_dummy_key",
            "regions": "us,us2",
            "markets": "outrights",
            "oddsFormat": "american",
        }

    @pytest.mark.asyncio
    async def test_get_sports_with_outrights_filters_missing_and_false_flags(self, client):
        async def fake_get_sports():
            return [
                {"key": "basketball_nba", "has_outrights": True},
                {"key": "soccer_epl", "has_outrights": False},
                {"key": "icehockey_nhl"},
            ]

        client.get_sports = fake_get_sports

        sports = await client.get_sports_with_outrights()

        assert sports == [{"key": "basketball_nba", "has_outrights": True}]

    @pytest.mark.asyncio
    async def test_get_all_odds_continues_after_single_sport_http_error(
        self,
        client,
        fixtures,
    ):
        calls = []

        async def fake_get_odds(sport_key: str):
            calls.append(sport_key)
            if sport_key == "bad_sport":
                request = httpx.Request("GET", "https://api.the-odds-api.com/v4/bad")
                response = httpx.Response(500, request=request)
                raise httpx.HTTPStatusError(
                    "upstream error",
                    request=request,
                    response=response,
                )
            return fixtures["event_h2h_only"]

        client.get_odds = fake_get_odds

        snapshots = await client.get_all_odds(["bad_sport", "icehockey_nhl"])

        assert calls == ["bad_sport", "icehockey_nhl"]
        assert len(snapshots) == 1
        assert snapshots[0].sport_key == "icehockey_nhl"
