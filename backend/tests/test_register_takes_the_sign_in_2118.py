"""#2118 (131-A): a phone is tied to an account only by that account's sign-in.

THE HOLE (read-only trace, Aug 23, on the issue). ``POST
/api/notifications/register`` had no authentication, read ``user_id`` straight
from the request body, and on a repeat token overwrote the owner. So, in one
request each:

* INBOUND: a stranger registers their OWN token with ``user_id = <victim>``,
  and the victim's notifications (the Morning Digest is the live consumer) go
  to the stranger's phone;
* OUTBOUND: a stranger posts the victim's token with their own or a null
  ``user_id``, and the victim's phone silently stops getting its notifications.

1.0.6 gives the iPhone its push entitlement (#12559), so real tokens start
arriving.

THE RULE NOW. The account comes from a valid sign-in (``get_optional_user``,
the same Bearer check as every signed-in route; the app already sends it,
checked on #2118). The body's ``user_id`` is ignored. A signed-out registration
is stored anonymous and keeps working. A call without a valid sign-in never
changes which account an already-registered phone belongs to.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.dialects.postgresql import dialect as postgresql_dialect

from app.dependencies.auth import get_optional_user
from app.routes import notifications
from app.services.database import get_db_rw

VICTIM, STRANGER = 42, 7


class _CaptureDB:
    def __init__(self):
        self.execute = AsyncMock()
        self.commit = AsyncMock()


def _client(db, user=None) -> TestClient:
    app = FastAPI()
    app.include_router(notifications.router)

    async def _db():
        return db

    async def _user():
        return user

    app.dependency_overrides[get_db_rw] = _db
    app.dependency_overrides[get_optional_user] = _user
    return TestClient(app)


def _statement(db):
    return db.execute.await_args.args[0]


def _inserted_user(db):
    return _statement(db).compile(dialect=postgresql_dialect()).params["user_id"]


def _set_user(db):
    stmt = _statement(db)
    for col, val in stmt._post_values_clause.update_values_to_set:
        name = col if isinstance(col, str) else col.key
        if name == "user_id":
            return val.value if hasattr(val, "value") else val
    return "NOT SET"


def _post(client, **body):
    payload = {"device_token": "a" * 64, "platform": "ios"}
    payload.update(body)
    return client.post("/api/notifications/register", json=payload)


class TestTheAccountComesFromTheSignIn:
    def test_a_signed_in_phone_belongs_to_the_signed_in_account(self):
        db = _CaptureDB()
        assert _post(_client(db, SimpleNamespace(id=VICTIM))).status_code == 200
        assert _inserted_user(db) == VICTIM
        assert _set_user(db) == VICTIM

    def test_the_body_user_id_is_ignored_even_when_signed_in(self):
        # The stranger, signed in as themselves, names the victim in the body.
        db = _CaptureDB()
        _post(_client(db, SimpleNamespace(id=STRANGER)), user_id=str(VICTIM))
        assert _inserted_user(db) == STRANGER
        assert _set_user(db) == STRANGER


class TestSignedOutRegistrationStillWorks:
    def test_it_is_stored_anonymous(self):
        db = _CaptureDB()
        res = _post(_client(db, None))
        assert res.status_code == 200 and res.json()["status"] == "ok"
        assert _inserted_user(db) is None
        db.commit.assert_awaited_once()


class TestTheAugustTrace:
    def test_inbound_a_strangers_token_naming_the_victim_lands_anonymous(self):
        db = _CaptureDB()
        _post(_client(db, None), device_token="stranger-device-token", user_id=str(VICTIM))
        assert _inserted_user(db) is None

    def test_outbound_an_unsigned_call_cannot_move_or_detach_a_registered_phone(self):
        # The victim's token re-posted without a sign-in, naming the stranger
        # or no one: the repeat-token update must not touch the owner.
        for body_user in (str(STRANGER), None):
            db = _CaptureDB()
            _post(_client(db, None), device_token="victim-device-token", user_id=body_user)
            assert _set_user(db) == "NOT SET"

    def test_an_invalid_sign_in_is_treated_as_signed_out(self):
        # get_optional_user resolves a bad, expired or deleted-account token to
        # None, the same as no token; the route then cannot write an owner.
        db = _CaptureDB()
        _post(_client(db, None), user_id=str(VICTIM))
        assert _inserted_user(db) is None and _set_user(db) == "NOT SET"


def test_the_route_depends_on_the_shared_optional_sign_in():
    import inspect

    sig = inspect.signature(notifications.register_device_token)
    deps = [p.default.dependency for p in sig.parameters.values() if hasattr(p.default, "dependency")]
    assert get_optional_user in deps
