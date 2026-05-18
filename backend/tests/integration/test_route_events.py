"""Contract tests for event endpoints.

- GET /api/events — event list
- GET /api/events/{id} — event detail
- GET /api/events/{id}/related-futures — related futures for event
- GET /api/events/search — event search
"""

import pytest


class TestEventList:
    """GET /api/events — list of events."""

    async def test_returns_200(self, client):
        resp = await client.get("/api/events")
        assert resp.status_code == 200

    async def test_response_envelope_for_empty_db(self, client):
        resp = await client.get("/api/events")
        body = resp.json()
        assert set(body.keys()) == {"events", "count"}
        assert body["events"] == []
        assert body["count"] == 0

    async def test_sport_filter_accepted(self, client):
        resp = await client.get("/api/events?sport=basketball_nba")
        assert resp.status_code == 200

    async def test_status_filter_accepted(self, client):
        resp = await client.get("/api/events?status=live")
        assert resp.status_code == 200

    async def test_limit_param_accepted(self, client):
        resp = await client.get("/api/events?limit=5")
        assert resp.status_code == 200

    async def test_invalid_days_type_returns_422(self, client):
        resp = await client.get("/api/events?days=soon")
        assert resp.status_code == 422


class TestLiveEvents:
    """GET /api/events/live — live event list."""

    async def test_empty_db_returns_envelope(self, client):
        resp = await client.get("/api/events/live")
        assert resp.status_code == 200
        assert resp.json() == {"events": [], "count": 0}


class TestEventSearch:
    """GET /api/events/search — search by query string."""

    async def test_missing_query_returns_422(self, client):
        resp = await client.get("/api/events/search")
        assert resp.status_code == 422

    async def test_with_query_returns_200(self, client):
        resp = await client.get("/api/events/search?q=celtics")
        assert resp.status_code == 200

    async def test_empty_db_returns_full_envelope(self, client):
        resp = await client.get("/api/events/search?q=celtics")
        body = resp.json()
        assert body["query"] == "celtics"
        assert body["teams"] == []
        assert body["results"] == []
        assert body["futures"] == []
        assert body["sports"] == []
        assert body["pagination"] == {
            "page": 1,
            "per_page": 25,
            "total_results": 0,
            "total_pages": 0,
            "has_next": False,
            "has_prev": False,
        }
        assert body["filters"] == {
            "sport": None,
            "days_back": 30,
            "include_upcoming": True,
        }

    @pytest.mark.parametrize(
        "query",
        [
            "q=x",
            "q=celtics&page=0",
            "q=celtics&per_page=0",
            "q=celtics&per_page=101",
            "q=celtics&days_back=0",
            "q=celtics&days_back=366",
        ],
    )
    async def test_invalid_params_return_422(self, client, query):
        resp = await client.get(f"/api/events/search?{query}")
        assert resp.status_code == 422


class TestEventTypeahead:
    """GET /api/events/typeahead — lightweight search suggestions."""

    async def test_empty_db_returns_suggestions_envelope(self, client):
        resp = await client.get("/api/events/typeahead?q=celtics")
        assert resp.status_code == 200
        assert resp.json() == {"suggestions": [], "query": "celtics"}

    @pytest.mark.parametrize("q", ["x", ""])
    async def test_short_query_returns_422(self, client, q):
        resp = await client.get(f"/api/events/typeahead?q={q}")
        assert resp.status_code == 422


class TestFacetedEvents:
    """GET /api/events/faceted — faceted event search."""

    async def test_empty_db_returns_envelope(self, client):
        resp = await client.get("/api/events/faceted")
        body = resp.json()
        assert resp.status_code == 200
        assert body == {
            "total": 0,
            "page": 1,
            "per_page": 25,
            "filters": [],
            "events": [],
            "facets": {},
        }

    @pytest.mark.parametrize("query", ["days=0", "days=31", "page=0", "per_page=0", "per_page=101"])
    async def test_invalid_params_return_422(self, client, query):
        resp = await client.get(f"/api/events/faceted?{query}")
        assert resp.status_code == 422


class TestEventHighlights:
    """GET /api/events/highlights — completed event highlights."""

    async def test_empty_db_returns_envelope(self, client):
        resp = await client.get("/api/events/highlights")
        body = resp.json()
        assert resp.status_code == 200
        assert body == {
            "highlights": [],
            "filters": {
                "sport": None,
                "days": 7,
                "min_percentile": 75,
            },
            "count": 0,
        }


class TestEventEiRankings:
    """GET /api/events/ei-rankings — all-time EI rankings."""

    async def test_empty_db_returns_envelope(self, client):
        resp = await client.get("/api/events/ei-rankings")
        body = resp.json()
        assert resp.status_code == 200
        assert body == {
            "highest": [],
            "lowest": [],
            "filters": {
                "sport": None,
                "limit": 25,
            },
        }

    @pytest.mark.parametrize("limit", [0, 101])
    async def test_invalid_limit_returns_422(self, client, limit):
        resp = await client.get(f"/api/events/ei-rankings?limit={limit}")
        assert resp.status_code == 422


class TestLiveOdds:
    """GET /api/events/live-odds/{sport_key} — direct live odds fetch."""

    async def test_empty_fetch_returns_envelope(self, client, monkeypatch):
        async def _mock_fetch_current_odds(sport_key):
            assert sport_key == "basketball_nba"
            return []

        monkeypatch.setattr(
            "app.routes.events.fetch_current_odds",
            _mock_fetch_current_odds,
        )

        resp = await client.get("/api/events/live-odds/basketball_nba")
        assert resp.status_code == 200
        assert resp.json() == {
            "sport": "basketball_nba",
            "events": [],
            "count": 0,
        }

    async def test_fetch_error_returns_503(self, client, monkeypatch):
        async def _mock_fetch_current_odds(sport_key):
            raise RuntimeError("provider unavailable")

        monkeypatch.setattr(
            "app.routes.events.fetch_current_odds",
            _mock_fetch_current_odds,
        )

        resp = await client.get("/api/events/live-odds/basketball_nba")
        body = resp.json()
        assert resp.status_code == 503
        assert body["detail"] == "Unable to fetch odds: provider unavailable"


class TestEventDetail404:

    async def test_nonexistent_event_returns_404(self, client):
        resp = await client.get("/api/events/999999")
        assert resp.status_code == 404

    async def test_404_body_has_detail(self, client):
        resp = await client.get("/api/events/999999")
        body = resp.json()
        assert "detail" in body
        assert body["detail"] == "Event not found"

    async def test_invalid_id_type_returns_422(self, client):
        resp = await client.get("/api/events/not-a-number")
        assert resp.status_code == 422

    async def test_zero_id_returns_404(self, client):
        resp = await client.get("/api/events/0")
        assert resp.status_code == 404

    async def test_negative_id_returns_404_or_422(self, client):
        resp = await client.get("/api/events/-1")
        assert resp.status_code in (404, 422)


class TestRelatedFutures404:

    async def test_nonexistent_event_returns_404(self, client):
        resp = await client.get("/api/events/999999/related-futures")
        assert resp.status_code == 404

    async def test_invalid_id_returns_422(self, client):
        resp = await client.get("/api/events/abc/related-futures")
        assert resp.status_code == 422


class TestEventOddsHistory:
    """GET /api/events/{id}/history — odds history for charting."""

    async def test_nonexistent_event_returns_404(self, client):
        resp = await client.get("/api/events/999999/history")
        assert resp.status_code == 404

    async def test_invalid_id_returns_422(self, client):
        resp = await client.get("/api/events/abc/history")
        assert resp.status_code == 422
