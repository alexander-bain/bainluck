"""Integration test fixtures for API contract tests.

Provides a mock async DB session and httpx test client that can hit
the real FastAPI routes without connecting to PostgreSQL.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.dependencies.auth import get_optional_user
from app.services.database import get_db, get_db_rw


@pytest.fixture(autouse=True)
def _bypass_rate_limits(monkeypatch):
    """Turn the rate limiter off for EVERY integration test, not just the ones
    whose fixture remembered to.

    Found by UX-P072 (#1829), and the way it was found is the point. The suite
    was sitting exactly at the limiter's `60 per 1 minute`. Adding ONE ordinary
    test — one more GET, in a different file, against a different fixture —
    tipped it, and the red landed on

        test_route_feed_seeded.py::test_futures_item_nested_fields_are_stable
        KeyError: 'items'

    an unrelated FUTURES test, with no mention of a rate limit anywhere. The
    actual response was `429 {"detail": "Rate limit exceeded: 60 per 1 minute"}`
    and the test read the error body as data (gotcha #53: an error body is a
    response shape, not an absence). Baseline was green, so the natural reading
    was "the blend change broke the feed" — a whole cycle's diagnosis pointed at
    the wrong file by a counter nobody knew was full.

    `BYPASS_RATE_LIMITS` was already being set — but only inside the `client`
    fixture in this file, so `seeded_client` and `event_detail_client`, which
    are defined in their own test modules, never got it. Autouse is what makes
    that class of miss impossible: a new fixture cannot forget to opt in.
    """
    monkeypatch.setenv("BYPASS_RATE_LIMITS", "1")


def _make_mock_result():
    """Create a mock SQLAlchemy Result that returns empty data."""
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    result.scalars.return_value.first.return_value = None
    result.scalar_one_or_none.return_value = None
    result.scalar.return_value = None
    result.fetchall.return_value = []
    result.all.return_value = []
    result.first.return_value = None
    return result


@pytest.fixture
def mock_db():
    """AsyncMock DB session where every query returns empty results."""
    session = AsyncMock()
    session.execute.return_value = _make_mock_result()
    return session


@pytest.fixture
async def client(mock_db, monkeypatch):
    """httpx AsyncClient wired to the FastAPI app with mocked dependencies."""
    monkeypatch.setenv("BYPASS_RATE_LIMITS", "1")

    from app.main import app

    async def _mock_get_db():
        yield mock_db

    async def _mock_get_optional_user():
        return None

    app.dependency_overrides[get_db] = _mock_get_db
    app.dependency_overrides[get_db_rw] = _mock_get_db
    app.dependency_overrides[get_optional_user] = _mock_get_optional_user

    with patch("app.main.init_db", new_callable=AsyncMock):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as ac:
            yield ac

    app.dependency_overrides.clear()
