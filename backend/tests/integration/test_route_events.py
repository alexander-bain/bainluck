"""Contract tests for event endpoints.

- GET /api/events/{id} — event detail
- GET /api/events/{id}/related-futures — related futures for event
"""

import pytest


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


class TestRelatedFutures404:

    async def test_nonexistent_event_returns_404(self, client):
        resp = await client.get("/api/events/999999/related-futures")
        assert resp.status_code == 404
