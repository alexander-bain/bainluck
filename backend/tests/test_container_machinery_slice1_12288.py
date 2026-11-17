"""Tests for #12288 Slice 1: topic-free container machinery (Direction 223 & Decision 224).

Proves:
1. All three Slice-1 candidate definitions (NFL Week, Oscars Best Picture, 2028 Presidential Race)
   live in ``backend/data/discover/candidates/``, stay switched OFF by default, contain ZERO
   hand-placed market or event IDs, and pass ``validate_roundup_definition`` (60-A, 71-A, 73-A).
2. ``choose_section_form`` selects each visual form purely from atom data shape (zero topic checks).
3. One single ``produce_container_machinery`` code path produces BOTH the Discover card
   (``compose_roundup_feed_item``) AND the multi-section container page (``compose_roundup_container``)
   across all three topics, reusing ``#12849``'s ``paired_metric_set`` for Oscars Best Picture,
   deduplicating members across sections, refusing non-trading/closed markets, and resolving
   verified subject imagery on teams, people, and films.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import pytest

from app.utils.container_machinery import (
    CANDIDATE_2028_PRESIDENTIAL_PATH,
    CANDIDATE_NFL_WEEK_PATH,
    CANDIDATE_OSCARS_BEST_PICTURE_PATH,
    MACHINERY_CANDIDATE_PATHS,
    SubjectArtResolver,
    build_container_machinery_producer,
    choose_section_form,
    container_machinery_enabled,
    load_machinery_definition,
    produce_container_machinery,
)
from app.utils.roundup_containers import (
    CONTAINERS_DATA_DIR,
    HAND_LIST_ID_RULE_KEYS,
    ROUNDUP_PRODUCERS,
    compose_roundup_container,
    compose_roundup_feed_item,
    evaluate_roundup_producer,
)

FIXED_NOW = datetime(2026, 10, 4, 16, 0, 0, tzinfo=timezone.utc)


def _sample_snapshot() -> dict[str, Any]:
    return {
        "events": [
            {
                "id": 9001,
                "sport": "americanfootball_nfl",
                "sport_name": "NFL",
                "away_team": "Baltimore Ravens",
                "home_team": "Carolina Panthers",
                "commence_time": "2026-10-04T17:00:00+00:00",
                "status": "scheduled",
                "current_odds": {"away_probability": 0.48, "home_probability": 0.52},
            },
            {
                "id": 9002,
                "sport": "americanfootball_nfl",
                "sport_name": "NFL",
                "away_team": "Chicago Bears",
                "home_team": "Detroit Lions",
                "commence_time": "2026-10-04T17:00:00+00:00",
                "status": "scheduled",
                "current_odds": {"away_probability": 0.51, "home_probability": 0.49},
            },
            {
                "id": 9003,
                "sport": "americanfootball_nfl",
                "sport_name": "NFL",
                "away_team": "Indianapolis Colts",
                "home_team": "Houston Texans",
                "commence_time": "2026-10-04T20:05:00+00:00",
                "status": "scheduled",
                "current_odds": {"away_probability": 0.15, "home_probability": 0.85},
            },
            {
                "id": 9004,
                "sport": "americanfootball_nfl",
                "sport_name": "NFL",
                "away_team": "Tennessee Titans",
                "home_team": "Dallas Cowboys",
                "commence_time": "2026-10-04T20:25:00+00:00",
                "status": "scheduled",
                "current_odds": {"away_probability": 0.21, "home_probability": 0.79},
            },
        ],
        "paired_sets": {
            "oscars-2027-best-picture": {
                "set_id": "oscars-2027-best-picture",
                "category": "entertainment",
                "kicker": "THE OSCARS · BEST PICTURE",
                "title": "The Odyssey leads Best Picture",
                "subtitle": "Nominated % and Wins % side by side",
                "stage_1_label": "Nominated",
                "stage_2_label": "Wins",
                "stage_1_settled_yes_label": "Nominated",
                "stage_1_settled_no_label": "Not nominated",
                "stage_1_market": {"id": 5165726, "name": "Oscar Nominee: Best Picture", "source": "kalshi"},
                "stage_2_market": {"id": 6173044, "name": "Oscar Winner: Best Picture", "source": "kalshi"},
                "entries": [
                    {
                        "subject_key": "the-odyssey",
                        "subject": "The Odyssey",
                        "detail": "Christopher Nolan",
                        "stage_1_market_id": 5165726,
                        "stage_1_probability": 0.94,
                        "stage_2_market_id": 6173044,
                        "stage_2_probability": 0.52,
                        "art": {
                            "kind": "tmdb_poster",
                            "url": "https://image.tmdb.org/t/p/w342/krVa7rKCQb4OBfsr2LTJv4rTz5q.jpg",
                            "adult": False,
                            "kid_safe_vetted": True,
                        },
                    },
                    {
                        "subject_key": "you-can-see-everything",
                        "subject": "You Can See Everything",
                        "detail": "Feature film",
                        "stage_1_market_id": 5165726,
                        "stage_1_probability": 0.85,
                        "stage_2_market_id": 6173044,
                        "stage_2_probability": 0.20,
                        "art": {
                            "kind": "tmdb_poster",
                            "url": "https://image.tmdb.org/t/p/w342/Ap8QwmKfSjYbWC4XIP8w9pdn72O.jpg",
                            "adult": False,
                            "kid_safe_vetted": True,
                        },
                    },
                    {
                        "subject_key": "dune-part-three",
                        "subject": "Dune: Part Three",
                        "detail": "Denis Villeneuve",
                        "stage_1_market_id": 5165726,
                        "stage_1_probability": 0.81,
                        "stage_2_market_id": 6173044,
                        "stage_2_probability": 0.12,
                        "art": {
                            "kind": "tmdb_poster",
                            "url": "https://image.tmdb.org/t/p/w342/glt0v4I89rMWstDNCaFXc5SNyO1.jpg",
                            "adult": False,
                            "kid_safe_vetted": True,
                        },
                    },
                ],
            }
        },
        "markets": [
            {
                "id": 40532,
                "name": "MVP Winner?",
                "status": "open",
                "source": "kalshi",
                "top_outcomes": [
                    {"id": 1, "name": "Joe Burrow", "probability": 0.48},
                    {"id": 2, "name": "Brock Purdy", "probability": 0.16},
                    {"id": 3, "name": "Josh Allen", "probability": 0.14},
                    {"id": 4, "name": "Trevor Lawrence", "probability": 0.08},
                ],
            },
            {
                "id": 2279147,
                "name": "NFL: NFC North Champion",
                "status": "open",
                "source": "polymarket",
                "top_outcomes": [
                    {"id": 11, "name": "Minnesota Vikings", "probability": 0.38},
                    {"id": 12, "name": "Chicago Bears", "probability": 0.34},
                    {"id": 13, "name": "Detroit Lions", "probability": 0.28},
                ],
            },
            {
                "id": 2248389,
                "name": "NFL: AFC North Champion",
                "status": "open",
                "source": "polymarket",
                "top_outcomes": [
                    {"id": 21, "name": "Cincinnati Bengals", "probability": 0.62},
                    {"id": 22, "name": "Pittsburgh Steelers", "probability": 0.22},
                    {"id": 23, "name": "Baltimore Ravens", "probability": 0.16},
                ],
            },
            {
                "id": 5869747,
                "name": "Oscar Winner: Best Director",
                "status": "open",
                "source": "kalshi",
                "top_outcomes": [
                    {"id": 31, "name": "Christopher Nolan", "probability": 0.55},
                    {"id": 32, "name": "Denis Villeneuve", "probability": 0.20},
                    {"id": 33, "name": "Nathan Fielder", "probability": 0.13},
                ],
            },
            {
                "id": 5869749,
                "name": "Oscar Winner: Best Actor",
                "status": "open",
                "source": "kalshi",
                "top_outcomes": [
                    {"id": 41, "name": "John Malkovich", "probability": 0.43},
                    {"id": 42, "name": "Andrew Scott", "probability": 0.21},
                    {"id": 43, "name": "Matt Damon", "probability": 0.16},
                ],
            },
            {
                "id": 5869748,
                "name": "Oscar winner: Best Actress",
                "status": "open",
                "source": "kalshi",
                "top_outcomes": [
                    {"id": 51, "name": "Julianne Moore", "probability": 0.75},
                    {"id": 52, "name": "Inde Navarrette", "probability": 0.12},
                    {"id": 53, "name": "Sandra Hüller", "probability": 0.08},
                ],
            },
            {
                "id": 108327,
                "name": "2028 Presidential Election winner? (Party)",
                "status": "open",
                "source": "kalshi",
                "top_outcomes": [
                    {"id": 61, "name": "Democratic party", "probability": 0.68},
                    {"id": 62, "name": "Republican party", "probability": 0.32},
                ],
            },
            {
                "id": 112897,
                "name": "Presidential Election Winner 2028",
                "status": "open",
                "source": "polymarket",
                "top_outcomes": [
                    {"id": 71, "name": "Jon Ossoff", "probability": 0.18},
                    {"id": 72, "name": "JD Vance", "probability": 0.15},
                    {"id": 73, "name": "Alexandria Ocasio-Cortez", "probability": 0.09},
                    {"id": 74, "name": "Gavin Newsom", "probability": 0.08},
                ],
            },
            {
                "id": 112895,
                "name": "Democratic Presidential Nominee 2028",
                "status": "open",
                "source": "polymarket",
                "top_outcomes": [
                    {"id": 81, "name": "Jon Ossoff", "probability": 0.26},
                    {"id": 82, "name": "Alexandria Ocasio-Cortez", "probability": 0.15},
                    {"id": 83, "name": "Gavin Newsom", "probability": 0.10},
                ],
            },
            {
                "id": 112900,
                "name": "Republican Presidential Nominee 2028",
                "status": "open",
                "source": "polymarket",
                "top_outcomes": [
                    {"id": 91, "name": "J.D. Vance", "probability": 0.37},
                    {"id": 92, "name": "Marco Rubio", "probability": 0.16},
                    {"id": 93, "name": "Ron DeSantis", "probability": 0.15},
                ],
            },
            {
                "id": 131074,
                "name": "Will the 2028 Democratic Presidential nominee be a woman?",
                "status": "open",
                "source": "kalshi",
                "top_outcomes": [{"id": 101, "name": "Yes", "probability": 0.22}],
            },
            {
                "id": 108442,
                "name": "Will a Trump family member be the 2028 Republican presidential nominee?",
                "status": "open",
                "source": "kalshi",
                "top_outcomes": [{"id": 102, "name": "Yes", "probability": 0.04}],
            },
            {
                "id": 999999,
                "name": "Closed stale 2028 Presidential Election winner? (Party)",
                "status": "closed",
                "source": "kalshi",
                "top_outcomes": [
                    {"id": 901, "name": "Democratic party", "probability": 0.50},
                    {"id": 902, "name": "Republican party", "probability": 0.50},
                ],
            },
        ],
    }


def test_slice1_candidates_are_switched_off_and_contain_zero_hand_placed_ids() -> None:
    assert container_machinery_enabled() is False
    for path in MACHINERY_CANDIDATE_PATHS:
        assert path.exists()
        assert not (CONTAINERS_DATA_DIR / path.name).exists()
        raw = json.loads(path.read_text(encoding="utf-8"))
        validated = load_machinery_definition(path)
        assert validated["slug"] not in ROUNDUP_PRODUCERS
        for bad_key in HAND_LIST_ID_RULE_KEYS:
            assert bad_key not in raw.get("rule", {})
        serialized = json.dumps(raw)
        assert "market_id" not in serialized
        assert "event_id" not in serialized


def test_choose_section_form_is_purely_data_shape_driven() -> None:
    assert choose_section_form("paired_stage", [{}, {}, {}]) == "paired_stage_bars"
    assert (
        choose_section_form("events", [{"fav_prob": 0.52}, {"fav_prob": 0.58}])
        == "coin_flip_matchups"
    )
    assert (
        choose_section_form("events", [{"fav_prob": 0.85}, {"fav_prob": 0.79}])
        == "matchup_slate"
    )
    assert choose_section_form("markets", [{"outcomes": [{}, {}]}]) == "duel_bar"
    assert (
        choose_section_form("markets", [{"outcomes": [{}, {}, {}, {}]}])
        == "contender_spotlight"
    )
    assert (
        choose_section_form(
            "markets", [{"outcomes": [{}, {}, {}]}, {"outcomes": [{}, {}, {}]}]
        )
        == "sibling_fields_grid"
    )
    assert (
        choose_section_form("markets", [{"outcomes": [{}]}, {"outcomes": [{}]}])
        == "benchmark_strip"
    )


@pytest.mark.asyncio
async def test_same_code_path_produces_card_and_container_for_nfl_awards_and_politics() -> None:
    snap = _sample_snapshot()

    # 1. NFL Week
    nfl_def = load_machinery_definition(CANDIDATE_NFL_WEEK_PATH)
    nfl_prod = build_container_machinery_producer(nfl_def, enabled=lambda: True)
    nfl_card, nfl_page = await evaluate_roundup_producer(nfl_prod, snap, now=FIXED_NOW)
    assert nfl_card is not None and nfl_page is not None
    assert nfl_card["data"]["collection_ref"]["href"] == "/collections/machinery-nfl-week"
    assert nfl_card["data"]["roundup"]["machinery_card"]["form_id"] == "coin_flip_matchups"
    nfl_forms = [s["visual_block"]["form_id"] for s in nfl_page["sections"]]
    assert nfl_forms == [
        "coin_flip_matchups",
        "matchup_slate",
        "contender_spotlight",
        "sibling_fields_grid",
    ]
    # Disjoint member IDs across sections so parseCollection never marks partial
    nfl_sec_ids = [[m["id"] for m in s["members"]] for s in nfl_page["sections"]]
    flat_nfl_ids = [i for sub in nfl_sec_ids for i in sub]
    assert len(flat_nfl_ids) == len(set(flat_nfl_ids))
    # Every NFL MVP contender and team resolves a verified image URL
    mvp_outcomes = nfl_page["sections"][2]["visual_block"]["items"][0]["outcomes"]
    assert all(o["art"]["url"].startswith("https://a.espncdn.com/") for o in mvp_outcomes)

    # 2. Oscars Best Picture (reuses #12849 paired_metric_set on card and page)
    osc_def = load_machinery_definition(CANDIDATE_OSCARS_BEST_PICTURE_PATH)
    osc_prod = build_container_machinery_producer(osc_def, enabled=lambda: True)
    osc_card, osc_page = await evaluate_roundup_producer(osc_prod, snap, now=FIXED_NOW)
    assert osc_card is not None and osc_page is not None
    assert osc_card["data"]["roundup"]["paired_metric_set"]["set_id"] == "oscars-2027-best-picture"
    osc_forms = [s["visual_block"]["form_id"] for s in osc_page["sections"]]
    assert osc_forms == ["paired_stage_bars", "contender_spotlight", "sibling_fields_grid"]
    dir_outcomes = osc_page["sections"][1]["visual_block"]["items"][0]["outcomes"]
    assert all(o["art"]["url"].startswith("https://image.tmdb.org/") for o in dir_outcomes)

    # 3. 2028 Presidential Race (refuses closed market 999999; resolves verified portraits)
    pol_def = load_machinery_definition(CANDIDATE_2028_PRESIDENTIAL_PATH)
    pol_prod = build_container_machinery_producer(pol_def, enabled=lambda: True)
    pol_card, pol_page = await evaluate_roundup_producer(pol_prod, snap, now=FIXED_NOW)
    assert pol_card is not None and pol_page is not None
    assert pol_card["data"]["roundup"]["machinery_card"]["form_id"] == "contender_spotlight"
    pol_forms = [s["visual_block"]["form_id"] for s in pol_page["sections"]]
    assert pol_forms == [
        "duel_bar",
        "contender_spotlight",
        "sibling_fields_grid",
        "benchmark_strip",
    ]
    pol_member_ids = {m["id"] for s in pol_page["sections"] for m in s["members"]}
    assert 999999 not in pol_member_ids
    pres_outcomes = pol_page["sections"][1]["visual_block"]["items"][0]["outcomes"]
    assert all(o["art"]["url"].startswith("https://thumb.wikimedia.org/") for o in pres_outcomes)
    assert compose_roundup_container(pol_prod, await produce_container_machinery(snap, pol_def, now=FIXED_NOW)) is not None
    assert compose_roundup_feed_item(pol_prod, await produce_container_machinery(snap, pol_def, now=FIXED_NOW)) is not None


def test_subject_art_resolver_excludes_horror_and_falls_back_to_monogram() -> None:
    resolver = SubjectArtResolver()
    burrow = resolver.resolve("Joe Burrow")
    assert burrow["url"] == "https://a.espncdn.com/i/headshots/nfl/players/full/3915511.png"
    vance = resolver.resolve("J.D. Vance")
    assert vance["url"] and "wikimedia.org" in vance["url"]
    unknown = resolver.resolve("Unlisted Challenger")
    assert unknown["url"] is None
    assert unknown["initials"] == "UC"


def test_slice2_bar_no_question_word_proper_case_and_definition_only_fourth_grouping(
    tmp_path: Any,
) -> None:
    from app.utils.container_machinery import (
        _proper_case_outcome_label,
        discover_machinery_candidate_paths,
    )

    # 1. All 4 unlike groupings discovered automatically (including machinery-fed-and-macro.json)
    paths = discover_machinery_candidate_paths()
    slugs = [load_machinery_definition(p)["slug"] for p in paths]
    assert slugs == [
        "machinery-2028-presidential",
        "machinery-fed-and-macro",
        "machinery-nfl-week",
        "machinery-oscars-best-picture",
    ]

    # 2. Proper-casing miscased names without mangling numeric/rate brackets
    assert _proper_case_outcome_label("Anne hathaway") == "Anne Hathaway"
    assert _proper_case_outcome_label("Hike 25bps") == "Hike 25bps"
    assert _proper_case_outcome_label("Fed maintains rate") == "Fed maintains rate"
    assert _proper_case_outcome_label("Democratic party") == "Democratic party"

    # 3. Calling a market a 'question' in definition copy is rejected
    bad = json.loads(CANDIDATE_2028_PRESIDENTIAL_PATH.read_text(encoding="utf-8"))
    bad["rule"]["sections"][-1]["note"] = "Yes-or-no questions on the ticket."
    bad_path = tmp_path / "machinery-bad.json"
    bad_path.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(ValueError, match="question"):
        load_machinery_definition(bad_path)


@pytest.mark.asyncio
async def test_ruling_227a_visual_diversity_report_and_primitives_doc() -> None:
    from pathlib import Path
    from app.utils.container_machinery import (
        CANDIDATE_FED_AND_MACRO_PATH,
        compute_visual_diversity_report,
    )

    # 1. docs/design/grouping-primitives.md records 227: A under Sets and Presentations
    doc_path = Path(__file__).resolve().parents[2] / "docs" / "design" / "grouping-primitives.md"
    doc_text = doc_path.read_text(encoding="utf-8")
    sets_part = doc_text.split("### 3. Sets", 1)[1].split("### 4. Presentations", 1)[0]
    pres_part = doc_text.split("### 4. Presentations", 1)[1].split("### 5. Triggers", 1)[0]
    assert "227: A" in sets_part and "60%" in sets_part
    assert "227: A" in pres_part and "A picture on every screen" in pres_part

    # 2. Report-only diversity report computes points 1–4 without blocking serving
    snap = _sample_snapshot()
    nfl_def = load_machinery_definition(CANDIDATE_NFL_WEEK_PATH)
    nfl_prod = build_container_machinery_producer(nfl_def, enabled=lambda: True)
    nfl_card, nfl_page = await evaluate_roundup_producer(nfl_prod, snap, now=FIXED_NOW)
    rep = compute_visual_diversity_report(nfl_def, nfl_card, nfl_page)
    assert rep["standard"] == "227-A"
    assert rep["report_only"] is True
    assert rep["card"]["point_1_pictures_per_screen_390px"]["passes"] is True
    assert rep["page"]["point_1_pictures_per_screen_390px"]["passes"] is True
    assert rep["page"]["point_3_forms"]["form_count"] == 4
    assert rep["page"]["point_4_content_mix"]["content_kinds"]["games"] >= 1
    assert rep["page"]["point_4_content_mix"]["content_kinds"]["futures"] >= 1

    # Fed & Macro definition loads cleanly as 4th topic with zero topic code
    fed_def = load_machinery_definition(CANDIDATE_FED_AND_MACRO_PATH)
    assert fed_def["slug"] == "machinery-fed-and-macro"


@pytest.mark.asyncio
async def test_admin_only_machinery_preview_blocks_public_and_serves_admin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from types import SimpleNamespace
    from fastapi import HTTPException
    from app.routes import admin_utils
    from app.routes.containers import get_container, get_machinery_preview

    monkeypatch.setenv("CONTAINERS_READ_ENABLED", "true")
    monkeypatch.setenv("CONTAINER_MACHINERY_SLICE1_ENABLED", "false")

    snap = _sample_snapshot()
    req_anon = SimpleNamespace(headers={}, url=SimpleNamespace(path="/api/containers/preview/machinery"))
    req_admin = SimpleNamespace(
        headers={"Authorization": "Bearer admin-ok"},
        url=SimpleNamespace(path="/api/containers/preview/machinery"),
    )

    async def _fake_admin_auth(secret: Any, request: Any, db: Any = None) -> bool:
        auth = (getattr(request, "headers", None) or {}).get("Authorization", "")
        return auth == "Bearer admin-ok"

    monkeypatch.setattr(admin_utils, "_check_admin_auth", _fake_admin_auth)

    # 1. Anonymous caller is denied on preview endpoint
    with pytest.raises(HTTPException) as exc_info:
        await get_machinery_preview(request=req_anon, slugs="machinery-nfl-week", db=snap)
    assert exc_info.value.status_code == 403

    # 2. Admin caller receives preview items + 227-A diversity_report while switch stays OFF
    preview_res = await get_machinery_preview(
        request=req_admin, slugs="machinery-nfl-week,machinery-2028-presidential", db=snap
    )
    assert preview_res["public_switch_enabled"] is False
    assert preview_res["count"] == 2
    assert [it["slug"] for it in preview_res["items"]] == [
        "machinery-nfl-week",
        "machinery-2028-presidential",
    ]
    assert preview_res["items"][0]["diversity_report"]["standard"] == "227-A"

    # 3. Direct /api/containers/machinery-nfl-week returns 200 for admin while global switch is OFF
    hub_res = await get_container(
        request=req_admin,
        slug="machinery-nfl-week",
        include_children=True,
        revision=None,
        cursor=None,
        limit=None,
        market_revision=None,
        market_cursor=None,
        market_limit=None,
        compact=True,
        debug_timing=False,
        db=snap,
    )
    assert hub_res["slug"] == "machinery-nfl-week"
    assert hub_res["state"] == "published"
