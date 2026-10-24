"""Cleanup must not hide shutdown after a transport failure (#10090 A3)."""
import asyncio
from types import SimpleNamespace

import pytest
from redis.exceptions import ConnectionError

from app.tasks.live_blend_refresh import LiveBlendRefresher


@pytest.mark.asyncio
@pytest.mark.parametrize('cancel_during', ['disconnect', 'release'])
async def test_transport_error_then_cleanup_cancellation_survives_proof_hold(
    monkeypatch, cancel_during,
):
    entered = asyncio.Event()
    never = asyncio.Event()
    first_transport = ConnectionError('reply lost')

    async def prepare(*args):
        raise first_transport

    async def disconnect():
        if cancel_during == 'disconnect':
            entered.set()
            await never.wait()

    async def release(connection):
        if cancel_during == 'release':
            entered.set()
            await never.wait()

    connection = SimpleNamespace(disconnect=disconnect)
    pool = SimpleNamespace(release=release)

    async def checkout(_):
        return connection

    preview = SimpleNamespace(claim_lock=None, unclaimed=lambda _: False, prepare=prepare)
    monkeypatch.setattr('app.utils.blend_preview.registry', lambda: preview)
    monkeypatch.setattr('app.utils.market_quote_push._checkout', checkout)
    worker = LiveBlendRefresher('kalshi')
    monkeypatch.setattr(worker, '_client', lambda: SimpleNamespace(connection_pool=pool))
    loop = asyncio.get_running_loop()
    deadline = loop.time() + .05
    held = {}

    async def locked_operation():
        try:
            await worker._prepare_ledger_previews([
                {'ledger_op': 'retire_idle', 'send_before': deadline},
            ])
        except BaseException as error:
            held['error'] = error
            try:
                await worker._hold_idle_proof_until(deadline, error)
            finally:
                held['released'] = loop.time()

    task = asyncio.create_task(locked_operation())
    await asyncio.wait_for(entered.wait(), 1)
    task.cancel('shutdown-during-cleanup')
    with pytest.raises(asyncio.CancelledError, match='shutdown-during-cleanup'):
        await task
    assert isinstance(held['error'], asyncio.CancelledError)
    assert held['error'].args == ('shutdown-during-cleanup',)
    assert held['released'] >= deadline
    assert task.cancelled() and task.cancelling() == 1
