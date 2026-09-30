"""#9897 — `chicago` puts this Sunday's Bears game with the week's games, proved
through the route on real Postgres.

Production 2026-09-30 17:4xZ, `/api/events/search?q=chicago` at 390px: the TEAMS
card read Blackhawks, Bulls, Cubs, Sky, White Sox — no Bears — and Jets @ Bears
(Sun, FOX) was the 8th game, under Celtics v Bulls on Oct 30. `los angeles` put
Rams @ Eagles 14th under Lakers in November; `new york` led with seven Knicks
games through Christmas.

The cause is the rows' history, not the query: the NBA/NHL/MLB/WNBA/MLS rows
carry the bare city as an alias (the #6974 folds of the odds provider's
city-only rows), the NFL rows carry only the nickname. The scorer calls the
city alias MC0 and the Bears' name MC1, so #8738's lead key read the card's
five sports as "the club typed" and sank every NFL game.

Why Postgres: the teams window is `ts_rank_cd` over name + aliases, LIMIT 25,
and that rank is what puts the Bears seventh — the arrival order the card cap
then cuts. SQLite serves neither.
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
            "set SEARCH_TEST_DATABASE_URL to run the real-Postgres city lead-tier "
            "contract (CI job `search-recall` provides one)"
        ),
    ),
]

# Production's rows and aliases (db-query, 2026-09-30).
CLUBS = [
    ("icehockey_nhl", "Chicago Blackhawks", ["Blackhawks", "Chicago"]),
    ("basketball_nba", "Chicago Bulls", ["Bulls", "Chicago"]),
    ("baseball_mlb", "Chicago Cubs", ["Cubs", "cubbies", "Chicago"]),
    ("basketball_wnba", "Chicago Sky", ["Chicago", "Sky"]),
    ("baseball_mlb", "Chicago White Sox", ["White Sox", "Chicago"]),
    ("soccer_usa_mls", "Chicago Fire", ["Chicago", "Chicago Fire FC"]),
    ("americanfootball_nfl", "Chicago Bears", ["Bears"]),
]

HAWKS_GAME = "Chicago Blackhawks @ Utah Mammoth"      # tomorrow
BEARS_GAME = "New York Jets @ Chicago Bears"          # Sunday
BULLS_GAME = "Chicago Bulls @ Boston Celtics"         # a month out


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
    """Seven clubs as production stores them, three games. Relative clocks
    (gotcha #44)."""
    from app.models.models import Event, Sport, Team

    now = datetime.now(timezone.utc)
    sports = {}
    for key in sorted({key for key, _name, _aliases in CLUBS}):
        sports[key] = Sport(key=key, name=key)
    session.add_all(sports.values())
    await session.flush()

    for key, name, aliases in CLUBS:
        session.add(Team(sport_id=sports[key].id, name=name, alternate_names=aliases))

    for key, away, home, days in (
        ("icehockey_nhl", "Chicago Blackhawks", "Utah Mammoth", 1),
        ("americanfootball_nfl", "New York Jets", "Chicago Bears", 4),
        ("basketball_nba", "Chicago Bulls", "Boston Celtics", 30),
    ):
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


def _teams(payload) -> list[str]:
    assert "teams" in payload, f"no `teams` key; got {sorted(payload)}"
    return [t["name"] for t in payload["teams"]]


@pytest.mark.parametrize("typed", ["chicago", "Chicago"])
async def test_the_bears_game_sits_with_the_weeks_games(maker, search, typed):
    """Tomorrow's hockey, then Sunday's football, then next month's basketball."""
    async with maker() as session:
        await _seed(session)

    games = _games_in_order(await search(typed))
    assert games == [HAWKS_GAME, BEARS_GAME, BULLS_GAME], games


async def test_the_card_shows_the_bears_first(maker, search):
    """#9941: a bare city cards one club per major league, football first — the
    Bears lead, and Sky (WNBA) and Fire (MLS) give up their slots."""
    async with maker() as session:
        await _seed(session)

    assert _teams(await search("chicago")) == [
        "Chicago Bears", "Chicago Cubs", "Chicago Bulls", "Chicago Blackhawks",
        "Chicago White Sox",
    ]


async def test_with_the_city_alias_counted_the_card_loses_the_bears(maker, search, monkeypatch):
    """#9941's strawman through the route: count the restated city alias again and
    production's card comes back, no Bears — the Postgres `ts_rank_cd` arrival
    order is what cuts them."""
    from app.routes import events as ev

    monkeypatch.setattr(ev, "_alias_restates_name_prefix", lambda alias, name: False)
    async with maker() as session:
        await _seed(session)

    card = _teams(await search("chicago"))
    assert "Chicago Bears" not in card and card[0] == "Chicago Blackhawks", card


async def test_a_nickname_still_leads_its_own_club(maker, search):
    """`bears` names one club: its game leads, and the key still arms."""
    async with maker() as session:
        await _seed(session)

    payload = await search("bears")
    assert _teams(payload)[0] == "Chicago Bears"
    assert _games_in_order(payload)[0] == BEARS_GAME


async def test_with_the_city_alias_counted_the_bears_sink_again(maker, search, monkeypatch):
    """The strawman: count the restated city alias again and production's order
    comes back — the Bulls game a month out above Sunday's Bears game."""
    from app.routes import events as ev

    monkeypatch.setattr(ev, "_alias_restates_name_prefix", lambda alias, name: False)
    async with maker() as session:
        await _seed(session)

    games = _games_in_order(await search("chicago"))
    assert games.index(BULLS_GAME) < games.index(BEARS_GAME), games
