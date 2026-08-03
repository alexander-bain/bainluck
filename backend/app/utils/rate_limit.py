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

import asyncio
import base64
import json
import logging
import os
import ssl
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

# #1197 (r259): hard wall-clock bound on the async rate-limit Redis check. Because
# the check is awaited (not a sync blocking call), wait_for genuinely cancels the
# redis op at this deadline, so a churning connection can add at most this much to
# a request; on a breach we fail open. Well under the 2s team-route bar.
_RL_CHECK_TIMEOUT = 0.6

# Fixed-window parameters for the async-redis hot path (mirrors ANON/AUTH above).
_RL_WINDOW_SECONDS = 60
_ANON_MAX = 60
_AUTH_MAX = 120

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
            # #1197 (r246 option a): the rate-limiter was the one Redis client that
            # bypassed the keepalive/health-check hardening applied everywhere else
            # (the `limits` lib passes these kwargs through to the redis client), so
            # its idle connections were prime candidates for the TLS handshake churn.
            from app.tasks.config import socket_keepalive_options
            from app.tasks.redis_state import (
                _redis_fast_fail_retry,
                _redis_retry_on_errors,
                _REDIS_MAX_CONNECTIONS,
            )

            _stability = {
                "socket_keepalive": True,
                "health_check_interval": 25,
                "socket_connect_timeout": 2,
                # #1197 (r259): LATENCY IS THE GATE for the team route (Priority #3).
                # The rate-limiter runs on EVERY non-exempt request (team pages are
                # not exempt), so its Redis op is on the hot request path. Bound the
                # blocking op with a small socket_timeout and a fast-fail retry
                # (1 retry, ~0.1s cap) so a churning TLS connection degrades to
                # fail-open in well under a second instead of spending the full
                # 3×1s background retry budget (× two ops on the 429 path) — the
                # cause of the 7-17.6s warm team-route latency. On a Redis blip the
                # dispatch() except-clause fails OPEN (allows the request), so a
                # tight timeout trades a rare un-counted request for a fast page.
                "socket_timeout": 0.5,
                "retry_on_timeout": True,
                # #1197: retry the TLS-handshake ConnectionError (the lever the
                # keepalive-only hardening lacked) + bound the pool. The `limits`
                # lib passes these kwargs straight through to the redis client.
                "retry": _redis_fast_fail_retry(),
                "retry_on_error": _redis_retry_on_errors(),
                "max_connections": _REDIS_MAX_CONNECTIONS,
            }
            _ka = socket_keepalive_options()
            if _ka:
                _stability["socket_keepalive_options"] = _ka
            if redis_url.startswith("rediss://"):
                storage = storage_from_string(
                    redis_url, ssl_cert_reqs=ssl.CERT_NONE, **_stability
                )
            else:
                storage = storage_from_string(redis_url, **_stability)
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
# Async-redis hot path (#1197 r259)
# ---------------------------------------------------------------------------
# The prod rate-limit check runs on our proven async redis client (cancellable by
# asyncio.wait_for, honors the bounded-client hardening) with an inline fixed-window
# counter — NOT the sync `limits` limiter, whose blocking hit() on the event loop
# turned one slow Redis op into site-wide 7-17.6s stalls. The sync `limits` limiter
# above is kept ONLY as the in-memory dev/CI fallback (no REDIS_URL).
_async_rl_redis = None
_async_rl_unavailable = False


def _get_async_rl_redis():
    """Cached async redis client for the rate-limit hot path, or None when no
    REDIS_URL (dev/CI → memory fallback)."""
    global _async_rl_redis, _async_rl_unavailable
    if _async_rl_redis is not None:
        return _async_rl_redis
    if _async_rl_unavailable:
        return None
    if not (os.getenv("REDIS_URL") or os.getenv("REDIS_TLS_URL")):
        _async_rl_unavailable = True
        return None
    try:
        from app.tasks.redis_state import get_async_redis_client
        _async_rl_redis = get_async_redis_client()
        return _async_rl_redis
    except Exception:
        _async_rl_unavailable = True
        return None


async def _redis_fixed_window_hit(redis_cli, key: str, now: int) -> int:
    """INCR the current window bucket and set its TTL on first hit. Returns the
    running count. Cancellable — the caller wraps it in asyncio.wait_for."""
    bucket = now // _RL_WINDOW_SECONDS
    rkey = f"rl:{key}:{bucket}"
    count = await redis_cli.incr(rkey)
    if count == 1:
        await redis_cli.expire(rkey, _RL_WINDOW_SECONDS + 5)
    return int(count)


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
    Decode JWT payload to extract 'uid' or 'sub' WITHOUT verifying the signature.

    LEGACY / UNSAFE for bucketing. Retained only as the target of the narrow
    revert path (RATE_LIMIT_TRUST_UNVERIFIED_TOKENS=1). Do NOT use this to select
    a rate-limit bucket key: an unverified payload lets a forged token with a
    rotating uid mint unlimited authenticated buckets (Queue 303 / C134
    UNVERIFIED_IDENTITY_RATE_BYPASS). Route bucketing through
    ``_resolve_trusted_uid`` instead.
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


# ---------------------------------------------------------------------------
# Trusted identity resolution (Queue 303 — stop forged-token bucket bypass)
# ---------------------------------------------------------------------------
# SECURITY: the authenticated (larger) rate-limit bucket must key ONLY on a uid
# whose token we have actually verified. The old path decoded the JWT payload
# WITHOUT checking the signature, so any forged three-part token supplying a
# rotating `uid`/`sub` minted an unlimited supply of 120/min authenticated
# buckets and escaped the anonymous per-IP fixed window entirely.
#
# Constraints (why this is deliberately minimal):
#   * The resolver runs on EVERY non-exempt request. It MUST be cheap and do NO
#     network I/O — the #1197 scar is that a blocking op in this middleware
#     stalls the whole event loop. So the default authority verifies only what
#     can be checked locally: backend-issued session tokens (HS256, no network).
#   * At middleware admission there is no already-verified request authority
#     (route auth dependencies run later). Tokens we cannot cheaply prove —
#     Firebase ID tokens and any forged/expired/wrong-issuer token — resolve to
#     None and fall to the anonymous IP bucket. The route's own auth dependency
#     still verifies and authorizes them normally; only the bucket choice changes.
#   * Injectable so tests supply a local fake authority (no network) and a future
#     cheap-local verifier can drop in without touching the hot path.
_trusted_uid_resolver = None


def _default_trusted_uid(token: str) -> Optional[str]:
    """Return a VERIFIED uid for a bearer token using only local (no-network)
    verification, or None when the token cannot be cheaply trusted.

    Verifies backend-issued session tokens (HS256 signature + iss + exp) via
    ``verify_session_token``. Firebase ID tokens and forged/invalid tokens are
    not trusted here (they are still authorized normally by the route's auth
    dependency) and return None so the request keys by IP.
    """
    try:
        from app.services.firebase_auth import verify_session_token

        claims = verify_session_token(token)
        if claims:
            return claims.get("uid") or claims.get("sub")
    except Exception:
        return None
    return None


def set_trusted_uid_resolver(resolver) -> None:
    """Override the trusted-uid resolver. For tests (local fake authority) and
    future local verifiers. Pass None to restore the default."""
    global _trusted_uid_resolver
    _trusted_uid_resolver = resolver


def _resolve_trusted_uid(token: str) -> Optional[str]:
    """Resolve a bearer token to a trusted uid for bucket keying, or None.

    Narrow revert path: RATE_LIMIT_TRUST_UNVERIFIED_TOKENS=1 restores the legacy
    unverified-decode behavior without a redeploy. Emergency use only — it
    re-opens the forgeable-bucket bypass this fix closes.
    """
    if os.getenv("RATE_LIMIT_TRUST_UNVERIFIED_TOKENS") == "1":
        return _extract_uid_from_token(token)
    resolver = _trusted_uid_resolver or _default_trusted_uid
    return resolver(token)


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
            # SECURITY (Queue 303): key the authenticated bucket ONLY on a uid we
            # have actually verified. A forged/unverified token resolves to None
            # and keys by IP, so it cannot select a user bucket or the larger
            # limit — nor rotate uids to mint unlimited buckets.
            uid = _resolve_trusted_uid(auth_header[7:].strip())

        if uid:
            key = f"user:{uid}"
            max_requests = _AUTH_MAX
        else:
            key = _get_client_ip(request)
            max_requests = _ANON_MAX

        # Check rate limit.
        #
        # #1197 (r259 ROOT CAUSE): the sync `limits` FixedWindowRateLimiter.hit() is
        # a BLOCKING Redis round-trip. Called on the asyncio event loop, one slow
        # hit() (Heroku Redis TLS churn) blocked the ENTIRE loop and stalled every
        # concurrent request — why warm non-exempt routes measured 7-17.6s while
        # exempt routes stayed sub-300ms. Fix: in prod run an inline fixed-window
        # counter on our async redis client and hard-bound it with wait_for; because
        # the op is AWAITED (not a blocked thread), wait_for genuinely cancels it at
        # the deadline. On timeout / any error we FAIL OPEN — a rare un-counted
        # request is the right trade for keeping the site fast under a Redis blip.
        redis_cli = _get_async_rl_redis()
        if redis_cli is not None:
            try:
                now = int(time.time())
                count = await asyncio.wait_for(
                    _redis_fixed_window_hit(redis_cli, key, now),
                    timeout=_RL_CHECK_TIMEOUT,
                )
                if count > max_requests:
                    retry_after = max(1, _RL_WINDOW_SECONDS - (now % _RL_WINDOW_SECONDS))
                    return JSONResponse(
                        status_code=429,
                        content={
                            "detail": f"Rate limit exceeded: {max_requests}/minute",
                            "retry_after": retry_after,
                        },
                        headers={"Retry-After": str(retry_after)},
                    )
            except Exception:
                # Redis down / slow / timed-out — allow the request through rather
                # than blocking traffic (a ConnectionError here is dropped from
                # Sentry by main.before_send; a timeout is the intended fail-open).
                logger.warning("Rate limit check failed/timed out — allowing request")
            return await call_next(request)

        # Dev/CI fallback (no REDIS_URL): the in-memory sync limiter is fast and
        # non-blocking (no network), so calling it directly is fine here.
        anon_limit, auth_limit = _get_limits()
        limit = auth_limit if uid else anon_limit
        try:
            rl = _get_rate_limiter()
            if not rl.hit(limit, "rate_limit", key):
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
            logger.warning("Rate limit check failed — allowing request")

        return await call_next(request)
