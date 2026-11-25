"""Regression tests for #13650: fast /api/events/{id}/nuggets, kept finished copy, and 503 timeout."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import HTTPException
from httpx import ASGITransport

from app.main import app
from app.routes import events as events_route
from app.services import get_db, league_context
from app.tasks import redis_state
from app.utils import game_nuggets_cache


NOW = datetime(2026, 11, 24, 21, 0, tzinfo=timezone.utc)


class _DummyRedis:
    def __init__(self) -> None:
        self.data: dict[str, tuple[str, int]] = {}

    def get(self, key: str):
        val = self.data.get(key)
        return None if val is None else val[0].encode("utf-8")

    def setex(self, key: str, ttl: int, value):
        raw = value.decode("utf-8") if isinstance(value, bytes) else str(value)
        self.data[key] = (raw, int(ttl))
        return True


class _FakeScalarResult:
    def __init__(self, *, one=None, many=None):
        self._one = one
        self._many = many if many is not None else []

    def scalar_one_or_none(self):
        return self._one

    def scalars(self):
        return self

    def all(self):
        return self._many


def _make_fake_event(*, event_id: int, status: str, sport_key: str = "basketball_nba"):
    return SimpleNamespace(
        id=event_id,
        sport_id=2,
        sport=SimpleNamespace(id=2, key=sport_key),
        home_team_id=10,
        away_team_id=20,
        home_team_name="Boston Celtics",
        away_team_name="Los Angeles Lakers",
        status=status,
        commence_time=NOW - timedelta(hours=18 if status == "completed" else 1),
        win_probability_sources={"espn": {"home_prob": 0.55}},
    )


def _sample_game_markets(event_id: int):
    obs = (NOW - timedelta(minutes=2)).isoformat()
    return {
        "event_id": event_id,
        "totals": [
            {
                "_market_id": 1001,
                "market_name": "Boston Celtics vs Los Angeles Lakers: O/U 224.5",
                "outcome_name": "Over",
                "over_probability": 0.56,
                "threshold": 224.5,
                "observed_at": obs,
                "pregame_mark": 0.49,
                "pregame_mark_source": "kickoff",
                "probability_change_24h": 0.07,
                "source_mark": {"state": "single"},
            }
        ],
        "spreads": [
            {
                "_market_id": 1002,
                "market_name": "Spread: Boston Celtics -4.5",
                "outcome_name": "Boston Celtics -4.5",
                "probability": 0.52,
                "observed_at": obs,
                "probability_change_24h": 0.02,
                "source_mark": {"state": "single"},
            }
        ],
        "player_props": [
            {
                "_market_id": 1003,
                "market_name": "Jayson Tatum Points O/U 27.5",
                "player_name": "Jayson Tatum",
                "stat_type": "Points",
                "threshold": 27.5,
                "over_probability": 0.58,
                "observed_at": obs,
                "probability_change_24h": 0.04,
                "source_mark": {"state": "single"},
            }
        ],
        "team_totals": [],
        "period_markets": [],
        "matchups": [],
        "other": [],
        "outcome_market_ids": {"2001": 1001, "2002": 1002, "2003": 1003},
        "stream_market_ids": [1001, 1002, 1003],
    }


@pytest.fixture(autouse=True)
def _reset_nuggets_caches(monkeypatch):
    game_nuggets_cache.clear_l1()
    yield
    game_nuggets_cache.clear_l1()


@pytest.mark.asyncio
async def test_finished_game_writes_kept_copy_and_serves_from_cache_across_builds(monkeypatch):
    dummy_redis = _DummyRedis()
    monkeypatch.setattr(redis_state, "get_redis_client", lambda *a, **kw: dummy_redis)

    ev = _make_fake_event(event_id=15350164, status="completed")
    gm = _sample_game_markets(15350164)

    async def _fake_exec(stmt):
        sql = str(stmt)
        if "FROM teams" in sql:
            return _FakeScalarResult(
                many=[
                    SimpleNamespace(
                        id=10, logo_url="https://cdn/bos.png", alternate_names=["Boston"], roster_players=[]
                    ),
                    SimpleNamespace(
                        id=20, logo_url="https://cdn/lal.png", alternate_names=["Lakers"], roster_players=[]
                    ),
                ]
            )
        return _FakeScalarResult(one=ev)

    fake_db = SimpleNamespace(execute=AsyncMock(side_effect=_fake_exec))
    gm_mock = AsyncMock(return_value=gm)
    rf_mock = AsyncMock(return_value={"home_team_futures": [], "away_team_futures": []})
    tp_mock = AsyncMock(return_value={})

    monkeypatch.setattr(
        events_route,
        "resolve_served_event",
        AsyncMock(return_value=SimpleNamespace(event=ev, event_id=15350164)),
    )
    monkeypatch.setattr(events_route, "get_game_markets", gm_mock)
    monkeypatch.setattr(events_route, "get_related_futures", rf_mock)
    monkeypatch.setattr(events_route, "get_team_progression", tp_mock)

    # First read builds once and stores 7-day kept copy in Redis.
    first = await events_route.build_event_nuggets(15350164, fake_db, limit=12, now=NOW)
    assert len(first["nuggets"]) >= 2
    assert gm_mock.await_count == 1
    assert rf_mock.await_count == 1

    key = game_nuggets_cache.cache_key(15350164)
    assert key in dummy_redis.data
    raw_json, ttl = dummy_redis.data[key]
    assert ttl == game_nuggets_cache.FRESH_TTL_FINAL == 604800
    assert json.loads(raw_json)["is_final"] is True

    # Simulate new process / new release: clear L1 AND bump HEROKU_RELEASE_VERSION.
    game_nuggets_cache.clear_l1()
    monkeypatch.setenv("HEROKU_RELEASE_VERSION", "v99999")

    # Second read with limit=1 hits kept copy with zero sub-surface builds and slices cleanly.
    second = await events_route.build_event_nuggets(15350164, fake_db, limit=1, now=NOW)
    assert len(second["nuggets"]) == 1
    assert gm_mock.await_count == 1
    assert rf_mock.await_count == 1


@pytest.mark.asyncio
async def test_nuggets_timeout_ceiling_returns_503_never_empty_list(monkeypatch):
    dummy_redis = _DummyRedis()
    monkeypatch.setattr(redis_state, "get_redis_client", lambda *a, **kw: dummy_redis)

    ev = _make_fake_event(event_id=14780582, status="in_progress")

    async def _fake_exec(stmt):
        sql = str(stmt)
        if "FROM teams" in sql:
            return _FakeScalarResult(many=[])
        return _FakeScalarResult(one=ev)

    fake_db = SimpleNamespace(execute=AsyncMock(side_effect=_fake_exec))

    async def _slow_game_markets(*_args, **_kwargs):
        await asyncio.sleep(0.25)
        return {}

    monkeypatch.setattr(
        events_route,
        "resolve_served_event",
        AsyncMock(return_value=SimpleNamespace(event=ev, event_id=14780582)),
    )
    monkeypatch.setattr(events_route, "get_game_markets", _slow_game_markets)

    with pytest.raises(HTTPException) as exc_info:
        await events_route.build_event_nuggets(14780582, fake_db, timeout_seconds=0.05)

    assert exc_info.value.status_code == 503
    assert exc_info.value.headers.get("Retry-After") == "5"
    # Timeouts must NEVER poison cache.
    assert game_nuggets_cache.cache_key(14780582) not in dummy_redis.data


@pytest.mark.asyncio
async def test_nuggets_http_503_on_sql_statement_timeout(monkeypatch):
    dummy_redis = _DummyRedis()
    monkeypatch.setattr(redis_state, "get_redis_client", lambda *a, **kw: dummy_redis)

    ev = _make_fake_event(event_id=14780582, status="in_progress")

    async def _fake_exec(stmt):
        sql = str(stmt)
        if "FROM teams" in sql:
            return _FakeScalarResult(many=[])
        return _FakeScalarResult(one=ev)

    fake_db = SimpleNamespace(execute=AsyncMock(side_effect=_fake_exec))

    async def _canceled_gm(*_args, **_kwargs):
        raise RuntimeError("canceling statement due to statement timeout")

    monkeypatch.setattr(
        events_route,
        "resolve_served_event",
        AsyncMock(return_value=SimpleNamespace(event=ev, event_id=14780582)),
    )
    monkeypatch.setattr(events_route, "get_game_markets", _canceled_gm)

    async def _db_override():
        yield fake_db

    prior = dict(app.dependency_overrides)
    app.dependency_overrides[get_db] = _db_override
    try:
        async with httpx.AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            resp = await client.get("/api/events/14780582/nuggets")
            assert resp.status_code == 503
            assert "timed out" in resp.json()["detail"].lower()
            assert "nuggets" not in resp.json()
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(prior)


@pytest.mark.asyncio
async def test_league_context_handles_none_grouped_teams_and_cache_only_helper(monkeypatch):
    dummy_redis = _DummyRedis()
    monkeypatch.setattr(redis_state, "get_redis_client", lambda *a, **kw: dummy_redis)

    async def _fake_grid(**_kwargs):
        return {
            "teams": [],
            "grouped_teams": None,
        }

    from app.routes import playoffs as playoffs_route

    monkeypatch.setattr(playoffs_route, "get_playoff_grid_cached", _fake_grid)

    ctx = await league_context._compute_league_context("nba", db=SimpleNamespace())
    assert ctx is not None
    assert ctx.league_slug == "nba"
    assert ctx.teams == {}

    # enrich_event_with_cached_context must never call _compute_league_context on a cache miss
    compute_spy = AsyncMock()
    monkeypatch.setattr(league_context, "_compute_league_context", compute_spy)
    ev = _make_fake_event(event_id=999, status="in_progress")
    assert league_context.enrich_event_with_cached_context(ev, "basketball_nba") is None
    assert compute_spy.await_count == 0


@pytest.mark.asyncio
async def test_fast_stakes_loader_skips_full_related_futures_and_grid_rebuild(monkeypatch):
    dummy_redis = _DummyRedis()
    monkeypatch.setattr(redis_state, "get_redis_client", lambda *a, **kw: dummy_redis)

    ev = _make_fake_event(event_id=88801, status="completed", sport_key="basketball_nba")

    market_row = SimpleNamespace(
        id=501,
        name="2026 NBA Finals Champion",
        market_tier=1,
        source="kalshi",
        external_id="KXNBA-26-CHAMP",
        category="championship",
        resolution_date=NOW + timedelta(days=90),
    )
    sibling_ncaa_row = SimpleNamespace(
        id=502,
        name="2026 NCAA Tournament Winner",
        market_tier=1,
        source="kalshi",
        external_id="KXNCAAMB-26",
        category="championship",
        resolution_date=NOW + timedelta(days=90),
    )
    outcome_celtics = SimpleNamespace(
        id=9001,
        market_id=501,
        name="Boston Celtics",
        team_id=10,
        current_probability=0.24,
        probability_change_24h=0.04,
        current_yes_bid=0.23,
        current_yes_ask=0.25,
        last_updated=NOW - timedelta(minutes=4),
    )
    team_bos = SimpleNamespace(
        id=10,
        logo_url="https://cdn/bos.png",
        alternate_names=["Boston", "Celtics"],
        roster_players=[{"name": "Jayson Tatum", "headshot": "https://cdn/jt.png"}],
    )
    team_lal = SimpleNamespace(
        id=20,
        logo_url="https://cdn/lal.png",
        alternate_names=["LA Lakers", "Lakers"],
        roster_players=[],
    )

    async def _fake_exec(stmt):
        sql = str(stmt)
        if "FROM teams" in sql:
            return _FakeScalarResult(many=[team_bos, team_lal])
        if "FROM futures_markets" in sql:
            assert "futures_markets.status =" in sql
            return _FakeScalarResult(many=[market_row, sibling_ncaa_row])
        if "FROM futures_outcomes" in sql:
            return _FakeScalarResult(many=[outcome_celtics])
        return _FakeScalarResult(one=ev)

    fake_db = SimpleNamespace(execute=AsyncMock(side_effect=_fake_exec))
    monkeypatch.setattr(
        events_route,
        "resolve_served_event",
        AsyncMock(return_value=SimpleNamespace(event=ev, event_id=88801)),
    )
    # Fail loudly if legacy _build_related_futures or _compute_league_context runs!
    monkeypatch.setattr(
        events_route,
        "_build_related_futures",
        AsyncMock(side_effect=AssertionError("legacy _build_related_futures must not run")),
    )
    monkeypatch.setattr(
        league_context,
        "_compute_league_context",
        AsyncMock(side_effect=AssertionError("inline grid rebuild must not run")),
    )

    # Keep _ORIG_GET_GAME_MARKETS monkeypatched to verify only fast stakes + cache-only tp run.
    monkeypatch.setattr(events_route, "get_game_markets", AsyncMock(return_value=_sample_game_markets(88801)))

    res = await events_route.build_event_nuggets(88801, fake_db, limit=12, now=NOW)
    assert any(n["kind"] == "stakes" and "Boston Celtics" in n["claim"] for n in res["nuggets"])
    assert "bainluck:nuggets:season_mkts:v2:basketball_nba" in dummy_redis.data
    assert "Boston Celtics" in dummy_redis.data["bainluck:nuggets:season_mkts:v2:basketball_nba"][0] or (
        "2026 NBA Finals Champion" in dummy_redis.data["bainluck:nuggets:season_mkts:v2:basketball_nba"][0]
    )


@pytest.mark.asyncio
async def test_load_nuggets_open_season_markets_reuses_discovery_and_orders_newest_first(monkeypatch):
    dummy_redis = _DummyRedis()
    monkeypatch.setattr(redis_state, "get_redis_client", lambda *a, **kw: dummy_redis)

    from app.utils import season_market_discovery

    # Case 1: warm season_market_discovery cache populates via PK IN (...) without scanning.
    season_market_discovery.write("basketball_nba", False, [701], rc=dummy_redis)
    captured_sql: list[str] = []

    market_pk_row = SimpleNamespace(
        id=701,
        name="2026 NBA Finals Champion",
        market_tier=1,
        source="kalshi",
        external_id="KXNBA-26-CHAMP",
        category="championship",
        resolution_date=NOW + timedelta(days=90),
    )

    async def _exec_warm(stmt):
        captured_sql.append(" ".join(str(stmt).split()))
        return _FakeScalarResult(many=[market_pk_row])

    res_warm = await events_route._load_nuggets_open_season_markets(
        SimpleNamespace(execute=AsyncMock(side_effect=_exec_warm)),
        "basketball_nba",
        event_is_finished=False,
    )
    assert [m["id"] for m in res_warm] == [701]
    assert "futures_markets.id IN" in captured_sql[0]

    # Case 2: cold miss uses ix_fm_feed_open_sports ordered newest-first (id DESC).
    game_nuggets_cache.clear_l1()
    dummy_redis.data.clear()
    captured_sql.clear()

    nfl_row = SimpleNamespace(
        id=900501,
        name="Super Bowl LXI Champion",
        market_tier=1,
        source="kalshi",
        external_id="KXNFL-26-SB",
        category="championship",
        resolution_date=NOW + timedelta(days=60),
    )

    async def _exec_cold(stmt):
        captured_sql.append(" ".join(str(stmt).split()))
        return _FakeScalarResult(many=[nfl_row])

    monkeypatch.setattr(
        events_route,
        "_build_related_futures",
        AsyncMock(side_effect=AssertionError("_build_related_futures must not run")),
    )
    res_cold = await events_route._load_nuggets_open_season_markets(
        SimpleNamespace(execute=AsyncMock(side_effect=_exec_cold)),
        "americanfootball_nfl",
        event_is_finished=True,
    )
    assert [m["id"] for m in res_cold] == [900501]
    cold_sql = captured_sql[0]
    assert "futures_markets.llm_sport_category =" in cold_sql
    assert "futures_markets.id DESC" in cold_sql
