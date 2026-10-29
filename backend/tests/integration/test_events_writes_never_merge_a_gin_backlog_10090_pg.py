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
* no deadlock (lane1b's review of 965ff55c): the indexes are recreated in
  production's creation order, so their OIDs ascend as production's very likely
  do (duplicates < event_tags < `_trgm` pair). A query locks a table's indexes
  in OID order, so a reader arriving after statement 0 must be queued and then
  answered. Without the table lock first, it held the duplicates while waiting
  on `event_tags` and was killed by the deadlock detector.

The follow-up, `events_fts_gin_fastupdate_off`, covers the two full-text GIN
indexes production built outside any migration (`ix_events_fts_{home,away}`,
read 2026-10-29 19:45Z). The parent's census came from the migrations, so it
could not see them. These arms read the census from `pg_index` instead:
* parent only (production at v5955): the census finds exactly the two
  full-text indexes without `fastupdate=off`, and writes leave pages on them.
* both revisions: every GIN on `events` in `pg_index` has `fastupdate=off`,
  writes leave zero pages on every one, and full-text search still answers
  through its index.
* undo: the follow-up's downgrade restores the two and leaves the parent's.
* no deadlock: the full-text pair is created away-first, as a REINDEX of the
  home index would leave it, so a query locks them against the batch's order.

The table lives in its own schema with only the columns the writes touch. The
statements under test name the indexes unqualified, as production's do, and
`search_path` resolves them here.
"""

from __future__ import annotations

import asyncio
import importlib.util
import os
import pathlib
import re
import time

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
FTS_MIGRATION = _load("events_fts_gin_fastupdate_off")
#: Production's full-text GIN indexes, which no migration creates: the DDL
#: `pg_get_indexdef` printed on 2026-10-29 19:45Z, schema dropped.
FTS_DDL = {
    side: (
        f"CREATE INDEX ix_events_fts_{side} ON events USING gin "
        f"(to_tsvector('english'::regconfig, "
        f"(COALESCE({side}_team_name, ''::character varying))::text))"
    )
    for side in ("home", "away")
}
FTS_INDEXES = tuple(f"ix_events_fts_{side}" for side in FTS_DDL)
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
#: The order production's migrations created them: add_search_indexes
#: (2026-02-02), add_event_tags (2026-03-01), add_pg_trgm (2026-05-02).
PRODUCTION_CREATION_ORDER = (
    "ix_events_home_team_name_trgm",
    "ix_events_away_team_name_trgm",
    "ix_events_event_tags",
    "ix_events_home_trgm",
    "ix_events_away_trgm",
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


async def _oid_order(c, names) -> list[str]:
    oids = dict(
        (
            await c.execute(
                text(
                    "SELECT c.relname, c.oid::bigint FROM pg_class c "
                    "JOIN pg_namespace n ON n.oid = c.relnamespace "
                    "WHERE n.nspname = :s AND c.relname = ANY(:names)"
                ),
                {"s": SCHEMA, "names": list(names)},
            )
        ).all()
    )
    await c.commit()
    return sorted(oids, key=oids.get)


async def _assert_a_reader_mid_batch_is_queued_then_answered(conn, statements) -> None:
    """Run statement 0, start a reader, wait until it queues, run the rest."""
    engine = create_async_engine(DB_URL)
    try:
        async with engine.connect() as migration, engine.connect() as reader:
            for c in (migration, reader):
                await c.execute(text(f"SET search_path TO {SCHEMA}, public"))
                await c.execute(text("SET lock_timeout = '10s'"))
                await c.commit()
            reader_pid = (await reader.execute(text("SELECT pg_backend_pid()"))).scalar_one()
            await reader.commit()

            await migration.execute(text(statements[0]))
            read = asyncio.create_task(
                reader.execute(text("SELECT count(*) FROM events WHERE id = 1"))
            )
            for _ in range(500):
                queued = (
                    await conn.execute(
                        text("SELECT count(*) FROM pg_locks WHERE pid = :p AND NOT granted"),
                        {"p": reader_pid},
                    )
                ).scalar_one()
                await conn.commit()
                if queued:
                    break
                await asyncio.sleep(0.01)
            else:
                read.cancel()
                pytest.fail("the reader never queued, so the gate cannot see the window")
            for statement in statements[1:]:
                await migration.execute(text(statement))
            await migration.commit()
            assert (await read).scalar_one() == 1, (
                "a live events query arriving mid-batch must be delayed, never killed"
            )
            await reader.rollback()
    finally:
        await engine.dispose()


async def test_a_query_arriving_mid_batch_is_queued_never_deadlocked(conn):
    for name in INDEXES:
        await conn.execute(text(f"DROP INDEX {name}"))
    for name in PRODUCTION_CREATION_ORDER:
        await conn.execute(text(_original_index_ddl(name)))
    await conn.commit()
    order = await _oid_order(conn, INDEXES)
    assert order == list(PRODUCTION_CREATION_ORDER), (
        f"the fixture is not in production's OID order, so it cannot see the "
        f"deadlock: {order}"
    )
    await _assert_a_reader_mid_batch_is_queued_then_answered(conn, MIGRATION.UPGRADE_SQL)


async def _add_full_text_indexes(c, sides=("home", "away")) -> None:
    for side in sides:
        await c.execute(text(FTS_DDL[side]))
    await c.commit()


async def _gin_census(c) -> dict[str, list[str] | None]:
    """Every GIN index on the `events` under test, read from `pg_index`."""
    rows = await c.execute(
        text(
            "SELECT c.relname, c.reloptions FROM pg_index i "
            "JOIN pg_class c ON c.oid = i.indexrelid "
            "JOIN pg_am a ON a.oid = c.relam "
            "WHERE i.indrelid = 'events'::regclass AND a.amname = 'gin'"
        )
    )
    census = {r[0]: r[1] for r in rows}
    await c.commit()
    return census


async def _drain(c, names) -> dict[str, int]:
    pages = {}
    for name in names:
        pages[name] = (
            await c.execute(text(f"SELECT gin_clean_pending_list('{name}'::regclass)"))
        ).scalar_one()
    await c.commit()
    return pages


async def _fts_upgrade(c) -> None:
    for statement in FTS_MIGRATION.UPGRADE_SQL:
        await c.execute(text(statement))
    await c.commit()


def _fastupdate_on(census) -> set[str]:
    return {name for name, opts in census.items() if "fastupdate=off" not in (opts or [])}


async def test_after_the_parent_only_the_full_text_pair_keeps_a_backlog(conn):
    await _add_full_text_indexes(conn)
    await _upgrade(conn)
    census = await _gin_census(conn)
    assert set(census) == set(INDEXES) | set(FTS_INDEXES)
    assert _fastupdate_on(census) == set(FTS_INDEXES)
    assert set((await _drain(conn, census)).values()) == {0}
    await _live_writes(conn)
    pending = await _drain(conn, census)
    assert all(pending[name] > 0 for name in FTS_INDEXES), (
        f"a full-text index left no pending pages, so the zero after the "
        f"follow-up would prove nothing: {pending}"
    )
    assert {name: pending[name] for name in INDEXES} == {name: 0 for name in INDEXES}


async def test_after_both_revisions_no_events_gin_keeps_a_backlog(conn):
    await _add_full_text_indexes(conn)
    await _upgrade(conn)
    await _fts_upgrade(conn)
    census = await _gin_census(conn)
    assert set(census) >= set(FTS_INDEXES), f"the census cannot see the full-text pair: {census}"
    assert _fastupdate_on(census) == set(), (
        f"a GIN index on events still takes a pending list: {census}"
    )
    assert set((await _drain(conn, census)).values()) == {0}
    await _live_writes(conn)
    pending = await _drain(conn, census)
    assert pending == {name: 0 for name in census}, (
        f"an events write still appended to a GIN pending list, so some later "
        f"write will pay to merge it: {pending}"
    )
    await conn.execute(text("SET enable_seqscan = off"))
    search = (
        "SELECT count(*) FROM events WHERE to_tsvector('english', "
        "coalesce(home_team_name, '')) @@ websearch_to_tsquery('english', :q)"
    )
    plan = "\n".join(
        r[0]
        for r in await conn.execute(text("EXPLAIN " + search), {"q": "c4ca4238a0b923820dcc509a6f75849b"})
    )
    found = (
        await conn.execute(text(search), {"q": "c4ca4238a0b923820dcc509a6f75849b"})
    ).scalar_one()
    await conn.rollback()
    assert "ix_events_fts_home" in plan, plan
    assert found == 1, "the full-text index must still answer a search"


async def test_the_full_text_downgrade_restores_the_two_and_keeps_the_parent(conn):
    await _add_full_text_indexes(conn)
    await _upgrade(conn)
    await _fts_upgrade(conn)
    for statement in FTS_MIGRATION.DOWNGRADE_SQL:
        await conn.execute(text(statement))
    await conn.commit()
    census = await _gin_census(conn)
    assert {name: census[name] for name in FTS_INDEXES} == {name: None for name in FTS_INDEXES}
    assert _fastupdate_on(census) == set(FTS_INDEXES)
    await _drain(conn, census)
    await _live_writes(conn)
    pending = await _drain(conn, census)
    assert all(pending[name] > 0 for name in FTS_INDEXES), pending
    assert all(pending[name] == 0 for name in INDEXES), pending


async def test_a_query_arriving_mid_full_text_batch_is_queued_never_deadlocked(conn):
    await _add_full_text_indexes(conn, sides=("away", "home"))
    order = await _oid_order(conn, FTS_INDEXES)
    assert order == ["ix_events_fts_away", "ix_events_fts_home"], (
        f"the pair must be in the order opposite the batch's, or the gate "
        f"cannot see the deadlock: {order}"
    )
    await _assert_a_reader_mid_batch_is_queued_then_answered(conn, FTS_MIGRATION.UPGRADE_SQL)


def _migrate_on_a_sync_connection(direction: str, monkeypatch) -> dict:
    """Run the full-text revision's own `upgrade()`/`downgrade()` as env.py does.

    A psycopg2 connection in its own thread, so the test can hold and release
    `events` from asyncio while the migration polls.
    """
    from types import SimpleNamespace

    from sqlalchemy import create_engine

    from app.utils.migration_lock_budget import psycopg2_url

    out: dict = {}
    engine = create_engine(psycopg2_url(DB_URL))
    try:
        with engine.connect() as sync:
            sync.execute(text(f"SET search_path TO {SCHEMA}, public"))
            sync.execute(text("SET lock_timeout = '12s'"))
            out["pid"] = sync.execute(text("SELECT pg_backend_pid()")).scalar_one()
            monkeypatch.setattr(
                FTS_MIGRATION,
                "op",
                SimpleNamespace(get_bind=lambda: sync, execute=lambda s: sync.execute(text(s))),
            )
            started = time.monotonic()
            getattr(FTS_MIGRATION, direction)()
            sync.commit()
            out["took_s"] = time.monotonic() - started
    finally:
        engine.dispose()
    return out


async def _hold_events(engine):
    """An `events` reader whose transaction stays open: the v5958 holder class."""
    holder = await engine.connect()
    await holder.execute(text(f"SET search_path TO {SCHEMA}, public"))
    await holder.execute(text("SELECT count(*) FROM events"))
    return holder


async def _access_exclusive_requests(c) -> int:
    n = (
        await c.execute(
            text(
                "SELECT count(*) FROM pg_locks WHERE locktype = 'relation' "
                "AND relation = 'events'::regclass AND mode = 'AccessExclusiveLock'"
            )
        )
    ).scalar_one()
    await c.commit()
    return n


async def test_a_long_events_holder_gets_no_lock_request_queued_behind_it(conn, monkeypatch):
    """v5958: a lock request waiting on a long reader queues every writer behind it.

    The revision must not request the lock while a transaction older than the
    gate holds `events`; a writer arriving meanwhile must not wait; once the
    holder ends, the revision takes the lock and applies.
    """
    await _add_full_text_indexes(conn)
    await _upgrade(conn)
    monkeypatch.setattr(FTS_MIGRATION, "GATE_HOLDER_AGE_S", 0.2, raising=False)
    engine = create_async_engine(DB_URL)
    holder = await _hold_events(engine)
    migration = None
    try:
        await asyncio.sleep(0.5)
        migration = asyncio.create_task(
            asyncio.to_thread(_migrate_on_a_sync_connection, "upgrade", monkeypatch)
        )
        writer_waits = []
        for i in range(8):
            await asyncio.sleep(0.25)
            assert await _access_exclusive_requests(conn) == 0, (
                "the revision requested the events lock behind a live holder, so "
                "every writer now queues behind the request"
            )
            started = time.monotonic()
            await conn.execute(
                text("UPDATE events SET last_updated = now() WHERE id = :id"), {"id": i + 1}
            )
            await conn.commit()
            writer_waits.append(time.monotonic() - started)
        assert not migration.done(), "the revision did not wait for the holder"
        await holder.commit()
        result = await asyncio.wait_for(migration, timeout=30)
    finally:
        await holder.rollback()
        await holder.close()
        if migration is not None and not migration.done():
            await asyncio.wait([migration], timeout=30)
        await conn.rollback()
        await engine.dispose()
    assert max(writer_waits) < 0.5, f"a writer queued while the holder lived: {writer_waits}"
    census = await _gin_census(conn)
    assert _fastupdate_on(census) == set(), census
    assert result["took_s"] < FTS_MIGRATION.GATE_BUDGET_S


async def test_an_already_applied_revision_takes_no_lock_even_beside_a_holder(conn, monkeypatch):
    """The attended-apply path: nothing to change means the release takes no lock."""
    await _add_full_text_indexes(conn)
    await _upgrade(conn)
    await _fts_upgrade(conn)
    engine = create_async_engine(DB_URL)
    holder = await _hold_events(engine)
    try:
        await asyncio.sleep(1.2)
        result = await asyncio.wait_for(
            asyncio.to_thread(_migrate_on_a_sync_connection, "upgrade", monkeypatch), timeout=20
        )
    finally:
        await holder.rollback()
        await holder.close()
        await engine.dispose()
    assert result["took_s"] < 0.5, (
        f"an already-applied revision waited {result['took_s']:.2f} s beside a holder"
    )
