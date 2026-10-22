"""#10090 (attempt195 contract) — display a blend before its stamp commits.

SHIP: a held event page displays genuine blended probability changes while its
database persistence is blocked. These pin the backend half:

* the preview is composed from the SAME reading and published BEFORE the
  event-row UPDATE, and a lock timeout does not retract it;
* one event's lock wait never holds back a sibling's preview;
* a commit retires the preview; a refusal or a return to the stored value
  revokes it; a sibling's commit recomposes the other arm's pending value;
* previews carry no committed revision, are never retained for replay, and
  the stream forwards them only as `event: preview` when enabled;
* disabled, nothing new is read, published or forwarded.

The real event-row contention lives in Root's actual-page lab; the fakes here
raise the lock timeout the production code already handles.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy.sql.dml import Update

from app.tasks.live_blend_refresh import LiveBlendRefresher
from app.utils import blend_preview
from app.utils.aggregation import compute_aggregate_probability, stamp_source_reading
from tests.test_event_frame_batching_10659 import private_redis_socket  # noqa: F401 (fixture)
from tests.test_live_blend_refresh import (
    _LockedRowSession,
    _one_event_refresher,
)

FRESH = datetime.now(timezone.utc).isoformat()
STORED = {"kalshi": {"value": 0.5, "updated_at": FRESH}}


@pytest.fixture(autouse=True)
def _fresh_registry(monkeypatch):
    blend_preview.reset_registry_for_tests()
    # Explicit legacy subject: its ordering/fencing regressions remain covered.
    monkeypatch.setattr(blend_preview, "_REGISTRY", blend_preview.PreviewRegistry())
    monkeypatch.setattr(blend_preview, "preview_events_for",
                        lambda source: frozenset(range(1, 600)) if source == "polymarket" else frozenset())
    yield
    blend_preview.reset_registry_for_tests()


def _expected(stored, source, value, status="live"):
    bag = stamp_source_reading(dict(stored), source, value)
    return compute_aggregate_probability(
        SimpleNamespace(win_probability_sources=bag, status=status,
                        espn_win_prob_home=None, opening_home_probability=None),
        status,
    )


class _PreviewSession(_LockedRowSession):
    """The production read plus the preview arm's two trailing columns."""

    def __init__(self, market_rows, returned, *, stored, rev, locked=True):
        super().__init__(market_rows, [], returned, locked=locked)
        self.stored = stored
        self.stored_rev = rev
        self.preview_reads = 0

    async def execute(self, statement, *args, **kwargs):
        result = await super().execute(statement, *args, **kwargs)
        if not isinstance(statement, Update):
            keys = [getattr(c, "key", None) for c in getattr(statement, "selected_columns", ())]
            if "preview_sources" in keys:
                self.preview_reads += 1
                result._rows = [tuple(row) + (self.stored, self.stored_rev) for row in result._rows]
        return result


def _event(eid=1, status="live"):
    event = SimpleNamespace(
        id=eid, home_team_name="Phillies", away_team_name="Brewers",
        completed_at=None, status=status, espn_win_prob_home=None,
        opening_home_probability=None,
    )
    return event, SimpleNamespace(id=10 * eid, event_id=eid, name="Brewers vs Phillies")


def _capture_previews(monkeypatch, r, session):
    previews: list[tuple[int, dict]] = []

    async def _record(frames):
        # How many UPDATEs had been attempted when each preview went out.
        previews.extend((len(session.updates), f) for f in frames)

    monkeypatch.setattr(r, "_publish_previews", _record)
    return previews


def _blends(previews):
    return [f for _, f in previews if f["preview"]["kind"] == "blend"]


def _revokes(previews):
    return [f for _, f in previews if f["preview"]["kind"] == "revoke"]


class TestPreviewBeforePersistence:
    async def test_the_preview_goes_out_before_the_update_and_survives_its_lock_timeout(self, monkeypatch):
        event, market = _event()
        session = _PreviewSession([(market, event)], None, stored=STORED, rev=10)
        r, committed = _one_event_refresher(monkeypatch, session)
        previews = _capture_previews(monkeypatch, r, session)

        stats = await r.refresh([1])

        assert stats["lock_skipped"] == 1 and stats["stamped"] == 0
        assert committed == [], "nothing the database did not keep is a committed frame"
        [(updates_before, frame)] = previews
        assert updates_before == 0, "published before the event-row UPDATE was attempted"
        assert len(session.updates) == 1
        assert "rev" not in frame and frame["provisional"] is True
        assert frame["preview"]["base_rev"] == 10
        assert frame["preview"]["pending"] == {"polymarket": 0.9}
        assert frame["p"] == pytest.approx(_expected(STORED, "polymarket", 0.9))
        assert frame["p"] != pytest.approx(compute_aggregate_probability(SimpleNamespace(
            win_probability_sources=STORED, status="live", espn_win_prob_home=None,
            opening_home_probability=None), "live")), "a real change, not the stored blend"
        assert blend_preview.registry().has_pending(1, "polymarket"), "a lock wait does not retract it"
        assert r._lock_retry == {1}

    async def test_the_retry_republishes_then_its_commit_retires_the_preview_without_a_revoke(self, monkeypatch):
        event, market = _event()
        session = _PreviewSession([(market, event)], None, stored=STORED, rev=10)
        r, committed = _one_event_refresher(monkeypatch, session)
        previews = _capture_previews(monkeypatch, r, session)
        await r.refresh([1])

        session.locked = False
        session._returned = stamp_source_reading(dict(STORED), "polymarket", 0.9)
        session.returned_rev = 11
        stats = await r.refresh([])

        assert stats["stamped"] == 1
        first, second = _blends(previews)
        assert second["preview"]["seq"] > first["preview"]["seq"]
        assert [f["rev"] for f in committed] == [{"1": 11}]
        assert committed[0]["p"] == pytest.approx(second["p"]), "the commit confirms the preview"
        assert _revokes(previews) == []
        assert not blend_preview.registry().has_pending(1)

    async def test_a_refused_stamp_revokes_the_preview(self, monkeypatch):
        event, market = _event()
        # The UPDATE matches nothing: refused (later stored observation) or gone.
        session = _PreviewSession([(market, event)], None, stored=STORED, rev=10, locked=False)
        r, committed = _one_event_refresher(monkeypatch, session)
        previews = _capture_previews(monkeypatch, r, session)

        await r.refresh([1])

        [blend] = _blends(previews)
        [revoke] = _revokes(previews)
        assert committed == []
        assert revoke["preview"]["through_seq"] == blend["preview"]["seq"]
        assert revoke["preview"]["reason"] in {"stale", "no_row"}
        assert not blend_preview.registry().has_pending(1)

    async def test_a_reading_back_at_the_stored_value_revokes_the_pending_preview(self, monkeypatch):
        event, market = _event()
        session = _PreviewSession([(market, event)], None, stored=STORED, rev=10)
        r, _ = _one_event_refresher(monkeypatch, session)
        previews = _capture_previews(monkeypatch, r, session)
        await r.refresh([1])  # 0.9 previewed, row locked

        r._last_written_value[1] = 0.5
        r._last_write_at[1] = 10**9  # inside the re-stamp interval
        monkeypatch.setattr(
            "app.utils.live_blend.compute_source_home_probability",
            lambda group, home, away: SimpleNamespace(
                home_probability=0.5, away_probability=None, draw_probability=None,
                eligibility=None,
            ),
        )
        await r.refresh([1])

        [revoke] = _revokes(previews)
        assert revoke["preview"]["reason"] == "unchanged"
        assert not blend_preview.registry().has_pending(1)

    async def test_within_one_batch_every_preview_precedes_every_update(self, monkeypatch):
        """A multi-event `_refresh_batch` computes and previews all, then stamps."""
        (e1, m1), (e2, m2) = _event(1), _event(2)
        session = _PreviewSession([(m1, e1), (m2, e2)], None, stored=STORED, rev=10)
        r, _ = _one_event_refresher(monkeypatch, session)
        previews = _capture_previews(monkeypatch, r, session)

        await r._refresh_batch([1, 2], 0.0)

        assert sorted(f["event_id"] for _, f in previews) == [1, 2]
        assert {updates for updates, _ in previews} == {0}, (
            "every preview precedes every UPDATE in the batch"
        )
        assert len(session.updates) == 2 and r._lock_retry == {1, 2}

    async def test_a_sibling_preview_does_not_wait_out_another_events_row_lock(self, monkeypatch):
        """refresh() stamps several events on separate workers; a held row's
        whole lock wait must not sit in front of a sibling's preview."""
        from app.tasks.live_blend_refresh import FRESH_STAMP_WORKERS

        assert FRESH_STAMP_WORKERS >= 2
        (e1, m1), (e2, m2) = _event(1), _event(2)
        session = _PreviewSession([(m1, e1), (m2, e2)], None, stored=STORED, rev=10)
        finished_waits = []
        original = session.execute

        async def held_row(statement, *a, **k):
            if isinstance(statement, Update):
                session.updates.append(statement)
                await asyncio.sleep(0.2)  # waits out its lock budget, then times out
                finished_waits.append(statement)
                from tests.test_live_blend_refresh import _LockTimeout

                raise _LockTimeout("canceling statement due to lock timeout")
            return await original(statement, *a, **k)

        session.execute = held_row
        r, _ = _one_event_refresher(monkeypatch, session)
        seen = []

        async def _record(frames):
            seen.extend((len(finished_waits), f["event_id"]) for f in frames)

        monkeypatch.setattr(r, "_publish_previews", _record)
        await r.refresh([1, 2])

        assert sorted(eid for _, eid in seen) == [1, 2]
        assert {waits for waits, _ in seen} == {0}, (
            "both previews went out before either row wait ended", seen,
        )

    async def test_a_terminal_event_gets_no_preview(self, monkeypatch):
        event, market = _event(status="completed")
        session = _PreviewSession([(market, event)], None, stored=STORED, rev=10)
        r, _ = _one_event_refresher(monkeypatch, session)
        previews = _capture_previews(monkeypatch, r, session)
        await r.refresh([1])
        assert _blends(previews) == []


class TestExcludedSourceIsUnchanged:
    async def test_excluded_source_reads_no_extra_columns_and_publishes_no_preview(self, monkeypatch):
        monkeypatch.setattr(blend_preview, "preview_events_for", lambda source: frozenset())
        event, market = _event()
        session = _PreviewSession([(market, event)], None, stored=STORED, rev=10)
        r, committed = _one_event_refresher(monkeypatch, session)
        assert 1 not in r.preview_events

        async def forbidden(frames):
            raise AssertionError("no preview publication for an excluded source")

        monkeypatch.setattr(r, "_publish_previews", forbidden)
        stats = await r.refresh([1])
        assert stats["lock_skipped"] == 1
        assert session.preview_reads == 0
        assert committed == []


class TestRegistry:
    def _registry(self, clock=None, **kw):
        t = {"now": 0.0}
        reg = blend_preview.PreviewRegistry(
            max_uncommitted_s=kw.pop("max_s", 60.0),
            clock=clock or (lambda: t["now"]), epoch=7, **kw,
        )
        return reg, t

    def _event(self, status="live"):
        return SimpleNamespace(status=status, espn_win_prob_home=None, opening_home_probability=None)

    def test_two_writers_compose_and_a_sibling_commit_recomposes_the_other_pending_value(self):
        reg, _ = self._registry()
        stored = {"kalshi": {"value": 0.5, "updated_at": FRESH},
                  "polymarket": {"value": 0.5, "updated_at": FRESH}}
        [k] = reg.propose(1, "kalshi", value=0.7, event=self._event(), row_sources=stored, row_rev=10)
        [p] = reg.propose(1, "polymarket", value=0.8, event=self._event(), row_sources=stored, row_rev=10)
        assert p["preview"]["seq"] > k["preview"]["seq"]
        assert p["preview"]["pending"] == {"kalshi": 0.7, "polymarket": 0.8}
        both = stamp_source_reading(stamp_source_reading(dict(stored), "kalshi", 0.7), "polymarket", 0.8)
        assert p["p"] == pytest.approx(compute_aggregate_probability(
            SimpleNamespace(win_probability_sources=both, status="live",
                            espn_win_prob_home=None, opening_home_probability=None), "live"))
        # Kalshi's stamp commits rev 11 (without the PM value): PM is recomposed on 11.
        after_k = stamp_source_reading(dict(stored), "kalshi", 0.7)
        [again] = reg.committed(1, "kalshi", seq=k["preview"]["seq"], sources=after_k, rev=11)
        assert again["preview"]["base_rev"] == 11
        assert again["preview"]["pending"] == {"polymarket": 0.8}
        assert again["p"] == pytest.approx(p["p"])
        # PM commits rev 12: nothing pending, nothing published.
        assert reg.committed(1, "polymarket", seq=p["preview"]["seq"],
                             sources=both, rev=12) == []
        assert not reg.has_pending(1)

    def test_a_delayed_older_commit_never_regresses_the_base(self):
        reg, _ = self._registry()
        [a] = reg.propose(1, "kalshi", value=0.7, event=self._event(), row_sources=STORED, row_rev=10)
        reg.propose(1, "polymarket", value=0.6, event=self._event(), row_sources=STORED, row_rev=10)
        frames = reg.committed(1, "kalshi", seq=a["preview"]["seq"], sources={"kalshi": {"value": 0.1}}, rev=9)
        assert frames[0]["preview"]["base_rev"] == 10, "rev 9 is older than the base"

    def test_refusal_revokes_or_recomposes(self):
        reg, _ = self._registry()
        [k] = reg.propose(1, "kalshi", value=0.7, event=self._event(), row_sources=STORED, row_rev=10)
        [p] = reg.propose(1, "polymarket", value=0.6, event=self._event(), row_sources=STORED, row_rev=10)
        [recomposed] = reg.refused(1, "kalshi", "stale")
        assert recomposed["preview"]["kind"] == "blend"
        assert recomposed["preview"]["pending"] == {"polymarket": 0.6}
        [revoke] = reg.refused(1, "polymarket", "no_reading")
        assert revoke["preview"] == {"kind": "revoke", "epoch": 7, "seq": revoke["preview"]["seq"],
                                     "through_seq": recomposed["preview"]["seq"], "reason": "no_reading"}
        assert reg.refused(1, "polymarket", "no_reading") == []

    def test_terminal_status_revokes_and_never_previews(self):
        reg, _ = self._registry()
        reg.propose(1, "kalshi", value=0.7, event=self._event(), row_sources=STORED, row_rev=10)
        [revoke] = reg.propose(1, "kalshi", value=0.8, event=self._event("completed"),
                               row_sources=STORED, row_rev=11)
        assert revoke["preview"]["kind"] == "revoke" and revoke["preview"]["reason"] == "terminal"
        assert not reg.has_pending(1)
        assert reg.propose(2, "kalshi", value=0.8, event=self._event("final"),
                           row_sources=STORED, row_rev=11) == []

    def test_an_uncommitted_value_expires_and_its_ttl_counts_down(self):
        reg, t = self._registry(max_s=10.0)
        [a] = reg.propose(1, "kalshi", value=0.7, event=self._event(), row_sources=STORED, row_rev=10)
        assert a["preview"]["ttl_ms"] == 10_000
        t["now"] = 4.0
        [b] = reg.propose(1, "kalshi", value=0.71, event=self._event(), row_sources=STORED, row_rev=10)
        assert b["preview"]["ttl_ms"] == 6_000, "re-proposal does not extend the uncommitted chain"
        t["now"] = 9.9
        assert reg.expire() == []
        t["now"] = 10.0
        [revoke] = reg.expire()
        assert revoke["preview"]["reason"] == "expired"
        assert revoke["preview"]["through_seq"] == b["preview"]["seq"]

    def test_state_is_bounded_and_an_evicted_pending_preview_is_revoked(self):
        reg, _ = self._registry(max_events=2)
        for eid in (1, 2):
            reg.propose(eid, "kalshi", value=0.7, event=self._event(), row_sources=STORED, row_rev=10)
        frames = reg.propose(3, "kalshi", value=0.7, event=self._event(), row_sources=STORED, row_rev=10)
        assert [f["preview"]["kind"] for f in frames] == ["blend", "revoke"]
        assert frames[1]["event_id"] == 1 and frames[1]["preview"]["reason"] == "evicted"
        assert not reg.has_pending(1) and reg.has_pending(3)

    def test_a_new_process_has_no_epoch_until_it_claims_and_its_seq_starts_at_one(self):
        new = blend_preview.PreviewRegistry()
        assert new.epoch is None, "the epoch is the fence claim, never invented locally"
        [a] = new.propose(1, "kalshi", value=0.7, event=self._event(), row_sources=STORED, row_rev=10)
        assert a["preview"]["seq"] == 1

    def test_no_integer_revision_means_no_preview(self):
        reg, _ = self._registry()
        assert reg.propose(1, "kalshi", value=0.7, event=self._event(), row_sources=STORED, row_rev=None) == []
        assert not reg.has_pending(1)


class TestStreamForwarding:
    @pytest.fixture(autouse=True)
    def _legacy(self, monkeypatch):
        from tests._event_stream_legacy_view import install_legacy_view

        install_legacy_view(monkeypatch, drop_reconcile=True)

    def _preview(self, eid=42):
        reg = blend_preview.PreviewRegistry(epoch=7)
        [frame] = reg.propose(eid, "kalshi", value=0.7,
                              event=SimpleNamespace(status="live", espn_win_prob_home=None,
                                                    opening_home_probability=None),
                              row_sources=STORED, row_rev=10)
        return frame

    def _committed(self, eid=42):
        return {"event_id": eid, "p": 0.61, "source": "kalshi", "source_value": 0.7,
                "updated_at": datetime.now(timezone.utc).isoformat(), "status": "live",
                "rev": {str(eid): 11}}

    async def _chunks(self, monkeypatch, frames, contributors=None, n=1):
        from app.routes import event_stream as route
        from app.utils import live_fanout
        from tests.test_folded_event_stream_invalidation_837 import Hub, Request

        hub = Hub()
        monkeypatch.setattr(live_fanout, "fanout", lambda: hub)

        async def no_replay(ids):
            return []

        monkeypatch.setattr(route, "latest_frames", no_replay)
        stream = route._stream(42, Request(), contributors)
        out = []
        try:
            await anext(stream)
            await anext(stream)
            for channel, frame in frames:
                hub.subscriptions[channel].offer(json.dumps(frame))
            for _ in range(n):
                out.append(await asyncio.wait_for(anext(stream), 1))
        finally:
            await stream.aclose()
        return out

    async def test_enabled_forwards_a_preview_as_its_own_event(self, monkeypatch):
        preview = self._preview()
        [chunk] = await self._chunks(monkeypatch, [("live:event:42", preview)])
        assert chunk.startswith("event: preview\n")
        assert json.loads(chunk.split("data: ")[1]) == preview

    @pytest.mark.parametrize("name,value", [
        (blend_preview.SOURCE_ENV, None),
        (blend_preview.EVENT_IDS_ENV, None),
        (blend_preview.EVENT_IDS_ENV, "41,43"),
        (blend_preview.EVENT_IDS_ENV, "42,x"),
    ], ids=["no-source", "no-events", "other-events", "malformed"])
    async def test_legacy_rollout_settings_do_not_drop_default_preview(self, monkeypatch, name, value):
        if value is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, value)
        committed = self._committed()
        [preview, chunk] = await self._chunks(
            monkeypatch, [("live:event:42", self._preview()), ("live:event:42", committed)], n=2,
        )
        assert preview.startswith("event: preview\n")
        assert chunk.startswith("event: probability\n")
        assert json.loads(chunk.split("data: ")[1])["rev"] == {"42": 11}

    async def test_a_folded_page_drops_it(self, monkeypatch):
        committed = self._committed()
        chunks = await self._chunks(
            monkeypatch, [("live:event:42", self._preview()), ("live:event:42", committed)],
            contributors=[42, 43],
        )
        assert not any(c.startswith("event: preview") for c in chunks)


class TestNeverRetained:
    async def test_a_published_preview_reaches_subscribers_and_is_never_replayed(
        self, monkeypatch, private_redis_socket,
    ):
        from unittest.mock import AsyncMock

        from redis.asyncio import Redis

        from app.utils import live_push, request_cache

        redis = Redis(unix_socket_path=str(private_redis_socket))
        listener = Redis(unix_socket_path=str(private_redis_socket))
        monkeypatch.setattr(request_cache, "get_shared_async_redis", AsyncMock(return_value=redis))
        try:
            pubsub = listener.pubsub()
            await pubsub.subscribe(live_push.event_channel(42))
            await pubsub.get_message(timeout=1)
            r = LiveBlendRefresher("kalshi")
            r._redis = redis
            frame = TestStreamForwarding()._preview()
            await r._publish_previews([frame])
            assert r.preview_stats == {"published": 1, "revoked": 0, "fenced": 0, "publish_errors": 0}
            assert r.stats["published"] == 0, "never counted as a committed publication"
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1)
            assert json.loads(message["data"]) == frame
            assert await live_push.latest_frames([42]) == []
            assert await redis.exists(live_push.latest_frame_key(42)) == 0
            await pubsub.aclose()
        finally:
            await redis.aclose()
            await listener.aclose()
