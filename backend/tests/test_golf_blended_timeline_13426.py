"""#13426 — Golf tournament blended history & /api/futures/cross-source-timeline routing."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.routes import golf as golf_route
from app.services import get_db
from app.utils.golf_blended_timeline import SnapshotReading, build_golf_blended_timeline

NOW = datetime(2031, 4, 12, 18, 0, tzinfo=timezone.utc)
_OID = iter(range(10_000, 99_999))


def _outcome(
    name: str, prob: float, *, bid: float | None = None, ask: float | None = None
):
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


def _snap(
    oid: int,
    ts: datetime,
    prob: float,
    *,
    bid: float | None = None,
    ask: float | None = None,
):
    return SnapshotReading(
        outcome_id=oid,
        captured_at=ts,
        valid_until=ts + timedelta(hours=2),
        probability=prob,
        yes_bid=round(max(0.0, prob - 0.005), 4) if bid is None else bid,
        yes_ask=round(min(1.0, prob + 0.005), 4) if ask is None else ask,
    )


def test_multi_source_blend_parity_and_zero_right_edge_jump():
    # Two sources disagree: DataGolf has Scheffler 0.50 / McIlroy 0.30 / Schauffele 0.20,
    # Kalshi has Scheffler 0.30 / McIlroy 0.40 / Schauffele 0.30 -> equal blend is 0.40 / 0.35 / 0.25.
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
        # t1: equal across both venues -> 0.45 / 0.35 / 0.20 vs 0.25 / 0.35 / 0.40 => blend 0.35 / 0.35 / 0.30
        _snap(dg_outs[0].id, t1, 0.45),
        _snap(dg_outs[1].id, t1, 0.35),
        _snap(dg_outs[2].id, t1, 0.20),
        _snap(kal_outs[0].id, t1, 0.25),
        _snap(kal_outs[1].id, t1, 0.35),
        _snap(kal_outs[2].id, t1, 0.40),
        # t2: latest snapshot equals current odds -> must match current_entry exactly (zero right-edge jump)
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
    assert result["timeline"][0]["outcomes"]["Scottie Scheffler"] == pytest.approx(
        0.35, abs=1e-4
    )

    latest = result["timeline"][-1]["outcomes"]
    current_by_name = {o["name"]: o["current_probability"] for o in result["outcomes"]}
    for name in ("Scottie Scheffler", "Rory McIlroy", "Xander Schauffele"):
        assert latest[name] == pytest.approx(current_by_name[name], abs=1e-4)


def test_single_source_field_normalization_parity_and_placeholder_filter():
    # Six Kalshi independent binaries sum to 2.0 (> 1.5), so _build_one_tournament
    # scales each outcome by 0.5: 0.60->0.30, 0.40->0.20, 0.40->0.20, 0.20->0.10 x 3.
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
        # t1 includes an empty-book placeholder on McIlroy (bid=0.0, ask=0.999) which must be filtered out
        _snap(kal_outs[0].id, t1, 0.60),
        _snap(kal_outs[1].id, t1, 0.50, bid=0.0, ask=0.999),
        _snap(kal_outs[2].id, t1, 0.40),
        _snap(kal_outs[3].id, t1, 0.20),
        _snap(kal_outs[4].id, t1, 0.20),
        _snap(kal_outs[5].id, t1, 0.20),
        # t2 matches current quotes exactly
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
    assert latest["Scottie Scheffler"] == pytest.approx(
        current_by_name["Scottie Scheffler"], abs=1e-4
    )


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

    async def execute(self, stmt, *args, **kwargs):
        sql_str = str(stmt)
        if "futures_odds_snapshots" in sql_str:
            return _RowsResult(self._snapshot_rows)
        if "futures_markets.canonical_market_key =" in sql_str:
            return _ScalarUniqueResult([])
        if "futures_markets" in sql_str:
            return _ScalarUniqueResult(self._markets)
        return _ScalarUniqueResult([])


@pytest.mark.asyncio
async def test_golf_tournament_timeline_route_open_completed_and_404(monkeypatch):
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
    tourn_entry["schedule_status"] = "in_progress"

    open_flag = {"open": True}

    async def fake_get_golf(db=None):
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
    fake_db = _FakeAsyncDB([m_dg, m_kal], snap_rows)

    async def override_db():
        yield fake_db

    app.dependency_overrides[get_db] = override_db
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            r_open = await ac.get(
                "/api/golf/tournaments/the-masters/probability-timeline"
            )
            assert r_open.status_code == 200
            body = r_open.json()
            assert body["source"] == "blend"
            assert body["bucket_seconds"] == 900
            assert len(body["timeline"]) == 1
            assert body["timeline"][0]["outcomes"][
                "Scottie Scheffler"
            ] == pytest.approx(0.40, abs=1e-4)

            # Client passes range=full (EvolutionFullRange); range=all is also accepted.
            for range_val in ("full", "all"):
                r_full = await ac.get(
                    "/api/golf/tournaments/the-masters/probability-timeline",
                    params={"range": range_val},
                )
                assert r_full.status_code == 200
                full_body = r_full.json()
                assert len(full_body["timeline"]) == 1
                assert full_body["actual_hours"] >= 1

            open_flag["open"] = False
            r_done = await ac.get(
                "/api/golf/tournaments/completed-masters/probability-timeline"
            )
            assert r_done.status_code == 200
            done_body = r_done.json()
            assert len(done_body["timeline"]) == 1
            assert done_body["timeline"][0]["outcomes"][
                "Scottie Scheffler"
            ] == pytest.approx(0.40, abs=1e-4)

            r_404 = await ac.get(
                "/api/golf/tournaments/no-such-tournament/probability-timeline"
            )
            assert r_404.status_code == 404

            # /api/futures/cross-source-timeline must NOT be shadowed by /{market_id} (which returned 422 int parse error)
            r_xs = await ac.get(
                "/api/futures/cross-source-timeline",
                params={"canonical_key": "golf:PGA:masters:2026"},
            )
            assert r_xs.status_code != 422
            assert r_xs.status_code == 404
    finally:
        app.dependency_overrides.pop(get_db, None)
