"""Task sessions reuse a publication client; standalone drains own their own."""

import asyncio
from types import SimpleNamespace

import pytest

from app.utils.nonvenue_live_push import publish_committed_nonvenue_frames


@pytest.mark.parametrize("outcome", ["success", "failure", "cancelled", "body_error"])
async def test_task_scope_reuses_client_and_releases_on_every_exit(monkeypatch, outcome):
    from app.utils.nonvenue_live_push import nonvenue_publication_scope

    sent, clients = [], []

    class Redis:
        closed = 0

        async def publish(self, channel, data):
            sent.append(data)
            if len(sent) == 2 and outcome == "failure":
                raise RuntimeError("one send failed")
            if len(sent) == 2 and outcome == "cancelled":
                raise asyncio.CancelledError()

        async def aclose(self):
            self.closed += 1

    def build():
        client = Redis()
        clients.append(client)
        return client

    monkeypatch.setattr("app.tasks.redis_state.get_async_redis_client", build)
    session = SimpleNamespace(info={})

    async def run():
        async with nonvenue_publication_scope(session):
            await publish_committed_nonvenue_frames(session)
            assert not clients
            for i in range(3):
                session.info["nonvenue_probability_committed"] = [
                    {"event_id": i, "source": "mlb", "p": 0.6}
                ]
                await publish_committed_nonvenue_frames(session)
                assert clients[0].closed == 0
                if outcome == "body_error":
                    raise ValueError("task failed after publication")

    if outcome == "cancelled":
        with pytest.raises(asyncio.CancelledError):
            await run()
    elif outcome == "body_error":
        with pytest.raises(ValueError, match="task failed"):
            await run()
    else:
        await run()
    assert len(clients) == 1
    assert clients[0].closed == 1
    assert len(sent) == {"cancelled": 2, "body_error": 1}.get(outcome, 3)
    assert "nonvenue_probability_client_scope" not in session.info
    # A later task/session scope must never inherit the old client's loop/pool.
    async with nonvenue_publication_scope(session):
        session.info["nonvenue_probability_committed"] = [
            {"event_id": 4, "source": "mlb", "p": 0.7}
        ]
        await publish_committed_nonvenue_frames(session)
    assert len(clients) == 2 and all(c.closed == 1 for c in clients)


async def test_scope_with_no_publication_never_constructs_client(monkeypatch):
    from app.utils.nonvenue_live_push import nonvenue_publication_scope

    def forbidden():
        raise AssertionError("no committed frame")

    monkeypatch.setattr("app.tasks.redis_state.get_async_redis_client", forbidden)
    async with nonvenue_publication_scope(SimpleNamespace(info={})):
        pass


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
