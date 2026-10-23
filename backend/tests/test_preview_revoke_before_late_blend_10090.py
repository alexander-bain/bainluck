"""#10090 — a live probability does not reappear after its newer revocation.

The single-source producer composes a blend (allocating its seq) BEFORE it
takes the publication lock, and sends batches in lock order. A batch that
waits behind another can therefore hold blend seq N while the batch ahead
sends `revoke through_seq >= N` (an expiry found by the observation path's
`prepare_frames`, which runs under the lock). The Redis fence checks only the
epoch, so the late blend passed; a reader holding nothing after the revoke
keeps no memory of N (`frontend/lib/blendPreview.ts` `previewAfter`, the iOS
singleton path), so the withdrawn value showed again for its `ttl_ms`.

Reported by Speed's source-extracted probe (artifacts/live-revoke-source-
receipt-20261021, sha256 18e48f10…). These run the real `_publish_previews`
and registry against a real Redis and read the wire.
"""

from __future__ import annotations

import asyncio

import pytest

from app.utils import blend_preview
from tests.test_blend_preview_canary_fence_10090 import (
    _canary,  # noqa: F401 (autouse fixture)
    _ctx,
    _drain,
    _redis,
    _refresher,
)
from tests.test_blend_preview_display_before_persist_195 import STORED
from tests.test_event_frame_batching_10659 import private_redis_socket  # noqa: F401 (fixture)


def _propose(reg, value):
    [frame] = reg.propose(2, "polymarket", value=value, event=_ctx(), row_sources=STORED, row_rev=10)
    return frame


def _wire(frames):
    return [(f["preview"]["kind"], f["preview"]["seq"], f["preview"].get("through_seq")) for f in frames]


def _reappears(frames) -> bool:
    """A blend sent after a revoke of the same epoch that withdrew its seq."""
    through = {}
    for f in frames:
        p = f["preview"]
        if p["kind"] == "revoke":
            through[p["epoch"]] = max(through.get(p["epoch"], 0), p["through_seq"])
        elif p["seq"] <= through.get(p["epoch"], 0):
            return True
    return False


async def _late_blend_behind_expiry(redis, clock, *, compose_after_revoke=False):
    """The probe's order: the observation path holds the lock; a price batch
    composes while it waits; the expiry sent first withdraws that seq."""
    r = _refresher(redis)
    reg = blend_preview.registry()
    await r._publish_previews([_propose(reg, 0.57)])  # seq 1 at t=0, claims the epoch
    started, resume = asyncio.Event(), asyncio.Event()
    late = []

    async def prepare_frames():  # what `preview_accepted_observations` hands in
        started.set()
        await resume.wait()
        clock[0] = 60.01
        return reg.expire()

    observation = asyncio.create_task(r._publish_previews([], prepare_frames=prepare_frames))
    await started.wait()
    clock[0] = 59.8
    if not compose_after_revoke:
        late.append(_propose(reg, 0.58))  # seq 2, ttl 200 ms, queued behind the lock
    prices = asyncio.create_task(r._publish_previews(late))
    await asyncio.sleep(0)
    resume.set()
    await asyncio.gather(observation, prices)
    if compose_after_revoke:
        clock[0] = 61.0
        await r._publish_previews([_propose(reg, 0.58)])
    return r


class TestALateBlendBehindItsRevoke:
    @pytest.fixture
    def clock(self, monkeypatch):
        clock = [0.0]
        blend_preview._REGISTRY = blend_preview.PreviewRegistry(
            clock=lambda: clock[0], max_uncommitted_s=60)
        return clock

    async def test_a_blend_queued_behind_a_sent_revoke_never_reaches_readers(self, private_redis_socket, clock):
        from app.utils import live_push

        redis, listener = await _redis(private_redis_socket), await _redis(private_redis_socket)
        try:
            pubsub = listener.pubsub()
            await pubsub.subscribe(live_push.event_channel(2))
            await pubsub.get_message(timeout=1)

            r = await _late_blend_behind_expiry(redis, clock)

            frames = await _drain(pubsub)
            assert _wire(frames) == [("blend", 1, None), ("revoke", 3, 2)], (
                "the seq-2 blend composed before the lock was withdrawn by the expiry sent first"
            )
            assert not _reappears(frames)
            assert r.preview_stats["withdrawn"] == 1
            assert r.preview_stats["fenced"] == 0 and r.preview_stats["publish_errors"] == 0
            assert not blend_preview.registry().has_pending(2)
            await pubsub.aclose()
        finally:
            await redis.aclose()
            await listener.aclose()

    async def test_a_blend_composed_after_the_revoke_still_publishes(self, private_redis_socket, clock):
        """Control: only a withdrawn seq is refused; the next value shows."""
        from app.utils import live_push

        redis, listener = await _redis(private_redis_socket), await _redis(private_redis_socket)
        try:
            pubsub = listener.pubsub()
            await pubsub.subscribe(live_push.event_channel(2))
            await pubsub.get_message(timeout=1)

            r = await _late_blend_behind_expiry(redis, clock, compose_after_revoke=True)

            frames = await _drain(pubsub)
            assert _wire(frames) == [("blend", 1, None), ("revoke", 2, 1), ("blend", 3, None)]
            assert frames[-1]["p"] is not None and frames[-1]["preview"]["ttl_ms"] > 0
            assert "withdrawn" not in r.preview_stats
            await pubsub.aclose()
        finally:
            await redis.aclose()
            await listener.aclose()

    async def test_a_batch_that_orders_its_blend_before_its_revoke_is_sent_whole(self, private_redis_socket, clock):
        """Control: in-batch order already reaches readers correctly, so a
        blend followed by the revoke that withdraws it is not touched."""
        from app.utils import live_push

        redis, listener = await _redis(private_redis_socket), await _redis(private_redis_socket)
        try:
            pubsub = listener.pubsub()
            await pubsub.subscribe(live_push.event_channel(2))
            await pubsub.get_message(timeout=1)
            r = _refresher(redis)
            reg = blend_preview.registry()

            blend = _propose(reg, 0.6)
            [revoke] = reg.refused(2, "polymarket", "no_reading")
            await r._publish_previews([blend, revoke])

            assert _wire(await _drain(pubsub)) == [("blend", 1, None), ("revoke", 2, 1)]
            assert "withdrawn" not in r.preview_stats
            await pubsub.aclose()
        finally:
            await redis.aclose()
            await listener.aclose()


class TestTheRegistryRecord:
    def test_only_a_sent_revoke_withdraws_and_only_seqs_at_or_below_it(self):
        reg = blend_preview.PreviewRegistry(epoch=7)
        first = _propose(reg, 0.5)
        [revoke] = reg.refused(2, "polymarket", "no_reading")
        assert not reg.withdrawn(first), "allocated, not sent: in-batch order decides"
        reg.sending(revoke)
        assert reg.withdrawn(first)
        assert not reg.withdrawn(revoke), "revokes are never refused"
        assert not reg.withdrawn(_propose(reg, 0.6)), "a newer seq stands"
        assert not reg.withdrawn({"event_id": 99, "preview": {"kind": "blend", "seq": 1}})
