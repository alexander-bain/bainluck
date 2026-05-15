"""Integration test fixtures for API contract tests.

Provides a mock async DB session and httpx test client that can hit
the real FastAPI routes without connecting to PostgreSQL.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.dependencies.auth import get_optional_user
from app.services.database import get_db


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
    app.dependency_overrides[get_optional_user] = _mock_get_optional_user

    with patch("app.main.init_db", new_callable=AsyncMock):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as ac:
            yield ac

    app.dependency_overrides.clear()
