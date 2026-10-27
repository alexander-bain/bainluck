"""Operator latency allowance preserves runtime and one-send contracts."""

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

import pytest

from app.services.dnpl_activation import ActivationController, eval_once
from app.services.dnpl_authority import AuthorityStore
from app.services.dnpl_operator_budget import OperatorAuthorityStore, OperatorBudgets


@pytest.mark.parametrize(
    "io,preview",
    [
        (0, 1000),
        (-1, 1000),
        (5001, 10000),
        (True, 1000),
        (1.5, 1000),
        (150, 0),
        (150, 149),
        (150, 30001),
        (150, True),
    ],
)
def test_invalid_budgets_refuse(io, preview):
    with pytest.raises(ValueError):
        OperatorBudgets(io, preview)


def test_defaults_and_runtime_cap_are_unchanged():
    b = OperatorBudgets()
    assert (b.io_s, b.preview_s) == (0.150, 1.0)
    assert AuthorityStore(None).budget_s == 0.150
    with pytest.raises(ValueError):
        AuthorityStore(None, budget_s=0.5)


async def test_operator_store_keeps_producer_sampling_at_150ms():
    @asynccontextmanager
    async def sessions():
        await asyncio.sleep(0.2)
        raise AssertionError("producer budget must expire before session opens")
        yield

    with pytest.raises(TimeoutError):
        await OperatorAuthorityStore(
            sessions, OperatorBudgets(1000, 5000)
        ).read_for_producer()


async def test_connection_latency_requires_explicit_operator_budget():
    row = dict(
        protocol=3,
        incarnation=0,
        namespace=UUID(int=0),
        operation_id=UUID(int=0),
        state="disabled",
        redis_run_id="",
        redis_master_replid="",
        policy_fingerprint="",
    )
    result = SimpleNamespace(mappings=lambda: SimpleNamespace(one_or_none=lambda: row))
    session = SimpleNamespace(execute=AsyncMock(return_value=result))

    @asynccontextmanager
    async def sessions():
        await asyncio.sleep(0.2)
        yield session

    with pytest.raises(TimeoutError):
        await AuthorityStore(sessions).read()
    assert (
        await OperatorAuthorityStore(sessions, OperatorBudgets(1000, 5000)).read()
    ).state == "disabled"


@pytest.mark.parametrize("lost_reply", [False, True])
async def test_command_latency_allowance_preserves_single_send(lost_reply):
    conn = SimpleNamespace(
        send_command=AsyncMock(),
        disconnect=AsyncMock(),
        read_response=AsyncMock(return_value=["ok"]),
    )
    if lost_reply:
        conn.read_response.side_effect = ConnectionError("lost reply")

    async def acquire():
        await asyncio.sleep(0.2)
        return conn

    pool = SimpleNamespace(
        get_connection=AsyncMock(side_effect=acquire), release=AsyncMock()
    )
    client = SimpleNamespace(connection_pool=pool)
    with pytest.raises(TimeoutError):
        await eval_once(client, "return 1", (), ())
    conn.send_command.assert_not_awaited()
    if lost_reply:
        with pytest.raises(ConnectionError):
            await eval_once(client, "return 1", (), (), budget_s=1)
        conn.disconnect.assert_awaited_once()
    else:
        assert await eval_once(client, "return 1", (), (), budget_s=1) == ["ok"]
    conn.send_command.assert_awaited_once()
    pool.release.assert_awaited_once()


@pytest.mark.parametrize("budget", [0, -1, 5.001, float("inf"), float("nan"), True])
async def test_invalid_command_budget_never_connects(budget):
    pool = SimpleNamespace(get_connection=AsyncMock())
    with pytest.raises(ValueError):
        await eval_once(
            SimpleNamespace(connection_pool=pool), "", (), (), budget_s=budget
        )
    pool.get_connection.assert_not_awaited()
    with pytest.raises(ValueError):
        ActivationController(None, None, command_budget_s=budget)
