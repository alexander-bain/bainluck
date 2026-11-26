"""#13573 — Unit tests for team page response cache and BitmapAnd SQL helpers."""

from __future__ import annotations

import json
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.ext.asyncio import AsyncSession

from app.routes import teams as teams_route
from app.utils import request_cache, team_page_cache as cache_mod


@pytest.fixture(autouse=True)
def _clean_team_page_cache():
    cache_mod.clear_team_page_l1_cache()
    request_cache._reset_shared_client_for_tests()
    yield
    cache_mod.clear_team_page_l1_cache()
    request_cache._reset_shared_client_for_tests()


def _fake_real_pg_session(*, pool: object | None = object()) -> AsyncSession:
    db = AsyncSession()
    fake_bind = SimpleNamespace(dialect=postgresql.dialect(), pool=pool)
    db.get_bind = lambda *_a, **_k: fake_bind  # type: ignore[method-assign]
    return db


def test_is_real_pg_engine_distinguishes_real_pool_from_stubs():
    assert cache_mod.is_real_pg_engine(MagicMock()) is False

    stub_pg = _fake_real_pg_session(pool=None)
    assert cache_mod.is_real_pg_engine(stub_pg) is False

    sqlite_db = AsyncSession()
    sqlite_db.get_bind = lambda *_a, **_k: SimpleNamespace(dialect=sqlite.dialect(), pool=object())  # type: ignore[method-assign]
    assert cache_mod.is_real_pg_engine(sqlite_db) is False

    real_pg = _fake_real_pg_session(pool=object())
    assert cache_mod.is_real_pg_engine(real_pg) is True


def test_ttl_for_team_payload():
    assert cache_mod.ttl_for_team_payload({"upcoming_events": []}) == 60
    assert (
        cache_mod.ttl_for_team_payload({"upcoming_events": [{"id": 1, "status": "scheduled"}]})
        == 60
    )
    assert (
        cache_mod.ttl_for_team_payload(
            {
                "upcoming_events": [
                    {"id": 1, "status": "scheduled"},
                    {"id": 2, "status": "live"},
                ]
            }
        )
        == 15
    )


@pytest.mark.asyncio
async def test_l1_cache_hit_miss_and_deepcopy_isolation(monkeypatch):
    monkeypatch.setenv("REDIS_URL", "")
    assert await cache_mod.read_team_page_cache(1, "boston-celtics") is None

    payload = {"team": {"slug": "boston-celtics"}, "upcoming_events": [], "futures": [{"id": 10}]}
    await cache_mod.write_team_page_cache(1, "boston-celtics", payload)
    payload["futures"].append({"id": 99})  # mutate caller dict after write

    hit = await cache_mod.read_team_page_cache(1, "boston-celtics")
    assert hit is not None
    assert hit["futures"] == [{"id": 10}]
    hit["futures"].append({"id": 88})  # mutate returned dict after read

    hit2 = await cache_mod.read_team_page_cache(1, "boston-celtics")
    assert hit2 is not None
    assert hit2["futures"] == [{"id": 10}]

    # Different scope keys stay isolated
    assert await cache_mod.read_team_page_cache(2, "boston-celtics") is None


@pytest.mark.asyncio
async def test_l1_cache_eviction_bound(monkeypatch):
    monkeypatch.setenv("REDIS_URL", "")
    monkeypatch.setattr(cache_mod, "TEAM_PAGE_L1_MAX_SIZE", 3)
    for i in range(4):
        await cache_mod.write_team_page_cache(1, f"team-{i}", {"id": i})
    assert await cache_mod.read_team_page_cache(1, "team-0") is None
    assert await cache_mod.read_team_page_cache(1, "team-3") == {"id": 3}


@pytest.mark.asyncio
async def test_redis_hit_preserves_remaining_age_and_rejects_expired(monkeypatch):
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    now = time.time()
    fresh_envelope = json.dumps(
        {
            "ts": now - 40.0,
            "ttl": 60,
            "payload": {"team": {"slug": "boston-celtics"}, "upcoming_events": []},
        }
    )

    fake_client = MagicMock()
    fake_client.get = AsyncMock(return_value=fresh_envelope)
    fake_client.setex = AsyncMock(return_value=True)

    with patch.object(cache_mod, "get_shared_async_redis", AsyncMock(return_value=fake_client)):
        hit = await cache_mod.read_team_page_cache(10, "boston-celtics")
        assert hit == {"team": {"slug": "boston-celtics"}, "upcoming_events": []}
        entry = cache_mod._l1_cache[(10, "boston-celtics")]
        remaining_mono = entry[0] - time.monotonic()
        # CERT-409: remaining TTL is ~20s, never re-granted full 60s
        assert 5.0 < remaining_mono <= 22.0

        # Expired envelope from Redis is ignored
        cache_mod.clear_team_page_l1_cache()
        fake_client.get = AsyncMock(
            return_value=json.dumps({"ts": now - 65.0, "ttl": 60, "payload": {"stale": True}})
        )
        assert await cache_mod.read_team_page_cache(10, "boston-celtics") is None


@pytest.mark.asyncio
async def test_redis_errors_fail_open(monkeypatch):
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    failing_client = MagicMock()
    failing_client.get = AsyncMock(side_effect=RuntimeError("redis down"))
    failing_client.setex = AsyncMock(side_effect=TimeoutError("redis timeout"))

    with patch.object(cache_mod, "get_shared_async_redis", AsyncMock(return_value=failing_client)):
        assert await cache_mod.read_team_page_cache(1, "boston-celtics") is None
        await cache_mod.write_team_page_cache(
            1, "boston-celtics", {"team": {"slug": "boston-celtics"}, "upcoming_events": []}
        )
    # L1 was still populated despite Redis write failure
    assert (1, "boston-celtics") in cache_mod._l1_cache


@pytest.mark.asyncio
async def test_get_team_cache_hit_skips_build_and_debug_timing_bypasses(monkeypatch):
    monkeypatch.setenv("REDIS_URL", "")
    db = _fake_real_pg_session()
    team_ns = SimpleNamespace(
        id=100,
        sport_id=1,
        name="Boston Celtics",
        slug="boston-celtics",
        abbreviation="BOS",
        logo_url=None,
        logo_url_small=None,
        logo_url_large=None,
        espn_id="2",
        primary_color="#007A33",
        secondary_color=None,
        alternate_names=[],
        current_record=None,
        location="Boston",
        roster_players=[],
        standings_data=None,
        standings_updated_at=None,
        season_stats=None,
        season_stats_updated_at=None,
        sport=SimpleNamespace(key="basketball_nba", name="NBA"),
    )
    from app.routes import user as user_route

    empty_scalars = MagicMock()
    empty_scalars.scalars.return_value.all.return_value = []
    db.execute = AsyncMock(return_value=empty_scalars)  # type: ignore[method-assign]

    built_calls = 0

    async def _counting_resolve(_db, _identifier):
        nonlocal built_calls
        built_calls += 1
        return team_ns

    with (
        patch.object(teams_route, "_resolve_team_by_identifier", side_effect=_counting_resolve),
        patch.object(
            teams_route,
            "_resolve_team_family_context",
            AsyncMock(return_value=("basketball_nba", "basketball_nba", [1], [1], {100}, {"Boston Celtics"}, [100], ["Boston Celtics"])),
        ),
        patch.object(teams_route, "_folded_briefs", AsyncMock(return_value=([], []))),
        patch.object(teams_route, "_read_cached_grid", AsyncMock(return_value=None)),
        patch.object(teams_route, "_format_team", return_value={"id": 100, "slug": "boston-celtics"}),
        patch.object(user_route, "_query_team_futures", AsyncMock(return_value={"items": [{"market_id": 1}]})),
        patch.object(teams_route, "_get_championship_path", AsyncMock(return_value=[])),
    ):
        first = await teams_route.get_team("Boston-Celtics ", debug_timing=False, db=db)
        second = await teams_route.get_team("boston-celtics", debug_timing=False, db=db)
        assert built_calls == 1
        assert first == second

        # debug_timing=True bypasses read & write
        dbg = await teams_route.get_team("boston-celtics", debug_timing=True, db=db)
        assert built_calls == 2
        assert "_timings_ms" in dbg


@pytest.mark.asyncio
async def test_get_team_does_not_cache_degraded_payloads(monkeypatch):
    monkeypatch.setenv("REDIS_URL", "")
    db = _fake_real_pg_session()
    team_ns = SimpleNamespace(
        id=100,
        sport_id=1,
        name="Boston Celtics",
        slug="boston-celtics",
        abbreviation="BOS",
        logo_url=None,
        logo_url_small=None,
        logo_url_large=None,
        espn_id="2",
        primary_color="#007A33",
        secondary_color=None,
        alternate_names=[],
        current_record=None,
        location="Boston",
        roster_players=[],
        standings_data=None,
        standings_updated_at=None,
        season_stats=None,
        season_stats_updated_at=None,
        sport=SimpleNamespace(key="basketball_nba", name="NBA"),
    )

    from app.routes import user as user_route

    base_patches = (
        patch.object(teams_route, "_resolve_team_by_identifier", AsyncMock(return_value=team_ns)),
        patch.object(
            teams_route,
            "_resolve_team_family_context",
            AsyncMock(return_value=("basketball_nba", "basketball_nba", [1], [1], {100}, {"Boston Celtics"}, [100], ["Boston Celtics"])),
        ),
        patch.object(teams_route, "_folded_briefs", AsyncMock(return_value=([], []))),
        patch.object(teams_route, "_read_cached_grid", AsyncMock(return_value=None)),
        patch.object(teams_route, "_format_team", return_value={"id": 100, "slug": "boston-celtics"}),
    )

    # Mock db.execute for upcoming & recent event rails (returns empty scalars)
    empty_scalars = MagicMock()
    empty_scalars.scalars.return_value.all.return_value = []
    db.execute = AsyncMock(return_value=empty_scalars)  # type: ignore[method-assign]

    with base_patches[0], base_patches[1], base_patches[2], base_patches[3], base_patches[4]:
        # 1) futures_unavailable -> must NOT cache
        with (
            patch.object(
                user_route,
                "_query_team_futures",
                AsyncMock(side_effect=user_route.TeamFuturesScreenUnavailableError()),
            ),
            patch.object(teams_route, "_get_championship_path", AsyncMock(return_value=[])),
        ):
            r1 = await teams_route.get_team("boston-celtics", debug_timing=False, db=db)
            assert r1.get("futures_unavailable") is True
            assert cache_mod._l1_cache == {}

        # 2) futures partial -> must NOT cache
        with (
            patch.object(
                user_route,
                "_query_team_futures",
                AsyncMock(return_value={"items": [], "partial": True, "omitted_count": 2}),
            ),
            patch.object(teams_route, "_get_championship_path", AsyncMock(return_value=[])),
        ):
            r2 = await teams_route.get_team("boston-celtics", debug_timing=False, db=db)
            assert r2.get("futures_partial") is True
            assert cache_mod._l1_cache == {}

        # 3) futures generic exception -> must NOT cache
        with (
            patch.object(
                user_route,
                "_query_team_futures",
                AsyncMock(side_effect=RuntimeError("db hiccup")),
            ),
            patch.object(teams_route, "_get_championship_path", AsyncMock(return_value=[])),
        ):
            await teams_route.get_team("boston-celtics", debug_timing=False, db=db)
            assert cache_mod._l1_cache == {}

        # 4) championship exception -> must NOT cache
        with (
            patch.object(
                user_route,
                "_query_team_futures",
                AsyncMock(return_value={"items": []}),
            ),
            patch.object(
                teams_route,
                "_get_championship_path",
                AsyncMock(side_effect=RuntimeError("champ hiccup")),
            ),
        ):
            await teams_route.get_team("boston-celtics", debug_timing=False, db=db)
            assert cache_mod._l1_cache == {}

        # 5) Clean build -> IS cached
        with (
            patch.object(
                user_route,
                "_query_team_futures",
                AsyncMock(return_value={"items": []}),
            ),
            patch.object(teams_route, "_get_championship_path", AsyncMock(return_value=[])),
        ):
            await teams_route.get_team("boston-celtics", debug_timing=False, db=db)
            assert len(cache_mod._l1_cache) == 1


def test_championship_path_stmt_market_ids_compile():
    base_sql = " ".join(
        str(teams_route._championship_path_stmt(853).compile(dialect=postgresql.dialect())).split()
    )
    assert "futures_outcomes.market_id = ANY" not in base_sql

    filtered_sql = " ".join(
        str(
            teams_route._championship_path_stmt(853, market_ids=[1, 2, 3]).compile(
                dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
            )
        ).split()
    )
    assert "futures_outcomes.market_id = ANY (ARRAY[1, 2, 3])" in filtered_sql
    assert "NOT (EXISTS (SELECT futures_outcomes.id FROM futures_outcomes" in filtered_sql
