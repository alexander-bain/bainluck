"""#13426 — Golf tournament blended history, caching, thread offload, and range bounds."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.routes import golf as golf_route
from app.services import get_db
from app.utils import request_cache
from app.utils.golf_blended_timeline import (
    GOLF_TIMELINE_FULL_MAX_DAYS,
    GOLF_TIMELINE_MAX_BUCKETS,
    DetachedMarket,
    SnapshotReading,
    build_golf_blended_timeline,
    choose_bucket_seconds,
    history_fetch_floor,
    reset_timeline_cache_for_tests,
)

NOW = datetime(2031, 4, 12, 18, 0, tzinfo=timezone.utc)
_OID = iter(range(10_000, 99_999))


@pytest.fixture(autouse=True)
def _clean_timeline_cache():
    reset_timeline_cache_for_tests()
    request_cache._reset_shared_client_for_tests()
    yield
    reset_timeline_cache_for_tests()
    request_cache._reset_shared_client_for_tests()


def _outcome(name: str, prob: float, *, bid: float | None = None, ask: float | None = None):
    oid = next(_OID)
    return SimpleNamespace(
        id=oid,
        external_id=f"out_{oid}",
        name=name,
        current_probability=prob,
        current_yes_bid=round(max(0.0, prob - 0.005), 4) if bid is None else bid,
        current_yes_ask=round(min(1.0, prob + 0.005), 4) if ask is None else ask,
        opening_probability=None,
        probability_change_24h=None,
        is_winner=None,
        resolution_source=None,
    )


def _market(
    mid: int,
    source: str,
    ext_id: str,
    outcomes: list,
    name: str = "The Masters Tournament Winner",
    *,
    mutually_exclusive: bool | None = True,
):
    return SimpleNamespace(
        id=mid,
        name=name,
        source=source,
        external_id=ext_id,
        outcomes=outcomes,
        commence_time=datetime(2031, 4, 10, 12, 0, tzinfo=timezone.utc),
        resolution_date=datetime(2031, 4, 14, 0, tzinfo=timezone.utc),
        status="open",
        llm_sport_category="golf",
        market_tier=1,
        market_metadata=None,
        mutually_exclusive=mutually_exclusive,
    )


def _snap(oid: int, ts: datetime, prob: float, *, bid: float | None = None, ask: float | None = None):
    return SnapshotReading(
        outcome_id=oid,
        captured_at=ts,
        valid_until=ts + timedelta(hours=2),
        probability=prob,
        yes_bid=round(max(0.0, prob - 0.005), 4) if bid is None else bid,
        yes_ask=round(min(1.0, prob + 0.005), 4) if ask is None else ask,
    )


def test_multi_source_blend_parity_and_zero_right_edge_jump():
    dg_outs = [
        _outcome("Scottie Scheffler", 0.50),
        _outcome("Rory McIlroy", 0.30),
        _outcome("Xander Schauffele", 0.20),
    ]
    kal_outs = [
        _outcome("Scottie Scheffler", 0.30),
        _outcome("Rory McIlroy", 0.40),
        _outcome("Xander Schauffele", 0.30),
    ]
    m_dg = _market(101, "datagolf", "datagolf:pga:masters:win", dg_outs)
    m_kal = _market(102, "kalshi", "KXMASTERS-26", kal_outs)
    markets = [m_dg, m_kal]

    current_entry = golf_route._build_one_tournament("masters", markets, {})
    assert current_entry is not None

    t1 = NOW - timedelta(hours=4)
    t2 = NOW - timedelta(minutes=15)
    readings = [
        _snap(dg_outs[0].id, t1, 0.45),
        _snap(dg_outs[1].id, t1, 0.35),
        _snap(dg_outs[2].id, t1, 0.20),
        _snap(kal_outs[0].id, t1, 0.25),
        _snap(kal_outs[1].id, t1, 0.35),
        _snap(kal_outs[2].id, t1, 0.40),
        _snap(dg_outs[0].id, t2, 0.50),
        _snap(dg_outs[1].id, t2, 0.30),
        _snap(dg_outs[2].id, t2, 0.20),
        _snap(kal_outs[0].id, t2, 0.30),
        _snap(kal_outs[1].id, t2, 0.40),
        _snap(kal_outs[2].id, t2, 0.30),
    ]

    result = build_golf_blended_timeline(
        "masters",
        markets,
        current_entry,
        readings,
        build_entry=lambda k, mkts, snaps: golf_route._build_one_tournament(
            k, [golf_route._AsOfMarket(m, snaps) for m in mkts], {}
        ),
        match_key_fn=golf_route._match_key,
        top=10,
        hours=24,
        commence_time=m_dg.commence_time,
        now=NOW,
    )

    assert result["source"] == "blend"
    assert sorted(result["sources"]) == ["datagolf", "kalshi"]
    assert len(result["timeline"]) == 2
    assert result["timeline"][0]["outcomes"]["Scottie Scheffler"] == pytest.approx(0.35, abs=1e-4)

    latest = result["timeline"][-1]["outcomes"]
    current_by_name = {o["name"]: o["current_probability"] for o in result["outcomes"]}
    for name in ("Scottie Scheffler", "Rory McIlroy", "Xander Schauffele"):
        assert latest[name] == pytest.approx(current_by_name[name], abs=1e-4)


def test_single_source_field_normalization_parity_and_placeholder_filter():
    kal_outs = [
        _outcome("Scottie Scheffler", 0.60),
        _outcome("Rory McIlroy", 0.40),
        _outcome("Xander Schauffele", 0.40),
        _outcome("Jon Rahm", 0.20),
        _outcome("Collin Morikawa", 0.20),
        _outcome("Ludvig Aberg", 0.20),
    ]
    m_kal = _market(201, "kalshi", "KXMASTERS-KAL", kal_outs, mutually_exclusive=None)
    current_entry = golf_route._build_one_tournament("masters", [m_kal], {})
    assert current_entry is not None

    t1 = NOW - timedelta(hours=3)
    t2 = NOW - timedelta(minutes=15)
    readings = [
        _snap(kal_outs[0].id, t1, 0.60),
        _snap(kal_outs[1].id, t1, 0.50, bid=0.0, ask=0.999),
        _snap(kal_outs[2].id, t1, 0.40),
        _snap(kal_outs[3].id, t1, 0.20),
        _snap(kal_outs[4].id, t1, 0.20),
        _snap(kal_outs[5].id, t1, 0.20),
        _snap(kal_outs[0].id, t2, 0.60),
        _snap(kal_outs[1].id, t2, 0.40),
        _snap(kal_outs[2].id, t2, 0.40),
        _snap(kal_outs[3].id, t2, 0.20),
        _snap(kal_outs[4].id, t2, 0.20),
        _snap(kal_outs[5].id, t2, 0.20),
    ]

    result = build_golf_blended_timeline(
        "masters",
        [m_kal],
        current_entry,
        readings,
        build_entry=lambda k, mkts, snaps: golf_route._build_one_tournament(
            k, [golf_route._AsOfMarket(m, snaps) for m in mkts], {}
        ),
        match_key_fn=golf_route._match_key,
        top=10,
        hours=24,
        commence_time=m_kal.commence_time,
        now=NOW,
    )

    assert len(result["timeline"]) == 2
    assert "Rory McIlroy" not in result["timeline"][0]["outcomes"]
    latest = result["timeline"][-1]["outcomes"]
    current_by_name = {o["name"]: o["current_probability"] for o in result["outcomes"]}
    assert latest["Scottie Scheffler"] == pytest.approx(0.30, abs=1e-4)
    assert latest["Scottie Scheffler"] == pytest.approx(current_by_name["Scottie Scheffler"], abs=1e-4)


def test_full_range_enforces_90d_floor_and_caps_buckets():
    floor = history_fetch_floor(
        NOW,
        hours=8760,
        full_range=True,
        max_reading_age=timedelta(hours=48),
    )
    assert floor == NOW - timedelta(days=GOLF_TIMELINE_FULL_MAX_DAYS, hours=48)

    # A 90-day hourly span (~2,160h) must widen bucket_seconds so <= 240 points exist.
    widened = choose_bucket_seconds(90 * 86400, started=False)
    assert (90 * 86400) / widened <= GOLF_TIMELINE_MAX_BUCKETS

    dg_outs = [
        _outcome("Scottie Scheffler", 0.45),
        _outcome("Rory McIlroy", 0.35),
        _outcome("Xander Schauffele", 0.20),
    ]
    m_dg = _market(501, "datagolf", "datagolf:pga:masters:win", dg_outs)
    current_entry = golf_route._build_one_tournament("masters", [m_dg], {})
    assert current_entry is not None

    # Create dense snapshots spanning 120 days; >90d must be excluded by the 90d floor
    # and the remaining 90d must cap at <= 240 points.
    readings = []
    for day_offset in range(120):
        for hour_step in (0, 6, 12, 18):
            ts = NOW - timedelta(days=day_offset, hours=hour_step)
            for idx, o in enumerate(dg_outs):
                readings.append(_snap(o.id, ts, o.current_probability))

    result = build_golf_blended_timeline(
        "masters",
        [m_dg],
        current_entry,
        readings,
        build_entry=lambda k, mkts, snaps: golf_route._build_one_tournament(
            k, [golf_route._AsOfMarket(m, snaps) for m in mkts], {}
        ),
        match_key_fn=golf_route._match_key,
        top=10,
        hours=24,
        full_range=True,
        commence_time=NOW + timedelta(days=7),
        is_live=False,
        now=NOW,
    )

    assert 1 <= len(result["timeline"]) <= GOLF_TIMELINE_MAX_BUCKETS
    assert result["actual_hours"] <= GOLF_TIMELINE_FULL_MAX_DAYS * 24
    earliest_bucket = datetime.fromisoformat(result["timeline"][0]["timestamp"])
    # Snapshot captured 120d ago must not extend the chart past the 90d cutoff.
    assert earliest_bucket >= NOW - timedelta(days=GOLF_TIMELINE_FULL_MAX_DAYS, hours=24)


class _ScalarUniqueResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def unique(self):
        return self

    def all(self):
        return self._rows

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None


class _RowsResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeAsyncDB:
    def __init__(self, markets: list, snapshot_rows: list):
        self._markets = markets
        self._snapshot_rows = snapshot_rows
        self.calls = 0

    async def execute(self, stmt, *args, **kwargs):
        self.calls += 1
        sql_str = str(stmt)
        if "futures_odds_snapshots" in sql_str:
            return _RowsResult(self._snapshot_rows)
        if "futures_markets.canonical_market_key =" in sql_str:
            return _ScalarUniqueResult([])
        if "futures_markets" in sql_str:
            return _ScalarUniqueResult(self._markets)
        return _ScalarUniqueResult([])


class _FakeRedis:
    def __init__(self):
        self.store: dict[str, tuple[str, int | None]] = {}

    async def get(self, key: str):
        hit = self.store.get(key)
        return hit[0] if hit else None

    async def set(self, key: str, value: str, ex: int | None = None):
        self.store[key] = (value, ex)
        return True


@pytest.mark.asyncio
async def test_route_offloads_to_thread_and_caches_per_slug_and_params(monkeypatch):
    dg_outs = [
        _outcome("Scottie Scheffler", 0.50),
        _outcome("Rory McIlroy", 0.30),
        _outcome("Xander Schauffele", 0.20),
    ]
    kal_outs = [
        _outcome("Scottie Scheffler", 0.30),
        _outcome("Rory McIlroy", 0.40),
        _outcome("Xander Schauffele", 0.30),
    ]
    m_dg = _market(301, "datagolf", "datagolf:pga:masters:win", dg_outs)
    m_kal = _market(302, "kalshi", "KXMASTERS-26", kal_outs)
    tourn_entry = golf_route._build_one_tournament("masters", [m_dg, m_kal], {})
    assert tourn_entry is not None
    tourn_entry["slug"] = "the-masters"
    tourn_entry["schedule_status"] = "in-progress"

    open_flag = {"open": True}
    get_golf_calls = 0

    async def fake_get_golf(db=None):
        nonlocal get_golf_calls
        get_golf_calls += 1
        return {"tournaments": [tourn_entry] if open_flag["open"] else []}

    async def fake_completed(slug, db, golf_data=None):
        if slug == "completed-masters":
            return {
                "name": "The Masters Tournament",
                "slug": "completed-masters",
                "key": "masters",
                "start_date": "2026-04-09",
                "commence_time": "2026-04-09T12:00:00+00:00",
                "schedule_status": "completed",
                "golfers": [
                    {"name": "Scottie Scheffler", "probability": 1.0, "won": True},
                    {"name": "Rory McIlroy", "probability": 0.0, "won": False},
                    {"name": "Xander Schauffele", "probability": 0.0, "won": False},
                ],
                "_all_golfers": [
                    {"name": "Scottie Scheffler", "probability": 1.0, "won": True},
                    {"name": "Rory McIlroy", "probability": 0.0, "won": False},
                    {"name": "Xander Schauffele", "probability": 0.0, "won": False},
                ],
                "market_ids": [301, 302],
                "market_names": [m_dg.name, m_kal.name],
                "market_sources": ["datagolf", "kalshi"],
            }
        return None

    now = datetime.now(timezone.utc)
    t_recent = now - timedelta(minutes=20)
    snap_rows = [
        SimpleNamespace(
            outcome_id=o.id,
            captured_at=t_recent,
            valid_until=t_recent + timedelta(hours=2),
            probability=o.current_probability,
            yes_bid=o.current_yes_bid,
            yes_ask=o.current_yes_ask,
        )
        for o in dg_outs + kal_outs
    ]

    monkeypatch.setattr(golf_route, "get_golf", fake_get_golf)
    monkeypatch.setattr(golf_route, "_build_completed_tournament", fake_completed)

    fake_redis = _FakeRedis()

    async def fake_shared_redis():
        return fake_redis

    monkeypatch.setattr(request_cache, "get_shared_async_redis", fake_shared_redis)

    to_thread_calls: list[tuple[bool, int]] = []
    real_to_thread = asyncio.to_thread

    async def spy_to_thread(func, *args, **kwargs):
        winner_mkts = args[1]
        to_thread_calls.append(
            (all(isinstance(m, DetachedMarket) for m in winner_mkts), len(winner_mkts))
        )
        return await real_to_thread(func, *args, **kwargs)

    monkeypatch.setattr(golf_route.asyncio, "to_thread", spy_to_thread)

    fake_db = _FakeAsyncDB([m_dg, m_kal], snap_rows)

    async def override_db():
        yield fake_db

    app.dependency_overrides[get_db] = override_db
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            r1 = await ac.get("/api/golf/tournaments/the-masters/probability-timeline")
            assert r1.status_code == 200
            assert r1.headers.get("X-Timeline-Cache") == "miss_built"
            body = r1.json()
            assert body["source"] == "blend"
            assert body["bucket_seconds"] == 900
            assert len(body["timeline"]) == 1
            assert body["timeline"][0]["outcomes"]["Scottie Scheffler"] == pytest.approx(0.40, abs=1e-4)
            assert len(to_thread_calls) == 1
            assert to_thread_calls[0][0] is True  # DetachedMarket only, zero ORM off-thread
            assert len(fake_redis.store) == 1
            assert next(iter(fake_redis.store.values()))[1] == 120  # Live TTL

            # Second identical request hits L0 cache without touching DB or get_golf
            r2 = await ac.get("/api/golf/tournaments/the-masters/probability-timeline")
            assert r2.status_code == 200
            assert r2.headers.get("X-Timeline-Cache") == "l0_hit"
            assert get_golf_calls == 1

            # Clear L0 only -> hits Redis tier
            reset_timeline_cache_for_tests()
            r3 = await ac.get("/api/golf/tournaments/the-masters/probability-timeline")
            assert r3.status_code == 200
            assert r3.headers.get("X-Timeline-Cache") == "redis_hit"
            assert get_golf_calls == 1

            # Different parameters miss and cache under their own key
            r_top5 = await ac.get(
                "/api/golf/tournaments/the-masters/probability-timeline",
                params={"top": 5, "range": "full"},
            )
            assert r_top5.status_code == 200
            assert r_top5.headers.get("X-Timeline-Cache") == "miss_built"
            assert get_golf_calls == 2
            assert len(fake_redis.store) == 2

            open_flag["open"] = False
            r_done = await ac.get("/api/golf/tournaments/completed-masters/probability-timeline")
            assert r_done.status_code == 200
            assert len(r_done.json()["timeline"]) == 1
            # Completed/idle tournament gets longer 600s TTL
            ttls = [ttl for _, ttl in fake_redis.store.values()]
            assert 600 in ttls

            r_404 = await ac.get("/api/golf/tournaments/no-such-tournament/probability-timeline")
            assert r_404.status_code == 404
    finally:
        app.dependency_overrides.pop(get_db, None)
