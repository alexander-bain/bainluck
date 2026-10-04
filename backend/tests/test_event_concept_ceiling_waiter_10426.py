"""#10426: the reader that loses the past-ceiling single-flight waits for an inline build.

Measured on production 2026-10-04. `/event/golf/alfred-dunhill-links-championship`
was live (final round) and the reader was served a 21-hour-old Round-3 leaderboard
`stale_ok`, with no warning logged — the request had found the refresh lock held.
Reproduced 10:05Z: two reads 0.3s apart past the ceiling; the first rebuilt inline
in 2.2s (`live`), the second got a 2.4-minute-old mirror in 107ms (`stale_ok`). On
a page load the first read is the site server's title fetch
(`app/event/[domain]/[slug]/layout.tsx`) and the second is the browser's, which
does not re-fetch — so the reader kept the old leaderboard for the whole visit.
"""

import asyncio
import time
import uuid
from datetime import timedelta
from unittest.mock import patch

import pytest

from app.routes import event as event_route
from app.utils import event_concept_cache as cache_mod
from tests.test_event_concept_swr import _FakeRedis

KEY = "event:golf:alfred-dunhill-links-championship"
KEYS = cache_mod.cache_keys(KEY)


class _Adapter:
    def __init__(self, *, mode="ok", delay=0.3):
        self.mode = mode
        self.delay = delay
        self.calls = 0
        self.completed = 0

    async def build_event(self, slug, db):
        self.calls += 1
        await asyncio.sleep(self.delay)
        if self.mode == "raise":
            raise RuntimeError("boom")
        self.completed += 1
        return {"event": {"name": "Dunhill Links", "status": "live"}, "_build_n": self.calls}


def _seed_mirror(rc, *, age_s=21 * 3600):
    payload = cache_mod.stamp_envelope(
        {"event": {"name": "Dunhill Links", "status": "live"}, "_build_n": 0},
        created_at=cache_mod._utcnow() - timedelta(seconds=age_s),
        lifecycle_watermark=None,
    )
    rc.setex(KEYS.stale, cache_mod.STALE_TTL, cache_mod.encode_payload(payload))
    return payload


async def _get(*, adapter, rc):
    return await event_route.get_event_concept(KEY, db=None)


async def _race(adapter, rc, *, budget=None):
    """Two readers of the same past-ceiling key, the second a beat behind."""
    patches = [
        patch.object(event_route, "get_adapter", return_value=adapter),
        patch("app.tasks.redis_state.get_redis_client", return_value=rc),
        patch.object(cache_mod, "INLINE_WAIT_POLL_SECONDS", 0.01),
    ]
    if budget is not None:
        patches.append(patch.object(event_route, "LIVE_INLINE_REBUILD_BUDGET", budget))
    for p in patches:
        p.start()
    try:
        async def second():
            await asyncio.sleep(0.05)
            return await _get(adapter=adapter, rc=rc)

        return await asyncio.gather(_get(adapter=adapter, rc=rc), second())
    finally:
        for p in reversed(patches):
            p.stop()


def _availability(out):
    return out[cache_mod.ENVELOPE_FIELD]["availability"]


@pytest.mark.asyncio
async def test_the_second_reader_gets_the_rebuild_the_first_reader_started():
    """THE specimen. The browser's read must not be handed the 21-hour mirror."""
    rc, adapter = _FakeRedis(), _Adapter()
    _seed_mirror(rc)

    with patch("app.tasks.celery_app.send_task") as send:
        first, second = await _race(adapter, rc)

    assert adapter.calls == 1, "single-flight broke: the waiter built a second time"
    assert first["_build_n"] == 1 and _availability(first) == cache_mod.AVAILABILITY_LIVE
    assert second["_build_n"] == 1, "the second reader was served the 21-hour mirror"
    assert _availability(second) == cache_mod.AVAILABILITY_LIVE
    assert send.call_count == 0
    assert KEYS.refresh_lock not in rc.store


@pytest.mark.asyncio
async def test_a_dispatched_refresh_holding_the_lock_is_not_waited_for():
    """Control: a background refresh can be minutes away — keep the mirror-first serve."""
    rc, adapter = _FakeRedis(), _Adapter()
    _seed_mirror(rc)
    # A route-dispatched refresh's token: a bare uuid, no inline prefix.
    rc.set(KEYS.refresh_lock, uuid.UUID(int=1).hex, nx=True, ex=cache_mod.REFRESH_LOCK_TTL)

    with patch.object(event_route, "get_adapter", return_value=adapter), patch(
        "app.tasks.redis_state.get_redis_client", return_value=rc
    ), patch.object(event_route, "LIVE_INLINE_REBUILD_BUDGET", 5.0), patch(
        "app.tasks.celery_app.send_task"
    ) as send:
        started = time.monotonic()
        out = await _get(adapter=adapter, rc=rc)
        elapsed = time.monotonic() - started

    assert elapsed < 1.0, f"waited {elapsed:.2f}s behind a background refresh"
    assert adapter.calls == 0
    assert out["_build_n"] == 0
    assert _availability(out) == cache_mod.AVAILABILITY_STALE_OK
    assert send.call_count == 0


@pytest.mark.asyncio
async def test_a_waiter_behind_an_overrunning_inline_build_falls_back_to_the_mirror():
    rc, adapter = _FakeRedis(), _Adapter(delay=5)
    _seed_mirror(rc)

    with patch("app.tasks.celery_app.send_task") as send:
        first, second = await _race(adapter, rc, budget=0.3)

    assert adapter.completed == 0
    assert _availability(first) == cache_mod.AVAILABILITY_STALE_OK
    assert _availability(second) == cache_mod.AVAILABILITY_STALE_OK
    assert second["_build_n"] == 0
    assert send.call_count == 1, "the overrun still puts exactly one refresh behind it"


@pytest.mark.asyncio
async def test_a_waiter_behind_an_inline_build_that_raises_falls_back_to_the_mirror():
    rc, adapter = _FakeRedis(), _Adapter(mode="raise")
    _seed_mirror(rc)

    with patch("app.tasks.celery_app.send_task"):
        first, second = await _race(adapter, rc)

    assert adapter.calls == 1
    assert second["_build_n"] == 0
    assert _availability(second) == cache_mod.AVAILABILITY_STALE_OK
    assert KEYS.refresh_lock not in rc.store


@pytest.mark.asyncio
async def test_a_wedged_inline_token_bounds_the_wait_by_the_budget():
    rc = _FakeRedis()
    stale = _seed_mirror(rc)
    rc.set(KEYS.refresh_lock, cache_mod.INLINE_TOKEN_PREFIX + "wedged", nx=True, ex=120)

    with patch.object(cache_mod, "INLINE_WAIT_POLL_SECONDS", 0.01):
        started = time.monotonic()
        out = await cache_mod.await_inline_build(rc, KEYS, stale, 0.2)
        elapsed = time.monotonic() - started

    assert out is None
    assert 0.15 <= elapsed < 1.0


@pytest.mark.asyncio
async def test_a_primary_no_newer_than_the_mirror_is_not_returned_as_fresh():
    """The holder let go, but nothing newer landed — never relabel old content `live`."""
    rc = _FakeRedis()
    stale = _seed_mirror(rc)
    rc.setex(KEYS.primary, cache_mod.ENVELOPE_TTL, cache_mod.encode_payload(stale))
    rc.set(KEYS.refresh_lock, cache_mod.INLINE_TOKEN_PREFIX + "x", nx=True, ex=120)

    async def let_go():
        await asyncio.sleep(0.05)
        rc.delete(KEYS.refresh_lock)

    with patch.object(cache_mod, "INLINE_WAIT_POLL_SECONDS", 0.01):
        out, _ = await asyncio.gather(
            cache_mod.await_inline_build(rc, KEYS, stale, 2.0), let_go()
        )

    assert out is None


def test_only_the_inline_path_marks_its_token():
    rc = _FakeRedis()
    inline = cache_mod.acquire_refresh_lock(rc, KEYS, inline=True)
    assert inline.startswith(cache_mod.INLINE_TOKEN_PREFIX)
    assert cache_mod.release_refresh_lock(rc, KEYS, inline)

    dispatched = cache_mod.acquire_refresh_lock(rc, KEYS)
    assert not dispatched.startswith(cache_mod.INLINE_TOKEN_PREFIX)
