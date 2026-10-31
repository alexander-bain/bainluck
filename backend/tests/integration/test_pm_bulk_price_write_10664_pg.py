"""#10664: actual bulk SQL and actual current-source chunk on PostgreSQL.

No synthetic timing claim: performance and generic-plan receipts are retained
in #10664's independent lab. These controls guard transaction semantics.
"""

import ast
import asyncio
import inspect
import json
import logging
import time
from contextlib import asynccontextmanager
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import event, insert, text
from sqlalchemy.ext.asyncio import create_async_engine

from app.models.models import Base, FuturesOutcome, FuturesMarket
import app.tasks.base as task_base
import app.tasks.polymarket_ws as module
from app.utils import market_quote_push
from app.utils.futures_rank import rerank_market_fields_stmt
from app.utils.repair_lock_budget import SET_LOCK_TIMEOUT_SQL, is_lock_timeout, lock_timeout_value
from tests.pm_bulk_test_support import cleanup_pg_engines, pg_engine

pytestmark = pytest.mark.asyncio


class _Connection:
    def __init__(self, publisher):
        self.publisher = publisher

    def pack_commands(self, commands):
        return list(commands)

    async def send_packed_command(self, commands, **_kw):
        for verb, channel, payload in commands:
            assert verb == "PUBLISH"
            await self.publisher.record(channel, payload)

    async def read_response(self, **_kw):
        return 0

    async def disconnect(self):
        pass


class _Pool:
    def __init__(self, publisher):
        self.connection = _Connection(publisher)

    async def get_connection(self, *_a):
        return self.connection

    async def release(self, _conn):
        pass


class _Publisher:
    def __init__(self, rig):
        self.rig = rig
        self.client = SimpleNamespace(connection_pool=_Pool(self))
        self.frames = []

    async def record(self, channel, payload):
        frame = json.loads(payload)
        # Independent connection must see exactly the committed observation
        # before the real publisher can emit it.
        async with self.rig.engine.connect() as conn:
            rows = (
                await conn.execute(
                    text(
                        "SELECT id, current_probability, last_updated FROM futures_outcomes "
                        "WHERE id = ANY(:ids)"
                    ),
                    {"ids": frame["outcome_ids"]},
                )
            ).all()
        assert {r.id for r in rows} == set(frame["outcome_ids"])
        for row in rows:
            assert (
                row.last_updated.isoformat()
                == frame["outcome_observed_at"][str(row.id)]
            )
        assert self.rig.trace[-1] == "commit"
        self.frames.append((channel, frame))

    async def publish_market_changes(self, session):
        return await market_quote_push.publish_committed_market_changes(
            session, self.client
        )


@pytest.fixture
async def rig():
    sync = pg_engine()
    with sync.begin() as conn:
        schema = conn.scalar(text("SELECT current_schema()"))
        Base.metadata.create_all(conn)
        conn.execute(
            insert(FuturesMarket.__table__),
            [
                dict(
                    id=1,
                    source="polymarket",
                    external_id="0x1",
                    name="A vs B",
                    category="game",
                    mutually_exclusive=True,
                    status="open",
                )
            ],
        )
        conn.execute(
            insert(FuturesOutcome.__table__),
            [
                dict(
                    id=i,
                    market_id=1,
                    external_id=f"leg{i}",
                    name=f"Leg {i}",
                    current_probability=Decimal("0.300000"),
                    rank=i,
                )
                for i in (1, 2, 3)
            ],
        )
    engine = create_async_engine(
        sync.url.set(drivername="postgresql+asyncpg"),
        connect_args={"server_settings": {"search_path": schema}},
        pool_size=4,
        max_overflow=0,
    )
    r = SimpleNamespace(
        engine=engine,
        trace=[],
        buffer={},
        before_exit=None,
        fail_rerank=False,
        fail_commit=False,
        price_started=asyncio.Event(),
        price_error_delay=0.0,
        price_errors=[],
    )
    stats = dict(
        price_updates=0,
        quotes_unchanged=0,
        ranks_rederived=0,
        errors=0,
        requeued=0,
        open_contract_prices_written=0,
    )
    r.stats = stats
    r.publisher = _Publisher(r)

    @event.listens_for(engine.sync_engine, "commit")
    def committed(_conn):
        if r.fail_commit:
            raise RuntimeError("outer commit failed")
        r.trace.append("commit")

    class Proxy:
        def __init__(self, real):
            self.real = real
            self.sync_session = real.sync_session
            self.info = real.info

        async def execute(self, stmt, params=None):
            # #10090: the price and rank statements arrive as a reused shape
            # plus their own binds; every other parameterised statement passes.
            if params is not None and not {"chunk_ids", "market_ids"} & set(params):
                return await self.real.execute(stmt, params)
            if "chunk_ids" in stmt.compile().params:
                r.price_pid = await self.real.scalar(text("SELECT pg_backend_pid()"))
                r.price_started.set()
                try:
                    return await self.real.execute(stmt, params)
                except Exception as exc:
                    r.price_errors.append(exc)
                    # Late receipt of the database's actual answer.
                    await asyncio.sleep(r.price_error_delay)
                    raise
            elif r.fail_rerank:
                # New input during the failed transaction must survive too.
                r.buffer[2] = 0.8
                # An actual SQL error after the price statement has returned.
                return await self.real.execute(text("SELECT 1 / 0"))
            return await self.real.execute(stmt, params)

    @asynccontextmanager
    async def factory():
        async with task_base.get_task_session(engine=engine) as session:
            yield Proxy(session)
            if r.before_exit is not None:
                r.before_exit()

    # Lift only the CURRENT application's closure, rather than copying its
    # orchestration into a test. Imports/outer bindings are the real ones.
    tree = ast.parse(inspect.getsource(module._run_polymarket_ws_consumer))
    fn = next(
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "write_chunk"
    )
    ns = dict(
        chunk_price_update_execution=module.chunk_price_update_execution,
        pm_rerank_market_fields_execution=module.pm_rerank_market_fields_execution,
        queue_market_change=market_quote_push.queue_market_change,
        rerank_market_fields_stmt=rerank_market_fields_stmt,
        get_task_session=factory,
        logger=logging.getLogger(__name__),
        open_outcome_ids=set(),
        non_blend_outcome_ids=set(),
        catalog_boundary=module._PMCatalogFlushBoundary(),
        stats=stats,
        market_by_outcome={1: 1, 2: 1, 3: 1},
        blend_refresher=r.publisher,
        buffer_lock=asyncio.Lock(),
        price_buffer=r.buffer,
        lock_retry_until={},
        lock_retry_events=set(),
        successful_price_write_at={},
        event_id_by_outcome={1: 10, 2: 10, 3: 10},
        event_ids_for_outcomes=lambda mapping, ids: {mapping[oid] for oid in ids if oid in mapping},
        PRICE_CHUNK_LOCK_TIMEOUT_MS=module.PRICE_CHUNK_LOCK_TIMEOUT_MS,
        PRICE_STATEMENT_LOCK_TIMEOUT_MS=module.PRICE_STATEMENT_LOCK_TIMEOUT_MS,
        PRICE_FLUSH_SECONDS=module.PRICE_FLUSH_SECONDS,
        SET_LOCK_TIMEOUT_SQL=SET_LOCK_TIMEOUT_SQL,
        is_lock_timeout=is_lock_timeout,
        is_price_row_lock_refusal=module.is_price_row_lock_refusal,
        lock_timeout_value=lock_timeout_value,
        _PMPriceWriteResult=module._PMPriceWriteResult,
    )
    exec(compile(ast.Module(body=[fn], type_ignores=[]), module.__file__, "exec"), ns)
    r.write = ns["write_chunk"]
    r.ns = ns
    try:
        yield r
    finally:
        await engine.dispose()


async def _prices(r):
    async with r.engine.connect() as conn:
        return dict(
            (
                await conn.execute(
                    text(
                        "SELECT id, current_probability FROM futures_outcomes ORDER BY id"
                    )
                )
            ).all()
        )


async def _write(r, chunk):
    r.buffer.update(chunk)
    return await r.write(dict(chunk))


async def test_order_precision_null_vanished_and_post_commit_publication(rig):
    chunk = {3: 0.30000001, 999: 0.8, 2: None, 1: 0.4567894}
    write_succeeded = await _write(rig, chunk)
    assert write_succeeded
    assert await _prices(rig) == {
        1: Decimal("0.456789"),
        2: None,
        3: Decimal("0.300000"),
    }
    assert rig.stats == dict(
        price_updates=3,
        quotes_unchanged=1,
        ranks_rederived=2,
        errors=0,
        requeued=0,
        open_contract_prices_written=0,
    )
    assert rig.buffer == {}
    assert len(rig.publisher.frames) == 1
    assert rig.publisher.frames[0][1]["outcome_ids"] == [1, 2]
    async with rig.engine.begin() as conn:
        rows = (
            await conn.execute(module.chunk_price_update_stmt({3: 0.4, 1: 0.5}))
        ).all()
    assert [(r.ord, r.id) for r in sorted(rows, key=lambda r: r.ord)] == [
        (1, 3),
        (2, 1),
    ]


async def test_settled_price_coverage_is_unchanged(rig):
    async with rig.engine.begin() as conn:
        await conn.execute(
            text(
                "UPDATE futures_outcomes SET resolution_source='settled', is_winner=true WHERE id=1"
            )
        )
    write_succeeded = await _write(rig, {1: 0.6})
    assert write_succeeded
    assert (await _prices(rig))[1] == Decimal(".600000")


async def test_repeat_ack_keeps_stamp_and_repairs_external_price_then_real_liveness(rig, monkeypatch):
    from tests.test_ws_flush_cadence_10090 import _FakeTime

    clock = _FakeTime(monkeypatch, t=1000)
    assert (await _write(rig, {1: 0.30000001})).written_ids == (1,)

    async def stamp():
        async with rig.engine.connect() as conn:
            return await conn.scalar(text("SELECT last_updated FROM futures_outcomes WHERE id=1"))

    first_stamp = await stamp()
    first_ranks = rig.stats["ranks_rederived"]
    clock.t = 1001
    assert (await _write(rig, {1: 0.30000001})).written_ids == ()
    assert rig.buffer == {} and await stamp() == first_stamp
    assert rig.stats["price_updates"] == 1
    assert rig.stats["ranks_rederived"] == first_ranks
    assert not rig.publisher.frames

    async with rig.engine.begin() as conn:
        await conn.execute(text("UPDATE futures_outcomes SET current_probability=0.4 WHERE id=1"))
    clock.t = 1002
    assert (await _write(rig, {1: 0.30000001})).written_ids == (1,)
    assert (await _prices(rig))[1] == Decimal("0.300000")
    assert len(rig.publisher.frames) == 1
    changed_stamp = await stamp()
    clock.t = 1032
    assert (await _write(rig, {1: 0.30000001})).written_ids == (1,)
    assert await stamp() != changed_stamp
    assert len(rig.publisher.frames) == 1, "a liveness write sends no unchanged-price frame"


async def test_atomic_overflow_returns_no_unchanged_observations(rig):
    write_succeeded = await _write(rig, {1: 0.3, 2: 10.0})
    assert not write_succeeded
    assert await _prices(rig) == {i: Decimal(".300000") for i in (1, 2, 3)}
    assert rig.publisher.frames == []
    assert rig.stats["quotes_unchanged"] == 0
    assert rig.stats["errors"] == 1 and rig.stats["requeued"] == 2
    assert rig.stats["price_updates"] == 0
    assert rig.buffer == {1: 0.3, 2: 10.0}


@pytest.mark.parametrize("failure", ["rerank", "outer_commit"])
async def test_later_failure_rolls_back_retains_latest_and_counts_returned_observations(
    rig, failure
):
    def fail_outer():
        rig.buffer[2] = 0.8

    if failure == "rerank":
        rig.fail_rerank = True
    else:
        rig.before_exit = fail_outer
        rig.fail_commit = True
    write_succeeded = await _write(rig, {1: 0.3, 2: 0.6})
    assert not write_succeeded
    assert await _prices(rig) == {i: Decimal(".300000") for i in (1, 2, 3)}
    assert rig.publisher.frames == []
    assert rig.stats["quotes_unchanged"] == 1
    assert rig.stats["price_updates"] == 0
    assert rig.stats["errors"] == 1 and rig.stats["requeued"] == 2
    assert rig.buffer == {1: 0.3, 2: 0.8}


async def test_newer_tick_survives_a_successful_old_write(rig):
    rig.before_exit = lambda: rig.buffer.update({1: 0.8})
    write_succeeded = await _write(rig, {1: 0.6})
    assert write_succeeded
    assert rig.buffer == {1: 0.8}
    assert (await _prices(rig))[1] == Decimal(".600000")
    rig.before_exit = None
    write_succeeded = await rig.write(dict(rig.buffer))
    assert write_succeeded
    assert rig.buffer == {}
    assert (await _prices(rig))[1] == Decimal(".800000")
    assert len(rig.publisher.frames) == 2


async def _wait_for_lock(rig):
    # Observe the actual blocked backend rather than assuming a sleep means a
    # lock was acquired. Bounded to 2s; private schema is unique to this test.
    for _ in range(100):
        async with rig.engine.connect() as conn:
            count = await conn.scalar(
                text(
                    "SELECT count(*) FROM pg_stat_activity WHERE wait_event_type='Lock' "
                    "AND pid = :pid"
                ),
                {"pid": rig.price_pid},
            )
        if count:
            return
        await asyncio.sleep(0.02)
    raise AssertionError("bulk statement never waited on the held PostgreSQL row")


async def test_concurrent_deletion_of_held_row_signals_only_surviving_row(rig):
    async with rig.engine.connect() as holder:
        txn = await holder.begin()
        await holder.execute(text("DELETE FROM futures_outcomes WHERE id=1"))
        pending = asyncio.create_task(_write(rig, {1: 0.6, 2: 0.7}))
        try:
            await asyncio.wait_for(rig.price_started.wait(), 2)
            await _wait_for_lock(rig)
            assert not pending.done() and rig.publisher.frames == []
            await txn.commit()
            write_succeeded = await asyncio.wait_for(pending, 2)
            assert write_succeeded
        finally:
            if txn.is_active:
                await txn.rollback()
            if not pending.done():
                pending.cancel()
                await asyncio.gather(pending, return_exceptions=True)
    assert 1 not in await _prices(rig)
    assert rig.publisher.frames[0][1]["outcome_ids"] == [2]
    assert rig.buffer == {}


async def test_cancelled_real_lock_wait_keeps_latest_input_and_publishes_nothing(rig):
    async with rig.engine.begin() as holder:
        await holder.execute(
            text("UPDATE futures_outcomes SET current_probability=.3 WHERE id=1")
        )
        pending = asyncio.create_task(_write(rig, {1: 0.6, 2: 0.7}))
        try:
            await asyncio.wait_for(rig.price_started.wait(), 2)
            await _wait_for_lock(rig)
            rig.buffer[1] = 0.8
            pending.cancel()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(pending, 2)
        finally:
            if not pending.done():
                pending.cancel()
                await asyncio.gather(pending, return_exceptions=True)
    assert rig.publisher.frames == []
    assert rig.buffer == {1: 0.8, 2: 0.7}
    assert await _prices(rig) == {i: Decimal(".300000") for i in (1, 2, 3)}
    assert (
        rig.stats["errors"] == rig.stats["requeued"] == rig.stats["price_updates"] == 0
    )


async def test_a_row_a_lock_already_refused_is_probed_nowait_and_a_fresh_chunk_still_waits(rig):
    # #10090: production's held 2- and 6-row cohorts failed about once a
    # second, each retry spending the whole 500 ms budget that every later
    # chunk and the next flush waited out. A known-held row is probed NOWAIT.
    async with rig.engine.connect() as holder:
        txn = await holder.begin()
        await holder.execute(
            text("SELECT id FROM futures_outcomes WHERE id IN (1, 3) FOR UPDATE")
        )
        fresh = None
        try:
            # The first attempt waits the short statement budget (actual lock timeout).
            assert await asyncio.wait_for(_write(rig, {1: 0.6, 2: 0.7}), 5) is None
            assert set(rig.ns["lock_retry_until"]) == {1, 2}
            # Any wait is now unmistakable: only NOWAIT can return in time.
            rig.ns["PRICE_CHUNK_LOCK_TIMEOUT_MS"] = 60_000
            rig.ns["PRICE_STATEMENT_LOCK_TIMEOUT_MS"] = 60_000
            rig.ns["lock_retry_until"].update({1: 0, 2: 0})  # cooldown expired
            rig.price_started.clear()
            written = await asyncio.wait_for(rig.write({1: 0.6, 2: 0.7}), 5)
            assert written is None
            # A refused probe waited for nothing: no new cooldown, still due.
            assert rig.ns["lock_retry_until"] == {1: 0, 2: 0}
            assert rig.buffer == {1: 0.6, 2: 0.7}
            assert rig.stats["errors"] == rig.stats["requeued"] // 2 == 1
            assert rig.stats["price_lock_probes_refused"] == 1
            # A row no lock has refused still waits out a brief holder.
            rig.price_started.clear()
            fresh = asyncio.create_task(_write(rig, {3: 0.8}))
            await asyncio.wait_for(rig.price_started.wait(), 2)
            await _wait_for_lock(rig)
            assert not fresh.done()
            await txn.rollback()
            assert (await asyncio.wait_for(fresh, 5)).written_ids == (3,)
        finally:
            if txn.is_active:
                await txn.rollback()
            if fresh is not None and not fresh.done():
                fresh.cancel()
                await asyncio.gather(fresh, return_exceptions=True)
    assert rig.publisher.frames[0][1]["outcome_ids"] == [3]
    # Released: the probe writes the retained pair atomically and clears it.
    rig.ns["lock_retry_until"].update({1: 0, 2: 0})
    written = await rig.write(dict(rig.buffer))
    assert written.written_ids == (1, 2)
    assert rig.buffer == {} and rig.ns["lock_retry_until"] == {}
    assert await _prices(rig) == {
        1: Decimal(".600000"), 2: Decimal(".700000"), 3: Decimal(".800000"),
    }


@pytest.mark.parametrize("refusal_delivery_delay", [0.0, 0.06])
async def test_a_known_held_pair_is_written_by_the_first_flush_after_a_brief_holder_lets_go(
    rig, refusal_delivery_delay,
):
    # #10090 recovery (Root's review_pg_transient_retry control): the pair's
    # cooldown is due and its holder lets go after a confirmed probe refusal
    # and at least 100 ms after the probe starts,
    # under the production 500 ms budget and the 250 ms flush cadence. A
    # refused probe used to re-arm the two-second cooldown, so every flush
    # skipped the pair for 2.2 s after the holder had gone (parent: 0.62 s).
    # 60 ms (Root's review_pg_delayed_refusal control): the same refusal,
    # received late. An elapsed-time test re-armed the cooldown (2.18 s).
    loop = asyncio.get_running_loop()
    rig.price_error_delay = refusal_delivery_delay
    rig.buffer.update({1: 0.6, 2: 0.4})
    rig.ns["lock_retry_until"].update({1: 0, 2: 0})
    rig.ns["lock_retry_events"].add(10)
    published = []
    record = rig.publisher.record

    async def stamped(channel, payload):
        await record(channel, payload)
        published.append(loop.time())

    rig.publisher.record = stamped
    released = []
    first_refusal = asyncio.Event()
    async with rig.engine.connect() as holder:
        txn = await holder.begin()
        await holder.execute(text("SELECT id FROM futures_outcomes WHERE id = 1 FOR UPDATE"))

        async def let_go():
            await asyncio.wait_for(rig.price_started.wait(), 2)
            await asyncio.sleep(0.1)
            await asyncio.wait_for(first_refusal.wait(), 5)
            await txn.rollback()
            released.append(loop.time())

        letting_go = asyncio.create_task(let_go())
        attempts = []
        start = loop.time()
        try:
            while rig.buffer.keys() & {1, 2} and len(attempts) < 16:
                await asyncio.sleep(max(0, start + 0.25 * len(attempts) - loop.time()))
                began = loop.time()
                if not released:
                    rig.buffer[1] = 0.61 + len(attempts) / 100  # latest input wins
                pair = {oid: rig.buffer[oid] for oid in (1, 2)}
                attempts.append((began, await asyncio.wait_for(rig.write(pair), 5), loop.time()))
                if len(attempts) == 1:
                    assert attempts[-1][1] is None
                    assert rig.price_errors and module.is_price_row_lock_refusal(rig.price_errors[-1])
                    first_refusal.set()
                # A row no lock refused, written in the same flush, never waits.
                fresh_write = await rig.write({3: 0.5 + len(attempts) / 100})
                assert fresh_write.written_ids == (3,)
                if len(attempts) == 1:
                    # Establish the release boundary before testing the next flush.
                    await letting_go
            await letting_go
        finally:
            if txn.is_active:
                await txn.rollback()
            await asyncio.gather(letting_go, return_exceptions=True)

    (released_at,) = released
    refused = [a for a in attempts if a[0] < released_at]
    after = [a for a in attempts if a[0] >= released_at]
    # Not vacuous: the holder refused the probe at once, NOWAIT, before it let go.
    assert refused and all(result is None and done < released_at for _, result, done in refused)
    # The FIRST flush after it let go writes the whole pair, newest values.
    assert after[0][1].written_ids == (1, 2) and len(after) == 1
    pair_frames = [f for _, f in rig.publisher.frames if f["outcome_ids"] == [1, 2]]
    assert len(pair_frames) == 1
    assert published[[f["outcome_ids"] for _, f in rig.publisher.frames].index([1, 2])] - released_at < 1.0
    assert rig.buffer == {} and rig.ns["lock_retry_until"] == {}
    assert rig.stats["price_lock_probes_refused"] == len(refused)
    assert rig.price_errors and all(
        module.is_price_row_lock_refusal(exc) for exc in rig.price_errors
    ), "classified by the database's own refusal"
    assert (await _prices(rig))[1] == Decimal(str(round(0.61 + (len(refused) - 1) / 100, 6)))


async def test_a_probe_whose_rerank_times_out_keeps_the_cooldown(rig):
    # #10090 (Root's review_pg_rerank_retry control): only the probe's own
    # immediate row refusal is retried next flush. Here the NOWAIT price write
    # succeeds and the rerank waits out the 500 ms budget on row 3, which must
    # move rank 3 -> 2. Treated as a refusal, that real wait would recur every
    # 250 ms flush with no error counted.
    rig.buffer.update({1: 0.6, 2: 0.1})
    rig.ns["lock_retry_until"].update({1: 0, 2: 0})
    rig.ns["lock_retry_events"].add(10)
    async with rig.engine.connect() as holder:
        txn = await holder.begin()
        await holder.execute(text("SELECT id FROM futures_outcomes WHERE id = 3 FOR UPDATE"))
        try:
            rig.price_started.clear()
            written = await asyncio.wait_for(rig.write(dict(rig.buffer)), 5)
            assert written is None
            assert rig.price_started.is_set(), "the probe's price statement ran"
            assert rig.stats["errors"] == 1 and rig.stats["requeued"] == 2
            assert not rig.stats.get("price_lock_probes_refused")
            assert min(rig.ns["lock_retry_until"].values()) > 0, "rerank timeout keeps the cooldown"
            # The next flush skips the pair without touching the database.
            await asyncio.sleep(0.25)
            rig.price_started.clear()
            written = await rig.write(dict(rig.buffer))
            assert written is None
            assert not rig.price_started.is_set()
            assert rig.stats["errors"] == 1
        finally:
            await txn.rollback()
    assert rig.buffer == {1: 0.6, 2: 0.1} and not rig.publisher.frames
    assert (await _prices(rig))[1] == Decimal(".300000")


async def test_a_first_attempt_waits_only_the_statement_budget_and_the_next_flush_writes(rig):
    # #10090 fast retry: a row no lock has refused yet waits the short price
    # statement budget, not the 500 ms chunk budget, and its lock timeout arms
    # no cooldown. A 150 ms holder used to be waited out and written in the
    # same flush; now it costs one failed attempt and the write lands at the
    # next flush (probed NOWAIT) after it lets go. In exchange the wait later
    # chunks of the flush pay for a held one falls from up to 500 ms to 50 ms.
    budget_s = module.PRICE_CHUNK_LOCK_TIMEOUT_MS / 1000
    assert module.PRICE_STATEMENT_LOCK_TIMEOUT_MS / 1000 < budget_s
    async with rig.engine.connect() as holder:
        txn = await holder.begin()
        await holder.execute(text("SELECT id FROM futures_outcomes WHERE id = 1 FOR UPDATE"))
        try:
            began = time.monotonic()
            assert await asyncio.wait_for(_write(rig, {1: 0.6, 2: 0.4}), 5) is None
            assert time.monotonic() - began < budget_s, "the chunk budget was waited out"
            (exc,) = rig.price_errors
            assert is_lock_timeout(exc) and not module.is_price_row_lock_refusal(exc)
            assert rig.stats["errors"] == 1 and rig.stats["requeued"] == 2
            assert set(rig.ns["lock_retry_until"]) == {1, 2}
            assert max(rig.ns["lock_retry_until"].values()) <= time.monotonic(), (
                "a price-statement lock timeout arms no cooldown"
            )
            # Still held: the next flush probes NOWAIT, refused at once.
            rig.price_started.clear()
            retried = await rig.write(dict(rig.buffer))
            assert retried is None
            assert rig.price_started.is_set(), "the next flush retries the pair"
            assert rig.stats["price_lock_probes_refused"] == 1
        finally:
            await txn.rollback()
    written = await rig.write(dict(rig.buffer))
    assert written.written_ids == (1, 2)
    assert rig.buffer == {} and rig.ns["lock_retry_until"] == {}
    assert rig.stats["errors"] == 1
    assert (await _prices(rig))[1] == Decimal(".600000")


async def test_a_probe_queued_behind_a_table_lock_is_an_error_retried_next_flush(rig):
    # #10090: NOWAIT covers row locks only; the statement's table lock is still
    # queued for, and the statement budget ends it as "canceling statement due
    # to lock timeout" — the same SQLSTATE as a row refusal, but real time
    # spent. It is never a refusal. Fast retry: it arms no cooldown, so the
    # next flush retries at the cost of one short statement budget and the
    # pair is written by the first flush after the table lock is released
    # (parent: a 500 ms wait, then a two-second cooldown). The rows were
    # already known-held, so each repeat is counted in `price_lock_timeouts`,
    # not logged as a fresh error (lane1 R1).
    rig.buffer.update({1: 0.6, 2: 0.4})
    rig.ns["lock_retry_until"].update({1: 0, 2: 0})
    rig.ns["lock_retry_events"].add(10)
    async with rig.engine.connect() as holder:
        txn = await holder.begin()
        await holder.execute(text("LOCK TABLE futures_outcomes IN EXCLUSIVE MODE"))
        try:
            written = await asyncio.wait_for(rig.write(dict(rig.buffer)), 5)
            assert written is None
            (exc,) = rig.price_errors
            assert is_lock_timeout(exc) and not module.is_price_row_lock_refusal(exc)
            assert rig.stats["price_lock_timeouts"] == 1
            assert rig.stats["errors"] == 0 and rig.stats["requeued"] == 0
            assert not rig.stats.get("price_lock_probes_refused")
            assert max(rig.ns["lock_retry_until"].values()) <= time.monotonic(), (
                "no cooldown is armed"
            )
            rig.price_started.clear()
            written = await rig.write(dict(rig.buffer))
            assert written is None
            assert rig.price_started.is_set(), "the next flush retries the pair"
            assert rig.stats["price_lock_timeouts"] == 2 and rig.stats["errors"] == 0
        finally:
            await txn.rollback()
    assert rig.buffer == {1: 0.6, 2: 0.4} and not rig.publisher.frames
    written = await rig.write(dict(rig.buffer))
    assert written.written_ids == (1, 2)
    assert rig.buffer == {} and rig.ns["lock_retry_until"] == {}
