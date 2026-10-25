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
    retirement_migration = runpy.run_path(
        str(Path(__file__).parents[2] / "alembic/versions/dnpl_retirement_10090.py")
    )

    def upgrade(conn):
        with Operations.context(MigrationContext.configure(conn)):
            migration["upgrade"]()
            retirement_migration["upgrade"]()

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


async def test_producer_sample_uses_current_primary_clock_and_exact_ready_record(rig):
    prepared = await rig.store.prepare(
        await rig.store.read(), next_candidate(await rig.store.read())
    )
    ready = await rig.store.ready(prepared)
    async with rig.maker() as session:
        before = await session.scalar(text("SELECT clock_timestamp()"))
    actual, sampled_at = await rig.store.read_for_producer()
    async with rig.maker() as session:
        after = await session.scalar(text("SELECT clock_timestamp()"))
    assert actual == ready
    assert before <= sampled_at <= after
    assert sampled_at.tzinfo is not None


async def test_producer_sample_does_not_bootstrap_missing_control(rig):
    async with rig.engine.begin() as conn:
        await conn.execute(text("DELETE FROM dnpl_authority"))
    from app.services.dnpl_authority import AuthorityLost

    with pytest.raises(AuthorityLost):
        await rig.store.read_for_producer()
    async with rig.maker() as session:
        assert await session.scalar(text("SELECT count(*) FROM dnpl_authority")) == 0


async def test_one_retirement_blocks_third_allocation_until_exact_ack(rig):
    seed = await rig.store.read()
    first = await rig.store.prepare(seed, next_candidate(seed))
    assert await rig.store.read_retirement() is None
    first = await rig.store.ready(first)
    second = await rig.store.prepare(first, next_candidate(first))
    assert await rig.store.read_retirement() == first
    candidate = next_candidate(second)
    with pytest.raises(AuthorityConflict, match="cleanup outstanding"):
        await rig.store.prepare(second, candidate)
    assert await rig.store.read() == second  # whole CAS rolled back
    assert await rig.store.read_retirement() == first
    # This PG control supplies the controller's cleanup acknowledgement.
    # Actual Redis absence/initialization fencing is a separate controller gate.
    await rig.store.complete_retirement(second, first)
    assert await rig.store.read_retirement() is None
    third = await rig.store.prepare(second, candidate)
    assert third.incarnation == 3
    assert await rig.store.read_retirement() == second


@pytest.mark.parametrize("after_commit", [False, True])
async def test_lost_prepare_ack_never_forgets_predecessor(rig, after_commit):
    seed = await rig.store.read()
    first = await rig.store.prepare(seed, next_candidate(seed))
    second = next_candidate(first)
    uncertain = AuthorityStore(uncertain_sessions(rig.maker, after_commit=after_commit))
    with pytest.raises(AuthorityWriteUncertain):
        await uncertain.prepare(first, second)
    assert await rig.store.read() == (second if after_commit else first)
    assert await rig.store.read_retirement() == (first if after_commit else None)


@pytest.mark.parametrize("after_commit", [False, True])
async def test_cleanup_ack_ambiguity_is_resolved_by_read_not_replayed(
    rig, after_commit
):
    seed = await rig.store.read()
    first = await rig.store.prepare(seed, next_candidate(seed))
    second = await rig.store.prepare(first, next_candidate(first))
    uncertain = AuthorityStore(uncertain_sessions(rig.maker, after_commit=after_commit))
    with pytest.raises(AuthorityWriteUncertain):
        await uncertain.complete_retirement(second, first)
    assert await rig.store.read() == second
    assert await rig.store.read_retirement() == (None if after_commit else first)


async def test_cleanup_cannot_clear_wrong_record_or_changed_current(rig):
    seed = await rig.store.read()
    first = await rig.store.prepare(seed, next_candidate(seed))
    second = await rig.store.prepare(first, next_candidate(first))
    with pytest.raises(AuthorityConflict):
        await rig.store.complete_retirement(
            second, replace(first, operation_id=uuid4())
        )
    ready = await rig.store.ready(second)
    with pytest.raises(AuthorityConflict):
        await rig.store.complete_retirement(second, first)
    assert await rig.store.read_retirement() == first
    await rig.store.complete_retirement(ready, first)
    assert await rig.store.read_retirement() is None
    with pytest.raises(AuthorityConflict):
        await rig.store.complete_retirement(ready, first)


async def test_activation_steps_are_ordered_and_cannot_repeat(rig):
    seed = await rig.store.read()
    current = await rig.store.prepare(seed, next_candidate(seed))
    assert await rig.store.activation_step(current) == 0
    with pytest.raises(AuthorityConflict):
        await rig.store.take_activation_step(current, 2)
    assert await rig.store.activation_step(current) == 0
    await rig.store.take_activation_step(current, 1)
    with pytest.raises(AuthorityConflict):
        await rig.store.take_activation_step(current, 1)
    await rig.store.take_activation_step(current, 2)
    with pytest.raises(AuthorityConflict):
        await rig.store.take_activation_step(current, 2)
    assert await rig.store.activation_step(current) == 2
    ready = await rig.store.ready(current)
    assert await rig.store.activation_step(ready) == 2
    with pytest.raises(AuthorityConflict):
        await rig.store.activation_step(current)
    with pytest.raises(ValueError):
        await rig.store.take_activation_step(ready, 1)
    # A new allocation resets only current bookkeeping. Recording the old
    # authority uses the real retirement schema (no inherited required step).
    successor = await rig.store.prepare(ready, next_candidate(ready))
    assert await rig.store.activation_step(successor) == 0
    assert await rig.store.read_retirement() == ready
    with pytest.raises(AuthorityConflict):
        await rig.store.take_activation_step(current, 1)


async def test_concurrent_activation_sends_have_one_permission(rig):
    seed = await rig.store.read()
    current = await rig.store.prepare(seed, next_candidate(seed))
    results = await asyncio.gather(
        rig.store.take_activation_step(current, 1),
        rig.store.take_activation_step(current, 1),
        return_exceptions=True,
    )
    assert sum(r is True for r in results) == 1
    assert sum(isinstance(r, AuthorityConflict) for r in results) == 1
    assert await rig.store.activation_step(current) == 1


@pytest.mark.parametrize("step", [1, 2])
@pytest.mark.parametrize("after_commit", [False, True])
@pytest.mark.parametrize("cancellation", [False, True])
async def test_lost_activation_step_ack_never_grants_send(
    rig, step, after_commit, cancellation
):
    seed = await rig.store.read()
    current = await rig.store.prepare(seed, next_candidate(seed))
    if step == 2:
        await rig.store.take_activation_step(current, 1)
    uncertain = AuthorityStore(
        uncertain_sessions(
            rig.maker, after_commit=after_commit, cancellation=cancellation
        )
    )
    error = asyncio.CancelledError if cancellation else AuthorityWriteUncertain
    with pytest.raises(error):
        await uncertain.take_activation_step(current, step)
    assert await rig.store.activation_step(current) == (
        step if after_commit else step - 1
    )
    if after_commit:
        with pytest.raises(AuthorityConflict):
            await rig.store.take_activation_step(current, step)


async def test_activation_step_lock_timeout_does_not_grant_late_send(rig):
    seed = await rig.store.read()
    current = await rig.store.prepare(seed, next_candidate(seed))
    async with rig.maker() as holder:
        async with holder.begin():
            await holder.execute(text("SELECT id FROM dnpl_authority FOR UPDATE"))
            with pytest.raises(AuthorityWriteUncertain):
                await rig.store.take_activation_step(current, 1)
    assert await rig.store.activation_step(current) == 0


async def test_only_first_allocation_or_changed_primary_can_bootstrap_fence(rig):
    seed = await rig.store.read()
    first = await rig.store.prepare(seed, next_candidate(seed))
    assert await rig.store.take_activation_step(first, 1) is True
    second = await rig.store.prepare(first, next_candidate(first))
    assert await rig.store.take_activation_step(second, 1) is False
    await rig.store.complete_retirement(second, first)
    third = await rig.store.prepare(
        second, replace(next_candidate(second), redis_run_id="c" * 40)
    )
    assert await rig.store.take_activation_step(third, 1) is True
    await rig.store.complete_retirement(third, second)
    fourth = await rig.store.prepare(
        third, replace(next_candidate(third), redis_master_replid="d" * 40)
    )
    assert await rig.store.take_activation_step(fourth, 1) is True
