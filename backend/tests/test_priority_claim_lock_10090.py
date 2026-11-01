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
