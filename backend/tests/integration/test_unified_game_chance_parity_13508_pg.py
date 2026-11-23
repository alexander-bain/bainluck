"""Standing real-PostgreSQL + FastAPI parity gate for the unified game-chance reader (#13508 / #13502).

Verifies against real PostgreSQL rows and real HTTP route handlers that every
mounted game-chance surface agrees identically with ``GET /api/events/{id}`` on:
- home / away / draw win probabilities and rendered percentages,
- headline ``source_mark`` state and contributing source probabilities, and
- sportsbook ``bookmaker_count`` (folded across twins where applicable).

Covers five production bug classes:
1. Blackpool-class (named-league row + ``soccer_other`` catch-all twin + team & container pages)
2. ASVEL-class (empty league row losing ``_elect`` to a ``basketball_other`` twin)
3. Port Vale-class (stale >72h canonical ``betting`` superseded by a fresh twin + 10 books)
4. Live three-way soccer with a tagged duplicate carrying fresher sources and books
5. Completed highlights/rankings and March Madness bracket games + tournament blends loader
"""

from __future__ import annotations

import datetime as dt
import os
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.dependencies.auth import get_optional_user
from app.services.database import get_db, get_db_rw
from app.utils.proven_duplicates import duplicate_tag

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

needs_postgres = pytest.mark.skipif(
    not DB_URL,
    reason=(
        "set SEARCH_TEST_DATABASE_URL to run the #13508/#13502 real-Postgres "
        "unified game-chance parity gate (CI database-integration shared job provides it)"
    ),
)

SPORT_ID_L1 = 90_135_071
SPORT_ID_L2 = 90_135_072
SPORT_ID_SOCCER_OTHER = 90_135_073
SPORT_ID_EUROLEAGUE = 90_135_074
SPORT_ID_BASKET_OTHER = 90_135_075
SPORT_ID_EPL = 90_135_076
SPORT_ID_NCAAB = 90_135_077

CANON_BLACKPOOL = 90_135_081
TWIN_BLACKPOOL = 90_135_082
CANON_ASVEL = 90_135_083
TWIN_ASVEL = 90_135_084
CANON_PV = 90_135_085
TWIN_PV = 90_135_086
CANON_LIVE = 90_135_087
TWIN_LIVE = 90_135_088
CANON_DONE = 90_135_089
TWIN_DONE = 90_135_090
CANON_MM = 90_135_091
TWIN_MM = 90_135_092

ALL_EVENT_IDS = [
    CANON_BLACKPOOL,
    TWIN_BLACKPOOL,
    CANON_ASVEL,
    TWIN_ASVEL,
    CANON_PV,
    TWIN_PV,
    CANON_LIVE,
    TWIN_LIVE,
    CANON_DONE,
    TWIN_DONE,
    CANON_MM,
    TWIN_MM,
]

TEAM_BLACKPOOL_HOME = 90_135_081
TEAM_BLACKPOOL_AWAY = 90_135_082
ALL_TEAM_IDS = [TEAM_BLACKPOOL_HOME, TEAM_BLACKPOOL_AWAY]

CONTAINER_ID = 90_135_095
CONTAINER_SLUG = "parity-13508-hub"
TEAM_SLUG = "blackpool-13508"


@pytest.fixture
async def pg_engine():
    from app.services.database import Base
    from app.utils.container_corrections import UPGRADE_STATEMENTS

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(lambda sync: Base.metadata.create_all(sync, checkfirst=True))
        for stmt in UPGRADE_STATEMENTS:
            await conn.execute(text(stmt))
    try:
        yield engine
    finally:
        await _cleanup(engine)
        async with engine.begin() as conn:
            # Remove FKs onto `containers` so sibling `shared` gates running
            # `Base.metadata.drop_all()` never hit dependency errors.
            await conn.execute(text("DROP TABLE IF EXISTS container_member_decisions"))
            await conn.execute(text("DROP TABLE IF EXISTS container_corrections"))
        await engine.dispose()


async def _cleanup(pg_engine) -> None:
    from app.models.models import Container, Event, EventEdge, OddsSnapshot, Team

    async with AsyncSession(pg_engine, expire_on_commit=False) as s:
        await s.execute(
            delete(EventEdge).where(
                EventEdge.parent_type == "container",
                EventEdge.parent_id == CONTAINER_ID,
            )
        )
        await s.execute(delete(Container).where(Container.id == CONTAINER_ID))
        await s.execute(delete(OddsSnapshot).where(OddsSnapshot.event_id.in_(ALL_EVENT_IDS)))
        await s.execute(delete(Event).where(Event.id.in_(ALL_EVENT_IDS)))
        await s.execute(delete(Team).where(Team.id.in_(ALL_TEAM_IDS)))
        await s.commit()


async def _ensure_sport(session: AsyncSession, fallback_id: int, key: str, name: str) -> int:
    from app.models.models import Sport

    existing = (await session.execute(select(Sport.id).where(Sport.key == key))).scalar()
    if existing is not None:
        return int(existing)
    await session.execute(
        pg_insert(Sport).values(id=fallback_id, key=key, name=name, active=True).on_conflict_do_nothing()
    )
    resolved = (await session.execute(select(Sport.id).where(Sport.key == key))).scalar()
    assert resolved is not None, f"failed to provision Sport({key})"
    return int(resolved)


async def _seed_fixtures(pg_engine) -> None:
    from app.models.models import Container, Event, EventEdge, OddsSnapshot, Team
    from app.utils.container_corrections import publish_container

    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    fresh_ts = now - dt.timedelta(minutes=12)
    stale_ts = now - dt.timedelta(days=5)

    await _cleanup(pg_engine)
    async with AsyncSession(pg_engine, expire_on_commit=False) as s:
        s_l1 = await _ensure_sport(s, SPORT_ID_L1, "soccer_england_league1", "League One")
        s_l2 = await _ensure_sport(s, SPORT_ID_L2, "soccer_england_league2", "League Two")
        s_soc_other = await _ensure_sport(s, SPORT_ID_SOCCER_OTHER, "soccer_other", "Soccer Other")
        s_euro = await _ensure_sport(s, SPORT_ID_EUROLEAGUE, "basketball_euroleague", "EuroLeague")
        s_bkt_other = await _ensure_sport(
            s, SPORT_ID_BASKET_OTHER, "basketball_other", "Basketball Other"
        )
        s_epl = await _ensure_sport(s, SPORT_ID_EPL, "soccer_epl", "EPL")
        s_ncaab = await _ensure_sport(s, SPORT_ID_NCAAB, "basketball_ncaab", "NCAAB")

        s.add_all(
            [
                Team(
                    id=TEAM_BLACKPOOL_HOME,
                    sport_id=s_l1,
                    name="Blackpool Parity",
                    slug=TEAM_SLUG,
                    abbreviation="BKP",
                ),
                Team(
                    id=TEAM_BLACKPOOL_AWAY,
                    sport_id=s_l1,
                    name="Rotherham Parity",
                    slug="rotherham-13508",
                    abbreviation="ROT",
                ),
            ]
        )
        await s.flush()

        s.add_all(
            [
                # 1. Blackpool-class: league row + soccer_other twin with Polymarket + 3 extra books
                Event(
                    id=CANON_BLACKPOOL,
                    sport_id=s_l1,
                    home_team_id=TEAM_BLACKPOOL_HOME,
                    away_team_id=TEAM_BLACKPOOL_AWAY,
                    home_team_name="Blackpool Parity",
                    away_team_name="Rotherham Parity",
                    commence_time=now + dt.timedelta(hours=18),
                    status="scheduled",
                    external_id="pg_13508_blackpool_canon",
                    raw_ei=92.0,
                    ei_computed_at=fresh_ts,
                    event_tags=["sport:soccer"],
                    opening_home_probability=0.47,
                    opening_away_probability=0.26,
                    win_probability_sources={
                        "betting": {
                            "value": 0.48,
                            "away_value": 0.25,
                            "draw_value": 0.27,
                            "three_way_home_value": 0.48,
                            "updated_at": fresh_ts.isoformat(),
                        },
                        "betting_book_count": 2,
                    },
                ),
                Event(
                    id=TWIN_BLACKPOOL,
                    sport_id=s_soc_other,
                    home_team_name="Blackpool Parity",
                    away_team_name="Rotherham Parity",
                    commence_time=now + dt.timedelta(hours=18),
                    status="scheduled",
                    external_id="pg_13508_blackpool_twin",
                    win_probability_sources={
                        "polymarket": {
                            "value": 0.52,
                            "away_value": 0.23,
                            "draw_value": 0.25,
                            "three_way_home_value": 0.52,
                            "updated_at": fresh_ts.isoformat(),
                        },
                    },
                ),
                # 2. ASVEL-class: unpriced league row loses _elect to basketball_other twin
                Event(
                    id=CANON_ASVEL,
                    sport_id=s_euro,
                    home_team_name="ASVEL Parity",
                    away_team_name="Olimpia Parity",
                    commence_time=now + dt.timedelta(hours=20),
                    status="scheduled",
                    external_id="pg_13508_asvel_canon",
                    win_probability_sources={},
                ),
                Event(
                    id=TWIN_ASVEL,
                    sport_id=s_bkt_other,
                    home_team_name="ASVEL Parity",
                    away_team_name="Olimpia Parity",
                    commence_time=now + dt.timedelta(hours=20),
                    status="scheduled",
                    external_id="pg_13508_asvel_twin",
                    win_probability_sources={
                        "kalshi": {"value": 0.61, "updated_at": fresh_ts.isoformat()},
                        "polymarket": {"value": 0.59, "updated_at": fresh_ts.isoformat()},
                    },
                ),
                # 3. Port Vale-class: stale canonical betting superseded by fresh twin + 10 books
                Event(
                    id=CANON_PV,
                    sport_id=s_l2,
                    home_team_name="Port Vale Parity",
                    away_team_name="Northampton Parity",
                    commence_time=now + dt.timedelta(hours=22),
                    status="scheduled",
                    external_id="pg_13508_pv_canon",
                    win_probability_sources={
                        "betting": {
                            "value": 0.31,
                            "away_value": 0.41,
                            "draw_value": 0.28,
                            "three_way_home_value": 0.31,
                            "updated_at": stale_ts.isoformat(),
                        },
                        "betting_book_count": 2,
                    },
                ),
                Event(
                    id=TWIN_PV,
                    sport_id=s_l2,
                    home_team_name="Port Vale Parity",
                    away_team_name="Northampton Parity",
                    commence_time=now + dt.timedelta(hours=22),
                    status="scheduled",
                    external_id="pg_13508_pv_twin",
                    win_probability_sources={
                        "betting": {
                            "value": 0.45,
                            "away_value": 0.26,
                            "draw_value": 0.29,
                            "three_way_home_value": 0.45,
                            "updated_at": fresh_ts.isoformat(),
                        },
                        "betting_book_count": 10,
                    },
                ),
                # 4. Live 3-way soccer + tagged duplicate with fresher books & kalshi
                Event(
                    id=CANON_LIVE,
                    sport_id=s_epl,
                    home_team_name="Chelsea Parity",
                    away_team_name="Everton Parity",
                    commence_time=now - dt.timedelta(minutes=25),
                    status="live",
                    home_score=1,
                    away_score=0,
                    period="1H",
                    game_clock="25'",
                    external_id="pg_13508_live_canon",
                    win_probability_sources={
                        "betting": {
                            "value": 0.62,
                            "away_value": 0.16,
                            "draw_value": 0.22,
                            "three_way_home_value": 0.62,
                            "updated_at": fresh_ts.isoformat(),
                        },
                        "betting_book_count": 4,
                    },
                ),
                Event(
                    id=TWIN_LIVE,
                    sport_id=s_epl,
                    home_team_name="Chelsea Parity",
                    away_team_name="Everton Parity",
                    commence_time=now - dt.timedelta(minutes=25),
                    status="live",
                    external_id="pg_13508_live_twin",
                    event_tags=[duplicate_tag(CANON_LIVE)],
                    win_probability_sources={
                        "kalshi": {
                            "value": 0.64,
                            "away_value": 0.15,
                            "draw_value": 0.21,
                            "three_way_home_value": 0.64,
                            "updated_at": fresh_ts.isoformat(),
                        },
                    },
                ),
                # 5. Completed EI highlight + ranking fixture on Blackpool's team rail
                Event(
                    id=CANON_DONE,
                    sport_id=s_l1,
                    home_team_id=TEAM_BLACKPOOL_HOME,
                    away_team_id=TEAM_BLACKPOOL_AWAY,
                    home_team_name="Blackpool Parity",
                    away_team_name="Rotherham Parity",
                    commence_time=now - dt.timedelta(hours=6),
                    completed_at=now - dt.timedelta(hours=4),
                    status="completed",
                    home_score=2,
                    away_score=1,
                    external_id="pg_13508_done_canon",
                    raw_ei=96.0,
                    ei_computed_at=fresh_ts,
                    ei_metadata='{"snapshot_count": 25}',
                    win_probability_sources={
                        "betting": {
                            "value": 0.99,
                            "away_value": 0.005,
                            "draw_value": 0.005,
                            "three_way_home_value": 0.99,
                            "updated_at": fresh_ts.isoformat(),
                        },
                    },
                ),
                Event(
                    id=TWIN_DONE,
                    sport_id=s_soc_other,
                    home_team_name="Blackpool Parity",
                    away_team_name="Rotherham Parity",
                    commence_time=now - dt.timedelta(hours=6),
                    completed_at=now - dt.timedelta(hours=4),
                    status="completed",
                    external_id="pg_13508_done_twin",
                    win_probability_sources={
                        "kalshi": {
                            "value": 0.98,
                            "away_value": 0.01,
                            "draw_value": 0.01,
                            "three_way_home_value": 0.98,
                            "updated_at": fresh_ts.isoformat(),
                        },
                    },
                ),
                # 6. March Madness bracket game + twin
                Event(
                    id=CANON_MM,
                    sport_id=s_ncaab,
                    home_team_name="Duke Parity",
                    away_team_name="Siena Parity",
                    commence_time=now + dt.timedelta(hours=24),
                    status="scheduled",
                    external_id="pg_13508_mm_canon",
                    is_tournament_game=True,
                    tournament_type="mens",
                    tournament_region="East",
                    tournament_round="Round of 64",
                    tournament_seed_home=1,
                    tournament_seed_away=16,
                    win_probability_sources={
                        "betting": {"value": 0.80, "updated_at": fresh_ts.isoformat()},
                        "betting_book_count": 2,
                    },
                ),
                Event(
                    id=TWIN_MM,
                    sport_id=s_ncaab,
                    home_team_name="Duke Parity",
                    away_team_name="Siena Parity",
                    commence_time=now + dt.timedelta(hours=24),
                    status="scheduled",
                    external_id="pg_13508_mm_twin",
                    win_probability_sources={
                        "polymarket": {"value": 0.84, "updated_at": fresh_ts.isoformat()},
                    },
                ),
            ]
        )

        snaps: list[OddsSnapshot] = []
        for i in range(2):
            snaps.append(
                OddsSnapshot(
                    event_id=CANON_BLACKPOOL,
                    bookmaker=f"bkp_c_{i}",
                    home_moneyline=108,
                    away_moneyline=300,
                    home_win_probability=0.48,
                    away_win_probability=0.25,
                    captured_at=fresh_ts,
                )
            )
        for i in range(3):
            snaps.append(
                OddsSnapshot(
                    event_id=TWIN_BLACKPOOL,
                    bookmaker=f"bkp_t_{i}",
                    home_moneyline=-108,
                    away_moneyline=320,
                    home_win_probability=0.52,
                    away_win_probability=0.23,
                    captured_at=fresh_ts,
                )
            )
        for i in range(3):
            snaps.append(
                OddsSnapshot(
                    event_id=TWIN_ASVEL,
                    bookmaker=f"asvel_t_{i}",
                    home_moneyline=-150,
                    away_moneyline=130,
                    home_win_probability=0.60,
                    away_win_probability=0.40,
                    captured_at=fresh_ts,
                )
            )
        for i in range(2):
            snaps.append(
                OddsSnapshot(
                    event_id=CANON_PV,
                    bookmaker=f"pv_book_{i}",
                    home_moneyline=220,
                    away_moneyline=145,
                    home_win_probability=0.31,
                    away_win_probability=0.41,
                    captured_at=stale_ts,
                )
            )
        for i in range(10):
            snaps.append(
                OddsSnapshot(
                    event_id=TWIN_PV,
                    bookmaker=f"pv_book_{i}",
                    home_moneyline=122,
                    away_moneyline=280,
                    home_win_probability=0.45,
                    away_win_probability=0.26,
                    captured_at=fresh_ts,
                )
            )
        for i in range(4):
            snaps.append(
                OddsSnapshot(
                    event_id=CANON_LIVE,
                    bookmaker=f"epl_c_{i}",
                    home_moneyline=-163,
                    away_moneyline=525,
                    home_win_probability=0.62,
                    away_win_probability=0.16,
                    captured_at=fresh_ts,
                )
            )
        for i in range(6):
            snaps.append(
                OddsSnapshot(
                    event_id=TWIN_LIVE,
                    bookmaker=f"epl_t_{i}",
                    home_moneyline=-175,
                    away_moneyline=560,
                    home_win_probability=0.635,
                    away_win_probability=0.155,
                    captured_at=now - dt.timedelta(minutes=2),
                )
            )
        for i in range(2):
            snaps.append(
                OddsSnapshot(
                    event_id=CANON_MM,
                    bookmaker=f"mm_c_{i}",
                    home_moneyline=-400,
                    away_moneyline=320,
                    home_win_probability=0.80,
                    away_win_probability=0.20,
                    captured_at=fresh_ts,
                )
            )
        for i in range(4):
            snaps.append(
                OddsSnapshot(
                    event_id=TWIN_MM,
                    bookmaker=f"mm_t_{i}",
                    home_moneyline=-500,
                    away_moneyline=400,
                    home_win_probability=0.83,
                    away_win_probability=0.17,
                    captured_at=fresh_ts,
                )
            )
        for i in range(2):
            snaps.append(
                OddsSnapshot(
                    event_id=CANON_DONE,
                    bookmaker=f"done_b_{i}",
                    home_moneyline=-200,
                    away_moneyline=170,
                    home_win_probability=0.65,
                    away_win_probability=0.15,
                    draw_probability=0.20,
                    captured_at=fresh_ts,
                )
            )
        s.add_all(snaps)

        # Published Container holding Blackpool, ASVEL, Port Vale, and Chelsea
        container = Container(
            id=CONTAINER_ID,
            kind="season",
            name="Unified Parity 13508 Hub",
            slug=CONTAINER_SLUG,
            sport_id=s_l1,
            status="scheduled",
        )
        s.add(container)
        await s.flush()
        for idx, cid in enumerate((CANON_BLACKPOOL, CANON_ASVEL, CANON_PV, CANON_LIVE)):
            s.add(
                EventEdge(
                    parent_id=CONTAINER_ID,
                    parent_type="container",
                    child_id=cid,
                    child_type="event",
                    kind="contains",
                    edge_class="match_winner",
                    source="admin",
                    confidence=1.0,
                )
            )
        await s.flush()
        await publish_container(
            s,
            container_id=CONTAINER_ID,
            reason="parity 13508 integration gate",
            actor="test-13508",
        )
        await s.commit()


@pytest.fixture
async def parity_client(pg_engine, monkeypatch):
    monkeypatch.setenv("BYPASS_RATE_LIMITS", "1")
    monkeypatch.setenv("CONTAINERS_READ_ENABLED", "true")
    monkeypatch.setenv("CONTAINERS_READ_CACHE_ENABLED", "false")

    from app.main import app
    from app.routes import events as events_route
    from app.routes import march_madness as mm_route
    from app.tasks import redis_state

    monkeypatch.setattr(redis_state, "get_redis_client", lambda *a, **k: None)
    monkeypatch.setattr(mm_route, "_get_tournament_state", lambda *a, **k: "in_progress")
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


def _source_map(mark: dict | None) -> dict[str, float | None]:
    return {
        s["key"]: s.get("probability")
        for s in ((mark or {}).get("sources") or [])
        if isinstance(s, dict) and s.get("key")
    }


def _assert_card_matches_detail(
    card: dict,
    detail: dict,
    *,
    surface: str,
    check_book_count: bool = True,
) -> None:
    d_odds = detail["current_odds"]
    c_odds = card.get("current_odds") or {}
    assert c_odds.get("home_probability") == pytest.approx(
        d_odds["home_probability"], abs=1e-3
    ), f"{surface}: home_probability mismatch for {detail['id']}"
    assert c_odds.get("away_probability") == pytest.approx(
        d_odds["away_probability"], abs=1e-3
    ), f"{surface}: away_probability mismatch for {detail['id']}"
    if d_odds.get("draw_probability") is not None:
        assert c_odds.get("draw_probability") == pytest.approx(
            d_odds["draw_probability"], abs=1e-3
        ), f"{surface}: draw_probability mismatch for {detail['id']}"
    if check_book_count and d_odds.get("bookmaker_count") is not None:
        assert c_odds.get("bookmaker_count") == d_odds["bookmaker_count"], (
            f"{surface}: bookmaker_count mismatch for {detail['id']}"
        )
    assert card.get("source_mark", {}).get("state") == detail["source_mark"]["state"], (
        f"{surface}: source_mark.state mismatch for {detail['id']}"
    )
    assert _source_map(card.get("source_mark")) == _source_map(detail["source_mark"]), (
        f"{surface}: source_mark.sources mismatch for {detail['id']}"
    )


@needs_postgres
@pytest.mark.asyncio
async def test_all_mounted_game_chance_surfaces_match_event_detail_on_postgres(
    parity_client, pg_engine
):
    from app.routes.tournaments import _load_blends

    # Reference truth directly from GET /api/events/{id}
    details: dict[int, dict] = {}
    for eid in (CANON_BLACKPOOL, CANON_ASVEL, CANON_PV, CANON_LIVE, CANON_DONE, CANON_MM):
        r = await parity_client.get(f"/api/events/{eid}", params={"fresh": "true"})
        assert r.status_code == 200, r.text
        details[eid] = r.json()

    # Positive non-vacuity checks on the folded event pages first
    assert set(_source_map(details[CANON_BLACKPOOL]["source_mark"])) == {"betting", "polymarket"}
    assert details[CANON_BLACKPOOL]["current_odds"]["bookmaker_count"] == 5

    assert set(_source_map(details[CANON_ASVEL]["source_mark"])) == {"kalshi", "polymarket"}
    assert details[CANON_ASVEL]["current_odds"]["bookmaker_count"] == 3

    assert details[CANON_PV]["current_odds"]["home_probability"] == pytest.approx(0.45, abs=1e-3)
    assert details[CANON_PV]["current_odds"]["bookmaker_count"] == 10

    assert set(_source_map(details[CANON_LIVE]["source_mark"])) == {"betting", "kalshi"}
    assert details[CANON_LIVE]["current_odds"]["bookmaker_count"] == 10

    # 1. GET /api/events (unscoped) + GET /api/events?sport=...
    # When unscoped /api/events reads both un-anchored CANON_ASVEL and priced catch-all
    # TWIN_ASVEL on the same page, fold_twin_events elects TWIN_ASVEL (source count rung >
    # names_league rung) and absorbs CANON_ASVEL into it with identical folded numbers.
    inpage_alias = {CANON_ASVEL: TWIN_ASVEL}
    all_ev_r = await parity_client.get("/api/events", params={"days": 7, "limit": 200})
    assert all_ev_r.status_code == 200, all_ev_r.text
    by_id_all = {e["id"]: e for e in all_ev_r.json()["events"]}
    for eid in (CANON_BLACKPOOL, CANON_ASVEL, CANON_PV, CANON_LIVE):
        alias_id = inpage_alias.get(eid)
        if alias_id is not None:
            assert not (eid in by_id_all and alias_id in by_id_all), (
                f"/api/events leaked duplicate pair {eid}/{alias_id}"
            )
        card_id = eid if eid in by_id_all else alias_id
        assert card_id is not None and card_id in by_id_all, f"/api/events missing {eid}"
        _assert_card_matches_detail(by_id_all[card_id], details[eid], surface="GET /api/events")

    for eid, sk in (
        (CANON_BLACKPOOL, "soccer_england_league1"),
        (CANON_ASVEL, "basketball_euroleague"),
        (CANON_PV, "soccer_england_league2"),
    ):
        scoped_r = await parity_client.get(
            "/api/events", params={"sport": sk, "days": 7, "limit": 100}
        )
        assert scoped_r.status_code == 200, scoped_r.text
        cards = [e for e in scoped_r.json()["events"] if e["id"] == eid]
        assert len(cards) == 1, f"/api/events?sport={sk} missing {eid}"
        _assert_card_matches_detail(cards[0], details[eid], surface=f"GET /api/events?sport={sk}")

    # 2. GET /api/leagues/{sport_key}
    for eid, sk in (
        (CANON_BLACKPOOL, "soccer_england_league1"),
        (CANON_ASVEL, "basketball_euroleague"),
        (CANON_PV, "soccer_england_league2"),
        (CANON_LIVE, "soccer_epl"),
    ):
        lg_r = await parity_client.get(f"/api/leagues/{sk}")
        assert lg_r.status_code == 200, lg_r.text
        lg_body = lg_r.json()
        pool = (
            (lg_body.get("upcoming_games") or [])
            + (lg_body.get("recent_results") or [])
            + (lg_body.get("unreported_games") or [])
        )
        lg_cards = [g for g in pool if g["id"] == eid]
        assert len(lg_cards) == 1, f"/api/leagues/{sk} missing {eid}"
        _assert_card_matches_detail(
            lg_cards[0], details[eid], surface=f"GET /api/leagues/{sk}"
        )

    # 3. GET /api/events/search
    for eid, query in (
        (CANON_BLACKPOOL, "Blackpool Parity"),
        (CANON_ASVEL, "ASVEL Parity"),
        (CANON_PV, "Port Vale Parity"),
        (CANON_LIVE, "Chelsea Parity"),
    ):
        sr = await parity_client.get("/api/events/search", params={"q": query, "per_page": 25})
        assert sr.status_code == 200, sr.text
        allowed_ids = {eid} | ({inpage_alias[eid]} if eid in inpage_alias else set())
        s_cards = [e for e in sr.json()["results"] if e["id"] in allowed_ids]
        assert len(s_cards) == 1, f"/api/events/search?q={query} missing {eid}"
        _assert_card_matches_detail(
            s_cards[0], details[eid], surface=f"GET /api/events/search?q={query}"
        )

    # 4. GET /api/events/live
    live_r = await parity_client.get("/api/events/live")
    assert live_r.status_code == 200, live_r.text
    live_cards = [e for e in live_r.json()["events"] if e["id"] == CANON_LIVE]
    assert len(live_cards) == 1
    _assert_card_matches_detail(
        live_cards[0], details[CANON_LIVE], surface="GET /api/events/live"
    )

    # 5. GET /api/events/highlights & /api/events/ei-rankings & /api/events/faceted
    hl_r = await parity_client.get(
        "/api/events/highlights", params={"days": 7, "min_percentile": 0, "limit": 50}
    )
    assert hl_r.status_code == 200, hl_r.text
    hl_cards = [e for e in hl_r.json()["highlights"] if e["id"] == CANON_DONE]
    assert len(hl_cards) == 1
    _assert_card_matches_detail(hl_cards[0], details[CANON_DONE], surface="GET /api/events/highlights")

    ei_r = await parity_client.get("/api/events/ei-rankings", params={"limit": 50})
    assert ei_r.status_code == 200, ei_r.text
    ei_pool = (ei_r.json().get("highest") or []) + (ei_r.json().get("lowest") or [])
    ei_cards = [e for e in ei_pool if e["id"] == CANON_DONE]
    assert len(ei_cards) >= 1
    _assert_card_matches_detail(ei_cards[0], details[CANON_DONE], surface="GET /api/events/ei-rankings")

    fac_r = await parity_client.get(
        "/api/events/faceted", params={"sport": "soccer", "days": 7, "per_page": 50}
    )
    assert fac_r.status_code == 200, fac_r.text
    fac_cards = [e for e in fac_r.json()["events"] if e["id"] == CANON_BLACKPOOL]
    assert len(fac_cards) == 1
    _assert_card_matches_detail(fac_cards[0], details[CANON_BLACKPOOL], surface="GET /api/events/faceted")

    # 6. GET /api/feed & GET /api/feed/price-cards
    feed_r = await parity_client.get("/api/feed", params={"mode": "sports", "limit": 200})
    assert feed_r.status_code == 200, feed_r.text
    feed_by_id = {
        item["data"]["id"]: item["data"]
        for item in feed_r.json()["items"]
        if item.get("type") == "event" and isinstance(item.get("data"), dict)
    }
    for eid in (CANON_BLACKPOOL, CANON_ASVEL, CANON_PV, CANON_LIVE):
        card_id = eid if eid in feed_by_id else inpage_alias.get(eid)
        if card_id is not None and card_id in feed_by_id:
            _assert_card_matches_detail(feed_by_id[card_id], details[eid], surface="GET /api/feed")

    pc_r = await parity_client.get(
        "/api/feed/price-cards",
        params={"event_ids": f"{CANON_BLACKPOOL},{CANON_ASVEL},{CANON_PV},{CANON_LIVE}"},
    )
    assert pc_r.status_code == 200, pc_r.text
    pc_by_id = {
        item["data"]["id"]: item["data"]
        for item in pc_r.json()["items"]
        if item.get("type") == "event"
    }
    for eid in (CANON_BLACKPOOL, CANON_ASVEL, CANON_PV, CANON_LIVE):
        assert eid in pc_by_id, f"/api/feed/price-cards missing {eid}"
        _assert_card_matches_detail(
            pc_by_id[eid], details[eid], surface="GET /api/feed/price-cards"
        )

    # 7. GET /api/teams/{identifier}
    tm_r = await parity_client.get(f"/api/teams/{TEAM_SLUG}")
    assert tm_r.status_code == 200, tm_r.text
    tm_body = tm_r.json()
    tm_cards = {
        ev["id"]: ev
        for ev in ((tm_body.get("upcoming_events") or []) + (tm_body.get("recent_events") or []))
    }
    assert CANON_BLACKPOOL in tm_cards
    bkp_brief = tm_cards[CANON_BLACKPOOL]
    assert bkp_brief["win_probability"] == pytest.approx(
        details[CANON_BLACKPOOL]["current_odds"]["home_probability"], abs=1e-3
    )
    assert bkp_brief.get("draw_probability") == pytest.approx(
        details[CANON_BLACKPOOL]["current_odds"]["draw_probability"], abs=1e-3
    )
    assert bkp_brief["bookmaker_count"] == 5
    assert _source_map(bkp_brief["source_mark"]) == _source_map(
        details[CANON_BLACKPOOL]["source_mark"]
    )

    # 8. GET /api/containers/{slug}
    ct_r = await parity_client.get(f"/api/containers/{CONTAINER_SLUG}")
    assert ct_r.status_code == 200, ct_r.text
    ct_cards: dict[int, dict] = {}
    for sec in ct_r.json().get("sections") or []:
        for m in sec.get("members") or []:
            if m.get("type") == "event" and isinstance(m.get("card"), dict):
                ct_cards[m["id"]] = m["card"]
    for eid in (CANON_BLACKPOOL, CANON_ASVEL, CANON_PV, CANON_LIVE):
        assert eid in ct_cards, f"/api/containers/{CONTAINER_SLUG} missing {eid}"
        _assert_card_matches_detail(
            ct_cards[eid], details[eid], surface="GET /api/containers/{slug}"
        )

    # 9. GET /api/march-madness/mens
    mm_r = await parity_client.get("/api/march-madness/mens")
    assert mm_r.status_code == 200, mm_r.text
    mm_games = [
        g for g in ((mm_r.json().get("bracket") or {}).get("games") or [])
        if g.get("event_id") == CANON_MM
    ]
    assert len(mm_games) == 1, f"/api/march-madness/mens missing {CANON_MM}"
    mm_g = mm_games[0]
    assert mm_g["prob_home"] == pytest.approx(
        details[CANON_MM]["current_odds"]["home_probability"], abs=1e-3
    )
    assert mm_g["prob_away"] == pytest.approx(
        details[CANON_MM]["current_odds"]["away_probability"], abs=1e-3
    )
    assert mm_g["bookmaker_count"] == 6
    assert _source_map(mm_g["source_mark"]) == _source_map(details[CANON_MM]["source_mark"])

    # 10. Tournaments loader parity (`tournaments._load_blends`)
    async with AsyncSession(pg_engine, expire_on_commit=False) as s:
        blends = await _load_blends(s, [CANON_BLACKPOOL, CANON_ASVEL, CANON_PV])
    for eid in (CANON_BLACKPOOL, CANON_ASVEL, CANON_PV):
        assert eid in blends
        b = blends[eid]
        assert b["home_probability"] == pytest.approx(
            details[eid]["current_odds"]["home_probability"], abs=1e-3
        )
        assert b["away_probability"] == pytest.approx(
            details[eid]["current_odds"]["away_probability"], abs=1e-3
        )
        assert b["bookmaker_count"] == details[eid]["current_odds"]["bookmaker_count"]
        assert _source_map(b["home_source_mark"]) == _source_map(details[eid]["source_mark"])
