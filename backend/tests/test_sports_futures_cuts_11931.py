"""#11931 — Sports futures stage cuts (two-pass tier query, 60s withheld-trades cache, scoring-loop fast skips).

Live `feed_stage_observability` on a cold Sports list build (`mode=sports`) showed
`futures=2,664 ms` dominated by:
1. `sports_futures.withheld` (940 ms, up to 1.4 s): querying the 51 GB
   `futures_odds_snapshots` table on every cold build for newest venue trade rows.
2. `sports_futures.id_query` (762 ms): single unbounded scan across ~31k Tier 3-5
   sports futures even though `ORDER BY market_tier ASC NULLS LAST, volume_24h
   DESC NULLS LAST, id ASC LIMIT 120` is satisfied by Tier 1-2 rows whenever
   120 Tier 1-2 rows exist.
3. `sports_futures.scoring_loop` (~478 ms): running display-scale and field
   normalization before cheap dead/settled/stale/favorites skips.

This test pins all three cuts, their parity with the uncached/single-pass paths,
the `[]` vs `[None]` vs `[price]` snapshot distinctions, cross-helper cache
isolation between `_newest_kalshi_trades` and `_newest_venue_trade_rows`, Redis L2
fail-open, engine isolation, and kill switches.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy import event as sa_event
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

from app.models.models import (
    Base,
    FuturesMarket,
    FuturesOddsSnapshot,
    FuturesOutcome,
    Sport,
)
from app.routes import feed as feed_route
from app.routes import futures as futures_route
from app.utils import withheld_trades_cache as wtc


@compiles(JSONB, "sqlite")
def _jsonb_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


@compiles(ARRAY, "sqlite")
def _array_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


class _SyncBackedAsyncSession(AsyncSession):
    """Lightweight AsyncSession subclass backed by sync SQLite (no aiosqlite needed).

    Passes `isinstance(db, AsyncSession)` and exposes `.sync_session.get_bind()`
    so `_withheld_trades_engine_key` isolates engines identically to production.
    """

    def __init__(self, sync_session: Session) -> None:
        self._sync = sync_session
        self.sync_session = sync_session

    async def execute(self, statement, *args, **kwargs):
        return self._sync.execute(statement)


class _FakePipeline:
    def __init__(self, store: dict[str, str], ttls: dict[str, int]) -> None:
        self._store = store
        self._ttls = ttls
        self._ops: list[tuple[str, int, str]] = []

    def setex(self, key: str, ttl: int, val: str) -> None:
        self._ops.append((key, ttl, val))

    async def execute(self) -> list[bool]:
        for k, ttl, v in self._ops:
            self._store[k] = v
            self._ttls[k] = ttl
        return [True] * len(self._ops)


class _FakeAsyncRedis:
    def __init__(self, *, fail_mget: bool = False, fail_write: bool = False) -> None:
        self.store: dict[str, str] = {}
        self.ttls: dict[str, int] = {}
        self.mget_calls = 0
        self.fail_mget = fail_mget
        self.fail_write = fail_write

    async def mget(self, keys: list[str]) -> list[str | None]:
        self.mget_calls += 1
        if self.fail_mget:
            raise RuntimeError("redis mget down")
        return [self.store.get(k) for k in keys]

    def pipeline(self, transaction: bool = False) -> _FakePipeline:
        if self.fail_write:
            raise RuntimeError("redis write down")
        return _FakePipeline(self.store, self.ttls)


def _make_db_with_snapshots() -> tuple:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(
        engine,
        tables=[
            FuturesMarket.__table__,
            FuturesOutcome.__table__,
            FuturesOddsSnapshot.__table__,
        ],
    )

    queries: list[str] = []

    @sa_event.listens_for(engine, "before_cursor_execute")
    def _record_sql(_conn, _cursor, statement, _params, _ctx, _many):
        queries.append(statement)

    s = Session(engine, expire_on_commit=False)
    now = datetime(2026, 11, 20, 12, 0, 0, tzinfo=timezone.utc)
    earlier = now - timedelta(hours=1)

    m = FuturesMarket(
        id=1,
        external_id="mkt-1",
        source="kalshi",
        name="Test Championship",
        status="open",
    )
    s.add(m)
    for oid in (10, 11, 12, 13):
        s.add(
            FuturesOutcome(
                id=oid,
                market_id=1,
                external_id=f"out-{oid}",
                name=f"Outcome {oid}",
                current_probability=0.5,
            )
        )
    # 10: two Kalshi rows sharing the newest captured_at (0.40 and 0.60)
    s.add_all(
        [
            FuturesOddsSnapshot(
                outcome_id=10,
                bookmaker="kalshi",
                probability=Decimal("0.50"),
                last_price=Decimal("0.20"),
                captured_at=earlier,
            ),
            FuturesOddsSnapshot(
                outcome_id=10,
                bookmaker="kalshi",
                probability=Decimal("0.50"),
                last_price=Decimal("0.40"),
                captured_at=now,
            ),
            FuturesOddsSnapshot(
                outcome_id=10,
                bookmaker="kalshi",
                probability=Decimal("0.50"),
                last_price=Decimal("0.60"),
                captured_at=now,
            ),
            # 11: no snapshots at all -> `[]`
            # 12: newest capture has last_price=None -> `[None]`
            FuturesOddsSnapshot(
                outcome_id=12,
                bookmaker="kalshi",
                probability=Decimal("0.50"),
                last_price=Decimal("0.30"),
                captured_at=earlier,
            ),
            FuturesOddsSnapshot(
                outcome_id=12,
                bookmaker="kalshi",
                probability=Decimal("0.50"),
                last_price=None,
                captured_at=now,
            ),
            # 13: single polymarket row
            FuturesOddsSnapshot(
                outcome_id=13,
                bookmaker="polymarket",
                probability=Decimal("0.50"),
                last_price=Decimal("0.72"),
                captured_at=now,
            ),
        ]
    )
    s.commit()
    queries.clear()
    return engine, _SyncBackedAsyncSession(s), queries


class TestWithheldTradesCache:
    def setup_method(self):
        wtc.clear_withheld_trades_cache()

    def teardown_method(self):
        wtc.clear_withheld_trades_cache()

    def test_l1_hit_preserves_empty_null_and_multi_row_and_skips_db(self, monkeypatch):
        monkeypatch.setenv("WITHHELD_TRADES_CACHE_ENABLED", "1")
        monkeypatch.setenv("WITHHELD_TRADES_CACHE_SHARED_ENABLED", "0")
        engine, db, queries = _make_db_with_snapshots()
        try:
            async def _run():
                rows1 = await futures_route._newest_venue_trade_rows(
                    db, "kalshi", [10, 11, 12]
                )
                assert len(queries) == 1
                assert sorted(
                    (oid, None if p is None else float(p)) for oid, p in rows1
                ) == [(10, 0.4), (10, 0.6), (12, None)]

                # Second call hits L1 -> zero DB queries, identical rows
                rows2 = await futures_route._newest_venue_trade_rows(
                    db, "kalshi", [10, 11, 12]
                )
                assert len(queries) == 1
                assert sorted(
                    (oid, None if p is None else float(p)) for oid, p in rows2
                ) == [(10, 0.4), (10, 0.6), (12, None)]

                # `_newest_kalshi_trades` reuses raw `"kalshi"` cache with ZERO DB queries
                # and preserves `11` absent, `12: None`, `10: 0.6` (max of tied rows).
                k_dict = await futures_route._newest_kalshi_trades(db, [10, 11, 12])
                assert len(queries) == 1
                assert k_dict == {10: 0.6, 12: None}
                assert 11 not in k_dict

            asyncio.run(_run())
        finally:
            engine.dispose()

    def test_kalshi_max_cache_never_shadows_multi_row_venue_read(self, monkeypatch):
        monkeypatch.setenv("WITHHELD_TRADES_CACHE_ENABLED", "1")
        monkeypatch.setenv("WITHHELD_TRADES_CACHE_SHARED_ENABLED", "0")
        engine, db, queries = _make_db_with_snapshots()
        try:
            async def _run():
                # Populate `"kalshi:max"` FIRST via `_newest_kalshi_trades`
                k1 = await futures_route._newest_kalshi_trades(db, [10, 11, 12])
                assert len(queries) == 1
                assert {
                    k: (None if v is None else float(v)) for k, v in k1.items()
                } == {10: 0.6, 12: None}

                # Repeat `_newest_kalshi_trades` -> hits `"kalshi:max"` L1 (0 new queries)
                k2 = await futures_route._newest_kalshi_trades(db, [10, 11, 12])
                assert len(queries) == 1
                assert k2 == {10: 0.6, 12: None}

                # `_newest_venue_trade_rows` MUST NOT read collapsed `"kalshi:max"`;
                # it queries `"kalshi"` and preserves BOTH tied rows `(10, 0.4)` and `(10, 0.6)`.
                rows = await futures_route._newest_venue_trade_rows(
                    db, "kalshi", [10, 11, 12]
                )
                assert len(queries) == 2
                assert sorted(
                    (oid, None if p is None else float(p)) for oid, p in rows
                ) == [(10, 0.4), (10, 0.6), (12, None)]

            asyncio.run(_run())
        finally:
            engine.dispose()

    def test_redis_l2_roundtrip_and_fail_open(self, monkeypatch):
        monkeypatch.setenv("WITHHELD_TRADES_CACHE_ENABLED", "1")
        monkeypatch.setenv("WITHHELD_TRADES_CACHE_SHARED_ENABLED", "1")
        fake_redis = _FakeAsyncRedis()

        async def _fake_shared():
            return fake_redis

        monkeypatch.setattr(wtc, "_shared_redis", _fake_shared)
        engine, db, queries = _make_db_with_snapshots()
        try:
            async def _run():
                # Cold L1 + L2 -> DB query populates both L1 and L2 with `read_at`
                rows1 = await futures_route._newest_venue_trade_rows(
                    db, "polymarket", [11, 13]
                )
                assert len(queries) == 1
                assert sorted((oid, float(p)) for oid, p in rows1) == [(13, 0.72)]
                entry_11 = json.loads(
                    fake_redis.store["withheld_trades:v2:polymarket:11"]
                )
                entry_13 = json.loads(
                    fake_redis.store["withheld_trades:v2:polymarket:13"]
                )
                assert entry_11["prices"] == []
                assert entry_13["prices"] == [0.72]
                assert isinstance(entry_13["read_at"], float)
                assert fake_redis.ttls["withheld_trades:v2:polymarket:13"] == 60

                # Simulate a second dyno (empty L1) -> hits Redis L2, zero new DB queries
                wtc.clear_withheld_trades_cache()
                rows2 = await futures_route._newest_venue_trade_rows(
                    db, "polymarket", [11, 13]
                )
                assert len(queries) == 1
                assert rows2 == [(13, 0.72)]

                # Redis failure fails open to DB cleanly
                wtc.clear_withheld_trades_cache()
                fake_redis.fail_mget = True
                fake_redis.fail_write = True
                rows3 = await futures_route._newest_venue_trade_rows(
                    db, "polymarket", [11, 13]
                )
                assert len(queries) == 2
                assert sorted((oid, float(p)) for oid, p in rows3) == [(13, 0.72)]

            asyncio.run(_run())
        finally:
            engine.dispose()

    def test_second_process_l2_copy_expires_at_60s_from_db_read_not_copy(
        self, monkeypatch
    ):
        """#13253 review guard: Process B copying from L2 at 59s MUST miss by 61s."""
        monkeypatch.setenv("WITHHELD_TRADES_CACHE_ENABLED", "1")
        monkeypatch.setenv("WITHHELD_TRADES_CACHE_SHARED_ENABLED", "1")
        fake_redis = _FakeAsyncRedis()

        async def _fake_shared():
            return fake_redis

        monkeypatch.setattr(wtc, "_shared_redis", _fake_shared)
        clock = {"wall": 1_763_680_000.0, "mono": 1000.0}
        monkeypatch.setattr(wtc.time, "time", lambda: clock["wall"])
        monkeypatch.setattr(wtc.time, "monotonic", lambda: clock["mono"])

        engine, db, queries = _make_db_with_snapshots()
        try:
            async def _run():
                # t = 0s: Process A reads DB and writes L1 + L2 (read_at = t=0)
                rows_a = await futures_route._newest_venue_trade_rows(
                    db, "polymarket", [13]
                )
                assert len(queries) == 1
                assert sorted((oid, float(p)) for oid, p in rows_a) == [(13, 0.72)]

                # t = 59s: Process B (empty L1) hits L2 and keeps remaining 1s in L1
                clock["wall"] += 59.0
                clock["mono"] += 59.0
                wtc.clear_withheld_trades_cache()
                rows_b59 = await futures_route._newest_venue_trade_rows(
                    db, "polymarket", [13]
                )
                assert len(queries) == 1
                assert rows_b59 == [(13, 0.72)]

                # t = 59.5s: still within the 60s bound from t=0 -> Process B hits L1
                clock["wall"] += 0.5
                clock["mono"] += 0.5
                rows_b595 = await futures_route._newest_venue_trade_rows(
                    db, "polymarket", [13]
                )
                assert len(queries) == 1
                assert rows_b595 == [(13, 0.72)]

                # t = 61s: past 60s from original DB read -> Process B MUST miss
                # both L1 and L2 (even if Redis hasn't evicted the key yet) and
                # re-query the DB.
                clock["wall"] += 1.5
                clock["mono"] += 1.5
                rows_b61 = await futures_route._newest_venue_trade_rows(
                    db, "polymarket", [13]
                )
                assert len(queries) == 2
                assert sorted((oid, float(p)) for oid, p in rows_b61) == [(13, 0.72)]

            asyncio.run(_run())
        finally:
            engine.dispose()

    def test_kill_switch_and_ttl_expiry_and_engine_isolation(self, monkeypatch):
        monkeypatch.setenv("WITHHELD_TRADES_CACHE_SHARED_ENABLED", "0")
        engine1, db1, queries1 = _make_db_with_snapshots()
        engine2, db2, queries2 = _make_db_with_snapshots()
        try:
            async def _run():
                # Kill switch OFF -> every call hits DB
                monkeypatch.setenv("WITHHELD_TRADES_CACHE_ENABLED", "0")
                await futures_route._newest_venue_trade_rows(db1, "polymarket", [13])
                await futures_route._newest_venue_trade_rows(db1, "polymarket", [13])
                assert len(queries1) == 2

                # Kill switch ON + engine isolation
                monkeypatch.setenv("WITHHELD_TRADES_CACHE_ENABLED", "1")
                wtc.clear_withheld_trades_cache()
                await futures_route._newest_venue_trade_rows(db1, "polymarket", [13])
                assert len(queries1) == 3
                # Engine 2 has its own engine_key -> does NOT read Engine 1's L1 entry
                await futures_route._newest_venue_trade_rows(db2, "polymarket", [13])
                assert len(queries2) == 1

                # TTL expiry past 60s re-queries DB
                base_mono = 1000.0
                monkeypatch.setattr(wtc.time, "monotonic", lambda: base_mono)
                wtc.clear_withheld_trades_cache()
                await futures_route._newest_venue_trade_rows(db1, "polymarket", [13])
                assert len(queries1) == 4
                monkeypatch.setattr(wtc.time, "monotonic", lambda: base_mono + 59.0)
                await futures_route._newest_venue_trade_rows(db1, "polymarket", [13])
                assert len(queries1) == 4
                monkeypatch.setattr(wtc.time, "monotonic", lambda: base_mono + 61.0)
                await futures_route._newest_venue_trade_rows(db1, "polymarket", [13])
                assert len(queries1) == 5

            asyncio.run(_run())
        finally:
            engine1.dispose()
            engine2.dispose()


def _make_sports_futures_db(
    *, tier12_count: int, tier35_count: int, include_dead: bool = False
) -> tuple:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(
        engine,
        tables=[
            Sport.__table__,
            FuturesMarket.__table__,
            FuturesOutcome.__table__,
            FuturesOddsSnapshot.__table__,
        ],
    )

    queries: list[str] = []

    @sa_event.listens_for(engine, "before_cursor_execute")
    def _record_sql(_conn, _cursor, statement, _params, _ctx, _many):
        queries.append(statement)

    s = Session(engine, expire_on_commit=False)
    now = datetime.now(timezone.utc)
    future_res = None

    _distinct_nouns = (
        "Super Bowl",
        "AFC Championship",
        "NFC Championship",
        "NFL MVP",
        "Offensive Rookie",
        "Defensive Rookie",
        "Coach of the Year",
        "AFC North",
        "AFC South",
        "AFC East",
        "AFC West",
        "NFC North",
        "NFC South",
        "NFC East",
        "NFC West",
    )

    mid = 1
    oid = 1
    for i in range(tier12_count):
        tier = 1 if i % 2 == 0 else 2
        label = _distinct_nouns[i % len(_distinct_nouns)]
        m = FuturesMarket(
            id=mid,
            external_id=f"nfl-t{tier}-{mid}",
            source="polymarket",
            name=f"{label} Contest {mid}",
            status="open",
            llm_sport_category="football",
            market_tier=tier,
            volume_24h=float(10000 - i),
            resolution_date=future_res,
            market_type="field",
            updated_at=now,
        )
        s.add(m)
        for j, prob in enumerate((0.55, 0.30, 0.15)):
            s.add(
                FuturesOutcome(
                    id=oid,
                    market_id=mid,
                    external_id=f"out-{oid}",
                    name=f"Team {mid}-{j}",
                    current_probability=prob,
                    current_yes_bid=prob - 0.02,
                    current_yes_ask=prob + 0.02,
                    last_updated=now,
                )
            )
            oid += 1
        mid += 1

    for i in range(tier35_count):
        tier = None if i % 3 == 0 else (3 + (i % 3))
        label = _distinct_nouns[(i + 5) % len(_distinct_nouns)]
        m = FuturesMarket(
            id=mid,
            external_id=f"nfl-low-{mid}",
            source="polymarket",
            name=f"{label} Secondary {mid}",
            status="open",
            llm_sport_category="football",
            market_tier=tier,
            volume_24h=float(50000 - i),  # higher volume, lower tier
            resolution_date=future_res,
            market_type="field",
            updated_at=now,
        )
        s.add(m)
        for j, prob in enumerate((0.55, 0.30, 0.15)):
            s.add(
                FuturesOutcome(
                    id=oid,
                    market_id=mid,
                    external_id=f"out-{oid}",
                    name=f"LowTeam {mid}-{j}",
                    current_probability=prob,
                    current_yes_bid=prob - 0.02,
                    current_yes_ask=prob + 0.02,
                    last_updated=now,
                )
            )
            oid += 1
        mid += 1

    if include_dead:
        # Market with an already-decided winner (prob >= 0.995) — should be
        # skipped BEFORE `drop_dominant_field_outcomes`.
        m = FuturesMarket(
            id=mid,
            external_id=f"nfl-dead-{mid}",
            source="polymarket",
            name="NFL Already Decided Future",
            status="open",
            llm_sport_category="football",
            market_tier=1,
            volume_24h=99999.0,
            resolution_date=future_res,
            market_type="field",
            updated_at=now,
        )
        s.add(m)
        s.add(
            FuturesOutcome(
                id=oid,
                market_id=mid,
                external_id=f"out-{oid}",
                name="Winner Team",
                current_probability=0.998,
                is_winner=True,
                resolution_source="api_settlement",
                last_updated=now,
            )
        )
        s.add(
            FuturesOutcome(
                id=oid + 1,
                market_id=mid,
                external_id=f"out-{oid + 1}",
                name="Loser Team",
                current_probability=0.002,
                last_updated=now,
            )
        )
    s.commit()
    queries.clear()
    return engine, _SyncBackedAsyncSession(s), queries


def _patch_scorer_helpers(monkeypatch):
    async def _fake_withheld(_db, markets):
        return {m.id: set() for m in markets}

    async def _fake_out_legs(_db, markets):
        return {m.id: frozenset() for m in markets}

    async def _fake_canonical(_db, keys=None):
        return {}

    async def _fake_team_names(_db, _outcomes):
        return {}

    monkeypatch.setattr(
        futures_route, "withheld_price_outcome_ids_for_markets", _fake_withheld
    )
    monkeypatch.setattr(feed_route, "graded_out_leg_ids_by_market", _fake_out_legs)
    monkeypatch.setattr(feed_route, "_get_canonical_source_counts", _fake_canonical)
    monkeypatch.setattr(feed_route, "_team_names_by_id", _fake_team_names)


def _blank_ctx():
    return SimpleNamespace(
        team_relations={},
        dismissed_events=set(),
        dismissed_markets=set(),
        seen_map={},
        favorite_league_keys=set(),
        boost_weights={},
        user_id=None,
    )


class TestSportsFuturesTwoPassAndScoringLoop:
    def setup_method(self):
        wtc.clear_withheld_trades_cache()

    def teardown_method(self):
        wtc.clear_withheld_trades_cache()

    def _run_score(self, db, *, timing_records: list[dict]):
        now = datetime.now(timezone.utc)
        return feed_route._score_sports_mode_futures(
            db,
            now,
            sport_filter="football",
            ctx=feed_route.PersonalizationContext(),
            my_teams_only=False,
            share_inputs=False,
            timing_records=timing_records,
        )

    def test_two_pass_short_circuits_at_120_and_matches_single_pass_order(
        self, monkeypatch
    ):
        monkeypatch.setenv("WITHHELD_TRADES_CACHE_ENABLED", "0")
        _patch_scorer_helpers(monkeypatch)
        engine, db, queries = _make_sports_futures_db(
            tier12_count=125, tier35_count=20
        )
        try:
            async def _run():
                # Two-pass ON: Pass 1 returns 120 Tier 1-2 rows; Pass 2 MUST NOT run.
                monkeypatch.setenv("SPORTS_FUTURES_TIER_PASS_ENABLED", "1")
                timings_two: list[dict] = []
                queries.clear()
                two_pass_items = await self._run_score(db, timing_records=timings_two)
                id_queries_two = [
                    q
                    for q in queries
                    if "SELECT futures_markets.id" in q
                    and "futures_markets.status =" in q
                ]
                assert len(id_queries_two) == 1
                assert "market_tier IN" in id_queries_two[0]
                assert any(
                    r["stage"] == "sports_futures.scoring_loop" for r in timings_two
                )

                # Single-pass fallback: exact same scored market IDs and order.
                monkeypatch.setenv("SPORTS_FUTURES_TIER_PASS_ENABLED", "0")
                timings_one: list[dict] = []
                queries.clear()
                single_pass_items = await self._run_score(
                    db, timing_records=timings_one
                )
                id_queries_one = [
                    q
                    for q in queries
                    if "SELECT futures_markets.id" in q
                    and "futures_markets.status =" in q
                ]
                assert len(id_queries_one) == 1
                assert "market_tier IN" not in id_queries_one[0]

                assert [x["data"]["id"] for x in two_pass_items] == [
                    x["data"]["id"] for x in single_pass_items
                ]
                assert len(two_pass_items) > 0

            asyncio.run(_run())
        finally:
            engine.dispose()

    def test_two_pass_fills_from_tier_3_plus_and_null_when_under_120(
        self, monkeypatch
    ):
        monkeypatch.setenv("WITHHELD_TRADES_CACHE_ENABLED", "0")
        _patch_scorer_helpers(monkeypatch)
        engine, db, queries = _make_sports_futures_db(tier12_count=5, tier35_count=6)
        try:
            async def _run():
                monkeypatch.setenv("SPORTS_FUTURES_TIER_PASS_ENABLED", "1")
                queries.clear()
                two_pass_items = await self._run_score(db, timing_records=[])
                id_queries_two = [
                    q
                    for q in queries
                    if "SELECT futures_markets.id" in q
                    and "futures_markets.status =" in q
                ]
                assert len(id_queries_two) == 2

                monkeypatch.setenv("SPORTS_FUTURES_TIER_PASS_ENABLED", "0")
                queries.clear()
                single_pass_items = await self._run_score(db, timing_records=[])

                assert [x["data"]["id"] for x in two_pass_items] == [
                    x["data"]["id"] for x in single_pass_items
                ]
                assert len(two_pass_items) == 11

            asyncio.run(_run())
        finally:
            engine.dispose()

    def test_early_skip_avoids_display_scale_work_on_decided_markets(
        self, monkeypatch
    ):
        monkeypatch.setenv("WITHHELD_TRADES_CACHE_ENABLED", "0")
        _patch_scorer_helpers(monkeypatch)

        seen_market_outcomes: list[list[str]] = []
        orig_drop = feed_route.drop_dominant_field_outcomes

        def _spy_drop(outcomes, name_fn, prob_fn):
            seen_market_outcomes.append([name_fn(o) for o in outcomes])
            return orig_drop(outcomes, name_fn, prob_fn)

        monkeypatch.setattr(feed_route, "drop_dominant_field_outcomes", _spy_drop)
        engine, db, _queries = _make_sports_futures_db(
            tier12_count=2, tier35_count=0, include_dead=True
        )
        try:
            async def _run():
                timings: list[dict] = []
                items = await self._run_score(db, timing_records=timings)
                assert len(items) == 2
                # The decided market ("Winner Team" / "Loser Team") was skipped
                # BEFORE `drop_dominant_field_outcomes` ran.
                assert len(seen_market_outcomes) == 2
                assert all("Winner Team" not in names for names in seen_market_outcomes)
                assert any(
                    r["stage"] == "sports_futures.scoring_loop" for r in timings
                )

            asyncio.run(_run())
        finally:
            engine.dispose()
