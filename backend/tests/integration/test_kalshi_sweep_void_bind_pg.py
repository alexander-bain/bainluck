"""#7035's void UPDATE, against a REAL asyncpg connection.

WHY A REAL SERVER, when the unit guards already drive this statement
---------------------------------------------------------------------

The sibling contract next door (``test_kalshi_sweep_settlement_bind_pg.py``)
records the failure this file exists to prevent: **asyncpg prepares with no
parameter types and lets Postgres infer them from the query text, so a parameter
sitting in a position the planner cannot type dies at PREPARE** — before a row is
read, whatever value is bound. ``AmbiguousParameterError`` shipped that way once
already.

``VOID_UPDATE_SQL`` puts a bind inside ``jsonb_build_object(...)``, which is a
``VARIADIC "any"`` function and therefore exactly such a position: Postgres has
no type to infer for an untyped parameter there. The statement carries an
explicit ``CAST(:updated_at AS text)`` for that reason, and the cast is the kind
of thing a later edit tidies away. Nothing cheaper than a real server can see it
— the statement compiles, the module imports, and the unit suite's session
doubles never prepare anything.

The behavioural claim is checked on a real ``jsonb`` column rather than a seeded
TEXT one: the void stamp lands, and — the half a merge would actually lose —
metadata the row already carried survives it.

Opt-in on ``SEARCH_TEST_DATABASE_URL``, following the other real-Postgres
contracts; CI's ``search-recall`` job provides a Postgres 15 service.
"""

import os
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from app.tasks.kalshi_resolution_sweep import VOID_UPDATE_SQL

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.skipif(
        not DB_URL,
        reason=(
            "set SEARCH_TEST_DATABASE_URL to run the real-Postgres void bind "
            "contract (CI job `search-recall` provides one)"
        ),
    ),
    pytest.mark.asyncio,
]

NOW = datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc)
FUTURE = NOW + timedelta(days=30)


@pytest.fixture
async def pg_session():
    """Real Postgres, real schema, real asyncpg parameter-type inference.

    Function-scoped for the reason the sibling gives: ``pytest.ini`` leaves
    ``asyncio_default_fixture_loop_scope`` unset, so a module-scoped async
    fixture would outlive the event loop that created its engine.
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


async def _seed(session, *, ext, metadata=None):
    """One resolved Kalshi row, inserted through raw ``text()`` on purpose.

    Raw rather than the ORM for the sibling's reason: this gate measures the
    driver's own type handling, and the ORM would adapt values on the way in and
    hide it. ``market_metadata`` is cast explicitly because an untyped NULL into
    a ``jsonb`` column is the same inference problem one layer down.
    """
    return (
        await session.execute(
            text("""
                INSERT INTO futures_markets
                    (name, source, category, mutually_exclusive, status,
                     external_id, resolution_date, expiration_time,
                     market_metadata)
                VALUES
                    (:name, 'kalshi', 'championship', TRUE, 'resolved',
                     :ext, :date, :date, CAST(:metadata AS jsonb))
                RETURNING id
                """),
            {
                "name": "Sweep void bind contract market",
                "ext": ext,
                "date": FUTURE,
                "metadata": metadata,
            },
        )
    ).scalar()


async def _metadata(session, market_id):
    return (
        await session.execute(
            text("SELECT market_metadata FROM futures_markets WHERE id = :id"),
            {"id": market_id},
        )
    ).scalar()


class TestTheVoidUpdatePrepares:
    async def test_the_void_stamp_lands_on_a_row_with_no_metadata(self, pg_session):
        """The PREPARE test. A bind inside ``jsonb_build_object`` must be typed.

        If the ``CAST(:updated_at AS text)`` is ever removed this raises
        ``AmbiguousParameterError`` here and nowhere else in the suite.
        """
        market_id = await _seed(pg_session, ext="KXBIND-VOID-26", metadata=None)

        await pg_session.execute(
            text(VOID_UPDATE_SQL),
            {"id": market_id, "updated_at": NOW.isoformat()},
        )

        stored = await _metadata(pg_session, market_id)
        assert stored["venue_voided"] is True
        assert stored["venue_voided_at"] == NOW.isoformat()

    async def test_the_merge_keeps_metadata_the_row_already_carried(self, pg_session):
        """🔴 THE HALF A PLAIN ASSIGNMENT WOULD LOSE.

        ``market_metadata["shape"]`` carries the side-kind the serializers read.
        A row that records a status fact must not forget what kind of market it
        is, and ``||`` against ``COALESCE`` is what keeps that true.
        """
        market_id = await _seed(
            pg_session,
            ext="KXBIND-VOID-MERGE-26",
            metadata='{"shape": {"side_kind": "team"}, "polymarket_event_id": "934163"}',
        )

        await pg_session.execute(
            text(VOID_UPDATE_SQL),
            {"id": market_id, "updated_at": NOW.isoformat()},
        )

        stored = await _metadata(pg_session, market_id)
        assert stored["venue_voided"] is True
        assert stored["shape"] == {"side_kind": "team"}, (
            "the merge dropped pre-existing metadata — this is the assignment "
            "bug the COALESCE/|| spelling exists to prevent"
        )
        assert stored["polymarket_event_id"] == "934163"

    async def test_a_second_void_write_is_idempotent(self, pg_session):
        """The sweep re-reads rows it has already swept (`provisional_recheck`)."""
        market_id = await _seed(pg_session, ext="KXBIND-VOID-TWICE-26", metadata=None)
        params = {"id": market_id, "updated_at": NOW.isoformat()}

        await pg_session.execute(text(VOID_UPDATE_SQL), params)
        await pg_session.execute(text(VOID_UPDATE_SQL), params)

        stored = await _metadata(pg_session, market_id)
        assert stored == {
            "venue_voided": True,
            "venue_voided_at": NOW.isoformat(),
        }
