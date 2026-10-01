"""#10114: a live concept page's first reader after a quiet spell gets a rebuilt payload.

Measured on production 2026-10-01: `event:golf:bank-of-utah-championship` served
an envelope built ~17:41Z to the 18:34Z reader during live round 1 ("not updating
· 53m ago"), with zero `refresh_event_concept` runs between 16:32Z and 18:34Z. No
refresh failed — nothing warms a non-major golf tournament, so the mirror was
simply as old as the last read, and `STALE_TTL` (24h) put no bound on serving it.
Reproduced 18:54Z: three reads served a 12-minute-old mirror and the dispatched
refresh started ~2 min later, behind 69 background jobs.
"""

import asyncio
from datetime import timedelta
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from app.routes import event as event_route
from app.utils import event_concept_cache as cache_mod
from tests.test_event_concept_swr import _FakeRedis

KEY = "event:golf:bank-of-utah-championship"
KEYS = cache_mod.cache_keys(KEY)


class _Adapter:
    def __init__(self, *, mode="ok", status="live"):
        self.mode = mode
        self.status = status
        self.calls = 0
        self.completed = 0

    async def build_event(self, slug, db):
        self.calls += 1
        if self.mode == "raise":
            raise RuntimeError("boom")
        if self.mode == "none":
            return None
        if self.mode == "slow":
            await asyncio.sleep(5)
        self.completed += 1
        return {"event": {"name": "Bank of Utah", "status": self.status}, "_build_n": self.calls}


def _seed_mirror(rc, *, age_s, status="live"):
    """A mirror built `age_s` ago, primary already expired."""
    payload = cache_mod.stamp_envelope(
        {"event": {"name": "Bank of Utah", "status": status}, "_build_n": 0},
        created_at=cache_mod._utcnow() - timedelta(seconds=age_s),
        lifecycle_watermark=None,
    )
    rc.setex(KEYS.stale, cache_mod.STALE_TTL, cache_mod.encode_payload(payload))
    return rc.store[KEYS.stale]


async def _get(*, adapter, rc):
    with patch.object(event_route, "get_adapter", return_value=adapter), patch(
        "app.tasks.redis_state.get_redis_client", return_value=rc
    ):
        return await event_route.get_event_concept(KEY, db=None)


@pytest.mark.asyncio
async def test_the_53_minute_live_mirror_is_rebuilt_before_it_is_served():
    """THE specimen. A live mirror 53 min old must not reach the reader as-is."""
    rc, adapter = _FakeRedis(), _Adapter()
    _seed_mirror(rc, age_s=53 * 60)

    with patch("app.tasks.celery_app.send_task") as send:
        out = await _get(adapter=adapter, rc=rc)

    assert adapter.calls == 1, "the 53-minute live mirror was served without a rebuild"
    assert out["_build_n"] == 1
    assert out[cache_mod.ENVELOPE_FIELD]["availability"] == cache_mod.AVAILABILITY_LIVE
    assert send.call_count == 0
    assert KEYS.refresh_lock not in rc.store, "the inline rebuild must give its lock back"
    assert cache_mod.decode_payload(rc.store[KEYS.stale])["_build_n"] == 1


@pytest.mark.asyncio
async def test_a_live_mirror_inside_the_ceiling_is_still_served_mirror_first():
    """Control: under the ceiling the LAT-P021 serve is unchanged."""
    rc, adapter = _FakeRedis(), _Adapter()
    _seed_mirror(rc, age_s=cache_mod.LIVE_STALE_SERVE_CEILING - 30)

    with patch("app.tasks.celery_app.send_task") as send:
        out = await _get(adapter=adapter, rc=rc)

    assert adapter.calls == 0
    assert out[cache_mod.ENVELOPE_FIELD]["availability"] == cache_mod.AVAILABILITY_STALE_OK
    assert send.call_count == 1


@pytest.mark.parametrize("status", ["upcoming", "settled", None])
@pytest.mark.asyncio
async def test_a_non_live_mirror_is_served_mirror_first_however_old(status):
    """Control: only LIVE content ages by the minute; the rest keeps the 0.4s serve."""
    rc, adapter = _FakeRedis(), _Adapter(status=status)
    _seed_mirror(rc, age_s=53 * 60, status=status)

    with patch("app.tasks.celery_app.send_task") as send:
        out = await _get(adapter=adapter, rc=rc)

    assert adapter.calls == 0
    assert out[cache_mod.ENVELOPE_FIELD]["availability"] == cache_mod.AVAILABILITY_STALE_OK
    assert send.call_count == 1


@pytest.mark.asyncio
async def test_a_held_lock_serves_the_mirror_without_a_second_builder():
    """Single-flight holds past the ceiling too: a rebuild in flight is not doubled."""
    rc, adapter = _FakeRedis(), _Adapter()
    _seed_mirror(rc, age_s=53 * 60)
    rc.set(KEYS.refresh_lock, "someone-else", nx=True, ex=cache_mod.REFRESH_LOCK_TTL)

    with patch("app.tasks.celery_app.send_task") as send:
        out = await _get(adapter=adapter, rc=rc)

    assert adapter.calls == 0
    assert out[cache_mod.ENVELOPE_FIELD]["availability"] == cache_mod.AVAILABILITY_STALE_OK
    assert send.call_count == 0
    assert rc.store[KEYS.refresh_lock] == b"someone-else"


@pytest.mark.asyncio
async def test_an_overrunning_rebuild_is_cancelled_and_falls_back_to_mirror_plus_refresh():
    rc, adapter = _FakeRedis(), _Adapter(mode="slow")
    seeded = _seed_mirror(rc, age_s=53 * 60)

    with patch.object(event_route, "LIVE_INLINE_REBUILD_BUDGET", 0.05), patch(
        "app.tasks.celery_app.send_task"
    ) as send:
        out = await _get(adapter=adapter, rc=rc)

    assert out[cache_mod.ENVELOPE_FIELD]["availability"] == cache_mod.AVAILABILITY_STALE_OK
    assert adapter.completed == 0, "the overrun build was not cancelled"
    assert rc.store[KEYS.stale] == seeded, "a cancelled build must not write"
    assert send.call_count == 1, "an overrun must still put a refresh behind the mirror"
    # The lock now belongs to the dispatched refresh, which carries its token.
    assert rc.store[KEYS.refresh_lock] == send.call_args.kwargs["args"][1].encode()


@pytest.mark.asyncio
async def test_a_rebuild_that_raises_serves_the_mirror_and_frees_the_lock():
    rc, adapter = _FakeRedis(), _Adapter(mode="raise")
    _seed_mirror(rc, age_s=53 * 60)

    with patch("app.tasks.celery_app.send_task"):
        out = await _get(adapter=adapter, rc=rc)

    assert out[cache_mod.ENVELOPE_FIELD]["availability"] == cache_mod.AVAILABILITY_STALE_OK
    assert out["_build_n"] == 0
    assert KEYS.refresh_lock not in rc.store


@pytest.mark.asyncio
async def test_a_rebuild_that_refuses_the_key_404s():
    rc, adapter = _FakeRedis(), _Adapter(mode="none")
    _seed_mirror(rc, age_s=53 * 60)

    with patch("app.tasks.celery_app.send_task"), pytest.raises(HTTPException) as exc:
        await _get(adapter=adapter, rc=rc)

    assert exc.value.status_code == 404
    assert KEYS.refresh_lock not in rc.store


def test_the_ceiling_reads_the_stored_content_time_and_the_live_status():
    now = cache_mod._utcnow()

    def stamped(age_s, status):
        return cache_mod.stamp_envelope(
            {"event": {"status": status}},
            created_at=now - timedelta(seconds=age_s),
            lifecycle_watermark=None,
        )

    ceiling = cache_mod.LIVE_STALE_SERVE_CEILING
    assert cache_mod.live_mirror_past_ceiling(stamped(ceiling + 1, "live"), now)
    assert not cache_mod.live_mirror_past_ceiling(stamped(ceiling - 1, "live"), now)
    assert not cache_mod.live_mirror_past_ceiling(stamped(86_000, "settled"), now)
    assert not cache_mod.live_mirror_past_ceiling({"event": "junk"}, now)
