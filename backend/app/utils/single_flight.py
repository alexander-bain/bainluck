"""One copy at a time: a Redis in-flight lease for beat tasks that lap (#3251).

A Celery beat entry publishes on a fixed period whether or not the previous
delivery has finished. When a task's duration exceeds its own interval it
**laps**: every tick adds a copy the worker will eventually have to run, and the
queue grows without bound. Measured on production 2026-09-05, `realtime` was
282 → 349 deep with **85 copies of `poll_all_odds`** queued (30 s beat, p95
118.2 s → 3.94× its own interval), against `worker-realtime --concurrency=4`.

The casualty was not odds polling — it was everything else sharing the queue.
`prewarm_live_feed_shapes`, the 40 s rail that is the only thing that can hold a
live-containing feed shape warm, carries `expires=40`, so once the queue's
service latency passed 40 s **every one of its messages was discarded on
arrival** — no start, no failure, `health: healthy`, and a front page costing
13.3 s cold instead of 0.2 s. (See `docs/gotchas-reference.md` and #3251: never
"fix" that by raising `expires`; the bound is correct. Fix the producers.)

So: before a lapping task does its work it takes a lease. If a previous copy
still holds it, this delivery logs one line and returns a `skipped` summary in
microseconds. The queue cannot form a line, so the 40 s rail keeps its slot.

Four properties this has to have, and how each is obtained:

* **A skip is not a failure.** The tick returns a summary; nothing raises,
  nothing retries, no price is cleared or aged out. A skipped tick performs no
  writes at all.
* **A crashed holder must not hold forever.** The lease carries a TTL, so a
  child SIGKILLed past its `finally` (gotcha: a hard kill reaches no handler)
  releases by expiry.
* **A slow holder must not release somebody else's lease.** The lease is a
  unique token and release is a compare-and-delete, exactly as
  `app/utils/event_concept_cache.py` does it: an unconditional `delete` in a
  `finally` is how #1678 admitted a third concurrent builder. A holder whose
  lease already expired deletes nothing.
* **Redis being down must not stop ingestion.** Acquisition FAILS OPEN — if the
  lease cannot be taken *or refused*, the work runs. Losing the guard degrades
  us to today's behaviour; letting the guard become a second outage would be
  worse than the one it repairs.

Trade-off, stated rather than hidden: the TTL is sized off the runtime's
*guaranteed* bound (`task_time_limit`), not off a measured p95, because a
measured number rots and an enforced one cannot. The cost is that a hard-killed
holder can stall its own task for up to the TTL; the benefit is that two copies
can never both call The Odds API and bill the 5M/month quota twice for the same
tick. Duplicate spend on the most constrained resource in the system is the
worse failure, so the bound that cannot be undershot is the one we use.
"""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from dataclasses import dataclass
from uuid import uuid4

logger = logging.getLogger(__name__)

#: Every lease key lives under this prefix, so `/api/admin/redis-read` can read
#: one by name and the whole set is greppable in Redis.
LEASE_KEY_PREFIX = "bainluck:inflight:"

#: Skip counters, one per task, under the same prefix. Diagnostic only — this is
#: how production proves the guard actually fired without needing dyno logs.
SKIP_COUNTER_PREFIX = "bainluck:inflight:skipped:"

#: 24 h window on the skip counters. They are evidence, not state; nothing reads
#: them to make a decision.
SKIP_COUNTER_TTL_SECONDS = 86400

#: Celery's global hard kill bound (`task_time_limit` in `app/tasks/__init__.py`).
#: A task that reaches it is SIGKILLed, so no un-overridden task can still be
#: running past this point. Mirrored here rather than imported because
#: `app.tasks` imports this module's consumers; `tests/test_single_flight_lease.py`
#: asserts the two are equal, so they cannot drift.
CELERY_HARD_TASK_TIME_LIMIT_SECONDS = 300

#: Headroom over the kill bound: the SIGKILL lands *at* the limit, and the lease
#: must still be held when it does.
LEASE_TTL_MARGIN_SECONDS = 30

#: 300 + 30. Both terms are declared above; neither is a literal chosen to make
#: the arithmetic come out.
DEFAULT_LEASE_TTL_SECONDS = (
    CELERY_HARD_TASK_TIME_LIMIT_SECONDS + LEASE_TTL_MARGIN_SECONDS
)

#: Compare-and-delete. Releasing without proving ownership is the #1678 defect.
_RELEASE_IF_OWNER_LUA = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
end
return 0
"""


@dataclass(frozen=True)
class Lease:
    """The outcome of one attempt to take a task's in-flight lease.

    ``acquired`` is the only thing a caller must branch on. ``reason`` says WHY,
    and the three values are meaningfully different to an operator:

    * ``"acquired"``    — we hold it; nobody else is running.
    * ``"already_running"`` — refused; a previous copy is still in flight.
    * ``"redis_unavailable"`` — we could not ask. ``acquired`` is True (fail
      open) and ``token`` is None, so release is a no-op.
    """

    task: str
    key: str
    token: str | None
    acquired: bool
    reason: str

    def skipped_result(self) -> dict:
        """The summary a declining tick returns. Never a failure shape.

        Deliberately carries ``skipped: True`` and no ``terminal``/``status``
        key, so `app.utils.task_verdict` classifies it as a non-authoritative
        UNKNOWN if it ever reaches the verdict contract — a declined tick is not
        an incomplete run and must never move a health counter.
        """
        return {
            "skipped": True,
            "reason": self.reason,
            "task": self.task,
            "lease_key": self.key,
        }


def lease_key(task: str) -> str:
    return f"{LEASE_KEY_PREFIX}{task}"


def skip_counter_key(task: str) -> str:
    return f"{SKIP_COUNTER_PREFIX}{task}"


def _client():
    """The bounded shared client, or None.

    Gotcha #39: a sync Redis client with no socket timeout can freeze an async
    task, so this must route through `get_redis_client()` and never hand-roll
    one. Imported lazily — `app.tasks.redis_state` pulls in Celery config, and
    this module is imported from task bodies.
    """
    try:
        from app.tasks.redis_state import get_redis_client

        return get_redis_client()
    except Exception:  # noqa: BLE001 — a lease must never be why a task cannot start
        return None


def acquire(
    task: str, ttl_seconds: int = DEFAULT_LEASE_TTL_SECONDS, rc=None
) -> Lease:
    """Take ``task``'s in-flight lease, or report that somebody else holds it.

    Fails OPEN: any Redis problem yields ``acquired=True, token=None``.

    ``rc`` lets the caller supply the client so one lease costs one client, not
    two: `get_redis_client()` builds a fresh client and pool per call, and these
    tasks fire every 30–120 s.
    """
    key = lease_key(task)
    rc = rc if rc is not None else _client()
    if rc is None:
        return Lease(task, key, None, True, "redis_unavailable")

    token = f"{uuid4().hex}:{int(time.time())}"
    try:
        if rc.set(key, token, nx=True, ex=ttl_seconds):
            return Lease(task, key, token, True, "acquired")
    except Exception as exc:  # noqa: BLE001 — see docstring: fail open
        logger.warning("single_flight: could not acquire %s (%s); running anyway", key, exc)
        return Lease(task, key, None, True, "redis_unavailable")

    # redis-py answers None for a refused NX. That is a refusal, not an error.
    _record_skip(rc, task)
    return Lease(task, key, None, False, "already_running")


def release(lease: Lease, rc=None) -> bool:
    """Release ``lease`` iff it still owns the key. True when it removed it.

    Fails CLOSED. If the compare-and-delete cannot run, the lease is LEFT to
    expire on its TTL: the cost is one delayed tick, whereas deleting on a
    failed check hands the key to a second concurrent copy.
    """
    if not lease.acquired or not lease.token:
        return False
    rc = rc if rc is not None else _client()
    if rc is None:
        return False
    try:
        return bool(rc.eval(_RELEASE_IF_OWNER_LUA, 1, lease.key, lease.token))
    except Exception:  # noqa: BLE001
        logger.warning(
            "single_flight: could not release %s; leaving it to expire", lease.key
        )
        return False


def _record_skip(rc, task: str) -> None:
    """Count this decline in a 24 h window. Best-effort; never raises.

    The counter exists because a skip is otherwise invisible: it records no
    start (`record_task_started` is inside `_tracked_run`, which a declining
    tick never reaches — deliberately, so millisecond skips cannot deflate the
    duration histogram that `schedule-adherence` reads to detect the very
    overrun this guard answers). Read it with
    ``/api/admin/redis-read?key=bainluck:inflight:skipped:<task>``.
    """
    try:
        key = skip_counter_key(task)
        pipe = rc.pipeline()
        pipe.set(key, 0, nx=True, ex=SKIP_COUNTER_TTL_SECONDS)
        pipe.incr(key)
        pipe.execute()
    except Exception:  # noqa: BLE001
        pass


@contextmanager
def single_flight(task: str, ttl_seconds: int = DEFAULT_LEASE_TTL_SECONDS):
    """Yield a :class:`Lease` for ``task``, releasing it on the way out.

    Usage in a task body — the decline path returns before `_tracked_run`, so a
    skipped tick records no start and no duration::

        with single_flight("app.tasks.sync_espn_live_events") as lease:
            if not lease.acquired:
                return lease.skipped_result()
            return _tracked_run("espn_sync", _sync_espn_live_events())

    The release is in a ``finally``, so it also runs when the body raises — a
    task that dies still frees its lease immediately, and one that is hard
    killed frees it by TTL.
    """
    rc = _client()
    lease = acquire(task, ttl_seconds=ttl_seconds, rc=rc)
    if not lease.acquired:
        logger.info(
            "single_flight: %s skipped — previous run still in flight (%s)",
            task,
            lease.key,
        )
    try:
        yield lease
    finally:
        # The same client, reused across a pass that can run for minutes. Safe
        # because `get_redis_client()` sets `health_check_interval=25`, so a
        # connection Heroku Redis idle-reaped is PINGed and recycled rather than
        # failing its next use with a TLS handshake error (#1197) — and if it
        # fails anyway, `release` leaves the lease to its TTL rather than
        # deleting blind.
        release(lease, rc=rc)
