"""Focused route contract tests for notification endpoints."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.dialects.postgresql import dialect as postgresql_dialect

from app.routes import notifications
from app.services.database import get_db_rw


def _client_with_db(db=None) -> TestClient:
    app = FastAPI()
    app.include_router(notifications.router)

    if db is not None:
        async def _override_get_db():
            return db

        app.dependency_overrides[notifications.get_db] = _override_get_db
        app.dependency_overrides[get_db_rw] = _override_get_db

    return TestClient(app)


def _compiled_params(statement):
    return statement.compile(dialect=postgresql_dialect()).params


class _CaptureDB:
    def __init__(self):
        self.execute = AsyncMock()
        self.commit = AsyncMock()


def test_register_device_token_upserts_with_body_session_and_numeric_user():
    db = _CaptureDB()
    client = _client_with_db(db)

    response = client.post(
        "/api/notifications/register",
        json={
            "device_token": "abcdef1234567890",
            "platform": "ios",
            "session_id": "body-session",
            "user_id": "42",
        },
        headers={"x-session-id": "header-session"},
    )

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    db.execute.assert_awaited_once()
    db.commit.assert_awaited_once()

    params = _compiled_params(db.execute.await_args.args[0])
    assert params["device_token"] == "abcdef1234567890"
    assert params["platform"] == "ios"
    assert params["session_id"] == "body-session"
    assert params["user_id"] == 42
    assert params["is_active"] is True
    assert params["param_1"] == "ios"
    assert params["param_2"] == 42
    assert params["param_3"] == "body-session"
    assert params["param_4"] is True


def test_register_device_token_falls_back_to_header_and_ignores_bad_user_id():
    db = _CaptureDB()
    client = _client_with_db(db)

    response = client.post(
        "/api/notifications/register",
        json={
            "device_token": "short",
            "platform": "macos",
            "user_id": "not-an-int",
        },
        headers={"x-session-id": "header-session"},
    )

    assert response.status_code == 200
    params = _compiled_params(db.execute.await_args.args[0])
    assert params["session_id"] == "header-session"
    assert params["user_id"] is None
    assert params["param_2"] is None


def test_list_device_tokens_rejects_invalid_admin_secret(monkeypatch):
    db = _CaptureDB()
    monkeypatch.setattr(notifications, "_check_admin_secret", lambda secret: False)

    response = _client_with_db(db).get("/api/notifications/admin/tokens?secret=bad")

    assert response.status_code == 403
    assert response.json() ["detail"] in ("Invalid admin secret", "Admin auth not configured")
    db.execute.assert_not_called()


class _ScalarRows:
    def __init__(self, rows):
        self.rows = rows

    def scalars(self):
        return self

    def all(self):
        return self.rows


class _ListDB:
    def __init__(self, rows):
        self.rows = rows
        self.statement = None

    async def execute(self, statement):
        self.statement = statement
        return _ScalarRows(self.rows)


def test_list_device_tokens_returns_redacted_active_tokens(monkeypatch):
    now = datetime(2026, 5, 18, 12, 30, tzinfo=timezone.utc)
    db = _ListDB(
        [
            SimpleNamespace(
                id=7,
                platform="ios",
                user_id=123,
                session_id="session-123",
                device_token="abcdef1234567890",
                created_at=now,
                updated_at=now,
            ),
            SimpleNamespace(
                id=8,
                platform="macos",
                user_id=None,
                session_id=None,
                device_token="xyz987",
                created_at=None,
                updated_at=None,
            ),
        ]
    )
    monkeypatch.setattr(notifications, "_check_admin_secret", lambda secret: secret == "ok")

    response = _client_with_db(db).get("/api/notifications/admin/tokens?secret=ok")

    assert response.status_code == 200
    assert response.json() == {
        "count": 2,
        "tokens": [
            {
                "id": 7,
                "platform": "ios",
                "user_id": 123,
                "session_id": "session-123",
                "token_prefix": "abcdef12",
                "token_suffix": "7890",
                "created_at": "2026-05-18T12:30:00+00:00",
                "updated_at": "2026-05-18T12:30:00+00:00",
            },
            {
                "id": 8,
                "platform": "macos",
                "user_id": None,
                "session_id": None,
                "token_prefix": "xyz987",
                "token_suffix": "z987",
                "created_at": None,
                "updated_at": None,
            },
        ],
    }
    compiled = str(db.statement.compile(dialect=postgresql_dialect()))
    assert "WHERE device_tokens.is_active IS true" in compiled
    assert "ORDER BY device_tokens.updated_at DESC" in compiled
    assert "LIMIT" in compiled


def test_send_test_notification_rejects_invalid_admin_secret(monkeypatch):
    monkeypatch.setattr(notifications, "_check_admin_secret", lambda secret: False)

    response = _client_with_db().post(
        "/api/notifications/admin/send-test?secret=bad",
        json={"device_token": "fcm-token"},
    )

    assert response.status_code == 403
    assert response.json() ["detail"] in ("Invalid admin secret", "Admin auth not configured")


class _FakeMessaging:
    sent_messages = []
    error = None

    class Notification:
        def __init__(self, title, body):
            self.title = title
            self.body = body

    class ApsAlert:
        def __init__(self, title, body):
            self.title = title
            self.body = body

    class Aps:
        def __init__(self, alert, sound, badge):
            self.alert = alert
            self.sound = sound
            self.badge = badge

    class APNSPayload:
        def __init__(self, aps):
            self.aps = aps

    class APNSConfig:
        def __init__(self, payload):
            self.payload = payload

    class Message:
        def __init__(self, notification, apns, token):
            self.notification = notification
            self.apns = apns
            self.token = token

    @classmethod
    def send(cls, message):
        cls.sent_messages.append(message)
        if cls.error:
            raise cls.error
        return "projects/bainluck/messages/abc123"


def _install_fake_firebase(monkeypatch, *, init_result=True, send_error=None):
    import sys

    import app.services.firebase_auth as firebase_auth

    _FakeMessaging.sent_messages = []
    _FakeMessaging.error = send_error
    monkeypatch.setitem(
        sys.modules,
        "firebase_admin",
        SimpleNamespace(messaging=_FakeMessaging),
    )
    monkeypatch.setattr(firebase_auth, "_init_firebase", lambda: init_result)


def test_send_test_notification_uses_fcm_payload_and_defaults(monkeypatch):
    monkeypatch.setattr(notifications, "_check_admin_secret", lambda secret: True)
    _install_fake_firebase(monkeypatch)

    response = _client_with_db().post(
        "/api/notifications/admin/send-test?secret=ok",
        json={"device_token": "fcm-token"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "status": "sent",
        "message_id": "projects/bainluck/messages/abc123",
    }
    assert len(_FakeMessaging.sent_messages) == 1
    message = _FakeMessaging.sent_messages[0]
    assert message.token == "fcm-token"
    assert message.notification.title == "Bain Luck"
    assert message.notification.body == "Test notification from Bain Luck"
    assert message.apns.payload.aps.alert.title == "Bain Luck"
    assert message.apns.payload.aps.alert.body == "Test notification from Bain Luck"
    assert message.apns.payload.aps.sound == "default"
    assert message.apns.payload.aps.badge == 1


def test_send_test_notification_returns_hint_for_invalid_fcm_token(monkeypatch):
    monkeypatch.setattr(notifications, "_check_admin_secret", lambda secret: True)
    _install_fake_firebase(
        monkeypatch,
        send_error=Exception("Invalid registration token"),
    )

    response = _client_with_db().post(
        "/api/notifications/admin/send-test?secret=ok",
        json={
            "device_token": "raw-apns-token",
            "title": "Custom title",
            "body": "Custom body",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "error"
    assert payload["error"] == "Invalid registration token"
    assert "raw APNS token" in payload["hint"]


def test_send_test_notification_reports_unconfigured_firebase(monkeypatch):
    monkeypatch.setattr(notifications, "_check_admin_secret", lambda secret: True)
    _install_fake_firebase(monkeypatch, init_result=False)

    response = _client_with_db().post(
        "/api/notifications/admin/send-test?secret=ok",
        json={"device_token": "fcm-token"},
    )

    assert response.status_code == 500
    assert response.json() == {"detail": "Firebase Admin SDK not configured"}
    assert _FakeMessaging.sent_messages == []
