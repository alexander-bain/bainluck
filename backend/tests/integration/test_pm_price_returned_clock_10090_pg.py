"""Ship: PM starts delivery without a redundant post-commit clock query."""
import asyncio
import time
from contextlib import AsyncExitStack, asynccontextmanager
from datetime import datetime, timezone
import pytest
from sqlalchemy import text
from app.tasks import live_blend_refresh as blend
from tests.integration.test_pm_held_price_row_stamps_received_quote_11138_pg import (
    DB_URL, rig, consumer, build, wire_held_quotes,
)
pytestmark = [pytest.mark.asyncio, pytest.mark.skipif(not DB_URL, reason="disposable PostgreSQL required")]

@pytest.fixture(autouse=True)
async def prepared_price_parameter_types(consumer):
    """Exercise returned-clock rules on an established consumer pool.

    SELECT 1 opens connections but leaves asyncpg array codecs cold. Prepare
    the price statement's types on every connection outside its 250ms budget;
    cold-pool behavior remains covered by the separate deadline suite.
    """
    async with AsyncExitStack() as stack:
        for _ in range(5):
            conn = await stack.enter_async_context(consumer.connect())
            await conn.execute(text(
                "SELECT ARRAY[1]::integer[], ARRAY[0.5]::numeric[], "
                "ARRAY[0.5]::double precision[], ARRAY[false]::boolean[]"
            ))


async def test_committed_price_supplies_future_bound_without_separate_query(rig, consumer, monkeypatch):
    t = await build(rig, consumer, monkeypatch, trace=False, lock_ms=500)
    held = await wire_held_quotes(t, consumer)
    old = held._database_bound
    mark = t.accept(1, 0.61)
    async def redundant_read(_sessions):
        pytest.fail("committed price clock must replace the extra query before display")
    held.sample_database_clock = redundant_read
    try:
        await t.tracked_flush(time.monotonic())
        await t.boundary.join_stamps()
        async with rig.engine.connect() as conn:
            updated = await conn.scalar(text("SELECT last_updated FROM futures_outcomes WHERE id=1"))
        assert held._database_bound >= updated.timestamp()
        assert held._database_bound > old
        assert held.bound_for(mark) == old
        assert held.bound_for(t.accept(1, 0.62)) == held._database_bound
        assert any(value == 0.61 for _, _, value, _ in t.pubs)
    finally:
        await t.boundary.join_stamps()
        held.close()

@pytest.mark.parametrize("failure", [RuntimeError, asyncio.CancelledError])
async def test_failed_session_exit_never_publishes_clock(rig, consumer, monkeypatch, failure):
    t = await build(rig, consumer, monkeypatch, trace=False, lock_ms=500)
    held = await wire_held_quotes(t, consumer)
    old = held._database_bound
    sessions = t.p.ns["get_task_session"]
    @asynccontextmanager
    async def failing_exit():
        async with sessions() as session:
            yield session
            assert held._database_bound == old
            raise failure("injected before commit")
    t.p.ns["get_task_session"] = failing_exit
    t.flush_starts.append(time.monotonic())
    t.accept(1, 0.61)
    try:
        if failure is asyncio.CancelledError:
            with pytest.raises(asyncio.CancelledError):
                await t.p.ns["write_chunk"]({1: 0.61})
        else:
            assert await t.p.ns["write_chunk"]({1: 0.61}) is False
        assert held._database_bound == old
        assert t.p.ns["price_buffer"][1] == 0.61
        async with rig.engine.connect() as conn:
            assert float(await conn.scalar(text("SELECT current_probability FROM futures_outcomes WHERE id=1"))) == 0.7
    finally:
        held.close()

@pytest.mark.parametrize("mode", ["replaced", "newer_ordinal", "no_rows", "final"])
async def test_unproven_write_retains_clock_fallback(rig, consumer, monkeypatch, mode):
    t = await build(rig, consumer, monkeypatch, trace=False, lock_ms=500)
    held = await wire_held_quotes(t, consumer)
    old = held._database_bound
    sessions = t.p.ns["get_task_session"]
    replacement = blend.HeldRowQuotes()
    @asynccontextmanager
    async def changed_exit():
        async with sessions() as session:
            yield session
            assert held._database_bound == old
        if mode == "replaced":
            t.r.held_quotes = replacement
        elif mode == "newer_ordinal":
            assert held.publish_write_clock(held.begin_write_clock(), datetime.fromtimestamp(old, timezone.utc))
    t.p.ns["get_task_session"] = changed_exit
    if mode == "no_rows":
        async with rig.engine.begin() as conn:
            await conn.execute(text("DELETE FROM futures_outcomes WHERE id=1"))
    t.flush_starts.append(time.monotonic())
    t.accept(1, 0.61)
    try:
        result = await t.p.ns["write_chunk"]({1: 0.61}, final=mode == "final")
        assert result.clock_owner is None
        assert held._database_bound == old
        assert replacement._database_bound is None
    finally:
        held.close()
        replacement.close()
