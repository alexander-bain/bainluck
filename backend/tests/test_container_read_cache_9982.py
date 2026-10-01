"""#9982 — the NFL Week 4 hub serves at once, on open and on Back.

SHIP: a reader who opens the NFL Week 4 hub, or comes Back to it from a game,
sees the games right away instead of "Loading collection…". Pillar: DISCOVER /
FORMATTING.

Week 4 (3,479 members) took ~5 s to hydrate on every request and the web hub
re-reads on every Back. What is pinned here, against ``GET /api/containers/{slug}``
with the #9636 session double and hubs:

* **same bytes** — a cached serve is byte-for-byte the body the uncached build
  renders, so the cache changes when a reader waits, never what they read;
* **a fresh entry skips the hydration, never the published read** — the
  revision is read on every request, and a republish is a miss at once;
* **stale is served at once and rebuilt once, in the background**; past its
  servable window an entry is never served;
* **two workers share one build** through Redis; concurrent cold readers on one
  worker share one build;
* **fails open** — a broken Redis is a slower hub, never an error;
* **the policy** — the feed's live / idle windows, capped by a scheduled
  game's kickoff, imported rather than copied.
"""

from __future__ import annotations

import asyncio
import json
import types
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import Response

from app.routes import containers as route
from app.utils import container_read_cache as cache
from app.utils import feed_cache
from app.utils import request_cache

from tests.test_container_hydrated_reader_9636 import (
    _cards_hydrated,
    _nfl_week,
    _Session,
)


class _FakeRedis:
    def __init__(self, *, broken=False):
        self.store = {}
        self.ttls = {}
        self.broken = broken
        self.gets = 0

    async def get(self, key):
        self.gets += 1
        if self.broken:
            raise ConnectionError("redis down")
        return self.store.get(key)

    async def set(self, key, value, ex=None):
        if self.broken:
            raise ConnectionError("redis down")
        self.store[key] = value
        self.ttls[key] = ex
        return True


class _YieldingSession(_Session):
    """Suspends on every statement, so concurrent requests interleave."""

    async def execute(self, sql, params=None):
        await asyncio.sleep(0)
        return await super().execute(sql, params)


@pytest.fixture
def clock(monkeypatch):
    now = [datetime.now(timezone.utc).timestamp()]
    monkeypatch.setattr(route, "time", types.SimpleNamespace(time=lambda: now[0]))
    return now


@pytest.fixture
def redis(monkeypatch):
    fake = _FakeRedis()

    async def _client():
        return fake

    monkeypatch.setattr(request_cache, "get_shared_async_redis", _client)
    return fake


@pytest.fixture(autouse=True)
def _enabled(monkeypatch):
    monkeypatch.setenv("CONTAINERS_READ_ENABLED", "true")
    monkeypatch.delenv("CONTAINERS_READ_CACHE_ENABLED", raising=False)
    route._reset_read_cache_for_tests()
    request_cache._reset_inflight_for_tests()
    yield
    route._reset_read_cache_for_tests()
    request_cache._reset_inflight_for_tests()


async def _drain_background():
    while request_cache._background_tasks:
        await asyncio.gather(*list(request_cache._background_tasks), return_exceptions=True)


async def _get(session, slug="nfl-2026-week-5", include_children=True):
    return await route.get_container(slug=slug, include_children=include_children, db=session)


def _session(revision=4, cls=_Session):
    hub, events, markets = _nfl_week(revision=revision)
    return cls(hub, events=events, markets=markets)


# ---------------------------------------------------------------------------
# The route
# ---------------------------------------------------------------------------


async def test_a_cached_serve_is_byte_for_byte_the_uncached_build(monkeypatch, redis, clock):
    first = await _get(_session())
    assert isinstance(first, Response)
    assert first.headers["X-Feed-Cache"] == "miss"
    second = await _get(_session())
    assert second.headers["X-Feed-Cache"] == "hit"
    assert second.body == first.body

    monkeypatch.setenv("CONTAINERS_READ_CACHE_ENABLED", "false")
    uncached = await _get(_session())
    assert isinstance(uncached, dict)
    assert first.body == route._render(uncached)
    assert json.loads(first.body) == json.loads(json.dumps(uncached, default=str))
    assert json.loads(first.body)["member_count"] == uncached["member_count"] > 0


async def test_the_kill_switch_hydrates_every_request(monkeypatch, redis, clock):
    monkeypatch.setenv("CONTAINERS_READ_CACHE_ENABLED", "false")
    for _ in range(2):
        session = _session()
        assert isinstance(await _get(session), dict)
        assert _cards_hydrated(session)
    assert redis.store == {}


async def test_a_fresh_entry_skips_the_hydration_but_never_the_published_read(redis, clock):
    await _get(_session())
    session = _session()
    resp = await _get(session)
    assert resp.headers["X-Feed-Cache"] == "hit"
    assert _cards_hydrated(session) == []
    # The revision is read on every request — that is what keys the entry.
    assert len(session.edge_reads()) == 1


async def test_a_republish_is_a_miss_at_once_and_serves_the_new_revision(redis, clock):
    first = await _get(_session(revision=4))
    session = _session(revision=5)
    resp = await _get(session)
    assert resp.headers["X-Feed-Cache"] == "miss"
    assert _cards_hydrated(session)
    assert json.loads(first.body)["revision"] == 4
    assert json.loads(resp.body)["revision"] == 5


async def test_the_scope_is_part_of_the_key(redis, clock):
    await _get(_session(), include_children=True)
    session = _session()
    resp = await _get(session, include_children=False)
    assert resp.headers["X-Feed-Cache"] == "miss"
    assert _cards_hydrated(session)


async def test_stale_is_served_at_once_and_rebuilt_once_in_the_background(
    monkeypatch, redis, clock
):
    first = await _get(_session())
    # Published to Redis too, as it is in production by the time anyone is
    # stale: the local copy and its shared twin must read as the SAME entry.
    await _drain_background()
    assert redis.store
    built = json.loads(first.body)
    # Week 5 carries a live game, so the payload ages on the LIVE windows.
    assert any(
        m["card"]["status"] == "live"
        for s in built["sections"] for m in s["members"] if m["type"] == "event"
    )
    clock[0] += cache.CONTAINER_READ_FRESH_TTL_LIVE_SECONDS + 1

    rebuilds = []
    # The rebuild is held at the door until both stale readers are served, so
    # the test does not depend on whether `asyncio.wait_for` yields to the loop
    # (it does on CI's Python 3.11, not on 3.12).
    gate = asyncio.Event()

    class _Maker:
        def __call__(self):
            return self

        async def __aenter__(self):
            await gate.wait()
            session = _session()
            rebuilds.append(session)
            return session

        async def __aexit__(self, *exc):
            return False

    from app.services import database

    monkeypatch.setattr(database, "async_session_maker", _Maker())

    session = _session()
    stale = await _get(session)
    assert stale.headers["X-Feed-Cache"] == "stale_hit"
    assert stale.body == first.body
    assert _cards_hydrated(session) == []
    # A second stale reader before the rebuild lands does not start another.
    assert (await _get(_session())).headers["X-Feed-Cache"] == "stale_hit"
    gate.set()
    await _drain_background()
    assert len(rebuilds) == 1
    assert _cards_hydrated(rebuilds[0])

    after = await _get(_session())
    assert after.headers["X-Feed-Cache"] == "hit"


async def test_a_rebuild_that_lands_during_the_shared_read_is_served_not_restarted(
    monkeypatch, redis, clock
):
    """CI's 3.11 found this: the shared read awaits, and a rebuild finishing
    on this worker in that gap must not be followed by a second one."""
    await _get(_session())
    clock[0] += cache.CONTAINER_READ_FRESH_TTL_LIVE_SECONDS + 1
    key = cache.container_read_cache_key("nfl-2026-week-5", 4, True)
    landed = cache.CachedRead(
        body=b'{"landed":true}', built_at=clock[0],
        fresh_until=clock[0] + 30, stale_until=clock[0] + 60,
    )
    real_get = redis.get

    async def _get_while_a_rebuild_lands(k):
        route._remember_local(key, landed)
        return await real_get(k)

    monkeypatch.setattr(redis, "get", _get_while_a_rebuild_lands)
    resp = await _get(_session())
    assert resp.headers["X-Feed-Cache"] == "hit"
    assert resp.body == landed.body
    assert request_cache.inflight_count() == 0


async def test_past_its_servable_window_an_entry_is_never_served(redis, clock):
    await _get(_session())
    clock[0] += cache.CONTAINER_READ_STALE_TTL_LIVE_SECONDS + 1
    session = _session()
    resp = await _get(session)
    assert resp.headers["X-Feed-Cache"] == "miss"
    assert _cards_hydrated(session)


async def test_another_workers_build_is_served_from_redis(redis, clock):
    first = await _get(_session())
    await _drain_background()
    assert redis.store, "the build is published to the shared tier"
    (key, ttl), = redis.ttls.items()
    assert key == cache.container_read_cache_key("nfl-2026-week-5", 4, True)
    assert ttl == cache.CONTAINER_READ_STALE_TTL_LIVE_SECONDS

    route._reset_read_cache_for_tests()  # a different worker
    session = _session()
    resp = await _get(session)
    assert resp.headers["X-Feed-Cache"] == "shared_hit"
    assert resp.body == first.body
    assert _cards_hydrated(session) == []


async def test_a_broken_redis_is_a_slower_hub_never_an_error(monkeypatch, clock):
    fake = _FakeRedis(broken=True)

    async def _client():
        return fake

    monkeypatch.setattr(request_cache, "get_shared_async_redis", _client)
    resp = await _get(_session())
    await _drain_background()
    assert resp.headers["X-Feed-Cache"] == "miss"
    assert json.loads(resp.body)["member_count"] > 0
    # The process-local tier still spares this worker's next Back.
    assert (await _get(_session())).headers["X-Feed-Cache"] == "hit"


async def test_concurrent_cold_readers_share_one_build(redis, clock):
    sessions = [_session(cls=_YieldingSession) for _ in range(3)]
    responses = await asyncio.gather(*(_get(s) for s in sessions))
    labels = sorted(r.headers["X-Feed-Cache"] for r in responses)
    assert labels == ["coalesced", "coalesced", "miss"]
    assert sum(1 for s in sessions if _cards_hydrated(s)) == 1
    assert len({r.body for r in responses}) == 1


async def test_a_state_with_no_members_is_not_cached(redis, clock):
    hub, events, markets = _nfl_week(publication="unpublished")
    resp = await _get(_Session(hub, events=events, markets=markets))
    assert isinstance(resp, dict) and resp["state"] == "unpublished"
    assert redis.store == {} and redis.gets == 0


# ---------------------------------------------------------------------------
# The policy and the envelope
# ---------------------------------------------------------------------------


def _payload(*cards):
    return {"sections": [{"members": [{"type": "event", "card": c} for c in cards]}]}


def test_the_windows_are_the_feeds_windows_imported_not_copied():
    assert cache.CONTAINER_READ_FRESH_TTL_SECONDS == feed_cache.FEED_RESPONSE_TTL_ANON_SECONDS
    assert cache.CONTAINER_READ_STALE_TTL_SECONDS == feed_cache.FEED_RESPONSE_STALE_TTL_SECONDS
    assert cache.CONTAINER_READ_FRESH_TTL_LIVE_SECONDS == feed_cache.FEED_RESPONSE_TTL_LIVE_SECONDS
    assert (
        cache.CONTAINER_READ_STALE_TTL_LIVE_SECONDS
        == feed_cache.FEED_RESPONSE_STALE_TTL_LIVE_SECONDS
    )


def test_one_live_game_puts_the_whole_payload_on_the_live_windows():
    t = 1_000_000.0
    idle = _payload({"status": "completed"})
    live = _payload({"status": "completed"}, {"status": "live"})
    assert cache.payload_deadlines(idle, t) == (
        t + cache.CONTAINER_READ_FRESH_TTL_SECONDS,
        t + cache.CONTAINER_READ_STALE_TTL_SECONDS,
    )
    assert cache.payload_deadlines(live, t) == (
        t + cache.CONTAINER_READ_FRESH_TTL_LIVE_SECONDS,
        t + cache.CONTAINER_READ_STALE_TTL_LIVE_SECONDS,
    )


def test_a_scheduled_kickoff_caps_the_life_of_the_payload():
    built = datetime(2026, 10, 4, 16, 58, tzinfo=timezone.utc)
    t = built.timestamp()
    soon = (built + timedelta(minutes=2)).isoformat()
    far = (built + timedelta(days=2)).isoformat()
    fresh, stale = cache.payload_deadlines(
        _payload({"status": "scheduled", "commence_time": far},
                 {"status": "scheduled", "commence_time": soon}),
        t,
    )
    cap = 120 + cache.CONTAINER_READ_FRESH_TTL_LIVE_SECONDS
    assert fresh == t + min(cache.CONTAINER_READ_FRESH_TTL_SECONDS, cap)
    assert stale == t + cap
    # A kickoff already past leaves only the live grace, never a negative life.
    past = (built - timedelta(hours=1)).isoformat()
    assert cache.payload_deadlines(
        _payload({"status": "scheduled", "commence_time": past}), t
    ) == (t + cache.CONTAINER_READ_FRESH_TTL_LIVE_SECONDS,) * 2


def test_an_unparseable_payload_gets_the_ordinary_windows_never_longer():
    t = 5.0
    ordinary = (t + cache.CONTAINER_READ_FRESH_TTL_SECONDS, t + cache.CONTAINER_READ_STALE_TTL_SECONDS)
    for payload in (None, [], {"sections": "x"}, _payload({"status": "scheduled", "commence_time": "soon"})):
        assert cache.payload_deadlines(payload, t) == ordinary


def test_the_envelope_round_trips_and_refuses_garbage():
    entry = cache.CachedRead(body=b'{"a":"\xc3\xa9\\n"}\n', built_at=1.5, fresh_until=31.5, stale_until=61.5)
    assert cache.decode_entry(cache.encode_entry(entry)) == entry
    # A real clock stamp survives exactly: a shared copy must never read as
    # newer (or older) than the local entry it was published from.
    stamped = cache.CachedRead(
        body=b"{}", built_at=1790820278.7646193, fresh_until=1790820308.7646193,
        stale_until=1790820338.7646193,
    )
    assert cache.decode_entry(cache.encode_entry(stamped)) == stamped
    for raw in (None, "text", b"not zlib", b"", __import__("zlib").compress(b"no header")):
        assert cache.decode_entry(raw) is None


def test_the_key_names_slug_revision_and_scope():
    key = cache.container_read_cache_key("nfl-2026-week-4", 2, True)
    assert key == "container_read:v1:nfl-2026-week-4:r2:all"
    assert cache.container_read_cache_key("nfl-2026-week-4", 3, True) != key
    assert cache.container_read_cache_key("nfl-2026-week-4", 2, False) != key
