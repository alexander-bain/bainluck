"""#10825: the related-futures series lookup carries only the OR-group patterns
that can decide a match.

Pass 3 of `_build_related_futures` ANDs each team's `name ILIKE` OR group with a
series detector. `'%Boston Celtics%'` beside `'%Boston%'` can never admit a row
the shorter one does not, and long patterns are the costly trigram probes
(production, 15324058's shape: 4,553 ms → 163 ms, same 0 rows). The equivalence
property itself is pinned in tests/test_game_markets_or_group_minimal_10820.py;
this pins that the series statement the route executes uses the minimal groups.
"""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects import postgresql

from app.dependencies.auth import get_optional_user
from app.services.database import get_db, get_db_rw
from tests.integration.test_route_related_futures import (
    _make_event,
    _make_related_futures_session,
)

pytestmark = pytest.mark.anyio


@pytest.fixture(autouse=True)
def _clear_memo():
    # An earlier test's body for the same id would answer from memory and the
    # series pass would never run (the strawman below catches exactly that).
    from app.routes import events as events_route

    events_route._related_futures_cache.clear()
    events_route._STALE_REFRESH_INFLIGHT.clear()
    yield
    events_route._related_futures_cache.clear()
    events_route._STALE_REFRESH_INFLIGHT.clear()


def _ilike_params(stmt):
    params = stmt.compile(dialect=postgresql.dialect()).params
    return sorted(v for v in params.values() if isinstance(v, str) and v.startswith("%"))


async def test_the_series_lookup_carries_only_the_minimal_groups(monkeypatch):
    monkeypatch.setenv("BYPASS_RATE_LIMITS", "1")
    from app.main import app

    event = _make_event(
        id=10825, home_team="Boston Celtics", away_team="Philadelphia 76ers",
        status="scheduled",
    )
    session = _make_related_futures_session(event)
    inner = session.execute.side_effect
    series: list[list[str]] = []

    async def recording(stmt, *a, **k):
        params = _ilike_params(stmt) if hasattr(stmt, "compile") else []
        if "%series%" in params:
            series.append(params)
        return await inner(stmt, *a, **k)

    session.execute = AsyncMock(side_effect=recording)

    async def _db():
        yield session

    async def _user():
        return None

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_db_rw] = _db
    app.dependency_overrides[get_optional_user] = _user
    try:
        with (
            patch("app.main.init_db", new_callable=AsyncMock),
            patch(
                "app.services.llm.generate_related_futures_summary",
                return_value="",
            ),
            patch(
                "app.services.league_context.enrich_event_with_context",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as ac:
                resp = await ac.get("/api/events/10825/related-futures")
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200, resp.text
    # Strawman: the series pass ran, or the assertion below says nothing.
    assert len(series) == 1, series
    assert series[0] == sorted(
        ["%series%", "%Celtics%", "%Boston%", "%76ers%", "%Philadelphia%"]
    ), series[0]
