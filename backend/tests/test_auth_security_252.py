"""Security guard tests for Queue #252 — the auth-bypass pack.

Item 1: passwordless admin mint (email-in-body alone) is closed.
Item 2: a deleted account's still-valid token can no longer resurrect the
        account or authenticate (no auto-create resurrection).
"""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.dependencies import auth as deps_auth
from app.routes import auth as auth_route


class _Result:
    def __init__(self, user):
        self._user = user

    def scalar_one_or_none(self):
        return self._user


class _DB:
    """Minimal async DB stub. Records add/flush so we can assert no writes."""

    def __init__(self, user):
        self._user = user
        self.added = []
        self.flushed = False

    async def execute(self, statement):
        return _Result(self._user)

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        self.flushed = True


class _Creds:
    def __init__(self, token="tok"):
        self.credentials = token


# --- Item 1: passwordless admin mint ---------------------------------------

def test_email_sign_in_disabled_by_default(monkeypatch):
    monkeypatch.delenv("ENABLE_INSECURE_EMAIL_SIGN_IN", raising=False)
    assert auth_route._email_sign_in_enabled() is False


def test_email_sign_in_opt_in_flag(monkeypatch):
    monkeypatch.setenv("ENABLE_INSECURE_EMAIL_SIGN_IN", "1")
    assert auth_route._email_sign_in_enabled() is True
    monkeypatch.setenv("ENABLE_INSECURE_EMAIL_SIGN_IN", "false")
    assert auth_route._email_sign_in_enabled() is False


@pytest.mark.asyncio
async def test_email_only_body_returns_401_never_a_token(monkeypatch):
    """The queue's guard: email-only body -> 401, never a token."""
    monkeypatch.delenv("ENABLE_INSECURE_EMAIL_SIGN_IN", raising=False)
    # Even an allowlisted admin email must not mint a token when disabled.
    monkeypatch.setenv("ADMIN_USER_EMAILS", "admin@example.com")

    body = auth_route.EmailSignInRequest(email="admin@example.com")
    with pytest.raises(HTTPException) as exc:
        await auth_route.email_sign_in(body, db=_DB(None))
    assert exc.value.status_code == 401


# --- Item 2: deleted-account token cannot resurrect / authenticate ---------

@pytest.mark.asyncio
async def test_deleted_user_token_resolves_to_none(monkeypatch):
    """A valid token whose User row is gone (deleted account) -> None (401),
    and must NOT auto-create/resurrect the account."""
    monkeypatch.setattr(
        deps_auth,
        "verify_id_token",
        lambda token: {"uid": "deleted-uid", "email": "gone@example.com"},
    )
    db = _DB(None)  # no user row
    user = await deps_auth._resolve_user(_Creds(), db)
    assert user is None
    assert db.added == []       # nothing created
    assert db.flushed is False  # no write


@pytest.mark.asyncio
async def test_existing_user_still_resolves(monkeypatch):
    monkeypatch.setattr(
        deps_auth,
        "verify_id_token",
        lambda token: {"uid": "live-uid", "email": "here@example.com"},
    )
    existing = SimpleNamespace(id=1, firebase_uid="live-uid", email="here@example.com")
    user = await deps_auth._resolve_user(_Creds(), _DB(existing))
    assert user is existing


@pytest.mark.asyncio
async def test_no_credentials_returns_none():
    assert await deps_auth._resolve_user(None, _DB(None)) is None
