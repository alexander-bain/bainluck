"""#9982 — the collection hub warmer keeps a published hub built ahead of expiry.

Alex, iPhone build 34: "the Week 4 container was very slow to open". Production
2026-10-02 00:3xZ: the first read 4.50 s to first byte, the next two 0.52 s —
the request-path cache only stays warm while readers keep arriving, and every
republish (~35 min) is a new key.

Pinned here:
* the rebuild rule (`needs_rebuild`) in both directions;
* the cadence relation that keeps an idle non-live hub from lapsing, asserted
  against the beat entry and the cache's own windows rather than as numbers;
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
    assert entry["options"]["queue"] == "background"


def test_an_idle_non_live_hub_cannot_lapse_between_on_time_passes():
    """Rebuilt when under REFRESH_AHEAD_S remain, a pass arrives every period,
    so the entry still has REFRESH_AHEAD_S - period of life at the latest
    rebuild. That needs margin > period and margin < the whole stale life."""
    assert warmer.REFRESH_AHEAD_S > warmer.BEAT_PERIOD_S
    assert warmer.REFRESH_AHEAD_S < CONTAINER_READ_STALE_TTL_SECONDS


def test_a_late_message_expires_before_it_could_be_useless():
    expires = _beat()["options"]["expires"]
    assert warmer.BEAT_PERIOD_S < expires <= warmer.REFRESH_AHEAD_S


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
    }

    @asynccontextmanager
    async def _session_maker():
        yield SimpleNamespace()

    async def _discover(session, *, limit):
        assert limit == warmer.MAX_HUBS
        return SimpleNamespace(collections=[{"slug": s} for s in state["slugs"]])

    async def _read_published(session, slug):
        st, rev = state["published"][slug]
        return SimpleNamespace(state=st, revision=rev, container_id=1, slug=slug)

    async def _build_entry(session, published, include_children):
        assert include_children is True
        if published.slug in state["fail"]:
            raise RuntimeError("boom")
        state["built"].append(published.slug)
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
    key = container_read_cache_key("nfl-2026-week-4", 34, True)
    stored = decode_entry(rig["redis"].store[key])
    assert stored is not None and stored.body == b'{"slug":"nfl-2026-week-4"}'
    assert 0 < rig["redis"].ttls[key] <= 300


async def test_a_hub_a_reader_just_built_is_skipped(rig):
    now = time.time()
    key = container_read_cache_key("nfl-2026-week-4", 34, True)
    rig["redis"].store[key] = encode_entry(_entry(now, fresh_in=30, stale_in=270))
    summary = await warmer._warm_container_hubs()
    assert summary["skipped"] == ["nfl-2026-week-4"]
    assert rig["built"] == ["nfl-2026-week-5"]


async def test_a_republish_is_a_cold_key_even_with_the_old_revision_warm(rig):
    now = time.time()
    old = container_read_cache_key("nfl-2026-week-4", 33, True)
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
