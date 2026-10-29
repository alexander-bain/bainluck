"""#10090: while the enrichment counts what is left, another writer can still
UPDATE a row it just enriched — against a REAL Postgres server.

WHY A REAL SERVER. The claim is about row locks, and a session double never
takes one. On master the "count remaining" query autoflushed the 50 ORM
assignments (taking their row locks) and then scanned the whole table inside
the same transaction, so a live price stamp on one of those games waited out
the scan (45 s measured 10/28). The unit guard next door
(``tests/test_enrich_events_metadata_row_locks_10090.py``) pins the statement
order; this control shows the order is what frees the rows.

At the moment the count statement reaches the server, a second connection runs
the production-shaped ``UPDATE events SET opening_home_probability = …`` on an
enriched row under the venue stamps' own 500 ms ``lock_timeout``. Red on master
(``LockNotAvailable``), green on the fix.

Opt-in on ``SEARCH_TEST_DATABASE_URL``, following the other real-Postgres
contracts; hosted CI runs it in the shared-tail #10090 return-to-stored step.
"""

import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import event as sa_event
from sqlalchemy import text

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.skipif(
        not DB_URL,
        reason="set SEARCH_TEST_DATABASE_URL to run the real-Postgres row-lock control",
    ),
    pytest.mark.asyncio,
]

T0 = datetime(2026, 10, 28, 23, 0, tzinfo=timezone.utc)


def _sync_dsn(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


async def _drop_tables_the_models_do_not_declare(conn):
    """`bl_searchtest` is shared by every step of the CI postgres job, and an
    earlier step can leave a table our metadata does not declare — #4586's
    restore leaves `bak_4586_futures_markets`, whose `id` DEFAULT depends on
    `futures_markets_id_seq`, so `drop_all` fails on `futures_markets`
    (hosted CI 40794170287). Same helper as the #1927 PG files.
    """
    import app.models.models  # noqa: F401 — registers every table on Base
    from app.services.database import Base

    known = set(Base.metadata.tables)
    rows = await conn.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'"))
    for (name,) in rows.fetchall():
        if name not in known:
            await conn.execute(text(f'DROP TABLE IF EXISTS "{name}" CASCADE'))


@pytest.fixture
async def engine():
    from sqlalchemy.ext.asyncio import create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    from app.services.database import Base

    eng = create_async_engine(DB_URL)
    async with eng.begin() as conn:
        await _drop_tables_the_models_do_not_declare(conn)
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(
            text("INSERT INTO sports (id, key, name, active) VALUES (1, 'americanfootball_nfl', 'NFL', true)")
        )
        for i in range(1, 6):
            await conn.execute(
                text(
                    "INSERT INTO events (id, sport_id, home_team_name, away_team_name, commence_time, status) "
                    "VALUES (:id, 1, :h, :a, :t, 'upcoming')"
                ),
                {"id": i, "h": f"Home {i}", "a": f"Away {i}", "t": T0 - timedelta(hours=i)},
            )
    yield eng
    await eng.dispose()


async def test_an_enriched_row_is_writable_while_the_count_runs(engine, monkeypatch):
    import psycopg2
    from psycopg2 import errors as pg_errors
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.services import llm
    from app.tasks import espn_sync

    maker = async_sessionmaker(engine, expire_on_commit=False)

    @asynccontextmanager
    async def _task_session(*args, **kwargs):
        # The real helper's shape: yield, then commit on a clean exit.
        async with maker() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    monkeypatch.setattr(espn_sync, "get_task_session", _task_session)
    monkeypatch.setattr(llm, "is_available", lambda: False)
    monkeypatch.setattr(llm, "classify_gender_cached", lambda t, s: "men")
    monkeypatch.setattr(llm, "classify_level_cached", lambda t, s: "professional")
    monkeypatch.setattr(llm, "classify_league_cached", lambda t, s: "NFL")
    monkeypatch.setattr(llm, "classify_importance_cached", lambda t, s: "regular_season")

    seen = []

    def _probe(conn, cursor, statement, parameters, context, executemany):
        sql = statement.lower()
        is_remaining_scan = (
            "from events" in sql
            and "llm_gender is null" in sql
            and "limit" not in sql
        )
        if not is_remaining_scan:
            return
        other = psycopg2.connect(_sync_dsn(DB_URL))
        try:
            with other.cursor() as cur:
                cur.execute("SET lock_timeout = '500ms'")
                try:
                    # Event 1 is the newest, so the task enriched it.
                    cur.execute(
                        "UPDATE events SET opening_home_probability = 0.61 WHERE id = 1"
                    )
                    seen.append(("updated", cur.rowcount))
                except pg_errors.LockNotAvailable:
                    seen.append(("locked", 0))
            other.rollback()
        finally:
            other.close()

    sa_event.listen(engine.sync_engine, "before_cursor_execute", _probe)
    try:
        stats = await espn_sync._enrich_events_metadata(limit=3)
    finally:
        sa_event.remove(engine.sync_engine, "before_cursor_execute", _probe)

    assert seen == [("updated", 1)], seen
    assert stats["enriched"] == 3 and stats["errors"] == 0
    assert stats["remaining"] == 2

    async with engine.connect() as conn:
        enriched = (
            await conn.execute(text("SELECT id FROM events WHERE llm_gender = 'men' ORDER BY id"))
        ).scalars().all()
    assert enriched == [1, 2, 3]
