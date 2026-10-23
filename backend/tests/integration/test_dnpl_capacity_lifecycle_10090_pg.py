"""Default DNPL admits new games after stale/deleted rows leave the slate."""
import asyncio
import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import pytest
from redis.asyncio import Redis
from sqlalchemy import select, text

from app.models.models import Event, Sport
from app.tasks.live_blend_refresh import LiveBlendRefresher
from app.utils import blend_preview
from app.utils.live_push import event_channel
from tests.integration.test_live_blend_grouped_commit_8129_pg import DB_URL, rig  # noqa: F401
from tests.test_blend_preview_ledger_tsp1_10090 import redis_kwargs, _ev, BASE10  # noqa: F401

pytestmark = [pytest.mark.asyncio, pytest.mark.skipif(
    not DB_URL, reason="requires disposable SEARCH_TEST_DATABASE_URL",
)]


@pytest.fixture
async def capacity(rig, redis_kwargs, monkeypatch):
    blend_preview.reset_registry_for_tests()
    client = Redis(**redis_kwargs)
    registry = blend_preview.registry()
    await registry.claim(client.execute_command, 'kalshi')
    await registry.claim(client.execute_command, 'polymarket')
    reads = []

    @asynccontextmanager
    async def factory():
        async with rig.maker() as session:
            execute = session.execute
            async def recording(statement, *args, **kwargs):
                reads.append(str(statement))
                return await execute(statement, *args, **kwargs)
            session.execute = recording
            yield session
            await session.commit()

    worker = LiveBlendRefresher('kalshi', session_factory=factory)
    monkeypatch.setattr(worker, '_client', lambda: client)
    async with rig.maker() as session:
        sport = Sport(id=1, key='tennis_atp', name='Tennis')
        session.add(sport)
        await session.flush()
        session.add_all([Event(id=eid, sport_id=1, status='live',
                              home_team_name='A', away_team_name='B',
                              commence_time=datetime.now(timezone.utc),
                              win_probability_sources=BASE10,
                              win_probability_sources_rev=10)
                         for eid in range(1, 514)])
        await session.commit()
    for eid in range(1, 513):
        ops = registry.propose(eid, 'kalshi', value=.7, event=_ev(),
                               row_sources=BASE10, row_rev=10,
                               stamped_at=datetime.now(timezone.utc))
        await registry.execute(ops, client.execute_command, event_channel, worker.preview_stats)
    assert int(await client.hget(blend_preview.LEDGER_KEY, 'nevents')) == 512
    try:
        yield worker, registry, client, reads
    finally:
        await worker._close_preview_maintenance()
        await client.aclose()
        blend_preview.reset_registry_for_tests()


@pytest.mark.parametrize('state', ['suspended', 'scheduled', 'deleted'])
async def test_full_stale_slate_retires_and_new_live_event_publishes(rig, capacity, state):
    worker, registry, client, reads = capacity
    async with rig.engine.begin() as conn:
        if state == 'deleted':
            await conn.execute(text('DELETE FROM events WHERE id <= 512'))
        else:
            await conn.execute(text("UPDATE events SET status=:status, "
                                    "commence_time=NOW()-INTERVAL '3 days' WHERE id <= 512"),
                               {'status': state})
    # Prepared before disappearance: it must never resurrect the old chain.
    stale = registry.propose(1, 'polymarket', value=.8, event=_ev(),
                             row_sources=BASE10, row_rev=10,
                             stamped_at=datetime.now(timezone.utc))
    assert stale
    await worker._preview_admission_read()
    await worker._preview_maintenance_task
    assert int(await client.hget(blend_preview.LEDGER_KEY, 'nevents')) == 480
    assert await client.hget(blend_preview.LEDGER_KEY, 'e:1:gen') is None
    assert not await registry.prepare(stale, client.execute_command, worker.preview_stats)
    assert await client.hget(blend_preview.LEDGER_KEY, 'e:1:gen') is None
    if state != 'deleted':
        async with rig.maker() as session:
            assert await session.scalar(select(Event.win_probability_sources_rev).where(Event.id == 1)) == 11
    subscriber = client.pubsub()
    await subscriber.subscribe(event_channel(513))
    await subscriber.get_message(timeout=1)
    try:
        ticket = await worker._preview_admission_read()
        event = _ev()
        event.preview_read_ticket = ticket
        ops = registry.propose(513, 'kalshi', value=.8, event=event,
                               row_sources=BASE10, row_rev=10,
                               stamped_at=datetime.now(timezone.utc))
        await registry.execute(ops, client.execute_command, event_channel, worker.preview_stats)
        msg = await subscriber.get_message(ignore_subscribe_messages=True, timeout=1)
        assert msg is not None
        frame = json.loads(msg['data'])
        assert frame['event_id'] == 513 and frame['preview']['kind'] == 'blend'
        assert int(await client.hget(blend_preview.LEDGER_KEY, 'nevents')) == 481
    finally:
        await subscriber.aclose()


async def test_capacity_scans_are_background_and_once_per_cadence(rig, capacity, monkeypatch):
    worker, registry, client, reads = capacity
    ticket, candidates = await registry.read_ticket(client.execute_command, 'kalshi')
    assert ticket == 0 and candidates == []
    ticket, candidates = await registry.read_ticket(client.execute_command, 'kalshi', include_candidates=True)
    assert len(candidates) == 512
    await worker._preview_admission_read()
    await worker._preview_maintenance_task
    scan = [s for s in reads if 'retirable' in s]
    assert len(scan) == 1
    task = worker._preview_maintenance_task
    hkeys = (await client.info('commandstats'))['cmdstat_hkeys']['calls']
    for _ in range(50):
        assert await worker._preview_admission_read() == 0
    assert worker._preview_maintenance_task is task
    assert (await client.info('commandstats'))['cmdstat_hkeys']['calls'] == hkeys
    assert len([s for s in reads if 'retirable' in s]) == 1
    worker._preview_maintenance_after = 0
    await worker._preview_admission_read()
    await worker._preview_maintenance_task
    assert len([s for s in reads if 'retirable' in s]) == 2
    assert int(await client.hget(blend_preview.LEDGER_KEY, 'nevents')) == 512


async def test_shutdown_cancels_and_joins_capacity_scan(capacity, monkeypatch):
    worker, registry, client, reads = capacity
    entered, cleanup, release = asyncio.Event(), asyncio.Event(), asyncio.Event()
    async def held():
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cleanup.set()
            await release.wait()
    monkeypatch.setattr(worker, '_maintain_preview_capacity', held)
    worker._start_preview_maintenance()
    await entered.wait()
    close = asyncio.create_task(worker._close_preview_maintenance())
    await cleanup.wait()
    close.cancel()
    await asyncio.sleep(0)
    assert not close.done()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await close
    assert worker._preview_maintenance_task.done()
    previous = worker._preview_maintenance_task
    worker._preview_maintenance_after = 0
    worker._start_preview_maintenance()
    assert worker._preview_maintenance_task is previous


async def test_missing_retirement_rejects_obsolete_owner_and_ticket(rig, capacity):
    async with rig.engine.begin() as conn:
        await conn.execute(text("DELETE FROM events WHERE id IN (1, 2)"))
    worker, registry, client, reads = capacity
    ticket, _ = await registry.read_ticket(client.execute_command, 'kalshi')
    replacement = blend_preview.LedgerRegistry(sources=blend_preview.PREVIEW_SOURCES)
    await replacement.claim(client.execute_command, 'kalshi')
    stats = {}
    await registry.prepare([registry.retire_missing(1, 'kalshi', ticket)],
                           client.execute_command, stats)
    assert await client.hget(blend_preview.LEDGER_KEY, 'e:1:gen') is not None
    assert int(await client.hget(blend_preview.LEDGER_KEY, 'retired')) == 0
    assert stats['fenced'] == 1
    # A separate proven deletion invalidates all preceding absence proofs.
    await replacement.prepare([replacement.retire_missing(2, 'kalshi', ticket)],
                              client.execute_command, stats)
    assert int(await client.hget(blend_preview.LEDGER_KEY, 'retired')) == 1
    await replacement.prepare([replacement.retire_missing(1, 'kalshi', ticket)],
                              client.execute_command, stats)
    assert await client.hget(blend_preview.LEDGER_KEY, 'e:1:gen') is not None
    assert int(await client.hget(blend_preview.LEDGER_KEY, 'nevents')) == 511


async def test_repeated_withdrawal_reads_do_not_spawn_capacity_owners(rig, capacity, monkeypatch):
    from types import SimpleNamespace
    from app.models.models import FuturesMarket
    from app.tasks import live_blend_refresh, polymarket_ws

    worker, registry, client, reads = capacity
    created = []
    class RecordingRefresher(LiveBlendRefresher):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            created.append(self)
        def _client(self):
            return client
    monkeypatch.setattr(live_blend_refresh, 'LiveBlendRefresher', RecordingRefresher)
    async with rig.maker() as session:
        session.add(FuturesMarket(id=1, sport_id=1, event_id=513,
                                  source='polymarket', external_id='withdrawn',
                                  name='A vs B', status='open'))
        await session.commit()
    withdrawn = [SimpleNamespace(id=1, market_id=1,
                                last_updated=datetime.now(timezone.utc))]
    before = (await client.info('commandstats')).get('cmdstat_hkeys', {}).get('calls', 0)
    for _ in range(20):
        async with rig.maker() as session:
            assert await polymarket_ws.withdraw_attributed_event_sources(session, withdrawn) == []
    assert len(created) == 20
    assert all(isinstance(ref.preview_events, blend_preview.PreviewEventScope)
               and 513 in ref.preview_events and ref.preview for ref in created)
    assert all(ref._preview_maintenance_task is None for ref in created)
    assert (await client.info('commandstats')).get('cmdstat_hkeys', {}).get('calls', 0) == before
    assert int(await client.hget(blend_preview.LEDGER_KEY, 'nevents')) == 512
