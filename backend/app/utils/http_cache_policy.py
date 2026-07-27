"""Centralized HTTP cache-isolation policy (C30 / Queue #264).

The previous ``request_timing`` middleware rewrote every successful GET whose
path matched a prefix in ``CACHE_RULES`` to a shared ``public`` directive,
without inspecting who the request came from or what the route already decided.
That marked two Bearer-protected surfaces (``/api/feed?debug=true`` and
``/api/sports/available``) and every personalized ``/api/feed`` response as
publicly reusable, so a standards-compliant shared cache could replay one
principal's authorized body to a different, unauthenticated principal.

This module makes the policy identity-aware and route-respecting. The single
rule that governs it:

    Authentication and identity ALWAYS win over latency caching.

Endpoint cache classes:

* **route-owned** — the route set its own ``Cache-Control`` (e.g. completed
  event-history's 3600s TTL). Ownership is singular: the middleware never
  overwrites it. The route author knows whether the response is
  identity-dependent.
* **protected / personalized / identity-bearing** — anything under ``/admin``,
  any ``/api/feed`` response (personalized surface), and any request carrying
  ``Authorization``, ``x-session-id``, or a ``session_id`` cookie → never
  storable/shared: ``private, no-store``.
* **public anonymous** — a ``CACHE_RULES`` prefix with no identity signal keeps
  its existing short TTL so anonymous read latency is preserved.

The protection does not rely on ``Vary`` (a ``no-store`` response is never
stored, so it can never be replayed to a second principal regardless of cache
keying), and it does not enable any CDN/edge rewrite.
"""

from __future__ import annotations

from typing import Optional

from starlette.requests import Request
from starlette.responses import Response


# (path-prefix, max-age seconds) for anonymous, identity-independent public
# routes. Order matters only for overlapping prefixes; first match wins.
CACHE_RULES: list[tuple[str, int]] = [
    ("/api/events", 10),
    ("/api/feed", 10),  # retained for completeness; feed is force-private below
    ("/api/playoffs/", 300),
    ("/api/sports", 120),
    ("/api/golf", 300),
    ("/api/weather", 300),
    ("/api/economics", 120),
    ("/api/politics", 120),
    ("/api/entertainment", 120),
    ("/api/categories", 120),
]

# Non-storable, non-shared directive for protected/personalized responses.
PRIVATE_DIRECTIVE = "private, no-store"


def request_is_identity_bearing(request: Request) -> bool:
    """True when the request carries any principal-identifying credential.

    Bearer tokens (admin token or a signed-in user's session JWT), the Discover
    ``x-session-id`` header, and the ``session_id`` cookie all make a response
    potentially principal-specific. Since Queue #252 admin auth is Bearer-only,
    every protected endpoint is covered by the Authorization check.
    """
    return bool(
        request.headers.get("authorization")
        or request.headers.get("x-session-id")
        or request.cookies.get("session_id")
    )


def cache_control_for(
    *,
    method: str,
    status_code: int,
    path: str,
    identity_bearing: bool,
    route_directive: Optional[str],
) -> Optional[str]:
    """Return the ``Cache-Control`` value to set, or ``None`` to leave as-is.

    Pure function so both the middleware and the contract test harness exercise
    the identical decision.
    """
    # Only successful reads are ever rewritten. Mutations, redirects, preflight,
    # 304s, and error responses are left to the framework/route.
    if method != "GET" or status_code != 200:
        return None

    # Singular ownership: never overwrite a directive the route set itself.
    if route_directive:
        return None

    # Authentication / identity / personalization always wins over latency.
    if "/admin" in path or path.startswith("/api/feed") or identity_bearing:
        return PRIVATE_DIRECTIVE

    # Public, anonymous, identity-independent routes keep their short TTLs.
    for prefix, max_age in CACHE_RULES:
        if path.startswith(prefix):
            return f"public, max-age={max_age}, stale-while-revalidate=60"

    return None


def apply_cache_policy(request: Request, response: Response) -> None:
    """Set ``Cache-Control`` on ``response`` per the isolation policy.

    Mutates ``response.headers`` in place; a no-op when no rule applies. Never
    touches ``Vary`` (so CORS's ``Vary: Origin`` stays intact).
    """
    directive = cache_control_for(
        method=request.method,
        status_code=response.status_code,
        path=request.url.path,
        identity_bearing=request_is_identity_bearing(request),
        route_directive=response.headers.get("Cache-Control"),
    )
    if directive is not None:
        response.headers["Cache-Control"] = directive
