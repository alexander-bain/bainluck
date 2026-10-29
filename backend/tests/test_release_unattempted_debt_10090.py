"""#10090 R8b — `release_unattempted_debt`: a mixed call's unattempted old events
leave its fence when the call knows which those are, not after its fresh stamps.

Pattern B path (ii): a mixed `refresh` opened its door with every due event in
`holding` and stamped its fresh population first, to completion. The old events
it would never attempt this flush (all but one under FRESH_FLUSH_PENDING_ATTEMPTS
= 1) stayed fenced through those fresh stamps: `admit_fresh` reported them HELD,
the caller fenced their newer prices, and 15330559 sat 21.7-30.4 s with its
commits stopped. With the switch on:

* a carried continuation head under one remaining attempt: the rest leave the
  fence BEFORE the fresh stamps (no read decides the choice);
* otherwise the old population's live-first read runs beside the fresh stamps
  (only when they leave a stamp worker free) and the rest leave the fence when
  it returns; the attempts reread their own groups, since that read predates the
  fresh stamps.

Off (today, and any switch error) is today's behaviour.
"""

import asyncio

import pytest

import app.tasks.live_blend_refresh as blend_mod
from app.tasks.speed_switches import OFF
from tests.test_single_event_commit_10090 import rig, settle_until

NAME = "release_unattempted_debt"


@pytest.fixture
def trial(monkeypatch):
    """A `release_unattempted_debt` alternation whose current arm the test sets."""
    arm = {"value": 1, "tripped": [], "reads": 0}

    class _Trial:
        def value(self, name, default, at=None):
            if name != NAME:
                return default
            arm["reads"] += 1
            return default if arm["tripped"] else arm["value"]

        def trip(self, name, error):
            arm["tripped"].append((name, error))

        def state(self, name):
            return OFF

        def arm(self, name, event_id, at=None):
            return False

        def tags(self, event_id, at=None):
            return ""

    monkeypatch.setattr(blend_mod, "_optional_db_trial", lambda: _Trial())
    monkeypatch.setattr(blend_mod, "FRESH_FLUSH_PENDING_ATTEMPTS", 1)
    return arm


def stamping(x, event_id):
    return any(event_id in s.event_ids for s in x.sessions)


async def fresh_stamp_held(x, event_id=5):
    await settle_until(lambda: stamping(x, event_id))
    for _ in range(5):
        await asyncio.sleep(0)


def hold_reads(x):
    """Every shared read waits until released; record what it was asked for."""
    calls, release = [], asyncio.Event()
    prepare = x.r._prepare_groups

    async def held(event_ids):
        calls.append(sorted(event_ids))
        await release.wait()
        return await prepare(event_ids)

    x.r._prepare_groups = held
    return calls, release


# ── the control: HELD at admission today, released with the switch on ────────


@pytest.mark.parametrize("on", [0, 1])
async def test_a_carried_head_call_releases_the_rest_before_its_fresh_stamps(
        monkeypatch, trial, on):
    trial["value"] = on
    x = rig(monkeypatch, count=5, block=True, blocked=(5,))
    x.r._lock_retry = {1, 2, 3, 4}
    x.r._pending_continuation = [2, 3]
    task = asyncio.create_task(x.r.refresh([5], flush_started=1000))
    await fresh_stamp_held(x)
    # The fresh stamp of 5 is held (a slow write). Event 3 commits a newer price.
    if on:
        assert x.r.holding_event_ids() == frozenset({2, 5})
        assert x.r._pending_continuation == [2, 3]
        assert x.r.admit_fresh([3], flush_started=1001) == frozenset({3})
    else:
        assert x.r.holding_event_ids() == frozenset({1, 2, 3, 4, 5})
        assert x.r.admit_fresh([3], flush_started=1001) == frozenset()   # HELD
    x.release.set()
    async with asyncio.timeout(2):
        await task
    # The one old attempt is the same head either way, after the fresh price.
    assert x.committed.index(5) < x.committed.index(2)
    assert x.committed.count(2) == 1
    if on:
        assert 3 in x.committed
        assert x.r.pending_event_ids().isdisjoint({2, 3, 5})
    else:
        assert 3 not in x.committed
        assert x.r.pending_event_ids() == frozenset({1, 3, 4})
        assert x.r._pending_continuation == [3]


@pytest.mark.parametrize("on", [0, 1])
async def test_without_a_head_the_rest_leave_the_fence_when_the_live_first_read_returns(
        monkeypatch, trial, on):
    trial["value"] = on
    x = rig(monkeypatch, count=5, block=True, blocked=(5,), statuses={
        1: "scheduled", 2: "scheduled", 3: "live", 4: "scheduled", 5: "live",
    })
    x.r._lock_retry = {1, 2, 3, 4}
    task = asyncio.create_task(x.r.refresh([5], flush_started=1000))
    await fresh_stamp_held(x)
    if on:
        await settle_until(lambda: len(x.r.holding_event_ids()) == 2)
        assert x.r.holding_event_ids() == frozenset({3, 5})   # live-first: 3
        assert x.r._pending_continuation == [1, 2, 4]
        assert x.r.admit_fresh([1], flush_started=1001) == frozenset({1})
    else:
        assert x.r.holding_event_ids() == frozenset({1, 2, 3, 4, 5})
        assert x.r.admit_fresh([1], flush_started=1001) == frozenset()
    x.release.set()
    async with asyncio.timeout(2):
        await task
    assert x.committed.index(5) < x.committed.index(3)
    assert x.committed.count(3) == 1
    if on:
        assert 1 in x.committed
    else:
        assert 1 not in x.committed
        assert x.r.pending_event_ids() == frozenset({1, 2, 4})
        assert x.r._pending_continuation == [1, 2, 4]


async def test_two_attempts_left_release_only_past_the_second(monkeypatch, trial):
    monkeypatch.setattr(blend_mod, "FRESH_FLUSH_PENDING_ATTEMPTS", 2)
    x = rig(monkeypatch, count=5, block=True, blocked=(5,), statuses={
        1: "scheduled", 2: "live", 3: "scheduled", 4: "live", 5: "live",
    })
    x.r._lock_retry = {1, 2, 3, 4}
    task = asyncio.create_task(x.r.refresh([5], flush_started=1000))
    await fresh_stamp_held(x)
    await settle_until(lambda: len(x.r.holding_event_ids()) == 3)
    assert x.r.holding_event_ids() == frozenset({2, 4, 5})
    assert x.r._pending_continuation == [1, 3]
    x.release.set()
    async with asyncio.timeout(2):
        await task
    assert [e for e in x.committed if e != 5] == [2, 4]
    assert x.r.pending_event_ids() == frozenset({1, 3})


@pytest.mark.parametrize("on", [0, 1])
async def test_the_attempts_after_an_early_read_reread_their_own_groups(monkeypatch, trial, on):
    trial["value"] = on
    monkeypatch.setattr(blend_mod, "FRESH_FLUSH_PENDING_ATTEMPTS", 2)
    x = rig(monkeypatch, count=5, statuses={
        1: "scheduled", 2: "live", 3: "scheduled", 4: "live", 5: "live",
    })
    x.r._lock_retry = {1, 2, 3, 4}
    seen = []
    real = x.r._refresh_batch

    async def record(event_ids, now, **kw):
        seen.append((list(event_ids), kw.get("prepared") is None))
        return await real(event_ids, now, **kw)

    x.r._refresh_batch = record
    await x.r.refresh([5], flush_started=1000)
    # Off: the shared read happens after the fresh stamp and the attempts use it.
    assert seen == [([5], True), ([2], bool(on)), ([4], bool(on))]


async def test_fresh_stamps_that_fill_the_workers_keep_todays_fence(monkeypatch, trial):
    x = rig(monkeypatch, count=7, block=True, blocked=(5, 6, 7), statuses={
        1: "scheduled", 2: "live", 3: "scheduled", 4: "scheduled",
        5: "live", 6: "live", 7: "live",
    })
    x.r._lock_retry = {1, 2, 3, 4}
    calls, release = hold_reads(x)
    task = asyncio.create_task(x.r.refresh([5, 6, 7], flush_started=1000))
    await fresh_stamp_held(x, 7)
    assert calls == []                      # no read beside a full set of fresh stamps
    assert x.r.holding_event_ids() == frozenset(range(1, 8))
    release.set()
    x.release.set()
    async with asyncio.timeout(2):
        await task
    assert calls == [[1, 2, 3, 4]]
    assert [e for e in x.committed if e not in (5, 6, 7)] == [2]


async def test_one_old_event_or_no_trial_changes_nothing(monkeypatch, trial):
    x = rig(monkeypatch, count=5, block=True, blocked=(5,))
    x.r._lock_retry = {2}
    task = asyncio.create_task(x.r.refresh([5], flush_started=1000))
    await fresh_stamp_held(x)
    assert x.r.holding_event_ids() == frozenset({2, 5})
    assert trial["reads"] == 0              # nothing to release: no switch read
    x.release.set()
    async with asyncio.timeout(2):
        await task
    assert x.committed == [5, 2]


# ── failure and cancellation ─────────────────────────────────────────────────


async def test_a_failed_early_read_keeps_todays_failure_and_trips_the_trial(monkeypatch, trial):
    x = rig(monkeypatch, count=5)
    x.r._lock_retry = {1, 2, 3, 4}

    async def failing(event_ids):
        raise RuntimeError("old population read failed")

    x.r._prepare_groups = failing
    await x.r.refresh([5], flush_started=1000)
    assert x.committed == [5]
    assert x.r.pending_event_ids() == frozenset({1, 2, 3, 4})
    assert [name for name, _ in trial["tripped"]] == [NAME]


async def test_a_cancel_during_the_fresh_stamps_joins_the_early_read(monkeypatch, trial):
    x = rig(monkeypatch, count=5, block=True, blocked=(5,))
    x.r._lock_retry = {1, 2, 3, 4}
    calls, _release = hold_reads(x)
    task = asyncio.create_task(x.r.refresh([5], flush_started=1000))
    await fresh_stamp_held(x)
    assert calls == [[1, 2, 3, 4]]          # the early read is in flight, held
    early = [
        t for t in asyncio.all_tasks()
        if "read_old_population" in t.get_coro().__qualname__
    ]
    assert len(early) == 1 and not early[0].done()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        # Bounded: a call that never cancels its held read would never return.
        await asyncio.wait_for(asyncio.shield(task), 1)
    assert early[0].cancelled()             # joined before the call returned
    assert x.r.pending_event_ids() == frozenset({1, 2, 3, 4, 5})
    assert not x.r._failed_hold_until
