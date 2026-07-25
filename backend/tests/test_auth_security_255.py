"""Security guard tests for Queue #255 Item 1 — residual auth-bypass closure.

Builds on Queue #252 (test_auth_security_252.py). #252 stopped a deleted
account's token from resurrecting the User on the Bearer-auth path
(``_resolve_user``). #255 closes the residual sign-in / user-creation paths:

  * ``verify_id_token(..., allow_session_token=False)`` must reject a
    backend-issued session token (it may only be honored on the read/Bearer
    path, never a create path).
  * ``POST /api/auth/google`` passes ``allow_session_token=False`` so an old
    backend session token from a since-deleted account can never re-create it.
  * ``/api/auth/google-access-token`` and ``/api/auth/apple`` use provider
    verifiers (Google userinfo / Apple JWKS), not ``verify_id_token`` — a backend
    session token can never enter their create paths either.

No real user is deleted and no production probe is performed here.
"""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

import firebase_admin.auth as fb_auth
from app.services import firebase_auth as fa
from app.services.database import get_db, get_db_rw
from app.dependencies.auth import get_optional_user


def _raise_not_firebase(_token):
    raise ValueError("not a firebase id token")


# ---------------------------------------------------------------------------
# Service layer: the allow_session_token flag
# ---------------------------------------------------------------------------

def test_verify_id_token_rejects_session_token_when_disallowed(monkeypatch):
    """A valid backend session token is honored on the default (Bearer) path
    but REJECTED when allow_session_token=False (the sign-in/create path)."""
    monkeypatch.setenv("ADMIN_SECRET", "test-admin-secret-255")
    # Firebase "configured", but the token is not a real Firebase ID token, so
    # auth.verify_id_token raises and we fall through to the session-token path.
    monkeypatch.setattr(fa, "_init_firebase", lambda: True)
    monkeypatch.setattr(fb_auth, "verify_id_token", _raise_not_firebase)

    session_token = fa.create_session_token(uid="deleted-uid-255", email="gone@example.com")
    assert session_token, "signing key should derive from ADMIN_SECRET"

    # Default path (Bearer / get_current_user) still accepts the fallback token.
    allowed = fa.verify_id_token(session_token, allow_session_token=True)
    assert allowed is not None
    assert allowed.get("uid") == "deleted-uid-255"

    # Create path rejects it — no claims, so no user is ever minted.
    denied = fa.verify_id_token(session_token, allow_session_token=False)
    assert denied is None


# ---------------------------------------------------------------------------
# Route layer: no sign-in entry recreates a deleted user's account
# ---------------------------------------------------------------------------

class _RecordingResult:
    def scalar_one_or_none(self):
        return None  # user row is gone (deleted account)

    def scalar_one(self):
        return None


class _RecordingDB:
    """Async DB stub that records writes so we can assert none happened."""

    def __init__(self):
        self.added = []
        self.flushed = False

    async def execute(self, *_a, **_k):
        return _RecordingResult()

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        self.flushed = True

    async def refresh(self, *_a, **_k):
        pass

    async def commit(self):
        pass

    async def delete(self, *_a, **_k):
        pass


@pytest.fixture
async def recording_client(monkeypatch):
    monkeypatch.setenv("BYPASS_RATE_LIMITS", "1")
    db = _RecordingDB()

    from app.main import app

    async def _mock_get_db():
        yield db

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
            yield ac, db

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_google_signin_rejects_deleted_users_session_token(recording_client, monkeypatch):
    """A deleted account's still-valid backend session token cannot re-create
    the User via /api/auth/google."""
    client, db = recording_client
    monkeypatch.setenv("ADMIN_SECRET", "test-admin-secret-255")
    monkeypatch.setattr(fa, "_init_firebase", lambda: True)
    monkeypatch.setattr(fb_auth, "verify_id_token", _raise_not_firebase)

    session_token = fa.create_session_token(uid="deleted-uid-255", email="gone@example.com")
    assert session_token

    resp = await client.post("/api/auth/google", json={"id_token": session_token})

    assert resp.status_code == 401
    assert db.added == []       # nothing created / resurrected
    assert db.flushed is False


@pytest.mark.asyncio
async def test_google_access_token_rejects_session_token(recording_client, monkeypatch):
    """A backend session token presented as a Google access_token is rejected by
    Google's userinfo endpoint (401) — no user is created."""
    client, db = recording_client
    monkeypatch.setenv("ADMIN_SECRET", "test-admin-secret-255")
    session_token = fa.create_session_token(uid="deleted-uid-255", email="gone@example.com")

    mock_response = MagicMock()
    mock_response.status_code = 401
    mock_response.json.return_value = {"error": "invalid_token"}

    async def _mock_get(*_a, **_k):
        return mock_response

    with patch("httpx.AsyncClient.get", side_effect=_mock_get):
        resp = await client.post(
            "/api/auth/google-access-token",
            json={"access_token": session_token},
        )

    assert resp.status_code == 401
    assert db.added == []


@pytest.mark.asyncio
async def test_apple_signin_rejects_session_token(recording_client, monkeypatch):
    """A backend session token presented as an Apple id_token fails Apple JWKS
    verification — no user is created. The apple route never calls
    verify_id_token, so a backend token can't enter its create path."""
    client, db = recording_client
    monkeypatch.setenv("APPLE_SERVICES_ID", "com.bainluck.web")
    monkeypatch.setenv("ADMIN_SECRET", "test-admin-secret-255")
    session_token = fa.create_session_token(uid="deleted-uid-255", email="gone@example.com")

    # Real Apple verification would reject a non-Apple JWT; simulate that verdict
    # without a network call to Apple's JWKS.
    monkeypatch.setattr("app.routes.auth.verify_apple_id_token", lambda token, audiences: None)

    resp = await client.post("/api/auth/apple", json={"id_token": session_token})

    assert resp.status_code == 401
    assert db.added == []
