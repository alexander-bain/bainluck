"""#10090 WORST bucket 1 on real Postgres — an abandoned optional read keeps its connection.

The unit file (`tests/test_optional_db_abandon_10090.py`) pins the deadline and
lifecycle contract. This file pins the reason for the switch, which only a real
asyncpg connection can show: cancelling an in-flight execute at the deadline
makes SQLAlchemy invalidate the pooled connection, so the next checkout opens a
new one; abandoning it lets the read finish and the connection go back to the
pool. Both arms run through the consumer's own pool shape (5 retained, no
overflow, pre-ping) and through `ConsumerSessions.observation_read`, the
autocommit scope the Polymarket observation preview reads in.
"""

import asyncio
import os

import pytest
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import create_async_engine

from app.tasks.live_blend_refresh import OPTIONAL_DB_ABANDON_ENV, LiveBlendRefresher

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")
pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL, reason="requires disposable SEARCH_TEST_DATABASE_URL"
    ),
]

#: Longer than the 0.25 s budget, short enough for CI.
SLOW_READ = "SELECT pg_sleep(0.6)"


@pytest.fixture
async def pool():
    engine = create_async_engine(
        DB_URL, pool_size=5, max_overflow=0, pool_pre_ping=True,
    )
    counts = {"connect": 0, "invalidate": 0}

    @event.listens_for(engine.sync_engine.pool, "connect")
    def _connect(*_):
        counts["connect"] += 1

    @event.listens_for(engine.sync_engine.pool, "invalidate")
    def _invalidate(*_):
        counts["invalidate"] += 1

    # Warm one pooled connection so the arms start from a retained pool.
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    assert counts == {"connect": 1, "invalidate": 0}
    try:
        yield engine, counts
    finally:
        await engine.dispose()


async def _read_through(r, engine, kind):
    """One optional read at the production budget; True if it timed out."""

    async def body():
        async with engine.connect() as conn:
            await conn.execute(text(SLOW_READ))

    loop = asyncio.get_running_loop()
    started = loop.time()
    with pytest.raises(TimeoutError):
        await r._optional_db(kind, .25, body)
    return loop.time() - started


async def _settle(r):
    for task in list(r._optional_db_running.values()):
        await asyncio.wait_for(asyncio.shield(task), 5)


async def test_off_the_deadline_cancel_costs_the_connection(pool, monkeypatch):
    """The control: today's path invalidates and the next use reconnects."""
    monkeypatch.delenv(OPTIONAL_DB_ABANDON_ENV, raising=False)
    engine, counts = pool
    r = LiveBlendRefresher("polymarket")
    await _read_through(r, engine, "normal_ack")
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    assert counts["invalidate"] == 1, counts
    assert counts["connect"] == 2, counts


async def test_on_the_abandoned_read_keeps_the_connection(pool, monkeypatch):
    monkeypatch.setenv(OPTIONAL_DB_ABANDON_ENV, "1")
    engine, counts = pool
    r = LiveBlendRefresher("polymarket")
    waited = await _read_through(r, engine, "normal_ack")
    # The caller is released at the same deadline, not when the read ends.
    assert waited < .5, waited
    assert r.optional_db_abandoned == 1
    await _settle(r)
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    assert counts == {"connect": 1, "invalidate": 0}, counts


async def test_capacity_read_inside_its_pass_keeps_the_connection(pool, monkeypatch):
    """A capacity read cut by its PASS deadline, through ConsumerSessions.session."""
    from app.tasks import base as task_base
    from app.tasks.ws_consumer_sessions import ConsumerSessions

    engine, counts = pool
    monkeypatch.setattr(task_base, "_get_task_engine", lambda **_: engine)
    sessions = ConsumerSessions("abandon-pg")
    r = LiveBlendRefresher("kalshi")

    async def body(gate):
        async with r._session_slot():
            if gate is not None:
                gate.reading = True
            async with sessions.session() as session:
                await session.execute(text(SLOW_READ))
            if gate is not None:
                gate.read_done()

    for setting, invalidations in (("1", 0), ("0", 1)):
        monkeypatch.setenv(OPTIONAL_DB_ABANDON_ENV, setting)
        before = dict(counts)
        with pytest.raises(TimeoutError):
            async with asyncio.timeout(.25):
                await r._optional_db_in_pass("preview_capacity", body)
        await _settle(r)
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        assert counts["invalidate"] - before["invalidate"] == invalidations, (setting, counts)
        assert counts["connect"] - before["connect"] == invalidations, (setting, counts)
    assert not r._session_slots.locked() and sessions._open == 0
