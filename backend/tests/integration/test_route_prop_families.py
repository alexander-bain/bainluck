"""Contract tests for Prop Families API: GET /api/teams/{identifier}/prop-families.

Verifies the endpoint returns the expected response shape, groups seeded
prop markets into families, and 404s for unknown teams. Uses the shared
mock_db / client fixtures from integration/conftest.py.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock


def _scalars_result(items):
    """Mock result with .scalars().first()/all() and .all() for row tuples."""
    result = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = items
    scalars.first.return_value = items[0] if items else None
    scalars.unique.return_value = scalars
    result.scalars.return_value = scalars
    result.all.return_value = items
    result.first.return_value = items[0] if items else None
    return result


def _mock_team(*, team_id=42, slug="lakers", name="Los Angeles Lakers"):
    return SimpleNamespace(
        id=team_id, slug=slug, name=name, roster_players=[],
    )


def _outcome(oid, name, prob, is_winner=False):
    return SimpleNamespace(
        id=oid, name=name, current_probability=prob, is_winner=is_winner,
    )


def _market(mid, name, *, source="kalshi", group_id=None, status="open"):
    return SimpleNamespace(
        id=mid, name=name, source=source, group_id=group_id, status=status,
        resolution_date=None, market_metadata=None,
    )


class TestPropFamiliesNotFound:
    async def test_returns_404_for_unknown_team(self, client):
        resp = await client.get("/api/teams/nonexistent/prop-families")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Team not found"


class TestPropFamiliesSeeded:
    async def test_returns_grouped_family(self, client, mock_db):
        team = _mock_team()
        m1 = _market(1, "LeBron James Next Team")
        m2 = _market(2, "Kevin Durant Next Team")
        rows = [
            (_outcome(11, "Lakers", 0.4), m1),
            (_outcome(12, "Warriors", 0.2), m1),
            (_outcome(21, "Suns", 0.5), m2),
            (_outcome(22, "Rockets", 0.1), m2),
        ]
        mock_db.execute.side_effect = [
            _scalars_result([team]),   # team lookup
            _scalars_result(rows),     # outcomes + markets query
        ]

        resp = await client.get("/api/teams/lakers/prop-families")
        assert resp.status_code == 200
        body = resp.json()
        assert set(body.keys()) == {"team", "families", "total_families"}
        assert body["team"]["id"] == 42
        assert body["total_families"] == 1
        fam = body["families"][0]
        assert fam["family_key"] == "next team"
        assert fam["entity_count"] == 2
        assert isinstance(fam["rows"], list)
        assert {r["entity"] for r in fam["rows"]} == {"Lebron James", "Kevin Durant"}

    async def test_empty_when_no_markets(self, client, mock_db):
        team = _mock_team()
        mock_db.execute.side_effect = [
            _scalars_result([team]),
            _scalars_result([]),
        ]
        resp = await client.get("/api/teams/42/prop-families")
        assert resp.status_code == 200
        body = resp.json()
        assert body["families"] == []
        assert body["total_families"] == 0


class TestPropFamiliesHTTP:
    async def test_rejects_post(self, client):
        resp = await client.post("/api/teams/lakers/prop-families")
        assert resp.status_code == 405
