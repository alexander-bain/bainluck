"""Tests for #13436: per-tournament detail cache, SWR refresh, singleflight,
warmers, non-mutation, and bounded evolution-market snapshot richness selection."""

from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.models import FuturesOddsSnapshot, FuturesOutcome
from app.routes import golf as golf_route
from app.services import get_db
from app.tasks import datagolf as datagolf_task
from app.utils import golf_tournament_cache as cache_mod
from app.utils import request_cache as rc_mod


def _sample_tournament(
    slug: str = "the-rsm-classic", *, status: str = "in-progress", prob: float = 0.25
) -> dict:
    return {
        "name": "The RSM Classic",
        "slug": slug,
        "key": "the_rsm_classic",
        "is_major": False,
        "is_womens": False,
        "is_tour_event": True,
        "start_date": "2026-11-19T00:00:00+00:00",
        "end_date": "2026-11-22T23:59:59+00:00",
        "venue": "Sea Island Golf Club",
        "location": "St. Simons Island, GA",
        "schedule_status": status,
        "commence_time": "2026-11-19T12:00:00+00:00",
        "resolution_date": "2026-11-22T23:59:59+00:00",
        "golfers": [
            {"name": "Tommy Fleetwood", "probability": prob, "sources": {"datagolf": prob}}
        ],
        "market_ids": [],
        "market_names": [],
        "market_sources": ["datagolf"],
        "h2h_matchups": [],
    }


def _sample_detail_payload(
    slug: str = "the-rsm-classic", *, status: str = "in-progress", prob: float = 0.25
) -> dict:
    t = _sample_tournament(slug=slug, status=status, prob=prob)
    return {
        "tournament": {
            "name": t["name"],
            "slug": slug,
            "key": t["key"],
            "is_major": False,
            "is_womens": False,
            "start_date": t["start_date"],
            "end_date": t["end_date"],
            "venue": t["venue"],
            "location": t["location"],
            "schedule_status": status,
            "commence_time": t["commence_time"],
            "resolution_date": t["resolution_date"],
        },
        "golfers": t["golfers"],
        "markets": [],
        "related_futures": [],
        "evolution_market_id": None,
        "biggest_movers": [],
        "h2h_matchups": [],
        "round_top_groups": [],
    }


class _AsyncSessionShim:
    """Minimal async wrapper around sync SQLAlchemy Session for SQLite unit tests."""

    def __init__(self, sync_session: Session) -> None:
        self._sync = sync_session

    async def execute(self, stmt, *args, **kwargs):
        return self._sync.execute(stmt, *args, **kwargs)


def _create_sqlite_golf_session():
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE futures_markets (id INTEGER PRIMARY KEY, source TEXT)"))
    FuturesOutcome.__table__.create(engine)
    FuturesOddsSnapshot.__table__.create(engine)
    sync_session = Session(engine)
    return engine, sync_session


class _FakeSyncRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.ttls: dict[str, int] = {}

    def get(self, key: str):
        return self.store.get(key)

    def set(self, key: str, value: str, ex: int | None = None, nx: bool = False):
        if nx and key in self.store:
            return False
        self.store[key] = value
        if ex is not None:
            self.ttls[key] = ex
        return True

    def pipeline(self, transaction: bool = False):
        return _FakeSyncPipeline(self)


class _FakeSyncPipeline:
    def __init__(self, client: _FakeSyncRedis) -> None:
        self._client = client
        self._ops: list[tuple[str, str, int | None]] = []

    def set(self, key: str, value: str, ex: int | None = None):
        self._ops.append((key, value, ex))
        return self

    def execute(self):
        for k, v, ex in self._ops:
            self._client.set(k, v, ex=ex)
        return [True] * len(self._ops)


class _FakeAsyncRedis:
    def __init__(self, backing: _FakeSyncRedis | None = None) -> None:
        self._backing = backing if backing is not None else _FakeSyncRedis()
        self.mget_calls = 0

    async def mget(self, keys: list[str]):
        self.mget_calls += 1
        return [self._backing.store.get(k) for k in keys]

    def pipeline(self, transaction: bool = False):
        return _FakeAsyncPipeline(self._backing)


class _FakeAsyncPipeline:
    def __init__(self, backing: _FakeSyncRedis) -> None:
        self._backing = backing
        self._ops: list[tuple[str, str, int | None]] = []

    def set(self, key: str, value: str, ex: int | None = None):
        self._ops.append((key, value, ex))
        return self

    async def execute(self):
        for k, v, ex in self._ops:
            self._backing.set(k, v, ex=ex)
        return [True] * len(self._ops)


@pytest.fixture
async def client():
    app = FastAPI()
    app.include_router(golf_route.router, prefix="/api/golf")

    async def _fake_db():
        yield AsyncMock()

    app.dependency_overrides[get_db] = _fake_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


class TestBoundedSnapshotRichness:
    async def test_single_eligible_winner_market_skips_snapshot_count(self, monkeypatch):
        engine, sync_db = _create_sqlite_golf_session()
        try:
            sync_db.execute(
                text("INSERT INTO futures_markets (id, source) VALUES (:id, :src)"),
                {"id": 501, "src": "kalshi"},
            )
            for i in range(6):
                sync_db.add(
                    FuturesOutcome(
                        id=5000 + i,
                        market_id=501,
                        external_id=f"ext_5000_{i}",
                        name=f"Golfer {i}",
                        current_probability=0.1,
                    )
                )
            sync_db.commit()

            db = _AsyncSessionShim(sync_db)
            monkeypatch.setattr(
                golf_route,
                "get_golf",
                AsyncMock(
                    return_value={
                        "tournaments": [
                            {
                                **_sample_tournament(),
                                "market_ids": [501],
                                "market_names": ["The RSM Classic Winner"],
                            }
                        ],
                        "biggest_movers": [],
                        "pga_schedule": [],
                    }
                ),
            )

            sql_seen: list[str] = []
            orig_exec = db.execute

            async def _spy_execute(stmt, *args, **kwargs):
                sql_seen.append(str(stmt))
                return await orig_exec(stmt, *args, **kwargs)

            monkeypatch.setattr(db, "execute", _spy_execute)

            res = await golf_route.get_golf_tournament(slug="the-rsm-classic", db=db)

            assert res["evolution_market_id"] == 501
            assert not any(
                "row_number" in s.lower()
                or ("futures_odds_snapshots" in s and "is_winner" not in s)
                for s in sql_seen
            ), sql_seen
        finally:
            sync_db.close()
            engine.dispose()

    async def test_bounded_top_contender_richness_picks_richest_and_memoizes(self, monkeypatch):
        engine, sync_db = _create_sqlite_golf_session()
        now = datetime.now(timezone.utc)
        try:
            sync_db.execute(
                text("INSERT INTO futures_markets (id, source) VALUES (:id, :src)"),
                [{"id": 601, "src": "datagolf"}, {"id": 602, "src": "kalshi"}],
            )

            # 12 outcomes per market; rank > 10 outcomes intentionally hold many
            # snapshots in m1 so we verify bounding stays focused on top-10 contenders,
            # while top-10 contenders in m2 hold more snapshots than m1's top-10.
            for idx in range(12):
                p = round(0.20 - idx * 0.015, 4)
                o1 = FuturesOutcome(
                    id=6100 + idx,
                    market_id=601,
                    external_id=f"ext_6100_{idx}",
                    name=f"Player {idx}",
                    current_probability=p,
                )
                o2 = FuturesOutcome(
                    id=6200 + idx,
                    market_id=602,
                    external_id=f"ext_6200_{idx}",
                    name=f"Player {idx}",
                    current_probability=p,
                )
                sync_db.add_all([o1, o2])
                if idx < 10:
                    sync_db.add(
                        FuturesOddsSnapshot(
                            outcome_id=6100 + idx,
                            bookmaker="datagolf",
                            probability=p,
                            captured_at=now,
                        )
                    )
                    for k in range(3):
                        sync_db.add(
                            FuturesOddsSnapshot(
                                outcome_id=6200 + idx,
                                bookmaker="kalshi",
                                probability=p,
                                captured_at=now - timedelta(minutes=k),
                            )
                        )
                else:
                    for k in range(20):
                        sync_db.add(
                            FuturesOddsSnapshot(
                                outcome_id=6100 + idx,
                                bookmaker="datagolf",
                                probability=p,
                                captured_at=now - timedelta(minutes=k),
                            )
                        )
            sync_db.commit()

            db = _AsyncSessionShim(sync_db)
            monkeypatch.setattr(
                golf_route,
                "get_golf",
                AsyncMock(
                    return_value={
                        "tournaments": [
                            {
                                **_sample_tournament(),
                                "market_ids": [601, 602],
                                "market_names": [
                                    "The RSM Classic - Winner",
                                    "The RSM Classic Winner",
                                ],
                            }
                        ],
                        "biggest_movers": [],
                        "pga_schedule": [],
                    }
                ),
            )

            res1 = await golf_route.get_golf_tournament(slug="the-rsm-classic", db=db)
            assert res1["evolution_market_id"] == 602

            # Second call hits richness memo without re-querying snapshots
            sql_seen: list[str] = []
            orig_exec = db.execute

            async def _spy_execute(stmt, *args, **kwargs):
                sql_seen.append(str(stmt))
                return await orig_exec(stmt, *args, **kwargs)

            monkeypatch.setattr(db, "execute", _spy_execute)
            res2 = await golf_route.get_golf_tournament(slug="the-rsm-classic", db=db)
            assert res2["evolution_market_id"] == 602
            assert not any("row_number" in s.lower() for s in sql_seen), sql_seen
        finally:
            sync_db.close()
            engine.dispose()

    async def test_supplied_golf_data_is_never_mutated_by_placement_enrichment(self):
        engine, sync_db = _create_sqlite_golf_session()
        try:
            sync_db.execute(
                text("INSERT INTO futures_markets (id, source) VALUES (:id, :src)"),
                [{"id": 701, "src": "datagolf"}, {"id": 702, "src": "datagolf"}],
            )
            for idx in range(5):
                sync_db.add(
                    FuturesOutcome(
                        id=7100 + idx,
                        market_id=701,
                        external_id=f"ext_7100_{idx}",
                        name="Tommy Fleetwood" if idx == 0 else f"Golfer {idx}",
                        current_probability=0.15,
                    )
                )
            sync_db.add(
                FuturesOutcome(
                    id=7200,
                    market_id=702,
                    external_id="ext_7200",
                    name="Tommy Fleetwood",
                    current_probability=0.45,
                )
            )
            sync_db.commit()

            shared_golf_data = {
                "tournaments": [
                    {
                        **_sample_tournament(),
                        "market_ids": [701, 702],
                        "market_names": ["The RSM Classic Winner", "The RSM Classic - Top 5 Finish"],
                    }
                ],
                "biggest_movers": [],
                "pga_schedule": [],
            }
            db = _AsyncSessionShim(sync_db)

            res = await golf_route.get_golf_tournament(
                slug="the-rsm-classic", db=db, golf_data=shared_golf_data
            )
            assert res["golfers"][0]["top_5_prob"] == 45.0
            assert "top_5_prob" not in shared_golf_data["tournaments"][0]["golfers"][0]
        finally:
            sync_db.close()
            engine.dispose()


class TestTournamentDetailCacheSWRAndSingleflight:
    async def test_live_fresh_hit_and_stale_swr_background_refresh(self, client, monkeypatch):
        sync_r = _FakeSyncRedis()
        async_r = _FakeAsyncRedis(sync_r)
        monkeypatch.setenv("GOLF_TOURNAMENT_CACHE_REDIS_ENABLED", "1")
        monkeypatch.setattr(rc_mod, "get_shared_async_redis", AsyncMock(return_value=async_r))

        builds = 0
        bg_done = asyncio.Event()

        async def _fake_build(slug: str, db=None, golf_data=None):
            nonlocal builds
            builds += 1
            return _sample_detail_payload(slug=slug, status="in-progress", prob=0.41)

        async def _fake_bg_build(slug: str):
            try:
                return await _fake_build(slug)
            finally:
                bg_done.set()

        monkeypatch.setattr(golf_route, "get_golf_tournament", _fake_build)
        monkeypatch.setattr(golf_route, "_bg_build_golf_tournament", _fake_bg_build)

        # 1. Seed fresh (age = 20s <= 90s live window) -> HTTP 200 X-Feed-Cache: hit, 0 builds
        fresh_payload = _sample_detail_payload(status="in-progress", prob=0.33)
        cache_mod.publish_tournament_payload_sync(
            "the-rsm-classic",
            fresh_payload,
            redis_client=sync_r,
            generated_at=datetime.now(timezone.utc) - timedelta(seconds=20),
        )
        r1 = await client.get("/api/golf/tournaments/the-rsm-classic")
        assert r1.status_code == 200
        assert r1.headers.get("X-Feed-Cache") == "hit"
        assert r1.json()["golfers"][0]["probability"] == 0.33
        assert builds == 0

        # Never read hourly bainluck:category:golf cache (CERT-686)
        assert golf_route.GOLF_CATEGORY_CACHE_KEY not in sync_r.store

        # 2. Seed stale-but-valid Redis envelope (age = 150s: > 90s, <= 600s) and clear L0
        cache_mod._reset_for_tests()
        stale_payload = _sample_detail_payload(status="in-progress", prob=0.22)
        cache_mod.publish_tournament_payload_sync(
            "the-rsm-classic",
            stale_payload,
            redis_client=sync_r,
            generated_at=datetime.now(timezone.utc) - timedelta(seconds=150),
        )
        cache_mod._l0_entries.clear()

        r2 = await client.get("/api/golf/tournaments/the-rsm-classic")
        assert r2.status_code == 200
        assert r2.headers.get("X-Feed-Cache") == "stale_hit"
        assert r2.json()["golfers"][0]["probability"] == 0.22

        # Concurrent stale read must NOT spawn a duplicate background refresh task
        r2_second = await client.get("/api/golf/tournaments/the-rsm-classic")
        assert r2_second.status_code == 200

        await asyncio.wait_for(bg_done.wait(), timeout=2.0)
        await asyncio.sleep(0)

        assert builds == 1
        r3 = await client.get("/api/golf/tournaments/the-rsm-classic")
        assert r3.status_code == 200
        assert r3.headers.get("X-Feed-Cache") == "hit"
        assert r3.json()["golfers"][0]["probability"] == 0.41

    async def test_l0_recheck_never_rolls_back_to_older_redis_envelope(self, monkeypatch):
        sync_r = _FakeSyncRedis()
        async_r = _FakeAsyncRedis(sync_r)
        monkeypatch.setenv("GOLF_TOURNAMENT_CACHE_REDIS_ENABLED", "1")
        monkeypatch.setattr(rc_mod, "get_shared_async_redis", AsyncMock(return_value=async_r))

        now_dt = datetime.now(timezone.utc)
        # Newer payload published locally at T-20s
        cache_mod.publish_tournament_payload_sync(
            "the-rsm-classic",
            _sample_detail_payload(status="in-progress", prob=0.88),
            redis_client=sync_r,
            generated_at=now_dt - timedelta(seconds=20),
        )
        # Overwrite Redis with an older envelope (T-60s) to simulate stale peer/mirror
        older_env = cache_mod.build_envelope(
            _sample_detail_payload(status="in-progress", prob=0.11),
            generated_at=now_dt - timedelta(seconds=60),
        )[1]
        sync_r.store[cache_mod.fresh_redis_key("the-rsm-classic")] = older_env
        sync_r.store[cache_mod.last_good_redis_key("the-rsm-classic")] = older_env

        # Age L0's recheck timer past L0_RECHECK_LIVE_SECONDS (15s)
        fetched_mono, gen_epoch, raw_p, nbytes, is_live, raw_env = cache_mod._l0_entries[
            "the-rsm-classic"
        ]
        cache_mod._l0_entries["the-rsm-classic"] = (
            fetched_mono - (cache_mod.L0_RECHECK_LIVE_SECONDS + 5.0),
            gen_epoch,
            raw_p,
            nbytes,
            is_live,
            raw_env,
        )

        async def _unexpected_build():
            raise AssertionError("builder should not run during L0 recheck")

        p1, st1 = await cache_mod.get_or_build("the-rsm-classic", builder=_unexpected_build)
        assert st1 == "hit"
        assert p1["golfers"][0]["probability"] == 0.88
        assert async_r.mget_calls == 1

        # Next call immediately after does not re-hit Redis because fetched_mono refreshed
        p2, st2 = await cache_mod.get_or_build("the-rsm-classic", builder=_unexpected_build)
        assert st2 == "hit"
        assert p2["golfers"][0]["probability"] == 0.88
        assert async_r.mget_calls == 1

        # Now Redis receives a genuinely newer envelope (T-5s): once recheck is due again, L0 adopts it
        newer_env = cache_mod.build_envelope(
            _sample_detail_payload(status="in-progress", prob=0.95),
            generated_at=now_dt - timedelta(seconds=5),
        )[1]
        sync_r.store[cache_mod.fresh_redis_key("the-rsm-classic")] = newer_env
        entry = cache_mod._l0_entries["the-rsm-classic"]
        cache_mod._l0_entries["the-rsm-classic"] = (
            time.monotonic() - (cache_mod.L0_RECHECK_LIVE_SECONDS + 5.0),
            entry[1],
            entry[2],
            entry[3],
            entry[4],
            entry[5],
        )

        p3, st3 = await cache_mod.get_or_build("the-rsm-classic", builder=_unexpected_build)
        assert st3 == "hit"
        assert p3["golfers"][0]["probability"] == 0.95
        assert async_r.mget_calls == 2

    async def test_singleflight_coalesces_concurrent_cold_misses(self):
        gate = asyncio.Event()
        calls = 0

        async def _slow_build():
            nonlocal calls
            calls += 1
            await gate.wait()
            return _sample_detail_payload(prob=0.55)

        t1 = asyncio.create_task(cache_mod.get_or_build("the-rsm-classic", builder=_slow_build))
        t2 = asyncio.create_task(cache_mod.get_or_build("the-rsm-classic", builder=_slow_build))
        await asyncio.sleep(0)
        gate.set()
        (p1, st1), (p2, st2) = await asyncio.gather(t1, t2)

        assert calls == 1
        assert {st1, st2} == {"miss", "coalesced"}
        assert p1 == p2

    async def test_fresh_true_bypasses_and_updates_cached_copy(self, client, monkeypatch):
        version = 0

        async def _build(slug: str, db=None, golf_data=None):
            nonlocal version
            version += 1
            return _sample_detail_payload(slug=slug, prob=0.10 * version)

        monkeypatch.setattr(golf_route, "get_golf_tournament", _build)

        r1 = await client.get("/api/golf/tournaments/the-rsm-classic")
        assert r1.status_code == 200
        assert r1.headers.get("X-Feed-Cache") == "miss"
        assert r1.json()["golfers"][0]["probability"] == pytest.approx(0.1)

        r_bypass = await client.get("/api/golf/tournaments/the-rsm-classic?fresh=true")
        assert r_bypass.status_code == 200
        assert r_bypass.headers.get("X-Feed-Cache") == "bypass"
        assert r_bypass.json()["golfers"][0]["probability"] == pytest.approx(0.2)

        r_hit = await client.get("/api/golf/tournaments/the-rsm-classic")
        assert r_hit.status_code == 200
        assert r_hit.headers.get("X-Feed-Cache") == "hit"
        assert r_hit.json()["golfers"][0]["probability"] == pytest.approx(0.2)

    async def test_404_is_never_cached(self, client, monkeypatch):
        calls = 0

        async def _not_found(slug: str, db=None, golf_data=None):
            nonlocal calls
            calls += 1
            raise HTTPException(status_code=404, detail="Not found")

        monkeypatch.setattr(golf_route, "get_golf_tournament", _not_found)

        r1 = await client.get("/api/golf/tournaments/not-a-real-event")
        r2 = await client.get("/api/golf/tournaments/not-a-real-event")
        assert r1.status_code == 404
        assert r2.status_code == 404
        assert calls == 2

    async def test_poll_datagolf_inplay_warms_live_and_settlement_ticks(self, monkeypatch):
        sync_r = _FakeSyncRedis()
        monkeypatch.setenv("GOLF_TOURNAMENT_CACHE_WARM_ENABLED", "1")
        monkeypatch.setenv("GOLF_TOURNAMENT_CACHE_REDIS_ENABLED", "1")
        monkeypatch.setattr("app.tasks.redis_state.get_redis_client", lambda: sync_r)
        monkeypatch.setattr(datagolf_task, "_golf_inplay_window_active", lambda _r: True)

        cache_mod.publish_tournament_payload_sync(
            "the-rsm-classic",
            _sample_detail_payload(status="in-progress", prob=0.25),
            redis_client=sync_r,
        )

        class _FakeCtx:
            async def __aenter__(self):
                return AsyncMock()

            async def __aexit__(self, *args):
                return False

        monkeypatch.setattr("app.tasks.base.get_task_session", lambda: _FakeCtx())

        settled_state = False

        async def _fake_get_golf(db):
            return {
                "tournaments": [
                    _sample_tournament(
                        status="completed" if settled_state else "in-progress",
                        prob=1.0 if settled_state else 0.72,
                    )
                ],
                "current_event": {
                    "slug": "the-rsm-classic",
                    "schedule_status": "completed" if settled_state else "in-progress",
                },
                "biggest_movers": [],
                "pga_schedule": [
                    {
                        "name": "The RSM Classic",
                        "status": "completed",
                        "end_date": "2026-11-22",
                    }
                ]
                if settled_state
                else [],
            }

        async def _fake_build_tournament(slug: str, db=None, golf_data=None):
            t = golf_data["tournaments"][0]
            return _sample_detail_payload(
                slug=slug,
                status=t["schedule_status"],
                prob=t["golfers"][0]["probability"],
            )

        monkeypatch.setattr(golf_route, "get_golf", _fake_get_golf)
        monkeypatch.setattr(golf_route, "get_golf_tournament", _fake_build_tournament)

        # Case 1: live tick warms in-progress page
        monkeypatch.setattr(
            datagolf_task,
            "_poll_datagolf_live",
            AsyncMock(return_value={"live_events": 1, "markets_resolved": 0}),
        )
        res_live = await datagolf_task._poll_datagolf_inplay()
        assert res_live["warmed_tournament_slugs"] == ["the-rsm-classic"]
        stored_live = json.loads(sync_r.store[cache_mod.fresh_redis_key("the-rsm-classic")])
        assert stored_live["payload"]["golfers"][0]["probability"] == 0.72

        # Case 2: settlement tick when markets already closed (only completed schedule entry remains)
        settled_state = True
        monkeypatch.setattr(
            golf_route,
            "get_golf",
            AsyncMock(
                return_value={
                    "tournaments": [],
                    "current_event": None,
                    "biggest_movers": [],
                    "pga_schedule": [
                        {
                            "name": "The RSM Classic",
                            "status": "completed",
                            "end_date": "2026-11-22",
                        }
                    ],
                }
            ),
        )
        monkeypatch.setattr(
            golf_route,
            "get_golf_tournament",
            AsyncMock(
                return_value=_sample_detail_payload(
                    slug="the-rsm-classic", status="completed", prob=1.0
                )
            ),
        )
        monkeypatch.setattr(
            datagolf_task,
            "_poll_datagolf_live",
            AsyncMock(return_value={"live_events": 0, "markets_resolved": 4}),
        )
        res_settled = await datagolf_task._poll_datagolf_inplay()
        assert res_settled["warmed_tournament_slugs"] == ["the-rsm-classic"]
        stored_settled = json.loads(sync_r.store[cache_mod.fresh_redis_key("the-rsm-classic")])
        assert stored_settled["payload"]["tournament"]["schedule_status"] == "completed"
        assert stored_settled["payload"]["golfers"][0]["probability"] == 1.0
