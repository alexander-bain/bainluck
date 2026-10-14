"""The resolution sweep's settlement UPDATE, against a REAL asyncpg connection.

WHY A REAL SERVER, when 127 unit guards are green over this statement
---------------------------------------------------------------------
#2722 gave ``UPDATE_SQL`` two shapes that only a type system can reject::

    resolution_date = COALESCE(:resolution_date, resolution_date)
    status          = CASE WHEN :venue_settled THEN 'resolved' ELSE status END

asyncpg prepares with **no parameter types** and lets Postgres infer them from
the query text, so a parameter that appears only in a position the planner cannot
type dies at PREPARE — before a row is read, whatever value is bound. That is
exactly how the sibling drain shipped with ``AmbiguousParameterError`` and had
never completed one work selection through its own endpoint
(``test_kalshi_fabricated_loss_bind_contract_pg.py``, measured 2026-09-05).

Nothing cheaper can see it. The statement COMPILES; the module IMPORTS; sqlite
types binds by value and is happy to put a Python ``bool`` in a ``CASE WHEN``;
the unit suite's session doubles never prepare anything. A ``None`` bound into
``COALESCE`` and a ``bool`` bound into ``CASE WHEN`` only meet a type system
here.

The behavioural claim is checked too, on real columns rather than on a seeded
TEXT table: the settled row comes out ``resolved`` with ``settled_at`` stamped
and its dates intact, and the unsettled control comes out untouched.

Opt-in on ``SEARCH_TEST_DATABASE_URL``, following the other real-Postgres
contracts; CI's ``search-recall`` job provides a Postgres 15 service and asserts
the gate did not silently skip.
"""

import os
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from app.tasks.kalshi_resolution_sweep import UPDATE_SQL

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.skipif(
        not DB_URL,
        reason=(
            "set SEARCH_TEST_DATABASE_URL to run the real-Postgres sweep "
            "settlement bind contract (CI job `search-recall` provides one)"
        ),
    ),
    pytest.mark.asyncio,
]

NOW = datetime(2026, 9, 5, 19, 30, tzinfo=timezone.utc)
FUTURE = NOW + timedelta(days=30)


@pytest.fixture
async def pg_session():
    """Real Postgres, real schema, real asyncpg parameter-type inference.

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


async def _seed(session, *, ext, settled_at=None):
    """One open Kalshi row, inserted through raw ``text()`` on purpose.

    This gate exists to exercise the driver's own type handling; the ORM would
    adapt values on the way in and hide the thing being measured. Python-side
    column defaults therefore do not apply, so every NOT NULL column with only a
    ``default=`` is supplied explicitly.
    """
    return (
        await session.execute(
            text("""
                INSERT INTO futures_markets
                    (name, source, category, mutually_exclusive, status,
                     external_id, resolution_date, expiration_time, settled_at)
                VALUES
                    (:name, 'kalshi', 'championship', TRUE, 'open',
                     :ext, :date, :date, :settled_at)
                RETURNING id
                """),
            {
                "name": "Sweep settlement bind contract market",
                "ext": ext,
                "date": FUTURE,
                "settled_at": settled_at,
            },
        )
    ).scalar()


async def _read(session, market_id):
    return (
        await session.execute(
            text("""
                SELECT status, settled_at, resolution_date, expiration_time
                FROM futures_markets WHERE id = :id
                """),
            {"id": market_id},
        )
    ).first()


class TestTheSettlementUpdatePrepares:
    async def test_a_settled_write_flips_status_and_keeps_its_dates(self, pg_session):
        market_id = await _seed(pg_session, ext="KXBIND-SETTLED-26")

        await pg_session.execute(
            text(UPDATE_SQL),
            {
                "id": market_id,
                "resolution_date": FUTURE,
                "expiration_time": FUTURE,
                "venue_settled": True,
                "updated_at": NOW,
            },
        )
        await pg_session.commit()

        status, settled_at, resolution_date, _expiry = await _read(
            pg_session, market_id
        )
        assert status == "resolved"
        assert settled_at == NOW
        assert resolution_date == FUTURE, (
            "the row's stored date is a month out and stays a month out — the "
            "#2722 cohort settles with no date movement at all"
        )

    async def test_a_null_date_bind_prepares_and_preserves(self, pg_session):
        """``COALESCE($1, resolution_date)`` with ``$1`` bound to ``None``.

        This is the shape the dateless settlement write uses, and the one a
        server has to be able to type. sqlite cannot fail it; Postgres can.
        """
        market_id = await _seed(pg_session, ext="KXBIND-NODATE-26")

        await pg_session.execute(
            text(UPDATE_SQL),
            {
                "id": market_id,
                "resolution_date": None,
                "expiration_time": None,
                "venue_settled": True,
                "updated_at": NOW,
            },
        )
        await pg_session.commit()

        status, _settled_at, resolution_date, expiry = await _read(
            pg_session, market_id
        )
        assert status == "resolved"
        assert resolution_date == FUTURE and expiry == FUTURE

    async def test_an_unsettled_write_leaves_the_row_open(self, pg_session):
        market_id = await _seed(pg_session, ext="KXBIND-OPEN-26")
        earlier = NOW - timedelta(days=1)

        await pg_session.execute(
            text(UPDATE_SQL),
            {
                "id": market_id,
                "resolution_date": earlier,
                "expiration_time": FUTURE,
                "venue_settled": False,
                "updated_at": NOW,
            },
        )
        await pg_session.commit()

        status, settled_at, resolution_date, _expiry = await _read(
            pg_session, market_id
        )
        assert status == "open"
        assert settled_at is None
        assert resolution_date == earlier

    async def test_an_existing_settled_at_survives(self, pg_session):
        stamped = NOW - timedelta(days=3)
        market_id = await _seed(
            pg_session, ext="KXBIND-STAMPED-26", settled_at=stamped
        )

        await pg_session.execute(
            text(UPDATE_SQL),
            {
                "id": market_id,
                "resolution_date": FUTURE,
                "expiration_time": FUTURE,
                "venue_settled": True,
                "updated_at": NOW,
            },
        )
        await pg_session.commit()

        _status, settled_at, _rd, _exp = await _read(pg_session, market_id)
        assert settled_at == stamped
