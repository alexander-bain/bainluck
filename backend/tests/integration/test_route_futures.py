"""Contract tests for futures endpoints.

- GET /api/futures/{market_id} — market detail
"""

import pytest


class TestFuturesMarketDetail:
    """GET /api/futures/{market_id} — single market detail."""

    async def test_nonexistent_market_returns_404(self, client):
        resp = await client.get("/api/futures/999999")
        assert resp.status_code == 404

    async def test_invalid_id_returns_422(self, client):
        resp = await client.get("/api/futures/not-a-number")
        assert resp.status_code == 422
