"""#1767 — the league mirror must REVALIDATE, not just be served.

The defect these pin: `GET /api/leagues/{sport_key}` cached with a 5-minute
primary and a 24-hour stale fallback, and the stale branch returned the mirror
while scheduling NOTHING. The build path was reached only when both slots missed,
so a league rebuilt once per 24 hours and served a stale copy for the other
23h55m — about 99.6% of loads.

It was measured in production an hour after the UX-P062 deploy: ten sampled
leagues all read `availability=stale, tier=None`, while an uncached key
(`baseball_kbo`) cold-built the complete current envelope. That pair is what
separates "the mirror is pinned" from "the build is broken" (gotcha #53), and it
is why these tests assert on SCHEDULING rather than on payload contents.

The cache-shape assertions here are deliberately about mechanism — which slot was
read, what was written, what was dispatched — because the payload contract is
already covered by `test_route_league_futures.py` and duplicating it would give
two graders one input (ruling 021, the thing this lane keeps closing).
"""

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from app.routes.league_futures import (
    LEAGUE_CACHE_PREFIX,
    LEAGUE_PRIMARY_TTL,
    LEAGUE_STALE_TTL,
    build_and_cache_league,
    is_empty_league,
    league_cache_keys,
)

pytestmark = pytest.mark.asyncio


class FakeRedis:
    """Enough Redis to exercise single-flight: get/setex/set-nx/eval/delete.

    `eval` implements exactly the compare-and-delete the release Lua does, so a
    release with the wrong token is a no-op here for the same reason it is in
    production. A fake that releases unconditionally would certify the #1678
    finding-1 bug as fixed.
    """

    def __init__(self, initial=None):
        self.store = dict(initial or {})
        self.writes = []

    def get(self, key):
        return self.store.get(key)

    def setex(self, key, ttl, value):
        self.store[key] = value
        self.writes.append((key, ttl))
        return True

    def set(self, key, value, nx=False, ex=None):
        if nx and key in self.store:
            return None
        self.store[key] = value
        return True

    def delete(self, *keys):
        for k in keys:
            self.store.pop(k, None)
        return True

    def eval(self, _script, _numkeys, key, token):
        if self.store.get(key) == token:
            del self.store[key]
            return 1
        return 0


def _payload(sections=None, games=(), results=(), availability="fresh"):
    return {
        "sport_key": "basketball_nba",
        "sections": sections if sections is not None else {"awards": [{"id": 1}]},
        "upcoming_games": list(games),
        "recent_results": list(results),
        "availability": availability,
        "tier": "standard",
    }


def _seed(redis, key_attr, payload):
    import json

    keys = league_cache_keys("basketball_nba")
    redis.store[getattr(keys, key_attr)] = json.dumps(payload)


class TestLegacyKeyNames:
    """The shared layout must reproduce the keys that are already live.

    Load-bearing: `cache_keys()` was adopted precisely because
    `<prefix><sport_key>` and `…:stale` are byte-identical to the names this route
    has used since #777. If that ever drifts, every live entry is orphaned in
    silence and every league cold-builds — which would look like a cache outage
    and read like a mystery.
    """

    async def test_primary_and_stale_match_the_names_live_since_777(self):
        keys = league_cache_keys("basketball_nba")
        assert keys.primary == "bainluck:league:basketball_nba"
        assert keys.stale == "bainluck:league:basketball_nba:stale"

    async def test_prefix_constant_is_the_one_in_the_keys(self):
        assert LEAGUE_CACHE_PREFIX == "bainluck:league:"
        assert league_cache_keys("x").primary.startswith(LEAGUE_CACHE_PREFIX)

    async def test_lock_key_is_namespaced_under_the_same_base(self):
        keys = league_cache_keys("baseball_mlb")
        assert keys.refresh_lock == "bainluck:league:baseball_mlb:refreshing"


class TestStaleServeSchedulesRevalidation:
    """The half that was missing."""

    async def test_stale_read_schedules_a_refresh(self, client):
        redis = FakeRedis()
        _seed(redis, "stale", _payload())
        sent = []

        with patch("app.routes.league_futures._redis_or_none", return_value=redis), \
             patch("app.tasks.celery_app.send_task", side_effect=lambda *a, **k: sent.append((a, k))):
            body = (await client.get("/api/leagues/basketball_nba")).json()

        assert body["availability"] == "stale", "the mirror must still declare itself"
        assert len(sent) == 1, "a stale serve must revalidate behind itself"
        name, kwargs = sent[0][0][0], sent[0][1]
        assert name == "app.tasks.refresh_league"
        assert kwargs["args"][0] == "basketball_nba"
        assert kwargs["queue"] == "background"

    async def test_the_owner_token_travels_with_the_dispatch(self, client):
        """#1678 finding 1: the route acquires, the worker releases."""
        redis = FakeRedis()
        _seed(redis, "stale", _payload())
        sent = []

        with patch("app.routes.league_futures._redis_or_none", return_value=redis), \
             patch("app.tasks.celery_app.send_task", side_effect=lambda *a, **k: sent.append((a, k))):
            await client.get("/api/leagues/basketball_nba")

        token = sent[0][1]["args"][1]
        keys = league_cache_keys("basketball_nba")
        assert token, "a producer that cannot name the token cannot release"
        assert redis.store[keys.refresh_lock] == token

    async def test_a_burst_produces_one_rebuild_not_one_per_reader(self, client):
        """Single-flight. Three readers behind one TTL expiry, one dispatch."""
        redis = FakeRedis()
        _seed(redis, "stale", _payload())
        sent = []

        with patch("app.routes.league_futures._redis_or_none", return_value=redis), \
             patch("app.tasks.celery_app.send_task", side_effect=lambda *a, **k: sent.append((a, k))):
            for _ in range(3):
                await client.get("/api/leagues/basketball_nba")

        assert len(sent) == 1, f"expected single-flight, got {len(sent)} dispatches"

    async def test_a_primary_hit_schedules_nothing(self, client):
        redis = FakeRedis()
        _seed(redis, "primary", _payload())
        sent = []

        with patch("app.routes.league_futures._redis_or_none", return_value=redis), \
             patch("app.tasks.celery_app.send_task", side_effect=lambda *a, **k: sent.append((a, k))):
            body = (await client.get("/api/leagues/basketball_nba")).json()

        assert body["availability"] == "fresh"
        assert sent == [], "a fresh hit has nothing to revalidate"

    async def test_a_failed_dispatch_releases_the_lock(self, client):
        """A dead broker costs the next reader a retry, never a wedged key."""
        redis = FakeRedis()
        _seed(redis, "stale", _payload())
        keys = league_cache_keys("basketball_nba")

        with patch("app.routes.league_futures._redis_or_none", return_value=redis), \
             patch("app.tasks.celery_app.send_task", side_effect=RuntimeError("broker down")):
            body = (await client.get("/api/leagues/basketball_nba")).json()

        assert body["availability"] == "stale", "a failed refresh must not error the page"
        assert keys.refresh_lock not in redis.store, "the lock must not outlive a failed dispatch"

    async def test_a_refresh_failure_never_errors_the_served_page(self, client):
        """Best-effort throughout: the caller already decided to serve the mirror."""
        redis = FakeRedis()
        _seed(redis, "stale", _payload())

        with patch("app.routes.league_futures._redis_or_none", return_value=redis), \
             patch(
                 "app.routes.league_futures.acquire_refresh_lock",
                 side_effect=RuntimeError("redis exploded"),
             ):
            resp = await client.get("/api/leagues/basketball_nba")

        assert resp.status_code == 200


class TestWhatGetsMirrored:
    """`build_and_cache_league` is the ONE builder for the cold path and the task."""

    async def test_cold_build_writes_both_slots_with_their_ttls(self, mock_db):
        redis = FakeRedis()
        await build_and_cache_league("basketball_nba", mock_db, redis)

        keys = league_cache_keys("basketball_nba")
        written = dict(redis.writes)
        assert written.get(keys.primary) == LEAGUE_PRIMARY_TTL
        assert written.get(keys.stale) == LEAGUE_STALE_TTL

    async def test_a_degraded_build_is_never_mirrored(self, mock_db):
        """An outage must not outlive its cause inside a 24h mirror."""
        redis = FakeRedis()
        mock_db.execute.side_effect = asyncio.TimeoutError()

        payload = await build_and_cache_league("basketball_nba", mock_db, redis)

        assert payload["availability"] == "degraded"
        assert redis.writes == [], "a degraded build must not be cached"

    async def test_an_empty_build_does_not_clobber_a_populated_mirror(self, mock_db):
        redis = FakeRedis()
        _seed(redis, "stale", _payload(sections={"awards": [{"id": 1}]}))

        payload = await build_and_cache_league("basketball_nba", mock_db, redis)

        assert is_empty_league(payload)
        assert redis.writes == [], "the rescue must have something to rescue"

    async def test_an_empty_build_DOES_write_when_the_mirror_is_also_empty(self, mock_db):
        """The deliberate divergence from `build_and_cache_hub`, and why.

        7 registered leagues genuinely have nothing (`wncaab`, `cfl`, `ufl`, …).
        Skipping the write whenever ANY stale entry exists would leave their
        primary slot permanently unset, so every request would fall to the stale
        branch and schedule another refresh — forever. Refusing to overwrite
        nothing with nothing protects no data and costs a rebuild per lock window.
        """
        redis = FakeRedis()
        _seed(redis, "stale", _payload(sections={}, availability="empty"))

        await build_and_cache_league("basketball_wncaab", mock_db, redis)

        keys = league_cache_keys("basketball_wncaab")
        assert keys.primary in dict(redis.writes), "an empty league must still go fresh"

    async def test_is_empty_league_counts_the_games_rails(self):
        """Alex's amendment: a league mid-season with a schedule and no futures is
        not empty. `availability` already encodes this; the mirror guard must agree
        or it would refuse to cache a real page."""
        assert is_empty_league(_payload(sections={}, games=[], results=[]))
        assert not is_empty_league(_payload(sections={}, games=[{"id": 1}]))
        assert not is_empty_league(_payload(sections={}, results=[{"id": 1}]))


class TestNoRedisIsNotAnError:
    async def test_route_serves_when_redis_is_unavailable(self, client):
        with patch("app.routes.league_futures._redis_or_none", return_value=None):
            resp = await client.get("/api/leagues/basketball_nba")
        assert resp.status_code == 200

    async def test_build_and_cache_tolerates_a_none_client(self, mock_db):
        payload = await build_and_cache_league("basketball_nba", mock_db, None)
        assert payload["sport_key"] == "basketball_nba"
