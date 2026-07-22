"""#237 Item 1 — GET /api/admin/ops-snapshot payload-shape guard.

The ops-snapshot digest composes only warm sources (Redis keys + task-metrics +
quota) so an ops round is 1-2 calls instead of ~20, and it must never 500 on a
cold cache — each field degrades to a status object. These guards assert the
compaction helper and the full payload shape (all sections present) even when
every underlying source is empty.
"""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.routes.admin import _ops_compact


class TestOpsCompact:
    def test_scalars_kept_verbatim(self):
        out = _ops_compact({"generated_at": "2026-07-22T00:00:00Z", "status": "green", "n": 3, "ok": True})
        assert out == {"generated_at": "2026-07-22T00:00:00Z", "status": "green", "n": 3, "ok": True}

    def test_lists_become_counts(self):
        out = _ops_compact({"failures": [1, 2, 3], "generated_at": "x"})
        assert out == {"failures_count": 3, "generated_at": "x"}

    def test_nested_dicts_dropped(self):
        out = _ops_compact({"a": 1, "nested": {"deep": 2}})
        assert out == {"a": 1}

    def test_non_dict_is_no_run_cached(self):
        assert _ops_compact(None) == {"status": "no_run_cached"}
        assert _ops_compact("garbage") == {"status": "no_run_cached"}


@pytest.mark.asyncio
async def test_ops_snapshot_shape_with_empty_sources(monkeypatch):
    """Every source cold → snapshot still returns with all sections, no exception."""
    import app.routes.admin as admin_mod
    import app.tasks.redis_state as rs

    # Bypass admin auth.
    monkeypatch.setattr(admin_mod, "_check_admin_secret", lambda *a, **k: True)
    # Reset the in-process cache so we compute fresh.
    admin_mod._OPS_SNAPSHOT_CACHE["at"] = 0.0
    admin_mod._OPS_SNAPSHOT_CACHE["data"] = None

    fake_redis = MagicMock()
    fake_redis.get.return_value = None       # every cached key cold
    fake_redis.llen.return_value = 0
    monkeypatch.setattr(rs, "get_redis_client", lambda *a, **k: fake_redis)
    monkeypatch.setattr(rs, "get_task_metrics", lambda label: {"health": "no_data"})
    monkeypatch.setattr(rs, "get_all_task_metrics", lambda: [])
    monkeypatch.setattr(rs, "get_odds_api_quota", lambda: {"status": "no_data"})

    resp = await admin_mod.get_ops_snapshot(request=MagicMock(), secret="x", fresh=True)

    for key in (
        "generated_at", "link_rate", "matured_linkage", "coverage",
        "cal_beat", "time_horizon", "sentinels", "quota", "sentry", "celery",
    ):
        assert key in resp, f"missing section: {key}"
    assert set(resp["sentinels"].keys()) == {"flow", "calibration", "grid"}
    assert set(resp["coverage"].keys()) == {"poll_kalshi", "poll_polymarket"}
    assert resp["celery"]["queue_depths"] == {"background": 0, "realtime": 0, "heavy": 0}
    assert resp["cache"] == "miss"


class TestSentrySnapshotBuckets:
    """gotcha #49: rank by summed 24h stat buckets, never the lifetime `count`."""

    def test_sums_bucket_counts(self):
        from app.tasks.sentry_snapshot import _sum_24h_buckets
        assert _sum_24h_buckets([[1000, 4], [2000, 6], [3000, 2]]) == 12

    def test_non_list_is_zero(self):
        from app.tasks.sentry_snapshot import _sum_24h_buckets
        assert _sum_24h_buckets(None) == 0
        assert _sum_24h_buckets({}) == 0

    def test_malformed_buckets_skipped(self):
        from app.tasks.sentry_snapshot import _sum_24h_buckets
        assert _sum_24h_buckets([[1000, 4], ["bad"], [2000, "x"], [3000, 3]]) == 7


@pytest.mark.asyncio
async def test_sentry_snapshot_no_token_degrades(monkeypatch):
    """No SENTRY_AUTH_TOKEN → writes a no_token status, never raises, never HTTPs."""
    import app.tasks.sentry_snapshot as ss

    monkeypatch.delenv("SENTRY_AUTH_TOKEN", raising=False)
    written = {}
    monkeypatch.setattr(ss, "_write", lambda payload: written.update(payload))

    result = await ss._run_sentry_snapshot()
    assert result["status"] == "no_token"
    assert result["issues"] == []
    assert "generated_at" in result
    assert written["status"] == "no_token"


@pytest.mark.asyncio
async def test_ops_snapshot_reads_warm_keys(monkeypatch):
    """Warm sentinel + sentry keys flow through to the compact digest."""
    import app.routes.admin as admin_mod
    import app.tasks.redis_state as rs

    monkeypatch.setattr(admin_mod, "_check_admin_secret", lambda *a, **k: True)
    admin_mod._OPS_SNAPSHOT_CACHE["at"] = 0.0
    admin_mod._OPS_SNAPSHOT_CACHE["data"] = None

    warm = {
        "bainluck:flow_sentinel:last": {"status": "green", "generated_at": "2026-07-22T07:10:00Z", "failures": []},
        "bainluck:sentry:top_24h": {"status": "ok", "total_24h": 12, "issues": [{"short_id": "X-1", "count_24h": 12}]},
    }
    fake_redis = MagicMock()
    fake_redis.get.side_effect = lambda k: json.dumps(warm[k]) if k in warm else None
    fake_redis.llen.return_value = 3
    monkeypatch.setattr(rs, "get_redis_client", lambda *a, **k: fake_redis)
    monkeypatch.setattr(rs, "get_task_metrics", lambda label: {"health": "healthy", "successes_24h": 5})
    monkeypatch.setattr(rs, "get_all_task_metrics", lambda: [{"health": "healthy"}, {"health": "degraded"}])
    monkeypatch.setattr(rs, "get_odds_api_quota", lambda: {"remaining": 4_000_000, "health": "healthy"})

    resp = await admin_mod.get_ops_snapshot(request=MagicMock(), secret="x", fresh=True)

    assert resp["sentinels"]["flow"]["status"] == "green"
    assert resp["sentinels"]["flow"]["failures_count"] == 0
    assert resp["sentry"]["total_24h"] == 12
    assert resp["quota"]["remaining"] == 4_000_000
    assert resp["celery"]["task_health"] == {"healthy": 1, "degraded": 1}
    assert resp["cal_beat"]["health"] == "healthy"
