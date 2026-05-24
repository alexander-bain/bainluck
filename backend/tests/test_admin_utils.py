from types import SimpleNamespace

import pytest

from app.routes import admin_utils


class _Result:
    def __init__(self, user):
        self.user = user

    def scalar_one_or_none(self):
        return self.user


class _DB:
    def __init__(self, user):
        self.user = user

    async def execute(self, statement):
        return _Result(self.user)


def _request(token="token"):
    return SimpleNamespace(headers={"authorization": f"Bearer {token}"})


@pytest.mark.asyncio
async def test_check_admin_auth_allows_default_admin_email(monkeypatch):
    monkeypatch.setattr(
        admin_utils,
        "_check_admin_secret",
        lambda secret: False,
    )
    monkeypatch.setattr(
        "app.services.firebase_auth.verify_id_token",
        lambda token: {"uid": "firebase-1", "email": "alex.bain@gmail.com"},
    )

    assert await admin_utils._check_admin_auth(
        None,
        _request(),
        _DB(SimpleNamespace(id=999, email="alex.bain@gmail.com")),
    )


@pytest.mark.asyncio
async def test_check_admin_auth_allows_configured_admin_email(monkeypatch):
    monkeypatch.setenv("ADMIN_USER_EMAILS", "ops@example.com")
    monkeypatch.setattr(
        admin_utils,
        "_check_admin_secret",
        lambda secret: False,
    )
    monkeypatch.setattr(
        "app.services.firebase_auth.verify_id_token",
        lambda token: {"uid": "firebase-2", "email": "ops@example.com"},
    )

    assert await admin_utils._check_admin_auth(
        None,
        _request(),
        _DB(SimpleNamespace(id=999, email="ops@example.com")),
    )


@pytest.mark.asyncio
async def test_check_admin_auth_rejects_unlisted_user(monkeypatch):
    monkeypatch.setattr(
        admin_utils,
        "_check_admin_secret",
        lambda secret: False,
    )
    monkeypatch.setattr(
        "app.services.firebase_auth.verify_id_token",
        lambda token: {"uid": "firebase-3", "email": "other@example.com"},
    )

    allowed = await admin_utils._check_admin_auth(
        None,
        _request(),
        _DB(SimpleNamespace(id=999, email="other@example.com")),
    )

    assert allowed is False
