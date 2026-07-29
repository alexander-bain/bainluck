"""Unit tests for the bounded request-path cache primitives (Queue 271).

Covers the pieces GET /api/feed and GET /api/calibration rely on to survive a
Redis stall or a cold-compute miss-storm without holding a request to the Heroku
router cutoff (#1459/#1197). The end-to-end mapping onto the C55 failure contract
lives in tests/integration/test_cache_failure_seam.py.
"""

from __future__ import annotations

import asyncio

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


async def test_dead_leader_slot_is_recoverable_via_takeover():
    """A leader that dies/cancels without calling finish_build leaves a not-done
    future installed. The stale slot must be recoverable: a timed-out waiter
    atomically takes over and becomes the unique replacement owner."""
    is_leader, fut = rc.begin_build("key")
    assert is_leader
    # Simulate death: finish_build is NEVER called (cancellation/exception).
    # A plain begin_build would just re-join the dead future (documents the bug).
    rejoined_leader, rejoined = rc.begin_build("key")
    assert not rejoined_leader and rejoined is fut  # still poisoned pre-takeover

    # takeover_build repairs it: the caller owns a fresh future and may build.
    became_owner, fut2 = rc.takeover_build("key", fut)
    assert became_owner and fut2 is not fut
    assert rc._inflight["key"] is fut2
    rc.finish_build("key", fut2, result={"ok": True})
    assert rc.inflight_count() == 0


async def test_two_waiters_taking_over_together_yield_one_owner():
    """Two waiters whose coalesced wait timed out on the same stale future must
    not both start a build — exactly one becomes owner; the other becomes a
    waiter on the replacement."""
    is_leader, stale = rc.begin_build("key")
    assert is_leader

    a_owner, a_fut = rc.takeover_build("key", stale)
    b_owner, b_fut = rc.takeover_build("key", stale)

    assert a_owner and not b_owner
    assert a_fut is not stale
    assert b_fut is a_fut  # loser waits on the winner's fresh future
    assert rc._inflight["key"] is a_fut


async def test_late_original_finish_does_not_remove_replacement_slot():
    """A slow original leader that finally completes after a waiter has taken
    over must NOT resolve or remove the replacement owner's future."""
    is_leader, original = rc.begin_build("key")
    assert is_leader
    became_owner, replacement = rc.takeover_build("key", original)
    assert became_owner

    # The late original completes now — it must touch only its own future.
    rc.finish_build("key", original, result={"stale": True})
    assert rc._inflight["key"] is replacement  # replacement slot intact
    assert not replacement.done()  # replacement not resolved by the original

    rc.finish_build("key", replacement, result={"fresh": True})
    assert replacement.result() == {"fresh": True}
    assert rc.inflight_count() == 0


async def test_takeover_no_op_when_slot_already_cleared():
    """If the slot was already cleared (leader finished cleanly) a takeover still
    installs a fresh owner rather than crashing on a missing slot."""
    is_leader, fut = rc.begin_build("key")
    rc.finish_build("key", fut, result={"x": 1})  # slot cleared
    became_owner, fut2 = rc.takeover_build("key", fut)
    assert became_owner and fut2 is not fut
    assert rc._inflight["key"] is fut2


# --- Queue 277 (#1475): leader lifecycle races (feed ownership-guard shape) ---
async def _leader_request(key, build, *, force_rounds=rc.MAX_WAITER_TAKEOVER_ROUNDS):
    """Emulate the feed handler's exact singleflight leader lifecycle: claim →
    build under an ownership guard that resolves/removes the slot on EVERY exit
    (success, exception, cancellation) → re-raise. A waiter recovers via bounded
    coalesce/takeover/force-own, never re-joining a poisoned future."""
    is_leader, fut = rc.begin_build(key)
    rounds = 0
    while not is_leader:
        try:
            coalesced = await rc.run_with_deadline(
                asyncio.shield(fut), deadline_ms=50
            )
        except Exception:
            coalesced = None
        if isinstance(coalesced, dict):
            return ("waiter", coalesced)
        if rounds >= force_rounds:
            fut = rc.force_build(key)
            is_leader = True
            break
        rounds += 1
        is_leader, fut = rc.takeover_build(key, fut)
    # Leader ownership guard.
    try:
        result = await build()
        rc.finish_build(key, fut, result=result)
        return ("leader", result)
    except BaseException:
        if is_leader and fut is not None:
            rc.finish_build(key, fut, result=None)
        raise


async def test_cancelled_leader_does_not_poison_slot():
    """A leader whose request is cancelled mid-build must clean its slot so the
    NEXT request becomes a fresh leader instead of a waiter on a dead future."""
    started = asyncio.Event()

    async def _slow_build():
        started.set()
        await asyncio.sleep(30)
        return {"never": True}  # pragma: no cover

    task = asyncio.ensure_future(_leader_request("key", _slow_build))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):  # cancellation never swallowed
        await task

    # Slot cleaned: no unresolved future left installed.
    assert rc.inflight_count() == 0
    is_leader, fut = rc.begin_build("key")
    assert is_leader  # fresh leader, NOT a waiter re-joining a poisoned future


async def test_leader_exception_does_not_poison_slot():
    async def _boom_build():
        raise RuntimeError("build blew up")

    with pytest.raises(RuntimeError):
        await _leader_request("key", _boom_build)

    assert rc.inflight_count() == 0
    is_leader, _ = rc.begin_build("key")
    assert is_leader


async def test_waiters_recover_after_leader_dies_exactly_one_rebuilds():
    """Leader dies; two concurrent waiters must not both rebuild — takeover makes
    exactly one the replacement owner, the other coalesces onto it.

    The recovery rebuild yields once (fast, well under a coalesce deadline) so
    the loser's coalesce resolves on the winner's fresh future — mirroring
    production where COMPUTE_DEADLINE_MS (22s) far exceeds any real build, so a
    waiter never prematurely takes over an actively-building replacement."""
    builds = {"n": 0}

    # A dead leader: claim the slot and never resolve it.
    is_leader, dead = rc.begin_build("key")
    assert is_leader

    async def _rebuild():
        builds["n"] += 1
        await asyncio.sleep(0)  # yield once so the co-waiter can coalesce
        return {"rebuilt": True}

    async def _recover():
        # No last-good, so both waiters time out on the dead future, then race
        # takeover; the winner rebuilds and the loser coalesces onto it.
        return await _leader_request("key", _rebuild, force_rounds=5)

    r1, r2 = await asyncio.gather(
        asyncio.ensure_future(_recover()),
        asyncio.ensure_future(_recover()),
    )

    assert builds["n"] == 1, "exactly one rebuild despite two recovering waiters"
    roles = sorted([r1[0], r2[0]])
    assert roles == ["leader", "waiter"]
    assert r1[1] == {"rebuilt": True} and r2[1] == {"rebuilt": True}
    assert rc.inflight_count() == 0
    # Silence the abandoned dead future (never awaited).
    dead.cancel()


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
