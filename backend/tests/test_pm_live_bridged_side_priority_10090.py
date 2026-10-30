"""#10090 — a live bridged Polymarket game's write no longer queues behind side writes.

PILLARS: TRUTH / FORMATTING. SHIP: a Polymarket price change on a live game
reaches the page without waiting 1.4-3.7 s behind prop and standalone write
chunks (Polymarket 15331071: 5.98 s from receipt to stamp at evening load).

Argon's rank 4 (production 2026-10-30 00:18-00:22Z, `PM_BRIDGED_SIDE_FIRST`
unset): the bridged writer's own writes took 0.11-0.28 s at most, but each
cohort waited up to 3.73 s (`side_wait`) for the one side connection, in
arrival order behind the standalone legs' and linked props' 200-row chunks.

A cohort of live events now takes that connection's first turn whatever the
switch says — behind the one side transaction in flight, never pre-empting
it — leads the bridged writer's queue, is never packed with a pre-game event,
and is never kept out by pre-game cohorts filling the queue bound. Pre-game
cohorts keep today's order with the switch off.

ORDERING: the bridged writer stays the one serial writer of a pure bridged
event's outcomes (reservation keeps an event in at most one queued cohort),
and a cohort reads its prices from the buffer only once it holds the side
connection. So a live cohort jumping the queue can never be followed by an
older value for the same outcome: per outcome, written values follow input
order and the last one written is the newest input. The randomized guard below
fails against a writer that captures values at offer time and lets a live
offer bypass reservation (the two ways a "fast path" would break this).

Executed shipped closures, the real bridged writer, side connection and stamp
owner; fake database and publication boundaries — control flow, not
production latency.
"""
import asyncio
import random
import time

import pytest

from app.tasks import live_blend_refresh as blend
from app.tasks import polymarket_ws as pm
from tests.test_pm_bridged_writer_10090 import _mark
from tests.test_polymarket_withdrawal_speed_10651 import rig as pm_rig
from tests.test_single_event_commit_10090 import rig as stamp_rig

pytestmark = pytest.mark.asyncio


def _bridges(monkeypatch, events=(2,), live=()):
    """Each of ``events`` a pure bridged open pair (yes 900+2n, no 901+2n);
    ``live`` events read live in their stamps and in the refresher's set."""
    count = max(events)
    statuses = {eid: "live" if eid in live else "scheduled" for eid in range(1, count + 1)}
    x = stamp_rig(monkeypatch, count=count, block=True, blocked=(1,), statuses=statuses)
    batch, mapping, complements = {}, {}, {}
    for n, eid in enumerate(events):
        yes, no = 900 + 2 * n, 901 + 2 * n
        batch.update({yes: 0.7, no: 0.3})
        mapping.update({yes: eid, no: eid})
        complements.update({yes: no, no: yes})
    p = pm_rig(batch=batch, mapping=mapping, books={})
    p.release.set()
    p.ns["FLUSH_CHUNK_ROWS"] = 250
    p.ns["open_complement_of"] = complements
    p.ns["open_outcome_ids"].update(batch)
    p.ns["input_marks"] = {
        oid: _mark(oid, mapping[oid], value, n)
        for n, (oid, value) in enumerate(batch.items(), 1)
    }
    x.r.receipts = p.ns["tail_receipts"] = blend.TailReceipts("polymarket")
    p.ns["blend_refresher"] = x.r
    p.ns["logger"] = blend.logger
    x.r._live_event_ids.update(live)
    x.release.set()
    return p, x


def _set_live(x, event_id, on):
    for _market, event in x.rows:
        if event.id == event_id:
            event.status = "live" if on else "scheduled"
    if on:
        x.r._live_event_ids.add(event_id)
    else:
        x.r._live_event_ids.discard(event_id)


async def _hold(side_writer, name, order, entered, release):
    """A side loop's chunk: `async with catalog_boundary.side_writer:`."""
    async with side_writer:
        order.append(name)
        entered.set()
        await release.wait()


async def _side_loop_holding(boundary, order):
    """A standalone chunk in flight and a prop chunk waiting behind it."""
    standalone_in, standalone_go = asyncio.Event(), asyncio.Event()
    prop_in, prop_go = asyncio.Event(), asyncio.Event()
    prop_go.set()
    standalone = asyncio.create_task(_hold(
        boundary.side_writer, "standalone", order, standalone_in, standalone_go,
    ))
    await asyncio.wait_for(standalone_in.wait(), 1)
    prop = asyncio.create_task(_hold(
        boundary.side_writer, "prop", order, prop_in, prop_go,
    ))
    await asyncio.sleep(0)
    return standalone_go, (standalone, prop)


def _record_bridged(p, order):
    original = p.ns["write_chunk"]

    async def write(chunk, **kwargs):
        if min(chunk, default=0) >= 900:
            order.append(sorted(chunk))
        return await original(chunk, **kwargs)

    p.ns["write_chunk"] = write


async def _drain(boundary):
    await asyncio.wait_for(boundary.bridges.join(), 2)
    await asyncio.wait_for(boundary.join_stamps(cancel=True), 2)


# ── the turn on the side connection ───────────────────────────────────────


@pytest.mark.parametrize("live", [True, False], ids=["live", "pre-game"])
async def test_switch_off_a_live_bridged_cohort_goes_ahead_of_a_waiting_side_loop(
    monkeypatch, live,
):
    """RED at 4351e94f for `live`: the bridged cohort waited behind the prop
    chunk queued before it. The pre-game control keeps today's order."""
    monkeypatch.setattr(pm, "PM_BRIDGED_SIDE_FIRST", False)
    p, x = _bridges(monkeypatch, events=(2,), live=(2,) if live else ())
    boundary = p.ns["catalog_boundary"]
    order = []
    _record_bridged(p, order)
    standalone_go, side = await _side_loop_holding(boundary, order)
    try:
        assert await asyncio.wait_for(
            p.ns["_flush_prices"](flush_started=time.monotonic()), 2,
        ) is True
        await asyncio.sleep(0)
        assert boundary.bridges.reserved == {2}
    finally:
        standalone_go.set()
        await asyncio.wait_for(asyncio.gather(*side), 1)
        await _drain(boundary)
    bridged = [900, 901]
    if live:
        # Behind the write in flight (never pre-empted), ahead of the prop
        # chunk that was already waiting.
        assert order == ["standalone", bridged, "prop"]
    else:
        assert order == ["standalone", "prop", bridged]
    assert not p.ns["price_buffer"]
    timing = boundary.bridges.take_timing()
    assert timing["bridged_live_cohorts"] == (1 if live else 0)


def _offer(boundary, order, buffer, ids, events, *, live=False, also=None):
    async def write(chunk, *, start_market_publish=None):
        order.append(sorted(chunk))
        if also is not None:
            also(chunk)
        if start_market_publish is not None:
            start_market_publish(object())
        for oid, value in chunk.items():
            if buffer.get(oid) == value:
                del buffer[oid]
        return True

    async def publish(session):
        return 0

    boundary.bridges.offer(
        ids, events, write=write, publish=publish,
        side_writer=boundary.side_writer, buffer_lock=asyncio.Lock(),
        price_buffer=buffer, input_marks={}, live=live,
    )


def _boundary(monkeypatch, on=False):
    monkeypatch.setattr(pm, "PM_BRIDGED_SIDE_FIRST", on)
    return pm._PMCatalogFlushBoundary()


async def test_a_live_offer_promotes_a_plain_wait_and_is_written_first(monkeypatch):
    """The writer already waits in arrival order for a pre-game cohort when a
    live cohort arrives: the wait moves to the first turn and the live cohort
    is the one written; the pre-game cohort then waits its turn as today."""
    boundary = _boundary(monkeypatch)
    order = []
    buffer = {700: 0.4, 800: 0.6}
    standalone_in, standalone_go = asyncio.Event(), asyncio.Event()
    standalone = asyncio.create_task(_hold(
        boundary.side_writer, "standalone", order, standalone_in, standalone_go,
    ))
    await asyncio.wait_for(standalone_in.wait(), 1)
    _offer(boundary, order, buffer, [700], {2})
    await asyncio.sleep(0)  # the writer asks for a plain turn
    prop_go = asyncio.Event()
    prop_go.set()
    prop = asyncio.create_task(_hold(
        boundary.side_writer, "prop", order, asyncio.Event(), prop_go,
    ))
    await asyncio.sleep(0)
    _offer(boundary, order, buffer, [800], {3}, live=True)
    standalone_go.set()
    await asyncio.wait_for(asyncio.gather(standalone, prop, boundary.bridges.join()), 1)
    assert order == ["standalone", [800], "prop", [700]]
    assert not buffer and not boundary.bridges.reserved
    assert not boundary.side_writer.locked()


async def test_pre_game_cohorts_filling_the_bound_never_keep_a_live_cohort_out(monkeypatch):
    assert pm.PM_BRIDGE_QUEUE_LIMIT == 2
    boundary = _boundary(monkeypatch)
    bridges = boundary.bridges
    order = []
    buffer = {700: 0.4, 701: 0.5, 800: 0.6, 801: 0.7}
    standalone_in, standalone_go = asyncio.Event(), asyncio.Event()
    standalone = asyncio.create_task(_hold(
        boundary.side_writer, "standalone", order, standalone_in, standalone_go,
    ))
    await asyncio.wait_for(standalone_in.wait(), 1)
    _offer(boundary, order, buffer, [700], {2})
    _offer(boundary, order, buffer, [701], {4})
    assert not bridges.accepting()
    assert bridges.accepting(live=True)
    _offer(boundary, order, buffer, [800], {3}, live=True)
    assert bridges.accepting(live=True)
    _offer(boundary, order, buffer, [801], {5}, live=True)
    # The live cohorts have their own bound.
    assert not bridges.accepting(live=True) and not bridges.accepting()
    standalone_go.set()
    await asyncio.wait_for(asyncio.gather(standalone, bridges.join()), 1)
    assert order == ["standalone", [800], [801], [700], [701]]
    assert not buffer


async def test_a_live_stream_never_starves_a_waiting_side_loop(monkeypatch):
    """The writer asks again only after its turn is handed on, so a side
    chunk already waiting takes the next turn between two live cohorts."""
    boundary = _boundary(monkeypatch)
    order = []
    buffer = {800: 0.6, 801: 0.7}
    standalone_in, standalone_go = asyncio.Event(), asyncio.Event()
    standalone = asyncio.create_task(_hold(
        boundary.side_writer, "standalone", order, standalone_in, standalone_go,
    ))
    await asyncio.wait_for(standalone_in.wait(), 1)

    def next_live(chunk):
        if 800 in chunk:  # the next flush's live cohort arrives meanwhile
            _offer(boundary, order, buffer, [801], {5}, live=True)

    _offer(boundary, order, buffer, [800], {3}, live=True, also=next_live)
    await asyncio.sleep(0)
    prop_go = asyncio.Event()
    prop_go.set()
    prop = asyncio.create_task(_hold(
        boundary.side_writer, "prop", order, asyncio.Event(), prop_go,
    ))
    await asyncio.sleep(0)
    standalone_go.set()
    await asyncio.wait_for(asyncio.gather(standalone, prop, boundary.bridges.join()), 1)
    assert order == ["standalone", [800], "prop", [801]]


async def test_live_wait_counts_from_hand_off_and_rides_the_minute_line(monkeypatch, caplog):
    import logging

    boundary = _boundary(monkeypatch)
    order = []
    held_in, held_go = asyncio.Event(), asyncio.Event()
    holder = asyncio.create_task(_hold(
        boundary.side_writer, "standalone", order, held_in, held_go,
    ))
    await asyncio.wait_for(held_in.wait(), 1)
    _offer(boundary, order, {800: 0.6}, [800], {3}, live=True)
    await asyncio.sleep(0.05)
    held_go.set()
    await asyncio.wait_for(asyncio.gather(holder, boundary.bridges.join()), 1)
    timing = boundary.bridges.take_timing()
    assert timing["bridged_live_cohorts"] == timing["bridged_cohorts"] == 1
    assert timing["bridged_live_wait_max_s"] >= 0.04
    assert boundary.bridges.take_timing()["bridged_live_wait_max_s"] == 0.0
    stats = {"open_contract_bridged_outcomes": 1, "open_contract_bridged_events": 1}
    stats.update(timing)
    with caplog.at_level(logging.INFO, logger=pm.logger.name):
        pm._log_open_contract_line(stats, {})
    line = caplog.records[-1].getMessage()
    assert "bridged=1/1 bridged_writes=1 side_wait=" in line
    assert " live_writes=1 live_wait=" in line and line.endswith("s")


# ── the flush's partition ─────────────────────────────────────────────────


async def test_live_events_are_offered_first_and_never_packed_with_pre_game(monkeypatch):
    """RED at 4351e94f: one 6-row cohort in buffer order."""
    monkeypatch.setattr(pm, "PM_BRIDGED_SIDE_FIRST", False)
    p, x = _bridges(monkeypatch, events=(2, 3, 4), live=(4,))
    boundary = p.ns["catalog_boundary"]
    order = []
    _record_bridged(p, order)
    try:
        assert await asyncio.wait_for(
            p.ns["_flush_prices"](flush_started=time.monotonic()), 2,
        ) is True
    finally:
        await _drain(boundary)
    assert order == [[904, 905], [900, 901, 902, 903]]
    assert not p.ns["price_buffer"]


# ── ordering: one writer per outcome, newest value last ───────────────────


async def test_a_queued_pre_game_event_that_turns_live_is_written_once_with_its_newest_value(
    monkeypatch,
):
    """Event 2's cohort is queued behind a side write; its price moves twice
    and it turns live. The next flush may not offer it again (it is reserved),
    and the one write carries the newest value — never the queued-time one."""
    monkeypatch.setattr(pm, "PM_BRIDGED_SIDE_FIRST", False)
    p, x = _bridges(monkeypatch, events=(2,))
    boundary = p.ns["catalog_boundary"]
    written = []
    original = p.ns["write_chunk"]

    async def write(chunk, **kwargs):
        written.append(dict(chunk))
        return await original(chunk, **kwargs)

    p.ns["write_chunk"] = write
    standalone_go, side = await _side_loop_holding(boundary, [])
    try:
        await p.ns["_flush_prices"](flush_started=time.monotonic())
        await asyncio.sleep(0)
        assert boundary.bridges.reserved == {2}
        for seq, value in ((50, 0.71), (51, 0.72)):
            p.ns["price_buffer"].update({900: value, 901: round(1 - value, 2)})
            p.ns["input_marks"][900] = _mark(900, 2, value, seq)
        _set_live(x, 2, True)
        await p.ns["_flush_prices"](flush_started=time.monotonic())
        assert p.ns["stats"]["bridged_handed_off"] == 2, "a reserved event was offered again"
        assert p.ns["stats"]["bridge_waiting"] >= 1
    finally:
        standalone_go.set()
        await asyncio.wait_for(asyncio.gather(*side), 1)
        await _drain(boundary)
    assert written == [{900: 0.72, 901: 0.28}]
    assert not p.ns["price_buffer"]


@pytest.mark.parametrize("seed", range(8))
async def test_randomized_ticks_liveness_and_side_load_keep_every_outcome_in_order(
    monkeypatch, seed,
):
    """Per outcome, the values written follow input order and the newest input
    is the last one written, under random ticks, liveness flips, flushes and
    a side loop taking turns on the connection."""
    monkeypatch.setattr(pm, "PM_BRIDGED_SIDE_FIRST", False)
    rnd = random.Random(seed)
    events = (2, 3, 4)
    p, x = _bridges(monkeypatch, events=events, live=(3,))
    p.ns["FLUSH_CHUNK_ROWS"] = rnd.choice((2, 4, 250))
    boundary = p.ns["catalog_boundary"]
    legs = {eid: (900 + 2 * n, 901 + 2 * n) for n, eid in enumerate(events)}
    seq_of = {}  # (oid, value) -> input seq
    last_seq = {}
    for oid, value in p.ns["price_buffer"].items():
        seq_of[(oid, value)] = last_seq[oid] = 0
    written = {}
    original = p.ns["write_chunk"]

    async def write(chunk, **kwargs):
        for oid, value in chunk.items():
            written.setdefault(oid, []).append(seq_of[(oid, value)])
        await asyncio.sleep(rnd.choice((0, 0, 0.001)))
        return await original(chunk, **kwargs)

    p.ns["write_chunk"] = write
    stop = asyncio.Event()

    async def side_loop():
        while not stop.is_set():
            async with boundary.side_writer:
                await asyncio.sleep(rnd.choice((0, 0.001, 0.002)))
            await asyncio.sleep(0)

    side = asyncio.create_task(side_loop())
    seq = 0
    try:
        for _ in range(200):
            op = rnd.random()
            if op < 0.4:
                eid = rnd.choice(events)
                seq += 1
                yes, no = legs[eid]
                value = round(0.01 + seq / 1000, 3)
                for oid, v in ((yes, value), (no, round(1 - value, 3))):
                    p.ns["price_buffer"][oid] = v
                    p.ns["input_marks"][oid] = _mark(oid, eid, v, seq)
                    seq_of[(oid, v)] = last_seq[oid] = seq
            elif op < 0.5:
                eid = rnd.choice(events)
                _set_live(x, eid, eid not in x.r._live_event_ids)
            elif op < 0.75:
                await asyncio.wait_for(
                    p.ns["_flush_prices"](flush_started=time.monotonic()), 2,
                )
            else:
                # Stamps and writes take their turns.
                await asyncio.sleep(rnd.choice((0, 0.001, 0.003)))
        stop.set()
        await asyncio.wait_for(side, 1)
        for _ in range(40):
            if not p.ns["price_buffer"] and not boundary.bridges.busy():
                break
            await asyncio.wait_for(boundary.bridges.join(), 2)
            await asyncio.wait_for(boundary.join_stamps(), 2)
            await asyncio.wait_for(
                p.ns["_flush_prices"](flush_started=time.monotonic()), 2,
            )
    finally:
        stop.set()
        await asyncio.gather(side, return_exceptions=True)
        await _drain(boundary)
    assert not p.ns["price_buffer"], p.ns["price_buffer"]
    for oid, seqs in written.items():
        assert seqs == sorted(set(seqs)), (oid, seqs)  # strictly in input order
        assert seqs[-1] == last_seq[oid], (oid, seqs, last_seq[oid])
    assert p.ns["stats"]["errors"] == 0
    timing = boundary.bridges.timing
    assert timing["bridged_live_cohorts"] >= 3
    assert timing["bridged_cohorts"] - timing["bridged_live_cohorts"] >= 3
