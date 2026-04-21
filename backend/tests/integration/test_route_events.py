"""Contract tests for event endpoints.

- GET /api/events — event list
- GET /api/events/{id} — event detail
- GET /api/events/{id}/related-futures — related futures for event
- GET /api/events/search — event search
"""

import pytest


class TestEventList:
    """GET /api/events — list of events."""

    async def test_returns_200(self, client):
        resp = await client.get("/api/events")
        assert resp.status_code == 200

    async def test_response_is_list(self, client):
        resp = await client.get("/api/events")
        body = resp.json()
        assert isinstance(body, (list, dict))

    async def test_sport_filter_accepted(self, client):
        resp = await client.get("/api/events?sport=basketball_nba")
        assert resp.status_code == 200

    async def test_status_filter_accepted(self, client):
        resp = await client.get("/api/events?status=live")
        assert resp.status_code == 200

    async def test_limit_param_accepted(self, client):
        resp = await client.get("/api/events?limit=5")
        assert resp.status_code == 200


class TestEventSearch:
    """GET /api/events/search — search by query string."""

    async def test_missing_query_returns_422(self, client):
        resp = await client.get("/api/events/search")
        assert resp.status_code == 422

    async def test_with_query_returns_200(self, client):
        resp = await client.get("/api/events/search?q=celtics")
        assert resp.status_code == 200


class TestEventDetail404:

    async def test_nonexistent_event_returns_404(self, client):
        resp = await client.get("/api/events/999999")
        assert resp.status_code == 404

    async def test_404_body_has_detail(self, client):
        resp = await client.get("/api/events/999999")
        body = resp.json()
        assert "detail" in body
        assert body["detail"] == "Event not found"

    async def test_invalid_id_type_returns_422(self, client):
        resp = await client.get("/api/events/not-a-number")
        assert resp.status_code == 422

    async def test_zero_id_returns_404(self, client):
        resp = await client.get("/api/events/0")
        assert resp.status_code == 404

    async def test_negative_id_returns_404_or_422(self, client):
        resp = await client.get("/api/events/-1")
        assert resp.status_code in (404, 422)


class TestRelatedFutures404:

    async def test_nonexistent_event_returns_404(self, client):
        resp = await client.get("/api/events/999999/related-futures")
        assert resp.status_code == 404

    async def test_invalid_id_returns_422(self, client):
        resp = await client.get("/api/events/abc/related-futures")
        assert resp.status_code == 422


class TestEventOddsHistory:
    """GET /api/events/{id}/history — odds history for charting."""

    async def test_nonexistent_event_returns_404(self, client):
        resp = await client.get("/api/events/999999/history")
        assert resp.status_code == 404

    async def test_invalid_id_returns_422(self, client):
        resp = await client.get("/api/events/abc/history")
        assert resp.status_code == 422
