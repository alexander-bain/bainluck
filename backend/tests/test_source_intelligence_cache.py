"""Guard tests for L2-129 / #206: the Measure page must NEVER cache a timeout/empty
build.

The blank-page bug: the four corpus queries run inline, a statement-timeout produces an
all-empty payload via the per-query fallbacks, and that empty payload was then cached for
6h — so one slow moment blanked the page until the TTL expired. The route now (a) prefers
a precomputed Redis snapshot, (b) on an inline build never persists a degraded/empty
result, and (c) serves the last good snapshot (stale) instead of a blank page.

These are behavioural guards on the route handler itself (called directly with a fake DB
and a fake Redis), so they assert the no-poison contract, not just SQL shape.
"""

import asyncio

import pytest

from app.routes import source_intelligence as si


class _FakeDB:
    """Minimal AsyncSession stand-in — only needs an awaitable execute for _set_timeout."""

    async def execute(self, *_a, **_k):
        return None


class _FakeRedis:
    """Records writes; get() misses unless a key was seeded (serve-stale test)."""

    def __init__(self, seed=None):
        self.store = dict(seed or {})
        self.sets = {}

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value, ex=None):
        self.sets[key] = value
        self.store[key] = value


@pytest.fixture(autouse=True)
def _reset_cache():
    prev = dict(si._cache)
    si._cache["data"] = None
    si._cache["timestamp"] = 0
    yield
    si._cache["data"] = prev.get("data")
    si._cache["timestamp"] = prev.get("timestamp", 0)


def _patch_queries_raise(monkeypatch):
    async def _boom(_db):
        raise RuntimeError("statement timeout")

    monkeypatch.setattr(si, "_query_coverage", _boom)
    monkeypatch.setattr(si, "_query_source_accuracy", _boom)
    monkeypatch.setattr(si, "_query_disagreements", _boom)
    monkeypatch.setattr(si, "_query_case_studies", _boom)


def _patch_redis(monkeypatch, fake):
    import app.tasks.redis_state as rs

    monkeypatch.setattr(rs, "get_redis_client", lambda *a, **k: fake)


def test_degenerate_helper_flags_all_empty_payload():
    assert si._is_degenerate_si(
        dict(si._EMPTY_COVERAGE), [], dict(si._EMPTY_DISAGREEMENTS), []
    )
    # A single non-empty component makes it non-degenerate.
    assert not si._is_degenerate_si(
        {"total_events": 5}, [], dict(si._EMPTY_DISAGREEMENTS), []
    )


def test_timeout_build_is_not_cached(monkeypatch):
    """All four queries time out → the empty result must NOT poison either cache."""
    _patch_queries_raise(monkeypatch)
    fake = _FakeRedis()
    _patch_redis(monkeypatch, fake)

    result = asyncio.run(si.source_intelligence(refresh=True, db=_FakeDB()))

    # The process-local cache stays empty (the poisoning bug would have set it).
    assert si._cache["data"] is None
    # Redis primary/stale keys were never written with the empty payload.
    assert si._REDIS_KEY not in fake.sets
    assert si._REDIS_STALE_KEY not in fake.sets
    # The degraded response is flagged so the caller knows it is not authoritative.
    assert result.get("degraded") is True


def test_serves_stale_process_snapshot_on_degraded_build(monkeypatch):
    """A prior good snapshot in the process cache is served (stale) rather than blank."""
    good = {
        "generated_at": "2026-07-15T00:00:00+00:00",
        "coverage": {"total_events": 42, "multi_source_events": 30,
                     "by_source_count": [], "by_sport": []},
        "source_accuracy": [{"source": "kalshi"}],
        "disagreements": dict(si._EMPTY_DISAGREEMENTS),
        "case_studies": [],
    }
    si._cache["data"] = good
    si._cache["timestamp"] = 1  # stale enough that refresh path rebuilds

    _patch_queries_raise(monkeypatch)
    fake = _FakeRedis()
    _patch_redis(monkeypatch, fake)

    result = asyncio.run(si.source_intelligence(refresh=True, db=_FakeDB()))

    assert result["coverage"]["total_events"] == 42
    assert result.get("stale") is True
    # The good snapshot survives — a degraded build never overwrites it.
    assert si._cache["data"]["coverage"]["total_events"] == 42


def test_serves_stale_redis_snapshot_when_no_process_cache(monkeypatch):
    """No process cache, but a Redis stale key exists → serve it stale, not blank."""
    import json

    good = {
        "generated_at": "2026-07-15T00:00:00+00:00",
        "coverage": {"total_events": 7, "multi_source_events": 4,
                     "by_source_count": [], "by_sport": []},
        "source_accuracy": [],
        "disagreements": dict(si._EMPTY_DISAGREEMENTS),
        "case_studies": [],
    }
    fake = _FakeRedis(seed={si._REDIS_STALE_KEY: json.dumps(good)})
    _patch_queries_raise(monkeypatch)
    _patch_redis(monkeypatch, fake)

    result = asyncio.run(si.source_intelligence(refresh=True, db=_FakeDB()))

    assert result["coverage"]["total_events"] == 7
    assert result.get("stale") is True
    # Still not cached into the process dict.
    assert si._cache["data"] is None


def test_healthy_build_is_cached_to_both_caches(monkeypatch):
    """A real (non-empty) build warms the process cache AND Redis primary+stale."""
    async def _cov(_db):
        return {"total_events": 100, "multi_source_events": 60,
                "by_source_count": [], "by_sport": []}

    async def _acc(_db):
        return [{"source": "kalshi", "mce": 3.1}]

    async def _dis(_db):
        return {"total_comparisons": 500, "rate_5pp": 0.4, "rate_10pp": 0.2,
                "rate_20pp": 0.1, "by_sport": [], "pairwise": []}

    async def _cases(_db):
        return [{"event_id": 1}]

    monkeypatch.setattr(si, "_query_coverage", _cov)
    monkeypatch.setattr(si, "_query_source_accuracy", _acc)
    monkeypatch.setattr(si, "_query_disagreements", _dis)
    monkeypatch.setattr(si, "_query_case_studies", _cases)
    fake = _FakeRedis()
    _patch_redis(monkeypatch, fake)

    result = asyncio.run(si.source_intelligence(refresh=True, db=_FakeDB()))

    assert result["coverage"]["total_events"] == 100
    assert result.get("degraded") is None and result.get("stale") is None
    assert si._cache["data"]["coverage"]["total_events"] == 100
    assert si._REDIS_KEY in fake.sets
    assert si._REDIS_STALE_KEY in fake.sets
