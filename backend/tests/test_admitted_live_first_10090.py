"""#10090 — an admitted LIVE game is stamped ahead of queued non-live games.

Ship: a changed eligible probability for a live game reaches the held event
page within a second while the running refresh is busy with other games.

Production stage trace (v5727 064f24bd, 02:14Z 2026-10-15, event 15329526):
the live game's cohort committed and was ADMITTED to the running refresh at
mono 3563087.232; its stamp (attempt 13) began at 3563093.658, 6.43 s later,
then took 66 us to a session and 95 ms to commit. In between, a flush found
it QUEUED_NOT_STARTED with 134 events held by that call. That establishes a
6.43 s wait before this attempt started; it does NOT establish 134 queued
predecessors, their status, or what the three workers were waiting on, so
"pregame games queued ahead of it" remains a hypothesis. (Its original input
was transient, so this is not itself a sustained-price latency.) The
admitted-cohort queue was first-come; the call's own population was already
stamped live-first (`test_live_stamps_lead_within_fresh_and_pending
_but_fresh_stays_first`), and the admitted queue now follows the same order.
This helps a known-live event over queued non-live ones when a worker comes
free; it cannot preempt occupied workers, and it does not touch the
dominant 5.26 s pre-flush residual, a different boundary (the game flush's
serial tail; candidate PR11053 moves the prop part of it).

Bound: queued non-live games still progress — after ADMITTED_LIVE_RUN live
stamps in a row, a waiting non-live game is stamped next. Status comes only
from this refresher's own reads: a never-read or newly live game queues as
non-live until its read says live. Cancellation with both queues occupied
keeps every unstamped event owed. Queue-order and recovery controls on the
existing rig; no subsecond timing claim.
"""
import asyncio

import pytest

from app.tasks import live_blend_refresh as module
from tests.test_single_event_commit_10090 import rig, settle_until

pytestmark = pytest.mark.asyncio


def _gated(x):
    """Every stamp after this waits for its own event's gate; record the
    order stamps START in (the moment a worker takes an event off the
    queue and begins its attempt)."""
    attempt = x.r._refresh_batch
    started, gates = [], {}

    async def stamp(ids, *args, **kwargs):
        (event_id,) = ids
        started.append(event_id)
        gate = gates.setdefault(event_id, asyncio.Event())
        await gate.wait()
        await attempt(ids, *args, **kwargs)

    x.r._refresh_batch = stamp

    def release(event_id):
        gates.setdefault(event_id, asyncio.Event()).set()

    return started, release


async def _seeded(monkeypatch, statuses):
    x = rig(monkeypatch, count=len(statuses), statuses=statuses)
    # Every game has been stamped once in this run, so the refresher has
    # read each one's status, exactly as a running consumer has.
    await x.r.refresh(sorted(statuses), flush_started=1000)
    assert sorted(x.published) == sorted(statuses)
    return x


async def test_an_admitted_live_game_starts_before_earlier_queued_non_live_games(
    monkeypatch,
):
    statuses = {1: "scheduled", 2: "scheduled", 3: "scheduled", 4: "scheduled",
                5: "scheduled", 6: "scheduled", 7: "live"}
    x = await _seeded(monkeypatch, statuses)
    started, release = _gated(x)
    running = asyncio.create_task(x.r.refresh([1], flush_started=1003))
    try:
        await settle_until(lambda: started == [1])
        # Five non-live games commit and are admitted: three take the
        # admitted workers, two wait in the queue.
        assert x.r.admit_fresh([2, 3, 4, 5, 6], flush_started=1003) == {2, 3, 4, 5, 6}
        await settle_until(lambda: sorted(started) == [1, 2, 3, 4])
        # Then the live game's newer price commits and is admitted.
        assert x.r.admit_fresh([7], flush_started=1003) == {7}
        await asyncio.sleep(0)
        assert 7 in x.r.holding_event_ids() and 7 not in started
        # The first worker to come free takes the live game, not game 5.
        release(2)
        await settle_until(lambda: len(started) == 5)
        assert started[-1] == 7, started
        for event_id in (1, 3, 4, 5, 6, 7):
            release(event_id)
        await asyncio.wait_for(running, 2)
    finally:
        for event_id in range(1, 8):
            release(event_id)
    assert started == [1, 2, 3, 4, 7, 5, 6]
    assert x.r._admission is None and not x.r.pending_event_ids()
    assert x.r.stats["errors"] == 0


async def test_queued_non_live_games_still_progress_behind_a_run_of_live_games(
    monkeypatch,
):
    assert module.ADMITTED_LIVE_RUN == 3
    statuses = {1: "scheduled", 2: "scheduled", 3: "scheduled", 4: "scheduled",
                5: "scheduled", 6: "live", 7: "live", 8: "live", 9: "live",
                10: "live"}
    x = await _seeded(monkeypatch, statuses)
    started, release = _gated(x)
    running = asyncio.create_task(x.r.refresh([1], flush_started=1003))
    try:
        await settle_until(lambda: started == [1])
        assert x.r.admit_fresh([2, 3, 4, 5], flush_started=1003) == {2, 3, 4, 5}
        await settle_until(lambda: sorted(started) == [1, 2, 3, 4])
        assert x.r.admit_fresh([6, 7, 8, 9, 10], flush_started=1003) == {
            6, 7, 8, 9, 10,
        }
        # One worker at a time comes free; each start is the next decision.
        for done in (2, 3, 4, 6, 7, 8):
            count = len(started)
            release(done)
            await settle_until(lambda: len(started) == count + 1)
        # Three live stamps in a row, then the waiting non-live game 5,
        # then the remaining live games.
        assert started[4:] == [6, 7, 8, 5, 9, 10], started
        for event_id in range(1, 11):
            release(event_id)
        await asyncio.wait_for(running, 2)
    finally:
        for event_id in range(1, 11):
            release(event_id)
    assert started == [1, 2, 3, 4, 6, 7, 8, 5, 9, 10]
    assert x.r._admission is None and not x.r.pending_event_ids()


async def test_status_learned_from_the_latest_read_decides_the_order(monkeypatch):
    # A game that has finished (status no longer live on its latest read) no
    # longer leads, and one first read live now does: precedence follows the
    # status the stamps actually read, never a stale or guessed one.
    statuses = {1: "scheduled", 2: "scheduled", 3: "scheduled", 4: "scheduled",
                5: "live", 6: "scheduled"}
    x = await _seeded(monkeypatch, statuses)
    assert x.r._live_event_ids == {5}
    for m, e in x.rows:
        if e.id == 5:
            e.status = "final"
        if e.id == 6:
            e.status = "live"
    await x.r.refresh([5, 6], flush_started=1003)
    assert x.r._live_event_ids == {6}
    started, release = _gated(x)
    running = asyncio.create_task(x.r.refresh([1], flush_started=1006))
    try:
        await settle_until(lambda: started == [1])
        assert x.r.admit_fresh([2, 3, 4, 5, 6], flush_started=1006) == {2, 3, 4, 5, 6}
        await settle_until(lambda: len(started) == 4)
        # Within one cohort the live game is claimed first, then id order.
        assert started == [1, 6, 2, 3], started
        for event_id in range(1, 7):
            release(event_id)
        await asyncio.wait_for(running, 2)
    finally:
        for event_id in range(1, 7):
            release(event_id)
    assert started == [1, 6, 2, 3, 4, 5]


async def test_live_stamps_with_nothing_else_waiting_do_not_count_against_the_run(
    monkeypatch,
):
    # The run counts live stamps that started while a non-live event waited.
    # Live games stamped through an otherwise empty queue spend none of it:
    # a non-live event admitted afterwards still waits its three live turns.
    statuses = {1: "scheduled", 2: "live", 3: "live", 4: "live", 5: "live",
                6: "live", 7: "live", 8: "live", 9: "scheduled"}
    x = await _seeded(monkeypatch, statuses)
    started, release = _gated(x)
    running = asyncio.create_task(x.r.refresh([1], flush_started=1003))
    try:
        await settle_until(lambda: started == [1])
        assert x.r.admit_fresh([2, 3, 4, 5], flush_started=1003) == {2, 3, 4, 5}
        await settle_until(lambda: sorted(started) == [1, 2, 3, 4])
        count = len(started)
        release(2)
        await settle_until(lambda: len(started) == count + 1)
        assert started[-1] == 5 and x.r._admission.live_run == 0
        assert x.r.admit_fresh([9, 6, 7, 8], flush_started=1003) == {6, 7, 8, 9}
        for done in (3, 4, 5, 6):
            count = len(started)
            release(done)
            await settle_until(lambda: len(started) == count + 1)
        assert started[5:] == [6, 7, 8, 9], started
        for event_id in range(1, 10):
            release(event_id)
        await asyncio.wait_for(running, 2)
    finally:
        for event_id in range(1, 10):
            release(event_id)
    assert x.r._admission is None and not x.r.pending_event_ids()


def _mark(event_id, seq):
    return module.InputMark(
        seq=seq, event_id=event_id, outcome_id=10 * event_id,
        probability=0.5 + seq / 100, kind="price", recv_wall=1000 + seq,
        recv_mono=100 + seq, venue_ts_ms=None, event_ordinal=seq,
    )


async def test_cancel_with_both_queues_occupied_keeps_every_unstamped_event_owed(
    monkeypatch,
):
    # Root's mixed-queue boundary: known-live and non-live work queued behind
    # occupied workers, the owner cancelled. Every event not yet committed is
    # owed again (both queues, and the workers' own), the one that committed
    # is not stamped twice, a newer same-event input keeps its newest mark,
    # and the next quiet flush stamps them all.
    statuses = {1: "scheduled", 2: "scheduled", 3: "scheduled", 4: "scheduled",
                5: "scheduled", 6: "live", 7: "live"}
    x = await _seeded(monkeypatch, statuses)
    receipts = x.r.receipts = module.TailReceipts("polymarket")
    receipts._live_events = set(statuses)
    started, release = _gated(x)
    running = asyncio.create_task(x.r.refresh([1], flush_started=1003))
    try:
        await settle_until(lambda: started == [1])
        assert x.r.admit_fresh(
            [2, 3, 4], flush_started=1003, marks=[_mark(e, e) for e in (2, 3, 4)],
        ) == {2, 3, 4}
        await settle_until(lambda: sorted(started) == [1, 2, 3, 4])
        assert x.r.admit_fresh(
            [5, 6, 7], flush_started=1003, marks=[_mark(e, e) for e in (5, 6, 7)],
        ) == {5, 6, 7}
        window = x.r._admission
        assert list(window.live_queue) == [6, 7] and list(window.queue) == [5]
        release(2)  # game 2 commits; its worker takes live game 6
        await settle_until(lambda: len(started) == 5)
        assert started[-1] == 6
        assert list(window.live_queue) == [7] and list(window.queue) == [5]
        # A newer price for queued game 5: refused while it is held, kept owed
        # with its mark, as the flush does.
        assert x.r.admit_fresh([5], flush_started=1003.25, marks=[_mark(5, 9)]) == set()
        x.r.keep_owed([5], marks=[_mark(5, 9)])
        running.cancel()
        with pytest.raises(asyncio.CancelledError):
            await running
    finally:
        for event_id in statuses:
            release(event_id)
        await asyncio.gather(running, return_exceptions=True)
    assert x.r._admission is None
    # Game 2's stamp completed before the cancel: it alone is not owed.
    assert x.r.pending_event_ids() == frozenset({1, 3, 4, 5, 6, 7})
    assert receipts._open[5].rev.seq == 9  # the newest input, not seq 5
    stamped_from = len(started)
    await x.r.refresh_pending(flush_started=1006)
    assert not x.r.pending_event_ids()
    # Recovery stamps every owed event once, the live ones first; game 2
    # is not stamped again.
    assert started[stamped_from:] == [6, 7, 1, 3, 4, 5]
    assert x.r.stats["errors"] == 0


async def test_an_event_never_read_is_not_treated_as_live(monkeypatch):
    # The order uses only a status this refresher has READ. A live game it
    # has never stamped (first seen, or newly live since its last read)
    # queues as non-live, in arrival order, until its own read says live.
    statuses = {1: "scheduled", 2: "scheduled", 3: "scheduled", 4: "scheduled",
                5: "scheduled", 6: "live"}
    x = rig(monkeypatch, count=6, statuses=statuses)
    await x.r.refresh([1, 2, 3, 4, 5], flush_started=1000)
    assert x.r._live_event_ids == set()  # game 6 has never been read
    started, release = _gated(x)
    running = asyncio.create_task(x.r.refresh([1], flush_started=1003))
    try:
        await settle_until(lambda: started == [1])
        assert x.r.admit_fresh([2, 3, 4], flush_started=1003) == {2, 3, 4}
        await settle_until(lambda: sorted(started) == [1, 2, 3, 4])
        assert x.r.admit_fresh([5, 6], flush_started=1003) == {5, 6}
        assert list(x.r._admission.queue) == [5, 6]
        assert not x.r._admission.live_queue
        for event_id in statuses:
            release(event_id)
        await asyncio.wait_for(running, 2)
    finally:
        for event_id in statuses:
            release(event_id)
    assert started == [1, 2, 3, 4, 5, 6]
    assert x.r._live_event_ids == {6}  # its own read taught it
