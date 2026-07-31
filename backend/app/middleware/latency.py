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

# Paths to skip entirely (health checks, docs, static).
_SKIP_PREFIXES = ("/docs", "/openapi.json", "/redoc", "/health", "/")

# Regex patterns to normalize dynamic path segments to placeholders.
# Matches UUIDs, numeric IDs, and sport keys like "basketball_nba".
_ID_PATTERNS = [
    (re.compile(r"/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"), "/{uuid}"),
    (re.compile(r"/\d+"), "/{id}"),
]

# #1500: per-endpoint counters. A single global counter meant a rare endpoint's
# sampling depended on unrelated traffic. Bounded by the normalized-path space,
# which is already bounded by the route table (IDs are collapsed by
# _normalize_path before they get here).
_request_counters: dict[str, int] = {}


def _should_sample(normalized: str) -> bool:
    """Per-endpoint 1-in-N sampling, with an always-sample allowlist."""
    if normalized in _ALWAYS_SAMPLE:
        return True
    if SAMPLE_RATE <= 1:
        return True
    count = _request_counters.get(normalized, 0) + 1
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


class LatencyMiddleware(BaseHTTPMiddleware):
    """Records sampled request latencies into Redis sorted sets."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        path = request.url.path

        # Skip non-API and admin paths.
        if path == "/" or not path.startswith("/api") or "/admin" in path:
            return await call_next(request)

        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - start) * 1000

        # Log memory for slow requests to diagnose OOM crashes (#809)
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

        # Sampling: per-endpoint 1-in-N, with an always-sample allowlist (#1500).
        normalized = _normalize_path(path)
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
