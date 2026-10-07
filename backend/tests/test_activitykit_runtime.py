"""Own runtime gates; mocked transport is not APNs or physical acceptance."""

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import create_engine, text

from app.services import activitykit_runtime as runtime

NOW = datetime(2026, 10, 7, tzinfo=timezone.utc)


@pytest.fixture
def rig(monkeypatch):
    rows = [dict(activity_id="a", event_id=42), dict(activity_id="b", event_id=42)]
    active_connections = []

    @asynccontextmanager
    async def sessions():
        active_connections.append(True)
        try:
            yield SimpleNamespace(
                execute=AsyncMock(
                    return_value=SimpleNamespace(
                        mappings=lambda: SimpleNamespace(all=lambda: rows)
                    )
                )
            )
        finally:
            active_connections.pop()

    snapshot = object()

    async def capture(event_id):
        assert not active_connections
        return SimpleNamespace(snapshot=snapshot, sequence=7)

    cleanup = AsyncMock(return_value=3)
    monkeypatch.setattr(runtime, "cleanup_expired", cleanup)
    adapter = SimpleNamespace(capture=AsyncMock(side_effect=capture))
    worker = SimpleNamespace(
        observe=AsyncMock(return_value=True),
        reserve=AsyncMock(return_value="reservation"),
        send=AsyncMock(return_value="accepted"),
    )
    token = AsyncMock(return_value="header.payload.signature")

    async def run(**kwargs):
        return await runtime.run_activitykit_page(
            sessions, adapter, worker, object(), token, clock=lambda: NOW, **kwargs
        )

    return SimpleNamespace(
        rows=rows,
        cleanup=cleanup,
        adapter=adapter,
        worker=worker,
        token=token,
        snapshot=snapshot,
        run=run,
    )


@pytest.mark.asyncio
async def test_default_disabled_touches_no_database_credentials_or_transport(rig):
    result = await rig.run(after="previous")
    assert (result.status, result.next_cursor) == ("disabled", "previous")
    for call in (rig.cleanup, rig.token, rig.adapter.capture, rig.worker.send):
        call.assert_not_called()


@pytest.mark.asyncio
async def test_one_canonical_snapshot_is_shared_without_retiming_and_connection_closed(
    rig,
):
    result = await rig.run(policy=runtime.RuntimePolicy(enabled=True))
    assert (result.scanned, result.observed, result.accepted, result.cleaned) == (
        2,
        2,
        2,
        3,
    )
    assert result.next_cursor == ""
    rig.adapter.capture.assert_awaited_once_with(42)
    for call in rig.worker.observe.await_args_list:
        assert call.args[1] is rig.snapshot
        assert call.kwargs == {"revision": 7}


@pytest.mark.asyncio
async def test_page_limit_has_continuation_and_does_not_touch_extra_row(rig):
    result = await rig.run(policy=runtime.RuntimePolicy(enabled=True, batch_size=1))
    assert (result.scanned, result.next_cursor) == (1, "a")
    rig.worker.observe.assert_awaited_once_with("a", rig.snapshot, revision=7)


@pytest.mark.asyncio
async def test_bad_game_read_is_attempted_once_and_healthy_game_still_sent(rig):
    rig.rows.append(dict(activity_id="c", event_id=43))
    rig.adapter.capture.side_effect = [
        RuntimeError("SECRET DATABASE BODY"),
        SimpleNamespace(snapshot=rig.snapshot, sequence=8),
    ]
    result = await rig.run(policy=runtime.RuntimePolicy(enabled=True))
    assert (result.failed, result.accepted) == (2, 1)
    assert result.status == "partial_failure"
    assert rig.adapter.capture.await_count == 2
    assert "SECRET" not in repr(result)


@pytest.mark.asyncio
async def test_revoked_registration_cannot_reach_reservation_or_send(rig):
    rig.worker.observe.return_value = False
    result = await rig.run(policy=runtime.RuntimePolicy(enabled=True))
    assert (result.fenced, result.accepted) == (2, 0)
    rig.worker.reserve.assert_not_called()
    rig.worker.send.assert_not_called()


@pytest.mark.asyncio
async def test_worker_backoff_is_preserved_without_new_reservation_or_inline_retry(rig):
    rig.worker.reserve.return_value = None
    result = await rig.run(policy=runtime.RuntimePolicy(enabled=True))
    assert result.observed == 2 and result.accepted == 0
    rig.worker.send.assert_not_called()


@pytest.mark.asyncio
async def test_send_failure_does_not_abort_healthy_sibling_or_leak_credentials(rig):
    rig.worker.send.side_effect = [RuntimeError("SECRET URL"), "accepted"]
    result = await rig.run(policy=runtime.RuntimePolicy(enabled=True))
    assert (result.failed, result.accepted, result.scanned) == (1, 1, 2)
    assert "SECRET" not in repr(result)


@pytest.mark.asyncio
async def test_item_timeout_moves_past_poison_registration(rig):
    async def send(*args, **kwargs):
        if rig.worker.send.await_count == 1:
            await asyncio.Event().wait()
        return "accepted"

    rig.worker.send.side_effect = send
    result = await rig.run(
        policy=runtime.RuntimePolicy(enabled=True, item_seconds=0.01)
    )
    assert (result.failed, result.accepted, result.scanned) == (1, 1, 2)


@pytest.mark.asyncio
async def test_whole_budget_retains_cursor_for_unattempted_tail(rig):
    async def send(*args, **kwargs):
        await asyncio.Event().wait()

    rig.worker.send.side_effect = send
    result = await rig.run(policy=runtime.RuntimePolicy(enabled=True, run_seconds=0.01))
    assert result.status == "time_budget_exhausted"
    assert (result.next_cursor, result.scanned, result.failed) == ("a", 1, 1)


@pytest.mark.asyncio
async def test_external_cancellation_propagates(rig):
    rig.adapter.capture.side_effect = asyncio.CancelledError()
    with pytest.raises(asyncio.CancelledError):
        await rig.run(policy=runtime.RuntimePolicy(enabled=True))
    rig.worker.send.assert_not_called()


@pytest.mark.asyncio
async def test_bad_provider_configuration_does_not_reserve_or_capture(rig):
    rig.token.return_value = "SECRET-invalid"
    result = await rig.run(policy=runtime.RuntimePolicy(enabled=True), after="a")
    assert (result.status, result.next_cursor) == ("configuration_failed", "a")
    assert "SECRET" not in repr(result)
    rig.adapter.capture.assert_not_called()
    rig.worker.reserve.assert_not_called()


@pytest.mark.parametrize(
    "kwargs",
    [
        {"enabled": "true"},
        {"batch_size": 0},
        {"batch_size": 101},
        {"batch_size": True},
        {"cleanup_size": 1001},
        {"item_seconds": float("nan")},
        {"run_seconds": float("inf")},
        {"item_seconds": -1},
        {"run_seconds": 301},
    ],
)
def test_invalid_bounds_refused(kwargs):
    with pytest.raises(ValueError):
        runtime.RuntimePolicy(**kwargs)


def test_real_sql_keyset_order_limit_and_authorization_filter():
    engine = create_engine("sqlite://")
    with engine.begin() as db:
        db.execute(
            text(
                "CREATE TABLE activitykit_registrations (activity_id TEXT, event_id INTEGER, is_active BOOLEAN, push_token TEXT, token_hash TEXT, created_at DATETIME, expires_at DATETIME)"
            )
        )
        for identity, active, token, expiry in [
            ("d", True, "token", NOW + timedelta(hours=1)),
            ("b", True, "token", NOW + timedelta(hours=1)),
            ("c", True, "token", NOW + timedelta(hours=1)),
            ("a", True, "token", NOW + timedelta(hours=1)),
            ("expired", True, "token", NOW),
            ("revoked", False, "token", NOW + timedelta(hours=1)),
            ("no-token", True, None, NOW + timedelta(hours=1)),
        ]:
            db.execute(
                runtime.REG.insert().values(
                    activity_id=identity,
                    event_id=42,
                    is_active=active,
                    push_token=token,
                    token_hash="hash",
                    created_at=NOW - timedelta(hours=1),
                    expires_at=expiry,
                )
            )
        rows = db.execute(runtime._candidates("a", 1, NOW)).mappings().all()
        assert [dict(row) for row in rows] == [
            {"activity_id": "b", "event_id": 42},
            {"activity_id": "c", "event_id": 42},
        ]
        rows = db.execute(runtime._candidates("d", 10, NOW)).all()
        assert rows == []
    engine.dispose()
