"""Contract tests for search-related endpoints on /api/events.

Tests that search, typeahead, and trending endpoints return the expected
response shape with correct top-level keys, nested structure, and field types.
Uses the shared ``client`` fixture from conftest.py (mock empty DB session).
"""

import pytest


# ============================================================================
# Search — GET /api/events/search?q=...
# ============================================================================


class TestSearchEndpoint:
    """GET /api/events/search — full event + futures search."""

    async def test_returns_200(self, client):
        resp = await client.get("/api/events/search?q=test")
        assert resp.status_code == 200

    async def test_response_has_query_field(self, client):
        resp = await client.get("/api/events/search?q=test")
        body = resp.json()
        assert "query" in body
        assert body["query"] == "test"

    async def test_response_has_results_list(self, client):
        resp = await client.get("/api/events/search?q=test")
        body = resp.json()
        assert "results" in body
        assert isinstance(body["results"], list)

    async def test_response_has_futures_list(self, client):
        resp = await client.get("/api/events/search?q=test")
        body = resp.json()
        assert "futures" in body
        assert isinstance(body["futures"], list)

    async def test_response_has_teams_list(self, client):
        resp = await client.get("/api/events/search?q=test")
        body = resp.json()
        assert "teams" in body
        assert isinstance(body["teams"], list)

    async def test_response_has_pagination(self, client):
        resp = await client.get("/api/events/search?q=test")
        body = resp.json()
        assert "pagination" in body
        pagination = body["pagination"]
        assert "page" in pagination
        assert "per_page" in pagination
        assert "total_results" in pagination
        assert "total_pages" in pagination
        assert "has_next" in pagination
        assert "has_prev" in pagination

    async def test_response_has_sports_list(self, client):
        resp = await client.get("/api/events/search?q=test")
        body = resp.json()
        assert "sports" in body
        assert isinstance(body["sports"], list)

    async def test_response_has_filters(self, client):
        resp = await client.get("/api/events/search?q=test")
        body = resp.json()
        assert "filters" in body
        filters = body["filters"]
        assert "sport" in filters
        assert "days_back" in filters
        assert "include_upcoming" in filters

    async def test_missing_q_returns_422(self, client):
        """The q parameter is required (min_length=2)."""
        resp = await client.get("/api/events/search")
        assert resp.status_code == 422

    async def test_short_q_returns_422(self, client):
        """q must be at least 2 characters."""
        resp = await client.get("/api/events/search?q=a")
        assert resp.status_code == 422

    async def test_pagination_defaults(self, client):
        resp = await client.get("/api/events/search?q=test")
        body = resp.json()
        assert body["pagination"]["page"] == 1
        assert body["pagination"]["per_page"] == 25

    async def test_empty_results_on_no_match(self, client):
        """Mock DB returns empty results, so all lists should be empty."""
        resp = await client.get("/api/events/search?q=xyznonexistent")
        body = resp.json()
        assert body["results"] == []
        assert body["futures"] == []

    async def test_sport_filter_accepted(self, client):
        resp = await client.get("/api/events/search?q=test&sport=basketball_nba")
        assert resp.status_code == 200
        body = resp.json()
        assert body["filters"]["sport"] == "basketball_nba"


# ============================================================================
# Typeahead — GET /api/events/typeahead?q=...
# ============================================================================


class TestTypeaheadEndpoint:
    """GET /api/events/typeahead — lightweight typeahead search."""

    async def test_returns_200(self, client):
        resp = await client.get("/api/events/typeahead?q=test")
        assert resp.status_code == 200

    async def test_response_has_suggestions(self, client):
        resp = await client.get("/api/events/typeahead?q=test")
        body = resp.json()
        assert "suggestions" in body
        assert isinstance(body["suggestions"], list)

    async def test_response_has_query(self, client):
        resp = await client.get("/api/events/typeahead?q=test")
        body = resp.json()
        assert "query" in body
        assert body["query"] == "test"

    async def test_missing_q_returns_422(self, client):
        resp = await client.get("/api/events/typeahead")
        assert resp.status_code == 422

    async def test_short_q_returns_422(self, client):
        """q must be at least 2 characters."""
        resp = await client.get("/api/events/typeahead?q=a")
        assert resp.status_code == 422

    async def test_long_q_returns_422(self, client):
        """q must be at most 50 characters."""
        long_query = "a" * 51
        resp = await client.get(f"/api/events/typeahead?q={long_query}")
        assert resp.status_code == 422

    async def test_empty_suggestions_on_no_match(self, client):
        """Mock DB returns no data, suggestions should be empty."""
        resp = await client.get("/api/events/typeahead?q=xyznonexistent")
        body = resp.json()
        assert body["suggestions"] == []

    async def test_suggestion_item_shape_if_present(self, client):
        """If suggestions exist, each should have type and text."""
        resp = await client.get("/api/events/typeahead?q=test")
        body = resp.json()
        for item in body["suggestions"]:
            assert "type" in item
            assert "text" in item
            assert isinstance(item["type"], str)
            assert isinstance(item["text"], str)
            assert item["type"] in {"team", "event", "futures"}


# ============================================================================
# Trending — GET /api/events/search/trending
# ============================================================================


class TestTrendingEndpoint:
    """GET /api/events/search/trending — trending search queries."""

    async def test_returns_200(self, client):
        """Endpoint should return 200 even without Redis (graceful fallback)."""
        resp = await client.get("/api/events/search/trending")
        assert resp.status_code == 200

    async def test_response_has_trending_list(self, client):
        resp = await client.get("/api/events/search/trending")
        body = resp.json()
        assert "trending" in body
        assert isinstance(body["trending"], list)

    async def test_no_auth_required(self, client):
        """Trending searches are public — no secret needed."""
        resp = await client.get("/api/events/search/trending")
        assert resp.status_code == 200
        body = resp.json()
        assert "error" not in body
