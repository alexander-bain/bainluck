"""Changed preview cohorts keep ordinary price authority ahead of unrelated waits."""

import asyncio
import os
from pathlib import Path
import time
from datetime import datetime, timezone

import pytest

from app.tasks.polymarket_ws import _PMPriceWriteResult
from tests.test_pm_observation_beside_price_10090 import consumer_rig, warm, until
from tests.test_fresh_observation_preview_10090 import preview_enabled  # noqa: F401
from tests.test_blend_preview_display_before_persist_195 import _blends, _expected


async def changed_rig(monkeypatch, *, unit=None, mode=None, withdrawal=False):
    if parent := os.environ.get('PM_OBSERVATION_PARENT'):
        import app.tasks.polymarket_ws as consumer
        from tests.test_polymarket_withdrawal_speed_10651 import compile_functions

        ns = dict(vars(consumer))
        compile_functions(Path(parent), ['_pm_lock_isolated_chunks'], ns)
        monkeypatch.setattr(consumer, '_pm_lock_isolated_chunks', ns['_pm_lock_isolated_chunks'])
    rig = consumer_rig(monkeypatch)
    rig.ns['FLUSH_CHUNK_ROWS'] = 10
    await warm(rig)
    rig.r.held_quotes.overlay_event = lambda group: None
    if mode == 'preview-off':
        rig.r.preview_events = set()
    if unit == 'market':
        rig.ns['market_by_outcome'][900] = 10
    elif unit == 'complement':
        rig.ns['open_complement_of'] = {101: 900, 900: 101}
    original = rig.ns['write_chunk']
    writes, receipts = [], []

    async def write(chunk, **kwargs):
        writes.append(dict(chunk))
        await original(chunk, **kwargs)
        written = tuple(oid for oid in chunk if oid in (101, 102))
        if written:
            at = datetime.now(timezone.utc)
            for row in rig.rows:
                if row.id in chunk:
                    row.current_probability = chunk[row.id]
                    row.last_updated = at
            # This fake database applies the successful ordinary price write;
            # the real refresher/registry then reads and publishes that value.
            rig.reading.home_probability = rig.rows[0].current_probability
            receipts.append((dict(chunk), at))
        return _PMPriceWriteResult(written)

    rig.ns['write_chunk'] = write
    rig.ns['price_buffer'][900] = .7
    await rig.feed({101: .8, 102: .2})
    if withdrawal:
        rig.ns['withdraw_buffer'][101] = (.01, .99)
    task = asyncio.create_task(rig.ns['flush_prices'](time.monotonic(), final=mode == 'final'))
    await asyncio.wait_for(rig.entered.wait(), .5)
    return rig, task, writes, receipts


async def finish(rig, task):
    rig.release.set()
    await task
    await rig.boundary.stamp_owner(rig.r).join()


async def test_buffered_changed_probability_publishes_while_unrelated_b_is_held(monkeypatch):
    rig, task, writes, receipts = await changed_rig(monkeypatch)
    try:
        await until(lambda: bool(_blends(rig.frames)))
        frame = _blends(rig.frames)[-1]
        assert frame['preview']['pending'] == {'polymarket': .8}
        assert frame['p'] == pytest.approx(_expected(rig.session.stored, 'polymarket', .8))
        assert frame['p'] != pytest.approx(_expected(rig.session.stored, 'polymarket', .9))
        assert frame['display_observed_at'] == receipts[0][1].isoformat()
        assert writes == [{101: .8, 102: .2}, {900: .7}]
        assert receipts[0][0] == {101: .8, 102: .2}
        assert not task.done() and not rig.release.is_set()
        assert not rig.committed, 'DNPL is provisional while the event row refuses its stamp'
    finally:
        await finish(rig, task)
        assert _blends(rig.frames), 'changed DNPL works after B releases on both arms'


@pytest.mark.parametrize('unit', ['market', 'complement'])
async def test_shared_unit_does_not_promote_part_of_an_event(monkeypatch, unit):
    rig, task, writes, receipts = await changed_rig(monkeypatch, unit=unit)
    try:
        assert writes == [{900: .7, 101: .8, 102: .2}]
        assert not receipts and not _blends(rig.frames)
        await rig.ns['flush_observations']()
        assert not _blends(rig.frames)
    finally:
        await finish(rig, task)
    assert len(writes) == 1


@pytest.mark.parametrize('mode', ['preview-off', 'final'])
async def test_preview_off_and_final_keep_original_changed_transaction(monkeypatch, mode):
    rig, task, writes, receipts = await changed_rig(monkeypatch, mode=mode)
    try:
        assert writes == [{900: .7, 101: .8, 102: .2}]
        assert not receipts and not _blends(rig.frames)
    finally:
        await finish(rig, task)
    assert len(writes) == 1


async def test_pending_withdrawal_keeps_changed_cohort_on_ordinary_path(monkeypatch):
    rig, task, writes, receipts = await changed_rig(monkeypatch, withdrawal=True)
    try:
        assert writes == [{900: .7, 101: .8, 102: .2}]
        assert not receipts and not _blends(rig.frames)
        assert 101 in rig.ns['withdraw_buffer']
        await rig.ns['flush_observations']()
        assert not _blends(rig.frames)
    finally:
        await finish(rig, task)
    assert not rig.ns['withdraw_buffer']


@pytest.mark.parametrize('withdrawal', [False, True])
async def test_newer_input_during_b_wait_remains_buffered_and_cannot_preview(monkeypatch, withdrawal):
    rig, task, writes, receipts = await changed_rig(monkeypatch)
    try:
        await until(lambda: bool(_blends(rig.frames)))
        before = list(rig.frames)
        await rig.feed({101: .7, 102: .3})
        if withdrawal:
            rig.ns['withdraw_buffer'][101] = (.01, .99)
        await rig.ns['flush_observations']()
        assert rig.frames == before
        assert rig.ns['price_buffer'][101] == .7
        assert rig.ns['price_buffer'][102] == .3
        assert receipts[0][0] == {101: .8, 102: .2}
        assert writes == [{101: .8, 102: .2}, {900: .7}]
    finally:
        await finish(rig, task)
    assert rig.ns['price_buffer'][101] == .7
    assert rig.ns['price_buffer'][102] == .3


def test_priority_exclusion_propagates_through_cross_event_units():
    from app.tasks.polymarket_ws import _pm_lock_isolated_chunks

    # A/C share one market; C/B share another. B is not eligible, so neither
    # C nor A may be partly promoted ahead of the original mixed transaction.
    chunks = [[900, 11, 12, 21, 22]]
    events = {11: 1, 12: 1, 21: 2, 22: 2, 900: 90}
    markets = {11: 100, 21: 100, 22: 200, 900: 200, 12: 300}
    assert _pm_lock_isolated_chunks(chunks, set(), events, markets, {}, 10,
                                    first_events={1, 2}) == chunks


def test_priority_keeps_all_event_chunks_limits_and_admitted_population():
    from app.tasks.polymarket_ws import _pm_lock_isolated_chunks

    chunks = [[900, 11], [12, 13], [901]]
    events = {11: 1, 12: 1, 13: 1, 900: 90, 901: 90, 14: 1}
    markets = {oid: oid for oid in events}
    result = _pm_lock_isolated_chunks(chunks, set(), events, markets, {}, 2,
                                     first_events={1})
    assert result == [[11, 12], [13], [900], [901]]
    assert sorted(oid for chunk in result for oid in chunk) == [11, 12, 13, 900, 901]
    assert all(len(chunk) <= 2 for chunk in result)
