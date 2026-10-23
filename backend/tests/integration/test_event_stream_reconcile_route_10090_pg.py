"""#10090 — an open or reopened page always learns which source removals it owes (real Postgres).

THE SHIP, IN A READER'S WORDS: a live event page that opens, reconnects or
stays open recovers an earlier source removal even after newer prices have
arrived or the price replay has expired — and never sees an old price brought
back to do it.

WHAT IS PINNED. The actual `_stream` route reads committed revision coverage
from real PostgreSQL through `async_session_maker`.

- attempt121/125 (`test_reconcile_route.py`, assertions verbatim, 10 cases):
  an open with no retained frame still owes the committed floor, price-free;
  a commit between the open read and the subscription confirmation emits a
  second obligation; an old removal arriving after a newer price (own row and
  folded row) is delivered as a control with no old price; a hub recovery
  re-issues current coverage once; a mailbox overflow closes with an explicit
  reconnect; a failed or incomplete coverage read closes without fabricating
  coverage; a fresh legacy invalidation is still delivered; a cancel during
  the coverage read releases the subscription.
- attempt121/125 (`test_reconcile_wire.py`, assertions verbatim, 1 case): the
  same old control crosses the unchanged packed Redis publisher, real Redis
  and the real fanout hub without replacing the newer replay frame.

REUSED, NOT COPIED. `stream_rig` is the 121/125 fixture already carried by
`test_event_stream_recovery_read_price_flow_10090_pg.py`; this file adds back
only its `revision` helper (`reconcile_rig`). `real_redis` is the private
socket / CI-service fixture of
`test_pm_withdrawal_peer_publication_and_startup_10090_pg.py` (CI points it at
a dedicated, flushed db 12). Non-DB route controls live in
`tests/test_event_stream_reconcile_route_controls_10090.py`.

BOUNDED WAITS. Every wait watches the stream task: a stream that ended first
re-raises its own error; one still running at the bound is cancelled and
awaited before the failure is reported.
"""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from redis.asyncio import Redis
from sqlalchemy import text

from app.routes import event_stream as route
from app.tasks import redis_state
from app.tasks.live_blend_refresh import LiveBlendRefresher
from app.utils import live_fanout, live_push, request_cache
from tests.integration.test_event_stream_recovery_read_price_flow_10090_pg import (  # noqa: F401
    stream_rig,
)
from tests.integration.test_live_blend_grouped_commit_8129_pg import (  # noqa: F401
    DB_URL,
    rig,
    seed,
)
from tests.integration.test_pm_withdrawal_peer_publication_and_startup_10090_pg import (  # noqa: F401
    real_redis,
)
from tests.test_event_stream_reconcile_route_controls_10090 import (  # noqa: F401
    reconcile_frames_reach_this_module,
)
from tests.test_event_stream_recovery_read_controls_10090 import data, until
from tests.test_folded_event_stream_invalidation_837 import Request, frame

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL, reason="requires disposable SEARCH_TEST_DATABASE_URL"
    ),
]


@pytest.fixture
async def reconcile_rig(stream_rig):  # noqa: F811
    async def revision(eid, rev):
        async with stream_rig.db.engine.begin() as db:
            await db.execute(
                text("UPDATE events SET win_probability_sources_rev=:r WHERE id=:id"),
                {"r": rev, "id": eid},
            )

    return SimpleNamespace(**vars(stream_rig), revision=revision)


async def ready(s, ids=None):
    chunks, task = s.start(ids)
    await until(lambda: data(chunks, "heartbeat"), task, "first heartbeat")
    return chunks, task


# --- attempt121/125 test_reconcile_route.py --------------------------------


async def test_open_without_retained_frame_obligates_committed_coverage(reconcile_rig):
    s = reconcile_rig
    await s.revision(1, 42)
    chunks, _ = await ready(s)
    controls = data(chunks, "reconcile")
    assert len(controls) == 1 and controls[0]["removal_rev"] == {"1": 42}
    assert set(controls[0]) == {"event_id", "custody_id", "removal_rev"}
    assert not data(chunks, "probability")


async def test_commit_between_open_read_and_subscription_confirmation(reconcile_rig):
    s = reconcile_rig
    chunks, _ = await ready(s)
    await s.revision(1, 43)
    s.hub.subscriptions["live:event:1"].offer(live_fanout.CONFIRMED)
    await asyncio.sleep(0.08)
    assert [c["removal_rev"] for c in data(chunks, "reconcile")] == [
        {"1": 0},
        {"1": 43},
    ]


@pytest.mark.parametrize("folded", [False, True])
async def test_old_removal_after_newer_price_survives_without_old_price(
    reconcile_rig, folded
):
    s = reconcile_rig
    chunks, task = await ready(s, [2] if folded else None)
    origin = 2 if folded else 1
    sub = s.hub.subscriptions[f"live:event:{origin}"]
    sub.offer(json.dumps(frame(origin, rev={str(origin): 20})))
    await until(lambda: data(chunks, "probability"), task, "newer price")
    control = {
        "event_id": origin,
        "custody_id": "pm-withdrawal:7",
        "removal_rev": {str(origin): 10},
    }
    sub.offer(
        json.dumps(
            frame(
                origin,
                p=None,
                source=None,
                source_value=None,
                rev={str(origin): 10},
                updated_at="2000-01-01T00:00:00+00:00",
                invalidation=True,
                reconcile=control,
                reconcile_only=True,
            )
        )
    )
    await asyncio.sleep(0.08)
    controls = [
        c for c in data(chunks, "reconcile") if c["custody_id"] == "pm-withdrawal:7"
    ]
    assert controls == [{**control, "event_id": 1}]
    assert len(data(chunks, "probability")) == 1


async def test_hub_recovery_reissues_current_coverage_once(reconcile_rig):
    s = reconcile_rig
    chunks, _ = await ready(s, [2])
    await s.revision(2, 55)
    for sub in s.hub.subscriptions.values():
        sub.offer(live_fanout.Recovery(1))
    await asyncio.sleep(0.08)
    assert len(data(chunks, "resync")) == 1
    controls = data(chunks, "reconcile")
    assert len(controls) == 2 and controls[-1]["removal_rev"] == {"1": 0, "2": 55}


async def test_overflow_closes_with_explicit_recovery(reconcile_rig):
    s = reconcile_rig
    chunks, task = await ready(s)
    sub = s.hub.subscriptions["live:event:1"]
    for _ in range(sub._queue.maxsize + 1):
        sub.offer(json.dumps(frame(1)))
    assert sub.dropped > 0
    await asyncio.sleep(0.08)
    assert data(chunks, "reconnect") == [{"reason": "mailbox_overflow"}]
    assert task.done() and task.exception() is None
    assert s.hub.released == ["live:event:1"]


async def test_failed_coverage_read_closes_without_fabricating_coverage(
    reconcile_rig, monkeypatch
):
    s = reconcile_rig

    def broken():
        raise ConnectionError("controlled coverage failure")

    monkeypatch.setattr(route, "async_session_maker", broken)
    chunks, task = s.start()
    await asyncio.sleep(0.08)
    assert task.done() and not data(chunks, "reconcile")
    assert s.hub.released == ["live:event:1"]


async def test_missing_fold_row_refuses_incomplete_coverage(reconcile_rig):
    s = reconcile_rig
    chunks, task = s.start([999])
    await asyncio.sleep(0.08)
    assert task.done() and not data(chunks, "reconcile")


async def test_fresh_legacy_invalidation_is_still_delivered(reconcile_rig):
    s = reconcile_rig
    chunks, task = await ready(s)
    old = frame(1, p=None, source=None, source_value=None, invalidation=True)
    s.hub.subscriptions["live:event:1"].offer(json.dumps(old))
    await until(lambda: data(chunks, "probability"), task, "legacy invalidation")
    assert data(chunks, "probability") == [old]


async def test_cancel_during_coverage_read_releases_subscription(
    reconcile_rig, monkeypatch
):
    s = reconcile_rig
    entered = asyncio.Event()

    @asynccontextmanager
    async def stalled():
        entered.set()
        await asyncio.Future()
        yield

    monkeypatch.setattr(route, "async_session_maker", stalled)
    chunks, task = s.start()
    # Parent never enters this new read; still assert its cancellation cleanup.
    await asyncio.sleep(0.03)
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    assert s.hub.released == ["live:event:1"] and not data(chunks, "reconcile")


# --- attempt121/125 test_reconcile_wire.py ---------------------------------


def items(chunks, kind):
    return [
        json.loads(c.split("data: ", 1)[1])
        for c in chunks
        if c.startswith("event: " + kind + "\n")
    ]


async def test_old_control_crosses_real_redis_without_replacing_newer_replay(
    rig, real_redis, monkeypatch  # noqa: F811
):
    await seed(rig, count=1)
    client = Redis(**real_redis.client_kwargs)
    monkeypatch.setattr(
        redis_state,
        "get_async_redis_client",
        lambda: Redis(**real_redis.client_kwargs),
    )
    monkeypatch.setattr(
        request_cache, "get_shared_async_redis", AsyncMock(return_value=client)
    )
    monkeypatch.setattr(route, "async_session_maker", rig.maker)
    monkeypatch.setattr(route, "FRAME_WAIT_S", 0.02)
    monkeypatch.setattr(live_fanout, "READ_TIMEOUT_S", 0.01)
    hub = live_fanout.LiveFanout()
    monkeypatch.setattr(live_fanout, "fanout", lambda: hub)
    r = LiveBlendRefresher("polymarket")
    r._redis = client
    chunks = []

    async def collect():
        async for c in route._stream(1, Request()):
            chunks.append(c)

    task = asyncio.create_task(collect())
    try:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + 2
        while (await client.pubsub_numsub(live_push.event_channel(1)))[0][1] != 1:
            if task.done():
                task.result()
                raise AssertionError("subscribed: the stream ended without it")
            if loop.time() >= deadline:
                raise AssertionError("subscribed: not within 2 s")
            await asyncio.sleep(0.005)
        newer = frame(1, rev={"1": 20})
        assert await r._publish([newer]) == {(1, 20)}
        await until(
            lambda: items(chunks, "probability"),
            task,
            "newer price",
            within=2.0,
            poll=0.005,
        )
        control = {
            "event_id": 1,
            "custody_id": "pm-withdrawal:55",
            "removal_rev": {"1": 10},
        }
        old = frame(
            1,
            p=None,
            source=None,
            source_value=None,
            rev={"1": 10},
            updated_at="2000-01-01T00:00:00+00:00",
            invalidation=True,
            reconcile=control,
            reconcile_only=True,
        )
        assert await r._publish([old]) == {(1, 10)}
        await asyncio.sleep(0.12)
        latest = json.loads(await client.get(live_push.latest_frame_key(1)))
        assert latest == newer
        assert len(items(chunks, "probability")) == 1
        assert control in items(chunks, "reconcile")
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await hub.aclose()
        await client.aclose()
    assert hub.subscriber_count == 0 and hub.redis_connections == 0
