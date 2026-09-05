"""
Rate limiting for public API endpoints.

Uses the ``limits`` library (Redis-backed in production, in-memory in dev)
to enforce per-IP and per-user rate limits as ASGI middleware.

Rate limits:
  - Anonymous:      60 requests / minute  (keyed by client IP)
  - Authenticated: 120 requests / minute  (keyed by user UID from JWT)
  - Admin:         300 requests / minute  (keyed by a HASH of the admin bearer
                   token) — a CEILING, never an exemption. See Queue 315 Item 1.
  - Trusted addr:  600 requests / minute  (opt-in via ``RATE_LIMIT_TRUSTED_IPS``,
                   matched against the address our ROUTER saw, not the one the
                   caller claimed) — also a ceiling, never an exemption. D70.
  - Docs/health:   exempt

Redis is shared with Celery (same REDIS_URL env var on Heroku).
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
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
# Queue 315 Item 1: /api/admin is rate limited, not exempt. This is ONE SHARED
# BUCKET per token value (P3) — Alex's browser, every agent lane, `/health`, the
# browser-audit rail and flow_sentinel's nightly self-calls all present the same
# ADMIN_TOKEN and therefore collide in it. The ceiling is sized against the SUM of
# concurrent callers, not the max of any one; see the census in the queue report.
ADMIN_RATE_LIMIT = "300/minute"
# D70 = A (Alex's recorded default, 2026-09-05; issue #3297). Every working window
# on our own Mac — plus the `look.sh` screenshot browser each of them drives — exits
# through ONE public address and shares the single 60/min anonymous bucket. They
# spend it continuously, so Alex's own browser asking for `/api/calibration` from
# that machine is turned away and the page renders "Failed to load calibration
# data". The site is healthy; we are throttling ourselves. Worse, every surface
# shows the same generic failure text, so a window taking a LOOK screenshot cannot
# tell "we throttled ourselves" from "the page is genuinely broken" — which is a
# hole in the way we check our own work, not just an annoyance.
#
# CEILING, NEVER EXEMPTION — the same rule Queue 315 Item 1 wrote above for admin,
# and for the same reason. An exemption would make this allowlist worth forging;
# a ceiling bounds what forging it can buy. See `_router_peer_ip` for why a
# forged header cannot claim it in the first place.
TRUSTED_RATE_LIMIT = "600/minute"

# #1197 (r259): hard wall-clock bound on the async rate-limit Redis check. Because
# the check is awaited (not a sync blocking call), wait_for genuinely cancels the
# redis op at this deadline, so a churning connection can add at most this much to
# a request; on a breach we fail open. Well under the 2s team-route bar.
_RL_CHECK_TIMEOUT = 0.6

# Fixed-window parameters for the async-redis hot path (mirrors ANON/AUTH above).
_RL_WINDOW_SECONDS = 60
_ANON_MAX = 60
_AUTH_MAX = 120
_ADMIN_MAX = 300
_TRUSTED_MAX = 600

# Admin paths get a ceiling instead of the old blanket exemption (Queue 315).
_ADMIN_PATH_PREFIX = "/api/admin"

# Paths exempt from rate limiting.
#
# SECURITY (Queue 315 Item 1): "/api/admin" WAS in this tuple. It is deliberately
# gone. The old docstring justified it as "already gated by _check_admin_secret",
# but an auth gate bounds WHO may call, never HOW OFTEN — so a leaked token bought
# unmetered access to every admin read, including `db-query`. Admin requests now
# fall through to the admin bucket below. Ceiling, never exemption: if the caller
# census outgrows 300/min, RAISE `_ADMIN_MAX` — do not re-add the prefix here.
_EXEMPT_PREFIXES = (
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


_admin_limit = None
_trusted_limit = None


def _get_limits():
    """Parse limit strings once and cache."""
    global _anon_limit, _auth_limit, _admin_limit, _trusted_limit
    if _anon_limit is not None:
        return _anon_limit, _auth_limit

    from limits import parse as parse_limit

    _anon_limit = parse_limit(ANON_RATE_LIMIT)
    _auth_limit = parse_limit(AUTH_RATE_LIMIT)
    _admin_limit = parse_limit(ADMIN_RATE_LIMIT)
    _trusted_limit = parse_limit(TRUSTED_RATE_LIMIT)
    return _anon_limit, _auth_limit


def _get_admin_limit():
    """Parsed admin limit for the dev/CI in-memory fallback path."""
    if _admin_limit is None:
        _get_limits()
    return _admin_limit


def _get_trusted_limit():
    """Parsed trusted-address limit for the dev/CI in-memory fallback path."""
    if _trusted_limit is None:
        _get_limits()
    return _trusted_limit


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


def _router_peer_ip(request: Request) -> str:
    """The address our own infrastructure observed, i.e. the LAST X-Forwarded-For
    entry — NOT the first one ``_get_client_ip`` returns.

    🔴 THE TWO ARE DIFFERENT ON PURPOSE AND ONLY THIS ONE MAY GATE A PRIVILEGE.
    Heroku's router APPENDS the connecting peer to whatever ``X-Forwarded-For``
    arrived, so on a request that ships its own header position 0 is the value the
    CALLER chose and position -1 is the value our router wrote. ``_get_client_ip``
    reads position 0, which is correct for the anonymous bucket (a bucket key is
    not a privilege — the worst a forger does there is pick which bucket to spend)
    and would be a total bypass here: an allowlist keyed on caller-supplied bytes
    is an allowlist for the entire internet. Measured 2026-09-05 against
    production: ``curl -H 'X-Forwarded-For: 203.0.113.77' $BAINLUCK_API/api/health``
    answers 200 from an address that was being 429'd, so position 0 is definitely
    caller-controlled and definitely honoured.

    HOLDS EVEN IF THAT APPEND BEHAVIOUR IS WRONG. If some proxy ever forwards the
    header untouched, first == last and a forged value could claim the ceiling —
    which is exactly why the grant is a CEILING (600/min) and not an exemption.
    The bounded downside of being wrong is a stranger getting 600/min instead of
    60; the pre-existing bucket-rotation bypass in #3297 is already strictly worse
    than that, and closing it is that issue's job, not this one's.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        parts = [p.strip() for p in forwarded.split(",") if p.strip()]
        if parts:
            return parts[-1]
    if request.client:
        return request.client.host
    return "unknown"


#: Parsed ``RATE_LIMIT_TRUSTED_IPS``, cached against the raw env string so a
#: changed value is picked up without a restart (and so tests can set it) while a
#: steady one costs a single ``getenv`` on the hot path rather than a re-split.
_trusted_ip_cache: tuple = ("", frozenset())


def _trusted_ips() -> frozenset:
    """Addresses granted the trusted CEILING, from ``RATE_LIMIT_TRUSTED_IPS``.

    Config-driven and therefore reversible without a deploy: unset the var and the
    ceiling is gone on the next dyno cycle. Empty/unset — the default, and the
    state this ships in — means nothing changes for anyone.

    Deliberately NOT checked into the repo: the value is a home IP address, and
    tracked files carry no operator identifiers (the credential rule's reasoning
    applies to anything that identifies Alex's network, not only to secrets).
    """
    global _trusted_ip_cache
    raw = os.getenv("RATE_LIMIT_TRUSTED_IPS") or ""
    cached_raw, cached = _trusted_ip_cache
    if raw != cached_raw:
        cached = frozenset(p.strip() for p in raw.split(",") if p.strip())
        _trusted_ip_cache = (raw, cached)
    return cached


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


# ---------------------------------------------------------------------------
# Admin bucket keying (Queue 315 Item 1)
# ---------------------------------------------------------------------------

def _admin_bucket_key(token: str) -> Optional[str]:
    """Return the admin rate-limit bucket key for a bearer token, or None.

    Returns a key ONLY when the presented token is the real ``ADMIN_TOKEN``.
    Two properties this shape buys, both of them load-bearing:

    1. **The key is a HASH, never the token.** ``rl:`` keys live in plaintext in
       the Redis keyspace and surface in ``SCAN`` output and in anything that
       dumps keys, so keying on the raw secret would copy the live admin
       credential into an unencrypted store — writing the credential down in the
       one place we monitor least, in order to protect it.

    2. **A non-matching token gets NO admin bucket.** It falls through to the
       normal uid/IP keying instead. Keying every presented bearer by its own
       hash would hand an attacker the Queue 303 bypass in a new coat: rotate the
       token value, mint a fresh 300/min bucket, repeat forever. Only a token
       that already equals the secret can select the larger bucket, and a caller
       holding that token can do far worse than spend requests.

    The comparison is constant-time and does no I/O — this runs on every request
    to an admin path, and the #1197 scar is that any blocking op in this
    middleware stalls the whole event loop.
    """
    expected = os.getenv("ADMIN_TOKEN") or os.getenv("ADMIN_SECRET")
    if not expected or not token:
        return None
    if not hmac.compare_digest(token, expected):
        return None
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()[:16]
    return f"admin:{digest}"


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
    - Admin paths with the admin token: 300/minute keyed by a hash of that token
    - Addresses in ``RATE_LIMIT_TRUSTED_IPS``: 600/minute, keyed separately (D70)
    - Docs / health paths: exempt

    Precedence is admin > trusted address > user > anonymous IP.

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
        bearer = (
            auth_header[7:].strip()
            if auth_header.lower().startswith("bearer ")
            else ""
        )

        # Queue 315 Item 1: admin paths get their own (larger) bucket keyed on a
        # hash of the admin token. Checked BEFORE the uid path because an admin
        # calling with a verified session token would otherwise land in the
        # 120/min user bucket and be throttled well below the intended ceiling.
        admin_key = (
            _admin_bucket_key(bearer)
            if bearer and path.startswith(_ADMIN_PATH_PREFIX)
            else None
        )

        uid = None
        if bearer and admin_key is None:
            # SECURITY (Queue 303): key the authenticated bucket ONLY on a uid we
            # have actually verified. A forged/unverified token resolves to None
            # and keys by IP, so it cannot select a user bucket or the larger
            # limit — nor rotate uids to mint unlimited buckets.
            uid = _resolve_trusted_uid(bearer)

        # D70: a trusted address outranks the per-user bucket deliberately. The
        # thing being trusted is the MACHINE, and the whole defect is that many
        # windows — signed in, signed out, and a headless screenshot browser that
        # has no identity at all — share its one address. Bucketing them per-uid
        # would leave the anonymous ones back in the 60/min bucket they exhausted.
        # Admin still wins, so an admin call is metered by its own ceiling.
        trusted_peer = None
        if not admin_key:
            allowlist = _trusted_ips()
            if allowlist:
                peer = _router_peer_ip(request)
                if peer in allowlist:
                    trusted_peer = peer

        if admin_key:
            key = admin_key
            max_requests = _ADMIN_MAX
        elif trusted_peer:
            # A DISTINCT key, not the anonymous one. If the append assumption in
            # `_router_peer_ip` ever fails, a forger who claims this address lands
            # in the anonymous `peer` bucket and cannot spend the trusted one — so
            # the failure mode is a stranger with 600/min, never a denial of
            # service against the machine we are trying to unblock.
            key = f"trusted:{trusted_peer}"
            max_requests = _TRUSTED_MAX
        elif uid:
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
        if admin_key:
            limit = _get_admin_limit()
        elif trusted_peer:
            limit = _get_trusted_limit()
        elif uid:
            limit = auth_limit
        else:
            limit = anon_limit
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
