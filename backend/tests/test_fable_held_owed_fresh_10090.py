"""Fable's control for held-owed-fresh (`STAMP_HELD_OWED_FRESH`, #10090).

Production 16:16-16:31Z 2026-10-31 (v6005, four held Polymarket games, held-first
on): a held game's price that was ADMITTED at its own offer reached the reader
in ~0.85 s; one that was refused (its stamp queued or running, its cohort
unfinished, under the floor) went to plain debt and the stamp that finally
carried it came p50 4.3 s / p90 12-19 s later, because the door's one
live-debt slot is held by an unheld rider for that rider's whole queue turn.
With the switch on, an owed held live game that is admissible joins the next
admission as a cohort member (held-first pick, this flush's clock) instead of
waiting for that slot. Unheld debt keeps its slots and turns.

The first test is RED on `c8bdb692` (the switch does not exist there, so the
held game waits) and GREEN with the change; the rest pin the gate it shares
with the cohort and the off arm.
"""

import asyncio

import pytest

from app.tasks import live_blend_refresh as module
from tests.test_admitted_debt_slots_10090 import _Gated, _settle

pytestmark = pytest.mark.asyncio


@pytest.fixture
def clock(monkeypatch):
    now = {"t": 1000.0}
    monkeypatch.setattr(module, "_mono", lambda: now["t"])
    return now


async def _running_call(r):
    task = asyncio.create_task(r.refresh([99], flush_started=1000.0))
    await _settle()
    assert r.admitting() and r.started == [99]
    return task


async def _busy_slots(r):
    """Pre-game 7 holds the shared debt slot and unheld live 1 the live
    allowance; neither stamp returns, as a rider deep in the live queue does
    not for a whole queue turn."""
    r.adopt_pending([7])
    r.admit_fresh((), flush_started=1000.5)
    await _settle()
    assert r._admission.debts == {7}
    r._live_event_ids.update({1, 2, 50})
    r.adopt_pending([1])
    r.admit_fresh((), flush_started=1001.0)
    await _settle()
    assert r._admission.live_debts == {1}
    assert r.started == [99, 7, 1]


async def test_a_held_owed_live_game_is_admitted_while_the_live_debt_slot_is_busy(
    clock, monkeypatch,
):
    monkeypatch.setenv(module.STAMP_HELD_OWED_FRESH_ENV, "1")
    r = _Gated(blocked={99, 7, 1})
    r.reader_held = lambda: frozenset({50})
    task = await _running_call(r)
    await _busy_slots(r)
    # Held 50's committed price was refused at its own offer and kept owed;
    # unheld live 2 is owed beside it. An unrelated cohort (60) is admitted.
    r.adopt_pending([50, 2])
    assert r.admit_fresh([60], flush_started=1002.0) == {60}
    await _settle()
    # `c8bdb692`: started == [99, 7, 1, 60] and 50 waits for the slot 1 holds.
    assert 50 in r.started, r.started
    # Picked held-first, before the cohort that let it in.
    assert r.started[3:] == [50, 60]
    assert 50 in r.finished
    # A cohort member, not a rider: the slots and their holders are unchanged,
    # and unheld owed 2 still waits for the live slot exactly as today.
    assert r._admission.live_debts == {1} and r._admission.debts == {7}
    assert 2 not in r.started
    assert r.pending_event_ids() == frozenset({2})
    r.release.set()
    await task


async def test_a_held_owed_game_whose_stamp_is_queued_or_running_is_not_admitted_again(
    clock, monkeypatch,
):
    # The same-event fence (I2): one attempt per event, however held.
    monkeypatch.setenv(module.STAMP_HELD_OWED_FRESH_ENV, "1")
    r = _Gated(blocked={99, 7, 1, 50})
    r.reader_held = lambda: frozenset({50})
    task = await _running_call(r)
    await _busy_slots(r)
    r._live_event_ids.add(50)
    r.admit_fresh([50], flush_started=1002.0)
    await _settle()
    assert r.started == [99, 7, 1, 50] and 50 in r._admission.holding
    # Its newer price is kept owed while that attempt runs; no second attempt
    # (the three workers hold 7, 1 and 50, so the cohort 60 queues behind).
    r.adopt_pending([50])
    assert r.admit_fresh([60], flush_started=1003.0) == {60}
    await _settle()
    assert r.started == [99, 7, 1, 50]
    assert r.started.count(50) == 1 and 60 in r._admission.queue
    assert r.pending_event_ids() == frozenset({50})
    r.release.set()
    await task


async def test_a_held_owed_game_still_being_written_is_not_admitted(clock, monkeypatch):
    # Complete cohorts (I1): the caller's unfinished events are refused here as
    # they are for the cohort and for debt riders.
    monkeypatch.setenv(module.STAMP_HELD_OWED_FRESH_ENV, "1")
    r = _Gated(blocked={99, 7, 1})
    r.reader_held = lambda: frozenset({50})
    task = await _running_call(r)
    await _busy_slots(r)
    r.adopt_pending([50])
    r.admit_fresh([60], flush_started=1002.0, defer_event_ids={50})
    await _settle()
    assert r.started == [99, 7, 1, 60]
    assert r.pending_event_ids() == frozenset({50})
    # The next admission, with its cohort finished, takes it.
    r.admit_fresh([61], flush_started=1003.0)
    await _settle()
    assert r.started == [99, 7, 1, 60, 50, 61]
    r.release.set()
    await task


async def test_with_the_switch_off_a_held_owed_game_waits_for_the_live_slot_as_today(
    clock, monkeypatch,
):
    monkeypatch.delenv(module.STAMP_HELD_OWED_FRESH_ENV, raising=False)
    r = _Gated(blocked={99, 7, 1})
    r.reader_held = lambda: frozenset({50})
    task = await _running_call(r)
    await _busy_slots(r)
    r.adopt_pending([50, 2])
    assert r.admit_fresh([60], flush_started=1002.0) == {60}
    await _settle()
    assert r.started == [99, 7, 1, 60]
    assert r.pending_event_ids() == frozenset({2, 50})
    # A later admission changes nothing while the slot stays busy.
    r.admit_fresh([61], flush_started=1003.0)
    await _settle()
    assert r.started == [99, 7, 1, 60, 61]
    assert r.pending_event_ids() == frozenset({2, 50})
    r.release.set()
    await task
