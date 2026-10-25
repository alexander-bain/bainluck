"""#10090 — a held event page receives the last changed probability after a
publication outage, without another venue tick or the detail poll.

A stamp's transaction also commits a compact normal-price intent
(`<source>_price_publish` in `owed_chart_points`: revision and stamped clock,
never a frame). A positive Redis acknowledgement deletes the revisions it
covers and nothing newer. The refresher's existing flush opportunities run a
bounded, indexed discovery and publish a PRICE-FREE reconciliation for any
intent still owed, so a fresh owner recovers an old owner's failed final
without a new input — including an intent whose COMMIT lands after the fresh
owner's first, empty scan.

Ported from Root's attempt151 lab (packet
`artifacts/live-iteration-goal-20261011/local-blended-web-20261016/attempt151-durable-normal-recovery`,
candidate blend SHA-256 3048e759…): the fifteen correctness controls and the
three shared-resource / terminal / primary-budget controls, assertions
unchanged. The private Redis socket is the shared `real_redis` endpoint (a
private server when a binary is present, otherwise the job's loopback Redis on
a dedicated, flushed db), and the terminal interleave now ASSERTS the intent
it retains after the ambiguous acknowledgement. Two TIMED controls (one per
consumer, added on Authority's review of be6d5958e1) drive back-to-back price
flushes that never reach `refresh_pending`, so a refresher whose only
recovery trigger sat there cannot pass them.

Fresh-owner cases model lost process state without the final drain: not an
OS kill, not a browser. Synthetic rows on one machine: order and coherence,
not production timing. The two cost cases bound a regression only; their
numbers are not a production forecast.
"""

from __future__ import annotations

import asyncio
import contextlib
import functools
import json
import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.tasks.base import get_task_session
from app.tasks.live_blend_refresh import LiveBlendRefresher, hand_off_pending
from app.utils.blend_preview import is_preview_frame
from app.utils.live_push import event_channel, latest_frame_key
from tests.integration.test_live_blend_grouped_commit_8129_pg import (  # noqa: F401
    DB_URL,
    rig,
)
from tests.integration.test_pm_stamp_release_wake_10090_pg import (  # noqa: F401
    PERIOD,
    _Pool,
    consumer,
    start_cadence,
    stop_cadence,
    wait_for,
)
from tests.integration.test_pm_withdrawal_debt_10090_pg import (
    WIDE,
    flush,
    prime,
    setup,
)
from tests.integration.test_pm_withdrawal_peer_publication_and_startup_10090_pg import (  # noqa: F401
    default_preview_redis,
    real_redis,
)

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL, reason="requires disposable SEARCH_TEST_DATABASE_URL"
    ),
]

NORMAL_SOURCE = "polymarket_price_publish"


async def join(ref):
    task = getattr(ref, "_normal_task", None)
    if task is not None:
        await asyncio.wait_for(asyncio.shield(task), 2)


async def close(ref):
    await ref._close_normal_recovery()
    task = ref._history_task
    if task is not None:
        await asyncio.wait_for(asyncio.shield(task), 2)


async def owed(rig):
    async with rig.engine.connect() as db:
        return [dict(x._mapping) for x in (await db.execute(text(
            "SELECT id,event_id,reading FROM owed_chart_points "
            "WHERE source='polymarket_price_publish' ORDER BY id"
        ))).all()]


async def add(db, start, count):
    await db.execute(text("""
        INSERT INTO owed_chart_points(source,event_id,value,reading)
        SELECT 'polymarket_price_publish', i, .78,
            jsonb_build_object('rev',1,'updated_at','2026-10-19T13:00:00Z')
        FROM generate_series(CAST(:start AS integer), CAST(:last AS integer)) AS i
    """), {"start": start, "last": start + count - 1})


def ref_for(consumer):
    return LiveBlendRefresher(
        "polymarket",
        session_factory=functools.partial(get_task_session, engine=consumer),
    )


def acknowledge_all(frames):
    return {(f["event_id"], f["rev"][str(f["event_id"])]) for f in frames}


async def failed_final(rig, consumer, monkeypatch):
    t = await setup(rig, consumer, monkeypatch)

    async def refuse(frames):
        return set()

    t.r._publish = refuse
    t.r.min_refresh_interval_s = 0
    mark = t.accept(1, .78)
    await flush(t)
    await join(t.r)
    async with rig.engine.connect() as db:
        sources, revision = (await db.execute(text(
            "SELECT win_probability_sources,win_probability_sources_rev "
            "FROM events WHERE id=1"
        ))).one()
    assert sources["polymarket"]["value"] == .78
    return t, mark, revision


# ── correctness ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize("terminal", [False, True])
async def test_fresh_owner_recovers_final_without_new_input(
    rig, consumer, monkeypatch, real_redis, terminal,
):
    client = real_redis.client()
    subscriber = real_redis.client()
    pubsub = subscriber.pubsub()
    await pubsub.subscribe(event_channel(1))
    await pubsub.get_message(timeout=1)
    t = fresh = None
    try:
        t, mark, revision = await failed_final(rig, consumer, monkeypatch)
        # Stop the old background owner, WITHOUT a final publication attempt.
        await t.r._close_normal_recovery()
        if terminal:
            async with rig.engine.begin() as db:
                await db.execute(text("UPDATE events SET status='finished' WHERE id=1"))
        fresh = LiveBlendRefresher("polymarket", session_factory=t.r._session_factory)
        fresh._client = lambda: client
        restored = time.monotonic()
        await fresh.refresh_pending()
        await join(fresh)
        item = await pubsub.get_message(ignore_subscribe_messages=True, timeout=.2)
        received = time.monotonic()
        frame = json.loads(item["data"]) if item else None
        after = await owed(rig)
        assert frame is not None, "no final recovery without a new venue input"
        assert frame.get("reconcile_only") is True and frame.get("p") is None
        assert "status" not in frame and "source_snapshot" not in frame
        assert frame["rev"] == {"1": revision}
        from app.routes.event_stream import _withdrawal_reconcile
        assert _withdrawal_reconcile(frame, 1, 1)
        assert not after
        assert received - restored < 1
    finally:
        if fresh:
            await close(fresh)
        if t:
            await close(t.r)
        await pubsub.aclose()
        await subscriber.aclose()
        await client.aclose()


async def test_old_ack_cannot_clear_newer_final(rig, consumer, monkeypatch):
    t, mark, oldrev = await failed_final(rig, consumer, monkeypatch)
    try:
        t.accept(1, .82)
        await flush(t)
        await join(t.r)
        await t.r._settle_normal_recovery({(1, oldrev)})
        remaining = await owed(rig)
        assert remaining and all(x["reading"]["rev"] > oldrev for x in remaining)
    finally:
        await close(t.r)


async def test_primary_ack_cleans_intent(rig, consumer, monkeypatch):
    t = await setup(rig, consumer, monkeypatch)
    try:
        t.accept(1, .78)
        await flush(t)
        await join(t.r)
        assert t.pubs[-1][2] == .78
        assert not await owed(rig)
    finally:
        await close(t.r)


async def test_failed_outer_commit_has_no_price_or_intent(rig, consumer, monkeypatch):
    t = await setup(rig, consumer, monkeypatch)
    failures = []

    @contextlib.asynccontextmanager
    async def rejecting_session():
        async with rig.maker() as db:
            yield db
            count = await db.scalar(text(
                "SELECT count(*) FROM owed_chart_points "
                "WHERE source='polymarket_price_publish'"
            ))
            if count and not failures:
                failures.append("before outer COMMIT")
                raise RuntimeError("injected outer COMMIT refusal")
            await db.commit()

    t.r._session_factory = rejecting_session
    try:
        t.accept(1, .78)
        await flush(t)
        await join(t.r)
        async with rig.engine.connect() as db:
            bag = await db.scalar(text("SELECT win_probability_sources FROM events WHERE id=1"))
        remaining = await owed(rig)
        assert failures and "polymarket" not in bag and not remaining and not t.pubs
    finally:
        await close(t.r)


async def test_failed_ack_cleanup_keeps_durable_recovery(rig, consumer, monkeypatch):
    t = await setup(rig, consumer, monkeypatch)
    cleanup = t.r._settle_normal_recovery

    async def fail(_ack):
        raise RuntimeError("injected cleanup failure after positive Redis ACK")

    t.r._settle_normal_recovery = fail
    try:
        t.accept(1, .78)
        await flush(t)
        await join(t.r)
        assert t.pubs[-1][2] == .78 and await owed(rig)
        sent = []

        async def accept(frames):
            sent.extend(frames)
            return acknowledge_all(frames)

        t.r._publish = accept
        t.r._settle_normal_recovery = cleanup
        t.r._normal_after = 0
        t.r._normal_retry_at = 0
        await t.r.refresh_pending()
        await join(t.r)
        assert sent and all(f.get("reconcile_only") is True for f in sent)
        assert not await owed(rig)
    finally:
        await close(t.r)


async def test_failed_first_batch_does_not_starve_later_events(rig, consumer):
    from tests.integration.test_live_blend_grouped_commit_8129_pg import seed

    await seed(rig, count=36)
    ref = ref_for(consumer)
    real_start = ref._start_normal_recovery
    ref._start_normal_recovery = lambda: None

    async def refuse(frames):
        return set()

    ref._publish = refuse
    try:
        await ref.refresh(list(range(1, 37)))
        assert len(await owed(rig)) == 36
        attempted = []

        async def selective(frames):
            attempted.append([f["event_id"] for f in frames])
            return {
                (f["event_id"], f["rev"][str(f["event_id"])])
                for f in frames if f["event_id"] > 32
            }

        ref._publish = selective
        ref._start_normal_recovery = real_start
        for _ in range(2):
            ref._normal_retry_at = 0  # remove wall-clock wait, keep cursor/order
            await ref.refresh_pending()
            await join(ref)
        remaining = await owed(rig)
        assert all(len(batch) <= 32 for batch in attempted)
        assert not any(row["event_id"] > 32 for row in remaining)
        assert len(remaining) == 32
    finally:
        await close(ref)


@pytest.mark.parametrize("delay", [0, .025])
async def test_healthy_delivery_cost(rig, consumer, monkeypatch, delay):
    from sqlalchemy import event

    t = await setup(rig, consumer, monkeypatch)
    t.r.min_refresh_interval_s = 0
    sent = []
    counts = {"intent_inserts": 0, "intent_deletes": 0, "recovery_reads": 0}

    def sql_observer(conn, cursor, statement, parameters, context, executemany):
        lower = statement.lower()
        if "owed_chart_points" not in lower:
            return
        if lower.startswith("insert"):
            counts["intent_inserts"] += 1
        if lower.startswith("delete"):
            counts["intent_deletes"] += 1
        if lower.startswith("select"):
            counts["recovery_reads"] += 1

    event.listen(consumer.sync_engine, "before_cursor_execute", sql_observer)
    original = AsyncSession.execute

    async def delayed(self, *args, **kwargs):
        if delay:
            await asyncio.sleep(delay)
        return await original(self, *args, **kwargs)

    monkeypatch.setattr(AsyncSession, "execute", delayed)

    async def sink(payload):
        if payload.get("p") is not None:
            async with rig.engine.connect() as db:
                row = (await db.execute(text(
                    "SELECT win_probability_sources,win_probability_sources_rev "
                    "FROM events WHERE id=1"
                ))).one()
            assert row[0]["polymarket"]["value"] == payload["source_value"]
            assert row[1] == payload["rev"]["1"]
            sent.append((time.monotonic(), payload["source_value"]))

    t.r._client = lambda: SimpleNamespace(connection_pool=_Pool(sink))
    timings = []
    try:
        for value in [.66, .78, .68, .76, .70, .74, .72, .80]:
            mark = t.accept(1, value)
            await flush(t)
            await join(t.r)
            assert sent and sent[-1][1] == value
            timings.append(sent[-1][0] - mark.recv_mono)
        assert len(timings) == 8 and max(timings) < 1, (timings, counts)
    finally:
        await close(t.r)
        event.remove(consumer.sync_engine, "before_cursor_execute", sql_observer)


async def test_quiet_failure_retried_despite_continuous_newer_debt(rig, consumer):
    ref = ref_for(consumer)
    async with rig.engine.begin() as db:
        await add(db, 1, 32)
    calls = []
    round_no = 0

    async def publish(frames):
        calls.append({"pass": round_no, "events": [f["event_id"] for f in frames]})
        return {
            (f["event_id"], f["rev"][str(f["event_id"])]) for f in frames
            if round_no > 0 or f["event_id"] != 1
        }

    ref._publish = publish
    try:
        for round_no in range(4):
            if round_no:
                async with rig.engine.begin() as db:
                    await add(db, 32 * round_no + 1, 32)
            await ref._recover_normal_prices()
        remaining = await owed(rig)
        retry_passes = [x["pass"] for x in calls if 1 in x["events"]]
        assert len(retry_passes) >= 2 and retry_passes[1] <= 2
        assert not any(r["event_id"] == 1 for r in remaining)
    finally:
        await close(ref)


async def test_duplicate_backlog_discovery_is_index_bounded(rig, consumer, monkeypatch):
    ref = ref_for(consumer)
    async with rig.engine.begin() as db:
        await add(db, 1, 1)
        await db.execute(text("""
            INSERT INTO owed_chart_points(source,event_id,value,reading)
            SELECT 'polymarket_price_publish', 2+(i%64), .78,
                jsonb_build_object('rev',i,'updated_at','2026-10-19T13:00:00Z')
            FROM generate_series(1,32768) AS i
        """))
        await db.execute(text("ANALYZE owed_chart_points"))
    captured = []
    original = AsyncSession.execute

    async def observe(self, statement, params=None, *args, **kwargs):
        sql = str(statement)
        if sql.startswith("SELECT") and "owed_chart_points" in sql:
            captured.append((sql, dict(params or {})))
        return await original(self, statement, params, *args, **kwargs)

    monkeypatch.setattr(AsyncSession, "execute", observe)
    sent = []

    async def refuse(frames):
        sent.extend(frames)
        return set()

    ref._publish = refuse
    started = time.monotonic()
    try:
        await ref._recover_normal_prices()
        elapsed = time.monotonic() - started
        plans = []
        async with rig.engine.connect() as db:
            for sql, params in captured:
                plans.append(await db.scalar(
                    text("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + sql), params,
                ))

        def nodes(node):
            yield node
            for child in node.get("Plans", []):
                yield from nodes(child)

        scans = [n for plan in plans for n in nodes(plan[0]["Plan"])]
        remaining = await owed(rig)
        assert sent and any(f["event_id"] == 1 for f in sent)
        assert len(sent) <= 32 and len(remaining) == 32769
        assert not any(n["Node Type"] in ("Sort", "Unique", "Seq Scan") for n in scans)
        assert all(n["Actual Rows"] <= 32 for n in scans)
        assert elapsed < .25
    finally:
        await close(ref)


async def test_repeated_cancel_joins_both_owners_before_handoff():
    ref = LiveBlendRefresher("polymarket")
    normal_started = asyncio.Event()
    normal_cleanup = asyncio.Event()
    release_normal = asyncio.Event()
    release_history = asyncio.Event()

    async def normal():
        normal_started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            normal_cleanup.set()
            await release_normal.wait()
            raise

    async def history():
        await release_history.wait()

    ref._normal_task = asyncio.create_task(normal())
    ref._history_task = asyncio.create_task(history())
    starts = []
    ref._start_history = lambda **kw: starts.append(kw)
    await asyncio.wait_for(normal_started.wait(), 2)
    drain = asyncio.create_task(ref.drain_history())
    await asyncio.wait_for(normal_cleanup.wait(), 2)
    drain.cancel()
    await asyncio.sleep(0)
    drain.cancel()
    await asyncio.sleep(0)
    release_normal.set()
    for _ in range(5):
        await asyncio.sleep(0)
    escaped_before_history = drain.done()
    release_history.set()
    result = await asyncio.gather(drain, return_exceptions=True)
    try:
        hand_off_pending(ref)
        assert not escaped_before_history
        assert starts and ref._normal_task is None and ref._history_task.done()
        assert isinstance(result[0], asyncio.CancelledError)
    finally:
        await close(ref)


async def test_late_lower_id_commit_reenables_empty_discovery(rig, consumer):
    ref = ref_for(consumer)
    sent = []

    async def ack(frames):
        sent.extend(frames)
        return acknowledge_all(frames)

    async def refuse(frames):
        return set()

    ref._publish = ack
    try:
        async with rig.engine.connect() as slow:
            txn = await slow.begin()
            await add(slow, 1, 1)  # sequence allocated but invisible to recovery
            async with rig.engine.begin() as fast:
                await add(fast, 2, 1)
            await ref._recover_normal_prices()
            await ref._recover_normal_prices()
            assert ref._normal_has_debt is False
            assert [f["event_id"] for f in sent] == [2]
            await txn.commit()
        ref._publish = refuse
        await ref._publish_prices([{"event_id": 1, "p": .78, "rev": {"1": 1}}])
        assert ref._normal_has_debt is True
        ref._publish = ack
        await ref._recover_normal_prices()
        assert [f["event_id"] for f in sent] == [2, 1] and not await owed(rig)
    finally:
        await close(ref)


async def test_new_owner_rediscovers_old_owner_late_commit(rig, consumer):
    old = ref_for(consumer)
    fresh = ref_for(consumer)
    sent = []

    async def refuse(frames):
        return set()

    async def ack(frames):
        sent.extend(frames)
        return acknowledge_all(frames)

    old._publish = refuse
    fresh._publish = ack
    try:
        async with rig.engine.connect() as slow:
            txn = await slow.begin()
            await add(slow, 1, 1)
            await fresh.refresh_pending()
            await join(fresh)
            assert not sent and not fresh._normal_has_debt
            await txn.commit()
        await old._publish_prices([{"event_id": 1, "p": .78, "rev": {"1": 1}}])
        await close(old)  # no handoff or new venue input to notify fresh owner
        fresh._normal_retry_at = 0  # opportunity after cooldown; not a latency measurement
        await fresh.refresh_pending()
        await join(fresh)
        assert sent and [f["event_id"] for f in sent] == [1] and not await owed(rig)
    finally:
        await close(old)
        await close(fresh)


async def test_empty_periodic_discovery_is_bounded(rig, consumer, monkeypatch):
    ref = ref_for(consumer)
    queries = []
    original = AsyncSession.execute

    async def observe(self, statement, params=None, *args, **kwargs):
        sql = str(statement)
        if sql.startswith("SELECT") and "owed_chart_points" in sql:
            queries.append(time.monotonic())
        return await original(self, statement, params, *args, **kwargs)

    monkeypatch.setattr(AsyncSession, "execute", observe)
    start = time.monotonic()
    try:
        while time.monotonic() - start < 1.6:
            await ref.refresh_pending()
            await join(ref)
            await asyncio.sleep(.025)
        spacings = [b - a for a, b in zip(queries, queries[1:])]
        assert 2 <= len(queries) <= 4 and all(x >= .49 for x in spacings), spacings
        assert not await owed(rig)
    finally:
        await close(ref)


# ── shared resources, terminal interleave, primary budget ───────────────────


async def next_frame(pubsub, value, timeout=4):
    async with asyncio.timeout(timeout):
        while True:
            item = await pubsub.get_message(ignore_subscribe_messages=True, timeout=.02)
            if item:
                frame = json.loads(item["data"])
                if frame.get("source_value") == value:
                    return frame


async def test_healthy_newer_price_survives_four_busy_publication_sockets(
    rig, consumer, monkeypatch, real_redis,
):
    t = await setup(rig, consumer, monkeypatch)
    await prime(t)
    t.accept(2, .62)
    await flush(t)
    original_publish = t.r._publish

    async def refuse(frames):
        return set()

    t.r._publish = refuse
    t.accept(3, .64)
    await flush(t)
    assert any(x["event_id"] == 3 for x in await owed(rig))
    # Keep the retained normal frame pending until the three other publishers
    # have acquired real sockets. This controls overlap, not the measured delay.
    t.r._normal_retry_at = time.monotonic() + 100
    task = t.r._normal_task
    if task is not None and not task.done():
        await task
    t.r._publish = original_publish
    pool = real_redis.blocking_pool(max_connections=4, timeout=2)
    subscriber = real_redis.client()
    pubsub = subscriber.pubsub()
    entered = {k: asyncio.Event() for k in ("remove1", "remove2", "market", "retry")}
    release = asyncio.Event()
    active = set()
    peak = 0
    waits = []

    class Connection:
        def __init__(self, raw, wait):
            self.raw = raw
            self.wait = wait
            self.kind = None

        def pack_commands(self, commands):
            for cmd in commands:
                if cmd[0] == "EVAL":
                    frame = json.loads(cmd[5])
                    if frame.get("invalidation") and frame.get("event_id") in (1, 2):
                        self.kind = "remove" + str(frame["event_id"])
                    elif frame.get("event_id") == 3 and frame.get("reconcile_only") is True:
                        self.kind = "retry"
                    elif frame.get("event_id") == 3 and frame.get("source_value") == .69:
                        waits.append(self.wait)
                        self.kind = "healthy"
                elif cmd[0] == "PUBLISH" and cmd[1] == "live:market:987654":
                    self.kind = "market"
            return self.raw.pack_commands(commands)

        async def send_packed_command(self, *a, **kw):
            return await self.raw.send_packed_command(*a, **kw)

        async def read_response(self):
            if self.kind in entered:
                entered[self.kind].set()
                await release.wait()
            return await self.raw.read_response()

        async def disconnect(self):
            await self.raw.disconnect()

    class Pool:
        async def get_connection(self, *a, **kw):
            nonlocal peak
            start = time.monotonic()
            raw = await pool.get_connection(*a, **kw)
            conn = Connection(raw, time.monotonic() - start)
            active.add(conn)
            peak = max(peak, len(active))
            return conn

        async def release(self, conn):
            active.discard(conn)
            await pool.release(conn.raw)

    t.r._client = lambda: SimpleNamespace(connection_pool=Pool())
    cadence = market = release_task = None
    stop = asyncio.Event()
    try:
        await pubsub.subscribe(event_channel(3))
        await pubsub.get_message(timeout=1)
        t.p.ns["withdraw_buffer"][1] = WIDE
        cadence = start_cadence(t, stop)
        await asyncio.wait_for(entered["remove1"].wait(), 2)
        t.p.ns["withdraw_buffer"][2] = WIDE
        await asyncio.wait_for(entered["remove2"].wait(), 2)
        now = datetime.now(timezone.utc).isoformat()
        change = dict(
            market_id=987654, source="polymarket", outcome_ids=[987654],
            outcome_observed_at={"987654": now}, updated_at=now,
            terminal=False, invalidation=True,
        )
        market = asyncio.create_task(t.r.publish_market_frames([change]))
        await asyncio.wait_for(entered["market"].wait(), 1)
        t.r._normal_retry_at = 0
        t.r._start_normal_recovery()
        await asyncio.wait_for(entered["retry"].wait(), 1)
        assert len(active) == 4
        # The old retry has been sent to Redis, but its ACK remains held.
        # Reconcile has no price; the following subscriber loop ignores it.
        accepted = time.monotonic()
        t.accept(3, .69)

        async def lift():
            await asyncio.sleep(1.5)
            release.set()

        release_task = asyncio.create_task(lift())
        frame = await next_frame(pubsub, .69)
        elapsed = time.monotonic() - accepted
        was_released = release.is_set()
        await release_task
        await market
        await t.r.withdrawal_debt.join_publications()
        await stop_cadence(t, stop, cadence)
        cadence = None
        await close(t.r)
        retained = json.loads(await subscriber.get(latest_frame_key(3)))
        assert retained == frame and frame["source_value"] == .69
        assert not active and not await owed(rig) and not t.r.withdrawal_debt.publications
        assert elapsed < 1, (elapsed, waits, peak)
        assert waits and max(waits) < 1 and not was_released
    finally:
        release.set()
        if release_task:
            await release_task
        if market:
            await market
        if cadence:
            await stop_cadence(t, stop, cadence)
        await close(t.r)
        await t.r.withdrawal_debt.join_publications(cancel=True)
        await pubsub.aclose()
        await subscriber.aclose()
        await pool.aclose()


async def _transition(rig, change, started, committed, times):
    async with rig.maker() as db:
        times["pid"] = await db.scalar(text("SELECT pg_backend_pid()"))
        started.set()
        sql = {
            "terminal": "UPDATE events SET status='finished' WHERE id=1",
            "completed": "UPDATE events SET completed_at=clock_timestamp() WHERE id=1",
            "newer": "UPDATE events SET win_probability_sources_rev="
                     "win_probability_sources_rev+1 WHERE id=1",
        }[change]
        await db.execute(text(sql))
        await db.commit()
    times["committed_at"] = time.monotonic()
    times["committed_wall"] = time.time()
    committed.set()


async def test_ambiguous_send_after_retry_timeout_does_not_execute_live_after_terminal(
    rig, consumer, monkeypatch, real_redis,
):
    t, _mark, _revision = await failed_final(rig, consumer, monkeypatch)
    assert await owed(rig)
    t.r._normal_retry_at = 0
    original = LiveBlendRefresher._publish.__get__(t.r)
    client = real_redis.client()
    await client.ping()
    blocker = real_redis.client()
    await blocker.ping()
    subscriber = real_redis.client()
    pubsub = subscriber.pubsub()
    await pubsub.subscribe(event_channel(1))
    await pubsub.get_message(timeout=1)
    sent = asyncio.Event()
    started = asyncio.Event()
    committed = asyncio.Event()
    times = {}
    blocking_task = writer = None
    rawpool = client.connection_pool

    class Connection:
        def __init__(self, raw):
            self.raw = raw

        def pack_commands(self, commands):
            return self.raw.pack_commands(commands)

        async def send_packed_command(self, *a, **kw):
            result = await self.raw.send_packed_command(*a, **kw)
            times["bytes_sent_at"] = time.monotonic()
            times["bytes_sent_wall"] = time.time()
            sent.set()
            return result

        async def read_response(self):
            return await self.raw.read_response()

        async def disconnect(self):
            await self.raw.disconnect()

    class Pool:
        async def get_connection(self, *a, **kw):
            return Connection(await rawpool.get_connection(*a, **kw))

        async def release(self, c):
            await rawpool.release(c.raw)

    t.r._client = lambda: SimpleNamespace(connection_pool=Pool())
    # Redis serializes this 700 ms busy loop: the retry's bytes queue behind it.
    # Redis 7 freezes TIME for a whole script until its 5 s busy threshold
    # (CI's redis:7 ran the old TIME loop for 5.000 s, into redis-py 8's 5 s
    # read timeout), so the loop runs on os.clock where the server has it;
    # Redis 6.2 has no os library and its TIME advances. TIME at script start
    # is the execution's start on both. The end is a TIME pipelined behind the
    # EVAL on the same connection, which Redis runs as soon as the script ends.
    lua = (
        "local t=redis.call('TIME'); "
        "local start_us=tonumber(t[1])*1000000+tonumber(t[2]); "
        "local os_lib=rawget(_G,'os'); "
        "if os_lib then local c=os_lib.clock(); repeat until os_lib.clock()-c>=0.7 "
        "else local until_us=start_us+700000; "
        "repeat t=redis.call('TIME') until tonumber(t[1])*1000000+tonumber(t[2])>=until_us "
        "end; "
        "return start_us"
    )

    async def block():
        pipe = blocker.pipeline(transaction=False)
        pipe.eval(lua, 0)
        pipe.time()
        start_us, (seconds, micros) = await pipe.execute()
        return start_us, seconds * 1_000_000 + micros

    async def delayed(frames):
        nonlocal blocking_task
        blocking_task = asyncio.create_task(block())
        await asyncio.sleep(.04)
        return await original(frames)

    t.r._publish = delayed
    try:
        t.r._start_normal_recovery()
        retry = t.r._normal_task
        await asyncio.wait_for(sent.wait(), 1)
        writer = asyncio.create_task(_transition(rig, "terminal", started, committed, times))
        await retry
        await writer
        block_times = await blocking_task
        times["redis_unblocked_at"] = time.monotonic()
        times["redis_block_start_wall"] = block_times[0] / 1e6
        times["redis_block_end_wall"] = block_times[1] / 1e6
        frames = []
        end = time.monotonic() + .15
        while time.monotonic() < end:
            item = await pubsub.get_message(ignore_subscribe_messages=True, timeout=.02)
            if item:
                frames.append(json.loads(item["data"]))
        raw = await client.get(latest_frame_key(1))
        latest = json.loads(raw) if raw else None
        pending_normal = len(await owed(rig))
        result = dict(times=times, frames=frames, latest=latest, pending_normal=pending_normal)
        assert times["committed_at"] < times["redis_unblocked_at"], result
        # All wall readings are CLOCK_REALTIME on this one host; Redis TIME
        # brackets the server's serialized Lua execution, not observer arrival.
        assert (
            times["redis_block_start_wall"] < times["bytes_sent_wall"]
            < times["committed_wall"] < times["redis_block_end_wall"]
        ), result
        assert len(frames) == 1 and frames[0].get("reconcile_only") is True, result
        assert frames[0].get("p") is None
        assert "status" not in frames[0] and "source_snapshot" not in frames[0]
        assert latest == frames[0]
        from app.routes.event_stream import _withdrawal_reconcile
        control = _withdrawal_reconcile(frames[0], 1, 1)
        assert control and control["custody_id"].startswith("normal-price:")
        # The acknowledgement was ambiguous (the recovery budget expired before
        # Redis answered): only a POSITIVE acknowledgement settles an intent,
        # so the durable intent survives for the next opportunity.
        assert pending_normal == 1, result
    finally:
        await close(t.r)
        if writer:
            await writer
        if blocking_task:
            await blocking_task
        await pubsub.aclose()
        await subscriber.aclose()
        await blocker.aclose()
        await client.aclose()


async def test_primary_350ms_ack_is_not_cancelled_by_recovery_budget(
    rig, consumer, monkeypatch,
):
    t = await setup(rig, consumer, monkeypatch)
    original = t.r._publish
    calls = []

    async def delayed(frames):
        calls.extend(frames)
        await asyncio.sleep(.35)
        return await original(frames)

    t.r._publish = delayed
    # Isolate the primary-path timeout: the independently tested recovery
    # owner must not rescue an incorrectly cancelled primary.
    t.r._normal_retry_at = time.monotonic() + 100
    started = time.monotonic()
    try:
        t.accept(1, .78)
        await flush(t)
        elapsed = time.monotonic() - started
        assert len(calls) == 1 and calls[0].get("source_value") == .78
        assert len(t.pubs) == 1 and t.pubs[0][2] == .78
        assert elapsed >= .35
        # The primary ACK is recorded off the publication path; the next
        # recovery opportunity settles it (live's owner revision), with no
        # control republished for a delivered price.
        assert t.r._normal_acked == {1: calls[0]["rev"]["1"]}
        t.r._normal_retry_at = 0
        await t.r.refresh_pending()
        await join(t.r)
        assert not await owed(rig) and len(calls) == 1
    finally:
        await close(t.r)


# ── the timed path (Authority's 151 review of be6d5958e1) ────────────────────
#
# Production flushes are TIMED (`flush_started` set) and, at ~4,600 Kalshi
# updates a minute, back to back with a price batch every time. Such a flush
# never reaches `refresh_pending` (Kalshi: only `if not batch`; PM: only the
# quiet branches), so every recovery control above, which flushes untimed and
# reaches it inline, could not see a refresher whose only trigger was there.
# Game A's one publication is refused, A goes quiet, game B has new input on
# every flush. A must get its price-free control and its intent must settle
# within a bounded number of periods, and B's receive-to-publish time must
# match a phase on the same rig with recovery stubbed out.


async def owed_for(rig, source, event_id):
    async with rig.engine.connect() as db:
        return [dict(x._mapping) for x in (await db.execute(text(
            "SELECT id,reading FROM owed_chart_points "
            "WHERE source=:source AND event_id=:eid ORDER BY id"
        ), {"source": source, "eid": event_id})).all()]


def count_pending(r):
    """Record every `refresh_pending` call; the premise is that none occur."""
    calls = []
    shipped = r.refresh_pending

    async def recorded(**kwargs):
        calls.append(time.monotonic())
        return await shipped(**kwargs)

    r.refresh_pending = recorded
    return calls


def refuse_first_price_of(r, event_id, publish, *, hold=0):
    """`publish` acknowledges what it sends. Once armed, A's next price frame
    is dropped unsent and unacknowledged; every price-free control is
    acknowledged (Redis accepted it) and recorded. With ``hold``, every price
    send takes that long before it is acknowledged, and each send's span is
    recorded: a cohort's later group commits while an earlier one is sending
    and is still owed when that send's recovery opportunity reads."""
    armed, refused, controls, sent_at, sent, spans = [], [], [], {}, [], []

    async def gate(frames):
        acked, forward = set(), []
        for f in frames:
            eid = f["event_id"]
            if f.get("reconcile_only"):
                controls.append((eid, f["rev"][str(eid)]))
                acked |= acknowledge_all([f])
            elif eid == event_id and armed and not refused:
                refused.append(f["rev"][str(eid)])
            else:
                forward.append(f)
        if forward:
            began = time.monotonic()
            if hold:
                await asyncio.sleep(hold)
            acked |= await publish(forward) or set()
            now = time.monotonic()
            spans.append((began, now))
            for f in forward:
                sent_at.setdefault((f["event_id"], f.get("source_value")), now)
                sent.append((f["event_id"], now))
        return acked

    r._publish = gate
    return SimpleNamespace(
        arm=lambda: armed.append(True), refused=refused, controls=controls,
        sent_at=sent_at, sent=sent, spans=spans,
    )


#: Authority's 151 review of 0f6389ce65: a price send this long, two busy games
#: per flush. Each group commits on its own and the groups send one at a time,
#: so a recovery opportunity started by one group's send reads the other's
#: committed intent while it waits or sends.
COHORT_HOLD = .05


def record_recovery_runs(r):
    """Wrap the recovery owner (still the task `_start_normal_recovery`
    creates, so it keeps its own session) and record each run's span."""
    runs = []
    shipped = r._recover_normal_prices

    async def recorded():
        began = time.monotonic()
        try:
            return await shipped()
        finally:
            runs.append((began, time.monotonic()))

    r._recover_normal_prices = recorded
    return runs


def overlapping(runs, spans):
    """Recovery runs that overlapped a busy price send."""
    return [
        run for run in runs
        if any(run[0] < end and began < run[1] for began, end in spans)
    ]


def median(values):
    ordered = sorted(values)
    return ordered[len(ordered) // 2]


@pytest.mark.parametrize("cohort", [False, True])
async def test_busy_timed_pm_flushes_recover_a_quiet_failed_game(
    rig, consumer, monkeypatch, cohort, default_preview_redis,
):
    t = await setup(rig, consumer, monkeypatch)
    t.r.min_refresh_interval_s = 0
    gate = refuse_first_price_of(
        t.r, 1, t.r._publish, hold=COHORT_HOLD if cohort else 0,
    )
    runs = record_recovery_runs(t.r)
    pending = count_pending(t.r)
    values = iter(round(.40 + i / 1000, 3) for i in range(400))
    recv = {}
    busy_games = {2, 3} if cohort else {2}

    async def busy_flush():
        # TIMED, as production's cadence calls it, and not joined: a PM
        # flush leaves its stamp owner running into the next one. B (and,
        # in the cohort, C) has new input on EVERY flush.
        value = next(values)
        recv[value] = t.accept(2, value).recv_mono
        if cohort:
            t.accept(3, next(values))
        started = time.monotonic()
        assert await t.tracked_flush(started) is True
        await asyncio.sleep(PERIOD)
        return started

    def latencies(since):
        return [
            at - recv[value] for (eid, value), at in gate.sent_at.items()
            if eid == 2 and value in recv and recv[value] >= since
        ]

    try:
        # Phase 1, the comparison arm: recovery stubbed out, B alone.
        t.r._start_normal_recovery = lambda: None
        stubbed_from = time.monotonic()
        for _ in range(8):
            await busy_flush()
        await t.boundary.join_stamps()
        stubbed = latencies(stubbed_from)
        del t.r._start_normal_recovery
        assert not gate.controls, "recovery was stubbed out"

        # Phase 2: A's single publication is refused, then A goes quiet.
        live_from = time.monotonic()
        gate.arm()
        t.accept(1, .78)
        busy, recovered = [], None
        for n in range(8):
            busy.append(await busy_flush())
            if recovered is None and any(e == 1 for e, _ in gate.controls) and not (
                await owed_for(rig, NORMAL_SOURCE, 1)
            ):
                recovered = n
        await t.boundary.join_stamps()
        await join(t.r)
        live = latencies(live_from)

        assert gate.refused, "rig: A's publication was refused"
        assert (1, gate.refused[0]) in gate.controls, "A's control names its revision"
        assert recovered is not None, "A's intent never settled through 8 busy flushes"
        assert not pending, "premise: a busy timed flush never reaches refresh_pending"
        written_b = {fs for fs, vals in t.writes if 2 in vals}
        assert set(busy) <= written_b, "premise: B's batch was never empty"
        if cohort:
            written_c = {fs for fs, vals in t.writes if 3 in vals}
            assert set(busy) <= written_c, "premise: C's batch was never empty"
            assert overlapping(runs, gate.spans), (
                "premise: no recovery run overlapped a busy price send", runs,
            )
        # A busy game's price is on its way or delivered: recovery owes its
        # readers nothing for it.
        assert not [c for c in gate.controls if c[0] in busy_games], gate.controls
        assert len(stubbed) >= 6 and len(live) >= 6, (stubbed, live)
        assert max(live) < 1, (live, stubbed)
        assert median(live) - median(stubbed) < .1, (live, stubbed)
    finally:
        await t.boundary.join_stamps()
        await close(t.r)
        await t.r.drain_history()


#: event (= market id): home outcome, away outcome, ticker, (home, code),
#: (away, code), title
KALSHI_GAMES = {
    2: (3, 4, "KXMLBGAME-26OCT17ATLNYM", ("New York Mets", "NYM"),
        ("Atlanta Braves", "ATL"), "Atlanta vs New York M Winner?"),
    3: (5, 6, "KXMLBGAME-26OCT17WSHPHI", ("Philadelphia Phillies", "PHI"),
        ("Washington Nationals", "WSH"), "Washington vs Philadelphia Winner?"),
}


async def _seed_kalshi_game(rig, eid):
    from app.models.models import Event, FuturesMarket, FuturesOutcome, Sport
    from sqlalchemy import select

    home_oid, away_oid, ticker, (home, home_code), (away, away_code), title = (
        KALSHI_GAMES[eid]
    )
    now = datetime.now(timezone.utc)
    async with rig.maker() as session:
        sport_id = await session.scalar(select(Sport.id).where(Sport.key == "baseball_mlb"))
        session.add(Event(
            id=eid, sport_id=sport_id, home_team_name=home,
            away_team_name=away, commence_time=now - timedelta(minutes=30),
            status="live", win_probability_sources={}, opening_home_probability=0.5,
        ))
        session.add(FuturesMarket(
            id=eid, source="kalshi", external_id=ticker,
            sport_id=sport_id, event_id=eid, name=title,
            status="open", category="game",
        ))
        await session.flush()
        for oid, name, side, prob in (
            (home_oid, home, home_code, 0.55),
            (away_oid, away, away_code, 0.45),
        ):
            session.add(FuturesOutcome(
                id=oid, market_id=eid, external_id=f"{ticker}-{side}", name=name,
                current_probability=prob, rank=1 if oid == home_oid else 2,
                last_updated=now - timedelta(minutes=1),
            ))
        await session.commit()


@pytest.mark.parametrize("cohort", [False, True])
async def test_busy_timed_kalshi_flushes_recover_a_quiet_failed_game(rig, cohort):
    from tests.integration import test_kalshi_held_price_row_10090_pg as k

    await k.seed(rig)
    busy_games = {2, 3} if cohort else {2}
    for eid in sorted(busy_games):
        await _seed_kalshi_game(rig, eid)
    c = k.Consumer(rig, overlay=False)
    for eid in busy_games:
        home_oid, away_oid = KALSHI_GAMES[eid][:2]
        c.ns["market_id_by_outcome"].update({home_oid: eid, away_oid: eid})
        c.ns["event_id_by_outcome"].update({home_oid: eid, away_oid: eid})
        c.ns["live_event_ids"].add(eid)
    r = c.refresher

    async def acknowledge(frames):
        c.frames.extend(frames)
        return acknowledge_all(frames)

    gate = refuse_first_price_of(
        r, 1, acknowledge, hold=COHORT_HOLD if cohort else 0,
    )
    runs = record_recovery_runs(r)
    pending = count_pending(r)
    source = "kalshi_price_publish"
    values = iter(round(.30 + i / 1000, 3) for i in range(400))

    async def busy_flush(into):
        # B (outcome 3, home of game 2) — and, in the cohort, C (outcome 5,
        # home of game 3) — has new input on EVERY flush. The frame carries
        # B's blend, not the raw quote: time the first B frame this flush
        # published.
        before = len(gate.sent)
        c.batch[3] = (next(values), None, None)
        if cohort:
            c.batch[5] = (next(values), None, None)
        received = time.monotonic()
        assert await c.flush() is True
        published = [at for eid, at in gate.sent[before:] if eid == 2]
        if published:
            into.append(published[0] - received)
        await asyncio.sleep(PERIOD)

    try:
        await r.refresh([1, *sorted(busy_games)])
        assert {e for e, _ in gate.sent_at} == {1, *busy_games}, "rig: every game speaks"
        # Phase 1, the comparison arm: recovery stubbed out, B alone.
        r._start_normal_recovery = lambda: None
        stubbed, live = [], []
        for _ in range(8):
            await busy_flush(stubbed)
        del r._start_normal_recovery
        assert not gate.controls, "recovery was stubbed out"

        # Phase 2: A's single publication is refused, then A goes quiet.
        gate.arm()
        c.accept(1, .375)
        recovered = None
        for n in range(8):
            await busy_flush(live)
            if recovered is None and any(e == 1 for e, _ in gate.controls) and not (
                await owed_for(rig, source, 1)
            ):
                recovered = n
        task = r._normal_task
        if task is not None:
            await asyncio.wait_for(asyncio.shield(task), 2)

        assert gate.refused, "rig: A's publication was refused"
        assert (1, gate.refused[0]) in gate.controls, "A's control names its revision"
        assert recovered is not None, "A's intent never settled through 8 busy flushes"
        assert not pending, "premise: a flush with a batch never reaches refresh_pending"
        if cohort:
            assert overlapping(runs, gate.spans), (
                "premise: no recovery run overlapped a busy price send", runs,
            )
        # A busy game's price is on its way or delivered: recovery owes its
        # readers nothing for it.
        assert not [c for c in gate.controls if c[0] in busy_games], gate.controls
        assert len(stubbed) >= 6 and len(live) >= 6, (stubbed, live)
        assert max(live) < 1, (live, stubbed)
        assert median(live) - median(stubbed) < .1, (live, stubbed)
    finally:
        await r._close_normal_recovery()
        await r.drain_history()
        c.close()


# ---------------------------------------------------- attempt163 refusal cost

RETENTION_REFUSED = "normal price replay retention failed after PUBLISH"


async def test_sustained_retention_refusal_cost_is_bounded_per_event_per_flush(
    rig, consumer, monkeypatch, real_redis, caplog, default_preview_redis,
):
    """#10090 attempt163: Redis refuses EVERY replay-cache SET for six flushes
    of three busy games. Each price still reaches its readers; each refused
    price costs one EVAL and one log record in its own flush and owes its
    intent exactly once; recovery pays every intent with a price-free control
    sent once per (event, revision); nothing settles without a control ACK.

    Recovery is offered after EVERY publication (cooldown removed), the most
    sweeps this path can run. Synthetic rows on one machine: a regression
    bound on counts, not a production rate or latency forecast.
    """
    import logging

    from app.utils import live_push
    from app.utils.dnpl_authority_transport import decode_preview, is_authority_payload
    from tests.test_blend_preview_ledger_tsp1_10090 import _VirtualTimeoutClock

    # This case counts retention-refusal work under a healthy database, not
    # host scheduling. Keep every production budget and real DB/Redis action;
    # the companion COMMIT-held case explicitly expires the 250ms budget.
    deadlines = _VirtualTimeoutClock(monkeypatch)
    flushes, games = 6, (1, 2, 3)
    client = real_redis.client()
    subscriber = real_redis.client()
    pubsub = subscriber.pubsub()
    await pubsub.subscribe(*(event_channel(eid) for eid in games))
    for _ in games:
        await pubsub.get_message(timeout=1)
    original = live_push.frame_publish_command
    evals: list[tuple[int, int, str, int]] = []  # (flush, event, kind, rev)
    current = {"flush": -1}

    def refusing(frame, **kwargs):
        cmd = original(frame, **kwargs)
        evals.append((current["flush"], frame["event_id"], cmd[9], cmd[7]))
        return (*cmd[:8], "0", *cmd[9:])  # real Redis refuses SET EX 0; PUBLISH runs

    monkeypatch.setattr(live_push, "frame_publish_command", refusing)
    t = await setup(rig, consumer, monkeypatch)
    t.r._client = lambda: client
    t.r.min_refresh_interval_s = 0
    settled: list[tuple[int, int]] = []
    settle = t.r._settle_normal_recovery

    async def recorded_settle(acknowledged):
        settled.extend(acknowledged)
        return await settle(acknowledged)

    t.r._settle_normal_recovery = recorded_settle
    caplog.set_level(logging.WARNING, logger="app.tasks.live_blend_refresh")
    try:
        for n in range(flushes):
            current["flush"] = n
            t.r._normal_retry_at = 0
            for eid in games:
                t.accept(eid, round(.60 + n / 100 + eid / 1000, 3))
            await flush(t)
            await join(t.r)
        current["flush"] = flushes  # one quiet opportunity pays the last flush
        t.r._normal_retry_at = 0
        await t.r.refresh_pending()
        await join(t.r)
        received = []
        while (item := await pubsub.get_message(
            ignore_subscribe_messages=True, timeout=.2,
        )) is not None:
            payload = item["data"]
            if is_authority_payload(payload):
                receipt = decode_preview(item["channel"].decode(), payload, time.monotonic())
                payload = receipt.payload
            received.append(json.loads(payload))
        remaining = await owed(rig)
    finally:
        await close(t.r)
        await pubsub.aclose()
        await subscriber.aclose()
        await client.aclose()

    assert .25 in deadlines.durations and deadlines.expired == 0
    assert not deadlines.active
    prices = [e for e in evals if e[2] == "price"]
    controls = [e for e in evals if e[2] == "control"]
    records = [r for r in caplog.records if r.name == "app.tasks.live_blend_refresh"]
    refused = [r for r in records if r.getMessage().startswith(
        "live_blend_refresh[polymarket]: publish failed for event ")]
    detail = (prices, controls, [r.getMessage() for r in records], settled)
    # One EVAL per game per flush: the refusal is never retried in its flush.
    assert sorted((f, eid) for f, eid, _, _ in prices) == sorted(
        (n, eid) for n in range(flushes) for eid in games), detail
    assert len({(eid, rev) for _, eid, _, rev in prices}) == len(prices), detail
    # One log record per refused price, and nothing else at WARNING or above:
    # no incomplete publication, no retained recovery, no retained settlement.
    assert len(refused) == len(prices) == flushes * len(games), detail
    assert len(records) == len(refused), detail
    assert all(RETENTION_REFUSED in (r.exc_text or "") for r in refused), detail
    # Errors count the refused prices once; every control is acknowledged.
    assert t.r.stats["publish_errors"] == len(prices), (t.r.stats, detail)
    assert t.r.stats["published"] == len(controls), (t.r.stats, detail)
    # Each control names a refused price's revision, at most once per
    # (event, revision), at most one per game per sweep opportunity.
    price_revs = {(eid, rev) for _, eid, _, rev in prices}
    control_revs = [(eid, rev) for _, eid, _, rev in controls]
    assert set(control_revs) <= price_revs, detail
    assert len(control_revs) == len(set(control_revs)), detail
    for n in range(flushes + 1):
        per_game = [eid for f, eid, _, _ in controls if f == n]
        assert len(per_game) == len(set(per_game)), (n, detail)
    # No double settlement: a refused price never settles itself. Only a
    # control's ACK settles, and only its own revision.
    assert set(settled) <= set(control_revs), detail
    assert not remaining, (remaining, detail)
    # Delivery despite refusal: readers got every committed price and control.
    # DNPL preview prices also share this channel, but have no committed rev.
    assert sorted((f["event_id"], f["rev"][str(f["event_id"])]) for f in received
                  if f.get("p") is not None and not is_preview_frame(f)) == sorted(price_revs), detail
    assert sorted((f["event_id"], f["rev"][str(f["event_id"])]) for f in received
                  if f.get("reconcile_only")) == sorted(control_revs), detail
    print(
        "attempt163 sustained refusal:",
        f"flushes={flushes} games={len(games)} price_evals={len(prices)}",
        f"control_evals={len(controls)} warning_records={len(records)}",
        f"settled={len(settled)} max_record_bytes="
        f"{max(len(r.getMessage()) + len(r.exc_text or '') for r in records)}",
    )


async def test_control_ack_commit_deadline_keeps_debt_for_fresh_owner(
    rig, consumer, monkeypatch, real_redis, caplog,
):
    """Expire the exact 250ms budget while a real PostgreSQL COMMIT is blocked."""
    from tests.integration.test_live_blend_grouped_commit_8129_pg import seed
    from tests.test_blend_preview_ledger_tsp1_10090 import _VirtualTimeoutClock

    await seed(rig, count=1)
    async with rig.engine.begin() as db:
        await add(db, 1, 1)
    deadlines = _VirtualTimeoutClock(monkeypatch)
    client, subscriber = real_redis.client(), real_redis.client()
    pubsub = subscriber.pubsub()
    await pubsub.subscribe(event_channel(1))
    await pubsub.get_message(timeout=1)
    r, fresh, task = ref_for(consumer), None, None
    r._client = lambda: client
    holder = await rig.engine.connect()
    lock_id = await holder.scalar(text("SELECT pg_backend_pid()"))
    await holder.execute(text("SELECT pg_advisory_lock(10090, :key)"), {"key": lock_id})
    await holder.commit()  # session advisory lock stays held
    try:
        async with rig.engine.begin() as db:
            await db.execute(text(f"""
                CREATE FUNCTION dnpl_hold_ack_commit() RETURNS trigger LANGUAGE plpgsql AS $$
                BEGIN
                    PERFORM pg_advisory_xact_lock(10090, {lock_id});
                    RETURN OLD;
                END $$
            """))
            await db.execute(text("""
                CREATE CONSTRAINT TRIGGER dnpl_hold_ack_commit
                AFTER DELETE ON owed_chart_points DEFERRABLE INITIALLY DEFERRED
                FOR EACH ROW EXECUTE FUNCTION dnpl_hold_ack_commit()
            """))
        before = await owed(rig)
        task = asyncio.create_task(r._recover_normal_prices())
        # Observe COMMIT inside PostgreSQL before advancing logical time; do
        # not infer the phase from elapsed host time or a pre-commit callback.
        async with asyncio.timeout(3):
            while True:
                waiting = await holder.scalar(text("""
                    SELECT EXISTS (
                        SELECT 1 FROM pg_locks l JOIN pg_stat_activity a ON a.pid=l.pid
                        WHERE l.locktype='advisory' AND NOT l.granted
                          AND l.classid=10090 AND l.objid=:key
                          AND upper(a.query) LIKE 'COMMIT%'
                    )
                """), {"key": lock_id})
                if waiting:
                    break
                await asyncio.sleep(.002)
        first = await pubsub.get_message(ignore_subscribe_messages=True, timeout=.2)
        first_frame = json.loads(first["data"]) if first else None
        assert first_frame and first_frame.get("reconcile_only") is True
        assert first_frame.get("p") is None and first_frame["rev"] == {"1": 1}
        assert r.stats["published"] == 1 and await owed(rig) == before
        assert len(deadlines.active) == 1
        assert deadlines.active[0][0] - deadlines.now == .25
        deadlines.advance(.25)
        await asyncio.wait_for(task, 3)
        assert deadlines.expired == 1 and not deadlines.active
        assert await owed(rig) == before, "a canceled COMMIT falsely paid recovery custody"
        assert not r._normal_acked
        errors = [record for record in caplog.records if record.getMessage() ==
                  "live_blend_refresh[polymarket]: durable normal recovery retained"]
        assert len(errors) == 1 and isinstance(errors[0].exc_info[1], TimeoutError)
        await holder.execute(text("SELECT pg_advisory_unlock(10090, :key)"), {"key": lock_id})
        await holder.commit()
        # A fresh owner has no remembered ACK; the durable row alone supplies
        # a truthful price-free control and only its positive ACK pays the row.
        fresh = ref_for(consumer)
        fresh._client = lambda: client
        await fresh._recover_normal_prices()
        second = await pubsub.get_message(ignore_subscribe_messages=True, timeout=.2)
        second_frame = json.loads(second["data"]) if second else None
        assert second_frame == first_frame
        from app.routes.event_stream import _withdrawal_reconcile
        assert _withdrawal_reconcile(second_frame, 1, 1)
        assert fresh.stats["published"] == 1 and not await owed(rig)
        assert deadlines.expired == 1 and not deadlines.active
    finally:
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        await holder.execute(text("SELECT pg_advisory_unlock_all()"))
        await holder.close()
        if fresh is not None:
            await close(fresh)
        await close(r)
        await pubsub.aclose()
        await subscriber.aclose()
        await client.aclose()
