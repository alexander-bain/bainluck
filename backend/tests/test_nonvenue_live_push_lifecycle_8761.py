"""The nonvenue publisher owns one short-lived client per committed batch."""

import asyncio
from types import SimpleNamespace

import pytest

from app.utils.nonvenue_live_push import publish_committed_nonvenue_frames


@pytest.mark.parametrize("outcome", ["success", "failure", "cancelled"])
async def test_committed_batch_closes_its_client_and_empty_drain_builds_none(
    monkeypatch, outcome
):
    class Redis:
        closed = 0
        published = 0

        async def publish(self, channel, data):
            self.published += 1
            if outcome == "failure":
                raise RuntimeError("Redis unavailable")
            if outcome == "cancelled":
                raise asyncio.CancelledError()

        async def aclose(self):
            self.closed += 1

    clients = []

    def build():
        client = Redis()
        clients.append(client)
        return client

    monkeypatch.setattr("app.tasks.redis_state.get_async_redis_client", build)
    session = SimpleNamespace(
        info={
            "nonvenue_probability_committed": [
                {"event_id": 8761, "source": "mlb", "p": 0.6}
            ]
        }
    )
    if outcome == "cancelled":
        with pytest.raises(asyncio.CancelledError):
            await publish_committed_nonvenue_frames(session)
    else:
        await publish_committed_nonvenue_frames(session)
    assert len(clients) == 1
    assert clients[0].published == 1
    assert clients[0].closed == 1
    await publish_committed_nonvenue_frames(session)
    assert len(clients) == 1
