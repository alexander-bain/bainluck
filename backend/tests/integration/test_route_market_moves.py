"""Contract tests for market moves endpoint.

Tests:
- GET /api/market-moves — 'The Market Was Wrong' surprises feed

Uses the shared ``client`` fixture from conftest.py (mock empty DB session).
"""

import pytest


class TestMarketMovesEndpoint:
    """GET /api/market-moves — recent market surprises."""

    async def test_returns_200(self, client):
        resp = await client.get("/api/market-moves")
        assert resp.status_code == 200

    async def test_response_is_list(self, client):
        resp = await client.get("/api/market-moves")
        body = resp.json()
        assert isinstance(body, (list, dict))

    async def test_hours_param_accepted(self, client):
        resp = await client.get("/api/market-moves?hours=72")
        assert resp.status_code == 200

    async def test_limit_param_accepted(self, client):
        resp = await client.get("/api/market-moves?limit=5")
        assert resp.status_code == 200

    async def test_hours_too_low_returns_422(self, client):
        resp = await client.get("/api/market-moves?hours=1")
        assert resp.status_code == 422

    async def test_hours_too_high_returns_422(self, client):
        resp = await client.get("/api/market-moves?hours=999")
        assert resp.status_code == 422

    async def test_limit_too_high_returns_422(self, client):
        resp = await client.get("/api/market-moves?limit=100")
        assert resp.status_code == 422

    async def test_limit_zero_returns_422(self, client):
        resp = await client.get("/api/market-moves?limit=0")
        assert resp.status_code == 422
