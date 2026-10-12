"""#10090: a `futures_outcomes` write never adds to, or merges, a GIN pending list.

THE SHIP. A changed live probability is not held behind a futures write that
stops for one to two seconds to empty a search index's backlog.

With the GIN default `fastupdate = on`, every new row version of
`futures_outcomes` is appended to `ix_futures_outcomes_name_trgm`'s pending
list. The writer whose append crosses `gin_pending_list_limit` merges the whole
list inside its own statement. On a synthetic local table that statement took
1.3 to 1.6 s (`alembic/versions/fo_trgm_fastupdate_off.py`). The production
minute line at 16:01:53Z on release 5671 recorded a 2.02 s rerank beside 0.02 s
of saves; that line is the symptom, not an exact attribution to the merge.

The stall is timing, so the gate does not time anything. It reads the
precondition straight from the server: `gin_clean_pending_list()` returns the
number of pending-list pages it emptied. If writers leave a pending list, some
writer will pay to merge it. If they leave nothing, no writer can.

Arms:
* parent: the index exactly as `add_futures_outcomes_search_index` creates it.
  Writes leave pages pending. This is the strawman; without it a zero below
  could mean the probe cannot see pages at all.
* ship: the migration's upgrade. The same writes leave zero pages pending, and
  the storage parameter reads `fastupdate=off`.
* undo: the migration's downgrade restores the parent behaviour (D51 undo line).

The table lives in its own schema with only the columns the writes touch. The
statements under test name the index unqualified, as production's do, and
`search_path` resolves them here.
"""

from __future__ import annotations

import importlib.util
import os
import pathlib

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL,
        reason=(
            "set SEARCH_TEST_DATABASE_URL to run the #10090 GIN pending-list gate "
            "(CI job `database-integration` provides one)"
        ),
    ),
]

VERSIONS = pathlib.Path(__file__).resolve().parents[2] / "alembic" / "versions"
SCHEMA = "t10090_gin_backlog"
INDEX = "ix_futures_outcomes_name_trgm"
ROWS = 400
WRITES = 200


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, VERSIONS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MIGRATION = _load("fo_trgm_fastupdate_off")


def _original_index_ddl() -> str:
    """The index DDL exactly as the migration that created it on production."""
    source = (VERSIONS / "add_futures_outcomes_search_index.py").read_text()
    start = source.index("CREATE INDEX IF NOT EXISTS ix_futures_outcomes_name_trgm")
    end = source.index(")", source.index("gin_trgm_ops", start)) + 1
    return " ".join(source[start:end].split())


@pytest.fixture
async def conn():
    engine = create_async_engine(DB_URL)
    async with engine.connect() as c:
        await c.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        await c.execute(text(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE"))
        await c.execute(text(f"CREATE SCHEMA {SCHEMA}"))
        await c.execute(text(f"SET search_path TO {SCHEMA}, public"))
        await c.execute(
            text(
                "CREATE TABLE futures_outcomes ("
                " id serial PRIMARY KEY,"
                " name varchar(300) NOT NULL,"
                " current_probability numeric(7, 6),"
                " last_updated timestamptz NOT NULL DEFAULT now())"
            )
        )
        await c.execute(text("CREATE INDEX ix_futures_outcomes_last_updated ON futures_outcomes (last_updated)"))
        await c.execute(
            text(
                "INSERT INTO futures_outcomes (name, current_probability) "
                "SELECT 'Leg ' || md5(g::text), 0.5 FROM generate_series(1, :n) g"
            ),
            {"n": ROWS},
        )
        await c.execute(text(_original_index_ddl()))
        await c.commit()
        try:
            yield c
        finally:
            await c.rollback()
            await c.execute(text(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE"))
            await c.commit()
    await engine.dispose()


async def _empty_backlog(c) -> int:
    pages = (
        await c.execute(text(f"SELECT gin_clean_pending_list('{INDEX}'::regclass)"))
    ).scalar_one()
    await c.commit()
    return pages


async def _price_writes(c) -> None:
    """The socket's write shape: a new price and a liveness stamp, row by row.

    `last_updated` is indexed, so none of these is a HOT update, the same as on
    production.
    """
    for i in range(1, WRITES + 1):
        await c.execute(
            text(
                "UPDATE futures_outcomes SET current_probability = :p, "
                "last_updated = now() WHERE id = :id"
            ),
            {"p": (i % 97) / 100, "id": i},
        )
        await c.commit()


async def _reloptions(c):
    return (
        await c.execute(
            text("SELECT reloptions FROM pg_class WHERE oid = CAST(:i AS regclass)"),
            {"i": f"{SCHEMA}.{INDEX}"},
        )
    ).scalar_one()


async def test_the_parent_index_leaves_writers_a_backlog_to_merge(conn):
    assert _original_index_ddl().endswith("USING gin (name gin_trgm_ops)")
    assert await _empty_backlog(conn) == 0
    await _price_writes(conn)
    assert await _empty_backlog(conn) > 0, (
        "the parent index left no pending pages, so the zero in the ship arm "
        "would prove nothing"
    )


async def test_after_the_migration_writes_leave_nothing_pending(conn):
    await conn.execute(text(MIGRATION.UPGRADE_SQL))
    await conn.commit()
    assert await _reloptions(conn) == ["fastupdate=off"]
    assert await _empty_backlog(conn) == 0
    await _price_writes(conn)
    assert await _empty_backlog(conn) == 0, (
        "a futures_outcomes write still appended to the GIN pending list, so "
        "some later write will pay to merge it"
    )
    hits = (
        await conn.execute(
            text("SELECT count(*) FROM futures_outcomes WHERE name ILIKE :q"),
            {"q": "%" + "Leg " + "c4ca4238"[:6] + "%"},
        )
    ).scalar_one()
    assert hits == 1, "the trigram index must still answer a search"


async def test_the_downgrade_restores_the_parent(conn):
    await conn.execute(text(MIGRATION.UPGRADE_SQL))
    await conn.execute(text(MIGRATION.DOWNGRADE_SQL))
    await conn.commit()
    assert await _reloptions(conn) is None
    await _price_writes(conn)
    assert await _empty_backlog(conn) > 0
