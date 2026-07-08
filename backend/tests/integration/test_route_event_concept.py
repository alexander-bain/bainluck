"""#999 slice 1: GET /api/event/{key} — generic event-concept endpoint.

Golf delegates to the existing get_golf_tournament aggregation (parity bar). We
patch that function so the test proves the ENDPOINT WIRING + generic envelope
shape without the heavy golf DB path (which is covered by the golf route's own
tests)."""

import pytest


def _golf_detail():
    return {
        "tournament": {
            "name": "The Open Championship",
            "key": "open_championship",
            "is_major": True,
            "start_date": "2026-07-16",
            "end_date": "2026-07-19",
            "venue": "Royal Birkdale",
            "location": "England",
            "schedule_status": "in_progress",
        },
        "golfers": [{"name": "Scottie Scheffler", "probability": 0.20}],
        "markets": [{"type": "winner", "label": "Winner", "market_ids": [1]}],
        "related_futures": [{"market_id": 9, "market_name": "H2H: X vs Y"}],
        "evolution_market_id": 1,
        "biggest_movers": [],
    }


class TestEventConceptRoute:
    async def test_golf_event_parity_envelope(self, client, monkeypatch):
        async def _fake_get_golf_tournament(slug, db):
            assert slug == "open-championship"
            return _golf_detail()

        monkeypatch.setattr("app.routes.golf.get_golf_tournament", _fake_get_golf_tournament)

        resp = await client.get("/api/event/event:golf:open-championship")
        assert resp.status_code == 200
        body = resp.json()
        assert body["event"]["domain"] == "golf"
        assert body["event"]["name"] == "The Open Championship"
        assert body["event"]["status"] == "live"          # in_progress -> live
        assert body["primary"]["kind"] == "winner_field"
        assert body["primary"]["competitors"][0]["name"] == "Scottie Scheffler"
        assert body["sections"][0]["type"] == "winner"
        assert body["children"][0]["market_name"] == "H2H: X vs Y"

    async def test_unknown_event_404(self, client, monkeypatch):
        async def _none(slug, db):
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="not found")

        monkeypatch.setattr("app.routes.golf.get_golf_tournament", _none)
        resp = await client.get("/api/event/event:golf:does-not-exist")
        assert resp.status_code == 404

    async def test_unknown_domain_404(self, client):
        # no tennis adapter yet (future slice) -> 404, not a crash
        resp = await client.get("/api/event/event:tennis:wimbledon-2026")
        assert resp.status_code == 404

    async def test_rejects_post(self, client):
        resp = await client.post("/api/event/event:golf:x")
        assert resp.status_code == 405


def _tennis_outcome(name, prob):
    from types import SimpleNamespace
    return SimpleNamespace(name=name, current_probability=prob)


def _tennis_winner_market():
    from types import SimpleNamespace
    from datetime import datetime, timezone, timedelta
    return SimpleNamespace(
        id=114157,
        name="2026 Wimbledon Winner",
        status="open",
        llm_sport_category="tennis",
        source="polymarket",
        group_id="polymarket:139182",
        resolution_date=datetime.now(timezone.utc) + timedelta(days=4),
        outcomes=[
            # independent binaries that sum >100% (the real Wimbledon case) —
            # must be #23-normalized after the "Other" field remainder is dropped.
            _tennis_outcome("Coco Gauff", 0.45),
            _tennis_outcome("Aryna Sabalenka", 0.40),
            _tennis_outcome("Karolína Muchová", 0.35),
            _tennis_outcome("Other", 0.10),  # field remainder — must be dropped
        ],
    )


class TestTennisEventAdapter:
    """#999 slice 2: tennis winner-field renders through the same envelope."""

    async def test_tennis_winner_field(self, client, mock_db):
        from tests.integration.test_route_weather import _query_result  # mock result
        mock_db.execute.return_value = _query_result([_tennis_winner_market()])

        resp = await client.get("/api/event/event:tennis:2026-wimbledon-winner")
        assert resp.status_code == 200
        body = resp.json()
        assert body["event"]["domain"] == "tennis"
        assert body["event"]["name"] == "2026 Wimbledon Winner"
        assert body["event"]["status"] == "live"  # resolves in 4 days
        assert body["primary"]["kind"] == "winner_field"
        comps = body["primary"]["competitors"]
        names = [c["name"] for c in comps]
        assert names == ["Coco Gauff", "Aryna Sabalenka", "Karolína Muchová"]  # sorted, "Other" dropped
        # #23 normalization: the >100% field is scaled to sum ~1.0 (L2-61).
        assert abs(sum(c["probability"] for c in comps) - 1.0) < 0.02
        assert body["sections"][0]["type"] == "winner"

    async def test_tennis_no_markets_404(self, client, mock_db):
        from tests.integration.test_route_weather import _query_result
        mock_db.execute.return_value = _query_result([])
        resp = await client.get("/api/event/event:tennis:2026-wimbledon-winner")
        assert resp.status_code == 404
