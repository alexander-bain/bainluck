"""#10090 held-first price writes: a live game a reader holds open takes the
first transaction of a PM game flush, and nothing else changes.

Executed consumer closures and the real refresher (the changed-cohort rig);
an asyncio barrier replaces persistence. Unrelated game 90's leg 900 leads the
buffer and its write blocks, so the order of the flush's transactions is what
the test reads. Proves scheduling, not PG latency.
"""

import asyncio
import time

import pytest

from app.tasks import live_blend_refresh as lbr
from app.tasks import polymarket_ws as consumer
from app.tasks.polymarket_ws import _pm_lock_isolated_chunks, _PMPriceWriteResult
from tests.test_pm_observation_beside_price_10090 import consumer_rig, until, warm
from tests.test_fresh_observation_preview_10090 import preview_enabled  # noqa: F401

pytestmark = pytest.mark.asyncio

HELD = {101: .8, 102: .2}
ONE_TRANSACTION = [{900: .7, 101: .8, 102: .2}]
HELD_FIRST = [HELD, {900: .7}]


async def held_rig(monkeypatch, *, held=frozenset({1}), live=frozenset({1}),
                   unit=None, preview=False, final=False, open_leg=False):
    rig = consumer_rig(monkeypatch)
    rig.ns['FLUSH_CHUNK_ROWS'] = 10
    await warm(rig)
    rig.r.held_quotes.overlay_event = lambda group: None
    if not preview:
        # The changed-preview promotion is off, so only the held set can
        # move a cohort.
        rig.r.preview_events = set()
    rig.r.reader_held = held if callable(held) else (lambda: held)
    rig.r._live_event_ids = set(live)
    if unit == 'market':
        rig.ns['market_by_outcome'][900] = 10
    elif unit == 'complement':
        rig.ns['open_complement_of'] = {101: 900, 900: 101}
    if open_leg:
        # Mixed held game: the linked binary 101/102 plus a bridged
        # open-catalog leg 103 of the same event, so it stays on this flush.
        rig.ns['event_id_by_outcome'][103] = 1
        rig.ns['market_by_outcome'][103] = 11
        rig.ns['open_outcome_ids'].add(103)
        rig.ns['price_buffer'][103] = .3
    original = rig.ns['write_chunk']
    writes = []

    async def write(chunk, **kwargs):
        writes.append(dict(chunk))
        await original(chunk, **kwargs)
        return _PMPriceWriteResult(tuple(oid for oid in chunk if oid in HELD))

    rig.ns['write_chunk'] = write
    rig.ns['price_buffer'][900] = .7
    await rig.feed(HELD)
    task = asyncio.create_task(rig.ns['flush_prices'](time.monotonic(), final=final))
    await asyncio.wait_for(rig.entered.wait(), .5)
    return rig, task, writes


async def finish(rig, task):
    rig.release.set()
    await task
    await rig.boundary.stamp_owner(rig.r).join()


async def test_baseline_unheld_game_keeps_the_one_shared_transaction(monkeypatch):
    rig, task, writes = await held_rig(monkeypatch, held=frozenset())
    try:
        assert writes == ONE_TRANSACTION
    finally:
        await finish(rig, task)


async def test_held_live_game_is_written_before_the_unrelated_blocked_write(monkeypatch):
    rig, task, writes = await held_rig(monkeypatch)
    try:
        # The held game's whole binary committed while game 90 still waits.
        assert writes == HELD_FIRST
        assert not task.done()
        assert 101 not in rig.ns['price_buffer'] and 102 not in rig.ns['price_buffer']
    finally:
        await finish(rig, task)
    # The unheld game is still written in the SAME flush: nothing is starved.
    assert writes == HELD_FIRST
    assert 900 not in rig.ns['price_buffer']


async def test_switch_off_restores_the_old_order(monkeypatch):
    monkeypatch.setenv(lbr.STAMP_READER_FIRST_ENV, '0')
    rig, task, writes = await held_rig(monkeypatch)
    try:
        assert writes == ONE_TRANSACTION
    finally:
        await finish(rig, task)


@pytest.mark.parametrize('case', ['not-live', 'source-raises', 'other-game-held'])
async def test_no_preference_without_a_held_live_game(monkeypatch, case):
    def raising():
        raise ConnectionError('presence unreadable')

    kwargs = {
        'not-live': dict(live=frozenset()),
        'source-raises': dict(held=raising),
        'other-game-held': dict(held=frozenset({77})),
    }[case]
    rig, task, writes = await held_rig(monkeypatch, **kwargs)
    try:
        assert writes == ONE_TRANSACTION
    finally:
        await finish(rig, task)


@pytest.mark.parametrize('unit', ['market', 'complement'])
async def test_a_unit_shared_with_an_unheld_game_is_never_split(monkeypatch, unit):
    rig, task, writes = await held_rig(monkeypatch, unit=unit)
    try:
        assert writes == ONE_TRANSACTION
    finally:
        await finish(rig, task)


async def test_a_mixed_held_game_with_an_open_leg_keeps_the_old_order(monkeypatch):
    # Authority R1 on 1090ab92: promoting it would pull open leg 103 into the
    # head transaction ([101, 102, 103]), which is then no game chunk and
    # makes every other live game in the flush wait behind it. The
    # changed-preview path already refuses an event with an open leg.
    rig, task, writes = await held_rig(monkeypatch, open_leg=True)
    try:
        assert writes == ONE_TRANSACTION
    finally:
        await finish(rig, task)
    assert writes == ONE_TRANSACTION + [{103: .3}]


async def test_final_drain_keeps_its_order(monkeypatch):
    rig, task, writes = await held_rig(monkeypatch, final=True)
    try:
        assert writes == ONE_TRANSACTION
    finally:
        await finish(rig, task)


async def test_a_lock_retried_held_game_keeps_its_isolation_behind(monkeypatch):
    rig = consumer_rig(monkeypatch)
    rig.ns['FLUSH_CHUNK_ROWS'] = 10
    await warm(rig)
    rig.r.preview_events = set()
    rig.r.reader_held = lambda: frozenset({1})
    rig.r._live_event_ids = {1}
    rig.ns['lock_retry_events'].add(1)
    writes = []
    original = rig.ns['write_chunk']

    async def write(chunk, **kwargs):
        writes.append(dict(chunk))
        return await original(chunk, **kwargs)

    rig.ns['write_chunk'] = write
    rig.ns['price_buffer'][900] = .7
    await rig.feed(HELD)
    task = asyncio.create_task(rig.ns['flush_prices'](time.monotonic()))
    try:
        await asyncio.wait_for(rig.entered.wait(), .5)
        # Retry isolation runs the healthy remainder first, as before.
        assert writes == [{900: .7}]
    finally:
        await finish(rig, task)


@pytest.mark.parametrize('stamping', [{1}, None], ids=['stamp-running', 'debt-unknown'])
async def test_a_held_game_whose_stamp_is_running_or_unknown_is_left_in_place(
    monkeypatch, stamping,
):
    rig = consumer_rig(monkeypatch)
    rig.ns['FLUSH_CHUNK_ROWS'] = 10
    await warm(rig)
    rig.r.preview_events = set()
    rig.r.reader_held = lambda: frozenset({1})
    rig.r._live_event_ids = {1}
    owner = rig.boundary.stamp_owner(rig.r)
    gate = asyncio.Event()
    owner.task = asyncio.create_task(gate.wait())
    monkeypatch.setattr(type(owner), 'held_events', lambda self: stamping)
    plans = []
    real = _pm_lock_isolated_chunks

    def spy(chunks, retry_events, *args, first_events=(), **kwargs):
        plans.append(set(first_events))
        return real(chunks, retry_events, *args, first_events=first_events, **kwargs)

    monkeypatch.setattr(consumer, '_pm_lock_isolated_chunks', spy)
    rig.ns['price_buffer'][900] = .7
    await rig.feed(HELD)
    task = asyncio.create_task(rig.ns['flush_prices'](time.monotonic()))
    try:
        # Unknown debt then takes the serial path (it waits for the stamp
        # before writing), so read the plan, not the write.
        await until(lambda: bool(plans))
        assert plans == [set()]
    finally:
        gate.set()
        await owner.task
        owner.task = None
        rig.release.set()
        await task


@pytest.mark.filterwarnings('ignore::pytest.PytestWarning')
def test_saturated_flush_puts_held_cohorts_first_and_keeps_every_row():
    # Six unheld games' binaries in planned chunks of four rows, held games 3
    # and 6 at the back. The held cohorts lead; every other chunk keeps its
    # rows and its relative order, and the admitted population is unchanged.
    events = {oid: oid // 10 for g in range(1, 7) for oid in (g * 10, g * 10 + 1)}
    markets = {oid: oid // 10 for oid in events}
    chunks = [[10, 11, 20, 21], [30, 31, 40, 41], [50, 51, 60, 61]]
    result = _pm_lock_isolated_chunks(chunks, set(), events, markets, {}, 4,
                                      first_events={3, 6})
    assert result[:2] == [[30, 31], [60, 61]]
    assert result[2:] == [[10, 11, 20, 21], [40, 41], [50, 51]]
    assert sorted(o for c in result for o in c) == sorted(o for c in chunks for o in c)
