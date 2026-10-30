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


async def test_owed_debt_never_takes_the_last_stamp_worker(clock):
    # lane1's R2 on 0b2a452d: two live debts plus the shared slot took all
    # three admitted workers. Owed riding is capped one short of them.
    assert lbr.ADMITTED_LIVE_DEBT_SLOTS == 1
    assert [lbr._admitted_live_debt_slots(n) for n in (1, 2, 3)] == [1, 0, 0]
    r = _Gated(blocked={99, 1, 2, 3})
    task = await _running_call(r)
    r._live_event_ids.update({1, 2, 3, 4, 70})
    r.adopt_pending([1, 2, 3, 4])
    r.admit_fresh((), flush_started=1001.0)
    await _settle()
    # One rides the live allowance, one the shared slot; the rest wait.
    w = r._admission
    assert w.live_debts == {1} and w.debts == {2}
    assert len(w.debts | w.live_debts) == lbr.FRESH_STAMP_WORKERS - 1
    assert r.pending_event_ids() == frozenset({3, 4})
    # The worker that stays is a later fresh cohort's.
    assert r.admit_fresh([70], flush_started=1002.0) == frozenset({70})
    await _settle()
    assert r.started == [99, 1, 2, 70] and 70 in r.finished
    await _finish(r, task)


async def test_a_later_fresh_live_cohort_starts_beside_pre_game_and_live_debt(clock):
    # lane1's probe (`_Gated` arm): the running call holds 99; pre-game 1 and
    # live 50, 60 are owed and held once started. Strawman (0b2a452d): started
    # [99, 50, 60, 1], three workers on debt, so 70 waited for one to return.
    r = _Gated(blocked={99, 1, 50, 60})
    task = await _running_call(r)
    r.adopt_pending([1, 50, 60])
    r._live_event_ids.update({50, 60, 70})
    r.admit_fresh((), flush_started=1001.0)
    await _settle()
    assert r.started == [99, 50, 1]
    assert r._admission.live_debts == {50} and r._admission.debts == {1}
    r.admit_fresh([70], flush_started=1002.0)
    await _settle()
    assert r.started == [99, 50, 1, 70] and 70 in r.finished
    assert 60 in r.pending_event_ids()
    await _finish(r, task)


async def test_a_re_owed_live_event_takes_only_its_own_shared_turn(clock):
    # lane1's R3 on 0b2a452d: with the live allowance full, live-first order
    # in the shared slot gave a live game owed again at every admission every
    # shared turn. Live 50 holds the allowance; lock retry 5 and pre-game 7
    # are owed; live 70 is owed again before each of six admissions.
    r = _Gated(blocked={99, 50})
    task = await _running_call(r)
    r._live_event_ids.update({50, 70})
    r.adopt_pending([50])
    r.admit_fresh((), flush_started=1000.5)
    await _settle()
    assert r._admission.live_debts == {50} and r._admission.debts == set()
    r._lock_retry.add(5)
    r.adopt_pending([7])
    for i in range(6):
        r.adopt_pending([70])
        r.admit_fresh((), flush_started=1001.0 + i)
        await _settle()
    # Strawman (live-first in the shared slot): [99, 50, 70, 70, 70, 70, 70, 70].
    assert r.started[:5] == [99, 50, 5, 7, 70]
    assert r.started.count(70) >= 2  # the live game still takes its turns
    await _finish(r, task)


async def test_control_with_the_live_allowance_free_a_live_debt_rides_it(clock):
    r = _Gated(blocked={99})
    task = await _running_call(r)
    r._live_event_ids.add(70)
    r._lock_retry.add(5)
    r.adopt_pending([7])
    for i in range(6):
        r.adopt_pending([70])
        r.admit_fresh((), flush_started=1001.0 + i)
        await _settle()
    assert r.started[:5] == [99, 70, 5, 70, 7]
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



async def test_at_most_one_stamp_per_floor_inside_one_long_flush(clock):
    # lane1's R1 probe on 0b2a452d: the stamp is recorded on the flush's start,
    # so on the current clock alone every admission past start + floor (2 s)
    # stamped again — nine stamps in 5.6 s, where a floor apart allows three.
    from tests.test_ws_flush_cadence_10090 import _Recording

    r = _Recording()
    stamps = []
    for t in (1000.4, 1002.5, 1002.75, 1003.0, 1003.25, 1003.5, 1004.0, 1005.0, 1006.0):
        clock["t"] = t
        n = len(r.batches)
        await r.refresh([1], flush_started=1000.0)
        if len(r.batches) > n:
            stamps.append(t)
    assert stamps == [1000.4, 1002.5, 1005.0]
