"""Stream-triggered standalone detail/history use one finite budget, isolated from ordinary API work."""
from collections import defaultdict

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from starlette.testclient import TestClient

from app.utils import rate_limit as limits


@pytest.fixture
def make_client(monkeypatch):
    def make(redis, principal="anonymous"):
        monkeypatch.setattr(limits, "_fresh_market_limit", None)
        monkeypatch.setattr(limits, "_fresh_game_market_limit", None)
        monkeypatch.setattr(limits, "FRESH_GAME_MARKET_RATE_LIMIT", "2/minute")
        monkeypatch.setattr(limits, "_FRESH_GAME_MARKET_MAX", 2)
        monkeypatch.setattr(limits, "FRESH_MARKET_RATE_LIMIT", "2/minute")
        monkeypatch.setattr(limits, "_FRESH_MARKET_MAX", 2)
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
        for path in ["/api/futures/{market_id}", "/api/futures/{market_id}/probability-timeline", "/api/feed", "/api/events/search", "/api/events/1", "/api/events/{event_id}/game-markets"]:
            app.add_api_route(path, okay, methods=["GET", "POST"])
        headers = {"Authorization": "Bearer valid"} if principal == "authenticated" else {}
        return TestClient(app, headers=headers), calls
    return make


@pytest.mark.parametrize("redis", [False, True])
@pytest.mark.parametrize("principal", ["anonymous", "authenticated", "trusted"])
def test_refresh_bucket_is_finite_and_cannot_starve_ordinary_routes(make_client, redis, principal):
    client, keys = make_client(redis, principal)
    assert client.get("/api/futures/1?fresh=true").status_code == 200
    assert client.get("/api/futures/999/probability-timeline?fresh=true&top=50&hours=168").status_code == 200
    blocked = client.get("/api/futures/500?fresh=true")
    assert blocked.status_code == 429
    assert int(blocked.headers["Retry-After"]) > 0
    assert int(blocked.headers["Retry-After"]) == blocked.json()["retry_after"]
    assert client.get("/api/futures/1").status_code == 200
    assert client.get("/api/feed").status_code == 200
    assert client.get("/api/events/search?q=hello").status_code == 200
    assert client.get("/api/events/1?fresh=true").status_code == 200
    if redis:
        price_keys = [key for key in keys if key.startswith("fresh-market:")]
        assert len(price_keys) == 1
        assert keys[price_keys[0]] == 3
        expected = {"anonymous": "testclient", "authenticated": "user:verified-user", "trusted": "trusted:192.0.2.1"}[principal]
        assert price_keys == [f"fresh-market:{expected}"]


@pytest.mark.parametrize("redis", [False, True])
def test_unverified_token_rotation_and_query_rotation_cannot_mint_budgets(make_client, redis):
    client, keys = make_client(redis)
    for value in ["forged-a", "forged-b"]:
        assert client.get(f"/api/futures/{len(value)}?fresh=true", headers={"Authorization": f"Bearer {value}"}).status_code == 200
    assert client.get("/api/futures/2?fresh=true", headers={"Authorization": "Bearer forged-c"}).status_code == 429


@pytest.mark.parametrize("method,path,query,expected", [
    ("GET", "/api/futures/1", "fresh=true", True),
    ("GET", "/api/futures/1", "fresh=TRUE", True),
    ("GET", "/api/futures/1", "fresh=false&fresh=true", True),
    ("GET", "/api/futures/1", "fresh=true&fresh=false", False),
    ("GET", "/api/futures/1", "", False),
    ("GET", "/api/futures/1", "fresh=other", False),
    ("POST", "/api/futures/1", "fresh=true", False),
    ("GET", "/api/futures/0", "fresh=true", False),
    ("GET", "/api/futures/1/", "fresh=true", False),
    # #9536: the web chart's fresh /history read joins this bucket (full contract:
    # test_rate_limit_fresh_market_budget.py).
    ("GET", "/api/futures/1/history", "fresh=true", True),
    ("GET", "/api/futures/1/history", "hours=168", False),
    ("GET", "/api/futures/search", "fresh=true", False),
    ("GET", "/api/futures/1/probability-timeline", "fresh=true&top=50&hours=8760", True),
    ("GET", "/api/futures/1/probability-timeline", "fresh=true&top=51", False),
    ("GET", "/api/futures/1/probability-timeline", "fresh=true&hours=8761", False),
    ("GET", "/api/futures/1/probability-timeline", "fresh=true&top=abc", False),
    ("GET", "/api/futures/1/probability-timeline", "fresh=true&hours=0", False),
])
def test_only_exact_opt_in_reads_with_valid_timeline_bounds_qualify(method, path, query, expected):
    from starlette.requests import Request
    request = Request({"type": "http", "method": method, "path": path, "headers": [], "query_string": query.encode()})
    assert limits._is_fresh_market_read(request) is expected


def test_exact_production_routes_exist_and_budget_is_finite():
    from app.main import app
    paths = {route.path for route in app.routes if isinstance(route, APIRoute) and "GET" in route.methods}
    assert {"/api/futures/{market_id}", "/api/futures/{market_id}/history",
            "/api/futures/{market_id}/probability-timeline"} <= paths
    assert limits.FRESH_MARKET_RATE_LIMIT == "120/minute"
    assert limits._FRESH_MARKET_MAX == 120


@pytest.mark.parametrize("redis", [False, True])
@pytest.mark.parametrize("principal", ["anonymous", "authenticated", "trusted"])
def test_event_market_budget_is_finite_and_independent(make_client, redis, principal):
    client, keys = make_client(redis, principal)
    assert client.get("/api/events/1/game-markets?fresh=true").status_code == 200
    assert client.get("/api/events/2/game-markets?fresh=true").status_code == 200
    blocked = client.get("/api/events/3/game-markets?fresh=true")
    assert blocked.status_code == 429
    assert int(blocked.headers["Retry-After"]) == blocked.json()["retry_after"] > 0
    for path in ["/api/feed", "/api/events/search?q=x", "/api/events/1?fresh=true",
                 "/api/events/3/game-markets", "/api/futures/1?fresh=true"]:
        assert client.get(path).status_code == 200
    if redis:
        bucket_keys = [key for key in keys if key.startswith("fresh-game-market:")]
        expected = {"anonymous": "testclient", "authenticated": "user:verified-user", "trusted": "trusted:192.0.2.1"}[principal]
        assert bucket_keys == [f"fresh-game-market:{expected}"]
        assert keys[bucket_keys[0]] == 3


@pytest.mark.parametrize("redis", [False, True])
def test_event_ids_and_forged_auth_do_not_mint_refresh_budgets(make_client, redis):
    client, _ = make_client(redis)
    for market_id in [1, 2]:
        assert client.get(f"/api/events/{market_id}/game-markets?fresh=true",
                          headers={"Authorization": f"Bearer forged-{market_id}"}).status_code == 200
    assert client.get("/api/events/3/game-markets?fresh=true",
                      headers={"Authorization": "Bearer forged-3"}).status_code == 429


@pytest.mark.parametrize("method,path,query,expected", [
    ("GET", "/api/events/1/game-markets", "fresh=true", True),
    ("GET", "/api/events/1/game-markets", "fresh=TRUE", True),
    ("GET", "/api/events/1/game-markets", "fresh=false&fresh=true", True),
    ("GET", "/api/events/1/game-markets", "fresh=true&fresh=false", False),
    ("GET", "/api/events/1/game-markets", "", False),
    ("GET", "/api/events/0/game-markets", "fresh=true", False),
    ("GET", "/api/events/1/game-markets/", "fresh=true", False),
    ("GET", "/api/events/1/history", "fresh=true", False),
    ("POST", "/api/events/1/game-markets", "fresh=true", False),
])
def test_event_market_budget_requires_exact_opt_in_get(method, path, query, expected):
    from starlette.requests import Request
    request = Request({"type": "http", "method": method, "path": path, "headers": [], "query_string": query.encode()})
    assert limits._is_fresh_game_market_read(request) is expected


def test_game_market_route_and_finite_ceiling():
    from app.main import app
    paths = {route.path for route in app.routes if isinstance(route, APIRoute) and "GET" in route.methods}
    assert "/api/events/{event_id}/game-markets" in paths
    assert limits.FRESH_GAME_MARKET_RATE_LIMIT == "60/minute"
    assert limits._FRESH_GAME_MARKET_MAX == 60
