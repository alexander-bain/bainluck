"""Security guard tests for Queue #252 — the auth-bypass pack.

Item 1: passwordless admin mint (email-in-body alone) is closed.
        **Superseded 2026-08-28 by #1279 V1 — see below.**
Item 2: a deleted account's still-valid token can no longer resurrect the
        account or authenticate (no auto-create resurrection).

── ITEM 1 MOVED, NOT DROPPED ──

Queue #252 closed the passwordless mint by putting it behind
``ENABLE_INSECURE_EMAIL_SIGN_IN``, and the three tests that lived here asserted
that containment: the flag defaults off, it parses as expected, and a
disabled handler returns 401. Alex then ruled the whole path deleted (#1279 V1),
so all three assert against symbols that no longer exist — the flag, the
request model, and the handler.

They were not weakened; they were replaced by a stronger claim in
``tests/integration/test_route_auth_email_signin_deleted.py``, which asserts the
route 404s, that setting the flag cannot bring it back, and that the flag name
is unreadable from anywhere in ``app/``. "The handler refuses" is a weaker
statement than "there is no handler", and only the second is the ruling.

Item 2 is untouched and still lives here.
"""

from types import SimpleNamespace

import pytest

from app.dependencies import auth as deps_auth


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
# Deleted with the endpoint it guarded (#1279 V1). The replacement is
# tests/integration/test_route_auth_email_signin_deleted.py — see the module
# docstring for why the move is a strengthening rather than a removal.


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
