from types import SimpleNamespace

import pytest
from fastapi import HTTPException

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
async def test_check_admin_auth_allows_configured_admin_email_via_env(monkeypatch):
    monkeypatch.setattr(
        admin_utils,
        "_check_admin_secret",
        lambda secret, **kw: False,
    )
    monkeypatch.setenv("ADMIN_USER_EMAILS", "alex.bain@gmail.com")
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
        lambda secret, **kw: False,
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
        lambda secret, **kw: False,
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


def test_check_admin_secret_none(monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", "correct-secret")
    with pytest.raises(HTTPException):
        admin_utils._check_admin_secret(None)


def test_check_admin_secret_empty(monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", "correct-secret")
    with pytest.raises(HTTPException):
        admin_utils._check_admin_secret("")


def test_check_admin_secret_wrong(monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", "correct-secret")
    with pytest.raises(HTTPException):
        admin_utils._check_admin_secret("wrong-secret")


def test_check_admin_secret_accepts_bearer_header(monkeypatch):
    """Queue #252 Item 3/4: the Bearer header is the accepted transport."""
    monkeypatch.setenv("ADMIN_TOKEN", "correct-secret")
    assert (
        admin_utils._check_admin_secret(None, request=_request("correct-secret"))
        is True
    )


def test_check_admin_secret_rejects_query_param(monkeypatch):
    """Queue #252 Item 3: a correct secret supplied via ?secret= is REJECTED —
    only the Authorization: Bearer header is honored."""
    monkeypatch.setenv("ADMIN_TOKEN", "correct-secret")
    # Correct value, but query-param form only (no Bearer header) -> rejected.
    with pytest.raises(HTTPException):
        admin_utils._check_admin_secret("correct-secret")
    # Even with a request that carries no matching Authorization header.
    empty_req = SimpleNamespace(headers={})
    with pytest.raises(HTTPException):
        admin_utils._check_admin_secret("correct-secret", request=empty_req)


@pytest.mark.asyncio
async def test_check_admin_auth_accepts_admin_token_bearer(monkeypatch):
    """Queue #252 Item 4: identity-aware auth accepts the ADMIN_TOKEN in the
    preferred Authorization: Bearer form even with no ?secret= present."""
    monkeypatch.setenv("ADMIN_TOKEN", "correct-secret")
    assert await admin_utils._check_admin_auth(
        None,
        _request("correct-secret"),
        _DB(None),
    )
