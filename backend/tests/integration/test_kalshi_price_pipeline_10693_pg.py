"""#10693 actual utility through the current source flush and retained PG rig.

The reused rig is source-bound #10689; only its candidate price loop and result
instrumentation change in memory. No older lab main, timing or server runs.
"""

import ast
import asyncio
import contextlib
from contextlib import aclosing
import inspect

import pytest
from sqlalchemy import event, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine

from app.tasks import base as task_base
from app.utils import kalshi_price_pipeline as pipeline
from tests.integration import test_kalshi_price_statement_10689_pg as rig
from tests.kalshi_price_statement_support import consuming_flush
from tests.pm_bulk_test_support import cleanup_pg_engines as cleanup_pg_engines
from tests.pm_bulk_test_support import pg_engine

pytestmark = pytest.mark.asyncio


def _pipeline_flush(candidate):
    node = consuming_flush(False)
    if candidate:
        fn = node.body[0]
        loop = next(
            n
            for n in ast.walk(fn)
            if isinstance(n, ast.For)
            and ast.unparse(n.target) == "(outcome_id, (prob, yes_bid, yes_ask))"
        )
        parent = next(
            n for n in ast.walk(fn) if isinstance(n, ast.AsyncWith) and loop in n.body
        )
        replacement = ast.parse(
            """async with aclosing(pipeline_results(session, phase)) as results:
    async for result in results:
        rows = result.all()
        declined += result.attempted - result.rowcount
        written_outcome_ids.extend(row.id for row in rows)
        for row in rows:
            if not row.quote_moved:
                stats["quotes_unchanged"] += 1
                continue
            queue_market_change(session, market_id=row.market_id, source="kalshi", outcome_observed_at={row.id: row.last_updated})
"""
        ).body
        index = parent.body.index(loop)
        parent.body[index : index + 1] = replacement
    return ast.fix_missing_locations(node)


def _source_rig():
    source = inspect.getsource(rig._run)
    needle = "    ns = dict(\n"
    assert source.count(needle) == 1
    source = source.replace(
        needle,
        """    async def pipeline_results(session, phase):
        nonlocal writer_pid
        owner = pipeline.install_kalshi_price_pipeline(session.real.bind)
        if writer_pid is None:
            writer_pid = await session.real.scalar(text("SELECT pg_backend_pid()"))
        price_started.set()
        async with aclosing(owner.iter_phase(session.real, phase)) as results:
            async for result in results:
                observations.extend((row.id, row.quote_moved) for row in result.all())
                yield result

""" + needle,
    )
    source = source.replace(
        "        asyncio=asyncio,",
        "        aclosing=aclosing, pipeline_results=pipeline_results, asyncio=asyncio,",
    )
    # Only the disclosed failed-run diagnostics differ; persistent facts do not.
    source = source.replace(
        "quotes_unchanged=1,", "quotes_unchanged=0 if candidate else 1,"
    )
    source = source.replace(
        "failed_prefix == [(1, True)]",
        "failed_prefix == ([] if candidate else [(1, True)])",
    )
    source = source.replace(
        "        await engine.dispose()",
        """        owner = getattr(engine.sync_engine, pipeline._OWNER, None)
        if owner is not None:
            assert owner._active == 0
            owner.close()
        await engine.dispose()""",
    )
    ns = dict(
        rig.__dict__,
        consuming_flush=_pipeline_flush,
        pipeline=pipeline,
        aclosing=aclosing,
    )
    exec(compile(source, rig.__file__, "exec"), ns)
    return ns["_run"]


_run = _source_rig()


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
async def test_actual_pipeline_source_flow_and_allowed_failed_prefix_boundary(control):
    baseline, candidate = await _run(control, False), await _run(control, True)
    before = [item for item in candidate["hooks"] if item[0] == "before"]
    if control == "precision_rounding":
        assert before and all(item[-1] is False for item in before)
    else:
        assert any(
            item[-1] is True for item in before
        ), "supported-floor utility was not used"
    for key in ("rows", "buffer", "frames", "succeeded", "trace", "sessions"):
        assert baseline[key] == candidate[key]
    expected_stats = dict(baseline["stats"])
    if control == "driver_error":
        expected_stats["quotes_unchanged"] = 0
        assert (
            baseline["observations"] == [(1, False)] and candidate["observations"] == []
        )
        assert [item[0] for item in candidate["hooks"]] == ["before", "error"]
        assert candidate["hooks"][-1] == ("error", "DBAPIError", False)
    elif control == "retry":
        assert candidate["failed_prefix"] == [] and baseline["failed_prefix"] == [
            (1, True)
        ]
        assert baseline["observations"][1:] == candidate["observations"]
        assert sum(item[0] == "before" for item in candidate["hooks"]) == 2
    else:
        assert baseline["observations"] == candidate["observations"]
    assert candidate["stats"] == expected_stats


async def _minimal_engine(n=4):
    sync = pg_engine()
    with sync.begin() as conn:
        schema = conn.scalar(text("SELECT current_schema()"))
        conn.execute(text("""CREATE TABLE futures_outcomes (
            id INTEGER PRIMARY KEY, market_id INTEGER, resolution_source TEXT,
            current_probability NUMERIC(7,6), current_yes_bid NUMERIC(6,4),
            current_yes_ask NUMERIC(6,4), last_updated TIMESTAMPTZ,
            price_changed_at TIMESTAMPTZ)"""))
        conn.execute(
            text("""INSERT INTO futures_outcomes
            (id,market_id,current_probability,current_yes_bid,current_yes_ask,last_updated,price_changed_at)
            SELECT i,1,.3,.2,.4,now()-interval '1 hour',now()-interval '1 hour'
            FROM generate_series(1,:n) i"""),
            {"n": n},
        )
    return create_async_engine(
        sync.url.set(drivername="postgresql+asyncpg"),
        connect_args={"server_settings": {"search_path": schema}},
        pool_size=1,
        max_overflow=1,
    )


async def _consume(owner, session, phase):
    rows = []
    async with aclosing(owner.iter_phase(session, phase)) as results:
        async for result in results:
            rows.extend(result.all())
    return rows


async def _prices(engine):
    async with engine.connect() as conn:
        return dict(
            (
                await conn.execute(
                    text(
                        "SELECT id,current_probability FROM futures_outcomes ORDER BY id"
                    )
                )
            ).all()
        )


async def test_prior_completed_run_diagnostics_survive_later_run_fault_without_replay():
    engine = await _minimal_engine()
    owner = pipeline.install_kalshi_price_pipeline(engine)
    submissions = []

    @event.listens_for(engine.sync_engine, "before_cursor_execute")
    def submitted(_conn, _cursor, sql, parameters, _ctx, many):
        if sql.startswith("UPDATE futures_outcomes SET current_probability="):
            submissions.append((many, len(parameters) if many else 1))

    try:
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    """CREATE FUNCTION fail_four() RETURNS trigger LANGUAGE plpgsql AS $$
                BEGIN IF NEW.id=4 THEN RAISE EXCEPTION 'owned row4 failure'; END IF; RETURN NEW; END $$"""
                )
            )
            await conn.execute(
                text(
                    "CREATE TRIGGER fail_four BEFORE UPDATE ON futures_outcomes FOR EACH ROW EXECUTE FUNCTION fail_four()"
                )
            )
        observed = []
        phase = {
            1: (0.3, 0.2, 0.4),
            2: (0.3, 0.2, 0.4),
            3: (0.3, None, None),
            4: (0.6, None, None),
        }
        with pytest.raises(DBAPIError):
            async with task_base.get_task_session(engine=engine) as session:
                async with aclosing(owner.iter_phase(session, phase)) as results:
                    async for result in results:
                        observed.extend(
                            (row.id, row.quote_moved) for row in result.all()
                        )
        assert observed == [(1, False), (2, False)]
        assert submissions == [(True, 2), (True, 2)]
        assert all(float(value) == 0.3 for value in (await _prices(engine)).values())
        assert owner._active == 0
    finally:
        owner.close()
        await engine.dispose()


@pytest.mark.parametrize("exit_kind", ["caller-error", "early-break"])
async def test_caller_exit_closes_iterator_and_rollback_discards_completed_run(
    exit_kind,
):
    engine = await _minimal_engine()
    owner = pipeline.install_kalshi_price_pipeline(engine)
    try:
        with pytest.raises(LookupError):
            async with task_base.get_task_session(engine=engine) as session:
                async with aclosing(
                    owner.iter_phase(
                        session,
                        {1: (0.6, 0.5, 0.7), 2: (0.6, 0.5, 0.7), 3: (0.9, None, None)},
                    )
                ) as results:
                    async for result in results:
                        assert result.attempted == 2 and owner._active == 1
                        if exit_kind == "caller-error":
                            raise LookupError("caller processing failed")
                        break
                if exit_kind == "early-break":
                    raise LookupError("caller aborts incomplete phase")
        assert owner._active == 0
        assert all(float(value) == 0.3 for value in (await _prices(engine)).values())
        owner.close()
    finally:
        owner.close()
        await engine.dispose()


async def test_cancelled_query_invalidates_pool_and_fresh_session_recovers():
    engine = await _minimal_engine(2)
    owner = pipeline.install_kalshi_price_pipeline(engine)
    ready = asyncio.Event()
    failed = []
    invalidated = []
    pids = []

    @event.listens_for(engine.sync_engine, "before_cursor_execute")
    def before(_conn, _cursor, sql, _params, ctx, _many):
        if pipeline._TAG in ctx.execution_options:
            ready.set()

    @event.listens_for(engine.sync_engine, "handle_error")
    def error(context):
        failed.append(context.is_disconnect)

    @event.listens_for(engine.sync_engine.pool, "invalidate")
    def invalidate(_connection, _record, _error):
        invalidated.append(True)

    async def write():
        async with task_base.get_task_session(engine=engine) as session:
            pids.append(await session.scalar(text("SELECT pg_backend_pid()")))
            return await _consume(
                owner, session, {1: (0.6, 0.5, 0.7), 2: (0.6, 0.5, 0.7)}
            )

    holder = pending = tx = None
    try:
        holder = await engine.connect()
        tx = await holder.begin()
        await holder.execute(
            text("UPDATE futures_outcomes SET current_probability=.3 WHERE id=1")
        )
        pending = asyncio.create_task(write())
        await asyncio.wait_for(ready.wait(), 3)
        # The exact worker must actually be blocked, not merely scheduled.
        deadline = asyncio.get_running_loop().time() + 3
        while True:
            waiting = await holder.scalar(
                text(
                    "SELECT count(*) FROM pg_stat_activity WHERE pid=:pid AND wait_event_type='Lock'"
                ),
                {"pid": pids[0]},
            )
            if waiting:
                break
            if asyncio.get_running_loop().time() >= deadline:
                raise AssertionError("cancel worker did not wait on held row")
            await asyncio.sleep(0.01)
        pending.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(pending, 3)
        assert failed == [True] and invalidated == [True]
        assert owner._active == 0
        await tx.rollback()
        tx = None
        await holder.close()
        holder = None
        async with task_base.get_task_session(engine=engine) as session:
            assert await session.scalar(text("SELECT 1")) == 1
            recovered_pid = await session.scalar(text("SELECT pg_backend_pid()"))
            assert recovered_pid != pids[0]
            assert await session.scalar(text("SHOW lock_timeout")) == "0"
            rows = await _consume(
                owner, session, {1: (0.6, 0.5, 0.7), 2: (0.6, 0.5, 0.7)}
            )
            assert [row.id for row in rows] == [1, 2]
        assert all(float(value) == 0.6 for value in (await _prices(engine)).values())
    finally:
        if pending is not None and not pending.done():
            pending.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await pending
        if tx is not None:
            await tx.rollback()
        if holder is not None:
            await holder.close()
        owner.close()
        await engine.dispose()


async def test_caller_lock_budget_and_timeout_free_wait_keep_same_session_policy():
    from app.utils.repair_lock_budget import (
        SET_LOCK_TIMEOUT_SQL,
        is_lock_timeout,
        lock_timeout_value,
    )

    engine = await _minimal_engine(2)
    owner = pipeline.install_kalshi_price_pipeline(engine)
    holder = await engine.connect()
    tx = await holder.begin()
    task = None
    try:
        await holder.execute(
            text("UPDATE futures_outcomes SET current_probability=.3 WHERE id=1")
        )
        with pytest.raises(DBAPIError) as failure:
            async with task_base.get_task_session(engine=engine) as session:
                await session.execute(
                    SET_LOCK_TIMEOUT_SQL, {"ms": lock_timeout_value(500)}
                )
                await _consume(owner, session, {1: (0.6, 0.5, 0.7), 2: (0.6, 0.5, 0.7)})
        assert is_lock_timeout(failure.value)

        async def final_attempt():
            async with task_base.get_task_session(engine=engine) as session:
                assert await session.scalar(text("SHOW lock_timeout")) == "0"
                return await _consume(
                    owner, session, {1: (0.6, 0.5, 0.7), 2: (0.6, 0.5, 0.7)}
                )

        task = asyncio.create_task(final_attempt())
        await asyncio.sleep(0.6)
        assert (
            not task.done()
        ), "utility imposed the periodic timeout on an unbounded attempt"
        await tx.rollback()
        tx = None
        rows = await asyncio.wait_for(task, 3)
        assert [row.id for row in rows] == [1, 2]
        assert all(float(value) == 0.6 for value in (await _prices(engine)).values())
    finally:
        if task is not None and not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        if tx is not None:
            await tx.rollback()
        await holder.close()
        owner.close()
        await engine.dispose()


@pytest.mark.parametrize("book", [False, True])
async def test_stale_plan_rolls_back_then_next_session_recovers_on_same_backend(book):
    from sqlalchemy.exc import NotSupportedError

    engine = await _minimal_engine(2)
    owner = pipeline.install_kalshi_price_pipeline(engine)
    faults = []
    sends = []

    @event.listens_for(engine.sync_engine, "handle_error")
    def error(context):
        faults.append(
            (type(context.sqlalchemy_exception).__name__, context.is_disconnect)
        )

    @event.listens_for(engine.sync_engine, "before_cursor_execute")
    def before(_conn, _cursor, sql, _parameters, _ctx, many):
        if sql.startswith("UPDATE futures_outcomes SET current_probability="):
            sends.append(many)

    def values(probability):
        return (probability, 0.2 if book else None, 0.4 if book else None)

    pids = []
    try:
        async with engine.connect() as pinned:
            async with task_base.get_task_session(engine=pinned) as session:
                pids.append(await session.scalar(text("SELECT pg_backend_pid()")))
                await _consume(owner, session, {1: values(0.3), 2: values(0.3)})
            async with engine.begin() as ddl:
                await ddl.execute(
                    text(
                        "ALTER TABLE futures_outcomes ALTER COLUMN market_id TYPE BIGINT"
                    )
                )
            with pytest.raises(NotSupportedError) as failure:
                async with task_base.get_task_session(engine=pinned) as session:
                    pids.append(await session.scalar(text("SELECT pg_backend_pid()")))
                    await _consume(owner, session, {1: values(0.6), 2: values(0.6)})
            assert "InvalidCachedStatementError" in str(failure.value)
            assert all(
                float(value) == 0.3 for value in (await _prices(engine)).values()
            )
            async with task_base.get_task_session(engine=pinned) as session:
                pids.append(await session.scalar(text("SELECT pg_backend_pid()")))
                await _consume(owner, session, {1: values(0.6), 2: values(0.6)})
        assert len(set(pids)) == 1
        assert faults == [("NotSupportedError", False)] and sends == [True, True, True]
        assert all(float(value) == 0.6 for value in (await _prices(engine)).values())
    finally:
        owner.close()
        await engine.dispose()


async def test_untagged_executemany_and_unknown_version_use_ordinary_paths(monkeypatch):
    engine = await _minimal_engine(2)
    owner = pipeline.install_kalshi_price_pipeline(engine)
    seen = []

    @event.listens_for(engine.sync_engine, "before_cursor_execute")
    def before(_conn, _cursor, sql, _parameters, _context, many):
        if sql.startswith("UPDATE futures_outcomes SET current_probability="):
            seen.append(many)

    try:
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "UPDATE futures_outcomes SET current_probability=:probability WHERE id=:id"
                ),
                [{"id": 1, "probability": 0.3}, {"id": 2, "probability": 0.3}],
            )
        assert not owner._compatibility_checked and seen == [True]
        monkeypatch.setattr(
            pipeline.importlib.metadata, "version", lambda _name: "unsupported"
        )
        async with task_base.get_task_session(engine=engine) as session:
            rows = await _consume(
                owner, session, {1: (0.6, 0.5, 0.7), 2: (0.6, 0.5, 0.7)}
            )
            assert [row.id for row in rows] == [1, 2]
        assert seen == [True, False, False]
        assert all(float(value) == 0.6 for value in (await _prices(engine)).values())
    finally:
        owner.close()
        await engine.dispose()
