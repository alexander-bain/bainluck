"""Real PG controls for the durable domain, not activation or reader proof.

Uses the existing disposable PG URL/schema convention and the actual migration.
No fixture may inherit a production URL or create a runtime authority on loss.
"""

import asyncio
from contextlib import asynccontextmanager
from dataclasses import replace
import os
from pathlib import Path
import runpy
from types import SimpleNamespace
from uuid import uuid4

from alembic.migration import MigrationContext
from alembic.operations import Operations
import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.services.dnpl_authority import (
    AuthorityConflict,
    AuthorityLost,
    AuthorityStore,
    AuthorityWriteUncertain,
    MAX_INCARNATION,
    preparing_candidate,
)

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")
pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL,
        reason="requires disposable SEARCH_TEST_DATABASE_URL",
    ),
]


@pytest.fixture
async def rig():
    url = make_url(DB_URL)
    assert url.host in (None, "localhost", "127.0.0.1", "::1"), "local PG only"
    if url.host is None:
        assert str(url.query.get("host", "")).startswith(
            "/"
        ), "explicit Unix socket required"
    schema = "dnpl_authority_" + uuid4().hex
    admin = create_async_engine(DB_URL)
    async with admin.begin() as conn:
        await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_async_engine(
        DB_URL, connect_args={"server_settings": {"search_path": schema}}
    )
    maker = async_sessionmaker(engine, expire_on_commit=False)
    migration = runpy.run_path(
        str(Path(__file__).parents[2] / "alembic/versions/dnpl_authority_10090.py")
    )

    def upgrade(conn):
        with Operations.context(MigrationContext.configure(conn)):
            migration["upgrade"]()

    try:
        async with engine.begin() as conn:
            await conn.run_sync(upgrade)
        store = AuthorityStore(maker)
        yield SimpleNamespace(
            engine=engine, maker=maker, store=store, migration=migration
        )
    finally:
        await engine.dispose()
        async with admin.begin() as conn:
            await conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await admin.dispose()


def next_candidate(expected):
    return preparing_candidate(
        expected,
        namespace=uuid4(),
        operation_id=uuid4(),
        redis_run_id="a" * 40,
        redis_master_replid="b" * 40,
        policy_fingerprint="v1-six-hour-fixture:240,112,64,48,32,16",
    )


async def test_migration_disabled_seed_never_opens_stream(rig):
    seed = await rig.store.read()
    assert (seed.incarnation, seed.state) == (0, "disabled")
    with pytest.raises(ValueError):
        seed.wire_identity()
    with pytest.raises(ValueError):
        await rig.store.ready(seed)
    assert await rig.store.read() == seed


async def test_prepare_ready_disable_and_next_generation(rig):
    seed = await rig.store.read()
    prepared = await rig.store.prepare(seed, next_candidate(seed))
    with pytest.raises(ValueError):
        prepared.wire_identity()
    ready = await rig.store.ready(prepared)
    assert ready.wire_identity() == {
        "incarnation": "1",
        "namespace": str(prepared.namespace),
    }
    disabled = await rig.store.disable(ready)
    assert disabled.incarnation == 1
    successor = await rig.store.prepare(disabled, next_candidate(disabled))
    assert successor.incarnation == 2
    with pytest.raises(AuthorityConflict):
        await rig.store.ready(prepared)
    assert await rig.store.read() == successor


async def test_simultaneous_preparations_have_one_winner(rig):
    seed = await rig.store.read()
    candidates = [next_candidate(seed), next_candidate(seed)]
    results = await asyncio.gather(
        *(rig.store.prepare(seed, c) for c in candidates), return_exceptions=True
    )
    assert sum(isinstance(r, AuthorityConflict) for r in results) == 1
    current = await rig.store.read()
    assert current in candidates and current.incarnation == 1
    assert sum(r == current for r in results) == 1


async def test_abandoned_preparing_is_burned_and_cannot_mark_ready(rig):
    seed = await rig.store.read()
    first = await rig.store.prepare(seed, next_candidate(seed))
    second = await rig.store.prepare(first, next_candidate(first))
    with pytest.raises(AuthorityConflict):
        await rig.store.ready(first)
    assert (await rig.store.ready(second)).incarnation == 2


@pytest.mark.parametrize(
    "field,value",
    [
        ("namespace", uuid4()),
        ("operation_id", uuid4()),
        ("redis_run_id", "c" * 40),
        ("redis_master_replid", "d" * 40),
        ("policy_fingerprint", "another-policy"),
        ("incarnation", 2),
    ],
)
async def test_ready_requires_every_exact_identity_field(rig, field, value):
    seed = await rig.store.read()
    current = await rig.store.prepare(seed, next_candidate(seed))
    with pytest.raises(AuthorityConflict):
        await rig.store.ready(replace(current, **{field: value}))
    assert await rig.store.read() == current


def uncertain_sessions(maker, *, after_commit, cancellation=False):
    @asynccontextmanager
    async def factory():
        async with maker() as session:
            original = session.begin

            def fail():
                if cancellation:
                    raise asyncio.CancelledError()
                raise ConnectionError("lost transaction acknowledgement")

            @asynccontextmanager
            async def begin():
                async with original():
                    yield
                    if not after_commit:
                        fail()
                if after_commit:
                    fail()

            session.begin = begin
            yield session

    return factory


@pytest.mark.parametrize("after_commit", [False, True])
async def test_same_ack_failure_can_mean_committed_or_not_no_retry(rig, after_commit):
    seed = await rig.store.read()
    candidate = next_candidate(seed)
    uncertain = AuthorityStore(uncertain_sessions(rig.maker, after_commit=after_commit))
    with pytest.raises(AuthorityWriteUncertain):
        await uncertain.prepare(seed, candidate)
    assert await rig.store.read() == (candidate if after_commit else seed)
    if after_commit:
        with pytest.raises(AuthorityConflict):
            await rig.store.prepare(seed, candidate)
        assert (await rig.store.read()).incarnation == 1


async def test_cancel_after_commit_propagates_and_exact_readback_resolves(rig):
    seed = await rig.store.read()
    candidate = next_candidate(seed)
    uncertain = AuthorityStore(
        uncertain_sessions(rig.maker, after_commit=True, cancellation=True)
    )
    with pytest.raises(asyncio.CancelledError):
        await uncertain.prepare(seed, candidate)
    assert await rig.store.read() == candidate


async def test_lost_ready_reply_does_not_create_another_incarnation(rig):
    seed = await rig.store.read()
    prepared = await rig.store.prepare(seed, next_candidate(seed))
    uncertain = AuthorityStore(uncertain_sessions(rig.maker, after_commit=True))
    with pytest.raises(AuthorityWriteUncertain):
        await uncertain.ready(prepared)
    assert await rig.store.read() == replace(prepared, state="ready")
    with pytest.raises(AuthorityConflict):
        await rig.store.ready(prepared)


async def test_missing_row_never_bootstraps(rig):
    seed = await rig.store.read()
    async with rig.engine.begin() as conn:
        await conn.execute(text("DELETE FROM dnpl_authority"))
    with pytest.raises(AuthorityLost):
        await rig.store.read()
    with pytest.raises(AuthorityConflict):
        await rig.store.prepare(seed, next_candidate(seed))
    async with rig.engine.connect() as conn:
        assert await conn.scalar(text("SELECT count(*) FROM dnpl_authority")) == 0


async def test_exhaustion_refuses_without_wrap_or_write(rig):
    seed = await rig.store.read()
    current = await rig.store.prepare(seed, next_candidate(seed))
    async with rig.engine.begin() as conn:
        await conn.execute(
            text("UPDATE dnpl_authority SET incarnation = :n"), {"n": MAX_INCARNATION}
        )
    maximum = await rig.store.read()
    with pytest.raises(ValueError, match="exhausted"):
        next_candidate(maximum)
    assert await rig.store.read() == maximum
    assert maximum.namespace == current.namespace


async def test_control_lock_timeout_does_not_later_allocate(rig):
    seed = await rig.store.read()
    candidate = next_candidate(seed)
    async with rig.maker() as holder:
        async with holder.begin():
            await holder.execute(text("SELECT id FROM dnpl_authority FOR UPDATE"))
            with pytest.raises(AuthorityWriteUncertain):
                await rig.store.prepare(seed, candidate)
            assert await rig.store.read() == seed
    assert await rig.store.read() == seed


async def test_downgrade_never_erases_allocated_identity(rig):
    seed = await rig.store.read()
    prepared = await rig.store.prepare(seed, next_candidate(seed))
    with pytest.raises(RuntimeError, match="history must be retained"):
        rig.migration["downgrade"]()
    assert await rig.store.read() == prepared


async def test_candidate_cannot_jump_or_reuse_namespace(rig):
    seed = await rig.store.read()
    candidate = next_candidate(seed)
    with pytest.raises(ValueError):
        await rig.store.prepare(seed, replace(candidate, incarnation=5))
    assert await rig.store.read() == seed
    current = await rig.store.prepare(seed, candidate)
    with pytest.raises(ValueError, match="fresh"):
        preparing_candidate(
            current,
            namespace=current.namespace,
            operation_id=uuid4(),
            redis_run_id="a" * 40,
            redis_master_replid="b" * 40,
            policy_fingerprint=current.policy_fingerprint,
        )
