"""TRUTH ship: a held game can keep its one-second fresh refresh without the API
refusing it.

WHAT WAS WRONG. A held game's page re-reads ``GET /api/events/{id}?fresh=true``
and ``GET /api/events/{id}/history?...&fresh=true`` once a second each — 120
requests a minute from one open page. The limiter gave an anonymous reader 60 a
minute and a signed-in one 120, for EVERYTHING. Replayed against the production
middleware (2026-09-28): anonymous 120 paired/min → 60 served, 60 refused, the
first refusal at second 30; signed in, the page's 7 opening requests were the
overflow.

WHAT SHIPPED. Those two reads, and nothing else, spend their own per-caller
180/minute bucket, shared across every event id. The 60/120 bucket is untouched
for every other request, and admin / trusted-address callers keep their own.

Every behavioural test here runs on BOTH limiter paths — the async-Redis counter
production uses and the in-memory limiter dev/CI falls back to — because they
pick the ceiling in two separate branches of the middleware and one can drift
from the other silently. The shipped ceilings are used throughout: the defect was
a mismatch between two real numbers (the page's cadence and the ceiling), so a
test at a lowered ceiling could not show it.
"""

from __future__ import annotations

import base64
import json
import re
import types

import pytest
from fastapi import FastAPI
from starlette.requests import Request
from starlette.testclient import TestClient

import app.utils.rate_limit as rl_mod
from app.utils.rate_limit import RateLimitMiddleware, _is_fresh_event_read

READER = "203.0.113.50"
TRUSTED = "198.51.100.7"

#: A fixed clock for the Redis path, mid-window, so a bucket boundary can never
#: fall inside a test and reset the count it is asserting on. (The memory path
#: anchors its window at the first hit, so it needs no freezing.)
_FROZEN_NOW = 1_800_000_000 + 20


class _KeyedAsyncRedis:
    """An async-redis stand-in that keeps a real count PER KEY, so tests can see
    which bucket a request was charged to — the whole question here."""

    def __init__(self):
        self.counts: dict[str, int] = {}

    async def incr(self, key):
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]

    async def expire(self, key, seconds):
        return True


@pytest.fixture(params=["redis", "memory"])
def limiter_path(request, monkeypatch):
    """Run the test on one of the two limiter paths. Yields the fake Redis (its
    per-key counts) on the Redis path, None on the memory path."""
    monkeypatch.delenv("BYPASS_RATE_LIMITS", raising=False)
    monkeypatch.delenv("RATE_LIMIT_TRUSTED_IPS", raising=False)
    if request.param == "redis":
        fake = _KeyedAsyncRedis()
        monkeypatch.setattr(rl_mod, "_get_async_rl_redis", lambda: fake)
        monkeypatch.setattr(
            rl_mod, "time", types.SimpleNamespace(time=lambda: float(_FROZEN_NOW))
        )
        yield fake
    else:
        monkeypatch.setattr(rl_mod, "_get_async_rl_redis", lambda: None)
        yield None


def _make_app() -> FastAPI:
    """The two polled routes with the real signatures' relevant half, plus an
    ordinary route and a non-polled event sub-route, behind the real middleware
    at its SHIPPED ceilings."""
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware)

    @app.get("/api/events/{event_id}")
    async def detail(event_id: int, fresh: bool = False):
        return {"id": event_id, "fresh": fresh}

    @app.get("/api/events/{event_id}/history")
    async def history(event_id: int, hours: int = 24, fresh: bool = False):
        return {"id": event_id, "fresh": fresh}

    @app.get("/api/events/{event_id}/game-markets")
    async def game_markets(event_id: int, fresh: bool = False):
        return {"id": event_id}

    @app.post("/api/events/{event_id}")
    async def detail_post(event_id: int, fresh: bool = False):
        return {"id": event_id}

    @app.get("/api/feed")
    async def feed():
        return {"ok": True}

    return app


def _jwt(uid: str) -> str:
    def seg(obj):
        return base64.urlsafe_b64encode(json.dumps(obj).encode()).rstrip(b"=").decode()

    return f"{seg({'alg': 'HS256'})}.{seg({'uid': uid})}.c2ln"


def _trust_test_tokens(monkeypatch):
    """A LOCAL fake authority that verifies the test's tokens by reading their
    uid (the middleware trusts no unverified token by default, Queue 303)."""
    monkeypatch.setattr(rl_mod, "_trusted_uid_resolver", rl_mod._extract_uid_from_token)


def _held_game_minute(client, headers, event_id=4242):
    """One minute of the held-game page: a fresh detail and a fresh history read
    every second. Returns the status codes in order."""
    codes = []
    for _second in range(60):
        codes.append(
            client.get(
                f"/api/events/{event_id}?fresh=true", headers=headers
            ).status_code
        )
        codes.append(
            client.get(
                f"/api/events/{event_id}/history?hours=24&fresh=true", headers=headers
            ).status_code
        )
    return codes


# ---------------------------------------------------------------------------
# The ship: a held game's minute of fresh reads is served in full
# ---------------------------------------------------------------------------


class TestAHeldGameMinuteIsServed:
    def test_anonymous_reader_gets_all_120_paired_reads(self, limiter_path):
        """The replayed case: before this, 60 of these 120 were refused."""
        client = TestClient(_make_app())
        codes = _held_game_minute(client, {"X-Forwarded-For": READER})
        assert codes.count(429) == 0, (
            f"{codes.count(429)} of 120 held-game fresh reads refused; first at "
            f"request {codes.index(429) + 1 if 429 in codes else None}"
        )

    def test_signed_in_reader_gets_opening_requests_plus_the_minute(
        self, limiter_path, monkeypatch
    ):
        """The replayed signed-in case: 7 opening requests + 120 fresh reads gave
        7 refusals. The opening requests are ordinary reads in the 120 bucket."""
        _trust_test_tokens(monkeypatch)
        client = TestClient(_make_app())
        headers = {
            "Authorization": f"Bearer {_jwt('reader-1')}",
            "X-Forwarded-For": READER,
        }
        opening = [client.get("/api/events/4242", headers=headers).status_code]
        opening += [
            client.get("/api/feed", headers=headers).status_code for _ in range(6)
        ]
        codes = _held_game_minute(client, headers)
        assert opening.count(429) == 0
        assert codes.count(429) == 0

    def test_the_fresh_minute_leaves_the_ordinary_budget_whole(self, limiter_path):
        """The fresh bucket is SEPARATE, not a bigger shared one: after a full
        fresh minute the reader still has exactly their 60 ordinary requests."""
        client = TestClient(_make_app())
        headers = {"X-Forwarded-For": READER}
        _held_game_minute(client, headers)
        ordinary = [
            client.get("/api/feed", headers=headers).status_code for _ in range(61)
        ]
        assert ordinary[:60] == [200] * 60
        assert ordinary[60] == 429


# ---------------------------------------------------------------------------
# Still a ceiling: one budget per caller, across every event
# ---------------------------------------------------------------------------


class TestTheFreshBudgetIsACeiling:
    def test_181st_fresh_read_is_refused(self, limiter_path):
        client = TestClient(_make_app())
        headers = {"X-Forwarded-For": READER}
        codes = [
            client.get("/api/events/7?fresh=true", headers=headers).status_code
            for _ in range(181)
        ]
        assert codes[:180] == [200] * 180
        assert codes[180] == 429

    def test_one_budget_shared_across_every_event_id(self, limiter_path):
        """No per-event bucket: walking ids must not multiply the budget. 180
        fresh reads over 180 DIFFERENT events exhaust it; a new id is refused."""
        client = TestClient(_make_app())
        headers = {"X-Forwarded-For": READER}
        codes = []
        for event_id in range(1, 181):
            path = f"/api/events/{event_id}"
            if event_id % 2:
                path += "/history"
            codes.append(client.get(f"{path}?fresh=true", headers=headers).status_code)
        assert codes == [200] * 180
        assert (
            client.get("/api/events/99999?fresh=true", headers=headers).status_code
            == 429
        )

    def test_a_refused_fresh_read_says_its_own_ceiling(self, limiter_path):
        client = TestClient(_make_app())
        headers = {"X-Forwarded-For": READER}
        for _ in range(180):
            client.get("/api/events/7?fresh=true", headers=headers)
        resp = client.get("/api/events/7?fresh=true", headers=headers)
        assert resp.status_code == 429
        assert "180" in resp.json()["detail"]
        assert int(resp.headers["Retry-After"]) >= 1

    def test_different_callers_have_independent_fresh_budgets(self, limiter_path):
        client = TestClient(_make_app())
        for _ in range(180):
            client.get("/api/events/7?fresh=true", headers={"X-Forwarded-For": READER})
        other = client.get(
            "/api/events/7?fresh=true", headers={"X-Forwarded-For": "203.0.113.51"}
        )
        assert other.status_code == 200


# ---------------------------------------------------------------------------
# The boundary: everything that is NOT a fresh detail/history GET stays ordinary
# ---------------------------------------------------------------------------


def _request(path: str, query: str = "", method: str = "GET") -> Request:
    return Request(
        {
            "type": "http",
            "method": method,
            "path": path,
            "query_string": query.encode(),
            "headers": [],
        }
    )


class TestTheBoundary:
    @pytest.mark.parametrize(
        "path,query",
        [
            ("/api/events/1", "fresh=true"),
            ("/api/events/123456", "fresh=true"),
            ("/api/events/1/history", "hours=24&fresh=true"),
            ("/api/events/1/history", "fresh=true&range=since_start&hours=6"),
        ],
    )
    def test_the_polled_shapes_are_fresh_reads(self, path, query):
        assert _is_fresh_event_read(_request(path, query)) is True

    @pytest.mark.parametrize(
        "path,query,method",
        [
            ("/api/events/1", "", "GET"),  # the ordinary detail read
            ("/api/events/1", "fresh=false", "GET"),
            ("/api/events/1", "fresh=true&fresh=true", "GET"),  # repeated
            ("/api/events/1", "fresh=true&fresh=false", "GET"),
            ("/api/events/1", "fresh=", "GET"),
            ("/api/events/1", "fresh=true", "POST"),
            ("/api/events/1", "fresh=true", "HEAD"),
            ("/api/events/1/", "fresh=true", "GET"),  # trailing slash
            ("/api/events/1/history/", "fresh=true", "GET"),
            ("/api/events/1/game-markets", "fresh=true", "GET"),
            ("/api/events/1/related-futures", "fresh=true", "GET"),
            ("/api/events/1/history/extra", "fresh=true", "GET"),
            ("/api/events/abc", "fresh=true", "GET"),
            ("/api/events/-1", "fresh=true", "GET"),
            ("/api/events/search", "fresh=true", "GET"),
            ("/api/events", "fresh=true", "GET"),
            ("/api/events/", "fresh=true", "GET"),
            ("/api/eventsX/1", "fresh=true", "GET"),
            ("/api/feed", "fresh=true", "GET"),
            ("/api/admin/events/1", "fresh=true", "GET"),
            ("/x/api/events/1", "fresh=true", "GET"),
        ],
    )
    def test_everything_else_is_ordinary(self, path, query, method):
        assert _is_fresh_event_read(_request(path, query, method)) is False

    def test_a_non_fresh_event_read_still_spends_the_ordinary_budget(
        self, limiter_path
    ):
        """Integration arm of the boundary: `fresh=false` on the polled route and
        `fresh=true` on a non-polled sub-route both exhaust the ordinary 60."""
        client = TestClient(_make_app())
        headers = {"X-Forwarded-For": READER}
        codes = []
        for i in range(61):
            path = (
                "/api/events/7?fresh=false"
                if i % 2
                else "/api/events/7/game-markets?fresh=true"
            )
            codes.append(client.get(path, headers=headers).status_code)
        assert codes[:60] == [200] * 60
        assert codes[60] == 429

    @pytest.mark.parametrize(
        "raw",
        [
            "true",
            "True",
            "TRUE",
            "1",
            "yes",
            "YES",
            "on",
            "t",
            "y",
            "false",
            "False",
            "0",
            "no",
            "off",
            "f",
            "n",
            "",
            "2",
            "truee",
            " true",
            "tru",
        ],
    )
    def test_fresh_means_what_the_route_parses_as_true(self, raw):
        """Parity with the ROUTE, not with a list somebody typed: whatever
        FastAPI reads as `fresh=True` is a fresh read, and nothing else is."""
        app = FastAPI()

        @app.get("/api/events/{event_id}")
        async def detail(event_id: int, fresh: bool = False):
            return {"fresh": fresh}

        resp = TestClient(app).get("/api/events/1", params={"fresh": raw})
        route_says_fresh = resp.status_code == 200 and resp.json()["fresh"] is True
        query = f"fresh={raw}".replace(" ", "%20")
        assert (
            _is_fresh_event_read(_request("/api/events/1", query)) is route_says_fresh
        )


class TestTheBoundaryMatchesTheRealRouteTable:
    """The pattern names two routes by path; if a route is renamed or a new one
    grows into the pattern, these fail rather than the budget silently moving."""

    @staticmethod
    def _get_routes():
        from fastapi.routing import APIRoute

        from app.main import app

        return [r for r in app.routes if isinstance(r, APIRoute) and "GET" in r.methods]

    def test_exactly_the_two_polled_routes_fall_inside_the_pattern(self):
        inside = sorted(
            {
                r.path
                for r in self._get_routes()
                if re.fullmatch(
                    rl_mod._FRESH_READ_PATH_PATTERN, re.sub(r"\{[^}]+\}", "123", r.path)
                )
            }
        )
        assert inside == ["/api/events/{event_id}", "/api/events/{event_id}/history"]

    def test_both_polled_routes_take_a_boolean_fresh_query(self):
        by_path = {r.path: r for r in self._get_routes()}
        for path in ("/api/events/{event_id}", "/api/events/{event_id}/history"):
            params = {p.name: p for p in by_path[path].dependant.query_params}
            assert "fresh" in params, f"{path} no longer takes `fresh`"
            assert params["fresh"].field_info.annotation is bool


# ---------------------------------------------------------------------------
# Admin / trusted / identity behaviour is unchanged (read off the Redis keys)
# ---------------------------------------------------------------------------


@pytest.fixture
def redis_keys(monkeypatch):
    fake = _KeyedAsyncRedis()
    monkeypatch.delenv("BYPASS_RATE_LIMITS", raising=False)
    monkeypatch.delenv("RATE_LIMIT_TRUSTED_IPS", raising=False)
    monkeypatch.setattr(rl_mod, "_get_async_rl_redis", lambda: fake)
    monkeypatch.setattr(
        rl_mod, "time", types.SimpleNamespace(time=lambda: float(_FROZEN_NOW))
    )
    return fake


def _bucket(key: str) -> str:
    return f"rl:{key}:{_FROZEN_NOW // 60}"


class TestWhichBucketIsCharged:
    def test_anonymous_fresh_read_charges_the_ip_fresh_bucket(self, redis_keys):
        TestClient(_make_app()).get(
            "/api/events/1?fresh=true", headers={"X-Forwarded-For": READER}
        )
        assert redis_keys.counts == {_bucket(f"fresh:{READER}"): 1}

    def test_verified_user_fresh_read_charges_the_user_fresh_bucket(
        self, redis_keys, monkeypatch
    ):
        _trust_test_tokens(monkeypatch)
        TestClient(_make_app()).get(
            "/api/events/1/history?fresh=true",
            headers={
                "Authorization": f"Bearer {_jwt('u9')}",
                "X-Forwarded-For": READER,
            },
        )
        assert redis_keys.counts == {_bucket("fresh:user:u9"): 1}

    def test_unverified_token_cannot_choose_a_user_fresh_bucket(self, redis_keys):
        """Queue 303 holds on the new bucket: a forged uid keys by IP."""
        TestClient(_make_app()).get(
            "/api/events/1?fresh=true",
            headers={
                "Authorization": f"Bearer {_jwt('forged')}",
                "X-Forwarded-For": READER,
            },
        )
        assert redis_keys.counts == {_bucket(f"fresh:{READER}"): 1}

    def test_trusted_address_stays_on_its_own_ceiling(self, redis_keys, monkeypatch):
        monkeypatch.setenv("RATE_LIMIT_TRUSTED_IPS", TRUSTED)
        TestClient(_make_app()).get(
            "/api/events/1?fresh=true", headers={"X-Forwarded-For": TRUSTED}
        )
        assert redis_keys.counts == {_bucket(f"trusted:{TRUSTED}"): 1}

    def test_ordinary_read_still_charges_the_ordinary_bucket(self, redis_keys):
        TestClient(_make_app()).get(
            "/api/events/1", headers={"X-Forwarded-For": READER}
        )
        assert redis_keys.counts == {_bucket(READER): 1}

    def test_shipped_ceilings_are_unchanged(self):
        assert rl_mod.ANON_RATE_LIMIT == "60/minute" and rl_mod._ANON_MAX == 60
        assert rl_mod.AUTH_RATE_LIMIT == "120/minute" and rl_mod._AUTH_MAX == 120
        assert rl_mod.ADMIN_RATE_LIMIT == "300/minute" and rl_mod._ADMIN_MAX == 300
        assert rl_mod.TRUSTED_RATE_LIMIT == "600/minute" and rl_mod._TRUSTED_MAX == 600
        assert rl_mod.FRESH_READ_RATE_LIMIT == "180/minute"
        assert rl_mod._FRESH_READ_MAX == 180
