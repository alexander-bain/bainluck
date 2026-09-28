"""`mnf` and `monday night football` find Monday night's NFL game.

THE DEFECT, read on production Monday 2026-09-28 07:5xZ: `/search?q=mnf` and
`/search?q=monday night football` returned ZERO rows of every kind (teams,
results, futures), and `/typeahead?q=mnf` offered nothing — with that night's
Eagles @ Bears (event 14780549, 2026-09-29 00:15Z, 8:15 PM ET) on the schedule.
The dropdown answered the spelled phrase only by accident: `football` resolved to
a bare NFL+NCAAF league arm, so Thursday's NFL game and two college games sat
under the Monday one.

A slot name is the league narrowed to a weekday evening on the Eastern clock
(`_BROADCAST_SLOT_ALIASES`), on both screens.

THE STRAWMAN empties the slot map: `mnf` goes back to serving nothing.
THE CONTROLS: `nfl` still serves every NFL game, and a team word beside the slot
(`eagles mnf`) narrows it to that team's Monday game.

WHY THE ROUTE AND POSTGRES: the slot is `timezone('America/New_York', …)` with
`extract(isodow …)`, wired inside two route bodies. SQLite serves neither.

Kickoffs are placed branch-free (clock_sweep rule): each is a fixed Eastern
weekday wall time, reached as `now + ((REF - now) mod 7 days)` — always the
next occurrence, always inside the dropdown's seven-day pool.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL,
        reason=(
            "set SEARCH_TEST_DATABASE_URL to run the real-Postgres broadcast-slot "
            "gate (CI job `search-recall` provides one)"
        ),
    ),
]

ET = ZoneInfo("America/New_York")
NFL = "americanfootball_nfl"
NCAAF = "americanfootball_ncaaf"

# Reference wall times, one per slot shape. 2026-09-28 is a Monday.
MON_2015 = datetime(2026, 9, 28, 20, 15, tzinfo=ET)
MON_2230 = datetime(2026, 9, 28, 22, 30, tzinfo=ET)
MON_1930 = datetime(2026, 9, 28, 19, 30, tzinfo=ET)
THU_2015 = datetime(2026, 10, 1, 20, 15, tzinfo=ET)
SUN_1625 = datetime(2026, 10, 4, 16, 25, tzinfo=ET)
SUN_2020 = datetime(2026, 10, 4, 20, 20, tzinfo=ET)

MNF = ("Philadelphia Eagles", "Chicago Bears")
MNF_LATE = ("Los Angeles Rams", "San Francisco 49ers")
TNF = ("Pittsburgh Steelers", "Cleveland Browns")
SUN_LATE_AFTERNOON = ("Dallas Cowboys", "Green Bay Packers")
SNF = ("Kansas City Chiefs", "Buffalo Bills")
COLLEGE_MONDAY = ("Western Kentucky Hilltoppers", "New Mexico State Aggies")

# (sport key, (away, home), Eastern reference wall time)
SEEDS = [
    (NFL, MNF, MON_2015),
    (NFL, MNF_LATE, MON_2230),
    (NFL, TNF, THU_2015),
    (NFL, SUN_LATE_AFTERNOON, SUN_1625),
    (NFL, SNF, SUN_2020),
    (NCAAF, COLLEGE_MONDAY, MON_1930),
]


def _next_occurrence(ref: datetime) -> datetime:
    """The next instant at ``ref``'s Eastern weekday and wall time, in UTC.

    Same-tzinfo arithmetic is wall-clock in Python, so a DST change between the
    reference and now still lands on 8:15 PM Eastern.
    """
    now_et = datetime.now(timezone.utc).astimezone(ET)
    # A minute of margin so the route's own `now` cannot overtake the kickoff.
    now_et = now_et + timedelta(minutes=1)
    return (now_et + (ref - now_et) % timedelta(days=7)).astimezone(timezone.utc)


@pytest.fixture
async def maker():
    """A clean schema per test — the `search-recall` database is shared."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    from app.models.models import Event, Sport
    from app.services.database import Base

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    async with session_maker() as session:
        sports = {
            NFL: Sport(key=NFL, name="NFL", group="American Football", active=True),
            NCAAF: Sport(key=NCAAF, name="NCAAF", group="American Football", active=True),
        }
        session.add_all(sports.values())
        await session.flush()
        for i, (sport_key, (away, home), ref) in enumerate(SEEDS):
            session.add(
                Event(
                    sport_id=sports[sport_key].id,
                    external_id=f"slot-{i}",
                    home_team_name=home,
                    away_team_name=away,
                    commence_time=_next_occurrence(ref),
                    status="scheduled",
                )
            )
        await session.commit()

    yield session_maker

    await engine.dispose()


@pytest.fixture
async def get(maker):
    """`GET` either screen against the real app and the real database.

    Redis raises so both response caches miss, as in the sibling gates.
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

            async def _get(path: str, q: str) -> dict:
                resp = await http.get(f"/api/events/{path}", params={"q": q})
                assert resp.status_code == 200, f"{path} {q!r} -> {resp.status_code}"
                return resp.json()

            yield _get

    app.dependency_overrides.clear()


def _search_games(payload: dict) -> set[tuple[str, str]]:
    assert "results" in payload, f"no `results` key; got {sorted(payload)}"
    return {(r["away_team"], r["home_team"]) for r in payload["results"]}


def _typeahead_games(payload: dict) -> set[tuple[str, str]]:
    assert "suggestions" in payload, f"no `suggestions` key; got {sorted(payload)}"
    away_home = {f"{a} at {h}": (a, h) for _, (a, h), _ in SEEDS}
    return {
        away_home[s["text"]]
        for s in payload["suggestions"]
        if s.get("type") == "event" and s.get("text") in away_home
    }


SCREENS = [("search", _search_games), ("typeahead", _typeahead_games)]
NOT_MONDAY_NFL_NIGHT = {TNF, SUN_LATE_AFTERNOON, SNF, COLLEGE_MONDAY}


@pytest.mark.parametrize("q", ["mnf", "monday night football", "MNF"])
@pytest.mark.parametrize("path, read", SCREENS)
async def test_the_slot_serves_monday_nights_nfl_games_only(get, path, read, q):
    games = read(await get(path, q))
    assert MNF in games, f"{path} {q!r} does not serve the Monday night game: {games}"
    assert not games & NOT_MONDAY_NFL_NIGHT, (
        f"{path} {q!r} serves a game outside NFL Monday night: {games}"
    )


@pytest.mark.parametrize("path, read", SCREENS)
async def test_sunday_night_is_the_evening_game_not_the_425(get, path, read):
    games = read(await get(path, "sunday night football"))
    assert SNF in games, games
    assert SUN_LATE_AFTERNOON not in games and MNF not in games, games


@pytest.mark.parametrize("path, read", SCREENS)
async def test_thursday_night_is_its_own_slot(get, path, read):
    games = read(await get(path, "tnf"))
    assert games == {TNF}, games


@pytest.mark.parametrize("path, read", SCREENS)
async def test_a_team_word_narrows_the_slot(get, path, read):
    """Control: `eagles mnf` is the Eagles' Monday game, not the late one."""
    games = read(await get(path, "eagles mnf"))
    assert MNF in games and MNF_LATE not in games, games


@pytest.mark.parametrize("path, read", SCREENS)
async def test_without_the_slot_map_mnf_serves_nothing(get, path, read, monkeypatch):
    """Strawman: the fixture reproduces production's empty answer."""
    from app.routes import events as events_module

    monkeypatch.setattr(events_module, "_BROADCAST_SLOT_ALIASES", {})
    assert MNF not in read(await get(path, "mnf"))


async def test_a_bare_league_word_is_unchanged(get):
    """Control: `nfl` is still every NFL game — the slot never touches it."""
    games = _search_games(await get("search", "nfl"))
    assert {MNF, MNF_LATE, TNF, SUN_LATE_AFTERNOON, SNF} <= games, games
    assert COLLEGE_MONDAY not in games, games
