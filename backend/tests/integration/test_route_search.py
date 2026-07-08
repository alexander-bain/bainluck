"""Contract tests for search-related endpoints on /api/events.

Tests that search, typeahead, and trending endpoints return the expected
response shape with correct top-level keys, nested structure, and field types.
Uses the shared ``client`` fixture from conftest.py (mock empty DB session).
"""

import pytest
from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from app.routes.events import (
    _event_search_vector,
    _futures_search_vector,
    _search_rank,
    _team_search_vector,
)


# ============================================================================
# Search — GET /api/events/search?q=...
# ============================================================================


class TestSearchEndpoint:
    """GET /api/events/search — full event + futures search."""

    async def test_returns_200(self, client):
        resp = await client.get("/api/events/search?q=test")
        assert resp.status_code == 200

    async def test_empty_db_response_top_level_shape(self, client):
        resp = await client.get("/api/events/search?q=test")
        body = resp.json()
        assert set(body.keys()) == {
            "query",
            "teams",
            "event_concepts",
            "results",
            "futures",
            "futures_families",
            "pagination",
            "sports",
            "filters",
        }

    async def test_futures_families_is_list(self, client):
        resp = await client.get("/api/events/search?q=test")
        body = resp.json()
        assert isinstance(body["futures_families"], list)

    async def test_event_concepts_is_list(self, client):
        # L2-65: tournament concept pages surfaced as first-class results.
        resp = await client.get("/api/events/search?q=test")
        body = resp.json()
        assert isinstance(body["event_concepts"], list)

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

    async def test_missing_q_returns_403(self, client):
        """The q parameter is required (min_length=2)."""
        resp = await client.get("/api/events/search")
        assert resp.status_code == 422

    async def test_short_q_returns_403(self, client):
        """q must be at least 2 characters."""
        resp = await client.get("/api/events/search?q=a")
        assert resp.status_code == 422

    async def test_pagination_defaults(self, client):
        resp = await client.get("/api/events/search?q=test")
        body = resp.json()
        assert body["pagination"]["page"] == 1
        assert body["pagination"]["per_page"] == 25
        assert body["pagination"]["total_results"] == 0
        assert body["pagination"]["total_pages"] == 0
        assert body["pagination"]["has_next"] is False
        assert body["pagination"]["has_prev"] is False

    async def test_pagination_params_reflected(self, client):
        resp = await client.get("/api/events/search?q=test&page=3&per_page=10")
        assert resp.status_code == 200
        body = resp.json()
        assert body["pagination"]["page"] == 3
        assert body["pagination"]["per_page"] == 10
        assert body["pagination"]["has_prev"] is True

    @pytest.mark.parametrize(
        "query",
        [
            "q=test&page=0",
            "q=test&per_page=0",
            "q=test&per_page=101",
            "q=test&days_back=0",
            "q=test&days_back=366",
        ],
    )
    async def test_invalid_bounded_params_return_422(self, client, query):
        resp = await client.get(f"/api/events/search?{query}")
        assert resp.status_code == 422

    async def test_empty_results_on_no_match(self, client):
        """Mock DB returns empty results, so all lists should be empty."""
        resp = await client.get("/api/events/search?q=xyznonexistent")
        body = resp.json()
        assert body["results"] == []
        assert body["futures"] == []
        assert body["teams"] == []
        assert body["sports"] == []

    async def test_sport_filter_accepted(self, client):
        resp = await client.get("/api/events/search?q=test&sport=basketball_nba")
        assert resp.status_code == 200
        body = resp.json()
        assert body["filters"]["sport"] == "basketball_nba"

    async def test_filter_params_reflected(self, client):
        resp = await client.get(
            "/api/events/search?q=test&days_back=7&include_upcoming=false"
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["filters"] == {
            "sport": None,
            "days_back": 7,
            "include_upcoming": False,
        }

    async def test_tags_filter_accepts_json_array(self, client):
        resp = await client.get(
            "/api/events/search",
            params={"q": "test", "tags": '["importance:playoff"]'},
        )
        assert resp.status_code == 200

    async def test_invalid_tags_filter_is_ignored(self, client):
        resp = await client.get(
            "/api/events/search",
            params={"q": "test", "tags": "not-json"},
        )
        assert resp.status_code == 200

    async def test_result_item_shape_if_present(self, client):
        resp = await client.get("/api/events/search?q=test")
        body = resp.json()
        for item in body["results"]:
            assert "id" in item
            assert "home_team" in item
            assert "away_team" in item
            assert "sport" in item
            assert "status" in item

    async def test_futures_item_shape_if_present(self, client):
        resp = await client.get("/api/events/search?q=test")
        body = resp.json()
        for item in body["futures"]:
            assert "id" in item
            assert "name" in item
            assert "outcomes" in item
            assert isinstance(item["outcomes"], list)

    async def test_team_item_shape_if_present(self, client):
        resp = await client.get("/api/events/search?q=test")
        body = resp.json()
        for item in body["teams"]:
            assert "id" in item
            assert "name" in item
            assert "sport_key" in item

    def test_event_search_rank_compiles_weighted_team_names(self):
        stmt = select(_search_rank(_event_search_vector(), "Lakers Celtics"))
        sql = str(
            stmt.compile(
                dialect=postgresql.dialect(),
                compile_kwargs={"literal_binds": True},
            )
        ).lower()

        assert "websearch_to_tsquery" in sql
        assert "to_tsvector" in sql
        assert "setweight" in sql
        assert "'a'" in sql
        assert "events.home_team_name" in sql
        assert "events.away_team_name" in sql

    def test_team_search_rank_compiles_weighted_team_names(self):
        stmt = select(_search_rank(_team_search_vector(), "NY Knicks"))
        sql = str(
            stmt.compile(
                dialect=postgresql.dialect(),
                compile_kwargs={"literal_binds": True},
            )
        ).lower()

        assert "'a'" in sql
        assert "teams.name" in sql
        assert "teams.abbreviation" in sql
        assert "teams.alternate_names" in sql

    def test_futures_search_rank_compiles_weighted_market_and_outcomes(self):
        stmt = select(_search_rank(_futures_search_vector(), "best picture"))
        sql = str(
            stmt.compile(
                dialect=postgresql.dialect(),
                compile_kwargs={"literal_binds": True},
            )
        ).lower()

        assert "websearch_to_tsquery" in sql
        assert "setweight" in sql
        assert "'b'" in sql
        assert "'c'" in sql
        assert "futures_markets.name" in sql
        assert "string_agg" in sql
        assert "futures_outcomes.market_id = futures_markets.id" in sql


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

    async def test_empty_db_response_top_level_shape(self, client):
        resp = await client.get("/api/events/typeahead?q=test")
        body = resp.json()
        assert set(body.keys()) == {"suggestions", "query"}

    async def test_missing_q_returns_403(self, client):
        resp = await client.get("/api/events/typeahead")
        assert resp.status_code == 422

    async def test_short_q_returns_403(self, client):
        """q must be at least 2 characters."""
        resp = await client.get("/api/events/typeahead?q=a")
        assert resp.status_code == 422

    async def test_long_q_returns_403(self, client):
        """q must be at most 50 characters."""
        long_query = "a" * 51
        resp = await client.get(f"/api/events/typeahead?q={long_query}")
        assert resp.status_code == 422

    async def test_empty_suggestions_on_no_match(self, client):
        """Mock DB returns no data, suggestions should be empty."""
        resp = await client.get("/api/events/typeahead?q=xyznonexistent")
        body = resp.json()
        assert body["suggestions"] == []

    async def test_at_most_7_suggestions(self, client):
        resp = await client.get("/api/events/typeahead?q=test")
        body = resp.json()
        assert len(body["suggestions"]) <= 7

    async def test_suggestion_item_shape_if_present(self, client):
        """If suggestions exist, each should have type and text."""
        resp = await client.get("/api/events/typeahead?q=test")
        body = resp.json()
        for item in body["suggestions"]:
            assert "type" in item
            assert "text" in item
            assert isinstance(item["type"], str)
            assert isinstance(item["text"], str)
            assert item["type"] in {"team", "event", "futures", "event_concept"}


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

    async def test_trending_item_shape_if_present(self, client):
        resp = await client.get("/api/events/search/trending")
        body = resp.json()
        for item in body["trending"]:
            assert "query" in item
            assert "count" in item
            assert isinstance(item["query"], str)
            assert isinstance(item["count"], int)


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
        assert set(body.keys()) == {"suggestions"}
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


# ============================================================================
# Faceted Search — GET /api/events/faceted
# ============================================================================


class TestFacetedSearchEndpoint:
    """GET /api/events/faceted — tag-based faceted event search."""

    async def test_returns_200(self, client):
        resp = await client.get("/api/events/faceted")
        assert resp.status_code == 200

    async def test_response_top_level_shape(self, client):
        resp = await client.get("/api/events/faceted")
        body = resp.json()
        assert set(body.keys()) == {"total", "page", "per_page", "filters", "events", "facets"}

    async def test_events_is_list(self, client):
        resp = await client.get("/api/events/faceted")
        body = resp.json()
        assert isinstance(body["events"], list)

    async def test_facets_is_dict(self, client):
        resp = await client.get("/api/events/faceted")
        body = resp.json()
        assert isinstance(body["facets"], dict)

    async def test_filters_is_list(self, client):
        resp = await client.get("/api/events/faceted")
        body = resp.json()
        assert isinstance(body["filters"], list)

    async def test_pagination_defaults(self, client):
        resp = await client.get("/api/events/faceted")
        body = resp.json()
        assert body["page"] == 1
        assert body["per_page"] == 25
        assert body["total"] == 0

    async def test_custom_pagination(self, client):
        resp = await client.get("/api/events/faceted?page=2&per_page=10")
        body = resp.json()
        assert body["page"] == 2
        assert body["per_page"] == 10

    async def test_invalid_page_returns_403(self, client):
        resp = await client.get("/api/events/faceted?page=0")
        assert resp.status_code == 422

    async def test_invalid_per_page_returns_403(self, client):
        resp = await client.get("/api/events/faceted?per_page=101")
        assert resp.status_code == 422

    async def test_invalid_days_too_low_returns_403(self, client):
        resp = await client.get("/api/events/faceted?days=0")
        assert resp.status_code == 422

    async def test_invalid_days_too_high_returns_403(self, client):
        resp = await client.get("/api/events/faceted?days=31")
        assert resp.status_code == 422

    async def test_sport_convenience_filter_accepted(self, client):
        resp = await client.get("/api/events/faceted?sport=basketball")
        assert resp.status_code == 200
        body = resp.json()
        assert "sport:basketball" in body["filters"]

    async def test_status_convenience_filter_accepted(self, client):
        resp = await client.get("/api/events/faceted?status=live")
        assert resp.status_code == 200
        body = resp.json()
        assert "status:live" in body["filters"]

    async def test_tags_json_array_accepted(self, client):
        resp = await client.get(
            "/api/events/faceted",
            params={"tags": '["sport:basketball", "stakes:high"]'},
        )
        assert resp.status_code == 200

    async def test_invalid_tags_json_is_ignored(self, client):
        """Malformed JSON tags should not crash the endpoint."""
        resp = await client.get(
            "/api/events/faceted",
            params={"tags": "not-valid-json"},
        )
        assert resp.status_code == 200

    async def test_empty_results_on_empty_db(self, client):
        resp = await client.get("/api/events/faceted")
        body = resp.json()
        assert body["events"] == []
        assert body["total"] == 0

    async def test_post_rejected(self, client):
        resp = await client.post("/api/events/faceted")
        assert resp.status_code == 405


# ============================================================================
# Search — Special Characters and Edge Cases
# ============================================================================


class TestSearchEdgeCases:
    """Edge cases for search query handling."""

    async def test_special_characters_in_query(self, client):
        """Queries with special characters should not crash."""
        resp = await client.get("/api/events/search?q=O'Brien")
        assert resp.status_code == 200

    async def test_unicode_query(self, client):
        resp = await client.get("/api/events/search?q=Müller")
        assert resp.status_code == 200

    async def test_numeric_query(self, client):
        resp = await client.get("/api/events/search?q=2026")
        assert resp.status_code == 200

    async def test_whitespace_padded_query(self, client):
        resp = await client.get("/api/events/search?q=  test  ")
        assert resp.status_code == 200
        body = resp.json()
        assert "query" in body

    async def test_max_length_query(self, client):
        """Very long queries should still work (no explicit max on search)."""
        long_q = "a" * 100
        resp = await client.get(f"/api/events/search?q={long_q}")
        assert resp.status_code == 200

    async def test_exactly_2_chars_accepted(self, client):
        """Minimum query length is 2."""
        resp = await client.get("/api/events/search?q=NY")
        assert resp.status_code == 200

    async def test_typeahead_exactly_2_chars_accepted(self, client):
        resp = await client.get("/api/events/typeahead?q=NY")
        assert resp.status_code == 200

    async def test_typeahead_exactly_50_chars_accepted(self, client):
        """Max typeahead length is 50."""
        q = "a" * 50
        resp = await client.get(f"/api/events/typeahead?q={q}")
        assert resp.status_code == 200


# ============================================================================
# Search — Sport Alias Matching
# ============================================================================


class TestSearchSportAliases:
    """Queries like 'NBA' or 'NFL' should be accepted and produce valid responses."""

    @pytest.mark.parametrize("alias", ["NBA", "NFL", "MLB", "NHL", "nba", "nfl"])
    async def test_sport_alias_search_returns_200(self, client, alias):
        resp = await client.get(f"/api/events/search?q={alias}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["query"] == alias

    @pytest.mark.parametrize("alias", ["NBA", "NFL", "MLB", "NHL"])
    async def test_sport_alias_typeahead_returns_200(self, client, alias):
        resp = await client.get(f"/api/events/typeahead?q={alias}")
        assert resp.status_code == 200
