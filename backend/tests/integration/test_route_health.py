"""Contract tests for health and utility endpoints."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest


class TestHealthEndpoint:

    @pytest.mark.parametrize("path", ["/health", "/api/health"])
    async def test_returns_health_contract(self, client, path):
        resp = await client.get(path)

        assert resp.status_code == 200
        body = resp.json()
        assert set(body) == {"status", "version", "commit", "features"}
        assert body["status"] == "healthy"
        assert body["version"] == "0.1.0"
        assert isinstance(body["commit"], str)
        assert body["commit"]
        assert body["features"] == [
            "sync_sports",
            "discover_events",
            "get_support",
        ]


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

    async def test_empty_response_contract(self, client):
        resp = await client.get("/api/sports")

        assert resp.status_code == 200
        assert resp.json() == {"sports": []}

    async def test_sport_item_contract(self, client, mock_db):
        sport = SimpleNamespace(
            id=42,
            key="basketball_nba",
            name="NBA",
            group="Basketball",
        )
        result = mock_db.execute.return_value
        result.scalars.return_value.all.return_value = [sport]

        resp = await client.get("/api/sports")

        assert resp.status_code == 200
        assert resp.json() == {
            "sports": [
                {
                    "id": 42,
                    "key": "basketball_nba",
                    "name": "NBA",
                    "group": "Basketball",
                }
            ]
        }


class TestSportsAdminEndpointGuards:
    """Quota-burning sports admin endpoints reject bad secrets before side effects."""

    @pytest.mark.parametrize(
        ("method", "path"),
        [
            ("get", "/api/sports/available?secret=bad"),
            ("post", "/api/sports/sync?secret=bad"),
        ],
    )
    async def test_invalid_secret_rejects_before_odds_api_call(
        self, client, method, path
    ):
        with patch("app.routes.sports.OddsAPIService") as service_cls:
            resp = await getattr(client, method)(path)

        assert resp.status_code == 403
        assert resp.json() == {"detail": "Invalid admin secret"}
        service_cls.assert_not_called()

    async def test_sync_invalid_secret_does_not_commit(self, client, mock_db):
        resp = await client.post("/api/sports/sync?secret=bad")

        assert resp.status_code == 403
        mock_db.commit.assert_not_awaited()
