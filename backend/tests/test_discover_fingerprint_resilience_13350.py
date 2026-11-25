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


async def test_fingerprint_lkg_expires_after_ten_minutes_for_process_and_redis(
    monkeypatch,
):
    import json

    fc._reset_fingerprint_cache_for_tests()
    fake, scheduled = _install_fake_redis(monkeypatch)
    clock = {"mono": 1000.0, "wall": 2_000_000.0}
    monkeypatch.setattr(fc.time, "monotonic", lambda: clock["mono"])
    monkeypatch.setattr(fc.time, "time", lambda: clock["wall"])
    try:
        healthy = _Session(value="4:1")
        fp = await fc.feed_collections_cache_fingerprint(healthy, max_age_seconds=5.0)
        assert fp is not None
        await _drain(scheduled)

        # Fail within 10 min: process copy survives.
        clock["mono"] += 120.0
        clock["wall"] += 120.0
        failing = _Session(error=RuntimeError("db down"))
        assert (
            await fc.feed_collections_cache_fingerprint(failing, max_age_seconds=5.0)
            == fp
        )
        assert fc.get_fingerprint_cache_status()["state"] == "fallback"

        # Past 10 min without a successful read: process LKG expires -> None.
        clock["mono"] = 1601.0
        clock["wall"] = 2_000_601.0
        fc._fingerprint_retry_after = 0.0
        assert (
            await fc.feed_collections_cache_fingerprint(failing, max_age_seconds=5.0)
            is None
        )
        assert fc.get_fingerprint_cache_status()["state"] == "fallback_expired"

        # Fresh Redis envelope (< 10 min old) rescues cold worker with true age;
        # >= 10 min old Redis envelope returns None.
        fc._reset_fingerprint_cache_for_tests()
        clock["mono"] = 2000.0
        clock["wall"] = 3_000_250.0
        fake.store[fc.FINGERPRINT_REDIS_LKG_KEY] = json.dumps(
            {"v": 1, "fp": fp, "read_at": 3_000_000.0}
        )
        rescued = await fc.feed_collections_cache_fingerprint(
            failing, max_age_seconds=5.0
        )
        assert rescued == fp
        status = fc.get_fingerprint_cache_status()
        assert status["state"] == "fallback"
        assert status["source"] == "fallback_redis"
        assert status["copy_age_seconds"] == 250.0

        fc._reset_fingerprint_cache_for_tests()
        clock["wall"] = 3_000_601.0
        assert (
            await fc.feed_collections_cache_fingerprint(failing, max_age_seconds=5.0)
            is None
        )
    finally:
        for coro in scheduled:
            coro.close()


async def test_published_themes_lkg_expires_after_ten_minutes_for_process_and_redis(
    monkeypatch,
):
    import json

    tcr._reset_published_cache_for_tests()
    fake, scheduled = _install_fake_redis(monkeypatch)
    clock = {"mono": 1000.0, "wall": 2_000_000.0}
    monkeypatch.setattr(tcr.time, "monotonic", lambda: clock["mono"])
    monkeypatch.setattr(tcr.time, "time", lambda: clock["wall"])
    try:
        healthy = _Session(rows=[(101, "ai", 18)])
        pub = await tcr.read_published_themes(
            max_age_seconds=5.0, session_factory=lambda: healthy
        )
        assert pub is not None
        await _drain(scheduled)

        clock["mono"] += 120.0
        clock["wall"] += 120.0
        failing = _Session(error=RuntimeError("db down"))
        assert (
            await tcr.read_published_themes(
                max_age_seconds=5.0, session_factory=lambda: failing
            )
            == pub
        )
        assert tcr.get_published_themes_cache_status()["state"] == "fallback"

        clock["mono"] = 1601.0
        clock["wall"] = 2_000_601.0
        tcr._published_retry_after = 0.0
        assert (
            await tcr.read_published_themes(
                max_age_seconds=5.0, session_factory=lambda: failing
            )
            is None
        )
        assert tcr.get_published_themes_cache_status()["state"] == "fallback_expired"

        tcr._reset_published_cache_for_tests()
        clock["mono"] = 2000.0
        clock["wall"] = 3_000_240.0
        fake.store[tcr.THEME_PUBLICATION_REDIS_LKG_KEY] = json.dumps(
            {"v": 1, "read_at": 3_000_000.0, "themes": [[101, "ai", 18]]}
        )
        rescued = await tcr.read_published_themes(
            max_age_seconds=5.0, session_factory=lambda: failing
        )
        assert rescued == pub
        status = tcr.get_published_themes_cache_status()
        assert status["state"] == "fallback"
        assert status["source"] == "fallback_redis"
        assert status["copy_age_seconds"] == 240.0

        tcr._reset_published_cache_for_tests()
        clock["wall"] = 3_000_601.0
        assert (
            await tcr.read_published_themes(
                max_age_seconds=5.0, session_factory=lambda: failing
            )
            is None
        )
    finally:
        for coro in scheduled:
            coro.close()


async def test_fallback_logs_one_error_after_five_minutes_and_resets_on_recovery(
    monkeypatch, caplog
):
    import logging

    fc._reset_fingerprint_cache_for_tests()
    tcr._reset_published_cache_for_tests()
    clock = {"mono": 1000.0, "wall": 2_000_000.0}
    monkeypatch.setattr(fc.time, "monotonic", lambda: clock["mono"])
    monkeypatch.setattr(fc.time, "time", lambda: clock["wall"])
    monkeypatch.setattr(tcr.time, "monotonic", lambda: clock["mono"])
    monkeypatch.setattr(tcr.time, "time", lambda: clock["wall"])

    healthy_fp = _Session(value="4:1")
    healthy_th = _Session(rows=[(101, "ai", 18)])
    await fc.feed_collections_cache_fingerprint(healthy_fp, max_age_seconds=5.0)
    await tcr.read_published_themes(
        max_age_seconds=5.0, session_factory=lambda: healthy_th
    )

    failing = _Session(error=RuntimeError("db down"))
    with caplog.at_level(logging.ERROR):
        # First failure at t=1010 -> fallback starts, no ERROR yet.
        clock["mono"] = 1010.0
        clock["wall"] = 2_000_010.0
        await fc.feed_collections_cache_fingerprint(failing, max_age_seconds=5.0)
        await tcr.read_published_themes(
            max_age_seconds=5.0, session_factory=lambda: failing
        )
        assert [r for r in caplog.records if r.levelno >= logging.ERROR] == []

        # Still under 5 min (t=1309) -> still no ERROR.
        clock["mono"] = 1309.0
        clock["wall"] = 2_000_309.0
        await fc.feed_collections_cache_fingerprint(failing, max_age_seconds=5.0)
        await tcr.read_published_themes(
            max_age_seconds=5.0, session_factory=lambda: failing
        )
        assert [r for r in caplog.records if r.levelno >= logging.ERROR] == []

        # At t=1310 (300s of fallback) -> ONE ERROR each, never repeated at t=1320.
        clock["mono"] = 1310.0
        clock["wall"] = 2_000_310.0
        await fc.feed_collections_cache_fingerprint(failing, max_age_seconds=5.0)
        await tcr.read_published_themes(
            max_age_seconds=5.0, session_factory=lambda: failing
        )
        await fc.feed_collections_cache_fingerprint(failing, max_age_seconds=5.0)
        await tcr.read_published_themes(
            max_age_seconds=5.0, session_factory=lambda: failing
        )
        errs = [r for r in caplog.records if r.levelno >= logging.ERROR]
        assert len(errs) == 2

    # Recovery clears fallback state; a future 5-min episode logs once again.
    clock["mono"] = 1320.0
    clock["wall"] = 2_000_320.0
    fc._fingerprint_retry_after = 0.0
    tcr._published_retry_after = 0.0
    await fc.feed_collections_cache_fingerprint(healthy_fp, max_age_seconds=5.0)
    await tcr.read_published_themes(
        max_age_seconds=5.0, session_factory=lambda: healthy_th
    )
    assert fc.get_fingerprint_cache_status()["state"] == "fresh"
    assert tcr.get_published_themes_cache_status()["state"] == "fresh"


async def test_health_surfaces_discover_publication_reads_and_asyncmock_session(
    monkeypatch,
):
    import json
    from unittest.mock import AsyncMock, MagicMock

    from app.routes import health as health_route

    fc._reset_fingerprint_cache_for_tests()
    tcr._reset_published_cache_for_tests()
    clock = {"mono": 500.0, "wall": 1_000_000.0}
    monkeypatch.setattr(fc.time, "monotonic", lambda: clock["mono"])
    monkeypatch.setattr(tcr.time, "monotonic", lambda: clock["mono"])

    # AsyncMock DB double must not raise TypeError on begin_nested().
    mock_res = MagicMock()
    mock_res.scalar.return_value = "4:1"
    mock_session = AsyncMock()
    mock_session.execute.return_value = mock_res
    fp = await fc.feed_collections_cache_fingerprint(mock_session, max_age_seconds=5.0)
    assert isinstance(fp, str) and fp

    class _Conn:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def execute(self, *_args):
            return None

    class _FakeEngine:
        def connect(self):
            return _Conn()

    fake_rc = MagicMock()
    fake_rc.ping.return_value = True
    monkeypatch.setattr("app.services.database.engine", _FakeEngine())
    monkeypatch.setattr("app.tasks.redis_state.get_redis_client", lambda: fake_rc)

    clock["mono"] = 502.5
    resp = await health_route.api_health_check()
    body = json.loads(resp.body.decode("utf-8"))
    pub = body["discover_publication_reads"]
    assert pub["collections_fingerprint"]["state"] == "fresh"
    assert pub["collections_fingerprint"]["copy_age_seconds"] == 2.5
    assert pub["published_themes"]["state"] == "uninitialized"

    # Trigger fallback and verify health reports it without extra I/O.
    clock["mono"] = 512.5
    await fc.feed_collections_cache_fingerprint(
        _Session(error=RuntimeError("db down")), max_age_seconds=5.0
    )
    clock["mono"] = 520.0
    resp2 = await health_route.api_health_check()
    body2 = json.loads(resp2.body.decode("utf-8"))
    fp_status = body2["discover_publication_reads"]["collections_fingerprint"]
    assert fp_status["state"] == "fallback"
    assert fp_status["source"] == "fallback_process"
    assert fp_status["copy_age_seconds"] == 20.0
    assert fp_status["fallback_duration_seconds"] == 7.5

