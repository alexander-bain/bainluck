"""Unit tests for the shared Discover candidate-ID base (Queue 285, #1459/#1475).

Guards the LIVE implementation at the real feed/base boundary:

* the identity key excludes limit/offset/user/session and includes only the pool
  inputs (sport + static tags) — matching the C85 offline oracle
  ``candidate_base_key``;
* the freshness boundary (``fresh`` only within the anon-feed freshness window),
  the bounded ``last_good`` fallback (Redis stale + process-local), and the
  ``direct`` fall-through beyond it;
* the Redis kill switch forces the direct-query path;
* a publish -> read round-trip returns the identical ordered candidate IDs;
* a user-independent, request-state-free payload (forbidden keys rejected).
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone

import pytest

from app.utils import candidate_base as cb
from app.utils import request_cache as rc


NOW = datetime(2026, 7, 30, 12, 0, 0, tzinfo=timezone.utc)


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


@pytest.fixture(autouse=True)
def _clean_process_state():
    cb._reset_l0_for_tests()
    rc._reset_last_good_for_tests()
    yield
    cb._reset_l0_for_tests()
    rc._reset_last_good_for_tests()


def _envelope(ids, *, age_s=0, sport=None, tags=None):
    identity = cb.base_identity(sport, tags)
    generated = NOW - timedelta(seconds=age_s)
    env = cb.build_envelope(generated, identity, ids)
    return identity, env


def _store_for(identity, env):
    fresh, last_good = cb._redis_keys(identity)
    payload = json.dumps(env, default=str)
    return {fresh: payload, last_good: payload}


# --- Identity keying ----------------------------------------------------------
def test_anon_default_identity_matches_c85_oracle():
    # The anonymous default (no sport, no static tags) must be the exact key the
    # C85 offline oracle asserts.
    assert (
        cb.base_identity(None, None) == "discover-candidates:v1:all:no-static-tags"
    )


def test_identity_excludes_request_shape_and_varies_only_by_pool_inputs():
    base = cb.base_identity(None, None)
    # Sport + static tags DO change the key (they change the candidate pools)...
    assert cb.base_identity("golf", None) != base
    assert cb.base_identity(None, ["politics"]) != base
    # ...but static tags are order-independent (same base for reordered tags).
    assert cb.base_identity(None, ["a", "b"]) == cb.base_identity(None, ["b", "a"])


# --- Envelope validation ------------------------------------------------------
def test_envelope_round_trips_and_validates():
    identity, env = _envelope([3, 1, 2])
    assert cb.payload_valid(env, expected_identity=identity)
    assert env["candidate_ids"] == [3, 1, 2]  # order preserved verbatim
    assert env["source_watermark"]["count"] == 3
    assert env["source_watermark"]["max_market_id"] == 3


def test_envelope_rejects_wrong_identity_schema_and_leaked_state():
    identity, env = _envelope([1, 2])
    assert not cb.payload_valid(env, expected_identity="discover-candidates:v1:golf:no-static-tags")
    assert not cb.payload_valid({**env, "schema_version": 999}, expected_identity=identity)
    assert not cb.payload_valid({**env, "user_id": 7}, expected_identity=identity)
    assert not cb.payload_valid({**env, "candidate_ids": [1, "x"]}, expected_identity=identity)
    # booleans are not valid market ids even though they are int subclasses
    assert not cb.payload_valid({**env, "candidate_ids": [True]}, expected_identity=identity)


# --- Selection tiers ----------------------------------------------------------
@pytest.mark.asyncio
async def test_fresh_base_is_served_as_fresh(monkeypatch):
    identity, env = _envelope([10, 20, 30], age_s=10)
    _install(monkeypatch, _FakeRedis(_store_for(identity, env)))
    ids, prov, _ = await cb.get_candidate_base(NOW, None, None)
    assert prov == cb.PROV_FRESH
    assert ids == [10, 20, 30]


@pytest.mark.asyncio
async def test_stale_base_within_last_good_is_last_good(monkeypatch):
    # Older than the 60s freshness window but inside the last-good window.
    identity, env = _envelope([5, 6], age_s=cb.CANDIDATE_BASE_FRESH_SECONDS + 120)
    _install(monkeypatch, _FakeRedis(_store_for(identity, env)))
    ids, prov, _ = await cb.get_candidate_base(NOW, None, None)
    assert prov == cb.PROV_LAST_GOOD
    assert ids == [5, 6]


@pytest.mark.asyncio
async def test_base_beyond_last_good_falls_to_direct(monkeypatch):
    identity, env = _envelope([9], age_s=cb.CANDIDATE_BASE_LAST_GOOD_MAX_AGE_S + 60)
    _install(monkeypatch, _FakeRedis(_store_for(identity, env)))
    ids, prov, _ = await cb.get_candidate_base(NOW, None, None)
    assert ids is None
    assert prov == cb.PROV_DIRECT


@pytest.mark.asyncio
async def test_missing_base_falls_to_direct(monkeypatch):
    _install(monkeypatch, _FakeRedis({}))
    ids, prov, _ = await cb.get_candidate_base(NOW, None, None)
    assert ids is None
    assert prov == cb.PROV_DIRECT


@pytest.mark.asyncio
async def test_kill_switch_forces_direct_and_reports_disabled(monkeypatch):
    identity, env = _envelope([1, 2, 3], age_s=1)
    store = _store_for(identity, env)
    store[cb.CANDIDATE_BASE_ENABLED_KEY] = "0"
    _install(monkeypatch, _FakeRedis(store))
    ids, prov, _ = await cb.get_candidate_base(NOW, None, None)
    assert ids is None
    assert prov == cb.PROV_DISABLED


# --- Publish / read round-trip + resilience -----------------------------------
@pytest.mark.asyncio
async def test_publish_then_read_returns_identical_order(monkeypatch):
    client = _FakeRedis({})
    _install(monkeypatch, client)
    identity = cb.base_identity(None, None)
    env = cb.build_envelope(NOW, identity, [7, 3, 11, 3, 7], pool_counts={"sports": 2})
    # dedup is the caller's job; build_envelope preserves the list verbatim.
    await cb.publish_candidate_base(env)
    assert client.sets == 2  # fresh + last_good keys written
    cb._reset_l0_for_tests()  # force a Redis re-read, not the process throttle
    ids, prov, _ = await cb.get_candidate_base(NOW, None, None)
    assert prov == cb.PROV_FRESH
    assert ids == [7, 3, 11, 3, 7]


@pytest.mark.asyncio
async def test_external_curator_recall_ids_round_trip(monkeypatch):
    # The recall-lane IDs (a scoring input) must survive publish -> read so a
    # base-served build applies the recall bonus identically to a direct build.
    client = _FakeRedis({})
    _install(monkeypatch, client)
    identity = cb.base_identity(None, None)
    env = cb.build_envelope(
        NOW, identity, [7, 3, 11], external_curator_recall_ids=[3, 11]
    )
    await cb.publish_candidate_base(env)
    cb._reset_l0_for_tests()
    ids, prov, curator_ids = await cb.get_candidate_base(NOW, None, None)
    assert prov == cb.PROV_FRESH
    assert ids == [7, 3, 11]
    assert curator_ids == [3, 11]


@pytest.mark.asyncio
async def test_kill_switch_blocks_publish(monkeypatch):
    client = _FakeRedis({cb.CANDIDATE_BASE_ENABLED_KEY: "0"})
    _install(monkeypatch, client)
    identity = cb.base_identity(None, None)
    await cb.publish_candidate_base(cb.build_envelope(NOW, identity, [1, 2]))
    assert client.sets == 0  # nothing published while disabled


@pytest.mark.asyncio
async def test_process_last_good_survives_redis_outage(monkeypatch):
    # Warm a fresh base, then drop Redis: the process-local last-good still serves
    # the base (no candidate SQL) rather than falling to direct.
    identity, env = _envelope([4, 8], age_s=5)
    _install(monkeypatch, _FakeRedis(_store_for(identity, env)))
    ids, prov, _ = await cb.get_candidate_base(NOW, None, None)
    assert prov == cb.PROV_FRESH and ids == [4, 8]

    cb._reset_l0_for_tests()  # bypass the process throttle
    _install(monkeypatch, _FakeRedis({}, mode="down"))
    ids2, prov2, _ = await cb.get_candidate_base(NOW, None, None)
    assert prov2 == cb.PROV_LAST_GOOD
    assert ids2 == [4, 8]


@pytest.mark.asyncio
async def test_wrong_identity_payload_is_not_served(monkeypatch):
    # A payload built for 'golf' stored under the 'all' key must be rejected (the
    # identity guard) rather than served as another sport's candidates.
    _, golf_env = _envelope([1, 2], sport="golf")
    all_fresh, all_last_good = cb._redis_keys(cb.base_identity(None, None))
    payload = json.dumps(golf_env, default=str)
    _install(monkeypatch, _FakeRedis({all_fresh: payload, all_last_good: payload}))
    ids, prov, _ = await cb.get_candidate_base(NOW, None, None)
    assert ids is None
    assert prov == cb.PROV_DIRECT
