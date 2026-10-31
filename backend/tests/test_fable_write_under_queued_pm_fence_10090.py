"""Fable's control for write-under-queued on the SHIPPED Polymarket game flush
(`STAMP_WRITE_UNDER_QUEUED`, #10090): executed consumer closures
(`consumer_rig`), the real refresher, an asyncio barrier for persistence.

Two things the chunk loop must do for the refresher's lift to be truth-safe:

1. The game chunk fence reads the refresher's `fenced_event_ids` through
   `_PMStampOwner.fenced_events` — an event the refresher no longer fences
   (its attempt is queued, within the lift) is written; one it still fences
   (its attempt is running) is kept buffered exactly as today.
2. The write lease brackets the planned events: `writing_begin(planned)`
   before the first `write_chunk`, `writing_end(done, written=...)` after the
   chunk has returned and BEFORE the committed cohort is offered — so a
   queued attempt never starts under its own event's write, and the offer
   finds the absorb right already granted.

Proves scheduling, not PG latency. RED on `6c9f406e` (no lease is taken and a
queued event the refresher would lift is still fenced there).
"""

import asyncio
import contextlib
import time

import pytest

from app.tasks import live_blend_refresh as refresh_module
from app.tasks import polymarket_ws as consumer
from app.tasks.polymarket_ws import _PMPriceWriteResult
from tests.test_admitted_debt_slots_10090 import _settle
from tests.test_pm_observation_beside_price_10090 import consumer_rig, until, warm
from tests.test_fresh_observation_preview_10090 import preview_enabled  # noqa: F401

GAME = {101: .8, 102: .2}  # event 1's two legs; 900 is unrelated game 90's


async def fence_rig(monkeypatch, *, fenced):
    """A flush with the stamp owner RUNNING, event 1 holding, and the
    refresher's fence answer stubbed to ``fenced``; records every write,
    lease call and offer in order."""
    rig = consumer_rig(monkeypatch)
    rig.ns['FLUSH_CHUNK_ROWS'] = 10
    await warm(rig)
    rig.r.held_quotes.overlay_event = lambda group: None
    rig.r.preview_events = set()
    rig.r._live_event_ids = {1}
    owner = rig.boundary.stamp_owner(rig.r)
    gate = asyncio.Event()
    owner.task = asyncio.create_task(gate.wait())
    owner.events = {1, 90}
    rig.r.holding_event_ids = lambda: frozenset({1})
    if fenced is not None:
        rig.r.fenced_event_ids = lambda: frozenset(fenced)
    trace = []
    original = rig.ns['write_chunk']

    async def write(chunk, **kwargs):
        trace.append(('write', frozenset(chunk)))
        await original(chunk, **kwargs)
        return _PMPriceWriteResult(tuple(chunk))

    rig.ns['write_chunk'] = write
    for name in ('writing_begin', 'writing_end'):
        real = getattr(rig.r, name, None)
        if real is None:
            continue

        def spy(event_ids, *, _name=name, _real=real, **kwargs):
            trace.append((_name, frozenset(event_ids), frozenset(kwargs.get('written', ()))))
            return _real(event_ids, **kwargs)

        setattr(rig.r, name, spy)
    admit = rig.r.admit_fresh

    def offer(event_ids, **kwargs):
        trace.append(('offer', frozenset(event_ids)))
        return admit(event_ids, **kwargs)

    rig.r.admit_fresh = offer
    rig.ns['price_buffer'][900] = .7
    await rig.feed(GAME)
    task = asyncio.create_task(rig.ns['flush_prices'](time.monotonic()))
    await asyncio.wait_for(rig.entered.wait(), .5)
    return rig, task, trace, gate, owner


async def finish(rig, task, gate, owner, trace=None):
    # The write returns first; with the owner still running, the committed
    # cohort is OFFERED to its door (`admit_fresh`), and only then does the
    # owner end, so the flush's join of it completes.
    rig.release.set()
    if trace is not None:
        await until(lambda: any(entry[0] == 'offer' for entry in trace))
    gate.set()
    await owner.task
    owner.task = None
    await task


@pytest.mark.asyncio
async def test_a_queued_event_the_refresher_lifts_is_written_under_the_lease(monkeypatch):
    monkeypatch.setenv('STAMP_WRITE_UNDER_QUEUED', 'all')
    rig, task, trace, gate, owner = await fence_rig(monkeypatch, fenced=set())
    try:
        # `6c9f406e`: 101/102 are fenced (holding) and no lease is taken.
        writes = [ids for kind, *rest in trace for ids in rest[:1] if kind == 'write']
        assert writes and {101, 102} <= writes[0], trace
        assert rig.ns['stats']['stamp_fenced'] == 0
        assert trace[0][0] == 'writing_begin' and {1, 90} <= trace[0][1], trace
        assert trace.index(trace[0]) < trace.index(('write', writes[0]))
    finally:
        await finish(rig, task, gate, owner, trace)
    kinds = [entry[0] for entry in trace]
    # The lease ends after the write returned and before the cohort is offered.
    assert kinds.index('writing_end') > kinds.index('write')
    assert kinds.index('writing_end') < kinds.index('offer'), trace
    ended = [entry for entry in trace if entry[0] == 'writing_end']
    assert any({1, 90} <= written for _kind, _ids, written in ended), ended
    assert 101 not in rig.ns['price_buffer'] and 102 not in rig.ns['price_buffer']


@pytest.mark.asyncio
async def test_an_event_the_refresher_still_fences_is_kept_buffered_as_today(monkeypatch):
    monkeypatch.setenv('STAMP_WRITE_UNDER_QUEUED', 'all')
    rig, task, trace, gate, owner = await fence_rig(monkeypatch, fenced={1})
    try:
        writes = [ids for kind, *rest in trace for ids in rest[:1] if kind == 'write']
        assert writes == [frozenset({900})], trace
        assert rig.ns['stats']['stamp_fenced'] == 2
        assert 101 in rig.ns['price_buffer'] and 102 in rig.ns['price_buffer']
    finally:
        await finish(rig, task, gate, owner)
    # A fenced event is released from the lease without a written right.
    ended = [entry for entry in trace if entry[0] == 'writing_end']
    assert ended and all(1 not in written for _kind, _ids, written in ended), ended


@pytest.mark.asyncio
async def test_with_the_switch_off_the_owner_fences_what_it_held_today(monkeypatch):
    monkeypatch.delenv('STAMP_WRITE_UNDER_QUEUED', raising=False)
    # No stub: the real `fenced_event_ids` falls back to `holding_event_ids`.
    rig, task, trace, gate, owner = await fence_rig(monkeypatch, fenced=None)
    try:
        writes = [ids for kind, *rest in trace for ids in rest[:1] if kind == 'write']
        assert writes == [frozenset({900})], trace
        assert rig.ns['stats']['stamp_fenced'] == 2
    finally:
        await finish(rig, task, gate, owner)


def test_the_owner_asks_the_refresher_for_the_fence_and_falls_back_to_holding():
    class Refresher:
        def __init__(self, holding, fenced=None):
            self._holding, self._fenced = holding, fenced
            self.release_wake = None

        def holding_event_ids(self):
            return self._holding

        def fenced_event_ids(self):
            return self._fenced

    owner = consumer._PMStampOwner(Refresher(frozenset({1, 2}), frozenset({2})))
    assert owner.fenced_events() is None  # membership unknown, as held_events
    owner.events = {1, 2, 3}
    assert owner.fenced_events() == {2}
    assert owner.held_events() == {1, 2}
    # Unknown fence (the call has not opened its door): the whole membership.
    owner = consumer._PMStampOwner(Refresher(None, None))
    owner.events = {1, 2, 3}
    assert owner.fenced_events() == {1, 2, 3} == owner.held_events()

    class Older:
        release_wake = None

        def holding_event_ids(self):
            return frozenset({4})

    owner = consumer._PMStampOwner(Older())
    owner.events = {4, 5}
    assert owner.fenced_events() == {4} == owner.held_events()


# ── Authority R1 / R2 (a1312769 review): the lease against the REAL call ─────
#
# The rigs above stub the refresher's fence and stand a bare gate in for the
# running call. These run the real refresher's call — its own stamp (99) and
# three admitted workers (7, 8, 9) held at their gates, the game's attempt
# QUEUED behind them, as on the saturated lane — so the executed chunk loop
# meets the real worker's lease skip.

async def running_call_rig(monkeypatch, *, queued, chunk_rows):
    monkeypatch.setattr(refresh_module, 'FRESH_STAMP_WORKERS', 3)
    monkeypatch.setattr(refresh_module, 'WRITE_LEASE_WAIT_S', .01)
    rig = consumer_rig(monkeypatch)
    rig.ns['FLUSH_CHUNK_ROWS'] = chunk_rows
    await warm(rig)
    rig.r.held_quotes.overlay_event = lambda group: None
    rig.r.preview_events = set()
    owner = rig.boundary.stamp_owner(rig.r)
    await owner.join()
    rig.r.min_refresh_interval_s = 0
    rig.r._last_refresh_at.clear()
    trace = []
    gates = {eid: asyncio.Event() for eid in (99, 7, 8, 9)}

    async def stamp(event_ids, now, *, on_committed=None, **_kwargs):
        for event_id in event_ids:
            trace.append(('stamp', event_id))
            rig.r._last_refresh_at[event_id] = now
        for event_id in event_ids:
            gate = gates.get(event_id)
            if gate is not None:
                await gate.wait()
        if on_committed is not None:
            on_committed(event_ids)

    rig.r._refresh_batch = stamp
    rig.r._live_event_ids = {7, 8, 9, *queued}
    at = time.monotonic()
    owner.task = asyncio.create_task(rig.r.refresh([99], flush_started=at))
    await _settle()
    assert rig.r.admitting()
    for event_id in (7, 8, 9, *queued):
        at += .01
        assert rig.r.admit_fresh([event_id], flush_started=at) == {event_id}
        await _settle()
    window = rig.r._admission
    assert list(window.live_queue) == list(queued) and not window.queue
    assert trace == [('stamp', eid) for eid in (99, 7, 8, 9)]
    owner.events = {99, 7, 8, 9, *queued}
    rig.release.set()  # the rig's own 900 barrier; these tests gate their own
    original = rig.ns['write_chunk']

    async def write(chunk, **kwargs):
        trace.append(('write', frozenset(chunk)))
        await original(chunk, **kwargs)
        return _PMPriceWriteResult(tuple(chunk))

    rig.ns['write_chunk'] = write
    return rig, owner, gates, trace


async def drained(rig, owner, gates, task):
    for gate in gates.values():
        gate.set()
    try:
        await asyncio.wait_for(asyncio.shield(task), 2)
    finally:
        if not task.done():
            # Unstick the deadlocked flush so the test fails rather than hangs.
            rig.r._writing.clear()
            task.cancel()
            with contextlib.suppress(BaseException):
                await task
        await owner.join(cancel=not task.done())


@pytest.mark.asyncio
@pytest.mark.parametrize('switch', ['all', '1'])
@pytest.mark.parametrize('site', ['chunk_loop_join', 'joined_ready_path'])
async def test_a_flush_that_joins_the_call_yields_its_lease_so_the_call_drains(
    monkeypatch, switch, site,
):
    """R1: a flush that WAITS for the running call while it holds the lease of
    an event whose attempt is queued in that call must hand the attempt back
    (`lease_yield` -> `writing_yield`): the worker skips a leased event, so
    the call could never drain and the lease never end. One case per PM join
    site; each site's `lease_yield()` deleted makes its case time out."""
    monkeypatch.setenv('STAMP_WRITE_UNDER_QUEUED', switch)
    rig, owner, gates, trace = await running_call_rig(
        monkeypatch, queued=(1,), chunk_rows=1,
    )
    if site == 'chunk_loop_join':
        # Membership unknown (as after a joined fallback started the next
        # call): the chunk loop's own join, before game 1's chunk is written.
        owner.events = None
        await rig.feed(GAME)
    else:
        # A call that no longer admits (its door closed by a lifecycle drain):
        # game 90's chunk returns first and its offer is refused, so the flush
        # joins the call while game 1's later chunk keeps its lease.
        rig.r.stop_admitting()
        rig.ns['price_buffer'][900] = .7
        await rig.feed(GAME)
    task = asyncio.create_task(rig.ns['flush_prices'](time.monotonic()))
    await until(lambda: 1 in rig.r._writing or task.done())
    await drained(rig, owner, gates, task)
    writes = [entry[1] for entry in trace if entry[0] == 'write']
    if site == 'joined_ready_path':
        assert writes[0] == frozenset({900}), trace
    # The lease stays for the chunks still to come: game 1 is written as
    # planned, and no attempt of game 1 started under its own write.
    assert {101, 102} <= frozenset().union(*writes), trace
    last_game_write = max(
        i for i, e in enumerate(trace) if e[0] == 'write' and e[1] & {101, 102}
    )
    assert ('stamp', 1) not in trace[:last_game_write], trace
    assert not rig.r._writing


@pytest.mark.asyncio
async def test_an_n_horizon_fenced_event_leaves_the_lease_while_the_written_one_is_in_flight(
    monkeypatch,
):
    """R2 (Authority P1's shape, on the executed chunk loop): with N=1 and
    games 1 and 90 queued in that order, the flush plans both; 1 is lifted and
    written, 90 is past the horizon and fenced. The fence is sticky, so 90
    leaves the lease when it is fenced, and a freed worker starts 90 while
    game 1's write is still in flight — and still never starts 1 under it."""
    monkeypatch.setenv('STAMP_WRITE_UNDER_QUEUED', '1')
    rig, owner, gates, trace = await running_call_rig(
        monkeypatch, queued=(1, 90), chunk_rows=10,
    )
    fenced = rig.r.fenced_event_ids()
    assert 1 not in fenced and 90 in fenced, fenced
    in_flight, finish_write = asyncio.Event(), asyncio.Event()
    recorded = rig.ns['write_chunk']

    async def write(chunk, **kwargs):
        if 101 in chunk:
            in_flight.set()
            await finish_write.wait()
        return await recorded(chunk, **kwargs)

    rig.ns['write_chunk'] = write
    rig.ns['price_buffer'][900] = .7
    await rig.feed(GAME)
    task = asyncio.create_task(rig.ns['flush_prices'](time.monotonic()))
    try:
        await asyncio.wait_for(in_flight.wait(), .5)
        assert rig.ns['stats']['stamp_fenced'] == 1  # 900: game 90, fenced
        gates[7].set()  # a worker frees mid-write
        await until(lambda: ('stamp', 90) in trace)
        assert ('stamp', 1) not in trace, trace  # 1 is still under its write
        assert rig.r._writing == {1}, rig.r._writing
        assert 900 in rig.ns['price_buffer']
    finally:
        finish_write.set()
        await drained(rig, owner, gates, task)
