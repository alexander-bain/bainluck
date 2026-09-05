"""
Redis-based adaptive polling state management.
"""

import hashlib
import json
import logging
import os
import time

import redis

logger = logging.getLogger(__name__)

from app.tasks.config import (
    POLL_STATE_KEY,
    LIVE_POLL_INTERVAL,
    FAST_POLL_INTERVAL,
    MEDIUM_POLL_INTERVAL,
    SLOW_POLL_INTERVAL,
    MEDIUM_THRESHOLD,
    SLOW_THRESHOLD,
)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")


# #969 NEVER-AGAIN: BOUNDED BY DEFAULT. A sync Redis client with no socket
# timeout blocks the CALLING thread forever if Redis hangs — and when that caller
# is invoked from inside an asyncio loop (e.g. a phase-marker setex in a
# progress_cb, or ANY of the 69 bare get_redis_client() calls in tasks/), the
# frozen thread IS the event loop, so no wait_for/deadline timer can fire. That
# was the residual sync block behind the #995 saga. The default is now a finite
# timeout so a bare call can never freeze the loop; pass socket_timeout=None to
# explicitly opt out (only if you know the caller does a legitimate long blocking
# op — none exist in this codebase today: no blpop/brpop, pubsub is WS not Redis).
_DEFAULT_REDIS_SOCKET_TIMEOUT = 5.0

# #1197: bound the connection pool. The E-class TLS-handshake churn
# (`[SSL: UNEXPECTED_EOF]`) can be aggravated by an unbounded pool cycling a large
# number of connections through Heroku Redis's idle-reap window. A finite cap keeps
# reuse tight (fewer idle connections to be reaped) and matches the plan's 40-conn
# budget. Override via REDIS_MAX_CONNECTIONS.
_REDIS_MAX_CONNECTIONS = int(os.getenv("REDIS_MAX_CONNECTIONS", "40"))


def _redis_retry():
    """A fresh retry policy: 3 attempts with equal-jitter backoff (cap 1s).

    #1197 THE STRUCTURAL LEVER. The sustained churn is a TLS
    ``ConnectionError: [SSL: UNEXPECTED_EOF_WHILE_READING]`` on a reused,
    idle-reaped connection. The prior ``retry_on_timeout=True`` fix ONLY retries
    ``TimeoutError`` — a handshake EOF is a ``ConnectionError``, so it was never
    retried and surfaced raw (which is why #233/#239 left the churn flat at
    ~378/24h). Pairing ``retry=Retry(...)`` with ``retry_on_error=[ConnectionError]``
    below makes redis-py transparently reconnect+retry the op instead of raising,
    so a handshake blip degrades into a sub-second reconnect rather than a 500 or a
    Sentry event. A fresh Retry per client avoids sharing mutable backoff state.
    """
    from redis.retry import Retry
    from redis.backoff import EqualJitterBackoff

    return Retry(EqualJitterBackoff(cap=1.0, base=0.05), 3)


def _redis_fast_fail_retry():
    """A fresh, LATENCY-BOUNDED retry policy: 1 retry, ~0.1s cap.

    #1197 (r259): the request-path middlewares (rate-limiter, latency sampler)
    must never spend the full ``_redis_retry()`` budget (3 attempts × up to 1s
    backoff, stacked across two ops on the 429 path) burning a churning TLS
    connection — that is exactly what pushed warm team-route latency to 7-17.6s.
    On the request path we want a connection blip to degrade to fail-open in a
    fraction of a second, NOT to be robustly retried: paired with a small
    ``socket_timeout`` the worst case is ~sub-second per op instead of ~seconds.
    Background tasks keep the robust ``_redis_retry()`` — durability matters there,
    latency does not. A fresh Retry per client avoids shared mutable backoff state.
    """
    from redis.retry import Retry
    from redis.backoff import EqualJitterBackoff

    return Retry(EqualJitterBackoff(cap=0.1, base=0.02), 1)


def _redis_retry_on_errors():
    """Exception classes that trigger a transparent reconnect+retry (#1197)."""
    from redis.exceptions import ConnectionError as _ConnErr, TimeoutError as _TmoErr

    return [_ConnErr, _TmoErr]


def get_redis_client(
    socket_timeout=_DEFAULT_REDIS_SOCKET_TIMEOUT,
    socket_connect_timeout=_DEFAULT_REDIS_SOCKET_TIMEOUT,
    fast_fail=False,
):
    """Get sync Redis client with proper SSL handling for Heroku.

    ``socket_timeout``/``socket_connect_timeout`` (seconds) bound every blocking
    Redis op on the returned client. Both default to
    ``_DEFAULT_REDIS_SOCKET_TIMEOUT`` (5s) — bounded by default (#969). Pass
    ``None`` to opt out of a bound (rare; only for a deliberate long blocking op).

    ``fast_fail=True`` (#1197 r259) swaps the robust 3-attempt background retry for
    the latency-bounded ``_redis_fast_fail_retry()`` — use it for clients on the hot
    request path (the latency sampler) so a churning TLS connection degrades to
    fail-open in a fraction of a second instead of spending the full retry budget.
    """
    import ssl

    kwargs = {}
    if socket_timeout is not None:
        kwargs["socket_timeout"] = socket_timeout
    if socket_connect_timeout is not None:
        kwargs["socket_connect_timeout"] = socket_connect_timeout
    # #1197: TCP keepalive + a health-check interval so a connection that Heroku
    # Redis has idle-closed is PINGed and transparently recycled instead of
    # failing its next reuse with a TLS [SSL: UNEXPECTED_EOF] handshake error.
    # r246 option (a): explicit keepalive timers (probe before the idle-reap window,
    # not the ~2h OS default) + retry_on_timeout so a transient EOF self-heals.
    from app.tasks.config import socket_keepalive_options

    kwargs["socket_keepalive"] = True
    _ka = socket_keepalive_options()
    if _ka:
        kwargs["socket_keepalive_options"] = _ka
    kwargs["health_check_interval"] = 25
    kwargs["retry_on_timeout"] = True
    # #1197: retry the TLS-handshake ConnectionError (not just timeouts) + bound
    # the pool. This is the lever the #233/#239 keepalive-only fixes lacked.
    # fast_fail (r259) uses the latency-bounded retry for hot-request-path clients.
    kwargs["retry"] = _redis_fast_fail_retry() if fast_fail else _redis_retry()
    kwargs["retry_on_error"] = _redis_retry_on_errors()
    kwargs["max_connections"] = _REDIS_MAX_CONNECTIONS

    if REDIS_URL.startswith("rediss://"):
        return redis.from_url(
            REDIS_URL,
            ssl_cert_reqs=ssl.CERT_NONE,
            **kwargs,
        )
    return redis.from_url(REDIS_URL, **kwargs)


def get_async_redis_client():
    """Get async Redis client for use in FastAPI route handlers."""
    import ssl
    import redis.asyncio as aioredis

    # #1197 / #969: bound the connect + keep pooled connections alive with a
    # health-check interval so idle-reaped Heroku Redis connections recycle
    # transparently rather than raising a TLS handshake ConnectionError. r246
    # option (a): explicit keepalive timers + retry_on_timeout (see get_redis_client).
    from app.tasks.config import socket_keepalive_options

    stability = {
        "socket_connect_timeout": 5,
        "socket_keepalive": True,
        "health_check_interval": 25,
        "retry_on_timeout": True,
        # #1197: transparently retry the TLS-handshake ConnectionError + bound pool.
        "retry": _redis_retry(),
        "retry_on_error": _redis_retry_on_errors(),
        "max_connections": _REDIS_MAX_CONNECTIONS,
    }
    _ka = socket_keepalive_options()
    if _ka:
        stability["socket_keepalive_options"] = _ka
    if REDIS_URL.startswith("rediss://"):
        return aioredis.from_url(
            REDIS_URL,
            ssl_cert_reqs=ssl.CERT_NONE,
            **stability,
        )
    return aioredis.from_url(REDIS_URL, **stability)


# ---------------------------------------------------------------------------
# Worker-generation liveness (#1280 Item 3).
#
# A poll's phase marker survives a SIGKILL by design (#995 diagnostics), so after
# a DEPLOY restart a frozen ``upsert_loop@120s`` marker sat in Redis for its full
# TTL and the phase-heartbeat watchdog read it as a live "event-loop block" (RED)
# — a false worker-outage alarm. A frozen marker is externally identical whether
# the owning process is WEDGED (real #995, still alive) or DEAD (deploy/restart).
# The only signal that distinguishes them is whether the worker GENERATION that
# wrote the marker is still alive.
#
# Each OS process gets a boot id at import time (prefork children inherit the
# parent's, so it identifies a worker generation / dyno, not a single child). A
# frequently-firing hook (``worker_heartbeat`` signal + every ``_tracked_run``)
# refreshes ``bainluck:worker:alive:<boot_id>`` with a bounded TTL. The watchdog
# stamps each marker with its writer's boot id and only treats a frozen marker as
# a live stall when that boot id is still alive; otherwise it is a stale leftover
# from a dead generation and is reconciled away instead of paging.
# ---------------------------------------------------------------------------
import uuid as _uuid

_WORKER_BOOT_ID = _uuid.uuid4().hex
WORKER_ALIVE_PREFIX = "bainluck:worker:alive:"
# TTL must exceed the worker's heartbeat cadence so a healthy-but-briefly-idle
# generation is never mis-read as dead. The Celery ``worker_heartbeat`` signal
# fires every few seconds and ``_tracked_run`` refreshes on every task, so 300s
# is comfortable headroom while still expiring within one deploy cycle.
WORKER_LIVENESS_TTL = 300


def get_worker_boot_id() -> str:
    """Stable id for THIS worker generation (one per OS process tree)."""
    return _WORKER_BOOT_ID


def touch_worker_liveness(rc=None) -> None:
    """Refresh this generation's liveness key (best-effort, bounded, never raises)."""
    try:
        rc = rc or get_redis_client()
        rc.setex(WORKER_ALIVE_PREFIX + _WORKER_BOOT_ID, WORKER_LIVENESS_TTL, "1")
    except Exception:
        pass


def worker_boot_alive(rc, boot_id: str | None) -> bool:
    """True if ``boot_id`` names a worker generation whose liveness key is fresh.

    Returns False for an empty/None boot id so a legacy marker with no recorded
    owner is handled by the caller's own back-compat path, not silently treated
    as alive."""
    if not boot_id:
        return False
    try:
        return bool(rc.get(WORKER_ALIVE_PREFIX + boot_id))
    except Exception:
        # A read hiccup must not let a stale marker masquerade as live — but also
        # must not suppress a real stall. Degrade to "unknown" = not-alive; the
        # watchdog's legacy back-compat path decides from there.
        return False


INFLIGHT_LEASE_PREFIX = "bainluck:inflight:"

#: Returned by :func:`acquire_inflight_lease` when Redis could not be consulted at
#: all. It is a TOKEN, not a failure: the caller runs. See the fail-open rationale
#: on the acquire function — and note :func:`release_inflight_lease` refuses it, so
#: an ungated pass can never delete a real holder's lease on the way out.
LEASE_UNGATED = "__ungated__"

#: Compare-and-delete. `DEL` alone is the classic bug: a holder whose lease already
#: expired mid-pass would delete its SUCCESSOR's lease on the way out, and two
#: copies would run with neither holding anything. The read and the delete have to
#: be one server-side step or the same race just moves inside the client.
_RELEASE_LEASE_LUA = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
end
return 0
"""


def acquire_inflight_lease(name: str, ttl_s: int) -> str | None:
    """Claim the right to run ``name``; ``None`` if another copy already holds it.

    One `SET key token NX EX ttl` — a SINGLE command, which is the whole design.
    **CERT-1920 is the reason this is not two.** That ship wrote a marker and its
    expiry as separate round trips under a swallowing `except`, and an interrupted
    pair left an immortal key at TTL `-1`. An immortal key here does not merely
    mislead a reader: it disables odds ingestion permanently, because the lease
    nobody can release is the lease nobody can acquire. `SET ... NX EX` cannot
    produce that state — there is no instant at which the key exists without its
    expiry.

    **Fails OPEN, deliberately.** If Redis is unreachable this returns
    :data:`LEASE_UNGATED` and the caller runs ungated. The alternative — refusing
    to poll when the coordination store is down — converts a Redis blip into a
    total ingestion outage, which is strictly worse than the concurrency this
    lease exists to bound. The caller reports which of the two it got, so an
    ungated pass is visible rather than silently indistinguishable from a held one.
    """
    if ttl_s <= 0:
        # Redis rejects a non-positive EX, and a lease with no expiry is the exact
        # failure this function exists to make unreachable — so refuse to gate
        # rather than fall back to an unexpiring SET.
        logger.warning("in-flight lease %s asked for a non-positive TTL %s", name, ttl_s)
        return LEASE_UNGATED

    token = _uuid.uuid4().hex
    try:
        rc = get_redis_client()
        if rc.set(INFLIGHT_LEASE_PREFIX + name, token, nx=True, ex=int(ttl_s)):
            return token
        return None
    except Exception:
        logger.warning("in-flight lease %s unreadable; running ungated", name, exc_info=True)
        return LEASE_UNGATED


def release_inflight_lease(name: str, token: str | None) -> bool:
    """Release ``name`` if ``token`` still owns it. True when this call freed it.

    Best-effort and never raises: a release that fails costs at most the remainder
    of the TTL, whereas an exception escaping a `finally` would replace the real
    error the pass was already raising.
    """
    if not token or token == LEASE_UNGATED:
        return False
    try:
        rc = get_redis_client()
        return bool(rc.eval(_RELEASE_LEASE_LUA, 1, INFLIGHT_LEASE_PREFIX + name, token))
    except Exception:
        logger.warning("in-flight lease %s release failed", name, exc_info=True)
        return False


def compute_odds_hash(events_data: list) -> str:
    """Compute hash of odds data to detect changes."""
    # Extract just the odds-relevant data
    odds_data = []
    for event in events_data:
        for bookmaker in event.get("bookmakers", []):
            for market in bookmaker.get("markets", []):
                for outcome in market.get("outcomes", []):
                    odds_data.append({
                        "event": event.get("id"),
                        "bookmaker": bookmaker.get("key"),
                        "market": market.get("key"),
                        "outcome": outcome.get("name"),
                        "price": outcome.get("price"),
                        "point": outcome.get("point"),
                    })

    # Sort for consistent ordering
    odds_data.sort(key=lambda x: (x["event"], x["bookmaker"], x["market"], x["outcome"]))

    # Hash the JSON representation
    data_str = json.dumps(odds_data, sort_keys=True)
    return hashlib.md5(data_str.encode()).hexdigest()


def should_poll_now() -> tuple[bool, str]:
    """
    Check if we should poll now based on adaptive logic.
    Returns (should_poll, reason).
    """
    try:
        r = get_redis_client()
        state = r.hgetall(POLL_STATE_KEY)

        if not state:
            # First poll ever
            return True, "first_poll"

        last_poll_time = float(state.get(b"last_poll_time", 0))
        unchanged_count = int(state.get(b"unchanged_count", 0))
        has_live_games = state.get(b"has_live_games", b"false") == b"true"

        elapsed = time.time() - last_poll_time

        # Always poll frequently for live games
        if has_live_games:
            if elapsed >= LIVE_POLL_INTERVAL:
                return True, "live_games"
            return False, f"live_wait_{int(LIVE_POLL_INTERVAL - elapsed)}s"

        # Determine interval based on unchanged count
        if unchanged_count >= SLOW_THRESHOLD:
            interval = SLOW_POLL_INTERVAL
        elif unchanged_count >= MEDIUM_THRESHOLD:
            interval = MEDIUM_POLL_INTERVAL
        else:
            interval = FAST_POLL_INTERVAL

        if elapsed >= interval:
            return True, f"interval_{interval}s"

        return False, f"wait_{int(interval - elapsed)}s"

    except Exception as e:
        # If Redis fails, default to polling
        logger.warning("Redis error in should_poll_now: %s", e)
        return True, "redis_error"


def update_poll_state(data_changed: bool, has_live_games: bool, new_hash: str):
    """Update the adaptive polling state in Redis."""
    try:
        r = get_redis_client()

        # Get current unchanged count
        current_count = int(r.hget(POLL_STATE_KEY, "unchanged_count") or 0)

        if data_changed:
            new_count = 0
        else:
            new_count = current_count + 1

        r.hset(POLL_STATE_KEY, mapping={
            "last_poll_time": time.time(),
            "unchanged_count": new_count,
            "has_live_games": "true" if has_live_games else "false",
            "last_hash": new_hash,
        })

        # Set expiry so state cleans up if worker stops
        r.expire(POLL_STATE_KEY, 3600)  # 1 hour

    except Exception as e:
        logger.warning("Redis error in update_poll_state: %s", e)


# =============================================================================
# Task-Level Success Metrics
# =============================================================================

# Redis key prefix for task metrics. Each task gets a hash:
#   bainluck:task_metrics:{task_name} -> {
#       last_success_at, last_failure_at, last_duration_ms,
#       success_count_24h, failure_count_24h,
#       last_result_summary (JSON), consecutive_failures
#   }
TASK_METRICS_PREFIX = "bainluck:task_metrics"
# How long to keep metrics (48 hours — enough for dashboard + debugging)
TASK_METRICS_TTL = 172800

#: The width of the rolling window the ``_24h`` counters accumulate over, and
#: the TTL each counter key is created with. LAT-P024 (#1609) named it: it was a
#: bare ``86400`` literal at the write site, and the read site had no way to
#: refer to the same number, which is half of why the window ended up being
#: tracked in a second key that could disagree with the first.
WINDOW_COUNTER_TTL = 86400

# Task metric labels that were RETIRED from the beat schedule but whose celery
# task + Redis metrics are intentionally kept dormant/registered (e.g. for a
# cheap re-add). Their last-run metrics never refresh, so a stale
# consecutive_failures count would latch the whole health surface to
# "degraded"/"critical" forever (a permanent false alarm). get_task_metrics
# reports these as health="retired" so every rollup that filters on
# "degraded"/"critical" (celery dashboard, build_worker_section, LLM diagnosis)
# drops them automatically. Re-adding a task to the beat = remove it from here.
# Match the label passed to _tracked_run(), not the fully-qualified beat name.
RETIRED_TASK_LABELS = frozenset({
    "resolve_winners",  # retired 2026-07-06 (#991); dormant, folded into backfill_winners
})

# Queue 300H: verdicts (written by _tracked_run via the task_verdict contract)
# that forbid a "healthy" reading of the most recent run.
#   partial   — returned real progress, but not a finished run
#   unknown   — spoke the vocabulary and proved nothing (skipped / overlap
#               refused / complete-but-unpublished)
#   failed    — the task returned a failed terminal without raising
# NOT included: "thrown" (a raised exception keeps the consecutive-failure
# bands) and "unverified" (a legacy summary with no terminal truth to read —
# recorded as before, but stamped so nothing mistakes it for proof).
_NOT_GREEN_VERDICTS = frozenset({"partial", "unknown", "failed"})


#: LAT-P070 (#1609, #1501): terminal fields a run can only have written from an
#: END handler. If any of them post-dates the last start, that run reached a
#: handler — whatever the counters say.
_TERMINAL_STAMP_FIELDS = ("last_success_at", "last_failure_at", "last_incomplete_at")

#: Tolerance on the start/terminal comparison. Both stamps are written by the
#: same process from the same clock, so this only absorbs sub-second ordering
#: noise; it is NOT a window.
_TERMINAL_STAMP_TOLERANCE_S = 1.0


def _parse_iso(value):
    """Epoch seconds from one of the metric hash's ISO stamps, or ``None``."""
    # Function-local, matching this module's existing convention (see
    # `_now_iso`); `datetime` is deliberately not a module-level name here.
    from datetime import datetime

    if not value:
        return None
    if isinstance(value, bytes):
        try:
            value = value.decode()
        except UnicodeDecodeError:
            return None
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return None


def _terminal_evidence_refutes_hard_kill(result: dict):
    """Did the LAST run demonstrably reach an end handler? Reason, or ``None``.

    ``hard_kills_24h`` is DERIVED — ``starts − (successes + failures +
    incompletes)`` — and the four counters do **not** share a window: each is
    stamped ``SET NX EX 86400`` at its own first increment, so each expires on
    its own schedule. For a task whose cadence is *exactly* 24 h, every key's
    expiry therefore lands within milliseconds of the next increment, and
    whether that increment lands on a live key (2) or a dead one (a fresh 1) is
    a race — one that can resolve DIFFERENTLY for ``starts`` and ``successes``,
    because they are written a fraction of a second apart.

    **Measured on production, 2026-08-18T22:45Z, one morning, two tasks, the
    same race resolving in opposite directions:**

    * ``mlb_schedule_coverage`` — ``starts_24h: 1``, ``successes_24h: 0`` (no
      success window at all) ⇒ a derived ``hard_kills_24h: 1`` and
      ``health: critical, "1 runs started, none reached an end handler —
      hard-killed"``. Yet the same payload carried ``last_started_at
      07:05:00.095``, ``last_success_at 07:05:00.851``, ``last_duration_ms
      734`` and a fully populated ``last_result_summary`` for 2026-08-18. A run
      that never reached an end handler cannot have written any of those three —
      **they ARE the end handler's writes.**
    * ``grid_sentinel`` — ``starts_24h: 0``, ``successes_24h: 1``. The inverse,
      saved from a negative only by the ``max(0, …)`` clamp.

    So the reconciliation is not a fudge factor; it is the payload's own
    self-consistency, and it refutes **exactly one** kill — the last run — which
    is the only run these stamps are evidence about. A genuine kill among
    earlier runs survives, because nothing here speaks for those.

    This is doctrine clause 1 in counter form: "could not compare" must not
    render as "hard-killed". A phantom kill is worse than a missing one — it
    files an issue, it turns a health surface red, and (LAT-P069's exact
    warning) it makes a graded read blame the wrong cause.
    """
    started = _parse_iso(result.get("last_started_at"))
    if started is None:
        return None
    for field_name in _TERMINAL_STAMP_FIELDS:
        ended = _parse_iso(result.get(field_name))
        if ended is None:
            continue
        if ended >= started - _TERMINAL_STAMP_TOLERANCE_S:
            return (
                f"counter-window artifact: {field_name}={result.get(field_name)} "
                f"post-dates last_started_at={result.get('last_started_at')}, so the "
                "last run DID reach an end handler; the zero terminal counter is an "
                "independently-expiring 24h window on a ~24h cadence, not a kill"
            )
    return None


def _bump_window_counter(pipe, key: str):
    """Increment a 24h counter WITHOUT sliding its expiry forward.

    ``EXPIRE`` on every increment is what made ``successes_24h`` a lifetime
    counter: a task succeeding hourly pushed the TTL out every hour, so the
    number never rolled over (r346 read `precompute_calibration_main` at 1015 —
    not 24 hours of an hourly task — and it only *looked* frozen because the
    successes had stopped while the TTL kept the stale total alive). SET NX EX
    stamps the window once, at the first increment; the key then dies on
    schedule and the next increment opens a fresh 24h window. Gotcha #49 in
    task-counter form: a lifetime total must never be read as a recent rate.

    LAT-P022 (#1609): the window is now STAMPED, under the same ``NX`` as the
    counter it belongs to, because rolling the window fixed the lifetime-total
    bug and left a subtler one behind — the count became recent but its AGE
    stayed unknowable. ``successes_24h`` names 24 hours and holds anywhere from
    0 to 24 of them, and nothing in the payload said which. Measured on
    2026-08-09: six fixed-cadence tasks whose counters read 52-63 all had
    windows about ONE hour old, so a 30-second task running perfectly at 0.99x
    its cadence (confirmed differentially) presented as missing 96% of its
    fires. A count without its window is not a rate, and every reader that
    treated it as one — including two windows debugging #1609 — got an answer
    off by the ratio of the true window to 24 hours.

    LAT-P024 (#1609): the ``:since`` sibling key that used to carry that window
    start is GONE, and the age is now derived from this counter's own TTL by
    ``_window_age_s``. The sibling could not do the job it was created for.

    Its contract was "``:since`` shares the counter's key prefix, its NX, and
    its TTL, so the two are created and expire together and can never describe
    different windows". That holds only for a pair BORN together, and ``NX`` --
    the very thing that stops the stamp being overwritten -- is also what stops
    it ever being corrected. Two keys with independent TTLs cannot resynchronise
    once anything separates their birthdays, and two ordinary events separate
    them:

    * **The deploy that introduces the stamp.** Every counter already alive at
      that moment keeps its value (``SET NX`` correctly declines to reset it)
      and gets a stamp dated NOW. The window then reads as the age of the
      RELEASE rather than the age of the count.
    * **The counter's own roll.** When the counter expires at its 24h mark and
      is recreated, a stamp created later is still alive, so ``SET NX`` declines
      again -- and the fresh counter inherits a stamp OLDER than itself.

    Measured in production 2026-08-10, both directions, on the same instance:
    ``:starts`` counters were born with v3740 (21:56:23 PT) and their stamps
    with v3743 (07:14:22 PT, the release that shipped the stamp), so
    ``precompute_category_pages`` reported 16 fires in a 6.47h window. It is an
    hourly ``crontab(minute=25)`` beat, so that reading requires **2.47
    schedulers** -- and a non-integer number of schedulers is impossible, which
    is what makes this a proof and not an opinion. The true window was 16.00h,
    the stamp understated it by 2.47x, and every rate derived from it was
    inflated by the same factor. The counter roll produces the mirror-image
    error, so the surface cannot even be relied on to fail in one direction.

    The TTL is not a second opinion about the window -- it IS the window, set
    once here by ``SET ... EX ... NX`` and never touched again (``INCR`` does not
    refresh an expiry). One key cannot disagree with itself. It also removes a
    Redis write from ``record_task_started``, which runs before every task in
    the system.
    """
    pipe.set(key, 0, ex=WINDOW_COUNTER_TTL, nx=True)
    pipe.incr(key)


#: How many recent run durations to keep per task. A p95 needs a tail, and one
#: sample has none: `last_duration_ms` recorded `refresh_open_commentary` at 8ms
#: — a real number, from the run that took the cheap off-tournament skip — while
#: the same task carried a Sentry issue for exceeding a 90s hard limit (#1609).
#: Both are true of that task; only the history shows the second one. Fifty is
#: enough to place a p95 and small enough (~50 short strings per task) that the
#: whole history for ~200 tasks is a rounding error against a 100MB instance.
#:
#: LAT-P040 (#835): fifty is also the reason every duration statistic needs its
#: OWN window. This is a count of SAMPLES, not a span of time, so the period it
#: covers is fifty times the task's own cadence and therefore different for
#: every task — ~50 minutes for a 30s beat, ~2 days for an hourly one. Measured
#: in production 2026-08-11: `poll_odds` held exactly 50 samples spanning ~50
#: minutes while the payload displayed them beside `window_s: 68550` (19.1h), a
#: 23x mismatch. Raising the cap is NOT the fix — it trades the same
#: misreading for more memory. Stamping each sample is, so the span is measured
#: rather than inferred from a counter that ages independently.
DURATION_HISTORY_LEN = 50

#: Separates a sample's duration from the epoch second it was recorded at:
#: ``"5821@1786500000"``. Entries written before LAT-P040 are bare integers and
#: are still read (they simply carry no timestamp), so the history does not have
#: to be discarded on deploy — it refills within one cap-length either way.
_DURATION_STAMP_SEP = "@"


def _push_duration(pipe, task_name: str, duration_ms: float, now_s=None):
    """Append one run's duration to the task's bounded rolling history.

    LTRIM keeps it bounded on every write rather than by TTL, so the list cannot
    grow without limit if a task suddenly runs hot — the memory cost is fixed by
    construction, which matters on an ``allkeys-lru`` instance where an
    unbounded key does not just cost memory, it evicts other people's keys.

    Written for EVERY terminal — success, incomplete and failure alike — because
    a lapping task's expensive runs are frequently the ones that end badly, and
    a history of only the happy path would systematically under-report the tail
    this exists to measure.

    LAT-P040 (#835): each sample carries the epoch second it was recorded at, so
    a reader can compute the span the history actually covers. Without it the
    only window on the payload belongs to the STARTS counter, which ages on its
    own 24h TTL and has no relationship to how far back fifty samples reach —
    and a p95 read against the wrong window is how a ~50-minute burst got
    reported, and staged, as a 19-hour steady state.

    ``now_s`` is injectable so tests can pin the clock instead of sampling it;
    an anchor that moves with the wall clock is gotcha #44.
    """
    hist_key = f"{TASK_METRICS_PREFIX}:{task_name}:durations"
    ts = time.time() if now_s is None else now_s
    pipe.lpush(
        hist_key, f"{round(duration_ms)}{_DURATION_STAMP_SEP}{int(ts)}"
    )
    pipe.ltrim(hist_key, 0, DURATION_HISTORY_LEN - 1)
    pipe.expire(hist_key, TASK_METRICS_TTL)


def _parse_duration_entry(raw):
    """One stored history entry -> ``(duration_ms, recorded_at_s_or_None)``.

    Accepts both the stamped form and the bare-integer form written before
    LAT-P040, because a reader that rejected the legacy shape would report an
    EMPTY history for every task for the first cap-length after deploy — which
    reads as "this task never ran", the precise false absence gotcha #53 is
    about. Anything unparseable is dropped rather than guessed at.
    """
    if isinstance(raw, bytes):
        raw = raw.decode()
    raw = str(raw)
    ms_part, _, ts_part = raw.partition(_DURATION_STAMP_SEP)
    try:
        ms = int(ms_part)
    except (TypeError, ValueError):
        return None
    try:
        ts = int(ts_part) if ts_part else None
    except (TypeError, ValueError):
        ts = None
    return ms, ts


def record_task_started(task_name: str):
    """Record that a task RAN, written in its first moments — CAL-P024b.

    Every other counter in this module is written when a run ENDS, by the
    handlers in ``_tracked_run``. That makes them all conditional on the process
    surviving long enough to reach a handler, and a hard kill does not: a
    Heroku R15 memory kill is a SIGKILL, and Celery's hard ``time_limit`` tears
    the child down. Neither runs an ``except`` block, so a run that dies that
    way leaves **no trace at all** — not a success, not a failure, not an
    incomplete.

    The consequence is not a missing statistic, it is a WRONG one with the
    opposite sign. ``precompute_calibration_main`` was hard-killed ~16 minutes
    into every hourly beat, and its counters read ``successes_24h: 0,
    failures_24h: 0`` — indistinguishable from a task that is not scheduled.
    Two separate windows concluded from that shape that the **beat was not
    firing** and went looking at the scheduler and the queue, when the beat was
    firing on time every hour and dying of memory. An absent observation was
    read as an observed absence: gotcha #53's shape, in the instrument rather
    than the data.

    So: fires are counted at the start, outcomes at the end, and the gap between
    them is exactly the number of runs that died without being able to say so.
    ``starts_24h - (successes + failures + incompletes)`` is the hard-kill count,
    and it is a first-class number rather than an inference.

    Deliberately the cheapest possible write (two Redis ops, best-effort,
    swallowing everything): it runs before the work on every task in the system,
    so it must never be the reason a task fails to start.
    """
    try:
        r = get_redis_client()
        key = f"{TASK_METRICS_PREFIX}:{task_name}"
        pipe = r.pipeline()
        pipe.hset(key, mapping={"last_started_at": _utc_now_iso()})
        pipe.expire(key, TASK_METRICS_TTL)
        _bump_window_counter(pipe, f"{TASK_METRICS_PREFIX}:{task_name}:starts")
        pipe.execute()
    except Exception:
        # Never let metrics recording break a task — least of all this one,
        # which is the first thing every task does.
        pass


#: Deliveries are counted under their OWN top-level prefix, keyed by the
#: fully-qualified celery name rather than by the short `_tracked_run` label.
#:
#: Two reasons, both load-bearing. First, the beat schedule speaks celery names,
#: so a delivery counter keyed that way needs no label join at all — and the
#: label join is exactly what 30 tasks fail (see `record_task_delivery`). A
#: numerator that depends on the join cannot grade the tasks the join loses.
#: Second, `get_all_task_metrics` enumerates `TASK_METRICS_PREFIX` and treats
#: any 3-part key as a task, so a delivery key parked under that prefix would be
#: read back as a phantom task on the health surface. A separate prefix cannot
#: be mistaken for one.
TASK_DELIVERY_PREFIX = "bainluck:task_deliveries"


def record_task_delivery(full_task_name: str):
    """Count one DELIVERY of a celery task — LAT-P039 (#1609, #1716).

    The distinction this draws is the whole point, so it is worth stating
    exactly. ``record_task_started`` claims to count "fires that BEGAN", and it
    is called from inside ``_tracked_run`` — a helper the *task body* invokes.
    So it does not count fires. It counts fires **whose body chose to call it**,
    and a task decides that after its own gate has already run. Measured in
    production 2026-08-11:

    * ``poll_all_odds`` returns ``{"skipped": True}`` from ``should_poll_now()``
      before it ever reaches ``_tracked_run``. Its adaptive gate declined about
      half of its fires — ``LIVE_POLL_INTERVAL`` was 32s against a 30s beat, so
      two consecutive fires could never both pass — and every decline was
      recorded as a fire that did not happen. The surface graded it
      ``ratio 0.50``, which was read as the ingestion beat running at half speed
      for two months. The realtime worker's own execution total says otherwise:
      66 deliveries in the 1,982s since the release, or one per 30.0s exactly.

      🔴 **THIS PARAGRAPH USED TO SAY THAT DECLINE WAS "BY DESIGN". IT WAS NOT
      (LAT-P159).** Correcting the instrument was right — a self-gated decline
      genuinely is not a missed beat, which is what the rest of this docstring
      is about — but the gate had no business declining. 32-against-30 was an
      accident that doubled every live sport's odds cadence, and describing it
      as intentional here is what kept it invisible for three weeks: the one
      surface that would have flagged a task discarding half its deliveries had
      been taught to expect exactly that. ``LIVE_POLL_INTERVAL`` is now derived
      from ``ODDS_POLL_BEAT_SECONDS`` and sits below it, so the decline rate
      should now be near zero while live. **A rising ``self_gated_fires`` on
      this task is once again a real signal — most likely that the pass has
      grown slower than the beat period.**
      ``sync_statpal_livescores`` — same 30s beat, same worker, same window, no
      self-gate — reads 65 deliveries and ``ratio 1.00``. Same beat, same
      infrastructure; the only difference is the gate, so the gate is the cause.
    * **30 of 117 beat-scheduled tasks never call ``_tracked_run`` at all**, so
      they never reach ``record_task_label`` either and are invisible to the
      join. They are precisely 30 of the 34 entries the surface reports as
      ``unmapped`` — a complete explanation, with no remainder (#1716). The
      other 4 call it and simply have not fired inside the window, which is an
      honestly different state and stays reported as one.

    Both failures are the same shape and it is gotcha #53's: a task deciding not
    to work is a fact about the TASK, and it was being read as a fact about the
    SCHEDULER. Wiring this to celery's ``task_prerun`` puts the count where the
    delivery actually is — before any body, before any gate, for every task —
    so "the beat fired" and "the task worked" stop being the same number.

    What a delivery is NOT — LAT-P043 (codex C-RV-1, #1802). ``task_prerun``
    fires before every execution ATTEMPT, so the caller filters two of them out
    before reaching here: a **retry** (``request.retries > 0``) is a re-publish
    the task body asked for, not a beat fire, and a failing task could otherwise
    manufacture ``max_retries + 1`` deliveries from one scheduled fire — padding
    exactly the denominator that would have exposed it; and an **eager** call
    (``request.is_eager``) never crossed a broker at all. The residual, stated
    rather than hidden: a manually dispatched run is indistinguishable from a beat
    publication at this signal, because beat stamps nothing on the message. So
    this counts *first-attempt broker deliveries*, which is an upper bound on
    beat fires — and it is an upper bound whose remaining slack is human-driven
    and rare, not one the scheduler's own failures inflate.

    Deliberately the cheapest possible write, and best-effort like every other
    recorder here: it runs before every task in the system, so it must never be
    the reason one fails to start.
    """
    if not full_task_name:
        return
    try:
        r = get_redis_client()
        pipe = r.pipeline()
        _bump_window_counter(pipe, f"{TASK_DELIVERY_PREFIX}:{full_task_name}")
        pipe.execute()
    except Exception:
        pass


def get_all_task_deliveries() -> dict:
    """``{celery task name: {"fires": int, "window_s": float|None}}``.

    ``window_s`` comes from the counter's own TTL via ``_window_age_s``, so a
    fire count is never handed to a caller without the window that makes it a
    rate — the LAT-P024 lesson, applied at birth this time rather than retrofitted.
    ``None`` is passed through rather than flattened to 0; adherence refuses to
    grade on it, which is the correct reading of "not measurable".
    """
    try:
        r = get_redis_client()
        prefix = f"{TASK_DELIVERY_PREFIX}:"
        out = {}
        for key in r.keys(f"{prefix}*"):
            key_str = key.decode() if isinstance(key, bytes) else key
            name = key_str[len(prefix):]
            if not name:
                continue
            try:
                fires = int(r.get(key_str) or 0)
            except (TypeError, ValueError):
                continue
            out[name] = {"fires": fires, "window_s": _window_age_s(r, key_str)}
        return out
    except Exception:
        return {}


#: Execution lifecycle, counted at celery's OWN signals and keyed by the
#: fully-qualified task name — #1501 item 2, from codex C-CERT-SENTRY-R2.
#:
#: This exists because the compensating instrument for a dropped Sentry event
#: STARTED BELOW THE FAILURE BOUNDARY it was supposed to cover.
#: ``hard_kills_24h`` is ``starts - terminals``, and ``record_task_started``
#: fires inside ``_tracked_run`` — a helper the *task body* elects to call. So:
#:
#: * a child killed BEFORE it reaches that helper records no start, contributes
#:   zero to the difference, and is therefore invisible to the counter;
#: * **30 of 117 beat-scheduled tasks never call the helper at all**, so for
#:   those tasks a hard kill and a healthy no-op delivery are the same
#:   observation — in the counter AND in Sentry, because the parent-side
#:   ``WorkerLostError`` is dropped on the premise that the counter sees it.
#:
#: A compensating instrument that starts below the failure boundary is not a
#: compensating instrument. These two counters are written from ``task_prerun``
#: and ``task_postrun``, which celery emits for **every execution of every
#: task** with no cooperation from any task body, so no body can opt out and
#: task 118 cannot forget to join.
#:
#: ``attempts - terminals`` is the death count. Two residuals, both named rather
#: than hidden:
#:
#: 1. **In-flight runs** inflate the gap by at most the fleet's total
#:    concurrency (~14 processes), so a gap of 1-2 is not yet evidence and a
#:    sustained or large gap is.
#: 2. **A death before ``task_prerun``** — a child lost while the message is
#:    being unpacked — is counted by neither. That window is microseconds of
#:    broker plumbing against a task body's seconds-to-minutes, and closing it
#:    would need a parent-side ``task_received`` counter whose prefetch makes it
#:    an upper bound rather than a count. Stated, not closed.
#:
#: Unlike ``:starts``, this pair deliberately does NOT filter retries or eager
#: runs: a retry that dies is a death, and both counters must apply the same
#: predicate or the difference goes negative and silently reads as healthy.
TASK_LIFECYCLE_PREFIX = "bainluck:task_lifecycle"


def record_task_attempt(full_task_name: str):
    """Count one EXECUTION ATTEMPT, from ``task_prerun`` (#1501 item 2).

    Cheapest possible write, best-effort, swallowing everything: it runs before
    every task in the system and must never be the reason one fails to start.
    """
    if not full_task_name:
        return
    try:
        r = get_redis_client()
        pipe = r.pipeline()
        _bump_window_counter(pipe, f"{TASK_LIFECYCLE_PREFIX}:{full_task_name}:attempts")
        pipe.execute()
    except Exception:
        pass


def record_task_terminal(full_task_name: str):
    """Count one TERMINAL, from ``task_postrun`` (#1501 item 2).

    ``task_postrun`` is emitted after the body returns **or raises**, so a
    handled failure is a terminal exactly like a success. What leaves no
    terminal is what this pair exists to see: SIGKILL, a hard ``time_limit``
    teardown, a dyno cycle mid-run — the deaths that reach no ``except`` block.
    """
    if not full_task_name:
        return
    try:
        r = get_redis_client()
        pipe = r.pipeline()
        _bump_window_counter(pipe, f"{TASK_LIFECYCLE_PREFIX}:{full_task_name}:terminals")
        pipe.execute()
    except Exception:
        pass


class HardKillCensusUnavailable(RuntimeError):
    """The hard-kill census could not be taken.

    A distinct type so a caller can tell "I looked and there were no kills" from
    "I could not look", which a bare ``{}`` cannot express. LAT-P069.
    """


def get_hard_kill_census() -> dict:
    """``{celery task name: {"attempts", "terminals", "hard_kills", "window_s"}}``.

    Independent of ``_tracked_run`` end to end: nothing here is keyed by the
    short label, so the 30 tasks that never call the helper appear like any
    other. ``window_s`` rides along for the LAT-P024 reason — a count handed
    over without the window that makes it a rate is not a measurement.

    ``hard_kills`` is floored at 0. A negative difference means terminals
    outran attempts across a window boundary (the two counters expire
    independently), which is a measurement artifact and not a negative number
    of deaths.

    ⚠️ **Raises rather than returning ``{}`` when the census cannot be taken**
    (LAT-P069, gotcha #53, ruling 075 second clause). This function used to end
    ``except Exception: return {}``, and its only consumer —
    ``ops-snapshot``'s ``hard_kills`` block — renders an empty census as
    ``tasks_observed: 0, total_hard_kills: 0``. That is indistinguishable from
    perfect health, and it is not hypothetical: **the gauge's first production
    read returned exactly that**, three minutes before the same Redis keys
    returned 117 tasks and 13 kills. An unreachable Redis and a fleet with zero
    hard kills produced the same JSON.

    The caller already has a correct error branch (it renders
    ``{"status": "error", "error_class": ..., "error": ...}``); swallowing here
    is what prevented that branch from ever being reached. A reader cannot
    recover a distinction the writer discarded.
    """
    try:
        r = get_redis_client()
        prefix = f"{TASK_LIFECYCLE_PREFIX}:"
        rows: dict = {}
        for key in r.keys(f"{prefix}*"):
            key_str = key.decode() if isinstance(key, bytes) else key
            remainder = key_str[len(prefix):]
            if ":" not in remainder:
                continue
            name, _, kind = remainder.rpartition(":")
            if not name or kind not in ("attempts", "terminals"):
                continue
            try:
                value = int(r.get(key_str) or 0)
            except (TypeError, ValueError):
                continue
            row = rows.setdefault(
                name, {"attempts": 0, "terminals": 0, "hard_kills": 0, "window_s": None}
            )
            row[kind] = value
            if kind == "attempts":
                row["window_s"] = _window_age_s(r, key_str)
        for row in rows.values():
            row["hard_kills"] = max(0, row["attempts"] - row["terminals"])
        return rows
    except Exception as exc:
        # Deliberately re-raised, NOT swallowed. See the docstring: the empty
        # dict this used to return renders as a clean bill of health.
        raise HardKillCensusUnavailable(str(exc)) from exc


#: `app.tasks.<name>` -> the short `_tracked_run` label. One hash, so a reader
#: joins the beat schedule to the metrics in a single round trip.
TASK_LABEL_MAP_KEY = f"{TASK_METRICS_PREFIX}:label_map"


def record_task_label(task_name: str):
    """Remember that this metric label belongs to the celery task now running.

    The beat schedule is keyed by the fully-qualified celery name and every
    counter here is keyed by the short label, and until now nothing joined
    them — so "is this beat firing as often as it is scheduled to?" could not be
    asked programmatically at all, only transcribed by hand for two beats.

    The full name comes from the live celery request rather than from a
    registry, so it records what ACTUALLY ran. A registry can list a task the
    beat never fires; this cannot. Outside a worker (unit tests, an admin
    invocation) there is no request and nothing is written, which is correct —
    an ad-hoc invocation says nothing about a schedule.
    """
    try:
        from celery import current_task

        request = getattr(current_task, "request", None)
        full_name = getattr(request, "task", None)
        if not full_name:
            return
        r = get_redis_client()
        pipe = r.pipeline()
        pipe.hset(TASK_LABEL_MAP_KEY, full_name, task_name)
        pipe.expire(TASK_LABEL_MAP_KEY, TASK_METRICS_TTL)
        pipe.execute()
    except Exception:
        # Same contract as every other recorder here: observability must never
        # be the reason a task fails to start.
        pass


def get_task_label_map() -> dict:
    """``{celery task name: metric label}`` as recorded by real runs."""
    try:
        raw = get_redis_client().hgetall(TASK_LABEL_MAP_KEY) or {}
        return {
            (k.decode() if isinstance(k, bytes) else k):
            (v.decode() if isinstance(v, bytes) else v)
            for k, v in raw.items()
        }
    except Exception:
        return {}


def record_task_success(
    task_name: str,
    duration_ms: float,
    result_summary: dict | None = None,
    verdict: str = "complete",
    verdict_reason: str = "",
):
    """
    Record a COMPLETED task execution with key output metrics.

    Only a run whose returned summary earned ``complete`` — or a legacy task
    with no terminal truth to read, recorded as ``unverified`` — reaches here.
    Partial/failed/unknown runs go to :func:`record_task_incomplete` or
    :func:`record_task_failure` (Queue 300H Item 1).

    Args:
        task_name: Short task identifier (e.g., "poll_odds", "espn_sync")
        duration_ms: How long the task took
        result_summary: Key-value pairs from the task's return dict
                       (e.g., {"events_synced": 12, "errors": 0})
        verdict: "complete" (proved it) or "unverified" (legacy shape — the
                 invocation returned, which is not proof of completed work)
        verdict_reason: Short machine-readable why, stored for operators
    """
    try:
        r = get_redis_client()
        key = f"{TASK_METRICS_PREFIX}:{task_name}"
        now_iso = _utc_now_iso()

        # Increment 24h success counter
        success_key = f"{TASK_METRICS_PREFIX}:{task_name}:successes"
        pipe = r.pipeline()
        pipe.hset(key, mapping={
            "last_success_at": now_iso,
            "last_duration_ms": str(round(duration_ms)),
            "last_result_summary": json.dumps(result_summary or {}),
            "consecutive_failures": "0",
            "last_verdict": verdict,
            "last_verdict_reason": verdict_reason,
        })
        pipe.expire(key, TASK_METRICS_TTL)
        _bump_window_counter(pipe, success_key)
        _push_duration(pipe, task_name, duration_ms)
        pipe.execute()
    except Exception as e:
        # Never let metrics recording break a task
        pass


def record_task_incomplete(
    task_name: str,
    duration_ms: float,
    verdict: str,
    verdict_reason: str,
    result_summary: dict | None = None,
):
    """Record a run that returned without completing its work (Queue 300H).

    This is the shape ``_tracked_run`` had no word for. A resumable sweep that
    stops at its deadline, a build that computed every phase but could not
    publish, a beat that refused an overlap lease — none of these threw, and
    none of them finished. Recording them as successes is how a calibration
    rail stayed dark for weeks while its task read ``healthy`` (#1515).

    Deliberately NOT a failure: ``consecutive_failures`` is left exactly as it
    was, so partial progress never escalates a task to critical and never
    relabels itself as a thrown error. It simply cannot be counted as
    completion, and ``last_verdict`` keeps the task out of GREEN until a run
    actually completes.
    """
    try:
        r = get_redis_client()
        key = f"{TASK_METRICS_PREFIX}:{task_name}"
        now_iso = _utc_now_iso()

        incomplete_key = f"{TASK_METRICS_PREFIX}:{task_name}:incompletes"
        pipe = r.pipeline()
        pipe.hset(key, mapping={
            "last_incomplete_at": now_iso,
            "last_duration_ms": str(round(duration_ms)),
            "last_result_summary": json.dumps(result_summary or {}),
            "last_verdict": verdict,
            "last_verdict_reason": verdict_reason,
        })
        pipe.expire(key, TASK_METRICS_TTL)
        _bump_window_counter(pipe, incomplete_key)
        _push_duration(pipe, task_name, duration_ms)
        pipe.execute()
    except Exception:
        pass


def record_task_failure(
    task_name: str,
    duration_ms: float,
    error: str,
    verdict: str = "thrown",
    verdict_reason: str = "",
    result_summary: dict | None = None,
):
    """Record a failed task execution.

    Reached two ways now: a thrown exception (``verdict="thrown"``, as always),
    and a run that returned a ``failed`` terminal without raising
    (``verdict="failed"``) — ``coverage_metrics`` swallows its own exception and
    returns ``terminal: "failed"``, which used to be recorded as a success.

    The two are distinguished because their escalation policies differ. A
    thrown exception keeps the long-standing consecutive-failure bands (one
    transient error does not degrade a task, and changing that across ~100
    tasks is not this queue's business). A *returned* failed terminal is the
    task's own verdict on itself, and reading GREEN off it is the defect
    (#1515) — so it degrades immediately.
    """
    try:
        r = get_redis_client()
        key = f"{TASK_METRICS_PREFIX}:{task_name}"
        now_iso = _utc_now_iso()

        # Get current consecutive failures
        current = int(r.hget(key, "consecutive_failures") or 0)

        failure_key = f"{TASK_METRICS_PREFIX}:{task_name}:failures"
        pipe = r.pipeline()
        pipe.hset(key, mapping={
            "last_failure_at": now_iso,
            "last_duration_ms": str(round(duration_ms)),
            "last_error": error[:500],  # Truncate long errors
            "consecutive_failures": str(current + 1),
            "last_verdict": verdict,
            "last_verdict_reason": verdict_reason,
            # CAL-P080 (#2007): the failure's OWN copy of its classification,
            # written under a `last_failure_*` name so it lives and dies with
            # `last_failure_at` and `last_error` beside it.
            #
            # This is not duplication of `last_verdict_reason` — it is the fix
            # for that field being the WRONG PLACE to keep it. `last_verdict*`
            # describes the last run of any kind, so the next SUCCESS overwrites
            # it, while `last_error` is never cleared and survives. The two
            # therefore desynchronise the moment a task recovers, and what is
            # left is the failure's message without the exception class that
            # would explain it.
            #
            # Measured cost of that, and it is why this line exists:
            # `precompute_calibration_main` failed at 2026-08-20T16:16:18Z and
            # the 17:15 beat then succeeded. What survived was
            # `last_error: "-241"` — a bare `str(exc)`, ambiguous between at
            # least KeyError(-241), Exception(-241) and a wrapped return code —
            # with `last_verdict: complete` sitting over the one field that
            # named the class. A stalled hourly producer could be measured
            # exactly (one skipped beat = one beat period of frozen
            # `generated_at`) and the cause could not be named at all, from a
            # record that had held it twenty-five minutes earlier.
            "last_failure_type": (verdict_reason or verdict)[:200],
            # #2222: the summary of the run that FAILED.
            #
            # `record_task_success` and `record_task_incomplete` both keep
            # `last_result_summary`. This recorder was the only one that threw it
            # away — and it is the one that fires for the runs an operator
            # actually needs to read. `futures_price_refresh` returned
            # `terminal: failed` on every run for a month while its own summary
            # held the answer (`unknown_outcomes` vs `not_found` vs
            # `unpriceable`), and diagnosing it required clearing the task's
            # Redis attempt markers and re-running it by hand to watch what the
            # counters did — a live experiment to recover a number the failing
            # run had already computed and discarded.
            #
            # Named `last_failure_*` for the CAL-P080 reason directly above: a
            # later SUCCESS overwrites `last_result_summary`, and the failure's
            # own copy has to survive the recovery that erases the shared field.
            "last_failure_summary": json.dumps(result_summary or {})[:4000],
        })
        pipe.expire(key, TASK_METRICS_TTL)
        _bump_window_counter(pipe, failure_key)
        _push_duration(pipe, task_name, duration_ms)
        pipe.execute()
    except Exception:
        pass


def _window_age_s(r, counter_key: str):
    """Seconds since this counter's 24h window opened, or ``None``.

    Derived from the counter's OWN remaining TTL — ``age = WINDOW_COUNTER_TTL -
    ttl`` — rather than from a sibling ``:since`` key, which is LAT-P024's fix
    for a window that drifted from the count it described in both directions.
    See ``_bump_window_counter`` for the measurement and why a second key cannot
    be kept in phase with the first.

    ``None`` means "this counter's window is not measurable", which is a
    genuinely different thing from "the window is new" and must not be flattened
    into 0: a zero age reads as an infinitely fast rate and would make every
    counter look like a task firing thousands of times a second. Callers treat
    ``None`` as unmeasurable — see ``app/utils/schedule_adherence.py``, which
    refuses to grade without it. Three distinct cases return it:

    * ``-2`` — no such key. The counter has never been incremented, or its
      window has rolled and nothing has fired since.
    * ``-1`` — the key exists with NO expiry. Something created this counter
      outside ``_bump_window_counter`` (a bare ``INCR`` creates a key with no
      TTL), so it is an unbounded lifetime total, not a 24h window. That is
      gotcha #118's original bug and it must read as unmeasurable, never as a
      rate.
    * ``ttl > WINDOW_COUNTER_TTL`` — the key outlives the window it is supposed
      to describe, so it was written under a different TTL regime. Refused
      rather than clamped to 0, because clamping would report a brand-new
      window for what is actually an old key and hand the caller the
      infinitely-fast-rate reading this contract exists to prevent.
    """
    try:
        ttl = r.ttl(counter_key)
        if ttl is None:
            return None
        ttl = int(ttl)
        if ttl < 0 or ttl > WINDOW_COUNTER_TTL:
            return None
        return float(WINDOW_COUNTER_TTL - ttl)
    except Exception:
        return None


def get_task_metrics(task_name: str) -> dict:
    """Get metrics for a specific task."""
    try:
        r = get_redis_client()
        key = f"{TASK_METRICS_PREFIX}:{task_name}"
        data = r.hgetall(key)
        if not data:
            return {"task": task_name, "status": "no_data"}

        success_key = f"{TASK_METRICS_PREFIX}:{task_name}:successes"
        failure_key = f"{TASK_METRICS_PREFIX}:{task_name}:failures"
        incomplete_key = f"{TASK_METRICS_PREFIX}:{task_name}:incompletes"
        start_key = f"{TASK_METRICS_PREFIX}:{task_name}:starts"
        successes_24h = int(r.get(success_key) or 0)
        failures_24h = int(r.get(failure_key) or 0)
        incompletes_24h = int(r.get(incomplete_key) or 0)
        starts_24h = int(r.get(start_key) or 0)
        # CAL-P024b: runs that began and never reached ANY end handler — a
        # SIGKILL (Heroku R15 memory) or a hard ``time_limit`` teardown. Clamped
        # at zero because a run can legitimately start in one 24h window and
        # finish in the next.
        #
        # 🔴 LAT-P070 (#1609, #1501): this subtraction spans FOUR INDEPENDENT
        # WINDOWS. The comment forty lines below already says they do not share
        # one — "each opens at its own first increment" — and this line subtracts
        # across them anyway. See ``_terminal_evidence_refutes_hard_kill``: the
        # difference is reconciled against the terminal timestamps before it is
        # published, because on an exactly-daily task the derivation is a
        # coin flip.
        hard_kills_24h = max(0, starts_24h - (successes_24h + failures_24h + incompletes_24h))

        # LAT-P022 (#1609): the counters' own window ages. Every count above is
        # named `_24h` and holds between 0 and 24 hours; without these a reader
        # cannot turn any of them into a rate, which is why "is this beat
        # running as often as it should?" was unanswerable from this payload.
        # `starts_window_s` is the one adherence needs — it ages the numerator
        # that counts fires — but all four are returned so nothing has to guess
        # that they share a window (they do not: each opens at its own first
        # increment, so a task with no failures for a day has no failure window
        # at all).
        windows = {}
        for label, ckey in (
            ("successes", success_key), ("failures", failure_key),
            ("incompletes", incomplete_key), ("starts", start_key),
        ):
            windows[f"{label}_window_s"] = _window_age_s(r, ckey)

        # A bounded rolling history, newest first. p95 lives here rather than
        # being precomputed so the reader can pick its own percentile and so a
        # stored aggregate can never drift from the samples behind it.
        durations = []
        duration_at = []
        duration_stamps = []
        try:
            raw_durations = r.lrange(
                f"{TASK_METRICS_PREFIX}:{task_name}:durations", 0,
                DURATION_HISTORY_LEN - 1,
            ) or []
            for d in raw_durations:
                parsed = _parse_duration_entry(d)
                if parsed is None:
                    continue
                ms, ts = parsed
                durations.append(ms)
                # `duration_at` is POSITIONALLY ALIGNED with `durations` and
                # carries `None` for the pre-LAT-P040 bare form. The window
                # calculation below wants only the real stamps, but a caller
                # asking "which of these samples postdate X" needs alignment,
                # and a list that silently skips unstamped entries would hand
                # it a confident answer about the wrong samples.
                duration_at.append(ts)
                if ts is not None:
                    duration_stamps.append(ts)
        except Exception:
            durations = []
            duration_at = []
            duration_stamps = []

        # LAT-P040 (#835): the duration sample's OWN window. Every other window
        # on this payload ages a counter; none of them ages this list, and the
        # list is bounded by COUNT, so how far back it reaches depends on the
        # task's cadence and is different for every task. Reported explicitly
        # because the alternative is what happened: a p95 computed over ~50
        # minutes of `poll_odds` was read against `starts_window_s` of 19.1
        # hours and became a standing claim about a steady state.
        #
        # `saturated` is the load-bearing half. At the cap, older runs EXIST and
        # were discarded, so the p95 provably cannot describe the full counter
        # window — a reader that sees it can stop treating the number as a
        # 24h property without needing to know DURATION_HISTORY_LEN.
        durations_window_s = None
        if len(duration_stamps) >= 2:
            durations_window_s = float(max(duration_stamps) - min(duration_stamps))

        result = {
            "task": task_name,
            "successes_24h": successes_24h,
            "failures_24h": failures_24h,
            "incompletes_24h": incompletes_24h,
            "starts_24h": starts_24h,
            "hard_kills_24h": hard_kills_24h,
            "recent_durations_ms": durations,
            # LAT-P079 (#2071): the per-sample epoch, newest-first, positionally
            # aligned with `recent_durations_ms`, `None` for legacy unstamped
            # entries. The stamps were already being parsed and then thrown
            # away, which forced every "did this sample happen after X?"
            # question to be answered by ESTIMATE from a 24h counter. Ruling
            # 110's falsifier was estimating a three-week horizon for a fact
            # that is exactly present in the data.
            "recent_durations_at": duration_at,
            "recent_durations_n": len(durations),
            "recent_durations_window_s": durations_window_s,
            "recent_durations_saturated": len(durations) >= DURATION_HISTORY_LEN,
            **windows,
        }

        for k, v in data.items():
            k_str = k.decode() if isinstance(k, bytes) else k
            v_str = v.decode() if isinstance(v, bytes) else v
            if k_str == "last_result_summary":
                try:
                    result[k_str] = json.loads(v_str)
                except (json.JSONDecodeError, TypeError):
                    result[k_str] = v_str
            else:
                result[k_str] = v_str

        # LAT-P070 (#1609, #1501): reconcile the DERIVED kill count against the
        # terminal stamps now that the hash has been merged in above. Done here
        # and not at the subtraction because the evidence lives in the hash, and
        # done before the health block because the health block asserts the
        # mechanism ("hard-killed (memory / hard time limit)") out loud.
        hard_kill_refutation = None
        if hard_kills_24h > 0:
            hard_kill_refutation = _terminal_evidence_refutes_hard_kill(result)
            if hard_kill_refutation:
                # Exactly one — the last run — because that is the only run these
                # stamps are evidence about. Earlier kills survive.
                hard_kills_24h = max(0, hard_kills_24h - 1)
                result["hard_kills_24h"] = hard_kills_24h
                result["hard_kills_refuted"] = hard_kill_refutation

        # Compute health status. Retired tasks report a distinct "retired"
        # health so their stale metrics can't latch the health rollups to
        # degraded/critical (those rollups filter on health == degraded/critical).
        if task_name in RETIRED_TASK_LABELS:
            result["retired"] = True
            result["health"] = "retired"
            return result

        consecutive = int(result.get("consecutive_failures", 0))
        # Idle-first health (L2-116): a task that recorded NO successes AND NO
        # failures in the last 24h is IDLE, not broken — the worker is alive
        # (fresh heartbeat, no active run) and simply had nothing to do. The
        # metrics hash keeps `consecutive_failures` for 48h (TASK_METRICS_TTL) but
        # the :successes / :failures counters expire at 24h, so between 24h–48h
        # after the last failure a stale `consecutive_failures` would otherwise
        # latch the health surface to critical/degraded during a pure idle window
        # (r195: an idle moment read `critical` — the inverse of a stuck fetch,
        # which is caught separately by the phase-heartbeat watchdog + surfaced on
        # the cockpit). Real, current failures still surface: any failure in the
        # last 24h keeps failures_24h > 0, so the consecutive bands below stay live.
        if successes_24h == 0 and failures_24h == 0 and incompletes_24h == 0:
            # CAL-P024b: "no outcomes" has TWO causes and they are opposites.
            # If the task also never STARTED, it is idle — the reading above.
            # If it started and recorded nothing, every run was killed before it
            # could reach a handler, which is the worst state this surface can
            # describe, not the most benign. ``precompute_calibration_main`` sat
            # in exactly that state for a week reading ``no_data``, and two
            # windows took the reading at face value and went looking for a
            # scheduler fault while the beat fired hourly and died of memory.
            if starts_24h > 0:
                # LAT-P070: ...unless the payload's own terminal stamps say the
                # last run DID reach a handler. Then this branch would publish a
                # mechanism ("hard-killed") that the same payload refutes, and a
                # daily task would flip red on a millisecond race between two
                # independently-expiring counters. Measured: `mlb_schedule_coverage`
                # read critical/hard-killed with a 734 ms duration and a full
                # result summary from the same morning.
                if hard_kill_refutation:
                    result["health"] = "healthy"
                    result["health_reason"] = hard_kill_refutation
                    return result
                result["health"] = "critical"
                result["health_reason"] = (
                    f"{starts_24h} runs started, none reached an end handler "
                    "— hard-killed (memory / hard time limit)"
                )
                return result
            result["health"] = "no_data"
        elif consecutive >= 5:
            result["health"] = "critical"
        elif consecutive >= 2:
            result["health"] = "degraded"
        elif result.get("last_verdict") in _NOT_GREEN_VERDICTS:
            # Queue 300H: the most recent run returned without completing its
            # work (partial sweep, unpublished build, refused overlap lease).
            # It threw nothing, so the consecutive-failure bands above are all
            # zero — and reporting "healthy" here is precisely the false GREEN
            # that let three calibration tasks vouch for a dark rail (#1515).
            # "degraded" is used rather than a new word so every existing
            # rollup (cockpit, celery dashboard, source health) surfaces it;
            # `last_verdict_reason` carries the why.
            result["health"] = "degraded"
        else:
            result["health"] = "healthy"

        return result
    except Exception as e:
        return {"task": task_name, "status": "error", "error": str(e)}


def get_all_task_metrics() -> list[dict]:
    """Get metrics for all tracked tasks."""
    try:
        r = get_redis_client()
        # Find all task metric keys
        pattern = f"{TASK_METRICS_PREFIX}:*"
        keys = r.keys(pattern)

        # Extract unique task names (skip :successes and :failures counter keys)
        task_names = set()
        for key in keys:
            key_str = key.decode() if isinstance(key, bytes) else key
            parts = key_str.split(":")
            if len(parts) == 3 and key_str != TASK_LABEL_MAP_KEY:
                # bainluck:task_metrics:task_name
                #
                # The label map sits under the same prefix and is also 3 parts
                # deep, so without excluding it by name it would be read back as
                # a task called "label_map" — and since it is a non-empty hash,
                # `get_task_metrics` would not even return `no_data` for it. It
                # would emit a phantom task on the health surface, which is the
                # exact class of thing this queue exists to stop inventing.
                task_names.add(parts[2])

        return [get_task_metrics(name) for name in sorted(task_names)]
    except Exception as e:
        return [{"status": "error", "error": str(e)}]


def _utc_now_iso() -> str:
    """Get current UTC time as ISO string."""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


# =============================================================================
# Odds API Quota Monitoring
# =============================================================================

QUOTA_KEY = "bainluck:odds_api_quota"
QUOTA_HISTORY_PREFIX = "bainluck:odds_api_quota:hourly"
QUOTA_TASK_HOURLY_PREFIX = "bainluck:odds_api_quota:task_hourly"
QUOTA_SPORT_HOURLY_PREFIX = "bainluck:odds_api_quota:sport_hourly"
QUOTA_ALERT_THRESHOLD = 500_000
QUOTA_WARNING_THRESHOLD = 1_000_000

# Emergency quota guard thresholds — TRUE EMERGENCIES ONLY.
# This is a last-resort circuit breaker, not a routine optimization tool.
# Prefer rate-limiting, tier adjustments, and region trimming first.
#
# The guard is purely remaining-driven: check_quota_guard() compares the live
# `remaining` reading (refreshed on every Odds API response via
# record_odds_api_quota) against these thresholds. There is NO date/expiry
# constant and there must never be one — a hardcoded expiry date silently
# disabled the guard once it rolled past (the QUOTA_GUARD_EXPIRY regression).
# Recovery is automatic: when the billing cycle resets, the API returns a
# refilled `remaining` and the guard stops tripping with no code change. Do not
# reintroduce a date-based enable/disable; gate only on `remaining`.
QUOTA_GUARD_LIVE_ONLY = 50_000   # Below this: only poll live games (no discovery/futures)
QUOTA_GUARD_FULL_STOP = 20_000   # Below this: stop ALL Odds API calls (except priority sports)
QUOTA_GUARD_ABSOLUTE_STOP = 500  # Below this: stop ALL Odds API calls, no exceptions

# Priority sports: allowed to poll even in FULL_STOP mode with conservation settings.
# h2h only, single region, slower interval.
QUOTA_GUARD_PRIORITY_SPORTS = frozenset({
    "basketball_nba",
    "baseball_mlb",
    "basketball_ncaab",
})
# Conservation poll interval for priority sports in low-quota mode (10 min)
QUOTA_GUARD_CONSERVATION_INTERVAL = 600

import logging
_quota_logger = logging.getLogger(__name__)


def check_quota_guard(
    task_type: str, sport_key: str | None = None, quiet: bool = False,
) -> tuple[bool, str]:
    """Check if an Odds API task should proceed based on remaining quota.

    Args:
        task_type: One of "poll_odds", "discover_events", "poll_futures".
                   "poll_odds" is further split: live games always allowed
                   until FULL_STOP; non-live polling stops at LIVE_ONLY.
        sport_key: Optional sport key for per-sport priority filtering.
        quiet: Suppress this function's own announcement of the breaker state.
               The RETURN VALUE is identical — only the log line is dropped.

               For callers that re-read the breaker inside a loop. Since
               CERT-535, `_poll_all_odds` re-reads once per sport in every
               quota mode, and a `full_stop` reading logs CRITICAL on every
               non-priority sport: a dozen sports at a 30 s beat is ~50,000
               CRITICAL lines a day for a state the pass already announced
               once. That is a Sentry flood during the exact emergency an
               operator needs to read, and drowning the breaker's own message
               is not the same thing as making it loud.

               A quiet read is an internal consistency check, not a decision.
               The caller is expected to announce what it DOES about it —
               `_poll_all_odds` logs the outer state once per pass and logs
               its own CRITICAL on a mid-pass absolute stop. Never pass this
               from a call site that has no such announcement.

    Returns:
        (should_proceed, reason) — False means skip this task entirely.
        Reason strings:
          "conservation_<remaining>" — proceed but use h2h/us only + slow interval
          "live_only_<remaining>" — proceed but only live games
          "full_stop_<remaining>" — do not proceed
    """
    from datetime import datetime, timezone

    r = get_redis_client()
    if not r:
        return True, "no_redis"

    try:
        data = r.hgetall(QUOTA_KEY)
        if not data:
            return True, "no_quota_data"

        remaining = int(data.get(b"remaining", b"999999"))

        # Absolute stop: no exceptions, no priority sports, nothing.
        # Live game data still flows via ESPN, StatPal, Kalshi, Polymarket.
        if remaining <= QUOTA_GUARD_ABSOLUTE_STOP:
            if not quiet:
                _quota_logger.critical(
                    "QUOTA GUARD: ABSOLUTE STOP — %s remaining. Blocking ALL Odds API calls.",
                    f"{remaining:,}",
                )
            return False, f"absolute_stop_{remaining}"

        if remaining <= QUOTA_GUARD_FULL_STOP:
            # Priority sports get through in conservation mode
            if task_type == "poll_odds" and sport_key in QUOTA_GUARD_PRIORITY_SPORTS:
                if not quiet:
                    _quota_logger.info(
                        "QUOTA GUARD: conservation mode — %s remaining. Allowing priority sport %s.",
                        f"{remaining:,}", sport_key,
                    )
                return True, f"conservation_{remaining}"
            if not quiet:
                _quota_logger.critical(
                    "QUOTA GUARD: FULL STOP — %s remaining. Blocking %s.",
                    f"{remaining:,}", task_type,
                )
            return False, f"full_stop_{remaining}"

        if remaining <= QUOTA_GUARD_LIVE_ONLY:
            # Only live game polling is allowed
            if task_type in ("discover_events", "poll_futures"):
                if not quiet:
                    _quota_logger.warning(
                        "QUOTA GUARD: live-only mode — %s remaining. Blocking %s.",
                        f"{remaining:,}", task_type,
                    )
                return False, f"live_only_{remaining}"
            # poll_odds proceeds but will be filtered to live-only by caller
            return True, f"live_only_{remaining}"

        return True, f"ok_{remaining}"
    except Exception:
        return True, "redis_error"


def record_odds_api_quota(
    remaining: int,
    used: int,
    source_task: str,
    pre_call_used: int | None = None,
    sport_key: str | None = None,
):
    """Store latest quota reading from passive header capture.

    Args:
        remaining: Remaining quota from API header
        used: Used quota from API header (after the call)
        source_task: Which task made the call (poll_odds, discover_events, poll_futures)
        pre_call_used: Used quota BEFORE the API call (from a previous header read).
                       If provided, enables accurate per-task attribution.
        sport_key: Optional sport identifier the call was made for. When provided
                   alongside a positive delta, billed units are also attributed to
                   a per-sport hourly bucket, enabling per-sport cost visibility.
    """
    from datetime import datetime, timezone, timedelta

    r = get_redis_client()
    if not r:
        return
    try:
        now = datetime.now(timezone.utc)
        hour_key = now.strftime("%Y-%m-%dT%H")

        pipe = r.pipeline()
        # Current snapshot (always up to date)
        pipe.hset(QUOTA_KEY, mapping={
            "remaining": str(remaining),
            "used": str(used),
            "updated_at": now.isoformat(),
            "source_task": source_task,
        })
        pipe.expire(QUOTA_KEY, 86400 * 7)  # 7 day TTL

        # Hourly history (for graphing)
        history_key = f"{QUOTA_HISTORY_PREFIX}:{hour_key}"
        pipe.hset(history_key, mapping={
            "remaining": str(remaining),
            "used": str(used),
        })
        pipe.expire(history_key, 86400 * 35)  # 35 day TTL (covers full billing cycle)

        # Per-task quota delta tracking
        # Use pre_call_used if provided (accurate per-task attribution),
        # otherwise fall back to global prev_used (may misattribute across tasks)
        if pre_call_used is not None:
            delta = used - pre_call_used
        else:
            prev_data = r.hgetall(QUOTA_KEY)
            prev_used = int(prev_data.get(b"used", b"0")) if prev_data else 0
            delta = used - prev_used
        if delta > 0:  # Skip negative deltas (month rollover)
            task_hourly_key = f"{QUOTA_TASK_HOURLY_PREFIX}:{source_task}:{hour_key}"
            pipe.incrby(task_hourly_key, delta)
            pipe.expire(task_hourly_key, 86400 * 35)  # 35 day TTL

            # Per-sport attribution (only when caller supplies a sport_key).
            # Sharing the same delta as task attribution keeps totals consistent.
            if sport_key:
                sport_hourly_key = f"{QUOTA_SPORT_HOURLY_PREFIX}:{sport_key}:{hour_key}"
                pipe.incrby(sport_hourly_key, delta)
                pipe.expire(sport_hourly_key, 86400 * 35)

        pipe.execute()

        # Log warnings at threshold crossings
        if remaining <= QUOTA_ALERT_THRESHOLD:
            _quota_logger.warning(
                "ODDS API QUOTA LOW: %s remaining (%s used)", f"{remaining:,}", f"{used:,}"
            )
        elif remaining <= QUOTA_WARNING_THRESHOLD:
            _quota_logger.warning(
                "Odds API quota low: %s remaining (%s used)", f"{remaining:,}", f"{used:,}"
            )
    except Exception:
        pass  # Never break a task for metrics


def get_odds_api_quota() -> dict:
    """Get current quota snapshot from Redis."""
    r = get_redis_client()
    if not r:
        return {"status": "unknown"}
    try:
        data = r.hgetall(QUOTA_KEY)
        if not data:
            return {"status": "no_data"}

        remaining = int(data.get(b"remaining", b"0"))
        used = int(data.get(b"used", b"0"))
        total = remaining + used
        pct_used = (used / total * 100) if total > 0 else 0

        if remaining <= QUOTA_ALERT_THRESHOLD:
            health = "critical"
        elif remaining <= QUOTA_WARNING_THRESHOLD:
            health = "warning"
        else:
            health = "healthy"

        return {
            "remaining": remaining,
            "used": used,
            "total": total,
            "pct_used": round(pct_used, 1),
            "health": health,
            "updated_at": data.get(b"updated_at", b"").decode(),
            "source_task": data.get(b"source_task", b"").decode(),
        }
    except Exception:
        return {"status": "error"}


def get_odds_api_quota_history(hours: int = 168) -> list:
    """Get hourly quota history for graphing (default: 7 days)."""
    from datetime import datetime, timezone, timedelta

    r = get_redis_client()
    if not r:
        return []
    try:
        now = datetime.now(timezone.utc)
        results = []
        for h in range(hours):
            dt = now - timedelta(hours=h)
            key = f"{QUOTA_HISTORY_PREFIX}:{dt.strftime('%Y-%m-%dT%H')}"
            data = r.hgetall(key)
            if data:
                results.append({
                    "hour": dt.strftime("%Y-%m-%dT%H:00Z"),
                    "remaining": int(data.get(b"remaining", b"0")),
                    "used": int(data.get(b"used", b"0")),
                })
        return list(reversed(results))
    except Exception:
        return []


def get_odds_api_task_breakdown(hours: int = 168) -> list:
    """Get daily quota usage breakdown by task type.

    Args:
        hours: Number of hours to look back (default: 168 = 7 days)

    Returns:
        List of daily totals per task, e.g.:
        [{"date": "2026-03-26", "poll_odds": 50000, "discover_events": 10000, "poll_futures": 5000}]
    """
    from datetime import datetime, timezone, timedelta
    from collections import defaultdict

    r = get_redis_client()
    if not r:
        return []
    try:
        # Scan for all task_hourly keys
        pattern = f"{QUOTA_TASK_HOURLY_PREFIX}:*"
        keys = r.keys(pattern)

        # Group by date and task
        daily_data: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

        for key in keys:
            key_str = key.decode() if isinstance(key, bytes) else key
            # Format: bainluck:odds_api_quota:task_hourly:{task_name}:{YYYY-MM-DDTHH}
            parts = key_str.split(":")
            if len(parts) >= 5:
                task_name = parts[3]
                hour_str = parts[4]
                date_str = hour_str[:10]  # Extract YYYY-MM-DD

                delta = int(r.get(key) or 0)
                daily_data[date_str][task_name] += delta

        # Convert to list format, sorted by date
        results = []
        for date in sorted(daily_data.keys()):
            entry = {"date": date}
            entry.update(daily_data[date])
            results.append(entry)

        return results
    except Exception:
        return []


def get_odds_api_sport_breakdown(hours: int = 24) -> list:
    """Get billed-unit usage broken down by sport_key over a rolling window.

    Per-sport attribution is only populated when callers pass ``sport_key`` to
    ``record_odds_api_quota`` — discovery, live polling, and futures all do so.

    Args:
        hours: Number of hours to look back (default: 24)

    Returns:
        List of per-sport totals sorted by usage descending, e.g.:
        [{"sport": "basketball_nba", "billed_units": 42000, "hours": 24}, ...]
    """
    from datetime import datetime, timezone, timedelta
    from collections import defaultdict

    r = get_redis_client()
    if not r:
        return []
    try:
        now = datetime.now(timezone.utc)
        # Build the set of hour keys within the window so we only aggregate
        # buckets we actually care about (avoids scan-every-key blowups).
        window_hours = {
            (now - timedelta(hours=h)).strftime("%Y-%m-%dT%H")
            for h in range(hours)
        }

        pattern = f"{QUOTA_SPORT_HOURLY_PREFIX}:*"
        keys = r.keys(pattern)

        per_sport: dict[str, int] = defaultdict(int)
        for key in keys:
            key_str = key.decode() if isinstance(key, bytes) else key
            # Format: bainluck:odds_api_quota:sport_hourly:{sport_key}:{YYYY-MM-DDTHH}
            # sport_key may itself contain colons in theory; split from the right.
            parts = key_str.rsplit(":", 1)
            if len(parts) != 2:
                continue
            hour_str = parts[1]
            if hour_str not in window_hours:
                continue
            # Strip the shared prefix (plus trailing colon) to recover sport_key
            prefix_len = len(QUOTA_SPORT_HOURLY_PREFIX) + 1
            sport_key = parts[0][prefix_len:]
            if not sport_key:
                continue
            try:
                delta = int(r.get(key) or 0)
            except (TypeError, ValueError):
                continue
            per_sport[sport_key] += delta

        results = [
            {"sport": sport, "billed_units": units, "hours": hours}
            for sport, units in per_sport.items()
        ]
        results.sort(key=lambda row: row["billed_units"], reverse=True)
        return results
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Database size history (for trended storage view)
# ---------------------------------------------------------------------------

DB_SIZE_HISTORY_PREFIX = "bainluck:db_size_history"

# ---------------------------------------------------------------------------
# StatPal API usage tracking
# ---------------------------------------------------------------------------

STATPAL_USAGE_KEY = "bainluck:statpal_usage"
STATPAL_USAGE_HISTORY_PREFIX = "bainluck:statpal_usage:daily"


def record_statpal_usage(request_count: int, api_date: str):
    """Store a StatPal daily request count reading.

    Args:
        request_count: Number of requests made today (from StatPal API).
        api_date: Date string from the API response (YYYY-MM-DD).
    """
    from datetime import datetime, timezone

    r = get_redis_client()
    if not r:
        return
    try:
        now_str = datetime.now(timezone.utc).isoformat()
        r.hset(STATPAL_USAGE_KEY, mapping={
            "request_count": request_count,
            "date": api_date,
            "updated_at": now_str,
        })
        # Also store in daily history (keyed by the API date)
        history_key = f"{STATPAL_USAGE_HISTORY_PREFIX}:{api_date}"
        r.set(history_key, str(request_count), ex=86400 * 90)  # 90 day TTL
    except Exception:
        pass


def get_statpal_usage() -> dict:
    """Get current StatPal usage snapshot from Redis."""
    r = get_redis_client()
    if not r:
        return {"status": "unknown"}
    try:
        data = r.hgetall(STATPAL_USAGE_KEY)
        if not data:
            return {"status": "no_data"}
        return {
            "request_count": int(data.get(b"request_count", b"0")),
            "date": data.get(b"date", b"").decode(),
            "updated_at": data.get(b"updated_at", b"").decode(),
        }
    except Exception:
        return {"status": "error"}


def get_statpal_usage_history(days: int = 90) -> list:
    """Get daily StatPal request counts for trending."""
    from datetime import datetime, timezone, timedelta

    r = get_redis_client()
    if not r:
        return []
    try:
        results = []
        now = datetime.now(timezone.utc)
        for i in range(days):
            day = (now - timedelta(days=days - 1 - i)).strftime("%Y-%m-%d")
            key = f"{STATPAL_USAGE_HISTORY_PREFIX}:{day}"
            val = r.get(key)
            if val:
                results.append({"date": day, "request_count": int(val)})
        return results
    except Exception:
        return []


def record_db_size(size_mb: float):
    """Store a DB size reading keyed by date (one per day)."""
    from datetime import datetime, timezone
    r = get_redis_client()
    if not r:
        return
    try:
        day_key = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        history_key = f"{DB_SIZE_HISTORY_PREFIX}:{day_key}"
        r.set(history_key, str(round(size_mb, 1)), ex=86400 * 90)  # 90 day TTL
    except Exception:
        pass


def get_db_size_history(days: int = 90) -> list:
    """Get daily DB size readings for trending."""
    from datetime import datetime, timezone, timedelta
    r = get_redis_client()
    if not r:
        return []
    try:
        results = []
        now = datetime.now(timezone.utc)
        for i in range(days):
            day = (now - timedelta(days=days - 1 - i)).strftime("%Y-%m-%d")
            key = f"{DB_SIZE_HISTORY_PREFIX}:{day}"
            val = r.get(key)
            if val:
                results.append({"date": day, "size_mb": float(val)})
        return results
    except Exception:
        return []


# =============================================================================
# Link Rate Change Detection
# =============================================================================

LINK_RATE_SNAPSHOT_PREFIX = "bainluck:link_rate_snapshot"
SOURCE_COVERAGE_SNAPSHOT_PREFIX = "bainluck:source_coverage_snapshot"


def record_link_rate_snapshot(rates: dict[str, float]) -> None:
    """Store today's per-sport/league link rates in Redis.

    Args:
        rates: {"kalshi:basketball_nba": 100.0, "polymarket:tennis": 35.1, ...}
    """
    from datetime import datetime, timezone
    try:
        r = get_redis_client()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        key = f"{LINK_RATE_SNAPSHOT_PREFIX}:{today}"
        r.hset(key, mapping={k: str(v) for k, v in rates.items()})
        r.expire(key, 86400 * 7)
    except Exception:
        pass


def get_link_rate_changes(threshold_pp: float = 5.0) -> list[dict]:
    """Compare today's link rates vs yesterday's. Return significant changes.

    Returns list of {"key": "kalshi:basketball_nba", "today": 95.0, "yesterday": 100.0, "delta": -5.0}
    """
    from datetime import datetime, timedelta, timezone
    try:
        r = get_redis_client()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")

        today_data = r.hgetall(f"{LINK_RATE_SNAPSHOT_PREFIX}:{today}")
        yesterday_data = r.hgetall(f"{LINK_RATE_SNAPSHOT_PREFIX}:{yesterday}")

        if not today_data or not yesterday_data:
            return []

        def _decode(d):
            return {
                (k.decode() if isinstance(k, bytes) else k): float(v.decode() if isinstance(v, bytes) else v)
                for k, v in d.items()
            }

        today_rates = _decode(today_data)
        yesterday_rates = _decode(yesterday_data)

        changes = []
        for key in set(today_rates) | set(yesterday_rates):
            t = today_rates.get(key)
            y = yesterday_rates.get(key)
            if t is not None and y is not None:
                delta = t - y
                if abs(delta) >= threshold_pp:
                    changes.append({"key": key, "today": t, "yesterday": y, "delta": round(delta, 1)})
            elif t is not None and y is None:
                changes.append({"key": key, "today": t, "yesterday": None, "delta": None, "note": "new"})
            elif t is None and y is not None:
                changes.append({"key": key, "today": None, "yesterday": y, "delta": None, "note": "disappeared"})

        return sorted(changes, key=lambda c: abs(c.get("delta") or 0), reverse=True)
    except Exception:
        return []


def record_source_coverage_snapshot(rates: dict[str, float]) -> None:
    """Store today's per-sport/source event coverage rates in Redis."""
    from datetime import datetime, timezone
    try:
        r = get_redis_client()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        key = f"{SOURCE_COVERAGE_SNAPSHOT_PREFIX}:{today}"
        r.hset(key, mapping={k: str(v) for k, v in rates.items()})
        r.expire(key, 86400 * 7)
    except Exception:
        pass


def get_source_coverage_changes(threshold_pp: float = 5.0) -> list[dict]:
    """Compare today's source coverage vs yesterday's. Return significant changes."""
    from datetime import datetime, timedelta, timezone
    try:
        r = get_redis_client()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")

        today_data = r.hgetall(f"{SOURCE_COVERAGE_SNAPSHOT_PREFIX}:{today}")
        yesterday_data = r.hgetall(f"{SOURCE_COVERAGE_SNAPSHOT_PREFIX}:{yesterday}")

        if not today_data or not yesterday_data:
            return []

        def _decode(d):
            return {
                (k.decode() if isinstance(k, bytes) else k): float(v.decode() if isinstance(v, bytes) else v)
                for k, v in d.items()
            }

        today_rates = _decode(today_data)
        yesterday_rates = _decode(yesterday_data)

        changes = []
        for key in set(today_rates) | set(yesterday_rates):
            t = today_rates.get(key)
            y = yesterday_rates.get(key)
            if t is not None and y is not None:
                delta = t - y
                if abs(delta) >= threshold_pp:
                    changes.append({"key": key, "today": t, "yesterday": y, "delta": round(delta, 1)})

        return sorted(changes, key=lambda c: abs(c.get("delta") or 0), reverse=True)
    except Exception:
        return []
