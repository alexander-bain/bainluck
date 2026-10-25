"""Folded DNPL policy inputs must match the authoritative fold without IO."""

import asyncio
from datetime import datetime, timezone
import json
from types import SimpleNamespace

import pytest

from app.utils.aggregation import stamp_source_reading
from app.utils.blend_preview import PreviewRegistry
from app.utils.folded_blend_preview import FoldedPreviewBase, QuoteWithPreviewBase
from app.utils.hero_probability import resolve_hero
from app.utils.proven_duplicates import (
    FoldedBlendView, merge_probability_sources, merge_probability_sources_with_owners,
)


def capable_request():
    from tests.test_folded_event_stream_invalidation_837 import Request

    request = Request()
    request.query_params = {"preview_protocol": "folded-v1"}
    return request


def rig(sport="soccer_epl"):
    now = datetime.now(timezone.utc)
    event = SimpleNamespace(id=1, status="live", espn_win_prob_home=None,
                            opening_home_probability=None, opening_away_probability=None)
    canonical = {"betting": {"value": .4, "updated_at": now.isoformat()},
                 "betting_book_count": 6}
    sibling = {"polymarket": {"value": .6, "updated_at": now.isoformat(),
                              "unknown_metadata": {"kept": True}}}
    sources, owners = merge_probability_sources_with_owners(1, canonical, [(2, sibling)])
    base = FoldedPreviewBase.capture(event, sources, owners, {"1": 11, "2": 22, "3": 7}, sport)
    registry = PreviewRegistry(epoch=8, clock=lambda: 100.)
    basis = {"101": now.timestamp(), "102": now.timestamp() - .2}
    [frame] = registry.propose(2, "polymarket", value=.82, event=event,
                              row_sources=sibling, row_rev=22,
                              observed_basis=basis, stamped_at=now)
    return event, canonical, sibling, base, frame, basis, now


def project(base, frame, **kwargs):
    return base.project(frame, members=[1, 2, 3], floors={"1": 11, "2": 22, "3": 7}, **kwargs)


def test_whole_fold_uses_books_and_exact_pending_entry_not_row_scalar():
    event, canonical, sibling, base, frame, basis, now = rig()
    candidate = project(base, frame, elapsed_ms=25.2)
    stamped = stamp_source_reading(sibling, "polymarket", .82, now=now, observed_basis=basis)
    expected = resolve_hero(FoldedBlendView(event, merge_probability_sources(canonical, [(2, stamped)])))
    assert candidate["p"] == expected.home_probability
    assert candidate["p"] != frame["p"]  # row-local PM .82 omits the books
    assert candidate["p_away"] is None  # soccer's draw is not the away team
    assert candidate["preview"]["base_fold_revision"] == {"1": 11, "2": 22, "3": 7}
    assert candidate["preview"]["origin_event_id"] == 2
    assert candidate["event_id"] == 1 and "rev" not in candidate
    assert candidate["preview"]["ttl_ms"] == frame["preview"]["ttl_ms"] - 26
    assert candidate["preview"]["seq"] == frame["preview"]["seq"]
    assert candidate["preview"]["pending_entries"]["polymarket"] == stamped["polymarket"]
    assert base.sources["polymarket"]["value"] == .6
    assert candidate["display_observed_at"] == now.isoformat()


def test_warm_base_detaches_metadata_and_public_quote_never_serializes_it():
    _, _, _, base, frame, _, _ = rig()
    frame["preview"]["pending_entries"]["polymarket"]["unknown_metadata"]["kept"] = False
    assert base.sources["polymarket"]["unknown_metadata"]["kept"] is True
    quote = QuoteWithPreviewBase({"event_id": 1}, base)
    assert json.loads(json.dumps(quote)) == {"event_id": 1}


@pytest.mark.parametrize("origin,value", [(1, 12), (2, 23), (3, 8)])
def test_any_newer_member_floor_refuses_even_noncontributing_member(origin, value):
    _, _, _, base, frame, _, _ = rig()
    assert base.project(frame, members=[1, 2, 3], floors={str(origin): value}) is None


@pytest.mark.parametrize("members", [[1, 2], [1, 2, 3, 4], [2, 3]])
def test_membership_changes_refuse(members):
    _, _, _, base, frame, _, _ = rig()
    assert base.project(frame, members=members, floors={}) is None


@pytest.mark.parametrize("mutation", [
    lambda f: f["preview"].update(base_rev=21),
    lambda f: f["preview"].update(base_rev=23),
    lambda f: f["preview"].update(pending_entries_version=2),
    lambda f: f["preview"].update(pending_entries_version=True),
    lambda f: f["preview"].update(pending_entries=None),
    lambda f: f["preview"]["pending"].update(kalshi=.4),
    lambda f: f["preview"]["pending_entries"]["polymarket"].update(observed_basis={}),
    lambda f: f["preview"]["pending_entries"]["polymarket"].update(observed_basis={"101": float("nan")}),
    lambda f: f["preview"]["pending_entries"]["polymarket"].update(observed_value=.81),
    lambda f: f["preview"]["pending_entries"]["polymarket"].update(updated_at="invalid"),
    lambda f: f["preview"]["pending_entries"]["polymarket"].update(updated_at="2026-10-21T00:00:00"),
    lambda f: f["preview"].update(ttl_ms=0),
    lambda f: f.update(status="completed"),
    lambda f: f.update(rev={"2": 22}),
])
def test_unproven_frames_cannot_obtain_folded_authority(mutation):
    _, _, _, base, frame, _, _ = rig()
    mutation(frame)
    assert project(base, frame) is None


def test_existing_owner_alone_can_change_source_and_owner_choice_is_shared():
    _, canonical, sibling, base, frame, _, _ = rig()
    canonical["polymarket"] = {"value": .3}
    merged, owners = merge_probability_sources_with_owners(1, canonical, [(2, sibling)])
    assert merged == merge_probability_sources(canonical, [(2, sibling)])
    base.sources.update(merged)
    base.owners.update(owners)
    assert project(base, frame) is None
    merged, owners = merge_probability_sources_with_owners(1, {}, [(9, sibling), (2, sibling)])
    assert owners["polymarket"] == 2


def test_stale_observation_and_expired_delivery_refuse():
    _, _, _, base, frame, basis, _ = rig()
    base.sources["polymarket"].update(observed_basis={k: v + 1 for k, v in basis.items()}, observed_value=.6)
    assert project(base, frame) is None
    _, _, _, base, frame, _, _ = rig()
    assert project(base, frame, elapsed_ms=frame["preview"]["ttl_ms"]) is None


def test_unknown_sibling_clock_remains_unknown_and_non_draw_away_is_complement():
    _, _, _, base, frame, _, _ = rig(sport="basketball_nba")
    base.sources["betting"].pop("updated_at")
    projected = project(base, frame)
    assert projected["display_observed_at"] is None
    assert projected["p_away"] == pytest.approx(1 - projected["p"])


def test_malformed_legacy_metadata_does_not_break_singleton_production():
    event, _, sibling, _, _, basis, now = rig()
    sibling["polymarket"]["bad"] = float("nan")
    [frame] = PreviewRegistry(epoch=1).propose(
        2, "polymarket", value=.82, event=event, row_sources=sibling, row_rev=22,
        observed_basis=basis, stamped_at=now,
    )
    assert frame["p"] == .82
    assert frame["preview"]["pending_entries"] is None
    json.dumps(frame, allow_nan=False)


@pytest.mark.parametrize("capable", [False, True])
async def test_route_keeps_reading_previews_and_terminal_while_projection_waits(monkeypatch, capable):
    from app.routes import event_stream as route
    from app.utils import live_fanout
    from tests.test_folded_event_stream_invalidation_837 import Hub

    _, _, _, base, preview, _, now = rig()
    hub = Hub()
    entered, cancelled = asyncio.Event(), asyncio.Event()

    async def blocked(*args):
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    async def coverage(*args):
        return {"event_id": 1, "custody_id": "state:test", "removal_rev": base.revision}

    hub.project_recovery_quote = blocked
    hub.project_folded_preview = lambda eid, frame, **kw: base.project(frame, **kw)
    monkeypatch.setattr(live_fanout, "fanout", lambda: hub)
    monkeypatch.setattr(route, "latest_frames", lambda ids: asyncio.sleep(0, result=[]))
    monkeypatch.setattr(route, "_current_reconcile", coverage)
    request = capable_request()
    if not capable:
        request.query_params = {}
    stream = route._stream(1, request, [1, 2, 3])
    task = None
    try:
        assert "retry:" in await anext(stream)
        assert "event: open" in await anext(stream)
        assert "event: reconcile" in await asyncio.wait_for(anext(stream), 1)
        task = asyncio.create_task(anext(stream))
        await asyncio.wait_for(entered.wait(), 1)
        hub.subscriptions["live:event:2"].offer(json.dumps(preview))
        if capable:
            chunk = await asyncio.wait_for(task, 1)
            assert chunk.startswith("event: preview\n")
            assert json.loads(chunk.split("data: ")[1])["p"] == project(base, preview)["p"]
        # A canonical terminal commit remains reachable while the read hangs.
        hub.subscriptions["live:event:1"].offer(json.dumps({
            "event_id": 1, "p": 1., "status": "completed", "rev": {"1": 12},
            "updated_at": now.isoformat(),
        }))
        floor = await asyncio.wait_for(anext(stream) if capable else task, 1)
        assert "event: fold_preview_floor" in floor
        assert "event: probability" in await asyncio.wait_for(anext(stream), 1)
        assert "event: closed" in await asyncio.wait_for(anext(stream), 1)
    finally:
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        await stream.aclose()
    assert cancelled.is_set()
    assert len(hub.released) == 3


@pytest.mark.parametrize("as_bytes", [False, True])
async def test_actual_mailbox_route_subtracts_age_and_refuses_expired_preview(monkeypatch, as_bytes):
    from app.routes import event_stream as route
    from app.utils import live_fanout
    from app.utils.folded_live_quote import FoldedQuoteProjector
    from tests.test_folded_event_stream_invalidation_837 import Hub

    _, _, _, base, preview, _, _ = rig()
    hub = Hub()
    hub._quote_projector = FoldedQuoteProjector()
    hub._quote_projector._preview_bases[(1, frozenset(base.revision))] = base
    hub.project_folded_preview = live_fanout.LiveFanout.project_folded_preview.__get__(hub)
    clock = [100.]
    monkeypatch.setattr(live_fanout, "monotonic", lambda: clock[0])
    monkeypatch.setattr(live_fanout, "fanout", lambda: hub)
    monkeypatch.setattr(route, "latest_frames", lambda ids: asyncio.sleep(0, result=[]))
    monkeypatch.setattr(route, "_current_reconcile", lambda *args: asyncio.sleep(0, result={
        "event_id": 1, "custody_id": "state:test", "removal_rev": base.revision,
    }))
    stream = route._stream(1, capable_request(), [1, 2, 3])
    try:
        await anext(stream)
        await anext(stream)
        assert "event: reconcile" in await asyncio.wait_for(anext(stream), 1)
        sub = hub.subscriptions["live:event:2"]
        payload = json.dumps(preview)
        sub.offer(payload.encode() if as_bytes else payload)
        clock[0] += .125
        chunk = await asyncio.wait_for(anext(stream), 1)
        assert chunk.startswith("event: preview\n")
        actual = json.loads(chunk.split("data: ")[1])
        assert actual["preview"]["ttl_ms"] == preview["preview"]["ttl_ms"] - 125
        # Suspend the generator at its SSE yield; the queued claim expires
        # before the downstream reader asks for the next frame.
        sub.offer(payload.encode() if as_bytes else payload)
        clock[0] += preview["preview"]["ttl_ms"] / 1000 + .1
        sub.offer(live_fanout.CLOSED)
        assert "event: reconnect" in await asyncio.wait_for(anext(stream), 1)
    finally:
        await stream.aclose()


@pytest.mark.parametrize("confirmation_only", [False, True])
async def test_recovery_rewarms_same_revision_without_a_new_committed_frame(monkeypatch, confirmation_only):
    from app.routes import event_stream as route
    from app.utils import live_fanout
    from tests.test_folded_event_stream_invalidation_837 import Hub

    _, _, _, base, preview, _, _ = rig()
    hub = Hub()
    warm = [False]
    loads = []

    async def load(*args):
        loads.append(args)
        warm[0] = True
        return {"event_id": 1, "status": "live", "blend_fold_revision": base.revision}

    hub.project_recovery_quote = load
    hub.forget_folded_preview = lambda eid: warm.__setitem__(0, False)
    hub.project_folded_preview = lambda eid, frame, **kw: base.project(frame, **kw) if warm[0] else None
    monkeypatch.setattr(live_fanout, "fanout", lambda: hub)
    monkeypatch.setattr(route, "latest_frames", lambda ids: asyncio.sleep(0, result=[]))
    monkeypatch.setattr(route, "_current_reconcile", lambda eid, ids: asyncio.sleep(0, result={
        "event_id": 1, "custody_id": "state:unchanged",
        "removal_rev": {str(member): base.revision[str(member)] for member in ids},
    }))
    stream = route._stream(1, capable_request(), [1, 2, 3])
    try:
        await anext(stream)
        await anext(stream)
        assert "event: reconcile" in await asyncio.wait_for(anext(stream), 1)
        assert "event: folded_probability" in await asyncio.wait_for(anext(stream), 1)
        assert len(loads) == 1
        hub.subscriptions["live:event:2"].offer(
            live_fanout.CONFIRMED if confirmation_only else live_fanout.Recovery(1))
        if not confirmation_only:
            assert "event: resync" in await asyncio.wait_for(anext(stream), 1)
            assert not warm[0]
            assert "event: reconcile" in await asyncio.wait_for(anext(stream), 1)
        assert "event: folded_probability" in await asyncio.wait_for(anext(stream), 1)
        assert len(loads) == 2 and warm[0]
        hub.subscriptions["live:event:2"].offer(json.dumps(preview))
        assert "event: preview" in await asyncio.wait_for(anext(stream), 1)
    finally:
        await stream.aclose()


@pytest.mark.parametrize("protocol", [None, "unknown", "folded-v1"])
@pytest.mark.parametrize("folded", [False, True])
async def test_preview_requires_capability_only_for_folded_pages(monkeypatch, protocol, folded):
    from app.routes import event_stream as route
    from app.utils import live_fanout
    from tests.test_folded_event_stream_invalidation_837 import Hub, Request

    _, _, _, base, preview, _, _ = rig()
    hub = Hub()
    projected = []

    def project_preview(eid, frame, **kwargs):
        projected.append(frame)
        return base.project(frame, **kwargs)

    hub.project_folded_preview = project_preview
    monkeypatch.setattr(live_fanout, "fanout", lambda: hub)
    monkeypatch.setattr(route, "latest_frames", lambda ids: asyncio.sleep(0, result=[]))
    monkeypatch.setattr(route, "_current_reconcile", lambda *args: asyncio.sleep(0, result={"event_id": 1 if folded else 2, "custody_id": "state:test", "removal_rev": base.revision}))
    request = Request()
    request.query_params = {} if protocol is None else {"preview_protocol": protocol}
    stream = route._stream(1 if folded else 2, request, [1, 2, 3] if folded else [2])
    try:
        assert "retry:" in await anext(stream)
        assert "event: open" in await anext(stream)
        assert "event: reconcile" in await asyncio.wait_for(anext(stream), 1)
        sub = hub.subscriptions["live:event:2"]
        sub.offer(json.dumps(preview))
        sub.offer(live_fanout.CLOSED)
        chunk = await asyncio.wait_for(anext(stream), 1)
        if not folded or protocol == "folded-v1":
            assert chunk.startswith("event: preview\n")
            assert "event: reconnect" in await asyncio.wait_for(anext(stream), 1)
        else:
            assert "event: reconnect" in chunk
            assert projected == []
    finally:
        await stream.aclose()
