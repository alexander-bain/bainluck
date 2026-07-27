"""Two-principal HTTP shared-cache isolation contract (C30 / Queue #264).

Two layers:

1. Unit tests of the pure ``cache_control_for`` decision against the full C30
   cache-policy matrix (feed, debug, sports/available, public routes, admin,
   route-owned directives, non-200 / non-GET, identity variants).

2. A deterministic *fake shared cache* over a stub ASGI origin that uses the
   real ``apply_cache_policy`` middleware. It replays principal A's stored
   response to principal B on the same URL exactly as a standards-compliant
   shared cache would, and asserts every protected/personalized response is
   NON-storable so principal B always reaches origin auth (403).

No production DB, network, or Redis; fully deterministic.
"""

from fastapi import FastAPI, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

from app.utils.http_cache_policy import (
    PRIVATE_DIRECTIVE,
    apply_cache_policy,
    cache_control_for,
    request_is_identity_bearing,
)


# ---------------------------------------------------------------------------
# Layer 1 — pure decision function
# ---------------------------------------------------------------------------

def _cc(path, *, method="GET", status=200, identity=False, route=None):
    return cache_control_for(
        method=method,
        status_code=status,
        path=path,
        identity_bearing=identity,
        route_directive=route,
    )


def test_anonymous_feed_is_never_publicly_storable():
    # Personalized surface: private+no-store even with no identity present, so a
    # public anon body can never be seeded then replayed to a signed-in user.
    assert _cc("/api/feed") == PRIVATE_DIRECTIVE


def test_identity_feed_is_private_no_store():
    assert _cc("/api/feed", identity=True) == PRIVATE_DIRECTIVE


def test_feed_debug_authenticated_is_private_no_store():
    # ?debug=true authenticates via Bearer → identity_bearing True.
    assert _cc("/api/feed", identity=True) == PRIVATE_DIRECTIVE


def test_sports_available_authenticated_is_private_no_store():
    assert _cc("/api/sports/available", identity=True) == PRIVATE_DIRECTIVE


def test_public_sports_list_anonymous_keeps_ttl():
    assert _cc("/api/sports") == "public, max-age=120, stale-while-revalidate=60"


def test_public_category_routes_keep_ttls_when_anonymous():
    assert _cc("/api/weather/featured") == "public, max-age=300, stale-while-revalidate=60"
    assert _cc("/api/politics") == "public, max-age=120, stale-while-revalidate=60"
    assert _cc("/api/economics") == "public, max-age=120, stale-while-revalidate=60"
    assert _cc("/api/entertainment") == "public, max-age=120, stale-while-revalidate=60"
    assert _cc("/api/playoffs/nba") == "public, max-age=300, stale-while-revalidate=60"


def test_identity_bearing_public_route_becomes_private():
    # Authentication wins over latency: a signed-in user on a public route is
    # not shared-cacheable via this middleware.
    assert _cc("/api/weather/featured", identity=True) == PRIVATE_DIRECTIVE


def test_admin_paths_never_public():
    assert _cc("/api/admin/anything") == PRIVATE_DIRECTIVE
    assert _cc("/api/admin/anything", identity=True) == PRIVATE_DIRECTIVE


def test_route_owned_directive_is_never_overwritten():
    # Singular ownership: completed event-history's 3600s TTL survives, even for
    # an identity-bearing request (route knows it is identity-independent).
    assert _cc("/api/events/1/history", route="public, max-age=3600, stale-while-revalidate=300") is None
    assert _cc("/api/events/1/history", identity=True, route="private, no-store") is None
    assert _cc("/api/feed", route="private, no-store") is None


def test_non_200_and_non_get_are_untouched():
    assert _cc("/api/feed", status=403) is None
    assert _cc("/api/sports/available", status=403, identity=True) is None
    assert _cc("/api/feed", method="POST") is None
    assert _cc("/api/feed", method="OPTIONS") is None
    assert _cc("/api/events/1", status=302) is None


def test_unmatched_public_path_gets_no_directive():
    assert _cc("/api/me/profile") is None  # not identity-bearing, not a cache prefix
    assert _cc("/api/me/profile", identity=True) == PRIVATE_DIRECTIVE


def test_request_is_identity_bearing_signals():
    class _Req:
        def __init__(self, headers=None, cookies=None):
            self.headers = headers or {}
            self.cookies = cookies or {}

    assert request_is_identity_bearing(_Req(headers={"authorization": "Bearer x"}))
    assert request_is_identity_bearing(_Req(headers={"x-session-id": "s1"}))
    assert request_is_identity_bearing(_Req(cookies={"session_id": "c1"}))
    assert not request_is_identity_bearing(_Req())


# ---------------------------------------------------------------------------
# Layer 2 — fake shared cache over a real-middleware ASGI origin
# ---------------------------------------------------------------------------

_ADMIN_TOKEN = "admin-secret-token"


def _build_origin() -> FastAPI:
    """Stub origin mirroring the real routes' auth/cache behavior, wrapped in
    the real ``apply_cache_policy`` middleware and CORS (added first so the
    policy middleware runs outermost, exactly like production)."""
    app = FastAPI()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["https://bainluck.com"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def _policy(request: Request, call_next):
        response = await call_next(request)
        apply_cache_policy(request, response)
        return response

    def _is_admin(request: Request) -> bool:
        return request.headers.get("authorization") == f"Bearer {_ADMIN_TOKEN}"

    @app.get("/api/feed")
    async def feed(request: Request, debug: bool = Query(False)):
        if debug and not _is_admin(request):
            return Response("forbidden", status_code=403)
        # Body reflects the principal so a cross-principal replay is detectable.
        who = (
            request.headers.get("authorization")
            or request.headers.get("x-session-id")
            or "anon"
        )
        suffix = "-debug" if debug else ""
        return Response(f"feed-body:{who}{suffix}")

    @app.get("/api/sports/available")
    async def sports_available(request: Request):
        if not _is_admin(request):
            return Response("forbidden", status_code=403)
        return Response("protected-sports-body")

    @app.get("/api/weather/featured")
    async def weather(request: Request):
        return Response("public-weather-body")

    @app.get("/api/events/{event_id}/history")
    async def history(event_id: int, response: Response):
        # Completed event: route claims ownership of a long TTL.
        response.headers["Cache-Control"] = "public, max-age=3600, stale-while-revalidate=300"
        return Response("history-body", headers=dict(response.headers))

    return app


class FakeSharedCache:
    """A minimal RFC-7234-ish shared cache in front of the origin.

    Stores a GET 200 response only when its ``Cache-Control`` permits shared
    storage (no ``no-store``, no ``private``). Keys on method+URL plus any
    ``Vary``-selected request header values. Serves a fresh stored entry WITHOUT
    forwarding the second principal's request to origin — the exact behavior
    that would leak a protected body if the response were marked public.
    """

    def __init__(self, client: TestClient):
        self.client = client
        self.store: dict = {}
        self.origin_hits = 0

    @staticmethod
    def _storable(cc: str) -> bool:
        cc = (cc or "").lower()
        return "no-store" not in cc and "private" not in cc

    def _vary_key(self, url: str, vary: str, headers: dict) -> tuple:
        parts = [p.strip().lower() for p in (vary or "").split(",") if p.strip()]
        selected = tuple((h, headers.get(h, "")) for h in parts)
        return (url, selected)

    def get(self, url: str, headers: dict | None = None):
        headers = headers or {}
        # Look for a stored entry that matches on Vary-selected headers.
        for (stored_url, selected), entry in self.store.items():
            if stored_url != url:
                continue
            if all(headers.get(h, "") == v for h, v in selected):
                return entry["body"], entry["status"], True  # served from cache
        # Miss → forward to origin.
        self.origin_hits += 1
        resp = self.client.get(url, headers=headers)
        cc = resp.headers.get("cache-control", "")
        if resp.request.method == "GET" and resp.status_code == 200 and self._storable(cc):
            key = self._vary_key(url, resp.headers.get("vary", ""), headers)
            self.store[key] = {"body": resp.text, "status": resp.status_code}
        return resp.text, resp.status_code, False


def _cache():
    return FakeSharedCache(TestClient(_build_origin()))


def test_signed_in_feed_not_replayed_to_second_principal():
    cache = _cache()
    body_a, status_a, from_cache_a = cache.get(
        "/api/feed", headers={"authorization": "Bearer user-A"}
    )
    assert status_a == 200 and "user-A" in body_a and not from_cache_a
    # Principal B (different user) must reach origin, not get A's body.
    body_b, status_b, from_cache_b = cache.get(
        "/api/feed", headers={"authorization": "Bearer user-B"}
    )
    assert not from_cache_b, "signed-in feed must not be shared-cached"
    assert "user-A" not in body_b and "user-B" in body_b


def test_session_feed_isolated_between_sessions():
    cache = _cache()
    a, _, _ = cache.get("/api/feed", headers={"x-session-id": "sess-A"})
    b, _, from_cache_b = cache.get("/api/feed", headers={"x-session-id": "sess-B"})
    assert "sess-A" in a
    assert not from_cache_b and "sess-A" not in b and "sess-B" in b


def test_anon_feed_not_replayed_to_signed_in():
    cache = _cache()
    anon, _, _ = cache.get("/api/feed")
    signed, _, from_cache = cache.get("/api/feed", headers={"authorization": "Bearer user-A"})
    assert "anon" in anon
    assert not from_cache and "anon" not in signed


def test_admin_feed_debug_not_replayed_to_anonymous():
    cache = _cache()
    admin_body, admin_status, _ = cache.get(
        "/api/feed?debug=true", headers={"authorization": f"Bearer {_ADMIN_TOKEN}"}
    )
    assert admin_status == 200 and admin_body == "feed-body:Bearer " + _ADMIN_TOKEN + "-debug"
    # Unauthenticated replay must reach origin and get 403 — never the cached 200.
    b_body, b_status, from_cache = cache.get("/api/feed?debug=true")
    assert not from_cache
    assert b_status == 403 and b_body == "forbidden"


def test_sports_available_not_replayed_to_anonymous():
    cache = _cache()
    a_body, a_status, _ = cache.get(
        "/api/sports/available", headers={"authorization": f"Bearer {_ADMIN_TOKEN}"}
    )
    assert a_status == 200 and a_body == "protected-sports-body"
    b_body, b_status, from_cache = cache.get("/api/sports/available")
    assert not from_cache
    assert b_status == 403 and b_body == "forbidden"


def test_public_route_remains_shared_cacheable():
    cache = _cache()
    a, _, from_cache_a = cache.get("/api/weather/featured")
    assert not from_cache_a
    b, _, from_cache_b = cache.get("/api/weather/featured")
    assert from_cache_b, "public anonymous route should be shared-cacheable"
    assert a == b == "public-weather-body"


def test_query_variants_are_distinct_cache_keys():
    cache = _cache()
    cache.get("/api/weather/featured?city=nyc")
    _, _, from_cache = cache.get("/api/weather/featured?city=la")
    assert not from_cache, "different query string is a distinct cache key"


def test_completed_history_directive_is_singular_and_preserved():
    client = TestClient(_build_origin())
    resp = client.get("/api/events/5/history")
    # Route's own 3600s directive survives — not overwritten to 30s or 10s.
    assert resp.headers["cache-control"] == "public, max-age=3600, stale-while-revalidate=300"


def test_cors_vary_origin_stays_intact_and_is_separate_from_isolation():
    client = TestClient(_build_origin())
    # A CORS request on a public route: Vary: Origin must remain.
    resp = client.get(
        "/api/weather/featured", headers={"origin": "https://bainluck.com"}
    )
    assert "origin" in resp.headers.get("vary", "").lower()
    # And the public directive is still applied alongside it.
    assert "public" in resp.headers["cache-control"]
