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
    GOLF_TIMELINE_FULL_MAX_HOURS,
    GOLF_TIMELINE_MAX_BUCKETS,
    GOLF_TIMELINE_PLAY_BUCKET_SECONDS,
    GOLF_TIMELINE_PRE_TEE_MAX_BUCKETS,
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
        if "max(" in sql_str.lower() and "futures_odds_snapshots" in sql_str.lower():
            max_ts = max((r.captured_at for r in self._snapshot_rows), default=None)
            return _ScalarUniqueResult([max_ts])
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


def _play_and_pre_readings(
    *,
    commence: datetime,
    pre_days: int,
    pre_step_hours: int,
    play_days: int,
    dg_outs: list,
    kal_outs: list,
) -> tuple[list[SnapshotReading], datetime]:
    readings: list[SnapshotReading] = []
    # Pre-tee snapshots strictly before first tee
    for h in range(pre_days * 24, 0, -pre_step_hours):
        ts = commence - timedelta(hours=h)
        shift = 0.01 * ((h % 3) - 1)
        for o in dg_outs + kal_outs:
            p = min(0.95, max(0.05, round(o.current_probability + shift, 4)))
            readings.append(_snap(o.id, ts, p))

    # Play snapshots every 15 minutes from commence through commence + play_days
    last_ts = commence
    for m in range(0, play_days * 24 * 60 + 1, 15):
        ts = commence + timedelta(minutes=m)
        last_ts = ts
        shift = 0.005 * ((m // 15) % 4)
        for idx, o in enumerate(dg_outs + kal_outs):
            delta = shift if idx % 3 == 0 else (-shift / 2.0)
            p = min(0.95, max(0.05, round(o.current_probability + delta, 4)))
            readings.append(_snap(o.id, ts, p))
    return readings, last_ts


def test_play_keeps_15m_steps_for_14d_and_300d_markets():
    dg_outs = [
        _outcome("Scottie Scheffler", 0.45),
        _outcome("Rory McIlroy", 0.35),
        _outcome("Xander Schauffele", 0.20),
    ]
    kal_outs = [
        _outcome("Scottie Scheffler", 0.40),
        _outcome("Rory McIlroy", 0.35),
        _outcome("Xander Schauffele", 0.25),
    ]
    m_dg = _market(701, "datagolf", "datagolf:pga:masters:win", dg_outs)
    m_kal = _market(702, "kalshi", "KXMASTERS-26", kal_outs)
    current_entry = golf_route._build_one_tournament("masters", [m_dg, m_kal], {})
    assert current_entry is not None

    # Case A: 14-day market (10d pre-tee + 4d play at 15m)
    commence_14 = NOW - timedelta(days=4)
    readings_14, end_14 = _play_and_pre_readings(
        commence=commence_14,
        pre_days=10,
        pre_step_hours=1,
        play_days=4,
        dg_outs=dg_outs,
        kal_outs=kal_outs,
    )
    res_14 = build_golf_blended_timeline(
        "masters",
        [m_dg, m_kal],
        current_entry,
        readings_14,
        build_entry=lambda k, mkts, snaps: golf_route._build_one_tournament(
            k, [golf_route._AsOfMarket(m, snaps) for m in mkts], {}
        ),
        match_key_fn=golf_route._match_key,
        top=10,
        hours=168,
        full_range=True,
        commence_time=commence_14,
        is_live=True,
        now=end_14 + timedelta(hours=1),
    )
    assert res_14["bucket_seconds"] == GOLF_TIMELINE_PLAY_BUCKET_SECONDS
    ts_14 = [datetime.fromisoformat(p["timestamp"]) for p in res_14["timeline"]]
    play_ts_14 = [t for t in ts_14 if t >= commence_14]
    pre_ts_14 = [t for t in ts_14 if t < commence_14]
    assert len(play_ts_14) >= 4 * 96
    assert all(
        (play_ts_14[i] - play_ts_14[i - 1]).total_seconds() == 900
        for i in range(1, len(play_ts_14))
    )
    assert 1 <= len(pre_ts_14) <= GOLF_TIMELINE_PRE_TEE_MAX_BUCKETS
    assert all(
        (pre_ts_14[i] - pre_ts_14[i - 1]).total_seconds() >= 3600
        for i in range(1, len(pre_ts_14))
    )

    # Case B: 300-day market (296d pre-tee + 4d play at 15m)
    commence_300 = NOW - timedelta(days=4)
    readings_300, end_300 = _play_and_pre_readings(
        commence=commence_300,
        pre_days=296,
        pre_step_hours=6,
        play_days=4,
        dg_outs=dg_outs,
        kal_outs=kal_outs,
    )
    res_300 = build_golf_blended_timeline(
        "masters",
        [m_dg, m_kal],
        current_entry,
        readings_300,
        build_entry=lambda k, mkts, snaps: golf_route._build_one_tournament(
            k, [golf_route._AsOfMarket(m, snaps) for m in mkts], {}
        ),
        match_key_fn=golf_route._match_key,
        top=10,
        hours=168,
        full_range=True,
        commence_time=commence_300,
        is_live=True,
        now=end_300 + timedelta(hours=1),
    )
    assert res_300["bucket_seconds"] == GOLF_TIMELINE_PLAY_BUCKET_SECONDS
    ts_300 = [datetime.fromisoformat(p["timestamp"]) for p in res_300["timeline"]]
    play_ts_300 = [t for t in ts_300 if t >= commence_300]
    pre_ts_300 = [t for t in ts_300 if t < commence_300]
    assert len(play_ts_300) >= 4 * 96
    assert all(
        (play_ts_300[i] - play_ts_300[i - 1]).total_seconds() == 900
        for i in range(1, len(play_ts_300))
    )
    assert 1 <= len(pre_ts_300) <= GOLF_TIMELINE_PRE_TEE_MAX_BUCKETS
    assert all(
        (pre_ts_300[i] - pre_ts_300[i - 1]).total_seconds() >= 3600
        for i in range(1, len(pre_ts_300))
    )


@pytest.mark.asyncio
async def test_finished_tournament_timeline_invariant_across_1_60_100_300_days(monkeypatch):
    dg_outs = [
        _outcome("Scottie Scheffler", 0.50),
        _outcome("Rory McIlroy", 0.30),
        _outcome("Xander Schauffele", 0.20),
    ]
    kal_outs = [
        _outcome("Scottie Scheffler", 0.40),
        _outcome("Rory McIlroy", 0.35),
        _outcome("Xander Schauffele", 0.25),
    ]
    m_dg = _market(801, "datagolf", "datagolf:pga:masters:win", dg_outs)
    m_kal = _market(802, "kalshi", "KXMASTERS-26", kal_outs)
    current_entry = golf_route._build_one_tournament("masters", [m_dg, m_kal], {})
    assert current_entry is not None

    commence = datetime(2031, 1, 10, 12, 0, tzinfo=timezone.utc)
    readings, final_putt = _play_and_pre_readings(
        commence=commence,
        pre_days=10,
        pre_step_hours=2,
        play_days=4,
        dg_outs=dg_outs,
        kal_outs=kal_outs,
    )

    baseline = None
    for offset_days in (1, 60, 100, 300):
        res = build_golf_blended_timeline(
            "masters",
            [m_dg, m_kal],
            current_entry,
            readings,
            build_entry=lambda k, mkts, snaps: golf_route._build_one_tournament(
                k, [golf_route._AsOfMarket(m, snaps) for m in mkts], {}
            ),
            match_key_fn=golf_route._match_key,
            top=10,
            hours=168,
            full_range=True,
            commence_time=commence,
            is_live=False,
            now=final_putt + timedelta(days=offset_days),
        )
        if baseline is None:
            baseline = res
        else:
            assert res["timeline"] == baseline["timeline"]
            assert res["bucket_seconds"] == baseline["bucket_seconds"]
            assert res["actual_hours"] == baseline["actual_hours"]
            assert res["coverage_hours"] == baseline["coverage_hours"]
            assert res["observation_times"] == baseline["observation_times"]

    # Also verify the route reads completed snapshots older than 90 days ago
    # by anchoring its SQL floor to `max(captured_at)` rather than today's clock.
    old_commence = datetime.now(timezone.utc) - timedelta(days=124)
    old_readings, _ = _play_and_pre_readings(
        commence=old_commence,
        pre_days=10,
        pre_step_hours=6,
        play_days=4,
        dg_outs=dg_outs,
        kal_outs=kal_outs,
    )
    old_snap_rows = [
        SimpleNamespace(
            outcome_id=s.outcome_id,
            captured_at=s.captured_at,
            valid_until=s.valid_until,
            probability=s.probability,
            yes_bid=s.yes_bid,
            yes_ask=s.yes_ask,
        )
        for s in old_readings
    ]

    async def fake_get_golf(db=None):
        return {"tournaments": []}

    async def fake_completed(slug, db, golf_data=None):
        return {
            "name": "The Masters Tournament",
            "slug": slug,
            "key": "masters",
            "start_date": old_commence.date().isoformat(),
            "commence_time": old_commence.isoformat(),
            "schedule_status": "completed",
            "golfers": current_entry["golfers"],
            "_all_golfers": current_entry["_all_golfers"],
            "market_ids": [801, 802],
            "market_names": [m_dg.name, m_kal.name],
            "market_sources": ["datagolf", "kalshi"],
        }

    monkeypatch.setattr(golf_route, "get_golf", fake_get_golf)
    monkeypatch.setattr(golf_route, "_build_completed_tournament", fake_completed)

    fake_db = _FakeAsyncDB([m_dg, m_kal], old_snap_rows)

    async def override_db():
        yield fake_db

    app.dependency_overrides[get_db] = override_db
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get(
                "/api/golf/tournaments/completed-masters/probability-timeline",
                params={"range": "full"},
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["bucket_seconds"] == GOLF_TIMELINE_PLAY_BUCKET_SECONDS
            assert len(body["timeline"]) > 300
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.asyncio
async def test_hours_ceiling_clamps_to_90_days_in_floor_builder_and_route():
    capped_floor = history_fetch_floor(
        NOW,
        hours=8760,
        full_range=False,
        max_reading_age=timedelta(hours=48),
    )
    full_floor = history_fetch_floor(
        NOW,
        hours=168,
        full_range=True,
        max_reading_age=timedelta(hours=48),
    )
    assert capped_floor == full_floor

    dg_outs = [
        _outcome("Scottie Scheffler", 0.50),
        _outcome("Rory McIlroy", 0.30),
        _outcome("Xander Schauffele", 0.20),
    ]
    m_dg = _market(901, "datagolf", "datagolf:pga:masters:win", dg_outs)
    current_entry = golf_route._build_one_tournament("masters", [m_dg], {})
    assert current_entry is not None

    readings = [
        _snap(o.id, NOW - timedelta(days=120), o.current_probability)
        for o in dg_outs
    ] + [
        _snap(o.id, NOW - timedelta(days=5), o.current_probability)
        for o in dg_outs
    ]
    res = build_golf_blended_timeline(
        "masters",
        [m_dg],
        current_entry,
        readings,
        build_entry=lambda k, mkts, snaps: golf_route._build_one_tournament(
            k, [golf_route._AsOfMarket(m, snaps) for m in mkts], {}
        ),
        match_key_fn=golf_route._match_key,
        top=10,
        hours=8760,
        full_range=False,
        now=NOW,
    )
    assert res["hours"] == GOLF_TIMELINE_FULL_MAX_HOURS
    assert res["actual_hours"] == GOLF_TIMELINE_FULL_MAX_HOURS
    assert len(res["timeline"]) == 1

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r_over = await ac.get(
            "/api/golf/tournaments/the-masters/probability-timeline",
            params={"hours": 8760},
        )
        assert r_over.status_code == 422


def test_closed_bucket_cache_reuses_closed_buckets_on_live_refresh():
    dg_outs = [
        _outcome("Scottie Scheffler", 0.50),
        _outcome("Rory McIlroy", 0.30),
        _outcome("Xander Schauffele", 0.20),
    ]
    m_dg = _market(1001, "datagolf", "datagolf:pga:masters:win", dg_outs)
    current_entry = golf_route._build_one_tournament("masters", [m_dg], {})
    assert current_entry is not None

    start = datetime(2031, 4, 10, 12, 0, tzinfo=timezone.utc)
    readings: list[SnapshotReading] = []
    for idx in range(20):
        ts = start + timedelta(minutes=15 * idx)
        shift = 0.005 * (idx % 5)
        readings.append(_snap(dg_outs[0].id, ts, 0.50 + shift))
        readings.append(_snap(dg_outs[1].id, ts, 0.30 - shift / 2.0))
        readings.append(_snap(dg_outs[2].id, ts, 0.20 - shift / 2.0))

    closed_end = start + timedelta(minutes=15 * 20)
    closed_cache = {}
    stats_cold: dict[str, int] = {}
    first = build_golf_blended_timeline(
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
        commence_time=start,
        is_live=True,
        closed_bucket_cache=closed_cache,
        build_stats=stats_cold,
        now=closed_end,
    )
    assert stats_cold["evaluated"] == 20
    assert stats_cold["reused"] == 0
    assert len(closed_cache) == 20

    # Append 1 new 15-minute tick; reuse all 20 closed buckets and evaluate only 1.
    tick_21 = closed_end
    readings_plus = list(readings) + [
        _snap(dg_outs[0].id, tick_21, 0.54),
        _snap(dg_outs[1].id, tick_21, 0.28),
        _snap(dg_outs[2].id, tick_21, 0.18),
    ]
    stats_warm: dict[str, int] = {}
    warm = build_golf_blended_timeline(
        "masters",
        [m_dg],
        current_entry,
        readings_plus,
        build_entry=lambda k, mkts, snaps: golf_route._build_one_tournament(
            k, [golf_route._AsOfMarket(m, snaps) for m in mkts], {}
        ),
        match_key_fn=golf_route._match_key,
        top=10,
        hours=24,
        commence_time=start,
        is_live=True,
        closed_bucket_cache=closed_cache,
        build_stats=stats_warm,
        now=tick_21 + timedelta(minutes=5),
    )
    cold_ref = build_golf_blended_timeline(
        "masters",
        [m_dg],
        current_entry,
        readings_plus,
        build_entry=lambda k, mkts, snaps: golf_route._build_one_tournament(
            k, [golf_route._AsOfMarket(m, snaps) for m in mkts], {}
        ),
        match_key_fn=golf_route._match_key,
        top=10,
        hours=24,
        commence_time=start,
        is_live=True,
        now=tick_21 + timedelta(minutes=5),
    )
    assert stats_warm["reused"] == 20
    assert stats_warm["evaluated"] == 1
    assert warm["timeline"] == cold_ref["timeline"]


@pytest.mark.asyncio
async def test_q1_market_list_parity_includes_continental_named_winner_market(monkeypatch):
    kal_outs = [
        _outcome("Scottie Scheffler", 0.60),
        _outcome("Rory McIlroy", 0.25),
        _outcome("Xander Schauffele", 0.15),
    ]
    # Contains the word "Continent" which NON_CONTENDER_WINNER_RE filters,
    # whereas `_build_one_tournament` retains it cleanly.
    m_kal = _market(1101, "kalshi", "KXCONT-26", kal_outs, name="Tour Continent Winner")
    tourn_entry = golf_route._build_one_tournament("continent_open", [m_kal], {})
    assert tourn_entry is not None
    tourn_entry["slug"] = "tour-continent-open"
    tourn_entry["schedule_status"] = "in-progress"

    now = datetime.now(timezone.utc)
    t_recent = now - timedelta(minutes=10)
    snap_rows = [
        SimpleNamespace(
            outcome_id=o.id,
            captured_at=t_recent,
            valid_until=t_recent + timedelta(hours=2),
            probability=o.current_probability,
            yes_bid=o.current_yes_bid,
            yes_ask=o.current_yes_ask,
        )
        for o in kal_outs
    ]

    async def fake_get_golf(db=None):
        return {"tournaments": [tourn_entry]}

    monkeypatch.setattr(golf_route, "get_golf", fake_get_golf)
    fake_db = _FakeAsyncDB([m_kal], snap_rows)

    async def override_db():
        yield fake_db

    app.dependency_overrides[get_db] = override_db
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            r = await ac.get("/api/golf/tournaments/tour-continent-open/probability-timeline")
            assert r.status_code == 200
            body = r.json()
            assert len(body["timeline"]) == 1
            assert body["timeline"][-1]["outcomes"]["Scottie Scheffler"] == pytest.approx(0.60, abs=1e-4)
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_q2_bucket_boundary_does_not_bleed_next_bucket_snapshot():
    dg_outs = [
        _outcome("Scottie Scheffler", 0.60),
        _outcome("Rory McIlroy", 0.25),
        _outcome("Xander Schauffele", 0.15),
    ]
    m_dg = _market(1201, "datagolf", "datagolf:pga:masters:win", dg_outs)
    current_entry = golf_route._build_one_tournament("masters", [m_dg], {})
    assert current_entry is not None

    t_1400 = datetime(2031, 4, 12, 14, 0, tzinfo=timezone.utc)
    t_1415 = datetime(2031, 4, 12, 14, 15, tzinfo=timezone.utc)
    readings = [
        _snap(dg_outs[0].id, t_1400, 0.30),
        _snap(dg_outs[1].id, t_1400, 0.45),
        _snap(dg_outs[2].id, t_1400, 0.25),
        _snap(dg_outs[0].id, t_1415, 0.60),
        _snap(dg_outs[1].id, t_1415, 0.25),
        _snap(dg_outs[2].id, t_1415, 0.15),
    ]
    res = build_golf_blended_timeline(
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
        commence_time=m_dg.commence_time,
        is_live=True,
        now=t_1415 + timedelta(minutes=20),
    )
    pts = res["timeline"]
    assert len(pts) == 2
    assert pts[0]["timestamp"] == t_1400.isoformat()
    assert pts[0]["outcomes"]["Scottie Scheffler"] == pytest.approx(0.30, abs=1e-4)
    assert pts[1]["timestamp"] == t_1415.isoformat()
    assert pts[1]["outcomes"]["Scottie Scheffler"] == pytest.approx(0.60, abs=1e-4)
