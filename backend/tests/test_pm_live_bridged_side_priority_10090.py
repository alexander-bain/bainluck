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
from app.utils import blend_preview
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


class _SimulatedClock:
    """``pm.time`` (and the refresher's ``_mono``) whose ``monotonic`` moves only
    when the test advances it, so queue ages (``PM_PREGAME_BRIDGE_MAX_WAIT_S``)
    and the stamp budget count simulated steps, never a busy runner's wall
    clock."""

    def __init__(self):
        self.now = 1000.0

    def monotonic(self):
        return self.now

    def __getattr__(self, name):
        return getattr(time, name)


async def _turns(count):
    """``count`` event-loop turns: pacing by scheduling, never by wall time."""
    for _ in range(count):
        await asyncio.sleep(0)


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


# ── a pre-game cohort under a live stream (lane1, #11769 review) ──────────


async def test_a_pre_game_cohort_has_its_own_bound_and_goes_first_once_it_has_waited(
    monkeypatch,
):
    """RED at 0b4954ed: pre-game admission counted live cohorts, and a queued
    live cohort was always popped first. Now two live cohorts outstanding leave
    a pre-game cohort room, and one that has waited its bound is written next."""
    monkeypatch.setattr(pm, "PM_PREGAME_BRIDGE_MAX_WAIT_S", 0.05, raising=False)
    boundary = _boundary(monkeypatch)
    bridges = boundary.bridges
    order = []
    buffer = {700: 0.4, 701: 0.5, 800: 0.6, 801: 0.7}
    standalone_in, standalone_go = asyncio.Event(), asyncio.Event()
    standalone = asyncio.create_task(_hold(
        boundary.side_writer, "standalone", order, standalone_in, standalone_go,
    ))
    await asyncio.wait_for(standalone_in.wait(), 1)
    _offer(boundary, order, buffer, [800], {3}, live=True)
    _offer(boundary, order, buffer, [801], {5}, live=True)
    assert not bridges.accepting(live=True)
    assert bridges.accepting(), "live cohorts kept a pre-game cohort out"
    _offer(boundary, order, buffer, [700], {2})
    await asyncio.sleep(0.06)  # the pre-game cohort waits past its bound
    _offer(boundary, order, buffer, [701], {4})  # this one has not
    assert not bridges.accepting()
    standalone_go.set()
    await asyncio.wait_for(asyncio.gather(standalone, bridges.join()), 1)
    assert order == ["standalone", [700], [800], [801], [701]]
    assert not buffer and not bridges.reserved


@pytest.mark.parametrize("withdraw", [False, True], ids=["price", "withdrawal"])
async def test_a_pre_game_event_repriced_under_a_saturating_live_stream_is_written(
    monkeypatch, withdraw,
):
    """RED at 0b4954ed (lane1's scratch case; base 4351e94f GREEN): live events
    2, 3 and 5 reprice every 2 ms flush and each bridged write takes 15 ms, so
    a live cohort is always queued and the writer never idles. Pre-game event 4 reprices once (``withdrawal``: and a
    wide book refutes its held price, a withdrawal that waits with that price).
    At 0b4954ed it was refused or passed over on every flush (lane1's rig: 0
    pre-game writes after 48 live ones). Now it is written once it has waited
    the shipped bound, and its withdrawal follows, while the stream keeps going."""
    monkeypatch.setattr(pm, "PM_BRIDGED_SIDE_FIRST", False)
    bound = getattr(pm, "PM_PREGAME_BRIDGE_MAX_WAIT_S", 0.5)
    assert bound <= 0.5
    p, x = _bridges(monkeypatch, events=(2, 3, 4, 5), live=(2, 3, 5))
    boundary = p.ns["catalog_boundary"]
    written = []
    original = p.ns["write_chunk"]

    async def write(chunk, **kwargs):
        written.append(sorted(chunk))
        await asyncio.sleep(0.015)  # several flushes: the writer never idles
        return await original(chunk, **kwargs)

    p.ns["write_chunk"] = write
    seq = 100

    async def live_flush():
        nonlocal seq
        for eid, (yes, no) in ((2, (900, 901)), (3, (902, 903)), (5, (906, 907))):
            seq += 1
            value = round(0.2 + (seq % 500) / 1000, 3)
            for oid, v in ((yes, value), (no, round(1 - value, 3))):
                p.ns["price_buffer"][oid] = v
                p.ns["input_marks"][oid] = _mark(oid, eid, v, seq)
        await asyncio.wait_for(
            p.ns["_flush_prices"](flush_started=time.monotonic()), 2,
        )
        await asyncio.sleep(0.002)

    def done():
        if withdraw:
            return any(
                kind == "withdraw" and ids and 904 in ids for kind, ids in p.trace
            )
        return any(904 in chunk for chunk in written[tick:])

    try:
        for _ in range(20):
            await live_flush()
        tick, ticked = len(written), time.monotonic()
        for oid, v in ((904, 0.61), (905, 0.39)):
            p.ns["price_buffer"][oid] = v
            p.ns["input_marks"][oid] = _mark(oid, 4, v, 99999)
        if withdraw:
            p.ns["withdraw_buffer"][904] = (0.1, 0.9)
        while not done() and time.monotonic() - ticked < bound + 1.5:
            await live_flush()
        waited = time.monotonic() - ticked
        after = written[tick:]
    finally:
        await _drain(boundary)
    pregame = [n for n, chunk in enumerate(after) if 904 in chunk]
    assert pregame, (
        f"pre-game event 4 unwritten {waited:.2f} s after its reprice, behind "
        f"{len(after)} live writes"
    )
    assert done(), "its withdrawal never followed the written price"
    # The stream really kept the writer busy: live cohorts went first until
    # the pre-game cohort's bound, then it took one turn.
    assert pregame[0] >= 10, after[:pregame[0] + 1]
    assert len(pregame) == 1
    assert 904 not in p.ns["price_buffer"]
    assert p.ns["stats"]["errors"] == 0


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
    a side loop taking turns on the connection.

    Every delay is event-loop turns and the writer's clock is simulated (one
    millisecond per step), each actor drawing from its own stream: the run is
    a function of the seed alone, so its cohort mix is too. With real sleeps,
    a loaded runner (load 48) wrote 2 live cohorts where the bound says 3."""
    monkeypatch.setattr(pm, "PM_BRIDGED_SIDE_FIRST", False)
    clock = _SimulatedClock()
    monkeypatch.setattr(pm, "time", clock)
    monkeypatch.setattr(blend, "_mono", clock.monotonic)  # the stamp budget's clock
    # No ledger: a stamp's preview read would open a real Redis socket, whose
    # reply arrives on the runner's clock.
    monkeypatch.setattr(blend_preview, "_REGISTRY", blend_preview.PreviewRegistry())
    rnd = random.Random(seed)
    write_pace = random.Random(f"write-{seed}")
    side_pace = random.Random(f"side-{seed}")
    events = (2, 3, 4)
    p, x = _bridges(monkeypatch, events=events, live=(3,))
    p.ns["FLUSH_CHUNK_ROWS"] = rnd.choice((2, 4, 250))
    # A pre-game cohort past its bound jumps the live ones (0 s: every time).
    monkeypatch.setattr(
        pm, "PM_PREGAME_BRIDGE_MAX_WAIT_S", rnd.choice((0.0, 0.002, 0.5)), raising=False,
    )
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
        await _turns(write_pace.choice((0, 0, 3)))
        return await original(chunk, **kwargs)

    p.ns["write_chunk"] = write
    stop = asyncio.Event()

    async def side_loop():
        while not stop.is_set():
            async with boundary.side_writer:
                await _turns(side_pace.choice((0, 3, 6)))
            await asyncio.sleep(0)

    side = asyncio.create_task(side_loop())
    seq = 0
    try:
        for _ in range(200):
            clock.now += 0.001
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
                    p.ns["_flush_prices"](flush_started=clock.monotonic()), 2,
                )
            else:
                # Stamps and writes take their turns.
                await _turns(rnd.choice((0, 3, 9)))
        stop.set()
        await asyncio.wait_for(side, 1)
        for _ in range(40):
            clock.now += 0.001
            if not p.ns["price_buffer"] and not boundary.bridges.busy():
                break
            await asyncio.wait_for(boundary.bridges.join(), 2)
            await asyncio.wait_for(boundary.join_stamps(), 2)
            await asyncio.wait_for(
                p.ns["_flush_prices"](flush_started=clock.monotonic()), 2,
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
