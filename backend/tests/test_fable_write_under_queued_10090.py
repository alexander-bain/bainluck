"""Fable's control for write-under-queued (`STAMP_WRITE_UNDER_QUEUED`, #10090).

Production 19:58-20:03Z 2026-10-31 (v6012, Polymarket): a game nobody holds
open has its stamp attempt QUEUED behind ~250 others for 6-60 s, and the
same-event fence held every newer price of the game buffered for that whole
wait — so the stamp that finally landed carried a price as old as the wait
(LIVE chains recv -> stamp p50 5.9 s / p90 11.1 s; pre-game p50 28 s / p90
64 s), and the current price waited a second whole turn. The fence protects
a RUNNING attempt's read; a queued attempt has read nothing.

With the switch on: (1) `fenced_event_ids` leaves queued admitted attempts
out of the fence (every one with ``all``, the next N picks per queue with N);
(2) the caller's write lease (`writing_begin` / `writing_end`) keeps a queued
attempt of an event under write from starting, so a read never straddles its
own event's write; (3) a cohort committed while the attempt stayed queued
RIDES that attempt (`admit_fresh` re-stages it: no debt, no second attempt).

The first test is RED on `6c9f406e` (the cohort is refused as HELD: the
door returns nothing and the event is left to be kept owed) and GREEN with
the change; the rest pin the lease, the running-attempt fence, the horizon,
the startup arm, the held-first/admitted band and the off arm.
"""

import asyncio

import pytest

from app.tasks import live_blend_refresh as module
from tests.test_admitted_debt_slots_10090 import _settle

pytestmark = pytest.mark.asyncio

# The name itself, so the file imports on `6c9f406e` and the first test
# fails at its assertion there rather than at collection.
SWITCH = getattr(module, "STAMP_WRITE_UNDER_QUEUED_ENV", "STAMP_WRITE_UNDER_QUEUED")


class _Gates(module.LiveBlendRefresher):
    """Records each stamp; an event in ``blocked`` waits for its own gate."""

    def __init__(self, blocked=()):
        super().__init__("polymarket", min_refresh_interval_s=0)
        self.started: list[int] = []
        self.finished: list[int] = []
        self.gates = {eid: asyncio.Event() for eid in blocked}

    async def _refresh_batch(
        self, event_ids, now, *, prepared=None, on_committed=None, publish_committed=None
    ):
        self.started.extend(event_ids)
        for event_id in event_ids:
            self._last_refresh_at[event_id] = now
        for event_id in event_ids:
            gate = self.gates.get(event_id)
            if gate is not None:
                await gate.wait()
        self.finished.extend(event_ids)
        if on_committed is not None:
            on_committed(event_ids)

    def open(self, *event_ids):
        for event_id in event_ids:
            self.gates[event_id].set()


@pytest.fixture
def clock(monkeypatch):
    now = {"t": 1000.0}
    monkeypatch.setattr(module, "_mono", lambda: now["t"])
    return now


def _mark(event_id, seq):
    return module.InputMark(
        seq=seq, event_id=event_id, outcome_id=event_id * 10, probability=0.5,
        kind="price", recv_wall=1.0, recv_mono=1.0, venue_ts_ms=None, event_ordinal=seq,
    )


async def _saturated_call(r, *, queued=(50,), live=True):
    """A call on 99 (held in its stamp), admitted 7, 1, 2 held on the three
    workers, then ``queued`` admitted with no free worker — as an unheld game
    on the saturated Polymarket lane is."""
    task = asyncio.create_task(r.refresh([99], flush_started=1000.0))
    await _settle()
    assert r.admitting() and r.started == [99]
    r._live_event_ids.update({7, 1, 2, *queued} if live else {7, 1, 2})
    for event_id, at in ((7, 1000.5), (1, 1001.0), (2, 1001.5)):
        assert r.admit_fresh([event_id], flush_started=at) == {event_id}
        await _settle()
    assert r.started == [99, 7, 1, 2]
    at = 1002.0
    for event_id in queued:
        assert r.admit_fresh([event_id], flush_started=at) == {event_id}
        at += 0.5
    await _settle()
    window = r._admission
    assert set(window.live_queue) | set(window.queue) == set(queued)
    assert r.started == [99, 7, 1, 2]
    return task, window


def _lease(r, events, *, written=None):
    """The flush's lease, as the PM chunk loop takes and releases it; a no-op
    on a refresher without one (the RED arm reaches the assertion below)."""
    begin, end = getattr(r, "writing_begin", None), getattr(r, "writing_end", None)
    if begin is not None:
        begin(events)
    if end is not None:
        end(events, written=events if written is None else written)


async def _finish(r, task):
    r.open(*r.gates)
    await task
    assert r._admission is None


async def test_a_cohort_committed_while_the_attempt_is_queued_rides_it(clock, monkeypatch):
    monkeypatch.setenv(SWITCH, "all")
    r = _Gates(blocked={99, 7, 1, 2})
    r.receipts = module.TailReceipts("polymarket")
    task, window = await _saturated_call(r)
    staged_before = window.staged.get(50)
    # The flush writes queued 50's newer price (the fence lifted: 50 is not
    # fenced) under the lease, then offers the committed cohort.
    fenced = getattr(r, "fenced_event_ids", lambda: r.holding_event_ids())()
    assert 50 not in fenced and {99, 7, 1, 2} <= fenced, fenced
    _lease(r, {50})
    mark = _mark(50, 7)
    # `6c9f406e`: refused as HELD — frozenset() — and the caller keeps it owed.
    assert r.admit_fresh([50], flush_started=1003.0, marks=[mark]) == {50}
    await _settle()
    # Rides the queued attempt: no second attempt, no debt, the newest input
    # staged onto it, its queue place kept.
    assert r.started == [99, 7, 1, 2]
    assert r.pending_event_ids() == frozenset()
    assert window.staged[50] is mark and window.staged[50] is not staged_before
    assert list(window.live_queue) == [50]
    assert r._admission.debts == set() and r._admission.live_debts == set()
    # Its turn comes: one stamp, on the board as it then is.
    r.open(7)
    await _settle()
    assert r.started == [99, 7, 1, 2, 50] and r.started.count(50) == 1
    await _finish(r, task)


async def test_a_running_attempt_is_fenced_and_its_later_cohort_is_held_as_today(
    clock, monkeypatch,
):
    monkeypatch.setenv(SWITCH, "all")
    r = _Gates(blocked={99, 7, 1, 2})
    task, window = await _saturated_call(r)
    assert {99, 7, 1, 2} <= r.fenced_event_ids()
    # A write that returned for 7 while 7 was RUNNING grants nothing: its read
    # may predate the commit, so the cohort is refused and kept owed as today.
    _lease(r, {7})
    assert r.admit_fresh([7], flush_started=1003.0, marks=[_mark(7, 8)]) == frozenset()
    assert 7 not in r._written_queued
    # A right granted to queued 50 is 50's alone: offered beside it, running
    # 7 is still refused, and 50's right is kept for 50's own offer.
    _lease(r, {50, 7}, written={50, 7})
    assert r.admit_fresh([7], flush_started=1003.5, marks=[_mark(7, 9)]) == frozenset()
    assert r.admit_fresh([50, 7], flush_started=1004.0, marks=[_mark(50, 10), _mark(7, 11)]) == {50}
    await _settle()
    assert r.started == [99, 7, 1, 2]
    await _finish(r, task)


async def test_the_lease_holds_a_queued_attempt_back_until_the_write_returns(
    clock, monkeypatch,
):
    monkeypatch.setenv(SWITCH, "all")
    r = _Gates(blocked={99, 7, 1, 2})
    task, window = await _saturated_call(r, queued=(50, 60))
    begin, end = r.writing_begin, r.writing_end
    begin({50})
    r.open(7)  # a worker frees while 50's rows are being written
    await _settle()
    # 60 is taken; 50 stays queued, at the head, and is not started.
    assert r.started == [99, 7, 1, 2, 60]
    assert list(window.live_queue) == [50]
    r.open(1)  # a second worker frees: still nothing eligible but 50
    await _settle()
    assert r.started == [99, 7, 1, 2, 60]
    end({50}, written={50})
    await _settle()
    assert r.started == [99, 7, 1, 2, 60, 50]
    await _finish(r, task)


async def test_a_worker_with_every_queued_event_leased_waits_and_looks_again(
    clock, monkeypatch,
):
    monkeypatch.setenv(SWITCH, "all")
    monkeypatch.setattr(module, "WRITE_LEASE_WAIT_S", 0.01)
    r = _Gates(blocked={99, 7, 1, 2})
    task, window = await _saturated_call(r, queued=(50,))
    r.writing_begin({50})
    r.open(7)
    await _settle()
    assert r.started == [99, 7, 1, 2]
    # The lease ends with no explicit wake needed within the wait bound.
    r._writing.clear()
    await asyncio.sleep(0.05)
    assert r.started == [99, 7, 1, 2, 50]
    await _finish(r, task)


async def test_the_horizon_lifts_the_next_picks_and_held_live_games_only(clock, monkeypatch):
    monkeypatch.setenv(SWITCH, "1")
    r = _Gates(blocked={99, 7, 1, 2})
    task, window = await _saturated_call(r, queued=(50, 60, 70))
    assert list(window.live_queue) == [50, 60, 70]
    fenced = r.fenced_event_ids()
    assert 50 not in fenced and {60, 70, 99, 7, 1, 2} <= fenced
    # A queued live game a reader holds is picked first, so it is lifted too.
    r.reader_held = lambda: frozenset({70})
    fenced = r.fenced_event_ids()
    assert 50 not in fenced and 70 not in fenced and 60 in fenced
    monkeypatch.setenv(SWITCH, "all")
    assert {50, 60, 70}.isdisjoint(r.fenced_event_ids())
    await _finish(r, task)


async def test_the_startup_population_stays_fenced(clock, monkeypatch):
    # The call's own fresh events (a new call, a hand-over's carried cohort)
    # keep today's fence: the three fixed workers claim three, the fourth
    # waits unclaimed and fenced, with ``all`` as with the switch off.
    monkeypatch.setenv(SWITCH, "all")
    r = _Gates(blocked={91, 92, 93, 94})

    async def no_shared_read(event_ids):
        return {}  # order only; each stamp reads its own group in the rig

    r._prepare_groups = no_shared_read
    task = asyncio.create_task(r.refresh([91, 92, 93, 94], flush_started=1000.0))
    await _settle()
    assert len(r.started) == 3, r.started
    assert r.fenced_event_ids() == frozenset({91, 92, 93, 94})
    monkeypatch.delenv(SWITCH, raising=False)
    assert r.fenced_event_ids() == frozenset({91, 92, 93, 94})
    await _finish(r, task)


async def test_held_first_and_the_debt_slots_are_unchanged_by_the_lift(clock, monkeypatch):
    monkeypatch.setenv(SWITCH, "all")
    r = _Gates(blocked={99, 7, 1, 2})
    task, window = await _saturated_call(r, queued=(50, 51))
    r.reader_held = lambda: frozenset({51})
    # 50's cohort rides its queued attempt; 51, held, is still picked first.
    _lease(r, {50})
    assert r.admit_fresh([50], flush_started=1004.0, marks=[_mark(50, 9)]) == {50}
    assert list(window.live_queue) == [50, 51]
    r.open(7)
    await _settle()
    # The freed worker picks held 51 first, then 50 (neither is held up).
    assert r.started == [99, 7, 1, 2, 51, 50]
    # Unheld debt keeps its slots: owed 3 still rides the live allowance.
    r.adopt_pending([3])
    r._live_event_ids.add(3)
    r.admit_fresh((), flush_started=1005.0)
    assert window.live_debts == {3}
    await _finish(r, task)


async def test_the_switch_off_is_todays_fence_and_door(clock, monkeypatch):
    monkeypatch.delenv(SWITCH, raising=False)
    r = _Gates(blocked={99, 7, 1, 2})
    task, window = await _saturated_call(r)
    assert r.fenced_event_ids() == r.holding_event_ids() == frozenset({99, 7, 1, 2, 50})
    # The lease is inert and grants no right; the cohort is refused as HELD.
    r.writing_begin({50})
    r.writing_end({50}, written={50})
    assert not r._written_queued
    assert r.admit_fresh([50], flush_started=1003.0, marks=[_mark(50, 7)]) == frozenset()
    r.open(7)
    await _settle()
    assert r.started == [99, 7, 1, 2, 50]
    await _finish(r, task)


async def test_an_unparseable_or_zero_value_is_off(monkeypatch):
    for raw in ("0", "", "off", "no", "-3", "two"):
        monkeypatch.setenv(SWITCH, raw)
        assert module.stamp_write_under_queued() is None, raw
    monkeypatch.setenv(SWITCH, "all")
    assert module.stamp_write_under_queued() == 0
    monkeypatch.setenv(SWITCH, "9")
    assert module.stamp_write_under_queued() == 9


async def test_the_minute_line_names_absorbed_cohorts_and_lease_waits(clock, monkeypatch):
    monkeypatch.setenv(SWITCH, "all")
    monkeypatch.setattr(module, "WRITE_LEASE_WAIT_S", 0.01)
    r = _Gates(blocked={99, 7, 1, 2})
    r.receipts = module.TailReceipts("polymarket")
    r.stamp_spans = module.StampSpans()
    task, window = await _saturated_call(r, queued=(50,))
    assert "write_under_queued" not in r.stamp_spans.line()
    _lease(r, {50})
    assert r.admit_fresh([50], flush_started=1003.0, marks=[_mark(50, 7)]) == {50}
    r.writing_begin({50})
    r.open(7)
    await asyncio.sleep(0.03)
    r.writing_end({50})
    await _settle()
    line = r.stamp_spans.line()
    assert line.endswith("write_under_queued=absorbed:1,lease_waits:" + line.rsplit(":", 1)[1])
    assert r.stamp_spans.absorbed == 1 and r.stamp_spans.lease_waits >= 1
    r.stamp_spans.reset()
    assert "write_under_queued" not in r.stamp_spans.line()
    await _finish(r, task)


async def test_a_flush_about_to_wait_for_the_call_hands_its_leased_queued_attempts_back(
    clock, monkeypatch,
):
    # The flush joins the running call inside its chunk loop (membership
    # unknown, or a door that closed): a leased event's queued attempt could
    # not start until the lease ended, and the lease could not end until the
    # flush resumed. `writing_yield` hands those attempts back to debt, as a
    # hand-over's shed does, so the call drains; the offer after the event's
    # last chunk admits it fresh.
    monkeypatch.setenv(SWITCH, "all")
    r = _Gates(blocked={99, 7, 1, 2})
    task, window = await _saturated_call(r, queued=(50, 60))
    r.writing_begin({50})
    assert r.writing_yield({50}) == frozenset({50})
    assert list(window.live_queue) == [60] and 50 not in window.holding
    assert r.pending_event_ids() == frozenset({50})
    assert not r._failed_hold_until  # owed now, never held 5 s
    # The call drains without 50: a freed worker takes 60 and the door closes.
    r.open(7, 1, 2, 99)
    await task
    assert r.started == [99, 7, 1, 2, 60] and r._admission is None
    # The flush's write of 50 returns; its offer starts the next call fresh.
    r.writing_end({50}, written={50})
    assert not r._written_queued  # no window: no right
    await asyncio.wait_for(r.refresh([50], flush_started=1010.0), 2)
    assert r.started[-1] == 50 and r.pending_event_ids() == frozenset()
    # Nothing leased, nothing queued: a no-op.
    assert r.writing_yield({50}) == frozenset()
