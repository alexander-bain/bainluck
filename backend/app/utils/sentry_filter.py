"""Sentry `before_send` filtering — keep the error rail inside the free-plan quota (#1501).

## Why this exists

The org's error quota is 5,000 events/month and resets on the **21st**. Measured
2026-08-13 over 14 days: **0 accepted**, 3,999 `rate_limited`
(`error_usage_exceeded`) and 29,800 `client_discard` (28,872 of them
`ratelimit_backoff` — the SDK backing off after a 429). That is ~2,414 error
events/day offered against a ~164/day budget: **14.7x over**. Spans are
unaffected (861,848 accepted), so the transport is healthy; only the error
category is refused.

The cost of that is not "we lose some noise". It is that **a green Sentry read
means nothing** — #1445 and #1199 both failed silently behind a 0-events-in-24h
bucket that only meant the quota was gone. Cutting volume is what makes a green
read mean something again.

## The shape of the fix

`main.py` (web) already carried almost exactly this filter. The **worker** init
in `app/tasks/__init__.py` carried none — and every top offender is worker-side
(Celery task death, the beat's Redis reconnects). The filter was written once
and applied to the process that wasn't generating the flood. This module is that
filter, shared by both entry points, with the gaps closed.

Three tiers, deliberately not uniform sampling:

* **DROP** — chronic infra noise with a compensating signal elsewhere. Heroku
  Redis TLS resets are the top offender by a wide margin and are already dropped
  on the web side; the client retries and Redis health is covered by the worker
  heartbeat and task metrics.
* **THROTTLE** — real but chronic classes (Celery task death, event-loop
  teardown). One event per signature per window keeps `lastSeen` honest and the
  issue alive in the UI while removing ~99% of the duplicates. Task death is
  independently tracked in Redis task-metrics (`failures_24h`, `hard_kills_24h`,
  `last_failure_at`), so throttling here does not create a blind spot.
* **PASS** — everything else, at full fidelity, subject only to the backstop.

The **backstop** is the important part. The July census (the last window with
accepted data) attributes ~60% of volume to one class, but total volume has since
grown ~5x and Sentry cannot attribute that growth: discarded events have no
server-side signature, because they were never accepted. So this filter does not
rely on the census being complete. Every signature — including one nobody has
identified — is capped at `BACKSTOP_PER_WINDOW` per window. A novel error always
sends its first event immediately; only a repeating one is capped. That is the
opposite of blanket sampling, which would drop a fraction of everything and lose
exactly the novel single-occurrence error you most want.

## Deliberately NOT done

Uniform/blanket `sample_rate`, and a plan upgrade. Both were considered and
ruled out (#1501, Alex 2026-08-13). Nothing here changes `traces_sample_rate` —
spans are inside their own quota and are healthy.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable

logger = logging.getLogger(__name__)

# --- Tier 1: dropped outright -------------------------------------------------
# Exception class names that are pure infrastructure noise. These already had a
# drop rule on the web side; the worker never got one.
DROP_EXC_NAMES = frozenset({
    # SQLAlchemy session-state cascades. These are always a SECOND error caused
    # by a first one that reports on its own; keeping them doubles the volume of
    # every DB incident without adding information.
    "PendingRollbackError",
    "InvalidRequestError",
})

# Redis connectivity is dropped only when the message actually looks like the
# Heroku Redis TLS reset — never on the exception name alone, since
# `ConnectionError` is also raised by httpx/requests for upstream API failures
# we very much want to see.
_REDIS_HOST_MARKERS = ("compute-1.amazonaws.com", "redis", "ec2-")
_REDIS_ERROR_MARKERS = (
    "ssl: unexpected_eof_while_reading",
    "connection reset by peer",
    "error 8 connecting",
    "error 104 connecting",
    "timeout writing to socket",
    "timeout reading from socket",
)

# --- Tier 2: throttled --------------------------------------------------------
# Chronic classes that carry real signal but repeat far too often to pay full
# price for. Each keeps ONE event per signature per THROTTLE_WINDOW_S.
THROTTLE_EXC_NAMES = frozenset({
    # Celery task death. All four are the same family: the task ran out of time
    # or the worker child was killed. Independently tracked in Redis
    # task-metrics, so a throttle here is not a blind spot.
    "SoftTimeLimitExceeded",
    "TimeLimitExceeded",
    "WorkerLostError",   # billiard's real class name -- the web filter said
    "WorkerLost",        # "WorkerLost", which never matched anything.
    "Terminated",
    "SchedulingError",   # beat failing to enqueue, usually a Redis blip
    # Async teardown noise from the run_async() bridge.
    "RuntimeError",      # narrowed by _is_event_loop_noise below
})

# A RuntimeError is only throttled when it is the known event-loop teardown
# message; every other RuntimeError passes at full fidelity.
_EVENT_LOOP_MARKERS = ("event loop is closed", "attached to a different loop")

# Caps are DAILY and deliberately tight. Replaying the real 07-21..07-29 census
# through this filter projects 42 events/day/process at these values, against a
# 164/day budget. The margin matters because state is per-process (see
# _SignatureThrottle): with a signature firing across all 4 realtime children the
# fleet total lands at ~166/day, i.e. right at the budget line and not over it.
# Loosening these is a post-deploy decision to be made against measured volume,
# not a guess made in advance.
THROTTLE_PER_WINDOW = 1           # chronic classes: 1 event per signature per day
THROTTLE_WINDOW_S = 86400
BACKSTOP_PER_WINDOW = 3           # anything else: 3 per signature per day
BACKSTOP_WINDOW_S = 86400
_MAX_TRACKED_SIGNATURES = 512     # bounded: this dict lives in a worker process


class _SignatureThrottle:
    """Per-signature token counter with a bounded, self-evicting table.

    Deliberately in-process and lock-guarded rather than Redis-backed: this code
    runs inside the exception path, and the single biggest error class IS Redis
    being unreachable. A filter that needs Redis to decide whether to report a
    Redis failure is a filter that fails exactly when it matters (gotcha #39).

    Per-process state means N worker processes each allow N times the cap. That
    is understood and priced in: the caps below are per-process, the fleet is a
    handful of processes, and the resulting volume is still ~2 orders of
    magnitude under today's.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._buckets: dict[str, tuple[float, int]] = {}

    def allow(self, signature: str, *, limit: int, window_s: int, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        with self._lock:
            existing = self._buckets.get(signature)
            # Membership, NOT truthiness: a window that opened at monotonic 0.0
            # is a real window, and `not started` would reset it on every call —
            # silently disabling the throttle for that signature forever.
            if existing is None:
                self._buckets[signature] = (now, 1)
                self._evict_if_needed(now)
                return True
            started, count = existing
            if (now - started) >= window_s:
                self._buckets[signature] = (now, 1)
                self._evict_if_needed(now)
                return True
            if count < limit:
                self._buckets[signature] = (started, count + 1)
                return True
            self._buckets[signature] = (started, count + 1)
            return False

    def _evict_if_needed(self, now: float) -> None:
        """Drop the oldest windows once the table is full. Caller holds the lock."""
        if len(self._buckets) <= _MAX_TRACKED_SIGNATURES:
            return
        victims = sorted(self._buckets.items(), key=lambda kv: kv[1][0])
        for key, _ in victims[: len(self._buckets) - _MAX_TRACKED_SIGNATURES]:
            self._buckets.pop(key, None)

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return {k: v[1] for k, v in self._buckets.items()}


def _exc_name_and_value(event: dict[str, Any], hint: dict[str, Any] | None) -> tuple[str, str]:
    """Best-effort (exception class name, message) from a hint or the event body."""
    hint = hint or {}
    exc_info = hint.get("exc_info")
    if exc_info and exc_info[0] is not None:
        name = getattr(exc_info[0], "__name__", "") or ""
        try:
            return name, str(exc_info[1] or "")
        except Exception:
            return name, ""
    values = ((event or {}).get("exception") or {}).get("values") or []
    if values:
        last = values[-1] or {}
        return str(last.get("type") or ""), str(last.get("value") or "")
    return "", str((event or {}).get("message") or "")


def _is_redis_transport_error(exc_name: str, message: str) -> bool:
    """Heroku Redis TLS churn, as opposed to an upstream HTTP ConnectionError."""
    if exc_name not in {"ConnectionError", "TimeoutError", "OperationalError", "HTTPException"}:
        return False
    low = message.lower()
    looks_like_redis = any(m in low for m in _REDIS_HOST_MARKERS)
    looks_like_transport = any(m in low for m in _REDIS_ERROR_MARKERS)
    return looks_like_redis and looks_like_transport


def _is_event_loop_noise(exc_name: str, message: str) -> bool:
    if exc_name != "RuntimeError":
        return False
    low = message.lower()
    return any(m in low for m in _EVENT_LOOP_MARKERS)


def event_signature(event: dict[str, Any], exc_name: str) -> str:
    """A stable grouping key: exception class + where it happened.

    Uses the transaction (Celery task name / HTTP route) rather than the message,
    because the messages carry hostnames, PIDs and row ids that would defeat
    de-duplication entirely -- which is precisely how one class ends up spending
    a whole month's quota.
    """
    where = (event or {}).get("transaction") or ((event or {}).get("logger")) or "?"
    return f"{exc_name or 'unknown'}|{where}"


class SentryVolumeFilter:
    """The `before_send` callable, with counters for post-deploy verification."""

    def __init__(self) -> None:
        self._throttle = _SignatureThrottle()
        self._lock = threading.Lock()
        self.counts = {"passed": 0, "dropped": 0, "throttled": 0, "backstopped": 0}
        self._last_log = 0.0

    def _bump(self, key: str) -> None:
        with self._lock:
            self.counts[key] += 1

    def _maybe_log(self) -> None:
        """Summarise at most once a minute, so the filter itself is auditable.

        Without this the filter is invisible: you cannot tell "the fix worked"
        from "the errors stopped happening", and #1501 is entirely a story about
        an absence being mistaken for health.
        """
        now = time.monotonic()
        with self._lock:
            if now - self._last_log < 60:
                return
            self._last_log = now
            snapshot = dict(self.counts)
        logger.info("sentry_filter: %s", snapshot)

    def __call__(self, event: dict[str, Any], hint: dict[str, Any] | None = None) -> dict[str, Any] | None:
        try:
            return self._decide(event, hint)
        except Exception:  # never let the filter break error reporting
            logger.exception("sentry_filter failed open")
            return event

    def _decide(self, event: dict[str, Any], hint: dict[str, Any] | None) -> dict[str, Any] | None:
        exc_name, message = _exc_name_and_value(event, hint)

        # Tier 1 -- drop outright.
        if exc_name in DROP_EXC_NAMES or _is_redis_transport_error(exc_name, message):
            self._bump("dropped")
            self._maybe_log()
            return None

        signature = event_signature(event, exc_name)

        # Tier 2 -- throttle the chronic-but-meaningful classes.
        if exc_name in THROTTLE_EXC_NAMES and (
            exc_name != "RuntimeError" or _is_event_loop_noise(exc_name, message)
        ):
            if self._throttle.allow(
                signature, limit=THROTTLE_PER_WINDOW, window_s=THROTTLE_WINDOW_S
            ):
                self._bump("passed")
                return event
            self._bump("throttled")
            self._maybe_log()
            return None

        # Tier 3 -- everything else passes, but nothing is unbounded. A novel
        # signature always gets its first event through immediately.
        if self._throttle.allow(
            signature, limit=BACKSTOP_PER_WINDOW, window_s=BACKSTOP_WINDOW_S
        ):
            self._bump("passed")
            return event
        self._bump("backstopped")
        self._maybe_log()
        return None


def build_before_send() -> Callable[[dict, dict | None], dict | None]:
    """Construct the filter. One instance per process (state is per-process)."""
    return SentryVolumeFilter()
