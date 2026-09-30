"""#9940 — `new york` leads with this week's games, not the ones whose names say
the city twice, proved through the route on real Postgres.

Production 2026-09-30 21:33Z, once #9897 had disarmed #8738's lead key on a bare
city: `new york` rows 1–4 were Islanders @ Rangers (Oct 6), Devils @ Islanders,
Saints @ Giants (Oct 18) and Patriots @ Jets (Dec 27), above tonight's Islanders
@ Maple Leafs and Sunday's Jets @ Bears (row 9). `los angeles` led with a
Rams–Chargers game on Nov 1.

The cause is the next key down: `search_rank` (`ts_rank_cd`) sorts before
kickoff, and it counts every cover of the city's words — the city on both
sides (2.5), or a New York home side read into a "New Orleans"/"New England"
away side (1.5) — against 1.0 for a game that names the city once.

Why Postgres: `ts_rank_cd` over the weighted team-name vectors is the whole
mechanism, and SQLite has neither.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL,
        reason=(
            "set SEARCH_TEST_DATABASE_URL to run the real-Postgres city rank-ties "
            "contract (CI provides one)"
        ),
    ),
]

# Production's rows and aliases (db-query, 2026-09-30 21:4xZ).
CLUBS = [
    ("basketball_nba", "New York Knicks", ["New York", "Knicks", "New York Knicks"]),
    ("baseball_mlb", "New York Mets", ["New York", "Mets"]),
    ("baseball_mlb", "New York Yankees", ["New York", "yanks", "Yankees"]),
    ("basketball_wnba", "New York Liberty", ["Liberty", "New York"]),
    ("soccer_usa_mls", "New York Red Bulls", ["NY Red Bulls", "Red Bull NY", "Red Bull New York", "New York"]),
    ("icehockey_nhl", "New York Islanders", ["New York I", "Islanders", "New York Islanders"]),
    ("icehockey_nhl", "New York Rangers", ["New York Rangers", "Rangers", "New York R"]),
    ("americanfootball_nfl", "New York Giants", ["Giants"]),
    ("americanfootball_nfl", "New York Jets", ["Jets"]),
    ("americanfootball_nfl", "New Orleans Saints", ["Saints"]),
    ("americanfootball_nfl", "New England Patriots", ["Patriots", "pats"]),
]

# Production's orientation (db-query, 2026-09-30): the vector reads HOME first,
# so `york … new` across a New York home side and a "New …" away side is a
# second cover — 1.5 against 1.0. The away @ home spelling below is the served one.
LEAFS_GAME = "New York Islanders @ Toronto Maple Leafs"   # tonight, 1.0
BEARS_GAME = "New York Jets @ Chicago Bears"              # Sunday, 1.0
CARDS_GAME = "Arizona Cardinals @ New York Giants"        # Monday, 1.0
DERBY_GAME = "New York Islanders @ New York Rangers"      # next week, 2.5
SAINTS_GAME = "New Orleans Saints @ New York Giants"      # 18 days, 1.5
PATS_GAME = "New England Patriots @ New York Jets"        # 88 days, 1.5

GAMES = (  # (sport, away, home, days out)
    ("icehockey_nhl", "New York Islanders", "Toronto Maple Leafs", 0.3),
    ("americanfootball_nfl", "New York Jets", "Chicago Bears", 4),
    ("americanfootball_nfl", "Arizona Cardinals", "New York Giants", 5),
    ("icehockey_nhl", "New York Islanders", "New York Rangers", 6),
    ("americanfootball_nfl", "New Orleans Saints", "New York Giants", 18),
    ("americanfootball_nfl", "New England Patriots", "New York Jets", 88),
)


@pytest.fixture
async def maker():
    """Clean schema per test — the database is shared with the whole job."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    from app.services.database import Base

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    yield async_sessionmaker(engine, expire_on_commit=False)

    await engine.dispose()


@pytest.fixture
async def search(maker):
    """`GET /api/events/search` against the real app and database.

    Redis raises, so every ask is a cache miss — the strawman asks the same
    query the ship case asks, and a live cache would answer it from the fixed run.
    """
    from unittest.mock import patch

    from httpx import ASGITransport, AsyncClient

    from app.dependencies.auth import get_optional_user
    from app.main import app
    from app.services.database import get_db, get_db_rw

    async def _override():
        async with maker() as session:
            yield session

    app.dependency_overrides[get_db] = _override
    app.dependency_overrides[get_db_rw] = _override
    app.dependency_overrides[get_optional_user] = lambda: None

    with patch(
        "app.tasks.redis_state.get_redis_client",
        side_effect=RuntimeError("no redis in the recall gate"),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as http:

            async def _search(q: str) -> dict:
                resp = await http.get("/api/events/search", params={"q": q})
                assert resp.status_code == 200, f"search {q!r} -> {resp.status_code}"
                return resp.json()

            yield _search

    app.dependency_overrides.clear()


async def _seed(session):
    """Eleven clubs as production stores them, six games. Relative clocks
    (gotcha #44)."""
    from app.models.models import Event, Sport, Team

    now = datetime.now(timezone.utc)
    sports = {}
    for key in sorted({key for key, _name, _aliases in CLUBS} | {"icehockey_nhl", "americanfootball_nfl"}):
        sports[key] = Sport(key=key, name=key)
    session.add_all(sports.values())
    await session.flush()

    for key, name, aliases in CLUBS:
        session.add(Team(sport_id=sports[key].id, name=name, alternate_names=aliases))

    for key, away, home, days in GAMES:
        session.add(
            Event(
                sport_id=sports[key].id,
                away_team_name=away,
                home_team_name=home,
                commence_time=now + timedelta(days=days),
                status="scheduled",
                event_tags=["provenance:source:espn"],
            )
        )
    await session.commit()


def _games_in_order(payload) -> list[str]:
    assert "results" in payload, f"no `results` key; got {sorted(payload)}"
    return [f"{e['away_team']} @ {e['home_team']}" for e in payload["results"]]


@pytest.mark.parametrize("typed", ["new york", "New York"])
async def test_a_bare_city_reads_its_games_by_kickoff(maker, search, typed):
    """Tonight, Sunday, next week, then the month-out games — by date alone."""
    async with maker() as session:
        await _seed(session)

    games = _games_in_order(await search(typed))
    assert games == [
        LEAFS_GAME, BEARS_GAME, CARDS_GAME, DERBY_GAME, SAINTS_GAME, PATS_GAME
    ], games


async def test_with_the_raw_rank_the_month_out_games_lead_again(maker, search, monkeypatch):
    """The strawman: sort by the raw `ts_rank_cd` again and production's order
    comes back — Jets @ New England (88 days) above Sunday's Bears @ Jets."""
    from app.routes import events as ev

    monkeypatch.setattr(
        ev, "_search_rank_order_key", lambda rank, *, names_a_club: rank.desc()
    )
    async with maker() as session:
        await _seed(session)

    games = _games_in_order(await search("new york"))
    assert games.index(PATS_GAME) < games.index(BEARS_GAME), games
    assert games.index(SAINTS_GAME) < games.index(LEAFS_GAME), games
