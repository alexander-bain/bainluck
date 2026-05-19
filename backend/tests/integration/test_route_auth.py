"""Contract tests for auth endpoints: /api/auth/*

Tests status, Google sign-in, Google access-token exchange, Apple sign-in,
GET /me, PATCH /me, DELETE /me.
"""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.dependencies.auth import get_current_user, get_optional_user
from app.services.database import get_db


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user(
    id: int = 1,
    firebase_uid: str = "fb-uid-123",
    email: str = "test@example.com",
    display_name: str = "Test User",
    photo_url: str = "https://example.com/photo.jpg",
    onboarding_completed: bool = False,
):
    user = MagicMock()
    user.id = id
    user.firebase_uid = firebase_uid
    user.email = email
    user.display_name = display_name
    user.photo_url = photo_url
    user.created_at = datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)
    user.onboarding_completed = onboarding_completed
    prefs = MagicMock()
    prefs.onboarding_completed = onboarding_completed
    user.preferences = prefs
    return user


def _make_mock_result(scalar_one_or_none_value=None, scalar_one_value=None):
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    result.scalars.return_value.first.return_value = None
    result.scalar_one_or_none.return_value = scalar_one_or_none_value
    result.scalar_one.return_value = scalar_one_value
    result.scalar.return_value = None
    result.fetchall.return_value = []
    result.all.return_value = []
    result.first.return_value = None
    return result


@pytest.fixture
def mock_db():
    session = AsyncMock()
    session.execute.return_value = _make_mock_result()
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
# GET /api/auth/status
# ===========================================================================

@pytest.mark.asyncio
async def test_auth_status_returns_providers_list(client, monkeypatch):
    """Auth status should return configured providers."""
    monkeypatch.setattr("app.routes.auth.is_configured", lambda: True)
    monkeypatch.setenv("APPLE_SERVICES_ID", "com.bainluck.web")

    resp = await client.get("/api/auth/status")

    assert resp.status_code == 200
    body = resp.json()
    assert "auth_configured" in body
    assert "providers" in body
    assert body["auth_configured"] is True
    assert "google" in body["providers"]
    assert "apple" in body["providers"]


@pytest.mark.asyncio
async def test_auth_status_unconfigured(client, monkeypatch):
    """Auth status should reflect unconfigured state."""
    monkeypatch.setattr("app.routes.auth.is_configured", lambda: False)
    monkeypatch.delenv("APPLE_SERVICES_ID", raising=False)

    resp = await client.get("/api/auth/status")

    assert resp.status_code == 200
    body = resp.json()
    assert body["auth_configured"] is False
    assert body["providers"] == []


# ===========================================================================
# POST /api/auth/google — Firebase ID token sign-in
# ===========================================================================

@pytest.mark.asyncio
async def test_google_sign_in_requires_id_token(client):
    """Google sign-in should reject requests without id_token."""
    resp = await client.post("/api/auth/google", json={})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_google_sign_in_rejects_invalid_token(client, monkeypatch):
    """Google sign-in should return 401 for an invalid token."""
    monkeypatch.setattr("app.routes.auth.verify_id_token", lambda token: None)

    resp = await client.post("/api/auth/google", json={"id_token": "bad-token"})

    assert resp.status_code == 401
    assert "Invalid or expired" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_google_sign_in_rejects_token_without_uid(client, monkeypatch):
    """Google sign-in should return 400 when token has no uid."""
    monkeypatch.setattr(
        "app.routes.auth.verify_id_token",
        lambda token: {"email": "test@example.com"},  # no uid
    )

    resp = await client.post("/api/auth/google", json={"id_token": "no-uid-token"})

    assert resp.status_code == 400
    assert "missing uid" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_google_sign_in_existing_user(client, mock_db, monkeypatch):
    """Google sign-in for existing user returns profile shape."""
    user = _make_user()
    monkeypatch.setattr(
        "app.routes.auth.verify_id_token",
        lambda token: {"uid": "fb-uid-123", "email": "test@example.com", "name": "Test User", "picture": "https://example.com/photo.jpg"},
    )
    mock_db.execute.return_value = _make_mock_result(scalar_one_or_none_value=user)

    resp = await client.post("/api/auth/google", json={"id_token": "valid-token"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == 1
    assert body["email"] == "test@example.com"
    assert body["display_name"] == "Test User"
    assert "onboarding_completed" in body
    assert "created_at" in body


@pytest.mark.asyncio
async def test_google_sign_in_new_user(client, mock_db, monkeypatch):
    """Google sign-in for new user calls add and flush to create user."""
    monkeypatch.setattr(
        "app.routes.auth.verify_id_token",
        lambda token: {"uid": "new-uid-456", "email": "new@example.com", "name": "New User", "picture": None},
    )
    # First execute returns None (user not found), triggering creation
    mock_db.execute.return_value = _make_mock_result(scalar_one_or_none_value=None)

    # The route creates a real User ORM instance, then calls flush and refresh.
    # After refresh, the route reads user.id and user.created_at. We patch refresh
    # to set these required fields on the newly-created model object.
    mock_db.flush = AsyncMock()

    async def _set_user_fields(obj):
        if hasattr(obj, "firebase_uid"):
            obj.id = 2
            obj.created_at = datetime(2026, 5, 18, tzinfo=timezone.utc)

    mock_db.refresh = AsyncMock(side_effect=_set_user_fields)

    # db.add is synchronous — use regular MagicMock (AsyncMock's sync call
    # returns a coroutine that triggers RuntimeWarning if not awaited)
    mock_db.add = MagicMock()

    resp = await client.post("/api/auth/google", json={"id_token": "valid-new-token"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == 2
    assert body["email"] == "new@example.com"
    assert body["display_name"] == "New User"
    assert body["onboarding_completed"] is False
    assert mock_db.add.called


# ===========================================================================
# POST /api/auth/google-access-token — Safari ITP fallback
# ===========================================================================

@pytest.mark.asyncio
async def test_google_access_token_requires_access_token(client):
    """Access token exchange should reject requests without access_token."""
    resp = await client.post("/api/auth/google-access-token", json={})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_google_access_token_rejects_invalid_token(client, monkeypatch):
    """Access token exchange should return 401 for invalid Google token."""
    import httpx

    mock_response = MagicMock()
    mock_response.status_code = 401
    mock_response.json.return_value = {"error": "invalid_token"}

    async def _mock_get(*args, **kwargs):
        return mock_response

    with patch("httpx.AsyncClient.get", side_effect=_mock_get):
        resp = await client.post(
            "/api/auth/google-access-token",
            json={"access_token": "bad-token"},
        )

    assert resp.status_code == 401
    assert "Invalid Google access token" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_google_access_token_rejects_missing_email(client, monkeypatch):
    """Access token exchange should return 400 when Google response has no email."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"name": "Test", "sub": "123"}  # no email

    async def _mock_get(*args, **kwargs):
        return mock_response

    with patch("httpx.AsyncClient.get", side_effect=_mock_get):
        resp = await client.post(
            "/api/auth/google-access-token",
            json={"access_token": "no-email-token"},
        )

    assert resp.status_code == 400
    assert "missing email" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_google_access_token_success(client, mock_db, monkeypatch):
    """Successful access-token exchange returns custom_token and user shape."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "email": "test@example.com",
        "name": "Test User",
        "picture": "https://example.com/photo.jpg",
    }

    async def _mock_get(*args, **kwargs):
        return mock_response

    user = _make_user()
    mock_db.execute.return_value = _make_mock_result(scalar_one_or_none_value=user)

    monkeypatch.setattr(
        "app.routes.auth.get_or_create_firebase_user",
        lambda email, name, pic: "fb-uid-123",
    )
    monkeypatch.setattr(
        "app.routes.auth.create_custom_token",
        lambda uid: "mock-custom-token",
    )
    monkeypatch.setattr(
        "app.services.firebase_auth.create_session_token",
        lambda uid, email=None, name=None, picture=None: "mock-session-token",
    )

    with patch("httpx.AsyncClient.get", side_effect=_mock_get):
        resp = await client.post(
            "/api/auth/google-access-token",
            json={"access_token": "valid-token"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert "custom_token" in body
    assert body["custom_token"] == "mock-custom-token"
    assert "id_token" in body
    assert "uid" in body
    assert "email" in body
    assert "user" in body
    assert body["user"]["id"] == 1
    assert body["expires_in"] == 2592000


# ===========================================================================
# POST /api/auth/apple — Apple Sign-In
# ===========================================================================

@pytest.mark.asyncio
async def test_apple_sign_in_requires_id_token(client):
    """Apple sign-in should reject requests without id_token."""
    resp = await client.post("/api/auth/apple", json={})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_apple_sign_in_not_configured(client, monkeypatch):
    """Apple sign-in should return 501 when not configured."""
    monkeypatch.delenv("APPLE_SERVICES_ID", raising=False)

    resp = await client.post("/api/auth/apple", json={"id_token": "apple-token"})

    assert resp.status_code == 501
    assert "not configured" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_apple_sign_in_rejects_invalid_token(client, monkeypatch):
    """Apple sign-in should return 401 for invalid Apple JWT."""
    monkeypatch.setenv("APPLE_SERVICES_ID", "com.bainluck.web")
    monkeypatch.setattr("app.routes.auth.verify_apple_id_token", lambda token, audiences: None)

    resp = await client.post("/api/auth/apple", json={"id_token": "bad-apple-token"})

    assert resp.status_code == 401
    assert "Invalid or expired" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_apple_sign_in_rejects_missing_email(client, monkeypatch):
    """Apple sign-in should return 400 when Apple JWT has no email."""
    monkeypatch.setenv("APPLE_SERVICES_ID", "com.bainluck.web")
    monkeypatch.setattr(
        "app.routes.auth.verify_apple_id_token",
        lambda token, audiences: {"sub": "apple-sub-123"},  # no email
    )

    resp = await client.post("/api/auth/apple", json={"id_token": "no-email-token"})

    assert resp.status_code == 400
    assert "missing email" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_apple_sign_in_success(client, mock_db, monkeypatch):
    """Successful Apple sign-in returns custom_token, session token, and user."""
    monkeypatch.setenv("APPLE_SERVICES_ID", "com.bainluck.web")
    monkeypatch.setattr(
        "app.routes.auth.verify_apple_id_token",
        lambda token, audiences: {"sub": "apple-sub-123", "email": "apple@example.com"},
    )
    monkeypatch.setattr(
        "app.routes.auth.get_or_create_firebase_user",
        lambda email, name, pic: "fb-uid-apple",
    )
    monkeypatch.setattr(
        "app.routes.auth.create_custom_token",
        lambda uid: "mock-apple-custom-token",
    )
    monkeypatch.setattr(
        "app.services.firebase_auth.create_session_token",
        lambda uid, email=None, name=None, picture=None: "mock-apple-session-token",
    )

    user = _make_user(firebase_uid="fb-uid-apple", email="apple@example.com")
    mock_db.execute.return_value = _make_mock_result(scalar_one_or_none_value=user)

    resp = await client.post(
        "/api/auth/apple",
        json={"id_token": "valid-apple-token", "first_name": "Jane", "last_name": "Doe"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["custom_token"] == "mock-apple-custom-token"
    assert body["id_token"] == "mock-apple-session-token"
    assert body["email"] == "apple@example.com"
    assert body["name"] == "Jane Doe"
    assert body["picture"] is None  # Apple doesn't provide photos
    assert "user" in body
    assert body["user"]["id"] == 1
    assert body["expires_in"] == 2592000


# ===========================================================================
# GET /api/auth/me — requires auth
# ===========================================================================

@pytest.mark.asyncio
async def test_get_me_unauthenticated(client):
    """GET /me should return 401 without authentication."""
    from app.main import app

    # Override get_current_user to raise 401 (real behavior when no token)
    async def _mock_no_user():
        from fastapi import HTTPException, status
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    app.dependency_overrides[get_current_user] = _mock_no_user
    try:
        resp = await client.get("/api/auth/me")
        assert resp.status_code == 401
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_get_me_authenticated(client, mock_db):
    """GET /me should return user profile for authenticated user."""
    from app.main import app

    user = _make_user()

    async def _mock_current_user():
        return user

    # When get_profile re-fetches the user, return the same user
    mock_db.execute.return_value = _make_mock_result(scalar_one_value=user)

    app.dependency_overrides[get_current_user] = _mock_current_user
    try:
        resp = await client.get("/api/auth/me")
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == 1
        assert body["email"] == "test@example.com"
        assert body["display_name"] == "Test User"
        assert "onboarding_completed" in body
        assert "created_at" in body
    finally:
        app.dependency_overrides.pop(get_current_user, None)


# ===========================================================================
# PATCH /api/auth/me — profile update
# ===========================================================================

@pytest.mark.asyncio
async def test_patch_me_unauthenticated(client):
    """PATCH /me should return 401 without authentication."""
    from app.main import app

    async def _mock_no_user():
        from fastapi import HTTPException, status
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")

    app.dependency_overrides[get_current_user] = _mock_no_user
    try:
        resp = await client.patch("/api/auth/me", json={"display_name": "New Name"})
        assert resp.status_code == 401
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_patch_me_updates_display_name(client, mock_db):
    """PATCH /me should update display_name and return updated profile."""
    from app.main import app

    user = _make_user()

    async def _mock_current_user():
        return user

    # After update, re-fetch returns user with updated name
    updated_user = _make_user(display_name="Updated Name")
    mock_db.execute.return_value = _make_mock_result(scalar_one_value=updated_user)

    app.dependency_overrides[get_current_user] = _mock_current_user
    try:
        resp = await client.patch("/api/auth/me", json={"display_name": "Updated Name"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["display_name"] == "Updated Name"
        assert "id" in body
        assert "email" in body
    finally:
        app.dependency_overrides.pop(get_current_user, None)


# ===========================================================================
# DELETE /api/auth/me — account deletion
# ===========================================================================

@pytest.mark.asyncio
async def test_delete_me_unauthenticated(client):
    """DELETE /me should return 401 without authentication."""
    from app.main import app

    async def _mock_no_user():
        from fastapi import HTTPException, status
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")

    app.dependency_overrides[get_current_user] = _mock_no_user
    try:
        resp = await client.delete("/api/auth/me")
        assert resp.status_code == 401
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_delete_me_authenticated(client, mock_db):
    """DELETE /me should delete user and return status."""
    from app.main import app

    user = _make_user()

    async def _mock_current_user():
        return user

    app.dependency_overrides[get_current_user] = _mock_current_user
    try:
        resp = await client.delete("/api/auth/me")
        assert resp.status_code == 200
        assert resp.json() == {"status": "deleted"}
        mock_db.delete.assert_called_once_with(user)
    finally:
        app.dependency_overrides.pop(get_current_user, None)
