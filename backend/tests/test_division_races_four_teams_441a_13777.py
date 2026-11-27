"""Tests for 441: A (#13777) NFL division-race four-team server behaviour."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy.dialects import postgresql

from app.utils.container_machinery import (
    _compute_member_number_parity,
    _load_snapshot_from_db,
    _market_matches_query,
    build_container_machinery_producer,
    compute_visual_diversity_report,
    load_machinery_definition,
    produce_container_machinery,
)
from app.utils.discover_fun_tags import clear_fun_markets_cache
from app.utils.roundup_containers import compose_roundup_container, compose_roundup_feed_item

NOW = datetime(2026, 11, 26, 23, 0, tzinfo=timezone.utc)
CANDIDATES_DIR = Path(__file__).resolve().parents[1] / "data" / "groupings" / "candidates"


def _nfl_teams() -> list[dict]:
    entries = [
        (1, "Denver Broncos", "DEN", "den"),
        (2, "Kansas City Chiefs", "KC", "kc"),
        (3, "Las Vegas Raiders", "LV", "lv"),
        (4, "Los Angeles Chargers", "LAC", "lac"),
        (5, "Chicago Bears", "CHI", "chi"),
        (6, "Minnesota Vikings", "MIN", "min"),
        (7, "Detroit Lions", "DET", "det"),
        (8, "Green Bay Packers", "GB", "gb"),
        (9, "Carolina Panthers", "CAR", "car"),
        (10, "Tampa Bay Buccaneers", "TB", "tb"),
        (11, "Atlanta Falcons", "ATL", "atl"),
        (12, "New Orleans Saints", "NO", "no"),
        (13, "San Francisco 49ers", "SF", "sf"),
        (14, "Los Angeles Rams", "LAR", "lar"),
        (15, "Seattle Seahawks", "SEA", "sea"),
        (16, "Arizona Cardinals", "ARI", "ari"),
    ]
    return [
        {
            "id": tid,
            "name": name,
            "abbreviation": abbr,
            "sport_key": "americanfootball_nfl",
            "espn_id": espn_id,
            "logo_url_small": f"https://a.espncdn.com/i/teamlogos/nfl/500/{espn_id}.png",
            "logo_url_large": f"https://a.espncdn.com/i/teamlogos/nfl/500/{espn_id}.png",
        }
        for tid, name, abbr, espn_id in entries
    ]


def _div_market(
    mid: int,
    name: str,
    outcomes: list[dict],
) -> dict:
    fresh = (NOW - timedelta(minutes=15)).isoformat()
    enriched = []
    for o in outcomes:
        row = dict(o)
        row.setdefault("last_updated", fresh)
        enriched.append(row)
    return {
        "id": mid,
        "name": name,
        "status": "open",
        "source": "kalshi",
        "category": "football",
        "sport": "americanfootball_nfl",
        "llm_sport_category": "NFL",
        "mutually_exclusive": True,
        "market_type": "field",
        "volume": 500_000.0,
        "lifetime_volume": 500_000.0,
        "resolution_date": "2027-01-11T15:00:00+00:00",
        "outcomes": enriched,
    }


def test_only_division_race_rules_enable_include_all_division_teams() -> None:
    defn = load_machinery_definition(CANDIDATES_DIR / "machinery-afc-west-duel.json")
    assert defn["section_title"] == "AFC West Title Race"
    assert defn["rule"]["card_rows"] == 4
    sections = {s["key"]: s for s in defn["rule"]["sections"]}
    assert set(sections) == {"afc_west_duel", "nfl_division_races"}
    assert sections["afc_west_duel"]["atom_query"]["max_outcomes"] == 4
    assert sections["afc_west_duel"]["atom_query"]["initial_visible_limit"] == 4
    assert sections["afc_west_duel"]["atom_query"]["include_all_division_teams"] is True
    assert sections["nfl_division_races"]["atom_query"]["max_outcomes"] == 4
    assert sections["nfl_division_races"]["atom_query"]["include_all_division_teams"] is True

    for path in sorted(CANDIDATES_DIR.glob("*.json")):
        if path.name == "machinery-afc-west-duel.json":
            continue
        doc = json.loads(path.read_text(encoding="utf-8"))
        for sec in (doc.get("rule") or {}).get("sections") or ():
            aq = sec.get("atom_query") or {}
            assert not aq.get("include_all_division_teams"), f"Unexpected opt-in in {path.name}"


@pytest.mark.asyncio
async def test_division_races_emit_all_four_teams_with_tiny_settled_and_unpriced_states() -> None:
    clear_fun_markets_cache()
    defn = load_machinery_definition(CANDIDATES_DIR / "machinery-afc-west-duel.json")
    prod = build_container_machinery_producer(defn)

    snap = {
        "events": [],
        "teams": _nfl_teams(),
        "markets": [
            # AFC West: 2 live (incl. <0.5% sub-1%), 1 unpriced None, 1 authoritatively settled out (residue 0.005)
            _div_market(
                53675,
                "AFC West Division Winner",
                [
                    {"id": 846594, "name": "Denver", "probability": 0.625},
                    {"id": 846593, "name": "Kansas City", "probability": 0.004},
                    {"id": 846592, "name": "Los Angeles Chargers", "probability": None},
                    {
                        "id": 846591,
                        "name": "Las Vegas",
                        "probability": 0.005,
                        "is_winner": False,
                        "resolution_source": "api_settlement",
                    },
                ],
            ),
            # NFC North: default ungraded is_winner=False (resolution_source=None) & ungradeable_result stay live/unpriced, never Eliminated;
            # live contender >= TERMINAL_LOSER_CEILING keeps its price even with api_settlement;
            # missing 4th team (Green Bay) is synthesized from NFL_DIVISION_REGISTER.
            _div_market(
                53673,
                "NFC North Division Winner",
                [
                    {"id": 846586, "name": "Chicago", "probability": 0.50, "is_winner": False, "resolution_source": None},
                    {
                        "id": 846583,
                        "name": "Minnesota",
                        "probability": 0.35,
                        "is_winner": False,
                        "resolution_source": "api_settlement",
                    },
                    {
                        "id": 846585,
                        "name": "Detroit",
                        "probability": 0.009,
                        "is_winner": False,
                        "resolution_source": "ungradeable_result",
                    },
                ],
            ),
            # NFC South: all 4 priced, 0.002 smallest preserved (< 0.005 floor not dropped!)
            _div_market(
                53672,
                "NFC South Division Winner",
                [
                    {"id": 846579, "name": "Carolina", "probability": 0.60},
                    {"id": 846580, "name": "Tampa Bay", "probability": 0.25},
                    {"id": 846582, "name": "Atlanta", "probability": 0.148},
                    {"id": 846581, "name": "New Orleans", "probability": 0.002},
                ],
            ),
            # NFC West: 1 priced + 1 tiny (0.0099) + 1 probability=0.0 (unpriced, not settled) + 1 missing (Seattle)
            _div_market(
                53671,
                "NFC West Division Winner",
                [
                    {"id": 846575, "name": "San Francisco", "probability": 0.90},
                    {"id": 846576, "name": "Los Angeles Rams", "probability": 0.0099},
                    {"id": 846578, "name": "Arizona", "probability": 0.0, "is_winner": False, "resolution_source": None},
                ],
            ),
        ],
    }

    res = await produce_container_machinery(snap, defn, now=NOW)
    feed_item = compose_roundup_feed_item(prod, res)
    container = compose_roundup_container(prod, res)

    card = feed_item["data"]["roundup"]["machinery_card"]
    assert card["form_id"] == "sibling_fields_grid"
    assert len(card["rows"]) == 4
    by_name = {r["name"]: r for r in card["rows"]}
    assert set(by_name) == {"Denver", "Kansas City", "Los Angeles Chargers", "Las Vegas"}

    assert by_name["Denver"]["probability"] == pytest.approx(0.625)
    assert by_name["Denver"]["settled_out"] is False
    # Tiny probability (<0.005) kept and unfloored preserved
    assert by_name["Kansas City"]["probability"] == pytest.approx(0.004)
    assert by_name["Kansas City"]["settled_out"] is False
    # Unpriced team emitted with null probability and settled_out=False
    assert by_name["Los Angeles Chargers"]["probability"] is None
    assert by_name["Los Angeles Chargers"]["rendered_percent"] is None
    assert by_name["Los Angeles Chargers"]["settled_out"] is False
    assert by_name["Los Angeles Chargers"]["art"]["url"].endswith("/lac.png")
    # Settled-out team carries settled_out=True and withheld numbers
    assert by_name["Las Vegas"]["settled_out"] is True
    assert by_name["Las Vegas"]["probability"] is None
    assert by_name["Las Vegas"]["rendered_percent"] is None
    assert by_name["Las Vegas"]["art"]["url"].endswith("/lv.png")

    # Section 1 (`nfl_division_races`) also carries all 4 teams per division
    sec_divs = {it["market_id"]: it for it in container["sections"][1]["visual_block"]["items"]}
    assert len(sec_divs[53673]["outcomes"]) == 4
    nfc_n = {o["name"]: o for o in sec_divs[53673]["outcomes"]}
    assert nfc_n["Chicago"]["settled_out"] is False
    assert nfc_n["Minnesota"]["settled_out"] is False and nfc_n["Minnesota"]["probability"] == pytest.approx(0.35)
    assert nfc_n["Detroit"]["settled_out"] is False and nfc_n["Detroit"]["probability"] == pytest.approx(0.009)
    assert nfc_n["Green Bay"]["settled_out"] is False and nfc_n["Green Bay"]["probability"] is None
    assert nfc_n["Green Bay"]["art"]["url"].endswith("/gb.png")

    nfc_s = {o["name"]: o for o in sec_divs[53672]["outcomes"]}
    assert nfc_s["New Orleans"]["probability"] == pytest.approx(0.002)
    assert nfc_s["New Orleans"]["settled_out"] is False

    nfc_w = {o["name"]: o for o in sec_divs[53671]["outcomes"]}
    assert nfc_w["Arizona"]["settled_out"] is False and nfc_w["Arizona"]["probability"] is None
    assert nfc_w["Seattle"]["settled_out"] is False and nfc_w["Seattle"]["probability"] is None
    assert nfc_w["Los Angeles Rams"]["probability"] == pytest.approx(0.0099)

    card_parity, page_parity = _compute_member_number_parity(feed_item, container)
    assert card_parity["passes"] is True
    assert page_parity["passes"] is True
    div_report = compute_visual_diversity_report(defn, feed_item, container)
    assert div_report["card"]["point_2_longest_form_run"]["passes"] is True


@pytest.mark.asyncio
async def test_non_division_card_keeps_existing_floor_and_null_dropping_behaviour() -> None:
    clear_fun_markets_cache()
    defn = {
        "slug": "test-non-div-field",
        "stage": "public",
        "look": "bars",
        "membership": "computed-produced",
        "kind": "roundup",
        "relations": ["same_event"],
        "level": "member",
        "kicker": "POLITICS · ELECTION",
        "name": "2028 Nominee Race",
        "category": "politics",
        "section_title": "Top Contenders",
        "footer": "",
        "rule": {
            "producer": "container_machinery",
            "refusal": "all-or-nothing",
            "materialize": "read-time",
            "card_rows": 2,
            "card_section_key": "top_contenders",
            "sections": [
                {
                    "key": "top_contenders",
                    "title": "Top Contenders",
                    "item_noun": "contenders",
                    "note": "Leading contenders in the 2028 field.",
                    "atom_query": {
                        "kind": "markets",
                        "title_all_tokens": ["nominee"],
                        "shape": "field",
                        "min_items": 1,
                        "max_items": 1,
                        "max_outcomes": 2,
                    },
                }
            ],
        },
    }

    snap = {
        "events": [],
        "teams": [],
        "markets": [
            {
                "id": 999112897,
                "name": "Who will win the 2028 Presidential Nominee race?",
                "status": "open",
                "source": "polymarket",
                "mutually_exclusive": True,
                "market_type": "field",
                "volume": 900_000.0,
                "resolution_date": "2028-11-08T00:00:00+00:00",
                "outcomes": [
                    {"id": 1, "name": "Gavin Newsom", "probability": 0.55},
                    {"id": 2, "name": "Pete Buttigieg", "probability": 0.448},
                    {"id": 3, "name": "Josh Shapiro", "probability": 0.002},
                    {"id": 4, "name": "Ro Khanna", "probability": None},
                ],
            }
        ],
    }
    non_div_aq = defn["rule"]["sections"][0]["atom_query"]
    two_priced_only = {
        **snap["markets"][0],
        "outcomes": [
            {"id": 1, "name": "Gavin Newsom", "probability": 0.55},
            {"id": 2, "name": "Pete Buttigieg", "probability": 0.45},
            {"id": 3, "name": "Josh Shapiro", "probability": None},
        ],
    }
    assert _market_matches_query(two_priced_only, non_div_aq, now_dt=NOW) is False
    # Add a second field market so sibling_fields_grid / benchmark_strip has >=2 items,
    # and keep 3 priced legs + 1 <0.005 + 1 None in market 1: non-division STILL drops <0.005 & None and omits settled_out.
    snap["markets"][0]["outcomes"] = [
        {"id": 1, "name": "Gavin Newsom", "probability": 0.55},
        {"id": 2, "name": "Pete Buttigieg", "probability": 0.30},
        {"id": 3, "name": "Josh Shapiro", "probability": 0.148},
        {"id": 4, "name": "Ro Khanna", "probability": 0.002},
        {"id": 5, "name": "Andy Beshear", "probability": None},
    ]
    snap["markets"].append(
        {
            "id": 999112898,
            "name": "Who will win the 2028 Vice Nominee race?",
            "status": "open",
            "source": "polymarket",
            "mutually_exclusive": True,
            "market_type": "field",
            "volume": 800_000.0,
            "resolution_date": "2028-11-08T00:00:00+00:00",
            "outcomes": [
                {"id": 11, "name": "Mark Kelly", "probability": 0.60},
                {"id": 12, "name": "Wes Moore", "probability": 0.25},
                {"id": 13, "name": "Roy Cooper", "probability": 0.15},
            ],
        }
    )
    defn["rule"]["card_rows"] = 3
    defn["rule"]["sections"][0]["atom_query"]["max_items"] = 2
    defn["rule"]["sections"][0]["atom_query"]["max_outcomes"] = 5
    res = await produce_container_machinery(snap, defn, now=NOW)
    container = compose_roundup_container(build_container_machinery_producer(defn), res)
    items_by_mid = {
        int(it["market_id"]): it
        for it in container["sections"][0]["visual_block"]["items"]
    }
    first_item_outs = items_by_mid[999112897]["outcomes"]
    assert [o["name"] for o in first_item_outs] == [
        "Gavin Newsom",
        "Pete Buttigieg",
        "Josh Shapiro",
    ]
    assert all("settled_out" not in o for o in first_item_outs)
    assert len(res.machinery_card["rows"]) == 2
    assert all("settled_out" not in r for r in res.machinery_card["rows"])


@pytest.mark.asyncio
async def test_db_snapshot_loader_preserves_division_all_outcomes_and_strips_internal_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clear_fun_markets_cache()
    defn = load_machinery_definition(CANDIDATES_DIR / "machinery-afc-west-duel.json")
    fresh = NOW - timedelta(minutes=10)

    def _fm(mid: int, name: str, outs: list[SimpleNamespace]):
        return SimpleNamespace(
            id=mid,
            name=name,
            status="open",
            source="kalshi",
            mutually_exclusive=True,
            market_type="field",
            volume=500_000.0,
            volume_24h=50_000.0,
            market_metadata={},
            image_url=None,
            llm_sport_category="NFL",
            sport=SimpleNamespace(key="americanfootball_nfl"),
            resolution_date=NOW + timedelta(days=45),
            event_date=None,
            outcomes=outs,
        )

    def _o(oid: int, name: str, prob, *, is_winner=False, resolution_source=None):
        return SimpleNamespace(
            id=oid,
            name=name,
            outcome_name=name,
            current_probability=Decimal(str(prob)) if prob is not None else None,
            implied_probability=None,
            opening_probability=None,
            image_url=None,
            last_updated=fresh,
            is_winner=is_winner,
            resolution_source=resolution_source,
        )

    markets_orm = [
        _fm(
            53675,
            "AFC West Division Winner",
            [
                _o(846594, "Denver", 0.56),
                _o(846593, "Kansas City", 0.003),
                _o(846592, "Los Angeles Chargers", None),
                _o(846591, "Las Vegas", 0.005, is_winner=False, resolution_source="api_settlement"),
            ],
        ),
        _fm(
            53673,
            "NFC North Division Winner",
            [
                _o(846586, "Chicago", 0.50),
                _o(846583, "Minnesota", 0.30),
                _o(846585, "Detroit", 0.19),
                _o(846584, "Green Bay", 0.01),
            ],
        ),
        _fm(
            53672,
            "NFC South Division Winner",
            [
                _o(846579, "Carolina", 0.55),
                _o(846580, "Tampa Bay", 0.29),
                _o(846582, "Atlanta", 0.09),
                _o(846581, "New Orleans", 0.07),
            ],
        ),
        _fm(
            53671,
            "NFC West Division Winner",
            [
                _o(846575, "San Francisco", 0.90),
                _o(846576, "Los Angeles Rams", 0.05),
                _o(846577, "Seattle", 0.04),
                _o(846578, "Arizona", 0.0099),
            ],
        ),
    ]

    class _Res:
        def __init__(self, rows):
            self._rows = rows

        def unique(self):
            return self

        def scalars(self):
            return self

        def all(self):
            return list(self._rows)

    class _FakeDB:
        async def execute(self, stmt):
            sql = str(stmt.compile(dialect=postgresql.dialect())).lower()
            if "from futures_markets" in sql:
                return _Res(markets_orm)
            if "from teams" in sql:
                return _Res([])
            return _Res([])

    async def _fake_withheld(db, markets):
        return {m.id: set() for m in markets}

    async def _fake_fleet(db, fm):
        return NOW

    async def _fake_out_legs(markets):
        return {}

    async def _fake_vt(db, fm):
        return SimpleNamespace(reason="not_a_title_question")

    def _fake_format(fm, *_args, **_kwargs):
        return {
            "id": fm.id,
            "name": fm.name,
            "outcomes": [
                {
                    "id": o.id,
                    "name": o.name,
                    "probability": float(o.current_probability) if o.current_probability is not None else None,
                    "is_winner": o.is_winner,
                    "resolution_source": o.resolution_source,
                    "opening_probability": None,
                }
                for o in fm.outcomes
                # Simulate _format_market_detail dropping authoritatively settled-out legs:
                # _load_snapshot_from_db must still recover them from fm.outcomes as settled_out=True.
                if o.resolution_source != "api_settlement"
            ],
        }

    monkeypatch.setattr("app.routes.futures.withheld_price_outcome_ids_for_markets", _fake_withheld)
    monkeypatch.setattr("app.routes.futures._fleet_newest_observation", _fake_fleet)
    monkeypatch.setattr("app.routes.futures.out_legs_by_market", _fake_out_legs)
    monkeypatch.setattr("app.routes.futures._resolve_verified_title", _fake_vt)
    monkeypatch.setattr("app.routes.futures._format_market_detail", _fake_format)
    monkeypatch.setattr("app.routes.futures._apply_verified_title_to_detail", lambda *_a, **_kw: None)

    snap = await _load_snapshot_from_db(_FakeDB(), defn, NOW)
    m53675 = next(m for m in snap["markets"] if m["id"] == 53675)
    assert "_division_all_outcomes" in m53675
    res = await produce_container_machinery(snap, defn, now=NOW)
    for env in res.members:
        assert "_division_all_outcomes" not in env["card"]
    afc_rows = {r["name"]: r for r in res.machinery_card["rows"]}
    assert afc_rows["Kansas City"]["probability"] == pytest.approx(0.003)
    assert afc_rows["Los Angeles Chargers"]["probability"] is None
    assert afc_rows["Los Angeles Chargers"]["settled_out"] is False
    assert afc_rows["Las Vegas"]["settled_out"] is True
    assert afc_rows["Las Vegas"]["probability"] is None
