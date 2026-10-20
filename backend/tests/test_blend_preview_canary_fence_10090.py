"""#10090 — the production boundary of display-before-persist.

SHIP: a held production event page receives correct changed blended
probabilities while database persistence is delayed. The preview contract
itself is pinned by `test_blend_preview_display_before_persist_195.py` and
`test_blend_preview_195_review_guards.py`; these pin what carries it into the
production topology:

* the canary switch: ONE named source, named events only; everything else in
  a batch runs the statements it always ran, in the one sorted lock order;
* the fence: a process claims an epoch at Redis before its first blend, a
  replacement's claim drops the superseded process's blends AT REDIS (its
  revokes still pass), and a lost owner key fails closed without a re-claim.

Production runs each venue arm in its own process (`WS_VENUE_PROCESSES=1`),
so no test here composes the two arms' pending values together.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy.sql.dml import Update

from app.tasks.live_blend_refresh import LiveBlendRefresher
from app.utils import blend_preview
from tests.test_blend_preview_display_before_persist_195 import (
    STORED,
    _capture_previews,
    _event,
    _PreviewSession,
)
from tests.test_event_frame_batching_10659 import private_redis_socket  # noqa: F401 (fixture)
from tests.test_live_blend_refresh import _one_event_refresher

FRESH = datetime.now(timezone.utc).isoformat()


@pytest.fixture(autouse=True)
def _canary(monkeypatch):
    blend_preview.reset_registry_for_tests()
    monkeypatch.setenv(blend_preview.SOURCE_ENV, "polymarket")
    monkeypatch.setenv(blend_preview.EVENT_IDS_ENV, "2")
    yield
    blend_preview.reset_registry_for_tests()


def _ctx():
    return SimpleNamespace(status="live", espn_win_prob_home=None, opening_home_probability=None)


def _updated_event_id(statement) -> int:
    """The event id an `UPDATE events … WHERE id = :id` statement targets."""
    params = statement.compile().params
    [eid] = [v for k, v in params.items() if k.startswith("id_")]
    return eid


class TestTheSwitch:
    def test_parsing(self, monkeypatch):
        monkeypatch.setenv(blend_preview.EVENT_IDS_ENV, " 3, 11 ,3 ")
        assert blend_preview.preview_event_ids() == frozenset({3, 11})
        assert blend_preview.preview_events_for("polymarket") == frozenset({3, 11})
        assert blend_preview.preview_events_for("kalshi") == frozenset()
        assert blend_preview.preview_route_events() == frozenset({3, 11})
        for bad in ("3,", "3;4", "-3", "3.0", "abc"):
            monkeypatch.setenv(blend_preview.EVENT_IDS_ENV, bad)
            assert blend_preview.preview_event_ids() == frozenset(), bad
        monkeypatch.setenv(blend_preview.EVENT_IDS_ENV, "3")
        monkeypatch.setenv(blend_preview.SOURCE_ENV, "Polymarket")
        assert blend_preview.preview_route_events() == frozenset(), "an exact source name only"

    def test_only_the_named_arm_previews(self):
        assert LiveBlendRefresher("polymarket").preview_events == frozenset({2})
        kalshi = LiveBlendRefresher("kalshi")
        assert kalshi.preview is False and kalshi.preview_events == frozenset()

    async def test_a_mixed_batch_previews_only_the_canary_and_keeps_one_sorted_lock_order(self, monkeypatch):
        rows = [_event(eid) for eid in (1, 2, 3)]
        session = _PreviewSession([(m, e) for e, m in rows], None, stored=STORED, rev=10)
        r, committed = _one_event_refresher(monkeypatch, session)
        previews = _capture_previews(monkeypatch, r, session)

        await r._refresh_batch([1, 2, 3], 0.0)

        assert [f["event_id"] for _, f in previews] == [2]
        assert [u for u, _ in previews] == [0], "the canary preview precedes every UPDATE"
        assert [_updated_event_id(u) for u in session.updates] == [1, 2, 3], (
            "one sorted lock order (#837), canary or not"
        )
        assert committed == [] and r._lock_retry == {1, 2, 3}
        assert not blend_preview.registry().has_pending(1)
        assert not blend_preview.registry().has_pending(3)

    async def test_a_batch_without_a_canary_event_reads_and_writes_as_before(self, monkeypatch):
        rows = [_event(eid) for eid in (1, 3)]
        session = _PreviewSession([(m, e) for e, m in rows], None, stored=STORED, rev=10)
        r, _ = _one_event_refresher(monkeypatch, session)
        assert r.preview is True

        async def _forbidden(frames):
            raise AssertionError("no preview publication for a non-canary batch")

        monkeypatch.setattr(r, "_publish_previews", _forbidden)
        await r._refresh_batch([1, 3], 0.0)

        assert session.preview_reads == 0, "no extra columns on a non-canary read"
        assert [_updated_event_id(u) for u in session.updates] == [1, 3]


async def _redis(socket):
    from redis.asyncio import Redis

    return Redis(unix_socket_path=str(socket))


def _refresher(redis):
    r = LiveBlendRefresher("polymarket")
    r._redis = redis
    return r


def _blend(registry, eid=2, value=0.9):
    [frame] = registry.propose(eid, "polymarket", value=value, event=_ctx(),
                               row_sources=STORED, row_rev=10)
    return frame


async def _drain(pubsub):
    out = []
    while True:
        message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.2)
        if message is None:
            return out
        out.append(json.loads(message["data"]))


class TestTheFence:
    async def test_the_first_publication_claims_an_epoch_and_stamps_every_frame(self, private_redis_socket):
        from app.utils import live_push

        redis, listener = await _redis(private_redis_socket), await _redis(private_redis_socket)
        try:
            pubsub = listener.pubsub()
            await pubsub.subscribe(live_push.event_channel(2))
            await pubsub.get_message(timeout=1)
            await redis.set(blend_preview.FENCE_EPOCH_KEY, 41)
            r = _refresher(redis)
            reg = blend_preview.registry()
            assert reg.epoch is None

            await r._publish_previews([_blend(reg)])

            assert reg.epoch == 42
            assert await redis.get(blend_preview.fence_owner_key("polymarket")) == b"42"
            [got] = await _drain(pubsub)
            assert got["preview"]["epoch"] == 42 and got["preview"]["kind"] == "blend"
            assert "rev" not in got
            assert r.preview_stats == {"published": 1, "revoked": 0, "fenced": 0, "publish_errors": 0}
            assert await live_push.latest_frames([2]) == []
            assert await redis.exists(live_push.latest_frame_key(2)) == 0, "never retained"
            await pubsub.aclose()
        finally:
            await redis.aclose()
            await listener.aclose()

    async def test_a_replacement_claim_fences_the_old_process_at_redis(self, private_redis_socket):
        """Restart overlap: the old worker is still running when its
        replacement claims. Whatever the old one publishes afterwards cannot
        reach a reader as a blend; its revokes may (they only remove)."""
        from app.utils import live_push

        redis, listener = await _redis(private_redis_socket), await _redis(private_redis_socket)
        try:
            pubsub = listener.pubsub()
            await pubsub.subscribe(live_push.event_channel(2))
            await pubsub.get_message(timeout=1)

            old_reg = blend_preview.PreviewRegistry()
            new_reg = blend_preview.PreviewRegistry()
            old, new = _refresher(redis), _refresher(redis)

            blend_preview._REGISTRY = old_reg
            first = _blend(old_reg, value=0.80)
            await old._publish_previews([first])
            blend_preview._REGISTRY = new_reg
            await new._publish_previews([_blend(new_reg, value=0.85)])
            blend_preview._REGISTRY = old_reg
            late = _blend(old_reg, value=0.95)
            [revoke] = old_reg.refused(2, "polymarket", "no_reading")
            await old._publish_previews([late, revoke])

            frames = await _drain(pubsub)
            assert new_reg.epoch > old_reg.epoch
            assert [(f["preview"]["kind"], f["preview"]["epoch"]) for f in frames] == [
                ("blend", old_reg.epoch), ("blend", new_reg.epoch), ("revoke", old_reg.epoch),
            ], "the superseded process's late blend never left Redis"
            assert old.preview_stats["fenced"] == 1 and old.preview_stats["revoked"] == 1
            assert old.preview_stats["published"] == 1, "only its pre-claim blend counts"
            assert await redis.get(blend_preview.fence_owner_key("polymarket")) == str(new_reg.epoch).encode()
            await pubsub.aclose()
        finally:
            await redis.aclose()
            await listener.aclose()

    async def test_a_lost_owner_key_fails_closed_and_is_never_reclaimed(self, private_redis_socket):
        from app.utils import live_push

        redis, listener = await _redis(private_redis_socket), await _redis(private_redis_socket)
        try:
            pubsub = listener.pubsub()
            await pubsub.subscribe(live_push.event_channel(2))
            await pubsub.get_message(timeout=1)
            r = _refresher(redis)
            reg = blend_preview.registry()
            await r._publish_previews([_blend(reg, value=0.8)])
            epoch = reg.epoch
            await _drain(pubsub)

            await redis.delete(blend_preview.fence_owner_key("polymarket"))
            await r._publish_previews([_blend(reg, value=0.85)])

            assert await _drain(pubsub) == []
            assert reg.epoch == epoch, "no re-claim from inside a running process"
            assert await redis.exists(blend_preview.fence_owner_key("polymarket")) == 0
            assert r.preview_stats["fenced"] == 1
            await pubsub.aclose()
        finally:
            await redis.aclose()
            await listener.aclose()

    async def test_no_claim_means_no_publication(self, monkeypatch):
        """Redis unreachable at the claim: nothing goes out, nothing raises."""
        r = LiveBlendRefresher("polymarket")

        class _Down:
            @property
            def connection_pool(self):
                raise ConnectionError("redis down")

        monkeypatch.setattr(r, "_client", lambda: _Down())
        reg = blend_preview.registry()
        await r._publish_previews([_blend(reg)])
        assert reg.epoch is None
        assert r.preview_stats == {"published": 0, "revoked": 0, "fenced": 0, "publish_errors": 1}

    def test_epochs_come_from_one_counter_for_every_source(self):
        assert blend_preview.FENCE_EPOCH_KEY == "live:blend_preview:epoch"
        assert blend_preview.fence_owner_key("kalshi") != blend_preview.fence_owner_key("polymarket")
        assert "INCR" in blend_preview.FENCE_CLAIM_SCRIPT and "SET" in blend_preview.FENCE_CLAIM_SCRIPT
        assert "owner == ARGV[1]" in blend_preview.FENCE_PUBLISH_SCRIPT


class TestTheUpdateHelperSeesTheTarget:
    def test_compile_params_name_the_event(self):
        from sqlalchemy import update

        from app.models import Event

        assert _updated_event_id(update(Event).where(Event.id == 5).values(status="live")) == 5
        assert isinstance(update(Event), Update)
