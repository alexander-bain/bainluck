"""#1484 — MLB grid bounded compute + truthful degradation.

Two defects lived behind one symptom ("MLB grid has 5 real defects (1 critical)"):

1. ``get_playoff_grid`` eager-loaded the outcomes of EVERY market matching the
   league's ticker/category filters before deciding which markets even belong to
   a grid column. In-season MLB matches every per-game Kalshi/Odds-API market, so
   the grid blew its request budget while the out-of-season NBA/NHL grids stayed
   cheap.
2. On timeout the endpoint returned ``200 + {"teams": [], "error": "timeout"}``
   — an empty grid that reads as a successful description of a league with no
   teams. The Grid Sentinel filed "ZERO teams" + four "missing column" defects:
   five REAL defects that were one timeout wearing a healthy costume.

These tests pin the fix in both directions: the degraded state must be
IMPOSSIBLE to mistake for healthy, and the healthy path must be unchanged.
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.routes.playoffs import (
    _grid_payload_usable,
    _load_outcomes_for_markets,
    _mark_last_good,
    get_playoff_grid_cached,
)
from app.tasks.grid_sentinel import (
    check_degraded_payload,
    check_teams_present,
    classify_findings,
    grid_verdict,
)


# ---------------------------------------------------------------------------
# Last-good validation
# ---------------------------------------------------------------------------
class TestGridPayloadUsable:
    def test_populated_grid_is_usable(self):
        assert _grid_payload_usable({"teams": [{"name": "Yankees"}]}) is True

    def test_empty_teams_is_not_usable(self):
        """An empty grid is never a usable fallback — serving one would
        re-create the exact failure this guard removes."""
        assert _grid_payload_usable({"teams": []}) is False

    def test_previously_cached_timeout_envelope_is_not_usable(self):
        assert _grid_payload_usable(
            {"teams": [], "columns": [], "error": "timeout"}
        ) is False

    def test_error_payload_with_teams_is_not_usable(self):
        assert _grid_payload_usable({"teams": [{"n": 1}], "error": "boom"}) is False

    @pytest.mark.parametrize("bad", [None, [], "grid", 7, {}, {"teams": None}])
    def test_non_grid_shapes_rejected(self, bad):
        assert _grid_payload_usable(bad) is False


class TestMarkLastGood:
    def test_marks_degraded_and_preserves_payload(self):
        payload = {"teams": [{"name": "Rays"}], "columns": [{"key": "championship"}]}
        marked = _mark_last_good(payload, "timeout")
        assert marked["degraded"] is True
        assert marked["degraded_reason"] == "timeout"
        assert marked["stale"] is True
        # Every original key survives byte-for-byte.
        assert marked["teams"] == [{"name": "Rays"}]
        assert marked["columns"] == [{"key": "championship"}]


# ---------------------------------------------------------------------------
# Endpoint behaviour on timeout
# ---------------------------------------------------------------------------
def _redis_mock(values: dict):
    rc = MagicMock()
    rc.get = AsyncMock(side_effect=lambda key: values.get(key))
    rc.set = AsyncMock()
    rc.aclose = AsyncMock()
    return rc


class TestTimeoutDegradation:
    """The load-bearing assertion: a timeout can never look healthy."""

    @pytest.mark.asyncio
    async def test_timeout_with_last_good_serves_labelled_payload(self):
        """The warm beat lands while a cold request is still building: both
        cache keys were cold on entry, so the request fell through to a live
        build, timed out, and only then found a last-good to serve."""
        import json

        good = {"teams": [{"name": "Dodgers"}], "columns": [{"key": "championship"}]}
        rc = MagicMock()
        # fresh -> None, stale (pre-build) -> None, stale (post-timeout) -> good
        rc.get = AsyncMock(side_effect=[None, None, json.dumps(good)])
        rc.set = AsyncMock()
        rc.aclose = AsyncMock()

        with patch("app.tasks.redis_state.get_async_redis_client", return_value=rc), \
             patch("asyncio.wait_for", side_effect=asyncio.TimeoutError):
            result = await get_playoff_grid_cached("mlb", None, 10, False, MagicMock())

        assert result["degraded"] is True
        assert result["degraded_reason"] == "timeout"
        assert result["teams"] == [{"name": "Dodgers"}]

    @pytest.mark.asyncio
    async def test_unusable_stale_falls_through_instead_of_being_served(self):
        """A cached empty/timeout envelope in the stale key must NOT be served
        as a 200 — it falls through to the live rebuild."""
        import json

        rc = MagicMock()
        rc.get = AsyncMock(side_effect=[
            None,                                                  # fresh: cold
            json.dumps({"teams": [], "error": "timeout"}),          # stale: junk
        ])
        rc.set = AsyncMock()
        rc.aclose = AsyncMock()
        built = {"teams": [{"name": "Padres"}], "columns": []}

        async def _build(*a, **kw):
            return built

        with patch("app.tasks.redis_state.get_async_redis_client", return_value=rc), \
             patch("app.routes.playoffs.get_playoff_grid", side_effect=_build):
            result = await get_playoff_grid_cached("mlb", None, 10, False, MagicMock())

        assert result == built
        assert "degraded" not in result

    @pytest.mark.asyncio
    async def test_timeout_without_last_good_raises_503(self):
        """No last-good means we have nothing true to say. A non-success status
        is the only honest answer — NOT 200 with an empty team list."""
        rc = _redis_mock({})

        with patch("app.tasks.redis_state.get_async_redis_client", return_value=rc), \
             patch("asyncio.wait_for", side_effect=asyncio.TimeoutError):
            with pytest.raises(HTTPException) as exc:
                await get_playoff_grid_cached("mlb", None, 10, False, MagicMock())

        assert exc.value.status_code == 503
        assert "degraded" in str(exc.value.detail).lower()

    @pytest.mark.asyncio
    async def test_timeout_rejects_an_empty_last_good(self):
        """A previously-cached empty/timeout payload must not be resurrected as
        'last good' — that would launder the failure into a 200."""
        import json

        junk = json.dumps({"teams": [], "columns": [], "error": "timeout"})
        rc = MagicMock()
        rc.get = AsyncMock(side_effect=[None, junk, junk])
        rc.set = AsyncMock()
        rc.aclose = AsyncMock()

        with patch("app.tasks.redis_state.get_async_redis_client", return_value=rc), \
             patch("asyncio.wait_for", side_effect=asyncio.TimeoutError):
            with pytest.raises(HTTPException) as exc:
                await get_playoff_grid_cached("mlb", None, 10, False, MagicMock())

        assert exc.value.status_code == 503

    @pytest.mark.asyncio
    async def test_fresh_cache_hit_is_not_labelled_degraded(self):
        """Adjacent-direction guard: the healthy path is untouched."""
        import json

        good = {"teams": [{"name": "Knicks"}], "columns": []}
        rc = _redis_mock({"bainluck:category:playoffs:nba": json.dumps(good)})

        with patch("app.tasks.redis_state.get_async_redis_client", return_value=rc):
            result = await get_playoff_grid_cached("nba", None, 10, False, MagicMock())

        assert result == good
        assert "degraded" not in result

    @pytest.mark.asyncio
    async def test_stale_fallback_is_labelled(self):
        """Serving last-good when the fresh key is cold is correct — serving it
        UNLABELLED is what made a stale grid indistinguishable from a fresh one."""
        import json

        good = {"teams": [{"name": "Oilers"}], "columns": []}
        rc = _redis_mock({"bainluck:category:playoffs:nhl:stale": json.dumps(good)})

        with patch("app.tasks.redis_state.get_async_redis_client", return_value=rc):
            result = await get_playoff_grid_cached("nhl", None, 10, False, MagicMock())

        assert result["degraded"] is True
        assert result["degraded_reason"] == "cache_miss"
        assert result["teams"] == [{"name": "Oilers"}]

    @pytest.mark.asyncio
    async def test_live_build_writes_both_cache_keys(self):
        import json

        built = {"teams": [{"name": "Astros"}], "columns": []}
        rc = _redis_mock({})

        async def _build(*a, **kw):
            return built

        with patch("app.tasks.redis_state.get_async_redis_client", return_value=rc), \
             patch("app.routes.playoffs.get_playoff_grid", side_effect=_build):
            result = await get_playoff_grid_cached("mlb", None, 10, False, MagicMock())

        assert result == built
        written = {c.args[0] for c in rc.set.await_args_list}
        assert "bainluck:category:playoffs:mlb" in written
        assert "bainluck:category:playoffs:mlb:stale" in written
        cached = json.loads(rc.set.await_args_list[0].args[1])
        assert cached["teams"] == [{"name": "Astros"}]


# ---------------------------------------------------------------------------
# Bounded outcome load
# ---------------------------------------------------------------------------
class TestBoundedOutcomeLoad:
    @pytest.mark.asyncio
    async def test_no_ids_issues_no_query(self):
        session = MagicMock()
        session.execute = AsyncMock()
        assert await _load_outcomes_for_markets(session, []) == {}
        session.execute.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_groups_outcomes_by_market(self):
        outcomes = [
            SimpleNamespace(id=1, market_id=10),
            SimpleNamespace(id=2, market_id=10),
            SimpleNamespace(id=3, market_id=11),
        ]
        result_obj = MagicMock()
        result_obj.scalars.return_value.all.return_value = outcomes
        session = MagicMock()
        session.execute = AsyncMock(return_value=result_obj)

        grouped = await _load_outcomes_for_markets(session, [10, 11])
        assert [o.id for o in grouped[10]] == [1, 2]
        assert [o.id for o in grouped[11]] == [3]
        # Absent markets return an empty tuple via .get(mid, ())
        assert grouped.get(99, ()) == ()

    @pytest.mark.asyncio
    async def test_only_requested_markets_are_queried(self):
        """The whole point of #1484: outcomes are fetched for column-matched
        markets ONLY, never for the thousands of in-season game markets that
        share MLB's ticker prefix."""
        result_obj = MagicMock()
        result_obj.scalars.return_value.all.return_value = []
        session = MagicMock()
        session.execute = AsyncMock(return_value=result_obj)

        await _load_outcomes_for_markets(session, [5, 5, 7])
        assert session.execute.await_count == 1

    @pytest.mark.asyncio
    async def test_batches_large_id_lists(self):
        from app.routes.playoffs import _OUTCOME_FETCH_BATCH

        result_obj = MagicMock()
        result_obj.scalars.return_value.all.return_value = []
        session = MagicMock()
        session.execute = AsyncMock(return_value=result_obj)

        ids = list(range(_OUTCOME_FETCH_BATCH * 2 + 3))
        await _load_outcomes_for_markets(session, ids)
        assert session.execute.await_count == 3


# ---------------------------------------------------------------------------
# Grid Sentinel classification of the degraded payload
# ---------------------------------------------------------------------------
class TestGridSentinelDegradedClassification:
    def test_degraded_payload_is_one_real_critical(self):
        findings = check_degraded_payload(
            {"degraded": True, "degraded_reason": "timeout", "teams": []}, "mlb"
        )
        assert len(findings) == 1
        assert findings[0]["check"] == "grid_degraded"
        assert findings[0]["severity"] == "critical"
        assert findings[0]["seasonal_ok"] is False
        assert "timeout" in findings[0]["detail"]

    def test_healthy_payload_emits_nothing(self):
        assert check_degraded_payload({"teams": [{"name": "Mets"}]}, "mlb") == []

    def test_degraded_never_gets_seasonally_excused(self):
        """A degraded measurement is RED in every season — the calendar cannot
        explain a build that did not complete."""
        findings = check_degraded_payload(
            {"degraded": True, "degraded_reason": "timeout"}, "nba"
        )
        classified = classify_findings(findings, "nba")
        assert classified["real"], "degraded must classify REAL, not explained"
        assert grid_verdict(classified) == "red"

    def test_degraded_replaces_the_derived_zero_teams_story(self):
        """Before: five defects describing the fallback's shape. After: one
        defect naming the cause. Both are RED — only one is true."""
        payload = {"degraded": True, "degraded_reason": "timeout", "teams": []}
        derived = check_teams_present(payload, "mlb")
        assert derived and derived[0]["check"] == "grid_empty"
        degraded = check_degraded_payload(payload, "mlb")
        assert degraded[0]["check"] == "grid_degraded"
        assert "ZERO teams" not in degraded[0]["detail"]
