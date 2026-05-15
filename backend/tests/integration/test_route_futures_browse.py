"""Contract tests for futures browsing, category, and movers endpoints.

Tests:
- GET /api/futures/browse — paginated market browsing
- GET /api/futures/categories — category counts for search grid
- GET /api/futures/movers — biggest probability movers
- GET /api/futures/available — list available sources/categories
- GET /api/futures — main futures listing
- GET /api/futures/compare — cross-source comparison

Uses the shared ``client`` fixture from conftest.py (mock empty DB session).
"""

import pytest


# ============================================================================
# Futures Browse — /api/futures/browse
# ============================================================================


class TestFuturesBrowseEndpoint:
    """GET /api/futures/browse — paginated category browsing."""

    async def test_returns_200(self, client):
        resp = await client.get("/api/futures/browse")
        assert resp.status_code == 200

    async def test_response_has_required_keys(self, client):
        resp = await client.get("/api/futures/browse")
        body = resp.json()
        for key in ["items", "total", "limit", "offset", "has_more"]:
            assert key in body, f"Missing key: {key}"

    async def test_items_is_list(self, client):
        resp = await client.get("/api/futures/browse")
        body = resp.json()
        assert isinstance(body["items"], list)

    async def test_total_is_non_negative_int(self, client):
        resp = await client.get("/api/futures/browse")
        body = resp.json()
        assert isinstance(body["total"], int)
        assert body["total"] >= 0

    async def test_limit_defaults(self, client):
        resp = await client.get("/api/futures/browse")
        body = resp.json()
        assert body["limit"] == 50
        assert body["offset"] == 0

    async def test_has_more_is_bool(self, client):
        resp = await client.get("/api/futures/browse")
        body = resp.json()
        assert isinstance(body["has_more"], bool)

    async def test_empty_db_returns_empty_items(self, client):
        resp = await client.get("/api/futures/browse")
        body = resp.json()
        assert body["items"] == []
        assert body["total"] == 0
        assert body["has_more"] is False

    async def test_category_filter_accepted(self, client):
        resp = await client.get("/api/futures/browse?category=politics")
        assert resp.status_code == 200

    async def test_search_q_accepted(self, client):
        resp = await client.get("/api/futures/browse?q=championship")
        assert resp.status_code == 200

    async def test_pagination_params_accepted(self, client):
        resp = await client.get("/api/futures/browse?limit=10&offset=5")
        assert resp.status_code == 200
        body = resp.json()
        assert body["limit"] == 10
        assert body["offset"] == 5

    async def test_limit_too_high_returns_422(self, client):
        resp = await client.get("/api/futures/browse?limit=999")
        assert resp.status_code == 422

    async def test_negative_offset_returns_422(self, client):
        resp = await client.get("/api/futures/browse?offset=-1")
        assert resp.status_code == 422

    async def test_item_shape_if_present(self, client):
        """When items exist, validate expected fields."""
        resp = await client.get("/api/futures/browse")
        body = resp.json()
        for item in body["items"]:
            assert "id" in item
            assert "name" in item
            assert "source" in item
            assert "top_outcomes" in item
            assert isinstance(item["id"], int)
            assert isinstance(item["name"], str)
            assert isinstance(item["source"], str)
            assert isinstance(item["top_outcomes"], list)


# ============================================================================
# Futures Categories — /api/futures/categories
# ============================================================================


class TestFuturesCategoriesEndpoint:
    """GET /api/futures/categories — category counts for search grid."""

    async def test_returns_200(self, client):
        resp = await client.get("/api/futures/categories")
        assert resp.status_code == 200

    async def test_response_has_categories_key(self, client):
        resp = await client.get("/api/futures/categories")
        body = resp.json()
        assert "categories" in body
        assert isinstance(body["categories"], list)

    async def test_response_has_total_key(self, client):
        resp = await client.get("/api/futures/categories")
        body = resp.json()
        assert "total" in body
        assert isinstance(body["total"], int)
        assert body["total"] >= 0

    async def test_category_item_shape_if_present(self, client):
        resp = await client.get("/api/futures/categories")
        body = resp.json()
        for cat in body["categories"]:
            assert "key" in cat
            assert "count" in cat
            assert isinstance(cat["key"], str)
            assert isinstance(cat["count"], int)
            assert cat["count"] > 0

    async def test_total_equals_sum_of_counts(self, client):
        resp = await client.get("/api/futures/categories")
        body = resp.json()
        assert body["total"] == sum(c["count"] for c in body["categories"])


# ============================================================================
# Futures Movers — /api/futures/movers
# ============================================================================


class TestFuturesMoversEndpoint:
    """GET /api/futures/movers — biggest probability movers."""

    async def test_returns_200(self, client):
        resp = await client.get("/api/futures/movers")
        assert resp.status_code == 200

    async def test_response_has_movers_key(self, client):
        resp = await client.get("/api/futures/movers")
        body = resp.json()
        assert "movers" in body
        assert isinstance(body["movers"], list)

    async def test_response_has_timeframe_hours(self, client):
        resp = await client.get("/api/futures/movers")
        body = resp.json()
        assert "timeframe_hours" in body
        assert isinstance(body["timeframe_hours"], int)
        assert body["timeframe_hours"] == 24  # default

    async def test_custom_hours_param(self, client):
        resp = await client.get("/api/futures/movers?hours=48")
        assert resp.status_code == 200
        body = resp.json()
        assert body["timeframe_hours"] == 48

    async def test_custom_limit_param(self, client):
        resp = await client.get("/api/futures/movers?limit=5")
        assert resp.status_code == 200

    async def test_mover_item_shape_if_present(self, client):
        resp = await client.get("/api/futures/movers")
        body = resp.json()
        for mover in body["movers"]:
            assert "outcome_id" in mover
            assert "name" in mover
            assert "market_id" in mover
            assert "market_name" in mover
            assert "current_probability" in mover
            assert "probability_change_24h" in mover
            assert isinstance(mover["outcome_id"], int)
            assert isinstance(mover["name"], str)
            assert isinstance(mover["market_id"], int)

    async def test_empty_db_returns_empty_movers(self, client):
        resp = await client.get("/api/futures/movers")
        body = resp.json()
        assert body["movers"] == []


# ============================================================================
# Futures Available — /api/futures/available
# ============================================================================


class TestFuturesAvailableEndpoint:
    """GET /api/futures/available — available sources and categories.

    This endpoint calls the external Odds API service, so it returns 502
    when the service is unavailable (expected in mock environment).
    """

    async def test_returns_200_or_502(self, client):
        """Returns 200 when Odds API is reachable, 502 otherwise."""
        resp = await client.get("/api/futures/available")
        assert resp.status_code in (200, 502)


# ============================================================================
# Futures Main List — /api/futures
# ============================================================================


class TestFuturesListEndpoint:
    """GET /api/futures — main futures listing."""

    async def test_returns_200(self, client):
        resp = await client.get("/api/futures")
        assert resp.status_code == 200

    async def test_response_is_list_or_paginated(self, client):
        resp = await client.get("/api/futures")
        body = resp.json()
        # Could be a list or paginated dict
        assert isinstance(body, (list, dict))

    async def test_sport_filter_accepted(self, client):
        resp = await client.get("/api/futures?sport=basketball")
        assert resp.status_code == 200

    async def test_source_filter_accepted(self, client):
        resp = await client.get("/api/futures?source=kalshi")
        assert resp.status_code == 200


# ============================================================================
# Futures Compare — /api/futures/compare
# ============================================================================


class TestFuturesCompareEndpoint:
    """GET /api/futures/compare — cross-source market comparison."""

    async def test_missing_key_returns_422(self, client):
        """The key parameter is required."""
        resp = await client.get("/api/futures/compare")
        assert resp.status_code == 422

    async def test_with_key_returns_200_or_404(self, client):
        """With a key parameter, returns 200 (with data or empty) or 404."""
        resp = await client.get("/api/futures/compare?key=nonexistent:key:here")
        assert resp.status_code in (200, 404)

    async def test_200_response_has_required_keys(self, client):
        """When 200, response should have canonical_key, sources, outcomes."""
        resp = await client.get("/api/futures/compare?key=test:key")
        if resp.status_code == 200:
            body = resp.json()
            assert "canonical_key" in body
            assert "sources" in body
            assert "outcomes" in body
            assert "outcome_count" in body
            assert isinstance(body["sources"], list)
            assert isinstance(body["outcomes"], list)
            assert isinstance(body["outcome_count"], int)
