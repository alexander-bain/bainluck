"""#10689: proposed consuming arguments in the actual Kalshi flush on PostgreSQL.

Each arm uses ordinary AsyncSession/Core UPDATE, real rank/commit/publisher,
an independent committed readback and the application's unchanged result loop.
No timings or raw driver access. The production consuming writer stays unedited.
"""

import asyncio
import contextlib
import json
import logging
import time
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import event, func, insert, or_, text, update
from sqlalchemy.ext.asyncio import create_async_engine

from app.models.models import Base, FuturesOutcome
from app.tasks import base as task_base, kalshi_ws
from app.tasks.live_blend_refresh import TailReceipts, event_ids_for_outcomes
from app.utils import market_quote_push
from app.utils.futures_rank import rerank_market_fields_stmt
from app.utils.kalshi_price_statement import (
    KALSHI_PRICE_STATEMENTS,
    kalshi_price_parameters,
)
from app.utils.price_change_stamp import price_changed_at_value, quote_moved_column
from app.utils.resolution_authority import AUTHORITATIVE_SOURCES
from tests.kalshi_price_statement_support import consuming_flush
from tests.pm_bulk_test_support import cleanup_pg_engines as cleanup_pg_engines
from tests.pm_bulk_test_support import fail_price_trigger, pg_engine

pytestmark = pytest.mark.asyncio
PRIOR = datetime(2026, 1, 1, tzinfo=timezone.utc)


class _Pool:
    def __init__(self, publish):
        self.publish = publish

    async def get_connection(self, *_a):
        return self

    async def release(self, _conn):
        pass

    def pack_commands(self, commands):
        return list(commands)

    async def send_packed_command(self, commands, **_kw):
        for verb, channel, payload in commands:
            assert verb == "PUBLISH"
            await self.publish(channel, payload)

    async def read_response(self, **_kw):
        return 0

    async def disconnect(self):
        pass


async def _run(control, candidate):
    sync = pg_engine()
    n = 6 if control == "mixed_books" else 2
    guard_sources = [None, "ungradeable_result", *sorted(AUTHORITATIVE_SOURCES)]
    if control == "resolution_guards":
        n = len(guard_sources)
    incoming = {i: (0.3, 0.2, 0.4) for i in range(1, n + 1)}
    if control in ("retry", "rollback", "commit_error", "resolution_guards"):
        incoming = {i: (0.6, 0.5, 0.7) for i in incoming}
    if control == "rank":
        incoming = {1: (0.2, 0.1, 0.3), 2: (0.8, 0.7, 0.9)}
    if control == "mixed_books":
        incoming = dict(
            enumerate(
                [
                    (0.3, 0.2, 0.4),
                    (0.3, None, 0.9),
                    (0.3, 0.8, None),
                    (0.3, None, None),
                    (0.30000001, 0.20001, 0.40001),
                    (0.3, 0.2, 0.4),
                ],
                1,
            )
        )
    if control == "precision_rounding":
        incoming = {1: (0.30000001, 0.20001, 0.40001), 2: (0.3, None, None)}
    with sync.begin() as conn:
        schema = conn.scalar(text("SELECT current_schema()"))
        tables = [
            Base.metadata.tables[name]
            for name in (
                "sports",
                "teams",
                "venues",
                "events",
                "futures_markets",
                "futures_outcomes",
            )
        ]
        Base.metadata.create_all(conn, tables=tables)
        conn.execute(
            insert(Base.metadata.tables["sports"]).values(
                id=1,
                key="baseball_mlb",
                name="MLB",
            )
        )
        conn.execute(
            insert(Base.metadata.tables["events"]).values(
                id=100,
                sport_id=1,
                home_team_name="Cubs",
                away_team_name="Marlins",
                status="live",
                commence_time=PRIOR,
            )
        )
        conn.execute(
            insert(Base.metadata.tables["futures_markets"]).values(
                id=1,
                source="kalshi",
                external_id="KXTEST",
                name="A vs B",
                category="game",
                status="open",
                mutually_exclusive=True,
                event_id=100,
            )
        )
        for oid in range(1, n + 1):
            probability = (0.6 if oid == 1 else 0.4) if control == "rank" else 0.3
            book = (0.2, 0.4)
            if control in ("later_row_writer", "real_book_move") and oid == 2:
                book = (0.1, 0.3)
            if control == "held_first_row_writer" and oid == 1:
                book = (0.1, 0.3)
            conn.execute(
                insert(FuturesOutcome.__table__).values(
                    id=oid,
                    market_id=1,
                    external_id=f"leg{oid}",
                    name=f"Leg {oid}",
                    rank=oid,
                    current_probability=probability,
                    current_yes_bid=book[0],
                    current_yes_ask=book[1],
                    last_updated=PRIOR,
                    price_changed_at=PRIOR,
                    resolution_source=(
                        guard_sources[oid - 1]
                        if control == "resolution_guards"
                        else None
                    ),
                )
            )
        if control in ("driver_error", "retry"):
            fail_price_trigger(conn, "hoist_row2", 2, "second leg")
    engine = create_async_engine(
        sync.url.set(drivername="postgresql+asyncpg"),
        connect_args={"server_settings": {"search_path": schema}},
        pool_size=4,
        max_overflow=0,
    )
    buffer, observations, frames, trace, hooks = dict(incoming), [], [], [], []
    stats = {
        key: 0
        for key in (
            "price_updates",
            "flushes",
            "errors",
            "requeued",
            "settled_declined",
            "quotes_unchanged",
            "ranks_rederived",
            "open_contract_prices_written",
        )
    }
    price_started = asyncio.Event()
    writer_pid = None
    sessions = 0
    fail_commit = control == "commit_error"

    def is_price(sql):
        return sql.startswith("UPDATE futures_outcomes SET current_probability=")

    @event.listens_for(engine.sync_engine, "before_cursor_execute")
    def before(_conn, _cursor, sql, parameters, _context, many):
        if is_price(sql):
            hooks.append(("before", sql, tuple(parameters), many))

    @event.listens_for(engine.sync_engine, "after_cursor_execute")
    def after(_conn, cursor, sql, _parameters, _context, _many):
        if is_price(sql):
            hooks.append(("after", cursor.rowcount))

    @event.listens_for(engine.sync_engine, "handle_error")
    def error(context):
        if context.statement and is_price(context.statement):
            hooks.append(
                (
                    "error",
                    type(context.sqlalchemy_exception).__name__,
                    context.is_disconnect,
                )
            )

    @event.listens_for(engine.sync_engine, "commit")
    def committed(_conn):
        if fail_commit:
            raise RuntimeError("deliberate outer commit failure")

    class Result:
        def __init__(self, real):
            self.real, self.rowcount = real, real.rowcount

        def all(self):
            rows = self.real.all()
            observations.extend((row.id, row.quote_moved) for row in rows)
            return rows

    class Proxy:
        def __init__(self, real):
            self.real, self.sync_session, self.info = real, real.sync_session, real.info

        async def execute(self, stmt, parameters=None):
            nonlocal writer_pid
            fields = {
                getattr(key, "name", str(key))
                for key in (getattr(stmt, "_values", None) or {})
            }
            if "current_probability" in fields:
                if writer_pid is None:
                    writer_pid = await self.real.scalar(text("SELECT pg_backend_pid()"))
                price_started.set()
                return Result(await self.real.execute(stmt, parameters))
            if control == "rollback" and "rank" in fields:
                return await self.real.execute(text("SELECT 1 / 0"))
            return await self.real.execute(stmt, parameters)

    @contextlib.asynccontextmanager
    async def factory():
        nonlocal sessions
        sessions += 1
        async with task_base.get_task_session(engine=engine) as session:
            event.listen(
                session.sync_session, "after_commit", lambda _: trace.append("commit")
            )
            event.listen(
                session.sync_session,
                "after_soft_rollback",
                lambda *_: trace.append("rollback"),
            )
            yield Proxy(session)

    async def publish(channel, payload):
        frame = json.loads(payload)
        assert "commit" in trace
        async with engine.connect() as conn:
            rows = (
                await conn.execute(
                    text(
                        "SELECT id,last_updated FROM futures_outcomes WHERE id=ANY(:ids)"
                    ),
                    {"ids": frame["outcome_ids"]},
                )
            ).all()
        assert {str(row.id): row.last_updated.isoformat() for row in rows} == frame[
            "outcome_observed_at"
        ]
        frames.append((channel, tuple(frame["outcome_ids"])))
        trace.append("publish")

    class Refresher:
        def pending_event_ids(self):  # #10655/#10661: no refresh debt owed here
            return frozenset()

        async def refresh_pending(self, **_kw):
            pass

        async def refresh(self, events, **_kw):
            trace.append(("blend", sorted(events)))

        async def publish_market_changes(self, session):
            return await market_quote_push.publish_committed_market_changes(
                session, SimpleNamespace(connection_pool=_Pool(publish))
            )

    ns = dict(
        asyncio=asyncio,
        contextlib=contextlib,
        logger=logging.getLogger(__name__),
        update=update,
        func=func,
        or_=or_,
        FuturesOutcome=FuturesOutcome,
        AUTHORITATIVE_SOURCES=AUTHORITATIVE_SOURCES,
        price_changed_at_value=price_changed_at_value,
        quote_moved_column=quote_moved_column,
        KALSHI_PRICE_STATEMENTS=KALSHI_PRICE_STATEMENTS,
        kalshi_price_parameters=kalshi_price_parameters,
        queue_market_change=market_quote_push.queue_market_change,
        rerank_market_fields_stmt=rerank_market_fields_stmt,
        linked_first_phases=kalshi_ws.linked_first_phases,
        # #10661: the per-phase lock budget the composed writer arms first.
        SET_LOCK_TIMEOUT_SQL=kalshi_ws.SET_LOCK_TIMEOUT_SQL,
        lock_timeout_value=kalshi_ws.lock_timeout_value,
        is_lock_timeout=kalshi_ws.is_lock_timeout,
        PRICE_PHASE_LOCK_TIMEOUT_MS=kalshi_ws.PRICE_PHASE_LOCK_TIMEOUT_MS,
        event_ids_for_outcomes=event_ids_for_outcomes,
        get_task_session=factory,
        buffer_lock=asyncio.Lock(),
        price_buffer=buffer,
        input_marks={},
        market_id_by_outcome={i: 1 for i in incoming},
        event_id_by_outcome={i: 100 for i in incoming},
        blend_refresher=Refresher(),
        tail_receipts=TailReceipts("kalshi"),
        open_contract_outcome_ids={1},
        stats=stats,
    )
    exec(compile(consuming_flush(candidate), kalshi_ws.__file__, "exec"), ns)
    holder = tx = pending = None
    try:
        held = control in {
            "held_first_row_writer",
            "later_row_writer",
            "newer_tick",
            "settlement",
            "vanished",
            "cancellation",
        }
        if held:
            holder = await engine.connect()
            tx = await holder.begin()
            await holder.execute(
                text("UPDATE futures_outcomes SET current_probability=.3 WHERE id=1")
            )
        pending = asyncio.create_task(ns["flush_prices"]())
        if held:
            await asyncio.wait_for(price_started.wait(), 3)
            deadline = time.monotonic() + 3
            while True:
                async with engine.connect() as conn:
                    waiting = await conn.scalar(
                        text(
                            "SELECT count(*) FROM pg_stat_activity WHERE pid=:pid AND wait_event_type='Lock'"
                        ),
                        {"pid": writer_pid},
                    )
                if waiting:
                    break
                if time.monotonic() >= deadline:
                    raise AssertionError("price backend did not wait on held row")
                await asyncio.sleep(0.01)
            if control == "cancellation":
                pending.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await asyncio.wait_for(pending, 3)
            elif control == "held_first_row_writer":
                await holder.execute(
                    text(
                        "UPDATE futures_outcomes SET current_yes_bid=.2,current_yes_ask=.4 WHERE id=1"
                    )
                )
                await tx.commit()
                trace.append("held_first_book_committed_after_observed_lock_wait")
                tx = None
            else:
                if control == "newer_tick":
                    buffer[1] = (0.9, 0.8, 1.0)
                elif control in {"later_row_writer", "settlement", "vanished"}:
                    statements = {
                        "later_row_writer": "UPDATE futures_outcomes SET current_yes_bid=.2,current_yes_ask=.4 WHERE id=2",
                        "settlement": "UPDATE futures_outcomes SET resolution_source=:source,current_probability=1 WHERE id=2",
                        "vanished": "DELETE FROM futures_outcomes WHERE id=2",
                    }
                    async with engine.begin() as conn:
                        await conn.execute(
                            text(statements[control]),
                            {"source": sorted(AUTHORITATIVE_SOURCES)[0]},
                        )
                await tx.rollback()
                tx = None
        succeeded = (
            False if control == "cancellation" else await asyncio.wait_for(pending, 8)
        )
        failed_prefix = []
        if control == "retry":
            assert not succeeded and buffer == incoming and not frames
            failed_prefix = list(observations)
            async with engine.begin() as conn:
                await conn.execute(text("DROP TRIGGER hoist_row2 ON futures_outcomes"))
            succeeded = await asyncio.wait_for(ns["flush_prices"](), 8)
            assert sessions == 2
        async with engine.connect() as conn:
            rows = [
                dict(row._mapping)
                for row in (
                    await conn.execute(
                        text(
                            "SELECT id,current_probability,current_yes_bid,current_yes_ask,rank,last_updated,price_changed_at FROM futures_outcomes ORDER BY id"
                        )
                    )
                ).all()
            ]
        if control in {"driver_error", "rollback", "commit_error", "cancellation"}:
            assert not succeeded and buffer == incoming and not frames
            assert all(row["last_updated"] == PRIOR for row in rows)
            assert "commit" not in trace
            if control != "cancellation":
                assert "rollback" in trace
        else:
            assert succeeded
            assert buffer == ({1: (0.9, 0.8, 1.0)} if control == "newer_tick" else {})
            assert "commit" in trace
        for row in rows:
            row["last_updated"] = "PRIOR" if row["last_updated"] == PRIOR else "TX"
            row["price_changed_at"] = (
                "PRIOR" if row["price_changed_at"] == PRIOR else "TX"
            )
        if control == "driver_error":
            assert stats == dict(
                price_updates=0,
                flushes=0,
                errors=1,
                requeued=2,
                settled_declined=0,
                quotes_unchanged=1,
                ranks_rederived=0,
                open_contract_prices_written=0,
            )
        if control == "retry":
            assert (
                failed_prefix == [(1, True)]
                and stats["errors"] == 1
                and stats["requeued"] == 2
            )
        if control in {
            "later_row_writer",
            "mixed_books",
            "precision_rounding",
        }:
            assert stats["quotes_unchanged"] == n and not frames
        if control == "held_first_row_writer":
            # This UPDATE began before the lock holder committed its book.
            # Its before-book subquery retains that statement snapshot, even
            # though the locked target row is rechecked after the holder exits.
            assert "held_first_book_committed_after_observed_lock_wait" in trace
            assert stats["quotes_unchanged"] == 1
            assert frames == [("live:market:1", (1,))]
        if control == "mixed_books":
            assert all(
                float(row["current_yes_bid"]) == 0.2
                and float(row["current_yes_ask"]) == 0.4
                for row in rows
            )
        if control == "real_book_move":
            assert frames == [("live:market:1", (2,))]
        if control == "rank":
            assert [row["rank"] for row in rows] == [2, 1]
        if control in {"settlement", "vanished"}:
            assert stats["settled_declined"] == 1 and stats["price_updates"] == 1
        if control == "settlement":
            assert (
                float(rows[1]["current_probability"]) == 1
                and rows[1]["last_updated"] == "PRIOR"
            )
        if control == "resolution_guards":
            assert stats["price_updates"] == 2 and stats["settled_declined"] == n - 2
            assert {oid for _, ids in frames for oid in ids} == {1, 2}
        return dict(
            rows=rows,
            stats=stats,
            buffer=buffer,
            frames=frames,
            observations=observations,
            failed_prefix=failed_prefix,
            succeeded=succeeded,
            hooks=hooks,
            trace=trace,
            sessions=sessions,
        )
    finally:
        if pending is not None and not pending.done():
            pending.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await pending
        if tx is not None:
            await tx.rollback()
        if holder is not None:
            await holder.close()
        await engine.dispose()


@pytest.mark.parametrize(
    "control",
    [
        "same",
        "later_row_writer",
        "held_first_row_writer",
        "real_book_move",
        "mixed_books",
        "precision_rounding",
        "resolution_guards",
        "rank",
        "settlement",
        "vanished",
        "driver_error",
        "retry",
        "rollback",
        "commit_error",
        "cancellation",
        "newer_tick",
    ],
)
async def test_actual_flush_source_counters_snapshots_hooks_and_transaction_parity(
    control,
):
    baseline = await _run(control, False)
    candidate = await _run(control, True)
    assert baseline == candidate
    before = [item for item in candidate["hooks"] if item[0] == "before"]
    assert all(item[-1] is False for item in before)
    if control == "driver_error":
        assert [item[0] for item in candidate["hooks"]] == [
            "before",
            "after",
            "before",
            "error",
        ]
        assert candidate["hooks"][-1] == ("error", "DBAPIError", False)
