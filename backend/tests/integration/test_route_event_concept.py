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


def _tennis_outcome(name, prob, won=False):
    from types import SimpleNamespace
    return SimpleNamespace(name=name, current_probability=prob, is_winner=won)


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


def _tennis_settled_winner_market():
    """A concluded slam: the winner market has flipped to `resolved` and the
    champion's outcome carries is_winner=True (L2-81)."""
    from types import SimpleNamespace
    from datetime import datetime, timezone, timedelta
    return SimpleNamespace(
        id=990001,
        name="2026 Women's Wimbledon Winner",
        status="resolved",  # Polymarket flips to resolved the moment it settles
        llm_sport_category="tennis",
        source="polymarket",
        group_id="polymarket:139182",
        resolution_date=datetime.now(timezone.utc) - timedelta(hours=6),
        outcomes=[
            _tennis_outcome("Aryna Sabalenka", 1.0, won=True),
            _tennis_outcome("Coco Gauff", 0.0),
            _tennis_outcome("Iga Swiatek", 0.0),
            _tennis_outcome("Other", 0.0),  # field remainder — dropped
        ],
    )


class TestTennisSettled:
    """L2-81: a concluded tournament survives resolution (no 404) and marks the
    champion so the page renders 'Won' instead of a stale probability."""

    async def test_settled_marks_champion_and_survives_resolution(self, client, mock_db):
        from tests.integration.test_route_weather import _query_result
        # In prod the broadened query keeps recently-resolved winner markets in the
        # result set; the mock returns rows regardless of the WHERE, so this proves
        # the adapter builds a settled envelope from a `resolved` market rather than
        # skipping it (the pre-L2-81 status=="open" filter would have dropped it →
        # None → 404).
        mock_db.execute.return_value = _query_result([_tennis_settled_winner_market()])
        resp = await client.get("/api/event/event:tennis:wimbledon")
        assert resp.status_code == 200  # did NOT 404 after the market resolved
        body = resp.json()
        assert body["event"]["status"] == "settled"
        comps = body["primary"]["competitors"]
        # "Other" dropped; the actual winner is flagged and only the winner.
        assert [c["name"] for c in comps][0] == "Aryna Sabalenka"
        assert sum(1 for c in comps if c.get("won")) == 1
        champ = next(c for c in comps if c.get("won"))
        assert champ["name"] == "Aryna Sabalenka"


def _tennis_price_settled_market():
    """The REAL women's Wimbledon shape (verified live 2026-07-12): the winner
    market is past its resolution_date but is_winner has NOT been graded yet, and
    the champion's raw price is ~1.0 while other candidates carry residual price so
    the field sums >100%. normalize_display_probs then dilutes the leader below the
    frontend's >=0.9 crown threshold — the exact gap L2-83 closes."""
    from types import SimpleNamespace
    from datetime import datetime, timezone, timedelta
    # A long residual tail so the field sums >105% (the #23 normalization trigger),
    # matching the real 51-player Polymarket field that diluted Nosková's raw 0.9995
    # down to the displayed 0.888.
    tail = [_tennis_outcome(f"Player {i}", 0.009) for i in range(15)]
    return SimpleNamespace(
        id=114157,
        name="2026 Women's Wimbledon Winner",
        status="open",  # Polymarket left it 'open'; date is what settles it
        llm_sport_category="tennis",
        source="polymarket",
        group_id="polymarket:139182",
        resolution_date=datetime.now(timezone.utc) - timedelta(hours=3),
        outcomes=[
            _tennis_outcome("Linda Nosková", 0.9995),   # the champion (raw ~1.0)
            _tennis_outcome("Aryna Sabalenka", 0.018),
            _tennis_outcome("Jessica Pegula", 0.01),
            _tennis_outcome("Serena Williams", 0.009),
            *tail,
            _tennis_outcome("Other", 1.0),  # field remainder — dropped
        ],
    )


class TestTennisPriceSettledCrown:
    """L2-83: during the is_winner grading-lag window, a settled winner-market whose
    top outcome is priced ~1.0 is crowned via the display `won` flag — read from the
    RAW price BEFORE #23 normalization dilutes the leader under the crown threshold."""

    async def test_price_settled_market_crowns_leader(self, client, mock_db):
        from tests.integration.test_route_weather import _query_result
        mock_db.execute.return_value = _query_result([_tennis_price_settled_market()])
        resp = await client.get("/api/event/event:tennis:2026-womens-wimbledon")
        assert resp.status_code == 200
        body = resp.json()
        assert body["event"]["status"] == "settled"  # resolution_date is past
        comps = body["primary"]["competitors"]
        champ = [c for c in comps if c.get("won")]
        assert len(champ) == 1, "exactly one price-settled champion crowned"
        assert champ[0]["name"] == "Linda Nosková"
        # The dilution that motivated the fix: her DISPLAYED prob is scaled under
        # 0.9, so without the crown the frontend's >=0.9 fallback would fail to name
        # her — the `won` flag is what makes the settled page honest.
        assert champ[0]["probability"] < 0.9

    async def test_undecided_settled_field_not_crowned(self, client, mock_db):
        """Men's-Wimbledon shape: settled by date but the price never converged
        (top ~0.81). Must NOT fabricate a champion — the page shows 'awaiting'."""
        from types import SimpleNamespace
        from datetime import datetime, timezone, timedelta
        from tests.integration.test_route_weather import _query_result
        mkt = SimpleNamespace(
            id=114156, name="2026 Men’s Wimbledon Winner", status="open",
            llm_sport_category="tennis", source="polymarket",
            group_id="polymarket:139181",
            resolution_date=datetime.now(timezone.utc) - timedelta(hours=3),
            outcomes=[
                _tennis_outcome("Jannik Sinner", 0.81),
                _tennis_outcome("Alexander Zverev", 0.19),
                _tennis_outcome("Other", 1.0),
            ],
        )
        mock_db.execute.return_value = _query_result([mkt])
        resp = await client.get("/api/event/event:tennis:2026-mens-wimbledon")
        assert resp.status_code == 200
        body = resp.json()
        assert body["event"]["status"] == "settled"
        assert not any(c.get("won") for c in body["primary"]["competitors"])


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

    async def test_f1_upcoming_populates_start_date_for_countdown(self, client, mock_db):
        """L2-83: an UPCOMING GP (>4d out) exposes start_date = the race time so the
        L2-78 countdown chip renders (daysUntilStart needs a start). Without it the
        chip could never show for F1."""
        from tests.integration.test_route_weather import _query_result
        winner = _f1_market(
            1, "Hungarian Grand Prix Winner", "KXF1RACE-HUNGP26",
            [("Lando Norris", 0.4), ("Max Verstappen", 0.35)], rd_days=10,
        )
        mock_db.execute.return_value = _query_result([winner])
        resp = await client.get("/api/event/event:f1:hungarian-grand-prix")
        assert resp.status_code == 200
        ev = resp.json()["event"]
        assert ev["status"] == "upcoming"
        assert ev["start_date"] is not None, "countdown chip needs a start_date"
        assert ev["start_date"] == ev["end_date"]  # one-day event

    async def test_f1_price_settled_crowns_winner(self, client, mock_db):
        """L2-83: a settled race whose leader is priced ~1.0 (grading lag) is crowned
        via the display `won` flag — parity with tennis."""
        from tests.integration.test_route_weather import _query_result
        winner = _f1_market(
            1, "British Grand Prix Winner", "KXF1RACE-BRIGP26",
            [("Lando Norris", 0.98), ("Max Verstappen", 0.02)], rd_days=-1,
        )
        mock_db.execute.return_value = _query_result([winner])
        resp = await client.get("/api/event/event:f1:british-grand-prix")
        assert resp.status_code == 200
        body = resp.json()
        assert body["event"]["status"] == "settled"
        champ = [c for c in body["primary"]["competitors"] if c.get("won")]
        assert len(champ) == 1 and champ[0]["name"] == "Lando Norris"


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

    async def test_ufc_329_naming_and_props(self, client, mock_db):
        """L2-84 (B2): a numbered card reads "UFC 329" and shows a real props
        section — Kalshi occurrence + Polymarket method props ride along, while
        the matchup-shaped negrisk bundle is excluded."""
        from types import SimpleNamespace
        from tests.integration.test_route_weather import _query_result

        fight = _ufc_fight(
            201, "UFC 329: McGregor vs. Holloway 2",
            "kalshi:KXUFCFIGHT-26JUL11MCGHOL",
            ("Conor McGregor", 0.6), ("Max Holloway", 0.4), ct_hours=48,
        )

        def _mkt(id_, name, ext, source, outs):
            return SimpleNamespace(
                id=id_, name=name, external_id=ext, status="open",
                llm_sport_category="mma", source=source, group_id=None,
                commence_time=None, resolution_date=None, market_metadata={},
                outcomes=[_tennis_outcome(n, p) for n, p in outs],
            )

        # Polymarket method prop (hash ticker, matched by surname in the name).
        method = _mkt(
            202, "Will Max Holloway win by KO or TKO?",
            "0x775f42b26ed999f5043f89932f06e01226651601c69368930bf5cf31359e6952",
            "polymarket", [("Yes", 0.4), ("No", 0.6)],
        )
        # Kalshi occurrence prop (matched by card number in the name + ticker).
        occ = _mkt(
            203, "Will Conor McGregor and Max Holloway fight at UFC 329?",
            "kalshi:KXUFCOCCUR-26CMCGMHOL", "kalshi", [("Yes", 0.9)],
        )
        # Polymarket bundled negrisk shape (matchup-named, 3 outcomes) — excluded.
        bundle = _mkt(
            204, "UFC 329: Max Holloway vs. Conor McGregor (Welterweight, Main Card)",
            "0xbundle", "polymarket",
            [("Holloway to win by KO/TKO?", 0.5), ("O/U 1.5 Rounds", 0.5), ("Distance?", 0.3)],
        )

        mock_db.execute.return_value = _query_result([fight, method, occ, bundle])
        resp = await client.get("/api/event/event:ufc:26jul11")
        assert resp.status_code == 200
        body = resp.json()
        assert body["event"]["name"] == "UFC 329: McGregor vs. Holloway 2"
        assert body["event"]["is_major"] is True

        kinds = [c.get("kind") for c in body["children"]]
        assert kinds.count("fight") == 1
        props = [c for c in body["children"] if c.get("kind") == "prop"]
        prop_names = {c["market_name"] for c in props}
        assert "Will Max Holloway win by KO or TKO?" in prop_names
        assert "Will Conor McGregor and Max Holloway fight at UFC 329?" in prop_names
        # the matchup-named bundle is NOT a prop (nor a fight)
        assert not any("Welterweight, Main Card" in n for n in prop_names)
        assert {c["prop_type"] for c in props} == {"method", "occurrence"}
        # a real props section exists
        assert any(s["type"] == "props" for s in body["sections"])


def _award_market(id_, name, ext, outs, source="kalshi", rd=None):
    """An award category/nominations/novelty market. `outs` is (name, prob[, won])."""
    from types import SimpleNamespace

    def _o(t):
        return _tennis_outcome(t[0], t[1], won=t[2] if len(t) > 2 else False)

    return SimpleNamespace(
        id=id_,
        name=name,
        external_id=ext,
        status="open",
        llm_sport_category="entertainment",
        source=source,
        group_id=None,
        commence_time=None,
        resolution_date=rd,
        market_metadata={},
        outcomes=[_o(t) for t in outs],
    )


class TestAwardsEventAdapter:
    """L2-87 (B6): an awards ceremony renders as co_equal_list — categories are the
    co-equal children, the marquee category is the head-to-head hero, and
    nomination/novelty markets ride along as props. Design §6."""

    async def test_oscars_categories_and_edition_filter(self, client, mock_db):
        from tests.integration.test_route_weather import _query_result

        best_pic = _award_market(
            1, "Oscar winner: Best Picture", "KXOSCARPIC-27",
            [("Anora", 0.4), ("The Brutalist", 0.3), ("Conclave", 0.2)],
        )
        best_dir = _award_market(
            2, "Oscar winner: Best Director", "KXOSCARDIR-27",
            [("Sean Baker", 0.5), ("Brady Corbet", 0.35)],
        )
        best_act = _award_market(
            3, "Oscar winner: Best Actor", "KXOSCARACTO-27",
            [("Adrien Brody", 0.6), ("Timothée Chalamet", 0.3)],
        )
        noms = _award_market(
            4, "Oscar nominations for Best Picture?", "KXOSCARNOMPIC-27",
            [("Anora", 0.9), ("Wicked", 0.7)],
        )
        # A DIFFERENT edition (2026) novelty — must be filtered out when year=27.
        guests_26 = _award_market(
            5, "Who will attend the Oscars?", "KXOSCARGUESTS-26",
            [("Yes", 0.5), ("No", 0.5)],
        )
        mock_db.execute.return_value = _query_result(
            [best_pic, best_dir, best_act, noms, guests_26]
        )

        resp = await client.get("/api/event/event:awards:oscars-2027")
        assert resp.status_code == 200
        body = resp.json()
        assert body["event"]["domain"] == "awards"
        assert body["event"]["name"] == "The Oscars 2027"
        assert body["event"]["key"] == "event:awards:oscars-2027"
        assert body["primary"]["kind"] == "co_equal_list"
        # marquee = Best Picture (by name), its nominees are the hero head-to-head
        assert body["primary"]["label"] == "Best Picture"
        assert "Anora" in [c["name"] for c in body["primary"]["competitors"]]

        # category children render with cleaned labels, no kind (-> MatchupsRail)
        cats = [c for c in body["children"] if c.get("kind") != "prop"]
        cat_names = {c["market_name"] for c in cats}
        assert {"Best Picture", "Best Director", "Best Actor"} <= cat_names
        # nominations ride along as a prop; the wrong-edition novelty is excluded
        props = [c for c in body["children"] if c.get("kind") == "prop"]
        assert any(c["prop_type"] == "nominations" for c in props)
        assert not any("attend" in (c["market_name"] or "").lower() for c in body["children"])
        assert any(s["type"] == "categories" for s in body["sections"])

    async def test_bare_slug_picks_latest_rich_edition(self, client, mock_db):
        from tests.integration.test_route_weather import _query_result

        # 2026 edition (3 categories) and 2027 edition (3 categories) both "rich" —
        # a bare slug picks the LATEST rich edition (2027).
        e26 = [
            _award_market(10, "Oscar for Best Picture?", "KXOSCARPIC-26", [("Anora", 0.5), ("Emilia", 0.3)]),
            _award_market(11, "Oscar for Best Director?", "KXOSCARDIR-26", [("Baker", 0.5), ("Corbet", 0.3)]),
            _award_market(12, "Oscar for Best Actor?", "KXOSCARACTO-26", [("Brody", 0.5), ("Chalamet", 0.4)]),
        ]
        e27 = [
            _award_market(20, "Oscar winner: Best Picture", "KXOSCARPIC-27", [("Sinners", 0.5), ("Wicked", 0.3)]),
            _award_market(21, "Oscar winner: Best Director", "KXOSCARDIR-27", [("Coogler", 0.5), ("Chazelle", 0.4)]),
            _award_market(22, "Oscar winner: Best Actor", "KXOSCARACTO-27", [("Washington", 0.5), ("Butler", 0.4)]),
        ]
        mock_db.execute.return_value = _query_result(e26 + e27)

        resp = await client.get("/api/event/event:awards:oscars")
        assert resp.status_code == 200
        body = resp.json()
        assert body["event"]["name"] == "The Oscars 2027"
        # only the 2027 categories are present
        assert all(
            c["market_id"] >= 20 for c in body["children"] if c.get("kind") != "prop"
        )

    async def test_settled_marquee_crowns_price_leader(self, client, mock_db):
        from tests.integration.test_route_weather import _query_result

        # A concluded category whose leader is priced ~1.0 but not yet graded — the
        # display `won` crown fires (parity with tennis/f1), status flips to settled.
        best_pic = _award_market(
            30, "Oscar winner: Best Picture", "KXOSCARPIC-26",
            [("Oppenheimer", 0.98), ("Barbie", 0.02)],
        )
        mock_db.execute.return_value = _query_result([best_pic])
        resp = await client.get("/api/event/event:awards:oscars-2026")
        assert resp.status_code == 200
        body = resp.json()
        assert body["event"]["status"] == "settled"
        champ = [c for c in body["primary"]["competitors"] if c.get("won")]
        assert len(champ) == 1 and champ[0]["name"] == "Oppenheimer"

    async def test_no_markets_404(self, client, mock_db):
        from tests.integration.test_route_weather import _query_result
        mock_db.execute.return_value = _query_result([])
        resp = await client.get("/api/event/event:awards:oscars")
        assert resp.status_code == 404

    async def test_unknown_ceremony_404(self, client, mock_db):
        from tests.integration.test_route_weather import _query_result
        # Golden Globes has no config yet -> 404 (adapter returns None), not a crash.
        mock_db.execute.return_value = _query_result([
            _award_market(40, "Golden Globe: Best Picture", "KXGLOBEPIC-27", [("A", 0.5)]),
        ])
        resp = await client.get("/api/event/event:awards:golden-globes")
        assert resp.status_code == 404
