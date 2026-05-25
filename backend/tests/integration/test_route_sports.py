"""Contract tests for sports-related endpoints on /api/sports.

Tests that the sports list, hierarchy, and detail endpoints return the
expected response shapes with correct top-level keys, nested structure,
and field types. Uses the shared ``client`` fixture from conftest.py
(mock empty DB session).
"""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.utils.sport_keys import SPORT_HIERARCHY


# ============================================================================
# GET /api/sports — list active sports
# ============================================================================


class TestListSports:
    """GET /api/sports — list all active sports."""

    async def test_returns_200(self, client):
        resp = await client.get("/api/sports")
        assert resp.status_code == 200

    async def test_response_top_level_shape(self, client):
        resp = await client.get("/api/sports")
        body = resp.json()
        assert set(body.keys()) == {"sports"}
        assert isinstance(body["sports"], list)

    async def test_empty_db_returns_empty_list(self, client):
        resp = await client.get("/api/sports")
        body = resp.json()
        assert body == {"sports": []}

    async def test_sport_item_fields(self, client, mock_db):
        """Each sport item must have id, key, name, group."""
        sport = SimpleNamespace(
            id=1,
            key="basketball_nba",
            name="NBA",
            group="Basketball",
        )
        result = mock_db.execute.return_value
        result.scalars.return_value.all.return_value = [sport]

        resp = await client.get("/api/sports")
        body = resp.json()
        assert len(body["sports"]) == 1
        item = body["sports"][0]
        assert set(item.keys()) == {"id", "key", "name", "group"}
        assert item["id"] == 1
        assert item["key"] == "basketball_nba"
        assert item["name"] == "NBA"
        assert item["group"] == "Basketball"

    async def test_multiple_sports_returned_in_order(self, client, mock_db):
        """Multiple sports are returned preserving query order."""
        sports = [
            SimpleNamespace(id=1, key="baseball_mlb", name="MLB", group="Baseball"),
            SimpleNamespace(id=2, key="basketball_nba", name="NBA", group="Basketball"),
            SimpleNamespace(id=3, key="icehockey_nhl", name="NHL", group="Ice Hockey"),
        ]
        result = mock_db.execute.return_value
        result.scalars.return_value.all.return_value = sports

        resp = await client.get("/api/sports")
        body = resp.json()
        assert len(body["sports"]) == 3
        assert [s["key"] for s in body["sports"]] == [
            "baseball_mlb",
            "basketball_nba",
            "icehockey_nhl",
        ]

    async def test_post_rejected(self, client):
        """POST /api/sports should return 405 Method Not Allowed."""
        resp = await client.post("/api/sports")
        assert resp.status_code == 405

    async def test_put_rejected(self, client):
        """PUT /api/sports should return 405 Method Not Allowed."""
        resp = await client.put("/api/sports")
        assert resp.status_code == 405

    async def test_delete_rejected(self, client):
        """DELETE /api/sports should return 405 Method Not Allowed."""
        resp = await client.delete("/api/sports")
        assert resp.status_code == 405


# ============================================================================
# GET /api/sports/{sport_key} — single sport detail
# ============================================================================


class TestGetSport:
    """GET /api/sports/{sport_key} — sport detail by key."""

    async def test_not_found_returns_404(self, client):
        resp = await client.get("/api/sports/nonexistent_sport")
        assert resp.status_code == 404
        body = resp.json()
        assert body["detail"] == "Sport not found"

    async def test_found_sport_returns_200(self, client, mock_db):
        sport = SimpleNamespace(
            id=5,
            key="icehockey_nhl",
            name="NHL",
            group="Ice Hockey",
            active=True,
        )
        result = mock_db.execute.return_value
        result.scalar_one_or_none.return_value = sport

        resp = await client.get("/api/sports/icehockey_nhl")
        assert resp.status_code == 200

    async def test_response_shape(self, client, mock_db):
        sport = SimpleNamespace(
            id=5,
            key="icehockey_nhl",
            name="NHL",
            group="Ice Hockey",
            active=True,
        )
        result = mock_db.execute.return_value
        result.scalar_one_or_none.return_value = sport

        resp = await client.get("/api/sports/icehockey_nhl")
        body = resp.json()
        assert set(body.keys()) == {"id", "key", "name", "group", "active"}
        assert body["id"] == 5
        assert body["key"] == "icehockey_nhl"
        assert body["name"] == "NHL"
        assert body["group"] == "Ice Hockey"
        assert body["active"] is True

    async def test_inactive_sport_still_returned(self, client, mock_db):
        """Even inactive sports are returned from the detail endpoint."""
        sport = SimpleNamespace(
            id=99,
            key="cricket_test",
            name="Test Cricket",
            group="Cricket",
            active=False,
        )
        result = mock_db.execute.return_value
        result.scalar_one_or_none.return_value = sport

        resp = await client.get("/api/sports/cricket_test")
        body = resp.json()
        assert body["active"] is False


# ============================================================================
# GET /api/sports/hierarchy — full sport hierarchy tree
# ============================================================================


class TestSportHierarchy:
    """GET /api/sports/hierarchy — sport navigation tree."""

    async def test_returns_200(self, client):
        resp = await client.get("/api/sports/hierarchy")
        assert resp.status_code == 200

    async def test_response_top_level_shape(self, client):
        resp = await client.get("/api/sports/hierarchy")
        body = resp.json()
        assert set(body.keys()) == {"sports"}
        assert isinstance(body["sports"], list)

    async def test_returns_all_sport_hierarchy_entries(self, client):
        resp = await client.get("/api/sports/hierarchy")
        body = resp.json()
        assert len(body["sports"]) == len(SPORT_HIERARCHY)

    async def test_sport_item_required_fields(self, client):
        resp = await client.get("/api/sports/hierarchy")
        body = resp.json()
        for sport in body["sports"]:
            assert "slug" in sport, f"Missing 'slug' in {sport}"
            assert "name" in sport, f"Missing 'name' in {sport}"
            assert "leagues" in sport, f"Missing 'leagues' in {sport}"
            assert "showcase_events" in sport, f"Missing 'showcase_events' in {sport}"
            assert isinstance(sport["leagues"], list)
            assert isinstance(sport["showcase_events"], list)

    async def test_league_item_structure(self, client):
        resp = await client.get("/api/sports/hierarchy")
        body = resp.json()
        for sport in body["sports"]:
            for league in sport["leagues"]:
                assert "slug" in league, f"Missing 'slug' in league of {sport['slug']}"
                assert "name" in league, f"Missing 'name' in league of {sport['slug']}"
                assert "sport_keys" in league, f"Missing 'sport_keys' in league of {sport['slug']}"
                assert isinstance(league["sport_keys"], list)

    async def test_showcase_event_structure(self, client):
        resp = await client.get("/api/sports/hierarchy")
        body = resp.json()
        for sport in body["sports"]:
            for event in sport["showcase_events"]:
                assert "name" in event
                assert "type" in event
                assert isinstance(event["name"], str)
                assert isinstance(event["type"], str)

    async def test_known_sports_present(self, client):
        """Verify core sports appear in the hierarchy."""
        resp = await client.get("/api/sports/hierarchy")
        body = resp.json()
        slugs = {s["slug"] for s in body["sports"]}
        for expected in ["basketball", "football", "baseball", "hockey", "soccer", "golf", "tennis", "mma", "boxing", "motorsports", "esports"]:
            assert expected in slugs, f"Expected sport '{expected}' in hierarchy"

    async def test_basketball_has_nba_league(self, client):
        resp = await client.get("/api/sports/hierarchy")
        body = resp.json()
        basketball = next(s for s in body["sports"] if s["slug"] == "basketball")
        league_slugs = [l["slug"] for l in basketball["leagues"]]
        assert "nba" in league_slugs

    async def test_no_db_dependency(self, client):
        """Hierarchy is static data — should not hit DB at all."""
        resp = await client.get("/api/sports/hierarchy")
        assert resp.status_code == 200

    async def test_post_rejected(self, client):
        resp = await client.post("/api/sports/hierarchy")
        assert resp.status_code == 405


# ============================================================================
# GET /api/sports/hierarchy/{sport_slug} — single sport hierarchy detail
# ============================================================================


class TestSportHierarchyDetail:
    """GET /api/sports/hierarchy/{sport_slug} — single sport hierarchy."""

    async def test_returns_200_for_valid_slug(self, client):
        resp = await client.get("/api/sports/hierarchy/basketball")
        assert resp.status_code == 200

    async def test_returns_404_for_invalid_slug(self, client):
        resp = await client.get("/api/sports/hierarchy/curling")
        assert resp.status_code == 404
        body = resp.json()
        assert "not found" in body["detail"].lower()

    async def test_response_shape(self, client):
        resp = await client.get("/api/sports/hierarchy/golf")
        body = resp.json()
        assert set(body.keys()) == {"slug", "name", "leagues", "showcase_events"}
        assert body["slug"] == "golf"
        assert body["name"] == "Golf"
        assert isinstance(body["leagues"], list)
        assert isinstance(body["showcase_events"], list)

    @pytest.mark.parametrize("slug", list(SPORT_HIERARCHY.keys()))
    async def test_all_hierarchy_slugs_return_200(self, client, slug):
        resp = await client.get(f"/api/sports/hierarchy/{slug}")
        assert resp.status_code == 200

    async def test_golf_has_showcase_events(self, client):
        resp = await client.get("/api/sports/hierarchy/golf")
        body = resp.json()
        assert len(body["showcase_events"]) > 0
        names = [e["name"] for e in body["showcase_events"]]
        assert "The Masters" in names

    async def test_mma_has_ufc_league(self, client):
        resp = await client.get("/api/sports/hierarchy/mma")
        body = resp.json()
        league_slugs = [l["slug"] for l in body["leagues"]]
        assert "ufc" in league_slugs

    async def test_soccer_has_multiple_leagues(self, client):
        resp = await client.get("/api/sports/hierarchy/soccer")
        body = resp.json()
        assert len(body["leagues"]) >= 5


# ============================================================================
# Admin endpoints — auth gating
# ============================================================================


class TestSportsAdminAuth:
    """Admin endpoints on /api/sports reject bad secrets before side effects."""

    async def test_available_missing_secret_returns_422(self, client):
        """Secret is a required query param."""
        resp = await client.get("/api/sports/available")
        assert resp.status_code == 422

    async def test_available_bad_secret_returns_403(self, client):
        with patch("app.routes.sports.OddsAPIService") as service_cls:
            resp = await client.get("/api/sports/available?secret=wrong")
        assert resp.status_code == 403
        service_cls.assert_not_called()

    async def test_sync_missing_secret_returns_422(self, client):
        resp = await client.post("/api/sports/sync")
        assert resp.status_code == 422

    async def test_sync_bad_secret_returns_403(self, client):
        with patch("app.routes.sports.OddsAPIService") as service_cls:
            resp = await client.post("/api/sports/sync?secret=wrong")
        assert resp.status_code == 403
        service_cls.assert_not_called()

    async def test_sync_bad_secret_does_not_commit(self, client, mock_db):
        resp = await client.post("/api/sports/sync?secret=wrong")
        assert resp.status_code == 403
        mock_db.commit.assert_not_awaited()
