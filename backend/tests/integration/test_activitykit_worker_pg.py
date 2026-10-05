"""Durable ActivityKit reservation/restart/race gates in disposable PostgreSQL."""

import asyncio
from datetime import timedelta
import os
from uuid import uuid4
import pytest
from sqlalchemy import insert, select, text, update
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from app.models.activitykit import ActivityKitRegistration
from app.models.activitykit_delivery import ActivityKitDelivery
from app.services.activitykit_apns import APNsResult
from app.services.activitykit_worker import DurableActivityKitWorker, decode_state
from tests.test_activitykit_delivery_state import NOW, POLICY, snapshot

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not DB_URL,
    reason="Disposable PostgreSQL URL required; no local concurrency acceptance",
)
REG = ActivityKitRegistration.__table__
DEL = ActivityKitDelivery.__table__


@pytest.fixture
async def pg():
    url = make_url(DB_URL)
    assert url.get_backend_name() == "postgresql" and url.database == "bl_searchtest"
    schema = "activitykit_worker_" + uuid4().hex
    admin = create_async_engine(url)
    async with admin.begin() as conn:
        await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_async_engine(
        url, connect_args={"server_settings": {"search_path": schema}}
    )
    async with engine.begin() as conn:
        await conn.execute(text("CREATE TABLE users(id INTEGER PRIMARY KEY)"))
        await conn.execute(text("CREATE TABLE events(id INTEGER PRIMARY KEY)"))
        await conn.execute(text("INSERT INTO users VALUES (1)"))
        await conn.execute(text("INSERT INTO events VALUES (42)"))
        await conn.run_sync(REG.create)
        await conn.run_sync(DEL.create)
        await conn.execute(
            insert(REG).values(
                activity_id="a",
                user_id=1,
                event_id=42,
                version=1,
                is_active=True,
                push_token="ab" * 32,
                token_hash="a" * 64,
                mutation_id=str(uuid4()),
                request_hash="b" * 64,
            )
        )
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    yield sessions
    await engine.dispose()
    async with admin.begin() as conn:
        await conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
    await admin.dispose()


def worker(pg):
    return DurableActivityKitWorker(pg, retry_policy=POLICY, clock=lambda: NOW)


class MockTransport:
    def __init__(self, result=None):
        self.calls = []
        self.result = result or APNsResult("accepted", "apns_accepted")

    async def send(self, command, **credentials):
        self.calls.append((command, credentials))
        return self.result


async def seed(pg):
    w = worker(pg)
    assert await w.observe("a", snapshot(), revision=1)
    return w


async def record(pg):
    async with pg() as db:
        return (await db.execute(select(DEL))).mappings().one()


async def mutate(pg, **values):
    async with pg() as db, db.begin():
        await db.execute(update(REG).where(REG.c.activity_id == "a").values(**values))


async def test_two_workers_reserve_only_one_committed_attempt(pg):
    await seed(pg)
    first, second = await asyncio.wait_for(
        asyncio.gather(
            worker(pg).reserve("a", now=NOW), worker(pg).reserve("a", now=NOW)
        ),
        timeout=10,
    )
    assert sum(x is not None for x in [first, second]) == 1


async def test_restart_lease_recovery_preserves_payload_and_fences_old_ack(pg):
    w = await seed(pg)
    first = await w.reserve("a", now=NOW)
    before = decode_state((await record(pg))["state"]).attempt.command
    second = await worker(pg).reserve("a", now=NOW + timedelta(seconds=60))
    assert second.lease_id != first.lease_id
    transport = MockTransport()
    assert (
        await worker(pg).send(
            first, transport, provider_token="mock", now=NOW + timedelta(seconds=60)
        )
        == "fenced"
    )
    assert not transport.calls
    assert (
        await worker(pg).send(
            second, transport, provider_token="mock", now=NOW + timedelta(seconds=60)
        )
        == "accepted"
    )
    assert transport.calls[0][0] == before


async def test_replacement_fences_old_token_before_dispatch(pg):
    w = await seed(pg)
    old = await w.reserve("a", now=NOW)
    await mutate(pg, version=2, push_token="cd" * 32, token_hash="c" * 64)
    transport = MockTransport()
    assert await w.send(old, transport, provider_token="mock", now=NOW) == "fenced"
    new = await worker(pg).reserve("a", now=NOW + timedelta(seconds=1))
    assert (
        await w.send(
            new, transport, provider_token="mock", now=NOW + timedelta(seconds=1)
        )
        == "accepted"
    )
    assert transport.calls[0][1]["activity_token"] == "cd" * 32


async def test_revoke_before_send_prevents_any_transport_call(pg):
    w = await seed(pg)
    reserved = await w.reserve("a", now=NOW)
    await mutate(pg, version=2, is_active=False, push_token=None, token_hash=None)
    transport = MockTransport()
    assert await w.send(reserved, transport, provider_token="mock", now=NOW) == "fenced"
    assert not transport.calls
    assert await w.reserve("a", now=NOW + timedelta(seconds=60)) is None


async def test_final_before_dispatch_fences_update_then_delivers_end(pg):
    w = await seed(pg)
    reserved = await w.reserve("a", now=NOW)
    await w.observe(
        "a",
        snapshot(
            lifecycle="final", home_rendered_percent=None, probability_observed_at=None
        ),
        revision=2,
    )
    transport = MockTransport()
    assert await w.send(reserved, transport, provider_token="mock", now=NOW) == "fenced"
    ended = await w.reserve("a", now=NOW + timedelta(seconds=1))
    assert (
        await w.send(
            ended, transport, provider_token="mock", now=NOW + timedelta(seconds=1)
        )
        == "accepted"
    )
    assert transport.calls[0][0].kind == "terminal"
    assert decode_state((await record(pg))["state"]).ended


async def test_send_lock_serializes_concurrent_revoke_and_duplicate_send(pg):
    w = await seed(pg)
    reserved = await w.reserve("a", now=NOW)
    entered = asyncio.Event()
    release = asyncio.Event()

    class Blocking(MockTransport):
        async def send(self, *args, **kwargs):
            entered.set()
            await release.wait()
            return await super().send(*args, **kwargs)

    transport = Blocking()
    sending = asyncio.create_task(
        w.send(reserved, transport, provider_token="mock", now=NOW)
    )
    await asyncio.wait_for(entered.wait(), timeout=10)
    revoking = asyncio.create_task(
        mutate(pg, version=2, is_active=False, push_token=None, token_hash=None)
    )
    duplicate = asyncio.create_task(
        worker(pg).send(reserved, transport, provider_token="mock", now=NOW)
    )
    await asyncio.sleep(0.05)
    assert not revoking.done() and not duplicate.done()
    release.set()
    results = await asyncio.wait_for(
        asyncio.gather(sending, revoking, duplicate), timeout=10
    )
    assert results[0] == "accepted" and results[2] == "fenced"
    assert len(transport.calls) == 1


async def test_retry_after_and_finite_budget_survive_worker_restart(pg):
    w = await seed(pg)
    reserved = await w.reserve("a", now=NOW)
    transport = MockTransport(
        APNsResult("retry", "rate_limited", retry_after_seconds=90)
    )
    assert await w.send(reserved, transport, provider_token="mock", now=NOW) == "retry"
    assert await worker(pg).reserve("a", now=NOW + timedelta(seconds=60)) is None
    retry = await worker(pg).reserve("a", now=NOW + timedelta(seconds=90))
    assert retry.attempt_id.endswith("attempt:2")
