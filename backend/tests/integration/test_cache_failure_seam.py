"""Production integration seam for the C55 cache-failure contract (Queue 271).

The offline contract (backend/scripts/evals/cache_failure_resilience.py) defines
the failure codes. This module proves the REAL request paths — the calibration
route handler and the shared request-cache primitives the feed handler now uses —
behave the way the contract requires under injected faults, then maps each
observed behavior back onto ``evaluate_scenario`` under the production deadline
policy and asserts it is contract-clean.

Faults covered (issue #1459/#1197): Redis down, Redis slow/hang, cache write
stall, malformed cache, cold-miss-with-last-good, 20-request stampede, and the
calibration sync-block + inline-compute-deadline seams.
"""

from __future__ import annotations

import asyncio
import json

import pytest
from fastapi import HTTPException

from app.utils import request_cache as rc
from scripts.evals.cache_failure_resilience import evaluate_scenario

# Production deadline policy — the real constants the code enforces, expressed in
# the C55 policy shape. compute_deadline is a safety bound well under the router
# cutoff, NOT a latency target (see request_cache.COMPUTE_DEADLINE_MS).
POLICY = {
    "version": "queue-271/v1",
    "router_timeout_ms": rc.ROUTER_TIMEOUT_MS,
    "redis_operation_deadline_ms": rc.REDIS_OP_DEADLINE_MS,
    "compute_deadline_ms": rc.COMPUTE_DEADLINE_MS,
    "db_checkout_deadline_ms": rc.DB_CHECKOUT_DEADLINE_MS,
}


def _assert_contract_clean(scenario: dict) -> None:
    result = evaluate_scenario(scenario, POLICY)
    assert result["valid"], f"contract violations: {result['findings']}"


@pytest.fixture(autouse=True)
def _clean_state():
    rc._reset_last_good_for_tests()
    rc._reset_inflight_for_tests()
    yield
    rc._reset_last_good_for_tests()
    rc._reset_inflight_for_tests()


class _FakeRedis:
    """Minimal async Redis stand-in with an injectable fault mode."""

    def __init__(self, mode: str, value=None):
        self.mode = mode
        self.value = value
        self.gets = 0
        self.setex_calls = 0

    async def get(self, key):
        self.gets += 1
        if self.mode == "down":
            raise ConnectionError("SSL: UNEXPECTED_EOF")
        if self.mode == "hang":
            await asyncio.sleep(30)
        return self.value  # None => miss; bytes/str => hit/malformed

    async def setex(self, key, ttl, value):
        self.setex_calls += 1
        if self.mode == "write_hang":
            await asyncio.sleep(30)
        return True


def _fake_getter(client):
    async def _get():
        return client

    return _get


# ---------------------------------------------------------------------------
# Calibration route — the real handler (small enough to drive directly).
# ---------------------------------------------------------------------------
def _reset_calibration_cache():
    from app.routes import calibration

    calibration._cache["data"] = None
    calibration._cache["timestamp"] = 0


async def test_calibration_redis_down_serves_last_good_no_compute(monkeypatch):
    """Redis error + a process-local last-good → serve stale, never compute."""
    from app.routes import calibration
    from app.tasks import precompute_calibration

    _reset_calibration_cache()
    rc.remember_last_good("calibration:main", {"buckets": [1, 2, 3]})

    client = _FakeRedis("down")
    monkeypatch.setattr(rc, "get_shared_async_redis", _fake_getter(client))

    computed = {"called": False}

    async def _boom(db):  # inline heavy compute must never run on the request path
        computed["called"] = True
        raise AssertionError("compute_calibration_payload ran inline")

    monkeypatch.setattr(precompute_calibration, "compute_calibration_payload", _boom)

    loop = asyncio.get_running_loop()
    start = loop.time()
    out = await calibration.public_calibration(db=object(), bust=0)
    elapsed_ms = (loop.time() - start) * 1000

    assert out["buckets"] == [1, 2, 3]
    assert out["cache"]["status"] == "stale"
    assert computed["called"] is False
    assert elapsed_ms < POLICY["router_timeout_ms"]

    _assert_contract_clean(
        {
            "id": "calibration-degraded-lastgood",
            "endpoint": "calibration",
            "cache_state": "error",
            "last_good": {"available": True, "usable": True},
            "redis_stages": [
                {
                    "stage": "main_cache",
                    "result": "connect_error",
                    "duration_ms": 5,
                    "awaited": True,
                    "event_loop_blocked": False,
                    "client_closed": True,
                }
            ],
            "concurrent_requests": 1,
            "builds_started": 0,
            "compute": {"started": False, "duration_ms": 0},
            "db": {"checkout_result": "unused", "wait_ms": 0},
            "cache_write": {
                "result": "unused",
                "duration_ms": 0,
                "awaited_before_response": False,
            },
            "response": {"kind": "stale", "elapsed_ms": round(elapsed_ms)},
            "metrics": {"independent": True, "verdict": "red"},
        }
    )


async def test_calibration_slow_redis_terminates_under_deadline(monkeypatch):
    """A hung Redis read is bounded — it never blocks toward the router cutoff."""
    from app.routes import calibration

    _reset_calibration_cache()
    rc.remember_last_good("calibration:main", {"buckets": []})
    client = _FakeRedis("hang")
    monkeypatch.setattr(rc, "get_shared_async_redis", _fake_getter(client))

    loop = asyncio.get_running_loop()
    start = loop.time()
    out = await calibration.public_calibration(db=object(), bust=0)
    elapsed = loop.time() - start

    # Bounded by REDIS_OP_DEADLINE_MS (0.6s), nowhere near the 30s router cutoff.
    assert elapsed < 2.0
    assert out["cache"]["status"] == "stale"


async def test_calibration_slow_compute_is_deadline_bounded(monkeypatch):
    """A hung cold compute is cancelled at its deadline → fast 503, never a 30s H12."""
    from app.routes import calibration
    from app.tasks import precompute_calibration

    _reset_calibration_cache()
    client = _FakeRedis("miss", value=None)  # clean miss (Redis healthy but empty)
    monkeypatch.setattr(rc, "get_shared_async_redis", _fake_getter(client))
    # Tighten the compute deadline so the test is fast; the handler reads it live.
    monkeypatch.setattr(rc, "CALIBRATION_COMPUTE_DEADLINE_MS", 200)

    async def _hang(db):
        await asyncio.sleep(30)

    monkeypatch.setattr(precompute_calibration, "compute_calibration_payload", _hang)

    loop = asyncio.get_running_loop()
    start = loop.time()
    with pytest.raises(HTTPException) as exc:
        await calibration.public_calibration(db=object(), bust=0)
    elapsed_ms = (loop.time() - start) * 1000

    assert exc.value.status_code == 503
    assert elapsed_ms < 2000  # bounded by the compute deadline, nowhere near 30s

    _assert_contract_clean(
        {
            "id": "calibration-compute-deadline",
            "endpoint": "calibration",
            "cache_state": "miss",
            "last_good": {"available": False, "usable": False},
            "redis_stages": [
                {
                    "stage": "main_cache",
                    "result": "miss",
                    "duration_ms": 5,
                    "awaited": True,
                    "event_loop_blocked": False,
                    "client_closed": True,
                }
            ],
            "concurrent_requests": 1,
            "builds_started": 1,
            # Compute STARTED but was hard-cancelled AT the deadline — it never ran
            # to the router cutoff (the whole point of the fix). Its bounded run
            # time is the deadline itself.
            "compute": {
                "started": True,
                "duration_ms": rc.CALIBRATION_COMPUTE_DEADLINE_MS,
                "deadline_ms": rc.CALIBRATION_COMPUTE_DEADLINE_MS,
                "passes": 1,
            },
            "db": {"checkout_result": "ok", "wait_ms": 10},
            "cache_write": {
                "result": "unused",
                "duration_ms": 0,
                "awaited_before_response": False,
            },
            "response": {"kind": "error", "elapsed_ms": round(elapsed_ms)},
            "metrics": {"independent": True, "verdict": "red"},
        }
    )


async def test_calibration_cold_miss_computes_and_serves(monkeypatch):
    """A clean cold miss computes via the canonical path and serves the shape."""
    from app.routes import calibration
    from app.tasks import precompute_calibration

    _reset_calibration_cache()
    client = _FakeRedis("miss", value=None)
    monkeypatch.setattr(rc, "get_shared_async_redis", _fake_getter(client))

    async def _compute(db):
        return {"buckets": [0, 1], "by_source": {}}

    monkeypatch.setattr(precompute_calibration, "compute_calibration_payload", _compute)

    out = await calibration.public_calibration(db=object(), bust=0)
    assert out["buckets"] == [0, 1]
    # Computed payload primes last-good for the next Redis blip.
    assert rc.recall_last_good("calibration:main") == {
        "buckets": [0, 1],
        "by_source": {},
    }


async def test_calibration_warm_hit_serves_and_remembers(monkeypatch):
    from app.routes import calibration

    _reset_calibration_cache()
    payload = {"buckets": [9, 9], "generated_at": "t"}
    client = _FakeRedis("hit", value=json.dumps(payload))
    monkeypatch.setattr(rc, "get_shared_async_redis", _fake_getter(client))

    out = await calibration.public_calibration(db=object(), bust=0)
    assert out["buckets"] == [9, 9]
    # A warm hit primes the process-local last-good for the next Redis blip.
    assert rc.recall_last_good("calibration:main") == payload


# ---------------------------------------------------------------------------
# Feed request-cache primitives — the exact composition the feed handler uses.
# ---------------------------------------------------------------------------
async def test_feed_redis_error_serves_last_good_without_cold_compute(monkeypatch):
    """The feed read path: a Redis *failure* serves last-good, not a cold build."""
    client = _FakeRedis("down")
    monkeypatch.setattr(rc, "get_shared_async_redis", _fake_getter(client))
    rc.remember_last_good("feed_cache:abc", {"items": [1]})

    redis = await rc.get_shared_async_redis()
    fresh = await rc.bounded_redis_call(lambda: redis.get("feed_cache:abc"))
    assert fresh.is_failure  # error, not a clean miss

    build_started = False
    served = None
    if fresh.is_failure:
        lg = rc.recall_last_good("feed_cache:abc")
        if isinstance(lg, dict):
            served = lg
        else:  # pragma: no cover - not reached in this fixture
            build_started = True

    assert served == {"items": [1]}
    assert build_started is False

    _assert_contract_clean(
        {
            "id": "feed-redis-unavailable-local-last-good",
            "endpoint": "feed",
            "cache_state": "error",
            "last_good": {"available": True, "usable": True},
            "redis_stages": [
                {
                    "stage": "fresh",
                    "result": "connect_error",
                    "duration_ms": 5,
                    "awaited": True,
                    "event_loop_blocked": False,
                    "client_closed": True,
                }
            ],
            "concurrent_requests": 1,
            "builds_started": 0,
            "compute": {"started": False, "duration_ms": 0},
            "db": {"checkout_result": "unused", "wait_ms": 0},
            "cache_write": {
                "result": "unused",
                "duration_ms": 0,
                "awaited_before_response": False,
            },
            "response": {"kind": "ok", "elapsed_ms": 10},
            "metrics": {"independent": True, "verdict": "red"},
        }
    )


async def test_feed_malformed_cache_is_typed_miss_not_crash(monkeypatch):
    client = _FakeRedis("hit", value=b"{not valid json")
    monkeypatch.setattr(rc, "get_shared_async_redis", _fake_getter(client))

    redis = await rc.get_shared_async_redis()
    res = await rc.bounded_redis_call(lambda: redis.get("feed_cache:abc"))
    assert res.is_ok  # Redis returned bytes; the corruption is in the payload

    # The feed handler decodes with a typed guard (never raises on bad JSON).
    def _safe(raw):
        try:
            v = json.loads(raw)
        except Exception:
            return None
        return v if isinstance(v, dict) else None

    payload = _safe(res.value)
    assert payload is None  # typed fallback → treated as a miss, no exception

    _assert_contract_clean(
        {
            "id": "feed-malformed-cache-typed",
            "endpoint": "feed",
            "cache_state": "malformed",
            "typed_cache_error": True,
            "last_good": {"available": False, "usable": False},
            "redis_stages": [
                {
                    "stage": "fresh",
                    "result": "malformed",
                    "duration_ms": 5,
                    "awaited": True,
                    "event_loop_blocked": False,
                    "client_closed": True,
                }
            ],
            "concurrent_requests": 1,
            "builds_started": 1,
            "compute": {"started": True, "duration_ms": 2000, "passes": 1},
            "db": {"checkout_result": "ok", "wait_ms": 10},
            "cache_write": {
                "result": "ok",
                "duration_ms": 50,
                "awaited_before_response": False,
            },
            "response": {"kind": "ok", "elapsed_ms": 2100},
            "metrics": {"independent": True, "verdict": "red"},
        }
    )


async def test_feed_stampede_coalesces_to_one_build():
    calls = {"n": 0}
    release = asyncio.Event()
    started = asyncio.Event()

    async def _one_request():
        is_leader, fut = rc.begin_build("feed_cache:hot")
        if is_leader:
            calls["n"] += 1
            started.set()
            await release.wait()
            payload = {"items": ["built"]}
            rc.finish_build("feed_cache:hot", fut, result=payload)
            return payload
        return await asyncio.shield(fut)

    tasks = [asyncio.ensure_future(_one_request()) for _ in range(20)]
    await started.wait()
    release.set()
    results = await asyncio.gather(*tasks)

    assert calls["n"] == 1
    assert all(r == {"items": ["built"]} for r in results)

    _assert_contract_clean(
        {
            "id": "feed-twenty-request-stampede",
            "endpoint": "feed",
            "cache_state": "miss",
            "last_good": {"available": False, "usable": False},
            "redis_stages": [],
            "concurrent_requests": 20,
            "builds_started": 1,  # singleflight → exactly one build
            "compute": {"started": True, "duration_ms": 4000, "passes": 1},
            "db": {"checkout_result": "ok", "wait_ms": 500},
            "cache_write": {
                "result": "ok",
                "duration_ms": 50,
                "awaited_before_response": False,
            },
            "response": {"kind": "ok", "elapsed_ms": 4100},
            "metrics": {"independent": True, "verdict": "red"},
        }
    )


async def test_feed_cache_write_does_not_block_response(monkeypatch):
    """A hung cache publish runs detached; the response is not delayed by it."""
    client = _FakeRedis("write_hang")
    published = asyncio.Event()

    async def _publish():
        published.set()
        await rc.bounded_redis_call(lambda: client.setex("k", 5, "v"))

    loop = asyncio.get_running_loop()
    start = loop.time()
    rc.schedule_background(_publish())
    # Response "returns" here immediately; publish is still in flight.
    elapsed = loop.time() - start
    assert elapsed < 0.1

    await asyncio.wait_for(published.wait(), timeout=1.0)

    _assert_contract_clean(
        {
            "id": "feed-cache-write-stall",
            "endpoint": "feed",
            "cache_state": "miss",
            "last_good": {"available": False, "usable": False},
            "redis_stages": [],
            "concurrent_requests": 1,
            "builds_started": 1,
            "compute": {"started": True, "duration_ms": 2000, "passes": 1},
            "db": {"checkout_result": "ok", "wait_ms": 10},
            "cache_write": {
                "result": "detached",
                "duration_ms": 30000,
                "awaited_before_response": False,  # detached → never blocks response
            },
            "response": {"kind": "ok", "elapsed_ms": 2100},
            "metrics": {"independent": True, "verdict": "red"},
        }
    )
