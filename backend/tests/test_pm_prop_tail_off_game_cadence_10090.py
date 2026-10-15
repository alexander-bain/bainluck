"""#10090 — a held prop write must not hold the next game flush.

Stage trace 43011 → 44306 → rev 6398: the selected game's earlier stamp
released, yet its next changed quote stayed buffered 4.67 s until the next
game flush began; what held that flush is not known. Root's tail falsifier on
parent 8bb31cee58 reproduced the boundary with a prop write: the game flush
appended every non-speaking prop chunk after the game chunks, and the cadence
starts no flush until the current one returns, so one held prop write kept
the new selected quote buffered (held 0.60 s; unheld control 0.25 s, the next
cadence turn).

The props now have their own loop (`flush_props`). Here BOTH real cadences run
over the shipped closures and the real refresher; the database boundary is
faked and a prop write is held by an asyncio Event. This proves the
control-flow boundary, not production latency.
"""

import asyncio
import time

import pytest

from app.tasks import live_blend_refresh as blend
from tests.test_pm_same_flush_fresh_admission_10090 import paired
from tests.test_single_event_commit_10090 import settle_until

pytestmark = pytest.mark.asyncio

PERIOD = 0.25  # production PM_WS_PRICE_FLUSH_SECONDS


@pytest.mark.parametrize("held_tail", [True, False], ids=["held", "unheld-control"])
async def test_selected_quote_writes_while_an_unrelated_prop_write_is_held(
    monkeypatch, held_tail,
):
    p, x = paired(monkeypatch)
    # Event 2's legs stay linked but are venue-refuted props: no cohort overlap.
    p.ns["non_blend_outcome_ids"].update({900, 901})
    entered, release_tail = asyncio.Event(), asyncio.Event()
    writes = []
    original_write = p.ns["write_chunk"]

    async def held_write(chunk, **kwargs):
        if 900 in chunk:
            entered.set()
            await release_tail.wait()
        result = await original_write(chunk, **kwargs)
        writes.append((time.monotonic(), dict(chunk)))
        return result

    p.ns["write_chunk"] = held_write
    boundary = p.ns["catalog_boundary"]
    stop = asyncio.Event()
    starts = []

    async def tracked(started):
        starts.append(started)
        return await p.ns["flush_prices"](flush_started=started)

    game = asyncio.create_task(blend.run_flush_cadence(
        tracked, PERIOD, stop=stop, wake=boundary.flush_wake,
        work_count=lambda: boundary.flush_work, wake_coalesce_s=0.005,
    ))
    props = asyncio.create_task(blend.run_flush_cadence(
        p.ns["flush_props"], PERIOD, stop=stop, wake=boundary.prop_wake,
        work_count=lambda: boundary.prop_work, wake_coalesce_s=0.005,
    ))

    def selected_writes():
        return [t for t, c in writes if c.get(1) == 0.65]

    try:
        await asyncio.wait_for(entered.wait(), 2)
        await settle_until(lambda: any(s.event_ids == [1] for s in x.sessions))
        assert 1 not in x.committed
        assert x.r.holding_event_ids() == frozenset({1})
        # No game write ever carried a prop leg.
        assert all(900 not in c and 901 not in c for _, c in writes)
        accepted = time.monotonic()
        for seq, (oid, value) in enumerate(((1, 0.65), (2, 0.35)), 10):
            p.ns["price_buffer"][oid] = value
            p.ns["input_marks"][oid] = blend.InputMark(
                seq=seq, event_id=1, outcome_id=oid, probability=value,
                kind="price", recv_wall=time.time(), recv_mono=accepted,
                venue_ts_ms=None, event_ordinal=seq,
            )
        boundary.wake_for_outcomes(
            [1, 2], p.ns["open_outcome_ids"], p.ns["event_id_by_outcome"],
            p.ns["non_blend_outcome_ids"],
        )
        x.release.set()
        await settle_until(lambda: 1 in x.published and not x.r.holding_event_ids())
        selected_released = time.monotonic()
        if not held_tail:
            release_tail.set()
        # The parent wrote nothing here: its cadence still awaited the held
        # prop chunk inside the first game flush (falsifier: 0.60 s, no
        # successor). Two cadence turns of slack for a loaded runner.
        deadline = selected_released + 4 * PERIOD
        while not selected_writes() and time.monotonic() < deadline:
            await asyncio.sleep(0.01)
        assert selected_writes(), "the new selected quote waited for the prop write"
        assert p.ns["price_buffer"].get(1) is None
        if held_tail:
            assert not release_tail.is_set() and 900 in p.ns["price_buffer"]
        assert len(starts) > 1
        release_tail.set()
        await settle_until(lambda: not p.ns["price_buffer"])
        await settle_until(lambda: not x.r.pending_event_ids())
    finally:
        release_tail.set()
        x.release.set()
        stop.set()
        boundary.flush_wake.set()
        boundary.prop_wake.set()
        try:
            await asyncio.wait_for(asyncio.gather(game, props), 2)
        finally:
            for task in (game, props):
                if not task.done():
                    task.cancel()
            await asyncio.gather(game, props, return_exceptions=True)
            await boundary.join_stamps(cancel=True)
    assert any(c.get(900) == 0.7 and c.get(901) == 0.3 for _, c in writes)
    assert not p.ns["price_buffer"]
    assert x.r.stats["errors"] == p.ns["stats"]["errors"] == 0


async def test_prop_and_standalone_writes_take_turns_on_one_connection(monkeypatch):
    # The socket's pool holds five: three stamps, the game writer and ONE side
    # writer. A held prop write keeps a standalone leg's write waiting (and
    # vice versa); neither ever holds the game flush.
    p, x = paired(monkeypatch)
    p.ns["non_blend_outcome_ids"].update({900, 901})
    p.ns["price_buffer"][700] = 0.5  # an eventless open leg
    p.ns["open_outcome_ids"].add(700)
    p.ns["market_by_outcome"][700] = 700
    entered, release_tail = asyncio.Event(), asyncio.Event()
    order = []
    original_write = p.ns["write_chunk"]

    async def held_write(chunk, **kwargs):
        order.append(sorted(chunk))
        if 900 in chunk:
            entered.set()
            await release_tail.wait()
        return await original_write(chunk, **kwargs)

    p.ns["write_chunk"] = held_write
    x.release.set()
    props = asyncio.create_task(p.ns["flush_props"]())
    standalone = None
    try:
        await asyncio.wait_for(entered.wait(), 1)
        standalone = asyncio.create_task(p.ns["flush_standalone"]())
        assert await asyncio.wait_for(p.ns["flush_prices"](flush_started=1000), 1)
        for _ in range(20):
            await asyncio.sleep(0)
        assert [700] not in order and not standalone.done()
        release_tail.set()
        assert await asyncio.wait_for(props, 1)
        assert await asyncio.wait_for(standalone, 1)
    finally:
        release_tail.set()
        await asyncio.gather(props, *([standalone] if standalone else []),
                             return_exceptions=True)
        await p.ns["catalog_boundary"].join_stamps()
    assert order.index([900, 901]) < order.index([700])
    assert not p.ns["price_buffer"]


async def test_a_prop_input_wakes_the_prop_loop_never_the_game_flush():
    from app.tasks.polymarket_ws import _PMCatalogFlushBoundary

    boundary = _PMCatalogFlushBoundary()
    events = {1: 10, 2: 10, 900: 10}
    boundary.wake_for_outcomes([900], set(), events, {900})
    assert boundary.prop_wake.is_set() and not boundary.flush_wake.is_set()
    boundary.prop_wake.clear()
    boundary.wake_for_outcomes([900, 1], set(), events, {900})
    assert boundary.prop_wake.is_set() and boundary.flush_wake.is_set()
    boundary.prop_wake.clear()
    boundary.flush_wake.clear()
    # Unknown status (no refutation passed) stays a game input.
    boundary.wake_for_outcomes([900], set(), events)
    assert boundary.flush_wake.is_set() and not boundary.prop_wake.is_set()


async def test_a_catalog_handover_fences_the_prop_write_while_games_still_flush(monkeypatch):
    # Maps change only with no flush of either kind running. The props' loop
    # is a side flush: the handover's first step waits out its write while a
    # game flush still runs on the unchanged maps, then fences new prop
    # flushes until the maps have changed.
    p, x = paired(monkeypatch)
    p.ns["non_blend_outcome_ids"].update({900, 901})
    x.release.set()
    entered, release_tail = asyncio.Event(), asyncio.Event()
    original_write = p.ns["write_chunk"]

    async def held_write(chunk, **kwargs):
        if 900 in chunk:
            entered.set()
            await release_tail.wait()
        return await original_write(chunk, **kwargs)

    p.ns["write_chunk"] = held_write
    boundary = p.ns["catalog_boundary"]
    changed = asyncio.Event()

    async def handover():
        async with boundary.updating():
            assert boundary.standalone_active == 0 and boundary.active == 0
            changed.set()

    props = asyncio.create_task(p.ns["flush_props"]())
    task = None
    try:
        await asyncio.wait_for(entered.wait(), 1)
        task = asyncio.create_task(handover())
        for _ in range(20):
            await asyncio.sleep(0)
        assert boundary.standalone_fenced and not changed.is_set()
        assert await asyncio.wait_for(p.ns["flush_prices"](flush_started=1000), 1)
        late = asyncio.create_task(p.ns["flush_props"]())
        for _ in range(20):
            await asyncio.sleep(0)
        assert not late.done()
        release_tail.set()
        assert await asyncio.wait_for(props, 1)
        await asyncio.wait_for(task, 2)
        assert changed.is_set()
        assert await asyncio.wait_for(late, 1)
    finally:
        release_tail.set()
        await asyncio.gather(props, *([task] if task else []), return_exceptions=True)
        await boundary.join_stamps()
    assert not p.ns["price_buffer"]
