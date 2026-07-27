"""Queue #263 Item 3 — the fair-fight ROUTE must never serve a legacy winner cache.

Queue #262 removed the winner claim from the fair-fight TASK output, but the route
served whatever sat in ``bainluck:calibration:fair_fight`` verbatim. A cache written
before the containment (a legacy ``winner``/``advantage_pp``/``shared_markets``
payload) — or a version-mismatched / malformed one — would still be served as a
source ranking. #263 validates the cache against the current population/schema
contract before serving and FAILS CLOSED to "computing" otherwise.

Pure-function tests on the validator + a direct call of the route coroutine with a
seeded fake Redis (the route reads Redis only; ``db`` is unused)."""

import json

import pytest

from app.routes.source_intelligence import (
    _fair_fight_cache_is_current,
    fair_fight_comparison,
)
from app.tasks.precompute_calibration import CALIBRATION_POPULATION_VERSION

_V = CALIBRATION_POPULATION_VERSION


def _current_payload(pairs=None):
    """The contained, current-shape payload the task writes today."""
    return {
        "generated_at": "2026-01-01T00:00:00+00:00",
        "comparison_available": False,
        "unavailable_reason": "winner withheld",
        "population_version": _V,
        "methodology": "Diagnostic per-source MCE only.",
        "min_shared_threshold": 100,
        "pairs": pairs if pairs is not None else [
            {"source_a": "kalshi", "source_b": "polymarket",
             "comparison_available": False, "reason": "not paired",
             "mce_a": 3.1, "mce_b": 4.2, "kalshi_rows": 900, "polymarket_rows": 800},
        ],
    }


def _legacy_winner_payload():
    """The pre-containment shape: a source ranking with winner grammar."""
    return {
        "generated_at": "2025-06-01T00:00:00+00:00",
        "min_shared_threshold": 100,
        "pairs": [
            {"source_a": "kalshi", "source_b": "polymarket",
             "winner": "kalshi", "advantage_pp": 2.4, "shared_markets": 850,
             "mce_a": 3.1, "mce_b": 5.5},
        ],
    }


class TestValidatorContract:
    def test_current_unavailable_payload_passes(self):
        assert _fair_fight_cache_is_current(_current_payload()) is True

    def test_legacy_winner_payload_fails_closed(self):
        assert _fair_fight_cache_is_current(_legacy_winner_payload()) is False

    def test_top_level_comparison_available_true_fails(self):
        p = _current_payload()
        p["comparison_available"] = True
        assert _fair_fight_cache_is_current(p) is False

    def test_version_mismatch_fails_closed(self):
        p = _current_payload()
        p["population_version"] = "q262"
        assert _fair_fight_cache_is_current(p) is False

    def test_missing_version_fails_closed(self):
        p = _current_payload()
        del p["population_version"]
        assert _fair_fight_cache_is_current(p) is False

    @pytest.mark.parametrize("banned", ["winner", "advantage_pp", "shared_markets"])
    def test_any_pair_winner_grammar_fails(self, banned):
        p = _current_payload()
        p["pairs"][0][banned] = "x"
        assert _fair_fight_cache_is_current(p) is False

    def test_malformed_shapes_fail_closed(self):
        assert _fair_fight_cache_is_current(None) is False
        assert _fair_fight_cache_is_current([]) is False
        assert _fair_fight_cache_is_current("nope") is False
        bad_pairs = _current_payload()
        bad_pairs["pairs"] = "not a list"
        assert _fair_fight_cache_is_current(bad_pairs) is False
        bad_pair = _current_payload()
        bad_pair["pairs"] = ["not a dict"]
        assert _fair_fight_cache_is_current(bad_pair) is False


class _FakeRedis:
    def __init__(self, value):
        self._value = value

    def get(self, key):
        return self._value


@pytest.mark.asyncio
class TestRouteContainment:
    async def _call_with_cache(self, monkeypatch, cache_value):
        import app.tasks.redis_state as redis_state

        monkeypatch.setattr(
            redis_state, "get_redis_client",
            lambda *a, **k: _FakeRedis(cache_value),
        )
        return await fair_fight_comparison(db=None)

    async def test_serves_current_payload(self, monkeypatch):
        payload = _current_payload()
        result = await self._call_with_cache(monkeypatch, json.dumps(payload))
        assert result["comparison_available"] is False
        assert result["population_version"] == _V

    async def test_legacy_winner_cache_returns_computing(self, monkeypatch):
        result = await self._call_with_cache(
            monkeypatch, json.dumps(_legacy_winner_payload())
        )
        assert result.get("status") == "computing"
        # No winner grammar leaks into the served response.
        assert "winner" not in result
        assert "advantage_pp" not in result
        assert "shared_markets" not in result

    async def test_version_mismatch_cache_returns_computing(self, monkeypatch):
        p = _current_payload()
        p["population_version"] = "q262"
        result = await self._call_with_cache(monkeypatch, json.dumps(p))
        assert result.get("status") == "computing"

    async def test_missing_cache_returns_computing(self, monkeypatch):
        result = await self._call_with_cache(monkeypatch, None)
        assert result.get("status") == "computing"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
