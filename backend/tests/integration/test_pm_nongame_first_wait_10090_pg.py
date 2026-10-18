"""#10090 — a brief hold on a prop or standalone PM row never costs a whole 250 ms retry.

## the ship

A fast game cadence (`PM_WS_GAME_FLUSH_SECONDS` <= 25 ms) tries a whole game
chunk's price rows for only 1 ms, so the held-quote overlay publishes a newly
held game quote about 40 ms sooner (Root attempt70/71, actual EventPage). The
side loops — linked props and standalone open legs — must keep their 50 ms
first wait: they run on the 250 ms cadence, so a 1 ms try abandons a 20 ms hold
and waits for the next loop.

## the countercase (Root attempt71, private PG17)

Foreign transaction holds the price row; it rolls back 20 ms after the first
`UPDATE futures_outcomes` begins. First attempt -> committed price, 250 ms
cadence: 50 ms budget 48.6 / 33.6 ms (prop / standalone); a global 1 ms budget
275.7 / 269.5 ms (REJECTED); the scoped budget 44.4 / 32.7 ms.

## the rig

#11138's: the SHIPPED `flush_props` / `flush_standalone` and `write_chunk` on
the consumer's own pool, run by the shipped `run_flush_cadence`. The boundary
is given the FAST game budget on purpose, so the side chunks' fallback to
50 ms is what is under test — not a vacuous default.
"""

import asyncio
import contextlib
import time

import pytest
from sqlalchemy import event as sa_event, text

from app.tasks import live_blend_refresh as blend
from app.tasks.polymarket_ws import (
    FAST_GAME_FLUSH_SECONDS, FAST_GAME_PRICE_STATEMENT_LOCK_TIMEOUT_MS,
    _PMCatalogFlushBoundary, chunk_price_update_stmt,
)
from tests.integration.test_live_blend_grouped_commit_8129_pg import (  # noqa: F401
    DB_URL, rig,
)
from tests.integration.test_pm_held_price_row_stamps_received_quote_11138_pg import (
    hold_price_row,
)
from tests.integration.test_pm_stamp_release_wake_10090_pg import (  # noqa: F401
    build, consumer,
)

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL, reason="requires disposable SEARCH_TEST_DATABASE_URL"
    ),
]


async def warm_price_statement(consumer):
    """Prepare the price statement on every pooled connection, as a running
    consumer's already are. Cold, asyncpg's first use on a connection prepares
    it and introspects its array types — ~40 ms on PG14, longer than the hold —
    so the holder let go before the UPDATE executed, no lock wait happened and
    even the rejected global 1 ms budget passed (rolled back: no data moves)."""
    stmt = chunk_price_update_stmt({1: 0.5}, force_ids={1})
    async with contextlib.AsyncExitStack() as stack:
        for _ in range(5):
            conn = await stack.enter_async_context(consumer.connect())
            tx = await conn.begin()
            await conn.execute(stmt)
            await tx.rollback()


@pytest.mark.parametrize("kind", ["prop", "standalone"])
async def test_brief_non_game_lock_does_not_cost_a_whole_retry_period(
    rig, consumer, monkeypatch, kind,  # noqa: F811
):
    t = await build(rig, consumer, monkeypatch, trace=False, lock_ms=500)
    t.boundary.game_price_lock_timeout_ms = _PMCatalogFlushBoundary(
        game_period=FAST_GAME_FLUSH_SECONDS
    ).game_price_lock_timeout_ms
    assert t.boundary.game_price_lock_timeout_ms == FAST_GAME_PRICE_STATEMENT_LOCK_TIMEOUT_MS
    if kind == "prop":
        t.p.ns["non_blend_outcome_ids"].add(1)
        flush = t.p.ns["flush_props"]
        wake = t.boundary.prop_wake
        count = lambda: t.boundary.prop_work  # noqa: E731
    else:
        t.p.ns["open_outcome_ids"].add(1)
        t.p.ns["event_id_by_outcome"].pop(1)
        flush = t.p.ns["flush_standalone"]
        wake = asyncio.Event()
        count = None
    await warm_price_statement(consumer)
    holder, tx = await hold_price_row(rig, 1)
    observed = {}
    stop = asyncio.Event()
    release_task = None
    cadence = None

    async def release():
        await asyncio.sleep(0.020)
        await tx.rollback()
        observed["released"] = time.monotonic()

    def before_sql(conn, cursor, statement, params, context, executemany):
        nonlocal release_task
        if release_task is None and "UPDATE futures_outcomes" in statement:
            observed["first_attempt"] = time.monotonic()
            release_task = asyncio.create_task(release())

    sa_event.listen(consumer.sync_engine, "before_cursor_execute", before_sql)

    async def tracked(started):
        t.flush_starts.append(started)
        result = await flush(flush_started=started)
        if not t.p.ns["price_buffer"]:
            observed["published"] = time.monotonic()
            stop.set()
            wake.set()
        return result

    try:
        t.accept(1, 0.82)
        wake.set()
        cadence = asyncio.create_task(
            blend.run_flush_cadence(tracked, 0.25, stop=stop, wake=wake, work_count=count)
        )
        await asyncio.wait_for(cadence, 3)
        async with rig.engine.connect() as conn:
            value = await conn.scalar(
                text("SELECT current_probability FROM futures_outcomes WHERE id = 1")
            )
        assert float(value) == 0.82
        assert not t.pubs, "a non-game price must not stamp a headline"
        delay = observed["published"] - observed["first_attempt"]
        print("NON_GAME_EVIDENCE", kind, f"first_attempt_to_publish_ms={delay * 1000:.1f}")
        assert delay < 0.150, "a 20 ms hold must not add the 250 ms retry cadence"
    finally:
        sa_event.remove(consumer.sync_engine, "before_cursor_execute", before_sql)
        stop.set()
        wake.set()
        if cadence and not cadence.done():
            cadence.cancel()
            await asyncio.gather(cadence, return_exceptions=True)
        if release_task:
            await asyncio.gather(release_task, return_exceptions=True)
        if tx.is_active:
            await tx.rollback()
        await holder.close()
        await t.boundary.join_stamps()
        await t.r.drain_history()
