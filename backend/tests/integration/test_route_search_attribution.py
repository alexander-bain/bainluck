"""Queue #243 Item 2: signed-in search attribution.

`request.state.user_id` is never set for the public /search route, so the
SearchQueryLog user_id was always NULL. The optional-auth dependency now
attributes signed-in searches. These tests assert both directions: an
authenticated user attributes; an anonymous search stays NULL (and still works).

LAT-P002/#1494 (1d): the write is now DISPATCHED, not awaited, on the request's
critical path. The attribution contract these tests guard is unchanged — the same
user_id must still reach the log — so they now drain the in-flight dispatch tasks
before asserting instead of relying on the event loop having happened to run them.
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.dependencies.auth import get_optional_user


async def _drain_search_log_tasks():
    """Await every in-flight fire-and-forget search-log task.

    Without this the assertions race the event loop: the response can return
    before the dispatched task has run.
    """
    from app.routes.events import _SEARCH_LOG_TASKS

    for _ in range(50):
        pending = [t for t in list(_SEARCH_LOG_TASKS) if not t.done()]
        if not pending:
            return
        await asyncio.gather(*pending, return_exceptions=True)


def _logged_user_id(mock_log):
    """user_id as passed to _log_search_query, positionally or by keyword."""
    call = mock_log.await_args
    if "user_id" in call.kwargs:
        return call.kwargs["user_id"]
    return call.args[3]


@pytest.mark.asyncio
async def test_signed_in_search_attributes_user_id(client):
    from app.main import app

    async def _fake_user():
        return SimpleNamespace(id=4242)

    app.dependency_overrides[get_optional_user] = _fake_user
    try:
        with patch(
            "app.routes.events._log_search_query", new_callable=AsyncMock
        ) as mock_log:
            resp = await client.get("/api/events/search?q=lakers")
            assert resp.status_code == 200
            await _drain_search_log_tasks()
            assert mock_log.await_count == 1
            assert _logged_user_id(mock_log) == 4242
    finally:
        # restore the conftest default (anonymous)
        async def _anon():
            return None
        app.dependency_overrides[get_optional_user] = _anon


@pytest.mark.asyncio
async def test_anonymous_search_user_id_none(client):
    # conftest overrides get_optional_user -> None
    with patch(
        "app.routes.events._log_search_query", new_callable=AsyncMock
    ) as mock_log:
        resp = await client.get("/api/events/search?q=celtics")
        assert resp.status_code == 200
        await _drain_search_log_tasks()
        assert mock_log.await_count == 1
        assert _logged_user_id(mock_log) is None


@pytest.mark.asyncio
async def test_search_response_does_not_wait_on_the_log_write(client):
    """LAT-P002/#1494 (1d): the response must not be gated on the log write.

    A log write that never completes must not delay the answer — before this fix
    the route awaited it, so a slow second session held the request open.
    """
    started = asyncio.Event()
    release = asyncio.Event()

    async def _hang(**_kwargs):
        started.set()
        await release.wait()

    with patch("app.routes.events._log_search_query", new=_hang):
        try:
            resp = await client.get("/api/events/search?q=celtics")
            assert resp.status_code == 200, "response must not wait on the log write"
        finally:
            release.set()
            await _drain_search_log_tasks()
