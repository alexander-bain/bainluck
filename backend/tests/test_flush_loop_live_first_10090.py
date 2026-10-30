"""#10090 — Argon's flush-loop Rank 2: a live game's throttled price is not held
behind pre-game debt, an idle wake, or an old flush clock.

Production 2026-10-30 00:18:40-44Z (Kalshi 15338515, origin=throttle,
lock_retries=0, held_s=4.300): the price committed, was throttled for the
0.25 s floor, and was stamped 4.3 s later. Three of the four barriers Argon
traced (`RETURN-argon-20261030T0043Z-…-FLUSH-LOOP-SATURATION-FINDINGS`, Q2):

- the running call's door admits one owed event at a time, in turn order, with
  no regard for live games (`admit_fresh`, `ADMITTED_DEBT_SLOTS`);
- Kalshi's empty 0.25 s wake did not offer the door anything while a stamp ran
  (Polymarket's quiet flush calls `admit_fresh(())`);
- the floor was judged on the caller's flush clock, and a Kalshi main flush
  hands the same start to every admission for its whole 3-7 s.

These prove admission order and the clock, not production latency.
"""

import asyncio

import pytest

import app.tasks.live_blend_refresh as lbr
from tests.test_admitted_debt_slots_10090 import _Gated, _settle
from tests.test_kalshi_game_isolation_10655 import rig as kalshi_rig

pytestmark = pytest.mark.asyncio


@pytest.fixture
def clock(monkeypatch):
    now = {"t": 1000.0}
    monkeypatch.setattr(lbr, "_mono", lambda: now["t"])
    return now


async def _running_call(r, flush_started=1000.0):
    """A call whose own stamp (event 99) is held, so its door stays open."""
    task = asyncio.create_task(r.refresh([99], flush_started=flush_started))
    await _settle()
    assert r.admitting() and r.started == [99]
    return task


async def _finish(r, task):
    r.release.set()
    await task
    assert r._admission is None


# ── 1. live debt first, on its own allowance ────────────────────────────────


async def test_a_live_owed_event_is_admitted_ahead_of_n_non_live_ones(clock):
    r = _Gated(blocked={99})
    task = await _running_call(r)
    r.adopt_pending([1, 2, 3, 4, 5, 6, 50])
    r._live_event_ids.add(50)
    assert r.admit_fresh((), flush_started=1001.0) == frozenset()
    await _settle()
    # Strawman (before): turn order 1..6 then 50 — the live game was last.
    assert r.started == [99, 50, 1]
    assert r.pending_event_ids() == frozenset({2, 3, 4, 5, 6})
    await _finish(r, task)


async def test_pre_game_debt_holding_the_one_slot_does_not_hold_a_due_live_event(clock):
    r = _Gated(blocked={99, 1})
    task = await _running_call(r)
    r.adopt_pending([1, 2, 3])
    r.admit_fresh((), flush_started=1001.0)
    await _settle()
    assert r.started == [99, 1] and r._admission.debts == {1}
    # A live game's price is throttled now, while pre-game 1 holds the slot.
    r.adopt_pending([50])
    r._live_event_ids.add(50)
    r.admit_fresh((), flush_started=1002.0)
    await _settle()
    assert r.started == [99, 1, 50] and 50 in r.finished
    assert r.pending_event_ids() == frozenset({2, 3})
    await _finish(r, task)


async def test_live_debt_never_takes_the_last_stamp_worker(clock):
    r = _Gated(blocked={99, 1, 2, 3})
    task = await _running_call(r)
    r._live_event_ids.update({1, 2, 3, 4})
    r.adopt_pending([1, 2, 3, 4])
    r.admit_fresh((), flush_started=1001.0)
    await _settle()
    # Two ride the live allowance, one the shared slot; the fourth waits.
    assert r._admission.live_debts == {1, 2} and r._admission.debts == {3}
    assert r.pending_event_ids() == frozenset({4})
    await _finish(r, task)


async def test_a_live_row_lock_retry_keeps_the_shared_turn(clock):
    # A lock retry may wait out a whole lock budget; it is not live debt.
    r = _Gated(blocked={99, 1})
    task = await _running_call(r)
    r.adopt_pending([1])
    r.admit_fresh((), flush_started=1001.0)
    await _settle()
    assert r._admission.debts == {1}
    r._lock_retry.add(50)
    r._live_event_ids.add(50)
    r.admit_fresh((), flush_started=1002.0)
    await _settle()
    assert r.started == [99, 1] and 50 in r.pending_event_ids()
    await _finish(r, task)


# ── 2. Kalshi's empty wake offers the running call its due debt ─────────────


async def test_an_empty_kalshi_wake_admits_a_due_throttled_live_event_while_stamping(
    clock,
):
    r = _Gated(blocked={99})
    k = kalshi_rig()
    k.batch.clear()  # nothing buffered: the 0.25 s wake is empty
    k.ns["blend_refresher"] = r
    prices = k.ns["prices"]
    prices.stamping = await _running_call(r)  # the run's refresh, still stamping
    prices.stamping_events = {99}
    r._live_event_ids.add(50)
    r.adopt_pending([50])
    clock["t"] = 1000.5
    assert await k.flush(1000.5) is True
    await _settle()
    # Strawman (before): the wake returned without a word to the refresher;
    # 50 waited for event 99's stamp to return.
    assert r.started == [99, 50] and 50 in r.finished
    assert not prices.stamping.done()
    await _finish(r, prices.stamping)


async def test_an_empty_kalshi_wake_beside_a_flush_keeps_that_flushs_events_owed(clock):
    r = _Gated(blocked={99})
    k = kalshi_rig()
    k.batch.clear()
    k.ns["blend_refresher"] = r
    k.ns["live_event_ids"] = {50, 60}
    prices = k.ns["prices"]
    prices.stamping = await _running_call(r)
    r._live_event_ids.update({50, 60})
    r.adopt_pending([50, 60])
    clock["t"] = 1000.5
    # The main flush is still writing event 60.
    beside = (frozenset(), frozenset({60}), frozenset())
    assert await k.flush(1000.5, beside=beside) is True
    await _settle()
    assert r.started == [99, 50] and 60 in r.pending_event_ids()
    await _finish(r, prices.stamping)


# ── 3. the floor reads the current clock ────────────────────────────────────


async def test_a_throttled_event_is_due_a_floor_after_its_last_refresh_whatever_the_flush_start(
    clock,
):
    r = lbr.LiveBlendRefresher("kalshi", min_refresh_interval_s=0.25)
    assert r._due(7, 1000.0)  # the main flush starts at 1000.0 and runs on
    # A write beside it stamped event 7 on its own, later clock.
    clock["t"] = 1003.0
    assert r._due(7, 1003.0)
    r._last_refresh_at[7] = 1003.0
    # The main flush still hands its own start to every admission.
    clock["t"] = 1003.1
    assert not r._due(7, 1000.0)  # inside the floor
    clock["t"] = 1003.25
    # Strawman (before): 1000.0 - 1003.0 < 0.25 for the rest of the flush.
    assert r._due(7, 1000.0)


async def test_a_stamp_just_before_the_flush_start_is_due_inside_that_flush(clock):
    r = lbr.LiveBlendRefresher("kalshi", min_refresh_interval_s=0.25)
    clock["t"] = 999.9
    assert r._due(7, 999.9)
    r._last_refresh_at[7] = 999.9
    clock["t"] = 1000.0
    assert not r._due(7, 1000.0)
    clock["t"] = 1000.3
    # Strawman (before): 1000.0 - 999.9 < 0.25 until the next flush start.
    assert r._due(7, 1000.0)


async def test_the_door_admits_debt_a_floor_after_its_stamp_on_an_old_flush_clock(clock):
    class Floored(_Gated):
        def __init__(self, blocked):
            super().__init__(blocked)
            self.min_refresh_interval_s = 0.25

    r = Floored(blocked={99})
    task = await _running_call(r, flush_started=1000.0)
    r._live_event_ids.add(7)
    clock["t"] = 1003.0
    assert r._due(7, 1003.0)
    r._last_refresh_at[7] = 1003.0  # stamped beside, on 1003.0
    r.adopt_pending([7])
    clock["t"] = 1003.1
    r.admit_fresh((), flush_started=1000.0)
    await _settle()
    assert 7 not in r.started  # still inside the floor
    clock["t"] = 1003.3
    r.admit_fresh((), flush_started=1000.0)
    await _settle()
    assert r.started == [99, 7]
    await _finish(r, task)

