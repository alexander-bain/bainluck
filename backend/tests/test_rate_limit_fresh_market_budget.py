"""#9536: the web futures chart's fresh /history refresh spends the market budget, not the ordinary one.

`useFuturesDetailStream` refreshes a held futures page with a fresh detail read
plus `/api/futures/{id}/history?hours=168&fresh=true`. Both must share the one
finite fresh-market caller bucket with `/probability-timeline` (native).
"""
from collections import defaultdict
from typing import Optional

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from limits import parse as parse_limit
from starlette.requests import Request
from starlette.testclient import TestClient

from app.utils import rate_limit as limits

EXPECTED_KEY = {"anonymous": "testclient", "authenticated": "user:verified-user", "trusted": "trusted:192.0.2.1"}


@pytest.fixture
def make_client(monkeypatch):
    def make(redis, principal="anonymous", market_max=3, ordinary_max=1000):
        monkeypatch.setattr(limits, "_fresh_market_limit", None)
        monkeypatch.setattr(limits, "FRESH_MARKET_RATE_LIMIT", f"{market_max}/minute")
        monkeypatch.setattr(limits, "_FRESH_MARKET_MAX", market_max)
        ordinary = parse_limit(f"{ordinary_max}/minute")
        monkeypatch.setattr(limits, "_get_limits", lambda: (ordinary, ordinary))
        monkeypatch.setattr(limits, "_get_trusted_limit", lambda: ordinary)
        for name in ("_ANON_MAX", "_AUTH_MAX", "_TRUSTED_MAX"):
            monkeypatch.setattr(limits, name, ordinary_max)
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
        for path in ["/api/futures/{market_id}", "/api/futures/{market_id}/history",
                     "/api/futures/{market_id}/probability-timeline", "/api/feed", "/api/events/search",
                     "/api/events/{event_id}", "/api/events/{event_id}/game-markets", "/api/feed/price-cards"]:
            app.add_api_route(path, okay, methods=["GET", "POST"])
        headers = {"Authorization": "Bearer valid"} if principal == "authenticated" else {}
        return TestClient(app, headers=headers), calls
    return make


def _assert_retry(response):
    assert response.status_code == 429
    assert int(response.headers["Retry-After"]) > 0
    assert int(response.headers["Retry-After"]) == response.json()["retry_after"]


@pytest.mark.parametrize("redis", [False, True])
@pytest.mark.parametrize("principal", ["anonymous", "authenticated", "trusted"])
def test_detail_history_and_timeline_share_one_finite_caller_budget(make_client, redis, principal):
    client, keys = make_client(redis, principal)
    assert client.get("/api/futures/1?fresh=true").status_code == 200
    assert client.get("/api/futures/1/history?hours=168&fresh=true").status_code == 200
    assert client.get("/api/futures/77/probability-timeline?fresh=true&top=10").status_code == 200
    # A different market and query on the history route still draws the same bucket.
    _assert_retry(client.get("/api/futures/2/history?hours=24&fresh=true"))
    # Fresh-history exhaustion leaves ordinary reads, nonfresh history and the
    # adjacent event/feed-price/game-market ceilings untouched.
    for path in ["/api/feed", "/api/events/search?q=hello", "/api/futures/2/history?hours=168",
                 "/api/futures/2", "/api/events/1?fresh=true", "/api/events/1/game-markets?fresh=true",
                 "/api/feed/price-cards"]:
        assert client.get(path).status_code == 200, path
    if redis:
        market_keys = [key for key in keys if key.startswith("fresh-market:")]
        assert market_keys == [f"fresh-market:{EXPECTED_KEY[principal]}"]
        assert keys[market_keys[0]] == 4


@pytest.mark.parametrize("redis", [False, True])
@pytest.mark.parametrize("principal", ["anonymous", "authenticated", "trusted"])
def test_ordinary_exhaustion_leaves_fresh_history_usable(make_client, redis, principal):
    client, _ = make_client(redis, principal, market_max=120, ordinary_max=2)
    assert client.get("/api/feed").status_code == 200
    assert client.get("/api/events/search?q=x").status_code == 200
    _assert_retry(client.get("/api/feed"))
    _assert_retry(client.get("/api/futures/1/history?hours=168"))
    assert client.get("/api/futures/1/history?hours=168&fresh=true").status_code == 200
    assert client.get("/api/futures/1?fresh=true").status_code == 200


@pytest.mark.parametrize("redis", [False, True])
def test_forged_tokens_and_market_ids_cannot_mint_history_budgets(make_client, redis):
    client, _ = make_client(redis, market_max=2)
    for market_id in [1, 2]:
        assert client.get(f"/api/futures/{market_id}/history?fresh=true",
                          headers={"Authorization": f"Bearer forged-{market_id}"}).status_code == 200
    _assert_retry(client.get("/api/futures/3/history?fresh=true", headers={"Authorization": "Bearer forged-3"}))


@pytest.mark.parametrize("path,query,expected", [
    # The exact web chart read.
    ("/api/futures/1/history", "hours=168&fresh=true", True),
    ("/api/futures/9536/history", "fresh=true", True),
    ("/api/futures/1/history", "fresh=TRUE", True),
    ("/api/futures/1/history", "fresh=false&fresh=true", True),
    ("/api/futures/1/history", "fresh=true&fresh=false", False),
    ("/api/futures/1/history", "hours=168", False),
    ("/api/futures/1/history", "fresh=other", False),
    ("/api/futures/0/history", "fresh=true", False),
    ("/api/futures/01/history", "fresh=true", False),
    ("/api/futures/abc/history", "fresh=true", False),
    ("/api/futures/1/history/", "fresh=true", False),
    ("/api/futures/1/history/x", "fresh=true", False),
    ("/api/futures/1/historyx", "fresh=true", False),
    # The history route's OWN contract: unbounded ints and a free-text champion.
    ("/api/futures/1/history", "fresh=true&hours=8761", True),
    ("/api/futures/1/history", "fresh=true&hours=0", True),
    ("/api/futures/1/history", "fresh=true&top_n=51&outcome_id=7", True),
    ("/api/futures/1/history", "fresh=true&champion=Scottie%20Scheffler", True),
    # Timeline-only `top` is not a history parameter, so it cannot disqualify.
    ("/api/futures/1/history", "fresh=true&top=abc", True),
    # Values the route itself rejects (422) are not fresh reads.
    ("/api/futures/1/history", "fresh=true&hours=abc", False),
    ("/api/futures/1/history", "fresh=true&top_n=1.5", False),
    ("/api/futures/1/history", "fresh=true&outcome_id=x", False),
])
def test_history_classifier_matches_the_real_route_contract(path, query, expected):
    request = Request({"type": "http", "method": "GET", "path": path, "headers": [], "query_string": query.encode()})
    assert limits._is_fresh_market_read(request) is expected


@pytest.mark.parametrize("method", ["POST", "PUT", "DELETE", "HEAD"])
def test_history_classifier_is_get_only(method):
    request = Request({"type": "http", "method": method, "path": "/api/futures/1/history",
                       "headers": [], "query_string": b"fresh=true"})
    assert limits._is_fresh_market_read(request) is False


def test_classifier_parameters_mirror_the_production_history_route():
    """If the route grows or renames an int query param, this classifier must follow."""
    from app.main import app
    route = next(r for r in app.routes if isinstance(r, APIRoute)
                 and r.path == "/api/futures/{market_id}/history" and "GET" in r.methods)
    int_params = {p.alias for p in route.dependant.query_params if p.field_info.annotation in (int, Optional[int])}
    assert int_params == set(limits._FRESH_MARKET_HISTORY_INT_PARAMS)
    assert limits.FRESH_MARKET_RATE_LIMIT == "120/minute"
    assert limits._FRESH_MARKET_MAX == 120
