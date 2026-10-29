"""#10090 `lock_retry_prompt` — a stamp that gave up on a row lock is attempted
again within about a second, not after every event owed ahead of it.

Production 2026-10-29 17:40:49.7Z (worker-ws): Kalshi event 15335270 logged
`row locked >500ms, re-queued for the next flush (statement bound)` and was
stamped at 17:42:27.5Z (`origin=lock lock_retries=1 held_s=97.796`) with no
attempt in between. The re-queue lands in `_lock_retry`, the same owed queue
as throttle debt. On a busy socket every flush carries fresh prices, so the
queue drains one event per flush (FRESH_FLUSH_PENDING_ATTEMPTS) plus one per
door admission (ADMITTED_DEBT_SLOTS), in continuation order: the new retry
waits out every event already owed.

On, the skip schedules a prompt attempt `LOCK_RETRY_PROMPT_DELAYS_S` later;
the first call (or door admission) that finds it due stamps it as fresh, still
behind the same lock/statement bound. A row that stays locked gets at most
those attempts, then is ordinary debt. Off (today, and any switch error) is
exactly the old queue.
"""

from contextlib import asynccontextmanager

import pytest
from sqlalchemy.sql.dml import Update

import app.tasks.live_blend_refresh as blend_mod
from app.tasks import speed_switches as sw
from app.tasks.speed_switches import OFF
from tests.test_live_blend_refresh import _LockTimeout
from tests.test_single_event_commit_10090 import rig

NAME = "lock_retry_prompt"


@pytest.fixture
def trial(monkeypatch):
    """A `lock_retry_prompt` alternation whose current arm the test sets."""
    arm = {"value": 1, "reads": 0}

    class _Trial:
        def value(self, name, default, at=None):
            if name != NAME:
                return default
            arm["reads"] += 1
            return arm["value"]

        def trip(self, name, error):
            pass

        def state(self, name):
            return OFF

        def arm(self, name, event_id, at=None):
            return False

        def tags(self, event_id, at=None):
            return ""

    monkeypatch.setattr(blend_mod, "_optional_db_trial", lambda: _Trial())
    monkeypatch.setattr(blend_mod, "FRESH_FLUSH_PENDING_ATTEMPTS", 1)
    return arm


@pytest.fixture
def clock(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(blend_mod, "_mono", lambda: now[0])
    return now


def locking(x, locked):
    """Every stamp UPDATE of an event in ``locked`` (a live set) times out on
    its row lock, as Postgres cancels it at the statement bound."""
    inner = x.r._session_factory
    attempts = []

    @asynccontextmanager
    async def factory():
        async with inner() as session:
            execute = session.execute

            async def guarded(statement, *args, **kwargs):
                if isinstance(statement, Update):
                    eid = statement.compile().params["id_1"]
                    attempts.append(eid)
                    if eid in locked:
                        raise _LockTimeout("canceling statement due to lock timeout")
                return await execute(statement, *args, **kwargs)

            session.execute = guarded
            yield session

    x.r._session_factory = factory
    return attempts


async def busy_flushes(x, clock, until, *, fresh=10, period=2.0, limit=30):
    """Fresh-bearing flushes `period` apart (another game ticks every flush)
    until ``until()``; returns how many it took."""
    for n in range(1, limit + 1):
        clock[0] += period
        await x.r.refresh([fresh], flush_started=clock[0])
        if until():
            return n
    return None


# ── the control: a lock skip behind owed debt ─────────────────────────────────


@pytest.mark.parametrize("on", [0, 1])
async def test_a_lock_skipped_price_is_stamped_by_the_next_flush_not_after_the_owed_queue(
        monkeypatch, trial, clock, on):
    trial["value"] = on
    x = rig(monkeypatch, count=10)
    x.r._throttle_deferred = {3, 4, 5, 6, 7, 8, 9}   # quiet games already owed
    locked = {2}
    attempts = locking(x, locked)
    await x.r.refresh([2], flush_started=clock[0])
    assert x.r.stats["lock_skipped"] == 1
    assert x.r._lock_retry == {2}
    locked.clear()                                  # the holder commits

    took = await busy_flushes(x, clock, lambda: 2 in x.committed)
    if on:
        # The next flush (2 s later, past the 1 s delay) stamps it as fresh.
        assert took == 1
        assert attempts.count(2) == 2
    else:
        # Today: one old attempt per flush, the six left in continuation
        # first; the retry waits out all of them.
        assert took == 7
    assert 2 in x.published
    assert x.r.stats["lock_skipped"] == 1


async def test_a_prompt_attempt_waits_for_its_delay(monkeypatch, trial, clock):
    x = rig(monkeypatch, count=10)
    x.r._throttle_deferred = {3, 4, 5, 6}
    locked = {2}
    attempts = locking(x, locked)
    await x.r.refresh([2], flush_started=clock[0])
    locked.clear()
    # 0.5 s later: not due as fresh yet; the one old attempt is the queue head.
    clock[0] += 0.5
    await x.r.refresh([10], flush_started=clock[0])
    assert attempts.count(2) == 1 and 2 not in x.committed
    assert x.r._lock_prompt_at == {2: 1001.0}
    clock[0] += 0.5
    await x.r.refresh([10], flush_started=clock[0])
    assert attempts.count(2) == 2 and 2 in x.committed
    assert x.r._lock_prompt_at == {}


async def test_a_row_that_stays_locked_gets_three_prompt_attempts_then_is_ordinary_debt(
        monkeypatch, trial, clock):
    x = rig(monkeypatch, count=70)
    # A queue longer than the run, so only prompt attempts reach the row.
    x.r._throttle_deferred = set(range(3, 70))
    attempts = locking(x, {2})
    await x.r.refresh([2], flush_started=clock[0])
    prompted = []
    for _ in range(40):                             # 20 s of flushes, 0.5 s apart
        clock[0] += 0.5
        before = x.r._lock_prompt_taken.get(2, 0)
        await x.r.refresh([70], flush_started=clock[0])
        if x.r._lock_prompt_taken.get(2, 0) > before:
            prompted.append(clock[0] - 1000.0)
    # 1 s after the first skip, 2 s after the second, 4 s after the third;
    # then ordinary debt at the back of the queue, never a loop on the row.
    assert prompted == [1.0, 3.0, 7.0]
    assert attempts.count(2) == 4
    assert x.r._lock_prompt_taken == {2: 3}
    assert x.r._lock_prompt_at == {}
    assert x.r.stats["lock_skipped"] == attempts.count(2)
    assert x.r._lock_retry == {2}                   # still owed, as before


@pytest.mark.parametrize("on", [0, 1])
async def test_a_locked_row_alone_costs_at_most_three_extra_attempts(
        monkeypatch, trial, clock, on):
    trial["value"] = on
    x = rig(monkeypatch, count=10)
    attempts = locking(x, {2})
    await x.r.refresh([2], flush_started=clock[0])
    for _ in range(40):
        clock[0] += 0.5
        await x.r.refresh([10], flush_started=clock[0])
    # Alone in the queue it is the old attempt of every flush either way; a
    # prompt attempt takes the place of that flush's old attempt.
    assert attempts.count(2) == 41
    assert x.r.stats["lock_skipped"] == 41


async def test_a_new_run_of_skips_after_a_stamp_gets_its_prompt_attempts_again(
        monkeypatch, trial, clock):
    x = rig(monkeypatch, count=10)
    locked = {2}
    locking(x, locked)
    await x.r.refresh([2], flush_started=clock[0])
    locked.clear()
    clock[0] += 2
    await x.r.refresh([10], flush_started=clock[0])
    assert 2 in x.committed
    clock[0] += 2
    await x.r.refresh([10], flush_started=clock[0])  # the run is over
    assert x.r._lock_prompt_taken == {}
    locked.add(2)
    x.r._last_written_value.pop(2)                  # a new price to stamp
    clock[0] += 2
    await x.r.refresh([2], flush_started=clock[0])
    assert x.r._lock_prompt_at == {2: clock[0] + 1.0}


async def test_a_prompt_retry_the_caller_still_writes_stays_owed_and_scheduled(
        monkeypatch, trial, clock):
    x = rig(monkeypatch, count=10)
    locked = {2}
    attempts = locking(x, locked)
    await x.r.refresh([2], flush_started=clock[0])
    locked.clear()
    clock[0] += 2
    await x.r.refresh([10], flush_started=clock[0], defer_event_ids={2})
    assert attempts.count(2) == 1
    assert x.r._lock_retry == {2} and 2 in x.r._lock_prompt_at
    clock[0] += 2
    await x.r.refresh([10], flush_started=clock[0])
    assert 2 in x.committed


async def test_a_quiet_flush_prompt_retry_keeps_the_flush_time_budget(
        monkeypatch, trial, clock):
    x = rig(monkeypatch, count=10)
    locked = {2}
    locking(x, locked)
    await x.r.refresh([2], flush_started=clock[0])
    locked.clear()
    x.r._throttle_deferred = {3, 4, 5}
    clock[0] += 2
    await x.r.refresh_pending(flush_started=clock[0])
    # The prompt retry and every owed event: a quiet flush is not made
    # fresh-bearing (one old attempt) by a lock retry.
    assert sorted(x.committed) == [2, 3, 4, 5]
    assert not x.r._pending_fresh_flush


async def running_call_with_a_due_prompt(x, clock):
    """A running call is held stamping event 9; its own stamp of event 11
    skipped on the row lock and went back to debt. The holder then commits,
    11's prompt attempt comes due, and lower-id quiet games are owed ahead of
    it in the door's debt order."""
    import asyncio

    locked = {11}
    attempts = locking(x, locked)
    running = asyncio.create_task(x.r.refresh([9, 11], flush_started=clock[0]))
    async with asyncio.timeout(1):
        while 9 not in attempts or x.r.stats["lock_skipped"] < 1:
            await asyncio.sleep(0)
    locked.clear()
    x.r._throttle_deferred |= {3, 4}
    clock[0] += 2
    return running, attempts


async def test_a_running_call_admits_a_due_prompt_retry_beside_its_cohort(
        monkeypatch, trial, clock):
    import asyncio

    x = rig(monkeypatch, count=12, block=True, blocked=(9,))
    running, attempts = await running_call_with_a_due_prompt(x, clock)
    cohort = x.r.admit_fresh([10], flush_started=clock[0])
    assert cohort == frozenset({10})                # the caller's own only
    # Beside the cohort and outside the one debt slot (which takes 3).
    async with asyncio.timeout(1):
        while not {3, 10, 11}.issubset(x.committed):
            await asyncio.sleep(0)
    assert x.r._lock_prompt_at == {}
    x.release.set()
    await running
    assert 11 in x.published


async def test_a_door_leaves_a_prompt_retry_the_caller_still_writes_scheduled(
        monkeypatch, trial, clock):
    import asyncio

    x = rig(monkeypatch, count=12, block=True, blocked=(9,))
    running, attempts = await running_call_with_a_due_prompt(x, clock)
    x.r.admit_fresh([10], flush_started=clock[0], defer_event_ids={11})
    async with asyncio.timeout(1):
        while not {3, 10}.issubset(x.committed):
            await asyncio.sleep(0)
    assert attempts.count(11) == 1
    assert 11 in x.r._lock_retry and 11 in x.r._lock_prompt_at
    x.release.set()
    await running


async def test_the_switch_is_read_once_per_row_lock_skip(monkeypatch, trial, clock):
    x = rig(monkeypatch, count=3)
    locking(x, {2})
    await x.r.refresh([1], flush_started=clock[0])
    assert trial["reads"] == 0                      # no skip, no read
    await x.r.refresh([2], flush_started=clock[0])
    assert trial["reads"] == 1


async def test_off_the_skip_schedules_nothing(monkeypatch, trial, clock):
    trial["value"] = 0
    x = rig(monkeypatch, count=3)
    locking(x, {2})
    await x.r.refresh([2], flush_started=clock[0])
    assert x.r._lock_retry == {2}
    assert x.r._lock_prompt_at == {} and x.r._lock_prompt_taken == {}


def test_the_lock_retry_prompt_arm_is_off_on_any_switch_error(monkeypatch):
    def broken():
        raise RuntimeError("switchboard unreadable")

    monkeypatch.setattr(blend_mod, "_optional_db_trial", broken)
    assert blend_mod._lock_retry_prompt() is False


# ── the switchboard entry ─────────────────────────────────────────────────────


@pytest.mark.parametrize("mode, kwargs", [
    ("ab", {"half": 0}),
    ("alternate", {"a": 1, "b": 1, "period_s": 60}),
    ("alternate", {"a": 0, "b": 2, "period_s": 60}),
])
def test_a_lock_retry_prompt_trial_outside_the_limits_is_refused(mode, kwargs):
    assert sw.validate(NAME, mode, **kwargs) is not None


def test_a_lock_retry_prompt_alternation_of_off_and_on_is_accepted():
    assert sw.validate(NAME, "alternate", a=0, b=1, period_s=60) is None
    assert sw.today(NAME) == 0
    assert NAME in sw.SWITCHES
    assert blend_mod.LOCK_RETRY_PROMPT_SWITCH == NAME
