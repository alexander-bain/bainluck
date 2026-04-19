"""Contract tests for GET /api/playoffs/{league_slug}.

Tests response shape, not exact data values.
"""

import pytest


class TestPlayoffGrid404:

    async def test_invalid_slug_returns_404(self, client):
        resp = await client.get("/api/playoffs/fake-league-xyz")
        assert resp.status_code == 404

    async def test_404_body_has_detail(self, client):
        resp = await client.get("/api/playoffs/fake-league-xyz")
        body = resp.json()
        assert "detail" in body
        assert "fake-league-xyz" in body["detail"]

    async def test_404_lists_available_leagues(self, client):
        resp = await client.get("/api/playoffs/nonexistent")
        body = resp.json()
        assert "Available" in body["detail"]


class TestPlayoffGridShape:

    async def test_valid_slug_returns_200(self, client):
        resp = await client.get("/api/playoffs/nba")
        assert resp.status_code == 200

    async def test_response_has_required_keys(self, client):
        resp = await client.get("/api/playoffs/nba")
        body = resp.json()
        for key in ["league", "name", "season", "columns", "teams", "team_count", "last_updated"]:
            assert key in body, f"Missing key: {key}"

    async def test_league_matches_slug(self, client):
        resp = await client.get("/api/playoffs/nba")
        body = resp.json()
        assert body["league"] == "nba"

    async def test_columns_are_list(self, client):
        resp = await client.get("/api/playoffs/nba")
        body = resp.json()
        assert isinstance(body["columns"], list)

    async def test_teams_are_list(self, client):
        resp = await client.get("/api/playoffs/nba")
        body = resp.json()
        assert isinstance(body["teams"], list)

    async def test_team_count_is_int(self, client):
        resp = await client.get("/api/playoffs/nba")
        body = resp.json()
        assert isinstance(body["team_count"], int)

    async def test_movers_present(self, client):
        resp = await client.get("/api/playoffs/nba")
        body = resp.json()
        assert "movers" in body
        assert isinstance(body["movers"], list)

    async def test_trend_chart_present(self, client):
        resp = await client.get("/api/playoffs/nba")
        body = resp.json()
        assert "trend_chart" in body
