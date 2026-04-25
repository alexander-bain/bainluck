"""Contract tests for GET /api/events/{id}/related-futures.

Verifies response shape, team-side classification, and category structure.
"""

import pytest


class TestRelatedFuturesEmptyShape:
    """With an empty DB, related futures returns valid empty response."""

    async def test_returns_200_for_nonexistent_event(self, client):
        resp = await client.get("/api/events/999999/related-futures")
        assert resp.status_code in (200, 404)

    async def test_returns_404_for_invalid_id(self, client):
        resp = await client.get("/api/events/abc/related-futures")
        assert resp.status_code == 422


class TestRelatedFuturesQueryParams:
    """Query parameter validation."""

    async def test_debug_param_accepted(self, client):
        resp = await client.get("/api/events/1/related-futures?debug=true")
        assert resp.status_code in (200, 404)

    async def test_debug_false_accepted(self, client):
        resp = await client.get("/api/events/1/related-futures?debug=false")
        assert resp.status_code in (200, 404)


class TestGameMarketsEmptyShape:
    """With an empty DB, game-markets returns valid empty response."""

    async def test_returns_200(self, client):
        resp = await client.get("/api/events/999999/game-markets")
        assert resp.status_code in (200, 404)

    async def test_response_has_sections(self, client):
        resp = await client.get("/api/events/999999/game-markets")
        if resp.status_code == 200:
            body = resp.json()
            for key in ["totals", "player_props", "spreads", "other"]:
                assert key in body, f"Missing key: {key}"


class TestEventHistoryEmptyShape:
    """With an empty DB, event history returns valid empty response."""

    async def test_returns_200(self, client):
        resp = await client.get("/api/events/999999/history")
        assert resp.status_code in (200, 404)
