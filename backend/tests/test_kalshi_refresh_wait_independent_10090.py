"""#10090 — an independent live game's new price does not wait for the running
blend refresh to return.

Ship: new live probabilities for an independent event keep reaching the
headline and chart while another event's refresh is slow.

Both cases run the real `flush_prices` with the real `LiveBlendRefresher`
(the `test_kalshi_fresh_admission_10090` rig: outcomes 1,2 -> game 1,
3 -> game 2, 9 standalone). Game 1's stamp is held in its UPDATE.

1. THE SAME-EVENT FENCE JOINED THE WHOLE REFRESH. A flush carrying a new
   tick for game 1 (still held by the running refresh) and for game 2 joined
   that refresh at game 1's phase, so game 2's write, commit and stamp waited
   for game 1's held stamp. Now game 2's whole cohort commits first and joins
   the running refresh; game 1 still waits for its own stamp before its write.

2. A QUIET FLUSH STAMPED OLD DEBT INLINE. A flush with no new prices ran the
   owed stamps inside itself, so the next flush, carrying game 2's new price,
   could not start until game 1's held debt stamp returned. Now the debt runs
   as the run's refresh (`prices.stamping`), the same as a price flush's, and
   game 2's cohort joins it.

Source/progress controls, not production timing.
"""
import asyncio

import pytest

from app.tasks import kalshi_ws
from tests.test_kalshi_fresh_admission_10090 import _caller as _admission_caller
from tests.test_single_event_commit_10090 import settle_until

pytestmark = pytest.mark.asyncio

_LIVE_PLAN = (
    "flush_budget_spent", "live_preempts_tail", "yield_written_nonlive_tail",
    "live_unfenced_first",
)


def _caller(monkeypatch, *, blocked):
    """The admission rig with games 1 and 2 live: the shipped live plan."""
    x, r = _admission_caller(monkeypatch, blocked=blocked)
    r.ns.update({name: getattr(kalshi_ws, name) for name in _LIVE_PLAN})
    r.ns["live_event_ids"] = {1, 2}
    return x, r


async def test_independent_live_game_is_not_held_behind_a_fenced_game(monkeypatch):
    x, r = _caller(monkeypatch, blocked=(1,))
    later_game_two = r.batch.pop(3)
    del r.batch[9]
    try:
        assert await asyncio.wait_for(r.flush(1000.0), 2) is True
        await settle_until(lambda: "update" in x.commands)
        assert r.committed == [1, 2] and x.committed == []
        assert r.ns["prices"].stamping_events == {1}
        # Game 1 ticks again (first in the buffer), then game 2.
        r.batch[1] = (.65, .64, .66)
        r.batch[3] = later_game_two
        flush = asyncio.create_task(r.flush(1002.0))
        await settle_until(lambda: 2 in x.published)
        assert r.committed == [1, 2, 3], "game 2 committed, game 1 not rewritten"
        assert 1 not in x.committed, "game 1's stamp is still held"
        # Game 1's new price still waits for game 1's own stamp: fenced.
        assert not flush.done()
    finally:
        x.release.set()
    assert await asyncio.wait_for(flush, 2) is True
    assert r.committed == [1, 2, 3, 1]
    await asyncio.wait_for(r.ns["prices"].join_stamp(x.r), 2)
    # Game 1's new price is re-stamped after its write; the rig's blend reads
    # the same value, so that second stamp is judged unchanged, not sent.
    assert x.published == [2, 1]
    assert x.r.stats["considered"] == 3 and x.r.stats["unchanged_skipped"] == 1
    assert not x.r.pending_event_ids() and x.r._admission is None
    assert x.r.stats["errors"] == 0


async def test_fenced_game_keeps_its_place_when_nothing_is_held(monkeypatch):
    # Control for the order: with no running refresh, batch order stands.
    x, r = _caller(monkeypatch, blocked=())
    del r.batch[9]
    assert await asyncio.wait_for(r.flush(1000.0), 2) is True
    assert r.committed == [1, 2, 3]
    await asyncio.wait_for(r.ns["prices"].join_stamp(x.r), 2)
    assert sorted(x.published) == [1, 2]


async def test_quiet_flush_debt_stamp_does_not_hold_the_next_flush(monkeypatch):
    x, r = _caller(monkeypatch, blocked=(1,))
    later_game_two = r.batch.pop(3)
    r.batch.clear()
    x.r._lock_retry = {1}  # game 1's price is stored; its stamp is owed
    try:
        # A quiet flush pays the debt on the run's refresh and returns.
        assert await asyncio.wait_for(r.flush(1000.0), 2) is True
        await settle_until(lambda: "update" in x.commands)
        assert r.ns["prices"].stamping is not None
        assert r.ns["prices"].stamping_events == {1}
        assert r.ns["prices"].flush_work == 1
        r.batch[3] = later_game_two
        assert await asyncio.wait_for(r.flush(1002.0), 2) is True
        await settle_until(lambda: 2 in x.published)
        assert r.committed == [3] and 1 not in x.committed, "game 1 still held"
    finally:
        x.release.set()
    await asyncio.wait_for(r.ns["prices"].join_stamp(x.r), 2)
    assert x.published == [2, 1]
    assert not x.r.pending_event_ids() and x.r._admission is None
    assert x.r.stats["errors"] == 0


async def test_final_drain_quiet_flush_still_stamps_its_debt_before_returning(
    monkeypatch,
):
    # The drain has no next flush: its debt stamp may not outlive it.
    x, r = _caller(monkeypatch, blocked=())
    r.batch.clear()
    x.r._lock_retry = {1}
    assert await asyncio.wait_for(r.flush(final_drain=True), 2) is True
    assert r.ns["prices"].stamping is None
    assert x.published == [1] and not x.r.pending_event_ids()


async def test_cancelled_quiet_flush_debt_stamp_stays_owed(monkeypatch):
    # The consumer joins the run's refresh at a scope change or before its
    # final drain. Cancelled there, the debt a quiet flush started stays owed
    # with no failed-retry hold, as a price flush's refresh does.
    x, r = _caller(monkeypatch, blocked=(1,))
    r.batch.clear()
    x.r._lock_retry = {1}
    assert await asyncio.wait_for(r.flush(1000.0), 2) is True
    await settle_until(lambda: "update" in x.commands)
    join = asyncio.create_task(r.ns["prices"].join_stamp(x.r))
    await asyncio.sleep(0)
    join.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(join, 2)
    assert r.ns["prices"].stamping is None and x.committed == []
    assert x.r.pending_event_ids() == frozenset({1})
    assert not x.r._failed_hold_until and x.r._admission is None


async def test_only_the_leading_live_phases_are_reordered():
    events = {1: 1, 2: 2, 3: 3, 4: 4, 5: 5}
    phases = [{1: "a"}, {2: "b"}, {3: "c"}, {4: "d"}, {5: "e"}]
    # Live 1,2,3; 1 and 3 held. Non-live 4 (held) and 5 keep their order.
    assert kalshi_ws.live_unfenced_first(phases, events, {1, 2, 3}, {1, 3, 4}) == [
        {2: "b"}, {1: "a"}, {3: "c"}, {4: "d"}, {5: "e"},
    ]
    assert kalshi_ws.live_unfenced_first(phases, events, {1, 2, 3}, set()) == phases
    assert kalshi_ws.live_unfenced_first(phases, events, set(), {1}) == phases


async def test_a_debt_stamp_still_fences_its_own_game_new_price(monkeypatch):
    # The debt a quiet flush started holds game 1: game 1's new price is not
    # written under that stamp's read, while game 2's cohort goes through.
    x, r = _caller(monkeypatch, blocked=(1,))
    later_game_two = r.batch.pop(3)
    r.batch.clear()
    x.r._lock_retry = {1}
    try:
        assert await asyncio.wait_for(r.flush(1000.0), 2) is True
        await settle_until(lambda: "update" in x.commands)
        r.batch[1] = (.65, .64, .66)
        r.batch[3] = later_game_two
        flush = asyncio.create_task(r.flush(1002.0))
        await settle_until(lambda: 2 in x.published)
        assert r.committed == [3], "game 1's new price waits for its own stamp"
        assert not flush.done()
    finally:
        x.release.set()
    assert await asyncio.wait_for(flush, 2) is True
    assert r.committed == [3, 1]
    await asyncio.wait_for(r.ns["prices"].join_stamp(x.r), 2)
    assert x.published == [2, 1]
    assert not x.r.pending_event_ids() and x.r._admission is None
