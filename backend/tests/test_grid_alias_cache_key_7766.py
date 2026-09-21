"""#7766 — one league, one grid, whichever slug the reader arrives on.

THE DEFECT, MEASURED ON PRODUCTION 2026-09-21 09:55Z.

`/api/playoffs/wncaab` and `/api/playoffs/ncaab` served payloads **164 minutes**
stale (`stale: true`) while `/api/playoffs/ncaa-women-basketball` and
`/api/playoffs/ncaa-basketball` were 29 minutes fresh. Two payloads for one
league — and the alias is the arm a reader sees: `frontend/lib/playoffLeagues.ts`
aliases `ncaab`/`wncaab` precisely so `/sport/basketball/ncaab` resolves, and
`LeagueChips` links that path.

Three causes, one line apart:

1. `get_playoff_grid_cached` keyed the cache on the RAW path slug, before any
   alias resolution, so the alias had its own pair of keys.
2. The hourly warm beat iterates canonical `GRID_WARM_LEAGUES`, so the alias
   keys were never warmed — only a reader's own cold build ever wrote them.
3. `_schedule_grid_refresh` resolves against `get_all_league_slugs()`, which
   holds no aliases, so it returned False on every alias read: **#7109's
   refresh-behind — the repair built for exactly this self-sustaining lapse —
   could not fire on the only slugs that had one.**

And the divergence is worse than a clock. `get_playoff_grid` branches on the
RAW slug — the NCAA and WNCAA bracket lookups (`league_slug ==
"ncaa-basketball"`, in two places) and the `MatchingOverride.league_slug`
query — so a build entered through the alias silently skips them. Measured the
same minute: `/ncaab` carried a seed and a region on **41 of 68** teams where
`/ncaa-basketball` carried **67**. That is why the fix cannot be "warm the alias
key too": the two doors must build the SAME grid before they may share a key.

WHAT THESE TESTS PIN.

Behaviour, not source text — which key was asked of Redis, which key was
written, which slug the builder was handed. A guard that greps the route stays
green when the route stops doing the thing.

1. The alias READS the canonical keys.
2. A live build entered via the alias WRITES the canonical keys.
3. The builder is handed the CANONICAL slug — the bracket/override branches.
4. A stale serve via the alias schedules the #7109 refresh (it could not before),
   under the canonical name so it dedups against the canonical reader.
5. Every alias resolves to a league that actually exists.
6. Resolution does not validate: an unrecognised slug is still refused by
   `_schedule_grid_refresh`, which is the taint guard #7109 put there.
7. A canonical slug is untouched — the control that fails if resolution starts
   rewriting slugs it was not asked about.
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config import league_configs as lc
from app.routes import events as ev
from app.routes import playoffs as pg


CANON = "ncaa-basketball"
ALIAS = "ncaab"
CANON_KEY = f"bainluck:category:playoffs:{CANON}"
ALIAS_KEY = f"bainluck:category:playoffs:{ALIAS}"

GOOD = {"teams": [{"name": "Duke"}], "columns": [{"key": "championship"}]}
BUILT = {"teams": [{"name": "Duke"}, {"name": "UConn"}], "columns": [{"key": "c"}]}


@pytest.fixture(autouse=True)
def _clear_inflight():
    """The in-flight set is process-global; a leaked name silently disables the
    refresh for every later test and they would all still pass."""
    for name in (f"playoff_grid:{CANON}", f"playoff_grid:{ALIAS}"):
        ev._STALE_REFRESH_INFLIGHT.discard(name)
    yield
    for name in (f"playoff_grid:{CANON}", f"playoff_grid:{ALIAS}"):
        ev._STALE_REFRESH_INFLIGHT.discard(name)


def _redis_mock(values: dict):
    rc = MagicMock()
    rc.reads = []

    async def _get(key):
        rc.reads.append(key)
        return values.get(key)

    rc.get = AsyncMock(side_effect=_get)
    rc.set = AsyncMock()
    rc.aclose = AsyncMock()
    return rc


# ---------------------------------------------------------------------------
# 1 + 2 — the two halves of the cache, on one key
# ---------------------------------------------------------------------------
class TestTheAliasUsesTheCanonicalKey:
    async def test_the_alias_reads_the_canonical_key(self):
        """FAILS ON THE PRE-#7766 TREE, which asked for `…:ncaab` and got the
        miss that sent the reader to its own cold build."""
        rc = _redis_mock({CANON_KEY: json.dumps(GOOD)})

        with patch("app.tasks.redis_state.get_async_redis_client", return_value=rc):
            result = await pg.get_playoff_grid_cached(ALIAS, None, 10, False, MagicMock())

        assert CANON_KEY in rc.reads, (
            f"a read of /{ALIAS} must hit the canonical key; asked for {rc.reads}"
        )
        assert not any(r.startswith(ALIAS_KEY) for r in rc.reads), (
            f"the alias must own no cache key of its own; asked for {rc.reads}"
        )
        assert result["teams"] == GOOD["teams"]

    async def test_a_build_entered_through_the_alias_writes_the_canonical_keys(self):
        """The write half. Keyed on the raw slug, a reader's cold build through
        the alias published a second grid that the warm beat never refreshed and
        that no canonical reader ever saw."""
        rc = _redis_mock({})

        with patch("app.tasks.redis_state.get_async_redis_client", return_value=rc), \
             patch.object(pg, "get_playoff_grid", AsyncMock(return_value=BUILT)):
            await pg.get_playoff_grid_cached(ALIAS, None, 10, False, MagicMock())

        written = {c.args[0] for c in rc.set.await_args_list}
        assert written == {CANON_KEY, f"{CANON_KEY}:stale"}, (
            f"an alias build must publish the canonical pair, wrote {written}"
        )

    async def test_the_alias_and_the_canonical_agree_on_both_keys(self):
        """States the property directly rather than per-arm: whatever the key
        scheme becomes, the two doors must not be able to drift apart."""
        reads = {}
        for slug in (ALIAS, CANON):
            rc = _redis_mock({})
            with patch("app.tasks.redis_state.get_async_redis_client", return_value=rc), \
                 patch.object(pg, "get_playoff_grid", AsyncMock(return_value=BUILT)):
                await pg.get_playoff_grid_cached(slug, None, 10, False, MagicMock())
            reads[slug] = (rc.reads, sorted(c.args[0] for c in rc.set.await_args_list))

        assert reads[ALIAS] == reads[CANON], (
            f"/{ALIAS} and /{CANON} must touch the same keys: {reads}"
        )


# ---------------------------------------------------------------------------
# 3 — the reason they are ALLOWED to share a key
# ---------------------------------------------------------------------------
class TestTheBuilderGetsTheCanonicalSlug:
    async def test_the_builder_is_handed_the_canonical_slug(self):
        """The correctness precondition for tests 1–2. `get_playoff_grid`
        branches on the raw slug for the NCAA/WNCAA bracket lookups and the
        `MatchingOverride.league_slug` query; handed `ncaab` it skips them and
        builds a grid missing 26 of 68 seeds (measured 2026-09-21). Sharing a
        cache key between two DIFFERENT builds would be the worse bug."""
        builder = AsyncMock(return_value=BUILT)
        rc = _redis_mock({})

        with patch("app.tasks.redis_state.get_async_redis_client", return_value=rc), \
             patch.object(pg, "get_playoff_grid", builder):
            await pg.get_playoff_grid_cached(ALIAS, None, 10, False, MagicMock())

        assert builder.await_args.args[0] == CANON, (
            "the build must run under the canonical slug or the bracket and "
            "override branches never fire"
        )

    async def test_the_refresh_behind_rebuild_also_builds_canonically(self):
        """`_rebuild_playoff_grid` publishes the 24 h mirror, so an alias-named
        rebuild would overwrite the canonical grid with the degraded build."""
        builder = AsyncMock(return_value=BUILT)
        rc = _redis_mock({})
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=MagicMock())
        cm.__aexit__ = AsyncMock(return_value=False)

        with patch.object(pg, "get_playoff_grid", builder), \
             patch("app.services.database.async_session_maker", MagicMock(return_value=cm)), \
             patch("app.tasks.redis_state.get_async_redis_client", return_value=rc):
            await pg._rebuild_playoff_grid(pg.resolve_league_slug(ALIAS))

        assert builder.await_args.args[0] == CANON
        assert {c.args[0] for c in rc.set.await_args_list} == {
            CANON_KEY,
            f"{CANON_KEY}:stale",
        }


# ---------------------------------------------------------------------------
# 4 — #7109's repair finally reaches the slug that needed it
# ---------------------------------------------------------------------------
class TestTheAliasCanBeRepaired:
    async def test_a_stale_serve_through_the_alias_schedules_a_rebuild(self):
        """THE SHIP, and the assertion that fails loudest on the pre-#7766 tree:
        `_schedule_grid_refresh("ncaab")` returned False every single time,
        because the registry it resolves against holds no aliases. The lapse
        #7109 was written to end was still live on the only slugs the page
        requests."""
        calls = []

        async def _fake_rebuild(slug):
            calls.append(slug)

        rc = _redis_mock({f"{CANON_KEY}:stale": json.dumps(GOOD)})

        with patch("app.tasks.redis_state.get_async_redis_client", return_value=rc), \
             patch.object(pg, "_rebuild_playoff_grid", _fake_rebuild):
            result = await pg.get_playoff_grid_cached(ALIAS, None, 10, False, MagicMock())
            await asyncio.sleep(0)
            await asyncio.sleep(0)

        assert calls == [CANON], (
            f"an alias read of a lapsed key must refresh behind itself, and do "
            f"it under the canonical name; got {calls}"
        )
        # The #1484 contract is not this change's to move.
        assert result["teams"] == GOOD["teams"]
        assert result["stale"] is True
        assert result["stale_reason"] == "cache_miss"

    def test_the_refresh_guard_recognises_a_resolved_alias(self):
        """The unit under the test above: the resolved value passes the registry
        filter that the raw alias could never pass."""
        assert pg._schedule_grid_refresh(ALIAS) is False, (
            "the guard resolves against the registry and must not learn aliases "
            "itself — the route resolves before calling it"
        )
        ev._STALE_REFRESH_INFLIGHT.discard(f"playoff_grid:{CANON}")
        with patch.object(ev, "_serve_stale_and_refresh", return_value=True) as sr:
            assert pg._schedule_grid_refresh(CANON) is True
        assert sr.call_args.args[0] == f"playoff_grid:{CANON}"


# ---------------------------------------------------------------------------
# 5 + 6 + 7 — the resolver's own contract
# ---------------------------------------------------------------------------
class TestResolveLeagueSlug:
    def test_every_alias_points_at_a_league_that_exists(self):
        """An alias to a slug with no config resolves a reader onto a 404 and
        parks an unwarmable key in Redis. Cheap to add, invisible until a page
        links it."""
        for alias, canonical in lc._SLUG_ALIASES.items():
            assert canonical in lc.LEAGUE_CONFIGS, (
                f"alias {alias!r} → {canonical!r}, which is not a configured league"
            )
            assert lc.resolve_league_slug(alias) == canonical
            assert lc.get_league_config(alias) is lc.LEAGUE_CONFIGS[canonical]

    def test_a_canonical_slug_is_returned_unchanged(self):
        """The control. Resolution that rewrote a canonical slug would move
        every cache key in the fleet at once."""
        for slug in lc.get_all_league_slugs():
            assert lc.resolve_league_slug(slug) == slug

    def test_resolution_does_not_validate(self):
        """It resolves; the caller's registry check is still the guard. #7109's
        taint argument depends on that check, and this is the test that fails if
        someone makes `resolve_league_slug` look like a sanitiser."""
        assert lc.resolve_league_slug("not-a-league") == "not-a-league"
        assert lc.get_league_config("not-a-league") is None
        assert pg._schedule_grid_refresh("mlb\nFAKE LOG LINE") is False
        assert pg._schedule_grid_refresh("../../etc/passwd") is False

    async def test_an_unknown_slug_still_404s_through_the_cached_route(self):
        """End to end: resolution must not turn a 404 into a cache key."""
        from fastapi import HTTPException

        rc = _redis_mock({})
        with patch("app.tasks.redis_state.get_async_redis_client", return_value=rc), \
             patch.object(
                 pg,
                 "get_playoff_grid",
                 AsyncMock(side_effect=HTTPException(status_code=404, detail="nope")),
             ):
            with pytest.raises(HTTPException) as exc:
                await pg.get_playoff_grid_cached("not-a-league", None, 10, False, MagicMock())

        assert exc.value.status_code == 404
        assert rc.set.await_count == 0
