"""#10090 review (43455) — the final drain never refreshes beside the flush
it replaces.

The consumer's shutdown cancels the periodic flush and then drains. The drain
used to start at once, joining the flush only after it, so a flush still
unwinding its stamp (a cancelled session rolling back) shared the refresher —
its throttle/retry sets, staged receipts and snapshot slots — with the drain's
own refresh. Drives the REAL Kalshi consumer on the #9462 rig with a refresher
whose cancelled refresh takes a moment to unwind; the premise (the cancel
landed inside a refresh) is asserted so the guard cannot pass vacuously.

The second half covers the refresher: a cancelled stamp of four or fewer due
events stays owed for the hand-off, with the retry/deferred work it took —
its prices committed and left the buffer, so nothing else re-asks for it.
"""

from __future__ import annotations

import asyncio

import pytest

import app.tasks.live_blend_refresh as lbr
from tests.test_ws_admission_mapped_legs_9462 import (
    _arm,
    _install_quiet_socket,
    _install_session,
    _timing,
)

pytestmark = pytest.mark.asyncio

UNWIND = 0.05


class _SlowUnwind(lbr.LiveBlendRefresher):
    instances: list = []

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.calls = 0
        self.running = 0
        self.most_running = 0
        self.cancelled = 0
        _SlowUnwind.instances.append(self)

    async def refresh_pending(self, *, flush_started=None):
        self.calls += 1
        first = self.calls == 1
        self.running += 1
        self.most_running = max(self.most_running, self.running)
        try:
            # The first (periodic) flush is still refreshing at the recycle.
            await asyncio.sleep(2.0 if first else 0)
        except asyncio.CancelledError:
            self.cancelled += 1
            await asyncio.sleep(UNWIND)  # a rollback still unwinding
            raise
        finally:
            self.running -= 1
        return self.stats


async def test_the_final_drain_waits_for_the_cancelled_flush(monkeypatch):
    module, consumer, slate = _arm(monkeypatch, "kalshi")
    monkeypatch.setattr(_SlowUnwind, "instances", [])
    monkeypatch.setattr(lbr, "LiveBlendRefresher", _SlowUnwind)
    monkeypatch.setattr(module, "PRICE_FLUSH_SECONDS", 0.01)
    _install_quiet_socket(monkeypatch)
    _timing(monkeypatch, module, refresh=0.3)
    _install_session(monkeypatch, slate, lambda n: [])

    stats = await asyncio.wait_for(consumer(), timeout=5)

    (refresher,) = _SlowUnwind.instances
    assert refresher.cancelled == 1, "premise: the recycle cancelled a refresh"
    assert refresher.calls >= 2, "premise: the final drain refreshed too"
    assert refresher.most_running == 1, "the drain refreshed beside the flush"
    assert stats["loops_unreaped"] == 0


class _HeldBatch(lbr.LiveBlendRefresher):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.entered = asyncio.Event()

    async def _prepare_groups(self, event_ids):
        return {}

    async def _refresh_batch(self, event_ids, now, **_kw):
        self.entered.set()
        await asyncio.Event().wait()


@pytest.mark.parametrize("n", [1, 4, 5])
async def test_a_cancelled_stamp_stays_owed_with_the_work_it_took(n):
    """Both arms: <=4 due events take the single-batch path, more take the
    grouped path that already kept them owed. Event 1 was a queued lock retry
    and event 2 a throttled price this stamp took; both stay owed too."""
    r = _HeldBatch("kalshi")
    r._lock_retry = {1}
    r._throttle_deferred = {2}
    fresh = list(range(3, 3 + max(n - 2, 1)))
    due = {1, 2, *fresh}
    if n == 1:
        r._lock_retry, r._throttle_deferred, due = set(), set(), {3}
        fresh = [3]
    if n == 5:
        assert len(due) == 5
    stamp = asyncio.create_task(r.refresh(fresh))
    await asyncio.wait_for(r.entered.wait(), 2)
    # Premise: the stamp took every owed id out of the pending sets.
    assert r.pending_event_ids() == frozenset()
    stamp.cancel()
    with pytest.raises(asyncio.CancelledError):
        await stamp
    assert r.pending_event_ids() == frozenset(due)
    if 1 in due:
        assert 1 in r._lock_retry, "a lock retry stays immediately due"
    assert not r._failed_hold_until, "a cancel is not a failure hold"
    handed = lbr.hand_off_pending(r)
    try:
        assert handed == len(due)
    finally:
        lbr._pending_handoff.pop("kalshi", None)
