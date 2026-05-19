"""Contract tests for Challenge endpoints: /api/challenges/*

Tests create challenge, get challenge, and accept challenge.
The challenges route uses its own async context manager for DB sessions
(get_session from app.services), not the DI-based get_db.
"""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.dependencies.auth import get_optional_user
from app.services.database import get_db


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _MockResult:
    """Mock SQLAlchemy result supporting first()/scalar()/scalars()."""

    def __init__(self, first_value=None, scalar_value=None, scalars_all=None):
        self._first = first_value
        self._scalar = scalar_value
        self._scalars_all = scalars_all or []

    def first(self):
        return self._first

    def scalar(self):
        return self._scalar

    def scalar_one_or_none(self):
        return self._scalar

    def scalars(self):
        parent = self

        class _Scalars:
            def all(self):
                return parent._scalars_all

            def first(self):
                return parent._scalars_all[0] if parent._scalars_all else None

        return _Scalars()

    def all(self):
        return self._scalars_all


class _MockSession:
    """Mock async DB session used by challenges route context manager."""

    def __init__(self, results=None):
        self._results = list(results or [])
        self.added = []
        self.committed = False

    async def execute(self, statement):
        if self._results:
            return self._results.pop(0)
        return _MockResult()

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.committed = True

    async def refresh(self, obj):
        if not hasattr(obj, "id") or obj.id is None:
            obj.id = 1


class _SessionContext:
    """Mock async context manager wrapping _MockSession."""

    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, exc, tb):
        return False


def _make_challenge(
    id: int = 1,
    challenge_code: str = "BL-abc123",
    market_id: int = 42,
    market_name: str = "Will the Fed cut rates?",
    creator_guess: str = "higher",
    creator_threshold: int = 55,
    friend_guess: str | None = None,
    creator_correct: bool | None = None,
    friend_correct: bool | None = None,
    actual_probability: float | None = None,
    resolved_at=None,
):
    ch = MagicMock()
    ch.id = id
    ch.challenge_code = challenge_code
    ch.market_id = market_id
    ch.market_name = market_name
    ch.creator_guess = creator_guess
    ch.creator_threshold = creator_threshold
    ch.friend_guess = friend_guess
    ch.creator_correct = creator_correct
    ch.friend_correct = friend_correct
    ch.actual_probability = actual_probability
    ch.resolved_at = resolved_at
    ch.created_at = datetime(2026, 5, 18, 10, 0, tzinfo=timezone.utc)
    ch.friend_session_id = None
    return ch


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_db():
    session = AsyncMock()
    session.execute.return_value = _MockResult()
    return session


@pytest.fixture
async def client(mock_db, monkeypatch):
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


# ===========================================================================
# POST /api/challenges — create a challenge
# ===========================================================================

@pytest.mark.asyncio
async def test_create_challenge_requires_body(client):
    """POST /api/challenges should reject empty body."""
    resp = await client.post("/api/challenges", json={})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_challenge_requires_all_fields(client):
    """POST /api/challenges should require market_id, guess, threshold."""
    resp = await client.post(
        "/api/challenges",
        json={"market_id": 1},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_challenge_rejects_invalid_guess(client, monkeypatch):
    """POST /api/challenges should reject guess values other than higher/lower."""
    session = _MockSession([
        _MockResult(first_value=SimpleNamespace(id=42, name="Test Market")),
    ])
    monkeypatch.setattr("app.routes.challenges.get_session", lambda: _SessionContext(session))

    resp = await client.post(
        "/api/challenges",
        json={"market_id": 42, "guess": "invalid", "threshold": 50},
    )
    assert resp.status_code == 400
    assert "higher" in resp.json()["detail"] or "lower" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_create_challenge_market_not_found(client, monkeypatch):
    """POST /api/challenges should return 404 when market doesn't exist."""
    session = _MockSession([
        _MockResult(first_value=None),  # market lookup returns nothing
    ])
    monkeypatch.setattr("app.routes.challenges.get_session", lambda: _SessionContext(session))

    resp = await client.post(
        "/api/challenges",
        json={"market_id": 999, "guess": "higher", "threshold": 50},
    )
    assert resp.status_code == 404
    assert "Market not found" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_create_challenge_success(client, monkeypatch):
    """Successful challenge creation returns code, URL, and details."""
    session = _MockSession([
        # Market lookup
        _MockResult(first_value=SimpleNamespace(id=42, name="Will Fed cut rates?")),
        # Code collision check (no collision)
        _MockResult(scalar_value=None),
    ])
    monkeypatch.setattr("app.routes.challenges.get_session", lambda: _SessionContext(session))

    resp = await client.post(
        "/api/challenges",
        json={"market_id": 42, "guess": "higher", "threshold": 55},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert "challenge_code" in body
    assert body["challenge_code"].startswith("BL-")
    assert "url" in body
    assert "bainluck.com/challenge/" in body["url"]
    assert body["market_name"] == "Will Fed cut rates?"
    assert body["creator_guess"] == "higher"
    assert body["threshold"] == 55


# ===========================================================================
# GET /api/challenges/{code} — get challenge details
# ===========================================================================

@pytest.mark.asyncio
async def test_get_challenge_not_found(client, monkeypatch):
    """GET /api/challenges/{code} should return 404 for unknown code."""
    session = _MockSession([
        _MockResult(scalar_value=None),
    ])
    monkeypatch.setattr("app.routes.challenges.get_session", lambda: _SessionContext(session))

    resp = await client.get("/api/challenges/BL-nonexistent")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_challenge_success(client, monkeypatch):
    """GET /api/challenges/{code} returns full challenge shape."""
    challenge = _make_challenge()
    session = _MockSession([
        _MockResult(scalar_value=challenge),
        _MockResult(scalar_value=0.62),  # current probability
    ])
    monkeypatch.setattr("app.routes.challenges.get_session", lambda: _SessionContext(session))

    resp = await client.get("/api/challenges/BL-abc123")
    assert resp.status_code == 200
    body = resp.json()

    expected_keys = {
        "challenge_code", "market_name", "market_id",
        "creator_guess", "threshold", "friend_guess",
        "current_probability", "creator_correct", "friend_correct",
        "resolved_at", "created_at",
    }
    assert set(body.keys()) == expected_keys
    assert body["challenge_code"] == "BL-abc123"
    assert body["market_name"] == "Will the Fed cut rates?"
    assert body["market_id"] == 42
    assert body["creator_guess"] == "higher"
    assert body["threshold"] == 55
    assert body["current_probability"] == 0.62


@pytest.mark.asyncio
async def test_get_challenge_null_probability(client, monkeypatch):
    """Challenge with no outcome probability should return null."""
    challenge = _make_challenge()
    session = _MockSession([
        _MockResult(scalar_value=challenge),
        _MockResult(scalar_value=None),  # no outcomes
    ])
    monkeypatch.setattr("app.routes.challenges.get_session", lambda: _SessionContext(session))

    resp = await client.get("/api/challenges/BL-abc123")
    assert resp.status_code == 200
    assert resp.json()["current_probability"] is None


# ===========================================================================
# POST /api/challenges/{code}/accept — friend accepts
# ===========================================================================

@pytest.mark.asyncio
async def test_accept_challenge_requires_body(client, monkeypatch):
    """POST /api/challenges/{code}/accept should require body."""
    resp = await client.post("/api/challenges/BL-abc123/accept", json={})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_accept_challenge_rejects_invalid_guess(client, monkeypatch):
    """POST /api/challenges/{code}/accept should reject invalid guess."""
    challenge = _make_challenge()
    session = _MockSession([
        _MockResult(scalar_value=challenge),
    ])
    monkeypatch.setattr("app.routes.challenges.get_session", lambda: _SessionContext(session))

    resp = await client.post(
        "/api/challenges/BL-abc123/accept",
        json={"guess": "sideways"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_accept_challenge_not_found(client, monkeypatch):
    """Accepting nonexistent challenge returns 404."""
    session = _MockSession([
        _MockResult(scalar_value=None),
    ])
    monkeypatch.setattr("app.routes.challenges.get_session", lambda: _SessionContext(session))

    resp = await client.post(
        "/api/challenges/BL-nonexistent/accept",
        json={"guess": "lower"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_accept_challenge_already_accepted(client, monkeypatch):
    """Accepting an already-accepted challenge returns 409."""
    challenge = _make_challenge(friend_guess="lower")  # already accepted
    session = _MockSession([
        _MockResult(scalar_value=challenge),
    ])
    monkeypatch.setattr("app.routes.challenges.get_session", lambda: _SessionContext(session))

    resp = await client.post(
        "/api/challenges/BL-abc123/accept",
        json={"guess": "higher"},
    )
    assert resp.status_code == 409
    assert "already accepted" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_accept_challenge_success(client, monkeypatch):
    """Successful accept returns status and evaluation."""
    challenge = _make_challenge()
    session = _MockSession([
        _MockResult(scalar_value=challenge),
        _MockResult(scalar_value=0.62),  # current probability
    ])
    monkeypatch.setattr("app.routes.challenges.get_session", lambda: _SessionContext(session))

    resp = await client.post(
        "/api/challenges/BL-abc123/accept",
        json={"guess": "lower"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "accepted"
    assert body["challenge_code"] == "BL-abc123"
    assert body["friend_guess"] == "lower"
    assert "actual_probability" in body
    assert "creator_correct" in body
    assert "friend_correct" in body
