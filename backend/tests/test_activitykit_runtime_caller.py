"""Serialization/checkpoint failures must never masquerade as delivery success."""

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services import activitykit_runtime_caller as caller
from app.services.activitykit_runtime import RuntimePolicy, RuntimeResult
from app.utils.durable_state import DurableEnvelope, EnvelopeRead


@pytest.fixture
def rig(monkeypatch):
    events = []
    state = SimpleNamespace(acquired=True, commit_error=False)
    conn = SimpleNamespace(
        execute=AsyncMock(
            side_effect=lambda *a, **k: SimpleNamespace(
                scalar_one=lambda: state.acquired
            )
        )
    )

    @asynccontextmanager
    async def begin():
        events.append("begin")
        try:
            yield conn
            if state.commit_error:
                raise RuntimeError("SECRET commit failure")
            events.append("commit")
        except BaseException:
            events.append("rollback")
            raise

    state.engine = SimpleNamespace(begin=begin)
    state.conn = conn
    state.read = AsyncMock(return_value=EnvelopeRead(status="missing", tier="durable"))
    state.write = AsyncMock(return_value={"status": "ok"})
    state.page = AsyncMock(return_value=RuntimeResult("complete", "next-private-id"))
    state.events = events
    monkeypatch.setattr(caller, "read_snapshot", state.read)
    monkeypatch.setattr(caller, "publish_snapshot_in_txn", state.write)
    monkeypatch.setattr(caller, "run_activitykit_page", state.page)

    async def run(enabled=True):
        return await caller.run_serialized_page(
            state.engine,
            None,
            None,
            None,
            None,
            None,
            policy=RuntimePolicy(enabled=enabled),
        )

    state.run = run
    return state


@pytest.mark.asyncio
async def test_disabled_and_overlapping_runs_never_read_cursor_or_deliver(rig):
    assert (await rig.run(False))["status"] == "disabled"
    assert rig.events == []
    rig.acquired = False
    assert (await rig.run())["status"] == "busy"
    rig.read.assert_not_called()
    rig.page.assert_not_called()
    rig.write.assert_not_called()
    sql = str(rig.conn.execute.call_args.args[0])
    assert "pg_try_advisory_xact_lock" in sql
    assert rig.conn.execute.call_args.args[1]["key"] == caller.advisory_lock_key(
        caller.TASK
    )


@pytest.mark.asyncio
async def test_first_page_banks_cursor_and_only_reports_committed_after_commit(rig):
    result = await rig.run()
    assert result["checkpoint_committed"] is True
    assert rig.events == ["begin", "commit"]
    assert rig.page.call_args.kwargs["after"] == ""
    conn, envelope = rig.write.call_args.args
    assert conn is rig.conn
    assert envelope.payload["after"] == "next-private-id"
    assert envelope.generation == 1
    assert "next-private-id" not in str(result)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status", ["partial_failure", "time_budget_exhausted", "complete"]
)
async def test_resumes_prior_cursor_and_banks_partial_progress(rig, status):
    envelope = DurableEnvelope.build(
        identity=caller.IDENTITY,
        schema_version=caller.SCHEMA,
        generation=9000000000000,
        payload={"after": "prior"},
    )
    rig.read.return_value = EnvelopeRead(status="ok", tier="durable", envelope=envelope)
    rig.page.return_value = RuntimeResult(
        status, "next", failed=int(status != "complete")
    )
    result = await rig.run()
    assert rig.page.call_args.kwargs["after"] == "prior"
    saved = rig.write.call_args.args[1]
    assert saved.generation == 9000000000001
    assert saved.payload == {"after": "next", "page_status": status}
    assert result["terminal"] == ("complete" if status == "complete" else "partial")


@pytest.mark.asyncio
async def test_completed_sweep_banks_empty_cursor(rig):
    rig.page.return_value = RuntimeResult("complete", "")
    await rig.run()
    assert rig.write.call_args.args[1].payload["after"] == ""


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["unavailable", "malformed", "wrong_version"])
async def test_unreadable_checkpoint_never_starts_from_zero(rig, status):
    rig.read.return_value = EnvelopeRead(status=status, tier="durable")
    result = await rig.run()
    assert result["status"] == "checkpoint_read_failed"
    rig.page.assert_not_called()
    rig.write.assert_not_called()
    assert rig.events[-1] == "rollback"


@pytest.mark.asyncio
@pytest.mark.parametrize("after", [None, [], "bad/id", "a" * 129])
async def test_invalid_cursor_fails_closed(rig, after):
    envelope = DurableEnvelope.build(
        identity=caller.IDENTITY, schema_version=caller.SCHEMA, payload={"after": after}
    )
    rig.read.return_value = EnvelopeRead(status="ok", tier="durable", envelope=envelope)
    assert (await rig.run())["terminal"] == "failed"
    rig.page.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["error", "superseded", "commit"])
async def test_missing_checkpoint_commit_is_failure_even_after_accepted_sends(
    rig, failure
):
    rig.page.return_value = RuntimeResult("complete", "next", accepted=2)
    rig.write.return_value = {"status": "ok" if failure == "commit" else failure}
    rig.commit_error = failure == "commit"
    result = await rig.run()
    assert result["accepted"] == 2
    assert result["terminal"] == "failed"
    assert result["checkpoint_committed"] is False
    assert rig.events[-1] == "rollback"
    assert "SECRET" not in str(result)


@pytest.mark.asyncio
async def test_cancellation_rolls_back_and_propagates(rig):
    rig.page.side_effect = asyncio.CancelledError()
    with pytest.raises(asyncio.CancelledError):
        await rig.run()
    rig.write.assert_not_called()
    assert rig.events[-1] == "rollback"
