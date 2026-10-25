import asyncio
from contextlib import asynccontextmanager
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from app.tasks import polymarket_ws as pm

pytestmark = pytest.mark.asyncio
PREFIX = 'Polymarket WS: startup recovery scan complete '


def withdrawal(cid):
    return (cid, 10, {'outcome_id': cid, 'market_id': 20, 'last_updated': None}, pm.PM_WITHDRAWAL_DEBT_SOURCE)


def publication(cid):
    return (cid, 10, {'frame': {'event_id': 10, 'rev': {'10': 3}}}, pm.PM_WITHDRAWAL_DEBT_SOURCE + '_publish')


@pytest.fixture
def rig(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=pm.logger.name)
    debt = pm.PMWithdrawalDebt()
    claim = AsyncMock(return_value=True)
    monkeypatch.setattr(debt, '_claim_owner', claim)
    batches = []
    queries = []

    class Session:
        async def execute(self, statement):
            queries.append(str(statement))
            item = batches.pop(0)
            if isinstance(item, BaseException):
                raise item
            return SimpleNamespace(all=lambda: item)

    @asynccontextmanager
    async def sessions():
        yield Session()

    def messages():
        return [r.getMessage() for r in caplog.records if r.getMessage().startswith(PREFIX)]

    return SimpleNamespace(debt=debt, claim=claim, batches=batches, queries=queries,
                           sessions=sessions, messages=messages)


async def test_empty_success_is_visible_and_scans_only_once(rig):
    rig.batches.append([])
    assert await rig.debt.load(rig.sessions) == 0
    assert rig.debt.loaded
    assert rig.messages() == [PREFIX + 'polymarket_withdrawal=0 polymarket_withdrawal_publish=0']
    assert await rig.debt.load(rig.sessions) == 0
    assert len(rig.queries) == rig.claim.await_count == 1
    assert len(rig.messages()) == 1


async def test_both_source_counts_are_the_rows_adopted(rig):
    rig.batches.append([withdrawal(1), publication(2), publication(3)])
    assert await rig.debt.load(rig.sessions) == 3
    assert set(rig.debt.owed) == {1}
    assert set(rig.debt.publications) == {2, 3}
    assert rig.messages() == [PREFIX + 'polymarket_withdrawal=1 polymarket_withdrawal_publish=2']
    assert len(rig.queries) == 1


async def test_failure_never_claims_empty_success_and_existing_retry_can_complete(rig):
    rig.batches.extend([RuntimeError('controlled read failure'), []])
    assert await rig.debt.load(rig.sessions) == 0
    assert not rig.debt.loaded and not rig.messages()
    # Advance only the existing retry gate; no new scheduling is introduced.
    rig.debt._retry_at = 0
    assert await rig.debt.load(rig.sessions) == 0
    assert rig.messages() == [PREFIX + 'polymarket_withdrawal=0 polymarket_withdrawal_publish=0']
    assert len(rig.queries) == 2


async def test_owner_refusal_does_not_claim_a_successful_scan(rig):
    rig.claim.return_value = False
    assert await rig.debt.load(rig.sessions) == 0
    assert not rig.debt.loaded and not rig.messages() and not rig.queries


async def test_cancellation_remains_cancellation_without_success(rig):
    rig.batches.append(asyncio.CancelledError())
    with pytest.raises(asyncio.CancelledError):
        await rig.debt.load(rig.sessions)
    assert not rig.debt.loaded and not rig.messages()
    assert not rig.debt._load_running


async def test_full_page_does_not_claim_completion_and_counts_survive_failed_continuation(rig, monkeypatch):
    monkeypatch.setattr(pm, 'PM_WITHDRAWAL_DEBT_LOAD_LIMIT', 2)
    rig.batches.extend([[withdrawal(1), publication(2)], RuntimeError('controlled continuation failure'), [publication(3)]])
    assert await rig.debt.load(rig.sessions) == 2
    assert not rig.debt.loaded and not rig.messages()
    assert await rig.debt.load(rig.sessions) == 0
    assert not rig.messages()
    rig.debt._retry_at = 0
    assert await rig.debt.load(rig.sessions) == 1
    assert rig.messages() == [PREFIX + 'polymarket_withdrawal=1 polymarket_withdrawal_publish=2']
    assert set(rig.debt.owed) == {1} and set(rig.debt.publications) == {2, 3}
    assert len(rig.queries) == 3


async def test_later_reload_does_not_repeat_startup_success(rig):
    rig.batches.extend([[], [withdrawal(1)]])
    assert await rig.debt.load(rig.sessions) == 0
    rig.debt.require_reload(uncertain=False)
    assert await rig.debt.load(rig.sessions) == 1
    assert set(rig.debt.owed) == {1}
    assert rig.messages() == [PREFIX + 'polymarket_withdrawal=0 polymarket_withdrawal_publish=0']
    assert len(rig.queries) == 2
