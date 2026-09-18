"""#7047 — a provider profile field must never be able to fail a sign-in.

On 2026-09-18 a real Google sign-in on TestFlight build 15 returned
``Server error (500). Please try again.`` twice (21:27:46Z and 21:28:03Z). The
server-side exception names the branch exactly: the ``INSERT INTO users`` in
``POST /api/auth/google-access-token`` raised
``asyncpg.exceptions.StringDataRightTruncationError: value too long for type
character varying(512)`` — the account's Google avatar URL is 1,343 characters
and ``users.photo_url`` is ``VARCHAR(512)``. Nothing about the account's domain
is involved; the Gmail control that signed in successfully in the same session
simply has a shorter avatar URL.

These tests drive the REAL route (Google introspection mocked, every identity
side effect a stub) and assert on the object handed to the session, because
that is where the contract lives: what we hand Postgres must fit the column it
is going into. The widths are read off the model here too, so widening a column
later cannot leave a test asserting a number the database no longer enforces.

The ordinary-Gmail control rows are the other half: the fix must not change
what a normal sign-in stores.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import String

from app.dependencies.auth import get_optional_user
from app.models.models import User
from app.services.database import get_db, get_db_rw

OUR_CLIENT_ID = "899260594814-ios.apps.googleusercontent.com"

#: The specimen from the incident, at its measured length (1,343 characters —
#: the real URL is not reproduced here, it identifies a person). Length, not
#: shape, is what broke the INSERT.
OVERSIZE_PHOTO_URL = (
    "https://lh3.googleusercontent.com/a-/ALV-Uj" + ("A1b2C3d4" * 162)[:1294] + "=s96-c"
)
assert len(OVERSIZE_PHOTO_URL) == 1343

#: The control: an ordinary Gmail avatar URL, the shape that has always worked.
ORDINARY_PHOTO_URL = "https://lh3.googleusercontent.com/a/ACg8ocK-short=s96-c"


def _string_columns_with_widths():
    """(name, width) for every bounded string column on ``users``."""
    return [
        (col.name, col.type.length)
        for col in User.__table__.columns
        if isinstance(col.type, String) and col.type.length
    ]


def _assert_every_string_fits(user: User) -> None:
    """The contract the database enforces, asserted where we can see it."""
    for name, width in _string_columns_with_widths():
        value = getattr(user, name, None)
        if isinstance(value, str):
            assert len(value) <= width, (
                f"users.{name} would be handed {len(value)} characters for a "
                f"VARCHAR({width}) column — this is the #7047 500"
            )


def _tokeninfo_ok() -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"aud": OUR_CLIENT_ID, "azp": OUR_CLIENT_ID}
    return resp


def _userinfo(email: str, name: str, picture) -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    body = {"email": email, "email_verified": True, "name": name}
    if picture is not None:
        body["picture"] = picture
    resp.json.return_value = body
    return resp


@pytest.fixture
def identity_stubs(monkeypatch):
    """Firebase lookup/create and both token mints, as call-counting stubs."""
    firebase = MagicMock(return_value="fb-uid-7047")
    custom = MagicMock(return_value="custom-token-7047")
    session = MagicMock(return_value="session-token-7047")
    monkeypatch.setattr("app.routes.auth.get_or_create_firebase_user", firebase)
    monkeypatch.setattr("app.routes.auth.create_custom_token", custom)
    monkeypatch.setattr("app.services.firebase_auth.create_session_token", session)
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_IDS", OUR_CLIENT_ID)
    return {"firebase": firebase, "custom": custom, "session": session}


def _session_stub(existing_user: User | None):
    """An async session that records ``add``ed rows and stamps ``created_at``.

    ``created_at`` is a server default, so a real flush fills it; the stub does
    the same thing so the response serializer runs the way production runs it.
    """
    db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = existing_user
    db.execute.return_value = result
    added: list = []
    db.add = MagicMock(side_effect=added.append)

    async def _refresh(obj, *args, **kwargs):
        # A real flush fills the primary key and the server defaults; the stub
        # does the same so the response serializer runs as production runs it.
        if getattr(obj, "id", None) is None:
            obj.id = 4207
        if getattr(obj, "created_at", None) is None:
            obj.created_at = datetime(2026, 9, 18, 21, 27, 46)

    db.refresh = AsyncMock(side_effect=_refresh)
    return db, added


def _users_created(added: list) -> list:
    """Only the account rows — a create also adds the empty preferences row."""
    return [obj for obj in added if isinstance(obj, User)]


@pytest.fixture
async def route_client(monkeypatch):
    """ASGI client over the real app with a swappable session stub."""
    monkeypatch.setenv("BYPASS_RATE_LIMITS", "1")

    from app.main import app

    state: dict = {}

    async def _mock_get_db():
        yield state["db"]

    app.dependency_overrides[get_db] = _mock_get_db
    app.dependency_overrides[get_db_rw] = _mock_get_db
    app.dependency_overrides[get_optional_user] = lambda: None

    with patch("app.main.init_db", new_callable=AsyncMock):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield ac, state

    app.dependency_overrides.clear()


async def _sign_in_with_access_token(
    route_client, *, email="user@example.com", name="Alex Bain",
    picture=ORDINARY_PHOTO_URL, existing_user=None,
):
    ac, state = route_client
    db, added = _session_stub(existing_user)
    state["db"] = db
    tok, ui = _tokeninfo_ok(), _userinfo(email, name, picture)

    async def _mock_get(url, *args, **kwargs):
        return tok if "tokeninfo" in url else ui

    with patch("httpx.AsyncClient.get", side_effect=_mock_get):
        resp = await ac.post(
            "/api/auth/google-access-token",
            json={"access_token": "opaque-access-token"},
        )
    return resp, _users_created(added), db


# --- The defect ------------------------------------------------------------


@pytest.mark.asyncio
async def test_oversize_avatar_url_signs_in_instead_of_500ing(
    route_client, identity_stubs
):
    """The incident, reproduced: this request returned 500 before the fix."""
    assert len(OVERSIZE_PHOTO_URL) > User.__table__.c.photo_url.type.length

    resp, added, _ = await _sign_in_with_access_token(
        route_client, picture=OVERSIZE_PHOTO_URL
    )

    assert resp.status_code == 200, resp.text
    assert len(added) == 1, "the sign-in must still create the account row"
    _assert_every_string_fits(added[0])
    # A prefix of a signed URL is a broken image, so the avatar is dropped
    # whole rather than truncated.
    assert added[0].photo_url is None


@pytest.mark.asyncio
async def test_the_rest_of_the_profile_survives_the_dropped_avatar(
    route_client, identity_stubs
):
    """Dropping the photo must not cost the reader their name or account."""
    resp, added, _ = await _sign_in_with_access_token(
        route_client, picture=OVERSIZE_PHOTO_URL, name="Alex Bain"
    )

    assert resp.status_code == 200
    assert added[0].display_name == "Alex Bain"
    assert added[0].email == "user@example.com"
    assert added[0].firebase_uid == "fb-uid-7047"
    body = resp.json()
    assert body["uid"] == "fb-uid-7047"
    assert body["custom_token"] and body["id_token"]


@pytest.mark.asyncio
async def test_an_existing_account_keeps_the_avatar_it_already_has(
    route_client, identity_stubs
):
    """The UPDATE path 500s the same way; here it must leave the row alone."""
    existing = User(
        id=42,
        firebase_uid="fb-uid-7047",
        email="user@example.com",
        display_name="Alex Bain",
        photo_url=ORDINARY_PHOTO_URL,
    )
    existing.preferences = None
    existing.created_at = datetime(2026, 9, 1, 12, 0, 0)

    resp, added, _ = await _sign_in_with_access_token(
        route_client, picture=OVERSIZE_PHOTO_URL, existing_user=existing
    )

    assert resp.status_code == 200, resp.text
    assert added == [], "an existing account is updated, never re-created"
    assert existing.photo_url == ORDINARY_PHOTO_URL
    _assert_every_string_fits(existing)


@pytest.mark.asyncio
async def test_an_oversize_display_name_is_truncated_not_refused(
    route_client, identity_stubs
):
    """A name HAS a valid prefix, so it is kept as much as the column allows."""
    width = User.__table__.c.display_name.type.length
    long_name = "Bartholomew " * 40

    resp, added, _ = await _sign_in_with_access_token(
        route_client, name=long_name
    )

    assert resp.status_code == 200, resp.text
    assert added[0].display_name == long_name[:width]
    _assert_every_string_fits(added[0])


@pytest.mark.asyncio
async def test_an_unstorable_email_is_refused_before_any_side_effect(
    route_client, identity_stubs
):
    """Identity is never shortened: a truncated email is a different person."""
    width = User.__table__.c.email.type.length
    long_email = ("a" * (width + 20)) + "@example.com"

    resp, added, db = await _sign_in_with_access_token(
        route_client, email=long_email
    )

    assert resp.status_code == 400, resp.text
    assert added == []
    assert identity_stubs["firebase"].call_count == 0
    assert identity_stubs["custom"].call_count == 0
    assert identity_stubs["session"].call_count == 0
    assert db.execute.call_count == 0


# --- The control: an ordinary Gmail sign-in is unchanged -------------------


@pytest.mark.asyncio
async def test_ordinary_gmail_signin_stores_its_avatar_byte_for_byte(
    route_client, identity_stubs
):
    """The Gmail account that DID sign in must behave exactly as before."""
    resp, added, _ = await _sign_in_with_access_token(
        route_client, email="someone@gmail.com", picture=ORDINARY_PHOTO_URL
    )

    assert resp.status_code == 200, resp.text
    assert added[0].photo_url == ORDINARY_PHOTO_URL
    assert added[0].display_name == "Alex Bain"
    assert resp.json()["picture"] == ORDINARY_PHOTO_URL
    _assert_every_string_fits(added[0])


@pytest.mark.asyncio
async def test_a_signin_with_no_avatar_at_all_still_works(
    route_client, identity_stubs
):
    """Absent is not oversize — a missing picture stays missing, not an error."""
    resp, added, _ = await _sign_in_with_access_token(route_client, picture=None)

    assert resp.status_code == 200, resp.text
    assert added[0].photo_url is None


# --- The same fields on the Firebase ID-token path -------------------------


@pytest.mark.asyncio
async def test_firebase_id_token_path_fits_the_same_columns(
    route_client, identity_stubs, monkeypatch
):
    """``POST /api/auth/google`` writes the same columns from the same source."""
    ac, state = route_client
    db, added = _session_stub(None)
    state["db"] = db
    monkeypatch.setattr(
        "app.routes.auth.verify_id_token",
        MagicMock(
            return_value={
                "uid": "fb-uid-7047",
                "email": "user@example.com",
                "name": "Alex Bain",
                "picture": OVERSIZE_PHOTO_URL,
            }
        ),
    )

    resp = await ac.post("/api/auth/google", json={"id_token": "firebase-id-token"})

    created = _users_created(added)
    assert resp.status_code == 200, resp.text
    assert len(created) == 1
    _assert_every_string_fits(created[0])
    assert created[0].photo_url is None
    assert created[0].display_name == "Alex Bain"
