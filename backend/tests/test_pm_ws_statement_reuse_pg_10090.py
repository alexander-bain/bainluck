"""#10090: real asyncpg checks for reused price and field-rank bindings.

Opt in with TEST_PM_WRITER_DSN pointing to a bl_argon10090_* database on
localhost:5432. Every test owns a new private schema; the replay's public
seed tables and every other local lab remain untouched.
"""

import asyncio
import os
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.tasks import polymarket_ws as task
from app.utils.futures_rank import rerank_market_fields_stmt

BEFORE = datetime(2020, 1, 1, tzinfo=timezone.utc)


def _local_writer_url(dsn):
    url = make_url(dsn)
    if (
        url.get_backend_name() != "postgresql"
        or url.host not in {"localhost", "127.0.0.1", "::1"}
        or url.port != 5432
        or not (url.database or "").startswith("bl_argon10090_")
        or url.query
    ):
        raise ValueError("TEST_PM_WRITER_DSN must name local :5432/bl_argon10090_*")
    return url.set(drivername="postgresql+asyncpg")


@pytest.mark.parametrize(
    "dsn",
    [
        "postgresql://example.com:5432/bl_argon10090_task2_20261030",
        "postgresql://localhost:5433/bl_argon10090_task2_20261030",
        "postgresql://localhost:5432/bainluck",
        "postgresql://localhost:5432/bl_argon10090_task2_20261030?host=example.com",
    ],
)
def test_pg_guard_rejects_foreign_database_or_connection_override(dsn):
    with pytest.raises(ValueError, match="must name local"):
        _local_writer_url(dsn)


@pytest_asyncio.fixture
async def writer_db():
    dsn = os.environ.get("TEST_PM_WRITER_DSN")
    if not dsn:
        pytest.skip("set TEST_PM_WRITER_DSN for the private-schema asyncpg guards")
    url = _local_writer_url(dsn)
    schema = f"argon_stmt_10090_guard_{os.getpid()}_{uuid4().hex[:12]}"
    engine = create_async_engine(
        url,
        # Sequential writes reuse asyncpg's prepared-statement cache. A second
        # connection lets the binary-pair guard hold a lock beside its writer.
        pool_size=2,
        max_overflow=0,
        connect_args={"server_settings": {"search_path": schema}},
    )
    created = False
    try:
        async with engine.begin() as connection:
            await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            created = True
            # Only columns these two real production statements read or write.
            await connection.execute(
                text(
                    f'CREATE TABLE "{schema}".futures_outcomes ('
                    "id INTEGER PRIMARY KEY, market_id INTEGER NOT NULL, "
                    "current_probability NUMERIC(7, 6), rank INTEGER, "
                    "last_updated TIMESTAMPTZ NOT NULL, price_changed_at TIMESTAMPTZ, "
                    "is_winner BOOLEAN, resolution_source VARCHAR(100))"
                )
            )
        yield engine
    finally:
        try:
            if created:
                async with engine.begin() as connection:
                    await connection.execute(
                        text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
                    )
        finally:
            await engine.dispose()


async def _seed(engine, rows):
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO futures_outcomes "
                "(id, market_id, current_probability, rank, last_updated, price_changed_at) "
                "VALUES (:id, :market, :price, :rank, :before, :before)"
            ),
            [
                {
                    "id": oid,
                    "market": market,
                    "price": price,
                    "rank": rank,
                    "before": BEFORE,
                }
                for oid, market, price, rank in rows
            ],
        )


async def _read(engine):
    async with engine.connect() as connection:
        rows = (
            (
                await connection.execute(
                    text(
                        "SELECT id, market_id, current_probability, rank, last_updated, "
                        "price_changed_at FROM futures_outcomes ORDER BY id"
                    )
                )
            )
            .mappings()
            .all()
        )
    return {row["id"]: dict(row) for row in rows}


async def _prices(engine, reused, chunk, *, force_ids=None, nowait=False):
    if reused:
        statement, parameters = task.chunk_price_update_execution(
            chunk, force_ids=force_ids, nowait=nowait
        )
    else:
        statement = task.chunk_price_update_stmt(
            chunk, force_ids=force_ids, nowait=nowait
        )
        parameters = None
    async with AsyncSession(engine) as session, session.begin():
        result = await session.execute(statement, parameters)
        return [dict(row) for row in result.mappings().all()]


async def _ranks(engine, reused, market_ids):
    if reused:
        statement, parameters = task.pm_rerank_market_fields_execution(market_ids)
    else:
        statement, parameters = rerank_market_fields_stmt(market_ids), None
    async with AsyncSession(engine) as session, session.begin():
        return (await session.execute(statement, parameters)).rowcount


@pytest.mark.parametrize("reused", [False, True], ids=["baseline", "reused"])
async def test_pg_successive_inputs_keep_precision_force_and_returned_order(
    writer_db, reused
):
    await _seed(
        writer_db,
        [(11, 101, Decimal("0.051235"), 2), (12, 202, Decimal("0.750000"), 1)],
    )
    first = await _prices(
        writer_db,
        reused,
        {12: Decimal("0.8123456789"), 11: Decimal("0.0512345678")},
        force_ids=set(),
    )
    assert [(row["id"], row["ord"], row["current_probability"]) for row in first] == [
        (12, 1, Decimal("0.812346"))
    ]
    assert first[0]["quote_moved"] is True
    assert first[0]["market_id"] == 202
    assert first[0]["is_winner"] is None and first[0]["resolution_source"] is None
    assert first[0]["database_clock"] >= first[0]["last_updated"] > BEFORE
    assert (await _read(writer_db))[11]["last_updated"] == BEFORE

    latest = {11: Decimal("0.0623456789"), 12: 0.1234567}
    second = await _prices(writer_db, reused, latest, force_ids=set())
    assert sorted(
        [(row["ord"], row["id"], row["current_probability"]) for row in second]
    ) == [(1, 11, Decimal("0.062346")), (2, 12, Decimal("0.123457"))]
    assert all(row["quote_moved"] is True for row in second)
    landed = await _read(writer_db)

    assert await _prices(writer_db, reused, latest, force_ids=set()) == []
    assert await _read(writer_db) == landed
    forced = await _prices(writer_db, reused, latest, force_ids={11})
    assert [(row["id"], row["quote_moved"]) for row in forced] == [(11, False)]
    liveness = await _read(writer_db)
    assert liveness[11]["last_updated"] > landed[11]["last_updated"]
    assert liveness[11]["price_changed_at"] == landed[11]["price_changed_at"]
    assert liveness[12] == landed[12]

    default_forced = await _prices(writer_db, reused, {12: 0.1234567})
    assert [(row["id"], row["quote_moved"]) for row in default_forced] == [(12, False)]
    assert await _prices(writer_db, reused, {}, force_ids=set()) == []


@pytest.mark.parametrize("reused", [False, True], ids=["baseline", "reused"])
async def test_pg_nowait_refusal_rolls_back_both_binary_legs_then_accepts_fresh_pair(
    writer_db, reused
):
    await _seed(
        writer_db,
        [(1, 101, Decimal("0.450000"), 2), (2, 101, Decimal("0.550000"), 1)],
    )
    before = await _read(writer_db)
    async with AsyncSession(writer_db) as holder, holder.begin():
        await holder.execute(
            text("SELECT id FROM futures_outcomes WHERE id = 1 FOR UPDATE")
        )
        # The free leg is first: a partial write before the locked companion
        # would violate CERT-3868 even if the later refusal were reported.
        with pytest.raises(DBAPIError) as refused:
            await asyncio.wait_for(
                _prices(
                    writer_db, reused, {2: 0.25, 1: 0.75}, force_ids={1, 2}, nowait=True
                ),
                timeout=2,
            )
        assert getattr(refused.value.orig, "sqlstate", None) == "55P03"
        assert await _read(writer_db) == before

    landed = await _prices(
        writer_db,
        reused,
        {2: Decimal("0.125"), 1: Decimal("0.875")},
        force_ids={1, 2},
        nowait=True,
    )
    assert sorted((row["ord"], row["id"]) for row in landed) == [(1, 2), (2, 1)]
    state = await _read(writer_db)
    assert [state[oid]["current_probability"] for oid in (1, 2)] == [
        Decimal("0.875000"),
        Decimal("0.125000"),
    ]
    assert all(state[oid]["last_updated"] > BEFORE for oid in (1, 2))


@pytest.mark.parametrize("reused", [False, True], ids=["baseline", "reused"])
async def test_pg_rerank_expands_fresh_markets_and_preserves_ties_nulls_and_liveness(
    writer_db, reused
):
    await _seed(
        writer_db,
        [
            (1, 101, Decimal("0.3"), 7),
            (2, 101, Decimal("0.3"), 8),
            (3, 101, None, 9),
            (4, 202, Decimal("0.8"), 6),
            (5, 202, Decimal("0.4"), 7),
            (6, 202, None, 8),
            (7, 303, Decimal("0.9"), 3),
            (8, 303, Decimal("0.1"), 4),
            (9, 303, Decimal("0.1"), 7),
        ],
    )
    assert await _ranks(writer_db, reused, [101]) == 3
    state = await _read(writer_db)
    assert [state[oid]["rank"] for oid in range(1, 10)] == [1, 1, 3, 6, 7, 8, 3, 4, 7]

    assert await _ranks(writer_db, reused, [303, 202]) == 6
    state = await _read(writer_db)
    assert [state[oid]["rank"] for oid in range(1, 10)] == [1, 1, 3, 1, 2, 3, 1, 2, 2]
    assert all(row["last_updated"] == BEFORE for row in state.values())

    async with writer_db.begin() as connection:
        await connection.execute(
            text("UPDATE futures_outcomes SET current_probability = 0.2 WHERE id = 4")
        )
        await connection.execute(
            text("UPDATE futures_outcomes SET current_probability = 0.8 WHERE id = 5")
        )
    assert await _ranks(writer_db, reused, [202]) == 2
    changed = await _read(writer_db)
    assert [changed[oid]["rank"] for oid in range(1, 10)] == [1, 1, 3, 2, 1, 3, 1, 2, 2]
    assert await _ranks(writer_db, reused, []) == 0
    assert await _read(writer_db) == changed
    assert await _ranks(writer_db, reused, [101, 202, 303]) == 0
    assert all(row["last_updated"] == BEFORE for row in changed.values())
