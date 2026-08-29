"""LAT-P128 — the event page rebuilt a grid the grid page had cached since #901.

``/api/events/{id}/related-futures`` ends by enriching its response with
``league_context``, which is the championship-progression grid for the event's
league. That grid has had a Redis key, a 3900 s TTL and a 24 h ``:stale``
fallback since #901. The event page did not read that key.
``_compute_league_context`` imported ``get_playoff_grid`` (the raw builder)
instead of ``get_playoff_grid_cached`` (the wrapper that owns the key), so every
miss of ``league_context``'s own 300 s Redis key paid a full inline grid
rebuild.

Measured on production, one sequence, three requests back to back
(2026-08-29T14:56:57Z). The key was warm on BOTH sides of the 21-second read:

    GET /api/playoffs/bundesliga              200   0.356 s  wall=20.7   q=0
    GET /api/events/14970280/related-futures  200  21.678 s  wall=21418  q=23
    GET /api/playoffs/bundesliga              200   0.329 s  wall=22.2   q=0
    GET /health                     (control)       0.241 s

And the A/B on ``league_context``'s own key — two events in the SAME league two
seconds apart, nothing changing but whether it was warm:

    14970283  league_context cold   28.667 s  wall=28396.9  db=28286.6  q=23
    14970280  league_context warm    2.170 s  wall=1913.0   db=1870.6   q=14

Nine extra queries and twenty-six extra seconds, for a payload that was already
sitting in Redis. ``q=23 - q=14 = 9`` is exactly the grid's own query count when
it rebuilds.

**The parameters were cache-eligible the whole time.** The wrapper caches when
``not debug and hours is None and top == 10``, and the call has always passed
exactly that triple. Nothing had to be made cacheable; the caller just had to
ask the function that reads the cache. That is what makes this class worth a
guard rather than a comment: *the call looked correct*. Both functions exist,
both are in the same module, both take the same arguments and return the same
shape, and only one of them is the one with the cache.

So the assertions below are about WIRING, not about latency:

* ``test_warm_grid_key_does_not_rebuild`` is load-bearing. The raw builder is
  replaced by a landmine. If anyone re-points this call at ``get_playoff_grid``
  the test does not get slower, it fails.
* ``test_call_is_cache_eligible`` pins the triple itself. A future edit that
  passes ``hours=24`` would keep every other test green while silently making
  the call ineligible — the defect would come back through the argument list
  rather than the import.
* ``test_json_roundtrip_context_matches_live_context`` is gotcha #1587's class.
  The wrapper stores ``json.dumps(result, default=str)``, so a warm read returns
  JSON-typed data and a cold read returns live Python objects. Both must build
  the SAME context, or the event page would show one thing warm and another
  cold.
* ``test_503_from_wrapper_degrades_to_none`` covers what the wrapper added: it
  can raise where the raw builder returned. A degraded side panel must not
  become a failed event page.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.services.league_context import (
    LeagueContext,
    _compute_league_context,
)

GRID_CACHE_KEY = "bainluck:category:playoffs:nba"


# A grid payload in the shape the NBA config produces: team rows carrying
# ``stages``. Probabilities are plain floats so the JSON round-trip below is a
# real test of the wiring and not of float formatting.
LIVE_GRID = {
    "columns": [
        {"key": "make_playoffs", "label": "Make Playoffs"},
        {"key": "championship", "label": "Champion"},
    ],
    "teams": [
        {
            "name": "Boston Celtics",
            "team_id": 1,
            "conference": "Eastern",
            "record": "64-18",
            "stages": [
                {
                    "key": "make_playoffs",
                    "probability": 0.98,
                    "trend_24h": 0.01,
                    "sources": [{"source": "kalshi"}, {"source": "polymarket"}],
                },
                {
                    "key": "championship",
                    "probability": 0.22,
                    "sources": [{"source": "kalshi"}],
                },
            ],
        },
    ],
}


def _redis_mock(values: dict):
    """The same shape ``test_playoff_grid_degradation`` uses, so the two files
    describe the wrapper's Redis contract the same way."""
    rc = MagicMock()
    rc.get = AsyncMock(side_effect=lambda key: values.get(key))
    rc.set = AsyncMock()
    rc.aclose = AsyncMock()
    return rc


def _landmine(*args, **kwargs):
    raise AssertionError(
        "get_playoff_grid (the RAW builder) was called while the grid cache key "
        "was warm. league_context must go through get_playoff_grid_cached — "
        "that is the entire LAT-P128 fix."
    )


class TestWarmGridKeyIsRead:
    @pytest.mark.asyncio
    async def test_warm_grid_key_does_not_rebuild(self):
        """The load-bearing one: a warm key means ZERO grid rebuilds."""
        rc = _redis_mock({GRID_CACHE_KEY: json.dumps(LIVE_GRID)})

        with patch(
            "app.tasks.redis_state.get_async_redis_client", return_value=rc
        ), patch("app.routes.playoffs.get_playoff_grid", side_effect=_landmine):
            ctx = await _compute_league_context("nba", db=MagicMock())

        assert ctx is not None
        assert ctx.league_slug == "nba"
        assert list(ctx.teams) == ["boston celtics"]
        assert ctx.teams["boston celtics"].cells == {
            "make_playoffs": 0.98,
            "championship": 0.22,
        }

    @pytest.mark.asyncio
    async def test_warm_key_read_twice_is_stable(self):
        """``_compute_league_context`` extends ``grid_data["teams"]`` in place on
        the grouped-teams path. A cached payload is re-parsed per call, so two
        reads of one warm key must not accumulate — pinned because the mutation
        is easy to miss and impossible to see from one call."""
        rc = _redis_mock({GRID_CACHE_KEY: json.dumps(LIVE_GRID)})

        with patch(
            "app.tasks.redis_state.get_async_redis_client", return_value=rc
        ), patch("app.routes.playoffs.get_playoff_grid", side_effect=_landmine):
            first = await _compute_league_context("nba", db=MagicMock())
            second = await _compute_league_context("nba", db=MagicMock())

        assert first is not None and second is not None
        assert list(first.teams) == list(second.teams)
        assert first.teams["boston celtics"].cells == second.teams["boston celtics"].cells


class TestCacheEligibility:
    @pytest.mark.asyncio
    async def test_call_is_cache_eligible(self):
        """Reading the cache is not enough — the arguments have to be the ones
        the wrapper is willing to cache. ``cache_eligible`` is
        ``not debug and hours is None and top == 10``; assert that triple at the
        call boundary so it cannot drift silently."""
        seen = {}

        async def _capture(league_slug=None, hours=None, top=None, debug=None, db=None):
            seen.update(
                league_slug=league_slug, hours=hours, top=top, debug=debug
            )
            return LIVE_GRID

        with patch("app.routes.playoffs.get_playoff_grid_cached", _capture):
            ctx = await _compute_league_context("nba", db=MagicMock())

        assert ctx is not None
        assert seen["league_slug"] == "nba"
        assert seen["hours"] is None
        assert seen["top"] == 10
        assert seen["debug"] is False
        # Restated as the wrapper itself spells it, so the link is explicit.
        assert (not seen["debug"]) and seen["hours"] is None and seen["top"] == 10

    @pytest.mark.asyncio
    async def test_cold_key_refills_the_shared_grid_cache(self):
        """A cold miss on the event page must leave the rebuilt grid where the
        grid PAGE will find it. Before LAT-P128 the event page could rebuild a
        grid and throw it away."""
        rc = _redis_mock({})

        async def _build(*args, **kwargs):
            return LIVE_GRID

        with patch(
            "app.tasks.redis_state.get_async_redis_client", return_value=rc
        ), patch("app.routes.playoffs.get_playoff_grid", side_effect=_build):
            ctx = await _compute_league_context("nba", db=MagicMock())

        assert ctx is not None
        written = {call.args[0] for call in rc.set.await_args_list}
        assert GRID_CACHE_KEY in written
        assert f"{GRID_CACHE_KEY}:stale" in written


class TestWarmAndColdAgree:
    @pytest.mark.asyncio
    async def test_json_roundtrip_context_matches_live_context(self):
        """Gotcha #1587's class, one layer up: the cache stores
        ``json.dumps(result, default=str)``, so warm and cold hand the SAME
        function different Python types. They must build the same context."""
        rc_cold = _redis_mock({})

        async def _build(*args, **kwargs):
            return LIVE_GRID

        with patch(
            "app.tasks.redis_state.get_async_redis_client", return_value=rc_cold
        ), patch("app.routes.playoffs.get_playoff_grid", side_effect=_build):
            cold = await _compute_league_context("nba", db=MagicMock())

        # Exactly what the wrapper persisted on that cold pass, read back.
        persisted = rc_cold.set.await_args_list[0].args[1]
        rc_warm = _redis_mock({GRID_CACHE_KEY: persisted})

        with patch(
            "app.tasks.redis_state.get_async_redis_client", return_value=rc_warm
        ), patch("app.routes.playoffs.get_playoff_grid", side_effect=_landmine):
            warm = await _compute_league_context("nba", db=MagicMock())

        assert cold is not None and warm is not None
        # Compare the OBJECTS' payload, not their JSON — `last_computed` is a
        # wall-clock stamp and is the one field that legitimately differs.
        cold_d = json.loads(cold.to_json())
        warm_d = json.loads(warm.to_json())
        cold_d.pop("last_computed", None)
        warm_d.pop("last_computed", None)
        assert cold_d == warm_d


class TestDegradation:
    @pytest.mark.asyncio
    async def test_503_from_wrapper_degrades_to_none(self):
        """The wrapper answers a timeout-with-no-last-good with 503. That is the
        right answer for the grid page and the wrong answer for an event page,
        so it degrades to `league_context: null` here."""

        async def _raise_503(*args, **kwargs):
            raise HTTPException(status_code=503, detail="degraded")

        with patch("app.routes.playoffs.get_playoff_grid_cached", _raise_503):
            assert await _compute_league_context("nba", db=MagicMock()) is None

    @pytest.mark.asyncio
    async def test_unknown_league_never_touches_the_grid(self):
        """The config lookup short-circuits before the import, so an unknown
        slug costs nothing at all."""
        with patch("app.routes.playoffs.get_playoff_grid_cached", _landmine), patch(
            "app.routes.playoffs.get_playoff_grid", side_effect=_landmine
        ):
            assert await _compute_league_context("not-a-league", db=MagicMock()) is None

    @pytest.mark.asyncio
    async def test_degraded_last_good_still_builds_a_context(self):
        """A labelled last-good payload carries `stale`/`degraded` markers the
        context builder does not read. It must still produce a context rather
        than tripping over the extra keys."""
        stale_payload = dict(LIVE_GRID, stale=True, stale_reason="cache_miss")
        rc = _redis_mock({GRID_CACHE_KEY: None, f"{GRID_CACHE_KEY}:stale": json.dumps(stale_payload)})

        with patch(
            "app.tasks.redis_state.get_async_redis_client", return_value=rc
        ), patch("app.routes.playoffs.get_playoff_grid", side_effect=_landmine):
            ctx = await _compute_league_context("nba", db=MagicMock())

        assert isinstance(ctx, LeagueContext)
        assert ctx.teams["boston celtics"].cells["championship"] == 0.22
