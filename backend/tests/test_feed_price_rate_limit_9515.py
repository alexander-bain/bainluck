"""Held Discover prices use one finite budget, isolated from ordinary API work."""
from collections import defaultdict

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from starlette.testclient import TestClient

from app.utils import rate_limit as limits


@pytest.fixture
def make_client(monkeypatch):
    def make(redis, principal="anonymous"):
        monkeypatch.setattr(limits, "_fresh_feed_price_limit", None)
        monkeypatch.setattr(limits, "FRESH_FEED_PRICE_RATE_LIMIT", "2/minute")
        monkeypatch.setattr(limits, "_FRESH_FEED_PRICE_MAX", 2)
        monkeypatch.setattr(limits, "_trusted_ips", lambda: set())
        monkeypatch.setattr(limits, "_resolve_trusted_uid", lambda token: "verified-user" if token == "valid" else None)
        if principal == "trusted":
            monkeypatch.setattr(limits, "_trusted_ips", lambda: {"192.0.2.1"})
            monkeypatch.setattr(limits, "_router_peer_ip", lambda request: "192.0.2.1")
        calls = defaultdict(int)
        if redis:
            monkeypatch.setattr(limits, "_get_async_rl_redis", lambda: object())
            async def hit(client, key, now):
                calls[key] += 1
                return calls[key]
            monkeypatch.setattr(limits, "_redis_fixed_window_hit", hit)
        else:
            from limits.storage import MemoryStorage
            from limits.strategies import FixedWindowRateLimiter
            limiter = FixedWindowRateLimiter(MemoryStorage())
            monkeypatch.setattr(limits, "_get_async_rl_redis", lambda: None)
            monkeypatch.setattr(limits, "_get_rate_limiter", lambda: limiter)
        app = FastAPI()
        app.add_middleware(limits.RateLimitMiddleware)
        async def okay():
            return {"ok": True}
        for path in ["/api/feed/price-cards", "/api/feed", "/api/events/search", "/api/events/1"]:
            app.add_api_route(path, okay, methods=["GET", "POST"])
        headers = {"Authorization": "Bearer valid"} if principal == "authenticated" else {}
        return TestClient(app, headers=headers), calls
    return make


@pytest.mark.parametrize("redis", [False, True])
@pytest.mark.parametrize("principal", ["anonymous", "authenticated", "trusted"])
def test_refresh_bucket_is_finite_and_cannot_starve_ordinary_routes(make_client, redis, principal):
    client, keys = make_client(redis, principal)
    assert client.get("/api/feed/price-cards?market_ids=1").status_code == 200
    assert client.get("/api/feed/price-cards?event_ids=123&market_ids=999").status_code == 200
    blocked = client.get("/api/feed/price-cards?market_ids=500")
    assert blocked.status_code == 429
    assert int(blocked.headers["Retry-After"]) > 0
    assert client.get("/api/feed").status_code == 200
    assert client.get("/api/events/search?q=hello").status_code == 200
    assert client.get("/api/events/1?fresh=true").status_code == 200
    if redis:
        price_keys = [key for key in keys if key.startswith("fresh-feed-price:")]
        assert len(price_keys) == 1
        assert keys[price_keys[0]] == 3
        expected = {"anonymous": "testclient", "authenticated": "user:verified-user", "trusted": "trusted:192.0.2.1"}[principal]
        assert price_keys == [f"fresh-feed-price:{expected}"]


@pytest.mark.parametrize("redis", [False, True])
def test_unverified_token_rotation_and_query_rotation_cannot_mint_budgets(make_client, redis):
    client, keys = make_client(redis)
    for value in ["forged-a", "forged-b"]:
        assert client.get(f"/api/feed/price-cards?market_ids={len(value)}", headers={"Authorization": f"Bearer {value}"}).status_code == 200
    assert client.get("/api/feed/price-cards?event_ids=2", headers={"Authorization": "Bearer forged-c"}).status_code == 429


def test_only_exact_get_production_route_uses_bucket():
    from app.main import app
    paths = [route.path for route in app.routes if isinstance(route, APIRoute) and "GET" in route.methods and route.path == limits._FRESH_FEED_PRICE_PATH]
    assert paths == ["/api/feed/price-cards"]
    from starlette.requests import Request
    for method, path, expected in [
        ("GET", "/api/feed/price-cards", True),
        ("POST", "/api/feed/price-cards", False),
        ("GET", "/api/feed/price-cards/other", False),
        ("GET", "/api/feed", False),
        ("GET", "/api/events/search", False),
    ]:
        request = Request({"type": "http", "method": method, "path": path, "headers": [], "query_string": b""})
        assert limits._is_fresh_feed_price_read(request) is expected
