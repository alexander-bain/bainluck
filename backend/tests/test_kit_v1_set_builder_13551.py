"""Tests for deterministic real-set Kit v1 builder (Item 3, #13551 & #13584 follow-up)."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone

import pytest

from app.utils.container_machinery import _default_art_resolver
from app.utils.kit_v1_set_builder import (
    REAL_SETS_FIXTURE_PATH,
    _parse_outcome_deadline,
    _restate_source_question,
    build_kit_card_for_real_set,
    build_real_sets_audit_report,
    load_real_sets_audit_report,
)
from app.utils.kit_v1_spec import ALLOWED_MARKS, validate_kit_v1_card

FIXED_NOW = datetime(2026, 11, 24, 6, 40, tzinfo=timezone.utc)


def _load_fixture() -> dict:
    with open(REAL_SETS_FIXTURE_PATH, encoding="utf-8") as f:
        return json.load(f)


def test_real_sets_audit_validates_all_shapes_and_guards() -> None:
    report = load_real_sets_audit_report(now=FIXED_NOW, resolver=_default_art_resolver())
    assert report["kit_version"] == 1
    assert len(report["top_10"]) == 10
    assert report["fitting_count"] + report["kept_today_count"] == report["total_sets"]
    assert report["fitting_count"] >= 20

    all_tested = report["top_10"] + report["fitting_beyond_top_10"]
    layouts_seen = set()
    variants_seen = set()
    for entry in all_tested:
        if entry["fits"]:
            card = entry["kit_card"]
            ok, errs = validate_kit_v1_card(card)
            assert ok, f"{entry['slug']} failed validation: {errs}"
            ok_probe, errs_probe = validate_kit_v1_card(
                dict(card, variant="future_unknown_variant_probe")
            )
            assert ok_probe, f"{entry['slug']} failed unknown variant probe: {errs_probe}"
            assert card["common_headline"].strip()
            assert not card["common_headline"].endswith("?"), entry["slug"]
            assert card["stat_caption"].strip()
            assert card["common_headline"].lower() != card["stat_caption"].lower()
            layouts_seen.add(card["layout"])
            variants_seen.add(card.get("variant"))

            raw_json = json.dumps(card)
            assert "kalshi" not in raw_json.lower()
            assert "polymarket" not in raw_json.lower()
            assert "opens at" not in raw_json.lower()
            assert "bain luck blend" not in raw_json.lower()
            assert "images.pexels.com" not in raw_json.lower()
            for m in re.finditer(r'"(fill_color|color)"\s*:\s*"#', raw_json):
                pytest.fail(f"{entry['slug']} emitted raw color hex near {m.group(0)}")
        else:
            assert entry["refusal_reason"], f"{entry['slug']} missing refusal_reason"
            assert entry["kit_card"].get("fallback_today") is True

    assert layouts_seen == {"stack", "grid", "axis"}
    assert {"dated_tiles", "countdown", "one_in_n", "shared_scale", "bubble_line", "scoreboard_grid", "road_ahead", "single_sport_slate", "casting_sheet"}.issubset(variants_seen)


def test_real_sets_fable_followups_and_shape_priority() -> None:
    snap = _load_fixture()
    report = build_real_sets_audit_report(snap, now=FIXED_NOW, resolver=_default_art_resolver())
    by_slug = {
        e["slug"]: e
        for e in report["top_10"] + report["fitting_beyond_top_10"]
    }
    refused_by_slug = {k["slug"]: k for k in report["kept_today"]}

    # 1. Picture rule: shaped looks fit non-person/team/film sets without monograms or placeholders
    assert by_slug["machinery-elon-musk-side-quests"]["variant"] == "one_in_n"
    assert by_slug["by-november-30"]["variant"] == "countdown"
    assert by_slug["by-december-31"]["variant"] == "countdown"
    assert by_slug["middle-east"]["variant"] == "dated_tiles"
    assert by_slug["russia-ukraine"]["variant"] == "dated_tiles"
    assert by_slug["roundup-tomorrows-highs"]["variant"] == "shared_scale"
    assert by_slug["machinery-2026-box-office-showdown"]["variant"] == "shared_scale"

    # 2. Oscars + 2028 Presidential + Google Search grids include column headers
    for grid_slug in (
        "machinery-oscars-best-picture",
        "machinery-oscars-best-actor-2027",
        "machinery-2028-presidential",
        "machinery-google-year-in-search-2026",
    ):
        assert by_slug[grid_slug]["layout"] == "grid", grid_slug
        assert by_slug[grid_slug]["variant"] == "scoreboard_grid", grid_slug
        body = by_slug[grid_slug]["kit_card"]["body"]
        assert body["show_column_headers"] is True
        assert body.get("leading_label")
        assert len(body["columns"]) == 2
        assert all(str(c.get("label") or "").strip() for c in body["columns"])

    cfp = by_slug["machinery-cfp-national-championship"]
    assert cfp["variant"] == "casting_sheet"
    cfp_bars = [
        m for it in cfp["kit_card"]["body"]["items"] for m in it["marks"] if m.get("mark") == "bar"
    ]
    assert cfp_bars and all(b.get("fill_color") for b in cfp_bars)

    # 3. NHL bubble axis carries all 32 teams + crests on bubble teams
    nhl = by_slug["nhl-playoffs-2026-27"]
    assert nhl["layout"] == "axis"
    assert nhl["variant"] == "bubble_line"
    nhl_dots = nhl["kit_card"]["body"]["marks"]
    assert len(nhl_dots) == 32
    elevated_crests = [d for d in nhl_dots if d.get("picture") and isinstance(d.get("y_lane"), int)]
    assert len(elevated_crests) >= 10
    assert "Edmonton Oilers lead at 98%" in nhl["stat_caption"]

    # 4. Casting sheets: uniform bar color for non-teams or mixed rows; team color kept for all-team sets
    odd = by_slug["machinery-pop-culture-oddities"]
    assert odd["variant"] == "casting_sheet"
    assert odd["common_headline"] == "Pop Culture Oddities"
    assert "long shots" not in odd["common_headline"].lower()
    odd_bars = [
        m
        for it in odd["kit_card"]["body"]["items"]
        for m in it["marks"]
        if m.get("mark") == "bar"
    ]
    assert odd_bars and all("fill_color" not in b for b in odd_bars)

    mixed_bundle = {
        "headline": "Jeremiah Smith for Heisman Trophy is at 84%, with Victor Wembanyama at 52%",
        "data": {
            "kind": "roundup",
            "title": "2026–27 Championship Races",
            "collection_ref": {"id": 9999, "slug": "test-mixed-championships", "name": "2026–27 Championship Races"},
            "roundup": {
                "kicker": "Awards & Cups",
                "machinery_card": {
                    "form_id": "benchmark_strip",
                    "rows": [
                        {
                            "name": "Heisman Trophy: Jeremiah Smith",
                            "probability": 0.84,
                            "rendered_percent": 84,
                            "art": {"url": "https://a.espncdn.com/i/headshots/college-football/players/full/5079720.png", "kind": "person", "accent_color": "#008348"},
                        },
                        {
                            "name": "NBA MVP: Victor Wembanyama",
                            "probability": 0.52,
                            "rendered_percent": 52,
                            "art": {"url": "https://a.espncdn.com/i/headshots/nba/players/full/5104157.png", "kind": "person", "accent_color": "#008348"},
                        },
                        {
                            "name": "UEFA Champions League: Barcelona",
                            "probability": 0.22,
                            "rendered_percent": 22,
                            "art": {"url": "https://a.espncdn.com/i/teamlogos/soccer/500/83.png", "kind": "team_logo", "accent_color": "#990000"},
                        },
                    ],
                },
            },
        },
    }
    mixed = build_kit_card_for_real_set(mixed_bundle, None, now=FIXED_NOW, resolver=_default_art_resolver())
    assert mixed["fits"] is True
    assert mixed["variant"] == "casting_sheet"
    mixed_bars = [
        m for it in mixed["kit_card"]["body"]["items"] for m in it["marks"] if m.get("mark") == "bar"
    ]
    assert mixed_bars and all("fill_color" not in b for b in mixed_bars)

    nfl_front = by_slug["roundup-nfl-division-front-runners"]
    assert "bain luck blend" not in nfl_front["stat_caption"].lower()
    assert "NFC East: Giants lead at 67%" in nfl_front["stat_caption"]
    assert " each" not in json.dumps(nfl_front["kit_card"]).lower()
    assert " each" not in json.dumps(by_slug["machinery-elon-musk-side-quests"]["kit_card"]).lower()

    # 5. Road captions & declarative headlines
    celtics = by_slug["celtics-next-3-games"]
    assert celtics["variant"] == "road_ahead"
    assert "Boston is " in celtics["stat_caption"]
    assert "Washington Wizards (" not in celtics["stat_caption"]
    assert by_slug["machinery-who-gets-engaged"]["common_headline"] == "Getting engaged"
    assert _restate_source_question("Who gets the stage and the cover") == "Stage and cover"
    assert by_slug["machinery-nba-night"]["common_headline"].startswith("NBA, ")
    assert by_slug["machinery-nfl-week"]["common_headline"].startswith("NFL, ")

    for entry in by_slug.values():
        card_blob = json.dumps(entry["kit_card"]).lower()
        assert "served ladder" not in card_blob
        assert " x " not in card_blob
        assert "ptb" not in card_blob

    # 6. Genuine refusals remain blocked honestly; 387: A strips wrong Casting portrait & draws initials + valid posters
    cast = by_slug["machinery-cast-delayed-cancelled"]
    assert cast["fits"] is True and cast["variant"] == "casting_sheet"
    cast_blob = json.dumps(cast["kit_card"])
    assert "wz3MRiMmoz6b5X3oSzMRC9nLxY1" not in cast_blob
    cast_pics = [
        m
        for it in cast["kit_card"]["body"]["items"]
        for m in it["marks"]
        if m.get("mark") == "picture"
    ]
    assert cast_pics[0]["url"] is None and cast_pics[0]["initials"] == "HJ"
    assert cast_pics[1]["url"] and cast_pics[2]["url"]
    assert "crests" in refused_by_slug["liga-profesional-relegation-2026"]["refusal_reason"].lower()
    assert "settled" in refused_by_slug["nfl-2026-week-11"]["refusal_reason"].lower()


def test_real_sets_only_uses_eight_generic_marks() -> None:
    report = load_real_sets_audit_report(now=FIXED_NOW, resolver=_default_art_resolver())
    for entry in report["top_10"] + report["fitting_beyond_top_10"]:
        if not entry["fits"]:
            continue
        parsed = json.loads(json.dumps(entry["kit_card"]))

        def _walk(node):
            if isinstance(node, list):
                for item in node:
                    _walk(item)
            elif isinstance(node, dict):
                if "mark" in node:
                    assert node["mark"] in ALLOWED_MARKS
                    assert "kind" not in node
                    assert "type" not in node
                for val in node.values():
                    _walk(val)

        _walk(parsed["body"])


def test_preview_endpoint_route_exists_before_catchall() -> None:
    from app.routes.containers import router

    paths = [r.path for r in router.routes]
    assert "/preview/kit-v1-real-sets" in paths
    assert paths.index("/preview/kit-v1-real-sets") < paths.index("/{slug}")


@pytest.mark.asyncio
async def test_live_builder_reads_feed_and_containers() -> None:
    import app.routes.containers as containers_route

    snap = _load_fixture()
    sample_bundles = snap["bundles"][:3]
    sample_containers = snap["containers"]

    async def fake_get_feed(**kwargs):
        return {"items": sample_bundles}

    async def fake_discover_collections(db, **kwargs):
        class Read:
            collections = [{"slug": s} for s in list(sample_containers)[:2]]
        return Read()

    async def fake_get_container(slug, *args, **kwargs):
        return sample_containers.get(slug) or {}

    live_report = await containers_route._build_live_real_sets_audit_report(
        None,
        now=FIXED_NOW,
        feed_getter=fake_get_feed,
        container_getter=fake_get_container,
        discovery_reader=fake_discover_collections,
        roundup_producers={s: None for s in list(sample_containers)[:3]},
    )
    assert live_report["kit_version"] == 1
    assert live_report["total_sets"] >= 3
    assert live_report["fitting_count"] + live_report["kept_today_count"] == live_report["total_sets"]


def test_real_sets_scrubs_venue_names_and_opens_at_copy() -> None:
    snap = _load_fixture()
    c19 = snap["containers"]["celtics-next-3-games"]
    b19 = next(
        b for b in snap["bundles"]
        if (b["data"].get("collection_ref") or {}).get("slug") == "celtics-next-3-games"
    )
    noisy = json.loads(json.dumps(b19))
    noisy["headline"] = "Boston opens at 79% in Washington on Kalshi"
    res = build_kit_card_for_real_set(noisy, c19, now=FIXED_NOW, resolver=_default_art_resolver())
    assert res["fits"] is True
    assert "opens at" not in res["stat_caption"].lower()
    assert "kalshi" not in res["stat_caption"].lower()


def test_v4_2028_presidential_keeps_jd_vance_fails_closed_and_ignores_section_order() -> None:
    snap = _load_fixture()
    c_pres = json.loads(json.dumps(snap["containers"]["machinery-2028-presidential"]))
    b_pres = next(
        b for b in snap["bundles"]
        if (b["data"].get("collection_ref") or {}).get("slug") == "machinery-2028-presidential"
    )
    res = build_kit_card_for_real_set(b_pres, c_pres, now=FIXED_NOW, resolver=_default_art_resolver())
    assert res["fits"] is True
    body = res["kit_card"]["body"]
    assert [c["label"] for c in body["columns"]] == ["Presidential", "Wins party nomination"]
    row_names = [
        next(m["text"] for m in rw["leading"] if m.get("style") == "row")
        for rw in body["rows"]
    ]
    assert row_names[:4] == ["Jon Ossoff", "JD Vance", "Alexandria Ocasio-Cortez", "Marco Rubio"]
    ranks = [
        next(m["text"] for m in rw["leading"] if m.get("style") == "rank")
        for rw in body["rows"]
    ]
    assert ranks == ["1", "2", "3", "4"]
    vance_cells = [c["marks"][0]["center_label"] for c in body["rows"][1]["cells"]]
    assert vance_cells == ["13%", "33%"]

    # Reordering sections must produce the exact same rows and columns
    shuffled = json.loads(json.dumps(c_pres))
    shuffled["sections"] = list(reversed(shuffled["sections"]))
    res_shuffled = build_kit_card_for_real_set(b_pres, shuffled, now=FIXED_NOW, resolver=_default_art_resolver())
    assert res_shuffled["kit_card"]["body"]["rows"] == body["rows"]
    assert res_shuffled["kit_card"]["body"]["columns"] == body["columns"]

    # Fail closed if a Column 1 top-4 contender lacks a Column 2 number (never skip/renumber)
    broken = json.loads(json.dumps(c_pres))
    for sec in broken["sections"]:
        for mem in sec.get("members") or []:
            c = mem.get("card") or {}
            if "nominee" in str(c.get("name") or "").lower():
                c["top_outcomes"] = [
                    o for o in (c.get("top_outcomes") or []) if "vance" not in str(o.get("name") or "").lower()
                ]
    res_broken = build_kit_card_for_real_set(b_pres, broken, now=FIXED_NOW, resolver=_default_art_resolver())
    assert res_broken["fits"] is False
    assert "JD Vance" in (res_broken["refusal_reason"] or "")


def test_v4_year_in_search_lists_headers_and_no_rank_marks() -> None:
    snap = _load_fixture()
    c_yis = json.loads(json.dumps(snap["containers"]["machinery-google-year-in-search-2026"]))
    b_yis = next(
        b for b in snap["bundles"]
        if (b["data"].get("collection_ref") or {}).get("slug") == "machinery-google-year-in-search-2026"
    )
    res = build_kit_card_for_real_set(b_yis, c_yis, now=FIXED_NOW, resolver=_default_art_resolver())
    assert res["fits"] is True
    body = res["kit_card"]["body"]
    assert [c["label"] for c in body["columns"]] == ["#1 in its list", "Top 5 in its list"]
    assert all(m.get("style") != "rank" for rw in body["rows"] for m in rw["leading"])
    sec_labels = [
        next(m.get("secondary_text") for m in rw["leading"] if m.get("style") == "row")
        for rw in body["rows"]
    ]
    assert sec_labels == ["Actor", "Athlete", "Movie", "TV show"]


def test_v4_dated_tiles_drops_expired_keeps_quoted_peak_and_uses_resolution_year() -> None:
    # Yearless deadline inherits market's resolution_date year instead of hardcoded 2026 (#13584 v4/v6).
    assert _parse_outcome_deadline("Before Mar 1", reference_year=2027) == ((2027, 3, 1), "before Mar 1 '27")

    snap = _load_fixture()
    now_nov24 = datetime(2026, 11, 24, 17, 20, tzinfo=timezone.utc)
    report = build_real_sets_audit_report(snap, now=now_nov24, resolver=_default_art_resolver())
    ai_entry = next(
        e for e in (report["top_10"] + report["fitting_beyond_top_10"]) if e["slug"] == "ai"
    )
    ai_card = ai_entry["kit_card"]
    ai_blob = json.dumps(ai_card)
    assert "Dec 31 '25" not in ai_blob
    assert "Mar 31 '26" not in ai_blob
    assert "Oct 31 '26" not in ai_blob
    assert "solution is " not in ai_card["stat_caption"]
    assert "43% before Jun 1 '27" in ai_card["stat_caption"]
    shown_labels = {
        m.get("center_label") + " " + (m.get("top_label") or "")
        for rw in ai_card["body"]["rows"]
        for cell in rw["cells"]
        for m in cell["marks"]
    }
    assert "43% before Jun 1 '27" in shown_labels
    assert "62% by Dec 31 '27" in shown_labels
    assert "ai" in report["dated_tiles_left_off"]


def test_v4_box_office_posters_countdown_client_iso_and_zero_slug_branches() -> None:
    snap = _load_fixture()
    c_bo = snap["containers"]["machinery-2026-box-office-showdown"]
    res_bo = build_kit_card_for_real_set(None, c_bo, now=FIXED_NOW, resolver=_default_art_resolver())
    assert res_bo["fits"] is True
    assert res_bo["variant"] == "shared_scale"
    series = res_bo["kit_card"]["body"]["series"]
    pics = [m for s in series for m in s["leading"] if m.get("mark") == "picture"]
    assert len(pics) == 2
    assert all(p.get("subject_kind") == "film" and p.get("url", "").startswith("https://") for p in pics)

    b_nov30 = next(
        b for b in snap["bundles"]
        if (b["data"].get("collection_ref") or {}).get("slug") == "by-november-30"
    )
    for dt_utc, exp_val, exp_disp, exp_label in [
        (datetime(2026, 11, 24, 17, 20, tzinfo=timezone.utc), 6, "6", "days left"),
        (datetime(2026, 11, 29, 17, 20, tzinfo=timezone.utc), 1, "1", "day left"),
        (datetime(2026, 11, 30, 17, 20, tzinfo=timezone.utc), 0, "Today", "ends today"),
    ]:
        res_cd = build_kit_card_for_real_set(b_nov30, None, now=dt_utc, resolver=_default_art_resolver())
        assert res_cd["fits"] is True
        hdr = res_cd["kit_card"]["body"]["header_marks"]
        assert hdr[0]["value"] == exp_val
        assert hdr[0]["display"] == exp_disp
        assert hdr[0].get("deadline_iso")
        assert hdr[1]["text"] == exp_label
        assert hdr[1].get("deadline_iso") == hdr[0]["deadline_iso"]

    builder_src = open(
        REAL_SETS_FIXTURE_PATH.parents[2] / "app" / "utils" / "kit_v1_set_builder.py",
        encoding="utf-8",
    ).read()
    assert "_DECLARATIVE_HEADLINES" not in builder_src
    assert '== "machinery-2028-presidential"' not in builder_src
    assert '== "machinery-google-year-in-search-2026"' not in builder_src
    assert '== "machinery-elon-musk-side-quests"' not in builder_src
    assert '== "roundup-nfl-division-front-runners"' not in builder_src
    assert "secs[1]" not in builder_src and "secs[3]" not in builder_src
    assert "mixed non-comparable questions" not in builder_src
    assert "distinct question shapes" not in builder_src


def test_v5_yearless_deadline_market_end_date_and_market_3484764() -> None:
    from datetime import date

    # Yearless deadline is the last such calendar date on or before the market's end (#13584 v5).
    end_dt = date(2027, 7, 1)
    assert _parse_outcome_deadline("June 30, 2027", market_end_date=end_dt) == ((2027, 6, 30), "Jun 30 '27")
    assert _parse_outcome_deadline("December 31", market_end_date=end_dt) == ((2026, 12, 31), "Dec 31 '26")
    assert _parse_outcome_deadline("November 30", market_end_date=end_dt) == ((2026, 11, 30), "Nov 30 '26")
    assert _parse_outcome_deadline("Before 2035") == ((2034, 12, 31), "before 2035")

    # End-to-end dated_tiles build for market 3484764's exact three labels + companion lane
    bundle = {
        "type": "bundle",
        "data": {
            "id": "middle-east",
            "title": "Middle East",
            "kind": "theme",
            "collection_ref": {"id": 99, "slug": "middle-east"},
            "roundup": {"kicker": "WORLD", "headline": "Middle East"},
            "items": [
                {
                    "type": "futures",
                    "data": {
                        "id": 3484764,
                        "name": "Iran leadership change by June 30, 2027?",
                        "resolution_date": "2027-07-01T03:59:00+00:00",
                        "top_outcomes": [
                            {"name": "June 30, 2027", "probability": 0.235, "rendered_percent": 24},
                            {"name": "December 31", "probability": 0.065, "rendered_percent": 7},
                            {"name": "November 30", "probability": 0.0085, "rendered_percent": 1},
                        ],
                    },
                },
                {
                    "type": "futures",
                    "data": {
                        "id": 69603905,
                        "name": "US–Iran Effective Ceasefire begins by November 30?",
                        "resolution_date": "2026-12-31T20:29:00+00:00",
                        "top_outcomes": [
                            {"name": "December 31", "probability": 0.815},
                            {"name": "November 30", "probability": 0.64},
                        ],
                    },
                },
            ],
        },
    }
    res = build_kit_card_for_real_set(
        bundle,
        None,
        now=datetime(2026, 11, 24, 9, 55, tzinfo=timezone.utc),
        resolver=_default_art_resolver(),
    )
    assert res["fits"] is True
    assert res["variant"] == "dated_tiles"
    iran_row = res["kit_card"]["body"]["rows"][0]
    tiles = [(c["marks"][0]["top_label"], c["marks"][0]["center_label"]) for c in iran_row["cells"]]
    assert tiles == [("by Nov 30 '26", "1%"), ("by Dec 31 '26", "7%"), ("by Jun 30 '27", "24%")]


def test_v5_dated_tiles_refuses_non_monotonic_lane_and_audits_reason() -> None:
    snap = {
        "bundles": [
            {
                "type": "bundle",
                "data": {
                    "id": "bad-dates",
                    "title": "Bad Dates",
                    "kind": "theme",
                    "collection_ref": {"id": 100, "slug": "bad-dates"},
                    "roundup": {"kicker": "WORLD", "headline": "Bad Dates"},
                    "items": [
                        {
                            "type": "futures",
                            "data": {
                                "id": 1,
                                "name": "Bad lane with inverted year",
                                "resolution_date": "2027-07-01T03:59:00+00:00",
                                "top_outcomes": [
                                    {"name": "June 30, 2027", "probability": 0.24},
                                    {"name": "November 30, 2027", "probability": 0.01},
                                    {"name": "December 31, 2027", "probability": 0.07},
                                ],
                            },
                        },
                        {
                            "type": "futures",
                            "data": {
                                "id": 2,
                                "name": "One point tolerance lane",
                                "resolution_date": "2027-12-31T20:00:00+00:00",
                                "top_outcomes": [
                                    {"name": "April 1, 2027", "probability": 0.62},
                                    {"name": "July 1, 2027", "probability": 0.61},
                                ],
                            },
                        },
                    ],
                },
            }
        ],
        "containers": {},
    }
    report = build_real_sets_audit_report(
        snap,
        now=datetime(2026, 11, 24, 9, 55, tzinfo=timezone.utc),
        resolver=_default_art_resolver(),
    )
    assert report["fitting_count"] == 0
    assert report["kept_today_count"] == 1
    assert "Non-monotonic lane" in (report["kept_today"][0]["refusal_reason"] or "")
    lanes = report["dated_tiles_left_off"]["bad-dates"]
    bad_lane = next(ln for ln in lanes if ln["lane"] == "Bad lane with inverted year")
    assert bad_lane["dropped"] is True
    assert "Non-monotonic lane" in (bad_lane.get("refusal_reason") or "")
    assert all("non_monotonic_drop" in o["reason"] for o in bad_lane["left_off"])


def test_v5_routes_year_only_dated_tiles_and_shared_date_countdown() -> None:
    # Year-only Before YYYY -> dated_tiles without "by before YYYY"
    year_only_bundle = {
        "type": "bundle",
        "data": {
            "id": "roundup:science-years",
            "title": "Unsolved Big Problems",
            "kind": "roundup",
            "collection_ref": {"id": 101, "slug": "machinery-unsolved-big-problems"},
            "roundup": {
                "kicker": "TECH · SCIENCE",
                "headline": "Science milestones stretch across the 2030s",
                "machinery_card": {"form_id": "benchmark_strip", "rows": []},
            },
            "items": [
                {
                    "type": "futures",
                    "data": {
                        "id": 9001,
                        "name": "When will the Riemann hypothesis win the Millennium Prize?",
                        "resolution_date": "2035-01-01T15:00:00+00:00",
                        "top_outcomes": [
                            {"name": "Before 2035", "probability": 0.90},
                            {"name": "Before 2030", "probability": 0.60},
                            {"name": "Before 2028", "probability": 0.02},
                        ],
                    },
                },
                {
                    "type": "futures",
                    "data": {
                        "id": 9002,
                        "name": "When will nuclear fusion be achieved?",
                        "resolution_date": "2040-01-01T04:59:00+00:00",
                        "top_outcomes": [
                            {"name": "Before 2040", "probability": 0.84},
                            {"name": "Before 2035", "probability": 0.64},
                            {"name": "Before 2030", "probability": 0.39},
                        ],
                    },
                },
            ],
        },
    }
    res_yr = build_kit_card_for_real_set(
        year_only_bundle,
        None,
        now=datetime(2026, 11, 24, 9, 55, tzinfo=timezone.utc),
        resolver=_default_art_resolver(),
    )
    assert res_yr["fits"] is True
    assert res_yr["variant"] == "dated_tiles"
    assert "by before" not in json.dumps(res_yr["kit_card"]).lower()

    # Shared PT resolution date across >= 3 markets -> countdown with deadline_iso
    xmas_bundle = {
        "type": "bundle",
        "data": {
            "id": "roundup:white-christmas",
            "title": "White Christmas",
            "kind": "roundup",
            "collection_ref": {"id": 102, "slug": "machinery-white-christmas"},
            "roundup": {
                "kicker": "WEATHER · CHRISTMAS",
                "headline": "Snow on Christmas leads at 50% in Pittsburgh",
                "machinery_card": {"form_id": "benchmark_strip", "rows": []},
            },
            "items": [
                {
                    "type": "futures",
                    "data": {
                        "id": 9101,
                        "name": "Will it snow in Pittsburgh on Christmas?",
                        "resolution_date": "2026-12-26T04:59:00+00:00",
                        "top_outcomes": [{"name": "Above 0 inches", "probability": 0.50}],
                    },
                },
                {
                    "type": "futures",
                    "data": {
                        "id": 9102,
                        "name": "Will it snow in Chicago on Christmas?",
                        "resolution_date": "2026-12-26T05:59:00+00:00",
                        "top_outcomes": [{"name": "Above 0 inches", "probability": 0.38}],
                    },
                },
                {
                    "type": "futures",
                    "data": {
                        "id": 9103,
                        "name": "Will it snow in Seattle on Christmas?",
                        "resolution_date": "2026-12-26T07:59:00+00:00",
                        "top_outcomes": [{"name": "Above 0 inches", "probability": 0.10}],
                    },
                },
            ],
        },
    }
    res_cd = build_kit_card_for_real_set(
        xmas_bundle,
        None,
        now=datetime(2026, 11, 24, 9, 55, tzinfo=timezone.utc),
        resolver=_default_art_resolver(),
    )
    assert res_cd["fits"] is True
    assert res_cd["variant"] == "countdown"
    hdr = res_cd["kit_card"]["body"]["header_marks"]
    assert hdr[0]["value"] == 31
    assert hdr[0]["deadline_iso"] == "2026-12-26T04:59:00+00:00"
    assert hdr[1]["secondary_text"] == "all of these end on Dec 25"


def test_v6_before_labels_threshold_ladder_no_dash_captions_slates_and_alex_example() -> None:
    from app.utils.kit_v1_set_builder import _parse_iso_dt

    # 1. "Before X" stays "before X" on exact market 109349 labels + AGI "Before Jan 1, 2031"
    assert _parse_outcome_deadline("Before 2027") == ((2026, 12, 31), "before 2027")
    assert _parse_outcome_deadline("Before February 2027") == ((2027, 1, 31), "before Feb '27")
    assert _parse_outcome_deadline("Before March 2027") == ((2027, 2, 28), "before Mar '27")
    assert _parse_outcome_deadline("Before April 2027") == ((2027, 3, 31), "before Apr '27")
    assert _parse_outcome_deadline("Before Jan 1, 2031") == ((2031, 1, 1), "before Jan 1 '31")

    snap = _load_fixture()

    # 2. threshold_points + top_outcomes ladder merge (Russia-Ukraine 14 points -> nearest, middle, last)
    # and fallback on year 2000 (Middle East 69603905), with no dash tile or footnote on Middle East.
    ru_bundle = {
        "type": "bundle",
        "data": {
            "id": "russia-ukraine",
            "title": "Russia–Ukraine",
            "kind": "theme",
            "collection_ref": {"id": 80, "slug": "russia-ukraine"},
            "roundup": {"kicker": "WORLD", "headline": "Russia–Ukraine"},
            "items": [
                {
                    "type": "futures",
                    "data": {
                        "id": 20569379,
                        "name": "Russia x Ukraine ceasefire agreement by May 31, 2027?",
                        "resolution_date": "2027-07-01T03:59:00+00:00",
                        "top_outcomes": [
                            {"name": "December 31, 2027", "probability": 0.685, "rendered_percent": 69},
                            {"name": "November 30, 2027", "probability": 0.675, "rendered_percent": 68},
                            {"name": "October 31, 2027", "probability": 0.67, "rendered_percent": 67},
                        ],
                        "discover_card": {
                            "threshold_points": [
                                {"label": "November 30", "value": 20261130, "unit": "date", "probability": 0.0155},
                                {"label": "January 31, 2027", "value": 20270131, "unit": "date", "probability": 0.185},
                                {"label": "May 31, 2027", "value": 20270531, "unit": "date", "probability": 0.53},
                                {"label": "June 30, 2027", "value": 20270630, "unit": "date", "probability": 0.56},
                                {"label": "October 31, 2027", "value": 20271031, "unit": "date", "probability": 0.67},
                            ]
                        },
                    },
                },
                {
                    "type": "futures",
                    "data": {
                        "id": 112896,
                        "name": "Putin out as President of Russia by June 30, 2027?",
                        "resolution_date": "2027-07-01T03:59:00+00:00",
                        "top_outcomes": [
                            {"name": "June 30, 2027", "probability": 0.085, "rendered_percent": 9},
                            {"name": "March 31, 2027", "probability": 0.055, "rendered_percent": 6},
                            {"name": "December 31, 2026", "probability": 0.0125, "rendered_percent": 1},
                        ],
                    },
                },
            ],
        },
    }
    res_ru = build_kit_card_for_real_set(
        ru_bundle,
        None,
        now=datetime(2026, 11, 24, 9, 55, tzinfo=timezone.utc),
        resolver=_default_art_resolver(),
    )
    assert res_ru["fits"] is True
    ru_row0 = [(c["marks"][0]["top_label"], c["marks"][0]["center_label"]) for c in res_ru["kit_card"]["body"]["rows"][0]["cells"]]
    assert ru_row0 == [("by Nov 30 '26", "2%"), ("by Jun 30 '27", "56%"), ("by Dec 31 '27", "69%")]

    # Year-2000 threshold_points value falls back to market_end_date rule
    me_res = build_kit_card_for_real_set(
        {
            "type": "bundle",
            "data": {
                "id": "middle-east",
                "title": "Middle East",
                "kind": "theme",
                "collection_ref": {"id": 81, "slug": "middle-east"},
                "roundup": {"kicker": "WORLD", "headline": "Middle East"},
                "items": [
                    {
                        "type": "futures",
                        "data": {
                            "id": 69603905,
                            "name": "US x Iran Effective Ceasefire begins?",
                            "resolution_date": "2026-12-31T20:29:00+00:00",
                            "top_outcomes": [
                                {"name": "December 31", "probability": 0.815, "rendered_percent": 82},
                                {"name": "November 30", "probability": 0.64, "rendered_percent": 64},
                            ],
                            "discover_card": {
                                "threshold_points": [
                                    {"label": "November 30", "value": 20001130, "unit": "date", "probability": 0.64},
                                    {"label": "December 31", "value": 20001231, "unit": "date", "probability": 0.815},
                                ]
                            },
                        },
                    },
                    {
                        "type": "futures",
                        "data": {
                            "id": 3484764,
                            "name": "Iran leadership change by June 30, 2027?",
                            "resolution_date": "2027-07-01T03:59:00+00:00",
                            "top_outcomes": [
                                {"name": "June 30, 2027", "probability": 0.235, "rendered_percent": 24},
                                {"name": "December 31", "probability": 0.065, "rendered_percent": 7},
                                {"name": "November 30", "probability": 0.0085, "rendered_percent": 1},
                            ],
                        },
                    },
                ],
            },
        },
        None,
        now=datetime(2026, 11, 24, 9, 55, tzinfo=timezone.utc),
        resolver=_default_art_resolver(),
    )
    assert me_res["fits"] is True
    assert me_res["kit_card"].get("footnote") is None
    me_rows = me_res["kit_card"]["body"]["rows"]
    assert len(me_rows[0]["cells"]) == 2 and len(me_rows[1]["cells"]) == 3
    assert "—" not in json.dumps(me_res["kit_card"])

    # 3. Audit invariants across fixture: 0 unshown % in captions, slate headers + time sort, captured_at, 1 uncounted example
    snap_plus = json.loads(json.dumps(snap))
    report = build_real_sets_audit_report(
        snap_plus,
        now=datetime(2026, 11, 24, 9, 55, tzinfo=timezone.utc),
        resolver=_default_art_resolver(),
        snapshot_captured_at="2026-11-23T22:35:00-08:00",
    )
    assert report["snapshot_captured_at"] == "2026-11-23T22:35:00-08:00"
    for e in [x for x in report["top_10"] if x["fits"]] + report["fitting_beyond_top_10"]:
        card = e["kit_card"]
        body_blob = json.dumps(card["body"])
        for m in re.finditer(r"\b(\d+)%", card["stat_caption"] or ""):
            assert f"{m.group(1)}%" in body_blob, f"{e['slug']} caption quoted unshown {m.group(0)}"
        if card["variant"] == "single_sport_slate":
            hdr_text = card["body"]["header_marks"][1]["text"]
            n_shown = len(card["body"]["items"])
            if n_shown == 3 and "16" in hdr_text:
                assert hdr_text == "3 OF 16 GAMES"
            times = [it["sub_marks"][0]["text"] for it in card["body"]["items"]]
            assert len(times) == n_shown and _parse_iso_dt("2026-11-24T00:00:00Z") is not None


def test_v7_387a_388a_389c_live_caption_and_split_bar_parity() -> None:
    # 1. 387: A — partial verified pictures show held pictures + initials circle; 0-pictured casting refuses for person/team/film
    partial_bundle = {
        "data": {
            "kind": "roundup",
            "collection_ref": {"id": 9001, "slug": "test-partial-cast", "name": "Test Partial Art"},
            "roundup": {
                "kicker": "FILM",
                "machinery_card": {
                    "form_id": "benchmark_strip",
                    "rows": [
                        {
                            "name": "Hugh Jackman as Wolverine",
                            "probability": 0.94,
                            "rendered_percent": 94,
                            "art": {
                                "url": "https://image.tmdb.org/t/p/w185/wrong.jpg",
                                "kind": "person",
                                "detail": "Benedict Cumberbatch TMDB portrait",
                            },
                        },
                        {
                            "name": "Dune: Part Three",
                            "probability": 0.81,
                            "rendered_percent": 81,
                            "art": {
                                "url": "https://image.tmdb.org/t/p/w342/glt0v4I89rMWstDNCaFXc5SNyO1.jpg",
                                "kind": "tmdb_poster",
                            },
                        },
                        {
                            "name": "Mystery Sequel",
                            "probability": 0.67,
                            "rendered_percent": 67,
                            "art": {"url": None, "kind": "monogram"},
                        },
                    ],
                },
            },
        }
    }
    res_partial = build_kit_card_for_real_set(partial_bundle, None, now=FIXED_NOW)
    assert res_partial["fits"] is True and res_partial["variant"] == "casting_sheet"
    pics = [m for it in res_partial["kit_card"]["body"]["items"] for m in it["marks"] if m["mark"] == "picture"]
    assert pics[0]["url"] is None and pics[0]["initials"] == "HJ"
    assert pics[1]["url"] == "https://image.tmdb.org/t/p/w342/glt0v4I89rMWstDNCaFXc5SNyO1.jpg"
    assert pics[2]["url"] is None and pics[2]["initials"] == "MS"
    assert "wrong.jpg" not in json.dumps(res_partial["kit_card"])

    # 2. 388: A — non-(person/team/film) plain_bar_stack only as last resort; dated_tiles wins when dated
    climate_bundle = {
        "data": {
            "kind": "roundup",
            "collection_ref": {"id": 9002, "slug": "test-climate-plain", "name": "Climate Metrics"},
            "roundup": {
                "kicker": "CLIMATE",
                "machinery_card": {
                    "form_id": "benchmark_strip",
                    "rows": [
                        {"name": "Melbourne wettest month: October", "probability": 0.91, "rendered_percent": 91},
                        {"name": "Napa seasonal rainfall: Above 10 inches", "probability": 0.87, "rendered_percent": 87},
                        {"name": "Top primary energy in 2030: Oil", "probability": 0.66, "rendered_percent": 66},
                    ],
                },
            },
        }
    }
    res_plain = build_kit_card_for_real_set(climate_bundle, None, now=FIXED_NOW)
    assert res_plain["fits"] is True and res_plain["variant"] == "plain_bar_stack"

    # Weather city "Pittsburgh" must not attach an NFL Steelers helmet
    white_xmas_snap = _load_fixture()
    rep = build_real_sets_audit_report(white_xmas_snap, now=FIXED_NOW, resolver=_default_art_resolver())
    assert rep["alex_question_examples"] == []

    # 3. 389: C — NHL bubble card has % under crest, zero footer_marks, two one-line end summaries
    by_slug = {e["slug"]: e for e in rep["top_10"] + rep["fitting_beyond_top_10"]}
    nhl = by_slug["nhl-playoffs-2026-27"]["kit_card"]
    assert nhl["body"].get("footer_marks") is None
    bubble_dots = [d for d in nhl["body"]["marks"] if d.get("in_band")]
    assert bubble_dots and all(d.get("badge_text", "").endswith("%") for d in bubble_dots)
    summaries = nhl["body"]["summary_marks"]
    assert len(summaries) == 2
    assert "25% or less (" in summaries[0]["text"]
    assert "75% or more (" in summaries[1]["text"]

    # 4. Live-game caption guard (slate & road_ahead) + same-hue blue split bar separation
    live_slate_bundle = {
        "headline": "Pistons (61%) at Magic (39%) live now",
        "data": {
            "kind": "roundup",
            "collection_ref": {"id": 9003, "slug": "test-live-nba", "name": "NBA Night"},
            "roundup": {
                "kicker": "NBA",
                "machinery_card": {
                    "form_id": "matchup_slate",
                    "rows": [
                        {
                            "event_id": 1,
                            "sport": "basketball_nba",
                            "status": "live",
                            "away_team": "Detroit Pistons",
                            "home_team": "Orlando Magic",
                            "away_short": "DET",
                            "home_short": "ORL",
                            "home_pct": 39,
                            "away_pct": 61,
                            "commence_time": "2026-11-24T20:00:00Z",
                        },
                        {
                            "event_id": 2,
                            "sport": "basketball_nba",
                            "status": "scheduled",
                            "away_team": "Boston Celtics",
                            "home_team": "Miami Heat",
                            "away_short": "BOS",
                            "home_short": "MIA",
                            "home_pct": 38,
                            "away_pct": 62,
                            "commence_time": "2026-11-24T22:00:00Z",
                        },
                    ],
                },
            },
        },
    }
    res_live = build_kit_card_for_real_set(live_slate_bundle, None, now=FIXED_NOW, resolver=_default_art_resolver())
    assert res_live["fits"] is True
    assert "61%" not in res_live["stat_caption"] and "39%" not in res_live["stat_caption"]
    split_bar = next(m for m in res_live["kit_card"]["body"]["items"][0]["marks"] if m["mark"] == "bar")
    assert split_bar["segments"][0]["color"] != split_bar["segments"][1]["color"]


def test_three_kept_grid_suited_sets_render_as_scoreboard_grid() -> None:
    """Item 8 / #13631 Fable 5 points: Big Tech (MS/NV initials, scoped icons), AI Leaderboard (Text Arena), Fed (Direction 228 order, no #, 388: A)."""
    resolver = _default_art_resolver()

    def _market(mid: int, title: str, outs: list[tuple[str, int, float]]) -> dict:
        return {
            "type": "market",
            "card": {
                "id": mid,
                "name": title,
                "top_outcomes": [
                    {"name": nm, "rendered_percent": pct, "probability": prob}
                    for nm, pct, prob in outs
                ],
            },
        }

    # 1. AI & Big Tech Race: Largest / 2nd Largest / 3rd Largest Company (symbols + MS/NV initials)
    big_tech = build_kit_card_for_real_set(
        {"type": "bundle", "data": {"id": "roundup:machinery-ai-and-big-tech-race", "title": "The AI & Big Tech Race", "roundup": {"kicker": "TECH · BUSINESS"}}},
        {
            "container": {"id": 3784574905, "slug": "machinery-ai-and-big-tech-race", "title": "The AI & Big Tech Race", "source_count": 1},
            "sections": [
                {
                    "class": "ai_and_big_tech_race",
                    "members": [
                        _market(113318, "Largest Company end of December 2026?", [("Apple", 84, 0.8425), ("NVIDIA", 15, 0.1505), ("Microsoft", 1, 0.0045), ("Alphabet", 1, 0.0035)]),
                        _market(68806125, "2nd Largest Company end of November 2026?", [("NVIDIA", 82, 0.8167), ("Microsoft", 15, 0.1465), ("Alphabet", 2, 0.0189), ("Apple", 1, 0.0133)]),
                        _market(68806126, "3rd Largest Company end of November 2026?", [("Microsoft", 64, 0.6338), ("Alphabet", 19, 0.1848), ("NVIDIA", 13, 0.1268), ("Apple", 1, 0.0131)]),
                    ],
                }
            ],
        },
        now=FIXED_NOW,
        resolver=resolver,
    )
    assert big_tech["fits"] is True, big_tech
    assert big_tech["layout"] == "grid" and big_tech["variant"] == "scoreboard_grid"
    assert [c["label"] for c in big_tech["kit_card"]["body"]["columns"]] == ["1st", "2nd", "3rd"]
    bt_rows = big_tech["kit_card"]["body"]["rows"]
    assert len(bt_rows) == 4
    bt_pics = {next(m["text"] for m in r["leading"] if m.get("style") == "row"): next(m for m in r["leading"] if m["mark"] == "picture") for r in bt_rows}
    assert bt_pics["Apple"]["url"] and bt_pics["Alphabet"]["url"]
    assert bt_pics["NVIDIA"]["url"] is None and bt_pics["NVIDIA"]["initials"] == "NV"
    assert bt_pics["Microsoft"]["url"] is None and bt_pics["Microsoft"]["initials"] == "MS"
    assert validate_kit_v1_card(big_tech["kit_card"])[0]

    # 2. AI Model Leaderboard: Overall / Coding / Text Arena across canonical labs
    ai_lb = build_kit_card_for_real_set(
        {"type": "bundle", "data": {"id": "roundup:machinery-ai-model-leaderboard-2026", "title": "The 2026 AI Model Leaderboard", "roundup": {"kicker": "TECH · AI"}}},
        {
            "container": {"id": 4001, "slug": "machinery-ai-model-leaderboard-2026", "title": "The 2026 AI Model Leaderboard", "source_count": 1},
            "sections": [
                {
                    "class": "ai_model_leaderboard_2026",
                    "members": [
                        _market(109596, "Best AI at the end of 2026?", [("Gemini", 80, 0.7968), ("Claude", 14, 0.1396), ("ChatGPT", 4, 0.0402), ("Grok", 1, 0.0083)]),
                        _market(109623, "Which AI company will have the best coding model at the end of 2026?", [("Anthropic", 57, 0.57), ("Google", 25, 0.25), ("OpenAI", 16, 0.155)]),
                        _market(109322, "Which AI will be the first to hit 1550 on Text Arena?", [("Gemini", 30, 0.295), ("Claude", 8, 0.075), ("ChatGPT", 5, 0.045)]),
                    ],
                }
            ],
        },
        now=FIXED_NOW,
        resolver=resolver,
    )
    assert ai_lb["fits"] is True, ai_lb
    assert [c["label"] for c in ai_lb["kit_card"]["body"]["columns"]] == ["Overall", "Coding", "Text Arena"]
    assert len(ai_lb["kit_card"]["body"]["rows"]) == 3
    assert validate_kit_v1_card(ai_lb["kit_card"])[0]

    # 3. Fed & U.S. Macro: Direction 228 value order, no # rank col, two-meeting wording, allowed by 388: A
    fed = build_kit_card_for_real_set(
        {"type": "bundle", "data": {"id": "roundup:machinery-fed-and-macro", "title": "Fed & U.S. Macro", "roundup": {"kicker": "ECONOMICS · FEDERAL RESERVE"}}},
        {
            "container": {"id": 3913944771, "slug": "machinery-fed-and-macro", "title": "Fed & U.S. Macro", "source_count": 1},
            "sections": [
                {
                    "class": "jan_fomc",
                    "members": [
                        _market(57574217, "Fed Decision in January?", [("Quarter-point increase", 53, 0.525), ("No change", 45, 0.445), ("Quarter-point cut", 2, 0.017), ("Half-point or larger increase", 1, 0.01)]),
                    ],
                },
                {
                    "class": "rate_path",
                    "members": [
                        _market(57574250, "Fed Decision in December?", [("Quarter-point increase", 93, 0.9322), ("No change", 4, 0.0329), ("Half-point or larger increase", 3, 0.0309), ("Quarter-point cut", 0, 0.0025)]),
                    ],
                },
            ],
        },
        now=FIXED_NOW,
        resolver=resolver,
    )
    assert fed["fits"] is True, fed
    assert [c["label"] for c in fed["kit_card"]["body"]["columns"]] == ["Dec FOMC", "Jan FOMC"]
    fed_rows = fed["kit_card"]["body"]["rows"]
    assert [next(m["text"] for m in r["leading"] if m.get("style") == "row") for r in fed_rows] == [
        "Quarter-point cut",
        "No change",
        "Quarter-point increase",
        "Half-point or larger increase",
    ]
    assert all(all(m.get("style") != "rank" for m in r["leading"]) for r in fed_rows)
    assert fed["stat_caption"] == "Quarter-point increase leads December FOMC at 93% (53% in January); no change is 4% for December and 45% for January."
    assert "rising from" not in fed["stat_caption"].lower()
    fed_blob = json.dumps(fed["kit_card"])
    assert "<1%" in fed_blob
    assert '"center_label": "0%"' not in fed_blob
    assert validate_kit_v1_card(fed["kit_card"])[0]
