"""#10090 held-first stamps — a live game a reader holds open is stamped before
live games nobody is watching when stamps queue.

Ship: on a Saturday with 100+ live games, a reader who has a live game open
sees its Polymarket price within a couple of seconds.

Production 15:35-15:40Z 2026-10-31 (Polymarket, G4F13 `6cbd058e`, ~150 live
events, ~14 stamps/s): hold -> stamp 9-21 s, `stamp_wait_reason`
QUEUED_OR_RUNNING 348. The admitted live queue was FIFO, so an open page
waited every other live game's turn. The tail receipts' "held" is the
refresher's ownership of the event, not a reader; the reader signal is the
web hub's `live:event:<id>` subscription (`reader_presence`).

Proved here: the ORDER only — held first among queued live games, unheld ones
still stamped (at least one turn in READER_FIRST_RUN + 1), the switch and an
unreadable/stale held set give the old order, and the cache never blocks.
Not proved: production latency (speed's readout).
"""

import asyncio

import pytest

from app.tasks import live_blend_refresh as module
from app.utils import reader_presence
from app.utils.reader_presence import HeldEventCache, ReaderPresence
from tests.test_admitted_debt_slots_10090 import _Gated, _settle
from tests.test_admitted_live_first_10090 import _gated, _seeded
from tests.test_single_event_commit_10090 import settle_until


def _window(live=(), queue=()):
    w = module._FreshAdmission(1000.0, 1000.0, ())
    w.live_queue.extend(live)
    w.queue.extend(queue)
    return w


def _drain(w, held):
    out = []
    while w.live_queue or w.queue:
        out.append(w.next_queued(held))
    return out


# ── 1. the pick, on the door's own queues ───────────────────────────────────


def test_the_oldest_held_live_game_goes_first_and_the_rest_keep_their_order():
    w = _window(live=[10, 11, 12, 7, 13, 8])
    assert _drain(w, frozenset({7, 8})) == [7, 8, 10, 11, 12, 13]


def test_no_held_set_is_the_old_fifo_order():
    w = _window(live=[10, 11, 7, 12])
    assert _drain(w, frozenset()) == [10, 11, 7, 12]
    w = _window(live=[10, 11, 7, 12])
    assert [w.next_queued() for _ in range(4)] == [10, 11, 7, 12]


def test_unheld_live_games_keep_one_turn_in_reader_first_run_plus_one():
    assert module.READER_FIRST_RUN == 3
    held = frozenset({1, 2, 3, 4, 5, 6, 7})
    w = _window(live=[20, 21, 1, 2, 3, 4, 5, 6, 7])
    assert _drain(w, held) == [1, 2, 3, 20, 4, 5, 6, 21, 7]


def test_held_games_with_no_unheld_one_waiting_spend_none_of_the_run():
    held = frozenset({1, 2, 3, 4, 5})
    w = _window(live=[1, 2, 3, 4, 5])
    assert _drain(w, held) == [1, 2, 3, 4, 5] and w.held_run == 0
    # An unheld game queued afterwards still waits a full run.
    w.live_queue.extend([20, 6, 7, 8, 9])
    assert _drain(w, held | {6, 7, 8, 9}) == [6, 7, 8, 20, 9]


def test_a_held_set_naming_only_unqueued_games_is_the_old_order():
    w = _window(live=[10, 11, 12])
    w.held_run = 2
    assert _drain(w, frozenset({99})) == [10, 11, 12] and w.held_run == 0


def test_live_first_and_its_non_live_turn_are_unchanged_by_the_held_pick():
    assert module.ADMITTED_LIVE_RUN == 3
    w = _window(live=[10, 11, 7, 12, 13], queue=[50, 51])
    # Held 7 leads the live games; after three live starts non-live 50 goes.
    assert _drain(w, frozenset({7})) == [7, 10, 11, 50, 12, 13, 51]


def test_held_non_live_games_are_not_reordered():
    w = _window(queue=[50, 51, 52])
    assert _drain(w, frozenset({52})) == [50, 51, 52]


# ── 2. the door, end to end on the admission rig ────────────────────────────

pytestmark_async = pytest.mark.asyncio


async def _saturated(monkeypatch, held_source):
    """Workers busy with 2, 3, 4; live 5..10 queued in id order."""
    statuses = {1: "scheduled", **{e: "live" for e in range(2, 11)}}
    x = await _seeded(monkeypatch, statuses)
    x.r.reader_held = held_source
    started, release = _gated(x)
    running = asyncio.create_task(x.r.refresh([1], flush_started=1003))
    await settle_until(lambda: started == [1])
    assert x.r.admit_fresh([2, 3, 4], flush_started=1003) == {2, 3, 4}
    await settle_until(lambda: sorted(started) == [1, 2, 3, 4])
    assert x.r.admit_fresh([5, 6, 7, 8, 9, 10], flush_started=1003) == set(range(5, 11))
    assert list(x.r._admission.live_queue) == [5, 6, 7, 8, 9, 10]
    return x, started, release, running


async def _free_workers_one_at_a_time(x, started, release, running, order):
    try:
        for done in order:
            count = len(started)
            release(done)
            await settle_until(lambda: len(started) == count + 1)
        for event_id in range(1, 11):
            release(event_id)
        await asyncio.wait_for(running, 2)
    finally:
        for event_id in range(1, 11):
            release(event_id)
    assert x.r._admission is None and not x.r.pending_event_ids()
    assert x.r.stats["errors"] == 0


@pytestmark_async
async def test_a_held_live_game_queued_last_takes_the_next_free_worker(monkeypatch):
    x, started, release, running = await _saturated(monkeypatch, lambda: frozenset({10}))
    await _free_workers_one_at_a_time(x, started, release, running, (2, 10, 3, 4, 5))
    # Strawman (FIFO): [1, 2, 3, 4, 5, 6, 7, 8, 9, 10] — the open page last.
    assert started == [1, 2, 3, 4, 10, 5, 6, 7, 8, 9]


@pytestmark_async
async def test_unheld_live_games_are_still_stamped_behind_held_ones(monkeypatch):
    held = frozenset({6, 7, 8, 9, 10})
    x, started, release, running = await _saturated(monkeypatch, lambda: held)
    await _free_workers_one_at_a_time(
        x, started, release, running, (2, 3, 4, 6, 7, 8),
    )
    assert started == [1, 2, 3, 4, 6, 7, 8, 5, 9, 10]


@pytestmark_async
async def test_the_switch_off_restores_the_fifo_order(monkeypatch):
    monkeypatch.setenv(module.STAMP_READER_FIRST_ENV, "0")
    x, started, release, running = await _saturated(monkeypatch, lambda: frozenset({10}))
    await _free_workers_one_at_a_time(x, started, release, running, (2,))
    assert started == list(range(1, 11))


@pytestmark_async
async def test_a_failing_held_source_is_the_old_order_and_fails_nothing(monkeypatch):
    def broken():
        raise RuntimeError("redis down")

    x, started, release, running = await _saturated(monkeypatch, broken)
    await _free_workers_one_at_a_time(x, started, release, running, (2,))
    assert started == list(range(1, 11))


@pytestmark_async
async def test_a_large_fresh_population_claims_held_live_games_first(monkeypatch):
    statuses = {e: "live" for e in range(1, 7)}
    x = await _seeded(monkeypatch, statuses)
    x.r.reader_held = lambda: frozenset({5, 6})
    started, release = _gated(x)
    running = asyncio.create_task(x.r.refresh(list(range(1, 7)), flush_started=1003))
    try:
        await settle_until(lambda: len(started) == 3)
        # Live-first, then held, then id (before: [1, 2, 3]).
        assert started == [5, 6, 1]
        for event_id in statuses:
            release(event_id)
        await asyncio.wait_for(running, 2)
    finally:
        for event_id in statuses:
            release(event_id)
    assert started == [5, 6, 1, 2, 3, 4]
    assert not x.r.pending_event_ids()


# ── 3. the live debt allowance ──────────────────────────────────────────────


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


@pytestmark_async
async def test_a_held_live_debt_takes_the_live_allowance_first(clock):
    r = _Gated(blocked={99, 1, 2, 3, 4})
    r.reader_held = lambda: frozenset({4})
    task = await _running_call(r)
    r._live_event_ids.update({1, 2, 3, 4})
    r.adopt_pending([1, 2, 3, 4])
    r.admit_fresh((), flush_started=1001.0)
    await _settle()
    # Strawman (turn order): live_debts == {1}.
    assert r._admission.live_debts == {4} and r._admission.debts == {1}
    assert r.pending_event_ids() == frozenset({2, 3})
    r.release.set()
    await task


@pytestmark_async
async def test_held_live_debt_preference_yields_one_admission_in_four(clock):
    # Pre-game 7 holds the shared slot, so the live allowance alone decides.
    # Held 50 is owed again before every admission; unheld live 1, 2 wait.
    r = _Gated(blocked={99, 7})
    r.reader_held = lambda: frozenset({50})
    task = await _running_call(r)
    r.adopt_pending([7])
    r.admit_fresh((), flush_started=1000.5)
    await _settle()
    assert r._admission.debts == {7}
    r._live_event_ids.update({1, 2, 50})
    r.adopt_pending([1, 2])
    riders = []
    for i in range(8):
        r.adopt_pending([50])
        r.admit_fresh((), flush_started=1001.0 + i)
        riders.append(set(r._admission.live_debts))
        await _settle()
    # Strawman (no bound): fifty every time and 1, 2 never.
    assert riders == [{50}, {50}, {50}, {1}, {50}, {50}, {50}, {2}], riders
    r.release.set()
    await task


# ── 4. the held-event cache ─────────────────────────────────────────────────


class _Starts:
    def __init__(self):
        self.targets = []

    def __call__(self, target):
        self.targets.append(target)

    def run(self):
        target = self.targets.pop(0)
        target()


def _cache(read, now, starts, **kwargs):
    return HeldEventCache(read, clock=lambda: now["t"], start=starts, **kwargs)


def test_the_cache_never_blocks_and_keeps_one_read_in_flight():
    now, starts = {"t": 0.0}, _Starts()
    cache = _cache(lambda: ReaderPresence(event_ids=frozenset({7})), now, starts)
    assert cache.event_ids() == frozenset()  # first call: read started, nothing yet
    assert len(starts.targets) == 1
    now["t"] = 10.0
    assert cache.event_ids() == frozenset() and len(starts.targets) == 1
    starts.run()
    assert cache.event_ids() == frozenset({7}) and cache.reads == 1
    assert len(starts.targets) == 1  # 10 s since the last attempt: a new read


def test_a_failed_read_keeps_the_last_set_until_stale_then_empty():
    now, starts = {"t": 0.0}, _Starts()
    answers = [ReaderPresence(event_ids=frozenset({7}))]

    def read():
        if answers:
            return answers.pop()
        raise reader_presence.PresenceUnreadable("down")

    cache = _cache(read, now, starts, refresh_s=2.0, stale_s=30.0)
    cache.event_ids()
    starts.run()
    for t in (5.0, 20.0, 30.0):
        now["t"] = t
        assert cache.event_ids() == frozenset({7})
        while starts.targets:
            starts.run()
    now["t"] = 30.5
    assert cache.event_ids() == frozenset()
    assert cache.failures >= 2


def test_reads_are_spaced_by_refresh_s():
    now, starts = {"t": 0.0}, _Starts()
    cache = _cache(lambda: ReaderPresence(), now, starts, refresh_s=2.0)
    cache.event_ids()
    starts.run()
    now["t"] = 1.0
    cache.event_ids()
    assert not starts.targets
    now["t"] = 2.0
    cache.event_ids()
    assert len(starts.targets) == 1


def test_a_forked_child_does_not_inherit_the_parents_in_flight_read(monkeypatch):
    now, starts = {"t": 0.0}, _Starts()
    cache = _cache(lambda: ReaderPresence(), now, starts)
    cache.event_ids()
    assert cache._reading_pid is not None and len(starts.targets) == 1
    monkeypatch.setattr(reader_presence.os, "getpid", lambda: -1)
    now["t"] = 5.0
    cache.event_ids()
    assert len(starts.targets) == 2


def test_a_thread_that_cannot_start_lets_the_next_call_try_again():
    now = {"t": 0.0}

    def refuse(target):
        raise RuntimeError("can't start new thread")

    cache = _cache(lambda: ReaderPresence(), now, refuse)
    assert cache.event_ids() == frozenset()
    assert cache._reading_pid is None


def test_the_real_thread_reads_off_the_caller():
    cache = HeldEventCache(lambda: ReaderPresence(event_ids=frozenset({3})))
    cache.event_ids()
    for _ in range(200):
        if cache.reads:
            break
        import time

        time.sleep(0.005)
    assert cache.event_ids() == frozenset({3})


# ── 5. the readout tags ─────────────────────────────────────────────────────


def test_the_reader_held_tag():
    assert module._reader_held_tag(None, 5) == ""
    assert module._reader_held_tag(lambda: frozenset({5}), 5) == " reader_held=1"
    assert module._reader_held_tag(lambda: frozenset(), 5) == " reader_held=0"

    def broken():
        raise RuntimeError

    assert module._reader_held_tag(broken, 5) == ""


def test_a_stamp_wait_line_carries_the_tag(caplog):
    waits = module.StampWaitLog("polymarket")
    with caplog.at_level("INFO", logger=module.logger.name):
        waits.note(5, "QUEUED_OR_RUNNING", (3, 50, 6.0, None), 100.0,
                   run="r", site="admit", held_tag=" reader_held=1")
    assert caplog.records[-1].getMessage().endswith("site=admit reader_held=1")
