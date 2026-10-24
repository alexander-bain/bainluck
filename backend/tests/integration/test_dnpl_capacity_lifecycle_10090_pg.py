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


@pytest.mark.parametrize('state', ['live', 'scheduled', 'suspended'])
async def test_idle_residency_reclaims_settled_slots_and_admits_eligible_pages(rig, capacity, state):
    worker, registry, client, reads = capacity
    async with rig.engine.begin() as conn:
        await conn.execute(text("UPDATE events SET status=:status, win_probability_sources_rev=11, "
                                "commence_time=NOW()+INTERVAL '2 hours'"),
                           {'status': state})
    for eid in range(1, 513):
        seq = registry.pending_seq(eid, 'kalshi')
        assert seq is not None
        await registry.execute(registry.committed(eid, 'kalshi', seq=seq, sources=BASE10, rev=11),
                               client.execute_command, event_channel, worker.preview_stats)
    assert int(await client.hget(blend_preview.LEDGER_KEY, 'nevents')) == 512
    ticket, candidates, idle, redis_now = await registry.capacity_ticket(client.execute_command, 'kalshi')
    assert set(candidates) == idle == set(range(1, 513))
    old_gen = int(await client.hget(blend_preview.LEDGER_KEY, 'e:1:gen'))
    event = _ev(state); event.preview_read_ticket = ticket
    delayed = registry.propose(1, 'polymarket', value=.8, event=event,
                               row_sources=BASE10, row_rev=11)
    subscriber = client.pubsub()
    await subscriber.subscribe(event_channel(1), event_channel(513))
    await subscriber.get_message(timeout=1)
    await subscriber.get_message(timeout=1)
    try:
        await worker._maintain_preview_capacity()
        if state in ('live', 'suspended'):
            # K1 supersedes the old expectation that settled LIVE residency
            # may be discarded. Protected capacity stays safely full.
            assert int(await client.hget(blend_preview.LEDGER_KEY, 'nevents')) == 512
            assert int(await client.hget(blend_preview.LEDGER_KEY, 'e:1:gen')) == old_gen
            ticket, _ = await registry.read_ticket(client.execute_command, 'kalshi')
            event.preview_read_ticket = ticket
            frames = await registry.prepare(registry.propose(1, 'kalshi', value=.8,
                event=event, row_sources=BASE10, row_rev=11), client.execute_command, worker.preview_stats)
            assert frames and frames[0]['preview']['kind'] == 'blend'
            return
        assert int(await client.hget(blend_preview.LEDGER_KEY, 'nevents')) == 480
        assert await client.hget(blend_preview.LEDGER_KEY, 'e:1:gen') is None
        assert not any('UPDATE events' in sql for sql in reads)
        async with rig.maker() as session:
            assert await session.scalar(select(Event.win_probability_sources_rev).where(Event.id == 1)) == 11
        revoke_msg = await subscriber.get_message(ignore_subscribe_messages=True, timeout=1)
        assert revoke_msg is not None
        old_revoke = json.loads(revoke_msg['data'])
        assert old_revoke['preview']['kind'] == 'revoke'
        assert old_revoke['preview']['reason'] == 'idle'
        assert not await registry.prepare(delayed, client.execute_command, worker.preview_stats)
        for eid in (513, 1):
            ticket, _ = await registry.read_ticket(client.execute_command, 'kalshi')
            event = _ev(state); event.preview_read_ticket = ticket
            await worker._publish_previews(registry.propose(
                eid, 'kalshi', value=.8, event=event, row_sources=BASE10, row_rev=11))
            message = await subscriber.get_message(ignore_subscribe_messages=True, timeout=1)
            assert message is not None
            frame = json.loads(message['data'])
            assert frame['event_id'] == eid and frame['preview']['kind'] == 'blend'
            assert frame['preview']['epoch'] > old_gen
            if eid == 1:
                assert frame['preview']['epoch'] > old_revoke['preview']['epoch']
        assert int(await client.hget(blend_preview.LEDGER_KEY, 'nevents')) == 482
        assert worker.preview_stats['publish_errors'] == 0
    finally:
        await subscriber.aclose()


async def test_idle_candidates_are_filtered_before_batch_limit_and_rechecked(rig, capacity, monkeypatch):
    worker, registry, client, reads = capacity
    async with rig.engine.begin() as conn:
        await conn.execute(text("UPDATE events SET status='scheduled', commence_time=NOW()+INTERVAL '2 hours'"))
    # First 480 are active; only the late 32 are idle. None may starve behind the first 32.
    for eid in range(481, 513):
        await registry.execute(registry.committed(eid, 'kalshi', seq=registry.pending_seq(eid, 'kalshi'),
                               sources=BASE10, rev=10), client.execute_command, event_channel, worker.preview_stats)
    prepare = worker._prepare_ledger_previews
    raced = False
    async def racing_prepare(items):
        nonlocal raced
        if not raced and items and items[0].get('ledger_op') == 'retire_idle':
            raced = True
            ticket, _ = await registry.read_ticket(client.execute_command, 'polymarket')
            event = _ev(); event.preview_read_ticket = ticket
            await registry.execute(registry.propose(481, 'polymarket', value=.8, event=event,
                                   row_sources=BASE10, row_rev=10),
                                   client.execute_command, event_channel, worker.preview_stats)
        return await prepare(items)
    monkeypatch.setattr(worker, '_prepare_ledger_previews', racing_prepare)
    await worker._maintain_preview_capacity()
    assert raced
    assert int(await client.hget(blend_preview.LEDGER_KEY, 'nevents')) == 481
    assert await client.hget(blend_preview.LEDGER_KEY, 'e:481:m:polymarket') is not None
    assert await client.hget(blend_preview.LEDGER_KEY, 'e:512:gen') is None
    assert await client.hget(blend_preview.LEDGER_KEY, 'e:1:m:kalshi') is not None
    assert worker.preview_stats['publish_errors'] == 0


async def test_adversarial_k1_live_residents_survive_and_farthest_scheduled_go_first(rig, capacity):
    worker, registry, client, reads = capacity
    async with rig.engine.begin() as conn:
        await conn.execute(text("UPDATE events SET status='scheduled', commence_time=NOW()+INTERVAL '2 hours'"))
        await conn.execute(text("UPDATE events SET status='live', commence_time=NOW()-INTERVAL '1 hour' WHERE id<=20"))
        await conn.execute(text("UPDATE events SET status='suspended', commence_time=NOW()-INTERVAL '2 hours' WHERE id BETWEEN 21 AND 40"))
        await conn.execute(text("UPDATE events SET commence_time=NOW()+id*INTERVAL '1 day' WHERE id>=481"))
    for eid in range(1, 513):
        await registry.execute(registry.committed(eid, 'kalshi', seq=registry.pending_seq(eid, 'kalshi'),
                               sources=BASE10, rev=10), client.execute_command, event_channel, worker.preview_stats)
    await worker._maintain_preview_capacity()
    assert all([await client.hget(blend_preview.LEDGER_KEY, f'e:{eid}:gen') is not None
                for eid in range(1, 41)]), 'K1: known-live or in-play suspended resident was reclaimed'
    assert all([await client.hget(blend_preview.LEDGER_KEY, f'e:{eid}:gen') is None
                for eid in range(481, 513)]), 'K1: farthest scheduled slots were not preferred'
    assert await client.hget(blend_preview.LEDGER_KEY, 'e:480:gen') is not None
    assert int(await client.hget(blend_preview.LEDGER_KEY, 'nevents')) == 480


@pytest.mark.parametrize('dead', ['old_owner', 'expired'])
async def test_adversarial_k2_dead_metadata_is_reclaimed_by_actual_caller(rig, capacity, monkeypatch, dead):
    worker, registry, client, reads = capacity
    async with rig.engine.begin() as conn:
        await conn.execute(text("UPDATE events SET status='scheduled', commence_time=NOW()+INTERVAL '8 days'"))
    if dead == 'old_owner':
        replacement = blend_preview.LedgerRegistry(sources=blend_preview.PREVIEW_SOURCES)
        await replacement.claim(client.execute_command, 'kalshi')
        monkeypatch.setattr(blend_preview, 'registry', lambda: replacement)
    else:
        # Execute the production Redis-clock check at an exact expired deadline.
        # Only time is virtual; metadata is produced by the actual fixture proposals.
        script = blend_preview.LEDGER_SCRIPT
        monkeypatch.setattr(blend_preview, 'LEDGER_SCRIPT', script.replace(
            'local now = now_ms()', 'local now = now_ms() + 60001'))
    await worker._maintain_preview_capacity()
    assert int(await client.hget(blend_preview.LEDGER_KEY, 'nevents')) == 480, 'K2: dead metadata still blocks idle reclamation'
    assert await client.hget(blend_preview.LEDGER_KEY, 'e:1:gen') is None
    assert await client.hget(blend_preview.LEDGER_KEY, 'e:1:m:kalshi') is None

    if dead == 'expired':
        ticket, _ = await registry.read_ticket(client.execute_command, 'kalshi')
        event = _ev('scheduled'); event.preview_read_ticket = ticket
        operations = registry.propose(1, 'kalshi', value=.7, event=event, row_sources=BASE10, row_rev=10)
        assert operations[0]['mode'] == 'continue'
        assert not await registry.prepare(operations, client.execute_command, worker.preview_stats)
        assert registry._events[1].expired['kalshi'] == .7
        assert registry.propose(1, 'kalshi', value=.7, event=event, row_sources=BASE10, row_rev=10) == []
        assert await client.hget(blend_preview.LEDGER_KEY, 'e:1:gen') is None


@pytest.mark.parametrize('race', ['before_lock', 'before_lock_suspended', 'before_lock_started',
                                  'before_lock_null', 'locked_row', 'during_mutation'])
async def test_idle_status_proof_is_locked_and_busy_rows_are_skipped(rig, capacity, monkeypatch, race):
    from sqlalchemy.exc import DBAPIError
    worker, registry, client, reads = capacity
    async with rig.engine.begin() as conn:
        if race == 'before_lock_null':
            # The model is NOT NULL; test the defensive guard under an
            # explicitly relaxed disposable schema, never production.
            await conn.execute(text("ALTER TABLE events ALTER COLUMN commence_time DROP NOT NULL"))
        await conn.execute(text("UPDATE events SET status='scheduled', commence_time=NOW()+INTERVAL '8 days' WHERE id=481"))
    await registry.execute(registry.committed(481, 'kalshi', seq=registry.pending_seq(481, 'kalshi'),
                           sources=BASE10, rev=10), client.execute_command, event_channel, worker.preview_stats)
    entered = False
    if race.startswith('before_lock'):
        retire = worker._retire_idle_preview_event
        async def flip_then_retire(eid, ticket, deadline_ms, when):
            nonlocal entered
            entered = True
            async with rig.engine.begin() as conn:
                changes = {
                    'before_lock': "status='live'",
                    'before_lock_suspended': "status='suspended'",
                    'before_lock_started': "commence_time=NOW()-INTERVAL '1 minute'",
                    'before_lock_null': "commence_time=NULL",
                }
                await conn.execute(text("UPDATE events SET " + changes[race] + " WHERE id=481"))
            await retire(eid, ticket, deadline_ms, when)
        monkeypatch.setattr(worker, '_retire_idle_preview_event', flip_then_retire)
    elif race == 'during_mutation':
        prepare = worker._prepare_ledger_previews
        async def prove_status_update_is_locked(items):
            nonlocal entered
            entered = True
            with pytest.raises(DBAPIError) as exc:
                async with rig.engine.begin() as conn:
                    await conn.execute(text("SET LOCAL lock_timeout='20ms'"))
                    await conn.execute(text("UPDATE events SET status='live' WHERE id=481"))
            assert 'lock timeout' in str(exc.value)
            return await prepare(items)
        monkeypatch.setattr(worker, '_prepare_ledger_previews', prove_status_update_is_locked)
    if race == 'locked_row':
        async with rig.engine.begin() as conn:
            await conn.execute(text("UPDATE events SET status='scheduled' WHERE id=481"))
            await worker._maintain_preview_capacity()
    else:
        await worker._maintain_preview_capacity()
        assert entered
    if race == 'during_mutation':
        assert await client.hget(blend_preview.LEDGER_KEY, 'e:481:gen') is None
        # The row lock is released before publishing and does not outlive maintenance.
        async with rig.engine.begin() as conn:
            await conn.execute(text("UPDATE events SET status='live' WHERE id=481"))
    else:
        assert await client.hget(blend_preview.LEDGER_KEY, 'e:481:gen') is not None
        assert int(await client.hget(blend_preview.LEDGER_KEY, 'nevents')) == 512
        assert int(await client.hget(blend_preview.LEDGER_KEY, 'retired')) == 0
    assert worker.preview_stats['publish_errors'] == 0


async def test_idle_cancel_before_eval_releases_status_lock_without_reclaim(rig, capacity, monkeypatch):
    worker, registry, client, reads = capacity
    async with rig.engine.begin() as conn:
        await conn.execute(text("UPDATE events SET status='scheduled', commence_time=NOW()+INTERVAL '8 days' WHERE id=481"))
    await registry.execute(registry.committed(481, 'kalshi', seq=registry.pending_seq(481, 'kalshi'),
                           sources=BASE10, rev=10), client.execute_command, event_channel, worker.preview_stats)
    entered = asyncio.Event()
    async def pause_before_eval(items):
        entered.set()
        await asyncio.Event().wait()
    monkeypatch.setattr(worker, '_prepare_ledger_previews', pause_before_eval)
    task = asyncio.create_task(worker._maintain_preview_capacity())
    try:
        await asyncio.wait_for(entered.wait(), 1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    assert await client.hget(blend_preview.LEDGER_KEY, 'e:481:gen') is not None
    assert int(await client.hget(blend_preview.LEDGER_KEY, 'retired')) == 0
    async with rig.engine.begin() as conn:
        await conn.execute(text("SET LOCAL lock_timeout='20ms'"))
        await conn.execute(text("UPDATE events SET status='live' WHERE id=481"))


@pytest.mark.parametrize('state', ['live', 'suspended', 'scheduled', 'unknown_start', 'boundary', 'future'])
async def test_existing_inplay_resident_keeps_preview_against_newcomer_without_pregame_escape(rig, capacity, state):
    worker, registry, client, reads = capacity
    async with rig.engine.begin() as conn:
        if state == 'unknown_start':
            # Explicit malformed-state control in this disposable schema.
            await conn.execute(text("ALTER TABLE events ALTER COLUMN commence_time DROP NOT NULL"))
        start = {'unknown_start': 'NULL', 'boundary': 'NOW()',
                 'future': "NOW()+INTERVAL '8 days'"}.get(state, "NOW()-INTERVAL '2 hours'")
        await conn.execute(text("UPDATE events SET status=:status, commence_time=" + start + " WHERE id=1"),
                           {'status': state if state in ('live', 'suspended') else 'scheduled'})
    await registry.execute(registry.committed(1, 'kalshi', seq=registry.pending_seq(1, 'kalshi'),
                           sources=BASE10, rev=10), client.execute_command, event_channel, worker.preview_stats)
    assert int(await client.hget(blend_preview.LEDGER_KEY, 'nevents')) == 512
    await worker._maintain_preview_capacity()
    resident_survives = await client.hget(blend_preview.LEDGER_KEY, 'e:1:gen') is not None
    ticket, _ = await registry.read_ticket(client.execute_command, 'kalshi')
    event = _ev('live'); event.preview_read_ticket = ticket
    newcomer = await registry.prepare(registry.propose(513, 'kalshi', value=.8, event=event,
                               row_sources=BASE10, row_rev=10), client.execute_command, worker.preview_stats)
    ticket, _ = await registry.read_ticket(client.execute_command, 'kalshi')
    event = _ev(state if state in ('live', 'suspended') else 'scheduled'); event.preview_read_ticket = ticket
    existing = await registry.prepare(registry.propose(1, 'kalshi', value=.9, event=event,
                               row_sources=BASE10, row_rev=10), client.execute_command, worker.preview_stats)
    if state == 'future':
        assert not resident_survives
        assert any(f['event_id'] == 513 and f['preview']['kind'] == 'blend' for f in newcomer)
        return
    assert resident_survives, 'CERT4288: the only idle in-play resident lost residency'
    assert not any(f['event_id'] == 513 and f['preview']['kind'] == 'blend' for f in newcomer)
    assert any(f['event_id'] == 1 and f['preview']['kind'] == 'blend' for f in existing)
    assert int(await client.hget(blend_preview.LEDGER_KEY, 'nevents')) == 512
