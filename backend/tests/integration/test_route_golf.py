"""Contract tests for golf endpoints.

- GET /api/golf — golf landing page
- GET /api/playoffs/golf — golf championship grid
"""

import pytest


@pytest.fixture(autouse=True)
def no_datagolf_network(monkeypatch):
    """Keep golf route contract tests independent from DataGolf/API state."""
    from app.routes import golf, playoffs

    async def _empty_schedule():
        return []

    async def _no_datagolf_grid(*args, **kwargs):
        return None

    monkeypatch.setattr(golf, "_get_golf_schedule", _empty_schedule)
    monkeypatch.setattr(playoffs, "_build_golf_grid_from_datagolf", _no_datagolf_grid)


class TestGolfLandingPage:
    """GET /api/golf — main golf data."""

    async def test_returns_200(self, client):
        resp = await client.get("/api/golf")
        assert resp.status_code == 200

    async def test_empty_db_response_has_required_keys(self, client):
        resp = await client.get("/api/golf")
        body = resp.json()

        for key in [
            "tournaments",
            "biggest_movers",
            "upcoming_events",
            "current_event",
            "total_tournaments",
            "total_golfers",
            "pga_schedule",
        ]:
            assert key in body, f"Missing key: {key}"

    async def test_empty_db_response_shape_is_deterministic(self, client):
        resp = await client.get("/api/golf")
        body = resp.json()

        assert body["tournaments"] == []
        assert body["biggest_movers"] == []
        assert body["upcoming_events"] == []
        assert body["current_event"] is None
        assert body["total_tournaments"] == 0
        assert body["total_golfers"] == 0
        assert body["pga_schedule"] is None


class TestGolfTournamentDetail:
    """GET /api/golf/tournaments/{slug} — tournament detail contract."""

    async def test_tournament_detail_uses_aggregated_golf_shape(self, client, monkeypatch):
        from app.routes import golf

        async def _mock_get_golf(db):
            return {
                "tournaments": [
                    {
                        "name": "The Masters",
                        "slug": "masters",
                        "key": "masters",
                        "is_major": True,
                        "is_womens": False,
                        "start_date": "2026-04-09T00:00:00+00:00",
                        "end_date": "2026-04-12T00:00:00+00:00",
                        "venue": "Augusta National",
                        "location": "Augusta, GA",
                        "schedule_status": "upcoming",
                        "commence_time": "2026-04-09T00:00:00+00:00",
                        "resolution_date": "2026-04-12T00:00:00+00:00",
                        "golfers": [
                            {
                                "name": "Scottie Scheffler",
                                "win_prob": 18.4,
                                "sources": ["datagolf"],
                            }
                        ],
                        "market_ids": [],
                        "market_names": [],
                        "h2h_matchups": [
                            {
                                "market_id": 42,
                                "market_name": "Scottie Scheffler vs Rory McIlroy",
                                "golfers": [],
                            }
                        ],
                    }
                ],
                "biggest_movers": [
                    {
                        "name": "Scottie Scheffler",
                        "tournament_key": "masters",
                        "probability_change": 2.5,
                    },
                    {
                        "name": "Other Golfer",
                        "tournament_key": "pga_championship",
                        "probability_change": 1.1,
                    },
                ],
            }

        monkeypatch.setattr(golf, "get_golf", _mock_get_golf)

        resp = await client.get("/api/golf/tournaments/masters")
        assert resp.status_code == 200
        body = resp.json()

        for key in [
            "tournament",
            "golfers",
            "markets",
            "related_futures",
            "evolution_market_id",
            "biggest_movers",
            "h2h_matchups",
        ]:
            assert key in body, f"Missing key: {key}"

        assert body["tournament"]["name"] == "The Masters"
        assert body["tournament"]["slug"] == "masters"
        assert body["tournament"]["is_major"] is True
        assert body["golfers"][0]["name"] == "Scottie Scheffler"
        assert body["markets"] == []
        assert body["related_futures"] == []
        assert body["evolution_market_id"] is None
        assert body["biggest_movers"] == [
            {
                "name": "Scottie Scheffler",
                "tournament_key": "masters",
                "probability_change": 2.5,
            }
        ]
        assert body["h2h_matchups"][0]["market_id"] == 42

    async def test_unknown_tournament_returns_404(self, client, monkeypatch):
        from app.routes import golf

        async def _mock_get_golf(db):
            return {"tournaments": [], "biggest_movers": []}

        async def _mock_completed_tournament(slug, db):
            return None

        monkeypatch.setattr(golf, "get_golf", _mock_get_golf)
        monkeypatch.setattr(golf, "_build_completed_tournament", _mock_completed_tournament)

        resp = await client.get("/api/golf/tournaments/not-real")
        assert resp.status_code == 404
        assert "not-real" in resp.json()["detail"]


class TestGolfGrid:
    """GET /api/playoffs/golf — golf championship grid."""

    async def test_returns_200(self, client):
        resp = await client.get("/api/playoffs/golf")
        assert resp.status_code == 200

    async def test_datagolf_grid_response_shape(self, client, monkeypatch):
        from app.routes import playoffs

        async def _mock_datagolf_grid(config, db, trend_hours, top):
            return {
                "league": "golf",
                "name": "PGA Tour",
                "season": "2026",
                "tournament": {
                    "name": "The Masters",
                    "status": "upcoming",
                },
                "columns": [
                    {"key": "win", "label": "Win"},
                ],
                "trend_chart": {"timeline": [], "outcomes": []},
                "teams": [
                    {
                        "name": "Scottie Scheffler",
                        "columns": {},
                    },
                ],
                "grouped_teams": None,
                "movers": [],
                "team_count": 1,
                "field_count": 1,
                "last_updated": "2026-04-01T00:00:00+00:00",
                "sources_available": ["datagolf"],
                "source_of_truth": "datagolf",
                "events": [
                    {
                        "tour": "pga",
                        "tour_name": "PGA Tour",
                        "tournament": {"name": "The Masters"},
                        "teams": [],
                    },
                ],
            }

        monkeypatch.setattr(playoffs, "_build_golf_grid_from_datagolf", _mock_datagolf_grid)

        resp = await client.get("/api/playoffs/golf")
        assert resp.status_code == 200
        body = resp.json()

        for key in [
            "league",
            "name",
            "season",
            "tournament",
            "columns",
            "trend_chart",
            "teams",
            "grouped_teams",
            "movers",
            "team_count",
            "field_count",
            "last_updated",
            "sources_available",
            "source_of_truth",
            "events",
        ]:
            assert key in body, f"Missing key: {key}"

        assert body["league"] == "golf"
        assert body["source_of_truth"] == "datagolf"
        assert body["team_count"] == len(body["teams"])
        assert body["field_count"] == 1
        assert body["events"][0]["tour"] == "pga"
