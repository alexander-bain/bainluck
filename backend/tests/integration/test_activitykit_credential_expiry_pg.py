"""#10564 real PostgreSQL erasure/race gates; no real transport or scheduler."""

import asyncio
from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4
import pytest
from sqlalchemy import insert, select, update
from app.routes import activitykit
from app.services.activitykit_apns import APNsResult
from app.services.activitykit_registration_lifecycle import (
    cleanup_expired,
    AUTHORIZATION_LIFETIME,
)
from app.services.activitykit_worker import decode_state
from tests.test_activitykit_delivery_state import NOW, snapshot
from tests.integration.test_activitykit_registration_pg import body, invoke
from tests.integration.test_activitykit_worker_pg import (
    seed,
    record,
    mutate,
    MockTransport,
    REG,
    DEL,
    DB_URL,
)

pytestmark = pytest.mark.skipif(
    not DB_URL, reason="Disposable PostgreSQL required; local skip unpaid"
)


@pytest.fixture
async def pg():
    from tests.integration.test_activitykit_worker_pg import pg as original

    async for sessions in original.__wrapped__():
        yield sessions


async def registration(pg):
    async with pg() as db:
        return (
            (await db.execute(select(REG).where(REG.c.activity_id == "a")))
            .mappings()
            .one()
        )


async def assert_erased(pg):
    reg = await registration(pg)
    assert (
        not reg["is_active"] and reg["push_token"] is None and reg["token_hash"] is None
    )
    state = decode_state((await record(pg))["state"])
    assert state.stopped and state.attempt is None and state.pending is None
    row = await record(pg)
    assert row["lease_id"] is None and row["lease_expires_at"] is None
    return state


async def test_observe_expiry_preserves_original_reading_and_identity(pg):
    w = await seed(pg)
    before = decode_state((await record(pg))["state"])
    w.clock = lambda: NOW + AUTHORIZATION_LIFETIME
    assert not await w.observe("a", snapshot(home_score=8), revision=2)
    after = await assert_erased(pg)
    assert after.snapshot == before.snapshot
    assert after.score_fence == before.score_fence
    assert (after.activity_id, after.event_id) == ("a", 42)


async def test_expired_latest_put_replay_conflicts_and_same_owner_get_delete_ack(
    pg, monkeypatch
):
    monkeypatch.setattr(activitykit, "utc_now", lambda: NOW)
    value = body()
    assert (await invoke(pg, value, identity="new"))[0] == 200
    monkeypatch.setattr(activitykit, "utc_now", lambda: NOW + AUTHORIZATION_LIFETIME)
    assert (await invoke(pg, value, identity="new"))[0] == 409
    async with pg() as db:
        ack = await activitykit.get_registration("new", SimpleNamespace(id=1), db)
    assert not ack["is_active"] and ack["version"] == 2
    status, deleted = await invoke(pg, body(0), identity="new", revoke=True)
    assert status == 200 and deleted == ack
    assert (await invoke(pg, body(2), identity="new"))[0] == 409
    # A zero-version attempt cannot claim an existing immutable identity;
    # a known-version owner lookup remains concealed. Neither cleans account A.
    assert (await invoke(pg, body(0), identity="new", user=2, revoke=True))[0] == 409
    assert (await invoke(pg, body(2), identity="new", user=2, revoke=True))[0] == 404
    async with pg() as db:
        retained = (
            (await db.execute(select(REG).where(REG.c.activity_id == "new")))
            .mappings()
            .one()
        )
    assert (
        retained["user_id"] == 1
        and retained["version"] == 2
        and not retained["is_active"]
    )


async def test_rotation_and_replay_preserve_original_horizon(pg, monkeypatch):
    monkeypatch.setattr(activitykit, "utc_now", lambda: NOW)
    first = body()
    assert (await invoke(pg, first, identity="new"))[0] == 200
    async with pg() as db:
        initial = (
            (await db.execute(select(REG).where(REG.c.activity_id == "new")))
            .mappings()
            .one()
        )
    monkeypatch.setattr(activitykit, "utc_now", lambda: NOW + timedelta(hours=7))
    assert (await invoke(pg, first, identity="new"))[0] == 200
    assert (await invoke(pg, body(1, "cd" * 32), identity="new"))[0] == 200
    async with pg() as db:
        later = (
            (await db.execute(select(REG).where(REG.c.activity_id == "new")))
            .mappings()
            .one()
        )
    assert (initial["created_at"], initial["expires_at"]) == (
        later["created_at"],
        later["expires_at"],
    )


async def test_reserve_samples_expiry_after_waiting_on_registration_lock(pg):
    w = await seed(pg)
    await mutate(pg, expires_at=NOW + timedelta(seconds=1))
    now = [NOW]
    w.clock = lambda: now[0]
    async with pg() as held, held.begin():
        await held.execute(
            select(REG).where(REG.c.activity_id == "a").with_for_update()
        )
        pending = asyncio.create_task(w.reserve("a", now=NOW))
        await asyncio.sleep(0.05)
        assert not pending.done()
        now[0] = NOW + timedelta(seconds=2)
    assert await asyncio.wait_for(pending, timeout=5) is None
    await assert_erased(pg)


async def test_expiry_fences_reserved_send_and_stale_replay(pg):
    w = await seed(pg)
    reserved = await w.reserve("a", now=NOW)
    w.clock = lambda: NOW + AUTHORIZATION_LIFETIME
    transport = MockTransport()
    assert await w.send(reserved, transport, provider_token="mock", now=NOW) == "fenced"
    assert await w.send(reserved, transport, provider_token="mock", now=NOW) == "fenced"
    assert not transport.calls
    await assert_erased(pg)
    assert (await registration(pg))["version"] == 2


async def test_transport_deadline_uses_remaining_authorization(pg, monkeypatch):
    from app.services import activitykit_worker as worker_module

    w = await seed(pg)
    reserved = await w.reserve("a", now=NOW)
    await mutate(pg, expires_at=NOW + timedelta(seconds=10))
    now = [NOW + timedelta(seconds=7)]
    w.clock = lambda: now[0]
    entered = asyncio.Event()
    original_timeout = asyncio.timeout
    deadlines = []

    def timeout(delay):
        deadlines.append(delay)
        # Controlled cancellation independently verifies the timeout path without
        # making database/runner scheduling fit a wall-clock80ms budget.
        return original_timeout(0.01)

    monkeypatch.setattr(worker_module.asyncio, "timeout", timeout)

    class Waiting(MockTransport):
        async def send(self, *args, **kwargs):
            entered.set()
            now[0] = NOW + timedelta(seconds=10)
            await asyncio.Event().wait()
            raise AssertionError("Transport exceeded credential horizon")

    assert (
        await asyncio.wait_for(
            w.send(reserved, Waiting(), provider_token="mock", now=NOW), timeout=5
        )
        == "retry"
    )
    assert deadlines == [3.0] and entered.is_set()
    await assert_erased(pg)


@pytest.mark.parametrize("kind", ["final", "stop"])
async def test_accepted_terminal_or_stop_erases_credentials_without_resetting_end(
    pg, kind
):
    w = await seed(pg)
    reading = (
        snapshot(
            lifecycle="final", home_rendered_percent=None, probability_observed_at=None
        )
        if kind == "final"
        else snapshot()
    )
    assert await w.observe("a", reading, revision=2, stop=kind == "stop")
    reserved = await w.reserve("a", now=NOW)
    assert (
        await w.send(reserved, MockTransport(), provider_token="mock", now=NOW)
        == "accepted"
    )
    after = await assert_erased(pg)
    assert after.ended and after.terminal_latched == (kind == "final")
    assert after.snapshot == reading


async def test_exact_unregistered_result_erases_and_blocks_true_token_generation_recovery(
    pg,
):
    w = await seed(pg)
    reserved = await w.reserve("a", now=NOW)
    transport = MockTransport(APNsResult("unavailable", "token_unregistered"))
    assert (
        await w.send(reserved, transport, provider_token="mock", now=NOW)
        == "unavailable"
    )
    await assert_erased(pg)
    assert (await invoke(pg, body(2, "cd" * 32), identity="a"))[0] == 409


@pytest.mark.parametrize(
    "result",
    [
        APNsResult("retry", "transport_failure"),
        APNsResult("rejected", "invalid_credentials"),
    ],
)
async def test_transient_or_config_error_retains_only_original_finite_horizon(
    pg, result
):
    w = await seed(pg)
    before = await registration(pg)
    reserved = await w.reserve("a", now=NOW)
    assert (
        await w.send(reserved, MockTransport(result), provider_token="mock", now=NOW)
        == result.outcome
    )
    after = await registration(pg)
    assert after["is_active"] and after["push_token"] == before["push_token"]
    assert after["expires_at"] == before["expires_at"]
    assert await cleanup_expired(pg, clock=lambda: NOW + AUTHORIZATION_LIFETIME) == 1
    await assert_erased(pg)


async def test_owner_revoke_atomically_erases_credentials_and_lease(pg, monkeypatch):
    w = await seed(pg)
    await w.reserve("a", now=NOW)
    monkeypatch.setattr(activitykit, "utc_now", lambda: NOW)
    status, ack = await invoke(pg, body(1), identity="a", revoke=True)
    assert status == 200 and not ack["is_active"]
    await assert_erased(pg)


async def test_cleanup_skips_locked_candidates_and_obeys_batch_bound(pg):
    await seed(pg)
    async with pg() as db, db.begin():
        await db.execute(
            insert(REG).values(
                activity_id="b",
                user_id=1,
                event_id=42,
                version=1,
                is_active=True,
                push_token="cd" * 32,
                token_hash="b" * 64,
                mutation_id=str(uuid4()),
                request_hash="b" * 64,
                created_at=NOW,
                expires_at=NOW + AUTHORIZATION_LIFETIME,
            )
        )
    async with pg() as held, held.begin():
        await held.execute(
            select(REG).where(REG.c.activity_id == "a").with_for_update()
        )
        assert (
            await asyncio.wait_for(
                cleanup_expired(
                    pg, batch_size=1, clock=lambda: NOW + AUTHORIZATION_LIFETIME
                ),
                timeout=5,
            )
            == 1
        )
        assert (await registration(pg))["is_active"]
    assert (
        await cleanup_expired(
            pg, batch_size=1, clock=lambda: NOW + AUTHORIZATION_LIFETIME
        )
        == 1
    )
    await assert_erased(pg)
    assert await cleanup_expired(pg, clock=lambda: NOW + AUTHORIZATION_LIFETIME) == 0
    assert (await registration(pg))["version"] == 2


async def test_cleanup_null_legacy_inactive_secrets_and_malformed_state(pg):
    await seed(pg)
    await mutate(pg, is_active=False, created_at=None, expires_at=None)
    async with pg() as db, db.begin():
        await db.execute(
            update(DEL).values(
                state={"broken": "state"},
                lease_id="lease",
                lease_expires_at=NOW + timedelta(seconds=60),
            )
        )
    assert await cleanup_expired(pg, clock=lambda: NOW) == 1
    after = await assert_erased(pg)
    assert (after.activity_id, after.event_id) == ("a", 42)
    assert await cleanup_expired(pg, clock=lambda: NOW) == 0


@pytest.mark.parametrize("size", [0, 1001, True])
async def test_cleanup_rejects_unbounded_or_noninteger_batch(pg, size):
    with pytest.raises(ValueError, match="batch"):
        await cleanup_expired(pg, batch_size=size)
