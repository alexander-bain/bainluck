"""#10090: a capacity pass completes and reclaims idle residents at production size.

PILLARS: TRUTH / FORMATTING. SHIP: idle and finished games stop holding preview
slots, so a busy live game in the full "Other" group gets the sub-second preview
instead of waiting for the committed stamp.

Production 10/29 (retained worker-ws windows, 10:14Z-22:42Z): the pass ended
`end=error` on its one-second budget in almost every pass on both venues.
The ledger held about 82 residents, about 42 of them idle; the shared counts
held "Other active" at 47-48 of 48 and "Other upcoming" at 10-16 of 16. Most
passes ran out of time inside the per-resident policy loop, then inside
per-resident idle retirement. Each resident cost one or two DB statements, one
`claim_lock` wait and one Redis round trip, all sequential.

Real here: `_maintain_preview_capacity`, the shipped Lua, disposable Postgres,
and a private Redis. One seam: every DB statement the worker issues costs
`STATEMENT_S`, the per-statement wait production pays under load (its passes
die after about ten statements plus lock waits, which is at least 90 ms each).

11/01 (488339ea, 8dab4471): idle residents are reclaimed only under ledger
pressure (`PREVIEW_IDLE_RECLAIM_FILL`, 75% of the cap), and lifecycle
retirements wait for pressure or a quiet ledger (`PREVIEW_LIFECYCLE_QUIET_LIVE`):
each retirement moves the global barrier and refuses every in-flight receipt.
This rig's 79 residents sit at ~15% of the cap, so the reclaim proofs run
`under_pressure` (the threshold at 0); the below-fill twins at the end keep
the shipped threshold and prove what such a pass does instead.
"""
import asyncio
import json
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

import pytest
from redis.asyncio import Redis
from sqlalchemy import text

from app.models.models import Event, Sport
from app.tasks.live_blend_refresh import LiveBlendRefresher
from app.utils import blend_preview
from app.utils.live_push import event_channel
from app.utils.preview_reservations import RESERVATIONS_ENV
from tests.integration.test_dnpl_capacity_lifecycle_10090_pg import fresh_event
from tests.integration.test_live_blend_grouped_commit_8129_pg import DB_URL, rig  # noqa: F401
from tests.test_blend_preview_ledger_tsp1_10090 import BASE10, _ev, redis_kwargs  # noqa: F401

pytestmark = [pytest.mark.asyncio, pytest.mark.skipif(
    not DB_URL, reason="requires disposable SEARCH_TEST_DATABASE_URL",
)]

L = blend_preview.LEDGER_KEY
STATEMENT_S = 0.03
#: "Other active" (bucket 4, limit 48): 10 games with a live preview, 38 idle.
ACTIVE_PREVIEW = range(1, 11)
ACTIVE_IDLE = range(11, 49)
#: "Other upcoming" (bucket 5, limit 16) and T1 upcoming (bucket 1): all idle.
OTHER_UPCOMING = range(101, 117)
T1_UPCOMING = range(201, 216)
#: Busy live "Other" games waiting for a slot.
WAITING = range(501, 504)


#: Release L's 1024 split (v2): "Other active" 448, so nothing above is full.
V2_SPLIT = '96,48,192,128,448,112'


@pytest.fixture
def ticket_kind():
    """``int``: the bare ledger. ``authority``: production's
    `AuthorityLedgerRegistry`, whose tickets are `AuthorityTicket`s (v5964)."""
    return 'int'


async def authority_registry(client, now):
    """Production's registry over its own initialized namespace on this Redis."""
    from dataclasses import replace
    from uuid import uuid4

    from app.services.dnpl_authority import Authority
    from app.utils.dnpl_authority_registry import AuthorityLedgerRegistry
    from app.utils.dnpl_redis_authority import namespace_keys
    from tests.test_dnpl_redis_authority_10090 import initial

    policy = blend_preview.LedgerRegistry(sources=('kalshi', 'polymarket')).policy
    server, repl = await client.info('server'), await client.info('replication')
    authority = Authority(3, 1, uuid4(), uuid4(), 'preparing', server['run_id'],
                          repl['master_replid'], policy.fingerprint)
    assert _text((await initial(client, authority))[0]) == 'initialized'
    authority = replace(authority, state='ready')
    return (AuthorityLedgerRegistry(authority=authority, observed_after=now - timedelta(seconds=2),
                                    sources=frozenset({'kalshi', 'polymarket'})),
            namespace_keys(authority)[0])


def _text(value):
    return value.decode() if isinstance(value, bytes) else value


def basis(now):
    """An observation after the authority registry's floor (the bare ledger ignores it)."""
    return {'1': (now - timedelta(seconds=1)).timestamp()}


@pytest.fixture
async def production(rig, redis_kwargs, monkeypatch, request, ticket_kind):
    if getattr(request, 'param', None):
        monkeypatch.setenv(RESERVATIONS_ENV, request.param)
    blend_preview.reset_registry_for_tests()
    client = Redis(**redis_kwargs)
    now = datetime.now(timezone.utc)
    if ticket_kind == 'authority':
        authority, key = await authority_registry(client, now)
        monkeypatch.setattr(blend_preview, '_REGISTRY', authority)
        monkeypatch.setitem(globals(), 'L', key)
    else:
        monkeypatch.setattr(blend_preview, '_REGISTRY',
                            blend_preview.LedgerRegistry(sources=('kalshi', 'polymarket')))
    registry = blend_preview.registry()
    await registry.claim(client.execute_command, 'kalshi')
    await registry.claim(client.execute_command, 'polymarket')
    statements = []

    @asynccontextmanager
    async def factory():
        async with rig.maker() as session:
            execute = session.execute

            async def slow(statement, *args, **kwargs):
                statements.append(str(statement))
                await asyncio.sleep(STATEMENT_S)
                return await execute(statement, *args, **kwargs)
            session.execute = slow
            yield session
            await session.commit()

    worker = LiveBlendRefresher('kalshi', session_factory=factory)
    worker._owns_preview_maintenance = False
    monkeypatch.setattr(worker, '_client', lambda: client)
    keys = ('tennis_atp', 'americanfootball_nfl')
    events = {}
    async with rig.maker() as session:
        session.add_all([Sport(id=i + 1, key=key, name=key) for i, key in enumerate(keys)])
        await session.flush()
        for eid in [*ACTIVE_PREVIEW, *ACTIVE_IDLE, *OTHER_UPCOMING, *T1_UPCOMING, *WAITING]:
            upcoming = eid >= 101 and eid < 500
            event = _ev('scheduled' if upcoming else 'live')
            event.sport_key = 'americanfootball_nfl' if eid >= 201 and eid < 500 else 'tennis_atp'
            event.preview_context_at = now
            event.commence_time = now + (timedelta(hours=2) if upcoming else -timedelta(hours=1))
            events[eid] = event
            session.add(Event(id=eid, sport_id=keys.index(event.sport_key) + 1,
                              status=event.status, home_team_name='A', away_team_name='B',
                              commence_time=event.commence_time,
                              win_probability_sources=BASE10, win_probability_sources_rev=10))
        await session.commit()
    for eid in [*ACTIVE_PREVIEW, *ACTIVE_IDLE, *OTHER_UPCOMING, *T1_UPCOMING]:
        if ticket_kind == 'authority':
            events[eid].preview_read_ticket, _ = await registry.read_ticket(
                client.execute_command, 'kalshi')
        ops = registry.propose(eid, 'kalshi', value=.7, event=events[eid],
                               row_sources=BASE10, row_rev=10, stamped_at=now,
                               observed_basis=basis(now) if ticket_kind == 'authority' else None)
        assert ops
        await registry.execute(ops, client.execute_command, event_channel, worker.preview_stats)
        if eid not in ACTIVE_PREVIEW:
            # Its commit landed: the resident now holds no valid preview.
            await registry.execute(
                registry.committed(eid, 'kalshi', seq=registry.pending_seq(eid, 'kalshi'),
                                   sources=BASE10, rev=10),
                client.execute_command, event_channel, worker.preview_stats)
    assert int(await client.hget(L, 'nevents')) == 79
    assert int(await client.hget(L, 'r:count:4')) == 48
    assert int(await client.hget(L, 'r:count:5')) == 16
    try:
        yield worker, registry, client, statements
    finally:
        await worker._close_preview_maintenance()
        await client.aclose()
        blend_preview.reset_registry_for_tests()


@pytest.fixture
def under_pressure(monkeypatch):
    """The ledger counts as full enough to reclaim idle residents and retire
    finished ones (`PREVIEW_IDLE_RECLAIM_FILL` at 0): these rigs prove the
    reclaim mechanics, which only run under pressure."""
    from app.tasks import live_blend_refresh

    monkeypatch.setattr(live_blend_refresh, 'PREVIEW_IDLE_RECLAIM_FILL', 0.0)


async def resident(client, eid):
    return await client.hget(L, f'e:{eid}:gen') is not None


async def admit(rig, registry, client, worker, eid):
    """A busy live game's next price: one fresh open, the way a flush makes it."""
    ticket, _ = await registry.read_ticket(client.execute_command, 'kalshi')
    event = await fresh_event(rig, eid, ticket)
    observed = (basis(datetime.now(timezone.utc))
                if type(ticket) is not int else None)  # AuthorityTicket: production's floor
    frames = await registry.prepare(registry.propose(eid, 'kalshi', value=.8, event=event,
                                                     row_sources=BASE10, row_rev=10,
                                                     observed_basis=observed),
                                    client.execute_command, worker.preview_stats)
    return [f['preview']['kind'] for f in frames]


def receipt(caplog):
    [line] = [r.getMessage() for r in caplog.records
              if 'preview capacity pass end=' in r.getMessage()]
    caplog.clear()
    return dict(part.split('=', 1) for part in line.split('pass ', 1)[1].split())


@pytest.mark.parametrize('ticket_kind', ['int', 'authority'])
async def test_full_other_group_reclaims_idle_residents_and_admits_busy_games(
        rig, production, caplog, ticket_kind, under_pressure):
    import logging

    worker, registry, client, statements = production
    caplog.set_level(logging.INFO, logger='app.tasks.live_blend_refresh')
    # The busy game is refused while "Other active" is full of idle residents.
    assert await admit(rig, registry, client, worker, WAITING[0]) == []
    assert not await resident(client, WAITING[0])

    loop = asyncio.get_running_loop()
    for index, eid in enumerate(WAITING):
        started = loop.time()
        statements.clear()
        await worker._maintain_preview_capacity()
        fields = receipt(caplog)
        assert fields['end'] == 'done', fields
        assert loop.time() - started < 1
        # One locked statement per stage, never one per resident.
        assert len(statements) <= 5, len(statements)
        upcoming = len(OTHER_UPCOMING) + len(T1_UPCOMING)
        if index == 0:
            # Every idle future-scheduled resident is reclaimed in one pass:
            # the full "Other upcoming" bucket gives one to policy retirement,
            # idle retirement takes the rest.
            assert not any([await resident(client, e) for e in [*OTHER_UPCOMING, *T1_UPCOMING]])
            assert int(fields['idle_attempted']) >= upcoming - 1
        # Policy retirement frees exactly one slot of the full bucket per pass,
        # never an active preview; the waiting busy game takes it.
        assert int(await client.hget(L, 'r:count:4')) == 47
        assert fields['reclaimed'] == str((upcoming if index == 0 else 0) + 1)
        assert await admit(rig, registry, client, worker, eid) == ['blend']
        assert int(await client.hget(L, 'r:count:4')) == 48
    # Protection: each game holding a valid preview kept its residency and lease.
    for eid in ACTIVE_PREVIEW:
        assert await resident(client, eid)
        meta = await client.hget(L, f'e:{eid}:m:kalshi')
        assert meta is not None
        assert int(meta.split()[-1]) > int((await client.time())[0]) * 1000
    assert sum([not await resident(client, e) for e in ACTIVE_IDLE]) == len(WAITING)


async def test_a_full_pass_publishes_one_idle_revoke_per_reclaimed_resident(
        rig, production, under_pressure):
    worker, registry, client, _ = production
    subscriber = client.pubsub()
    channels = [event_channel(e) for e in OTHER_UPCOMING]
    await subscriber.subscribe(*channels)
    for _ in channels:
        await subscriber.get_message(timeout=1)
    try:
        await worker._maintain_preview_capacity()
        revoked = set()
        while (message := await subscriber.get_message(ignore_subscribe_messages=True,
                                                         timeout=.2)) is not None:
            frame = json.loads(message['data'])
            assert frame['preview']['kind'] == 'revoke'
            assert frame['preview']['reason'] == 'idle'
            revoked.add(frame['event_id'])
        assert revoked == set(OTHER_UPCOMING)
    finally:
        await subscriber.aclose()


async def test_a_row_that_went_live_inside_the_batch_keeps_its_residency(
        rig, production, monkeypatch, under_pressure):
    """The batch's one locked read proves each row; a row no longer
    future-scheduled is skipped while its siblings are reclaimed."""
    worker, registry, client, _ = production
    async with rig.engine.begin() as conn:
        await conn.execute(text("UPDATE events SET status='live', "
                                "commence_time=NOW() - INTERVAL '1 minute' WHERE id=105"))
    retire = worker._retire_idle_preview_events
    seen = []

    async def record(eids, *args):
        seen.append(list(eids))
        return await retire(eids, *args)
    monkeypatch.setattr(worker, '_retire_idle_preview_events', record)
    await worker._maintain_preview_capacity()
    [batch] = seen
    assert 105 not in batch           # the pass's own read already saw it live
    assert await resident(client, 105)
    assert not any([await resident(client, e) for e in OTHER_UPCOMING if e != 105])


async def test_a_pass_on_a_ledger_with_nothing_idle_sends_no_retirement(rig, production):
    worker, registry, client, statements = production
    before = await client.hget(L, 'retired')
    for eid in [*ACTIVE_IDLE, *OTHER_UPCOMING, *T1_UPCOMING]:
        ticket, _ = await registry.read_ticket(client.execute_command, 'kalshi')
        event = await fresh_event(rig, eid, ticket)
        await registry.prepare(registry.propose(eid, 'kalshi', value=.75, event=event,
                                                row_sources=BASE10, row_rev=10),
                               client.execute_command, worker.preview_stats)
    statements.clear()
    await worker._maintain_preview_capacity()
    assert await client.hget(L, 'retired') == before
    assert int(await client.hget(L, 'nevents')) == 79
    assert not any('FOR SHARE' in s and 'commence_time >' in s for s in statements)


async def test_a_finished_game_and_the_idle_batch_retire_in_the_same_pass(
        rig, production, under_pressure):
    """The finished game's retirement moves the barrier; the idle batch is then
    proved after a fresh ticket, so it still reclaims in that pass."""
    worker, registry, client, _ = production
    async with rig.engine.begin() as conn:
        await conn.execute(text("UPDATE events SET status='final' WHERE id=101"))
    await worker._maintain_preview_capacity()
    assert not any([await resident(client, e) for e in [*OTHER_UPCOMING, *T1_UPCOMING]])


@pytest.mark.parametrize('production', [V2_SPLIT], indirect=True)
async def test_under_the_1024_split_the_pass_still_finishes_and_reclaims_idle_upcoming(
        rig, production, caplog, under_pressure):
    """After the switch-over no bucket here is full: the policy batch frees
    nothing, the busy game is admitted without a pass, and the same pass still
    ends inside its budget and reclaims every idle future-scheduled resident."""
    import logging

    worker, registry, client, statements = production
    assert registry.policy.cap == 1024
    caplog.set_level(logging.INFO, logger='app.tasks.live_blend_refresh')
    assert await admit(rig, registry, client, worker, WAITING[0]) == ['blend']
    started = asyncio.get_running_loop().time()
    statements.clear()
    await worker._maintain_preview_capacity()
    fields = receipt(caplog)
    assert fields['end'] == 'done', fields
    assert asyncio.get_running_loop().time() - started < 1
    assert len(statements) <= 5, len(statements)
    upcoming = len(OTHER_UPCOMING) + len(T1_UPCOMING)
    assert not any([await resident(client, e) for e in [*OTHER_UPCOMING, *T1_UPCOMING]])
    assert fields['reclaimed'] == str(upcoming)
    # A bucket below its limit gives policy retirement nothing to take.
    assert all([await resident(client, e) for e in [*ACTIVE_PREVIEW, *ACTIVE_IDLE]])
    assert int(await client.hget(L, 'r:count:4')) == 49


# ── below the fill threshold (the shipped PREVIEW_IDLE_RECLAIM_FILL) ─────────


async def test_below_the_fill_threshold_only_a_full_bucket_gives_up_a_resident(
        rig, production, caplog):
    """At ~15% of the cap no idle resident is reclaimed: each full bucket's
    policy retirement frees exactly one slot ("Other active" and "Other
    upcoming"), the busy game takes the freed one, and every T1 upcoming
    resident keeps its residency."""
    import logging

    worker, registry, client, _ = production
    caplog.set_level(logging.INFO, logger='app.tasks.live_blend_refresh')
    assert await admit(rig, registry, client, worker, WAITING[0]) == []
    await worker._maintain_preview_capacity()
    fields = receipt(caplog)
    assert fields['end'] == 'done', fields
    assert fields['idle_attempted'] == '0', fields
    assert fields['reclaimed'] == '2', fields
    assert int(await client.hget(L, 'r:count:4')) == 47
    assert sum([not await resident(client, e) for e in OTHER_UPCOMING]) == 1
    assert all([await resident(client, e) for e in T1_UPCOMING])
    assert await admit(rig, registry, client, worker, WAITING[0]) == ['blend']
    for eid in ACTIVE_PREVIEW:
        assert await resident(client, eid)


async def test_below_fill_a_finished_game_waits_while_the_ledger_is_busy(
        rig, production, monkeypatch):
    """A finished resident in a bucket below its limit is not retired while
    more than PREVIEW_LIFECYCLE_QUIET_LIVE residents are live (here 48): its
    retirement would move the barrier under every live game's next receipt.
    The same pass on a quiet ledger retires it."""
    from app.tasks import live_blend_refresh

    worker, registry, client, _ = production
    async with rig.engine.begin() as conn:
        await conn.execute(text("UPDATE events SET status='final' WHERE id=201"))
    await worker._maintain_preview_capacity()
    assert await resident(client, 201)

    monkeypatch.setattr(live_blend_refresh, 'PREVIEW_LIFECYCLE_QUIET_LIVE', 48)
    await worker._maintain_preview_capacity()
    assert not await resident(client, 201)
