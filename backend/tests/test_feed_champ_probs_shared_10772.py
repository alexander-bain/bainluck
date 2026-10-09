"""#10772: the feed's championship-odds map is shared across processes.

The guards below pin the four properties the change claims:
  * a fresh shared slot answers without the query;
  * the per-process dict inherits the slot's age, so the 300 s bound never stacks;
  * every failure of the shared level degrades to the query, never to an error
    or a wrong answer;
  * concurrent cold builds in one process run the query once.
"""

import asyncio
import json
import time

import pytest

from app.routes import feed
from app.utils import championship_probs_cache as cpc


class FakeRedis:
    def __init__(self, raw=None, fail_get=False, fail_set=False):
        self.raw = raw
        self.fail_get = fail_get
        self.fail_set = fail_set
        self.setex_calls = []

    def get(self, key):
        assert key == cpc.CACHE_KEY
        if self.fail_get:
            raise ConnectionError("down")
        return self.raw

    def setex(self, key, ttl, value):
        if self.fail_set:
            raise ConnectionError("down")
        self.setex_calls.append((key, ttl, value))
        self.raw = value.encode()


class _Row:
    def __init__(self, team_id, max_prob):
        self.team_id = team_id
        self.max_prob = max_prob


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class FakeDB:
    def __init__(self, rows, delay=0.0):
        self.rows = rows
        self.delay = delay
        self.calls = 0

    async def execute(self, *_a, **_k):
        self.calls += 1
        if self.delay:
            await asyncio.sleep(self.delay)
        return _Result(self.rows)


@pytest.fixture(autouse=True)
def _cold_process(monkeypatch):
    monkeypatch.setattr(feed, "_champ_prob_cache", None)
    monkeypatch.setattr(feed, "_champ_prob_cache_ts", 0.0)


def _use(monkeypatch, client):
    monkeypatch.setattr(cpc, "_client", lambda: client)


# --- the pure codec ----------------------------------------------------------


def test_round_trip_including_the_empty_map():
    for probs in ({7: 0.25, 11: 0.5}, {}):
        assert cpc.decode(cpc.encode(probs, 123.5)) == (probs, 123.5)


@pytest.mark.parametrize(
    "raw",
    [
        b"\xff",
        "not json",
        "[]",
        json.dumps({"probs": []}),
        json.dumps({"computed_at": True, "probs": []}),
        json.dumps({"computed_at": 1.0, "probs": {}}),
        json.dumps({"computed_at": 1.0, "probs": [[1]]}),
        json.dumps({"computed_at": 1.0, "probs": [[True, 0.5]]}),
        json.dumps({"computed_at": 1.0, "probs": [["1", 0.5]]}),
        json.dumps({"computed_at": 1.0, "probs": [[1, "0.5"]]}),
        '{"computed_at": NaN, "probs": []}',
    ],
)
def test_a_malformed_slot_is_a_miss_not_an_empty_answer(raw):
    assert cpc.decode(raw) is None


def test_a_slot_older_than_the_ttl_reads_as_a_miss():
    now = 10_000.0
    old = FakeRedis(cpc.encode({1: 0.4}, now - cpc.TTL_SECONDS))
    young = FakeRedis(cpc.encode({1: 0.4}, now - cpc.TTL_SECONDS + 1))
    assert cpc.read(rc=old, now=now) is None
    assert cpc.read(rc=young, now=now) == ({1: 0.4}, now - cpc.TTL_SECONDS + 1)


def test_the_shared_ttl_is_the_feeds_own_number():
    assert cpc.TTL_SECONDS == feed._CHAMP_PROB_CACHE_TTL == 300


# --- the ladder in the route ------------------------------------------------


@pytest.mark.asyncio
async def test_a_fresh_shared_slot_answers_without_the_query(monkeypatch):
    _use(monkeypatch, FakeRedis(cpc.encode({5: 0.3}, time.time() - 10)))
    db = FakeDB([_Row(5, 0.9)])
    assert await feed._get_championship_probabilities(db) == {5: 0.3}
    assert db.calls == 0


@pytest.mark.asyncio
async def test_l1_inherits_the_slots_age_so_the_bounds_do_not_stack(monkeypatch):
    computed_at = time.time() - (cpc.TTL_SECONDS - 5)
    redis = FakeRedis(cpc.encode({5: 0.3}, computed_at))
    _use(monkeypatch, redis)
    db = FakeDB([_Row(5, 0.9)])
    assert await feed._get_championship_probabilities(db) == {5: 0.3}
    assert feed._champ_prob_cache_ts == computed_at

    # Six seconds later the map is past 300 s. Neither level may serve it,
    # even though L1 was filled only six seconds ago.
    real_time = time.time
    monkeypatch.setattr(cpc.time, "time", lambda: real_time() + 6)
    monkeypatch.setattr(feed.time, "time", lambda: real_time() + 6)
    assert await feed._get_championship_probabilities(db) == {5: 0.9}
    assert db.calls == 1


@pytest.mark.asyncio
async def test_a_miss_queries_once_and_publishes_to_both_levels(monkeypatch):
    redis = FakeRedis(None)
    _use(monkeypatch, redis)
    db = FakeDB([_Row(5, 0.9), _Row(8, 0.1)])
    assert await feed._get_championship_probabilities(db) == {5: 0.9, 8: 0.1}
    assert await feed._get_championship_probabilities(db) == {5: 0.9, 8: 0.1}
    assert db.calls == 1
    assert len(redis.setex_calls) == 1
    key, ttl, value = redis.setex_calls[0]
    assert (key, ttl) == (cpc.CACHE_KEY, cpc.TTL_SECONDS)
    probs, computed_at = cpc.decode(value)
    assert probs == {5: 0.9, 8: 0.1}
    assert computed_at == feed._champ_prob_cache_ts


@pytest.mark.asyncio
async def test_an_empty_map_is_cached_like_any_other_answer(monkeypatch):
    _use(monkeypatch, FakeRedis(None))
    db = FakeDB([])
    assert await feed._get_championship_probabilities(db) == {}
    assert await feed._get_championship_probabilities(db) == {}
    assert db.calls == 1


@pytest.mark.parametrize(
    "client",
    [None, FakeRedis(fail_get=True, fail_set=True), FakeRedis(b"garbage")],
    ids=["no-redis", "redis-errors", "malformed-slot"],
)
@pytest.mark.asyncio
async def test_every_shared_failure_degrades_to_the_query(monkeypatch, client):
    _use(monkeypatch, client)
    db = FakeDB([_Row(3, 0.6)])
    assert await feed._get_championship_probabilities(db) == {3: 0.6}
    assert db.calls == 1


@pytest.mark.asyncio
async def test_concurrent_cold_builds_in_one_process_run_the_query_once(monkeypatch):
    _use(monkeypatch, FakeRedis(None))
    db = FakeDB([_Row(5, 0.9)], delay=0.05)
    results = await asyncio.gather(
        *(feed._get_championship_probabilities(db) for _ in range(6))
    )
    assert results == [{5: 0.9}] * 6
    assert db.calls == 1


@pytest.mark.asyncio
async def test_a_failed_query_releases_the_lock_for_the_next_build(monkeypatch):
    _use(monkeypatch, FakeRedis(None))

    class Boom(FakeDB):
        async def execute(self, *_a, **_k):
            self.calls += 1
            raise RuntimeError("statement timeout")

    with pytest.raises(RuntimeError):
        await feed._get_championship_probabilities(Boom([]))
    db = FakeDB([_Row(5, 0.9)])
    assert await feed._get_championship_probabilities(db) == {5: 0.9}
