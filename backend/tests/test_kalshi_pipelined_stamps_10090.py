"""#10090 — a Kalshi phase's blend stamp runs while the next phase writes.

Executes the production `flush_prices` on the #10655 rig with a refresher
whose stamp can be held. Proves ordering and lifetime, not production latency:
the next game's write commits while the previous game's stamp is still
running; refreshes never overlap each other; no stamp outlives its flush, on
success, on a later write failure, or on cancellation.
"""
import ast
import asyncio

import pytest

from tests.kalshi_price_statement_support import flush_ast
from tests.test_kalshi_game_isolation_10655 import rig
from tests.test_kalshi_pipeline_consumer_10693 import (
    _without_reviewed_pipelined_stamps,
)

pytestmark = pytest.mark.asyncio


def held_refresher(r, hold_ids=(100,)):
    gate = asyncio.Event()
    calls = {"started": [], "finished": [], "cancelled": [], "running": 0,
             "most_running": 0}

    class Refresher:
        def pending_event_ids(self):
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


async def test_strawman_the_serial_flush_holds_the_next_write():
    """The rig can tell: the same flush with its stamp reverted to serial (the
    10693 comparator's exact reversal) keeps game 200 unwritten while 100's
    stamp is held."""
    r = rig()
    r.release.set()
    serial = _without_reviewed_pipelined_stamps(flush_ast())
    exec(compile(ast.Module(body=[serial], type_ignores=[]), "serial", "exec"), r.ns)
    gate, calls = held_refresher(r)
    flush = asyncio.create_task(r.ns["flush_prices"]())
    for _ in range(20):
        await asyncio.sleep(0)
    assert calls["started"] == [(100,)]
    assert not r.entered.is_set() and r.committed == [1, 2]
    gate.set()
    assert await asyncio.wait_for(flush, 2) is True
    assert r.trace.index(("refresh", (100,))) < r.trace.index(("commit", (3,)))


async def test_a_later_write_failure_still_waits_for_the_running_stamp():
    r = rig(failed=3)
    r.release.set()
    gate, calls = held_refresher(r)
    flush = asyncio.create_task(r.flush())
    for _ in range(20):
        await asyncio.sleep(0)
    assert not flush.done()
    gate.set()
    assert await asyncio.wait_for(flush, 2) is False
    assert calls["finished"] == [(100,)]
    assert calls["running"] == 0
    assert r.committed == [1, 2] and set(r.batch) == {3, 9}


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


async def test_a_cancel_landing_on_the_last_stamp_join_still_joins_it():
    """#10090 review (43455): the flush's last stamp is awaited in `finally`.
    A recycle cancel that lands on THAT await used to leave the stamp running
    after the flush returned, beside the final drain's own refresh."""
    r = rig()
    r.release.set()
    gate, calls = held_refresher(r, hold_ids=(200,))
    flush = asyncio.create_task(r.flush())
    for _ in range(50):
        await asyncio.sleep(0)
        if r.committed == [1, 2, 3, 9]:
            break
    # Premise: every write committed; only game 200's stamp is still running.
    assert r.committed == [1, 2, 3, 9]
    assert calls["started"] == [(100,), (200,)] and calls["running"] == 1
    flush.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(flush, 2)
    assert calls["cancelled"] == [(200,)]
    assert calls["running"] == 0, "no stamp outlives its flush"
