"""
Tests for the API rate limiting middleware.

Verifies:
  - Anonymous requests are rate-limited at 60/minute per IP
  - Authenticated requests get 120/minute per user
  - Admin endpoints are exempt
  - 429 responses include Retry-After header and JSON body
  - Different IPs / users have independent buckets
"""

import base64
import json
import time

import pytest

from app.utils.rate_limit import (
    RateLimitMiddleware,
    _extract_uid_from_token,
    _get_client_ip,
    _is_exempt,
    ANON_RATE_LIMIT,
    AUTH_RATE_LIMIT,
)


# ---------------------------------------------------------------------------
# Unit tests for helper functions
# ---------------------------------------------------------------------------


class TestGetClientIp:
    """Tests for _get_client_ip."""

    def _make_request(self, headers: list, client=None):
        from starlette.requests import Request
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": headers,
        }
        if client is not None:
            scope["client"] = client
        return Request(scope)

    def test_x_forwarded_for_single(self):
        """Uses the first IP from X-Forwarded-For."""
        request = self._make_request([(b"x-forwarded-for", b"1.2.3.4")])
        assert _get_client_ip(request) == "1.2.3.4"

    def test_x_forwarded_for_chain(self):
        """Uses only the first (client) IP from a proxy chain."""
        request = self._make_request([(b"x-forwarded-for", b"1.2.3.4, 10.0.0.1, 10.0.0.2")])
        assert _get_client_ip(request) == "1.2.3.4"

    def test_fallback_to_client_host(self):
        """Falls back to request.client.host when no X-Forwarded-For."""
        request = self._make_request([], client=("192.168.1.1", 12345))
        assert _get_client_ip(request) == "192.168.1.1"

    def test_no_client_info(self):
        """Returns 'unknown' when no client info is available."""
        request = self._make_request([])
        assert _get_client_ip(request) == "unknown"


class TestExtractUid:
    """Tests for _extract_uid_from_token."""

    def _make_jwt(self, payload: dict) -> str:
        """Build a fake JWT (header.payload.signature) with the given payload."""
        header = base64.urlsafe_b64encode(json.dumps({"alg": "HS256"}).encode()).rstrip(b"=").decode()
        body = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
        sig = base64.urlsafe_b64encode(b"fakesig").rstrip(b"=").decode()
        return f"{header}.{body}.{sig}"

    def test_extract_uid(self):
        token = self._make_jwt({"uid": "user123", "email": "a@b.com"})
        assert _extract_uid_from_token(token) == "user123"

    def test_extract_sub_fallback(self):
        token = self._make_jwt({"sub": "sub456"})
        assert _extract_uid_from_token(token) == "sub456"

    def test_uid_preferred_over_sub(self):
        token = self._make_jwt({"uid": "user123", "sub": "sub456"})
        assert _extract_uid_from_token(token) == "user123"

    def test_no_uid_or_sub(self):
        token = self._make_jwt({"email": "a@b.com"})
        assert _extract_uid_from_token(token) is None

    def test_invalid_token(self):
        assert _extract_uid_from_token("not-a-jwt") is None

    def test_empty_token(self):
        assert _extract_uid_from_token("") is None


class TestIsExempt:
    """Tests for _is_exempt."""

    def test_admin_exempt(self):
        assert _is_exempt("/api/admin/something") is True

    def test_docs_exempt(self):
        assert _is_exempt("/docs") is True

    def test_openapi_exempt(self):
        assert _is_exempt("/openapi.json") is True

    def test_health_exempt(self):
        assert _is_exempt("/health") is True

    def test_feed_not_exempt(self):
        assert _is_exempt("/api/feed") is False

    def test_events_not_exempt(self):
        assert _is_exempt("/api/events/123") is False


# ---------------------------------------------------------------------------
# Integration tests using the actual middleware with in-memory storage
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_rate_limiter_state():
    """Reset the rate limiter singleton between tests."""
    import app.utils.rate_limit as rl_mod
    old_limiter = rl_mod._rate_limiter
    old_anon = rl_mod._anon_limit
    old_auth = rl_mod._auth_limit
    # Force fresh singletons each test
    rl_mod._rate_limiter = None
    rl_mod._anon_limit = None
    rl_mod._auth_limit = None
    yield
    rl_mod._rate_limiter = old_limiter
    rl_mod._anon_limit = old_anon
    rl_mod._auth_limit = old_auth


def _make_test_app(anon_limit: str = "5/minute", auth_limit: str = "10/minute"):
    """
    Build a minimal FastAPI app with RateLimitMiddleware for testing.

    Uses small limits so tests don't need 60+ requests.
    """
    import app.utils.rate_limit as rl_mod
    # Override limits for testing
    rl_mod.ANON_RATE_LIMIT = anon_limit
    rl_mod.AUTH_RATE_LIMIT = auth_limit

    from fastapi import FastAPI
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware)

    @app.get("/api/feed")
    async def feed():
        return {"ok": True}

    @app.get("/api/admin/status")
    async def admin_status():
        return {"admin": True}

    @app.get("/api/events/1")
    async def event_detail():
        return {"event": 1}

    return app


def _make_jwt(payload: dict) -> str:
    header = base64.urlsafe_b64encode(json.dumps({"alg": "HS256"}).encode()).rstrip(b"=").decode()
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
    sig = base64.urlsafe_b64encode(b"fakesig").rstrip(b"=").decode()
    return f"{header}.{body}.{sig}"


class TestRateLimitFailFast:
    """#1197 (r259): a slow/churning Redis op must never block the request — the
    async check is hard-bounded by wait_for and fails OPEN within the budget."""

    def test_slow_redis_fails_open_within_budget(self, monkeypatch):
        import asyncio
        import time as _time
        from starlette.testclient import TestClient
        import app.utils.rate_limit as rl_mod

        rl_mod._RL_CHECK_TIMEOUT = 0.2

        class _SlowAsyncRedis:
            async def incr(self, *a, **k):
                await asyncio.sleep(3)  # simulate a churning Redis round-trip
                return 1

            async def expire(self, *a, **k):
                return True

        monkeypatch.setattr(rl_mod, "_get_async_rl_redis", lambda: _SlowAsyncRedis())
        app = _make_test_app()
        client = TestClient(app)

        start = _time.perf_counter()
        resp = client.get("/api/feed")
        elapsed = _time.perf_counter() - start
        # Fails OPEN (request allowed) and returns fast — NOT after the 3s sleep.
        assert resp.status_code == 200
        assert elapsed < 2.0, f"rate-limit check did not fail-fast: {elapsed:.2f}s"

    def test_async_redis_path_enforces_limit(self, monkeypatch):
        from starlette.testclient import TestClient
        import app.utils.rate_limit as rl_mod

        rl_mod._RL_CHECK_TIMEOUT = 0.6
        rl_mod._ANON_MAX = 3

        counter = {"n": 0}

        class _CountingAsyncRedis:
            async def incr(self, *a, **k):
                counter["n"] += 1
                return counter["n"]

            async def expire(self, *a, **k):
                return True

        monkeypatch.setattr(rl_mod, "_get_async_rl_redis", lambda: _CountingAsyncRedis())
        app = _make_test_app()
        client = TestClient(app)

        for i in range(3):
            assert client.get("/api/feed").status_code == 200, f"req {i+1}"
        # 4th exceeds the (patched) max of 3 → 429.
        resp = client.get("/api/feed")
        assert resp.status_code == 429
        assert "Rate limit exceeded" in resp.json()["detail"]
        rl_mod._ANON_MAX = 60  # restore


class TestRateLimitMiddleware:
    """Integration tests for the rate limit middleware."""

    def test_anonymous_rate_limit_enforced(self):
        """Anonymous requests are limited (5/minute in test config)."""
        from starlette.testclient import TestClient
        app = _make_test_app(anon_limit="5/minute")
        client = TestClient(app)

        # First 5 requests should succeed
        for i in range(5):
            resp = client.get("/api/feed")
            assert resp.status_code == 200, f"Request {i+1} should succeed"

        # 6th request should be rate limited
        resp = client.get("/api/feed")
        assert resp.status_code == 429
        body = resp.json()
        assert "Rate limit exceeded" in body["detail"]
        assert "retry_after" in body
        assert "Retry-After" in resp.headers

    def test_admin_endpoints_exempt(self):
        """Admin endpoints are never rate limited."""
        from starlette.testclient import TestClient
        app = _make_test_app(anon_limit="2/minute")
        client = TestClient(app)

        # Admin endpoints should never be limited
        for _ in range(10):
            resp = client.get("/api/admin/status")
            assert resp.status_code == 200

    def test_admin_exemption_does_not_touch_limiter(self):
        """Admin exemption short-circuits before storage is consulted."""
        import app.utils.rate_limit as rl_mod
        from starlette.testclient import TestClient

        class TrackingLimiter:
            called = False

            def hit(self, *args, **kwargs):
                self.called = True
                return True

        limiter = TrackingLimiter()
        rl_mod._rate_limiter = limiter

        app = _make_test_app(anon_limit="1/minute")
        client = TestClient(app)

        for _ in range(3):
            resp = client.get("/api/admin/status")
            assert resp.status_code == 200

        assert limiter.called is False

    def test_authenticated_gets_higher_limit(self):
        """Authenticated users get a higher rate limit than anonymous."""
        from starlette.testclient import TestClient
        app = _make_test_app(anon_limit="3/minute", auth_limit="6/minute")
        client = TestClient(app)

        token = _make_jwt({"uid": "testuser1"})
        headers = {"Authorization": f"Bearer {token}"}

        # Authenticated user can make 6 requests
        for i in range(6):
            resp = client.get("/api/feed", headers=headers)
            assert resp.status_code == 200, f"Auth request {i+1} should succeed"

        # 7th should be limited
        resp = client.get("/api/feed", headers=headers)
        assert resp.status_code == 429

    def test_different_users_independent_buckets(self):
        """Different authenticated users have independent rate limits."""
        from starlette.testclient import TestClient
        app = _make_test_app(anon_limit="2/minute", auth_limit="3/minute")
        client = TestClient(app)

        token_a = _make_jwt({"uid": "user_a"})
        token_b = _make_jwt({"uid": "user_b"})

        # User A uses up their limit
        for _ in range(3):
            resp = client.get("/api/feed", headers={"Authorization": f"Bearer {token_a}"})
            assert resp.status_code == 200

        resp = client.get("/api/feed", headers={"Authorization": f"Bearer {token_a}"})
        assert resp.status_code == 429

        # User B should still have full quota
        for _ in range(3):
            resp = client.get("/api/feed", headers={"Authorization": f"Bearer {token_b}"})
            assert resp.status_code == 200

    def test_authenticated_user_bucket_independent_from_same_ip_anonymous_bucket(self):
        """Authenticated and anonymous traffic from one IP do not share quota."""
        from starlette.testclient import TestClient

        app = _make_test_app(anon_limit="2/minute", auth_limit="2/minute")
        client = TestClient(app)
        ip_headers = {"X-Forwarded-For": "10.0.0.50"}
        auth_headers = {
            **ip_headers,
            "Authorization": f"Bearer {_make_jwt({'uid': 'same-ip-user'})}",
        }

        for _ in range(2):
            resp = client.get("/api/feed", headers=ip_headers)
            assert resp.status_code == 200

        assert client.get("/api/feed", headers=ip_headers).status_code == 429

        for _ in range(2):
            resp = client.get("/api/feed", headers=auth_headers)
            assert resp.status_code == 200

        assert client.get("/api/feed", headers=auth_headers).status_code == 429

    def test_different_ips_independent_buckets(self):
        """Different IPs have independent rate limits."""
        from starlette.testclient import TestClient
        app = _make_test_app(anon_limit="2/minute")
        client = TestClient(app)

        # IP 1 uses up its limit
        for _ in range(2):
            resp = client.get("/api/feed", headers={"X-Forwarded-For": "10.0.0.1"})
            assert resp.status_code == 200

        resp = client.get("/api/feed", headers={"X-Forwarded-For": "10.0.0.1"})
        assert resp.status_code == 429

        # IP 2 should still have full quota
        for _ in range(2):
            resp = client.get("/api/feed", headers={"X-Forwarded-For": "10.0.0.2"})
            assert resp.status_code == 200

    def test_invalid_bearer_token_uses_ip_bucket(self):
        """Malformed bearer tokens do not bypass anonymous IP limits."""
        from starlette.testclient import TestClient

        app = _make_test_app(anon_limit="2/minute", auth_limit="10/minute")
        client = TestClient(app)
        headers = {
            "Authorization": "Bearer not-a-jwt",
            "X-Forwarded-For": "10.0.0.60",
        }

        for _ in range(2):
            resp = client.get("/api/feed", headers=headers)
            assert resp.status_code == 200

        resp = client.get("/api/feed", headers=headers)
        assert resp.status_code == 429

    def test_429_response_format(self):
        """429 response has correct JSON body and Retry-After header."""
        from starlette.testclient import TestClient
        app = _make_test_app(anon_limit="1/minute")
        client = TestClient(app)

        # Use up the limit
        client.get("/api/feed")

        # Trigger 429
        resp = client.get("/api/feed")
        assert resp.status_code == 429

        # Check JSON body
        body = resp.json()
        assert "detail" in body
        assert "retry_after" in body
        assert isinstance(body["retry_after"], int)
        assert body["retry_after"] >= 1

        # Check Retry-After header
        assert "Retry-After" in resp.headers
        assert int(resp.headers["Retry-After"]) >= 1

    def test_rate_limit_applies_across_endpoints(self):
        """Rate limit is per key (IP/user), not per endpoint."""
        from starlette.testclient import TestClient
        app = _make_test_app(anon_limit="3/minute")
        client = TestClient(app)

        # Mix requests across endpoints — all count toward the same bucket
        client.get("/api/feed", headers={"X-Forwarded-For": "10.0.0.99"})
        client.get("/api/events/1", headers={"X-Forwarded-For": "10.0.0.99"})
        client.get("/api/feed", headers={"X-Forwarded-For": "10.0.0.99"})

        # 4th request should be rate limited regardless of path
        resp = client.get("/api/events/1", headers={"X-Forwarded-For": "10.0.0.99"})
        assert resp.status_code == 429

    def test_rate_limit_fail_open_when_storage_raises(self):
        """Storage errors fail open so Redis outages do not block traffic."""
        import app.utils.rate_limit as rl_mod
        from starlette.testclient import TestClient

        class FailingLimiter:
            def hit(self, *args, **kwargs):
                raise RuntimeError("storage unavailable")

        rl_mod._rate_limiter = FailingLimiter()

        app = _make_test_app(anon_limit="1/minute")
        client = TestClient(app)

        for _ in range(3):
            resp = client.get("/api/feed", headers={"X-Forwarded-For": "10.0.0.70"})
            assert resp.status_code == 200

    def test_fixed_window_resets_after_boundary(self):
        """A fixed-window limit blocks bursts, then permits after reset."""
        from starlette.testclient import TestClient

        app = _make_test_app(anon_limit="2/second")
        client = TestClient(app)
        headers = {"X-Forwarded-For": "10.0.0.80"}

        assert client.get("/api/feed", headers=headers).status_code == 200
        assert client.get("/api/events/1", headers=headers).status_code == 200
        assert client.get("/api/feed", headers=headers).status_code == 429

        time.sleep(1.1)

        assert client.get("/api/feed", headers=headers).status_code == 200
