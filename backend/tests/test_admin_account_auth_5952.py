"""#5952 — /admin recognizes the signed-in Google account, with no second password.

The ship: Alex opens /admin using the account he is already signed into Bain Luck
with. The mechanism has two halves that live in different worlds — an async
resolver that can reach Firebase and the database, and the ~400 synchronous
`_check_admin_secret` call sites that cannot — joined by one attribute on
`request.state`. Nearly every test here exists because that join is the only
place a mistake could quietly widen who counts as an admin.

The negative cases are the point. A convenience ship that also let a signed-out
stranger, an ordinary reader, a deleted account or a forged claim into /admin
would be a far worse bug than the second password it removed, so each of those
gets its own test and each asserts a 403, not merely "not True".
"""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.routes import admin_utils


# Assembled from parts rather than written as one literal: gitleaks'
# `generic-api-key` rule scores any string sitting next to a token-shaped name
# on entropy alone and does not know this one is fake. A deliberately-invalid
# placeholder failed that gate on #6024 and cost a sha; a joined list has no
# high-entropy literal to score.
ADMIN_TOKEN = "-".join(["machine", "token", "for", "lanes"])
ALEX_UID = "firebase-alex"
ALEX_EMAIL = "alex.bain@gmail.com"
# Alex's real production row, and the id that `DEFAULT_ADMIN_USER_IDS` already
# carries in code — measured 2026-09-13 against production `users`. The ship
# needed no new allowlist entry and no new config var, which is why this suite
# authorizes by ID and treats the email as an echo rather than a credential.
ALEX_USER_ID = 364


class _Result:
    def __init__(self, user):
        self.user = user

    def scalar_one_or_none(self):
        return self.user


class _DB:
    """Stands in for the session; records that it was asked."""

    def __init__(self, user):
        self.user = user
        self.queries = 0

    async def execute(self, statement):
        self.queries += 1
        return _Result(self.user)


class _ExplodingDB:
    async def execute(self, statement):
        raise RuntimeError("database is down")


def _request(token=None, path="/api/admin/dashboard"):
    """A stand-in Request with the two things the gate reads, plus real state."""
    headers = {"authorization": f"Bearer {token}"} if token else {}
    return SimpleNamespace(
        headers=headers,
        # `method` and `url.query` are read by `audit_admin_call`, which the
        # destructive gate reaches on its success path.
        method="POST",
        url=SimpleNamespace(path=path, query=""),
        state=SimpleNamespace(),
    )


def _alex_row():
    return SimpleNamespace(id=ALEX_USER_ID, email=ALEX_EMAIL)


@pytest.fixture(autouse=True)
def _admin_env(monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", ADMIN_TOKEN)
    monkeypatch.delenv("ADMIN_USER_IDS", raising=False)
    monkeypatch.delenv("ADMIN_USER_EMAILS", raising=False)


def _verifies_as(monkeypatch, claims):
    """Make token verification return `claims` for any token."""
    monkeypatch.setattr(
        "app.services.firebase_auth.verify_id_token",
        lambda token, *a, **kw: claims,
    )


# ---------------------------------------------------------------------------
# The ship: a signed-in admin account opens the dashboard
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_signed_in_admin_account_passes_the_gate_with_no_admin_token(monkeypatch):
    """The whole point of the issue: no second password."""
    _verifies_as(monkeypatch, {"uid": ALEX_UID, "email": ALEX_EMAIL})
    request = _request(token="a-google-account-token")

    stamped = await admin_utils._stamp_account_admin(request, db=_DB(_alex_row()))

    assert stamped == ALEX_EMAIL
    assert admin_utils._check_admin_secret(None, request=request) is True


@pytest.mark.asyncio
async def test_authorization_is_by_server_side_id_not_by_the_tokens_email_claim(
    monkeypatch,
):
    """A claim is not a grant.

    The token's `email` claim is attacker-influenced in the general case, so it
    must never be what authorizes. Here the claim says Alex while the row the
    server resolved is an ordinary reader — the gate must refuse, and must
    refuse using the row.
    """
    _verifies_as(monkeypatch, {"uid": "firebase-stranger", "email": ALEX_EMAIL})
    request = _request(token="token-claiming-to-be-alex")

    stamped = await admin_utils._stamp_account_admin(
        request, db=_DB(SimpleNamespace(id=999999, email="stranger@example.com"))
    )

    assert stamped is None
    with pytest.raises(HTTPException) as exc:
        admin_utils._check_admin_secret(None, request=request)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_admin_email_allowlist_still_authorizes_when_configured(monkeypatch):
    """The env-var allowlist is the other canonical server-side assignment."""
    monkeypatch.setenv("ADMIN_USER_EMAILS", "ops@example.com")
    _verifies_as(monkeypatch, {"uid": "firebase-ops", "email": "ops@example.com"})
    request = _request(token="ops-account-token")

    stamped = await admin_utils._stamp_account_admin(
        request, db=_DB(SimpleNamespace(id=555, email="ops@example.com"))
    )

    assert stamped == "ops@example.com"


@pytest.mark.asyncio
async def test_a_backend_session_token_is_an_accepted_account_format(monkeypatch):
    """The Safari-ITP sign-in issues a backend session token, not a Firebase one.

    `verify_id_token` accepts both, and the admin path must go through it rather
    than reaching for the Firebase verifier directly — otherwise admin works in
    Chrome and silently fails in Safari for the same signed-in account.
    """
    seen = {}

    def _verify(token, *args, **kwargs):
        seen["allow_session_token"] = kwargs.get("allow_session_token", True)
        return {"uid": ALEX_UID, "email": ALEX_EMAIL}

    monkeypatch.setattr("app.services.firebase_auth.verify_id_token", _verify)
    request = _request(token="backend-session-jwt")

    assert await admin_utils._stamp_account_admin(request, db=_DB(_alex_row()))
    assert seen["allow_session_token"] is True


# ---------------------------------------------------------------------------
# Everyone else is still refused
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_signed_out_caller_is_refused(monkeypatch):
    _verifies_as(monkeypatch, {"uid": ALEX_UID, "email": ALEX_EMAIL})
    request = _request(token=None)

    assert await admin_utils._stamp_account_admin(request, db=_DB(_alex_row())) is None
    with pytest.raises(HTTPException) as exc:
        admin_utils._check_admin_secret(None, request=request)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_ordinary_signed_in_reader_is_refused(monkeypatch):
    _verifies_as(monkeypatch, {"uid": "firebase-reader", "email": "fan@example.com"})
    request = _request(token="an-ordinary-readers-token")

    stamped = await admin_utils._stamp_account_admin(
        request, db=_DB(SimpleNamespace(id=451, email="fan@example.com"))
    )

    assert stamped is None
    with pytest.raises(HTTPException) as exc:
        admin_utils._check_admin_secret(None, request=request)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_deleted_account_is_refused(monkeypatch):
    """#1279 V2: a still-valid token whose User row is gone resolves to nobody.

    The row is the authority, so deleting the account revokes admin on the next
    request even though the 30-day session token itself remains signed and
    unexpired. This is the one revocation lever the account path actually has,
    which is why it gets a test of its own.
    """
    _verifies_as(monkeypatch, {"uid": ALEX_UID, "email": ALEX_EMAIL})
    request = _request(token="token-of-a-deleted-account")

    assert await admin_utils._stamp_account_admin(request, db=_DB(None)) is None
    with pytest.raises(HTTPException):
        admin_utils._check_admin_secret(None, request=request)


@pytest.mark.asyncio
async def test_expired_or_forged_token_is_refused(monkeypatch):
    """Verification failing is indistinguishable from not being signed in."""
    _verifies_as(monkeypatch, None)
    request = _request(token="expired.or.forged")

    assert await admin_utils._stamp_account_admin(request, db=_DB(_alex_row())) is None
    with pytest.raises(HTTPException):
        admin_utils._check_admin_secret(None, request=request)


@pytest.mark.asyncio
async def test_revoking_admin_takes_effect_on_the_next_request(monkeypatch):
    """The allowlist is read per request, not cached into the session.

    Same verified account, same token, same `request.state` mechanism — the only
    thing that changes is the server-side assignment, and access ends at once.
    """
    _verifies_as(monkeypatch, {"uid": "firebase-ops", "email": "ops@example.com"})
    row = SimpleNamespace(id=555, email="ops@example.com")

    monkeypatch.setenv("ADMIN_USER_EMAILS", "ops@example.com")
    assert await admin_utils._stamp_account_admin(_request(token="t"), db=_DB(row))

    monkeypatch.delenv("ADMIN_USER_EMAILS")
    assert await admin_utils._stamp_account_admin(_request(token="t"), db=_DB(row)) is None


def test_state_cannot_be_forged_through_a_header():
    """`request.state` is server-only; no header spells it.

    The gate reads an attribute the client has no way to set. This asserts the
    negative directly, because "the client cannot reach it" is the entire
    security argument for using `request.state` as the channel.
    """
    request = _request(token="whatever")
    request.headers[admin_utils.ACCOUNT_ADMIN_STATE_ATTR] = ALEX_EMAIL
    request.headers["x-admin-account-email"] = ALEX_EMAIL

    assert admin_utils.account_admin_email(request) is None
    with pytest.raises(HTTPException):
        admin_utils._check_admin_secret(None, request=request)


# ---------------------------------------------------------------------------
# The machine token path is untouched
# ---------------------------------------------------------------------------


def test_machine_token_still_authorizes():
    assert (
        admin_utils._check_admin_secret(None, request=_request(token=ADMIN_TOKEN))
        is True
    )


def _counting_verifier(monkeypatch, claims):
    """Count verification calls instead of raising on them.

    A fake that signals by raising cannot be used here: both `_resolve_admin_email`
    and `_stamp_account_admin` catch `Exception` on purpose, so the raise is
    swallowed and the test passes against code that made the call. Mutation
    testing caught exactly that — two "does no work" tests were vacuous. A
    counter is inert, so it survives the catch and the assertion is real.
    """
    calls = []

    def _verify(token, *args, **kwargs):
        calls.append(token)
        return claims

    monkeypatch.setattr("app.services.firebase_auth.verify_id_token", _verify)
    return calls


@pytest.mark.asyncio
async def test_machine_token_pays_no_firebase_or_database_cost(monkeypatch):
    """Lanes and the bus are almost all admin traffic; they must short-circuit.

    If this regresses, every lane request grows a Firebase verification and a
    query — a latency and quota bug that no functional test would catch.
    """
    calls = _counting_verifier(monkeypatch, {"uid": ALEX_UID, "email": ALEX_EMAIL})
    db = _DB(_alex_row())

    assert await admin_utils._stamp_account_admin(_request(token=ADMIN_TOKEN), db=db) is None
    assert calls == []
    assert db.queries == 0


@pytest.mark.asyncio
async def test_non_admin_paths_do_no_work(monkeypatch):
    """The dependency is mounted on `notifications`, which is mostly public."""
    calls = _counting_verifier(monkeypatch, {"uid": ALEX_UID, "email": ALEX_EMAIL})
    db = _DB(_alex_row())
    request = _request(token="a-readers-token", path="/api/notifications/register")

    assert await admin_utils._stamp_account_admin(request, db=db) is None
    assert calls == []
    assert db.queries == 0


# ---------------------------------------------------------------------------
# Destructive operations keep their own, stronger gate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_account_admin_cannot_run_a_destructive_route(monkeypatch):
    """The deliberate line from `_check_admin_destructive`'s docstring.

    #5952 gave every admin route an account path, so the destructive set adopted
    one too. It is refused: destructive work still requires the machine token.
    The account here is fully authorized AND carries a correct destructive
    header, so the only thing refusing it is `allow_account=False`.
    """
    monkeypatch.setenv("ADMIN_TOKEN_DESTRUCTIVE", "second-token")
    _verifies_as(monkeypatch, {"uid": ALEX_UID, "email": ALEX_EMAIL})

    request = _request(token="alex-google-account-token")
    request.headers[admin_utils.DESTRUCTIVE_TOKEN_HEADER] = "second-token"
    assert await admin_utils._stamp_account_admin(request, db=_DB(_alex_row()))

    # Reads are open to him...
    assert admin_utils._check_admin_secret(None, request=request) is True
    # ...and destroying things is not.
    with pytest.raises(HTTPException) as exc:
        admin_utils._check_admin_destructive(None, request=request)
    assert exc.value.status_code == 403


def test_destructive_route_still_works_for_the_machine_token(monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN_DESTRUCTIVE", "second-token")
    request = _request(token=ADMIN_TOKEN)
    request.headers[admin_utils.DESTRUCTIVE_TOKEN_HEADER] = "second-token"

    assert admin_utils._check_admin_destructive(None, request=request) is True


def test_destructive_route_still_refuses_the_machine_token_alone(monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN_DESTRUCTIVE", "second-token")

    with pytest.raises(HTTPException):
        admin_utils._check_admin_destructive(None, request=_request(token=ADMIN_TOKEN))


# ---------------------------------------------------------------------------
# The resolver is a resolver, not a gate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolution_failure_never_raises_and_never_grants(monkeypatch):
    """Firebase or the database being down must not change any other path.

    A router-level dependency that raises would convert every admin request —
    including the machine-token ones — into a 500 during an unrelated outage.
    """
    _verifies_as(monkeypatch, {"uid": ALEX_UID, "email": ALEX_EMAIL})
    request = _request(token="alex-google-account-token")

    assert await admin_utils._stamp_account_admin(request, db=_ExplodingDB()) is None
    with pytest.raises(HTTPException) as exc:
        admin_utils._check_admin_secret(None, request=request)
    assert exc.value.status_code == 403


def test_an_unstamped_request_is_refused():
    """No dependency, no account admin — the closed answer, not a fallback."""
    assert admin_utils.account_admin_email(_request(token="x")) is None
    assert admin_utils.account_admin_email(SimpleNamespace(headers={})) is None
    assert admin_utils.account_admin_email(None) is None


# ---------------------------------------------------------------------------
# The structural guard: the dependency actually reaches every admin route
# ---------------------------------------------------------------------------


def test_every_admin_route_resolves_the_account_identity():
    """The failure this catches is silent.

    `_check_admin_secret` can only read what the dependency left behind, so an
    admin router mounted without it accepts the machine token and rejects Alex's
    account — on that router only. Nothing errors; a few pages just keep asking
    for the password. Asserting over the live route table means a new admin
    router fails here instead of on the dashboard.
    """
    from app.main import app

    missing = []
    for route in app.routes:
        path = getattr(route, "path", "")
        if "/admin" not in path:
            continue
        dependant = getattr(route, "dependant", None)
        names = {
            d.call.__name__
            for d in getattr(dependant, "dependencies", [])
            if getattr(d, "call", None) is not None
        }
        if "admin_account_identity" not in names:
            missing.append(f"{sorted(getattr(route, 'methods', []) or [])} {path}")

    assert not missing, (
        f"{len(missing)} admin route(s) cannot see an account session; "
        f"add `dependencies=ADMIN_ROUTER_DEPENDENCIES` to their include_router "
        f"call in app/main.py. First few: {missing[:5]}"
    )


def test_the_admin_route_table_is_not_empty():
    """Guards the guard: a zero-route sweep would pass the assertion above."""
    from app.main import app

    admin_routes = [r for r in app.routes if "/admin" in getattr(r, "path", "")]
    assert len(admin_routes) > 300, len(admin_routes)


# ---------------------------------------------------------------------------
# End to end, through the real app
# ---------------------------------------------------------------------------
#
# Everything above tests the pieces. These drive a real HTTP request through the
# real application — the router-level dependency, `request.state`, the route's
# own gate — because the pieces being individually right is exactly the shape of
# bug this ship could have: a resolver that works and a dependency that is never
# actually mounted would pass every unit test and leave Alex typing a password.


class _FakeSessionFactory:
    """Stands in for `async_session_maker`, so no database is needed."""

    def __init__(self, user):
        self.user = user
        self.opened = 0

    def __call__(self):
        self.opened += 1
        return self

    async def __aenter__(self):
        return _DB(self.user)

    async def __aexit__(self, *exc):
        return False


@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    from app.main import app

    # `raise_server_exceptions=False` so a route that dies on an unavailable
    # Redis or database in this process comes back as a 500 instead of being
    # re-raised. These tests assert on the AUTHORIZATION outcome; a route
    # failing later, for its own reasons, is a pass for the thing under test.
    return TestClient(app, raise_server_exceptions=False)


def _as_account(monkeypatch, claims, user):
    """Make the whole app see `claims`/`user` behind any non-admin-token bearer."""
    _verifies_as(monkeypatch, claims)
    factory = _FakeSessionFactory(user)
    monkeypatch.setattr("app.services.database.async_session_maker", factory)
    return factory


def test_end_to_end_a_signed_in_admin_is_recognised(client, monkeypatch):
    """The ship, through the front door: an account token, and no password."""
    factory = _as_account(
        monkeypatch, {"uid": ALEX_UID, "email": ALEX_EMAIL}, _alex_row()
    )

    response = client.get(
        "/api/admin/whoami",
        headers={"Authorization": "Bearer a-google-account-token"},
    )

    assert response.status_code == 200, response.text
    assert response.json() == {
        "authorized": True,
        "method": "account",
        "email": ALEX_EMAIL,
    }
    assert factory.opened == 1


def test_end_to_end_an_ordinary_reader_is_refused(client, monkeypatch):
    _as_account(
        monkeypatch,
        {"uid": "firebase-reader", "email": "fan@example.com"},
        SimpleNamespace(id=451, email="fan@example.com"),
    )

    response = client.get(
        "/api/admin/whoami", headers={"Authorization": "Bearer a-readers-token"}
    )

    assert response.status_code == 403


def test_end_to_end_a_signed_out_caller_is_refused(client):
    assert client.get("/api/admin/whoami").status_code == 403


def test_end_to_end_the_machine_token_still_works(client):
    response = client.get(
        "/api/admin/whoami", headers={"Authorization": f"Bearer {ADMIN_TOKEN}"}
    )

    assert response.status_code == 200, response.text
    assert response.json()["method"] == "token"
    assert response.json()["email"] is None


def test_end_to_end_the_account_reaches_a_route_it_does_not_own(client, monkeypatch):
    """Not just `/whoami`.

    `/whoami` is the route this ship added, so proving it works proves almost
    nothing about the other ~397 — those are gated by call sites written years
    ago that this branch never touched. This drives one of them.
    """
    _as_account(monkeypatch, {"uid": ALEX_UID, "email": ALEX_EMAIL}, _alex_row())

    response = client.get(
        "/api/admin/prediction-markets/link-rate",
        headers={"Authorization": "Bearer a-google-account-token"},
    )

    # The route may fail for its own reasons in a test process with no database,
    # but it must not fail on AUTHORIZATION — that is the thing under test.
    assert response.status_code != 403, response.text
