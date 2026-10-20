"""169: a recovery read refused only by the 4-entry recovery share waits for a release.

The wait is inside the read's own request deadline, holds no slot, entry or load,
and is counted: admitted plus waiting recovery reads never exceed MAX_PENDING.

VIRTUAL TIME (integrator 0606Z: the deadline test failed 2 of 6 at load 15-18).
Every test here runs on `VirtualClockLoop`, and the projector reads that loop's
clock: time stands still while anything is runnable and jumps to the next timer
when nothing is. A deadline measures exactly and a runner stall moves no clock.
"""
import asyncio
import time
import pytest
from app.utils import folded_live_quote as fq
from tests._virtual_clock_loop import VirtualClockLoop, VirtualClockPolicy
from tests.test_normal_recovery_projection159 import notice, quote

pytestmark = pytest.mark.asyncio


@pytest.fixture(scope="module")
def event_loop_policy():
    return VirtualClockPolicy()


class Gates:
    """One gate per event, so a test can release exactly one recovery entry."""

    def __init__(self, open_=()):
        self.gates, self.started, self.open = {}, [], set(open_)

    def gate(self, eid):
        return self.gates.setdefault(eid, asyncio.Event())

    async def load(self, eid, origin, rev):
        self.started.append(eid)
        if eid not in self.open:
            await self.gate(eid).wait()
        return {**quote(), "event_id": eid, "blend_fold_revision": {str(eid): rev}}

    def release_all(self):
        self.open.update(range(1, 100))
        for event in self.gates.values():
            event.set()


async def settle(n=30):
    for _ in range(n):
        await asyncio.sleep(0)


def recovery_keys(projector, eid=None):
    return [key for key in projector._pending if key[-1] and (eid is None or key[0] == eid)]


async def full_share(monkeypatch, gates):
    monkeypatch.setattr(fq, "load_folded_quote", gates.load)
    projector = fq.FoldedQuoteProjector()
    held = [asyncio.create_task(projector.project(eid, notice(eid), fresh=True)) for eid in range(1, 5)]
    await settle()
    assert len(recovery_keys(projector)) == fq.RECOVERY_MAX_PENDING and gates.started == [1]
    return projector, held


async def drain(projector, gates, *tasks):
    gates.release_all()
    await asyncio.gather(*tasks, return_exceptions=True)
    assert not projector._pending and projector._recovery_waiting == 0


@pytest.mark.parametrize("offset", range(16))
async def test_a_release_racing_the_refusal_still_admits_the_waiter(monkeypatch, offset):
    """The deciding control: the fifth read arrives at every loop step of one release.

    Whichever step the release lands on — before the count, between the count and
    the wait, or after — the fifth read is admitted on that release, not at its deadline.
    """
    gates = Gates(); projector, held = await full_share(monkeypatch, gates)
    gates.gate(1).set()  # exactly one recovery entry (event 1) starts leaving
    for _ in range(offset):
        await asyncio.sleep(0)
    fifth = asyncio.create_task(projector.project(5, notice(5), fresh=True))
    await settle()
    assert not recovery_keys(projector, 1), "event 1 released"
    assert recovery_keys(projector, 5), f"offset {offset}: the release was lost; fifth still waiting"
    assert projector._recovery_waiting == 0 and len(recovery_keys(projector)) == 4
    await drain(projector, gates, *held, fifth)
    assert (await fifth)["event_id"] == 5


async def test_waiters_are_counted_and_bounded_by_max_pending(monkeypatch):
    gates = Gates(); projector, held = await full_share(monkeypatch, gates)
    waiting = [asyncio.create_task(projector.project(eid, notice(eid), fresh=True)) for eid in range(5, 9)]
    await settle()
    assert projector._recovery_waiting == fq.MAX_PENDING - fq.RECOVERY_MAX_PENDING == 4
    assert not any(task.done() for task in waiting)
    # Admitted plus waiting is already MAX_PENDING: the next one is refused at once.
    assert await projector.project(9, notice(9), fresh=True) is None
    assert 9 not in gates.started and 9 not in projector._recovery_retry_after
    # Waiters hold no entry: ordinary readers still get all of theirs.
    ordinary = [asyncio.create_task(projector.project(eid, notice(eid))) for eid in range(21, 25)]
    await settle()
    assert len(projector._pending) == fq.MAX_PENDING and 21 in gates.started
    await drain(projector, gates, *held, *waiting, *ordinary)
    assert [r["event_id"] for r in await asyncio.gather(*waiting)] == [5, 6, 7, 8]


async def test_a_waiter_that_reaches_its_deadline_records_nothing_and_stays_ended(monkeypatch):
    monkeypatch.setattr(fq, "PROJECTION_TIMEOUT_S", 0.05)
    gates = Gates(); projector, held = await full_share(monkeypatch, gates)
    started = asyncio.get_running_loop().time()
    assert await projector.project(5, notice(5), fresh=True) is None
    assert asyncio.get_running_loop().time() - started < 0.2
    # It never loaded: no failure, no spend, no load start, no entry.
    assert projector._recovery_waiting == 0 and 5 not in projector._recovery_retry_after
    assert 5 not in gates.started and not recovery_keys(projector, 5)
    # A later release cannot revive the ended request.
    gates.gate(1).set()
    await settle()
    assert not recovery_keys(projector, 5) and 5 not in gates.started
    await drain(projector, gates, *held)


async def test_a_cancelled_waiter_releases_its_count_and_takes_nothing(monkeypatch):
    gates = Gates(); projector, held = await full_share(monkeypatch, gates)
    waiter = asyncio.create_task(projector.project(5, notice(5), fresh=True))
    other = asyncio.create_task(projector.project(6, notice(6), fresh=True))
    await settle()
    assert projector._recovery_waiting == 2
    waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter
    assert projector._recovery_waiting == 1
    gates.gate(1).set()  # the release goes to the waiter still present
    await settle()
    assert recovery_keys(projector, 6) and not recovery_keys(projector, 5)
    assert 5 not in projector._recovery_retry_after and 5 not in gates.started
    await drain(projector, gates, *held, other)


async def test_a_waiter_cancelled_after_its_wakeup_does_not_take_the_entry(monkeypatch):
    gates = Gates(); projector, held = await full_share(monkeypatch, gates)
    waiter = asyncio.create_task(projector.project(5, notice(5), fresh=True))
    other = asyncio.create_task(projector.project(6, notice(6), fresh=True))
    await settle()
    released = projector._recovery_released
    gates.gate(1).set()
    for _ in range(30):  # cancel in the same step the wakeup is delivered
        if released.is_set():
            waiter.cancel()
            break
        await asyncio.sleep(0)
    assert released.is_set()
    await asyncio.gather(waiter, return_exceptions=True)
    await settle()
    assert not recovery_keys(projector, 5) and recovery_keys(projector, 6)
    assert projector._recovery_waiting == 0
    await drain(projector, gates, *held, other)


async def test_the_request_deadline_includes_the_wait(monkeypatch):
    # The held reads keep their slot past the fifth's deadline. With one shared
    # budget, event 2's own deadline would land first and correctly free the slot
    # for event 5 inside its remaining time — the premise, not a defect.
    monkeypatch.setattr(fq, "PROJECTION_TIMEOUT_S", 10)
    gates = Gates(); projector, held = await full_share(monkeypatch, gates)
    monkeypatch.setattr(fq, "PROJECTION_TIMEOUT_S", 0.3)
    loop = asyncio.get_running_loop(); began = loop.time()
    assert isinstance(loop, VirtualClockLoop)
    fifth = asyncio.create_task(projector.project(5, notice(5), fresh=True))
    await asyncio.sleep(0.15)
    gates.gate(1).set()  # admitted after 0.15 s, then queued behind event 2 (held)
    time.sleep(0.3)  # a runner stall: on a wall clock this alone breaks the bound below
    assert await fifth is None
    elapsed = loop.time() - began
    # One deadline from the request: not 0.15 s of wait plus a fresh 0.3 s load budget.
    assert 0.25 < elapsed < 0.4, elapsed
    retry = projector._recovery_retry_after[5]
    assert retry.failures == 1 and not retry.spent and 5 not in gates.started
    await drain(projector, gates, *held)


async def test_a_waiter_that_joins_later_work_still_leaves_by_its_own_deadline(monkeypatch):
    """A later read of the same key can take the freed entry before the waiter resumes.

    The waiter then joins work bounded by that later request's deadline. It must still
    return by its own, and its departure must not cancel the later reader's shared work.
    """
    monkeypatch.setattr(fq, "PROJECTION_TIMEOUT_S", 0.3)
    joined_at = []
    for offset in range(12):  # the release lands at every loop step before the later read
        gates = Gates(); projector, held = await full_share(monkeypatch, gates)
        loop = asyncio.get_running_loop(); began = loop.time()
        waiter = asyncio.create_task(projector.project(5, notice(5), fresh=True))
        await settle()
        assert projector._recovery_waiting == 1
        await asyncio.sleep(0.2)
        gates.gate(1).set()
        for _ in range(offset):
            await asyncio.sleep(0)
        later = asyncio.create_task(projector.project(5, notice(5), fresh=True))
        assert await waiter is None
        elapsed = loop.time() - began
        assert elapsed < 0.4, f"offset {offset}: the waiter took {elapsed:.3f}s against its 0.3 s deadline"
        if recovery_keys(projector, 5):  # the waiter joined the later read's work and left
            joined_at.append(offset)
            work = projector._pending[recovery_keys(projector, 5)[0]]
            assert not later.done() and work.waiters == 1 and not work.task.cancelling()
        await drain(projector, gates, *held, later)
        if joined_at and joined_at[-1] == offset:
            assert (await later)["event_id"] == 5, "the later reader's shared work survived"
    assert joined_at, "no offset reached the join; the sweep no longer decides this"


async def test_a_waited_read_spends_from_its_admitted_load_start(monkeypatch):
    """Spend accounting reads the load's own start, never the wait's start."""
    gates = Gates(); projector, held = await full_share(monkeypatch, gates)
    loop = asyncio.get_running_loop()
    async def load(eid, origin, rev):
        if eid == 5:
            gates.started.append(5)
            return None
        return await gates.load(eid, origin, rev)
    monkeypatch.setattr(fq, "load_folded_quote", load)
    arrived = loop.time()
    # Event 5 has an open retry whose restoration opened just after the request arrived.
    projector._recovery_retry_after[5] = fq._RecoveryRetry(2, arrived - 1, arrived - 1, arrived + 0.05)
    fifth = asyncio.create_task(projector.project(5, notice(5), fresh=True))
    await asyncio.sleep(0.1)
    assert not fifth.done() and projector._recovery_waiting == 1
    gates.release_all()
    assert await fifth is None
    retry = projector._recovery_retry_after[5]
    assert gates.started.count(5) == 1
    assert retry.spent, "a load started after the opening is spent, whatever the request's arrival"
    await drain(projector, gates, *held)


async def test_a_backoff_that_closes_during_the_wait_is_honoured_after_it(monkeypatch):
    gates = Gates(); projector, held = await full_share(monkeypatch, gates)
    fifth = asyncio.create_task(projector.project(5, notice(5), fresh=True))
    await settle()
    assert projector._recovery_waiting == 1
    # A sibling read of event 5 failed meanwhile and closed its backoff.
    now = asyncio.get_running_loop().time()
    projector._recovery_retry_after[5] = fq._RecoveryRetry(1, now + 10, now + 10)
    gates.gate(1).set()
    await settle()
    # Refused on its wake by the backoff, not admitted to queue for a slot.
    assert fifth.done() and fifth.result() is None
    assert 5 not in gates.started and not recovery_keys(projector, 5)
    await drain(projector, gates, *held)
