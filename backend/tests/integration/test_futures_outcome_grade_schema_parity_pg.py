"""A metadata-built database gives `futures_outcomes.is_winner` PRODUCTION's semantics.

## Why this file exists, stated as the defect it catches

`b3e46d34` widened the column to `Mapped[Optional[bool]]` so a test database
could finally express "nobody graded this" — the state 12-CAL's `graded` count,
gotcha #21 and Queue 299's ungraded-market rung all rest on. **CERT-521 blocked
it**, and the finding was right: nullability was only half of parity.

Production's DDL is `boolean NULL DEFAULT false` — `add_futures_tables.py`
declared `server_default='false'`. The model carried only a *client-side*
`default=False`, which fires on an ORM insert and is invisible to
`text("INSERT ...")`. So:

* **before** the widening, a raw INSERT omitting `is_winner` failed loudly
  against the NOT NULL a metadata-built schema had and production did not;
* **after** it, the same statement would have stored **NULL here and FALSE in
  production**.

Raw INSERT is precisely how the real-Postgres gates in this directory seed. A
gate could therefore have manufactured "ungraded truth" out of a column it simply
forgot to name, and certified a calibration population that cannot exist —
recreating the test/prod split the widening was for, one layer down.
`tests/test_pg_gate_seed_completeness.py` states the asymmetry as its own reason
to exist: *a raw INSERT bypasses SQLAlchemy's Python-side `default=`; only a
`server_default` is excused.*

## Why it needs a real Postgres

The metadata assertions in `tests/test_model_nullability_matches_production.py`
prove what the compiler EMITS. They cannot prove what a server DOES with it, and
the emitted-vs-observed gap is the entire history above: four green metadata
guards sat over `is_winner BOOLEAN,` and none of them could see the missing
DEFAULT. A default is applied by the database, so the database has to be asked.

Opt-in on `SEARCH_TEST_DATABASE_URL`, following its neighbours: `initdb` dies on
`shmget` in the agent sandbox, so CI's `search-recall` job is the only reader,
and that job's skip-detector refuses to let an unrun gate read as a passing one.

## The four facts, and the production reading each is pinned to

Measured against `information_schema.columns` and the outcome table on
production, 2026-08-31:

    is_winner: data_type = boolean, is_nullable = YES, column_default = false
    is_winner NULL, resolution_source NULL          2,536
    is_winner NOT NULL, resolution_source NULL    778,306
    is_winner NOT NULL, resolution_source set   3,112,284
    is_winner NULL, resolution_source set               0
"""

from __future__ import annotations

import os

import pytest

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL,
        reason=(
            "set SEARCH_TEST_DATABASE_URL to run the futures_outcomes grade "
            "schema-parity gate (CI job: search-recall)"
        ),
    ),
]

PARITY_MARKET_ID = 910157
PARITY_OUTCOME_ID = 910158


@pytest.fixture
async def db():
    """A real Postgres carrying the schema `create_all` builds from the model."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.models.models  # noqa: F401  — registers every table on Base
    from app.services.database import Base

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session

    await engine.dispose()


async def _seed_market(session):
    """One market, seeded with raw SQL exactly the way the gates around this do."""
    from sqlalchemy import text

    await session.execute(
        text(
            "INSERT INTO futures_markets (id, source, external_id, name, "
            "category, status, mutually_exclusive) VALUES "
            "(:id, 'kalshi', 'KXPARITY', 'Parity Probe', 'futures', 'open', true)"
        ),
        {"id": PARITY_MARKET_ID},
    )


async def _read_is_winner(session, external_id):
    from sqlalchemy import text

    return (
        await session.execute(
            text(
                "SELECT is_winner FROM futures_outcomes WHERE external_id = :e"
            ),
            {"e": external_id},
        )
    ).scalar()


class TestTheColumnProductionActuallyHas:
    async def test_the_built_column_matches_productions_information_schema_row(
        self, db
    ):
        """The whole of CERT-521, read back off a server instead of a compiler.

        `is_nullable` alone was already green on the blocked head. It is
        `column_default` that was NULL there and `false` here, and the two have
        to be asserted together — that pairing IS the parity claim.
        """
        from sqlalchemy import text

        row = (
            await db.execute(
                text(
                    "SELECT data_type, is_nullable, column_default "
                    "FROM information_schema.columns "
                    "WHERE table_name = 'futures_outcomes' "
                    "AND column_name = 'is_winner'"
                )
            )
        ).first()

        assert row is not None, "futures_outcomes.is_winner was not created at all"
        data_type, is_nullable, column_default = row
        assert (data_type, is_nullable, column_default) == (
            "boolean",
            "YES",
            "false",
        ), (
            f"the metadata-built column is {data_type} / nullable={is_nullable} / "
            f"default={column_default!r}, while production is boolean / YES / "
            f"'false' (information_schema, 2026-08-31). Every real-Postgres gate "
            f"in this directory builds its schema this way, so a difference here "
            f"is a difference in what those gates are allowed to prove."
        )


class TestWhatEachInsertShapeStores:
    async def test_a_raw_insert_that_omits_is_winner_stores_false(self, db):
        """CERT-521's [P1], as the statement that would have written the wrong row.

        Without the server default this INSERT stores NULL, and NULL is
        "nobody graded this" — a state gotcha #21 forbids publishing as a loss.
        Production stores FALSE for the identical statement.
        """
        await _seed_market(db)

        from sqlalchemy import text

        await db.execute(
            text(
                "INSERT INTO futures_outcomes (market_id, external_id, name) "
                "VALUES (:m, 'OMITTED', 'Omitted')"
            ),
            {"m": PARITY_MARKET_ID},
        )

        assert await _read_is_winner(db, "OMITTED") is False, (
            "a raw INSERT omitting is_winner did not land FALSE. The column has "
            "lost its server default, so this test database now manufactures "
            "ungraded truth out of an unnamed field while production writes an "
            "unsettled FALSE."
        )

    async def test_an_explicit_null_is_still_storable(self, db):
        """And the widening still buys what it was for.

        A server default that made NULL unreachable would close CERT-521 by
        undoing `b3e46d34` — the fixture that started all of this could not be
        seeded again. Both properties are one column's, so both are asserted.
        """
        await _seed_market(db)

        from sqlalchemy import text

        await db.execute(
            text(
                "INSERT INTO futures_outcomes (market_id, external_id, name, "
                "is_winner) VALUES (:m, 'UNGRADED', 'Ungraded', NULL)"
            ),
            {"m": PARITY_MARKET_ID},
        )

        assert await _read_is_winner(db, "UNGRADED") is None, (
            "an explicit NULL did not survive. 'Nobody graded this' is not "
            "expressible again, which is the state 12-CAL, gotcha #21 and the "
            "ungraded-market rung all distinguish from a graded loss."
        )

    async def test_the_orm_writers_are_unchanged(self, db):
        """No writer moves. Unsettled-but-tracked is FALSE, as it has always been.

        The client-side `default=False` still fires — including for an explicit
        `None`, which is how `test_futures_price_refresh_writes_pg.py` seeds its
        tri-state halves. If this ever starts landing NULL, ordinary polling has
        begun manufacturing unknown truth and the ungraded-market rung will start
        excluding live markets from the curve.
        """
        from app.models.models import FuturesMarket, FuturesOutcome

        market = FuturesMarket(
            source="kalshi",
            external_id="KXPARITY-ORM",
            name="Parity Probe ORM",
            category="futures",
            market_tier=1,
            status="open",
        )
        db.add(market)
        await db.flush()

        omitted = FuturesOutcome(
            market_id=market.id, external_id="ORM-OMITTED", name="Omitted"
        )
        explicit_none = FuturesOutcome(
            market_id=market.id,
            external_id="ORM-NONE",
            name="None",
            is_winner=None,
        )
        db.add_all([omitted, explicit_none])
        await db.flush()

        assert await _read_is_winner(db, "ORM-OMITTED") is False
        assert await _read_is_winner(db, "ORM-NONE") is False
