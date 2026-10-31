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
import time

import pytest

from app.tasks import polymarket_ws as consumer
from app.tasks.polymarket_ws import _PMPriceWriteResult
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
