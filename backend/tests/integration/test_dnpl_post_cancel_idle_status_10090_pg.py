"""#10090 10090-POST-CANCEL-IDLE-STATUS-INTERLEAVING through the ACTUAL caller.

PILLAR: TRUTH. SHIP: a reader following a live event keeps valid DNPL coverage
while genuinely idle capacity is reclaimed; when preview service cannot be
provided, the committed fallback stays truthful.

Fable, test-only, base b37cd811ce10ae5e9cba0ea90904af616ce892cc.
The unchanged residency assertion reproduced on b37cd811 at line 123.
Successor controls also verify lock lifetime, repeated cancellation and read failure.

Real: `LiveBlendRefresher._maintain_preview_capacity`, `_retire_idle_preview_event`,
`_prepare_ledger_previews`, the shipped Lua, redis-py's pooled connection,
disposable Postgres, and a private Redis (existing `capacity` fixture).
Controlled seam: a byte-faithful unix-socket relay between the worker's redis
client and the private Redis. It forwards bytes in order, but holds the stream
once it sees the retire_idle operation argument, until the test releases it
(network/TLS/retransmission delay). Like TCP after FIN, it still delivers bytes
the client sent before closing. Barriers only; there is no sleep race.
"""
import asyncio
import re

import pytest
from redis.asyncio import Redis
from sqlalchemy import text

from app.utils import blend_preview
from app.utils.live_push import event_channel
from tests.integration.test_dnpl_capacity_lifecycle_10090_pg import capacity  # noqa: F401
from tests.integration.test_live_blend_grouped_commit_8129_pg import DB_URL, rig  # noqa: F401
from tests.test_blend_preview_ledger_tsp1_10090 import BASE10, _ev, redis_kwargs  # noqa: F401

pytestmark = [pytest.mark.asyncio, pytest.mark.skipif(
    not DB_URL, reason="requires disposable SEARCH_TEST_DATABASE_URL",
)]

L = blend_preview.LEDGER_KEY
#: The operation is its own RESP bulk string; the script text only contains it quoted.
OP = re.compile(rb"\r\n\$11\r\nretire_idle\r\n\$\d+\r\n[a-z]+\r\n\$\d+\r\n\d+\r\n\$\d+\r\n(\d+)\r\n")


class HoldingRelay:
    def __init__(self, upstream: str, path: str):
        self.upstream, self.path = upstream, path
        self.holding, self.release, self.reply_seen = asyncio.Event(), asyncio.Event(), asyncio.Event()
        self.event_id = None
        self.clients = []

    async def start(self):
        self.server = await asyncio.start_unix_server(self._serve, path=self.path)

    async def _serve(self, cr, cw):
        self.clients.append(cw)
        ur, uw = await asyncio.open_unix_connection(self.upstream)
        held = False

        async def up():
            nonlocal held
            seen = b""
            while True:
                chunk = await cr.read(65536)
                if not chunk:
                    break
                seen = (seen + chunk)[-4096:]
                match = None if held else OP.search(seen)
                if match:
                    held = True
                    self.event_id = int(match.group(1))
                    self.holding.set()
                    await self.release.wait()
                uw.write(chunk)
                await uw.drain()
            if held:                         # the client is gone; deliver, await the reply, then close
                await self.reply_seen.wait()
            uw.close()

        async def down():
            while True:
                data = await ur.read(65536)
                if not data:
                    break
                if held and self.release.is_set():
                    self.reply = data
                    self.reply_seen.set()
                try:
                    cw.write(data)
                    await cw.drain()
                except Exception:
                    pass                      # the client already closed: reply is undeliverable

        await asyncio.gather(up(), down(), return_exceptions=True)


@pytest.mark.parametrize("failure", ["shutdown", "pass_timeout", "read_connection_error"])
async def test_post_cancel_late_retire_idle_does_not_remove_a_row_that_went_live(
        rig, capacity, redis_kwargs, monkeypatch, tmp_path, failure):
    worker, registry, client, reads = capacity
    async with rig.engine.begin() as conn:
        await conn.execute(text("UPDATE events SET status='scheduled', commence_time=NOW()+INTERVAL '8 days'"))
    for eid in range(1, 513):                        # settled -> idle future-scheduled residency
        await registry.execute(registry.committed(eid, 'kalshi', seq=registry.pending_seq(eid, 'kalshi'),
                               sources=BASE10, rev=10), client.execute_command, event_channel, worker.preview_stats)
    relay = HoldingRelay(redis_kwargs['unix_socket_path'], str(tmp_path / 'relay.sock'))
    await relay.start()
    relayed = Redis(unix_socket_path=relay.path)
    monkeypatch.setattr(worker, '_client', lambda: relayed)
    timing = {}
    hold_entered = asyncio.Event()
    retire = worker._retire_idle_preview_event
    async def record_deadline(eid, ticket, deadline_ms, when):
        timing['deadline'] = when
        return await retire(eid, ticket, deadline_ms, when)
    monkeypatch.setattr(worker, '_retire_idle_preview_event', record_deadline)
    hold = worker._hold_idle_proof_until
    async def record_hold(when, error):
        timing['hold_start'] = asyncio.get_running_loop().time()
        timing['error'] = error
        hold_entered.set()
        try:
            await hold(when, error)
        finally:
            timing['hold_end'] = asyncio.get_running_loop().time()
            timing['cancelling_at_hold_end'] = asyncio.current_task().cancelling()
    monkeypatch.setattr(worker, '_hold_idle_proof_until', record_hold)
    try:
        task = asyncio.create_task(worker._maintain_preview_capacity())
        await asyncio.wait_for(relay.holding.wait(), 5)     # 3: retire_idle transmitted, not executed
        E = relay.event_id
        assert await client.hget(L, f'e:{E}:gen') is not None
        if failure == 'shutdown':
            task.cancel('shutdown-first')  # Outer pass timeout supplies the second cancellation.
        elif failure == 'read_connection_error':
            for writer in relay.clients:
                writer.close()
                await writer.wait_closed()
        await asyncio.wait_for(hold_entered.wait(), 3)
        if failure != 'pass_timeout':
            from sqlalchemy.exc import DBAPIError
            with pytest.raises(DBAPIError) as locked:
                async with rig.engine.begin() as conn:
                    await conn.execute(text("SET LOCAL lock_timeout='20ms'"))
                    await conn.execute(text("UPDATE events SET status='live' WHERE id=:id"), {'id': E})
            assert 'lock timeout' in str(locked.value)
        await asyncio.gather(task, return_exceptions=True)
        assert task.done()
        assert timing['hold_end'] >= timing['deadline']
        if failure == 'shutdown':
            # asyncio.timeout.__aexit__ removes its own cancellation after the hold.
            assert timing['cancelling_at_hold_end'] >= 2
            assert task.cancelled() and task.cancelling() >= 1
            assert timing['error'].args == ('shutdown-first',)
        elif failure == 'read_connection_error':
            from app.tasks.live_blend_refresh import PreviewSettlementUncertain
            from redis.exceptions import ConnectionError
            assert isinstance(timing['error'], PreviewSettlementUncertain)
            assert isinstance(timing['error'].__cause__, ConnectionError)
            assert not task.cancelled()
        else:
            assert timing['hold_start'] >= timing['deadline']
            assert timing['hold_end'] - timing['hold_start'] < .1
            assert not task.cancelled()
        # 5: a supported writer commits the live transition once the row lock is free.
        # A repaired caller may hold the lock until the existing pass deadline (<= 1 s).
        async with rig.engine.begin() as conn:
            await conn.execute(text("SET LOCAL lock_timeout='3s'"))
            await conn.execute(text("UPDATE events SET status='live' WHERE id=:id"), {'id': E})
        assert asyncio.get_running_loop().time() >= timing['deadline']
        assert await client.hget(L, f'e:{E}:gen') is not None   # still not executed
        relay.release.set()                                  # 6: delayed bytes reach Redis
        await asyncio.wait_for(relay.reply_seen.wait(), 5)
        assert b'late' in relay.reply
        # 7: invariant: a row the database says is live keeps its residency, so its
        # next changed blend publishes without re-admission.
        assert await client.hget(L, f'e:{E}:gen') is not None, (
            'POST-CANCEL: a delayed retire_idle removed residency from a row that went live: '
            + relay.reply[:40].decode(errors='replace'))
        ticket, _ = await registry.read_ticket(client.execute_command, 'kalshi')
        event = _ev('live'); event.preview_read_ticket = ticket
        frames = await registry.prepare(registry.propose(E, 'kalshi', value=.73, event=event,
                                                         row_sources=BASE10, row_rev=10),
                                        client.execute_command, worker.preview_stats)
        assert frames and frames[0]['preview']['kind'] == 'blend'
    finally:
        relay.release.set()
        relay.server.close()
        await relay.server.wait_closed()
        await relayed.aclose()


@pytest.mark.parametrize('deadline,status', [(10000, 'late'), (9999, 'late'), (10001, 'ok'), (None, 'malformed')])
async def test_idle_deadline_exact_redis_clock_boundary(rig, capacity, monkeypatch, deadline, status):
    worker, registry, client, _ = capacity
    for eid in range(1, 513):
        await registry.execute(registry.committed(eid, 'kalshi', seq=registry.pending_seq(eid, 'kalshi'),
                               sources=BASE10, rev=10), client.execute_command, event_channel, worker.preview_stats)
    from tests.test_blend_preview_ledger_tsp1_10090 import REAL_NOW, FAKE_NOW, CLOCK_KEY
    script = blend_preview.LEDGER_SCRIPT
    assert REAL_NOW in script
    monkeypatch.setattr(blend_preview, 'LEDGER_SCRIPT', script.replace(REAL_NOW, FAKE_NOW))
    await client.set(CLOCK_KEY, 10000)
    ticket, _, _, now = await registry.capacity_ticket(client.execute_command, 'kalshi')
    assert now == 10000
    before = await client.hgetall(L)
    args = ['kalshi', registry.claim_of('kalshi'), 1, ' '.join(registry.sources), 10, ticket]
    if deadline is not None:
        args.append(deadline)
    reply = await registry._eval(client.execute_command, 'retire_idle', *args)
    assert reply[0] == status
    if status == 'ok':
        assert await client.hget(L, 'e:1:gen') is None
        assert int(await client.hget(L, 'nevents')) == 511
    else:
        assert await client.hgetall(L) == before


async def test_elapsed_local_budget_never_sends_idle_eval(rig, capacity, monkeypatch):
    worker, registry, client, _ = capacity
    from app.tasks.live_blend_refresh import PreviewSettlementUncertain
    ticket, _, _, now = await registry.capacity_ticket(client.execute_command, 'kalshi')
    op = registry.retire_idle(1, 'kalshi', 10, ticket, now + 1000)
    op['send_before'] = asyncio.get_running_loop().time()
    before = await client.hgetall(L)
    with pytest.raises(PreviewSettlementUncertain) as exc:
        await worker._prepare_ledger_previews([op])
    assert isinstance(exc.value.__cause__, TimeoutError)
    assert 'before transmission' in str(exc.value.__cause__)
    assert await client.hgetall(L) == before
