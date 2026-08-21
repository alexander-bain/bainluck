"""Queue 386 Item 2 — admin access by IDENTITY, and the two invariants that bound it.

Alex ruled on 2026-08-20 that his Google-authenticated session should unlock
``/admin/labeling`` without the pasted admin secret. That is one sentence with
four separate things that can go wrong, and every one of them is a security
regression rather than a broken feature:

1. The lanes' token path changes shape and a lane silently loses (or gains) access.
2. Identity leaks into the DESTRUCTIVE gate and an unattended session can delete.
3. A non-admin user's valid session is accepted.
4. A garbage bearer takes a different code path than a wrong token and becomes
   an oracle for which arm exists.

Each has a test below, and each is asserted in BOTH directions (gotcha #43): a
gate exercised only in the failing direction can be inverted and still pass; one
exercised only in the passing direction is indistinguishable from no gate.

These are unit tests over the auth primitives rather than route tests, and
deliberately so — ``_check_admin_auth`` / ``_check_admin_destructive`` are the
things every admin route delegates to, so pinning them pins the whole surface.
The one structural test at the bottom covers the direction unit tests cannot: a
future route WIRING identity into the destructive set.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.routes.admin_utils import (
    DESTRUCTIVE_TOKEN_HEADER,
    _check_admin_auth,
    _check_admin_destructive,
    _check_admin_secret,
    _resolve_admin_email,
    _resolve_admin_user,
    _user_is_admin,
)

BASE_TOKEN = "base-admin-token"
DESTRUCTIVE_TOKEN = "second-destructive-token"
ADMIN_JWT = "admin.session.jwt"
CIVILIAN_JWT = "civilian.session.jwt"
GARBAGE_JWT = "not-a-jwt-at-all"

ADMIN_UID = "firebase-uid-alex"
CIVILIAN_UID = "firebase-uid-someone-else"


# --------------------------------------------------------------------------
# Test doubles
# --------------------------------------------------------------------------


class FakeUser:
    """A ``users`` row.

    ``__dict__`` carries the column values because that is exactly what
    ``_user_is_admin`` reads — ``getattr`` on an unloaded ORM attribute triggers
    a lazy refresh that raises ``MissingGreenlet`` in async context, so the
    production helper reads ``__dict__`` and this double must mirror that or the
    test would pass against an implementation that crashes in production.
    """

    def __init__(self, *, id: int, email: str | None, is_admin: bool | None = False):
        self.id = id
        self.email = email
        if is_admin is not None:
            self.is_admin = is_admin


class _Result:
    def __init__(self, row):
        self._row = row

    def scalar_one_or_none(self):
        return self._row


class FakeDB:
    """Returns whichever row the current test registered for a uid.

    Records ``queries`` so a test can prove the token path did NOT touch the
    database — the cheapness of the token arm is part of the "lanes are
    unchanged" claim, not an implementation detail.
    """

    def __init__(self, rows: dict[str, FakeUser] | None = None):
        self.rows = rows or {}
        self.queries = 0
        self.next_row: FakeUser | None = None

    async def execute(self, _stmt):
        self.queries += 1
        return _Result(self.next_row)


def _request(
    *,
    bearer: str | None = None,
    destructive: str | None = None,
    path: str = "/api/admin/ranking-judgments",
    method: str = "POST",
) -> Request:
    headers = []
    if bearer is not None:
        headers.append((b"authorization", f"Bearer {bearer}".encode()))
    if destructive is not None:
        headers.append(
            (DESTRUCTIVE_TOKEN_HEADER.lower().encode(), destructive.encode())
        )
    return Request(
        {
            "type": "http",
            "method": method,
            "path": path,
            "query_string": b"",
            "headers": headers,
        }
    )


@pytest.fixture
def tokens(monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", BASE_TOKEN)
    monkeypatch.setenv("ADMIN_TOKEN_DESTRUCTIVE", DESTRUCTIVE_TOKEN)
    # The legacy allowlists must be empty for these tests, or a hardcoded
    # DEFAULT_ADMIN_USER_IDS hit would make the COLUMN look like it works when
    # it does not.
    monkeypatch.setenv("ADMIN_USER_IDS", "")
    monkeypatch.setenv("ADMIN_USER_EMAILS", "")
    monkeypatch.setattr("app.routes.admin_utils.DEFAULT_ADMIN_USER_IDS", set())
    monkeypatch.setattr("app.routes.admin_utils.DEFAULT_ADMIN_EMAILS", set())


@pytest.fixture
def verifier(monkeypatch):
    """Stub ``verify_id_token``: only the two known JWTs verify.

    Everything else returns ``None``, which is what a real unverifiable token
    produces. Note this stubs the SERVICE, not the auth helper — the helper's
    own error handling stays under test.
    """
    claims = {
        ADMIN_JWT: {"uid": ADMIN_UID, "email": "alex@example.com"},
        CIVILIAN_JWT: {"uid": CIVILIAN_UID, "email": "someone@example.com"},
    }

    def fake_verify(token, allow_session_token=True):
        return claims.get(token)

    monkeypatch.setattr(
        "app.services.firebase_auth.verify_id_token", fake_verify
    )
    return fake_verify


# --------------------------------------------------------------------------
# 1. REGRESSION: the token path is byte-for-byte the lanes' old path
# --------------------------------------------------------------------------


class TestTokenPathUnchanged:
    """The lanes' path. Nothing in this queue may move it."""

    @pytest.mark.asyncio
    async def test_correct_token_is_admin(self, tokens, verifier):
        db = FakeDB()
        assert await _check_admin_auth(None, _request(bearer=BASE_TOKEN), db) is True

    @pytest.mark.asyncio
    async def test_wrong_token_is_not_admin(self, tokens, verifier):
        """The failing direction. Without it, a gate returning True
        unconditionally would satisfy the test above."""
        db = FakeDB()
        assert await _check_admin_auth(None, _request(bearer="wrong"), db) is False

    @pytest.mark.asyncio
    async def test_token_path_never_touches_the_database(self, tokens, verifier):
        """Ordering, asserted as a cost rather than as a comment.

        The token arm runs first and short-circuits, so a lane pays no JWT parse
        and no query. If someone reorders the arms, this is the test that
        notices — the boolean result would be identical.
        """
        db = FakeDB()
        await _check_admin_auth(None, _request(bearer=BASE_TOKEN), db)
        assert db.queries == 0

    def test_check_admin_secret_itself_is_token_only(self, tokens, verifier):
        """``_check_admin_secret`` must not learn about identity.

        It is the primitive ``_check_admin_destructive`` leans on for invariant
        1. If it ever accepted a session JWT, the destructive gate would open
        without anyone editing the destructive gate.
        """
        with pytest.raises(HTTPException) as exc:
            _check_admin_secret(None, request=_request(bearer=ADMIN_JWT))
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_admin_token_is_not_attributed_to_a_person(self, tokens, verifier):
        """A capability is not an identity.

        A dozen lanes hold ADMIN_TOKEN, so resolving it to an email would put an
        unfalsifiable provenance claim into the gold corpus (#671).
        """
        db = FakeDB()
        assert await _resolve_admin_email(_request(bearer=BASE_TOKEN), db) is None


# --------------------------------------------------------------------------
# 2. Identity grants READ/WRITE admin
# --------------------------------------------------------------------------


class TestIdentityGrantsAdmin:
    @pytest.mark.asyncio
    async def test_is_admin_column_grants_admin(self, tokens, verifier):
        db = FakeDB()
        db.next_row = FakeUser(id=99, email="alex@example.com", is_admin=True)
        assert await _check_admin_auth(None, _request(bearer=ADMIN_JWT), db) is True

    @pytest.mark.asyncio
    async def test_identity_admin_is_attributed_by_email(self, tokens, verifier):
        """Invariant 2's mechanism: a verified session names a person."""
        db = FakeDB()
        db.next_row = FakeUser(id=99, email="Alex@Example.COM", is_admin=True)
        assert (
            await _resolve_admin_email(_request(bearer=ADMIN_JWT), db)
            == "alex@example.com"
        )

    @pytest.mark.asyncio
    async def test_legacy_id_allowlist_still_grants(self, tokens, verifier, monkeypatch):
        """The fallback that keeps the release from locking Alex out.

        The column ships in a deploy; the grant is a manual UPDATE afterwards.
        Between those two moments the allowlist is the only thing holding the
        admin UI open.

        AMENDED 2026-08-21 (Queue 390): this row is now ``is_admin=None``, not
        ``False``.

        Not a weakened assertion — a corrected DOUBLE. The column became nullable
        so that a never-granted row and a REVOKED row stop being the same value
        (``C-2063-REVIEW`` finding 2: with two states, the documented
        ``UPDATE users SET is_admin = false`` could not outrank the allowlist
        OR-ed after it). ``None`` is what a real un-granted row holds after this
        revision, so ``False`` here would no longer be testing the rollout
        window this test is named for — it would be testing revocation, and
        asserting that revocation FAILS. The behaviour under test is unchanged
        and is additionally pinned from the other side by
        ``test_admin_identity_auth_q390_r2.py``.
        """
        monkeypatch.setattr("app.routes.admin_utils.DEFAULT_ADMIN_USER_IDS", {364})
        db = FakeDB()
        db.next_row = FakeUser(id=364, email="alex@example.com", is_admin=None)
        assert await _check_admin_auth(None, _request(bearer=ADMIN_JWT), db) is True

    @pytest.mark.asyncio
    async def test_an_explicit_false_is_not_the_rollout_state(
        self, tokens, verifier, monkeypatch
    ):
        """The distinction the test above now depends on, asserted directly.

        Added with the amendment so the two states cannot quietly re-merge: if a
        future change makes ``None`` and ``False`` behave alike again, exactly one
        of these two tests fails whichever way it goes.
        """
        monkeypatch.setattr("app.routes.admin_utils.DEFAULT_ADMIN_USER_IDS", {364})
        db = FakeDB()
        db.next_row = FakeUser(id=364, email="alex@example.com", is_admin=False)
        assert await _check_admin_auth(None, _request(bearer=ADMIN_JWT), db) is False

    def test_user_is_admin_reads_dict_not_getattr(self):
        """A row whose ``is_admin`` was never loaded is NOT an admin.

        Encoded here because the safe reading of an unknown privilege is
        'denied', and because ``getattr`` on an unloaded ORM attribute raises
        ``MissingGreenlet`` in async context rather than returning a default.
        """
        unloaded = FakeUser(id=1, email="x@y.z", is_admin=None)
        assert "is_admin" not in unloaded.__dict__
        assert _user_is_admin(unloaded) is False


# --------------------------------------------------------------------------
# 3. INVARIANT 1: identity NEVER unlocks a destructive endpoint
# --------------------------------------------------------------------------


class TestIdentityNeverUnlocksDestructive:
    """The invariant Alex named first. Both directions, and then the structure."""

    def test_token_pair_still_opens_the_destructive_gate(self, tokens):
        """PASSING direction — a gate that denies everything is not a gate."""
        assert (
            _check_admin_destructive(
                None,
                request=_request(bearer=BASE_TOKEN, destructive=DESTRUCTIVE_TOKEN),
            )
            is True
        )

    def test_identity_bearer_is_refused_even_with_the_destructive_token(self, tokens, verifier):
        """The invariant itself.

        The destructive token is CORRECT here. What is refused is the first
        factor: ``_check_admin_destructive`` calls ``_check_admin_secret``,
        which is token-only, so an identity session fails before the second
        token is ever examined.
        """
        with pytest.raises(HTTPException) as exc:
            _check_admin_destructive(
                None,
                request=_request(bearer=ADMIN_JWT, destructive=DESTRUCTIVE_TOKEN),
                )
        assert exc.value.status_code == 403

    def test_destructive_gate_takes_no_db_and_cannot_consult_identity(self):
        """Structural, and the one that survives a refactor.

        ``_check_admin_destructive`` has no ``db`` parameter, so it is not merely
        *choosing* not to check identity — it has no way to. Adding one would
        fail here, which is the moment to have the conversation rather than
        after the delete.
        """
        import inspect

        params = inspect.signature(_check_admin_destructive).parameters
        assert "db" not in params, (
            "_check_admin_destructive gained a `db` parameter. Identity admin is "
            "attended-by-construction for READS, but a delete must stay gated on "
            "ADMIN_TOKEN + ADMIN_TOKEN_DESTRUCTIVE (Queue 386 Item 2, invariant 1)."
        )


# --------------------------------------------------------------------------
# 4. Everything else is refused, identically
# --------------------------------------------------------------------------


class TestRefusals:
    @pytest.mark.asyncio
    async def test_non_admin_identity_is_refused(self, tokens, verifier):
        """A real, verifiable session of a real user who is simply not an admin."""
        db = FakeDB()
        db.next_row = FakeUser(id=7, email="someone@example.com", is_admin=False)
        assert await _check_admin_auth(None, _request(bearer=CIVILIAN_JWT), db) is False
        assert await _resolve_admin_email(_request(bearer=CIVILIAN_JWT), db) is None

    @pytest.mark.asyncio
    async def test_garbage_bearer_is_refused(self, tokens, verifier):
        db = FakeDB()
        assert await _check_admin_auth(None, _request(bearer=GARBAGE_JWT), db) is False

    @pytest.mark.asyncio
    async def test_verified_token_with_no_user_row_is_refused(self, tokens, verifier):
        """A deleted account's still-valid 30-day JWT (Queue #252 Item 2)."""
        db = FakeDB()
        db.next_row = None
        assert await _check_admin_auth(None, _request(bearer=ADMIN_JWT), db) is False

    @pytest.mark.asyncio
    async def test_no_bearer_at_all_is_refused(self, tokens, verifier):
        db = FakeDB()
        assert await _check_admin_auth(None, _request(), db) is False

    @pytest.mark.asyncio
    async def test_identity_arm_swallows_a_raising_database(self, tokens, verifier):
        """A broken identity arm must DENY, not 500.

        It runs only after the token arm has declined, so returning False here
        can never downgrade an acceptance — but raising would turn every wrong
        token into a 500 and take the admin API down with it.
        """

        class ExplodingDB(FakeDB):
            async def execute(self, _stmt):
                raise RuntimeError("connection reset")

        db = ExplodingDB()
        assert await _check_admin_auth(None, _request(bearer=ADMIN_JWT), db) is False
        assert await _resolve_admin_user(_request(bearer=ADMIN_JWT), db) is None

    @pytest.mark.asyncio
    async def test_a_wrong_token_and_a_garbage_jwt_are_indistinguishable(
        self, tokens, verifier
    ):
        """No oracle. Which arm declined is not disclosed to the caller."""
        db = FakeDB()
        wrong_token = await _check_admin_auth(None, _request(bearer="wrong"), db)
        garbage = await _check_admin_auth(None, _request(bearer=GARBAGE_JWT), db)
        assert wrong_token == garbage is False


# --------------------------------------------------------------------------
# 5. Structural: no destructive route may adopt the identity gate
# --------------------------------------------------------------------------


ROUTES_DIR = Path(__file__).resolve().parents[1] / "app/routes"


def _functions_calling(name: str) -> dict[str, set[str]]:
    """Map ``module -> {function names that call ``name`` directly}``."""
    found: dict[str, set[str]] = {}
    for path in sorted(ROUTES_DIR.glob("*.py")):
        try:
            tree = ast.parse(path.read_text())
        except SyntaxError:  # pragma: no cover - a syntax error fails elsewhere
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for inner in ast.walk(node):
                if not isinstance(inner, ast.Call):
                    continue
                func = inner.func
                called = getattr(func, "id", None) or getattr(func, "attr", None)
                if called == name:
                    found.setdefault(path.name, set()).add(node.name)
    return found


def test_no_handler_mixes_the_destructive_gate_with_the_identity_gate():
    """The failure mode the unit tests above cannot reach.

    ``_check_admin_destructive`` cannot be *tricked* into accepting an identity.
    But a handler could call ``_check_admin_auth`` first, return early on
    success, and reach the destructive work having never called the destructive
    gate. That is not a bug in either function; it is a bug in the wiring, and
    wiring is what this test reads.
    """
    destructive = _functions_calling("_check_admin_destructive")
    identity = _functions_calling("_check_admin_auth")
    identity_authorize = _functions_calling("_authorize_admin")

    # Non-vacuity. A source-scanning test whose scanner silently stops matching
    # (a rename, a decorator change, an import indirection) passes forever while
    # checking nothing. Both sides must be populated for the assertion below to
    # mean anything.
    assert sum(len(v) for v in destructive.values()) >= 10, (
        "The destructive-handler scan found almost nothing — the scanner is "
        "broken, not the codebase."
    )
    assert sum(len(v) for v in {**identity, **identity_authorize}.values()) >= 3, (
        "The identity-handler scan found almost nothing — the scanner is broken."
    )

    offenders = []
    for module, handlers in destructive.items():
        soft = identity.get(module, set()) | identity_authorize.get(module, set())
        for handler in sorted(handlers & soft):
            offenders.append(f"{module}::{handler}")

    assert not offenders, (
        "These handlers call BOTH the destructive gate and an identity-accepting "
        f"gate: {offenders}. Identity alone must never unlock a delete (Queue 386 "
        "Item 2, invariant 1) — a handler that satisfies the identity gate first "
        "and returns early bypasses the second token entirely."
    )
