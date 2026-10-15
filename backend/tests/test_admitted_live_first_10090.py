"""#10090 — an admitted LIVE game is stamped ahead of queued non-live games.

Ship: a changed eligible probability for a live game reaches the held event
page within a second while the running refresh is busy with other games.

Production stage trace (v5727 064f24bd, 02:14Z 2026-10-15, event 15329526):
the live game's cohort committed and was ADMITTED to the running refresh at
mono 3563087.232; its stamp (attempt 13) began at 3563093.658, 6.43 s later,
then took 66 us to a session and 95 ms to commit. In between, a flush found
it QUEUED_NOT_STARTED with 134 events held by that call. Attempt 14 waited
6.67 s the same way. The wait sat in the admitted-cohort queue, which was
first-come: every game admitted earlier, live or not, was stamped first, so
a live game waited out the whole held set. The call's own population was
already stamped live-first (`test_live_stamps_lead_within_fresh_and_pending
_but_fresh_stays_first`); the admitted queue now follows the same order.

Bound: queued non-live games still progress — after ADMITTED_LIVE_RUN live
stamps in a row, a waiting non-live game is stamped next. Source/progress
controls on the existing rig, not production timing.
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
