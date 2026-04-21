"""Contract tests for GET /api/feed.

Tests response shape and query parameter validation, not exact data values.
The feed is the home page — the most important endpoint for user experience.
"""

import pytest


class TestFeedEmptyShape:
    """With an empty DB, the feed returns a valid empty response."""

    async def test_returns_200(self, client):
        resp = await client.get("/api/feed")
        assert resp.status_code == 200

    async def test_has_required_keys(self, client):
        resp = await client.get("/api/feed")
        body = resp.json()
        for key in ["items", "total", "limit", "offset", "has_more"]:
            assert key in body, f"Missing key: {key}"

    async def test_items_is_list(self, client):
        resp = await client.get("/api/feed")
        body = resp.json()
        assert isinstance(body["items"], list)

    async def test_empty_db_returns_empty_items(self, client):
        resp = await client.get("/api/feed")
        body = resp.json()
        assert body["items"] == []
        assert body["total"] == 0

    async def test_has_more_is_false_when_empty(self, client):
        resp = await client.get("/api/feed")
        body = resp.json()
        assert body["has_more"] is False

    async def test_limit_defaults_to_200(self, client):
        resp = await client.get("/api/feed")
        body = resp.json()
        assert body["limit"] == 200

    async def test_offset_defaults_to_0(self, client):
        resp = await client.get("/api/feed")
        body = resp.json()
        assert body["offset"] == 0

    async def test_total_is_int(self, client):
        resp = await client.get("/api/feed")
        body = resp.json()
        assert isinstance(body["total"], int)
        assert body["total"] >= 0


class TestFeedQueryParams:

    async def test_custom_limit(self, client):
        resp = await client.get("/api/feed?limit=10")
        body = resp.json()
        assert body["limit"] == 10

    async def test_custom_offset(self, client):
        resp = await client.get("/api/feed?offset=5")
        body = resp.json()
        assert body["offset"] == 5

    async def test_sport_filter_accepted(self, client):
        resp = await client.get("/api/feed?sport=basketball")
        assert resp.status_code == 200

    async def test_multiple_sport_filter(self, client):
        resp = await client.get("/api/feed?sport=basketball&sport=baseball")
        assert resp.status_code == 200

    async def test_include_events_false(self, client):
        resp = await client.get("/api/feed?include_events=false")
        assert resp.status_code == 200

    async def test_include_futures_false(self, client):
        resp = await client.get("/api/feed?include_futures=false")
        assert resp.status_code == 200

    async def test_include_both_false_returns_empty(self, client):
        resp = await client.get("/api/feed?include_events=false&include_futures=false")
        assert resp.status_code == 200
        body = resp.json()
        assert body["items"] == []

    async def test_status_filter_accepted(self, client):
        resp = await client.get("/api/feed?status=live")
        assert resp.status_code == 200

    async def test_limit_validation_too_high(self, client):
        resp = await client.get("/api/feed?limit=99999")
        assert resp.status_code == 422

    async def test_limit_validation_zero(self, client):
        resp = await client.get("/api/feed?limit=0")
        assert resp.status_code == 422

    async def test_offset_validation_negative(self, client):
        resp = await client.get("/api/feed?offset=-1")
        assert resp.status_code == 422


class TestFeedMyTeamsAnonymous:
    """my_teams_only without auth returns early with requires_auth flag."""

    async def test_returns_200(self, client):
        resp = await client.get("/api/feed?my_teams_only=true")
        assert resp.status_code == 200

    async def test_requires_auth_flag(self, client):
        resp = await client.get("/api/feed?my_teams_only=true")
        body = resp.json()
        assert body.get("requires_auth") is True
        assert body.get("my_teams_only") is True

    async def test_empty_items(self, client):
        resp = await client.get("/api/feed?my_teams_only=true")
        body = resp.json()
        assert body["items"] == []
        assert body["total"] == 0


class TestFeedResponseTypes:
    """Verify field types in the response match the frontend's expectations."""

    async def test_total_limit_offset_are_ints(self, client):
        resp = await client.get("/api/feed")
        body = resp.json()
        assert isinstance(body["total"], int)
        assert isinstance(body["limit"], int)
        assert isinstance(body["offset"], int)

    async def test_has_more_is_bool(self, client):
        resp = await client.get("/api/feed")
        body = resp.json()
        assert isinstance(body["has_more"], bool)
