"""Tests for deterministic real-set Kit v1 builder (Item 3, #13551 & #13584 follow-up)."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone

import pytest

from app.utils.container_machinery import _default_art_resolver
from app.utils.kit_v1_set_builder import (
    REAL_SETS_FIXTURE_PATH,
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

    # 2. Oscars + CFP + 2028 Presidential + Google Search grids include column headers
    for grid_slug in (
        "machinery-oscars-best-picture",
        "machinery-oscars-best-actor-2027",
        "machinery-cfp-national-championship",
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

    # 3. NHL bubble axis carries all 32 teams + crests on bubble teams
    nhl = by_slug["nhl-playoffs-2026-27"]
    assert nhl["layout"] == "axis"
    assert nhl["variant"] == "bubble_line"
    nhl_dots = nhl["kit_card"]["body"]["marks"]
    assert len(nhl_dots) == 32
    elevated_crests = [d for d in nhl_dots if d.get("picture") and isinstance(d.get("y_lane"), int)]
    assert len(elevated_crests) >= 10
    assert "%" in nhl["stat_caption"]

    # 4. Casting sheets: uniform bar color for non-teams; team color kept for teams; Mariah Carey allowed
    odd = by_slug["machinery-pop-culture-oddities"]
    assert odd["variant"] == "casting_sheet"
    odd_bars = [
        m
        for it in odd["kit_card"]["body"]["items"]
        for m in it["marks"]
        if m.get("mark") == "bar"
    ]
    assert odd_bars and all("fill_color" not in b for b in odd_bars)

    nfl_front = by_slug["roundup-nfl-division-front-runners"]
    assert "bain luck blend" not in nfl_front["stat_caption"].lower()
    assert "%" in nfl_front["stat_caption"]

    # 5. Road captions & declarative headlines
    celtics = by_slug["celtics-next-3-games"]
    assert celtics["variant"] == "road_ahead"
    assert "Boston is " in celtics["stat_caption"]
    assert "Washington Wizards (" not in celtics["stat_caption"]
    assert by_slug["machinery-who-gets-engaged"]["common_headline"] == "Celebrity engagements by Dec 31"
    assert by_slug["machinery-nba-night"]["common_headline"].startswith("NBA, ")
    assert by_slug["machinery-nfl-week"]["common_headline"].startswith("NFL, ")

    for entry in by_slug.values():
        card_blob = json.dumps(entry["kit_card"]).lower()
        assert "served ladder" not in card_blob
        assert " x " not in card_blob
        assert "ptb" not in card_blob

    # 6. Genuine refusals remain blocked honestly
    assert "benedict cumberbatch" in refused_by_slug["machinery-cast-delayed-cancelled"]["refusal_reason"].lower()
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
