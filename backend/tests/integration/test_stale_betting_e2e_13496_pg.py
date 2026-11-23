"""End-to-end route tests (real PostgreSQL + FastAPI HTTP) for #13496.

Verifies `GET /api/events` and `GET /api/events/{event_id}` end-to-end against
real PostgreSQL rows:

1. Two-row scheduled fixture where the canonical row holds a stale (>72h)
   ``betting`` reading + stale snapshots and the absorbed twin holds a fresh
   ``betting`` reading + 10 fresh sportsbook snapshots serves the fresh
   number and 10-book credit on BOTH list and detail routes.
2. Two-row scheduled gap-fill where the canonical row holds ``betting=None``
   and an orphan ``betting_book_count=2`` serves the twin's fresh probability
   and ``10``-book count on BOTH list and detail routes.
3. Control: a live two-row fixture (non-``scheduled``) never overrides the
   canonical row's ``betting`` reading or book count even if its reading is
   >72h old and the twin's is newer.
"""

from __future__ import annotations

import datetime as dt
import os
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.dependencies.auth import get_optional_user
from app.services.database import get_db, get_db_rw

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

needs_postgres = pytest.mark.skipif(
    not DB_URL,
    reason=(
        "set SEARCH_TEST_DATABASE_URL to run the #13496 real-Postgres HTTP e2e gate "
        "(CI database-integration shared job provides it)"
    ),
)

SPORT_RESERVED_ID = 90_134_960
SPORT_KEY = "soccer_england_league2"

CANON_STALE = 90_134_961
TWIN_FRESH = 90_134_962
CANON_GAP = 90_134_963
TWIN_GAP = 90_134_964
CANON_DONE = 90_134_965
TWIN_DONE = 90_134_966

ALL_EVENT_IDS = [
    CANON_STALE,
    TWIN_FRESH,
    CANON_GAP,
    TWIN_GAP,
    CANON_DONE,
    TWIN_DONE,
]


@pytest.fixture
async def pg_engine():
    from app.services.database import Base

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(lambda sync: Base.metadata.create_all(sync, checkfirst=True))
    yield engine
    await engine.dispose()


async def _cleanup(pg_engine) -> None:
    from app.models.models import Event, OddsSnapshot

    async with AsyncSession(pg_engine, expire_on_commit=False) as s:
        await s.execute(delete(OddsSnapshot).where(OddsSnapshot.event_id.in_(ALL_EVENT_IDS)))
        await s.execute(delete(Event).where(Event.id.in_(ALL_EVENT_IDS)))
        await s.commit()


async def _ensure_sport_id(session: AsyncSession) -> int:
    await session.execute(
        text(
            "INSERT INTO sports (id, key, name, active) "
            "VALUES (:i, :k, :n, true) ON CONFLICT DO NOTHING"
        ),
        {"i": SPORT_RESERVED_ID, "k": SPORT_KEY, "n": "League Two"},
    )
    sport_id = (
        await session.execute(text("SELECT id FROM sports WHERE key = :k"), {"k": SPORT_KEY})
    ).scalar()
    assert sport_id is not None
    return int(sport_id)


async def _seed_fixtures(pg_engine) -> None:
    from app.models.models import Event, OddsSnapshot

    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    stale_ts = now - dt.timedelta(days=63)
    fresh_ts = now - dt.timedelta(minutes=25)
    kickoff_1 = now + dt.timedelta(hours=30)
    kickoff_2 = now + dt.timedelta(hours=34)

    await _cleanup(pg_engine)
    async with AsyncSession(pg_engine, expire_on_commit=False) as s:
        sport_id = await _ensure_sport_id(s)

        s.add_all(
            [
                Event(
                    id=CANON_STALE,
                    sport_id=sport_id,
                    home_team_name="Crawley Town",
                    away_team_name="Barnet",
                    commence_time=kickoff_1,
                    status="scheduled",
                    external_id="e2e_13496_crawley_canon",
                    win_probability_sources={
                        "betting": {
                            "value": 0.2248,
                            "updated_at": stale_ts.isoformat(),
                        },
                        "betting_book_count": 4,
                    },
                ),
                Event(
                    id=TWIN_FRESH,
                    sport_id=sport_id,
                    home_team_name="Crawley Town",
                    away_team_name="Barnet",
                    commence_time=kickoff_1,
                    status="scheduled",
                    external_id="e2e_13496_crawley_twin",
                    win_probability_sources={
                        "betting": {
                            "value": 0.2487,
                            "away_value": 0.5041,
                            "draw_value": 0.2472,
                            "three_way_home_value": 0.2487,
                            "updated_at": fresh_ts.isoformat(),
                        },
                        "betting_book_count": 10,
                    },
                ),
                Event(
                    id=CANON_GAP,
                    sport_id=sport_id,
                    home_team_name="Port Vale",
                    away_team_name="Northampton Town",
                    commence_time=kickoff_2,
                    status="scheduled",
                    external_id="e2e_13496_portvale_canon",
                    win_probability_sources={
                        "betting": None,
                        "betting_book_count": 2,
                    },
                ),
                Event(
                    id=TWIN_GAP,
                    sport_id=sport_id,
                    home_team_name="Port Vale",
                    away_team_name="Northampton Town",
                    commence_time=kickoff_2,
                    status="scheduled",
                    external_id="e2e_13496_portvale_twin",
                    win_probability_sources={
                        "betting": {
                            "value": 0.4492,
                            "away_value": 0.2631,
                            "draw_value": 0.2877,
                            "three_way_home_value": 0.4492,
                            "updated_at": fresh_ts.isoformat(),
                        },
                        "betting_book_count": 10,
                    },
                ),
                Event(
                    id=CANON_DONE,
                    sport_id=sport_id,
                    home_team_name="Crewe Alexandra",
                    away_team_name="Notts County",
                    commence_time=now - dt.timedelta(minutes=30),
                    status="live",
                    home_score=1,
                    away_score=1,
                    external_id="e2e_13496_live_canon",
                    win_probability_sources={
                        "betting": {
                            "value": 0.40,
                            "away_value": 0.30,
                            "draw_value": 0.30,
                            "three_way_home_value": 0.40,
                            "updated_at": stale_ts.isoformat(),
                        },
                        "betting_book_count": 3,
                    },
                ),
                Event(
                    id=TWIN_DONE,
                    sport_id=sport_id,
                    home_team_name="Crewe Alexandra",
                    away_team_name="Notts County",
                    commence_time=now - dt.timedelta(minutes=30),
                    status="live",
                    home_score=1,
                    away_score=1,
                    external_id="e2e_13496_live_twin",
                    win_probability_sources={
                        "betting": {
                            "value": 0.70,
                            "away_value": 0.15,
                            "draw_value": 0.15,
                            "three_way_home_value": 0.70,
                            "updated_at": fresh_ts.isoformat(),
                        },
                        "betting_book_count": 9,
                    },
                ),
            ]
        )

        # 4 stale books on CANON_STALE + 10 fresh books on TWIN_FRESH + 10 fresh books on TWIN_GAP
        snaps: list[OddsSnapshot] = [
            OddsSnapshot(
                event_id=CANON_STALE,
                bookmaker=f"book_{i}",
                home_moneyline=345,
                away_moneyline=-115,
                home_win_probability=0.2248,
                away_win_probability=0.5350,
                captured_at=stale_ts,
            )
            for i in range(4)
        ]
        snaps.extend(
            OddsSnapshot(
                event_id=TWIN_FRESH,
                bookmaker=f"book_{i}",
                home_moneyline=302,
                away_moneyline=-102,
                home_win_probability=0.2487,
                away_win_probability=0.5041,
                captured_at=fresh_ts,
            )
            for i in range(10)
        )
        snaps.extend(
            OddsSnapshot(
                event_id=TWIN_GAP,
                bookmaker=f"pv_book_{i}",
                home_moneyline=122,
                away_moneyline=280,
                home_win_probability=0.4492,
                away_win_probability=0.2631,
                captured_at=fresh_ts,
            )
            for i in range(10)
        )
        s.add_all(snaps)
        await s.commit()


@pytest.fixture
async def e2e_client(pg_engine, monkeypatch):
    monkeypatch.setenv("BYPASS_RATE_LIMITS", "1")
    from app.main import app
    from app.routes import events as events_route
    from app.tasks import redis_state

    monkeypatch.setattr(redis_state, "get_redis_client", lambda *a, **k: None)
    events_route._event_detail_cache.clear()
    await _seed_fixtures(pg_engine)

    async def _real_get_db():
        async with AsyncSession(pg_engine, expire_on_commit=False) as session:
            yield session

    async def _no_user():
        return None

    app.dependency_overrides[get_db] = _real_get_db
    app.dependency_overrides[get_db_rw] = _real_get_db
    app.dependency_overrides[get_optional_user] = _no_user
    try:
        with patch("app.main.init_db", new_callable=AsyncMock):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as ac:
                yield ac
    finally:
        events_route._event_detail_cache.clear()
        app.dependency_overrides.clear()
        await _cleanup(pg_engine)


@needs_postgres
@pytest.mark.asyncio
async def test_crawley_and_port_vale_twins_match_across_list_and_detail_endpoints(e2e_client):
    list_resp = await e2e_client.get(
        "/api/events",
        params={"sport": SPORT_KEY, "status": "scheduled", "days": 7, "limit": 50},
    )
    assert list_resp.status_code == 200, list_resp.text
    events = list_resp.json()["events"]

    crawley_cards = [e for e in events if e["id"] in (CANON_STALE, TWIN_FRESH)]
    assert len(crawley_cards) == 1
    crawley_card = crawley_cards[0]
    assert crawley_card["id"] == CANON_STALE
    assert crawley_card["hero_probability"] == pytest.approx(0.2487)
    assert crawley_card["current_odds"]["bookmaker_count"] == 10
    assert crawley_card["source_mark"]["sources"][0]["key"] == "betting"
    assert crawley_card["source_mark"]["sources"][0]["count"] == 10

    crawley_detail_resp = await e2e_client.get(f"/api/events/{CANON_STALE}")
    assert crawley_detail_resp.status_code == 200, crawley_detail_resp.text
    crawley_detail = crawley_detail_resp.json()
    assert crawley_detail["id"] == CANON_STALE
    assert crawley_detail["hero_probability"] == pytest.approx(crawley_card["hero_probability"])
    assert crawley_detail["hero_sportsbook_count"] == 10
    assert crawley_detail["source_mark"]["sources"][0]["count"] == 10

    port_vale_cards = [e for e in events if e["id"] in (CANON_GAP, TWIN_GAP)]
    assert len(port_vale_cards) == 1
    pv_card = port_vale_cards[0]
    assert pv_card["id"] == CANON_GAP
    assert pv_card["hero_probability"] == pytest.approx(0.4492)
    assert pv_card["current_odds"]["bookmaker_count"] == 10

    pv_detail_resp = await e2e_client.get(f"/api/events/{CANON_GAP}")
    assert pv_detail_resp.status_code == 200, pv_detail_resp.text
    pv_detail = pv_detail_resp.json()
    assert pv_detail["hero_probability"] == pytest.approx(0.4492)
    assert pv_detail["hero_sportsbook_count"] == 10


@needs_postgres
@pytest.mark.asyncio
async def test_live_control_keeps_canonical_betting_and_book_count(e2e_client):
    detail_resp = await e2e_client.get(f"/api/events/{CANON_DONE}")
    assert detail_resp.status_code == 200, detail_resp.text
    detail = detail_resp.json()
    assert detail["id"] == CANON_DONE
    assert detail["hero_probability"] == pytest.approx(0.40)
    assert detail["hero_sportsbook_count"] == 3
