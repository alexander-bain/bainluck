"""Contract tests for GET /api/playoffs/{league_slug}.

Tests response shape, column structure, and validation for all configured leagues.
"""

import pytest

from app.config.league_configs import get_all_league_slugs


# All configured league slugs — tests run against each
ALL_SLUGS = get_all_league_slugs()
TEAM_SPORT_SLUGS = [s for s in ALL_SLUGS if s != "golf"]


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
    """Response shape for a valid league slug (mocked empty DB)."""

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

    async def test_sources_available_present(self, client):
        resp = await client.get("/api/playoffs/nba")
        body = resp.json()
        assert "sources_available" in body
        assert isinstance(body["sources_available"], list)


class TestPlayoffGridAllLeagues:
    """Every configured league slug returns 200 with valid shape."""

    @pytest.mark.parametrize("slug", ALL_SLUGS)
    async def test_all_leagues_return_200(self, client, slug):
        resp = await client.get(f"/api/playoffs/{slug}")
        assert resp.status_code == 200, f"League {slug} returned {resp.status_code}"

    @pytest.mark.parametrize("slug", TEAM_SPORT_SLUGS)
    async def test_all_team_sports_have_required_keys(self, client, slug):
        resp = await client.get(f"/api/playoffs/{slug}")
        body = resp.json()
        for key in ["league", "columns", "teams", "team_count"]:
            assert key in body, f"League {slug} missing key: {key}"

    @pytest.mark.parametrize("slug", TEAM_SPORT_SLUGS)
    async def test_league_field_matches_slug(self, client, slug):
        resp = await client.get(f"/api/playoffs/{slug}")
        body = resp.json()
        assert body["league"] == slug


class TestPlayoffGridColumns:
    """Column structure validation.

    With mocked empty DB, columns may be empty (populated from market data).
    These tests validate structure when columns are present.
    """

    async def test_columns_is_list(self, client):
        resp = await client.get("/api/playoffs/nba")
        body = resp.json()
        assert isinstance(body["columns"], list)

    async def test_column_objects_have_key_and_label_when_present(self, client):
        resp = await client.get("/api/playoffs/nba")
        body = resp.json()
        for col in body["columns"]:
            assert "key" in col, f"Column missing 'key': {col}"
            assert "label" in col, f"Column missing 'label': {col}"
            assert isinstance(col["key"], str)
            assert isinstance(col["label"], str)


class TestPlayoffGridQueryParams:

    async def test_debug_flag_accepted(self, client):
        resp = await client.get("/api/playoffs/nba?debug=true")
        assert resp.status_code == 200

    async def test_top_param_accepted(self, client):
        resp = await client.get("/api/playoffs/nba?top=5")
        assert resp.status_code == 200

    async def test_hours_param_accepted(self, client):
        resp = await client.get("/api/playoffs/nba?hours=48")
        assert resp.status_code == 200


class TestPlayoffLeagueList:
    """GET /api/playoffs/ — list available leagues."""

    async def test_returns_200(self, client):
        resp = await client.get("/api/playoffs/")
        assert resp.status_code == 200

    async def test_response_has_leagues(self, client):
        resp = await client.get("/api/playoffs/")
        body = resp.json()
        assert "leagues" in body
        assert isinstance(body["leagues"], list)
        assert len(body["leagues"]) > 0

    async def test_each_league_has_slug_and_name(self, client):
        resp = await client.get("/api/playoffs/")
        body = resp.json()
        for league in body["leagues"]:
            assert "slug" in league, f"League missing slug: {league}"
            assert "name" in league, f"League missing name: {league}"
