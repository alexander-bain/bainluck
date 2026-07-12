"""Contract tests for the L2-90 async-cache on heavy admin health endpoints.

``/api/admin/audit/all`` and ``/api/admin/prediction-markets/link-rate`` compute
~25s synchronously and were 503ing at the 30s router limit under load. They now
serve a precomputed Redis snapshot instantly, falling back to computing inline on
a cold cache or ``?bust=1``. These tests pin that contract:

- valid secret + warm cache  → served from Redis, compute NOT called
- valid secret + cold cache   → compute called, result written to Redis
- valid secret + ``bust=1``   → compute called even when the cache is warm
- bad / missing secret        → 403 (guard applies before the cache read)
"""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest


class _FakeRedis:
    """Minimal in-memory stand-in for the sync redis client."""

    def __init__(self, initial=None):
        self.store = dict(initial or {})
        self.set_calls = []

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value, ex=None):
        self.store[key] = value
        self.set_calls.append((key, value, ex))


@pytest.fixture
def admin_secret(monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", "testsecret")
    return "testsecret"


# ---------------------------------------------------------------------------
# link-rate
# ---------------------------------------------------------------------------
class TestLinkRateCache:
    PATH = "/api/admin/prediction-markets/link-rate"

    async def test_warm_cache_served_without_compute(self, client, admin_secret, monkeypatch):
        cached = {"generated_at": "2026-07-12T00:00:00+00:00", "overall": {"link_rate_pct": 91.2}}
        fake = _FakeRedis({"bainluck:admin:link_rate": json.dumps(cached)})
        monkeypatch.setattr("app.tasks.redis_state.get_redis_client", lambda *a, **k: fake)
        compute = AsyncMock()
        monkeypatch.setattr("app.routes.admin_matching._compute_link_rate", compute)

        resp = await client.get(f"{self.PATH}?secret={admin_secret}")

        assert resp.status_code == 200
        assert resp.json() == cached
        compute.assert_not_called()

    async def test_cold_cache_computes_and_writes(self, client, admin_secret, monkeypatch):
        fake = _FakeRedis()
        monkeypatch.setattr("app.tasks.redis_state.get_redis_client", lambda *a, **k: fake)
        payload = {"generated_at": "2026-07-12T01:00:00+00:00", "overall": {"link_rate_pct": 88.0}}
        monkeypatch.setattr(
            "app.routes.admin_matching._compute_link_rate", AsyncMock(return_value=payload)
        )

        resp = await client.get(f"{self.PATH}?secret={admin_secret}")

        assert resp.status_code == 200
        assert resp.json() == payload
        # Result written back to Redis with a TTL so the next read is instant.
        assert fake.store["bainluck:admin:link_rate"] == json.dumps(payload)
        assert fake.set_calls and fake.set_calls[0][2] == 3600

    async def test_bust_bypasses_warm_cache(self, client, admin_secret, monkeypatch):
        stale = {"overall": {"link_rate_pct": 10.0}}
        fake = _FakeRedis({"bainluck:admin:link_rate": json.dumps(stale)})
        monkeypatch.setattr("app.tasks.redis_state.get_redis_client", lambda *a, **k: fake)
        fresh = {"generated_at": "2026-07-12T02:00:00+00:00", "overall": {"link_rate_pct": 99.0}}
        compute = AsyncMock(return_value=fresh)
        monkeypatch.setattr("app.routes.admin_matching._compute_link_rate", compute)

        resp = await client.get(f"{self.PATH}?secret={admin_secret}&bust=1")

        assert resp.status_code == 200
        assert resp.json() == fresh
        compute.assert_awaited_once()

    async def test_bad_secret_returns_403(self, client):
        resp = await client.get(f"{self.PATH}?secret=bad")
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# audit/all
# ---------------------------------------------------------------------------
class TestAuditAllCache:
    PATH = "/api/admin/audit/all"

    async def test_warm_cache_served_without_compute(self, client, admin_secret, monkeypatch):
        cached = {"generated_at": "2026-07-12T00:00:00+00:00", "avg_score": 100, "scores": {}, "grids": {}}
        fake = _FakeRedis({"bainluck:admin:audit_all": json.dumps(cached)})
        monkeypatch.setattr("app.tasks.redis_state.get_redis_client", lambda *a, **k: fake)
        compute = AsyncMock()
        monkeypatch.setattr("app.routes.admin_data_quality._compute_audit_all_grids", compute)

        resp = await client.get(f"{self.PATH}?secret={admin_secret}")

        assert resp.status_code == 200
        assert resp.json() == cached
        compute.assert_not_called()

    async def test_cold_cache_computes_and_writes(self, client, admin_secret, monkeypatch):
        fake = _FakeRedis()
        monkeypatch.setattr("app.tasks.redis_state.get_redis_client", lambda *a, **k: fake)
        payload = {"generated_at": "2026-07-12T01:00:00+00:00", "avg_score": 97, "scores": {"nba": 97}, "grids": {}}
        monkeypatch.setattr(
            "app.routes.admin_data_quality._compute_audit_all_grids",
            AsyncMock(return_value=payload),
        )

        resp = await client.get(f"{self.PATH}?secret={admin_secret}")

        assert resp.status_code == 200
        assert resp.json() == payload
        assert fake.store["bainluck:admin:audit_all"] == json.dumps(payload)
        assert fake.set_calls and fake.set_calls[0][2] == 3600

    async def test_bust_bypasses_warm_cache(self, client, admin_secret, monkeypatch):
        stale = {"avg_score": 1, "scores": {}, "grids": {}}
        fake = _FakeRedis({"bainluck:admin:audit_all": json.dumps(stale)})
        monkeypatch.setattr("app.tasks.redis_state.get_redis_client", lambda *a, **k: fake)
        fresh = {"generated_at": "2026-07-12T02:00:00+00:00", "avg_score": 99, "scores": {}, "grids": {}}
        compute = AsyncMock(return_value=fresh)
        monkeypatch.setattr("app.routes.admin_data_quality._compute_audit_all_grids", compute)

        resp = await client.get(f"{self.PATH}?secret={admin_secret}&bust=1")

        assert resp.status_code == 200
        assert resp.json() == fresh
        compute.assert_awaited_once()

    async def test_bad_secret_returns_403(self, client):
        resp = await client.get(f"{self.PATH}?secret=bad")
        assert resp.status_code == 403


class TestAdminHealthPrecomputeTasks:
    """The precompute impls write the same Redis keys the routes read."""

    async def test_link_rate_task_writes_cache(self, monkeypatch):
        from app.tasks import precompute_admin_health as mod

        fake = _FakeRedis()
        monkeypatch.setattr("app.tasks.redis_state.get_redis_client", lambda *a, **k: fake)
        payload = {"generated_at": "x", "overall": {"link_rate_pct": 90.0, "total_game_markets": 5}}
        monkeypatch.setattr(
            "app.routes.admin_matching._compute_link_rate", AsyncMock(return_value=payload)
        )

        class _FakeSession:
            async def __aenter__(self):
                return MagicMock()

            async def __aexit__(self, *a):
                return False

        monkeypatch.setattr("app.tasks.base.get_task_session", lambda: _FakeSession())

        result = await mod._precompute_admin_link_rate()

        assert result["status"] == "ok"
        assert fake.store["bainluck:admin:link_rate"] == json.dumps(payload)

    async def test_audit_all_task_writes_cache(self, monkeypatch):
        from app.tasks import precompute_admin_health as mod

        fake = _FakeRedis()
        monkeypatch.setattr("app.tasks.redis_state.get_redis_client", lambda *a, **k: fake)
        payload = {"generated_at": "x", "avg_score": 100, "scores": {}, "grids": {}}
        monkeypatch.setattr(
            "app.routes.admin_data_quality._compute_audit_all_grids",
            AsyncMock(return_value=payload),
        )

        result = await mod._precompute_admin_audit_all()

        assert result["status"] == "ok"
        assert fake.store["bainluck:admin:audit_all"] == json.dumps(payload)
