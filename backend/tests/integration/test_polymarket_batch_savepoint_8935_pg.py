"""#8935 — one failing event no longer throws away its whole Polymarket write batch (real Postgres).

PILLAR: TRUTH. SHIP: a Polymarket market's price, status and result stop going
stale for an hour, or six, because a different market in the same write batch
hit a database deadlock.

Production, recovery pass 2026-09-26 20:39Z: one ``DeadlockDetectedError`` and
then 18 ``InFailedSQLTransactionError`` on every later event in the batch. The
writer caught each failure and carried on inside the aborted transaction, and
its single closing ``COMMIT`` is turned into a ``ROLLBACK`` by Postgres, so the
events written BEFORE the failure were discarded as well.

Only Postgres can grade this. A session double does not abort a transaction on
a failed statement and does not turn COMMIT into ROLLBACK. The failure here is
a real database-side error (a title longer than ``futures_markets.name``'s
300), which aborts the transaction exactly as the deadlock did.

The payload is Gamma's own bytes (``tests/fixtures/polymarket_leg_dates_8466``),
copied to three events with distinct event and condition ids, and driven
through the REAL parser and the REAL ``_process_event_batch``.

#10090 — the batch now COMMITs after each complete event, not once at the end.
Releasing a savepoint releases no row lock, so a finished event's markets and
outcomes stayed locked while the writer waited on a later, unrelated event, and
a fresh live quote for the finished event waited behind it. The guards below
hold the next event's row from a second connection and write the finished
event's outcome with ``NOWAIT``; a failed per-event COMMIT (a real deferred
constraint) rolls back that event and its counts; and a cancellation never
commits a half-written event, while the events before it stay committed.
"""

from __future__ import annotations

import asyncio
import contextlib
import copy
import json
import os
from pathlib import Path

import pytest

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not DB_URL,
    reason="set SEARCH_TEST_DATABASE_URL to run the real-Postgres #8935 batch-savepoint gate",
)

FIXTURE = (
    Path(__file__).resolve().parent.parent
    / "fixtures"
    / "polymarket_leg_dates_8466"
    / "gamma-event-1038648.json"
)

FIRST, POISONED, LAST = "8935001", "8935002", "8935003"


def _copy(event_id: str, *, poison: bool = False) -> dict:
    raw = copy.deepcopy(json.loads(FIXTURE.read_text()))
    raw["id"] = event_id
    raw["slug"] = f"{raw['slug']}-{event_id}"
    for m in raw["markets"]:
        m["id"] = f"{m['id']}{event_id}"
        m["conditionId"] = f"{m['conditionId']}{event_id}"
    if poison:
        # futures_markets.name is String(300): Postgres refuses this at the upsert,
        # a database-side failure that aborts the transaction like a deadlock does.
        raw["title"] = "x" * 400
    return raw


@pytest.fixture
async def pg_engine(monkeypatch):
    from sqlalchemy.ext.asyncio import create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    import app.tasks.base as task_base
    from app.services.database import Base

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    monkeypatch.setattr(task_base, "DATABASE_URL", DB_URL)
    yield engine
    await engine.dispose()


async def _write_batch(raws: list[dict]) -> dict:
    """The REAL discovery-poll writer, handed one batch."""
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from app.models import FuturesMarket, FuturesOddsSnapshot, FuturesOutcome
    from app.services.polymarket_api import PolymarketAPIService
    from app.tasks.polymarket import _process_event_batch
    from app.utils.market_label_normalization import compute_market_tier
    from app.utils.odds_math import probability_to_american

    class _Counting(dict):
        def __missing__(self, key):
            return 0

    stats = _Counting({"errors": []})
    service = PolymarketAPIService()
    events = [service._parse_event(r) for r in raws]
    assert all(e is not None and len(e.markets) == 6 for e in events)
    await _process_event_batch(
        events, stats, FuturesMarket, FuturesOutcome, FuturesOddsSnapshot,
        pg_insert, probability_to_american, compute_market_tier,
    )
    return stats


async def _parents(engine) -> set[str]:
    from sqlalchemy import text

    async with engine.connect() as conn:
        rows = (await conn.execute(text(
            "SELECT external_id FROM futures_markets "
            "WHERE source='polymarket' AND external_id NOT LIKE '0x%'"
        ))).fetchall()
    return {r[0] for r in rows}


async def _legs_of(engine, event_id: str) -> int:
    from sqlalchemy import text

    async with engine.connect() as conn:
        return (await conn.execute(text(
            "SELECT count(*) FROM futures_markets "
            "WHERE source='polymarket' AND external_id LIKE :sfx"
        ), {"sfx": f"0x%{event_id}"})).scalar_one()


async def test_a_clean_batch_writes_every_event(pg_engine):
    """Control: without the poison all three land, so the arm below is
    measuring the failure and not the rig."""
    stats = await _write_batch([_copy(FIRST), _copy(POISONED), _copy(LAST)])
    assert not stats["errors"], stats["errors"]
    assert await _parents(pg_engine) == {FIRST, POISONED, LAST}


async def test_one_failing_event_rolls_back_only_itself(pg_engine):
    stats = await _write_batch(
        [_copy(FIRST), _copy(POISONED, poison=True), _copy(LAST)]
    )

    # Exactly one failure, and it is the poisoned event's own: the event after
    # it must not fail with "current transaction is aborted".
    assert [e.split(":")[0] for e in stats["errors"]] == [POISONED], stats["errors"]
    assert not any("InFailedSQLTransaction" in e for e in stats["errors"])

    # The event before the failure survives the closing COMMIT, and so does the
    # event after it, each with its six legs. Only the poisoned one is missing.
    assert await _parents(pg_engine) == {FIRST, LAST}
    assert await _legs_of(pg_engine, FIRST) == 6
    assert await _legs_of(pg_engine, LAST) == 6
    assert await _legs_of(pg_engine, POISONED) == 0


async def _first_outcome_and_last_parent(engine) -> tuple[int, int]:
    from sqlalchemy import text

    async with engine.connect() as conn:
        first_oid = (await conn.execute(text(
            "SELECT o.id FROM futures_outcomes o "
            "JOIN futures_markets m ON m.id = o.market_id "
            "WHERE m.source='polymarket' AND m.external_id LIKE :sfx "
            "ORDER BY o.id LIMIT 1"
        ), {"sfx": f"0x%{FIRST}"})).scalar_one()
        last_mid = (await conn.execute(text(
            "SELECT id FROM futures_markets "
            "WHERE source='polymarket' AND external_id=:id"
        ), {"id": LAST})).scalar_one()
    return first_oid, last_mid


async def test_a_finished_event_is_writable_while_the_next_event_waits(pg_engine):
    """#10090: the live socket's price UPDATE on a finished event's outcome must
    not wait for an unrelated later event in the same batch to finish.

    A second connection holds the LAST event's parent row, so the writer blocks
    on it with FIRST already written. FIRST's outcome must then be lockable with
    NOWAIT and its write must commit, and survive the batch finishing."""
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError

    raws = [_copy(FIRST), _copy(LAST)]
    seeded = await _write_batch(raws)
    assert not seeded["errors"], seeded["errors"]
    first_oid, last_mid = await _first_outcome_and_last_parent(pg_engine)

    task = None
    stats = None
    async with pg_engine.connect() as holder:
        held = await holder.begin()
        holder_pid = (await holder.execute(text("SELECT pg_backend_pid()"))).scalar_one()
        await holder.execute(
            text("SELECT id FROM futures_markets WHERE id=:id FOR UPDATE"), {"id": last_mid}
        )
        task = asyncio.create_task(_write_batch(raws))
        try:
            # The writer is provably parked on LAST's row, so FIRST is finished.
            async with pg_engine.connect() as observer:
                async with asyncio.timeout(15):
                    while not (await observer.execute(text(
                        "SELECT pid FROM pg_stat_activity "
                        "WHERE :holder = ANY(pg_blocking_pids(pid))"
                    ), {"holder": holder_pid})).scalars().all():
                        assert not task.done(), task.exception()
                        await asyncio.sleep(0.02)

            async with pg_engine.connect() as live_writer:
                try:
                    await live_writer.execute(text(
                        "SELECT id FROM futures_outcomes WHERE id=:id FOR UPDATE NOWAIT"
                    ), {"id": first_oid})
                except DBAPIError as exc:
                    # 55P03 lock_not_available: the finished event is still locked.
                    pytest.fail(
                        f"finished event {FIRST} still locked while {LAST} waits: "
                        f"{getattr(exc.orig, 'sqlstate', None)}"
                    )
                await live_writer.execute(text(
                    "UPDATE futures_outcomes SET current_probability=0.4321 WHERE id=:id"
                ), {"id": first_oid})
                await live_writer.commit()
        finally:
            await held.rollback()
            if task is not None:
                stats = await asyncio.wait_for(task, 15)

    assert not stats["errors"], stats["errors"]
    assert await _parents(pg_engine) == {FIRST, LAST}
    assert await _legs_of(pg_engine, FIRST) == 6
    assert await _legs_of(pg_engine, LAST) == 6
    async with pg_engine.connect() as conn:
        survived = (await conn.execute(text(
            "SELECT current_probability FROM futures_outcomes WHERE id=:id"
        ), {"id": first_oid})).scalar_one()
    assert float(survived) == 0.4321


async def test_a_failed_event_commit_rolls_back_that_event_and_its_counts(pg_engine):
    """#10090: a per-event COMMIT can fail on its own (a deferred constraint, a
    serialization failure). That event is rolled back, reported once, and does
    not count as processed; the next event still lands."""
    from sqlalchemy import text

    async with pg_engine.begin() as conn:
        await conn.execute(text(
            "CREATE OR REPLACE FUNCTION reject_8935001_at_commit() RETURNS trigger "
            "LANGUAGE plpgsql AS $$ BEGIN "
            "RAISE EXCEPTION 'deferred failure for 8935001'; END $$"
        ))
        # Deferred: every statement succeeds and only the COMMIT fails.
        await conn.execute(text(
            "CREATE CONSTRAINT TRIGGER reject_8935001_at_commit "
            "AFTER INSERT OR UPDATE ON futures_markets "
            "DEFERRABLE INITIALLY DEFERRED FOR EACH ROW "
            f"WHEN (NEW.external_id = '{FIRST}') "
            "EXECUTE FUNCTION reject_8935001_at_commit()"
        ))
    try:
        stats = await _write_batch([_copy(FIRST), _copy(LAST)])
    finally:
        async with pg_engine.begin() as conn:
            await conn.execute(text(
                "DROP TRIGGER IF EXISTS reject_8935001_at_commit ON futures_markets"
            ))
            await conn.execute(text("DROP FUNCTION IF EXISTS reject_8935001_at_commit()"))

    assert len(stats["errors"]) == 1, stats["errors"]
    assert stats["errors"][0].startswith(f"{FIRST}: commit failed:"), stats["errors"]
    assert await _parents(pg_engine) == {LAST}
    assert await _legs_of(pg_engine, FIRST) == 0
    assert await _legs_of(pg_engine, LAST) == 6
    # The counters are LAST's alone: FIRST's attempt was rolled back with it.
    assert stats["events_processed"] == 1, dict(stats)
    assert stats["sub_markets_created"] == 6, dict(stats)


@pytest.mark.parametrize("finished_first", [False, True], ids=["first-event", "after-a-finished-event"])
async def test_a_cancelled_batch_commits_no_half_written_event(pg_engine, monkeypatch, finished_first):
    """#10090: cancellation (a worker shutdown, a timeout) arrives between two
    statements of one event. That event must not be committed half-written by
    the per-event COMMIT, the CancelledError must propagate, and an event that
    had already finished stays committed with all six legs."""
    from sqlalchemy.ext.asyncio import AsyncSession

    target = LAST if finished_first else FIRST
    paused = asyncio.Event()
    original_execute = AsyncSession.execute

    async def pause_after_target_parent(self, statement, *args, **kwargs):
        result = await original_execute(self, statement, *args, **kwargs)
        table = getattr(getattr(statement, "table", None), "name", None)
        if (
            not paused.is_set()
            and getattr(statement, "is_insert", False)
            and table == "futures_markets"
            and statement.compile().params.get("external_id") == target
        ):
            paused.set()
            await asyncio.Event().wait()  # cancelled here, parent row written
        return result

    monkeypatch.setattr(AsyncSession, "execute", pause_after_target_parent)
    raws = [_copy(FIRST)] + ([_copy(LAST)] if finished_first else [])
    task = asyncio.create_task(_write_batch(raws))
    try:
        await asyncio.wait_for(paused.wait(), 15)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    finally:
        if not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    if finished_first:
        assert await _parents(pg_engine) == {FIRST}
        assert await _legs_of(pg_engine, FIRST) == 6
    else:
        assert await _parents(pg_engine) == set()
    assert await _legs_of(pg_engine, LAST) == 0
