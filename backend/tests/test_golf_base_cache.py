"""Unit tests for the shared golf listing base (Queue 278, #1475/#1459).

Guards the LIVE implementation of the C71 golf contract
(``backend/scripts/evals/cold_feed_equivalence.py`` golf scenarios):

* the 300s feed-golf freshness boundary (a 301s payload is NOT fresh),
* the bounded last-good fallback (Redis stale / process-local),
* no DataGolf rebuild on a plain process restart (Redis still holds the base),
* one singleflight fill per process across concurrent feed response keys,
* a cancelled owner leaves a clean slot for exactly one replacement,
* a user-independent payload shape (no feed/personalization/score state).
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone

import pytest

from app.utils import golf_base as gb
from app.utils import request_cache as rc


NOW = datetime(2026, 7, 29, 12, 0, 0, tzinfo=timezone.utc)


def _tournament(**over):
    t = {
        "key": "the_open",
        "golfers": [
            {"name": "A", "probability": 0.31, "rank": 1, "movement_24h": 0.02}
        ],
        "market_ids": [11, 12],
        "market_sources": ["polymarket", "datagolf"],
        "h2h_matchups": [],
        "prop_markets": [],
        "schedule_status": "scheduled",
    }
    t.update(over)
    return t


def _envelope(age_s=0, tournaments=None):
    generated = NOW - timedelta(seconds=age_s)
    return {
        "schema_version": gb.GOLF_BASE_SCHEMA_VERSION,
        "generated_at": generated.isoformat(),
        "tournaments": tournaments if tournaments is not None else [_tournament()],
    }


class _FakeRedis:
    """Async Redis stand-in backed by a dict with an injectable fault mode."""

    def __init__(self, store=None, mode="ok"):
        self.store = dict(store or {})
        self.mode = mode
        self.gets = 0
        self.sets = 0

    async def get(self, key):
        self.gets += 1
        if self.mode == "down":
            raise ConnectionError("redis down")
        if self.mode == "hang":
            await asyncio.sleep(30)
        return self.store.get(key)

    async def set(self, key, value, ex=None):
        self.sets += 1
        self.store[key] = value
        return True


def _install(monkeypatch, client):
    async def _get():
        return client

    monkeypatch.setattr(rc, "get_shared_async_redis", _get)


def _boom_get_golf(monkeypatch):
    """Make the DataGolf rebuild path explode so any inline call fails the test."""

    async def _boom(db):
        raise AssertionError("get_golf (DataGolf rebuild) ran on the request path")

    monkeypatch.setattr("app.routes.golf.get_golf", _boom)


@pytest.fixture(autouse=True)
def _clean():
    rc._reset_last_good_for_tests()
    rc._reset_inflight_for_tests()
    gb._reset_l0_for_tests()
    yield
    rc._reset_last_good_for_tests()
    rc._reset_inflight_for_tests()
    gb._reset_l0_for_tests()


# --- validation + normalization ----------------------------------------------
def test_payload_valid_accepts_base_and_rejects_user_state():
    assert gb.payload_valid(_envelope()) is True
    assert gb.payload_valid({"personalized": True, "tournaments": []}) is False
    scored = _tournament()
    scored["score"] = 99
    assert gb.payload_valid({"tournaments": [scored]}) is False
    missing = _tournament()
    del missing["schedule_status"]
    assert gb.payload_valid({"tournaments": [missing]}) is False


def test_build_envelope_defaults_missing_keys_and_strips_forbidden():
    raw = {"key": "x", "golfers": [], "market_ids": [1], "market_sources": ["kalshi"]}
    env = gb.build_envelope(NOW, [raw])
    t = env["tournaments"][0]
    assert t["schedule_status"] is None
    assert t["h2h_matchups"] == []
    assert t["prop_markets"] == []
    assert gb.payload_valid(env)

    leaked = {**raw, "_marquee_pin": True, "score": 5, "reason": "x"}
    env2 = gb.build_envelope(NOW, [leaked])
    t2 = env2["tournaments"][0]
    assert "_marquee_pin" not in t2 and "score" not in t2 and "reason" not in t2
    assert gb.payload_valid(env2)


# --- freshness boundary ------------------------------------------------------
async def test_fresh_base_served_without_rebuild(monkeypatch):
    client = _FakeRedis({gb.GOLF_BASE_FRESH_KEY: json.dumps(_envelope(age_s=120))})
    _install(monkeypatch, client)
    _boom_get_golf(monkeypatch)

    tours, prov = await gb.get_golf_base(db=None, now=NOW)

    assert prov == gb.PROV_FRESH
    assert tours[0]["key"] == "the_open"
    assert client.sets == 0  # a fresh hit never republishes


async def test_300s_is_fresh_301s_is_last_good(monkeypatch):
    _boom_get_golf(monkeypatch)

    client = _FakeRedis({gb.GOLF_BASE_FRESH_KEY: json.dumps(_envelope(age_s=300))})
    _install(monkeypatch, client)
    _, prov = await gb.get_golf_base(None, NOW)
    assert prov == gb.PROV_FRESH

    gb._reset_l0_for_tests()
    client = _FakeRedis({gb.GOLF_BASE_FRESH_KEY: json.dumps(_envelope(age_s=301))})
    _install(monkeypatch, client)
    tours, prov = await gb.get_golf_base(None, NOW)
    assert prov == gb.PROV_LAST_GOOD  # 301s is bounded fallback, NOT fresh
    assert tours  # still served — no rebuild


async def test_restart_with_stale_redis_base_does_not_call_datagolf(monkeypatch):
    # A cold process (empty L0/last-good) with a stale-but-bounded Redis base
    # must serve last-good, never rebuild via DataGolf.
    client = _FakeRedis(
        {gb.GOLF_BASE_FRESH_KEY: json.dumps(_envelope(age_s=1800))}
    )
    _install(monkeypatch, client)
    _boom_get_golf(monkeypatch)

    tours, prov = await gb.get_golf_base(None, NOW)
    assert prov == gb.PROV_LAST_GOOD
    assert tours


async def test_fresh_key_expired_falls_to_last_good_key(monkeypatch):
    # Fresh key gone (>2h without precompute) but the durable last-good key holds.
    client = _FakeRedis(
        {gb.GOLF_BASE_LAST_GOOD_KEY: json.dumps(_envelope(age_s=3600))}
    )
    _install(monkeypatch, client)
    _boom_get_golf(monkeypatch)

    tours, prov = await gb.get_golf_base(None, NOW)
    assert prov == gb.PROV_LAST_GOOD
    assert tours


# --- Redis outage fallbacks --------------------------------------------------
async def test_redis_down_serves_process_local_last_good(monkeypatch):
    rc.remember_last_good("golf_base", _envelope(age_s=100))
    client = _FakeRedis(mode="down")
    _install(monkeypatch, client)
    _boom_get_golf(monkeypatch)

    tours, prov = await gb.get_golf_base(None, NOW)
    assert prov == gb.PROV_LAST_GOOD
    assert tours


async def test_redis_hang_is_bounded_then_serves_last_good(monkeypatch):
    rc.remember_last_good("golf_base", _envelope(age_s=100))
    client = _FakeRedis(mode="hang")
    _install(monkeypatch, client)
    _boom_get_golf(monkeypatch)

    loop = asyncio.get_running_loop()
    started = loop.time()
    tours, prov = await gb.get_golf_base(None, NOW)
    elapsed = loop.time() - started

    assert prov == gb.PROV_LAST_GOOD
    assert tours
    assert elapsed < 5.0  # bounded well under any router cutoff


# --- inline rebuild (genuine cold) -------------------------------------------
async def test_empty_redis_triggers_bounded_inline_fill_and_publishes(monkeypatch):
    client = _FakeRedis({})  # clean miss on both keys
    _install(monkeypatch, client)

    calls = {"n": 0}

    async def _fake_get_golf(db):
        calls["n"] += 1
        return {"tournaments": [_tournament(key="masters")]}

    monkeypatch.setattr("app.routes.golf.get_golf", _fake_get_golf)

    tours, prov = await gb.get_golf_base(None, NOW)
    assert prov == gb.PROV_INLINE
    assert calls["n"] == 1
    assert tours[0]["key"] == "masters"

    await asyncio.sleep(0.05)  # let the background publish run
    assert gb.GOLF_BASE_FRESH_KEY in client.store
    assert gb.GOLF_BASE_LAST_GOOD_KEY in client.store


async def test_two_response_keys_launch_one_shared_fill(monkeypatch):
    client = _FakeRedis({})
    _install(monkeypatch, client)

    calls = {"n": 0}
    started = asyncio.Event()
    release = asyncio.Event()

    async def _slow_get_golf(db):
        calls["n"] += 1
        started.set()
        await release.wait()
        return {"tournaments": [_tournament(key="masters")]}

    monkeypatch.setattr("app.routes.golf.get_golf", _slow_get_golf)

    leader = asyncio.ensure_future(gb.get_golf_base(None, NOW))
    await started.wait()  # leader is mid-rebuild
    waiter = asyncio.ensure_future(gb.get_golf_base(None, NOW))
    await asyncio.sleep(0.02)
    release.set()

    r_leader = await leader
    r_waiter = await waiter

    assert calls["n"] == 1  # ONE fill for two concurrent response keys
    assert r_leader[1] == gb.PROV_INLINE
    assert r_waiter[1] == gb.PROV_INLINE


async def test_cancelled_leader_leaves_clean_slot_for_one_replacement(monkeypatch):
    client = _FakeRedis({})
    _install(monkeypatch, client)

    calls = {"n": 0}

    async def _get_golf(db):
        i = calls["n"]
        calls["n"] += 1
        if i == 0:
            await asyncio.sleep(30)  # leader hangs -> will be cancelled
        return {"tournaments": [_tournament(key="masters")]}

    monkeypatch.setattr("app.routes.golf.get_golf", _get_golf)

    leader = asyncio.ensure_future(gb.get_golf_base(None, NOW))
    await asyncio.sleep(0.02)
    leader.cancel()
    with pytest.raises(asyncio.CancelledError):
        await leader

    assert rc.inflight_count() == 0  # slot cleared on cancellation

    tours, prov = await gb.get_golf_base(None, NOW)
    assert prov == gb.PROV_INLINE
    assert calls["n"] == 2  # cancelled leader + one clean replacement
    assert tours[0]["key"] == "masters"


async def test_unavailable_when_redis_empty_and_rebuild_fails(monkeypatch):
    client = _FakeRedis({})
    _install(monkeypatch, client)

    async def _broken_get_golf(db):
        raise RuntimeError("datagolf down")

    monkeypatch.setattr("app.routes.golf.get_golf", _broken_get_golf)

    tours, prov = await gb.get_golf_base(None, NOW)
    assert prov == gb.PROV_UNAVAILABLE
    assert tours == []
    assert rc.inflight_count() == 0  # slot cleared on failure


# --- L0 read throttle --------------------------------------------------------
async def test_l0_throttles_redis_round_trips(monkeypatch):
    client = _FakeRedis({gb.GOLF_BASE_FRESH_KEY: json.dumps(_envelope(age_s=10))})
    _install(monkeypatch, client)
    _boom_get_golf(monkeypatch)

    await gb.get_golf_base(None, NOW)
    assert client.gets == 1
    await gb.get_golf_base(None, NOW)  # within L0 window -> no new Redis read
    assert client.gets == 1


# --- publish helpers ---------------------------------------------------------
def test_publish_envelope_sync_writes_both_keys():
    class _SyncRC:
        def __init__(self):
            self.store = {}

        def set(self, k, v, ex=None):
            self.store[k] = (v, ex)

    rc_ = _SyncRC()
    env = gb.build_envelope(NOW, [_tournament()])
    gb.publish_envelope_sync(rc_, env)

    assert gb.GOLF_BASE_FRESH_KEY in rc_.store
    assert gb.GOLF_BASE_LAST_GOOD_KEY in rc_.store
    assert rc_.store[gb.GOLF_BASE_FRESH_KEY][1] == gb.GOLF_BASE_FRESH_TTL_S
    assert rc_.store[gb.GOLF_BASE_LAST_GOOD_KEY][1] == gb.GOLF_BASE_LAST_GOOD_TTL_S
