"""#9051: a prune stays findable after Heroku's ~3 min log buffer has rolled.

The heavy app has no log drain, so the trail in Redis is the only place a held
page's lost source can be paired with the prune that removed it.
"""
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.tasks import prediction_market_matching as pmm
from app.utils import blend_prune_trail as bpt


class FakeRedis:
    def __init__(self, on_write=None, fail=False):
        self.store, self.ttl, self.on_write, self.fail = {}, {}, on_write, fail

    def get(self, key):
        if self.fail:
            raise ConnectionError("redis down")
        return self.store.get(key)

    def setex(self, key, ttl, value):
        if self.on_write:
            self.on_write(key)
        self.store[key], self.ttl[key] = value, ttl

    def trail(self, eid):
        raw = self.store.get(bpt.trail_key(eid))
        return json.loads(raw) if raw else []


@pytest.fixture
def redis(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr("app.tasks.redis_state.get_redis_client", lambda: fake)
    return fake


def unlink_session(remaining=0, sources=None):
    db = AsyncMock()
    db.execute.side_effect = [
        SimpleNamespace(scalar=lambda: remaining),
        SimpleNamespace(scalar_one_or_none=lambda: sources if sources is not None else
                        {"kalshi": 0.7, "betting": 0.6}),
        None,
    ]
    return db


def cleanup_session():
    db = AsyncMock()
    db.execute.side_effect = [
        SimpleNamespace(all=lambda: [(123, {"kalshi": 0.7, "betting": 0.6}),
                                      (456, {"betting": 0.6})]),
        None,
        SimpleNamespace(all=lambda: [(789, {"polymarket": 0.4})]),
        None,
    ]
    return db


@pytest.mark.asyncio
async def test_unlink_prune_is_kept_as_staged_never_committed(redis):
    db = unlink_session()
    assert await pmm._prune_orphaned_blend_source(db, 123, "kalshi") is True
    [rec] = redis.trail(123)
    assert (rec["source"], rec["phase"], rec["committed"]) == ("kalshi", "unlink", False)
    assert rec["at"].endswith("+00:00")
    assert redis.ttl[bpt.trail_key(123)] == bpt.TRAIL_TTL_S
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_surviving_source_writes_no_trail(redis):
    db = unlink_session(remaining=1, sources={"kalshi": 0.7})
    assert await pmm._prune_orphaned_blend_source(db, 123, "kalshi") is False
    assert redis.store == {}


@pytest.mark.asyncio
async def test_cleanup_records_each_prune_only_after_its_commit(monkeypatch):
    db = cleanup_session()
    commits_at_write = []
    fake = FakeRedis(on_write=lambda key: commits_at_write.append(db.commit.await_count))
    monkeypatch.setattr("app.tasks.redis_state.get_redis_client", lambda: fake)

    assert await pmm._cleanup_orphaned_blend_sources(db) == 2
    assert commits_at_write == [1, 1]  # every write saw the commit already done
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
    assert redis.store == {}


@pytest.mark.asyncio
async def test_deadline_commit_path_also_records(redis):
    db = cleanup_session()
    clock = iter([100, 5])  # second candidate hits the deadline
    assert await pmm._cleanup_orphaned_blend_sources(db, time_remaining_fn=lambda: next(clock)) == 1
    db.commit.assert_awaited_once()
    assert [r["committed"] for r in redis.trail(123)] == [True]


@pytest.mark.asyncio
async def test_redis_failure_cannot_change_prune_or_commit(monkeypatch):
    monkeypatch.setattr("app.tasks.redis_state.get_redis_client", lambda: FakeRedis(fail=True))
    db = unlink_session()
    assert await pmm._prune_orphaned_blend_source(db, 123, "kalshi") is True
    assert db.execute.await_count == 3
    db = cleanup_session()
    assert await pmm._cleanup_orphaned_blend_sources(db) == 2
    db.commit.assert_awaited_once()


def test_trail_is_capped_newest_kept_and_appends_in_order():
    fake = FakeRedis()
    for i in range(bpt.TRAIL_MAX + 5):
        assert bpt.record_blend_prune(7, f"s{i}", "unlink", committed=False, client=fake)
    trail = fake.trail(7)
    assert len(trail) == bpt.TRAIL_MAX
    assert trail[0]["source"] == "s5" and trail[-1]["source"] == f"s{bpt.TRAIL_MAX + 4}"


def test_corrupt_trail_is_replaced_not_fatal():
    fake = FakeRedis()
    fake.store[bpt.trail_key(9)] = "{not json"
    assert bpt.record_blend_prune(9, "kalshi", "cleanup", committed=True, client=fake)
    assert [r["source"] for r in fake.trail(9)] == ["kalshi"]


def test_key_is_readable_by_the_existing_redis_read_endpoint():
    # /api/admin/redis-read refuses any key outside the bainluck: namespace.
    assert bpt.trail_key(14781135) == "bainluck:blend_prune_trail:14781135"
    assert bpt.trail_key(14781135).startswith("bainluck:")
