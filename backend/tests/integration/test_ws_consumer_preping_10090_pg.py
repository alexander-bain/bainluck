"""#10090 on a real Postgres — the consumer engine's pre-ping switch and the set_lock split.

The unit file (`tests/test_ws_consumer_preping_switch_10090.py`) proves the
setting, the factory call and the flush's retention. What only a running server
can show:

* STATEMENT ORDER. On a pooled connection, a price phase's statements as the
  driver sent them. On: BEGIN, ``;``, ROLLBACK (the ping), then the phase's own.
  Off: the phase's own, identical, and nothing else.
* A SERVER-CLOSED CONNECTION. Off, the backend is terminated between two
  phases: the next phase's first statement raises with the connection
  invalidated, nothing commits, and the phase after it connects afresh. On (the
  control), the ping finds it and the phase succeeds.
* THE LOG FIELDS on the engine's own pool events: a first phase connects inside
  its span, a pooled one does not, and a span that begins with all five slots
  out says so and books its wait in `checkout`.
"""

from __future__ import annotations

import asyncio
import os
import uuid

import pytest
from sqlalchemy import event, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine

import app.tasks.base as base_mod
import app.tasks.ws_consumer_sessions as wcs
from app.tasks.kalshi_ws import PRICE_PHASE_LOCK_TIMEOUT_MS, _FlushTimings
from app.utils.repair_lock_budget import SET_LOCK_TIMEOUT_SQL, lock_timeout_value

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [pytest.mark.asyncio]

needs_postgres = pytest.mark.skipif(
    not DB_URL,
    reason=(
        "set SEARCH_TEST_DATABASE_URL to run the real-Postgres consumer pre-ping "
        "contract (CI job `search-recall` provides one)"
    ),
)


@pytest.fixture
def driver_log(monkeypatch):
    """Point the factory at the test server; per connection, record what it
    sent. ``simple``: the driver's own query logger, which sees the
    simple-protocol round trips (the ping, BEGIN, COMMIT) and reports them
    later on the loop, in order among themselves. ``statements``: the phase's
    own statements, which go as prepared statements the driver does not log,
    from SQLAlchemy's ``before_cursor_execute``."""
    monkeypatch.setattr(base_mod, "DATABASE_URL", DB_URL)
    real = base_mod._get_task_engine
    logs: list[dict[str, list[str]]] = []
    by_driver: dict[int, dict[str, list[str]]] = {}

    def logging_engine(**kwargs):
        engine = real(**kwargs)

        @event.listens_for(engine.sync_engine, "connect")
        def _log(dbapi_connection, _record):
            sent = {"simple": [], "statements": []}
            logs.append(sent)
            driver = dbapi_connection.driver_connection
            by_driver[id(driver)] = sent
            driver.add_query_logger(
                lambda record: sent["simple"].append(record.query.strip())
            )

        @event.listens_for(engine.sync_engine, "before_cursor_execute")
        def _statement(conn, _cursor, statement, *_rest):
            driver = conn.connection.dbapi_connection.driver_connection
            by_driver[id(driver)]["statements"].append(" ".join(statement.split()))

        return engine

    monkeypatch.setattr(base_mod, "_get_task_engine", logging_engine)
    return logs


@pytest.fixture
def pre_ping(monkeypatch):
    def set_to(value: bool):
        monkeypatch.setattr(wcs, "CONSUMER_POOL_PRE_PING", value)

    return set_to


async def _phase(sessions, timings=None, *, insert=None):
    """A price phase's opening: its lock budget first, as the flush runs it."""
    async with sessions.session() as session:
        if timings is None:
            await session.execute(
                SET_LOCK_TIMEOUT_SQL,
                {"ms": lock_timeout_value(PRICE_PHASE_LOCK_TIMEOUT_MS)},
            )
        else:
            async with timings.waited("db"):
                async with timings.waited("set_lock"):
                    await session.execute(
                        SET_LOCK_TIMEOUT_SQL,
                        {"ms": lock_timeout_value(PRICE_PHASE_LOCK_TIMEOUT_MS)},
                    )
        if insert is not None:
            table, op = insert
            await session.execute(
                text(f"INSERT INTO {table} (op) VALUES (:op)"), {"op": op}
            )
        return (await session.execute(text("SELECT pg_backend_pid()"))).scalar_one()


async def _pooled_phase_statements(driver_log, value):
    sessions = wcs.ConsumerSessions(f"preping-{value}")
    try:
        await _phase(sessions)  # the connection's first checkout never pings
        await asyncio.sleep(0)  # the driver reports on the loop
        (sent,) = driver_log
        before = {kind: len(sent[kind]) for kind in sent}
        await _phase(sessions)
        await asyncio.sleep(0)
        return {kind: sent[kind][before[kind]:] for kind in sent}
    finally:
        await sessions.aclose()
        driver_log.clear()


@needs_postgres
async def test_off_removes_exactly_the_three_ping_round_trips(driver_log, pre_ping):
    pre_ping(True)
    on = await _pooled_phase_statements(driver_log, True)
    pre_ping(False)
    off = await _pooled_phase_statements(driver_log, False)
    # The ping: BEGIN, `;`, ROLLBACK before the phase's own BEGIN ... COMMIT.
    assert on["simple"] == ["BEGIN;", ";", "ROLLBACK;", "BEGIN;", "COMMIT;"], on
    assert off["simple"] == ["BEGIN;", "COMMIT;"], off
    # The phase's own statements are the same, the lock budget first.
    assert off["statements"] == on["statements"], (on, off)
    assert off["statements"][0].startswith("SELECT set_config('lock_timeout'"), off


@needs_postgres
async def test_off_a_terminated_backend_fails_the_first_statement_then_reconnects(
    driver_log, pre_ping, scratch_table,
):
    pre_ping(False)
    table, admin = scratch_table
    sessions = wcs.ConsumerSessions("preping-off-disconnect")
    try:
        first_pid = await _phase(sessions, insert=(table, 1))
        async with admin.connect() as conn:
            await conn.execute(
                text("SELECT pg_terminate_backend(:pid)"), {"pid": first_pid}
            )
        await asyncio.sleep(0.2)
        with pytest.raises(DBAPIError) as raised:
            await _phase(sessions, insert=(table, 2))
        assert raised.value.connection_invalidated is True
        third_pid = await _phase(sessions, insert=(table, 3))
        assert third_pid != first_pid
        assert len(driver_log) == 2  # one connect per connection, no more
        async with admin.connect() as conn:
            ops = (await conn.execute(text(f"SELECT op FROM {table} ORDER BY op"))).scalars().all()
        assert ops == [1, 3]  # the failed phase committed nothing
    finally:
        await sessions.aclose()


@needs_postgres
async def test_on_control_the_ping_finds_a_terminated_backend(
    driver_log, pre_ping, scratch_table,
):
    pre_ping(True)
    table, admin = scratch_table
    sessions = wcs.ConsumerSessions("preping-on-disconnect")
    try:
        first_pid = await _phase(sessions, insert=(table, 1))
        async with admin.connect() as conn:
            await conn.execute(
                text("SELECT pg_terminate_backend(:pid)"), {"pid": first_pid}
            )
        await asyncio.sleep(0.2)
        assert await _phase(sessions, insert=(table, 2)) != first_pid
    finally:
        await sessions.aclose()


@needs_postgres
@pytest.mark.parametrize("value", [True, False])
async def test_the_set_lock_split_on_the_real_pool(driver_log, pre_ping, value):
    pre_ping(value)
    sessions = wcs.ConsumerSessions(f"preping-split-{value}")
    try:
        first = _FlushTimings()
        await _phase(sessions, first)
        first.flushed(1.0)
        assert first.slowest_lock["connects"] == 1
        assert 0 < first.slowest_lock["connect"] <= first.slowest_lock["checkout"]
        assert first.slowest_lock["checkout"] <= first.slowest_db["set_lock"]
        assert (first.slowest_lock["full"], first.slowest_lock["spans"]) == (0, 1)

        pooled = _FlushTimings()
        await _phase(sessions, pooled)
        pooled.flushed(1.0)
        assert pooled.slowest_lock["connects"] == 0
        assert pooled.slowest_lock["connect"] == 0.0
        assert pooled.slowest_lock["set"] > 0

        # All five slots out: the span starts full and waits for a release.
        release = asyncio.Event()
        holding = 0
        all_out = asyncio.Event()

        async def hold():
            nonlocal holding
            async with sessions.session() as session:
                await session.execute(text("SELECT 1"))
                holding += 1
                if holding == 5:
                    all_out.set()
                await release.wait()

        holders = [asyncio.create_task(hold()) for _ in range(5)]
        await all_out.wait()
        asyncio.get_running_loop().call_later(0.3, release.set)
        waited = _FlushTimings()
        await _phase(sessions, waited)
        waited.flushed(1.0)
        await asyncio.gather(*holders)
        assert (waited.slowest_lock["full"], waited.slowest_lock["spans"]) == (1, 1)
        assert waited.slowest_lock["checkout"] >= 0.25
        assert waited.slowest_lock["set"] < waited.slowest_lock["checkout"]
        assert "full_at_start=1/1" in waited.line()
    finally:
        await sessions.aclose()


@pytest.fixture
async def scratch_table():
    name = f"ws10090pp_{uuid.uuid4().hex[:10]}"
    admin = create_async_engine(DB_URL)
    async with admin.begin() as conn:
        await conn.execute(text(f"CREATE TABLE {name} (op int PRIMARY KEY)"))
    try:
        yield name, admin
    finally:
        async with admin.begin() as conn:
            await conn.execute(text(f"DROP TABLE IF EXISTS {name}"))
        await admin.dispose()
