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
        self.ttls: dict[str, int] = {}

    def get(self, k):
        return self.store.get(k)

    def setex(self, k, ttl, v):
        self.ttls[k] = ttl
        self.store[k] = v.encode() if isinstance(v, str) else v

    def delete(self, k):
        self.ttls.pop(k, None)
        return int(self.store.pop(k, None) is not None)


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


# ---------------------------------------------------------------------------
# LAT-P014/#1107 — a MISS must not cost what a HIT costs.
#
# Only successful envelopes were cached, so a key resolving to nothing re-ran the
# adapter's full build every single time. MEASURED in production 2026-08-09,
# paired against a control on the same route 4-5s away: a bad golf key 404'd in
# 6,931-14,518ms and a bad tennis key in 7,923ms, where a bad CYCLING key — whose
# adapter proves absence from an in-memory config parse — 404'd in 290ms. Same
# route, same 404, ~25-50x apart: the cost is the work done before giving up.
# ---------------------------------------------------------------------------
class _MissAdapter:
    """An adapter whose build always resolves to nothing (the 404 path)."""

    def __init__(self):
        self.calls = 0

    async def build_event(self, slug, db):
        self.calls += 1
        return None


@pytest.mark.asyncio
async def test_a_miss_is_only_built_once():
    """The second request for a known-absent key must not re-run the build."""
    from fastapi import HTTPException

    adapter = _MissAdapter()
    rc = _FakeRedis()
    with patch.object(event_route, "get_adapter", return_value=adapter), \
         patch("app.tasks.redis_state.get_redis_client", return_value=rc):
        for _ in range(3):
            with pytest.raises(HTTPException) as exc:
                await event_route.get_event_concept("event:golf:nope-zqx", db=None)
            assert exc.value.status_code == 404

    assert adapter.calls == 1, (
        f"the absent-key build ran {adapter.calls} times — every repeat is paying "
        "the full adapter cost again, which is the 7-14.5s 404 this fixes"
    )


@pytest.mark.asyncio
async def test_a_negative_entry_is_short_lived():
    """A cached absence must expire quickly.

    The cost of caching a negative is that a key which becomes valid inside the
    window keeps 404ing. Pinned to the envelope's own TTL so the trade stays
    small and visible rather than drifting into a long stale-404 window.
    """
    adapter = _MissAdapter()
    rc = _FakeRedis()
    with patch.object(event_route, "get_adapter", return_value=adapter), \
         patch("app.tasks.redis_state.get_redis_client", return_value=rc):
        with pytest.raises(Exception):
            await event_route.get_event_concept("event:golf:nope-zqx", db=None)

    neg = [k for k in rc.store if k.endswith(":404")]
    assert neg, "the absence was not recorded, so every repeat re-runs the build"
    assert rc.ttls[neg[0]] <= 300, (
        f"negative TTL is {rc.ttls[neg[0]]}s — too long. A key that starts "
        "resolving would keep 404ing for that whole window."
    )


@pytest.mark.asyncio
async def test_a_negative_entry_is_never_served_as_a_200():
    """The sentinel must produce a 404, never a body.

    A negative entry sharing the envelope's key space is one careless read away
    from being deserialized and returned as content.
    """
    from fastapi import HTTPException

    adapter = _MissAdapter()
    rc = _FakeRedis()
    with patch.object(event_route, "get_adapter", return_value=adapter), \
         patch("app.tasks.redis_state.get_redis_client", return_value=rc):
        with pytest.raises(HTTPException):
            await event_route.get_event_concept("event:golf:nope-zqx", db=None)
        with pytest.raises(HTTPException) as exc:
            result = await event_route.get_event_concept("event:golf:nope-zqx", db=None)
            raise AssertionError(f"cached absence returned a 200 body: {result!r}")
        assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_a_key_that_starts_resolving_is_sticky_for_the_window_then_recovers():
    """The COST of negative caching, pinned as a decision rather than discovered.

    A key that 404s and then becomes valid keeps 404ing until its negative entry
    expires. That is inherent — the whole point is not to call the adapter — and
    it is the reason the TTL is short. Asserted in both halves so the trade is
    explicit and cannot silently grow:

      * WITHIN the window the stale 404 is served and the adapter is NOT called;
      * ONCE the entry expires the key resolves normally, and no negative is left
        behind afterwards.

    The alternative to accepting this is re-running a build that measured
    7-14.5s in production on every request for an absent key.
    """
    from fastapi import HTTPException

    rc = _FakeRedis()
    miss = _MissAdapter()
    with patch.object(event_route, "get_adapter", return_value=miss), \
         patch("app.tasks.redis_state.get_redis_client", return_value=rc):
        with pytest.raises(HTTPException):
            await event_route.get_event_concept("event:golf:late-bloomer", db=None)

    live = _StubAdapter({"event": {"name": "Late Bloomer"}, "primary": {"competitors": []}})

    # Half 1 — inside the window: still 404, and the build did NOT run.
    with patch.object(event_route, "get_adapter", return_value=live), \
         patch("app.tasks.redis_state.get_redis_client", return_value=rc):
        with pytest.raises(HTTPException) as exc:
            await event_route.get_event_concept("event:golf:late-bloomer", db=None)
    assert exc.value.status_code == 404
    assert live.calls == 0, (
        "the adapter ran despite a live negative entry — the entry is not "
        "actually short-circuiting, so the 7-14.5s cost is still being paid"
    )

    # Half 2 — the entry expires (drop it, as Redis would).
    rc.delete("bainluck:event_concept:event:golf:late-bloomer:404")
    with patch.object(event_route, "get_adapter", return_value=live), \
         patch("app.tasks.redis_state.get_redis_client", return_value=rc):
        got = await event_route.get_event_concept("event:golf:late-bloomer", db=None)

    assert got["event"]["name"] == "Late Bloomer", "the key never recovered"
    assert not [k for k in rc.store if k.endswith(":404")], (
        "a negative entry survived a successful build"
    )


@pytest.mark.asyncio
async def test_a_dead_redis_still_404s_rather_than_500s():
    """Observability must never change the status code.

    If the negative write throws, the request must still be a clean 404 — the
    caching is an optimisation, not part of the contract.
    """
    from fastapi import HTTPException

    class _ExplodingRedis(_FakeRedis):
        def setex(self, k, ttl, v):
            raise RuntimeError("redis down")

    adapter = _MissAdapter()
    with patch.object(event_route, "get_adapter", return_value=adapter), \
         patch("app.tasks.redis_state.get_redis_client", return_value=_ExplodingRedis()):
        with pytest.raises(HTTPException) as exc:
            await event_route.get_event_concept("event:golf:nope-zqx", db=None)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_a_negative_written_during_our_build_is_cleared_by_the_success():
    """The only interleaving in which the success-path `delete` does anything.

    In a single request the negative key was just read as absent, so deleting it
    is a no-op. It exists for the race: request A reads (absent), starts a slow
    build; request B for the same key resolves to nothing and writes a negative;
    A's build then succeeds. Without the delete, A's fresh envelope sits behind a
    negative entry written from staler information.

    Simulated by having the adapter write the negative key mid-build, which is
    exactly that interleaving. Without this the `delete` is untested code — a
    mutation removing it stayed green.
    """
    rc = _FakeRedis()
    neg_key = "bainluck:event_concept:event:golf:racy:404"

    class _RacyAdapter:
        calls = 0

        async def build_event(self, slug, db):
            _RacyAdapter.calls += 1
            # A concurrent request for the same key 404s while we are building.
            rc.setex(neg_key, 60, "404")
            return {"event": {"name": "Racy"}, "primary": {"competitors": []}}

    with patch.object(event_route, "get_adapter", return_value=_RacyAdapter()), \
         patch("app.tasks.redis_state.get_redis_client", return_value=rc):
        got = await event_route.get_event_concept("event:golf:racy", db=None)

    assert got["event"]["name"] == "Racy"
    assert neg_key not in rc.store, (
        "a negative entry written during the build survived the successful write "
        "— the next request 404s on a key we just proved resolves"
    )
