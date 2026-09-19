"""#7109 — a lapsed playoff-grid cache key stops being self-sustaining.

THE DEFECT, MEASURED ON PRODUCTION 2026-09-19.

`/api/playoffs/mlb` served a payload built at 00:26:33Z for 3 h 24 m while
nhl/nba/nfl warmed inside one 18-second window at 02:25Z. The reader's
Championship Path read Division 1% / AL Champ 1% / World Series 1% — the exact
defect #7076 had already fixed and verified, with the cache-bypassing door
serving 1% / 12% / 5% — plus 22 of 30 MLB team records a game behind.

The mechanism is not a slow grid and not a cold cache. `get_playoff_grid_cached`
finds the 3900 s fresh key cold, finds the 24 h `:stale` mirror usable, serves it
and STOPS: it rebuilds nothing and rewrites neither key. So the only thing that
can end the lapse is `precompute_category_pages`, which owns both writes — and
when that beat cannot warm a league (mlb: `outcome=timeout duration_s=89.4`
against a `timeout_s=66.1`), the lapse sustains itself until the mirror expires a
day later. A correct, merged, released fix could not reach the page.

WHAT THESE TESTS PIN, AND WHY EACH ONE EXISTS.

Every test drives the REAL functions and asserts on BEHAVIOUR — whether a
rebuild ran, what was published, whether the reader waited. None assert on
source text: a guard that reads the source stays green when the function stops
doing the thing, and the whole value of this change is in *when* the rebuild
runs.

1. **A last-good serve now schedules a rebuild.** This is the ship, and it is
   the assertion that fails on the pre-#7109 tree.
2. **The reader still gets the stale payload, unchanged, on this request.** The
   repair must not turn a fast stale serve into a slow fresh one; `stale`,
   `stale_reason` and the absence of `degraded` are the #1484 contract and are
   not this change's to move.
3. **The rebuild publishes BOTH keys.** Republishing only the fresh key would
   leave the mirror ageing out on its original 24 h clock, which is half a fix
   that looks whole.
4. **An empty build publishes NOTHING.** This writer owns the 24 h mirror, so a
   transiently empty build must not replace a working grid with one the route
   then refuses as a fallback — that converts a healthy page into a live
   rebuild, which for a league like NFL is the 503.
5. **A fresh-key hit schedules nothing.** The refresh is the lapse's repair, not
   a second warmer running on every read.
6. **A dispatch that fails leaves the reader's serve intact.** The payload is
   already in hand; a refresh that cannot start must never become a 500.
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.routes import events as ev
from app.routes import playoffs as pg


GOOD = {"teams": [{"name": "Red Sox"}], "columns": [{"key": "championship"}]}
REBUILT = {"teams": [{"name": "Red Sox"}, {"name": "Rays"}], "columns": []}
EMPTY = {"teams": [], "columns": []}


@pytest.fixture(autouse=True)
def _clear_inflight():
    """The in-flight set is process-global; a leaked name silently disables the
    refresh for every later test and they would all still pass."""
    ev._STALE_REFRESH_INFLIGHT.discard("playoff_grid:mlb")
    yield
    ev._STALE_REFRESH_INFLIGHT.discard("playoff_grid:mlb")


def _redis_mock(values: dict):
    rc = MagicMock()
    rc.get = AsyncMock(side_effect=lambda key: values.get(key))
    rc.set = AsyncMock()
    rc.aclose = AsyncMock()
    return rc


def _session_maker_mock():
    """`async with async_session_maker() as session` — nothing more is used."""
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=MagicMock())
    cm.__aexit__ = AsyncMock(return_value=False)
    return MagicMock(return_value=cm)


# ---------------------------------------------------------------------------
# 1 + 2 — the ship, and the reader who must not pay for it
# ---------------------------------------------------------------------------
class TestLastGoodServeSchedulesARebuild:
    async def test_cache_miss_serve_schedules_a_rebuild(self):
        """FAILS ON THE PRE-#7109 TREE: the branch served and returned, so
        `calls` stayed empty and the lapse could only be ended by the beat."""
        calls = []

        async def _fake_rebuild(slug):
            calls.append(slug)

        rc = _redis_mock({"bainluck:category:playoffs:mlb:stale": json.dumps(GOOD)})

        with patch("app.tasks.redis_state.get_async_redis_client", return_value=rc), \
             patch.object(pg, "_rebuild_playoff_grid", _fake_rebuild):
            result = await pg.get_playoff_grid_cached("mlb", None, 10, False, MagicMock())
            # Let the scheduled task reach its first line. The reader did not
            # await this — that is property 2, asserted below.
            await asyncio.sleep(0)
            await asyncio.sleep(0)

        assert calls == ["mlb"], (
            "a last-good serve must refresh behind itself; without this the "
            "lapsed key is self-sustaining for the mirror's full 24h"
        )
        # Property 2: the reader's payload is the stale one, untouched.
        assert result["teams"] == GOOD["teams"]
        assert result["stale"] is True
        assert result["stale_reason"] == "cache_miss"
        assert "degraded" not in result, (
            "#1484: a routine between-warms serve is not a failure"
        )

    async def test_second_reader_in_the_same_lapse_does_not_stampede(self):
        """Without the in-flight guard a burst of readers arriving in the same
        expired millisecond each launch their own 6 s grid build."""
        calls = []

        async def _slow_rebuild(slug):
            calls.append(slug)
            await asyncio.sleep(0.05)

        rc = _redis_mock({"bainluck:category:playoffs:mlb:stale": json.dumps(GOOD)})

        with patch("app.tasks.redis_state.get_async_redis_client", return_value=rc), \
             patch.object(pg, "_rebuild_playoff_grid", _slow_rebuild):
            for _ in range(5):
                await pg.get_playoff_grid_cached("mlb", None, 10, False, MagicMock())
            await asyncio.sleep(0)

        assert calls == ["mlb"], f"expected one rebuild for five readers, got {calls}"


# ---------------------------------------------------------------------------
# 3 + 4 — what the rebuild is allowed to publish
# ---------------------------------------------------------------------------
class TestRebuildPublish:
    async def test_publishes_both_keys(self):
        rc = _redis_mock({})

        with patch.object(pg, "get_playoff_grid", AsyncMock(return_value=REBUILT)), \
             patch("app.services.database.async_session_maker", _session_maker_mock()), \
             patch("app.tasks.redis_state.get_async_redis_client", return_value=rc):
            await pg._rebuild_playoff_grid("mlb")

        written = {c.args[0]: c for c in rc.set.await_args_list}
        assert set(written) == {
            "bainluck:category:playoffs:mlb",
            "bainluck:category:playoffs:mlb:stale",
        }, (
            "republishing only the fresh key leaves the mirror ageing out on its "
            "original clock — half a fix that looks whole"
        )
        fresh = written["bainluck:category:playoffs:mlb"]
        assert json.loads(fresh.args[1])["teams"] == REBUILT["teams"]
        assert fresh.kwargs["ex"] == 3900
        assert written["bainluck:category:playoffs:mlb:stale"].kwargs["ex"] == 86400

    async def test_an_empty_build_publishes_nothing(self):
        """The load-bearing one. This writer owns the 24h mirror, so publishing
        an empty build removes the fallback the route falls back to."""
        rc = _redis_mock({})

        with patch.object(pg, "get_playoff_grid", AsyncMock(return_value=EMPTY)), \
             patch("app.services.database.async_session_maker", _session_maker_mock()), \
             patch("app.tasks.redis_state.get_async_redis_client", return_value=rc):
            await pg._rebuild_playoff_grid("mlb")

        assert rc.set.await_count == 0, (
            "an empty build must never replace a working grid: the route would "
            "then refuse the mirror and fall through to a live rebuild"
        )

    async def test_the_rebuild_is_bounded(self):
        """A rebuild with no wall is a background job that can outlive the
        lapse it was repairing."""
        async def _never_returns(*a, **k):
            await asyncio.sleep(3600)

        rc = _redis_mock({})

        with patch.object(pg, "GRID_REFRESH_BEHIND_TIMEOUT_S", 0.01), \
             patch.object(pg, "get_playoff_grid", _never_returns), \
             patch("app.services.database.async_session_maker", _session_maker_mock()), \
             patch("app.tasks.redis_state.get_async_redis_client", return_value=rc):
            with pytest.raises(asyncio.TimeoutError):
                await pg._rebuild_playoff_grid("mlb")

        assert rc.set.await_count == 0


# ---------------------------------------------------------------------------
# 5 + 6 — where the refresh must NOT fire, and what it must not break
# ---------------------------------------------------------------------------
class TestTheRefreshStaysInItsLane:
    async def test_a_fresh_key_hit_schedules_nothing(self):
        calls = []

        async def _fake_rebuild(slug):
            calls.append(slug)

        rc = _redis_mock({"bainluck:category:playoffs:mlb": json.dumps(GOOD)})

        with patch("app.tasks.redis_state.get_async_redis_client", return_value=rc), \
             patch.object(pg, "_rebuild_playoff_grid", _fake_rebuild):
            result = await pg.get_playoff_grid_cached("mlb", None, 10, False, MagicMock())
            await asyncio.sleep(0)

        assert calls == [], "the refresh repairs a lapse; it is not a second warmer"
        assert result["teams"] == GOOD["teams"]
        assert "stale" not in result

    async def test_a_failed_dispatch_still_serves_last_good(self):
        """The reader's payload is already in hand. A refresh that cannot even
        start must not turn a working serve into a 500."""
        rc = _redis_mock({"bainluck:category:playoffs:mlb:stale": json.dumps(GOOD)})

        with patch("app.tasks.redis_state.get_async_redis_client", return_value=rc), \
             patch.object(
                 ev, "_serve_stale_and_refresh", side_effect=RuntimeError("no loop")
             ):
            result = await pg.get_playoff_grid_cached("mlb", None, 10, False, MagicMock())

        assert result["teams"] == GOOD["teams"]
        assert result["stale_reason"] == "cache_miss"

    async def test_a_failing_rebuild_leaves_the_cached_value_alone(self):
        """A rebuild that raises must not poison the cache — the stale payload
        is still the best answer available."""
        async def _boom(slug):
            raise RuntimeError("database went away")

        rc = _redis_mock({"bainluck:category:playoffs:mlb:stale": json.dumps(GOOD)})

        with patch("app.tasks.redis_state.get_async_redis_client", return_value=rc), \
             patch.object(pg, "_rebuild_playoff_grid", _boom):
            result = await pg.get_playoff_grid_cached("mlb", None, 10, False, MagicMock())
            await asyncio.sleep(0)
            await asyncio.sleep(0)

        assert result["teams"] == GOOD["teams"]
        assert rc.set.await_count == 0
        assert "playoff_grid:mlb" not in ev._STALE_REFRESH_INFLIGHT, (
            "a failed rebuild must clear its in-flight marker or the league can "
            "never be refreshed again in this process"
        )
