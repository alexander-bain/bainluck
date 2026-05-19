"""Integration tests for GET /api/entertainment.

Validates response shape, empty-DB defaults, and HTTP method rejection.
Uses the shared ``client`` / ``mock_db`` fixtures from conftest.py.
"""

import pytest


class _MockScalars:
    def __init__(self, items):
        self._items = items

    def all(self):
        return self._items

    def unique(self):
        return self


class _MockResult:
    def __init__(self, items):
        self._scalars = _MockScalars(items)

    def scalars(self):
        return self._scalars


class TestEntertainmentBasicShape:
    async def test_returns_200(self, client, mock_db):
        mock_db.execute.return_value = _MockResult([])
        resp = await client.get("/api/entertainment")
        assert resp.status_code == 200

    async def test_has_expected_top_level_keys(self, client, mock_db):
        mock_db.execute.return_value = _MockResult([])
        body = (await client.get("/api/entertainment")).json()
        assert "themes" in body
        assert "total_markets" in body
        assert "by_source" in body
        assert "cross_source" in body

    async def test_empty_db_returns_zero_totals(self, client, mock_db):
        mock_db.execute.return_value = _MockResult([])
        body = (await client.get("/api/entertainment")).json()
        assert body["total_markets"] == 0
        assert isinstance(body["themes"], dict)
        assert isinstance(body["cross_source"], list)

    async def test_empty_db_by_source_zeros(self, client, mock_db):
        mock_db.execute.return_value = _MockResult([])
        body = (await client.get("/api/entertainment")).json()
        by_source = body["by_source"]
        assert by_source.get("kalshi", 0) == 0
        assert by_source.get("polymarket", 0) == 0


class TestEntertainmentHTTPMethods:
    async def test_post_rejected(self, client):
        resp = await client.post("/api/entertainment")
        assert resp.status_code == 405

    async def test_put_rejected(self, client):
        resp = await client.put("/api/entertainment")
        assert resp.status_code == 405

    async def test_delete_rejected(self, client):
        resp = await client.delete("/api/entertainment")
        assert resp.status_code == 405

    async def test_query_params_ignored(self, client, mock_db):
        mock_db.execute.return_value = _MockResult([])
        resp = await client.get("/api/entertainment?foo=bar&baz=1")
        assert resp.status_code == 200
