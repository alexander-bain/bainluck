"""Unit tests for the bounded request-path cache primitives (Queue 271).

Covers the pieces GET /api/feed and GET /api/calibration rely on to survive a
Redis stall or a cold-compute miss-storm without holding a request to the Heroku
router cutoff (#1459/#1197). The end-to-end mapping onto the C55 failure contract
lives in tests/integration/test_cache_failure_seam.py.
"""

from __future__ import annotations

import asyncio
import time

import pytest

from app.utils import request_cache as rc


@pytest.fixture(autouse=True)
def _clean_state():
    rc._reset_last_good_for_tests()
    rc._reset_inflight_for_tests()
    yield
    rc._reset_last_good_for_tests()
    rc._reset_inflight_for_tests()


# --- bounded_redis_call -------------------------------------------------------
async def test_bounded_call_ok():
    async def _get():
        return b"value"

    res = await rc.bounded_redis_call(_get)
    assert res.is_ok and res.value == b"value"
    assert not res.is_failure


async def test_bounded_call_clean_miss_is_not_failure():
    async def _get():
        return None

    res = await rc.bounded_redis_call(_get)
    assert res.is_miss
    assert not res.is_failure  # a clean miss must be distinguishable from an error


async def test_bounded_call_connection_error_is_failure_not_miss():
    async def _get():
        raise ConnectionError("redis down")

    res = await rc.bounded_redis_call(_get)
    assert res.status == rc.ERROR
    assert res.is_failure and not res.is_miss


async def test_bounded_call_terminates_under_deadline_on_hang():
    async def _hang():
        await asyncio.sleep(30)

    loop = asyncio.get_running_loop()
    started = loop.time()
    res = await rc.bounded_redis_call(_hang, deadline_ms=200)
    elapsed = loop.time() - started
    assert res.status == rc.TIMEOUT
    assert res.is_failure
    assert elapsed < 1.0  # bounded well under any router cutoff


async def test_bounded_call_reraises_cancellation():
    async def _hang():
        await asyncio.sleep(30)

    task = asyncio.ensure_future(rc.bounded_redis_call(_hang, deadline_ms=5000))
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


# --- process-local last-good --------------------------------------------------
def test_last_good_round_trip():
    rc.remember_last_good("k", {"a": 1})
    assert rc.recall_last_good("k") == {"a": 1}


def test_last_good_ignores_none_and_empty_key():
    rc.remember_last_good("", {"a": 1})
    rc.remember_last_good("k", None)
    assert rc.recall_last_good("") is None
    assert rc.recall_last_good("k") is None


def test_last_good_age_bound():
    rc.remember_last_good("k", {"a": 1})
    # `recall_last_good` expires on `elapsed > max_age_s`, so with max_age_s=0 the
    # entry must be measurably older than 0s. Two adjacent `time.time()` calls can
    # return the SAME float, making elapsed exactly 0.0 and the entry not-yet-
    # expired — an intermittent red with no defect behind it. Sleep past the clock
    # granularity so the assertion tests the age bound, not the timer.
    time.sleep(0.002)
    assert rc.recall_last_good("k", max_age_s=0) is None  # already older than 0s
    assert rc.recall_last_good("k", max_age_s=1000) == {"a": 1}


# --- singleflight -------------------------------------------------------------
async def test_singleflight_runs_build_once_under_stampede():
    calls = {"n": 0}
    started = asyncio.Event()
    release = asyncio.Event()

    async def _leader_build():
        calls["n"] += 1
        started.set()
        await release.wait()
        return {"built": True}

    async def _request():
        is_leader, fut = rc.begin_build("key")
        if is_leader:
            try:
                result = await _leader_build()
                rc.finish_build("key", fut, result=result)
                return ("leader", result)
            except BaseException as exc:  # pragma: no cover - defensive
                rc.finish_build("key", fut, exc=exc)
                raise
        else:
            return ("waiter", await asyncio.shield(fut))

    # Fire 20 identical concurrent requests; exactly one builds.
    tasks = [asyncio.ensure_future(_request()) for _ in range(20)]
    await started.wait()
    release.set()
    results = await asyncio.gather(*tasks)

    assert calls["n"] == 1, "at most one build per cache key"
    leaders = [r for r in results if r[0] == "leader"]
    waiters = [r for r in results if r[0] == "waiter"]
    assert len(leaders) == 1
    assert len(waiters) == 19
    assert all(r[1] == {"built": True} for r in results)
    assert rc.inflight_count() == 0  # slot cleared


async def test_singleflight_waiter_not_orphaned_when_leader_dies():
    # A leader that never resolves must not hang a waiter forever — the waiter
    # bounds its own wait and falls through.
    is_leader, fut = rc.begin_build("key")
    assert is_leader

    # Waiter joins the same in-flight build.
    is_leader2, fut2 = rc.begin_build("key")
    assert not is_leader2 and fut2 is fut

    with pytest.raises(asyncio.TimeoutError):
        await rc.run_with_deadline(asyncio.shield(fut2), deadline_ms=100)


async def test_singleflight_new_leader_after_finish():
    is_leader, fut = rc.begin_build("key")
    rc.finish_build("key", fut, result={"x": 1})
    # Slot cleared → the next caller becomes a fresh leader.
    is_leader2, fut2 = rc.begin_build("key")
    assert is_leader2 and fut2 is not fut


# --- Queue 277 (#1475): exact singleflight ownership --------------------------
async def test_finish_build_resolves_and_removes_exact_future_once():
    is_leader, fut = rc.begin_build("key")
    assert is_leader
    rc.finish_build("key", fut, result={"x": 1})
    assert fut.done() and fut.result() == {"x": 1}
    assert rc.inflight_count() == 0
    # Idempotent: a second finish must not raise (e.g. a finally after the
    # normal return path already resolved it).
    rc.finish_build("key", fut, result={"y": 2})
    assert fut.result() == {"x": 1}


# --- Queue 280 (#1475): single-owner invariant — no takeover/force ------------
def test_takeover_and_force_escape_hatches_are_removed():
    """C74 ``unconditional_force_overwrites_live_owner`` can never occur: the
    displacing takeover and the unconditional force_build escape are gone, so no
    caller can install a second owner for a live key."""
    assert not hasattr(rc, "takeover_build")
    assert not hasattr(rc, "force_build")
    assert not hasattr(rc, "MAX_WAITER_TAKEOVER_ROUNDS")


async def test_late_stale_finish_never_removes_a_fresh_slot():
    """finish_build's identity guard survives without takeover: a late finish on
    an OLD (already-cleared) future must not remove a fresh leader's slot."""
    is_leader, first = rc.begin_build("key")
    assert is_leader
    rc.finish_build("key", first, result={"a": 1})  # clears the slot cleanly

    is_leader2, second = rc.begin_build("key")
    assert is_leader2 and second is not first

    # A stale, late finish on the old future touches only its own future.
    rc.finish_build("key", first, result={"stale": True})
    assert rc._inflight["key"] is second  # fresh slot intact
    assert not second.done()  # not resolved by the stale finish

    rc.finish_build("key", second, result={"b": 2})
    assert rc.inflight_count() == 0


# --- Queue 280 (#1475): leader/waiter lifecycle (feed ownership-guard shape) --
async def _leader_build(key, build):
    """Emulate the feed/golf leader path: claim → build under an ownership guard
    that resolves+removes the EXACT slot on every exit (success/exception/
    cancellation) → re-raise. No waiter loop: a live leader is the sole owner."""
    is_leader, fut = rc.begin_build(key)
    if not is_leader:
        return ("waiter", fut)
    try:
        result = await build()
        rc.finish_build(key, fut, result=result)
        return ("leader", result)
    except BaseException:
        rc.finish_build(key, fut, result=None)
        raise


async def _waiter(key, *, wait_deadline_ms, last_good=None):
    """Emulate the NEW feed/golf waiter path: a SINGLE bounded coalesce wait
    within the remaining budget, then fall back to last-good / unavailable. Never
    takes over the live owner and never starts a second build."""
    is_leader, fut = rc.begin_build(key)
    assert not is_leader, "test must set up a live leader before the waiter"
    coalesced = None
    if wait_deadline_ms > 0:
        try:
            coalesced = await rc.run_with_deadline(
                asyncio.shield(fut), deadline_ms=wait_deadline_ms
            )
        except Exception:
            coalesced = None
    if isinstance(coalesced, dict):
        return ("coalesced", coalesced)
    if isinstance(last_good, dict):
        return ("last_good", last_good)
    return ("unavailable", None)


async def test_cancelled_leader_does_not_poison_slot():
    """A leader whose request is cancelled mid-build must clean its slot so the
    NEXT request becomes a fresh leader instead of a waiter on a dead future."""
    started = asyncio.Event()

    async def _slow_build():
        started.set()
        await asyncio.sleep(30)
        return {"never": True}  # pragma: no cover

    task = asyncio.ensure_future(_leader_build("key", _slow_build))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):  # cancellation never swallowed
        await task

    # Slot cleaned: no unresolved future left installed. Self-heals for the next
    # request WITHOUT any takeover.
    assert rc.inflight_count() == 0
    is_leader, fut = rc.begin_build("key")
    assert is_leader  # fresh leader, NOT a waiter re-joining a poisoned future


async def test_leader_exception_does_not_poison_slot():
    async def _boom_build():
        raise RuntimeError("build blew up")

    with pytest.raises(RuntimeError):
        await _leader_build("key", _boom_build)

    assert rc.inflight_count() == 0
    is_leader, _ = rc.begin_build("key")
    assert is_leader  # slot self-heals on the next request


async def test_two_waiters_on_a_slow_live_owner_launch_zero_replacements():
    """C74 ``two_waiters_one_slow_owner``: while the owner runs, owner count
    stays exactly 1; two waiters coalesce onto its payload — neither rebuilds."""
    release = asyncio.Event()
    builds = {"n": 0}

    async def _build():
        builds["n"] += 1
        await release.wait()
        return {"ok": True}

    leader = asyncio.ensure_future(_leader_build("key", _build))
    await asyncio.sleep(0)  # let the leader claim the slot + start building
    assert rc.inflight_count() == 1

    w1 = asyncio.ensure_future(_waiter("key", wait_deadline_ms=5000))
    w2 = asyncio.ensure_future(_waiter("key", wait_deadline_ms=5000))
    await asyncio.sleep(0)
    # Still exactly one owner while both waiters coalesce — no replacement.
    assert rc.inflight_count() == 1

    release.set()
    lr, r1, r2 = await asyncio.gather(leader, w1, w2)
    assert builds["n"] == 1, "zero replacement builds despite two waiters"
    assert lr == ("leader", {"ok": True})
    assert r1 == ("coalesced", {"ok": True})
    assert r2 == ("coalesced", {"ok": True})
    assert rc.inflight_count() == 0


async def test_timed_out_waiter_falls_back_and_owner_remains():
    """C74 ``cancellation_ignoring_owner_remains_owner`` /
    ``total_budget_exhausted_no_compute``: a waiter whose budget runs out before
    the leader finishes serves a bounded fallback and leaves the owner in place —
    it never displaces the leader or starts a second build."""
    release = asyncio.Event()
    builds = {"n": 0}

    async def _build():
        builds["n"] += 1
        await release.wait()
        return {"ok": True}

    leader = asyncio.ensure_future(_leader_build("key", _build))
    await asyncio.sleep(0)
    assert rc.inflight_count() == 1

    # No last-good → truthful unavailable; owner untouched.
    role, _ = await _waiter("key", wait_deadline_ms=10)
    assert role == "unavailable"
    assert builds["n"] == 1  # no replacement build launched
    assert rc.inflight_count() == 1  # the original leader remains the sole owner

    # With last-good present, the waiter serves it instead (still no rebuild).
    role2, payload2 = await _waiter(
        "key", wait_deadline_ms=10, last_good={"stale": True}
    )
    assert role2 == "last_good" and payload2 == {"stale": True}
    assert builds["n"] == 1
    assert rc.inflight_count() == 1

    release.set()
    await leader
    assert rc.inflight_count() == 0


# --- schedule_background ------------------------------------------------------
async def test_schedule_background_runs_without_blocking_and_swallows_errors():
    ran = asyncio.Event()

    async def _work():
        ran.set()

    async def _boom():
        raise RuntimeError("boom")

    rc.schedule_background(_work())
    rc.schedule_background(_boom())  # must not raise into the caller
    await asyncio.wait_for(ran.wait(), timeout=1.0)
    # let the failing task finish its done-callback
    await asyncio.sleep(0.05)
