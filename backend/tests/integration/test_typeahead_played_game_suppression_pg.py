"""A played game's market leaves the search pool — executed by a REAL PostgreSQL. #4914.

## Why a real server is the only witness

The ship (#4914) is one predicate added to the futures pool both `/search` and
`/typeahead` build: the market's own game must not already be Final. Its whole
risk is a **NULL semantics** question, and NULL semantics are exactly what a
session double cannot answer.

Two thirds of the pool — 32,483 of the ~50,576 markets production admitted when
this was measured (2026-09-11 ~01:55Z, backend `9ed5a436`) — carry
`event_id IS NULL`. The natural spelling of "the linked event is not finished"::

    ~FuturesMarket.event_id.in_(select(Event.id).where(Event.status.in_(...)))

is wrong on every one of them, because `NULL NOT IN (...)` evaluates to NULL,
not TRUE, and a NULL WHERE term drops the row. It reads like a tightening and it
silently deletes two thirds of search recall. The shipped spelling is
`NOT EXISTS`, which is correct on a NULL correlation by construction.

`tests/test_typeahead_drops_a_played_games_market_4914.py` is the cheap half: it
compiles the clause and asserts the emitted SQL is `NOT EXISTS` and correlated.
It cannot tell you what PostgreSQL then does with those rows. **This file is the
oracle** — it seeds the four cases that matter and asserts which ids come back.

## The four rows, and why each is here

    completed game  -> SUPPRESSED   the ship (574 such markets in production)
    closed game     -> SUPPRESSED   the venue's word for the same thing (9)
    live game       -> SURVIVES     200 markets; suppressing these empties the
                                    dropdown during the game a reader is watching
    no game at all  -> SURVIVES     32,483 markets; the NULL trap above

Also seeded: a market on a completed game whose `resolution_date` is in the
FUTURE. That is not a decoration — it is the production specimen. `Set 2 Winner:
Swiatek vs Zheng` (market 60299706, tier 1) was served as row 7 of `q=swiatek`
with `No 100%` four days after that match ended, precisely because its
`resolution_date` is 2026-09-13. A test that let the old `resolution_date`
filter do the work would pass without the ship.

Opt-in on ``SEARCH_TEST_DATABASE_URL``, following the other bind contracts —
CI's ``search-recall`` job provides a Postgres 15 service. Registered in
``tests/test_pg_gate_seed_completeness.py``'s ``COVERED`` tuple AND given its own
CI step; a file with only one of those two wirings never runs and the job stays
green without it.
"""

import os
from datetime import datetime, timedelta, timezone

import pytest

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.skipif(
        not DB_URL,
        reason=(
            "set SEARCH_TEST_DATABASE_URL to run the real-Postgres played-game "
            "suppression contract (CI job `search-recall` provides one)"
        ),
    ),
    pytest.mark.asyncio,
]


@pytest.fixture
async def pg_session():
    """Real Postgres, real schema, real asyncpg NULL handling.

    Function-scoped: ``pytest.ini`` leaves ``asyncio_default_fixture_loop_scope``
    unset, so a module-scoped async fixture would outlive the event loop that
    created its engine.
    """
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    from app.services.database import Base

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session

    await engine.dispose()


async def _seed(session):
    """One market per game state, plus one with no game at all.

    Raw `text()` INSERTs deliberately, the same way the other bind contracts in
    this directory write theirs: the point is what the driver and the server do
    with these rows, not what the ORM does on the way in.

    Every market is `status='open'` with a FUTURE `resolution_date`, so the two
    filters that were already on the pool admit all five. Anything suppressed
    below is suppressed by the ship and by nothing else.
    """
    from sqlalchemy import text

    now = datetime.now(timezone.utc)
    future = now + timedelta(days=3)

    sport_id = (
        await session.execute(
            text(
                """
                INSERT INTO sports (key, name, title, active)
                VALUES ('tennis_atp', 'Tennis', 'Tennis', TRUE)
                RETURNING id
                """
            )
        )
    ).scalar()

    async def _event(status, commence, completed_at=None):
        return (
            await session.execute(
                text(
                    """
                    INSERT INTO events
                        (sport_id, home_team_name, away_team_name,
                         commence_time, status, completed_at)
                    VALUES (:sid, 'Swiatek', 'Zheng', :ct, :st, :ca)
                    RETURNING id
                    """
                ),
                {
                    "sid": sport_id,
                    "ct": commence,
                    "st": status,
                    "ca": completed_at,
                },
            )
        ).scalar()

    async def _market(name, event_id, external_id):
        return (
            await session.execute(
                text(
                    """
                    INSERT INTO futures_markets
                        (name, source, category, mutually_exclusive, status,
                         resolution_date, external_id, llm_sport_category,
                         event_id)
                    VALUES (:n, 'polymarket', 'prop', TRUE, 'open', :rd, :xid,
                            'tennis', :eid)
                    RETURNING id
                    """
                ),
                {"n": name, "rd": future, "xid": external_id, "eid": event_id},
            )
        ).scalar()

    ids = {}
    completed = await _event("completed", now - timedelta(days=4), now - timedelta(days=4))
    closed = await _event("closed", now - timedelta(days=4), now - timedelta(days=4))
    live = await _event("live", now - timedelta(hours=1))
    scheduled = await _event("scheduled", now + timedelta(days=1))

    ids["completed"] = await _market("Set 2 Winner: played", completed, "PGX-4914-A")
    ids["closed"] = await _market("Set 2 Winner: closed", closed, "PGX-4914-B")
    ids["live"] = await _market("Set 2 Winner: in progress", live, "PGX-4914-C")
    ids["scheduled"] = await _market("Set 2 Winner: upcoming", scheduled, "PGX-4914-D")
    ids["unattached"] = await _market("Announcer prop, no game", None, "PGX-4914-E")

    await session.commit()
    return ids


async def _surviving(session):
    """Ids the pool still admits, under the REAL production predicate tuple."""
    from sqlalchemy import or_, select

    from app.models import FuturesMarket
    from app.routes.events import _futures_game_already_played

    now = datetime.now(timezone.utc)
    rows = await session.execute(
        select(FuturesMarket.id).where(
            FuturesMarket.status == "open",
            or_(
                FuturesMarket.resolution_date.is_(None),
                FuturesMarket.resolution_date >= now,
            ),
            _futures_game_already_played(),
        )
    )
    return set(rows.scalars().all())


class TestAPlayedGamesMarketLeavesThePool:
    async def test_the_seed_is_not_vacuous(self, pg_session):
        """Every row is `open` and unresolved, so the pre-#4914 pool takes all
        five. If this fails, nothing below is measuring the ship."""
        from sqlalchemy import or_, select

        from app.models import FuturesMarket

        ids = await _seed(pg_session)
        now = datetime.now(timezone.utc)
        rows = await pg_session.execute(
            select(FuturesMarket.id).where(
                FuturesMarket.status == "open",
                or_(
                    FuturesMarket.resolution_date.is_(None),
                    FuturesMarket.resolution_date >= now,
                ),
            )
        )
        assert set(rows.scalars().all()) == set(ids.values())

    async def test_a_completed_games_market_is_suppressed(self, pg_session):
        """THE SHIP. `Set 2 Winner: Swiatek vs Zheng` stops being offered."""
        ids = await _seed(pg_session)
        assert ids["completed"] not in await _surviving(pg_session)

    async def test_a_closed_games_market_is_suppressed(self, pg_session):
        """`closed` is the venue's word for Final; both mean Final to a client."""
        ids = await _seed(pg_session)
        assert ids["closed"] not in await _surviving(pg_session)

    async def test_a_live_games_market_survives(self, pg_session):
        """🔴 The regression that would hurt most: suppressing a market on a game
        that is being played right now empties the dropdown during the game the
        reader opened the app to watch."""
        ids = await _seed(pg_session)
        assert ids["live"] in await _surviving(pg_session)

    async def test_an_upcoming_games_market_survives(self, pg_session):
        ids = await _seed(pg_session)
        assert ids["scheduled"] in await _surviving(pg_session)

    async def test_an_unattached_market_survives_the_null_correlation(self, pg_session):
        """🔴 THE NULL TRAP, on a real server. 32,483 production markets carry
        `event_id IS NULL`. Re-spell the helper as `~event_id.in_(...)` and this
        row vanishes — along with two thirds of search recall — while every
        other test in this file still passes."""
        ids = await _seed(pg_session)
        assert ids["unattached"] in await _surviving(pg_session)

    async def test_exactly_the_played_games_are_gone(self, pg_session):
        """The whole cut in one assertion, so a future widening of
        `SETTLED_STATUSES` has to come here and say so."""
        ids = await _seed(pg_session)
        assert await _surviving(pg_session) == {
            ids["live"],
            ids["scheduled"],
            ids["unattached"],
        }
