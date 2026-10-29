"""#10090: an `events` write never adds to, or merges, a GIN pending list.

THE SHIP. A live score or price write on `events` never stops for seconds to
merge a search index's backlog inside its own statement.

With the GIN default `fastupdate = on`, every new row version of `events` is
appended to each GIN index's pending list, and the writer whose append crosses
`gin_pending_list_limit` merges the whole list inside its own statement. On
production 2026-10-29 04:39Z a single-row `UPDATE events` sat active >= 9.9 s
in that shape (`alembic/versions/events_gin_fastupdate_off.py`).

The stall is timing, so the gate does not time anything. It reads the
precondition from the server, as `fo_trgm_fastupdate_off`'s gate does:
`gin_clean_pending_list()` returns the pending-list pages it emptied. If writers
leave a pending list, some writer will pay to merge it. If they leave nothing,
no writer can.

Arms:
* parent: the five indexes exactly as their migrations create them, with the
  `gin_pending_list_limit=256` production carries on three of them (step 0,
  2026-10-29 15:47Z). Writes leave pages pending on all five. This is the
  strawman; without it a zero below could mean the probe cannot see pages.
* ship: the upgrade. The same writes leave zero pages pending, `fastupdate=off`
  is set, the 256 kB limits are kept, and search still answers.
* duplicates dropped first: the attended psql drop of the
  `_team_name_trgm` pair runs before the release. The upgrade still applies.
* undo: the downgrade restores the parent's reloptions and behaviour (D51).

The table lives in its own schema with only the columns the writes touch. The
statements under test name the indexes unqualified, as production's do, and
`search_path` resolves them here.
"""

from __future__ import annotations

import importlib.util
import os
import pathlib
import re

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL,
        reason=(
            "set SEARCH_TEST_DATABASE_URL to run the #10090 events GIN gate "
            "(CI job `database-integration` provides one)"
        ),
    ),
]

VERSIONS = pathlib.Path(__file__).resolve().parents[2] / "alembic" / "versions"
SCHEMA = "t10090_events_gin"
ROWS = 400
WRITES = 200
DUPLICATES = ("ix_events_home_team_name_trgm", "ix_events_away_team_name_trgm")
#: Production's reloptions before this migration (step 0 receipt).
PRODUCTION_LIMIT_256 = (
    "ix_events_home_trgm",
    "ix_events_away_trgm",
    "ix_events_away_team_name_trgm",
)


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, VERSIONS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MIGRATION = _load("events_gin_fastupdate_off")
#: The five GIN indexes production's `events` carries (step 0 receipt). Fixed
#: here, not read from the migration, so a migration that skips one fails the
#: ship arm instead of shrinking the table under test.
INDEXES = (
    "ix_events_event_tags",
    "ix_events_home_trgm",
    "ix_events_away_trgm",
    "ix_events_home_team_name_trgm",
    "ix_events_away_team_name_trgm",
)


def _original_index_ddl(index_name: str) -> str:
    """The index DDL exactly as the migration that created it on production.

    `CONCURRENTLY` is dropped: it cannot run in the test's transaction, and it
    changes how the index is built, not what it stores.
    """
    pattern = re.compile(
        r"CREATE INDEX\s+(?:CONCURRENTLY\s+)?IF NOT EXISTS\s+"
        + index_name
        + r"\s+ON\s+events\s+USING\s+gin\s*\([^)]*\)"
    )
    for path in sorted(VERSIONS.glob("*.py")):
        source = " ".join(path.read_text(encoding="utf-8").replace('"', " ").split())
        match = pattern.search(source)
        if match:
            return match.group(0).replace("CONCURRENTLY ", "")
    raise AssertionError(f"no migration creates {index_name}")


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
                "CREATE TABLE events ("
                " id serial PRIMARY KEY,"
                " home_team_name varchar(200) NOT NULL,"
                " away_team_name varchar(200) NOT NULL,"
                " event_tags jsonb DEFAULT '[]',"
                " last_updated timestamptz NOT NULL DEFAULT now())"
            )
        )
        await c.execute(text("CREATE INDEX ix_events_last_updated ON events (last_updated)"))
        await c.execute(
            text(
                "INSERT INTO events (home_team_name, away_team_name, event_tags) "
                "SELECT 'Home ' || md5(g::text), 'Away ' || md5((g + 7)::text), "
                "jsonb_build_array('nfl', 'team-' || g) "
                "FROM generate_series(1, :n) g"
            ),
            {"n": ROWS},
        )
        for name in INDEXES:
            await c.execute(text(_original_index_ddl(name)))
        for name in PRODUCTION_LIMIT_256:
            await c.execute(text(f"ALTER INDEX {name} SET (gin_pending_list_limit = 256)"))
        await c.commit()
        try:
            yield c
        finally:
            await c.rollback()
            await c.execute(text(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE"))
            await c.commit()
    await engine.dispose()


async def _existing(c) -> list[str]:
    rows = await c.execute(
        text(
            "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = :s AND c.relname = ANY(:names)"
        ),
        {"s": SCHEMA, "names": list(INDEXES)},
    )
    present = {r[0] for r in rows}
    return [name for name in INDEXES if name in present]


async def _empty_backlogs(c) -> dict[str, int]:
    pages = {}
    for name in await _existing(c):
        pages[name] = (
            await c.execute(text(f"SELECT gin_clean_pending_list('{name}'::regclass)"))
        ).scalar_one()
    await c.commit()
    return pages


async def _live_writes(c) -> None:
    """The live writer's shape: a liveness stamp and fresh tags, row by row.

    `last_updated` is indexed, so none of these is a HOT update, and every
    write inserts into all five GIN indexes.
    """
    for i in range(1, WRITES + 1):
        await c.execute(
            text(
                "UPDATE events SET last_updated = now(), "
                "event_tags = jsonb_build_array('nfl', 'live-' || :i) WHERE id = :id"
            ),
            {"i": str(i), "id": i},
        )
        await c.commit()


async def _reloptions(c) -> dict[str, list[str] | None]:
    rows = await c.execute(
        text(
            "SELECT c.relname, c.reloptions FROM pg_class c "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = :s AND c.relname = ANY(:names)"
        ),
        {"s": SCHEMA, "names": list(INDEXES)},
    )
    return {r[0]: r[1] for r in rows}


async def _upgrade(c) -> None:
    for statement in MIGRATION.UPGRADE_SQL:
        await c.execute(text(statement))
    await c.commit()


async def _downgrade(c) -> None:
    for statement in MIGRATION.DOWNGRADE_SQL:
        await c.execute(text(statement))
    await c.commit()


def _parent_reloptions() -> dict[str, list[str] | None]:
    return {
        name: (["gin_pending_list_limit=256"] if name in PRODUCTION_LIMIT_256 else None)
        for name in INDEXES
    }


async def test_the_parent_indexes_leave_writers_a_backlog_to_merge(conn):
    assert await _reloptions(conn) == _parent_reloptions()
    assert set((await _empty_backlogs(conn)).values()) == {0}
    await _live_writes(conn)
    pending = await _empty_backlogs(conn)
    assert set(pending) == set(INDEXES)
    assert all(pages > 0 for pages in pending.values()), (
        f"a parent index left no pending pages, so the zero in the ship arm "
        f"would prove nothing: {pending}"
    )


async def test_after_the_migration_writes_leave_nothing_pending(conn):
    await _upgrade(conn)
    expected = {
        name: (opts or []) + ["fastupdate=off"]
        for name, opts in _parent_reloptions().items()
    }
    assert await _reloptions(conn) == expected
    assert set((await _empty_backlogs(conn)).values()) == {0}
    await _live_writes(conn)
    pending = await _empty_backlogs(conn)
    assert pending == {name: 0 for name in INDEXES}, (
        f"an events write still appended to a GIN pending list, so some later "
        f"write will pay to merge it: {pending}"
    )
    await conn.execute(text("SET enable_seqscan = off"))
    home = (
        await conn.execute(
            text("SELECT count(*) FROM events WHERE home_team_name ILIKE :q"),
            {"q": "%" + "Home " + "c4ca42" + "%"},
        )
    ).scalar_one()
    tagged = (
        await conn.execute(
            text("SELECT count(*) FROM events WHERE event_tags @> CAST(:t AS jsonb)"),
            {"t": '["live-7"]'},
        )
    ).scalar_one()
    await conn.rollback()
    assert home == 1, "the trigram index must still answer a search"
    assert tagged == 1, "the tags index must still answer a containment query"


async def test_the_upgrade_applies_after_the_duplicates_are_dropped(conn):
    for name in DUPLICATES:
        await conn.execute(text(f"DROP INDEX {name}"))
    await conn.commit()
    await _upgrade(conn)
    kept = [name for name in INDEXES if name not in DUPLICATES]
    assert await _existing(conn) == kept
    await _live_writes(conn)
    assert await _empty_backlogs(conn) == {name: 0 for name in kept}


async def test_the_downgrade_restores_the_parent(conn):
    await _upgrade(conn)
    await _downgrade(conn)
    assert await _reloptions(conn) == _parent_reloptions()
    await _live_writes(conn)
    pending = await _empty_backlogs(conn)
    assert all(pages > 0 for pages in pending.values()), pending
