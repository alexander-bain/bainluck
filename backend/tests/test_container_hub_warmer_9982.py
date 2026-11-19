"""#9982 — the collection hub warmer keeps a published hub built ahead of expiry.

Alex, iPhone build 34: "the Week 4 container was very slow to open". Production
2026-10-02 00:3xZ: the first read 4.50 s to first byte, the next two 0.52 s —
the request-path cache only stays warm while readers keep arriving, and every
republish (~35 min) is a new key.

Pinned here:
* the rebuild rule (`needs_rebuild`) in both directions;
* the cadence relation that keeps an idle non-live hub from lapsing, asserted
  against the beat entry and the cache's own windows rather than as numbers;
* the queue is `realtime`, because that relation holds only for ON-TIME passes
  (on `background` the after-check saw a ~4-minute hole and two 4.4 s misses),
  and the pass is bounded so it cannot hold a realtime slot for long;
* a pass writes the ROUTE's key and envelope (a warm entry under any other key
  is a cache nobody reads), skips a hub a reader just built, skips an
  unpublished one, and one failing hub never stops the others.
"""

from __future__ import annotations

import inspect
import time
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from app.routes import containers as route
from app.tasks import celery_app
from app.tasks import container_hub_warmer as warmer
from app.utils import container_corrections as corrections
from app.utils.container_read_cache import (
    CONTAINER_READ_FRESH_TTL_LIVE_SECONDS,
    CONTAINER_READ_STALE_TTL_SECONDS,
    CachedRead,
    container_read_cache_key,
    decode_entry,
    encode_entry,
)


def _entry(now: float, *, fresh_in: float, stale_in: float, body: bytes = b"{}") -> CachedRead:
    return CachedRead(body=body, built_at=now - 1, fresh_until=now + fresh_in, stale_until=now + stale_in)


# --- the rule -----------------------------------------------------------------

def test_no_entry_or_an_expired_one_is_rebuilt():
    now = 1_000.0
    assert warmer.needs_rebuild(None, now)
    assert warmer.needs_rebuild(_entry(now, fresh_in=-200, stale_in=-1), now)


def test_a_fresh_entry_is_left_alone():
    now = 1_000.0
    assert not warmer.needs_rebuild(_entry(now, fresh_in=10, stale_in=20), now)


def test_a_stale_entry_is_rebuilt_only_inside_the_refresh_ahead_margin():
    now = 1_000.0
    margin = warmer.REFRESH_AHEAD_S
    assert not warmer.needs_rebuild(_entry(now, fresh_in=-1, stale_in=margin + 5), now)
    assert warmer.needs_rebuild(_entry(now, fresh_in=-1, stale_in=margin - 5), now)


# --- the cadence ----------------------------------------------------------------

def _beat():
    return celery_app.conf.beat_schedule["warm-container-hubs"]


def test_the_beat_fires_at_the_period_the_module_reasons_about():
    entry = _beat()
    assert entry["task"] == "app.tasks.warm_container_hubs"
    assert float(entry["schedule"]) == float(warmer.BEAT_PERIOD_S)


def test_the_beat_rides_the_queue_that_delivers_its_period():
    """The no-lapse relation below assumes a pass every BEAT_PERIOD_S. On
    `background` (2026-10-02 08:49:37 -> 08:53:46Z, no pass; LAT-P112 p50 152 s /
    max 2,511 s against 120 s) the entry expired between passes and the first
    reader after a quiet spell paid the 4.4 s build anyway."""
    assert _beat()["options"]["queue"] == "realtime"


def test_an_idle_non_live_hub_cannot_lapse_between_on_time_passes():
    """Rebuilt when under REFRESH_AHEAD_S remain, a pass arrives every period,
    so the entry still has REFRESH_AHEAD_S - period of life at the latest
    rebuild. That needs margin > period and margin < the whole stale life."""
    assert warmer.REFRESH_AHEAD_S > warmer.BEAT_PERIOD_S
    assert warmer.REFRESH_AHEAD_S < CONTAINER_READ_STALE_TTL_SECONDS


def test_a_superseded_fire_is_dropped_not_queued():
    """One period, the `_EXPIRING_WARMER_BEATS` rule: a fire still waiting when
    its successor is published is superseded, so a worker-restart backlog
    drops instead of running passes back to back on `realtime`."""
    assert _beat()["options"]["expires"] == warmer.BEAT_PERIOD_S


#: The measured NFL Week 4 build, rounded up (production 2026-10-02: 4.40 /
#: 4.47 s first-byte on a miss, server wall 3,746 ms). The largest hub today.
WEEK4_BUILD_S = 5.0


def test_passes_never_stack_on_realtime():
    """A pass starts no build after PASS_BUDGET_S, so it holds a realtime slot
    for at most the budget plus one build — under one period, so passes never
    stack on the queue that carries the live price poll. Pins the RELATION
    only: the 15 s value is a judgement (a 40 s budget also passes)."""
    assert warmer.PASS_BUDGET_S + WEEK4_BUILD_S < warmer.BEAT_PERIOD_S


# --- a pass ---------------------------------------------------------------------

class FakeRedis:
    def __init__(self):
        self.store: dict = {}
        self.ttls: dict = {}

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value, ex=None):
        self.store[key] = value
        self.ttls[key] = ex


@pytest.fixture
def rig(monkeypatch):
    redis = FakeRedis()
    state = {
        "slugs": ["nfl-2026-week-4", "nfl-2026-week-5"],
        "published": {
            "nfl-2026-week-4": (corrections.READ_PUBLISHED, 34),
            "nfl-2026-week-5": (corrections.READ_PUBLISHED, 7),
        },
        "fail": set(),
        "built": [],
        "compact": {},
    }

    @asynccontextmanager
    async def _session_maker():
        yield SimpleNamespace()

    async def _discover(session, *, limit):
        assert limit == discovery.MAX_COLLECTIONS
        return SimpleNamespace(collections=[{"slug": s} for s in state["slugs"]])

    async def _read_published(session, slug, *, include_headers):
        assert include_headers
        st, rev = state["published"][slug]
        return corrections.PublishedRead(state=st, revision=rev, container_id=1, slug=slug)

    async def _build_entry(session, published, include_children, *, compact=False):
        assert include_children is True
        if published.slug in state["fail"]:
            raise RuntimeError("boom")
        state["built"].append(published.slug)
        state["compact"][published.slug] = compact
        now = time.time()
        return CachedRead(
            body=f'{{"slug":"{published.slug}"}}'.encode(),
            built_at=now, fresh_until=now + 60, stale_until=now + 300,
        )

    import app.services.container_discovery as discovery
    import app.services.database as database
    import app.tasks.redis_state as redis_state

    monkeypatch.setattr(database, "async_session_maker", _session_maker)
    monkeypatch.setattr(discovery, "discover_collections", _discover)
    monkeypatch.setattr(corrections, "read_published", _read_published)
    monkeypatch.setattr(route, "read_published", _read_published)
    monkeypatch.setattr(route, "_build_entry", _build_entry)
    monkeypatch.setattr(redis_state, "get_redis_client", lambda *a, **k: redis)
    monkeypatch.delenv("CONTAINER_HUB_WARMER_ENABLED", raising=False)
    monkeypatch.delenv("CONTAINERS_READ_CACHE_ENABLED", raising=False)
    state["redis"] = redis
    return state


async def test_a_cold_hub_is_built_under_the_routes_own_key(rig):
    summary = await warmer._warm_container_hubs()
    assert summary["status"] == "ok"
    assert summary["built"] == ["nfl-2026-week-4", "nfl-2026-week-5"]
    key = container_read_cache_key("nfl-2026-week-4", 34, True, compact=True)
    stored = decode_entry(rig["redis"].store[key])
    assert stored is not None and stored.body == b'{"slug":"nfl-2026-week-4"}'
    assert 0 < rig["redis"].ttls[key] <= 300
    assert rig["compact"]["nfl-2026-week-4"] is True
    assert container_read_cache_key("nfl-2026-week-4", 34, True) not in rig["redis"].store


async def test_a_non_nfl_hub_keeps_its_public_default_key(rig):
    slug = "mlb-2026-postseason"
    rig["slugs"] = [slug]
    rig["published"][slug] = (corrections.READ_PUBLISHED, 11)

    await warmer._warm_container_hubs()

    assert rig["compact"] == {slug: False}
    assert container_read_cache_key(slug, 11, True) in rig["redis"].store


async def test_a_bounded_pass_prefers_recent_nfl_weeks_and_keeps_other_hub_seats(rig):
    baseball = "mlb-2026-postseason"
    weeks = [f"nfl-2026-week-{week}" for week in (4, 5, 7, 8, 9, 10, 11, 12)]
    rig["slugs"] = [baseball, *weeks]
    rig["published"] = {slug: (corrections.READ_PUBLISHED, 1) for slug in rig["slugs"]}

    summary = await warmer._warm_container_hubs()

    assert summary["hubs"] == warmer.MAX_HUBS
    assert summary["built"] == [baseball, *reversed(weeks[-3:])]
    assert container_read_cache_key("nfl-2026-week-10", 1, True, compact=True) in rig["redis"].store


async def test_default_week_read_reuses_the_warmed_body(rig, monkeypatch):
    from app.utils import request_cache

    async def get_redis():
        return rig["redis"]

    async def bounded_read(read):
        return SimpleNamespace(is_ok=True, value=read())

    monkeypatch.setattr(request_cache, "get_shared_async_redis", get_redis)
    monkeypatch.setattr(request_cache, "bounded_redis_call", bounded_read)
    monkeypatch.setattr(route, "_local_entries", {})
    monkeypatch.setenv("CONTAINERS_READ_ENABLED", "true")
    await warmer._warm_container_hubs()
    rig["built"].clear()

    response = await route.get_container(
        slug="nfl-2026-week-4", include_children=True, db=SimpleNamespace()
    )

    assert response.headers["X-Feed-Cache"] == "shared_hit"
    assert response.body == b'{"slug":"nfl-2026-week-4"}'
    assert not rig["built"]


async def test_week_preview_is_available_while_the_response_is_still_building(rig, monkeypatch):
    from app.utils.container_week_preview import (
        PreparedWeekMarketPreview,
        WeekMarketPreview,
        decode_prepared_week_preview,
        prepared_week_preview_key,
    )

    slug = "nfl-2026-week-4"
    rig["slugs"] = [slug]
    response_key = container_read_cache_key(slug, 34, True, compact=True)
    preview_key = prepared_week_preview_key(response_key)
    prepared = PreparedWeekMarketPreview(time.time(), WeekMarketPreview([81], {11: 2}, {}, {81: "prop"}))
    original_build = route._build_entry

    async def prepare(session, published):
        assert published.slug == slug
        return prepared

    async def build(session, published, include_children, *, compact, prepared_preview):
        assert prepared_preview is prepared
        assert response_key not in rig["redis"].store
        assert decode_prepared_week_preview(rig["redis"].store[preview_key], time.time()) == prepared
        return await original_build(session, published, include_children, compact=compact)

    monkeypatch.setattr(route, "_prepare_week_market_preview", prepare)
    monkeypatch.setattr(route, "_build_entry", build)

    summary = await warmer._warm_container_hubs()

    assert summary["built"] == [slug]
    assert response_key in rig["redis"].store
    assert 0 < rig["redis"].ttls[preview_key] <= CONTAINER_READ_FRESH_TTL_LIVE_SECONDS


async def test_a_hub_a_reader_just_built_is_skipped(rig):
    now = time.time()
    key = container_read_cache_key("nfl-2026-week-4", 34, True, compact=True)
    rig["redis"].store[key] = encode_entry(_entry(now, fresh_in=30, stale_in=270))
    summary = await warmer._warm_container_hubs()
    assert summary["skipped"] == ["nfl-2026-week-4"]
    assert rig["built"] == ["nfl-2026-week-5"]


async def test_a_republish_is_a_cold_key_even_with_the_old_revision_warm(rig):
    now = time.time()
    old = container_read_cache_key("nfl-2026-week-4", 33, True, compact=True)
    rig["redis"].store[old] = encode_entry(_entry(now, fresh_in=30, stale_in=270))
    await warmer._warm_container_hubs()
    assert "nfl-2026-week-4" in rig["built"]


async def test_an_unpublished_hub_is_never_built(rig):
    rig["published"]["nfl-2026-week-5"] = ("unpublished", 7)
    summary = await warmer._warm_container_hubs()
    assert rig["built"] == ["nfl-2026-week-4"]
    assert "nfl-2026-week-5" in summary["skipped"]


async def test_one_failing_hub_does_not_stop_the_next(rig):
    rig["fail"].add("nfl-2026-week-4")
    summary = await warmer._warm_container_hubs()
    assert summary["failed"] == ["nfl-2026-week-4"]
    assert rig["built"] == ["nfl-2026-week-5"]
    assert summary["status"] == "partial"


async def test_a_pass_starts_no_build_after_its_budget(rig, monkeypatch):
    clock = {"t": 0.0}
    # The warmer's own `time` name only — patching `time.monotonic` itself would
    # freeze the event loop's clock too.
    monkeypatch.setattr(warmer, "time", SimpleNamespace(monotonic=lambda: clock["t"], time=time.time))
    built = rig["built"]

    real_build = route._build_entry

    async def _slow_build(session, published, include_children, *, compact=False):
        entry = await real_build(session, published, include_children, compact=compact)
        clock["t"] += warmer.PASS_BUDGET_S + 1
        return entry

    monkeypatch.setattr(route, "_build_entry", _slow_build)
    summary = await warmer._warm_container_hubs()
    assert built == ["nfl-2026-week-4"]
    assert summary["status"] == "partial"
    assert "nfl-2026-week-5" not in summary["skipped"]


async def test_the_kill_switch_builds_nothing(rig, monkeypatch):
    monkeypatch.setenv("CONTAINER_HUB_WARMER_ENABLED", "false")
    summary = await warmer._warm_container_hubs()
    assert summary["status"] == "disabled" and rig["built"] == []


async def test_the_route_cache_switch_also_stops_it(rig, monkeypatch):
    monkeypatch.setenv("CONTAINERS_READ_CACHE_ENABLED", "false")
    summary = await warmer._warm_container_hubs()
    assert summary["status"] == "disabled" and rig["built"] == []


def test_the_route_default_is_the_variant_the_warmer_builds():
    """The web hub and the iPhone request `/api/containers/{slug}` with no
    query, so `include_children` takes the route's default."""
    default = inspect.signature(route.get_container).parameters["include_children"].default
    assert getattr(default, "default", default) is True
    assert inspect.signature(route.get_container).parameters["compact"].default is True
