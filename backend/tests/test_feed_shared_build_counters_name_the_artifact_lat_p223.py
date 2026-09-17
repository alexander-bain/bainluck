"""GATE for LAT-P223 (#2143 residual) — the cache's counters must NAME the
artifact that stopped being shared, and production must be able to read them.

## The ship

A reader opens Discover and waits ~1s instead of ~0.1s because the feed's most
expensive artifact (`market_load`, 692-775 ms of a cold build) is being rebuilt
per worker instead of read across workers. This file does not make that faster
— it makes it VISIBLE, which is the thing that was missing.

## Why this is a gate and not a nice-to-have

LAT-P221 (#2971) found `market_load` refused at publish on EVERY build, for
weeks, silently. The counter that was recording it — `cross_worker_publish_refused`
— was correct the whole time and had **no reader outside the test suite**:
`shared_build_stats()` has called itself "counters for the admin/latency panel"
since LAT-P103 while no route called it. The defect was eventually found by
probing `/api/feed` end-to-end, which is `always_sampled` and so contaminates
`/api/admin/latency-stats` with its own traffic while measuring.

Two things therefore have to hold, and each has a test below that fails without
the other half of the fix:

1. **The counters name the artifact.** Summed across namespaces, "the big
   artifact never publishes" is arithmetically indistinguishable from "the small
   ones churn healthily" — a nonzero refusal beside a large publish count reads
   as normal. That indistinguishability is what let LAT-P221 hide.
2. **Production can read them.** A counter with no reader is not an instrument.

## What these tests deliberately do NOT assert

Not a duration. A timing assertion on a cache is a flake generator and
LAT-P084's own gate says so. These assert attribution and reachability.
"""

from __future__ import annotations

import pytest

from app.utils import principal_independent_cache as pic


class _FakeRedis:
    """Serves the stage tier only — same discipline as the cold-worker suite."""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.sets = 0

    def _stage_key(self, key: str) -> bool:
        return str(key).startswith(pic.REDIS_KEY_PREFIX)

    async def get(self, key):
        if not self._stage_key(key):
            raise ConnectionError("only the stage tier is served by this fake")
        return self.store.get(key)

    async def set(self, key, value, ex=None):
        if not self._stage_key(key):
            raise ConnectionError("only the stage tier is served by this fake")
        self.sets += 1
        self.store[key] = value
        return True


@pytest.fixture
def fake_redis(monkeypatch):
    from app.utils import request_cache as _rc

    fake = _FakeRedis()

    async def _get_client():
        return fake

    monkeypatch.setattr(_rc, "get_shared_async_redis", _get_client)
    return fake


@pytest.fixture(autouse=True)
def _clean_shared_cache():
    pic.clear_shared_builds()
    yield
    pic.clear_shared_builds()


async def _build_small():
    return {"ok": 1}


# --------------------------------------------------------------------------
# THE HEADLINE GATE — attribution
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_refusal_is_attributed_to_the_refused_artifact_and_not_its_sibling(
    fake_redis, monkeypatch
):
    """THE gate. This is LAT-P221's exact shape, in miniature.

    One namespace is over the cap and is refused on every publish; a sibling
    namespace publishes fine. The aggregate sees `refused=1, publishes=1` — the
    reading that looked like healthy churn for weeks. `by_namespace` is the only
    view that can say WHICH artifact is not reaching another worker.
    """
    monkeypatch.setattr(pic, "MAX_ENVELOPE_BYTES", 512)

    async def _build_big():
        return {"blob": "x" * 4096}

    await pic.get_or_build("market_load", ("big", (), 1), _build_big)
    await pic.get_or_build("concepts", ("small", (), 1), _build_small)

    stats = pic.shared_build_stats()
    by_ns = stats["by_namespace"]

    # The aggregate view: both events, no way to tell them apart.
    assert stats["cross_worker_publish_refused"] == 1
    assert stats["cross_worker_publishes"] == 1

    # The view that names the artifact. The second assertion is the one that
    # makes this test non-vacuous: if `by_namespace` were merely a copy of the
    # aggregate, the healthy sibling would carry the refusal too.
    assert by_ns["market_load"]["cross_worker_publish_refused"] == 1
    assert "cross_worker_publish_refused" not in by_ns.get("concepts", {}), (
        "the refusal was attributed to a namespace that published fine — "
        "by_namespace is not actually per-namespace"
    )
    assert by_ns["concepts"]["cross_worker_publishes"] == 1
    assert (
        "cross_worker_publishes" not in by_ns["market_load"]
    ), "a refused artifact was also counted as published"


@pytest.mark.asyncio
async def test_the_two_views_count_the_same_events(fake_redis):
    """The per-namespace view is a second reading of the same events, never a
    separate tally that can drift. Every aggregate cross-worker counter must
    equal the sum of its per-namespace parts."""
    # A publish, a miss (cold read of a key never written), and a hit.
    await pic.get_or_build("concepts", ("a", (), 1), _build_small)
    pic.clear_shared_builds()  # cold worker: local empty, Redis warm
    await pic.get_or_build("concepts", ("a", (), 1), _build_small)  # hit
    await pic.get_or_build("canonical_counts", ("b", (), 1), _build_small)  # miss

    stats = pic.shared_build_stats()
    by_ns = stats["by_namespace"]

    assert stats["cross_worker_hits"] >= 1, "the scenario produced no hit to check"
    assert stats["cross_worker_misses"] >= 1, "the scenario produced no miss to check"

    for counter in (
        "cross_worker_hits",
        "cross_worker_misses",
        "cross_worker_failures",
        "cross_worker_publishes",
        "cross_worker_publish_refused",
    ):
        summed = sum(c.get(counter, 0) for c in by_ns.values())
        assert summed == stats[counter], (
            f"{counter}: aggregate {stats[counter]} but per-namespace sums to "
            f"{summed} — the two views have drifted"
        )


@pytest.mark.asyncio
async def test_a_worker_boundary_resets_both_views_together(fake_redis):
    """`clear_shared_builds()` models a cold worker, and a cold worker starts
    with cold counters. If only the aggregate reset, the per-namespace view
    would accumulate across a boundary the aggregate says never happened."""
    await pic.get_or_build("concepts", ("a", (), 1), _build_small)
    assert pic.shared_build_stats()["by_namespace"], "nothing was recorded to reset"

    pic.clear_shared_builds()

    stats = pic.shared_build_stats()
    assert stats["by_namespace"] == {}
    assert stats["cross_worker_publishes"] == 0


@pytest.mark.asyncio
async def test_the_namespace_view_is_bounded(fake_redis, monkeypatch):
    """A per-key dict in a process that lives for days is a leak unless it is
    bounded. The real namespace set is small and fixed; this proves an unbounded
    one cannot grow the dict without limit, and that the overflow is still
    COUNTED rather than dropped (a silently-discarded event is worse than a
    coarse one)."""
    monkeypatch.setattr(pic, "MAX_TRACKED_NAMESPACES", 4)

    for i in range(20):
        await pic.get_or_build(f"ns{i}", ("k", (), 1), _build_small)

    by_ns = pic.shared_build_stats()["by_namespace"]

    assert len(by_ns) <= 5, f"unbounded namespace tracking: {len(by_ns)} buckets"
    assert pic._NS_OVERFLOW_BUCKET in by_ns, "overflow events were dropped, not folded"
    summed = sum(c.get("cross_worker_publishes", 0) for c in by_ns.values())
    assert summed == pic.shared_build_stats()["cross_worker_publishes"] == 20


# --------------------------------------------------------------------------
# reachability — a counter with no reader is not an instrument
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_production_can_read_the_counters(fake_redis, monkeypatch):
    """The half LAT-P221 was missing. `shared_build_stats()` described itself as
    feeding the admin panel while no route called it, so the refusal it was
    faithfully counting was unreadable from production."""
    from httpx import ASGITransport, AsyncClient

    from app.main import app
    from app.routes import admin as admin_routes

    monkeypatch.setattr(pic, "MAX_ENVELOPE_BYTES", 512)
    monkeypatch.setattr(admin_routes, "_check_admin_secret", lambda *a, **k: None)

    async def _build_big():
        return {"blob": "x" * 4096}

    await pic.get_or_build("market_load", ("big", (), 1), _build_big)
    await pic.get_or_build("concepts", ("small", (), 1), _build_small)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/admin/shared-build-stats")

    assert resp.status_code == 200, resp.text
    body = resp.json()

    # The actionable read, computed for the operator rather than left to a scan.
    assert body["publish_refused_namespaces"] == ["market_load"]
    assert (
        body["stats"]["by_namespace"]["market_load"]["cross_worker_publish_refused"]
        == 1
    )
    # The rail must declare its own blindness: these are per-process counters,
    # so a zero is not proof of absence and the payload has to say so.
    assert isinstance(body["worker_pid"], int)
    assert "not proof of absence" in body["caveat"]


@pytest.mark.asyncio
async def test_the_endpoint_requires_the_admin_secret():
    """Gotcha #2: an admin route without `_check_admin_secret` is an open one."""
    from httpx import ASGITransport, AsyncClient

    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/admin/shared-build-stats")

    assert resp.status_code in (
        401,
        403,
    ), f"the rail answered {resp.status_code} with no secret — it is unguarded"
