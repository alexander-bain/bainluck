"""TRUTH: default DNPL keeps committed observations deliverable through ledger failure.

Real PostgreSQL intents and private Redis; no legacy registry or enrolled scope.
The bounded-stall case measures this fixture's committed publication, not DOM.
"""
import asyncio
import json
import time

import pytest
from redis.asyncio import Redis
from sqlalchemy import text

from app.tasks.live_blend_refresh import LiveBlendRefresher
from app.utils import blend_preview
from app.utils.live_push import event_channel
from tests.integration.test_live_blend_grouped_commit_8129_pg import DB_URL, rig  # noqa: F401
from tests.integration.test_pm_stamp_release_wake_10090_pg import consumer  # noqa: F401
from tests.integration.test_pm_price_statement_deadline_10090_pg import (
    prepared, close_rig, preview, private_redis_socket,  # noqa: F401
)
from tests.integration.test_live_normal_publication_recovery_10090_pg import owed, join, close

pytestmark = [pytest.mark.asyncio, pytest.mark.skipif(
    not DB_URL, reason="requires disposable SEARCH_TEST_DATABASE_URL",
)]


async def changed_row(t, rig):
    # A fresh accepted quote, then its ordinary price-row write; the target is
    # the ensuing event stamp's post-COMMIT delivery boundary.
    t.accept(1, .78)
    async with rig.engine.begin() as conn:
        await conn.execute(text("UPDATE futures_outcomes SET current_probability=.78, "
                                "last_updated=clock_timestamp() WHERE id=1"))


def assert_default(ref):
    assert isinstance(blend_preview.registry(), blend_preview.LedgerRegistry)
    assert isinstance(ref.preview_events, blend_preview.PreviewEventScope)
    assert 1 in ref.preview_events and 987654 in ref.preview_events


async def finish_warmup(t, rig):
    # Join an already-running ACK cleanup before stopping its owner. Cancelling
    # that cleanup after it swaps out _normal_acked correctly retains durable
    # warmup intents, but would contaminate the single new revision below.
    await join(t.r)
    await t.r._close_normal_recovery()
    await t.r._settle_normal_recovery(set(t.r._normal_acked.items()))
    assert not await owed(rig), "warmup publication must be acknowledged and settled"


async def test_cancel_after_commit_before_ledger_settlement_recovers_without_input(
    rig, consumer, monkeypatch, private_redis_socket,
):
    t, _ = await prepared(rig, consumer, monkeypatch)
    assert_default(t.r)
    await finish_warmup(t, rig)  # Only the fresh owner may recover below.
    await changed_row(t, rig)
    actual_call = t.r._preview_call(None)
    entered = asyncio.Event()
    queued = []
    fresh = task = client = subscriber = None

    async def interrupted_call(*args):
        if args[0] == 'EVAL' and args[3 + int(args[2])] == 'settle':
            entered.set()
            await asyncio.Event().wait()
        return await actual_call(*args)

    async def queue(frames):
        queued.extend(frames)
        await t.r._publish_prices(frames)

    monkeypatch.setattr(t.r, '_preview_call', lambda connection: interrupted_call)
    try:
        task = asyncio.create_task(t.r._refresh_batch([1], time.monotonic(), publish_committed=queue))
        await asyncio.wait_for(entered.wait(), 2)
        debt = [row for row in await owed(rig) if row['event_id'] == 1]
        assert len(debt) == 1
        revision = debt[0]['reading']['rev']
        async with rig.engine.connect() as conn:
            sources, stored_rev = (await conn.execute(text(
                'SELECT win_probability_sources,win_probability_sources_rev FROM events WHERE id=1'
            ))).one()
        assert sources['polymarket']['value'] == .78 and stored_rev == revision
        assert (1, revision) in t.r._normal_inflight and not queued
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert not t.r._normal_inflight and not queued
        assert [row for row in await owed(rig) if row['event_id'] == 1] == debt

        client = Redis(unix_socket_path=str(private_redis_socket))
        subscriber = client.pubsub()
        await subscriber.subscribe(event_channel(1))
        await subscriber.get_message(timeout=1)
        fresh = LiveBlendRefresher('polymarket', session_factory=t.r._session_factory)
        fresh._client = lambda: client
        assert_default(fresh)
        await fresh.refresh_pending()
        await join(fresh)
        message = await subscriber.get_message(ignore_subscribe_messages=True, timeout=1)
        assert message is not None, 'fresh owner must recover without another venue input'
        frame = json.loads(message['data'])
        assert frame.get('reconcile_only') is True and frame.get('p') is None
        assert 'source_value' not in frame and 'status' not in frame
        assert frame['rev'] == {'1': revision}
        assert not [row for row in await owed(rig) if row['event_id'] == 1]
    finally:
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        if fresh is not None:
            await close(fresh)
        await close_rig(t)
        if subscriber is not None:
            await subscriber.aclose()
        if client is not None:
            await client.aclose()


async def test_default_stalled_ledger_eval_is_bounded_and_committed_frame_still_sends(
    rig, consumer, monkeypatch,
):
    t, _ = await prepared(rig, consumer, monkeypatch)
    assert_default(t.r)
    await finish_warmup(t, rig)
    await changed_row(t, rig)
    attempts, queued = [], []
    errors_before = t.r.preview_stats.get('publish_errors', 0)
    actual_call = t.r._preview_call(None)

    async def stalled_call(*args):
        if args[0] == 'EVAL':
            attempts.append(args[3 + int(args[2])])
            await asyncio.Event().wait()
        return await actual_call(*args)

    async def queue(frames):
        queued.extend(frames)
        await t.r._publish_prices(frames)

    monkeypatch.setattr(t.r, '_preview_call', lambda connection: stalled_call)
    started = time.monotonic()
    try:
        # .25s admission + 1s settlement caps, with .75s fixture/DB allowance.
        # No post-settlement blend exists when the settlement EVAL times out.
        await asyncio.wait_for(t.r._refresh_batch(
            [1], started, publish_committed=queue,
        ), 2)
        elapsed = time.monotonic() - started
        assert 'read_ticket' in attempts and 'settle' in attempts
        assert t.r.preview_stats['publish_errors'] - errors_before >= 2
        assert len(queued) == 1 and queued[0]['source_value'] == .78
        assert not queued[0].get('provisional')
        assert any(eid == 1 and value == .78 for _, eid, value, _ in t.pubs)
        assert not t.r._normal_inflight
        revision = queued[0]['rev']['1']
        assert t.r._normal_acked[1] == revision
        # Publication deliberately does no DB cleanup; the next recovery
        # opportunity pays this ACK. Its background owner is closed above.
        await t.r._settle_normal_recovery({(1, revision)})
        assert not [row for row in await owed(rig) if row['event_id'] == 1]
        print('DEFAULT_LEDGER_STALL', {'committed_publication_seconds': elapsed,
                                      'operations': attempts})
    finally:
        await close_rig(t)
