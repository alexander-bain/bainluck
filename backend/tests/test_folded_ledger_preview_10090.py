"""Both venues reach a combined page through one atomic origin ledger.

No split-origin union: books stay in the committed fold, all pending entries
must be elected from the single ledger event. Reuse real Redis send controls.
"""
from copy import deepcopy
from datetime import datetime, timezone

import pytest

from app.utils.aggregation import stamp_source_reading
from app.utils.folded_blend_preview import FoldedPreviewBase
from app.utils.hero_probability import resolve_hero
from app.utils.proven_duplicates import FoldedBlendView
from tests.test_blend_preview_ledger_tsp1_10090 import (
    BASE10, EV, FRESH, _blends, _ev, _propose, _stamp,
    redis_kwargs as redis_kwargs, rig as rig,
)


def base_for(sources=None, revision=10):
    event = _ev()
    event.id = 8
    bag = {**BASE10, "betting": {"value": .4, "updated_at": FRESH},
           "betting_book_count": 6}
    if sources is not None:
        bag.update(sources)
    return FoldedPreviewBase.capture(
        event, bag, {"kalshi": EV, "polymarket": EV, "betting": 8},
        {str(EV): revision, "8": 3}, "soccer_epl",
    )


def project(base, frame, **kw):
    return base.project(frame, members={EV, 8}, floors={}, **kw)


@pytest.mark.parametrize("order", [("kalshi", "polymarket"), ("polymarket", "kalshi")])
async def test_two_processes_project_both_values_and_keep_books(rig, order):
    registries = {"kalshi": rig.k, "polymarket": rig.p}
    values = {"kalshi": .6, "polymarket": .7}
    for source in order:
        [frame] = _blends(await rig.run(registries[source], _propose(
            registries[source], source, values[source], basis_s=2)))
    base = base_for()
    before = deepcopy(base.sources)
    result = project(base, frame, elapsed_ms=25.2)
    assert result is not None
    expected = resolve_hero(FoldedBlendView(_ev(), {
        **base.sources, **frame["preview"]["pending_entries"],
    }))
    assert result["p"] == expected.home_probability
    assert result["p"] != frame["p"]
    assert result["p_away"] is None
    assert result["preview"]["pending"] == values
    assert result["preview"]["origin_event_id"] == EV
    assert result["preview"]["base_fold_revision"] == {str(EV): 10, "8": 3}
    assert result["preview"]["ttl_ms"] == frame["preview"]["ttl_ms"] - 26
    assert result["preview"]["epoch"] == frame["preview"]["epoch"]
    assert result["preview"]["seq"] == frame["preview"]["seq"]
    assert result["display_observed_at"] == FRESH  # books' clock is retained
    assert base.sources == before


@pytest.mark.parametrize("bad", ["split_owner", "missing_entry", "version", "authority", "basis", "value", "source_value", "base_floor", "terminal"])
async def test_complete_single_origin_authority_required(rig, bad):
    await rig.run(rig.k, _propose(rig.k, "kalshi", .6))
    [frame] = _blends(await rig.run(rig.p, _propose(rig.p, "polymarket", .7)))
    base = base_for()
    if bad == "split_owner":
        base.owners["kalshi"] = 8
    elif bad == "missing_entry":
        del frame["preview"]["pending_entries"]["kalshi"]
    elif bad == "version":
        frame["preview"]["pending_entries_version"] = 1
    elif bad == "authority":
        frame["preview"].pop("pending_entries_authority")
    elif bad == "basis":
        frame["preview"]["pending_entries"]["kalshi"]["observed_basis"] = {}
    elif bad == "value":
        frame["preview"]["pending_entries"]["kalshi"]["observed_value"] = .5
    elif bad == "source_value":
        frame["source_value"] = .5
    elif bad == "base_floor":
        base.revision["8"] = 4
        assert base.project(frame, members={EV, 8}, floors={"8": 5}) is None
        return
    elif bad == "terminal":
        base.context["status"] = "completed"
    assert project(base, frame) is None


async def test_settling_one_source_keeps_sibling_identity_and_committed_bag(rig):
    await rig.run(rig.k, _propose(rig.k, "kalshi", .6))
    await rig.run(rig.p, _propose(rig.p, "polymarket", .7, basis_s=2))
    bag = stamp_source_reading(BASE10, "polymarket", .7, now=_stamp(2))
    ops = rig.p.committed(EV, "polymarket", seq=rig.p.pending_seq(EV, "polymarket"),
                          sources=bag, rev=11, event=_ev())
    [frame] = _blends(await rig.run(rig.p, ops))
    assert frame["source"] == "polymarket" and frame["source_value"] == .6
    assert frame["preview"]["pending"] == {"kalshi": .6}
    result = project(base_for(bag, revision=11), frame)
    assert result is not None and result["preview"]["base_rev"] == 11


@pytest.mark.parametrize("interleave", ["new_owner", "terminal", "expired", "new_base"])
@pytest.mark.parametrize("rig", ["fake_clock"], indirect=True)
async def test_prepared_fold_metadata_never_bypasses_final_send_checks(rig, interleave):
    await rig.run(rig.k, _propose(rig.k, "kalshi", .6))
    prepared = await rig.p.prepare(_propose(rig.p, "polymarket", .7), rig.call, rig.stats)
    if interleave == "new_owner":
        await rig.registry().claim(rig.call, "kalshi")
    elif interleave == "terminal":
        await rig.run(rig.k, rig.k.committed(EV, "kalshi", seq=None,
                      sources=BASE10, rev=11, event=_ev("completed")))
    elif interleave == "expired":
        await rig.clock(1_060_001)
    else:
        await rig.run(rig.k, rig.k.committed(EV, "kalshi", seq=None,
                      sources=BASE10, rev=11, event=_ev()))
    for frame in prepared:
        await rig.p._publish(frame, rig.call, rig.channel, rig.stats)
    # It may recompose a currently valid subset, but cannot send the old pair.
    sent = await rig.drain()
    for frame in _blends(sent):
        assert frame["preview"]["pending"] != {"kalshi": .6, "polymarket": .7}


@pytest.mark.parametrize("source", ["kalshi", "polymarket"])
async def test_single_pending_entry_cannot_open_split_origin_ledger_page(rig, source):
    reg = rig.k if source == "kalshi" else rig.p
    [frame] = _blends(await rig.run(reg, _propose(reg, source, .7)))
    base = base_for()
    other = "polymarket" if source == "kalshi" else "kalshi"
    base.owners[other] = 8
    assert project(base, frame) is None


async def test_actual_folded_route_forwards_both_entries_then_terminal_floor(rig, monkeypatch):
    import asyncio
    import json

    from app.routes import event_stream as route
    from app.utils import live_fanout
    from app.utils.folded_live_quote import FoldedQuoteProjector
    from tests.test_folded_event_stream_invalidation_837 import Hub, Request

    await rig.run(rig.k, _propose(rig.k, "kalshi", .6))
    [frame] = _blends(await rig.run(rig.p, _propose(rig.p, "polymarket", .7)))
    base = base_for()
    hub = Hub()
    hub._quote_projector = FoldedQuoteProjector()
    hub._quote_projector._preview_bases[(8, frozenset(base.revision))] = base
    hub.project_folded_preview = live_fanout.LiveFanout.project_folded_preview.__get__(hub)
    entered, cancelled = asyncio.Event(), asyncio.Event()

    async def blocked(*args):
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    hub.project_recovery_quote = blocked
    monkeypatch.setattr(live_fanout, "fanout", lambda: hub)
    monkeypatch.setattr(route, "preview_route_events", lambda: {8})
    monkeypatch.setattr(route, "latest_frames", lambda ids: asyncio.sleep(0, result=[]))
    monkeypatch.setattr(route, "_current_reconcile", lambda *args: asyncio.sleep(0, result={
        "event_id": 8, "custody_id": "state:test", "removal_rev": base.revision,
    }))
    stream = route._stream(8, Request(), [8, EV])
    task = None
    try:
        await anext(stream)
        await anext(stream)
        assert "event: reconcile" in await asyncio.wait_for(anext(stream), 1)
        task = asyncio.create_task(anext(stream))
        await asyncio.wait_for(entered.wait(), 1)
        hub.subscriptions[f"live:event:{EV}"].offer(json.dumps(frame))
        chunk = await asyncio.wait_for(task, 1)
        assert chunk.startswith("event: preview\n")
        actual = json.loads(chunk.split("data: ")[1])
        assert actual["event_id"] == 8
        assert actual["p"] == project(base, frame)["p"]
        assert actual["preview"]["pending"] == {"kalshi": .6, "polymarket": .7}
        assert actual["preview"]["ttl_ms"] <= frame["preview"]["ttl_ms"]
        hub.subscriptions["live:event:8"].offer(json.dumps({
            # Stamped now: the route drops a frame older than MAX_FRAME_AGE_S,
            # and FRESH is fixed at import, so it ages with the session.
            "event_id": 8, "p": 1., "status": "completed", "rev": {"8": 4},
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }))
        assert "event: fold_preview_floor" in await asyncio.wait_for(anext(stream), 1)
        assert "event: probability" in await asyncio.wait_for(anext(stream), 1)
        assert "event: closed" in await asyncio.wait_for(anext(stream), 1)
    finally:
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        await stream.aclose()
    assert cancelled.is_set() and len(hub.released) == 2
