"""Contract tests for GET /api/futures/multi-history.

Tests:
- Input validation (bad IDs, empty, missing)
- Single-market fallback (delegates to /{market_id}/history)
- Multiple market IDs with no data returns 404
- Endpoint routing works (not swallowed by /{market_id} wildcard)

Uses the shared ``client`` fixture from conftest.py (mock empty DB session).
"""

import pytest


class TestMultiHistoryEndpoint:
    """GET /api/futures/multi-history — cross-source history aggregation."""

    async def test_missing_market_ids_returns_422(self, client):
        """Required query param market_ids must be present."""
        resp = await client.get("/api/futures/multi-history")
        assert resp.status_code == 422

    async def test_bad_market_ids_returns_400(self, client):
        """Non-integer market_ids returns 400."""
        resp = await client.get("/api/futures/multi-history?market_ids=abc")
        assert resp.status_code == 400

    async def test_empty_market_ids_returns_400(self, client):
        """Empty market_ids string returns 400."""
        resp = await client.get("/api/futures/multi-history?market_ids=")
        assert resp.status_code == 400

    async def test_single_market_delegates_to_history(self, client):
        """Single market_id delegates to standard history (returns 404 on empty DB)."""
        resp = await client.get("/api/futures/multi-history?market_ids=1")
        assert resp.status_code == 404

    async def test_multiple_markets_no_data_returns_404(self, client):
        """Multiple market_ids with no matching markets returns 404."""
        resp = await client.get("/api/futures/multi-history?market_ids=999,998")
        assert resp.status_code == 404

    async def test_accepts_hours_param(self, client):
        """hours query param is accepted."""
        resp = await client.get("/api/futures/multi-history?market_ids=1,2&hours=24")
        assert resp.status_code in (200, 404)

    async def test_accepts_top_n_param(self, client):
        """top_n query param is accepted."""
        resp = await client.get("/api/futures/multi-history?market_ids=1,2&top_n=5")
        assert resp.status_code in (200, 404)

    async def test_not_swallowed_by_market_id_wildcard(self, client):
        """Route is not caught by /{market_id} dynamic route."""
        # If it were swallowed, we'd get a 422 (can't parse "multi-history" as int)
        resp = await client.get("/api/futures/multi-history?market_ids=1")
        # Should be 404 (market not found), not 422 (validation error on path param)
        assert resp.status_code == 404
