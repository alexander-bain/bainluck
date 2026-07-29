"""Bounded, availability-safe request-path cache primitives (Queue 271).

Consumed by ``GET /api/feed`` and ``GET /api/calibration`` so a Redis stall or a
cold-compute miss-storm can never hold a request to the Heroku router's 30s H12
cutoff (#1459), and so the per-request Redis client construct/close churn that
amplifies the Heroku Redis TLS flakiness (#1197) is replaced by one shared,
process-owned client.

The failure contract these primitives satisfy is the executable C55 pack in
``backend/scripts/evals/cache_failure_resilience.py`` +
``cache_failure_resilience_fixtures.json``. Every deadline here is deliberately
below the external router cutoff, and every operation fails *distinguishably*
(miss vs. timeout vs. error) so a degraded response can be truthful.

Design notes:

* **Shared client, one per process.** ``get_shared_async_redis`` returns a single
  lazily-created (and lifespan-closed) async client. Request handlers must not
  build/close a pool per request (that churn is the #1197 amplifier).
* **Bounded ops.** ``bounded_redis_call`` wraps one awaitable in a hard
  ``asyncio.wait_for`` deadline (default 600ms) and never raises past a typed
  ``RedisResult`` — connect/read/write stalls terminate well under the router
  cutoff instead of blocking the response or the event loop.
* **Process-local last-good.** ``remember_last_good`` / ``recall_last_good`` keep
  the last successfully served payload per cache key in-process, so a Redis
  outage serves truthful stale data instead of forcing a cold recompute.
* **Per-key singleflight.** ``begin_build`` / ``finish_build`` coalesce identical
  concurrent cold requests onto ONE build per cache key per process; waiters
  receive the leader's completed payload (or fall back) rather than each paying
  the full compute — this is what stops the concurrent-cold-build stampede that
  tips ``/api/feed`` over the 30s router limit.
* **Non-blocking publish.** ``schedule_background`` runs a bounded cache write as
  a detached task so publication never delays a ready response.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional

logger = logging.getLogger(__name__)


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


# --- Deadline policy (mirrors the C55 heroku-router-contract/v1 policy) --------
# These are AVAILABILITY safety bounds, not latency targets. COMPUTE_DEADLINE_MS
# sits well under the 30s Heroku router H12 cutoff so a pathological cold build or
# waiter coalesce fails fast / serves fallback instead of a router-level 503.
REDIS_OP_DEADLINE_MS = _env_int("REQUEST_REDIS_OP_DEADLINE_MS", 600)
ROUTER_TIMEOUT_MS = _env_int("REQUEST_ROUTER_TIMEOUT_MS", 30000)
COMPUTE_DEADLINE_MS = _env_int("REQUEST_COMPUTE_DEADLINE_MS", 22000)
DB_CHECKOUT_DEADLINE_MS = _env_int("REQUEST_DB_CHECKOUT_DEADLINE_MS", 1000)
# Total /api/feed request budget — the futures-scoring pass (the slow, DB-bound
# stage that hangs a cold build) is bounded to the time remaining under this so a
# pathological build degrades to the valid events-only feed instead of a 30s
# Heroku router H12 (#1459). Kept comfortably under the 30s cutoff.
FEED_TOTAL_BUDGET_MS = _env_int("FEED_TOTAL_BUDGET_MS", 25000)
# Calibration cold-miss compute is deadline-guarded so it can never run to the
# router cutoff (the 12-27s inline CTE that caused the #1459 calibration H12).
# The precompute beat keeps Redis warm, so a request-path compute is rare and,
# when it happens, either finishes fast or fails fast + explicit.
CALIBRATION_COMPUTE_DEADLINE_MS = _env_int("CALIBRATION_COMPUTE_DEADLINE_MS", 9000)

# Typed outcome of a bounded Redis op — miss/timeout/error are distinguishable so
# a caller can serve last-good on a *failure* but cold-compute on a genuine miss.
OK = "ok"
MISS = "miss"
TIMEOUT = "timeout"
ERROR = "error"


@dataclass(frozen=True)
class RedisResult:
    """Result of one bounded Redis operation. Never carries an exception."""

    status: str
    value: Any = None

    @property
    def is_ok(self) -> bool:
        return self.status == OK

    @property
    def is_miss(self) -> bool:
        return self.status == MISS

    @property
    def is_failure(self) -> bool:
        """A stall or connection error (NOT a clean miss)."""
        return self.status in (TIMEOUT, ERROR)


# --- Shared async client (one connection pool per process) --------------------
_shared_client: Any = None
_client_lock = asyncio.Lock()


async def get_shared_async_redis() -> Any:
    """Return the process-shared async Redis client, creating it once.

    One pool per process, reused across requests — never construct/close a pool
    per request (#1197). Callers must NOT ``aclose()`` the returned client.
    """
    global _shared_client
    if _shared_client is None:
        async with _client_lock:
            if _shared_client is None:
                from app.tasks.redis_state import get_async_redis_client

                _shared_client = get_async_redis_client()
    return _shared_client


async def close_shared_async_redis() -> None:
    """Close and drop the shared client (lifespan shutdown)."""
    global _shared_client
    client = _shared_client
    _shared_client = None
    if client is not None:
        try:
            await client.aclose()
        except Exception:  # pragma: no cover - shutdown best-effort
            logger.debug("shared async redis close failed", exc_info=True)


def _reset_shared_client_for_tests() -> None:
    """Drop the cached shared client so a test's patched factory is re-read.

    Sync + reference-drop only (no await) — the cached client in tests is either a
    fake or an unconnected pool, so there is nothing to close.
    """
    global _shared_client
    _shared_client = None


# --- Bounded operation wrapper ------------------------------------------------
async def bounded_redis_call(
    factory: Callable[[], Awaitable[Any]],
    *,
    deadline_ms: int = REDIS_OP_DEADLINE_MS,
    treat_none_as_miss: bool = True,
) -> RedisResult:
    """Run ONE Redis awaitable under a hard deadline; never raise.

    ``factory`` must return a fresh awaitable each call (e.g.
    ``lambda: client.get(key)``). A timeout or any exception is captured as a
    typed ``RedisResult`` so the request path stays fast and the failure stays
    distinguishable from a clean miss. ``CancelledError`` (client disconnect /
    outer deadline) is re-raised so it is never swallowed.
    """
    try:
        value = await asyncio.wait_for(factory(), timeout=deadline_ms / 1000.0)
    except asyncio.TimeoutError:
        return RedisResult(TIMEOUT)
    except asyncio.CancelledError:
        raise
    except Exception:
        return RedisResult(ERROR)
    if value is None and treat_none_as_miss:
        return RedisResult(MISS)
    return RedisResult(OK, value)


async def run_with_deadline(awaitable: Awaitable[Any], *, deadline_ms: int) -> Any:
    """Await ``awaitable`` under a hard deadline (raises ``TimeoutError``)."""
    return await asyncio.wait_for(awaitable, timeout=deadline_ms / 1000.0)


# --- Process-local last-good store --------------------------------------------
_last_good: dict[str, tuple[float, Any]] = {}
_LAST_GOOD_MAX = _env_int("REQUEST_LAST_GOOD_MAX", 512)


def remember_last_good(key: Optional[str], payload: Any) -> None:
    """Record the last successfully served payload for ``key`` (in-process)."""
    if not key or payload is None:
        return
    if key not in _last_good and len(_last_good) >= _LAST_GOOD_MAX:
        # Evict the oldest entry to bound memory (rare; keys are stable-ish).
        oldest = min(_last_good.items(), key=lambda kv: kv[1][0])[0]
        _last_good.pop(oldest, None)
    _last_good[key] = (time.time(), payload)


def recall_last_good(key: Optional[str], *, max_age_s: Optional[float] = None) -> Any:
    """Return the last-good payload for ``key`` (optionally age-bounded)."""
    if not key:
        return None
    hit = _last_good.get(key)
    if not hit:
        return None
    ts, payload = hit
    if max_age_s is not None and (time.time() - ts) > max_age_s:
        return None
    return payload


def _reset_last_good_for_tests() -> None:
    _last_good.clear()


# --- Per-key singleflight -----------------------------------------------------
# One in-flight build per cache key per process. Waiters await the leader's
# future (bounded by the caller) rather than launching a duplicate build. The
# future is keyed by the SAME cache key the payload is stored under — which
# already encodes user/session identity — so a coalesced payload can never cross
# a user boundary.
#
# Single-owner invariant (Queue 280 / #1475): a *live* future is the sole owner
# of its key. A waiter whose bounded wait times out NEVER displaces that owner
# and NEVER starts a second build — it falls back (bounded last-good / truthful
# unavailable) so a slow leader can never be turned into a duplicate-work
# stampede. Recovery is self-healing without a takeover: ``finish_build``
# resolves and removes the exact future on EVERY leader exit (success /
# exception / cancellation), and process death clears all process-local state,
# so the very next ``begin_build`` for a done/absent slot becomes a fresh leader.
_inflight: dict[str, "asyncio.Future[Any]"] = {}


def begin_build(key: str) -> tuple[bool, "asyncio.Future[Any]"]:
    """Claim or join the build for ``key``.

    Returns ``(is_leader, future)``. The leader MUST later resolve its slot
    exactly once via ``finish_build(key, future, ...)`` on EVERY exit — success,
    exception, AND cancellation — so a dead leader never leaves an unresolved
    future installed. Waiters await ``future`` (the caller bounds the wait). A
    waiter whose wait times out does NOT take over or force a second build: a
    live future remains the sole owner, and the slot self-heals for the next
    caller once the leader resolves/clears it (or the process dies).
    """
    fut = _inflight.get(key)
    if fut is not None and not fut.done():
        return False, fut
    loop = asyncio.get_running_loop()
    fut = loop.create_future()
    _inflight[key] = fut
    return True, fut


def finish_build(
    key: str,
    future: "asyncio.Future[Any]",
    *,
    result: Any = None,
    exc: Optional[BaseException] = None,
) -> None:
    """Resolve ``future`` once and clear the slot iff it still holds ``future``.

    Safe to call on every leader exit path (success/exception/cancellation) and
    idempotent: a second call after the future is already resolved is a no-op.
    The slot is popped ONLY when ``_inflight[key]`` is still the exact
    ``future`` passed in — so a stale/late leader can never remove a *fresh*
    leader's slot after the key self-healed (identity guard).
    """
    if future is not None and not future.done():
        if exc is not None:
            future.set_exception(exc)
        else:
            future.set_result(result)
    if _inflight.get(key) is future:
        _inflight.pop(key, None)


def inflight_count() -> int:
    return sum(1 for f in _inflight.values() if not f.done())


def _reset_inflight_for_tests() -> None:
    _inflight.clear()


# --- Non-blocking background work --------------------------------------------
_background_tasks: set[asyncio.Task] = set()


def schedule_background(coro: Awaitable[Any]) -> None:
    """Run ``coro`` detached so it never delays the calling response.

    A strong reference is held until completion so the task is not GC'd
    mid-flight; failures are logged, never propagated.
    """
    try:
        task = asyncio.ensure_future(coro)
    except RuntimeError:  # pragma: no cover - no running loop
        return

    def _done(t: asyncio.Task) -> None:
        _background_tasks.discard(t)
        if not t.cancelled():
            exc = t.exception()
            if exc is not None:
                logger.debug("background cache task failed", exc_info=exc)

    _background_tasks.add(task)
    task.add_done_callback(_done)
