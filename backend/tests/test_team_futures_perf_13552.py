"""#13552 — Regression guards for `/api/me/team-futures` and `/api/shared/team-futures` latency."""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

from app.routes import user as user_route
from app.utils import open_futures_outcomes as ofo_mod

pytestmark = pytest.mark.asyncio


def _ts_now() -> datetime:
    return datetime.now(timezone.utc)


def _outcome(
    oid: int,
    market_id: int,
    name: str,
    prob: float,
    *,
    stamp: datetime,
    team_id: int | None = 1,
    rank: int = 1,
    bid: float | None = None,
    ask: float | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=oid,
        market_id=market_id,
        name=name,
        team_id=team_id,
        current_probability=prob,
        probability_change_24h=0.0,
        current_yes_bid=prob - 0.01 if bid is None else bid,
        current_yes_ask=prob + 0.01 if ask is None else ask,
        rank=rank,
        is_winner=False,
        resolution_source=None,
        external_id=f"EXT-{market_id}-{oid}",
        last_updated=stamp,
        volume_24h=100.0,
        volume_24h_at=stamp,
        price_changed_at=stamp,
        volume=1000.0,
    )


def _market(
    mid: int,
    name: str,
    outcomes: list[SimpleNamespace],
    *,
    updated_at: datetime,
    source: str = "odds_api",
    sport_id: int = 1,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=mid,
        source=source,
        external_id=f"M-{mid}",
        group_id=f"{source}:{mid}",
        sport_id=sport_id,
        status="open",
        event_id=None,
        name=name,
        llm_sport_category="basketball",
        market_tier=2,
        market_type="championship",
        resolution_date=None,
        canonical_market_key=f"winner_{mid}",
        market_metadata=None,
        updated_at=updated_at,
        outcomes=outcomes,
    )


def _result(rows, scalar=None):
    res = MagicMock()
    res.all.return_value = list(rows)
    sc = MagicMock()
    sc.all.return_value = list(rows)
    res.scalars.return_value = sc
    res.scalar_one_or_none.return_value = scalar
    return res


class QueryCanceledError(Exception):
    """Stand-in for asyncpg.QueryCanceledError recognized by is_statement_timeout."""


class _FakeSavepoint:
    def __init__(self, pg_state: dict):
        self._pg_state = pg_state
        self._prev_aborted = pg_state["aborted"]

    async def commit(self):
        return None

    async def rollback(self):
        self._pg_state["aborted"] = self._prev_aborted


def _build_pg_session(
    *,
    teams: list[SimpleNamespace],
    fk_rows: list[tuple],
    markets: list[SimpleNamespace],
    award_rows: list[tuple] | None = None,
    fleet_stamp: datetime | None = None,
    bind: SimpleNamespace | None = None,
    initial_timeout: str = "30s",
    fail_q1_timeout: bool = False,
) -> tuple[AsyncSession, list[str], list[list[int]]]:
    """Create a real AsyncSession bound to PG dialect (emulates tx/savepoints/timeouts)."""
    now = fleet_stamp or _ts_now()
    markets_by_id = {m.id: m for m in markets}
    executed_sql: list[str] = []
    screen_wave_calls: list[list[int]] = []
    pg_state = {"timeout": initial_timeout, "aborted": False}

    db = AsyncSession()
    fake_bind = bind or SimpleNamespace(dialect=postgresql.dialect())

    def _get_bind(*_a, **_k):
        return fake_bind

    async def _begin_nested():
        return _FakeSavepoint(pg_state)

    async def _execute(stmt, params=None, *_a, **_k):
        if pg_state["aborted"]:
            raise RuntimeError("InFailedSQLTransactionError: current transaction is aborted")
        if hasattr(stmt, "compile"):
            sql = str(
                stmt.compile(
                    dialect=postgresql.dialect(),
                    compile_kwargs={"literal_binds": True},
                )
            )
        else:
            sql = str(stmt)
        executed_sql.append(sql)

        if "SHOW statement_timeout" in sql:
            return _result([], scalar=pg_state["timeout"])
        if "SET LOCAL statement_timeout" in sql:
            pg_state["timeout"] = sql.split("=", 1)[1].strip().strip("'")
            return _result([])
        if "set_config('statement_timeout'" in sql:
            val = params["val"] if isinstance(params, dict) and "val" in params else initial_timeout
            pg_state["timeout"] = str(val)
            return _result([], scalar=pg_state["timeout"])
        if sql.strip() == "SELECT 1":
            return _result([(1,)], scalar=1)
        if "max(futures_outcomes.last_updated)" in sql:
            return _result([], scalar=now)
        if "FROM teams JOIN sports" in sql:
            return _result([(t, "basketball_nba") for t in teams])
        if "FROM team_identity_mapping" in sql:
            return _result([])
        if "count(*)" in sql.lower() and "GROUP BY" in sql:
            return _result([(m.id, len(m.outcomes), sum(o.current_probability or 0 for o in m.outcomes)) for m in markets])
        if "futures_outcomes.team_id IN" in sql:
            if fail_q1_timeout:
                pg_state["aborted"] = True
                raise QueryCanceledError("canceling statement due to statement timeout")
            return _result(fk_rows)
        if "futures_outcomes.name ILIKE" in sql or "open_futures_outcomes" in sql:
            return _result([])
        if "FROM futures_outcomes JOIN futures_markets" in sql and "MVP" in sql:
            return _result(award_rows or [])
        if "FROM futures_markets" in sql and "WHERE futures_markets.id IN" in sql:
            wave_ids = [
                mid for mid in markets_by_id
                if f"({mid}" in sql or f" {mid}," in sql or f" {mid})" in sql
            ]
            # Parse exact integers cleanly from compiled IN (...) clause
            if "WHERE futures_markets.id IN (" in sql:
                in_part = sql.split("WHERE futures_markets.id IN (", 1)[1].split(")", 1)[0]
                wave_ids = [int(x.strip()) for x in in_part.split(",") if x.strip()]
            screen_wave_calls.append(wave_ids)
            if "futures_markets.group_id" in sql:
                # Full ORM select(FuturesMarket) used by origin/master or non-PG fallback
                return _result([m for mid in wave_ids if (m := markets_by_id.get(mid)) is not None])
            return _result(
                [
                    (
                        m.id,
                        m.source,
                        m.external_id,
                        m.status,
                        m.event_id,
                        m.market_type,
                        m.market_metadata,
                        m.updated_at,
                        m.name,
                    )
                    for mid in wave_ids
                    if (m := markets_by_id.get(mid)) is not None
                ]
            )
        if "FROM futures_outcomes" in sql and "WHERE futures_outcomes.market_id IN" in sql:
            in_part = sql.split("WHERE futures_outcomes.market_id IN (", 1)[1].split(")", 1)[0]
            wave_ids = [int(x.strip()) for x in in_part.split(",") if x.strip()]
            out_rows = []
            for mid in wave_ids:
                m = markets_by_id.get(mid)
                if not m:
                    continue
                for o in m.outcomes:
                    out_rows.append(
                        (
                            o.id,
                            o.market_id,
                            o.current_probability,
                            o.current_yes_bid,
                            o.current_yes_ask,
                            o.resolution_source,
                            o.is_winner,
                            o.volume_24h,
                            o.volume_24h_at,
                            o.last_updated,
                        )
                    )
            return _result(out_rows)
        if "FROM futures_odds_snapshots" in sql:
            return _result([])
        return _result([])

    db.get_bind = _get_bind  # type: ignore[method-assign]
    db.begin_nested = _begin_nested  # type: ignore[method-assign]
    db.execute = _execute  # type: ignore[method-assign]
    db._pg_state = pg_state  # type: ignore[attr-defined]
    return db, executed_sql, screen_wave_calls


async def test_pg_name_query_uses_ilike_any_open_outcomes_and_arms_statement_timeout():
    """On PG, team-name search uses ILIKE ANY(ARRAY[...]), open_futures_outcomes when servable, and statement_timeout."""
    if hasattr(user_route, "_award_outcomes_cache"):
        user_route._award_outcomes_cache.clear()
    now = _ts_now()
    team = SimpleNamespace(
        id=1,
        name="Boston Celtics",
        sport_id=1,
        espn_id="2",
        logo_url_small=None,
        logo_url=None,
        primary_color=None,
        alternate_names=None,
        roster_players=["Jayson Tatum"],
    )
    o = _outcome(101, 1001, "Boston Celtics", 0.28, stamp=now, team_id=1)
    m = _market(1001, "NBA Championship Winner", [o], updated_at=now)

    shared_bind = SimpleNamespace(dialect=postgresql.dialect())
    # 1. With open_futures_outcomes maintainer state servable
    db_ofo, sql_ofo, _ = _build_pg_session(
        teams=[team], fk_rows=[(o, m, "basketball_nba")], markets=[m], bind=shared_bind
    )
    ofo_mod._memo["at"] = None
    ofo_mod._memo["state"] = None
    with patch.object(
        ofo_mod,
        "_fetch_state",
        lambda: {"reader_floor": 1000, "pass_at": now.timestamp(), "cycle_complete": True},
    ):
        res1 = await user_route._query_team_futures([1], db_ofo, limit=20)
    assert [it["market_id"] for it in res1["items"]] == [1001]

    assert any("SET LOCAL statement_timeout" in s for s in sql_ofo)
    name_sqls = [s for s in sql_ofo if "Boston Celtics" in s]
    assert len(name_sqls) == 1
    assert "ILIKE ANY" in name_sqls[0]
    assert "open_futures_outcomes" in name_sqls[0]
    # Also verify Award Q2 used ILIKE ANY + cached on 2nd call
    award_sqls_1 = [s for s in sql_ofo if "MVP" in s]
    assert len(award_sqls_1) == 1
    assert "ILIKE ANY" in award_sqls_1[0]

    # 2. Second PG call on same engine bind hits in-process Q2 award cache (0 award SQL)
    db_cached, sql_cached, _ = _build_pg_session(
        teams=[team], fk_rows=[(o, m, "basketball_nba")], markets=[m], bind=shared_bind
    )
    await user_route._query_team_futures([1], db_cached, limit=20)
    assert [s for s in sql_cached if "MVP" in s] == []

    # 3. With open_futures_outcomes unavailable, falls back to ILIKE ANY on futures_outcomes (no N-way OR)
    db_fb, sql_fb, _ = _build_pg_session(
        teams=[team], fk_rows=[(o, m, "basketball_nba")], markets=[m], bind=shared_bind
    )
    ofo_mod._memo["at"] = None
    ofo_mod._memo["state"] = None
    with patch.object(ofo_mod, "_fetch_state", lambda: None):
        res2 = await user_route._query_team_futures([1], db_fb, limit=20)
    assert res2["items"] == res1["items"]
    fb_name_sqls = [s for s in sql_fb if "Boston Celtics" in s]
    assert len(fb_name_sqls) == 1
    assert "ILIKE ANY" in fb_name_sqls[0]
    assert "open_futures_outcomes" not in fb_name_sqls[0]


async def test_stopped_boards_hoist_single_fleet_read_and_skip_trade_lookup():
    """5 stopped boards must emit at most ONE fleet max(last_updated) query and 0 trade snapshot reads."""
    now = _ts_now()
    stale = now - timedelta(days=90)
    team = SimpleNamespace(
        id=1,
        name="New England Patriots",
        sport_id=1,
        espn_id="17",
        logo_url_small=None,
        logo_url=None,
        primary_color=None,
        alternate_names=None,
        roster_players=None,
    )
    stopped_markets = [
        _market(
            200 + i,
            f"Old Award Board {i}",
            [_outcome(300 + i, 200 + i, "New England Patriots", 0.25, stamp=stale, team_id=1)],
            updated_at=stale,
            source="kalshi",
        )
        for i in range(5)
    ]
    live_market = _market(
        999,
        "Live Division Winner",
        [_outcome(9991, 999, "New England Patriots", 0.40, stamp=now, team_id=1)],
        updated_at=now,
        source="kalshi",
    )
    all_markets = stopped_markets + [live_market]
    fk_rows = [(m.outcomes[0], m, "basketball_nba") for m in all_markets]

    db, executed_sql, _ = _build_pg_session(
        teams=[team], fk_rows=fk_rows, markets=all_markets, fleet_stamp=now
    )
    seen_in_trade_screen: list[int] = []

    async def _spy_withheld(_db, screen_markets):
        seen_in_trade_screen.extend(m.id for m in screen_markets)
        return {m.id: set() for m in screen_markets}

    with patch("app.routes.futures.withheld_price_outcome_ids_for_markets", _spy_withheld):
        res = await user_route._query_team_futures([1], db, limit=20)

    fleet_queries = [s for s in executed_sql if "max(futures_outcomes.last_updated)" in s]
    assert len(fleet_queries) == 1
    assert set(seen_in_trade_screen) == {999}
    assert [it["market_id"] for it in res["items"]] == [999]


async def test_progressive_wave_screening_stops_early_and_matches_full_scan():
    """With 80 coherent markets and limit=20, wave screening loads <=60 markets across 1 fleet query and matches full scan."""
    now = _ts_now()
    stale = now - timedelta(days=90)
    team = SimpleNamespace(
        id=1,
        name="Boston Celtics",
        sport_id=1,
        espn_id="2",
        logo_url_small=None,
        logo_url=None,
        primary_color=None,
        alternate_names=None,
        roster_players=None,
    )
    # 80 markets: first 2 are stopped boards, remaining 78 are live coherent boards ordered by prob desc
    markets = []
    for i in range(80):
        prob = round(0.95 - i * 0.01, 4)
        stamp = stale if i < 2 else now
        m = _market(
            5000 + i,
            f"Celtics Prop {i}",
            [
                _outcome(6000 + i, 5000 + i, "Boston Celtics", prob, stamp=stamp, team_id=1),
                _outcome(7000 + i, 5000 + i, "Other Club", round(1.0 - prob, 4), stamp=stamp, team_id=None, rank=2),
            ],
            updated_at=stamp,
            source="kalshi",
        )
        markets.append(m)

    fk_rows = [(m.outcomes[0], m, "basketball_nba") for m in markets]

    # Run with production _SCREEN_WAVE_SIZE (60)
    db_wave, sql_wave, wave_calls = _build_pg_session(
        teams=[team], fk_rows=fk_rows, markets=markets, fleet_stamp=now
    )
    res_wave = await user_route._query_team_futures([1], db_wave, limit=20)

    # Compare against forced full scan (_SCREEN_WAVE_SIZE=10000)
    db_full, _, _ = _build_pg_session(
        teams=[team], fk_rows=fk_rows, markets=markets, fleet_stamp=now
    )
    orig_wave_size = getattr(user_route, "_SCREEN_WAVE_SIZE", 10000)
    assert len(wave_calls) == 1
    assert len(wave_calls[0]) <= 60
    assert len(res_wave["items"]) == 20
    try:
        if hasattr(user_route, "_SCREEN_WAVE_SIZE"):
            user_route._SCREEN_WAVE_SIZE = 10000
        res_full = await user_route._query_team_futures([1], db_full, limit=20)
    finally:
        if hasattr(user_route, "_SCREEN_WAVE_SIZE"):
            user_route._SCREEN_WAVE_SIZE = orig_wave_size

    assert res_wave == res_full
    # Stopped boards 5000, 5001 were withheld and skipped
    served_ids = {it["market_id"] for it in res_wave["items"]}
    assert 5000 not in served_ids and 5001 not in served_ids
    # Multi-wave scenario: lower wave temporarily to 30 to force 2 waves & verify 1 fleet query
    db_multi, sql_multi, multi_calls = _build_pg_session(
        teams=[team], fk_rows=fk_rows, markets=markets, fleet_stamp=now
    )
    try:
        if hasattr(user_route, "_SCREEN_WAVE_SIZE"):
            user_route._SCREEN_WAVE_SIZE = 30
        res_multi = await user_route._query_team_futures([1], db_multi, limit=50)
    finally:
        if hasattr(user_route, "_SCREEN_WAVE_SIZE"):
            user_route._SCREEN_WAVE_SIZE = orig_wave_size

    assert len(multi_calls) == 2
    assert len(res_multi["items"]) == 50
    fleet_multi = [s for s in sql_multi if "max(futures_outcomes.last_updated)" in s]
    assert len(fleet_multi) <= 1


async def test_route_cache_keyed_by_limit_and_coalesces_concurrent_requests():
    """Cache must isolate limit=20 vs limit=100 and singleflight must coalesce overlapping identical calls."""
    user_route._team_futures_cache.clear()
    if hasattr(user_route, "_shared_team_futures_cache"):
        user_route._shared_team_futures_cache.clear()

    class _FavDB:
        async def execute(self, *_a, **_k):
            return _result([(1,), (2,)])

    fake_db = _FavDB()
    fake_user = SimpleNamespace(id=4242)
    query_calls = 0

    async def _fake_query(team_ids, db, *, limit: int = 20, timings: dict | None = None):
        nonlocal query_calls
        query_calls += 1
        await asyncio.sleep(0.02)
        items = [{"market_id": 100 + i, "probability": 0.5} for i in range(limit)]
        return {"items": items, "teams": [], "team_ids": list(team_ids), "total_count": len(items)}

    with patch.object(user_route, "_query_team_futures", _fake_query):
        # Two concurrent /api/me/team-futures?limit=20 coalesce to 1 DB query
        r1, r2 = await asyncio.gather(
            user_route.get_team_futures(limit=20, user=fake_user, db=fake_db),
            user_route.get_team_futures(limit=20, user=fake_user, db=fake_db),
        )
        assert query_calls == 1
        assert len(r1["items"]) == 20 and len(r2["items"]) == 20

        # Same user asking limit=100 does NOT get poisoned by the cached limit=20 payload
        r_100 = await user_route.get_team_futures(limit=100, user=fake_user, db=fake_db)
        assert query_calls == 2
        assert len(r_100["items"]) == 100

        # Concurrent /api/shared/team-futures also singleflight & isolate by limit
        query_calls = 0
        s1, s2 = await asyncio.gather(
            user_route.get_shared_team_futures(team_ids="1,2", limit=10, db=fake_db),
            user_route.get_shared_team_futures(team_ids="2,1", limit=10, db=fake_db),
        )
        assert query_calls == 1
        assert len(s1["items"]) == 10 and len(s2["items"]) == 10

        s_50 = await user_route.get_shared_team_futures(team_ids="1,2", limit=50, db=fake_db)
        assert query_calls == 2
        assert len(s_50["items"]) == 50


async def test_wave_timeout_keeps_screened_omits_unscreened_logs_and_skips_cache(caplog):
    """When wave 2 times out, wave 1 screened markets stay, wave 2+ unscreened are omitted, timeout+count are logged, and routes never cache incomplete answers."""
    now = _ts_now()
    user_route._team_futures_cache.clear()
    user_route._shared_team_futures_cache.clear()
    team = SimpleNamespace(
        id=1,
        name="Boston Celtics",
        sport_id=1,
        espn_id="2",
        logo_url_small=None,
        logo_url=None,
        primary_color=None,
        alternate_names=None,
        roster_players=None,
    )
    markets = [
        _market(
            8000 + i,
            f"Celtics Market {i}",
            [
                _outcome(9000 + i, 8000 + i, "Boston Celtics", round(0.9 - i * 0.01, 4), stamp=now, team_id=1),
                _outcome(9500 + i, 8000 + i, "Other Club", round(0.1 + i * 0.01, 4), stamp=now, team_id=None, rank=2),
            ],
            updated_at=now,
            source="kalshi",
        )
        for i in range(40)
    ]
    fk_rows = [(m.outcomes[0], m, "basketball_nba") for m in markets]

    orig_wave_size = user_route._SCREEN_WAVE_SIZE
    call_num = 0

    async def _timeout_on_wave2(_db, screen_markets):
        nonlocal call_num
        call_num += 1
        if call_num == 2:
            raise QueryCanceledError("canceling statement due to statement timeout")
        return {m.id: set() for m in screen_markets}

    db_t, _, _ = _build_pg_session(teams=[team], fk_rows=fk_rows, markets=markets, fleet_stamp=now)
    timings: dict = {}
    caplog.set_level(logging.WARNING)
    try:
        user_route._SCREEN_WAVE_SIZE = 15
        with patch("app.routes.futures.withheld_price_outcome_ids_for_markets", _timeout_on_wave2):
            res = await user_route._query_team_futures([1], db_t, limit=40, timings=timings)
    finally:
        user_route._SCREEN_WAVE_SIZE = orig_wave_size

    # Wave 1 screened top 15 markets; wave 2 timed out -> 15 kept, 25 omitted.
    assert [it["market_id"] for it in res["items"]] == [8000 + i for i in range(15)]
    assert timings["screen_incomplete"] is True
    assert timings["screen_unscreened"] == 25
    assert timings["screen_waves"] == 2
    assert any("timed out" in rec.message and "25 unscreened" in rec.message for rec in caplog.records)

    # Route endpoints never cache an answer whose screen failed/timed out.
    class _FavAndPgDB:
        async def execute(self, stmt, *a, **k):
            sql = str(stmt)
            if "user_favorites" in sql:
                return _result([(1,)])
            return await db_t.execute(stmt, *a, **k)

        async def begin_nested(self):
            return await db_t.begin_nested()

        def get_bind(self):
            return db_t.get_bind()

    fake_user = SimpleNamespace(id=7771)
    fav_db = _FavAndPgDB()
    exec_count = 0

    # Directly verify via route-level spy returning screen_incomplete=True
    async def _incomplete_query(team_ids, db, *, limit=20, timings=None):
        nonlocal exec_count
        exec_count += 1
        if timings is not None:
            timings["screen_incomplete"] = True
        return {"items": [{"market_id": 8000, "probability": 0.9}], "teams": [], "team_ids": [1], "total_count": 1}

    with patch.object(user_route, "_query_team_futures", _incomplete_query):
        await user_route.get_team_futures(limit=20, user=fake_user, db=fav_db)
        await user_route.get_team_futures(limit=20, user=fake_user, db=fav_db)
        assert exec_count == 2
        await user_route.get_shared_team_futures(team_ids="1", limit=20, db=fav_db)
        await user_route.get_shared_team_futures(team_ids="1", limit=20, db=fav_db)
        assert exec_count == 4


async def test_caller_transaction_isolated_on_normal_return_and_query_timeout():
    """Caller's statement_timeout and transaction health survive BOTH normal return and Query 1 timeout."""
    from sqlalchemy import text as sa_text

    now = _ts_now()
    user_route._award_outcomes_cache.clear()
    team = SimpleNamespace(
        id=1,
        name="Boston Celtics",
        sport_id=1,
        espn_id="2",
        logo_url_small=None,
        logo_url=None,
        primary_color=None,
        alternate_names=None,
        roster_players=None,
    )
    o = _outcome(101, 1001, "Boston Celtics", 0.28, stamp=now, team_id=1)
    m = _market(1001, "NBA Championship Winner", [o], updated_at=now)

    # (a) Normal return restores caller's previous statement_timeout and allows subsequent SQL
    db_ok, _, _ = _build_pg_session(
        teams=[team], fk_rows=[(o, m, "basketball_nba")], markets=[m], initial_timeout="30s"
    )
    res = await user_route._query_team_futures([1], db_ok, limit=20)
    assert len(res["items"]) == 1
    assert db_ok._pg_state["timeout"] == "30s"
    assert db_ok._pg_state["aborted"] is False
    assert (await db_ok.execute(sa_text("SELECT 1"))).scalar_one_or_none() == 1

    # (b) Query 1 timeout rolls back outer savepoint, restores timeout, and leaves caller tx usable
    db_to, _, _ = _build_pg_session(
        teams=[team], fk_rows=[], markets=[m], initial_timeout="30s", fail_q1_timeout=True
    )
    with pytest.raises(QueryCanceledError):
        await user_route._query_team_futures([1], db_to, limit=20)
    assert db_to._pg_state["aborted"] is False
    assert db_to._pg_state["timeout"] == "30s"
    assert (await db_to.execute(sa_text("SELECT 1"))).scalar_one_or_none() == 1


async def test_award_cache_limits_total_route_cache_age_to_120s():
    """Route cache expires from the Award cache's own fetch time so award age never reaches 180s."""
    user_route._team_futures_cache.clear()
    user_route._award_outcomes_cache.clear()
    fake_user = SimpleNamespace(id=5151)

    class _FavDB:
        async def execute(self, *_a, **_k):
            return _result([(1,)])

    fake_db = _FavDB()
    award_fetched_at = time.time() - 55.0

    async def _query_with_aged_award(team_ids, db, *, limit=20, timings=None):
        if timings is not None:
            timings["_award_cached_at"] = award_fetched_at
        return {"items": [{"market_id": 1, "probability": 0.4}], "teams": [], "team_ids": [1], "total_count": 1}

    with patch.object(user_route, "_query_team_futures", _query_with_aged_award):
        await user_route.get_team_futures(limit=20, user=fake_user, db=fake_db)

    scope = user_route._cache_scope_key(fake_db)
    stored_ts, _ = user_route._team_futures_cache[(scope, fake_user.id, 20)]
    assert stored_ts <= award_fetched_at + 1e-6
    # 70s later (125s since award snapshot was fetched, only 70s since route cached): expired!
    assert user_route._cache_get(user_route._team_futures_cache, (scope, fake_user.id, 20), award_fetched_at + 125.0) is None
