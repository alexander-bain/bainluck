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

# Rolling window: keep samples from the last hour.
WINDOW_SECONDS = 3600

# Paths to skip entirely (health checks, docs, static).
_SKIP_PREFIXES = ("/docs", "/openapi.json", "/redoc", "/health", "/")

# Regex patterns to normalize dynamic path segments to placeholders.
# Matches UUIDs, numeric IDs, and sport keys like "basketball_nba".
_ID_PATTERNS = [
    (re.compile(r"/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"), "/{uuid}"),
    (re.compile(r"/\d+"), "/{id}"),
]

_request_counter = 0

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
        global _request_counter

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

        # Sampling: only record every Nth request.
        _request_counter += 1
        if _request_counter % SAMPLE_RATE != 0:
            return response

        # Fire-and-forget write to Redis. Never let tracking break a request.
        try:
            normalized = _normalize_path(path)
            now = time.time()
            key = f"latency:{normalized}"

            r = _get_redis()
            if r is None:
                return response

            pipe = r.pipeline(transaction=False)
            # Store timestamp as score (for window trimming), latency in member.
            member = f"{now}:{duration_ms:.1f}"
            pipe.zadd(key, {member: now})
            # Trim entries older than the window.
            pipe.zremrangebyscore(key, "-inf", now - WINDOW_SECONDS)
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
