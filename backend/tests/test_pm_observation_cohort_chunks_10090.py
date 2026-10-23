"""Acknowledged observations in an initial mixed chunk retain ordinary writes."""

import asyncio
import time
from datetime import datetime, timezone

import pytest

from tests.test_pm_observation_beside_price_10090 import consumer_rig, warm, until
from tests.test_fresh_observation_preview_10090 import preview_enabled  # noqa: F401
from tests.test_blend_preview_display_before_persist_195 import _blends


async def mixed_chunk_rig(monkeypatch, *, unit=None, mode=None):
    rig = consumer_rig(monkeypatch)
    rig.ns['FLUSH_CHUNK_ROWS'] = 10
    await warm(rig)
    if mode == "preview-off":
        rig.r.preview_events = set()
    writes = []
    original = rig.ns['write_chunk']

    async def write(chunk, **kwargs):
        writes.append(dict(chunk))
        return await original(chunk, **kwargs)

    rig.ns['write_chunk'] = write
    if unit == 'market':
        rig.ns['market_by_outcome'][900] = rig.ns['market_by_outcome'][101]
    elif unit == 'complement':
        rig.ns['open_complement_of'] = {101: 900, 900: 101}
    await rig.feed()
    rig.ns['price_buffer'][900] = .7
    task = asyncio.create_task(rig.ns['flush_prices'](time.monotonic(), final=mode == 'final'))
    await asyncio.wait_for(rig.entered.wait(), .5)
    return rig, task, writes


async def test_initial_mixed_chunk_allows_fresh_acknowledged_a_during_b_hold(monkeypatch):
    rig, task, writes = await mixed_chunk_rig(monkeypatch)
    try:
        before = len(_blends(rig.frames))
        rig.bound[0] += .1
        await rig.feed()
        await until(lambda: len(_blends(rig.frames)) > before)
        assert _blends(rig.frames)[-1]['display_observed_at'] == datetime.fromtimestamp(
            rig.bound[0], timezone.utc,
        ).isoformat()
        assert not task.done() and not rig.release.is_set()
        assert writes == [{900: .7}], 'only B owns the held transaction'
    finally:
        rig.release.set()
        await task
    assert writes == [{900: .7}, {101: .9, 102: .1}]
    assert not rig.ns['price_buffer']
    assert not rig.session.updates and not rig.committed and not rig.r._history


async def test_a_change_during_b_hold_still_waits_for_its_ordinary_write(monkeypatch):
    rig, task, writes = await mixed_chunk_rig(monkeypatch)
    before = list(rig.frames)
    try:
        await rig.feed({101: .8, 102: .2})
        await rig.ns['flush_observations']()
        assert rig.frames == before
        assert writes == [{900: .7}]
    finally:
        rig.release.set()
        await task
    assert writes == [{900: .7}, {101: .8, 102: .2}]
    assert not rig.ns['price_buffer'] and rig.frames == before


@pytest.mark.parametrize('unit', ['market', 'complement'])
async def test_cross_event_market_or_complement_unit_stays_indivisible(monkeypatch, unit):
    rig, task, writes = await mixed_chunk_rig(monkeypatch, unit=unit)
    try:
        assert len(writes) == 1 and set(writes[0]) == {101, 102, 900}
        await rig.feed()
        await rig.ns['flush_observations']()
        assert not _blends(rig.frames), 'A shares the actual transaction with B'
    finally:
        rig.release.set()
        await task
    assert len(writes) == 1 and not rig.ns['price_buffer']


@pytest.mark.parametrize('mode', ['preview-off', 'final'])
async def test_preview_off_and_final_keep_original_mixed_transaction(monkeypatch, mode):
    rig, task, writes = await mixed_chunk_rig(monkeypatch, mode=mode)
    try:
        assert writes == [{101: .9, 102: .1, 900: .7}]
        assert not task.done()
    finally:
        rig.release.set()
        await task
    assert len(writes) == 1 and not rig.ns['price_buffer']


async def test_split_unchanged_cohort_still_writes_heartbeat_and_owes_stamp(monkeypatch):
    from tests.test_pm_quote_lock_bound_10090 import writer_rig
    from tests.test_ws_flush_cadence_10090 import _FakeTime

    clock = _FakeTime(monkeypatch, t=1030)
    database = {1: .6, 2: .4, 900: .1}
    rig, state = writer_rig(clock, database=database, books={})
    state.held = False
    rig.ns['FLUSH_CHUNK_ROWS'] = 10
    rig.ns['blend_refresher'].preview_events = {10}
    tokens = {oid: (0, value) for oid, value in database.items() if oid != 900}
    rig.ns['observation_continuity'].update(tokens)
    rig.ns['catalog_boundary'].observation_ack.update(tokens)
    rig.ns['successful_price_write_at'].update(dict.fromkeys(database, 1000))

    assert await rig.ns['flush_prices'](flush_started=1030)
    assert state.attempts == [(1030, (900,)), (1030, (1, 2))]
    assert state.forced == [{900}, {1, 2}]
    assert state.commits == [900, 1, 2]
    assert rig.ns['successful_price_write_at'] == dict.fromkeys(database, 1030)
    assert ('refresh', [10]) in rig.trace
    assert not rig.ns['price_buffer']
    assert not rig.ns['catalog_boundary'].observation_pending
