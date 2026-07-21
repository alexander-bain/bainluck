"""Guard tests for the Flow Sentinel unlinked-held flow (Queue #223 Item 4).

The flow reads the ``unlinked_held`` block of the precomputed matured-linkage
payload from Redis and files each matcher-missed link (a game-winner market we hold,
unlinked, whose both teams match an imminent event). These assert it is registered,
a clean block passes, misses fail with (event, source, market) detail, and a
cold/insufficient cache skips rather than fails."""

import importlib

import pytest

fs = importlib.import_module("app.tasks.flow_sentinel")


class _FakeRedis:
    def __init__(self, value):
        self._value = value

    def get(self, key):
        return self._value


def _patch_redis(monkeypatch, full_payload):
    import json

    raw = json.dumps(full_payload) if full_payload is not None else None

    def _fake_get_client(*a, **k):
        return _FakeRedis(raw)

    monkeypatch.setattr("app.tasks.redis_state.get_redis_client", _fake_get_client)


class TestRegistration:
    def test_flow_has_title_and_area_label(self):
        assert "unlinked_held" in fs._FLOW_TITLES
        assert fs._FLOW_AREA_LABELS["unlinked_held"] == "area:event-details"

    def test_runner_registered_in_sentinel(self):
        import inspect

        src = inspect.getsource(fs._run_flow_sentinel)
        assert '"unlinked_held", _run_unlinked_held' in src


class TestRunner:
    @pytest.mark.asyncio
    async def test_clean_block_passes(self, monkeypatch):
        _patch_redis(monkeypatch, {
            "status": "ok",
            "unlinked_held": {
                "status": "ok", "headline_unlinked_held": 0, "events_checked": 4,
                "candidates_scanned": 120, "misses": [], "by_source": {},
            },
        })
        out = await fs._run_unlinked_held(None)
        assert out["passed"] is True
        assert out["failures"] == []
        assert out["checked"] == 120

    @pytest.mark.asyncio
    async def test_miss_fails_with_market_detail(self, monkeypatch):
        _patch_redis(monkeypatch, {
            "status": "ok",
            "unlinked_held": {
                "status": "ok", "headline_unlinked_held": 1, "events_checked": 3,
                "candidates_scanned": 90,
                "misses": [{
                    "event_id": 77, "source": "kalshi", "sport": "baseball_mlb",
                    "matchup": "Rays @ Red Sox", "market_id": 12345,
                    "market_name": "Rays vs Red Sox",
                }],
                "by_source": {"kalshi": 1},
            },
        })
        out = await fs._run_unlinked_held(None)
        assert out["passed"] is False
        assert len(out["failures"]) == 1
        f = out["failures"][0]
        assert f["event_id"] == 77 and f["source"] == "kalshi"
        assert "matcher miss" in f["detail"] and "12345" in f["detail"]

    @pytest.mark.asyncio
    async def test_insufficient_slate_skips(self, monkeypatch):
        _patch_redis(monkeypatch, {"status": "ok", "unlinked_held": {"status": "insufficient_slate"}})
        out = await fs._run_unlinked_held(None)
        assert out["passed"] is True and out.get("skipped") is True

    @pytest.mark.asyncio
    async def test_cold_cache_skips(self, monkeypatch):
        _patch_redis(monkeypatch, None)
        out = await fs._run_unlinked_held(None)
        assert out["passed"] is True and out.get("skipped") is True

    @pytest.mark.asyncio
    async def test_missing_block_skips(self, monkeypatch):
        # matured-linkage payload present but no unlinked_held block yet (pre-deploy).
        _patch_redis(monkeypatch, {"status": "ok", "headline_pct": 100.0})
        out = await fs._run_unlinked_held(None)
        assert out["passed"] is True and out.get("skipped") is True
