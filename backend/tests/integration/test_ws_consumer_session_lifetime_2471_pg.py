"""#2471 on a real Postgres — the consumer's operations stop reconnecting.

The unit file (`tests/test_ws_consumer_session_lifetime_2471.py`) proves the
consumers lend one engine to every session. What only a running server can
show is the thing that costs time: whether a NEW connection (TCP, startup
packet, auth) is opened per operation. Counted here with the pool's own
``connect`` event, on both arms:

* CONTROL — the task factory as every consumer used it before #2471: one
  engine per ``get_task_session()``. N operations, N connects.
* TREATMENT — :class:`ConsumerSessions`: N operations, ONE connect, one backend
  pid, and still N separate transactions — each commit visible from an
  independent connection, a failed one rolled back and invisible, and the
  resting statement bound on the reused connection after every commit.
"""

from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import create_async_engine

import app.tasks.base as base_mod
from app.services.database import DB_STATEMENT_TIMEOUT_MS

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [pytest.mark.asyncio]

needs_postgres = pytest.mark.skipif(
    not DB_URL,
    reason=(
        "set SEARCH_TEST_DATABASE_URL to run the real-Postgres consumer-session "
        "contract (CI job `search-recall` provides one)"
    ),
)

OPERATIONS = 4


@needs_postgres
async def test_burst_reads_see_new_commits_without_another_checkout(
    counted, scratch_table,
):
    from sqlalchemy import column, select, table as sql_table
    from app.tasks.ws_consumer_sessions import ConsumerSessions

    name, admin = scratch_table
    rows = sql_table(name, column("op"))
    sessions = ConsumerSessions("burst-snapshot-test")
    engine = sessions._engine_here()
    checkouts, in_transactions = [], []

    @event.listens_for(engine.sync_engine, "checkout")
    def checkout(dbapi, record, proxy):
        checkouts.append(record)

    @event.listens_for(engine.sync_engine, "after_cursor_execute")
    def transaction_state(connection, *args):
        in_transactions.append(
            connection.connection.driver_connection.is_in_transaction()
        )

    try:
        async with sessions.observation_read() as reader:
            assert list((await reader.execute(select(rows.c.op))).scalars()) == []
        async with admin.begin() as writer:
            await writer.execute(text(f"INSERT INTO {name} VALUES (17)"))
        async with sessions.observation_read() as reader:
            assert list((await reader.execute(select(rows.c.op))).scalars()) == [17]
        assert len(checkouts) == 1
        assert in_transactions == [False, False]
        assert engine.pool.size() == 5
        assert engine.pool._max_overflow == 0
    finally:
        await sessions.aclose()
    assert engine.pool.checkedout() == 0


@needs_postgres
async def test_observation_read_has_no_commit_and_writer_pool_stays_transactional(
    counted, scratch_table, monkeypatch,
):
    import asyncpg.transaction
    from sqlalchemy import column, select, table as sql_table
    from app.tasks.ws_consumer_sessions import ConsumerSessions

    name, admin = scratch_table
    rows = sql_table(name, column("op"))
    sessions = ConsumerSessions("observation-test")
    commits = []
    original_commit = asyncpg.transaction.Transaction.commit

    async def counted_commit(transaction):
        commits.append(transaction)
        return await original_commit(transaction)

    states = []
    engine = sessions._engine_here()

    @event.listens_for(engine.sync_engine, "after_cursor_execute")
    def record_transaction(connection, cursor, statement, parameters, context, many):
        states.append(connection.connection.driver_connection.is_in_transaction())

    try:
        with monkeypatch.context() as patch:
            patch.setattr(asyncpg.transaction.Transaction, "commit", counted_commit)
            async with sessions.observation_read() as reader:
                assert list((await reader.execute(select(rows.c.op))).scalars()) == []
                with pytest.raises(ValueError, match="exactly one SELECT"):
                    await reader.execute(select(rows.c.op))
            assert states == [False]
            assert commits == []

        async with sessions.session() as writer:
            await writer.execute(text(f"INSERT INTO {name} VALUES (1)"))
        assert states[-1] is True
        assert await _committed_ops(admin, name) == [1]
        async with sessions.observation_read() as reader:
            assert list((await reader.execute(select(rows.c.op))).scalars()) == [1]
        assert states[-1] is False
        with pytest.raises(RuntimeError, match="rollback"):
            async with sessions.session() as writer:
                await writer.execute(text(f"INSERT INTO {name} VALUES (2)"))
                raise RuntimeError("rollback")
        assert await _committed_ops(admin, name) == [1]
        async with sessions.observation_read() as reader:
            with pytest.raises(ValueError, match="exactly one SELECT"):
                await reader.execute(rows.delete())
        assert sessions._open == 0
        assert counted["engines"] == 1
        assert counted["connects"] == 1
    finally:
        await sessions.aclose()


@needs_postgres
async def test_cancelled_observation_read_returns_capacity(counted):
    import asyncio
    from sqlalchemy import func, select
    from app.tasks.ws_consumer_sessions import ConsumerSessions

    sessions = ConsumerSessions("cancel-observation-test")
    try:
        with pytest.raises(TimeoutError):
            async with asyncio.timeout(.05), sessions.observation_read() as reader:
                await reader.execute(select(func.pg_sleep(1)))
        assert sessions._open == 0 and sessions._idle.is_set()
        async with sessions.observation_read() as reader:
            assert (await reader.execute(select(1))).scalar_one() == 1
        async with sessions.session() as writer:
            assert (await writer.execute(text("SELECT 2"))).scalar_one() == 2
    finally:
        await sessions.aclose()


@pytest.fixture
def counted(monkeypatch):
    """Point the task factory at the test server and count DBAPI connects."""
    monkeypatch.setattr(base_mod, "DATABASE_URL", DB_URL)
    real = base_mod._get_task_engine
    tally = {"engines": 0, "connects": 0}

    def _counting(**budget):
        engine = real(**budget)
        tally["engines"] += 1

        @event.listens_for(engine.sync_engine, "connect")
        def _on_connect(_dbapi, _record):
            tally["connects"] += 1

        return engine

    monkeypatch.setattr(base_mod, "_get_task_engine", _counting)
    return tally


@pytest.fixture
async def scratch_table():
    name = f"ws2471_{uuid.uuid4().hex[:10]}"
    admin = create_async_engine(DB_URL)
    async with admin.begin() as conn:
        await conn.execute(text(f"CREATE TABLE {name} (op int PRIMARY KEY)"))
    try:
        yield name, admin
    finally:
        async with admin.begin() as conn:
            await conn.execute(text(f"DROP TABLE IF EXISTS {name}"))
        await admin.dispose()


async def _committed_ops(admin, table) -> list[int]:
    async with admin.connect() as conn:
        rows = await conn.execute(text(f"SELECT op FROM {table} ORDER BY op"))
        return [r.op for r in rows]


@needs_postgres
async def test_control_the_task_factory_connects_per_operation(counted):
    for _ in range(OPERATIONS):
        async with base_mod.get_task_session() as session:
            await session.execute(text("SELECT 1"))
    assert counted["engines"] == OPERATIONS
    assert counted["connects"] == OPERATIONS, counted


@needs_postgres
async def test_treatment_one_connect_separate_committed_transactions(
    counted, scratch_table
):
    from app.tasks.ws_consumer_sessions import ConsumerSessions

    table, admin = scratch_table
    scope = ConsumerSessions("test")
    pids, stmts = set(), set()
    failed_op = 2
    for op in range(OPERATIONS):
        try:
            async with scope.session() as session:
                row = (
                    await session.execute(
                        text(
                            "SELECT pg_backend_pid() AS pid,"
                            " current_setting('statement_timeout') AS stmt"
                        )
                    )
                ).one()
                pids.add(int(row.pid))
                stmts.add(row.stmt)
                await session.execute(
                    text(f"INSERT INTO {table} (op) VALUES (:op)"), {"op": op}
                )
                if op == failed_op:
                    raise RuntimeError("simulated flush failure")
        except RuntimeError:
            assert op == failed_op
        # Each operation's own commit is visible to an independent connection
        # before the next operation starts — not one transaction at the end.
        expected = [o for o in range(op + 1) if o != failed_op]
        assert await _committed_ops(admin, table) == expected

    assert counted["engines"] == 1
    assert counted["connects"] == 1, (
        f"{counted['connects']} connects for {OPERATIONS} operations — the "
        "consumer is still paying connection setup per transaction"
    )
    assert len(pids) == 1, pids
    resting_s = DB_STATEMENT_TIMEOUT_MS // 1000
    assert stmts in ({f"{resting_s}s"}, {f"{resting_s // 60}min"}), stmts

    await scope.aclose()
    with pytest.raises(RuntimeError, match="closed"):
        async with scope.session():
            pass
    assert counted["connects"] == 1
