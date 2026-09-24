"""#8428: `dallas washington` in the dropdown shows the game they just played AND the rematch.

Alex's build-20 recording, production 2026-09-24 19:39Z, `x-bainluck-origin: latency`:

    /api/events/typeahead?q=dallas%20Washington
        15176292  Dallas Cowboys at Washington Commanders  2027-01-10  scheduled
    /api/events/search?q=dallas%20Washington
        15176292  (the rematch)                            2027-01-10  scheduled
        14781697  Washington Commanders at Dallas Cowboys  2026-09-20  completed 37-20

The results page reads 30 days back; the dropdown's upcoming pool is now±7d, so
neither game is in it. The or-NEXT arm (#5059) finds the January rematch and then
SHORT-CIRCUITS the or-LAST arm (#4411) — right for `cowboys`, where next replaces
last, and wrong for a reader who typed both teams and is asking about the pairing.

The repair: when the query names EACH side of the next fixture separately
(`query_names_both_sides`), the or-LAST arm runs too, inside its existing 30-day
floor, and admits exactly one row — the previous meeting of the SAME pairing,
whoever was at home.

Real Postgres for the reason `test_typeahead_next_fixture_pg.py` gives: the claim
is about which rows the route's recall predicates select, and the mocked
integration session returns empty lists. CI's `search-recall` job runs this file.

## the controls

  * `cowboys` — one team named. The #5059 lifecycle is unchanged: the rematch
    replaces the played game, it does not join it.
  * `nfl` — a league, no participant. History must not start appearing.
  * the WNBA Wings–Mystics final, two days old — MORE recent than the Cowboys
    game, and a genuine answer to the words `dallas washington`. It is not the
    previous meeting of the pairing on the page, so it must not ride in.
  * Eagles–Giants, last met 40 days ago — the 30-day floor still binds.
  * `new york` against Mets–Yankees — one token lands on BOTH names, so it is a
    city, not a matchup, and the played game stays out.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [pytest.mark.asyncio]

needs_postgres = pytest.mark.skipif(
    not DB_URL,
    reason=(
        "set SEARCH_TEST_DATABASE_URL to run the real-Postgres matchup typeahead "
        "contract (CI job `search-recall` provides one)"
    ),
)

DALLAS = "Dallas Cowboys"
WASHINGTON = "Washington Commanders"


async def _seed(session):
    from app.models.models import Event, Sport, Team

    nfl = Sport(key="americanfootball_nfl", name="NFL")
    wnba = Sport(key="basketball_wnba", name="WNBA")
    mlb = Sport(key="baseball_mlb", name="MLB")
    session.add_all([nfl, wnba, mlb])
    await session.flush()

    dallas = Team(sport_id=nfl.id, name=DALLAS, abbreviation="DAL")
    washington = Team(sport_id=nfl.id, name=WASHINGTON, abbreviation="WSH")
    session.add_all([dallas, washington])
    await session.flush()

    now = datetime.now(timezone.utc)

    # The production shape: Dallas at home four days ago, Washington at home
    # in January — past the seven-day pool, inside the 120-day horizon.
    played = Event(
        sport_id=nfl.id,
        home_team_name=DALLAS,
        home_team_id=dallas.id,
        away_team_name=WASHINGTON,
        away_team_id=washington.id,
        commence_time=now - timedelta(days=4),
        status="completed",
        home_score=37,
        away_score=20,
        event_tags=None,
    )
    rematch = Event(
        sport_id=nfl.id,
        home_team_name=WASHINGTON,
        home_team_id=washington.id,
        away_team_name=DALLAS,
        away_team_id=dallas.id,
        commence_time=now + timedelta(days=107),
        status="scheduled",
        event_tags=None,
    )

    # Same two cities, another sport, and more recent than the NFL game.
    wings_mystics = Event(
        sport_id=wnba.id,
        home_team_name="Washington Mystics",
        away_team_name="Dallas Wings",
        commence_time=now - timedelta(days=2),
        status="completed",
        event_tags=None,
    )

    # The floor: this pairing last met forty days ago.
    eagles_giants_next = Event(
        sport_id=nfl.id,
        home_team_name="New York Giants",
        away_team_name="Philadelphia Eagles",
        commence_time=now + timedelta(days=12),
        status="scheduled",
        event_tags=None,
    )
    eagles_giants_old = Event(
        sport_id=nfl.id,
        home_team_name="Philadelphia Eagles",
        away_team_name="New York Giants",
        commence_time=now - timedelta(days=40),
        status="completed",
        event_tags=None,
    )

    # The city control: `new york` lands on both names.
    subway_next = Event(
        sport_id=mlb.id,
        home_team_name="New York Yankees",
        away_team_name="New York Mets",
        commence_time=now + timedelta(days=10),
        status="scheduled",
        event_tags=None,
    )
    subway_played = Event(
        sport_id=mlb.id,
        home_team_name="New York Mets",
        away_team_name="New York Yankees",
        commence_time=now - timedelta(days=3),
        status="completed",
        event_tags=None,
    )

    rows = [
        played, rematch, wings_mystics, eagles_giants_next, eagles_giants_old,
        subway_next, subway_played,
    ]
    session.add_all(rows)
    await session.commit()
    return {
        "played": played.id,
        "rematch": rematch.id,
        "wings_mystics": wings_mystics.id,
        "eagles_giants_next": eagles_giants_next.id,
        "eagles_giants_old": eagles_giants_old.id,
        "subway_next": subway_next.id,
        "subway_played": subway_played.id,
    }


@pytest.fixture
async def seeded():
    """Real Postgres, real schema, real `pg_trgm`; function-scoped (see sibling file)."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.models import models  # noqa: F401 — registers every table on Base
    from app.services.database import Base

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        ids = await _seed(session)

    yield maker, ids

    await engine.dispose()


@pytest.fixture
async def typeahead(seeded):
    """The real app against the real database, with Redis refused.

    Redis raises so `/typeahead`'s response cache cannot serve one query's
    answer to the next — the controls would pass for the worst reason.
    """
    from unittest.mock import patch

    from httpx import ASGITransport, AsyncClient

    from app.dependencies.auth import get_optional_user
    from app.main import app
    from app.services.database import get_db, get_db_rw

    maker, ids = seeded

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

            async def _typeahead(q: str) -> dict:
                resp = await http.get("/api/events/typeahead", params={"q": q})
                assert resp.status_code == 200, f"typeahead {q!r} -> {resp.status_code}"
                return resp.json()

            yield _typeahead, ids

    app.dependency_overrides.clear()


def _event_ids(payload) -> list[int]:
    items = payload.get("suggestions", []) if isinstance(payload, dict) else []
    return [
        i["event_id"]
        for i in items
        if isinstance(i, dict) and i.get("type") == "event" and i.get("event_id")
    ]


# ---------------------------------------------------------------------------
# 1. The ship
# ---------------------------------------------------------------------------


@needs_postgres
async def test_a_matchup_query_shows_the_played_game_beside_the_rematch(typeahead):
    """🔴 THE SHIP. Both games, as the full results page already shows them."""
    ask, ids = typeahead

    returned = _event_ids(await ask("dallas Washington"))

    assert ids["rematch"] in returned, f"the rematch went missing: {returned}"
    assert ids["played"] in returned, (
        "the game Dallas and Washington played four days ago is still missing "
        f"from the dropdown — the or-LAST arm stayed short-circuited. Got: {returned}"
    )
    # The next game still leads; the played one sits beside it, not above it.
    assert returned.index(ids["rematch"]) < returned.index(ids["played"]), returned


@needs_postgres
async def test_the_order_the_teams_are_typed_in_does_not_matter(typeahead):
    """Washington was AWAY in the played game and HOME in the rematch."""
    ask, ids = typeahead

    returned = _event_ids(await ask("washington dallas"))

    assert ids["rematch"] in returned and ids["played"] in returned, returned


@needs_postgres
async def test_only_the_previous_meeting_of_this_pairing_rides_in(typeahead):
    """The Wings–Mystics final is newer and matches the words; it is not this pairing."""
    ask, ids = typeahead

    returned = _event_ids(await ask("dallas washington"))

    assert ids["wings_mystics"] not in returned, (
        "a WNBA final rode in beside an NFL rematch — the arm admitted the "
        f"newest row naming the words instead of this pairing's. Got: {returned}"
    )
    assert len(returned) == len(set(returned)), f"a game was offered twice: {returned}"


# ---------------------------------------------------------------------------
# 2. The controls
# ---------------------------------------------------------------------------


@needs_postgres
async def test_one_team_named_still_gets_next_instead_of_last(typeahead):
    """#5059's lifecycle is untouched: `cowboys` is not a matchup."""
    ask, ids = typeahead

    returned = _event_ids(await ask("cowboys"))

    assert ids["rematch"] in returned, returned
    assert ids["played"] not in returned, (
        "a single-team query started offering the finished game beside the next "
        f"one — the matchup gate is not gating. Got: {returned}"
    )


@needs_postgres
async def test_a_league_query_does_not_start_pulling_history(typeahead):
    ask, ids = typeahead

    returned = _event_ids(await ask("nfl"))

    for key in ("played", "eagles_giants_old", "wings_mystics", "subway_played"):
        assert ids[key] not in returned, f"`nfl` pulled finished game {key}: {returned}"


@needs_postgres
async def test_the_thirty_day_floor_still_binds_a_matchup(typeahead):
    """No unbounded history: a meeting forty days back is not the last meeting."""
    ask, ids = typeahead

    returned = _event_ids(await ask("eagles giants"))

    assert ids["eagles_giants_next"] in returned, returned
    assert ids["eagles_giants_old"] not in returned, (
        f"a game forty days old was offered — the floor is gone. Got: {returned}"
    )


@needs_postgres
async def test_a_city_that_names_both_teams_is_not_a_matchup(typeahead):
    """`new york` lands on Mets AND Yankees with one token — a city, not a pairing."""
    ask, ids = typeahead

    returned = _event_ids(await ask("new york"))

    assert ids["subway_next"] in returned, returned
    assert ids["subway_played"] not in returned, (
        f"`new york` was read as a matchup and pulled the played game: {returned}"
    )
