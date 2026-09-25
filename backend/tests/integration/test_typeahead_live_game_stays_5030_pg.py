"""#5030 — a game being played stays in the search dropdown, against a real Postgres.

Production 2026-09-25 08:46Z (`e4bfcfec`), `GET /api/events/typeahead`:

    q=mannarino  ->  two finished September matches, then the Chengdu market.
                     His Chengdu match (15318277, status live, started 06:30Z)
                     is absent.
    q=richmond   ->  Richmond Tigers team row, then a Saturday college game.
                     Richmond v Carlton (15316735, live, started 06:00Z) is
                     absent.

Every upcoming-game pool floored `commence_time` at a flat `now - 1h`, so a
live row left the dropdown one hour after its start. `_pool_start_floor` keeps
a LIVE row eligible up to `MAX_GAME_DURATION` (12h) and leaves every other row
on the one-hour grace.

The fix is a WHERE clause. A session double cannot observe one, so the route
runs against real rows here. Wired as its own step in the `search-recall` CI job,
with skip, zero-count and short-count refusals.

    SEARCH_TEST_DATABASE_URL=postgresql+asyncpg://postgres@localhost/bl_searchtest \\
        python3 -m pytest tests/integration/test_typeahead_live_game_stays_5030_pg.py -v
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.skipif(
        not DB_URL,
        reason="set SEARCH_TEST_DATABASE_URL to run the #5030 real-Postgres gate",
    ),
    pytest.mark.asyncio,
]

# Offsets from the real clock, taken once per seed. Each margin is hours wide,
# so no test run can straddle a boundary (gotcha #44: offset first, no branch).
_LIVE_IN_PROGRESS = timedelta(hours=3)  # past the old 1h floor, inside 12h
_LIVE_STUCK = timedelta(hours=13)  # past the 12h ceiling: a row the net missed
_SCHEDULED_OVERDUE = timedelta(hours=2)  # not live, past the 1h grace

_LIVE_MATCH = "Adrian Mannarino at Alejandro Tabilo"
_STUCK_MATCH = "Adrian Mannarino at Giovanni Mpetshi Perricard"
_OVERDUE_MATCH = "Adrian Mannarino at Tomas Machac"
_LIVE_GAME = "Carlton Blues at Richmond Tigers"


async def _seed(session):
    from app.models.models import Event, Sport, Team

    now = datetime.now(timezone.utc)
    tennis = Sport(key="tennis_atp_chengdu_open", name="ATP Chengdu")
    aflw = Sport(key="aussierules_aflw", name="AFLW")
    session.add_all([tennis, aflw])
    await session.flush()

    def _match(away: str, home: str, ago: timedelta, status: str) -> Event:
        return Event(
            sport_id=tennis.id,
            away_team_name=away,
            home_team_name=home,
            commence_time=now - ago,
            status=status,
        )

    session.add_all([
        _match("Adrian Mannarino", "Alejandro Tabilo", _LIVE_IN_PROGRESS, "live"),
        _match("Adrian Mannarino", "Giovanni Mpetshi Perricard", _LIVE_STUCK, "live"),
        _match("Adrian Mannarino", "Tomas Machac", _SCHEDULED_OVERDUE, "scheduled"),
    ])

    richmond = Team(sport_id=aflw.id, name="Richmond Tigers", abbreviation="RIC")
    carlton = Team(sport_id=aflw.id, name="Carlton Blues", abbreviation="CAR")
    session.add_all([richmond, carlton])
    await session.flush()
    session.add(
        Event(
            sport_id=aflw.id,
            home_team_id=richmond.id,
            away_team_id=carlton.id,
            home_team_name="Richmond Tigers",
            away_team_name="Carlton Blues",
            commence_time=now - _LIVE_IN_PROGRESS,
            status="live",
        )
    )
    await session.commit()


@pytest.fixture
async def typeahead():
    """The real route, the real schema, the seed above; Redis patched out.

    `typeahead_search` reads a cache before the database, and a hit would make
    every assertion here a test of Redis instead of the WHERE clause.
    """
    from unittest.mock import patch

    from httpx import ASGITransport, AsyncClient
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.models.models  # noqa: F401  — registers every table on Base
    from app.main import app
    from app.services.database import Base, get_db, get_db_rw

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        await _seed(session)

    async def _override():
        async with maker() as session:
            yield session

    app.dependency_overrides[get_db] = _override
    app.dependency_overrides[get_db_rw] = _override
    try:
        with patch(
            "app.tasks.redis_state.get_redis_client",
            side_effect=RuntimeError("no redis"),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:

                async def _do(q: str) -> list[dict]:
                    resp = await client.get("/api/events/typeahead", params={"q": q})
                    assert resp.status_code == 200, f"{q!r} -> HTTP {resp.status_code}"
                    return resp.json()["suggestions"]

                yield _do
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()


def _events(rows: list[dict]) -> dict[str, dict]:
    return {r["text"]: r for r in rows if r.get("type") == "event"}


async def test_a_match_three_hours_in_is_still_offered(typeahead):
    """The production specimen: `mannarino` while his match is being played."""
    events = _events(await typeahead("mannarino"))
    assert _LIVE_MATCH in events, f"the live match left the dropdown: {list(events)}"
    assert events[_LIVE_MATCH]["status"] == "live"


async def test_a_row_stuck_live_past_the_ceiling_is_not(typeahead):
    """gotcha #41's second bound: 13h after its start, `live` is a stuck row."""
    events = _events(await typeahead("mannarino"))
    assert _STUCK_MATCH not in events, list(events)


async def test_a_row_that_is_not_live_keeps_the_one_hour_grace(typeahead):
    """The live arm must not widen the window for scheduled rows."""
    events = _events(await typeahead("mannarino"))
    assert _OVERDUE_MATCH not in events, list(events)


async def test_a_resolved_teams_live_game_follows_its_card(typeahead):
    """The `richmond` specimen, through the team-identity arm (#5201)."""
    rows = await typeahead("richmond tigers")
    texts = [r["text"] for r in rows]
    assert "Richmond Tigers" in texts, texts
    assert _LIVE_GAME in texts, f"the team's live game is missing: {texts}"


async def test_the_strawman_floor_reproduces_production(typeahead, monkeypatch):
    """With the old flat `now - 1h` floor, the live match is gone.

    Proves the seed can express the defect. Without this, a green run could
    mean only that the rig never built a row the old floor would drop.
    """
    from app.models.models import Event
    from app.routes import events as events_module

    monkeypatch.setattr(
        events_module,
        "_pool_start_floor",
        lambda now: Event.commence_time >= now - timedelta(hours=1),
    )
    events = _events(await typeahead("mannarino"))
    assert _LIVE_MATCH not in events, list(events)
    texts = [r["text"] for r in await typeahead("richmond tigers")]
    assert _LIVE_GAME not in texts, texts
