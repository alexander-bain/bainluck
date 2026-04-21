"""Contract tests for golf endpoints.

- GET /api/golf — golf landing page
- GET /api/playoffs/golf — golf championship grid
"""

import pytest


class TestGolfLandingPage:
    """GET /api/golf — main golf data."""

    async def test_returns_200(self, client):
        resp = await client.get("/api/golf")
        assert resp.status_code == 200


class TestGolfGrid:
    """GET /api/playoffs/golf — golf championship grid."""

    async def test_returns_200(self, client):
        resp = await client.get("/api/playoffs/golf")
        assert resp.status_code == 200
