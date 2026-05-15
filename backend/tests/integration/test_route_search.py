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


# ============================================================================
# Search Suggestions — GET /api/events/search-suggestions
# ============================================================================


class TestSearchSuggestionsEndpoint:
    """GET /api/events/search-suggestions — smart zero-state suggestions."""

    async def test_returns_200(self, client):
        resp = await client.get("/api/events/search-suggestions")
        assert resp.status_code == 200

    async def test_response_has_suggestions_key(self, client):
        """Response has a 'suggestions' key containing a list."""
        resp = await client.get("/api/events/search-suggestions")
        body = resp.json()
        assert "suggestions" in body
        assert isinstance(body["suggestions"], list)

    async def test_at_most_8_suggestions(self, client):
        resp = await client.get("/api/events/search-suggestions")
        body = resp.json()
        assert len(body["suggestions"]) <= 8

    async def test_suggestion_item_shape_if_present(self, client):
        resp = await client.get("/api/events/search-suggestions")
        body = resp.json()
        for item in body["suggestions"]:
            assert "query" in item, "Suggestion missing 'query'"
            assert "label" in item, "Suggestion missing 'label'"
            assert "type" in item, "Suggestion missing 'type'"
            assert isinstance(item["query"], str)
            assert isinstance(item["label"], str)
            assert isinstance(item["type"], str)

    async def test_suggestion_types_are_valid(self, client):
        resp = await client.get("/api/events/search-suggestions")
        body = resp.json()
        valid_types = {"event", "futures", "team", "trending"}
        for item in body["suggestions"]:
            assert item["type"] in valid_types, (
                f"Unknown suggestion type: {item['type']}"
            )


# ============================================================================
# Search — Individual Sport Filtering
# ============================================================================


class TestSearchIndividualSportFiltering:
    """Verify individual-sport teams (tennis, golf) are filtered from search team results.

    With an empty mock DB there are no teams returned, but we can verify the
    endpoint runs without error when querying sport terms that would match
    individual-sport athletes on a real database.
    """

    async def test_golf_query_returns_200(self, client):
        resp = await client.get("/api/events/search?q=golf")
        assert resp.status_code == 200

    async def test_tennis_query_returns_200(self, client):
        resp = await client.get("/api/events/search?q=tennis")
        assert resp.status_code == 200

    async def test_golf_teams_not_in_results(self, client):
        """In empty DB, teams should be empty. This documents the contract:
        individual-sport players should never appear in the teams array."""
        resp = await client.get("/api/events/search?q=djokovic")
        body = resp.json()
        assert isinstance(body["teams"], list)
        # No individual-sport teams should appear
        for team in body["teams"]:
            sport_key = team.get("sport_key", "")
            assert "tennis" not in (sport_key or ""), (
                f"Individual sport team leaked: {team['name']} ({sport_key})"
            )
            assert "golf" not in (sport_key or ""), (
                f"Individual sport team leaked: {team['name']} ({sport_key})"
            )

    async def test_typeahead_golf_query_returns_200(self, client):
        resp = await client.get("/api/events/typeahead?q=golf")
        assert resp.status_code == 200

    async def test_typeahead_tennis_query_returns_200(self, client):
        resp = await client.get("/api/events/typeahead?q=tennis")
        assert resp.status_code == 200

    async def test_typeahead_no_individual_sport_teams(self, client):
        """Typeahead suggestions should never include individual-sport teams."""
        resp = await client.get("/api/events/typeahead?q=nadal")
        body = resp.json()
        for suggestion in body["suggestions"]:
            if suggestion["type"] == "team":
                sport_key = suggestion.get("sport_key", "")
                assert "tennis" not in (sport_key or ""), (
                    f"Individual sport in typeahead: {suggestion['text']}"
                )


# ============================================================================
# Multi-Word Search
# ============================================================================


class TestSearchMultiWord:
    """Multi-word search queries like 'USA Canada' should be accepted."""

    async def test_multi_word_search_returns_200(self, client):
        resp = await client.get("/api/events/search?q=USA Canada")
        assert resp.status_code == 200

    async def test_multi_word_typeahead_returns_200(self, client):
        resp = await client.get("/api/events/typeahead?q=USA Canada")
        assert resp.status_code == 200

    async def test_multi_word_search_has_standard_shape(self, client):
        resp = await client.get("/api/events/search?q=Lakers Celtics")
        body = resp.json()
        assert "results" in body
        assert "futures" in body
        assert "teams" in body
        assert "pagination" in body
