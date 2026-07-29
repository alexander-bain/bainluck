"""Queue 282 / C78 — Google access-token audience (confused-deputy) contract.

Drives ``POST /api/auth/google-access-token`` against every row of
``scripts/evals/google_access_token_audience_fixtures.json`` with the real route
logic. No test issues a real Google call, uses a real token/client id/email, or
mutates Firebase or the database — tokeninfo/userinfo are mocked and every
identity side effect (Firebase lookup/create, DB lookup/create, custom-token
mint, session-token mint) is a call-counting stub.

The fixture's symbolic allowed client ids (``web_client``/``ios_client``) are
loaded into the server-owned ``GOOGLE_OAUTH_CLIENT_IDS`` allowlist so the strict
exact-match path is exercised; a rejected row must return a non-2xx AND prove
zero identity side effects.
"""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.dependencies.auth import get_optional_user
from app.services.database import get_db, get_db_rw

FIXTURE_PATH = (
    Path(__file__).resolve().parent.parent
    / "scripts"
    / "evals"
    / "google_access_token_audience_fixtures.json"
)
_CORPUS = json.loads(FIXTURE_PATH.read_text())
_ALLOWED_CLIENT_IDS = ",".join(
    _CORPUS["configuration_authority"]["symbolic_allowed_client_ids"]
)


def _tokeninfo_response(row: dict) -> MagicMock:
    """Mock the Google tokeninfo introspection response for a fixture row."""
    resp = MagicMock()
    status = row["tokeninfo_status"]
    if status == "ok":
        resp.status_code = 200
        body = {}
        if row.get("introspected_audience") is not None:
            body["aud"] = row["introspected_audience"]
        if row.get("authorized_party") is not None:
            body["azp"] = row["authorized_party"]
        resp.json.return_value = body
    elif status == "expired_or_revoked":
        resp.status_code = 400
        resp.json.return_value = {"error": "invalid_token"}
    else:  # "error"
        resp.status_code = 401
        resp.json.return_value = {"error": "invalid_token"}
    return resp


def _userinfo_response(row: dict) -> MagicMock:
    """Mock the Google userinfo response for a fixture row."""
    resp = MagicMock()
    if row["userinfo_status"] == "ok":
        resp.status_code = 200
        body = {"name": "Test User", "picture": "https://example.com/p.jpg"}
        if row.get("email_present"):
            body["email"] = "user@example.com"
            body["email_verified"] = bool(row.get("email_verified"))
        resp.json.return_value = body
    else:  # "error" / "not_called" (not_called rows fail at tokeninfo first)
        resp.status_code = 401
        resp.json.return_value = {"error": "invalid_token"}
    return resp


@pytest.fixture
def side_effect_probes(monkeypatch):
    """Call-counting stubs for every forbidden rejection side effect."""
    firebase = MagicMock(return_value="fb-uid-282")
    custom = MagicMock(return_value="custom-token-282")
    session = MagicMock(return_value="session-token-282")
    monkeypatch.setattr("app.routes.auth.get_or_create_firebase_user", firebase)
    monkeypatch.setattr("app.routes.auth.create_custom_token", custom)
    monkeypatch.setattr(
        "app.services.firebase_auth.create_session_token", session
    )
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_IDS", _ALLOWED_CLIENT_IDS)
    return {"firebase": firebase, "custom": custom, "session": session}


@pytest.fixture
async def probe_client(monkeypatch):
    """ASGI client with a call-counting DB session (execute = identity lookup)."""
    monkeypatch.setenv("BYPASS_RATE_LIMITS", "1")

    from app.main import app

    db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None  # force the create branch
    db.execute.return_value = result

    async def _mock_get_db():
        yield db

    app.dependency_overrides[get_db] = _mock_get_db
    app.dependency_overrides[get_db_rw] = _mock_get_db
    app.dependency_overrides[get_optional_user] = lambda: None

    with patch("app.main.init_db", new_callable=AsyncMock):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield ac, db

    app.dependency_overrides.clear()


async def _run_row(probe_client, side_effect_probes, row):
    ac, db = probe_client
    tok = _tokeninfo_response(row)
    ui = _userinfo_response(row)

    async def _mock_get(url, *args, **kwargs):
        return tok if "tokeninfo" in url else ui

    with patch("httpx.AsyncClient.get", side_effect=_mock_get):
        resp = await ac.post(
            "/api/auth/google-access-token",
            json={"access_token": "opaque-access-token"},
        )
    return resp, db


@pytest.mark.parametrize("row", _CORPUS["scenarios"], ids=lambda r: r["id"])
@pytest.mark.asyncio
async def test_audience_scenarios(probe_client, side_effect_probes, row):
    resp, db = await _run_row(probe_client, side_effect_probes, row)
    probes = side_effect_probes

    if row["accepted"]:
        assert resp.status_code == 200, (row["id"], resp.text)
        # Accepted rows perform the identity side effects the fixture declares.
        assert probes["firebase"].called is row["firebase_lookup_or_create"]
        assert (db.execute.called) is row["database_lookup_or_create"]
        assert probes["custom"].called is row["custom_token_minted"]
        assert probes["session"].called is row["session_minted"]
    else:
        # Every rejection is non-2xx (401/400) with ZERO identity side effects.
        assert resp.status_code >= 400, (row["id"], resp.text)
        assert probes["firebase"].call_count == 0, row["id"]
        assert db.execute.call_count == 0, row["id"]
        assert probes["custom"].call_count == 0, row["id"]
        assert probes["session"].call_count == 0, row["id"]


_REJECTED_401_ROWS = [
    r
    for r in _CORPUS["scenarios"]
    # Rejected rows only; the missing-email row is a distinct 400 contract.
    if not r["accepted"] and r["id"] != "email_absent"
]


@pytest.mark.parametrize("row", _REJECTED_401_ROWS, ids=lambda r: r["id"])
@pytest.mark.asyncio
async def test_rejected_rows_return_401(probe_client, side_effect_probes, row):
    """Item 1 acceptance: every rejected audience/introspection row is a 401."""
    resp, _ = await _run_row(probe_client, side_effect_probes, row)
    assert resp.status_code == 401, (row["id"], resp.text)


@pytest.mark.asyncio
async def test_admin_email_cannot_override_wrong_audience(
    probe_client, side_effect_probes
):
    """An allowlisted admin identity cannot rescue a wrong-audience token."""
    row = next(r for r in _CORPUS["scenarios"] if r["id"] == "wrong_audience_admin")
    resp, db = await _run_row(probe_client, side_effect_probes, row)
    assert resp.status_code == 401
    assert side_effect_probes["firebase"].call_count == 0
    assert db.execute.call_count == 0
    assert side_effect_probes["session"].call_count == 0


@pytest.mark.asyncio
async def test_rejected_counterexamples_have_no_side_effects(
    probe_client, side_effect_probes
):
    """The corpus' rejected counterexamples must fail closed at the real route.

    They encode the exact bug being fixed (accepting a wrong/missing audience and
    performing identity side effects), so the route must reject them.
    """
    for row in _CORPUS["rejected_counterexamples"]:
        # Reset probe counters between rows.
        for probe in side_effect_probes.values():
            probe.reset_mock()
        resp, db = await _run_row(probe_client, side_effect_probes, row)
        db.execute.reset_mock()
        assert resp.status_code == 401, row["id"]
        assert side_effect_probes["firebase"].call_count == 0, row["id"]
        assert side_effect_probes["custom"].call_count == 0, row["id"]
        assert side_effect_probes["session"].call_count == 0, row["id"]


@pytest.mark.asyncio
async def test_same_project_default_allows_configured_web_client(
    probe_client, side_effect_probes, monkeypatch
):
    """Deploy-safety: with no explicit allowlist, a token from our own GCP
    project (same client-id prefix) is accepted; a cross-project token is not."""
    monkeypatch.delenv("GOOGLE_OAUTH_CLIENT_IDS", raising=False)
    ours = "899260594814-web.apps.googleusercontent.com"
    theirs = "111111111111-other.apps.googleusercontent.com"

    ok_row = {
        "tokeninfo_status": "ok",
        "introspected_audience": ours,
        "authorized_party": ours,
        "userinfo_status": "ok",
        "email_present": True,
        "email_verified": True,
    }
    resp, _ = await _run_row(probe_client, side_effect_probes, ok_row)
    assert resp.status_code == 200

    for probe in side_effect_probes.values():
        probe.reset_mock()
    bad_row = {**ok_row, "introspected_audience": theirs, "authorized_party": theirs}
    resp, db = await _run_row(probe_client, side_effect_probes, bad_row)
    assert resp.status_code == 401
    assert side_effect_probes["firebase"].call_count == 0


@pytest.mark.asyncio
async def test_transport_failure_is_503(probe_client, side_effect_probes):
    """A transport error reaching Google fails closed as 503, no side effects."""
    import httpx

    ac, db = probe_client

    async def _boom(url, *args, **kwargs):
        raise httpx.ConnectError("no route to google")

    with patch("httpx.AsyncClient.get", side_effect=_boom):
        resp = await ac.post(
            "/api/auth/google-access-token",
            json={"access_token": "opaque"},
        )
    assert resp.status_code == 503
    assert side_effect_probes["firebase"].call_count == 0
    assert db.execute.call_count == 0


@pytest.mark.asyncio
async def test_malformed_tokeninfo_json_is_401(probe_client, side_effect_probes):
    """Malformed introspection JSON fails closed (no persistence/mint)."""
    ac, db = probe_client
    bad = MagicMock()
    bad.status_code = 200
    bad.json.side_effect = ValueError("not json")

    async def _mock_get(url, *args, **kwargs):
        return bad

    with patch("httpx.AsyncClient.get", side_effect=_mock_get):
        resp = await ac.post(
            "/api/auth/google-access-token",
            json={"access_token": "opaque"},
        )
    assert resp.status_code == 401
    assert side_effect_probes["firebase"].call_count == 0
    assert db.execute.call_count == 0
