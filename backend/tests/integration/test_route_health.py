"""Contract tests for health and utility endpoints."""

import pytest


class TestHealthEndpoint:

    async def test_returns_200(self, client):
        resp = await client.get("/health")
        assert resp.status_code == 200

    async def test_has_status_field(self, client):
        resp = await client.get("/health")
        body = resp.json()
        assert "status" in body
        assert body["status"] == "healthy"

    async def test_has_version(self, client):
        resp = await client.get("/health")
        body = resp.json()
        assert "version" in body


class TestApiHealth:

    async def test_returns_200(self, client):
        resp = await client.get("/api/health")
        assert resp.status_code == 200


class TestSportsEndpoint:
    """GET /api/sports — list of supported sports."""

    async def test_returns_200(self, client):
        resp = await client.get("/api/sports")
        assert resp.status_code == 200

    async def test_response_has_sports_key(self, client):
        resp = await client.get("/api/sports")
        body = resp.json()
        assert "sports" in body
        assert isinstance(body["sports"], list)
