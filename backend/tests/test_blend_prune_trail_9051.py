"""#9051: a prune stays findable after Heroku's ~3 min log buffer has rolled.

The heavy app has no log drain, so the trail in Redis is the only place a held
page's lost source can be paired with the prune that removed it.
"""
import asyncio
import json
import os
import threading
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.tasks import prediction_market_matching as pmm
from app.utils import blend_prune_trail as bpt


class FakeRedis:
    """Mirrors the append script ATOMICALLY. ``get``/``setex``/``set`` raise:
    a client-side read-modify-write is the race, so the writer may not use one."""

    def __init__(self, on_write=None, fail=False, delay=0.0):
        self.store, self.ttl, self.on_write = {}, {}, on_write
        self.fail, self.delay, self.evals = fail, delay, 0
        self._lock = threading.Lock()

    def eval(self, script, numkeys, *args):
        self.evals += 1
        if self.delay:
            time.sleep(self.delay)
        if self.fail:
            raise ConnectionError("redis down")
        assert script == bpt._APPEND_LUA
        keys, cap, ttl = args[:numkeys], int(args[numkeys]), int(args[numkeys + 1])
        with self._lock:
            for key, raw in zip(keys, args[numkeys + 2:]):
                if self.on_write:
                    self.on_write(key)
                try:
                    trail = json.loads(self.store.get(key) or "[]")
                except ValueError:
                    trail = []
                trail = (trail if isinstance(trail, list) else []) + [json.loads(raw)]
                self.store[key], self.ttl[key] = json.dumps(trail[-cap:]), ttl
        return numkeys

    def get(self, key):
        raise AssertionError("client-side GET: the append must be one atomic script")

    setex = set = get

    def trail(self, eid):
        raw = self.store.get(bpt.trail_key(eid))
        return json.loads(raw) if raw else []


@pytest.fixture(autouse=True)
def _unsuspended(monkeypatch):
    monkeypatch.setattr(bpt, "_suspended_until", 0.0)


@pytest.fixture
def redis(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(bpt, "_client", lambda: fake)
    return fake


def rec(source="kalshi", phase="unlink", committed=False):
    return {"at": "2026-10-04T00:00:00+00:00", "source": source, "phase": phase,
            "committed": committed}


def unlink_session(remaining=0, sources=None):
    db = AsyncMock()
    db.execute.side_effect = [
        SimpleNamespace(scalar=lambda: remaining),
        SimpleNamespace(scalar_one_or_none=lambda: sources if sources is not None else
                        {"kalshi": 0.7, "betting": 0.6}),
        None,
    ]
    return db


def cleanup_session(first=None):
    db = AsyncMock()
    first = first if first is not None else [(123, {"kalshi": 0.7, "betting": 0.6}),
                                             (456, {"betting": 0.6})]
    db.execute.side_effect = [
        SimpleNamespace(all=lambda: first),
        *[None] * sum(1 for _, w in first if "kalshi" in w),
        SimpleNamespace(all=lambda: [(789, {"polymarket": 0.4})]),
        None,
    ]
    return db


@pytest.mark.asyncio
async def test_unlink_prune_is_kept_as_staged_never_committed(redis):
    db = unlink_session()
    assert await pmm._prune_orphaned_blend_source(db, 123, "kalshi") is True
    [r] = redis.trail(123)
    assert (r["source"], r["phase"], r["committed"]) == ("kalshi", "unlink", False)
    assert r["at"].endswith("+00:00")
    assert redis.ttl[bpt.trail_key(123)] == bpt.TRAIL_TTL_S
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_surviving_source_writes_no_trail(redis):
    db = unlink_session(remaining=1, sources={"kalshi": 0.7})
    assert await pmm._prune_orphaned_blend_source(db, 123, "kalshi") is False
    assert redis.store == {} and redis.evals == 0


@pytest.mark.asyncio
async def test_cleanup_records_each_prune_only_after_its_commit(monkeypatch):
    db = cleanup_session()
    commits_at_write = []
    fake = FakeRedis(on_write=lambda key: commits_at_write.append(db.commit.await_count))
    monkeypatch.setattr(bpt, "_client", lambda: fake)

    assert await pmm._cleanup_orphaned_blend_sources(db) == 2
    assert commits_at_write == [1, 1]  # every write saw the commit already done
    assert fake.evals == 1  # one batch, not one round trip per prune
    assert [(r["source"], r["phase"], r["committed"]) for r in fake.trail(123)] == [
        ("kalshi", "cleanup", True)]
    assert [(r["source"], r["committed"]) for r in fake.trail(789)] == [("polymarket", True)]
    assert fake.trail(456) == []  # no key to prune, nothing claimed


@pytest.mark.asyncio
async def test_failed_cleanup_commit_claims_nothing(redis):
    db = cleanup_session()
    db.commit.side_effect = RuntimeError("commit failed")
    with pytest.raises(RuntimeError, match="commit failed"):
        await pmm._cleanup_orphaned_blend_sources(db)
    assert redis.store == {} and redis.evals == 0


@pytest.mark.asyncio
async def test_deadline_commit_path_also_records(redis):
    db = cleanup_session()
    clock = iter([100, 5])  # second candidate hits the deadline
    assert await pmm._cleanup_orphaned_blend_sources(db, time_remaining_fn=lambda: next(clock)) == 1
    db.commit.assert_awaited_once()
    assert [r["committed"] for r in redis.trail(123)] == [True]


@pytest.mark.asyncio
async def test_redis_failure_cannot_change_prune_or_commit(monkeypatch):
    monkeypatch.setattr(bpt, "_client", lambda: FakeRedis(fail=True))
    db = unlink_session()
    assert await pmm._prune_orphaned_blend_source(db, 123, "kalshi") is True
    assert db.execute.await_count == 3
    monkeypatch.setattr(bpt, "_suspended_until", 0.0)
    db = cleanup_session()
    assert await pmm._cleanup_orphaned_blend_sources(db) == 2
    db.commit.assert_awaited_once()


def test_competing_appends_both_survive():
    # The 3dbe GET/SETEX lost one of two concurrent records (both read []).
    fake = FakeRedis()
    gate = threading.Barrier(2)

    def writer(source):
        gate.wait()
        assert bpt.write_trail_batch([(5, rec(source))], client=fake) == 1

    threads = [threading.Thread(target=writer, args=(s,)) for s in ("kalshi", "polymarket")]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert sorted(r["source"] for r in fake.trail(5)) == ["kalshi", "polymarket"]


def test_trail_is_capped_newest_kept_and_appends_in_order():
    fake = FakeRedis()
    for i in range(bpt.TRAIL_MAX + 5):
        assert bpt.write_trail_batch([(7, rec(f"s{i}"))], client=fake) == 1
    trail = fake.trail(7)
    assert len(trail) == bpt.TRAIL_MAX
    assert trail[0]["source"] == "s5" and trail[-1]["source"] == f"s{bpt.TRAIL_MAX + 4}"


def test_first_failure_stops_a_full_cleanup_trail_and_suspends():
    fake = FakeRedis(fail=True)
    full = [(i, rec(phase="cleanup", committed=True)) for i in range(4000)]
    assert bpt.write_trail_batch(full, client=fake) == 0
    assert fake.evals == 1  # 40 chunks queued, one attempt made
    assert bpt.write_trail_batch(full, client=fake) == 0
    assert fake.evals == 1  # suspended: the next prune pays nothing


def test_slow_redis_is_cut_off_by_the_budget_not_walked_to_the_end():
    fake = FakeRedis()
    now = [0.0]

    def clock():
        return now[0]

    def slow_eval(*a, _orig=fake.eval):
        now[0] += 0.4  # each op eats 0.4s of a 0.5s budget
        return _orig(*a)

    fake.eval = slow_eval
    full = [(i, rec(phase="cleanup", committed=True)) for i in range(4000)]
    written = bpt.write_trail_batch(full, client=fake, budget_s=bpt.TRAIL_DEADLINE_BUDGET_S,
                                    clock=clock)
    assert written == 2 * bpt.TRAIL_CHUNK  # two ops fit, the other 38 are dropped
    assert bpt.write_trail_batch(full, client=fake, budget_s=0, clock=clock) == 0


@pytest.mark.asyncio
async def test_deadline_branch_uses_the_short_budget(monkeypatch):
    seen = []

    async def spy(pairs, phase, committed, budget_s=bpt.TRAIL_BATCH_BUDGET_S):
        seen.append(budget_s)
        return 0

    monkeypatch.setattr(pmm, "record_blend_prunes", spy)
    clock = iter([100, 5])
    await pmm._cleanup_orphaned_blend_sources(cleanup_session(), time_remaining_fn=lambda: next(clock))
    await pmm._cleanup_orphaned_blend_sources(cleanup_session())
    assert seen == [bpt.TRAIL_DEADLINE_BUDGET_S, bpt.TRAIL_BATCH_BUDGET_S]


@pytest.mark.asyncio
async def test_write_does_not_block_the_event_loop(monkeypatch):
    fake = FakeRedis(delay=0.3)
    monkeypatch.setattr(bpt, "_client", lambda: fake)
    ticks = 0

    async def ticker():
        nonlocal ticks
        while True:
            await asyncio.sleep(0.02)
            ticks += 1

    t = asyncio.create_task(ticker())
    assert await bpt.record_blend_prunes([(1, "kalshi")], "unlink", False) == 1
    t.cancel()
    assert ticks >= 5  # the loop kept running while Redis was slow


@pytest.mark.asyncio
async def test_a_hung_redis_returns_within_the_bound(monkeypatch):
    release = threading.Event()

    class Hung(FakeRedis):
        def eval(self, *a):
            release.wait(10)
            raise ConnectionError("gave up")

    monkeypatch.setattr(bpt, "_client", lambda: Hung())
    t0 = time.monotonic()
    try:
        assert await bpt.record_blend_prunes([(1, "kalshi")], "unlink", False, budget_s=0.1) == 0
        assert time.monotonic() - t0 < 0.1 + 2 * bpt.TRAIL_OP_TIMEOUT_S + 0.5
    finally:
        release.set()


def test_trail_client_is_short_timeout_fast_fail(monkeypatch):
    calls = []
    monkeypatch.setattr("app.tasks.redis_state.get_redis_client",
                        lambda **kw: calls.append(kw) or object())
    bpt._client()
    assert calls == [{"socket_timeout": bpt.TRAIL_OP_TIMEOUT_S,
                      "socket_connect_timeout": bpt.TRAIL_OP_TIMEOUT_S, "fast_fail": True}]


def test_key_is_readable_by_the_existing_redis_read_endpoint():
    # /api/admin/redis-read refuses any key outside the bainluck: namespace.
    assert bpt.trail_key(14781135) == "bainluck:blend_prune_trail:14781135"
    assert bpt.trail_key(14781135).startswith("bainluck:")


# --- the real script on a real Redis -------------------------------------------
# CI's unit job has no Redis, so these skip there; run locally with
# BL_TRAIL_TEST_REDIS_URL=redis://127.0.0.1:56379/13 (redislite's binary works).
_REAL_URL = os.environ.get("BL_TRAIL_TEST_REDIS_URL")


@pytest.fixture
def real_redis():
    if not _REAL_URL:
        pytest.skip("BL_TRAIL_TEST_REDIS_URL not set")
    import redis as redis_lib

    client = redis_lib.Redis.from_url(_REAL_URL, socket_timeout=5)
    client.flushdb()
    yield client
    client.flushdb()


def test_real_script_keeps_every_competing_append(real_redis):
    n_threads, per_thread = 8, 6  # 48 records, under the cap of 50
    gate = threading.Barrier(n_threads)

    def writer(t):
        gate.wait()
        for i in range(per_thread):
            assert bpt.write_trail_batch([(11, rec(f"t{t}-{i}"))], client=real_redis) == 1

    threads = [threading.Thread(target=writer, args=(t,)) for t in range(n_threads)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    trail = json.loads(real_redis.get(bpt.trail_key(11)))  # the existing GET reader
    assert len(trail) == n_threads * per_thread
    assert len({r["source"] for r in trail}) == n_threads * per_thread


def test_real_script_caps_expires_replaces_corrupt_and_keeps_types(real_redis):
    real_redis.set(bpt.trail_key(21), "{not json")
    real_redis.set(bpt.trail_key(22), json.dumps({"a": 1}))  # an object, not a list
    batch = [(21, rec("kalshi", "cleanup", True)), (22, rec("polymarket"))]
    batch += [(23, rec(f"s{i}")) for i in range(bpt.TRAIL_MAX + 3)]
    assert bpt.write_trail_batch(batch, client=real_redis) == len(batch)

    assert json.loads(real_redis.get(bpt.trail_key(21))) == [rec("kalshi", "cleanup", True)]
    assert json.loads(real_redis.get(bpt.trail_key(22))) == [rec("polymarket")]
    capped = json.loads(real_redis.get(bpt.trail_key(23)))
    assert [r["source"] for r in capped] == [f"s{i}" for i in range(3, bpt.TRAIL_MAX + 3)]
    assert capped[0]["committed"] is False
    assert 0 < real_redis.ttl(bpt.trail_key(23)) <= bpt.TRAIL_TTL_S
