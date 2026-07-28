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
