"""PM unchanged observations progress during an unrelated captured write chunk.

Executed consumer closures and real observation admission/registry; an asyncio
barrier replaces only persistence. This proves scheduling, not PG/Redis latency.
PM_OBSERVATION_PARENT selects the retained parent source for the red control.
"""

import asyncio
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock

import pytest

from app.tasks.live_blend_refresh import TailReceipts
from app.tasks.polymarket_ws import _PMPriceWriteResult
from tests.test_polymarket_withdrawal_speed_10651 import rig, compile_functions
from tests.test_fresh_observation_preview_10090 import acknowledged_rig, preview_enabled  # noqa: F401
from tests.test_blend_preview_display_before_persist_195 import _blends


def consumer_rig(monkeypatch):
    import app.tasks.polymarket_ws as consumer

    refresher, session, frames, committed, rows, reading, _, _, now = acknowledged_rig(monkeypatch)
    state = rig(batch={}, mapping={101: 1, 102: 1, 900: 90}, books={})
    boundary = state.ns['catalog_boundary']
    entered, release = asyncio.Event(), asyncio.Event()
    values = {row.id: row.current_probability for row in rows}
    bound = [(now - timedelta(seconds=1)).timestamp()]
    class Bounds(NS):
        def __contains__(self, oid):
            return False

    held = Bounds(bound_for=lambda mark: bound[0] if mark else None,
              note_input=lambda mark: None, sample_database_clock=AsyncMock(),
              release=lambda ids: None)
    refresher.held_quotes = held
    refresher._admission = None
    refresher.preview_events = {1}
    state.ns.update(blend_refresher=refresher, held_quotes=held,
                    tail_receipts=TailReceipts('polymarket'), input_marks={},
                    market_by_outcome={101: 10, 102: 10, 900: 90},
                    observation_continuity={}, routing_generation=0, game_period=.01)

    async def write(chunk, *, final=False, start_market_publish=None):
        if 900 in chunk:
            entered.set()
            await release.wait()
        for oid, value in chunk.items():
            if state.ns['price_buffer'].get(oid) == value:
                state.ns['price_buffer'].pop(oid)
        return _PMPriceWriteResult(())

    state.ns['write_chunk'] = write
    source = Path(os.environ.get('PM_OBSERVATION_PARENT', consumer.__file__))
    names = ['_mark_input', '_flush_prices', 'flush_prices']
    if not os.environ.get('PM_OBSERVATION_PARENT'):
        names.append('flush_observations')
    compile_functions(source, names, state.ns)

    async def feed(new_values=None):
        async with state.ns['buffer_lock']:
            for oid, value in (new_values or values).items():
                state.ns['price_buffer'][oid] = value
                state.ns['_mark_input'](oid, value, 'price_change', {})

    return NS(ns=state.ns, boundary=boundary, entered=entered, release=release,
              r=refresher, rows=rows, reading=reading, session=session, frames=frames, committed=committed,
              feed=feed, bound=bound, values=values)


async def until(predicate):
    async with asyncio.timeout(.5):
        while not predicate():
            await asyncio.sleep(.001)


async def warm(rig):
    await rig.feed()
    await rig.ns['flush_prices'](time.monotonic())
    assert _blends(rig.frames), 'both arms must have working DNPL before the barrier'
    rig.frames.clear()
    rig.bound[0] += .1


async def start_unrelated(rig):
    rig.ns['price_buffer'][900] = .7
    task = asyncio.create_task(rig.ns['flush_prices'](time.monotonic()))
    await asyncio.wait_for(rig.entered.wait(), .5)
    return task


async def test_fresh_unchanged_observation_advances_before_unrelated_write_releases(monkeypatch):
    rig = consumer_rig(monkeypatch)
    await warm(rig)
    task = await start_unrelated(rig)
    try:
        await rig.feed()
        await until(lambda: bool(_blends(rig.frames)))
        assert not task.done() and not rig.release.is_set()
        assert rig.boundary.active == 1, 'the joined drain remains inside catalog scope'
        assert not rig.session.updates and not rig.committed and not rig.r._history
    finally:
        rig.release.set()
        await task


async def test_capacity_retry_keeps_frozen_input_and_does_not_need_a_new_tick(monkeypatch):
    rig = consumer_rig(monkeypatch)
    await warm(rig)
    slots = 0
    while not rig.r._session_slots.locked():
        await rig.r._session_slots.acquire()
        slots += 1
    task = await start_unrelated(rig)
    try:
        await rig.feed()
        frozen = dict(rig.boundary.observation_pending)
        attempted = asyncio.Event()
        original = rig.r.preview_accepted_observations

        async def observe(*args):
            result = await original(*args)
            if result is False:
                attempted.set()
            return result

        rig.r.preview_accepted_observations = observe
        await asyncio.wait_for(attempted.wait(), .5)
        assert rig.boundary.observation_pending == frozen
        assert not _blends(rig.frames)
        rig.bound[0] += 10
        for _ in range(slots):
            rig.r._session_slots.release()
        slots = 0
        await until(lambda: bool(_blends(rig.frames)))
        assert _blends(rig.frames)[0]['display_observed_at'] == datetime.fromtimestamp(
            frozen[101][2], timezone.utc,
        ).isoformat()
        assert not task.done()
    finally:
        for _ in range(slots):
            rig.r._session_slots.release()
        rig.release.set()
        await task


@pytest.mark.parametrize('transition', ['changed', 'a-b-a', 'withdrawal', 'routing', 'write-started', 'stamp', 'unknown-stamp'])
async def test_send_time_recheck_refuses_related_work(monkeypatch, transition):
    rig = consumer_rig(monkeypatch)
    await warm(rig)
    task = await start_unrelated(rig)
    checkout, send, sent = asyncio.Event(), asyncio.Event(), asyncio.Event()
    original = rig.r._publish_previews

    async def publish(initial, *, prepare_frames=None):
        checkout.set()
        await send.wait()
        await original(initial, prepare_frames=prepare_frames)
        sent.set()

    rig.r._publish_previews = publish
    try:
        await rig.feed()
        await asyncio.wait_for(checkout.wait(), .5)
        if transition in ('changed', 'a-b-a'):
            await rig.feed({101: .8})
            if transition == 'a-b-a':
                await rig.feed({101: .9})
        elif transition == 'withdrawal':
            rig.ns['withdraw_buffer'][101] = (.01, .99)
        elif transition == 'routing':
            rig.ns['routing_generation'] += 1
        elif transition == 'write-started':
            rig.boundary.observation_write_epoch[1] = rig.boundary.observation_write_epoch.get(1, 0) + 1
        else:
            owner = rig.boundary.stamp_owner(rig.r)
            owner.task = NS(done=lambda: False)
            owner.events = {1} if transition == 'stamp' else None
        send.set()
        await asyncio.wait_for(sent.wait(), .5)
        assert not _blends(rig.frames)
    finally:
        owner = rig.boundary.stamp_owner(rig.r)
        owner.task = None
        owner.events = None
        send.set()
        rig.release.set()
        await task
    assert not _blends(rig.frames)


async def test_cancel_joins_observation_and_restores_frozen_work(monkeypatch):
    rig = consumer_rig(monkeypatch)
    await warm(rig)
    entered = asyncio.Event()
    original = rig.r._read_groups

    async def blocked(*args, **kwargs):
        entered.set()
        await asyncio.Event().wait()
        return await original(*args, **kwargs)

    rig.r._read_groups = blocked
    task = await start_unrelated(rig)
    await rig.feed()
    frozen = dict(rig.boundary.observation_pending)
    await asyncio.wait_for(entered.wait(), .5)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert rig.boundary.active == 0
    assert rig.boundary.observation_pending == frozen
    assert not _blends(rig.frames)
    assert not any(t.get_name() == 'kalshi-book-observations' for t in asyncio.all_tasks() if not t.done())


async def test_queued_changed_partner_owns_event_before_its_chunk_starts(monkeypatch):
    rig = consumer_rig(monkeypatch)
    await warm(rig)
    rig.reading.contributing_outcomes = [rig.rows[0]]
    task = await start_unrelated(rig)
    try:
        await rig.feed({102: .2, 101: .9})
        # The changed partner is not a contributor to this stored reading,
        # but its pending price work still owns the same event.
        await rig.ns['flush_observations']()
        assert not _blends(rig.frames)
        assert 101 in rig.boundary.observation_pending
        assert not task.done()
    finally:
        rig.release.set()
        await task
    assert not _blends(rig.frames)


async def test_false_retry_never_overwrites_newer_arrival(monkeypatch):
    rig = consumer_rig(monkeypatch)
    await warm(rig)
    task = await start_unrelated(rig)
    entered, resume = asyncio.Event(), asyncio.Event()
    original = rig.r.preview_accepted_observations

    async def unavailable(*args):
        entered.set()
        await resume.wait()
        return False

    rig.r.preview_accepted_observations = unavailable
    try:
        await rig.feed()
        await asyncio.wait_for(entered.wait(), .5)
        old = dict(rig.ns['input_marks'])
        rig.bound[0] += .1
        await rig.feed()
        newer = dict(rig.boundary.observation_pending)
        assert all(newer[oid][3].seq > old[oid].seq for oid in newer)
        resume.set()
        # Join on cancellation after the failed attempt has restored its input;
        # the latest arrival must keep ownership of both slots.
        await asyncio.sleep(.02)
        assert rig.boundary.observation_pending == newer
    finally:
        resume.set()
        rig.r.preview_accepted_observations = original
        rig.release.set()
        await task


async def test_disabled_preview_adds_no_drain_or_event_write_bookkeeping(monkeypatch):
    rig = consumer_rig(monkeypatch)
    rig.r.preview_events = frozenset()
    await rig.feed()
    await rig.ns['flush_prices'](time.monotonic())
    assert rig.boundary.observation_drain is None
    assert not rig.boundary.observation_writing
    assert not rig.boundary.observation_write_epoch
    assert not rig.boundary.observation_pending
    assert not rig.boundary.observation_ack
    assert not _blends(rig.frames)
