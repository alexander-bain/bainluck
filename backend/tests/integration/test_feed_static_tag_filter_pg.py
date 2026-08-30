"""The static tag filter, executed by a REAL PostgreSQL through asyncpg.

## Why a real server is the only witness

`/api/feed?tags=["sport:soccer"]` served zero events and zero futures for every
static tag in every namespace, from the day tag filtering was written. The
predicate was built as::

    Event.event_tags.op("@>")(cast(json.dumps(["sport:soccer"]), JSONB))

`cast()` over a bare Python value types the bind as the cast target, and
``JSONB``'s bind processor serializes it — a second time. The wire value became
the JSON *string* ``'"[\\"sport:soccer\\"]"'`` instead of the JSON *array*
``'["sport:soccer"]'``, and PostgreSQL answered `false` to every containment
test. No exception, no warning, no log line: `@>` is total on well-formed JSONB.

Nothing without a real server and a real driver could see it. The generated SQL
differs by one token (`$1::JSONB` vs `$1::VARCHAR`) and the *broken* one is the
one that reads correctly. Session doubles never run a bind processor at all.

The cheap halves live in `tests/test_jsonb_containment_bind.py` (the wire value)
and `tests/test_feed_static_tag_filter_reaches_sql.py` (the predicate is on the
production code path). This file is the oracle: it asserts that rows come back.

Opt-in on ``SEARCH_TEST_DATABASE_URL``, following the other bind contracts —
CI's ``search-recall`` job provides a Postgres 15 service.
"""

import os
from datetime import datetime, timedelta, timezone

import pytest

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.skipif(
        not DB_URL,
        reason=(
            "set SEARCH_TEST_DATABASE_URL to run the real-Postgres static tag "
            "filter contract (CI job `search-recall` provides one)"
        ),
    ),
    pytest.mark.asyncio,
]


@pytest.fixture
async def pg_session():
    """Real Postgres, real schema, real asyncpg type coercion.

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


async def _seed_tagged_rows(session):
    """One soccer event and one soccer futures market, each carrying its tag.

    Raw `text()` INSERTs deliberately — this gate exists to exercise the
    driver's own type coercion on the way OUT, and the rows on the way in are
    written the same way the production writers write them.
    """
    from sqlalchemy import text

    now = datetime.now(timezone.utc)

    sport_id = (
        await session.execute(
            text(
                """
                INSERT INTO sports (key, name, title, active)
                VALUES ('soccer_epl', 'EPL', 'EPL', TRUE)
                RETURNING id
                """
            )
        )
    ).scalar()

    event_id = (
        await session.execute(
            text(
                """
                INSERT INTO events
                    (sport_id, home_team_name, away_team_name, commence_time,
                     status, event_tags)
                VALUES
                    (:sid, 'Bournemouth', 'Everton', :ct, 'scheduled',
                     CAST(:tags AS jsonb))
                RETURNING id
                """
            ),
            {
                "sid": sport_id,
                "ct": now + timedelta(hours=3),
                "tags": '["sport:soccer", "tier:1"]',
            },
        )
    ).scalar()

    market_id = (
        await session.execute(
            text(
                """
                INSERT INTO futures_markets
                    (name, source, category, mutually_exclusive, status,
                     resolution_date, external_id, llm_sport_category,
                     market_tags)
                VALUES
                    ('Premier League Winner', 'kalshi', 'championship', TRUE,
                     'open', :rd, 'PGTAGCONTRACT-EPL', 'soccer',
                     CAST(:tags AS jsonb))
                RETURNING id
                """
            ),
            {"rd": now + timedelta(days=60), "tags": '["sport:soccer", "tier:1"]'},
        )
    ).scalar()

    await session.commit()
    return sport_id, event_id, market_id


class TestContainmentActuallyMatchesRows:
    """The assertion the whole defect turns on: `@>` must return the row."""

    async def test_the_helper_finds_a_tagged_event(self, pg_session):
        from sqlalchemy import select

        from app.models.models import Event
        from app.utils.jsonb_containment import jsonb_contains

        _sid, event_id, _mid = await _seed_tagged_rows(pg_session)

        rows = (
            await pg_session.execute(
                select(Event.id).where(
                    jsonb_contains(Event.event_tags, ["sport:soccer"])
                )
            )
        ).scalars().all()

        assert rows == [event_id]

    async def test_the_helper_finds_a_tagged_futures_market(self, pg_session):
        from sqlalchemy import select

        from app.models.models import FuturesMarket
        from app.utils.jsonb_containment import jsonb_contains

        _sid, _eid, market_id = await _seed_tagged_rows(pg_session)

        rows = (
            await pg_session.execute(
                select(FuturesMarket.id).where(
                    jsonb_contains(FuturesMarket.market_tags, ["sport:soccer"])
                )
            )
        ).scalars().all()

        assert rows == [market_id]

    async def test_the_broken_spelling_returns_nothing_on_the_same_row(
        self, pg_session
    ):
        """Pin the defect against the live server, so the premise stays proven.

        Same row, same operator, same column — only the bind differs, and the
        broken bind finds nothing. If this ever starts returning the row, the
        double-encoding has been fixed upstream and this whole family of guards
        can be reconsidered.
        """
        import json

        from sqlalchemy import cast, select
        from sqlalchemy.dialects.postgresql import JSONB

        from app.models.models import Event

        await _seed_tagged_rows(pg_session)

        rows = (
            await pg_session.execute(
                select(Event.id).where(
                    Event.event_tags.op("@>")(
                        cast(json.dumps(["sport:soccer"]), JSONB)
                    )
                )
            )
        ).scalars().all()

        assert rows == []

    async def test_a_tag_that_is_not_present_still_matches_nothing(self, pg_session):
        """The fix must not turn containment into a no-op that matches everything."""
        from sqlalchemy import select

        from app.models.models import Event
        from app.utils.jsonb_containment import jsonb_contains

        await _seed_tagged_rows(pg_session)

        rows = (
            await pg_session.execute(
                select(Event.id).where(
                    jsonb_contains(Event.event_tags, ["sport:basketball"])
                )
            )
        ).scalars().all()

        assert rows == []

    async def test_multi_tag_containment_is_conjunctive(self, pg_session):
        """`@>` on an array means "carries ALL of these", and must keep meaning it."""
        from sqlalchemy import select

        from app.models.models import Event
        from app.utils.jsonb_containment import jsonb_contains

        _sid, event_id, _mid = await _seed_tagged_rows(pg_session)

        both = (
            await pg_session.execute(
                select(Event.id).where(
                    jsonb_contains(Event.event_tags, ["sport:soccer", "tier:1"])
                )
            )
        ).scalars().all()
        assert both == [event_id]

        one_absent = (
            await pg_session.execute(
                select(Event.id).where(
                    jsonb_contains(Event.event_tags, ["sport:soccer", "tier:4"])
                )
            )
        ).scalars().all()
        assert one_absent == []


class TestTheProductionBuildersFindTheRows:
    """End of the chain: the real pool queries, run by the real server."""

    async def test_the_futures_pool_specs_return_the_tagged_market(self, pg_session):
        import app.routes.feed as feed_mod

        _sid, _eid, market_id = await _seed_tagged_rows(pg_session)
        now = datetime.now(timezone.utc)

        _filters, specs = feed_mod._discover_candidate_pool_specs(
            now, None, ["sport:soccer"]
        )

        found = set()
        for _name, query, limit in specs:
            ids = (await pg_session.execute(query.limit(limit))).scalars().all()
            found.update(ids)

        assert market_id in found, (
            "no Discover futures pool returned the tagged market — a "
            "tag-filtered feed request serves an empty page"
        )

    async def test_the_pools_exclude_a_market_without_the_tag(self, pg_session):
        """The filter must still filter."""
        import app.routes.feed as feed_mod

        _sid, _eid, market_id = await _seed_tagged_rows(pg_session)
        now = datetime.now(timezone.utc)

        _filters, specs = feed_mod._discover_candidate_pool_specs(
            now, None, ["sport:basketball"]
        )

        found = set()
        for _name, query, limit in specs:
            ids = (await pg_session.execute(query.limit(limit))).scalars().all()
            found.update(ids)

        assert market_id not in found
