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


def _tennis_winner(id_, name, players, source="polymarket", group_id=None):
    from types import SimpleNamespace
    from datetime import datetime, timezone, timedelta
    return SimpleNamespace(
        id=id_,
        name=name,
        status="open",
        llm_sport_category="tennis",
        source=source,
        group_id=group_id or f"{source}:{id_}",
        resolution_date=datetime.now(timezone.utc) + timedelta(days=4),
        outcomes=[_tennis_outcome(n, p) for n, p in players],
    )


class TestTennisCanonicalResolution:
    """L2-65 Item 2: a slug resolves to the RICHEST winner field for the event,
    and a gendered slug never crosses to the opposite gender."""

    async def test_richest_market_wins(self, client, mock_db):
        from tests.integration.test_route_weather import _query_result
        sparse = _tennis_winner(
            1, "Wimbledon Women's Singles Winner",
            [("Aryna Sabalenka", 0.6)], source="kalshi",
        )
        rich = _tennis_winner(
            2, "2026 Women's Wimbledon Winner",
            [("Aryna Sabalenka", 0.30), ("Coco Gauff", 0.28),
             ("Iga Swiatek", 0.22), ("Elena Rybakina", 0.20)],
            source="polymarket",
        )
        mock_db.execute.return_value = _query_result([sparse, rich])

        # Bare slug -> the richer (Polymarket, 4-player) field, not the sparse one.
        resp = await client.get("/api/event/event:tennis:wimbledon")
        assert resp.status_code == 200
        body = resp.json()
        assert body["event"]["name"] == "2026 Women's Wimbledon Winner"
        assert len(body["primary"]["competitors"]) == 4
        # Canonical key reported from the winning market's name (links converge).
        assert body["event"]["key"] == "event:tennis:2026-women-s-wimbledon-winner"

    async def test_gendered_slug_does_not_cross(self, client, mock_db):
        from tests.integration.test_route_weather import _query_result
        womens = _tennis_winner(
            1, "2026 Women's Wimbledon Winner",
            [("Aryna Sabalenka", 0.3), ("Coco Gauff", 0.3), ("Iga Swiatek", 0.3)],
        )
        mens = _tennis_winner(
            2, "2026 Men's Wimbledon Winner",
            [("Carlos Alcaraz", 0.5), ("Jannik Sinner", 0.4)],
        )
        mock_db.execute.return_value = _query_result([womens, mens])

        # A men's slug must land on the men's field even though it is sparser.
        resp = await client.get("/api/event/event:tennis:wimbledon-men-s-singles-winner")
        assert resp.status_code == 200
        body = resp.json()
        assert body["event"]["name"] == "2026 Men's Wimbledon Winner"
        names = [c["name"] for c in body["primary"]["competitors"]]
        assert "Carlos Alcaraz" in names
        assert "Coco Gauff" not in names


def _f1_market(id_, name, ext, players, source="kalshi", rd_days=3):
    from types import SimpleNamespace
    from datetime import datetime, timezone, timedelta
    return SimpleNamespace(
        id=id_, name=name, external_id=ext, status="open",
        llm_sport_category="motorsports", source=source, group_id=None,
        commence_time=None,
        resolution_date=datetime.now(timezone.utc) + timedelta(days=rd_days),
        outcomes=[_tennis_outcome(n, p) for n, p in players],
    )


class TestF1EventAdapter:
    """#999 L2-72: F1 winner-field (motorsports) renders through the envelope."""

    async def test_f1_winner_field(self, client, mock_db):
        from tests.integration.test_route_weather import _query_result
        winner = _f1_market(
            1, "British Grand Prix Winner", "KXF1RACE-BRIGP26",
            [("Lando Norris", 0.35), ("Max Verstappen", 0.30), ("Charles Leclerc", 0.20)],
        )
        sprint = _f1_market(
            2, "British Grand Prix: Sprint Race Winner", "KXF1RACESPRINT-BRIGP26",
            [("Max Verstappen", 0.4), ("Lando Norris", 0.35)],
        )
        mock_db.execute.return_value = _query_result([winner, sprint])
        resp = await client.get("/api/event/event:f1:british-grand-prix")
        assert resp.status_code == 200
        body = resp.json()
        assert body["event"]["domain"] == "f1"
        assert body["primary"]["kind"] == "winner_field"
        names = [c["name"] for c in body["primary"]["competitors"]]
        assert "Lando Norris" in names
        # the sprint sub-market folds in as a child, not the primary
        assert any("Sprint" in (c.get("market_name") or "") for c in body["children"])

    async def test_f1_no_markets_404(self, client, mock_db):
        from tests.integration.test_route_weather import _query_result
        mock_db.execute.return_value = _query_result([])
        resp = await client.get("/api/event/event:f1:british-grand-prix")
        assert resp.status_code == 404


def _ufc_fight(id_, name, ext, a, b, ct_hours=2):
    from types import SimpleNamespace
    from datetime import datetime, timezone, timedelta
    return SimpleNamespace(
        id=id_, name=name, external_id=ext, status="open",
        llm_sport_category="mma", source="kalshi", group_id=None,
        commence_time=datetime.now(timezone.utc) + timedelta(hours=ct_hours),
        resolution_date=None,
        outcomes=[_tennis_outcome(a[0], a[1]), _tennis_outcome(b[0], b[1])],
    )


class TestUFCEventAdapter:
    """#999 L2-72: UFC card renders as co_equal_list (the TwoSidedTimeline variant)."""

    async def test_ufc_co_equal_card(self, client, mock_db):
        from tests.integration.test_route_weather import _query_result
        f1 = _ufc_fight(
            101, "Fight Night: Collins vs Tanzilovi",
            "kalshi:KXUFCFIGHT-26JUN20COLTAN", ("Collins", 0.6), ("Tanzilovi", 0.4), ct_hours=1,
        )
        f2 = _ufc_fight(
            102, "Fight Night: Kape vs Horiguchi",
            "kalshi:KXUFCFIGHT-26JUN20KAPHOR", ("Kape", 0.55), ("Horiguchi", 0.45), ct_hours=3,
        )
        # A title future on the same category, different ticker — must be excluded.
        prop = _ufc_fight(
            103, "UFC Heavyweight Title Holder?",
            "kalshi:KXUFCHEAVYWEIGHTTITLE-26", ("A", 0.5), ("B", 0.5),
        )
        mock_db.execute.return_value = _query_result([f1, f2, prop])
        resp = await client.get("/api/event/event:ufc:26jun20")
        assert resp.status_code == 200
        body = resp.json()
        assert body["event"]["domain"] == "ufc"
        assert body["primary"]["kind"] == "co_equal_list"
        # main event = latest commence_time (Kape, +3h)
        names = [c["name"] for c in body["primary"]["competitors"]]
        assert "Kape" in names and "Horiguchi" in names
        # both fights are children; the title future is excluded
        assert len(body["children"]) == 2
        assert not any("Title" in (c.get("market_name") or "") for c in body["children"])

    async def test_ufc_no_card_404(self, client, mock_db):
        from tests.integration.test_route_weather import _query_result
        mock_db.execute.return_value = _query_result([])
        resp = await client.get("/api/event/event:ufc:26jun20")
        assert resp.status_code == 404
