"""Contract tests for Team Detail API: GET /api/teams/{identifier}.

Tests the team detail endpoint returns the expected response shape with
correct top-level keys and nested structure, and that 404 is returned
for non-existent teams.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, AsyncMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _scalars_result(items):
    """Build a mock result with .scalars().first()/all() returning items."""
    result = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = items
    scalars.first.return_value = items[0] if items else None
    scalars.unique.return_value = scalars
    result.scalars.return_value = scalars
    result.all.return_value = items
    result.first.return_value = items[0] if items else None
    return result


def _mock_sport(*, sport_id=1, key="basketball_nba", name="NBA"):
    return SimpleNamespace(id=sport_id, key=key, name=name)


def _mock_team(
    *, team_id=42, slug="lakers", name="Los Angeles Lakers",
    abbreviation="LAL", location="Los Angeles",
    sport=None,
):
    return SimpleNamespace(
        id=team_id,
        slug=slug,
        name=name,
        abbreviation=abbreviation,
        location=location,
        sport=sport or _mock_sport(),
        primary_color="#552583",
        secondary_color="#FDB927",
        logo_url_small="https://example.test/lal-sm.png",
        logo_url_large="https://example.test/lal-lg.png",
        current_record="52-30",
        standings_data={"rank": 3},
        season_stats={"ppg": 115.2},
        roster_players=[],
    )


# ============================================================================
# GET /api/teams/{identifier} — team not found
# ============================================================================


class TestTeamNotFound:
    """GET /api/teams/{identifier} when team does not exist."""

    async def test_returns_404_for_unknown_slug(self, client):
        resp = await client.get("/api/teams/nonexistent-team")
        assert resp.status_code == 404

    async def test_returns_404_for_unknown_id(self, client):
        resp = await client.get("/api/teams/99999")
        assert resp.status_code == 404

    async def test_404_body_has_detail(self, client):
        resp = await client.get("/api/teams/nonexistent-team")
        body = resp.json()
        assert "detail" in body
        assert body["detail"] == "Team not found"


# ============================================================================
# GET /api/teams/{identifier} — with seeded team data
# ============================================================================


class TestTeamSeeded:
    """GET /api/teams/{identifier} with mock team data."""

    async def test_returns_200_for_existing_team(self, client, mock_db):
        team = _mock_team()
        # First execute: team lookup returns the team
        # Subsequent executes: upcoming events, recent events, futures, championship path
        mock_db.execute.side_effect = [
            _scalars_result([team]),     # team query
            _scalars_result([]),         # upcoming events
            _scalars_result([]),         # recent events
            _scalars_result([]),         # team futures (_query_team_futures)
            _scalars_result([]),         # championship path
        ]

        resp = await client.get("/api/teams/lakers")
        assert resp.status_code == 200

    async def test_has_top_level_keys(self, client, mock_db):
        team = _mock_team()
        mock_db.execute.side_effect = [
            _scalars_result([team]),
            _scalars_result([]),
            _scalars_result([]),
            _scalars_result([]),
            _scalars_result([]),
        ]

        resp = await client.get("/api/teams/lakers")
        body = resp.json()
        assert "team" in body
        assert "upcoming_events" in body
        assert "recent_events" in body
        assert "futures" in body
        assert "championship_path" in body

    async def test_team_object_shape(self, client, mock_db):
        team = _mock_team()
        mock_db.execute.side_effect = [
            _scalars_result([team]),
            _scalars_result([]),
            _scalars_result([]),
            _scalars_result([]),
            _scalars_result([]),
        ]

        resp = await client.get("/api/teams/42")
        body = resp.json()
        t = body["team"]
        expected_keys = {
            "id", "slug", "name", "abbreviation", "sport_key", "sport_name",
            "location", "primary_color", "secondary_color",
            "logo_small", "logo_large", "record", "standings",
            "season_stats", "roster",
        }
        assert expected_keys.issubset(set(t.keys())), (
            f"Missing keys: {expected_keys - set(t.keys())}"
        )
        assert t["id"] == 42
        assert t["slug"] == "lakers"
        assert t["name"] == "Los Angeles Lakers"
        assert t["abbreviation"] == "LAL"
        assert t["sport_key"] == "basketball_nba"
        assert t["sport_name"] == "NBA"

    async def test_event_lists_are_lists(self, client, mock_db):
        team = _mock_team()
        mock_db.execute.side_effect = [
            _scalars_result([team]),
            _scalars_result([]),
            _scalars_result([]),
            _scalars_result([]),
            _scalars_result([]),
        ]

        resp = await client.get("/api/teams/lakers")
        body = resp.json()
        assert isinstance(body["upcoming_events"], list)
        assert isinstance(body["recent_events"], list)
        assert isinstance(body["futures"], list)
        assert isinstance(body["championship_path"], list)


# ============================================================================
# HTTP behavior
# ============================================================================


class TestTeamHTTPBehavior:
    """General HTTP contract checks."""

    async def test_rejects_post(self, client):
        resp = await client.post("/api/teams/lakers")
        assert resp.status_code == 405
