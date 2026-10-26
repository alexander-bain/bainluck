"""One-send transport controls: disconnect does not imply command cancellation."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.dnpl_activation import eval_once

pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize(
    "error", [ConnectionError("lost reply"), asyncio.CancelledError()]
)
async def test_lost_reply_or_cancel_disconnects_releases_and_never_resends(error):
    connection = SimpleNamespace(
        send_command=AsyncMock(),
        read_response=AsyncMock(side_effect=error),
        disconnect=AsyncMock(),
    )
    pool = SimpleNamespace(
        get_connection=AsyncMock(return_value=connection), release=AsyncMock()
    )
    client = SimpleNamespace(connection_pool=pool, eval=AsyncMock())
    with pytest.raises(type(error)):
        await eval_once(client, "return 1", ("a",), ("b",))
    connection.send_command.assert_awaited_once_with(
        "EVAL",
        "return 1",
        1,
        "a",
        "b",
        check_health=False,
    )
    connection.disconnect.assert_awaited_once()
    pool.release.assert_awaited_once_with(connection)
    client.eval.assert_not_awaited()


async def test_timeout_after_send_consumes_only_one_command_and_releases():
    waiting = asyncio.Event()

    async def blocked():
        await waiting.wait()

    connection = SimpleNamespace(
        send_command=AsyncMock(),
        read_response=AsyncMock(side_effect=blocked),
        disconnect=AsyncMock(),
    )
    pool = SimpleNamespace(
        get_connection=AsyncMock(return_value=connection), release=AsyncMock()
    )
    with pytest.raises(TimeoutError):
        await eval_once(SimpleNamespace(connection_pool=pool), "return 1", (), ())
    connection.send_command.assert_awaited_once()
    connection.disconnect.assert_awaited_once()
    pool.release.assert_awaited_once_with(connection)
