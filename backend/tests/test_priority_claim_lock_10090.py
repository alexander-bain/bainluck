"""#10090: the preview claim lock hands a receipt publication the lock before
stamp work (`app.utils.priority_lock.PriorityLock`). 2026-11-01 21:2xZ Kalshi:
a receipt preview queued up to 259 ms behind stamp publications."""

import asyncio

import pytest

from app.utils.priority_lock import PriorityLock


async def _holder(lock, order, name, hold=0.0, urgent=False):
    ctx = lock.urgent() if urgent else lock
    async with ctx:
        order.append(name)
        await asyncio.sleep(hold)


@pytest.mark.asyncio
async def test_an_urgent_waiter_goes_before_ordinary_waiters_that_asked_first():
    lock, order = PriorityLock(), []
    holder = asyncio.create_task(_holder(lock, order, "holder", 0.02))
    await asyncio.sleep(0)
    stamps = [asyncio.create_task(_holder(lock, order, f"stamp{i}")) for i in range(3)]
    await asyncio.sleep(0)
    receipt = asyncio.create_task(_holder(lock, order, "receipt", urgent=True))
    await asyncio.gather(holder, receipt, *stamps)
    assert order == ["holder", "receipt", "stamp0", "stamp1", "stamp2"]


@pytest.mark.asyncio
async def test_the_holder_in_progress_is_never_preempted():
    lock, order = PriorityLock(), []
    holder = asyncio.create_task(_holder(lock, order, "holder", 0.02))
    await asyncio.sleep(0)
    receipt = asyncio.create_task(_holder(lock, order, "receipt", urgent=True))
    await asyncio.sleep(0.005)
    assert order == ["holder"] and lock.locked()
    await asyncio.gather(holder, receipt)
    assert order == ["holder", "receipt"] and not lock.locked()


@pytest.mark.asyncio
async def test_ordinary_waiters_keep_fifo_order():
    lock, order = PriorityLock(), []
    holder = asyncio.create_task(_holder(lock, order, "holder", 0.01))
    await asyncio.sleep(0)
    waiters = [asyncio.create_task(_holder(lock, order, i)) for i in range(5)]
    await asyncio.gather(holder, *waiters)
    assert order == ["holder", 0, 1, 2, 3, 4]


@pytest.mark.asyncio
async def test_a_cancelled_waiter_leaves_the_queue_and_the_lock_moves_on():
    lock, order = PriorityLock(), []
    holder = asyncio.create_task(_holder(lock, order, "holder", 0.02))
    await asyncio.sleep(0)
    gone = asyncio.create_task(_holder(lock, order, "gone", urgent=True))
    later = asyncio.create_task(_holder(lock, order, "later"))
    await asyncio.sleep(0)
    gone.cancel()
    await asyncio.gather(holder, later)
    with pytest.raises(asyncio.CancelledError):
        await gone
    assert order == ["holder", "later"] and not lock.locked()


@pytest.mark.asyncio
async def test_a_timeout_while_waiting_frees_nothing_it_never_held():
    lock = PriorityLock()
    await lock.acquire()
    with pytest.raises(TimeoutError):
        async with asyncio.timeout(0.01):
            async with lock.urgent():
                pass
    assert lock.locked()
    lock.release()
    assert not lock.locked()
    async with lock:
        assert lock.locked()


@pytest.mark.asyncio
async def test_a_waiter_cancelled_as_it_is_handed_the_lock_passes_it_on():
    lock, order = PriorityLock(), []
    await lock.acquire()
    first = asyncio.create_task(lock.acquire(urgent=True))
    second = asyncio.create_task(_holder(lock, order, "second"))
    await asyncio.sleep(0)
    lock.release()          # hands the lock to `first`...
    first.cancel()          # ...which is cancelled before it runs
    with pytest.raises(asyncio.CancelledError):
        await first
    await asyncio.wait_for(second, 1)
    assert order == ["second"] and not lock.locked()


def test_releasing_an_unheld_lock_raises():
    with pytest.raises(RuntimeError):
        PriorityLock().release()


def test_the_refresher_creates_a_priority_claim_lock():
    from app.tasks.live_blend_refresh import _new_claim_lock

    assert isinstance(_new_claim_lock(), PriorityLock)


# ── the publish path: a receipt publication asks urgently ───────────────────

from tests.test_dnpl_admission_read_lock_10090 import setup_worker  # noqa: E402
from tests.test_dnpl_authority_registry_10090 import proposal  # noqa: E402
from tests.test_dnpl_redis_authority_10090 import rig as _rig_fixture  # noqa: E402
from tests.test_blend_preview_ledger_tsp1_10090 import redis_kwargs  # noqa: E402,F401

rig = _rig_fixture


@pytest.mark.asyncio
async def test_a_receipt_publication_goes_before_queued_stamp_publications(rig, monkeypatch):
    client, _, now, reg, worker = await setup_worker(rig, monkeypatch)
    reg.claim_lock = PriorityLock()
    entered, release, order = asyncio.Event(), asyncio.Event(), []
    original = reg.execute
    receipt_ops: list = []

    async def execute(frames, *args, **kwargs):
        order.append("receipt" if frames is receipt_ops else "stamp")
        if len(order) == 1:
            entered.set()
            await release.wait()
        return await original(frames, *args, **kwargs)

    monkeypatch.setattr(reg, "execute", execute)
    ops = await proposal(reg, client.execute_command, "kalshi", now=now)
    first = asyncio.create_task(worker._publish_previews(list(ops)))
    await asyncio.wait_for(entered.wait(), 1)
    stamp = asyncio.create_task(worker._publish_previews(list(ops)))
    await asyncio.sleep(0.01)

    receipt_ops.extend(ops)

    async def prepare():
        return receipt_ops

    receipt = asyncio.create_task(worker._publish_previews(
        [], prepare_frames=prepare, refused=lambda *_: None))
    await asyncio.sleep(0.01)
    release.set()
    await asyncio.gather(first, stamp, receipt)
    assert order == ["stamp", "receipt", "stamp"]


# ── yield_to_urgent (11/01 00:20Z: a receipt waited 575 ms behind one 579 ms settle hold) ──

async def _batch_holder(lock, order, units, gap=0.005):
    async with lock:
        for unit in range(units):
            if unit:
                await lock.yield_to_urgent()
            order.append(("batch", unit))
            await asyncio.sleep(gap)


@pytest.mark.asyncio
async def test_a_batch_hands_a_queued_receipt_the_lock_between_its_units_and_takes_it_back_first():
    lock, order = PriorityLock(), []
    batch = asyncio.create_task(_batch_holder(lock, order, 3))
    await asyncio.sleep(0)
    stamp = asyncio.create_task(_holder(lock, order, "stamp"))
    receipt = asyncio.create_task(_holder(lock, order, "receipt", urgent=True))
    await asyncio.gather(batch, stamp, receipt)
    assert order == [("batch", 0), "receipt", ("batch", 1), ("batch", 2), "stamp"]
    assert not lock.locked()


@pytest.mark.asyncio
async def test_with_no_urgent_waiter_a_yield_is_nothing():
    lock = PriorityLock()
    async with lock:
        assert await lock.yield_to_urgent() is False
        assert lock.locked()
    assert not lock.locked()


@pytest.mark.asyncio
async def test_a_holder_cancelled_while_yielded_gets_the_lock_back_before_it_unwinds():
    """Its `async with` releases on the way out; it must own the lock then, or it
    would free the urgent holder's lock out from under it."""
    lock, order = PriorityLock(), []
    entered = asyncio.Event()

    async def batch():
        async with lock:
            entered.set()
            await asyncio.sleep(0.005)
            await lock.yield_to_urgent()
            order.append("batch back")

    task = asyncio.create_task(batch())
    await entered.wait()
    receipt = asyncio.create_task(_holder(lock, order, "receipt", hold=0.02, urgent=True))
    await asyncio.sleep(0.01)            # the batch has yielded; the receipt holds the lock
    task.cancel()
    await asyncio.sleep(0.001)
    assert order == ["receipt"] and lock.locked(), "the receipt still holds it"
    with pytest.raises(asyncio.CancelledError):
        await task
    await receipt
    assert order == ["receipt"] and not lock.locked()


@pytest.mark.asyncio
async def test_the_ledger_yields_between_events_never_inside_one():
    from app.utils.blend_preview import LedgerRegistry

    lock, order = PriorityLock(), []
    registry = LedgerRegistry.__new__(LedgerRegistry)
    registry.claim_lock = lock
    seen = []

    async def mutate(item, call, stats, outcome=None):
        seen.append(item["event_id"])
        if len(seen) == 1:
            asyncio.get_running_loop().call_soon(
                lambda: asyncio.ensure_future(_holder(lock, order, "receipt", urgent=True)))
        await asyncio.sleep(0.002)
        order.append(item["event_id"])
        return []

    registry._mutate = mutate
    registry._alarm_batch = lambda: __import__("contextlib").nullcontext()
    async with lock:
        await registry.prepare([{"ledger_op": "x", "event_id": 1}, {"ledger_op": "x", "event_id": 1},
                                {"ledger_op": "x", "event_id": 2}], None, {})
    await asyncio.sleep(0.01)
    assert order == [1, 1, "receipt", 2]


def test_a_long_claim_hold_is_logged_with_what_it_held(caplog, monkeypatch):
    import logging

    import app.tasks.live_blend_refresh as lbr

    refresher = lbr.LiveBlendRefresher.__new__(lbr.LiveBlendRefresher)
    refresher.source, refresher._claim_holds, refresher._long_holds_logged = "polymarket", {}, 0
    monkeypatch.setattr(lbr, "_mono", lambda: 100.0)
    with caplog.at_level(logging.INFO, logger=lbr.logger.name):
        refresher._note_claim_hold("led_settle", 99.4195, [{"event_id": 7}, {"event_id": 7}, {"event_id": 9}])
        refresher._note_claim_hold("pub_frames", 99.9, [{"event_id": 7}])     # 100 ms: not long
    lines = [r.getMessage() for r in caplog.records if "long-claim-hold" in r.getMessage()]
    assert len(lines) == 1
    assert "label=led_settle held_ms=580 items=3 events=2" in lines[0]
    assert refresher._claim_holds["led_settle"][2] == pytest.approx(0.5805)
