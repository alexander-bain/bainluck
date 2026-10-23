"""Tier 1: remove redundant checkout waits, never cache observation data."""

import asyncio
from contextlib import asynccontextmanager

import pytest
from sqlalchemy import select, literal, text

from app.tasks import ws_consumer_sessions as mod


class Connection:
    def __init__(self, engine):
        self.engine = engine
        self.invalidated = self.closed = self.executing = False
        self.did_close = asyncio.Event()

    async def __aenter__(self):
        self.engine.checkouts += 1
        if self.engine.checkouts > 1 and self.engine.block_next_checkout:
            try:
                await asyncio.Event().wait()
            except BaseException:
                self.closed = True  # failed checkout owns its own unwind
                raise
        return self

    async def execution_options(self, **options):
        assert options == {"isolation_level": "AUTOCOMMIT"}
        return self

    async def execute(self, statement):
        assert not self.executing and not self.closed and not self.invalidated
        self.executing = True
        try:
            if self.engine.query_error:
                raise RuntimeError("query failed")
            if self.engine.query_gate is not None:
                self.engine.query_entered.set()
                await self.engine.query_gate.wait()
            self.engine.reads += 1
            return self.engine.value
        finally:
            self.executing = False

    async def invalidate(self):
        self.invalidated = True

    async def close(self):
        assert not self.executing
        if self.engine.close_gate is not None:
            self.engine.close_entered.set()
            await self.engine.close_gate.wait()
        self.closed = True
        self.did_close.set()


class Engine:
    def __init__(self):
        self.connections = []
        self.checkouts = self.reads = 0
        self.value = 1
        self.query_error = self.block_next_checkout = False
        self.query_gate = self.close_gate = None
        self.query_entered = asyncio.Event()
        self.close_entered = asyncio.Event()
        self.disposed = False

    def connect(self):
        connection = Connection(self)
        self.connections.append(connection)
        return connection

    async def dispose(self):
        assert all(c.closed for c in self.connections)
        self.disposed = True


@pytest.fixture
def rig(monkeypatch):
    engine = Engine()
    owner = mod.ConsumerSessions("burst")
    owner._engine = engine
    monkeypatch.setattr(owner, "_engine_here", lambda: engine)
    return owner, engine


async def read(owner):
    async with owner.observation_read() as session:
        return await session.execute(select(literal(1)))


async def test_new_observation_arrives_while_redundant_checkout_would_stall(rig):
    owner, engine = rig
    try:
        assert await read(owner) == 1
        engine.value = 2
        engine.block_next_checkout = True
        # Parent waits in its second checkout; candidate fetches NEW data.
        assert await asyncio.wait_for(read(owner), 0.05) == 2
        assert engine.reads == 2 and engine.checkouts == 1
    finally:
        await owner.aclose()
    assert owner._open == 0 and engine.disposed


@pytest.mark.parametrize("bound", ["idle", "absolute"])
async def test_connection_returns_to_pool_at_burst_bound(rig, monkeypatch, bound):
    owner, engine = rig
    monkeypatch.setattr(mod, "OBSERVATION_IDLE_S", 0.01 if bound == "idle" else 1.0)
    monkeypatch.setattr(
        mod, "OBSERVATION_MAX_AGE_S", 0.01 if bound == "absolute" else 1.0
    )
    try:
        await read(owner)
        await asyncio.wait_for(engine.connections[0].did_close.wait(), 1)
        await read(owner)
        assert engine.checkouts == 2
    finally:
        await owner.aclose()
    assert owner._open == 0


async def test_each_read_gets_a_new_single_select_guard(rig):
    owner, engine = rig
    try:
        async with owner.observation_read() as session:
            assert await session.execute(select(literal(1))) == 1
            with pytest.raises(ValueError):
                await session.execute(select(literal(1)))
        assert await read(owner) == 1
        assert engine.reads == 2
        async with owner.observation_read() as session:
            with pytest.raises(ValueError):
                await session.execute(text("DELETE FROM events"))
        assert engine.reads == 2
        assert owner._observation_cached is None
    finally:
        await owner.aclose()


@pytest.mark.parametrize("failure", ["query", "caller", "cancel"])
async def test_failed_scope_never_reuses_connection(rig, failure):
    owner, engine = rig
    try:
        await read(owner)
        connection = engine.connections[0]
        if failure == "query":
            engine.query_error = True
            with pytest.raises(RuntimeError, match="query failed"):
                await read(owner)
            engine.query_error = False
        elif failure == "caller":
            with pytest.raises(RuntimeError, match="materialize"):
                async with owner.observation_read() as session:
                    await session.execute(select(literal(1)))
                    raise RuntimeError("materialize")
        else:
            engine.query_gate = asyncio.Event()
            task = asyncio.create_task(read(owner))
            await asyncio.wait_for(engine.query_entered.wait(), 1)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            engine.query_gate = None
        assert connection.invalidated and connection.closed
        assert await read(owner) == 1
        assert engine.checkouts == 2
    finally:
        await owner.aclose()


async def test_concurrent_reads_never_share_connection(rig):
    owner, engine = rig
    entered, release = asyncio.Event(), asyncio.Event()

    async def held():
        async with owner.observation_read() as session:
            await session.execute(select(literal(1)))
            entered.set()
            await release.wait()

    first = asyncio.create_task(held())
    try:
        await asyncio.wait_for(entered.wait(), 1)
        assert await read(owner) == 1
        release.set()
        await first
        assert engine.checkouts == 2
        assert sum(not c.closed for c in engine.connections) == 1
    finally:
        release.set()
        await first
        await owner.aclose()
    assert owner._open == 0


async def test_writer_demand_releases_idle_reader_and_prevents_new_reservation(
    rig, monkeypatch
):
    from app.tasks import base

    owner, engine = rig

    @asynccontextmanager
    async def writer(**kwargs):
        yield object()

    monkeypatch.setattr(base, "get_task_session", writer)
    try:
        await read(owner)
        first = engine.connections[0]
        async with owner.session():
            await asyncio.wait_for(first.did_close.wait(), 1)
            await read(owner)
            assert owner._observation_cached is None
            assert all(c.closed for c in engine.connections)
        assert owner._writers == 0
    finally:
        await owner.aclose()


async def test_shutdown_owns_idle_close_until_it_finishes(rig):
    owner, engine = rig
    await read(owner)
    engine.close_gate = asyncio.Event()
    task = asyncio.create_task(owner.aclose())
    try:
        await asyncio.wait_for(engine.close_entered.wait(), 1)
        assert not task.done() and not engine.disposed
        assert owner._open == 1
    finally:
        engine.close_gate.set()
        await task
    assert owner._open == 0 and engine.disposed


async def test_caught_query_error_still_discards_connection(rig):
    owner, engine = rig
    try:
        engine.query_error = True
        async with owner.observation_read() as reader:
            with pytest.raises(RuntimeError, match="query failed"):
                await reader.execute(select(literal(1)))
        assert engine.connections[0].invalidated
        assert owner._observation_cached is None
    finally:
        await owner.aclose()


async def test_shutdown_during_read_does_not_cache_connection(rig):
    owner, engine = rig
    entered, release = asyncio.Event(), asyncio.Event()

    async def held():
        async with owner.observation_read() as reader:
            await reader.execute(select(literal(1)))
            entered.set()
            await release.wait()

    read_task = asyncio.create_task(held())
    await asyncio.wait_for(entered.wait(), 1)
    close_task = asyncio.create_task(owner.aclose())
    await asyncio.sleep(0)
    assert not close_task.done()
    release.set()
    await read_task
    await close_task
    assert owner._observation_cached is None
    assert owner._open == 0 and engine.disposed


async def test_cancelled_writer_demand_still_owns_borrowed_connection_close(rig):
    owner, engine = rig
    await read(owner)
    engine.close_gate = asyncio.Event()

    async def writer():
        async with owner.session():
            pytest.fail("writer must await the released connection")

    task = asyncio.create_task(writer())
    await asyncio.wait_for(engine.close_entered.wait(), 1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert owner._writers == 0 and owner._open == 1
    engine.close_gate.set()
    await owner.aclose()
    assert owner._open == 0 and engine.disposed
