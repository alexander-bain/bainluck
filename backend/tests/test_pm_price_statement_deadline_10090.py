"""Only a proven price statement deadline with completed cleanup admits fallback."""

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace as NS

import asyncpg.exceptions
import pytest
from sqlalchemy.exc import DBAPIError

from app.tasks import polymarket_ws as pm
from app.utils.repair_lock_budget import SET_LOCK_TIMEOUT_SQL, SET_STATEMENT_TIMEOUT_SQL
from tests.test_pm_quote_lock_bound_10090 import writer_rig, LockHeld
from tests.test_ws_flush_cadence_10090 import _FakeTime


class PGError(Exception):
    def __init__(self, message='canceling statement due to statement timeout', code='57014'):
        self.message, self.sqlstate = message, code
        super().__init__(message)


def server_timeout():
    error = asyncpg.exceptions.QueryCanceledError()
    error.message = 'canceling statement due to statement timeout'
    return error


@pytest.mark.parametrize('error,accepted', [
    (PGError(), True),
    (PGError('canceling statement due to user request'), False),
    (PGError('statement canceled'), False),
    (PGError(code='55P03'), False),
    (TimeoutError('canceling statement due to statement timeout'), False),
    (asyncio.CancelledError(), False),
    (server_timeout(), True),
])
def test_exact_statement_timeout_diagnostic(error, accepted):
    wrapped = DBAPIError(None, None, error)
    assert pm.is_price_statement_timeout(wrapped) is accepted


def test_diagnostic_and_code_must_belong_to_same_exception():
    outer = PGError(code='57014', message='canceling statement due to user request')
    outer.__cause__ = PGError(code='XX000')
    assert not pm.is_price_statement_timeout(outer)


@pytest.fixture(autouse=True, params=[True, False], ids=['fused', 'separate'])
def fuse(request, monkeypatch):
    # #10090: every case holds with the arm/restore pairs fused (the default)
    # and with `PM_FUSE_PRICE_TIMEOUT_SETS=0` (four separate statements).
    monkeypatch.setattr(pm, 'PM_FUSE_PRICE_TIMEOUT_SETS', request.param)
    return request.param


def configured_writer(monkeypatch, failure=None, scope='game'):
    r, state = writer_rig(_FakeTime(monkeypatch, t=1000), books={})
    state.held = False
    r.ns['blend_refresher'].preview = scope != 'off'
    r.ns['blend_refresher'].preview_events = {90} if scope not in {'off', 'empty'} else set()
    if scope == 'prop':
        r.ns['non_blend_outcome_ids'].add(1)
    elif scope == 'open':
        r.ns['open_outcome_ids'].add(1)
    elif scope == 'mixed':
        r.ns['non_blend_outcome_ids'].add(2)
    elif scope == 'unknown':
        r.ns['event_id_by_outcome'].pop(1)
    events = []
    factory = r.ns['get_task_session']

    class Session:
        def __init__(self, original):
            self.original, self.info = original, original.info

        async def rollback(self):
            events.append('rollback')
            if failure == 'rollback':
                raise LockHeld()

        async def execute(self, stmt, params=None):
            if stmt is pm.ARM_LOCK_AND_DNPL_PRICE_STATEMENT_TIMEOUT_SQL:
                # The fused arm: the lock budget's SET rides inside it.
                events.append('arm')
                if failure == 'config':
                    raise PGError()
                assert params == {'lock_ms': '50ms', 'ms': '250ms'}
                await self.original.execute(SET_LOCK_TIMEOUT_SQL, {'ms': params['lock_ms']})
                return NS(scalar_one=lambda: '2s')
            if stmt is pm.RESTORE_DNPL_PRICE_TIMEOUTS_SQL:
                events.append(('restore', params['ms']))
                if failure == 'restore':
                    raise PGError()
                assert params['lock_ms'] == '500ms'
                await self.original.execute(SET_LOCK_TIMEOUT_SQL, {'ms': params['lock_ms']})
                return NS()
            if stmt is pm.ARM_DNPL_PRICE_STATEMENT_TIMEOUT_SQL:
                events.append('arm')
                if failure == 'config':
                    raise PGError()
                assert params == {'ms': '250ms'}
                return NS(scalar_one=lambda: '2s')
            if stmt is SET_STATEMENT_TIMEOUT_SQL:
                events.append(('restore', params['ms']))
                if failure == 'restore':
                    raise PGError()
                return NS()
            if isinstance(stmt, tuple) and stmt[0] == 'price':
                events.append('price')
                if failure in {'timeout', 'rollback', 'cleanup', 'cleanup-lock'}:
                    raise PGError()
                if failure == 'operator':
                    raise PGError('canceling statement due to user request')
                if failure == 'network':
                    raise ConnectionError('transport lost')
                if failure == 'cancel':
                    raise asyncio.CancelledError()
            if isinstance(stmt, tuple) and stmt[0] == 'rank':
                events.append('rank')
                if failure == 'rerank':
                    raise PGError()
            return await self.original.execute(stmt, params)

    @asynccontextmanager
    async def sessions():
        try:
            async with factory() as original:
                yield Session(original)
                if failure == 'commit':
                    raise PGError()
        finally:
            events.append('cleanup')
            if failure == 'cleanup':
                raise ConnectionError('cleanup lost')
            if failure == 'cleanup-lock':
                raise LockHeld()

    r.ns['get_task_session'] = sessions
    return r, state, events


async def test_only_update_timeout_after_rollback_and_cleanup_returns_held(monkeypatch):
    r, state, events = configured_writer(monkeypatch, 'timeout')
    assert await r.ns['write_chunk']({1: .6, 2: .4}) is None
    assert events == ['arm', 'price', 'rollback', 'cleanup']
    assert r.ns['stats']['price_statement_timeouts'] == 1
    assert not r.ns['stats'].get('price_lock_probes_refused')
    assert not state.commits and not r.ns['successful_price_write_at']
    assert {1, 2} <= r.ns['price_buffer'].keys()
    assert r.ns['lock_retry_until'] == {1: 0, 2: 0}


@pytest.mark.parametrize('failure', [
    'operator', 'network', 'config', 'restore', 'rerank', 'commit',
    'rollback', 'cleanup', 'cleanup-lock',
])
async def test_other_cause_or_phase_never_authorizes_held_fallback(monkeypatch, failure):
    r, state, events = configured_writer(monkeypatch, failure)
    assert await r.ns['write_chunk']({1: .6, 2: .4}) is False
    assert not r.ns['stats'].get('price_statement_timeouts')
    assert not state.commits and not r.ns['successful_price_write_at']
    assert {1, 2} <= r.ns['price_buffer'].keys()
    assert not r.ns['lock_retry_until']
    assert events[-1] == 'cleanup'


async def test_client_cancellation_propagates_after_cleanup_with_buffer_retained(monkeypatch):
    r, state, events = configured_writer(monkeypatch, 'cancel')
    with pytest.raises(asyncio.CancelledError):
        await r.ns['write_chunk']({1: .6, 2: .4})
    assert events == ['arm', 'price', 'cleanup']
    assert {1, 2} <= r.ns['price_buffer'].keys()
    assert not state.commits and not r.ns['lock_retry_until']


@pytest.mark.parametrize('scope', ['game', 'off', 'empty', 'prop', 'open', 'unknown', 'mixed', 'final'])
async def test_scope_and_success_restore_before_rerank(monkeypatch, scope):
    r, state, events = configured_writer(monkeypatch, scope=scope)
    assert (await r.ns['write_chunk']({1: .6, 2: .4}, final=scope == 'final')).written_ids == (1, 2)
    if scope == 'game':
        assert events == ['arm', 'price', ('restore', '2s'), 'rank', 'cleanup']
    else:
        assert events == ['price', 'rank', 'cleanup']
    assert state.commits == [1, 2]
    assert state.budgets == ([] if scope == 'final' else ['50ms', '500ms'])
