"""#9836 — `ohio st` finds Ohio State, proved through the route on real Postgres.

Production 2026-09-30 13:4xZ, `/api/events/search`::

    ohio st      0 teams   0 games   10 markets (Kalshi `Ohio St.` only)
    ohio state   1 team   11 games   10 markets (Polymarket `Ohio State` only)
    penn st / iowa st      0 teams   0 games    (their `... state` forms: team + 7 games)

The Teams gate and the game arms both require every typed word to be a WHOLE
word of the name, and `st` is not a word of "Ohio State Buckeyes". The dropdown
(`/typeahead`, substring ILIKE) offered the team, so pressing Enter lost it.

The fix ADDS `state` beside a non-leading `st`; it substitutes nothing. So the
ship case asserts the union: the team, the game, AND both venues' spellings of
the market — Kalshi's `Ohio St.` must survive the widening.

Why Postgres: the Teams gate is pure FTS and the game arms AND a `to_tsvector`
word test onto the ILIKE. SQLite serves neither.
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
            "set SEARCH_TEST_DATABASE_URL to run the real-Postgres college `St.` "
            "contract (CI job `search-recall` provides one)"
        ),
    ),
]

SCHOOL = "Ohio State Buckeyes"
OPPONENT = "Iowa Hawkeyes"
KALSHI_MARKET = "Ohio St. vs Iowa"
POLY_MARKET = "NCAA Football: Ohio State 2026 Win Total"
SAINT = "St. Louis Cardinals"
SAINT_OPPONENT = "Chicago Cubs"


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

    Redis raises, so every ask is a cache miss — the strawman case asks the
    same query the ship case asks, and a live cache would answer it from the
    fixed run.
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


async def _market(session, source, external_id, name, now):
    from app.models.models import FuturesMarket, FuturesOutcome

    market = FuturesMarket(
        source=source,
        external_id=external_id,
        name=name,
        status="open",
        resolution_date=now + timedelta(days=30),
    )
    session.add(market)
    await session.flush()
    # A market with no outcomes is served by no spelling at all (#6977's note).
    for outcome_name in ("Yes", "No"):
        session.add(
            FuturesOutcome(
                market_id=market.id,
                external_id=f"{external_id}:{outcome_name}",
                name=outcome_name,
                current_probability=0.5,
            )
        )


async def _seed(session):
    """The school spelled as ESPN and the team registry spell it, one game, and
    the same question as each venue spells it. Relative clocks (gotcha #44)."""
    from app.models.models import Event, Sport, Team

    now = datetime.now(timezone.utc)
    ncaaf = Sport(key="americanfootball_ncaaf", name="NCAAF")
    mlb = Sport(key="baseball_mlb", name="MLB")
    session.add_all([ncaaf, mlb])
    await session.flush()

    session.add(
        Event(
            sport_id=ncaaf.id,
            home_team_name=OPPONENT,
            away_team_name=SCHOOL,
            commence_time=now + timedelta(days=3),
            status="scheduled",
            event_tags=["provenance:source:espn"],
        )
    )
    session.add(Team(sport_id=ncaaf.id, name=SCHOOL, abbreviation="OSU"))
    session.add(
        Event(
            sport_id=mlb.id,
            home_team_name=SAINT,
            away_team_name=SAINT_OPPONENT,
            commence_time=now + timedelta(days=1),
            status="scheduled",
            event_tags=["provenance:source:espn"],
        )
    )
    session.add(Team(sport_id=mlb.id, name=SAINT, abbreviation="STL"))
    await _market(session, "kalshi", "KXNCAAFGAME-26OCT03OSUIOWA", KALSHI_MARKET, now)
    await _market(session, "polymarket", "poly-osu-win-total-2026", POLY_MARKET, now)
    await session.commit()


def _games(payload) -> list[str]:
    assert "results" in payload, f"no `results` key; got {sorted(payload)}"
    return sorted(f"{e['away_team']} @ {e['home_team']}" for e in payload["results"])


def _teams(payload) -> list[str]:
    assert "teams" in payload, f"no `teams` key; got {sorted(payload)}"
    return [t["name"] for t in payload["teams"]]


def _futures(payload) -> list[str]:
    assert "futures" in payload, f"no `futures` key; got {sorted(payload)}"
    return sorted(f["name"] for f in payload["futures"])


GAME = f"{SCHOOL} @ {OPPONENT}"


@pytest.mark.parametrize("typed", ["ohio st", "Ohio St.", "OHIO ST"])
async def test_the_abbreviation_serves_the_team_the_game_and_both_venues(
    maker, search, typed
):
    async with maker() as session:
        await _seed(session)

    payload = await search(typed)
    assert _teams(payload) == [SCHOOL]
    assert _games(payload) == [GAME]
    # The union: Kalshi's `Ohio St.` survives, Polymarket's `Ohio State` joins.
    assert _futures(payload) == sorted([KALSHI_MARKET, POLY_MARKET])
    assert payload["query"] == typed, "`q` is echoed as typed"


async def test_the_abbreviation_follows_the_school_into_a_matchup(maker, search):
    """`st` in the MIDDLE of the query is still `State` — `ohio st iowa`."""
    async with maker() as session:
        await _seed(session)

    assert _games(await search("ohio st iowa")) == [GAME]


async def test_a_leading_st_is_saint_and_reaches_only_the_saint(maker, search):
    """`st louis` is Saint Louis. No `state` arm, so no state school joins it."""
    async with maker() as session:
        await _seed(session)

    payload = await search("st louis")
    assert _teams(payload) == [SAINT]
    assert _games(payload) == [f"{SAINT_OPPONENT} @ {SAINT}"]


async def test_an_unrelated_query_still_finds_nothing(maker, search):
    """The widening must not collapse a predicate to TRUE."""
    async with maker() as session:
        await _seed(session)

    noise = await search("michigan st")
    assert _teams(noise) == []
    assert _games(noise) == []
    assert _futures(noise) == []


async def test_without_the_expansion_the_abbreviation_loses_the_team_and_the_game(
    maker, search, monkeypatch
):
    """The strawman, on this rig: both halves of the fix made no-ops brings back
    production's page — no team, no game. Proves the cases above measure
    the fix and not the fixture."""
    from app.routes import events as ev
    from app.utils import name_normalization as nn

    monkeypatch.setattr(nn, "college_state_expansion", lambda index, lower: None)
    monkeypatch.setattr(ev, "college_state_query", lambda q: None)
    async with maker() as session:
        await _seed(session)

    payload = await search("ohio st")
    assert _teams(payload) == []
    assert _games(payload) == []
    # The rails still ran: the futures rail's substring arm reaches both markets
    # on this rig either way (on production the Polymarket row lost the top-10 to
    # Kalshi's `Ohio St.` rows, which is ranking, not recall).
    assert KALSHI_MARKET in _futures(payload)


# The half production's 16:4xZ check left open (web v5325): `ohio st` carded the
# school but led its GAMES with Kent State Golden Flashes vs Ohio Bobcats — `ohio`
# on the Bobcats, `state` on Kent State, and that game is sooner. #9044's
# split-words key puts the carded club's games first, but it only arms when the
# card's leader owns every typed word, and "Ohio State Buckeyes" does not own `st`.
KENT = "Kent State Golden Flashes"
BOBCATS = "Ohio Bobcats"
SPLIT_GAME = f"{BOBCATS} @ {KENT}"


async def _seed_split_namesake(session):
    """`_seed` plus the namesake game, a day SOONER than the school's own."""
    from sqlalchemy import select

    from app.models.models import Event, Sport, Team

    await _seed(session)
    now = datetime.now(timezone.utc)
    ncaaf = (
        await session.execute(select(Sport).where(Sport.key == "americanfootball_ncaaf"))
    ).scalar_one()
    session.add(
        Event(
            sport_id=ncaaf.id,
            home_team_name=KENT,
            away_team_name=BOBCATS,
            commence_time=now + timedelta(days=2),
            status="scheduled",
            event_tags=["provenance:source:espn"],
        )
    )
    session.add_all([
        Team(sport_id=ncaaf.id, name=KENT, abbreviation="KENT"),
        Team(sport_id=ncaaf.id, name=BOBCATS, abbreviation="OHIO"),
    ])
    await session.commit()


def _games_in_order(payload) -> list[str]:
    assert "results" in payload, f"no `results` key; got {sorted(payload)}"
    return [f"{e['away_team']} @ {e['home_team']}" for e in payload["results"]]


@pytest.mark.parametrize("typed", ["ohio st", "Ohio St.", "ohio state"])
async def test_the_school_leads_its_games_over_a_split_namesake(maker, search, typed):
    """The school's own game first; the namesake game stays on the page after it."""
    async with maker() as session:
        await _seed_split_namesake(session)

    payload = await search(typed)
    assert _teams(payload)[0] == SCHOOL
    games = _games_in_order(payload)
    assert games[0] == GAME, games
    assert SPLIT_GAME in games, "a key, never a filter"


async def test_without_the_st_spelling_the_namesake_leads_again(maker, search, monkeypatch):
    """The strawman: the card's `St` spelling made a no-op brings back
    production's order — the sooner Kent State v Ohio game first."""
    from app.routes import events as ev

    monkeypatch.setattr(ev, "college_state_abbreviated_names", lambda name: ())
    async with maker() as session:
        await _seed_split_namesake(session)

    payload = await search("ohio st")
    assert _teams(payload)[0] == SCHOOL
    assert _games_in_order(payload)[0] == SPLIT_GAME
