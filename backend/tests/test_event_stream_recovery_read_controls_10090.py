"""#10090 — an open page keeps receiving prices while a recovery read waits.

THE SHIP, IN A READER'S WORDS: a live event page that is already open keeps
showing each new committed price while the server re-reads which source
removals the page has covered, and a quiet page wakes as soon as that re-read
finishes — without the server doing extra work on every ordinary price.

WHAT IS PINNED (actual `_stream` route, the real hub `Subscription` mailbox and
the #837 in-process `Hub`; the coverage read itself is a controlled stand-in —
its real-PostgreSQL counterpart is
`integration/test_event_stream_recovery_read_price_flow_10090_pg.py`):

- attempt133 (`test_recovery_controls.py`, assertions verbatim): repeated
  confirmations and hub generations keep at most two coverage reads per stream
  and schedule one later read; a catch-up never replays a frame older than one
  sent during the read; a recovery read is cancelled and joined on every exit;
  a completed recovery read wakes an idle stream at the production 1 s mailbox
  wait without losing a frame that arrives in the same turn.
- attempt136 (Latency T1, new here): once no coverage read is owned, a steady
  frame is read inline — no Task and no `asyncio.wait` per frame. The owned
  path stays for in-flight reads only.

Cancellation on both paths lives in `test_event_stream_lost_cancel_10090.py`:
the inline strawman (unchanged) and the owned-path positive (attempt136's
corrected test).

BOUNDED WAITS. Every wait here is bounded and watches the stream task: a stream
that ended first re-raises its own error, and one still running at the bound is
cancelled and awaited before the failure is reported.
"""

import asyncio
import json
from unittest.mock import AsyncMock

import pytest

from app.routes import event_stream as route
from app.utils import live_fanout
from tests.test_folded_event_stream_invalidation_837 import Hub, Request, frame

pytestmark = pytest.mark.asyncio


async def until(predicate, task, what, within=1.0, poll=0.001):
    """Poll `predicate` for at most `within` s while the stream `task` runs."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + within
    while not predicate():
        if task.done():
            task.result()  # a stream that died says why, not "timed out"
            raise AssertionError(f"{what}: the stream ended without it")
        if loop.time() >= deadline:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            raise AssertionError(f"{what}: not within {within} s")
        await asyncio.sleep(poll)


def data(chunks, kind):
    return [
        json.loads(c.split("data: ", 1)[1])
        for c in chunks
        if c.startswith("event: " + kind + "\n")
    ]


def control(ids, n):
    return {
        "event_id": 1,
        "custody_id": "state:" + str(n),
        "removal_rev": {str(i): n for i in ids},
    }


@pytest.mark.parametrize("initial_blocked", [False, True])
async def test_repeated_confirmations_and_generations_keep_two_read_bound(
    monkeypatch, initial_blocked
):
    hub = Hub()
    release = asyncio.Event()
    reads = []
    chunks = []
    active = 0
    peak = 0
    latest = []

    async def coverage(eid, ids):
        nonlocal active, peak
        reads.append(list(ids))
        number = len(reads)
        active += 1
        peak = max(peak, active)
        try:
            if number == 2 or (number == 1 and initial_blocked):
                await release.wait()
            return control(ids, number)
        finally:
            active -= 1

    async def retained(ids):
        latest.append(list(ids))
        return []

    monkeypatch.setattr(live_fanout, "fanout", lambda: hub)
    monkeypatch.setattr(route, "_current_reconcile", coverage)
    monkeypatch.setattr(route, "latest_frames", retained)
    monkeypatch.setattr(route, "FRAME_WAIT_S", 0.01)

    async def collect():
        async for c in route._stream(1, Request(), [2, 3]):
            chunks.append(c)

    task = asyncio.create_task(collect())
    try:
        await until(lambda: len(reads) == 1, task, "initial read")
        hub.subscriptions["live:event:2"].offer(live_fanout.CONFIRMED)
        await until(lambda: len(reads) == 2, task, "confirmation read")
        # Repeated obligations while a read is blocked, without overflowing
        # the production mailbox (8 slots) and legitimately forcing reconnect.
        for _ in range(4):
            hub.subscriptions["live:event:2"].offer(live_fanout.CONFIRMED)
        hub.subscriptions["live:event:3"].offer(live_fanout.CONFIRMED)
        hub.subscriptions["live:event:3"].offer(json.dumps(frame(3)))
        hub.subscriptions["live:event:2"].offer(live_fanout.Recovery(1))
        hub.subscriptions["live:event:2"].offer(live_fanout.Recovery(2))
        await until(
            lambda: len(data(chunks, "resync")) == 2
            and bool(data(chunks, "probability")),
            task,
            "both resyncs and the price while the read is held",
        )
        assert len(reads) == 2 and peak == (2 if initial_blocked else 1)
        release.set()
        await until(
            lambda: len(reads) == 3 and len(data(chunks, "reconcile")) >= 3,
            task,
            "the one later read",
        )
        assert reads == [[1, 2, 3], [2], [1, 2, 3]]
        assert latest == [[1, 2, 3], [2], [2, 3]]
        assert [x["generation"] for x in data(chunks, "resync")] == [1, 2]
        assert data(chunks, "reconcile")[-1]["removal_rev"] == {"1": 3, "2": 3, "3": 3}
        assert peak <= 2
    finally:
        release.set()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        assert active == 0 and route._open_connections == 0


async def test_catchup_does_not_replay_older_than_live_frame_sent_during_read(
    monkeypatch,
):
    hub = Hub()
    entered = asyncio.Event()
    release = asyncio.Event()
    reads = 0
    chunks = []
    latest_calls = 0

    async def coverage(eid, ids):
        nonlocal reads
        reads += 1
        if reads == 2:
            entered.set()
            await release.wait()
        return control(ids, reads)

    async def latest(ids):
        nonlocal latest_calls
        latest_calls += 1
        return [] if latest_calls == 1 else [(1, json.dumps(frame(1, rev={"1": 10})))]

    monkeypatch.setattr(live_fanout, "fanout", lambda: hub)
    monkeypatch.setattr(route, "_current_reconcile", coverage)
    monkeypatch.setattr(route, "latest_frames", latest)
    monkeypatch.setattr(route, "FRAME_WAIT_S", 0.01)

    async def collect():
        async for c in route._stream(1, Request()):
            chunks.append(c)

    task = asyncio.create_task(collect())
    try:
        await until(lambda: data(chunks, "reconcile"), task, "initial coverage")
        hub.subscriptions["live:event:1"].offer(live_fanout.CONFIRMED)
        await until(entered.is_set, task, "confirmation read entered")
        hub.subscriptions["live:event:1"].offer(json.dumps(frame(1, rev={"1": 11})))
        await until(lambda: data(chunks, "probability"), task, "price during the read")
        release.set()
        await until(
            lambda: len(data(chunks, "reconcile")) == 2, task, "confirmation coverage"
        )
        hub.subscriptions["live:event:1"].offer(json.dumps(frame(1, rev={"1": 12})))
        await until(
            lambda: len(data(chunks, "probability")) >= 2, task, "price after the read"
        )
        assert [x["rev"] for x in data(chunks, "probability")] == [{"1": 11}, {"1": 12}]
    finally:
        release.set()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.parametrize(
    "exit_kind", ["cancel", "disconnect", "terminal", "failed_read"]
)
async def test_recovery_read_is_cancelled_joined_on_exit(monkeypatch, exit_kind):
    hub = Hub()
    entered = asyncio.Event()
    release = asyncio.Event()
    finished = asyncio.Event()
    chunks = []
    reads = 0
    leaving = False

    class Reader:
        async def is_disconnected(self):
            return leaving

    async def coverage(eid, ids):
        nonlocal reads
        reads += 1
        if reads == 1:
            return control(ids, 1)
        entered.set()
        try:
            await release.wait()
            if exit_kind == "failed_read":
                raise ConnectionError("controlled recovery error")
            return control(ids, 2)
        finally:
            finished.set()

    monkeypatch.setattr(live_fanout, "fanout", lambda: hub)
    monkeypatch.setattr(route, "_current_reconcile", coverage)
    monkeypatch.setattr(route, "latest_frames", AsyncMock(return_value=[]))
    monkeypatch.setattr(route, "FRAME_WAIT_S", 0.01)

    async def collect():
        async for c in route._stream(1, Reader()):
            chunks.append(c)

    task = asyncio.create_task(collect())
    try:
        await until(lambda: data(chunks, "reconcile"), task, "initial coverage")
        hub.subscriptions["live:event:1"].offer(live_fanout.Recovery(1))
        await until(entered.is_set, task, "recovery read entered")
        if exit_kind == "cancel":
            task.cancel()
        elif exit_kind == "disconnect":
            leaving = True
        elif exit_kind == "terminal":
            hub.subscriptions["live:event:1"].offer(
                json.dumps(frame(1, status="completed"))
            )
        else:
            release.set()
        await until(task.done, task, f"stream exit ({exit_kind})")
        assert finished.is_set() and len(data(chunks, "reconcile")) == 1
        assert hub.released == ["live:event:1"] and route._open_connections == 0
    finally:
        release.set()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.parametrize("folded", [False, True])
@pytest.mark.parametrize("simultaneous_frame", [False, True])
async def test_completed_recovery_wakes_idle_stream_without_losing_mailbox_frame(
    monkeypatch, folded, simultaneous_frame
):
    # Keep the production1s mailbox timeout. A completed query must wake it,
    # rather than relying on a later quote or a shortened test-only timeout.
    hub = Hub()
    entered = asyncio.Event()
    release = asyncio.Event()
    reads = 0
    chunks = []
    latest_calls = 0
    target = 2 if folded else 1

    async def coverage(eid, ids):
        nonlocal reads
        reads += 1
        if reads == 2:
            entered.set()
            await release.wait()
        return control(ids, reads)

    async def retained(ids):
        nonlocal latest_calls
        latest_calls += 1
        return (
            []
            if latest_calls == 1
            else [(target, json.dumps(frame(target, rev={str(target): 10})))]
        )

    monkeypatch.setattr(live_fanout, "fanout", lambda: hub)
    monkeypatch.setattr(route, "_current_reconcile", coverage)
    monkeypatch.setattr(route, "latest_frames", retained)
    assert route.FRAME_WAIT_S == 1

    async def collect():
        async for c in route._stream(1, Request(), [2] if folded else []):
            chunks.append(c)

    task = asyncio.create_task(collect())
    try:
        await until(lambda: data(chunks, "reconcile"), task, "initial coverage")
        hub.subscriptions[f"live:event:{target}"].offer(live_fanout.CONFIRMED)
        await until(entered.is_set, task, "confirmation read entered")
        release.set()
        if simultaneous_frame:
            hub.subscriptions[f"live:event:{target}"].offer(
                json.dumps(frame(target, rev={str(target): 11}))
            )
        async with asyncio.timeout(0.2):
            await until(
                lambda: len(data(chunks, "reconcile")) == 2
                and bool(data(chunks, "probability")),
                task,
                "woken catch-up",
            )
            if simultaneous_frame:
                await until(
                    lambda: any(
                        x["rev"] == {str(target): 11}
                        for x in data(chunks, "probability")
                    ),
                    task,
                    "the same-turn mailbox frame",
                )
        values = [x["rev"][str(target)] for x in data(chunks, "probability")]
        assert values == sorted(set(values))
        assert values[-1] == (11 if simultaneous_frame else 10)
        assert reads == 2 and latest_calls == 2
    finally:
        release.set()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        assert route._open_connections == 0
        pending = [
            t
            for t in asyncio.all_tasks()
            if t is not asyncio.current_task()
            and not t.done()
            and "_FoldSubscription.next" in getattr(t.get_coro(), "__qualname__", "")
        ]
        assert not pending


async def test_steady_frames_take_the_inline_read_with_no_task_per_frame(monkeypatch):
    """attempt136 (Latency T1): with no coverage read owned, a frame costs no Task.

    attempt133 created a mailbox Task plus an `asyncio.wait` for EVERY frame for
    the whole stream life, though the race it buys only matters while a read
    is in flight. One warm-up frame drains the mailbox Task the initial read
    legitimately left behind; after it, eight steady frames must each arrive in
    order with zero `asyncio.create_task` and zero `asyncio.wait` calls. A
    singleton stream: the folded reader's per-contributor Tasks predate #10090
    and are not this path.
    """
    hub = Hub()
    chunks = []

    async def coverage(eid, ids):
        return control(ids, 1)

    monkeypatch.setattr(live_fanout, "fanout", lambda: hub)
    monkeypatch.setattr(route, "_current_reconcile", coverage)
    monkeypatch.setattr(route, "latest_frames", AsyncMock(return_value=[]))

    async def collect():
        async for c in route._stream(1, Request()):
            chunks.append(c)

    task = asyncio.create_task(collect())
    try:
        await until(lambda: data(chunks, "reconcile"), task, "initial coverage")
        mailbox = hub.subscriptions["live:event:1"]
        mailbox.offer(json.dumps(frame(1, rev={"1": 1})))
        await until(
            lambda: len(data(chunks, "probability")) == 1, task, "warm-up frame"
        )
        created = []
        waits = []
        real_create_task = asyncio.create_task
        real_wait = asyncio.wait

        def counting_create_task(coro, *args, **kwargs):
            created.append(getattr(coro, "__qualname__", type(coro).__name__))
            return real_create_task(coro, *args, **kwargs)

        async def counting_wait(fs, *args, **kwargs):
            waits.append(len(fs))
            return await real_wait(fs, *args, **kwargs)

        with monkeypatch.context() as counting:
            counting.setattr(asyncio, "create_task", counting_create_task)
            counting.setattr(asyncio, "wait", counting_wait)
            for n in range(2, 10):
                mailbox.offer(json.dumps(frame(1, rev={"1": n})))
                await until(
                    lambda: len(data(chunks, "probability")) == n,
                    task,
                    f"steady frame {n}",
                )
            per_frame = {"create_task": list(created), "wait": list(waits)}
        assert [x["rev"] for x in data(chunks, "probability")] == [
            {"1": n} for n in range(1, 10)
        ]
        assert per_frame == {"create_task": [], "wait": []}, per_frame
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        assert route._open_connections == 0
