"""Contract tests for Notifications API: /api/notifications/*

Tests device token registration, admin token listing, and admin send-test
endpoints. Admin endpoints require valid secret; registration is public.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest


# ============================================================================
# Helpers
# ============================================================================

def _make_device_token(
    id: int = 1,
    platform: str = "ios",
    user_id: int | None = None,
    session_id: str | None = "sess-001",
    device_token: str = "abc123def456ghi789jkl012",
):
    tok = MagicMock()
    tok.id = id
    tok.platform = platform
    tok.user_id = user_id
    tok.session_id = session_id
    tok.device_token = device_token
    tok.is_active = True
    tok.created_at = datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc)
    tok.updated_at = datetime(2026, 5, 18, 12, 0, tzinfo=timezone.utc)
    return tok


# ============================================================================
# POST /api/notifications/register — device token registration
# ============================================================================


class TestNotificationRegister:
    """POST /api/notifications/register — upsert device token."""

    async def test_returns_200_with_valid_body(self, client, mock_db):
        resp = await client.post(
            "/api/notifications/register",
            json={
                "device_token": "abc123def456",
                "platform": "ios",
                "session_id": "sess-001",
            },
        )
        assert resp.status_code == 200

    async def test_response_has_status_ok(self, client, mock_db):
        resp = await client.post(
            "/api/notifications/register",
            json={
                "device_token": "abc123def456",
                "platform": "ios",
            },
        )
        body = resp.json()
        assert body == {"status": "ok"}

    async def test_accepts_user_id(self, client, mock_db):
        resp = await client.post(
            "/api/notifications/register",
            json={
                "device_token": "xyz789",
                "platform": "macos",
                "user_id": "42",
            },
        )
        assert resp.status_code == 200

    async def test_missing_device_token_returns_422(self, client):
        resp = await client.post(
            "/api/notifications/register",
            json={"platform": "ios"},
        )
        assert resp.status_code == 422

    async def test_missing_platform_returns_422(self, client):
        resp = await client.post(
            "/api/notifications/register",
            json={"device_token": "abc123"},
        )
        assert resp.status_code == 422

    async def test_rejects_get(self, client):
        resp = await client.get("/api/notifications/register")
        assert resp.status_code == 405

    async def test_commits_after_upsert(self, client, mock_db):
        """Registration should call commit on success."""
        resp = await client.post(
            "/api/notifications/register",
            json={
                "device_token": "abc123def456",
                "platform": "ios",
            },
        )
        assert resp.status_code == 200
        assert mock_db.commit.called

    async def test_session_header_fallback(self, client, mock_db):
        """When session_id not in body, x-session-id header is used."""
        resp = await client.post(
            "/api/notifications/register",
            headers={"x-session-id": "header-session-456"},
            json={
                "device_token": "abc123def456ghi789",
                "platform": "ios",
            },
        )
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

    async def test_empty_body_returns_422(self, client):
        """Empty JSON body should be rejected."""
        resp = await client.post("/api/notifications/register", json={})
        assert resp.status_code == 422


# ============================================================================
# GET /api/notifications/admin/tokens — list device tokens (admin)
# ============================================================================


class TestNotificationAdminTokens:
    """GET /api/notifications/admin/tokens — requires admin secret."""

    async def test_rejects_bad_secret(self, client):
        resp = await client.get("/api/notifications/admin/tokens?secret=bad")
        assert resp.status_code == 403

    async def test_rejects_missing_secret(self, client):
        resp = await client.get("/api/notifications/admin/tokens")
        assert resp.status_code == 422

    async def test_403_body_has_detail(self, client):
        resp = await client.get("/api/notifications/admin/tokens?secret=wrong")
        body = resp.json()
        assert "detail" in body
        assert body["detail"] in ("Invalid admin secret", "Admin auth not configured")

    async def test_success_returns_count_and_tokens(self, client, mock_db, monkeypatch):
        """Valid admin secret returns response with count and tokens list."""
        monkeypatch.setenv("ADMIN_TOKEN", "test-secret")

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        resp = await client.get("/api/notifications/admin/tokens?secret=test-secret")
        assert resp.status_code == 200
        body = resp.json()
        assert "count" in body
        assert "tokens" in body
        assert body["count"] == 0
        assert isinstance(body["tokens"], list)

    async def test_token_response_shape(self, client, mock_db, monkeypatch):
        """Each token in the list should have the expected fields."""
        monkeypatch.setenv("ADMIN_TOKEN", "test-secret")

        token = _make_device_token()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [token]
        mock_db.execute.return_value = mock_result

        resp = await client.get("/api/notifications/admin/tokens?secret=test-secret")
        assert resp.status_code == 200
        body = resp.json()
        assert body["count"] == 1
        assert len(body["tokens"]) == 1

        tok = body["tokens"][0]
        expected_keys = {"id", "platform", "user_id", "session_id",
                         "token_prefix", "token_suffix", "created_at", "updated_at"}
        assert set(tok.keys()) == expected_keys
        assert tok["platform"] == "ios"
        assert tok["token_prefix"] == "abc123de"  # first 8 chars
        assert tok["token_suffix"] == "l012"  # last 4 chars


# ============================================================================
# POST /api/notifications/admin/send-test — send test notification (admin)
# ============================================================================


class TestNotificationAdminSendTest:
    """POST /api/notifications/admin/send-test — requires admin secret."""

    async def test_rejects_bad_secret(self, client):
        resp = await client.post(
            "/api/notifications/admin/send-test?secret=bad",
            json={"device_token": "abc123"},
        )
        assert resp.status_code == 403

    async def test_rejects_missing_secret(self, client):
        resp = await client.post(
            "/api/notifications/admin/send-test",
            json={"device_token": "abc123"},
        )
        assert resp.status_code == 422

    async def test_rejects_get(self, client):
        resp = await client.get("/api/notifications/admin/send-test?secret=bad")
        assert resp.status_code == 405

    async def test_missing_body_returns_422(self, client):
        resp = await client.post("/api/notifications/admin/send-test?secret=bad")
        assert resp.status_code == 422

    async def test_missing_device_token_returns_422(self, client, monkeypatch):
        """Body without device_token should fail validation."""
        monkeypatch.setenv("ADMIN_TOKEN", "test-secret")
        resp = await client.post(
            "/api/notifications/admin/send-test?secret=test-secret",
            json={},
        )
        assert resp.status_code == 422
