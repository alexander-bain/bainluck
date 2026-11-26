"""#13762 — Tests for team futures Part 2 (`q2` pre-filter, shared L1+Redis caches, wave deferral)."""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy import text

from app.models.models import FuturesMarket, FuturesOutcome, Sport, Team
from app.routes import futures as futures_route
from app.routes import prop_families as prop_families_route
from app.routes import user as user_route
from app.services.database import Base
from app.utils import open_futures_outcomes as ofo_mod
from app.utils import request_cache, team_futures_shared_cache as tf_cache

pytestmark = pytest.mark.asyncio


class _FakePipeline:
    def __init__(self, store: "_FakeAsyncRedis"):
        self._store = store
        self._ops: list[tuple[str, int, str]] = []

    def setex(self, key: str, ttl: int, value: str) -> "_FakePipeline":
        self._ops.append((key, ttl, value))
        return self

    async def execute(self) -> list[bool]:
        for key, ttl, value in self._ops:
            await self._store.setex(key, ttl, value)
        return [True] * len(self._ops)


class _FakeAsyncRedis:
    """Minimal in-memory async Redis stand-in supporting get, setex, mget, and pipeline."""

    def __init__(self) -> None:
        self.data: dict[str, bytes] = {}
        self.ttls: dict[str, int] = {}
        self.get_calls: list[str] = []
        self.mget_calls: list[list[str]] = []

    async def get(self, key: str) -> bytes | None:
        self.get_calls.append(key)
        return self.data.get(key)

    async def setex(self, key: str, ttl: int, value: str | bytes) -> bool:
        raw = value.encode("utf-8") if isinstance(value, str) else value
        self.data[key] = raw
        self.ttls[key] = int(ttl)
        return True

    async def mget(self, keys: list[str]) -> list[bytes | None]:
        self.mget_calls.append(list(keys))
        return [self.data.get(k) for k in keys]

    def pipeline(self, transaction: bool = False) -> _FakePipeline:
        del transaction
        return _FakePipeline(self)


def _scalar_result(rows: list, scalar=None):
    res = MagicMock()
    res.all.return_value = list(rows)
    sc = MagicMock()
    sc.all.return_value = list(rows)
    res.scalars.return_value = sc
    res.scalar_one_or_none.return_value = scalar
    return res


def _fake_real_pg_db(execute_fn) -> AsyncSession:
    db = MagicMock(spec=AsyncSession)
    fake_bind = SimpleNamespace(dialect=postgresql.dialect(), pool=object())
    db.get_bind.return_value = fake_bind
    db.execute = execute_fn

    async def _begin_nested():
        sp = MagicMock()

        async def _noop():
            return None

        sp.commit = _noop
        sp.rollback = _noop
        return sp

    db.begin_nested = _begin_nested
    return db


def _make_team_row(tid: int, *, sport_id: int = 1, sport_key: str = "basketball_nba") -> tuple:
    t = SimpleNamespace(
        id=tid,
        sport_id=sport_id,
        name="Boston Celtics",
        logo_url=None,
        espn_id="2",
        primary_color="#007A33",
        logo_url_small=None,
        alternate_names=None,
        roster_players=["Jayson Tatum"],
    )
    return (t, sport_key)


def _make_outcome(
    oid: int,
    mid: int,
    name: str,
    prob: float | Decimal,
    *,
    team_id: int | None,
    stamp: datetime,
) -> SimpleNamespace:
    p = float(prob)
    return SimpleNamespace(
        id=oid,
        market_id=mid,
        external_id=f"EXT-O-{mid}-{oid}",
        name=name,
        team_id=team_id,
        current_probability=prob,
        probability_change_24h=0.0,
        current_yes_bid=max(0.01, p - 0.01),
        current_yes_ask=min(0.99, p + 0.01),
        rank=1,
        is_winner=False,
        resolution_source=None,
        last_updated=stamp,
        volume_24h=250.0,
        volume_24h_at=stamp,
    )


def _make_market(
    mid: int,
    name: str,
    *,
    source: str = "polymarket",
    sport_id: int = 1,
    event_id: int | None = None,
    stamp: datetime,
    res_date: datetime | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=mid,
        source=source,
        external_id=f"{source.upper()}-{mid}",
        sport_id=sport_id,
        event_id=event_id,
        name=name,
        llm_sport_category="basketball",
        market_tier=1,
        market_type="championship",
        status="open",
        resolution_date=res_date,
        canonical_market_key=f"winner_{mid}",
        market_metadata=None,
        updated_at=stamp,
    )


def _extract_bind_ints(compiled) -> list[int]:
    out: list[int] = []
    for val in compiled.params.values():
        if isinstance(val, int) and not isinstance(val, bool):
            out.append(val)
        elif isinstance(val, (list, tuple, set)):
            for item in val:
                if isinstance(item, int) and not isinstance(item, bool):
                    out.append(item)
    return sorted(out)


def _route_pg_sql(
    *,
    teams: list | None = None,
    fk_market_ids: list[int] | None = None,
    q1_rows: list | None = None,
    award_market_ids: list[int] | None = None,
    q2_rows: list | None = None,
    wave_markets: dict[int, tuple] | None = None,
    wave_outcomes: dict[int, list[tuple]] | None = None,
    stats_rows: dict[int, tuple[int, float | None]] | None = None,
    stats_recorder: list[list[int]] | None = None,
    sql_log: list[str] | None = None,
    fleet_now: datetime,
):
    """Build a single shared SQL responder for fake real-PG AsyncSessions."""
    wave_markets = wave_markets or {}
    wave_outcomes = wave_outcomes or {}
    stats_rows = stats_rows or {}

    async def _execute(stmt, *_a, **_k):
        if hasattr(stmt, "compile") and not isinstance(stmt, str):
            try:
                compiled = stmt.compile(dialect=postgresql.dialect())
                raw_sql = str(compiled)
            except Exception:
                compiled = None
                raw_sql = str(stmt)
        else:
            compiled = None
            raw_sql = str(stmt)
        if sql_log is not None:
            sql_log.append(raw_sql)
        low = raw_sql.lower()
        if "show statement_timeout" in low:
            return _scalar_result([], scalar="30s")
        if "set local statement_timeout" in low or "set_config" in low:
            return _scalar_result([])
        if "from teams" in low:
            return _scalar_result(teams or [_make_team_row(100)])
        # Wave loaders MUST be matched before open-market ID filters (`SELECT futures_markets.id ...`).
        if "from futures_markets" in low and "futures_markets.id in" in low and compiled is not None:
            wids = _extract_bind_ints(compiled)
            return _scalar_result([wave_markets[mid] for mid in wids if mid in wave_markets])
        if "from futures_outcomes" in low and "futures_outcomes.market_id in" in low and "group by" not in low and compiled is not None:
            wids = _extract_bind_ints(compiled)
            rows = []
            for mid in wids:
                rows.extend(wave_outcomes.get(mid, ()))
            return _scalar_result(rows)
        if "group by futures_outcomes.market_id" in low and compiled is not None:
            mids_in = _extract_bind_ints(compiled)
            if stats_recorder is not None:
                stats_recorder.append(mids_in)
            return _scalar_result([(mid, *stats_rows[mid]) for mid in mids_in if mid in stats_rows])
        if "with fk_hits" in low:
            return _scalar_result(q1_rows or [])
        if "with ofo_hits" in low or "with tail_scan" in low:
            return _scalar_result([])
        if "select futures_markets.id" in low and "futures_markets.name ilike any" in low:
            return _scalar_result(award_market_ids or [])
        if "select futures_markets.id" in low:
            return _scalar_result(fk_market_ids or [])
        if "futures_outcomes.market_id = any" in low:
            return _scalar_result(q2_rows or [])
        if "ilike any" in low:
            return _scalar_result([])
        if "max(futures_outcomes.last_updated)" in low:
            return _scalar_result([], scalar=fleet_now)
        if "from futures_odds_snapshots" in low:
            return _scalar_result([])
        return _scalar_result([])

    return _execute


async def _coro_val(val):
    return val


@pytest.fixture(autouse=True)
def _clean_part2_caches(monkeypatch):
    user_route._award_outcomes_cache.clear()
    user_route._team_futures_cache.clear()
    user_route._shared_team_futures_cache.clear()
    tf_cache.clear_team_futures_shared_cache()
    request_cache._reset_shared_client_for_tests()
    monkeypatch.setattr(ofo_mod, "open_outcomes_floor", lambda: None)
    yield
    user_route._award_outcomes_cache.clear()
    user_route._team_futures_cache.clear()
    user_route._shared_team_futures_cache.clear()
    tf_cache.clear_team_futures_shared_cache()
    request_cache._reset_shared_client_for_tests()


async def test_q2_shared_redis_round_trip_and_expiry(monkeypatch):
    fake_redis = _FakeAsyncRedis()
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:56379/0")
    monkeypatch.setattr(tf_cache, "get_shared_async_redis", lambda: _coro_val(fake_redis))

    res_dt = datetime(2027, 6, 30, 12, 0, tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    o = _make_outcome(101, 201, "Jayson Tatum", Decimal("0.28"), team_id=None, stamp=now)
    m = _make_market(201, "NBA MVP", event_id=77, stamp=now, res_date=res_dt)
    written_ts = time.time()

    await tf_cache.write_award_outcomes_cache(1, written_ts, [(o, m, "basketball_nba")])
    assert fake_redis.ttls[tf_cache._AWARD_Q2_L2_KEY] == 60

    loaded = await tf_cache.read_award_outcomes_cache(1)
    assert loaded is not None
    ts_back, rows_back = loaded
    assert ts_back == pytest.approx(written_ts)
    assert len(rows_back) == 1
    o_b, m_b, sk_b = rows_back[0]
    assert sk_b == "basketball_nba"
    assert o_b.id == 101 and o_b.current_probability == pytest.approx(0.28)
    assert m_b.id == 201 and m_b.event_id == 77
    assert m_b.resolution_date == res_dt

    monkeypatch.setattr(tf_cache.time, "time", lambda: written_ts + 61.0)
    assert await tf_cache.read_award_outcomes_cache(1) is None


async def test_stats_and_screen_ttl_split_remaining_l1_cap_and_bool_guard(monkeypatch):
    fake_redis = _FakeAsyncRedis()
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:56379/0")
    monkeypatch.setattr(tf_cache, "get_shared_async_redis", lambda: _coro_val(fake_redis))

    now_wall = 1_800_000_000.0
    now_mono = 100.0
    monkeypatch.setattr(tf_cache.time, "time", lambda: now_wall)
    monkeypatch.setattr(tf_cache.time, "monotonic", lambda: now_mono)

    await tf_cache.write_market_stats_and_screen(
        1,
        stats_entries={10: (30, 1.01, now_wall), 20: (2, 1.0, now_wall)},
        screen_entries={10: ({1001}, now_wall), 20: (set(), now_wall)},
        ttl_by_mid={10: 60.0, 20: 15.0},
    )
    assert fake_redis.ttls["team_futures:mkt_stats:v1:10"] == 60
    assert fake_redis.ttls["team_futures:mkt_screen:v1:10"] == 60
    assert fake_redis.ttls["team_futures:mkt_stats:v1:20"] == 15
    assert fake_redis.ttls["team_futures:mkt_screen:v1:20"] == 15

    tf_cache.clear_team_futures_shared_cache()
    now_wall = 1_800_000_010.0
    now_mono = 110.0
    stats_hits, screen_hits = await tf_cache.read_market_stats_and_screen(
        2, [10, 20], include_screen=True
    )
    assert set(stats_hits) == {10, 20}
    assert set(screen_hits) == {10, 20}
    assert len(fake_redis.mget_calls) == 1

    now_wall = 1_800_000_016.0
    now_mono = 116.0
    fake_redis.data.pop("team_futures:mkt_stats:v1:20")
    fake_redis.data.pop("team_futures:mkt_screen:v1:20")
    stats_hits2, screen_hits2 = await tf_cache.read_market_stats_and_screen(
        2, [10, 20], include_screen=True
    )
    assert set(stats_hits2) == {10}
    assert set(screen_hits2) == {10}

    tf_cache.clear_team_futures_shared_cache()
    fake_redis.data["team_futures:mkt_stats:v1:99"] = json.dumps([True, 1.0, now_wall, 60.0]).encode()
    fake_redis.data["team_futures:mkt_stats:v1:98"] = json.dumps([5, False, now_wall, 60.0]).encode()
    bad_stats, _ = await tf_cache.read_market_stats_and_screen(3, [99, 98], include_screen=False)
    assert bad_stats == {}


async def test_q2_two_step_uses_shared_redis_across_workers_and_propagates_age(monkeypatch):
    fake_redis = _FakeAsyncRedis()
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:56379/0")
    monkeypatch.setattr(tf_cache, "get_shared_async_redis", lambda: _coro_val(fake_redis))

    now = datetime.now(timezone.utc)
    award_market = _make_market(501, "NBA MVP 2026", stamp=now)
    award_outcome = _make_outcome(5001, 501, "Jayson Tatum", 0.35, team_id=None, stamp=now)
    executed_sqls: list[str] = []

    db = _fake_real_pg_db(
        _route_pg_sql(
            award_market_ids=[501],
            q2_rows=[(award_outcome, award_market, "basketball_nba")],
            wave_markets={
                501: (501, "polymarket", "PM-501", 1, None, "championship", None, now, "NBA MVP 2026")
            },
            wave_outcomes={
                501: [(5001, 501, 0.35, 0.34, 0.36, None, False, 250.0, now, now)]
            },
            sql_log=executed_sqls,
            fleet_now=now,
        )
    )
    t1: dict = {}
    res1 = await user_route._query_team_futures([100], db, limit=20, timings=t1)
    assert len(res1["items"]) == 1
    assert res1["items"][0]["total_outcomes"] == 1
    assert any("SELECT futures_markets.id" in s and "ILIKE ANY" in s for s in executed_sqls)
    assert any("futures_outcomes.market_id = ANY" in s for s in executed_sqls)
    assert tf_cache._AWARD_Q2_L2_KEY in fake_redis.data

    first_ts = t1["_award_cached_at"]
    user_route._award_outcomes_cache.clear()
    tf_cache.clear_team_futures_shared_cache()
    executed_sqls.clear()
    t2: dict = {}
    res2 = await user_route._query_team_futures([100], db, limit=20, timings=t2)
    assert res2 == res1
    assert not any("futures_markets.name ilike any" in s.lower() for s in executed_sqls)
    assert t2["screen_waves"] == 0
    assert t2["_award_cached_at"] == pytest.approx(first_ts)


async def test_monkeypatch_guard_bypasses_screen_cache_on_real_pg(monkeypatch):
    fake_redis = _FakeAsyncRedis()
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:56379/0")
    monkeypatch.setattr(tf_cache, "get_shared_async_redis", lambda: _coro_val(fake_redis))

    now = datetime.now(timezone.utc)
    await tf_cache.write_market_stats_and_screen(
        1,
        stats_entries={701: (2, 1.0, time.time())},
        screen_entries={701: (set(), time.time())},
        ttl_by_mid={701: 60.0},
    )

    m701 = _make_market(701, "NBA Championship", stamp=now)
    o7001 = _make_outcome(7001, 701, "Boston Celtics", 0.25, team_id=100, stamp=now)
    patched_called: list[list[int]] = []

    async def fake_withheld_prices(db, markets):
        del db
        patched_called.append([m.id for m in markets])
        return {m.id: {7001} for m in markets}

    monkeypatch.setattr(futures_route, "withheld_price_outcome_ids_for_markets", fake_withheld_prices)

    db = _fake_real_pg_db(
        _route_pg_sql(
            fk_market_ids=[701],
            q1_rows=[(o7001, m701, "basketball_nba")],
            wave_markets={
                701: (701, "polymarket", "PM-701", 1, None, "championship", None, now, "NBA Championship")
            },
            wave_outcomes={
                701: [(7001, 701, 0.25, 0.24, 0.26, None, False, 250.0, now, now)]
            },
            fleet_now=now,
        )
    )
    res = await user_route._query_team_futures([100], db, limit=20)
    assert patched_called == [[701]]
    assert res["items"] == []

    # Also verify monkeypatching _board_staleness_withheld alone bypasses screen cache cleanly.
    user_route._award_outcomes_cache.clear()
    tf_cache.clear_team_futures_shared_cache()
    monkeypatch.undo()
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:56379/0")
    monkeypatch.setattr(tf_cache, "get_shared_async_redis", lambda: _coro_val(fake_redis))
    monkeypatch.setattr(ofo_mod, "open_outcomes_floor", lambda: None)
    stale_called: list[int] = []

    async def fake_staleness(db_s, market, **kw):
        del db_s, kw
        stale_called.append(market.id)
        return {o.id for o in market.outcomes}

    monkeypatch.setattr(prop_families_route, "_board_staleness_withheld", fake_staleness)
    res_stale = await user_route._query_team_futures([100], db, limit=20)
    assert stale_called == [701]
    assert res_stale["items"] == []


async def test_soundness_guard_skips_caching_poison_market(monkeypatch):
    fake_redis = _FakeAsyncRedis()
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:56379/0")
    monkeypatch.setattr(tf_cache, "get_shared_async_redis", lambda: _coro_val(fake_redis))

    now = datetime.now(timezone.utc)
    m801 = _make_market(801, "NBA Championship", source="polymarket", stamp=now)
    o8001 = _make_outcome(8001, 801, "Boston Celtics", 0.20, team_id=100, stamp=now)

    db = _fake_real_pg_db(
        _route_pg_sql(
            fk_market_ids=[801],
            q1_rows=[(o8001, m801, "basketball_nba")],
            wave_markets={
                801: (801, "polymarket", "PM-801", 1, None, "championship", None, now, "NBA Championship")
            },
            wave_outcomes={
                801: [
                    (8001, 801, 0.20, 0.19, 0.21, None, False, 250.0, now, now),
                    (8002, 801, 0.20, "not-a-number", 0.21, None, False, 250.0, now, now),
                ]
            },
            fleet_now=now,
        )
    )
    res = await user_route._query_team_futures([100], db, limit=20)
    assert len(res["items"]) == 1
    assert "team_futures:mkt_stats:v1:801" in fake_redis.data
    assert "team_futures:mkt_screen:v1:801" not in fake_redis.data


async def test_multi_wave_deferral_skips_unneeded_non_kalshi_stats_and_patches_survivors(monkeypatch):
    fake_redis = _FakeAsyncRedis()
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:56379/0")
    monkeypatch.setattr(tf_cache, "get_shared_async_redis", lambda: _coro_val(fake_redis))

    now = datetime.now(timezone.utc)
    all_mids = list(range(9001, 9066)) + [9901, 9902]
    q1_rows = []
    wave_markets: dict[int, tuple] = {}
    wave_outcomes: dict[int, list[tuple]] = {}
    stats_rows: dict[int, tuple[int, float | None]] = {}

    for idx, mid in enumerate(range(9001, 9066)):
        prob = 0.90 - idx * 0.005
        m = _make_market(mid, f"PM Futures {mid}", source="polymarket", stamp=now)
        o = _make_outcome(mid * 10 + 1, mid, "Boston Celtics", prob, team_id=100, stamp=now)
        q1_rows.append((o, m, "basketball_nba"))
        wave_markets[mid] = (mid, "polymarket", f"PM-{mid}", 1, None, "championship", None, now, f"PM Futures {mid}")
        wave_outcomes[mid] = [
            (mid * 10 + 1, mid, prob, prob - 0.01, prob + 0.01, None, False, 250.0, now, now),
            (mid * 10 + 2, mid, 1.0 - prob, 0.1, 0.2, None, False, 250.0, now, now),
        ]
        stats_rows[mid] = (7, 1.0)
    for mid in (9901, 9902):
        m = _make_market(mid, f"Kalshi Futures {mid}", source="kalshi", stamp=now)
        o = _make_outcome(mid * 10 + 1, mid, "Boston Celtics", 0.10, team_id=100, stamp=now)
        q1_rows.append((o, m, "basketball_nba"))
        wave_markets[mid] = (mid, "kalshi", f"KX-{mid}", 1, None, "championship", None, now, f"Kalshi Futures {mid}")
        wave_outcomes[mid] = [
            (mid * 10 + 1, mid, 0.10, 0.09, 0.11, None, False, 250.0, now, now),
        ]
        stats_rows[mid] = (1, 0.10)

    stats_query_binds: list[list[int]] = []
    db = _fake_real_pg_db(
        _route_pg_sql(
            fk_market_ids=all_mids,
            q1_rows=q1_rows,
            wave_markets=wave_markets,
            wave_outcomes=wave_outcomes,
            stats_rows=stats_rows,
            stats_recorder=stats_query_binds,
            fleet_now=now,
        )
    )
    t1: dict = {}
    res = await user_route._query_team_futures([100], db, limit=1, timings=t1)
    assert len(res["items"]) == 1
    assert res["items"][0]["market_id"] == 9001
    assert res["items"][0]["total_outcomes"] == 2
    assert t1["screen_waves"] == 1
    assert stats_query_binds == [[9901, 9902]]

    # Screen cache hit + stats cache miss -> tiny fallback SQL fetches only surviving 9001.
    user_route._award_outcomes_cache.clear()
    tf_cache.clear_team_futures_shared_cache()
    fake_redis.data.pop("team_futures:mkt_stats:v1:9001", None)
    stats_query_binds.clear()
    res2 = await user_route._query_team_futures([100], db, limit=1)
    assert res2["items"][0]["market_id"] == 9001
    assert res2["items"][0]["total_outcomes"] == 7
    assert stats_query_binds[-1] == [9001]


_PG_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")


@pytest.mark.skipif(not _PG_URL, reason="set SEARCH_TEST_DATABASE_URL for real-PG #13762 Part 2 check")
async def test_real_pg_q2_two_step_and_shared_cache_roundtrip(monkeypatch):
    engine = create_async_engine(_PG_URL)  # type: ignore[arg-type]
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    fake_redis = _FakeAsyncRedis()
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:56379/0")
    monkeypatch.setattr(tf_cache, "get_shared_async_redis", lambda: _coro_val(fake_redis))

    now = datetime.now(timezone.utc)
    try:
        async with maker() as db:
            db.add_all([
                Sport(id=1, key="basketball_nba", name="NBA", group="Basketball", active=True),
                Team(
                    id=100,
                    sport_id=1,
                    name="Boston Celtics",
                    slug="boston-celtics",
                    espn_id="2",
                    roster_players=["Jayson Tatum"],
                ),
                FuturesMarket(
                    id=11,
                    source="polymarket",
                    external_id="PM-11",
                    sport_id=1,
                    name="NBA MVP 2026",
                    category="futures",
                    mutually_exclusive=True,
                    llm_sport_category="basketball",
                    market_tier=1,
                    status="open",
                    updated_at=now,
                ),
                FuturesMarket(
                    id=12,
                    source="polymarket",
                    external_id="PM-12",
                    sport_id=1,
                    name="NBA Non Award Board",
                    category="futures",
                    mutually_exclusive=True,
                    llm_sport_category="basketball",
                    market_tier=1,
                    status="resolved",
                    updated_at=now,
                ),
                FuturesOutcome(
                    id=111,
                    market_id=11,
                    external_id="O-111",
                    name="Jayson Tatum",
                    team_id=None,
                    current_probability=0.45,
                    current_yes_bid=0.44,
                    current_yes_ask=0.46,
                    volume_24h=500.0,
                    volume_24h_at=now,
                    last_updated=now,
                ),
            ])
            await db.commit()

            t1: dict = {}
            r1 = await user_route._query_team_futures([100], db, limit=20, timings=t1)
            assert [it["market_id"] for it in r1["items"]] == [11]
            assert r1["items"][0]["total_outcomes"] == 1
            assert tf_cache._AWARD_Q2_L2_KEY in fake_redis.data

            # Clear L1 and confirm L2 hit serves identically with 0 waves.
            user_route._award_outcomes_cache.clear()
            tf_cache.clear_team_futures_shared_cache()
            t2: dict = {}
            r2 = await user_route._query_team_futures([100], db, limit=20, timings=t2)
            assert r2 == r1
            assert t2["screen_waves"] == 0
            assert t2["_award_cached_at"] == pytest.approx(t1["_award_cached_at"])
    finally:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()
