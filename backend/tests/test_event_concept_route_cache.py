"""Guard tests for the /api/event/{key} whole-envelope cache (#1107).

The golf event-detail path recomputes the full uncached get_golf aggregation on
every request (~4-16s cold, never warms). The route now wraps the build in a
short-TTL Redis cache + stale fallback (mirrors routes/hub.py). These tests pin
the caching CONTRACT without a live DB/Redis:
  * a warm read is served from cache (the expensive build runs once), AND
  * a dead Redis / cache miss falls straight through to the live build (never
    worse than the pre-cache path), AND
  * a build error serves the last-good stale snapshot instead of 500-ing.
"""

from unittest.mock import patch

import pytest

from app.routes import event as event_route


class _FakeRedis:
    """Minimal in-memory Redis: get / setex over a dict, bytes values."""

    def __init__(self):
        self.store: dict[str, bytes] = {}

    def get(self, k):
        return self.store.get(k)

    def setex(self, k, ttl, v):
        self.store[k] = v.encode() if isinstance(v, str) else v


class _StubAdapter:
    def __init__(self, envelope, *, raises=False):
        self._envelope = envelope
        self._raises = raises
        self.calls = 0

    async def build_event(self, slug, db):
        self.calls += 1
        if self._raises:
            raise RuntimeError("boom")
        # Return a fresh copy each call so cache vs live are distinguishable.
        return {**self._envelope, "_build_n": self.calls}


@pytest.mark.asyncio
async def test_second_read_served_from_cache():
    adapter = _StubAdapter({"event": {"name": "The Open"}, "primary": {"competitors": []}})
    rc = _FakeRedis()
    with patch.object(event_route, "get_adapter", return_value=adapter), \
         patch("app.tasks.redis_state.get_redis_client", return_value=rc):
        first = await event_route.get_event_concept("event:golf:the-open", db=None)
        second = await event_route.get_event_concept("event:golf:the-open", db=None)

    # The expensive build ran exactly once; the warm read came from Redis.
    assert adapter.calls == 1
    assert first["_build_n"] == 1
    assert second["_build_n"] == 1
    # Both the primary and stale keys were written.
    assert "bainluck:event_concept:event:golf:the-open" in rc.store
    assert "bainluck:event_concept:event:golf:the-open:stale" in rc.store


@pytest.mark.asyncio
async def test_no_redis_falls_through_to_build():
    adapter = _StubAdapter({"event": {"name": "X"}, "primary": {"competitors": []}})
    with patch.object(event_route, "get_adapter", return_value=adapter), \
         patch("app.tasks.redis_state.get_redis_client", side_effect=RuntimeError("no redis")):
        out = await event_route.get_event_concept("event:golf:x", db=None)
    assert out["_build_n"] == 1
    assert adapter.calls == 1  # dead Redis == live build, never worse than before


@pytest.mark.asyncio
async def test_build_error_serves_stale():
    rc = _FakeRedis()
    # Seed a last-good stale snapshot.
    good = _StubAdapter({"event": {"name": "Good"}, "primary": {"competitors": []}})
    with patch.object(event_route, "get_adapter", return_value=good), \
         patch("app.tasks.redis_state.get_redis_client", return_value=rc):
        await event_route.get_event_concept("event:golf:o", db=None)
    # Now the primary key expires (drop it) but stale remains; build errors.
    rc.store.pop("bainluck:event_concept:event:golf:o", None)
    broken = _StubAdapter(None, raises=True)
    with patch.object(event_route, "get_adapter", return_value=broken), \
         patch("app.tasks.redis_state.get_redis_client", return_value=rc):
        out = await event_route.get_event_concept("event:golf:o", db=None)
    assert out["event"]["name"] == "Good"  # served the stale snapshot, not a 500


@pytest.mark.asyncio
async def test_build_error_no_stale_reraises():
    rc = _FakeRedis()
    broken = _StubAdapter(None, raises=True)
    with patch.object(event_route, "get_adapter", return_value=broken), \
         patch("app.tasks.redis_state.get_redis_client", return_value=rc):
        with pytest.raises(RuntimeError):
            await event_route.get_event_concept("event:golf:none", db=None)
