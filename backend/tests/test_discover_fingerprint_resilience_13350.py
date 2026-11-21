"""#13350 — Discover keeps using its saved copy under load (unit tests)."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from app.utils import feed_collections as fc
from app.utils import request_cache as _rc
from app.utils import theme_collection_ref as tcr


class _Result:
    def __init__(self, value=None, rows=()):
        self._value = value
        self._rows = list(rows)

    def scalar(self):
        return self._value

    def fetchall(self):
        return list(self._rows)


class _Session:
    def __init__(self, *, value="4:1", rows=(), delay: float = 0.0, error=None):
        self.value = value
        self.rows = rows
        self.delay = delay
        self.error = error
        self.calls = 0

    @asynccontextmanager
    async def begin_nested(self):
        yield

    async def execute(self, statement, params=None):
        self.calls += 1
        if self.delay > 0:
            await asyncio.sleep(self.delay)
        if self.error is not None:
            raise self.error
        return _Result(value=self.value, rows=self.rows)

    async def rollback(self):
        return None

    async def close(self):
        return None

    async def invalidate(self):
        return None


class _DictRedis:
    def __init__(self):
        self.store: dict[str, str] = {}

    async def get(self, key):
        return self.store.get(key)

    async def setex(self, key, ttl, value):
        self.store[key] = value
        return True


async def _async(val):
    return val


async def _drain(scheduled):
    while scheduled:
        await scheduled.pop(0)


def _install_fake_redis(monkeypatch):
    fake = _DictRedis()
    scheduled: list = []
    _rc._reset_last_good_for_tests()
    _rc._reset_inflight_for_tests()
    _rc._reset_shared_client_for_tests()
    monkeypatch.setenv("FEED_FINGERPRINT_REDIS_LKG_ENABLED", "1")
    monkeypatch.setattr(_rc, "get_shared_async_redis", lambda: _async(fake))
    monkeypatch.setattr(_rc, "schedule_background", scheduled.append)
    return fake, scheduled


async def test_slow_fingerprint_respects_budget_and_falls_back_to_process_lkg():
    fc._reset_fingerprint_cache_for_tests()
    healthy = _Session(value="4:1,7:2")
    fp1 = await fc.feed_collections_cache_fingerprint(healthy, max_age_seconds=5.0)
    assert isinstance(fp1, str) and fp1

    fc._fingerprint_cache = (fc._fingerprint_cache[0] - 10.0, fp1)
    slow = _Session(delay=2.0)
    loop = asyncio.get_running_loop()
    t0 = loop.time()
    fp2 = await fc.feed_collections_cache_fingerprint(
        slow, max_age_seconds=5.0, budget_seconds=0.05
    )
    elapsed = loop.time() - t0
    assert fp2 == fp1
    assert elapsed < 0.5

    next_db = _Session(value="4:2,7:2")
    assert await fc.feed_collections_cache_fingerprint(next_db, max_age_seconds=5.0) == fp1
    assert next_db.calls == 0

    fc._fingerprint_retry_after = 0.0
    fc._fingerprint_cache = (fc._fingerprint_cache[0] - 10.0, fp1)
    fp3 = await fc.feed_collections_cache_fingerprint(next_db, max_age_seconds=5.0)
    assert fp3 != fp1 and next_db.calls == 1


async def test_fingerprint_uses_redis_lkg_on_cold_process_failure(monkeypatch):
    fc._reset_fingerprint_cache_for_tests()
    fake, scheduled = _install_fake_redis(monkeypatch)
    try:
        healthy = _Session(value="4:1")
        fp = await fc.feed_collections_cache_fingerprint(healthy, max_age_seconds=5.0)
        await _drain(scheduled)
        assert fc.FINGERPRINT_REDIS_LKG_KEY in fake.store

        fc._reset_fingerprint_cache_for_tests()
        failing = _Session(error=RuntimeError("db down"))
        assert (
            await fc.feed_collections_cache_fingerprint(failing, max_age_seconds=5.0)
            == fp
        )

        # Process memo was warmed by Redis LKG during backoff, so no DB or Redis retry.
        db_skipped = _Session(value="9:9")
        assert (
            await fc.feed_collections_cache_fingerprint(db_skipped, max_age_seconds=5.0)
            == fp
        )
        assert db_skipped.calls == 0
    finally:
        for coro in scheduled:
            coro.close()


async def test_concurrent_fingerprint_refreshes_coalesce_via_singleflight():
    fc._reset_fingerprint_cache_for_tests()
    slow_but_valid = _Session(value="4:1", delay=0.05)
    results = await asyncio.gather(
        *[
            fc.feed_collections_cache_fingerprint(slow_but_valid, max_age_seconds=5.0)
            for _ in range(6)
        ]
    )
    assert len(set(results)) == 1 and results[0] is not None
    assert slow_but_valid.calls == 1


async def test_published_themes_lkg_backoff_and_singleflight(monkeypatch):
    tcr._reset_published_cache_for_tests()
    fake, scheduled = _install_fake_redis(monkeypatch)
    try:
        healthy = _Session(rows=[(101, "ai", 18)])
        pub = await tcr.read_published_themes(
            max_age_seconds=5.0, session_factory=lambda: healthy
        )
        assert pub is not None and pub.revision_of(101) == 18
        await _drain(scheduled)
        assert tcr.THEME_PUBLICATION_REDIS_LKG_KEY in fake.store

        tcr._reset_published_cache_for_tests()
        failing = _Session(error=RuntimeError("db down"))
        lkg = await tcr.read_published_themes(
            max_age_seconds=5.0, session_factory=lambda: failing
        )
        assert lkg == pub

        tcr._reset_published_cache_for_tests()
        slow = _Session(rows=[(101, "ai", 19)], delay=0.05)
        batch = await asyncio.gather(
            *[
                tcr.read_published_themes(
                    max_age_seconds=5.0, session_factory=lambda s=slow: s
                )
                for _ in range(5)
            ]
        )
        assert all(b is not None and b.revision_of(101) == 19 for b in batch)
        assert slow.calls == 1
    finally:
        for coro in scheduled:
            coro.close()
