"""Integration tests for POST /api/admin/db-query endpoint."""

import os

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

_has_db = "DATABASE_URL" in os.environ
_needs_db = pytest.mark.skipif(not _has_db, reason="No DATABASE_URL — CI only")


@pytest.fixture
def admin_secret(monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", "test-secret")
    return "test-secret"


def _client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.mark.asyncio
async def test_403_without_secret():
    async with _client() as client:
        resp = await client.post(
            "/api/admin/db-query?secret=wrong",
            json={"sql": "SELECT 1"},
        )
    assert resp.status_code == 403


@pytest.mark.asyncio
@_needs_db
async def test_simple_select(admin_secret):
    async with _client() as client:
        resp = await client.post(
            f"/api/admin/db-query?secret={admin_secret}",
            json={"sql": "SELECT 1 AS n, 'hello' AS greeting"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert "columns" in data
    assert "rows" in data
    assert data["row_count"] >= 1
    assert "duration_ms" in data


@pytest.mark.asyncio
@pytest.mark.parametrize("sql", [
    "INSERT INTO events (id) VALUES (1)",
    "UPDATE events SET status='live'",
    "DELETE FROM events",
    "DROP TABLE events",
    "TRUNCATE events",
    "ALTER TABLE events ADD COLUMN x TEXT",
])
async def test_mutation_rejected(admin_secret, sql):
    async with _client() as client:
        resp = await client.post(
            f"/api/admin/db-query?secret={admin_secret}",
            json={"sql": sql},
        )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_multi_statement_rejected(admin_secret):
    async with _client() as client:
        resp = await client.post(
            f"/api/admin/db-query?secret={admin_secret}",
            json={"sql": "SELECT 1; DROP TABLE events"},
        )
    assert resp.status_code == 400


@pytest.mark.asyncio
@_needs_db
async def test_row_cap_enforced(admin_secret):
    async with _client() as client:
        resp = await client.post(
            f"/api/admin/db-query?secret={admin_secret}",
            json={"sql": "SELECT generate_series(1, 5000)", "limit": 10},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["row_count"] <= 10
    assert data["truncated"] is True


@pytest.mark.asyncio
@_needs_db
async def test_with_cte_allowed(admin_secret):
    async with _client() as client:
        resp = await client.post(
            f"/api/admin/db-query?secret={admin_secret}",
            json={"sql": "WITH x AS (SELECT 1 AS n) SELECT * FROM x"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["row_count"] == 1


@pytest.mark.asyncio
@_needs_db
async def test_limit_capped_at_1000(admin_secret):
    async with _client() as client:
        resp = await client.post(
            f"/api/admin/db-query?secret={admin_secret}",
            json={"sql": "SELECT generate_series(1, 5000)", "limit": 9999},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["row_count"] <= 1000
