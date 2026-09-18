"""#6977 — a plain keyboard reaches an accented club, proved through the route.

THE DEFECT, measured on production 2026-09-18, the same minute, two spellings::

    q=Atlético Madrid   10 events, 1 team card, 10 futures (10 naming the club)
    q=Atletico Madrid    1 event,  0 team cards, 10 futures ( 1 naming the club)

The single event the unaccented spelling reached was a DUPLICATE the venue
happened to mint without the accent, and the nine futures it was handed instead
belonged to other clubs — `Champions League Winner: PSG vs Arsenal`,
`Vitinha: Next Club`. The page looked full and answered someone else's question,
which is why this is filed as truth and not as relevance. Controls taken the
same minute: `Sevilla` and `Napoli` get tight, club-owned rails, so the rail
works; the name could not be typed.

WHY THE ASSERTION LIVES HERE AND NOT ON THE HELPER. #5821's lesson, one week
old: its bridge case called the house recall builder with the WHOLE query and
passed against a predicate the route never builds, because for a multi-term
query the route ANDs one arm PER TERM. Using the right function is not the same
as using the reader's filter. So every case below drives
`GET /api/events/search` over a real database and reads the served payload.

WHY POSTGRES. The three rails this ship crosses are all Postgres-only: the event
arms compile to pg_trgm-servable ILIKE ANDed with a `to_tsvector` word test, the
futures rail ORs FTS with ILIKE, and the Teams gate is pure FTS. SQLite serves
none of it.

THE TSVECTOR HALF IS THE TRAP. `_event_name_match` ANDs a whole-word FTS test
onto the ILIKE, and `to_tsvector('Atlético Madrid')` yields the lexeme
`atlético` — NOT `atletico` — so a fold that widened only the ILIKE is ANDed
straight back out. The expansion therefore has to reach `_build_expanded_fts`
too, which it does because that helper ORs it.

⚠️ WHICH RAIL THAT COSTS IS NOT THE OBVIOUS ONE, and it was mutation-measured
rather than reasoned. Making the FTS arm ignore its expansion (an ILIKE-only
fold) fails the FUTURES case and leaves the GAME CARD green — because the card
has a second, independent route: the teams rail resolves `Atlético Madrid` via
the query rewrite and the event query rescues that team's fixtures. Removing
EITHER mechanism alone still serves the card; removing BOTH loses all four ship
cases. That redundancy is real and worth knowing, and it is the reason the
per-rail cases below are not each pinned to a single line of the fix.
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
            "set SEARCH_TEST_DATABASE_URL to run the real-Postgres diacritic fold "
            "contract (CI job `search-recall` provides one)"
        ),
    ),
]

# ── The specimen, transcribed from production ───────────────────────────────
#
# The club is spelled with the accent in every column a reader's text is matched
# against, which is the whole defect: there is no unaccented row to fall back on.
CLUB = "Atlético Madrid"
OPPONENT = "Real Madrid"
FUTURE_NAME = "Will Atlético Madrid be relegated from the 2026-27 LaLiga?"

#: What a plain keyboard produces, and the query that returned nothing.
TYPED = "Atletico Madrid"
#: The spelling that already worked — the control every case compares against.
ACCENTED = "Atlético Madrid"


@pytest.fixture
async def maker():
    """A clean schema and a sessionmaker, per test.

    Function-scoped, and `drop_all` first: this database is shared with every
    other gate in the `search-recall` job, so a fixture that assumes empty
    tables collides with its siblings (#5821 lost two cases to exactly that).
    """
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
    """`GET /api/events/search` against the real app and the real database.

    🔴 Redis is patched to raise, and it is load-bearing: `/search` has had a
    full response cache since LAT-P090, and every case here asks the SAME query
    twice — once typed, once accented — so a live cache would serve the first
    answer to the second ask and a dead fold would pass. Both routes treat a
    raising client as a miss, which is the pre-cache behaviour.
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


async def _seed_club(session):
    """One accented fixture, one accented team row, one accented open future.

    Deliberately NO unaccented twin: the production duplicate that used to be
    the plain-keyboard reader's only route is tagged and suppressed by #5821, so
    the fold is the only way through. Seeding one here would let a case pass on
    the twin and hide the ship.

    The kickoff and resolution are RELATIVE (gotcha #44): the route scopes
    events on `commence_time` and futures on `resolution_date IS NULL OR
    resolution_date >= now()`, so pinned calendar dates are a test that passes
    until that date and then silently stops exercising the route.
    """
    from app.models.models import (
        Event,
        FuturesMarket,
        FuturesOutcome,
        Sport,
        Team,
    )

    now = datetime.now(timezone.utc)

    la_liga = Sport(key="soccer_spain_la_liga", name="La Liga")
    session.add(la_liga)
    await session.flush()

    session.add(
        Event(
            sport_id=la_liga.id,
            home_team_name=CLUB,
            away_team_name=OPPONENT,
            commence_time=now + timedelta(days=2),
            status="scheduled",
            event_tags=["provenance:source:odds_api"],
        )
    )
    session.add(Team(sport_id=la_liga.id, name=CLUB, abbreviation="ATM"))
    market = FuturesMarket(
        source="kalshi",
        external_id="KXLALIGARELEGATION-27-ATM",
        name=FUTURE_NAME,
        status="open",
        # Must be in the future: the route filters
        # `resolution_date IS NULL OR resolution_date >= now()`.
        resolution_date=now + timedelta(days=90),
    )
    session.add(market)
    await session.flush()
    # The outcomes are NOT decoration. A market with none is served by neither
    # spelling — measured here on the ACCENTED control, the one that works in
    # production, before any of this was attributed to the fold. Checking the
    # control first is what kept a fixture gap from being filed as a futures-rail
    # defect.
    for outcome_name in ("Yes", "No"):
        session.add(
            FuturesOutcome(
                market_id=market.id,
                external_id=f"KXLALIGARELEGATION-27-ATM:{outcome_name}",
                name=outcome_name,
                current_probability=0.25,
            )
        )
    await session.commit()


def _events(payload) -> list[str]:
    """Home team names of the game cards. The key is `results`, not `events`.

    `.get("events", [])` reads `[]` on every response, so a probe keyed on the
    wrong name reports an empty route for a route that served the row. Asserted,
    because a missing key is a contract change and not an empty answer.
    """
    assert "results" in payload, f"no `results` key; got {sorted(payload)}"
    return [e["home_team"] for e in payload["results"]]


def _teams(payload) -> list[str]:
    assert "teams" in payload, f"no `teams` key; got {sorted(payload)}"
    return [t["name"] for t in payload["teams"]]


def _futures(payload) -> list[str]:
    assert "futures" in payload, f"no `futures` key; got {sorted(payload)}"
    return [f["name"] for f in payload["futures"]]


# ── The ship, one case per rail ─────────────────────────────────────────────


async def test_the_typed_spelling_reaches_the_game_card(maker, search):
    """The event rail: `Atletico Madrid` must find the accented fixture.

    Measured: this case survives the loss of EITHER mechanism on its own (see
    the module docstring) — the per-term fold and the team-resolution rescue are
    redundant here. It goes red when both are gone, which is the state master is
    in. Asserting the reader's outcome rather than one mechanism is deliberate.
    """
    async with maker() as session:
        await _seed_club(session)

    assert _events(await search(TYPED)) == [CLUB]


async def test_the_typed_spelling_reaches_the_team_card(maker, search):
    """The Teams rail, which rides the query REWRITE rather than the per-term
    expansion — `_build_team_search_filter` gates on FTS over the whole query."""
    async with maker() as session:
        await _seed_club(session)

    assert _teams(await search(TYPED)) == [CLUB]


async def test_the_typed_spelling_reaches_the_clubs_own_future(maker, search):
    """The futures rail — the one measured at 9 wrong rows out of 10."""
    async with maker() as session:
        await _seed_club(session)

    assert _futures(await search(TYPED)) == [FUTURE_NAME]


async def test_both_spellings_agree_on_every_rail(maker, search):
    """#6977's acceptance criterion, stated as the equality it actually claims.

    Asserting the typed spelling finds rows is not enough on its own — it would
    still pass if the accented spelling had silently REGRESSED to the same small
    set. Comparing the two makes the ship "the spellings agree", which is what
    the issue asks for, and catches a fold that widened one rail by narrowing
    another.
    """
    async with maker() as session:
        await _seed_club(session)

    typed, accented = await search(TYPED), await search(ACCENTED)

    assert _events(typed) == _events(accented) == [CLUB]
    assert _teams(typed) == _teams(accented) == [CLUB]
    assert _futures(typed) == _futures(accented) == [FUTURE_NAME]


async def test_an_unrelated_query_still_finds_nothing(maker, search):
    """The fold widens recall; it must not make search match anything.

    Without this, every case above would pass against a predicate that had
    collapsed to TRUE — the failure mode that makes a recall change look like a
    success right up until the page fills with noise.
    """
    async with maker() as session:
        await _seed_club(session)

    noise = await search("Sevilla")
    assert _events(noise) == []
    assert _teams(noise) == []
    assert _futures(noise) == []
