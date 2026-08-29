"""`POST /api/auth/email-sign-in` is DELETED, and must stay deleted.

#1279 V1 — Alex ruled "delete it permanently" (2026-08-28). The endpoint minted
a full 30-day session token from an email address ALONE: no password, no OAuth
assertion, no proof of possession of the mailbox. Anyone who knew an allowlisted
admin address became that admin.

**Why deletion and not the flag.** Queue #252 already closed the live hole by
putting the handler behind ``ENABLE_INSECURE_EMAIL_SIGN_IN``, unset in
production, so the deployed route returned 401. That is a correct containment
and a bad resting state: the code path that mints the token still existed, one
env var away from live, in a file that four other sign-in flows are edited in.
A flag is a decision someone can reverse by accident; a deleted route is not.

**What replaces it.** Nothing. Admins sign in through the verified OAuth flows
(``POST /api/auth/google``, ``/api/auth/google-access-token``,
``/api/auth/apple``), which are the controls asserted below so this file cannot
pass by having deleted the whole router.

The flag is asserted absent as well as the route, because "the endpoint 404s"
and "the passwordless mint is gone" are different claims and only the second
one is the ruling. A handler kept and merely unregistered would satisfy the
first.

Frontend half: ``frontend/__tests__/components/userMenuEmailSignInGone.test.tsx``.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from app.routes import auth as auth_route


# ---------------------------------------------------------------------------
# The route: gone from the wire
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_post_email_sign_in_is_404_not_401(client):
    """404 is the assertion, not `not 200`.

    While the route existed-but-disabled it answered **401** with a JSON
    ``detail``. A test that only asserted "no token came back" was green
    against the containment and would stay green against it forever. 404 is
    the status FastAPI produces when nothing is registered at the path, so it
    is the one status the disabled handler could never return.
    """
    resp = await client.post(
        "/api/auth/email-sign-in", json={"email": "admin@example.com"}
    )
    assert resp.status_code == 404, (
        f"the deleted endpoint answered with {resp.status_code} — "
        "401 means it is still registered and merely refusing"
    )
    body = resp.json()
    assert "id_token" not in body
    # The old handler's refusal text must not be what is being served.
    assert "Direct email sign-in is disabled" not in resp.text


@pytest.mark.asyncio
async def test_flag_cannot_resurrect_the_route(client, monkeypatch):
    """The opt-in that used to enable it is now inert, because there is no
    handler left to enable. This is the test that distinguishes "deleted" from
    "still default-off"."""
    monkeypatch.setenv("ENABLE_INSECURE_EMAIL_SIGN_IN", "1")
    resp = await client.post(
        "/api/auth/email-sign-in", json={"email": "admin@example.com"}
    )
    assert resp.status_code == 404
    assert "id_token" not in resp.text


@pytest.mark.asyncio
async def test_other_verbs_do_not_reach_a_handler(client):
    """No 405 either — a 405 would mean *something* is registered at the path."""
    for verb in ("get", "put", "patch", "delete"):
        resp = await getattr(client, verb)("/api/auth/email-sign-in")
        assert resp.status_code == 404, f"{verb.upper()} reached a handler"


@pytest.mark.asyncio
async def test_the_supported_sign_in_routes_still_exist(client):
    """Control (gotcha #43, both directions): this file must fail if the fix
    were "delete the auth router". Each of these answers *something* other than
    404 — the point is only that the path resolves to a handler."""
    for path in ("/api/auth/google", "/api/auth/google-access-token", "/api/auth/apple"):
        resp = await client.post(path, json={})
        assert resp.status_code != 404, f"{path} disappeared with the deletion"

    status = await client.get("/api/auth/status")
    assert status.status_code == 200


# ---------------------------------------------------------------------------
# The mint: gone from the source
# ---------------------------------------------------------------------------

def test_route_is_not_registered_on_the_auth_router():
    paths = {getattr(r, "path", None) for r in auth_route.router.routes}
    assert "/email-sign-in" not in paths
    # Control: the router is populated, so an empty set cannot pass this.
    assert "/status" in paths


def test_handler_model_and_flag_helper_are_gone():
    assert not hasattr(auth_route, "email_sign_in")
    assert not hasattr(auth_route, "EmailSignInRequest")
    assert not hasattr(auth_route, "_email_sign_in_enabled")


def test_module_source_carries_no_passwordless_mint():
    src = inspect.getsource(auth_route)
    for needle in (
        "email-sign-in",
        "EmailSignInRequest",
        "_email_sign_in_enabled",
        "ENABLE_INSECURE_EMAIL_SIGN_IN",
    ):
        assert needle not in src, f"{needle!r} survives in app/routes/auth.py"


def test_the_flag_name_appears_nowhere_in_the_backend_app():
    """Ruling-level, not file-level: the env var must not be readable from
    anywhere in the served application, or a second reader could re-open the
    path this queue closed."""
    app_dir = Path(auth_route.__file__).resolve().parents[1]
    assert app_dir.name == "app", app_dir
    offenders = [
        str(p.relative_to(app_dir))
        for p in app_dir.rglob("*.py")
        if "ENABLE_INSECURE_EMAIL_SIGN_IN" in p.read_text(encoding="utf-8")
    ]
    assert offenders == [], f"the deleted flag is still read by: {offenders}"
