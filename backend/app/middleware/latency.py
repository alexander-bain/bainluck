"""
Latency tracking middleware.

Samples request latency and stores per-endpoint percentiles in Redis
using sorted sets with a 1-hour rolling window. Lightweight: only
samples every Nth request and normalizes paths to collapse IDs.

Redis keys:
  latency:{normalized_path}  — sorted set of (timestamp, latency_ms)
  latency:_endpoints          — set of all tracked endpoint paths
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from typing import Optional

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from app.utils.request_timing import REQUEST_START_HEADER

logger = logging.getLogger(__name__)

# Sample every Nth request to limit Redis writes.
SAMPLE_RATE = int(os.getenv("LATENCY_SAMPLE_RATE", "10"))

# #1500: endpoints that are ALWAYS sampled, regardless of SAMPLE_RATE.
#
# The 1-in-10 rate was applied against ONE process-global counter shared by
# every endpoint, so a low-traffic, high-variance endpoint like /api/feed kept a
# handful of samples an hour — and those survivors were biased to whatever is
# most frequent, i.e. warm cache hits. The rail retained n=3 for /api/feed in an
# hour that contained four measured cold misses of 3.9–8.8 s, and captured none
# of them. An always-sample allowlist is the smallest change that makes the cold
# tail measurable; everything else keeps the global default.
_ALWAYS_SAMPLE = frozenset(
    p.strip()
    for p in os.getenv("LATENCY_ALWAYS_SAMPLE", "/api/feed").split(",")
    if p.strip()
)

# Rolling window: keep samples from the last hour.
WINDOW_SECONDS = 3600

# #1500: hard ceiling on members per endpoint, on top of the time window.
#
# Always-sampling /api/feed multiplies its sorted set by ~SAMPLE_RATE, and Redis
# here is Premium-0 / 50 MB / allkeys-lru — where an oversized working set evicts
# COLD keys regardless of TTL (r320 lost the grid-sentinel verdict exactly that
# way). The time window alone bounds nothing under a traffic spike, so the size
# is capped explicitly. 2000 samples is far above the n=100 that p99 needs and
# costs ~60 KB per endpoint, so the whole rail stays a rounding error against
# 50 MB.
MAX_SAMPLES_PER_ENDPOINT = int(os.getenv("LATENCY_MAX_SAMPLES", "2000"))

# #1459 (LAT-P011): the slow-event forensic ring.
#
# The sorted set above keeps `timestamp:latency:cache_bucket` for one hour — it
# can say /api/feed had a 13.6 s p100 and nothing about WHICH STAGE spent the
# time. So the tail had to be hunted by hand, and three consecutive queues
# hand-ran a spaced benchmark and measured three different spike rates (9%, 10%,
# then 0.3% over a full clock hour). At 0.3% you need thousands of hand-fired
# requests to collect the eight tail events the analysis needs.
#
# The attribution is already in the response: `X-Feed-Stages`. Recording the
# slow ones into a small capped list makes the tail a read instead of a stakeout.
SLOW_EVENT_MS = float(os.getenv("LATENCY_SLOW_EVENT_MS", "5000"))
SLOW_EVENT_MAX = int(os.getenv("LATENCY_SLOW_EVENT_MAX", "500"))
# Longer than the 1h percentile window on purpose: a tail event is rare, and the
# whole failure being fixed is that it aged out before anyone could read it
# (r330 watched a 19.7 s cold observation expire with nothing left to say it had
# existed). Bounded by SLOW_EVENT_MAX, so the TTL costs nothing extra.
SLOW_EVENT_TTL_SECONDS = int(os.getenv("LATENCY_SLOW_EVENT_TTL", str(7 * 24 * 3600)))
SLOW_EVENT_KEY = "latency:slow_events"

# #1917 (LAT-P070): the router-queue / app / DB split.
#
# `X-Feed-Stages` attributes /api/feed and nothing else, so every other endpoint's
# tail — /api/golf/tournaments/{slug}'s measured p90 15.260 s under load against a
# 2.451 s quiet baseline — could be seen but not attributed. LAT-P069 measured that
# BOTH terms of the requested split were unreachable: `X-Request-Start` had 0 hits
# in app/, and `debug_timing` 0 hits in routes/golf.py.
#
# Kill switch rather than a constant: this writes a response header on every /api
# request, and a rail with no off switch is one that gets reverted wholesale the
# first time it is suspected. Default ON — an instrument nobody enables measures
# nothing.
TIMING_SPLIT_ENABLED = os.getenv("TIMING_SPLIT_ENABLED", "1").strip().lower() not in {
    "0",
    "false",
    "no",
    "off",
}

# #1500: cache-status buckets recorded alongside each sample. Constrained to a
# fixed allowlist so the dimension can never grow unbounded — an unknown header
# value collapses to "other". Warm hits dominate the /api/feed population, so a
# single blended p95 cannot express the cold tail; the bucket is what makes the
# cold number measurable.
_CACHE_BUCKETS = frozenset({"miss", "hit", "stale_hit", "error"})
_BUCKET_OTHER = "other"
_BUCKET_NONE = "none"


def _cache_bucket(response) -> str:
    """Map the X-Feed-Cache response header onto a bounded bucket label."""
    try:
        raw = (response.headers.get("x-feed-cache") or "").strip().lower()
    except Exception:
        return _BUCKET_NONE
    if not raw:
        return _BUCKET_NONE
    return raw if raw in _CACHE_BUCKETS else _BUCKET_OTHER

# Regex patterns to normalize dynamic path segments to placeholders.
# Matches UUIDs and numeric IDs. Fallback only — see _endpoint_bucket, which
# prefers the route template the router actually matched.
_ID_PATTERNS = [
    (re.compile(r"/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"), "/{uuid}"),
    (re.compile(r"/\d+"), "/{id}"),
]

# #1500 (ops r329 finding B2): every request that matched NO route collapses
# into this one constant bucket.
#
# The middleware runs before routing, and the only path filter is the /api
# prefix check in dispatch(). So a 404 on any arbitrary `/api/<junk>` used to be
# recorded under its own key, and `latency:_endpoints` has no cap — any
# unauthenticated caller could mint unbounded Redis keys. Redis here is
# Premium-0 / 50 MB / allkeys-lru, where an oversized working set evicts COLD
# keys regardless of TTL (r320 lost the grid-sentinel verdict exactly that way),
# so the flood would take out the very samples this rail exists to keep.
#
# One constant bucket instead of dropping the sample outright: it is equally
# bounded (exactly one key, forever) and a 404 storm stays visible rather than
# becoming invisible to the only latency rail in production.
UNMATCHED_BUCKET = "/api/{unmatched}"

# #1500: per-endpoint counters. A single global counter meant a rare endpoint's
# sampling depended on unrelated traffic. Now bounded by the ROUTE TABLE rather
# than by whatever paths callers invent (r329 B2 flagged this same dict as
# unbounded per-dyno memory growth on attacker-controlled input); the cap below
# is belt-and-braces in case a future bucket source is less disciplined.
_request_counters: dict[str, int] = {}
_MAX_COUNTER_KEYS = 2000


def _endpoint_bucket(request, path: str) -> str:
    """The aggregation bucket for this request: the matched route template.

    ``request.scope["route"]`` is populated by the router during ``call_next``,
    so it is readable on the way OUT of the middleware even though the
    middleware itself runs before routing. Verified against Starlette's actual
    behaviour, not assumed:

    * ``/api/leagues/basketball_nba`` -> ``/api/leagues/{sport_key}``
    * ``/api/events/12345``           -> ``/api/events/{event_id}``
    * ``/api/total-junk-9x/aaa``      -> no route -> :data:`UNMATCHED_BUCKET`

    The template is what fixes B2: ``_normalize_path`` only collapses numeric
    IDs and UUIDs, so every route with a STRING path parameter
    (``/api/leagues/{sport_key}``, ``/api/hub/{competition}``,
    ``/api/teams/{identifier}``, ...) kept its raw value as its own bucket.

    Falls back to ``_normalize_path`` when the scope is not a real ASGI dict
    (test doubles), so callers that hand-build a request object still behave as
    they did before.
    """
    scope = getattr(request, "scope", None)
    if not isinstance(scope, dict):
        return _normalize_path(path)
    template = getattr(scope.get("route"), "path_format", None)
    if isinstance(template, str) and template:
        return template
    return UNMATCHED_BUCKET


def _should_sample(normalized: str) -> bool:
    """Per-endpoint 1-in-N sampling, with an always-sample allowlist."""
    if normalized in _ALWAYS_SAMPLE:
        return True
    if SAMPLE_RATE <= 1:
        return True
    count = _request_counters.get(normalized, 0) + 1
    if len(_request_counters) >= _MAX_COUNTER_KEYS and normalized not in _request_counters:
        # Bounded, and bounded in the direction that keeps the rail honest: drop
        # the counter state rather than the sample. Sampling is a 1-in-N phase,
        # so a reset costs at most one endpoint's phase alignment; unbounded
        # growth would cost dyno memory permanently.
        _request_counters.clear()
    _request_counters[normalized] = count
    return count % SAMPLE_RATE == 0

# #1197: cache the sync client. A fresh get_redis_client() per sampled request
# spins up a NEW connection pool that is never closed — abandoned pools cycle
# connections through Heroku Redis's idle-reap window and feed the TLS-handshake
# churn. One shared, bounded, retry-wrapped client for the whole process instead.
_latency_redis = None


def _normalize_path(path: str) -> str:
    """Collapse IDs/UUIDs in a URL path so per-endpoint aggregation works.

    Examples:
        /api/events/12345          -> /api/events/{id}
        /api/events/12345/history  -> /api/events/{id}/history
        /api/feed                  -> /api/feed
    """
    for pattern, replacement in _ID_PATTERNS:
        path = pattern.sub(replacement, path)
    return path


def _get_redis():
    """Lazy import + cached client to avoid import-time + per-request pools."""
    global _latency_redis
    if _latency_redis is not None:
        return _latency_redis
    try:
        from app.tasks.redis_state import get_redis_client
        # #1197 (r259): this write is on the hot request path (sampled, but blocks
        # the sampled response). Use a fast-fail, tightly-bounded client so a
        # churning TLS connection can add at most a fraction of a second to a
        # sampled request instead of the full 3×1s background retry budget.
        _latency_redis = get_redis_client(socket_timeout=0.5, fast_fail=True)
        return _latency_redis
    except Exception:
        return None


async def _record_slow_event(
    normalized: str,
    duration_ms: float,
    cache_bucket: str,
    response,
    rss_mb: Optional[float] = None,
    split: Optional[dict] = None,
) -> None:
    """Append one tail observation to the bounded slow-event ring (#1459).

    Same discipline as the sampled write below it: fast-fail client, the
    blocking round-trip pushed off the event loop under a hard timeout, and a
    bare ``except`` so observability can never fail a user's request.
    """
    try:
        from app.utils.latency_stats import build_slow_event

        try:
            stages = response.headers.get("x-feed-stages")
        except Exception:
            stages = None

        r = _get_redis()
        if r is None:
            return

        member = build_slow_event(
            timestamp=time.time(),
            path=normalized,
            duration_ms=duration_ms,
            cache_bucket=cache_bucket,
            stages=stages,
            rss_mb=rss_mb,
            split=split,
        )
        pipe = r.pipeline(transaction=False)
        # LPUSH + LTRIM(0, MAX-1) keeps the ring newest-first and capped, so a
        # sustained outage cannot grow the key without bound.
        pipe.lpush(SLOW_EVENT_KEY, member)
        pipe.ltrim(SLOW_EVENT_KEY, 0, SLOW_EVENT_MAX - 1)
        pipe.expire(SLOW_EVENT_KEY, SLOW_EVENT_TTL_SECONDS)
        await asyncio.wait_for(asyncio.to_thread(pipe.execute), timeout=0.6)
    except Exception:
        logger.debug("Slow-event record failed", exc_info=True)


class LatencyMiddleware(BaseHTTPMiddleware):
    """Records sampled request latencies into Redis sorted sets."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        path = request.url.path

        # Skip non-API and admin paths.
        if path == "/" or not path.startswith("/api") or "/admin" in path:
            return await call_next(request)

        # #1917 (LAT-P070): the router-queue term is read HERE, at the moment the
        # dyno first has the request — not after call_next. Reading it later would
        # fold the app's own service time into "queue time", which is the exact
        # mis-attribution the probe exists to rule out.
        db_token = None
        router_ms: Optional[float] = None
        if TIMING_SPLIT_ENABLED:
            try:
                from app.utils.request_timing import begin_db_timing, router_queue_ms

                router_ms = router_queue_ms(request.headers.get(REQUEST_START_HEADER))
                db_token = begin_db_timing()
            except Exception:
                logger.debug("Timing split setup failed", exc_info=True)

        start = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            db_snapshot = None
            if db_token is not None:
                try:
                    from app.utils.request_timing import current_db_timing, end_db_timing

                    db_snapshot = current_db_timing()
                    end_db_timing(db_token)
                except Exception:
                    logger.debug("Timing split teardown failed", exc_info=True)
        duration_ms = (time.perf_counter() - start) * 1000

        # Build the split and publish it on the response. Wrapped whole: an
        # observability rail must never be the reason a request fails.
        split: Optional[dict] = None
        if TIMING_SPLIT_ENABLED:
            try:
                from app.utils.request_timing import (
                    SPLIT_HEADER,
                    build_split,
                    format_split_header,
                )

                split = build_split(
                    wall_ms=duration_ms, db=db_snapshot, router_ms=router_ms
                )
                response.headers[SPLIT_HEADER] = format_split_header(split)
            except Exception:
                logger.debug("Timing split emit failed", exc_info=True)

        # Log memory for slow requests to diagnose OOM crashes (#809)
        rss_mb: Optional[float] = None
        if duration_ms > 5000:
            try:
                import resource
                rss_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024 * 1024)
                logger.warning(
                    "Slow request: %s %.0fms RSS=%.0fMB",
                    path[:60], duration_ms, rss_mb,
                )
            except Exception:
                pass

        # Bucket by the route template the router actually matched, so the key
        # space is bounded by the route table instead of by caller input
        # (#1500 / r329 B2). Read AFTER call_next — that is when scope["route"]
        # exists.
        normalized = _endpoint_bucket(request, path)

        # #1459: record the tail BEFORE the sampling gate. A slow request on a
        # 1-in-10 endpoint is precisely the observation worth keeping, and
        # gating it behind sampling would throw away 9 of every 10 of them.
        if duration_ms >= SLOW_EVENT_MS:
            await _record_slow_event(
                normalized, duration_ms, _cache_bucket(response), response, rss_mb, split
            )

        # Sampling: per-endpoint 1-in-N, with an always-sample allowlist (#1500).
        if not _should_sample(normalized):
            return response

        # Fire-and-forget write to Redis. Never let tracking break a request.
        try:
            now = time.time()
            key = f"latency:{normalized}"

            r = _get_redis()
            if r is None:
                return response

            pipe = r.pipeline(transaction=False)
            # Store timestamp as score (for window trimming), latency + cache
            # bucket in the member. #1500: the bucket rides the EXISTING sorted
            # set rather than adding a key family — Redis is Premium-0/50MB with
            # allkeys-lru, so widening a member is strictly cheaper than new
            # keys. Readers must tolerate the legacy 2-field form.
            member = f"{now}:{duration_ms:.1f}:{_cache_bucket(response)}"
            pipe.zadd(key, {member: now})
            # Trim entries older than the window.
            pipe.zremrangebyscore(key, "-inf", now - WINDOW_SECONDS)
            # ...and cap the member count so a traffic spike on an
            # always-sampled endpoint cannot grow the working set (#1500).
            # Rank 0 is the oldest (score = timestamp), so this drops the
            # oldest overflow and keeps the most recent window.
            pipe.zremrangebyrank(key, 0, -(MAX_SAMPLES_PER_ENDPOINT + 1))
            # Set TTL so keys self-clean if traffic stops.
            pipe.expire(key, WINDOW_SECONDS + 60)
            # Track this endpoint in the master set.
            pipe.sadd("latency:_endpoints", normalized)
            pipe.expire("latency:_endpoints", WINDOW_SECONDS + 60)
            # #1197 (r259): pipe.execute() is a blocking Redis round-trip. Run it in
            # a worker thread with a hard timeout so a churning Redis connection can
            # never block the asyncio event loop (which would stall EVERY concurrent
            # request) on the 1/10 sampled request.
            await asyncio.wait_for(asyncio.to_thread(pipe.execute), timeout=0.6)
        except Exception:
            # Never fail a request because of latency tracking.
            logger.debug("Latency tracking write failed", exc_info=True)

        return response
