"""Contract tests for user endpoints: /api/me/*

Tests pins CRUD, preferences, onboarding, favorites, team search,
teams by location, sport affinities, and team futures.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.dependencies.auth import get_current_user, get_optional_user
from app.services.database import get_db


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user(id: int = 1):
    user = MagicMock()
    user.id = id
    user.firebase_uid = "fb-uid-123"
    user.email = "test@example.com"
    user.display_name = "Test User"
    user.photo_url = None
    user.created_at = datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)
    return user


def _make_mock_result(
    scalars_all=None,
    scalar_one_or_none=None,
    scalar_one=None,
    all_rows=None,
):
    result = MagicMock()
    result.scalars.return_value.all.return_value = scalars_all or []
    result.scalars.return_value.first.return_value = None
    result.scalar_one_or_none.return_value = scalar_one_or_none
    result.scalar_one.return_value = scalar_one
    result.scalar.return_value = None
    result.fetchall.return_value = []
    result.all.return_value = all_rows or []
    result.first.return_value = None
    return result


@pytest.fixture
def mock_db():
    session = AsyncMock()
    session.execute.return_value = _make_mock_result()
    return session


@pytest.fixture
async def client(mock_db, monkeypatch):
    monkeypatch.setenv("BYPASS_RATE_LIMITS", "1")

    from app.main import app

    async def _mock_get_db():
        yield mock_db

    async def _mock_get_optional_user():
        return None

    app.dependency_overrides[get_db] = _mock_get_db
    app.dependency_overrides[get_optional_user] = _mock_get_optional_user

    with patch("app.main.init_db", new_callable=AsyncMock):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as ac:
            yield ac

    app.dependency_overrides.clear()


# ===========================================================================
# GET /api/me/pins — requires auth
# ===========================================================================

@pytest.mark.asyncio
async def test_get_pins_unauthenticated(client):
    """GET /pins should return 401 without auth."""
    from app.main import app

    async def _mock_no_user():
        from fastapi import HTTPException, status
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")

    app.dependency_overrides[get_current_user] = _mock_no_user
    try:
        resp = await client.get("/api/me/pins")
        assert resp.status_code == 401
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_get_pins_empty(client, mock_db):
    """GET /pins should return empty lists when no pins exist."""
    from app.main import app

    user = _make_user()
    app.dependency_overrides[get_current_user] = lambda: user
    mock_db.execute.return_value = _make_mock_result(scalars_all=[])

    try:
        resp = await client.get("/api/me/pins")
        assert resp.status_code == 200
        body = resp.json()
        assert body == {"events": [], "futures": []}
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_get_pins_with_data(client, mock_db):
    """GET /pins should return event and futures IDs."""
    from app.main import app

    user = _make_user()
    app.dependency_overrides[get_current_user] = lambda: user

    pin1 = MagicMock()
    pin1.pin_type = "event"
    pin1.target_id = 42
    pin2 = MagicMock()
    pin2.pin_type = "future"
    pin2.target_id = 99
    mock_db.execute.return_value = _make_mock_result(scalars_all=[pin1, pin2])

    try:
        resp = await client.get("/api/me/pins")
        assert resp.status_code == 200
        body = resp.json()
        assert body["events"] == [42]
        assert body["futures"] == [99]
    finally:
        app.dependency_overrides.pop(get_current_user, None)


# ===========================================================================
# POST /api/me/pins — add single pin
# ===========================================================================

@pytest.mark.asyncio
async def test_add_pin_invalid_type(client, mock_db):
    """POST /pins should reject invalid pin_type."""
    from app.main import app

    user = _make_user()
    app.dependency_overrides[get_current_user] = lambda: user

    try:
        resp = await client.post(
            "/api/me/pins",
            json={"pin_type": "invalid", "target_id": 1},
        )
        assert resp.status_code == 400
        assert "pin_type" in resp.json()["detail"]
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_add_pin_requires_fields(client, mock_db):
    """POST /pins should require pin_type and target_id."""
    from app.main import app

    user = _make_user()
    app.dependency_overrides[get_current_user] = lambda: user

    try:
        resp = await client.post("/api/me/pins", json={})
        assert resp.status_code == 422
    finally:
        app.dependency_overrides.pop(get_current_user, None)


# ===========================================================================
# DELETE /api/me/pins/{pin_type}/{target_id}
# ===========================================================================

@pytest.mark.asyncio
async def test_remove_pin_invalid_type(client, mock_db):
    """DELETE /pins should reject invalid pin_type."""
    from app.main import app

    user = _make_user()
    app.dependency_overrides[get_current_user] = lambda: user

    try:
        resp = await client.delete("/api/me/pins/invalid/42")
        assert resp.status_code == 400
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_remove_pin_success(client, mock_db):
    """DELETE /pins should return unpinned status."""
    from app.main import app

    user = _make_user()
    app.dependency_overrides[get_current_user] = lambda: user

    try:
        resp = await client.delete("/api/me/pins/event/42")
        assert resp.status_code == 200
        assert resp.json() == {"status": "unpinned"}
    finally:
        app.dependency_overrides.pop(get_current_user, None)


# ===========================================================================
# PUT /api/me/pins — bulk upsert
# ===========================================================================

@pytest.mark.asyncio
async def test_bulk_upsert_pins_unauthenticated(client):
    """PUT /pins should return 401 without auth."""
    from app.main import app

    async def _mock_no_user():
        from fastapi import HTTPException, status
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")

    app.dependency_overrides[get_current_user] = _mock_no_user
    try:
        resp = await client.put("/api/me/pins", json={"events": [1], "futures": [2]})
        assert resp.status_code == 401
    finally:
        app.dependency_overrides.pop(get_current_user, None)


# ===========================================================================
# GET /api/me/preferences — uses optional auth
# ===========================================================================

@pytest.mark.asyncio
async def test_get_preferences_anonymous(client):
    """GET /preferences for anonymous user returns defaults."""
    resp = await client.get("/api/me/preferences")

    assert resp.status_code == 200
    body = resp.json()
    assert body["home_location"] is None
    assert body["sport_affinities"] == {}
    assert body["onboarding_completed"] is False
    assert body["favorites"] == []


@pytest.mark.asyncio
async def test_get_preferences_authenticated(client, mock_db):
    """GET /preferences for authenticated user returns preferences shape."""
    from app.main import app

    user = _make_user()

    async def _mock_optional_user():
        return user

    prefs = MagicMock()
    prefs.home_location = "Boston"
    prefs.sport_affinities = {"basketball_nba": 1.0}
    prefs.onboarding_completed = True

    # First execute returns preferences, second returns favorites
    mock_db.execute.side_effect = [
        _make_mock_result(scalar_one_or_none=prefs),
        _make_mock_result(all_rows=[]),
    ]

    app.dependency_overrides[get_optional_user] = _mock_optional_user
    try:
        resp = await client.get("/api/me/preferences")
        assert resp.status_code == 200
        body = resp.json()
        assert body["home_location"] == "Boston"
        assert body["onboarding_completed"] is True
        assert isinstance(body["sport_affinities"], dict)
        assert isinstance(body["favorites"], list)
    finally:
        app.dependency_overrides.pop(get_optional_user, None)


# ===========================================================================
# POST /api/me/onboarding — requires auth
# ===========================================================================

@pytest.mark.asyncio
async def test_onboarding_unauthenticated(client):
    """POST /onboarding should return 401 without auth."""
    from app.main import app

    async def _mock_no_user():
        from fastapi import HTTPException, status
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")

    app.dependency_overrides[get_current_user] = _mock_no_user
    try:
        resp = await client.post("/api/me/onboarding", json={})
        assert resp.status_code == 401
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_onboarding_success(client, mock_db):
    """POST /onboarding should save preferences and return ok."""
    from app.main import app

    user = _make_user()
    app.dependency_overrides[get_current_user] = lambda: user

    prefs = MagicMock()
    prefs.home_location = None
    prefs.sport_affinities = {}
    prefs.onboarding_completed = False
    mock_db.execute.return_value = _make_mock_result(scalar_one_or_none=prefs)

    try:
        resp = await client.post(
            "/api/me/onboarding",
            json={
                "home_location": "Boston",
                "local_teams": [],
                "follow_teams": [],
                "alma_mater_teams": [],
                "rival_teams": [],
                "sport_affinities": {"basketball": 1.0, "baseball": 0.5},
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["onboarding_completed"] is True
    finally:
        app.dependency_overrides.pop(get_current_user, None)


# ===========================================================================
# GET /api/me/teams/search — no auth required
# ===========================================================================

@pytest.mark.asyncio
async def test_team_search_too_short(client):
    """Team search should return empty for query shorter than 2 chars."""
    resp = await client.get("/api/me/teams/search?q=a")

    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_team_search_returns_list(client, mock_db):
    """Team search should return list of team results."""
    resp = await client.get("/api/me/teams/search?q=celtics")

    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_team_search_requires_q_param(client):
    """Team search should require the q query parameter."""
    resp = await client.get("/api/me/teams/search")
    assert resp.status_code == 422


# ===========================================================================
# GET /api/me/teams/by-location — no auth required
# ===========================================================================

@pytest.mark.asyncio
async def test_teams_by_location_too_short(client):
    """By-location should return empty for query shorter than 2 chars."""
    resp = await client.get("/api/me/teams/by-location?q=a")

    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_teams_by_location_returns_list(client, mock_db):
    """By-location should return list of team results."""
    resp = await client.get("/api/me/teams/by-location?q=boston")

    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_teams_by_location_requires_q_param(client):
    """By-location should require the q query parameter."""
    resp = await client.get("/api/me/teams/by-location")
    assert resp.status_code == 422


# ===========================================================================
# POST /api/me/favorites — add favorite (requires auth)
# ===========================================================================

@pytest.mark.asyncio
async def test_add_favorite_unauthenticated(client):
    """POST /favorites should return 401 without auth."""
    from app.main import app

    async def _mock_no_user():
        from fastapi import HTTPException, status
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")

    app.dependency_overrides[get_current_user] = _mock_no_user
    try:
        resp = await client.post(
            "/api/me/favorites",
            json={"team_id": 1, "relation_type": "follow"},
        )
        assert resp.status_code == 401
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_add_favorite_invalid_relation_type(client, mock_db):
    """POST /favorites should reject invalid relation_type."""
    from app.main import app

    user = _make_user()
    app.dependency_overrides[get_current_user] = lambda: user

    try:
        resp = await client.post(
            "/api/me/favorites",
            json={"team_id": 1, "relation_type": "invalid_type"},
        )
        assert resp.status_code == 400
        assert "relation_type" in resp.json()["detail"]
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_add_favorite_requires_fields(client, mock_db):
    """POST /favorites should require team_id and relation_type."""
    from app.main import app

    user = _make_user()
    app.dependency_overrides[get_current_user] = lambda: user

    try:
        resp = await client.post("/api/me/favorites", json={})
        assert resp.status_code == 422
    finally:
        app.dependency_overrides.pop(get_current_user, None)


# ===========================================================================
# DELETE /api/me/favorites/{team_id} — requires auth + relation_type param
# ===========================================================================

@pytest.mark.asyncio
async def test_remove_favorite_invalid_relation_type(client, mock_db):
    """DELETE /favorites should reject invalid relation_type."""
    from app.main import app

    user = _make_user()
    app.dependency_overrides[get_current_user] = lambda: user

    try:
        resp = await client.delete("/api/me/favorites/1?relation_type=invalid_type")
        assert resp.status_code == 400
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_remove_favorite_requires_relation_type(client, mock_db):
    """DELETE /favorites should require relation_type query param."""
    from app.main import app

    user = _make_user()
    app.dependency_overrides[get_current_user] = lambda: user

    try:
        resp = await client.delete("/api/me/favorites/1")
        assert resp.status_code == 422
    finally:
        app.dependency_overrides.pop(get_current_user, None)


# ===========================================================================
# PUT /api/me/preferences/sport-affinities — requires auth
# ===========================================================================

@pytest.mark.asyncio
async def test_update_sport_affinities_unauthenticated(client):
    """PUT /preferences/sport-affinities should return 401 without auth."""
    from app.main import app

    async def _mock_no_user():
        from fastapi import HTTPException, status
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")

    app.dependency_overrides[get_current_user] = _mock_no_user
    try:
        resp = await client.put(
            "/api/me/preferences/sport-affinities",
            json={"sport_affinities": {"basketball": 1.0}},
        )
        assert resp.status_code == 401
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_update_sport_affinities_success(client, mock_db):
    """PUT /preferences/sport-affinities should update and return ok."""
    from app.main import app

    user = _make_user()
    app.dependency_overrides[get_current_user] = lambda: user

    prefs = MagicMock()
    prefs.sport_affinities = {}
    mock_db.execute.return_value = _make_mock_result(scalar_one_or_none=prefs)

    try:
        resp = await client.put(
            "/api/me/preferences/sport-affinities",
            json={"sport_affinities": {"basketball": 1.0, "football": 0.5}},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "updated"
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_update_sport_affinities_requires_body(client, mock_db):
    """PUT /preferences/sport-affinities should reject empty body."""
    from app.main import app

    user = _make_user()
    app.dependency_overrides[get_current_user] = lambda: user

    try:
        resp = await client.put("/api/me/preferences/sport-affinities", json={})
        assert resp.status_code == 422
    finally:
        app.dependency_overrides.pop(get_current_user, None)


# ===========================================================================
# GET /api/me/team-futures — requires auth
# ===========================================================================

@pytest.mark.asyncio
async def test_team_futures_unauthenticated(client):
    """GET /team-futures should return 401 without auth."""
    from app.main import app

    async def _mock_no_user():
        from fastapi import HTTPException, status
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")

    app.dependency_overrides[get_current_user] = _mock_no_user
    try:
        resp = await client.get("/api/me/team-futures")
        assert resp.status_code == 401
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_team_futures_no_favorites(client, mock_db):
    """GET /team-futures with no followed teams returns empty."""
    from app.main import app

    user = _make_user()
    app.dependency_overrides[get_current_user] = lambda: user

    mock_db.execute.return_value = _make_mock_result(all_rows=[])

    try:
        resp = await client.get("/api/me/team-futures")
        assert resp.status_code == 200
        body = resp.json()
        assert body["items"] == []
        assert body["total_count"] == 0
    finally:
        app.dependency_overrides.pop(get_current_user, None)


# ===========================================================================
# GET /api/shared/team-futures — public (no auth)
# ===========================================================================

@pytest.mark.asyncio
async def test_shared_team_futures_requires_team_ids(client):
    """Shared team-futures should require team_ids param."""
    resp = await client.get("/api/shared/team-futures")
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_shared_team_futures_rejects_non_integer(client):
    """Shared team-futures should reject non-integer team_ids."""
    resp = await client.get("/api/shared/team-futures?team_ids=abc,def")
    assert resp.status_code == 400
    assert "integers" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_shared_team_futures_rejects_too_many(client):
    """Shared team-futures should reject more than 50 team IDs."""
    ids = ",".join(str(i) for i in range(51))
    resp = await client.get(f"/api/shared/team-futures?team_ids={ids}")
    assert resp.status_code == 400
    assert "50" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_shared_team_futures_returns_shape(client, mock_db):
    """Shared team-futures should return items/teams/total_count shape."""
    resp = await client.get("/api/shared/team-futures?team_ids=1,2,3")
    assert resp.status_code == 200
    body = resp.json()
    assert "items" in body
    assert "total_count" in body
    assert isinstance(body["items"], list)


# ===========================================================================
# Unit tests for helper functions
# ===========================================================================

def test_expand_location_query_with_aliases():
    """Location expansion should include metro aliases."""
    from app.routes.user import _expand_location_query

    terms = _expand_location_query("Boston")
    assert "boston" in terms
    assert "new england" in terms
    assert "foxborough" in terms


def test_expand_location_query_unknown_city():
    """Unknown cities should return just the original term."""
    from app.routes.user import _expand_location_query

    terms = _expand_location_query("Smallville")
    assert terms == ["smallville"]


def test_expand_sport_affinities():
    """Sport affinity expansion should map user-friendly keys to backend keys."""
    from app.routes.user import _expand_sport_affinities

    expanded = _expand_sport_affinities({"basketball": 1.0})
    assert "basketball_nba" in expanded
    assert "basketball_ncaab" in expanded
    assert expanded["basketball_nba"] == 1.0


def test_compress_sport_affinities():
    """Sport affinity compression should use split keys, not legacy."""
    from app.routes.user import _compress_sport_affinities

    compressed = _compress_sport_affinities({"basketball_nba": 1.0, "americanfootball_ncaaf": 0.5})
    assert "nba" in compressed
    assert "college_football" in compressed
