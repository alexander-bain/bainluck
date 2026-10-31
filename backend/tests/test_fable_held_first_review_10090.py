"""Fable's review controls for latency's held-first stamps (`667df791` on G4F13).

Two things the author's file does not exercise:

1. RECOVERY under the reorder: a held live game picked out of FIFO order is
   running when the owner is cancelled. Every event not committed — the held
   one, the unheld ones queued behind it, the workers' own — must be owed
   again, the one that committed must not be stamped twice, and the next
   quiet flush stamps them all, held first among live.

2. The live-debt bound's accounting (`_held_debt_run`): the return says
   "every fourth SUCH admission" (one where a held game took the allowance)
   follows rotation order. On `667df791` the counter advances on every
   admission that merely has an unheld live debt and a non-empty held set —
   no held live debt need be owed — so a due held debt can arrive at an
   admission whose turn was already spent on nothing. Nonblocking: it costs
   that held game one admission interval, never a wrong price. The control
   below is RED on `667df791` and GREEN with the one-line guard.
"""

import asyncio

import pytest

from app.tasks import live_blend_refresh as module
from tests.test_admitted_debt_slots_10090 import _Gated, _settle
from tests.test_admitted_live_first_10090 import _gated, _mark, _seeded
from tests.test_single_event_commit_10090 import settle_until

pytestmark = pytest.mark.asyncio


async def test_cancel_with_a_held_game_picked_out_of_order_keeps_every_unstamped_event_owed(
    monkeypatch,
):
    statuses = {1: "scheduled", **{e: "live" for e in range(2, 11)}}
    x = await _seeded(monkeypatch, statuses)
    receipts = x.r.receipts = module.TailReceipts("polymarket")
    receipts._live_events = set(statuses)
    x.r.reader_held = lambda: frozenset({9})
    started, release = _gated(x)
    running = asyncio.create_task(x.r.refresh([1], flush_started=1003))
    try:
        await settle_until(lambda: started == [1])
        assert x.r.admit_fresh(
            [2, 3, 4], flush_started=1003, marks=[_mark(e, e) for e in (2, 3, 4)],
        ) == {2, 3, 4}
        await settle_until(lambda: sorted(started) == [1, 2, 3, 4])
        assert x.r.admit_fresh(
            [5, 6, 7, 8, 9, 10], flush_started=1003,
            marks=[_mark(e, e) for e in range(5, 11)],
        ) == set(range(5, 11))
        window = x.r._admission
        assert list(window.live_queue) == [5, 6, 7, 8, 9, 10]
        release(2)  # game 2 commits; its worker takes HELD game 9, not game 5
        await settle_until(lambda: len(started) == 5)
        assert started[-1] == 9
        assert list(window.live_queue) == [5, 6, 7, 8, 10]
        # The held game is accounted exactly as a FIFO pick would be.
        assert 9 in window.holding and 9 in window.admitted and 9 not in window.completed
        running.cancel()
        with pytest.raises(asyncio.CancelledError):
            await running
    finally:
        for event_id in statuses:
            release(event_id)
        await asyncio.gather(running, return_exceptions=True)
    assert x.r._admission is None
    # Game 2's stamp completed before the cancel: it alone is not owed.
    assert x.r.pending_event_ids() == frozenset({1, 3, 4, 5, 6, 7, 8, 9, 10})
    stamped_from = len(started)
    await x.r.refresh_pending(flush_started=1006)
    assert not x.r.pending_event_ids()
    # Recovery stamps every owed event once: live first, held first among
    # them, then id; game 2 is not stamped again.
    assert started[stamped_from:] == [9, 3, 4, 5, 6, 7, 8, 10, 1]
    assert x.r.stats["errors"] == 0


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


async def test_a_due_held_live_debt_is_preferred_even_after_admissions_that_had_none(
    clock, monkeypatch,
):
    # Pre-game 7 holds the shared slot, so the live allowance alone decides.
    # The off arm of STAMP_HELD_OWED_FRESH: the held game rides the live slot.
    monkeypatch.delenv(module.STAMP_HELD_OWED_FRESH_ENV, raising=False)
    r = _Gated(blocked={99, 7})
    r.reader_held = lambda: frozenset({50})
    task = await _running_call(r)
    r.adopt_pending([7])
    r.admit_fresh((), flush_started=1000.5)
    await _settle()
    assert r._admission.debts == {7}
    r._live_event_ids.update({1, 2, 50})
    # Three admissions with only UNHELD live debt owed: the preference has
    # nothing to prefer, so none of them is a "held admission".
    for i in range(3):
        r.adopt_pending([1, 2])
        r.admit_fresh((), flush_started=1001.0 + i)
        await _settle()
        assert r._admission.live_debts.issubset({1, 2})
    # Now held 50 is owed and due beside unheld 1 and 2: it takes the
    # allowance first — nothing held has used the run yet.
    r.adopt_pending([1, 2, 50])
    r.admit_fresh((), flush_started=1004.0)
    # Read before the unblocked rider finishes: which game took the allowance.
    # `667df791`: {2} (rotation order) with `_held_debt_run` reset to 0 — the
    # three held-less admissions spent the run; 50 waits another admission.
    assert r._admission.live_debts == {50}, (r._admission.live_debts, r._held_debt_run)
    await _settle()
    r.release.set()
    await task


async def test_with_held_owed_fresh_a_due_held_debt_is_a_member_after_admissions_that_had_none(
    clock, monkeypatch,
):
    # STAMP_HELD_OWED_FRESH on (Authority N2): the same three held-less
    # admissions, then held 50 owed and due beside unheld 1 and 2. It joins
    # the admission as a member, stamped first, and the live allowance stays
    # with unheld debt in rotation order.
    monkeypatch.setenv(module.STAMP_HELD_OWED_FRESH_ENV, "1")
    r = _Gated(blocked={99, 7})
    r.reader_held = lambda: frozenset({50})
    task = await _running_call(r)
    r.adopt_pending([7])
    r.admit_fresh((), flush_started=1000.5)
    await _settle()
    assert r._admission.debts == {7}
    r._live_event_ids.update({1, 2, 50})
    for i in range(3):
        r.adopt_pending([1, 2])
        r.admit_fresh((), flush_started=1001.0 + i)
        await _settle()
        assert r._admission.live_debts.issubset({1, 2})
    stamped_from = len(r.started)
    r.adopt_pending([1, 2, 50])
    r.admit_fresh((), flush_started=1004.0)
    assert r._admission.live_debts == {2} and 50 in r._admission.events
    await _settle()
    assert r.started[stamped_from:] == [50, 2]
    assert r.pending_event_ids() == frozenset({1})
    r.release.set()
    await task
