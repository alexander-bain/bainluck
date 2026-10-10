"""#10090 — a Kalshi phase's blend stamp runs while the next phase writes.

Executes the production `flush_prices` on the #10655 rig with a refresher
whose stamp can be held. Proves ordering and lifetime, not production latency:
the next game's write commits while the previous game's stamp is still
running; refreshes never overlap each other; a cancelled flush cancels its
stamp. #10090 cross-flush: a stamp may outlive the flush that started it — it
is the run's (`prices.stamping`), joined by the next flush that needs it, by a
scope change and before the final drain (`join_stamp`), never left running.
"""
import asyncio

import pytest

from app.tasks.kalshi_ws import _KalshiPriceOwner
from tests.test_kalshi_game_isolation_10655 import rig

pytestmark = pytest.mark.asyncio


def held_refresher(r, hold_ids=(100,)):
    gate = asyncio.Event()
    calls = {"started": [], "finished": [], "cancelled": [], "running": 0,
             "most_running": 0, "adopted": []}

    class Refresher:
        def pending_event_ids(self):
            return frozenset()

        def adopt_pending(self, ids):
            calls["adopted"].append(set(ids))

        def admit_fresh(self, ids, **kwargs):
            # #10090: a refresher that refuses admission keeps the flush's
            # queue-then-launch contract these tests pin; admission itself
            # is proven on the real refresher (test_kalshi_fresh_admission).
            return frozenset()

        async def publish_market_changes(self, s):
            r.trace.append(("publish", tuple(s.rows)))

        async def refresh(self, ids, **kwargs):
            key = tuple(sorted(ids))
            calls["started"].append(key)
            calls["running"] += 1
            calls["most_running"] = max(calls["most_running"], calls["running"])
            try:
                if key == tuple(hold_ids):
                    await gate.wait()
                else:
                    await asyncio.sleep(0)
            except asyncio.CancelledError:
                calls["cancelled"].append(key)
                raise
            finally:
                calls["running"] -= 1
            calls["finished"].append(key)
            r.trace.append(("refresh", key))

        async def refresh_pending(self, **kwargs):
            r.trace.append(("pending",))

    r.ns["blend_refresher"] = Refresher()
    return gate, calls


async def test_the_next_game_commits_while_the_previous_stamp_runs():
    r = rig()
    r.release.set()  # game 200's write is not held; game 100's STAMP is
    gate, calls = held_refresher(r)
    flush = asyncio.create_task(r.flush())
    # Game 200's write began while game 100's stamp is still running.
    await asyncio.wait_for(r.entered.wait(), 2)
    for _ in range(20):
        await asyncio.sleep(0)
    assert calls["started"] == [(100,)] and calls["finished"] == []
    assert r.committed[:3] == [1, 2, 3], "game 200 committed beside 100's stamp"
    assert ("publish", (3,)) in r.trace
    # The refresher still runs one refresh at a time, in phase order.
    assert calls["started"] == [(100,)]
    assert not flush.done(), "a flush never returns ahead of its stamp"
    gate.set()
    assert await asyncio.wait_for(flush, 2) is True
    assert calls["started"] == [(100,), (200,)]
    assert calls["finished"] == [(100,), (200,)]
    assert calls["most_running"] == 1
    assert r.committed == [1, 2, 3, 9] and not r.batch


class _HeldOverlapsEverything(set):
    """A held-event set that overlaps every phase while it holds anything."""

    def isdisjoint(self, other):
        return not self and super().isdisjoint(other)


class _SerialOwner(_KalshiPriceOwner):
    """The run's stamp owner with its same-event fence widened to every event:
    any stamp it holds overlaps the next phase, so the flush joins that stamp
    before writing. That is the serial flush, at the persistent-owner boundary
    the flush actually consults (`prices.stamping_events`)."""

    @property
    def stamping_events(self):
        return self._held

    @stamping_events.setter
    def stamping_events(self, events):
        self._held = _HeldOverlapsEverything(events)


async def test_strawman_the_serial_owner_holds_the_next_write():
    """The rig can tell: with the serial owner, game 200's disjoint write does
    not begin while game 100's stamp is held, and starts once it is released."""
    r = rig()
    r.release.set()
    r.ns["prices"] = _SerialOwner()
    gate, calls = held_refresher(r)
    flush = asyncio.create_task(r.flush())
    for _ in range(20):
        await asyncio.sleep(0)
    assert calls["started"] == [(100,)] and calls["finished"] == []
    assert r.ns["prices"].stamping_events == {100}, "the owner holds only game 100"
    assert not r.entered.is_set() and r.committed == [1, 2]
    assert ("write", 3) not in r.trace
    gate.set()
    assert await asyncio.wait_for(flush, 2) is True
    assert r.trace.index(("refresh", (100,))) < r.trace.index(("write", 3))
    assert r.committed == [1, 2, 3, 9] and calls["most_running"] == 1


async def test_a_later_write_failure_leaves_the_running_stamp_to_the_run():
    r = rig(failed=3)
    r.release.set()
    gate, calls = held_refresher(r)
    # The failure returns at once; game 100's held stamp stays the run's.
    assert await asyncio.wait_for(r.flush(), 2) is False
    assert calls["running"] == 1 and r.ns["prices"].stamping is not None
    assert r.committed == [1, 2] and set(r.batch) == {3, 9}
    gate.set()
    await asyncio.wait_for(
        r.ns["prices"].join_stamp(r.ns["blend_refresher"]), 2,
    )
    assert calls["finished"] == [(100,)]
    assert calls["running"] == 0 and r.ns["prices"].stamping is None


async def test_cancellation_cancels_the_running_stamp_before_returning():
    r = rig()
    gate, calls = held_refresher(r)
    flush = asyncio.create_task(r.flush())
    await asyncio.wait_for(r.entered.wait(), 2)  # 200's write held, 100 stamping
    assert calls["running"] == 1
    flush.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(flush, 2)
    assert calls["cancelled"] == [(100,)]
    assert calls["running"] == 0, "no stamp outlives its flush"
    assert r.committed == [1, 2] and set(r.batch) == {3, 9}


async def test_a_cancel_landing_on_the_run_stamp_join_still_joins_it():
    """#10090 review (43455): a recycle cancel that lands on the last stamp's
    join must not leave the stamp running beside the final drain's own
    refresh. Cross-flush, that join is the consumer's `join_stamp` (scope
    change, final drain); the flush itself returns with the stamp running."""
    r = rig()
    r.release.set()
    gate, calls = held_refresher(r, hold_ids=(200,))
    assert await asyncio.wait_for(r.flush(), 2) is True
    # Premise: every write committed; only game 200's stamp is still running.
    assert r.committed == [1, 2, 3, 9]
    assert calls["started"] == [(100,), (200,)] and calls["running"] == 1
    join = asyncio.create_task(r.ns["prices"].join_stamp(r.ns["blend_refresher"]))
    await asyncio.sleep(0)
    join.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(join, 2)
    assert calls["cancelled"] == [(200,)]
    assert calls["running"] == 0, "no stamp outlives its join"
    assert calls["adopted"][-1] == {200}, "its committed game stays owed"
    assert r.ns["prices"].stamping is None


async def test_the_final_drain_still_joins_its_stamp():
    # The drain has no next flush; its hand-off and exit follow at once.
    r = rig()
    r.release.set()
    gate, calls = held_refresher(r)
    flush = asyncio.create_task(r.flush(final_drain=True))
    for _ in range(50):
        await asyncio.sleep(0)
    assert calls["running"] == 1 and not flush.done()
    gate.set()
    assert await asyncio.wait_for(flush, 2) is True
    assert calls["running"] == 0 and r.ns["prices"].stamping is None
