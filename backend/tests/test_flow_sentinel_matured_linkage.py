"""Guard tests for the Flow Sentinel matured-linkage flow (Queue #220/221 Item 2).

The flow reads the precomputed matured-linkage payload from Redis and files each
phantom blend source as an (event, source) pair. These assert: it is registered
(runner + title + area label), a clean payload passes, phantoms fail with
(event, source) detail, and a cold/insufficient cache skips rather than fails.
"""

import importlib

import pytest

fs = importlib.import_module("app.tasks.flow_sentinel")


class _FakeRedis:
    def __init__(self, value):
        self._value = value

    def get(self, key):
        return self._value


def _patch_redis(monkeypatch, payload):
    import json

    raw = json.dumps(payload) if payload is not None else None

    def _fake_get_client(*a, **k):
        return _FakeRedis(raw)

    monkeypatch.setattr("app.tasks.redis_state.get_redis_client", _fake_get_client)


class TestRegistration:
    def test_flow_has_title_and_area_label(self):
        assert "matured_linkage" in fs._FLOW_TITLES
        assert fs._FLOW_AREA_LABELS["matured_linkage"] == "area:event-details"

    def test_runner_registered_in_sentinel(self):
        import inspect

        src = inspect.getsource(fs._run_flow_sentinel)
        assert '"matured_linkage", _run_matured_linkage' in src


class TestRunner:
    @pytest.mark.asyncio
    async def test_clean_payload_passes(self, monkeypatch):
        _patch_redis(monkeypatch, {
            "status": "ok", "checkable_pairs": 5, "backed": 5, "phantom": 0,
            "headline_pct": 100.0, "misses": [], "by_source": {},
            "events_checked": 4, "events_consistent": 4, "window": "NOW-6h..NOW+24h",
        })
        out = await fs._run_matured_linkage(None)
        assert out["passed"] is True
        assert out["failures"] == []
        assert out["checked"] == 5

    @pytest.mark.asyncio
    async def test_phantom_fails_with_event_source_pair(self, monkeypatch):
        _patch_redis(monkeypatch, {
            "status": "ok", "checkable_pairs": 3, "backed": 2, "phantom": 1,
            "headline_pct": 66.7,
            "misses": [{"event_id": 42, "source": "kalshi",
                        "sport": "baseball_mlb", "matchup": "A @ B"}],
            "by_source": {}, "events_checked": 3, "events_consistent": 2,
            "window": "NOW-6h..NOW+24h",
        })
        out = await fs._run_matured_linkage(None)
        assert out["passed"] is False
        assert len(out["failures"]) == 1
        f = out["failures"][0]
        assert f["event_id"] == 42 and f["source"] == "kalshi"
        assert "phantom blend source" in f["detail"]

    @pytest.mark.asyncio
    async def test_insufficient_slate_skips(self, monkeypatch):
        _patch_redis(monkeypatch, {"status": "insufficient_slate", "misses": []})
        out = await fs._run_matured_linkage(None)
        assert out["passed"] is True
        assert out.get("skipped") is True

    @pytest.mark.asyncio
    async def test_cold_cache_skips(self, monkeypatch):
        _patch_redis(monkeypatch, None)
        out = await fs._run_matured_linkage(None)
        assert out["passed"] is True
        assert out.get("skipped") is True
