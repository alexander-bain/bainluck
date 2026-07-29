"""Queue 275 (#1475): route-level proof that every /api/feed return path emits
the truthful cache/singleflight/coverage diagnostics, and that CORS exposes them.

Drives each of get_feed's return branches deterministically by faking the
process-shared Redis client and (where needed) the singleflight primitives, then
asserts the three observability headers are present with a truthful singleflight
label. An early return is NEVER labelled ``leader``. Also proves an allowed
browser origin can read all seven feed/request headers cross-origin.
"""

import asyncio
import json

from app.utils import request_cache as _rc


class _FakeRedis:
    """Minimal async Redis fake driving get_feed's cache/singleflight branches.

    ``mode`` selects what ``.get`` returns:
    - ``fresh``: JSON payload for the primary key (fresh hit)
    - ``stale``: miss on primary, JSON payload on the ``:stale`` key
    - ``miss``: clean miss on both (drives a leader build)
    - ``error``: raise on ``.get`` (bounded_redis_call → failure → last-good)
    """

    def __init__(self, mode: str, payload: dict | None = None):
        self.mode = mode
        self._json = json.dumps(payload) if payload is not None else None

    async def get(self, key):
        if self.mode == "error":
            raise RuntimeError("redis down")
        if self.mode == "fresh":
            return None if key.endswith(":stale") else self._json
        if self.mode == "stale":
            return self._json if key.endswith(":stale") else None
        return None  # clean miss

    async def setex(self, *a, **k):
        return True


async def _async(value):
    """Coroutine wrapper so a plain fake stands in for an async factory."""
    return value


def _reset_rc():
    _rc._reset_last_good_for_tests()
    _rc._reset_inflight_for_tests()
    _rc._reset_shared_client_for_tests()


_CACHED_PAYLOAD = {
    "items": [
        {"type": "futures", "data": {"id": 1}},
        {"type": "event", "data": {"id": 2}},
    ],
    "total": 2,
    "limit": 200,
    "offset": 0,
    "has_more": False,
}


async def test_fresh_hit_emits_headers_singleflight_none(client, monkeypatch):
    _reset_rc()
    fake = _FakeRedis("fresh", _CACHED_PAYLOAD)
    monkeypatch.setattr(_rc, "get_shared_async_redis", lambda: _async(fake))

    resp = await client.get("/api/feed?limit=5")

    assert resp.status_code == 200
    assert resp.headers["x-feed-cache"] == "hit"
    assert resp.headers["x-feed-singleflight"] == "none"
    counts = resp.headers["x-feed-counts"]
    assert "total=2" in counts
    assert "type_futures=1" in counts and "type_event=1" in counts


async def test_stale_hit_emits_headers_singleflight_none(client, monkeypatch):
    _reset_rc()
    fake = _FakeRedis("stale", _CACHED_PAYLOAD)
    monkeypatch.setattr(_rc, "get_shared_async_redis", lambda: _async(fake))

    resp = await client.get("/api/feed?limit=5")

    assert resp.status_code == 200
    assert resp.headers["x-feed-cache"] == "stale_hit"
    assert resp.headers["x-feed-singleflight"] == "none"
    assert "total=2" in resp.headers["x-feed-counts"]


async def test_redis_error_last_good_emits_headers(client, monkeypatch):
    _reset_rc()
    fake = _FakeRedis("error")
    monkeypatch.setattr(_rc, "get_shared_async_redis", lambda: _async(fake))
    monkeypatch.setattr(_rc, "recall_last_good", lambda key, **k: dict(_CACHED_PAYLOAD))

    resp = await client.get("/api/feed?limit=5")

    assert resp.status_code == 200
    assert resp.headers["x-feed-cache"] == "last_good"
    # A Redis-error bail predates singleflight participation.
    assert resp.headers["x-feed-singleflight"] == "none"
    assert "total=2" in resp.headers["x-feed-counts"]


async def test_coalesced_waiter_emits_singleflight_coalesced(client, monkeypatch):
    _reset_rc()
    fake = _FakeRedis("miss")
    monkeypatch.setattr(_rc, "get_shared_async_redis", lambda: _async(fake))

    fut: asyncio.Future = asyncio.get_event_loop().create_future()
    fut.set_result(dict(_CACHED_PAYLOAD))
    monkeypatch.setattr(_rc, "begin_build", lambda key: (False, fut))

    resp = await client.get("/api/feed?limit=5")

    assert resp.status_code == 200
    assert resp.headers["x-feed-cache"] == "coalesced"
    assert resp.headers["x-feed-singleflight"] == "coalesced"
    assert "total=2" in resp.headers["x-feed-counts"]


async def test_waiter_last_good_distinguished_from_redis_last_good(client, monkeypatch):
    _reset_rc()
    fake = _FakeRedis("miss")
    monkeypatch.setattr(_rc, "get_shared_async_redis", lambda: _async(fake))

    fut: asyncio.Future = asyncio.get_event_loop().create_future()
    fut.set_result(None)  # leader produced nothing usable
    monkeypatch.setattr(_rc, "begin_build", lambda key: (False, fut))
    monkeypatch.setattr(_rc, "recall_last_good", lambda key, **k: dict(_CACHED_PAYLOAD))

    resp = await client.get("/api/feed?limit=5")

    assert resp.status_code == 200
    assert resp.headers["x-feed-cache"] == "last_good"
    # Distinguishable from the Redis-error last-good (singleflight=none) above.
    assert resp.headers["x-feed-singleflight"] == "waiter_last_good"


async def test_waiter_budget_exhausted_serves_unavailable_without_building(
    client, monkeypatch
):
    """Queue 280: when the one absolute request budget is exhausted, a waiter on
    a still-running leader must NOT start a second build (never labelled leader).
    With no last-good it returns the truthful empty ``unavailable`` terminal."""
    _reset_rc()
    fake = _FakeRedis("miss")
    monkeypatch.setattr(_rc, "get_shared_async_redis", lambda: _async(fake))

    live = asyncio.get_event_loop().create_future()  # leader still running
    monkeypatch.setattr(_rc, "begin_build", lambda key: (False, live))
    # Zero budget => remaining is 0 => the waiter never awaits or builds.
    monkeypatch.setattr(_rc, "FEED_TOTAL_BUDGET_MS", 0)

    resp = await client.get("/api/feed?limit=5")

    assert resp.status_code == 200
    assert resp.headers["x-feed-cache"] == "unavailable"
    assert resp.headers["x-feed-singleflight"] == "waiter_unavailable"
    body = resp.json()
    assert body["items"] == [] and body["total"] == 0
    live.cancel()  # silence the never-awaited leader future


async def test_waiter_budget_exhausted_prefers_last_good(client, monkeypatch):
    """With budget exhausted, a waiter serves bounded last-good in preference to
    the empty unavailable terminal — still without a second build."""
    _reset_rc()
    fake = _FakeRedis("miss")
    monkeypatch.setattr(_rc, "get_shared_async_redis", lambda: _async(fake))

    live = asyncio.get_event_loop().create_future()
    monkeypatch.setattr(_rc, "begin_build", lambda key: (False, live))
    monkeypatch.setattr(_rc, "FEED_TOTAL_BUDGET_MS", 0)
    monkeypatch.setattr(_rc, "recall_last_good", lambda key, **k: dict(_CACHED_PAYLOAD))

    resp = await client.get("/api/feed?limit=5")

    assert resp.status_code == 200
    assert resp.headers["x-feed-cache"] == "last_good"
    assert resp.headers["x-feed-singleflight"] == "waiter_last_good"
    live.cancel()


async def test_leader_build_is_the_only_leader_labelled_path(client, monkeypatch):
    _reset_rc()
    fake = _FakeRedis("miss")
    monkeypatch.setattr(_rc, "get_shared_async_redis", lambda: _async(fake))

    resp = await client.get("/api/feed?limit=5")

    assert resp.status_code == 200
    # Empty DB → miss → this request leads the build.
    assert resp.headers["x-feed-singleflight"] == "leader"
    assert "returned=0" in resp.headers["x-feed-counts"]


async def test_requires_auth_early_return_reports_diagnostics(client, monkeypatch):
    _reset_rc()
    fake = _FakeRedis("miss")
    monkeypatch.setattr(_rc, "get_shared_async_redis", lambda: _async(fake))

    resp = await client.get("/api/feed?my_teams_only=true")

    assert resp.status_code == 200
    assert resp.json()["requires_auth"] is True
    # Never labelled a leader; empty coverage reported honestly.
    assert resp.headers["x-feed-singleflight"] == "none"
    assert "returned=0" in resp.headers["x-feed-counts"]


async def test_no_pii_in_cached_path_headers(client, monkeypatch):
    _reset_rc()
    fake = _FakeRedis("fresh", _CACHED_PAYLOAD)
    monkeypatch.setattr(_rc, "get_shared_async_redis", lambda: _async(fake))

    resp = await client.get(
        "/api/feed?limit=5", headers={"x-session-id": "secret-session-42"}
    )

    blob = (
        resp.headers.get("x-feed-stages", "")
        + resp.headers.get("x-feed-counts", "")
        + resp.headers.get("x-feed-singleflight", "")
    ).lower()
    for banned in ("secret-session-42", "session", "u:", "s:", "@", "http"):
        assert banned not in blob


async def test_cors_exposes_all_seven_feed_headers(client, monkeypatch):
    """A browser on an allowed origin must be able to read all seven
    feed/request diagnostic headers cross-origin (Item 2)."""
    _reset_rc()
    fake = _FakeRedis("fresh", _CACHED_PAYLOAD)
    monkeypatch.setattr(_rc, "get_shared_async_redis", lambda: _async(fake))

    resp = await client.get(
        "/api/feed?limit=5", headers={"Origin": "https://bainluck.com"}
    )

    assert resp.status_code == 200
    exposed = resp.headers["access-control-expose-headers"].lower()
    for header in (
        "x-response-time",
        "x-request-id",
        "x-feed-elapsed-ms",
        "x-feed-cache",
        "x-feed-stages",
        "x-feed-counts",
        "x-feed-singleflight",
    ):
        assert header in exposed, f"CORS does not expose {header}"
