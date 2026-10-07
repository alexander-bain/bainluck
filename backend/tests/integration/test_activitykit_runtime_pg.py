"""Actual PostgreSQL overlap/commit/restart gates; transport remains mocked."""

import asyncio
import os
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import text

from app.models.models import DurableStateSnapshot
from app.services import activitykit_runtime_caller as caller
from app.services.activitykit_runtime import RuntimePolicy, RuntimeResult
from app.services.durable_snapshots import read_snapshot

pytestmark = pytest.mark.skipif(
    not os.environ.get("SEARCH_TEST_DATABASE_URL"),
    reason="Disposable PostgreSQL required",
)


@pytest.fixture
async def pg():
    from tests.integration.test_activitykit_worker_pg import pg as original

    async for sessions in original.__wrapped__():
        async with sessions.kw["bind"].begin() as conn:
            await conn.run_sync(DurableStateSnapshot.__table__.create)
        yield sessions


async def run(pg):
    return await caller.run_serialized_page(
        pg.kw["bind"], pg, None, None, None, None, policy=RuntimePolicy(enabled=True)
    )


async def cursor(pg):
    async with pg() as db:
        return await read_snapshot(db, caller.IDENTITY, expected_version=caller.SCHEMA)


async def test_two_overlapping_callers_only_dispatch_one_page(pg, monkeypatch):
    started, release = asyncio.Event(), asyncio.Event()

    async def page(*args, **kwargs):
        started.set()
        await release.wait()
        return RuntimeResult("partial_failure", "b", failed=1)

    dispatch = AsyncMock(side_effect=page)
    monkeypatch.setattr(caller, "run_activitykit_page", dispatch)
    first = asyncio.create_task(run(pg))
    try:
        await asyncio.wait_for(started.wait(), 3)
        second = await asyncio.wait_for(run(pg), 3)
        assert second == {"status": "busy", "terminal": "skipped"}
        assert (await cursor(pg)).status == "missing"
    finally:
        release.set()
        result = await asyncio.wait_for(first, 5)
    assert result["checkpoint_committed"] and result["terminal"] == "partial"
    assert dispatch.await_count == 1
    assert (await cursor(pg)).envelope.payload["after"] == "b"


async def test_new_connection_resumes_partial_cursor_and_complete_wraps(
    pg, monkeypatch
):
    page = AsyncMock(return_value=RuntimeResult("time_budget_exhausted", "c", failed=1))
    monkeypatch.setattr(caller, "run_activitykit_page", page)
    assert (await run(pg))["checkpoint_committed"]
    await pg.kw["bind"].dispose()
    page.return_value = RuntimeResult("complete", "")
    assert (await run(pg))["terminal"] == "complete"
    assert page.call_args.kwargs["after"] == "c"
    saved = (await cursor(pg)).envelope
    assert saved.payload["after"] == "" and saved.generation == 2


async def test_cancelled_call_releases_lock_without_banking_cursor(pg, monkeypatch):
    started = asyncio.Event()

    async def page(*args, **kwargs):
        started.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(caller, "run_activitykit_page", page)
    pending = asyncio.create_task(run(pg))
    await asyncio.wait_for(started.wait(), 3)
    pending.cancel()
    with pytest.raises(asyncio.CancelledError):
        await pending
    assert (await cursor(pg)).status == "missing"
    monkeypatch.setattr(
        caller,
        "run_activitykit_page",
        AsyncMock(return_value=RuntimeResult("complete", "")),
    )
    assert (await asyncio.wait_for(run(pg), 3))["checkpoint_committed"]


async def test_checkpoint_write_failure_rolls_back_and_releases_lock(pg, monkeypatch):
    page = AsyncMock(return_value=RuntimeResult("complete", "later", accepted=1))
    monkeypatch.setattr(caller, "run_activitykit_page", page)
    original = caller.publish_snapshot_in_txn

    async def fail(conn, envelope):
        await original(conn, envelope)
        raise RuntimeError("injected failure after write before commit")

    monkeypatch.setattr(caller, "publish_snapshot_in_txn", fail)
    result = await run(pg)
    assert result["terminal"] == "failed" and result["accepted"] == 1
    assert not result["checkpoint_committed"]
    assert (await cursor(pg)).status == "missing"
    monkeypatch.setattr(caller, "publish_snapshot_in_txn", original)
    assert (await run(pg))["checkpoint_committed"]
    assert page.call_args.kwargs["after"] == ""


async def test_corrupt_cursor_prevents_dispatch(pg, monkeypatch):
    page = AsyncMock(return_value=RuntimeResult("complete", "later"))
    monkeypatch.setattr(caller, "run_activitykit_page", page)
    await run(pg)
    async with pg.kw["bind"].begin() as conn:
        await conn.execute(
            text("UPDATE durable_state_snapshots SET checksum='corrupt'")
        )
    page.reset_mock()
    assert (await run(pg))["status"] == "checkpoint_read_failed"
    page.assert_not_called()
