"""Tests for Batch 7 preview grouping sets and Item 8 card forms (#12288)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.utils.container_machinery import (
    _PAIRED_REGISTER_PATH,
    MACHINERY_FORM_IDS,
    _compute_member_number_parity,
    build_container_machinery_producer,
    load_machinery_definition,
    produce_container_machinery,
)
from app.utils.discover_fun_tags import clear_fun_markets_cache
from app.utils.discover_image_policy import sanitize_discover_feed_item
from app.utils.roundup_containers import (
    compose_roundup_container,
    compose_roundup_feed_item,
)

NOW = datetime(2026, 11, 22, 23, 0, tzinfo=timezone.utc)
CANDIDATES_DIR = Path(__file__).resolve().parents[1] / "data" / "groupings" / "candidates"
BATCH7_CURATED_PATH = (
    Path(__file__).resolve().parents[1] / "data" / "groupings" / "batch7_curated_sets.json"
)
PRIOR_CURATED_PATHS = (
    Path(__file__).resolve().parents[1] / "data" / "groupings" / "batch3_curated_sets.json",
    Path(__file__).resolve().parents[1] / "data" / "groupings" / "batch4_curated_sets.json",
    Path(__file__).resolve().parents[1] / "data" / "groupings" / "batch5_curated_sets.json",
    Path(__file__).resolve().parents[1] / "data" / "groupings" / "batch6_curated_sets.json",
)

BATCH7_SLUGS = (
    "machinery-oscars-best-actor-2027",
    "machinery-cfp-national-championship",
    "machinery-afc-west-duel",
    "machinery-nhl-this-week",
    "machinery-college-basketball-slate",
    "machinery-european-league-titles",
    "machinery-tech-and-space-movers",
    "machinery-extreme-earth-2026",
)


def _team_row(tid: int, name: str, abbr: str, sport_key: str, espn_id: str) -> dict:
    folder = (
        "nfl"
        if "nfl" in sport_key
        else ("nhl" if "nhl" in sport_key else ("soccer" if "soccer" in sport_key else "ncaa"))
    )
    return {
        "id": tid,
        "name": name,
        "abbreviation": abbr,
        "sport_key": sport_key,
        "espn_id": espn_id,
        "logo_url_small": f"https://a.espncdn.com/i/teamlogos/{folder}/500/{espn_id}.png",
        "logo_url_large": f"https://a.espncdn.com/i/teamlogos/{folder}/500/{espn_id}.png",
    }


def _event_row(eid: int, sport_key: str, away: str, home: str, hp: float, hours_ahead: int) -> dict:
    ap = round(1.0 - hp, 4)
    h_pct = int(round(hp * 100))
    a_pct = 100 - h_pct
    return {
        "id": eid,
        "sport": sport_key,
        "sport_name": sport_key.upper(),
        "home_team": home,
        "away_team": away,
        "commence_time": (NOW + timedelta(hours=hours_ahead)).isoformat(),
        "status": "scheduled",
        "home_score": None,
        "away_score": None,
        "hero_probability": hp,
        "hero_probability_away": ap,
        "hero_source": "betting",
        "has_sportsbook": True,
        "current_odds": {
            "home_probability": hp,
            "away_probability": ap,
            "away_rendered_percent": a_pct,
            "home_rendered_percent": h_pct,
        },
        "member_page_numbers": {
            "away_pct": a_pct,
            "home_pct": h_pct,
        },
    }


def _make_batch7_snapshot() -> dict:
    teams = [
        _team_row(1, "Georgia Bulldogs", "UGA", "americanfootball_ncaaf", "61"),
        _team_row(2, "Notre Dame Fighting Irish", "ND", "americanfootball_ncaaf", "87"),
        _team_row(3, "Texas Longhorns", "TEX", "americanfootball_ncaaf", "251"),
        _team_row(4, "Alabama Crimson Tide", "ALA", "americanfootball_ncaaf", "333"),
        _team_row(5, "Oregon Ducks", "ORE", "americanfootball_ncaaf", "2483"),
        _team_row(6, "Utah Utes", "UTAH", "americanfootball_ncaaf", "254"),
        _team_row(7, "Boise State Broncos", "BOIS", "americanfootball_ncaaf", "68"),
        _team_row(8, "Denver Broncos", "DEN", "americanfootball_nfl", "den"),
        _team_row(9, "Kansas City Chiefs", "KC", "americanfootball_nfl", "kc"),
        _team_row(10, "Minnesota Vikings", "MIN", "americanfootball_nfl", "min"),
        _team_row(11, "Carolina Panthers", "CAR", "americanfootball_nfl", "car"),
        _team_row(12, "San Francisco 49ers", "SF", "americanfootball_nfl", "sf"),
        _team_row(13, "Anaheim Ducks", "ANA", "icehockey_nhl", "ana"),
        _team_row(14, "Seattle Kraken", "SEA", "icehockey_nhl", "sea"),
        _team_row(15, "Utah Mammoth", "UTA", "icehockey_nhl", "utah"),
        _team_row(16, "Winnipeg Jets", "WPG", "icehockey_nhl", "wpg"),
        _team_row(17, "Houston Cougars", "HOU", "basketball_ncaab", "248"),
        _team_row(18, "Duke Blue Devils", "DUKE", "basketball_ncaab", "150"),
        _team_row(19, "Kansas Jayhawks", "KU", "basketball_ncaab", "2305"),
        _team_row(20, "Florida Gators", "FLA", "basketball_ncaab", "57"),
        _team_row(21, "Arsenal", "ARS", "soccer_epl", "359"),
        _team_row(22, "Barcelona", "BAR", "soccer_spain_la_liga", "83"),
        _team_row(23, "Inter Milan", "INT", "soccer_italy_serie_a", "110"),
        _team_row(24, "Bayern Munich", "FCB", "soccer_germany_bundesliga", "132"),
        _team_row(25, "Paris Saint-Germain", "PSG", "soccer_france_ligue_one", "160"),
    ]
    events = [
        _event_row(9001, "icehockey_nhl", "Anaheim Ducks", "Seattle Kraken", 0.51, 3),
        _event_row(9002, "icehockey_nhl", "Utah Mammoth", "Winnipeg Jets", 0.49, 5),
        _event_row(9003, "icehockey_nhl", "Winnipeg Jets", "Seattle Kraken", 0.62, 24),
        _event_row(9004, "icehockey_nhl", "Anaheim Ducks", "Winnipeg Jets", 0.66, 30),
        _event_row(9005, "icehockey_nhl", "Utah Mammoth", "Seattle Kraken", 0.68, 40),
        _event_row(9101, "basketball_ncaab", "Duke Blue Devils", "Houston Cougars", 0.68, 4),
        _event_row(9102, "basketball_ncaab", "Florida Gators", "Kansas Jayhawks", 0.72, 8),
        _event_row(9103, "basketball_ncaab", "Florida Gators", "Duke Blue Devils", 0.64, 26),
    ]

    def _mkt(
        mid: int,
        name: str,
        cat: str,
        outs: list[tuple[int, str, float]],
        *,
        sport: str | None = None,
    ) -> dict:
        return {
            "id": mid,
            "name": name,
            "status": "open",
            "source": "kalshi",
            "category": cat,
            "sport": sport,
            "volume": 500_000,
            "outcomes": [{"id": oid, "name": oname, "probability": prob} for oid, oname, prob in outs],
        }

    markets = [
        _mkt(5388752, "Oscar nominees: Best Actor", "entertainment", [(53887521, "John Malkovich", 0.94), (53887522, "Andrew Scott", 0.92), (53887523, "Matt Damon", 0.93)]),
        _mkt(5869749, "Oscar Winner: Best Actor", "entertainment", [(58697491, "John Malkovich", 0.47), (58697492, "Andrew Scott", 0.25), (58697493, "Matt Damon", 0.15)]),
        _mkt(5869747, "Oscar Winner: Best Director", "entertainment", [(58697471, "Christopher Nolan", 0.61), (58697472, "Denis Villeneuve", 0.17)]),
        _mkt(58492239, "Oscars 2027: Best Animated Feature Film Winner", "entertainment", [(584922391, "Wildwood", 0.87), (584922392, "Toy Story 5", 0.07)]),
        _mkt(58492240, "Oscars 2027: Best Supporting Actress Winner", "entertainment", [(584922401, "Anne Hathaway", 0.63), (584922402, "Amanda Seyfried", 0.21)]),
        _mkt(58492236, "Oscars 2027: Best Original Screenplay Winner", "entertainment", [(584922361, "Wild Horse Nine", 0.61), (584922362, "Club Kid", 0.13)]),
        _mkt(181, "College Football National Championship Winner", "football", [(1811, "Georgia", 0.35), (1812, "Notre Dame", 0.17), (1813, "Texas", 0.11), (1814, "Alabama", 0.09)], sport="americanfootball_ncaaf"),
        _mkt(232, "College Football Big Ten Championship Winner", "football", [(2321, "Oregon", 0.50), (2322, "Indiana", 0.20), (2323, "Ohio State", 0.15)], sport="americanfootball_ncaaf"),
        _mkt(234, "College Football Big 12 Championship Winner", "football", [(2341, "Utah", 0.56), (2342, "Texas Tech", 0.38), (2343, "BYU", 0.06)], sport="americanfootball_ncaaf"),
        _mkt(4121125, "College Football Pac-12 Championship Winner", "football", [(41211251, "Boise St.", 0.87), (41211252, "San Diego St.", 0.12), (41211253, "Fresno St.", 0.01)], sport="americanfootball_ncaaf"),
        _mkt(233, "College Football SEC Championship Winner", "football", [(2331, "Georgia", 0.69), (2332, "Texas", 0.26), (2333, "Alabama", 0.05)], sport="americanfootball_ncaaf"),
        _mkt(53675, "AFC West Division Winner", "football", [(536751, "Denver", 0.55), (536752, "Kansas City", 0.43), (536753, "Las Vegas", 0.02)], sport="americanfootball_nfl"),
        _mkt(53673, "NFC North Division Winner", "football", [(536731, "Minnesota", 0.37), (536732, "Chicago", 0.31), (536733, "Detroit", 0.30)], sport="americanfootball_nfl"),
        _mkt(53672, "NFC South Division Winner", "football", [(536721, "Carolina", 0.51), (536722, "Tampa Bay", 0.27), (536723, "Atlanta", 0.11)], sport="americanfootball_nfl"),
        _mkt(53671, "NFC West Division Winner", "football", [(536711, "San Francisco", 0.87), (536712, "Seattle", 0.09), (536713, "Los Angeles", 0.04)], sport="americanfootball_nfl"),
        _mkt(70732920, "EPL: 2027 Champion", "soccer", [(707329201, "Arsenal", 0.73), (707329202, "Liverpool", 0.14), (707329203, "Brighton", 0.06)], sport="soccer_epl"),
        _mkt(70732921, "LALIGA: 2027 Champion", "soccer", [(707329211, "Barcelona", 0.67), (707329212, "Real Madrid", 0.31), (707329213, "Atlético Madrid", 0.02)], sport="soccer_spain_la_liga"),
        _mkt(70732919, "Serie A: 2027 Champion", "soccer", [(707329191, "Inter Milan", 0.57), (707329192, "Como", 0.08), (707329193, "Lazio", 0.06)], sport="soccer_italy_serie_a"),
        _mkt(70732968, "Bundesliga: 2027 Champion", "soccer", [(707329681, "Bayern Munich", 0.76), (707329682, "Borussia Dortmund", 0.16), (707329683, "RB Leipzig", 0.04)], sport="soccer_germany_bundesliga"),
        _mkt(70732922, "Ligue 1: 2027 Champion", "soccer", [(707329221, "Paris Saint-Germain", 0.90), (707329222, "Lille", 0.02), (707329223, "Monaco", 0.02)], sport="soccer_france_ligue_one"),
        _mkt(24647105, "What will OpenAI's IPO valuation be?", "tech", [(246471051, "<$1T", 0.33), (246471052, "$1.0T–$1.25T", 0.22), (246471053, "$1.25T–$1.5T", 0.21)]),
        _mkt(60607595, "OpenAI announces another Millennium Prize solution by...?", "tech", [(606075951, "December 31, 2027", 0.58), (606075952, "December 31, 2026", 0.10)]),
        _mkt(109358, "Will 2026 be the hottest year ever?", "weather", [(1093581, "Yes", 0.91)]),
        _mkt(108220, "Will the world pass 2 degrees Celsius over pre-industrial levels before 2050?", "weather", [(1082201, "Yes", 0.69)]),
        _mkt(61054994, "Will the 2026–27 El Niño be the strongest on record?", "weather", [(610549941, "Yes", 0.58)]),
        _mkt(108294, "8.0 magnitude earthquake in Japan before 2030?", "weather", [(1082941, "Yes", 0.33)]),
    ]
    histories = {
        246471051: [
            {"timestamp": (NOW - timedelta(days=5)).isoformat(), "probability": 0.18},
            {"timestamp": (NOW - timedelta(days=1)).isoformat(), "probability": 0.33},
        ],
        246471053: [
            {"timestamp": (NOW - timedelta(days=5)).isoformat(), "probability": 0.33},
            {"timestamp": (NOW - timedelta(days=1)).isoformat(), "probability": 0.21},
        ],
        606075951: [
            {"timestamp": (NOW - timedelta(days=5)).isoformat(), "probability": 0.44},
            {"timestamp": (NOW - timedelta(days=1)).isoformat(), "probability": 0.58},
        ],
    }
    reg = json.loads(_PAIRED_REGISTER_PATH.read_text(encoding="utf-8"))
    return {
        "events": events,
        "markets": markets,
        "paired_sets": reg.get("sets") or {},
        "market_histories": histories,
        "teams": teams,
    }


def test_batch7_sets_are_preview_and_disjoint_from_prior_batches() -> None:
    clear_fun_markets_cache()
    batch7 = json.loads(BATCH7_CURATED_PATH.read_text(encoding="utf-8"))
    b7_ids = {
        int(e["id"])
        for spec in (batch7.get("sets") or {}).values()
        for e in (spec.get("entries") or ())
    }
    prior_ids: set[int] = set()
    for p in PRIOR_CURATED_PATHS:
        doc = json.loads(p.read_text(encoding="utf-8"))
        for spec in (doc.get("sets") or {}).values():
            for e in (spec.get("entries") or ()):
                prior_ids.add(int(e["id"]))
    assert b7_ids.isdisjoint(prior_ids), f"Overlap with Batch 3-6: {sorted(b7_ids & prior_ids)}"

    categories = set()
    for slug in BATCH7_SLUGS:
        defn = load_machinery_definition(CANDIDATES_DIR / f"{slug}.json")
        assert defn["stage"] == "preview", f"{slug} must stay in preview stage"
        categories.add(defn["category"])
    assert len(categories) >= 5


@pytest.mark.asyncio
async def test_batch7_eight_sets_cover_all_eight_visual_forms_and_clean_copy() -> None:
    clear_fun_markets_cache()
    db = _make_batch7_snapshot()
    seen_forms: set[str] = set()

    for slug in BATCH7_SLUGS:
        defn = load_machinery_definition(CANDIDATES_DIR / f"{slug}.json")
        prod = build_container_machinery_producer(defn)
        res = await produce_container_machinery(db, defn, now=NOW)
        feed_item = sanitize_discover_feed_item(compose_roundup_feed_item(prod, res))
        container = compose_roundup_container(prod, res)
        assert container["state"] == "published", slug
        card_parity, page_parity = _compute_member_number_parity(feed_item, container)
        assert card_parity["passes"] is True and page_parity["passes"] is True, slug
        card = feed_item["data"]["roundup"]["machinery_card"]
        seen_forms.add(card["form_id"])
        if card["form_id"] == "probability_history_chart":
            assert card["title"] == "The chance OpenAI lists below $1T rose 15 points since Nov 17"
            assert card["subtitle"] == (
                "Pricing on OpenAI's IPO valuation and Millennium Prize milestones shifted sharply over the past week."
            )
            assert card["mini_chart"]["title"] == "OpenAI's IPO valuation"
            assert len(card["rows"]) == 3
        elif card["form_id"] == "duel_bar":
            assert card["title"].startswith("Denver leads Kansas City")
            assert card["title"].endswith("in the AFC West race")
            assert len(card["rows"]) == 2
            assert min(r["rendered_percent"] for r in card["rows"]) >= 20
        elif card["slug"] == "machinery-extreme-earth-2026":
            assert card["title"] == (
                "2026 is at 91% to be the hottest year on record, and 2°C of warming before 2050 is at 69%"
            )
            assert card.get("image_url", "").endswith("Top_of_Atmosphere.jpg")
        elif card["slug"] == "machinery-college-basketball-slate":
            assert card["title"] == "Florida at Duke headlines the Nov 22–23 slate"

    assert seen_forms == set(MACHINERY_FORM_IDS)


@pytest.mark.asyncio
async def test_batch7_fable_fixes_big_ten_college_slate_and_history_first_to_last() -> None:
    from app.utils.container_machinery import _history_chart_moved, _prose_market_phrase

    # 1. Phrase casing: only "big ten", never standalone "big" or "ten"
    assert _prose_market_phrase("Big Ten Championship") == "the Big Ten championship"
    assert _prose_market_phrase("Big Tech Deals") == "the big tech deals"
    assert _prose_market_phrase("Top Ten Releases") == "the top ten releases"

    # 2. History swing checks first-to-last, not peak-to-trough
    bounced_flat = {
        "series": [
            {
                "outcome_id": 1,
                "current_pct": 29,
                "points": [
                    {"t": "2026-11-19T17:00:00+00:00", "pct": 26},
                    {"t": "2026-11-20T17:00:00+00:00", "pct": 40},
                    {"t": "2026-11-22T17:00:00+00:00", "pct": 29},
                ],
            }
        ]
    }
    assert _history_chart_moved(bounced_flat, min_swing_pp=10) is False

    # 3. College basketball slate: school names, drops 0%-100% & completed, visible-card toss-ups & closest game lead
    db = {
        "teams": [
            _team_row(101, "UAB Blazers", "UAB", "basketball_ncaab", "5"),
            _team_row(102, "Rhode Island Rams", "URI", "basketball_ncaab", "227"),
            _team_row(103, "Long Beach St 49ers", "LBSU", "basketball_ncaab", "299"),
            _team_row(104, "Florida Int'l Golden Panthers", "FIU", "basketball_ncaab", "2229"),
        ],
        "events": [
            # Completed game should be filtered out
            {**_event_row(9200, "basketball_ncaab", "UAB Blazers", "Rhode Island Rams", 0.50, -1), "status": "completed"},
            # Decided 0%-100% game should be filtered out even if status not yet flipped
            _event_row(9201, "basketball_ncaab", "Long Beach St 49ers", "Florida Int'l Golden Panthers", 0.996, 1),
            # Row 1: 34%-66%
            _event_row(9202, "basketball_ncaab", "Long Beach St 49ers", "Florida Int'l Golden Panthers", 0.66, 2),
            # Row 2 (closest visible toss-up on card): 49%-51%
            _event_row(9203, "basketball_ncaab", "UAB Blazers", "Rhode Island Rams", 0.51, 3),
            # Row 3: 30%-70%
            _event_row(9204, "basketball_ncaab", "Duke Blue Devils", "Houston Cougars", 0.70, 4),
            # Row 4 (off card): another 50%-50% toss-up that must NOT inflate card headline count
            _event_row(9205, "basketball_ncaab", "Kansas Jayhawks", "Florida Gators", 0.50, 5),
        ],
        "markets": [],
        "paired_sets": {},
        "market_histories": {},
    }
    defn = load_machinery_definition(CANDIDATES_DIR / "machinery-college-basketball-slate.json")
    prod = build_container_machinery_producer(defn)
    res = await produce_container_machinery(db, defn, now=NOW)
    card = sanitize_discover_feed_item(compose_roundup_feed_item(prod, res))["data"]["roundup"]["machinery_card"]
    row_matchups = [(r["away_short"], r["home_short"], r["away_pct"], r["home_pct"]) for r in card["rows"]]
    assert ("UAB", "Rhode Island", 49, 51) in row_matchups
    assert ("Long Beach St", "Florida Int'l", 34, 66) in row_matchups
    assert all(max(r["away_pct"], r["home_pct"]) < 100 for r in card["rows"])
    assert card["title"] == "UAB at Rhode Island headlines the Nov 22 slate"
    assert "Golden" not in str(row_matchups)
    assert "toss-up" not in card["title"]

    # 4. Tech & space fallback when first-to-last < 10 even with peak swing >= 10
    b7_db = _make_batch7_snapshot()
    b7_db["market_histories"] = {
        246471051: [
            {"timestamp": (NOW - timedelta(days=5)).isoformat(), "probability": 0.27},
            {"timestamp": (NOW - timedelta(days=3)).isoformat(), "probability": 0.40},
            {"timestamp": (NOW - timedelta(days=1)).isoformat(), "probability": 0.30},
        ],
        606075951: [
            {"timestamp": (NOW - timedelta(days=2)).isoformat(), "probability": 0.52},
            {"timestamp": (NOW - timedelta(days=1)).isoformat(), "probability": 0.58},
        ],
    }
    tech_defn = load_machinery_definition(CANDIDATES_DIR / "machinery-tech-and-space-movers.json")
    tech_res = await produce_container_machinery(
        b7_db, tech_defn, now=NOW, build_container_fn=None
    ) if False else await produce_container_machinery(b7_db, tech_defn, now=NOW)
    tech_container = compose_roundup_container(build_container_machinery_producer(tech_defn), tech_res)
    assert tech_container["sections"][0]["visual_block"]["form_id"] == "benchmark_strip"
    assert tech_container["sections"][0]["title"] == "Tech & Space Milestone Odds"
    tech_card = sanitize_discover_feed_item(
        compose_roundup_feed_item(build_container_machinery_producer(tech_defn), tech_res)
    )["data"]["roundup"]["machinery_card"]
    assert "James_Webb_Primary_Mirror.jpg" in str(tech_card.get("image_url") or "")

    # And when the history DOES move >= 10 pts first-to-last, mini_chart is kept and image_url is omitted.
    b7_db_moved = _make_batch7_snapshot()
    b7_db_moved["market_histories"] = {
        246471051: [
            {"timestamp": (NOW - timedelta(days=5)).isoformat(), "probability": 0.18},
            {"timestamp": (NOW - timedelta(days=3)).isoformat(), "probability": 0.25},
            {"timestamp": (NOW - timedelta(days=1)).isoformat(), "probability": 0.30},
        ],
        606075951: [
            {"timestamp": (NOW - timedelta(days=2)).isoformat(), "probability": 0.52},
            {"timestamp": (NOW - timedelta(days=1)).isoformat(), "probability": 0.58},
        ],
    }
    moved_res = await produce_container_machinery(b7_db_moved, tech_defn, now=NOW)
    moved_card = sanitize_discover_feed_item(
        compose_roundup_feed_item(build_container_machinery_producer(tech_defn), moved_res)
    )["data"]["roundup"]["machinery_card"]
    assert moved_card["form_id"] == "probability_history_chart"
    assert moved_card.get("mini_chart") is not None
    assert not moved_card.get("image_url")
