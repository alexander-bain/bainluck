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
    """Lazy import to avoid import-time Redis connection."""
    try:
        from app.tasks.redis_state import get_redis_client
        return get_redis_client()
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
            pipe.execute()
        except Exception:
            # Never fail a request because of latency tracking.
            logger.debug("Latency tracking write failed", exc_info=True)

        return response
