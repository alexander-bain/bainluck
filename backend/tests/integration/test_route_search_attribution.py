"""Queue #243 Item 2: signed-in search attribution.

`request.state.user_id` is never set for the public /search route, so the
SearchQueryLog user_id was always NULL. The optional-auth dependency now
attributes signed-in searches. These tests assert both directions: an
authenticated user attributes; an anonymous search stays NULL (and still works).
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.dependencies.auth import get_optional_user


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
            assert mock_log.await_count == 1
            # _log_search_query(query, result_count, top_result_id, user_id, session_id)
            args = mock_log.await_args.args
            assert args[3] == 4242
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
        assert mock_log.await_count == 1
        assert mock_log.await_args.args[3] is None
