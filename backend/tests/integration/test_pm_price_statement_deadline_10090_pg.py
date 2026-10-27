"""A server-bounded slow PM price UPDATE releases later changed DNPL inputs."""

from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path

import pytest
from sqlalchemy import event as sa_event, text

from app.tasks import live_blend_refresh as blend, polymarket_ws as pm
from app.utils import blend_preview
from tests.integration.test_live_blend_grouped_commit_8129_pg import DB_URL, rig  # noqa: F401
from tests.integration.test_pm_stamp_release_wake_10090_pg import (
    build, consumer, wait_for,
)
from tests.integration.test_pm_held_price_row_stamps_received_quote_11138_pg import wire_held_quotes
from tests.test_polymarket_withdrawal_speed_10651 import compile_functions
from tests.test_event_frame_batching_10659 import private_redis_socket  # noqa: F401

pytestmark = [pytest.mark.asyncio, pytest.mark.skipif(
    not DB_URL, reason='requires disposable SEARCH_TEST_DATABASE_URL',
)]


@pytest.fixture(autouse=True)
async def preview(monkeypatch, private_redis_socket, rig):  # noqa: F811
    """Default ledger runs real Lua; the existing sink still verifies commits.

    Record actual Redis subscriber receipts, not pre-CAS composed frames.
    Only the preview socket transport is injected; production admission,
    composition, publication and committed readback assertions remain intact.
    """
    from redis.asyncio import Redis
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from uuid import uuid4
    import runpy
    from app.services.dnpl_authority import AuthorityStore, preparing_candidate
    from app.services.dnpl_activation import ActivationController
    from app.utils.dnpl_authority_transport import decode_preview
    from app.utils.live_push import event_channel

    blend_preview.reset_registry_for_tests()
    client = Redis(unix_socket_path=str(private_redis_socket))
    # Exercise the real default v3 path: explicit migrations and activation,
    # followed by primary binding before this fixture accepts any source input.
    def upgrade(conn):
        with Operations.context(MigrationContext.configure(conn)):
            for name in ('dnpl_authority_10090.py', 'dnpl_retirement_10090.py'):
                runpy.run_path(str(Path(__file__).parents[2] / 'alembic/versions' / name))['upgrade']()

    async with rig.engine.begin() as conn:
        await conn.run_sync(upgrade)
    store = AuthorityStore(rig.maker)
    server, repl = await client.info('server'), await client.info('replication')
    old = await store.read()
    current = await store.prepare(old, preparing_candidate(
        old, namespace=uuid4(), operation_id=uuid4(), redis_run_id=server['run_id'],
        redis_master_replid=repl['master_replid'],
        policy_fingerprint=blend_preview.registry().policy.fingerprint,
    ))
    controller = ActivationController(store, client)
    await controller.arm(current)
    await controller.initialize(current)
    ready = await controller.ready(current)
    await blend_preview.registry().bind_primary(store)
    subscriber = client.pubsub()
    await subscriber.subscribe(*(event_channel(eid) for eid in (1, 2, 3)))
    for _ in range(3):
        await subscriber.get_message(timeout=1)

    async def call(*args):
        result = await client.execute_command(*args)
        if (args[0] == 'EVAL' and args[9 + int(args[2])] in ('publish', 'revoke')
                and result and result[0] == b'published'):
            message = await subscriber.get_message(ignore_subscribe_messages=True, timeout=1)
            assert message is not None, 'successful DNPL PUBLISH must reach subscriber'
            at = time.monotonic()
            receipt = decode_preview(message['channel'].decode(), message['data'], at)
            assert receipt.authority == ready
            call.frames.append((at, json.loads(receipt.payload)))
        return result

    call.frames = []
    monkeypatch.setattr(blend.LiveBlendRefresher, '_preview_call', staticmethod(lambda connection: call))
    try:
        assert isinstance(blend_preview.registry(), blend_preview.LedgerRegistry)
        yield
    finally:
        await subscriber.aclose()
        await client.aclose()
        blend_preview.reset_registry_for_tests()


async def prepared(rig, consumer, monkeypatch, *, warm=True, initialize=True):
    t = await build(rig, consumer, monkeypatch, trace=False, lock_ms=500)
    if parent := os.environ.get('PM_STATEMENT_PARENT'):
        compile_functions(Path(parent), ['write_chunk'], t.p.ns)
    # A running consumer has prepared the array UPDATE on its connections.
    # Warm the existing SQL on all five, as the neighboring first-wait rig does.
    from tests.integration.test_pm_nongame_first_wait_10090_pg import warm_price_statement
    if warm:
        await warm_price_statement(consumer)
    connection = t.r._client().connection_pool.connection
    original_sink = connection.sink

    async def sink(payload):
        if payload.get('reconcile_only'):
            # This is a price-free minimum-revision request. Verify its durable
            # revision independently; ordinary price payloads retain the full
            # original source-value and revision readback assertions below.
            assert payload['p'] is None
            eid = payload['event_id']
            async with rig.engine.connect() as conn:
                rev = await conn.scalar(text(
                    'SELECT win_probability_sources_rev FROM events WHERE id=:id'
                ), {'id': eid})
            assert rev >= payload['rev'][str(eid)]
            return
        await original_sink(payload)

    connection.sink = sink
    t.boundary.game_price_lock_timeout_ms = 1
    t.r.min_refresh_interval_s = .025
    await wire_held_quotes(t, consumer)
    frames = t.r._preview_call(None).frames
    if not initialize:
        return t, frames
    try:
        t.accept(1, .6)
        t.accept(2, .6)
        await t.tracked_flush(time.monotonic())
        await t.boundary.join_stamps()
        assert any(frame['preview']['kind'] == 'blend' for _, frame in frames)
        if warm:
            assert not t.p.ns['stats'].get('price_statement_timeouts'), 'warmup must complete before pressure'
        frames.clear()
        return t, frames
    except BaseException:
        await close_rig(t)
        raise


async def close_rig(t, stop=None, cadence=None):
    try:
        if cadence is not None:
            stop.set()
            t.boundary.flush_wake.set()
            await asyncio.wait_for(cadence, timeout=5)
    finally:
        try:
            await t.boundary.join_stamps()
        finally:
            try:
                await t.r.drain_history()
            finally:
                t.r.held_quotes = None
                await blend.reap_stopped_loops('polymarket', [])


async def slow_trigger(rig):
    async with rig.engine.begin() as conn:
        await conn.execute(text('CREATE TABLE price_delay (ends_at timestamptz)'))
        await conn.execute(text('''
            CREATE FUNCTION delayed_price() RETURNS trigger LANGUAGE plpgsql AS $$
            DECLARE remaining double precision;
            BEGIN
                IF NEW.id = 2 AND NEW.current_probability = .81 THEN
                    SELECT extract(epoch FROM ends_at - clock_timestamp())
                    INTO remaining FROM price_delay;
                    IF remaining > 0 THEN PERFORM pg_sleep(remaining); END IF;
                END IF;
                RETURN NEW;
            END $$
        '''))
        await conn.execute(text('''
            CREATE TRIGGER slow_price BEFORE UPDATE OF current_probability
            ON futures_outcomes FOR EACH ROW EXECUTE FUNCTION delayed_price()
        '''))
        await conn.execute(text("INSERT INTO price_delay VALUES (clock_timestamp() + interval '3.5 seconds')"))


def changed_frame(frames, eid, value):
    return [(at, frame) for at, frame in frames
            if frame['preview']['kind'] == 'blend' and frame['event_id'] == eid
            and frame['preview']['pending'].get('polymarket') == value]


async def test_later_changed_a_writes_and_previews_before_b_slow_period_ends(
    rig, consumer, monkeypatch,
):
    t, frames = await prepared(rig, consumer, monkeypatch)
    await slow_trigger(rig)
    pids = []

    def price_started(conn, cursor, statement, params, context, many):
        if 'UPDATE futures_outcomes SET' in statement:
            pids.append(conn.connection.driver_connection.get_server_pid())

    sa_event.listen(consumer.sync_engine, 'before_cursor_execute', price_started)
    stop = asyncio.Event()
    t.accept(2, .81)
    cadence = asyncio.create_task(blend.run_flush_cadence(
        t.tracked_flush, .025, stop=stop, failed_retry_interval_s=pm.PRICE_FLUSH_SECONDS,
        wake=t.boundary.flush_wake, work_count=lambda: t.boundary.flush_work,
    ))
    try:
        # New A arrives only after the real price UPDATE is asleep in PostgreSQL.
        async with asyncio.timeout(2):
            while True:
                async with rig.engine.connect() as conn:
                    asleep = await conn.scalar(text(
                        "SELECT count(*) FROM pg_stat_activity WHERE pid = ANY(:ids) "
                        "AND wait_event = 'PgSleep'"
                    ), {'ids': pids})
                if asleep:
                    break
                await asyncio.sleep(.005)
        sent = time.monotonic()
        t.accept(1, .82)
        await wait_for(lambda: bool(changed_frame(frames, 1, .82)), timeout=2.5)
        assert t.p.ns['stats']['price_statement_timeouts'] >= 1
        async with rig.engine.connect() as conn:
            rows = dict((await conn.execute(text(
                'SELECT id, current_probability FROM futures_outcomes WHERE id IN (1,2)'
            ))).all())
            still_slow = await conn.scalar(text('SELECT ends_at > clock_timestamp() FROM price_delay'))
        assert still_slow
        assert float(rows[1]) == .82, 'A took its ordinary price write'
        assert float(rows[2]) == .6, 'the timed-out B transaction rolled back'
        await wait_for(lambda: bool(changed_frame(frames, 2, .81)), timeout=1)
        assert 2 in t.r.held_quotes, 'B used the established frozen held-quote path'
        assert not any(values.get(2) == .81 for _, values in t.writes)
        print('EVIDENCE', {'a_changed_preview_after_input_s': round(
            changed_frame(frames, 1, .82)[0][0] - sent, 4),
            'price_statement_timeouts': t.p.ns['stats']['price_statement_timeouts']})
    finally:
        # End the injected slow period, then require ordinary recovery on both
        # arms; a harness unable to publish after release is not a red control.
        try:
            async with rig.engine.begin() as conn:
                await conn.execute(text('UPDATE price_delay SET ends_at = clock_timestamp()'))
            await wait_for(lambda: bool(changed_frame(frames, 1, .82)), timeout=6)
            await wait_for(lambda: 2 not in t.p.ns['price_buffer'], timeout=6)
        finally:
            try:
                await close_rig(t, stop, cadence)
            finally:
                sa_event.remove(consumer.sync_engine, 'before_cursor_execute', price_started)
    async with rig.engine.connect() as conn:
        assert float(await conn.scalar(text(
            'SELECT current_probability FROM futures_outcomes WHERE id=2'
        ))) == .81


@pytest.mark.parametrize('prior,mode', [('0', 'success'), ('2s', 'success'), ('2s', 'timeout'),
                                        ('80ms', 'success'), ('80ms', 'timeout'),
                                        ('2s', 'operator')])
async def test_real_statement_budget_scope_and_pooled_restoration(
    rig, consumer, monkeypatch, prior, mode,
):
    from contextlib import asynccontextmanager
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.sql.dml import Update
    from app.tasks.base import get_task_session

    t, frames = await prepared(rig, consumer, monkeypatch)
    t.r.preview_events = {1}  # unrelated B still shares the active DNPL game writer
    async with rig.engine.connect() as conn:
        schema = await conn.scalar(text('SELECT current_schema()'))
    pool = create_async_engine(DB_URL, pool_size=1, max_overflow=0, connect_args={
        'server_settings': {'search_path': schema, 'lock_timeout': '333ms'},
    })
    # Prime the new connection/type cache BEFORE installing the budget under
    # test. Otherwise an 80ms case can fail in asyncpg type introspection,
    # before the price-only budget action this warm-pool control exercises.
    # The separate cold-pool control below still does no preparation.
    async with pool.connect() as conn:
        tx = await conn.begin()
        await conn.execute(pm.chunk_price_update_stmt({1: .6}, force_ids={1}))
        await tx.rollback()
        await conn.execute(text("SELECT set_config('statement_timeout', :prior, false)"),
                           {'prior': prior})
        await conn.commit()
        assert await conn.scalar(text("SELECT current_setting('statement_timeout')")) == prior
    during, after, pids, price_errors = [], [], [], []
    settings_sql = text("SELECT current_setting('statement_timeout'), current_setting('lock_timeout')")

    class ObservedSession:
        def __init__(self, session):
            self.session, self.info = session, session.info

        def __getattr__(self, name):
            return getattr(self.session, name)

        async def execute(self, stmt, params=None):
            if (isinstance(stmt, Update) and stmt.table.name == 'futures_outcomes'
                    and 'current_probability' in {getattr(k, 'key', k) for k in stmt._values}):
                during.append(tuple((await self.session.execute(settings_sql)).one()))
                pids.append(await self.session.scalar(text('SELECT pg_backend_pid()')))
                try:
                    return await self.session.execute(stmt, params)
                except Exception as exc:
                    price_errors.append(exc)
                    raise
            return await self.session.execute(stmt, params)

        async def rollback(self):
            await self.session.rollback()

    @asynccontextmanager
    async def sessions():
        async with get_task_session(engine=pool) as session:
            yield ObservedSession(session)
            after.append(tuple((await session.execute(settings_sql)).one()))
            if prior in {'0', '2s'}:
                # The later transaction work must retain its original budget,
                # not the price-only 250ms limit.
                await session.execute(text('SELECT pg_sleep(.30)'))

    t.p.ns['get_task_session'] = sessions
    task = None
    try:
        if mode != 'success':
            await slow_trigger(rig)
        if mode == 'operator':
            # Deterministically deliver PostgreSQL's operator-cancel signal
            # inside the real price execute. An external observer can miss the
            # short interval before the 250ms deadline; cause is the subject.
            async with rig.engine.begin() as conn:
                await conn.execute(text('''
                    CREATE OR REPLACE FUNCTION delayed_price() RETURNS trigger
                    LANGUAGE plpgsql AS $$ BEGIN
                        IF NEW.id = 2 AND NEW.current_probability = .81 THEN
                            PERFORM pg_cancel_backend(pg_backend_pid());
                            PERFORM pg_sleep(3.5);
                        END IF;
                        RETURN NEW;
                    END $$
                '''))
        oid = 1 if mode == 'success' else 2
        t.accept(oid, .65 if mode == 'success' else .81)
        task = asyncio.create_task(t.p.ns['write_chunk']({oid: .65 if mode == 'success' else .81}))
        result = await task
        if mode == 'success':
            assert result.written_ids == (1,)
            assert after == [(prior, '500ms')]
        else:
            assert result is (False if mode == 'operator' else None)
            assert not after
            assert t.p.ns['price_buffer'][2] == .81
            assert t.p.ns['stats'].get('price_statement_timeouts', 0) == (mode == 'timeout')
            if mode == 'operator':
                assert len(price_errors) == 1
                driver_error = price_errors[0].orig.__cause__
                assert driver_error.sqlstate == '57014'
                assert driver_error.message == 'canceling statement due to user request'
                assert not pm.is_price_statement_timeout(price_errors[0])
                print('OPERATOR_EVIDENCE', driver_error.sqlstate, driver_error.message)
            async with rig.engine.connect() as conn:
                assert float(await conn.scalar(text('SELECT current_probability FROM futures_outcomes WHERE id=2'))) == .6
        assert during == [('80ms' if prior == '80ms' else '250ms', '1ms')]
        # Same single pooled connection, after success or aborted transaction:
        # neither local statement nor lock settings can leak to its next user.
        async with pool.connect() as conn:
            assert await conn.scalar(text('SELECT pg_backend_pid()')) == pids[0]
            assert tuple((await conn.execute(settings_sql)).one()) == (prior, '333ms')
    finally:
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        try:
            await close_rig(t)
        finally:
            await pool.dispose()


async def test_cold_pool_retries_make_ordinary_price_and_changed_preview_progress(
    rig, consumer, monkeypatch,
):
    # No direct preparation of the UPDATE on this consumer pool. Any first-use
    # statement timeout is real retained retry work, not reset or hidden.
    t, frames = await prepared(rig, consumer, monkeypatch, warm=False, initialize=False)
    stop = asyncio.Event()
    t.accept(1, .72)
    t.accept(2, .74)
    sent = time.monotonic()
    cadence = asyncio.create_task(blend.run_flush_cadence(
        t.tracked_flush, .025, stop=stop, failed_retry_interval_s=pm.PRICE_FLUSH_SECONDS,
        wake=t.boundary.flush_wake, work_count=lambda: t.boundary.flush_work,
    ))
    try:
        await wait_for(lambda: bool(changed_frame(frames, 1, .72))
                       and bool(changed_frame(frames, 2, .74))
                       and not t.p.ns['price_buffer'], timeout=2.5)
        async with rig.engine.connect() as conn:
            rows = dict((await conn.execute(text(
                'SELECT id, current_probability FROM futures_outcomes WHERE id IN (1,2)'
            ))).all())
        assert float(rows[1]) == .72 and float(rows[2]) == .74
        assert any(values.get(1) == .72 for _, values in t.writes)
        assert any(values.get(2) == .74 for _, values in t.writes)
        print('COLD_POOL_EVIDENCE', {'ordinary_writes_and_previews_after_input_s': round(
            time.monotonic() - sent, 4),
            'price_statement_timeouts': t.p.ns['stats'].get('price_statement_timeouts', 0)})
    finally:
        await close_rig(t, stop, cadence)
