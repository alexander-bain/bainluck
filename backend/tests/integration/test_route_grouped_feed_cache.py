"""LAT-P100 — route-level proof that the grouped-feed cache is on the hot path.

The unit suite (`tests/test_grouped_feed_cache.py`) proves the KEY contract. It
cannot prove the thing that actually matters, which is that the real route reads
that key before it touches the database, and that the warmer reaches the same
key a real HTTP request reads.

That distinction has bitten this repo before: a guard that exercises a pure
helper stays green when the surface stops calling it. So every test here drives
the real ASGI route.
"""

import json
from contextlib import asynccontextmanager
from importlib import import_module
from unittest.mock import MagicMock

import pytest

from app.utils import request_cache as _rc
from app.utils.grouped_feed_cache import (
    GROUPED_FEED_CACHE_HEADER,
    grouped_feed_cache_key,
)

pcp = import_module("app.tasks.precompute_category_pages")


_WARM_PAYLOAD = {
    "feed": [{"type": "market", "market": {"id": 4242, "name": "a warmed row"}}],
    "total_grouped": 0,
    "total_ungrouped": 1,
    "group_counts": {"stat_prop": 0, "playoff_progression": 0, "threshold": 0},
}


class _RecordingRedis:
    """Records every read and write; serves whatever it was seeded with."""

    def __init__(self, seed: dict[str, dict] | None = None):
        self.reads: list[str] = []
        self.writes: list[tuple[str, int]] = []
        self._store = {k: json.dumps(v) for k, v in (seed or {}).items()}

    async def get(self, key):
        self.reads.append(key)
        return self._store.get(key)

    async def setex(self, key, ttl, body):
        self.writes.append((key, ttl))
        self._store[key] = body
        return True


async def _async(value):
    return value


def _reset_rc():
    _rc._reset_last_good_for_tests()
    _rc._reset_inflight_for_tests()
    _rc._reset_shared_client_for_tests()


def _install_redis(monkeypatch, fake):
    monkeypatch.setattr(_rc, "get_shared_async_redis", lambda: _async(fake))


def _install_task_session(monkeypatch, db):
    @asynccontextmanager
    async def fake_session():
        yield db

    monkeypatch.setattr("app.tasks.base.get_task_session", fake_session)


NATIVE_KEY = grouped_feed_cache_key(
    category=None, sport=None, sports_only=False, limit=20
)


async def test_a_warm_entry_is_served_without_touching_the_database(
    client, mock_db, monkeypatch
):
    """The claim in one test: a hit costs a Redis read, not a build.

    The DB assertion is the load-bearing half. A cache that returns the right
    body AFTER running the query it was added to avoid is not a cache, and a
    timing test on a mocked database cannot tell the two apart.
    """
    _reset_rc()
    fake = _RecordingRedis({NATIVE_KEY: _WARM_PAYLOAD})
    _install_redis(monkeypatch, fake)
    mock_db.execute.reset_mock()

    resp = await client.get("/api/futures/grouped-feed?limit=20")

    assert resp.status_code == 200
    assert resp.headers[GROUPED_FEED_CACHE_HEADER] == "hit"
    assert resp.json() == _WARM_PAYLOAD
    assert mock_db.execute.await_count == 0, (
        "the route queried the database on a cache HIT — the cache is not on the "
        "hot path and the warm buys nothing"
    )
    assert NATIVE_KEY in fake.reads


async def test_the_key_a_real_request_reads_is_the_key_the_warm_shape_publishes(
    client, mock_db, monkeypatch
):
    """Bar C1, end to end rather than derived twice from the same function."""
    _reset_rc()
    fake = _RecordingRedis()
    _install_redis(monkeypatch, fake)

    resp = await client.get("/api/futures/grouped-feed?limit=20")
    assert resp.status_code == 200
    read_keys = [k for k in fake.reads if not k.endswith(":stale")]
    assert read_keys, "the route read no cache key at all"

    shape = next(
        s for s in pcp.GROUPED_FEED_PREWARM_SHAPES if s["label"] == "grouped_native"
    )
    warmed = grouped_feed_cache_key(
        category=shape["category"],
        sport=shape["sport"],
        sports_only=shape["sports_only"],
        limit=shape["limit"],
    )
    assert read_keys[0] == warmed, (
        "the native Sports tab reads a key the warmer never publishes — the "
        "warm runs, logs success, and the tab still pays the full build"
    )


async def test_the_web_shape_is_a_different_entry_from_the_native_one(
    client, mock_db, monkeypatch
):
    """`sports_only` is a real selector, so it must be a real key difference."""
    _reset_rc()
    fake = _RecordingRedis()
    _install_redis(monkeypatch, fake)

    await client.get("/api/futures/grouped-feed?limit=20")
    await client.get("/api/futures/grouped-feed?limit=20&sports_only=true")

    primary = [k for k in fake.reads if not k.endswith(":stale")]
    assert len(set(primary)) == 2, (
        "the two Sports surfaces resolved to ONE cache entry — one of them is "
        "being served the other's body"
    )


async def test_a_stale_only_entry_is_served_and_labelled(client, mock_db, monkeypatch):
    """A failed or skipped beat must be invisible to users, not a 1-second stall."""
    _reset_rc()
    fake = _RecordingRedis({f"{NATIVE_KEY}:stale": _WARM_PAYLOAD})
    _install_redis(monkeypatch, fake)
    mock_db.execute.reset_mock()

    resp = await client.get("/api/futures/grouped-feed?limit=20")

    assert resp.status_code == 200
    assert resp.headers[GROUPED_FEED_CACHE_HEADER] == "stale_hit"
    assert resp.json() == _WARM_PAYLOAD
    assert mock_db.execute.await_count == 0


async def test_a_miss_is_labelled_and_an_empty_build_publishes_nothing(
    client, mock_db, monkeypatch
):
    """An empty read must never become shared truth for three minutes.

    `mock_db` returns no rows, so this request builds an empty feed. Publishing
    it would serve everybody an empty Sports board until it expired — strictly
    worse than the build it replaced.
    """
    _reset_rc()
    fake = _RecordingRedis()
    _install_redis(monkeypatch, fake)

    resp = await client.get("/api/futures/grouped-feed?limit=20")

    assert resp.status_code == 200
    assert resp.headers[GROUPED_FEED_CACHE_HEADER] == "miss"
    assert resp.json()["feed"] == []
    assert fake.writes == [], f"an empty feed was published: {fake.writes}"


async def test_a_client_cannot_force_a_cold_rebuild_over_http(
    client, mock_db, monkeypatch
):
    """The pre-warm marker is scope-only. Reachable, it would be a DoS lever."""
    _reset_rc()
    fake = _RecordingRedis({NATIVE_KEY: _WARM_PAYLOAD})
    _install_redis(monkeypatch, fake)
    mock_db.execute.reset_mock()

    from app.utils.grouped_feed_cache import GROUPED_FEED_PREWARM_SCOPE_KEY

    resp = await client.get(
        f"/api/futures/grouped-feed?limit=20&{GROUPED_FEED_PREWARM_SCOPE_KEY}=1",
        headers={GROUPED_FEED_PREWARM_SCOPE_KEY: "1"},
    )

    assert resp.status_code == 200
    assert resp.headers[GROUPED_FEED_CACHE_HEADER] == "hit"
    assert mock_db.execute.await_count == 0, (
        "a client forced a rebuild through a header or query param — that is a "
        "free lever on an expensive endpoint"
    )


async def test_the_warmer_rebuilds_instead_of_reading_its_own_entry(
    mock_db, monkeypatch
):
    """A warmer that read the cache would re-serve an ageing payload forever.

    It would return the existing entry, report `ok`, and refresh nothing —
    indistinguishable from working until the body is an hour old.
    """
    _reset_rc()
    fake = _RecordingRedis({NATIVE_KEY: _WARM_PAYLOAD})
    _install_redis(monkeypatch, fake)
    _install_task_session(monkeypatch, mock_db)
    mock_db.execute.reset_mock()

    shape = next(
        s for s in pcp.GROUPED_FEED_PREWARM_SHAPES if s["label"] == "grouped_native"
    )
    outcome = await pcp._prewarm_grouped_feed_shape(dict(shape), MagicMock())

    assert NATIVE_KEY not in fake.reads, (
        "the warmer read the entry it is supposed to replace — it would "
        "re-publish the same ageing payload forever"
    )
    assert mock_db.execute.await_count > 0, "the warmer did not rebuild"
    # `mock_db` yields no rows, so the honest outcome is `empty`, not `ok` — and
    # an empty warm must publish nothing.
    assert outcome["outcome"] == "empty"
    assert fake.writes == []


@pytest.mark.parametrize("label", ["grouped_native", "grouped_web"])
async def test_the_warmer_survives_a_dead_redis(label, mock_db, monkeypatch):
    """A warm target must never raise into the beat and kill its siblings."""
    _reset_rc()

    async def _boom():
        raise RuntimeError("redis is down")

    monkeypatch.setattr(_rc, "get_shared_async_redis", lambda: _boom())
    _install_task_session(monkeypatch, mock_db)

    shape = next(s for s in pcp.GROUPED_FEED_PREWARM_SHAPES if s["label"] == label)
    outcome = await pcp._prewarm_grouped_feed_shape(dict(shape), MagicMock())
    assert outcome["outcome"] in {"empty", "ok", "error"}
    assert "duration_s" in outcome
