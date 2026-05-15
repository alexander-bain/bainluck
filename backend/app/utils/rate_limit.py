"""
Rate limiting for public API endpoints.

Uses the ``limits`` library (Redis-backed in production, in-memory in dev)
to enforce per-IP and per-user rate limits as ASGI middleware.

Rate limits:
  - Anonymous:      60 requests / minute  (keyed by client IP)
  - Authenticated: 120 requests / minute  (keyed by user UID from JWT)
  - Admin:         exempt (already gated by _check_admin_secret)
  - Docs/health:   exempt

Redis is shared with Celery (same REDIS_URL env var on Heroku).
"""

from __future__ import annotations

import base64
import json
import logging
import os
import time
from typing import Optional

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Rate limit constants
# ---------------------------------------------------------------------------
ANON_RATE_LIMIT = "60/minute"
AUTH_RATE_LIMIT = "120/minute"

# Disable rate limiting entirely in test/CI environments
_DISABLED = bool(os.getenv("TESTING") or os.getenv("CI") or os.getenv("GITHUB_ACTIONS"))

# Paths exempt from rate limiting
_EXEMPT_PREFIXES = (
    "/api/admin",
    "/docs",
    "/openapi.json",
    "/redoc",
    "/health",
)


# ---------------------------------------------------------------------------
# Storage + strategy (lazy singletons)
# ---------------------------------------------------------------------------
_rate_limiter = None


def _get_rate_limiter():
    """Return a FixedWindowRateLimiter backed by Redis (prod) or memory (dev)."""
    global _rate_limiter
    if _rate_limiter is not None:
        return _rate_limiter

    from limits.storage import storage_from_string
    from limits.strategies import FixedWindowRateLimiter

    redis_url = os.getenv("REDIS_URL") or os.getenv("REDIS_TLS_URL")
    storage = None

    if redis_url:
        try:
            if redis_url.startswith("rediss://"):
                storage = storage_from_string(
                    redis_url, ssl_cert_reqs="CERT_NONE"
                )
            else:
                storage = storage_from_string(redis_url)
            logger.info("Rate limiter using Redis storage")
        except Exception:
            logger.warning(
                "Failed to connect to Redis for rate limiting; "
                "falling back to memory"
            )

    if storage is None:
        storage = storage_from_string("memory://")
        logger.info("Rate limiter using in-memory storage")

    _rate_limiter = FixedWindowRateLimiter(storage)
    return _rate_limiter


# ---------------------------------------------------------------------------
# Parsed limit objects (lazy singletons)
# ---------------------------------------------------------------------------
_anon_limit = None
_auth_limit = None


def _get_limits():
    """Parse limit strings once and cache."""
    global _anon_limit, _auth_limit
    if _anon_limit is not None:
        return _anon_limit, _auth_limit

    from limits import parse as parse_limit

    _anon_limit = parse_limit(ANON_RATE_LIMIT)
    _auth_limit = parse_limit(AUTH_RATE_LIMIT)
    return _anon_limit, _auth_limit


# ---------------------------------------------------------------------------
# Key extraction helpers
# ---------------------------------------------------------------------------

def _get_client_ip(request: Request) -> str:
    """Extract the real client IP, respecting X-Forwarded-For (Heroku)."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def _extract_uid_from_token(token: str) -> Optional[str]:
    """
    Decode JWT payload to extract 'uid' or 'sub' without verification.

    Safe for rate-limit keying: we only use this as a bucket key, not for
    authorization.  Full token verification still happens in the auth
    dependency layer.
    """
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        payload_b64 = parts[1]
        # Pad to multiple of 4
        padding = 4 - len(payload_b64) % 4
        if padding != 4:
            payload_b64 += "=" * padding
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        return payload.get("uid") or payload.get("sub")
    except Exception:
        return None


def _is_exempt(path: str) -> bool:
    """Return True if the path should skip rate limiting."""
    if os.getenv("BYPASS_RATE_LIMITS") == "1":
        return True

    for prefix in _EXEMPT_PREFIXES:
        if path.startswith(prefix):
            return True
    return False


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    ASGI middleware that enforces per-IP / per-user rate limits.

    - Anonymous requests: 60/minute keyed by client IP
    - Authenticated requests (Bearer JWT): 120/minute keyed by user UID
    - Admin / docs / health paths: exempt

    Returns 429 with Retry-After header when limit is exceeded.
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        path = request.url.path

        # Skip exempt paths
        if _is_exempt(path):
            return await call_next(request)

        # Determine key and limit
        auth_header = request.headers.get("authorization", "")
        uid = None
        if auth_header.lower().startswith("bearer "):
            uid = _extract_uid_from_token(auth_header[7:].strip())

        anon_limit, auth_limit = _get_limits()

        if uid:
            key = f"user:{uid}"
            limit = auth_limit
        else:
            key = _get_client_ip(request)
            limit = anon_limit

        # Check rate limit
        try:
            rl = _get_rate_limiter()
            if not rl.hit(limit, "rate_limit", key):
                # Limit exceeded — compute seconds until window resets
                stats = rl.get_window_stats(limit, "rate_limit", key)
                retry_after = max(1, int(stats.reset_time - time.time()))
                return JSONResponse(
                    status_code=429,
                    content={
                        "detail": f"Rate limit exceeded: {limit}",
                        "retry_after": retry_after,
                    },
                    headers={"Retry-After": str(retry_after)},
                )
        except Exception:
            # If Redis is down, allow the request through rather than
            # blocking all traffic.  Log for observability.
            logger.exception("Rate limit check failed — allowing request")

        return await call_next(request)
