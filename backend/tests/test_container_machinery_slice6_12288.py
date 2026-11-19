"""#12288 Slice 6 tests:
2a. First section never repeats the page headline (Oscars embedded paired card & section 0 heading).
2b. Every number on a card or page equals that member's own page at the same moment; report fails on any mismatch.
2c. Failed reads surface an explicit error state, never an empty or shorter grouping.
"""

from __future__ import annotations

import copy
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from app.utils.container_machinery import (
    CANDIDATE_2028_PRESIDENTIAL_PATH,
    CANDIDATE_NFL_WEEK_PATH,
    CANDIDATE_OSCARS_BEST_PICTURE_PATH,
    compute_visual_diversity_report,
    discover_machinery_candidate_paths,
    evaluate_machinery_candidates_preview,
    load_machinery_definition,
    produce_container_machinery,
    serve_machinery_candidate_preview,
)
from tests.test_container_machinery_slice1_12288 import FIXED_NOW, _sample_snapshot

CORE_FOUR_SLUGS = [
    "machinery-nfl-week",
    "machinery-oscars-best-picture",
    "machinery-2028-presidential",
    "machinery-fed-and-macro",
]


@pytest.mark.asyncio
async def test_slice6_2a_oscars_and_section0_never_repeat_page_headline() -> None:
    snap = _sample_snapshot()
    oscars = await serve_machinery_candidate_preview(
        "machinery-oscars-best-picture", snap, now=FIXED_NOW
    )
    assert oscars is not None and oscars["status"] == "ok"
    page_headline = oscars["container"]["container"]["name"]
    sec0 = oscars["container"]["sections"][0]
    assert sec0["title"].strip().casefold() != page_headline.strip().casefold()
    # Embedded paired card inside section 0 suppresses its duplicate internal header
    assert (
        sec0["visual_block"]["paired_metric_set"]["suppress_card_header_in_section"]
        is True
    )
    # Standalone Discover card keeps its own header
    card_pms = oscars["feed_item"]["data"]["roundup"]["paired_metric_set"]
    assert card_pms["suppress_card_header_in_section"] is False

    # Even if a definition's section 0 title matches the dynamic page headline verbatim,
    # produce_container_machinery replaces or suppresses it so it never repeats twice in a row.
    defn = load_machinery_definition(CANDIDATE_OSCARS_BEST_PICTURE_PATH)
    defn_dup = copy.deepcopy(defn)
    defn_dup["rule"]["sections"][0]["title"] = page_headline
    defn_dup["rule"]["sections"][0]["fallback_title"] = "Category Contenders"
    outcome = await produce_container_machinery(snap, defn_dup, now=FIXED_NOW)
    assert outcome.sections[0]["title"] == "Category Contenders"
    assert outcome.sections[0]["title"].casefold() != outcome.title.casefold()


@pytest.mark.asyncio
async def test_slice6_2b_member_page_number_parity_passes_all_four_and_fails_on_drift() -> (
    None
):
    snap = _sample_snapshot()
    # Inject aKalshi-style vig pair (0.675 + 0.335 = 1.01) on 2028 Party Control (#108327):
    # /futures/108327 normalizes 0.675/1.01 -> 67% and 0.335/1.01 -> 33% (NOT 68% / 32%).
    for m in snap["markets"]:
        if int(m["id"]) == 108327:
            m["top_outcomes"] = [
                {"id": 501, "name": "Democratic Party", "probability": 0.675},
                {"id": 502, "name": "Republican Party", "probability": 0.335},
            ]

    items = await evaluate_machinery_candidates_preview(
        snap, slugs=CORE_FOUR_SLUGS, now=FIXED_NOW
    )
    assert len(items) == 4
    by_slug = {it["slug"]: it for it in items}

    # Verify 108327 normalized to 67% / 33% matching /futures/108327
    pol_sec0_outs = by_slug["machinery-2028-presidential"]["container"]["sections"][0][
        "visual_block"
    ]["items"][0]["outcomes"]
    assert [o["rendered_percent"] for o in pol_sec0_outs] == [67, 33]
    assert (
        "67%"
        in by_slug["machinery-2028-presidential"]["container"]["container"]["name"]
    )

    # Every grouping passes member_number_parity with 0 mismatches across card & page
    for it in items:
        rep = it["diversity_report"]
        assert rep is not None
        assert rep["overall_passes"] is True, f"{it['slug']} failed: {rep}"
        assert rep["member_number_parity"]["passes"] is True
        assert rep["member_number_parity"]["checked_numbers"] >= 8
        assert rep["member_number_parity"]["mismatch_count"] == 0
        assert rep["card"]["member_number_parity"]["passes"] is True
        assert rep["page"]["member_number_parity"]["passes"] is True

    # 1. Drift on a market outcome's own page fails the grouping
    pol_entry = copy.deepcopy(by_slug["machinery-2028-presidential"])
    pol_defn = load_machinery_definition(CANDIDATE_2028_PRESIDENTIAL_PATH)
    pol_entry["container"]["sections"][0]["visual_block"]["items"][0]["outcomes"][0][
        "rendered_percent"
    ] = 68
    bad_pol_report = compute_visual_diversity_report(
        pol_defn, pol_entry["feed_item"], pol_entry["container"]
    )
    assert bad_pol_report["overall_passes"] is False
    assert bad_pol_report["member_number_parity"]["passes"] is False
    assert bad_pol_report["member_number_parity"]["mismatch_count"] >= 1
    assert "member_number_parity" in bad_pol_report["page"]["failing_points"]

    # 2. Drift on a Discover card row fails card & overall report
    nfl_entry = copy.deepcopy(by_slug["machinery-nfl-week"])
    nfl_defn = load_machinery_definition(CANDIDATE_NFL_WEEK_PATH)
    nfl_entry["feed_item"]["data"]["roundup"]["machinery_card"]["rows"][0][
        "away_pct"
    ] += 1
    bad_nfl_report = compute_visual_diversity_report(
        nfl_defn, nfl_entry["feed_item"], nfl_entry["container"]
    )
    assert bad_nfl_report["overall_passes"] is False
    assert bad_nfl_report["card"]["overall_passes"] is False
    assert "member_number_parity" in bad_nfl_report["card"]["failing_points"]

    # 3. Drift on Oscars paired_stage_bars Nominated % vs /futures/5165726 fails the grouping
    osc_entry = copy.deepcopy(by_slug["machinery-oscars-best-picture"])
    osc_defn = load_machinery_definition(CANDIDATE_OSCARS_BEST_PICTURE_PATH)
    osc_entry["container"]["sections"][0]["visual_block"]["paired_metric_set"][
        "entries"
    ][0]["stage_1_rendered_percent"] = 81
    bad_osc_report = compute_visual_diversity_report(
        osc_defn, osc_entry["feed_item"], osc_entry["container"]
    )
    assert bad_osc_report["overall_passes"] is False
    assert bad_osc_report["page"]["overall_passes"] is False
    assert "member_number_parity" in bad_osc_report["page"]["failing_points"]


@pytest.mark.asyncio
async def test_slice6_2c_failed_read_returns_error_state_never_empty_or_shorter_grouping() -> (
    None
):
    snap = _sample_snapshot()

    # Break ONLY Oscars' paired_sets read; the other 3 groupings remain healthy
    broken_oscars_snap = copy.deepcopy(snap)
    broken_oscars_snap["paired_sets"] = {}

    # 1. Direct container read raises HTTP 503 unavailable (never None -> empty unpublished hub)
    with pytest.raises(HTTPException) as exc_info:
        await serve_machinery_candidate_preview(
            "machinery-oscars-best-picture", broken_oscars_snap, now=FIXED_NOW
        )
    assert exc_info.value.status_code == 503
    assert exc_info.value.detail["state"] == "unavailable"
    assert exc_info.value.detail["slug"] == "machinery-oscars-best-picture"

    # 2. Preview list keeps every requested grouping (never drops Oscars to return a shorter list!), with status='error' on Oscars
    preview_items = await evaluate_machinery_candidates_preview(
        broken_oscars_snap, slugs=CORE_FOUR_SLUGS, now=FIXED_NOW
    )
    assert len(preview_items) == 4
    by_slug = {it["slug"]: it for it in preview_items}
    assert by_slug["machinery-oscars-best-picture"]["status"] == "error"
    assert by_slug["machinery-oscars-best-picture"]["container"] is None
    assert "Couldn't load" in by_slug["machinery-oscars-best-picture"]["error"]
    for ok_slug in (
        "machinery-nfl-week",
        "machinery-2028-presidential",
        "machinery-fed-and-macro",
    ):
        assert by_slug[ok_slug]["status"] == "ok"
        assert by_slug[ok_slug]["container"]["state"] == "published"

    # 3. Missing one section inside NFL (e.g. zero division markets) refuses the whole NFL grouping
    #    rather than emitting a shorter 4-section NFL page.
    shorter_nfl_snap = copy.deepcopy(snap)
    shorter_nfl_snap["markets"] = [
        m
        for m in shorter_nfl_snap["markets"]
        if "division" not in m["name"].lower()
        and "north champion" not in m["name"].lower()
    ]
    with pytest.raises(HTTPException) as exc_nfl:
        await serve_machinery_candidate_preview(
            "machinery-nfl-week", shorter_nfl_snap, now=FIXED_NOW
        )
    assert exc_nfl.value.status_code == 503

    # 4. Full DB read exception surfaces status='error' on every grouping (never [] or 500 crash on preview)
    class _ExplodingSession:
        async def execute(self, *_args: object, **_kwargs: object) -> object:
            raise RuntimeError("simulated database connection failure")

    exploded = await evaluate_machinery_candidates_preview(
        _ExplodingSession(), now=FIXED_NOW
    )
    assert len(exploded) == len(discover_machinery_candidate_paths())
    assert all(it["status"] == "error" and it["container"] is None for it in exploded)


@pytest.mark.asyncio
async def test_general_sport_titles_and_single_diacritic_spelling_across_sections() -> (
    None
):
    from datetime import datetime, timezone

    from app.utils.container_machinery import (
        SubjectArtResolver,
        _clean_section_market_label,
        _default_art_resolver,
    )

    _default_art_resolver.cache_clear()
    # 1. General sport/stat/award title cleaning across sports (no per-grouping rewrite)
    assert (
        _clean_section_market_label("Pro Basketball Points Per Game (PPG) Leader")
        == "Points Per Game Leader"
    )
    assert (
        _clean_section_market_label("Pro Basketball Rebounds Per Game (RPG) Leader")
        == "Rebounds Per Game Leader"
    )
    assert (
        _clean_section_market_label(
            "Pro Basketball Defensive Player of the Year Winner"
        )
        == "Defensive Player of the Year"
    )
    assert (
        _clean_section_market_label("Pro Basketball Sixth Man of the Year Winner")
        == "Sixth Man of the Year"
    )
    assert (
        _clean_section_market_label("Pro Baseball Home Runs (HR) Leader")
        == "Home Runs Leader"
    )

    # 2. SubjectArtResolver canonicalizes ASCII 'Luka Doncic' to accented 'Luka Dončić'
    resolver = SubjectArtResolver()
    luka_art = resolver.resolve("Luka Doncic")
    assert luka_art.get("canonical_name") == "Luka Dončić"
    assert luka_art["url"].startswith("https://a.espncdn.com/")

    # 3. Full NBA Slate grouping serves 'Luka Dončić' identically in both stat leaders and MVP tiles
    nba_snap = {
        "events": [
            {
                "id": 9001,
                "sport": "basketball_nba",
                "home_team": "Atlanta Hawks",
                "away_team": "Detroit Pistons",
                "commence_time": "2026-06-16T00:00:00+00:00",
                "status": "scheduled",
                "hero_probability": 0.50,
                "hero_probability_away": 0.50,
            },
            {
                "id": 9002,
                "sport": "basketball_nba",
                "home_team": "Orlando Magic",
                "away_team": "Philadelphia 76ers",
                "commence_time": "2026-06-16T00:30:00+00:00",
                "status": "scheduled",
                "hero_probability": 0.51,
                "hero_probability_away": 0.49,
            },
            {
                "id": 9003,
                "sport": "basketball_nba",
                "home_team": "Boston Celtics",
                "away_team": "Chicago Bulls",
                "commence_time": "2026-06-16T01:00:00+00:00",
                "status": "scheduled",
                "hero_probability": 0.74,
                "hero_probability_away": 0.26,
            },
            {
                "id": 9004,
                "sport": "basketball_nba",
                "home_team": "Cleveland Cavaliers",
                "away_team": "Memphis Grizzlies",
                "commence_time": "2026-06-16T01:30:00+00:00",
                "status": "scheduled",
                "hero_probability": 0.71,
                "hero_probability_away": 0.29,
            },
        ],
        "markets": [
            {
                "id": 8101,
                "name": "Pro Basketball Points Per Game (PPG) Leader",
                "status": "open",
                "source": "kalshi",
                "top_outcomes": [
                    {"id": 81011, "name": "Luka Dončić", "probability": 0.58},
                    {
                        "id": 81012,
                        "name": "Shai Gilgeous-Alexander",
                        "probability": 0.27,
                    },
                    {"id": 81013, "name": "Giannis Antetokounmpo", "probability": 0.15},
                ],
            },
            {
                "id": 8102,
                "name": "Pro Basketball Assists Per Game (APG) Leader",
                "status": "open",
                "source": "kalshi",
                "top_outcomes": [
                    {"id": 81021, "name": "Trae Young", "probability": 0.46},
                    {"id": 81022, "name": "Nikola Jokić", "probability": 0.34},
                    {"id": 81023, "name": "Cade Cunningham", "probability": 0.20},
                ],
            },
            {
                "id": 8103,
                "name": "Pro Basketball MVP Winner",
                "status": "open",
                "source": "kalshi",
                "top_outcomes": [
                    {"id": 81031, "name": "Victor Wembanyama", "probability": 0.43},
                    {"id": 81032, "name": "Luka Doncic", "probability": 0.38},
                    {"id": 81033, "name": "Nikola Jokic", "probability": 0.19},
                ],
            },
            {
                "id": 8104,
                "name": "Pro Basketball Defensive Player of the Year Winner",
                "status": "open",
                "source": "kalshi",
                "top_outcomes": [
                    {"id": 81041, "name": "Victor Wembanyama", "probability": 0.52},
                    {"id": 81042, "name": "Chet Holmgren", "probability": 0.28},
                    {"id": 81043, "name": "Evan Mobley", "probability": 0.20},
                ],
            },
            {
                "id": 8105,
                "name": "Pro Basketball Sixth Man of the Year Winner",
                "status": "open",
                "source": "kalshi",
                "top_outcomes": [
                    {"id": 81051, "name": "Payton Pritchard", "probability": 0.44},
                    {"id": 81052, "name": "Malik Monk", "probability": 0.31},
                    {"id": 81053, "name": "Naz Reid", "probability": 0.25},
                ],
            },
            {
                "id": 8106,
                "name": "Women's Pro Basketball Defensive Player of the Year Winner",
                "status": "open",
                "source": "kalshi",
                "top_outcomes": [
                    {"id": 81061, "name": "A'ja Wilson", "probability": 0.49},
                    {"id": 81062, "name": "Angel Reese", "probability": 0.28},
                    {"id": 81063, "name": "Gabby Williams", "probability": 0.23},
                ],
            },
        ],
        "paired_sets": {},
        "market_histories": {},
    }
    res = await serve_machinery_candidate_preview(
        "machinery-nba-night",
        nba_snap,
        now=datetime(2026, 6, 15, 18, 0, tzinfo=timezone.utc),
    )
    assert res is not None and res["status"] == "ok"
    assert res["diversity_report"]["member_number_parity"]["passes"] is True
    secs = {s["class"]: s for s in res["container"]["sections"]}
    prop_titles = [it["title"] for it in secs["prop_leaders"]["visual_block"]["items"]]
    assert prop_titles == ["Points Per Game Leader", "Assists Per Game Leader"]
    award_titles = [it["title"] for it in secs["award_races"]["visual_block"]["items"]]
    assert award_titles == ["Defensive Player of the Year", "Sixth Man of the Year"]
    mvp_names = [
        o["name"] for o in secs["mvp_race"]["visual_block"]["items"][0]["outcomes"]
    ]
    assert "Luka Dončić" in mvp_names and "Luka Doncic" not in mvp_names
    assert "Nikola Jokić" in mvp_names and "Nikola Jokic" not in mvp_names


@pytest.mark.asyncio
async def test_dotted_initial_spellings_unify_across_sections_and_charts() -> None:
    """'JD Vance' and 'J.D. Vance' unify to one spelling across spotlight, sparklines, and sibling rows."""
    pol_snap = {
        "events": [],
        "markets": [
            {
                "id": 9101,
                "name": "2028 U.S. Presidential Election Party Winner",
                "status": "open",
                "source": "polymarket",
                "top_outcomes": [
                    {"id": 91011, "name": "Democratic Party", "probability": 0.67},
                    {"id": 91012, "name": "Republican Party", "probability": 0.33},
                ],
            },
            {
                "id": 9102,
                "name": "Presidential Election Winner 2028",
                "status": "open",
                "source": "polymarket",
                "top_outcomes": [
                    {"id": 91021, "name": "Jon Ossoff", "probability": 0.22},
                    {"id": 91022, "name": "JD Vance", "probability": 0.18},
                    {
                        "id": 91023,
                        "name": "Alexandria Ocasio-Cortez",
                        "probability": 0.12,
                    },
                ],
            },
            {
                "id": 9103,
                "name": "2028 Iowa Republican Presidential Caucus Winner",
                "status": "open",
                "source": "kalshi",
                "top_outcomes": [
                    {"id": 91031, "name": "J.D. Vance", "probability": 0.31},
                    {"id": 91032, "name": "Marco Rubio", "probability": 0.18},
                    {"id": 91033, "name": "Ron DeSantis", "probability": 0.14},
                ],
            },
            {
                "id": 9104,
                "name": "2028 Republican Presidential Nominee",
                "status": "open",
                "source": "kalshi",
                "top_outcomes": [
                    {"id": 91041, "name": "J.D. Vance", "probability": 0.35},
                    {"id": 91042, "name": "Marco Rubio", "probability": 0.19},
                    {"id": 91043, "name": "Ron DeSantis", "probability": 0.15},
                ],
            },
            {
                "id": 9105,
                "name": "2028 Democratic Presidential Nominee",
                "status": "open",
                "source": "kalshi",
                "top_outcomes": [
                    {"id": 91051, "name": "Jon Ossoff", "probability": 0.28},
                    {
                        "id": 91052,
                        "name": "Alexandria Ocasio-Cortez",
                        "probability": 0.16,
                    },
                    {"id": 91053, "name": "Gavin Newsom", "probability": 0.12},
                ],
            },
        ],
        "paired_sets": {},
        "market_histories": {
            91031: [
                {"timestamp": "2026-06-10T00:00:00+00:00", "probability": 0.24},
                {"timestamp": "2026-06-15T12:00:00+00:00", "probability": 0.31},
            ],
            91032: [
                {"timestamp": "2026-06-10T00:00:00+00:00", "probability": 0.21},
                {"timestamp": "2026-06-15T12:00:00+00:00", "probability": 0.18},
            ],
            91033: [
                {"timestamp": "2026-06-10T00:00:00+00:00", "probability": 0.14},
                {"timestamp": "2026-06-15T12:00:00+00:00", "probability": 0.14},
            ],
        },
    }
    res = await serve_machinery_candidate_preview(
        "machinery-2028-presidential",
        pol_snap,
        now=datetime(2026, 6, 15, 18, 0, tzinfo=timezone.utc),
    )
    assert res is not None and res["status"] == "ok"
    assert res["diversity_report"]["member_number_parity"]["passes"] is True
    secs = {s["class"]: s for s in res["container"]["sections"]}
    iowa_series = [
        s["name"] for s in secs["race_history"]["visual_block"]["items"][0]["series"]
    ]
    assert "JD Vance" in iowa_series and "J.D. Vance" not in iowa_series
    gop_nom_names = [
        o["name"]
        for o in secs["party_nominations"]["visual_block"]["items"][0]["outcomes"]
    ]
    assert "JD Vance" in gop_nom_names and "J.D. Vance" not in gop_nom_names
