"""Tests for deterministic real-set Kit v1 builder (Item 3, #13551)."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone

import pytest

from app.utils.kit_v1_set_builder import (
    REAL_SETS_SNAPSHOT_PATH,
    build_kit_card_for_real_set,
    build_real_sets_audit_report,
    load_real_sets_audit_report,
)
from app.utils.kit_v1_spec import ALLOWED_MARKS, validate_kit_v1_card


def _load_snapshot() -> dict:
    with open(REAL_SETS_SNAPSHOT_PATH, encoding="utf-8") as f:
        return json.load(f)


def test_real_sets_audit_covers_top_10_and_all_valid_cards() -> None:
    report = load_real_sets_audit_report()
    assert report["kit_version"] == 1
    assert len(report["top_10"]) == 10
    assert report["total_sets"] == 66
    assert report["fitting_count"] >= 20
    assert report["fitting_count"] + report["kept_today_count"] == report["total_sets"]

    all_tested = report["top_10"] + report["fitting_beyond_top_10"]
    layouts_seen = set()
    for entry in all_tested:
        if entry["fits"]:
            card = entry["kit_card"]
            ok, errs = validate_kit_v1_card(card)
            assert ok, f"{entry['slug']} failed validation: {errs}"
            # Unknown future variant hint MUST also pass layout-generic validation
            ok_probe, errs_probe = validate_kit_v1_card(
                dict(card, variant="future_unknown_variant_probe")
            )
            assert ok_probe, f"{entry['slug']} failed unknown variant probe: {errs_probe}"
            assert card["common_headline"].strip()
            assert card["stat_caption"].strip()
            assert card["common_headline"].lower() != card["stat_caption"].lower()
            layouts_seen.add(card["layout"])

            raw_json = json.dumps(card)
            assert "kalshi" not in raw_json.lower()
            assert "polymarket" not in raw_json.lower()
            assert "opens at" not in raw_json.lower()
            # Ensure no bare hex leaked inside marks; only adaptive {"light", "dark"} dicts allowed
            for m in re.finditer(r'"(fill_color|color)"\s*:\s*"#', raw_json):
                pytest.fail(f"{entry['slug']} emitted raw color hex near {m.group(0)}")
        else:
            assert entry["refusal_reason"], f"{entry['slug']} missing refusal_reason"
            assert entry["kit_card"].get("fallback_today") is True

    assert layouts_seen == {"stack", "grid", "axis"}


def test_real_sets_specific_guards_and_shapes() -> None:
    snap = _load_snapshot()
    report = build_real_sets_audit_report(snap, now=datetime(2026, 11, 24, 6, 40, tzinfo=timezone.utc))
    by_slug = {
        e["slug"]: e
        for e in report["top_10"] + report["fitting_beyond_top_10"]
    }
    refused_by_slug = {k["slug"]: k for k in report["kept_today"]}

    # Single-team road_ahead (no 'opens at', real stat caption with %)
    assert by_slug["celtics-next-3-games"]["layout"] == "stack"
    assert by_slug["celtics-next-3-games"]["variant"] == "road_ahead"
    assert "%" in by_slug["celtics-next-3-games"]["stat_caption"]
    assert by_slug["lakers-next-3-games"]["variant"] == "road_ahead"
    assert "%" in by_slug["lakers-next-3-games"]["stat_caption"]

    # Full-league NHL bubble axis (all 32 teams have verified crests, real stat caption with %, declarative headline)
    assert by_slug["nhl-playoffs-2026-27"]["layout"] == "axis"
    assert by_slug["nhl-playoffs-2026-27"]["variant"] == "bubble_line"
    assert not by_slug["nhl-playoffs-2026-27"]["common_headline"].endswith("?")
    assert "%" in by_slug["nhl-playoffs-2026-27"]["stat_caption"]

    for entry in by_slug.values():
        card_blob = json.dumps(entry["kit_card"]).lower()
        assert "served ladder" not in card_blob
        assert " x " not in card_blob
        assert "ptb" not in card_blob
        assert "current market probabilities" not in card_blob

    # Oscars paired scoreboard grids
    assert by_slug["machinery-oscars-best-picture"]["layout"] == "grid"
    assert by_slug["machinery-oscars-best-actor-2027"]["layout"] == "grid"

    # Countdown sets repeat generic category placeholder images -> refused honestly
    assert "placeholder" in refused_by_slug["by-november-30"]["refusal_reason"].lower()
    assert "placeholder" in refused_by_slug["by-december-31"]["refusal_reason"].lower()

    # Upcoming single-sport slates fit; settled past NFL weeks refuse honestly
    assert by_slug["machinery-nba-night"]["variant"] == "single_sport_slate"
    assert by_slug["nfl-2026-week-12"]["variant"] == "single_sport_slate"
    assert "settled" in refused_by_slug["nfl-2026-week-11"]["refusal_reason"].lower()

    # Contender spotlight stays bar spotlight rather than long-shot 1-in-N
    assert by_slug["machinery-2028-presidential"]["variant"] == "casting_sheet"

    # Integrity refusals: monograms, duplicate entities, art mismatch, missing league crests, stock photos
    assert "monogram" in refused_by_slug["machinery-elon-musk-side-quests"]["refusal_reason"].lower()
    assert "duplicate" in refused_by_slug["machinery-2026-box-office-showdown"]["refusal_reason"].lower()
    assert "benedict cumberbatch" in refused_by_slug["machinery-cast-delayed-cancelled"]["refusal_reason"].lower()
    assert "crests" in refused_by_slug["liga-profesional-relegation-2026"]["refusal_reason"].lower()
    assert "images.pexels.com" in refused_by_slug["middle-east"]["refusal_reason"].lower()
    assert "overlapping" in refused_by_slug["roundup-cfp-picture"]["refusal_reason"].lower()


def test_real_sets_only_uses_eight_generic_marks() -> None:
    report = load_real_sets_audit_report()
    for entry in report["top_10"] + report["fitting_beyond_top_10"]:
        if not entry["fits"]:
            continue
        raw = json.dumps(entry["kit_card"])
        parsed = json.loads(raw)

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


def test_preview_endpoint_route_exists_and_requires_admin() -> None:
    from app.routes.containers import router

    paths = [r.path for r in router.routes]
    assert "/preview/kit-v1-real-sets" in paths
    # Must appear before /{slug} catch-all
    assert paths.index("/preview/kit-v1-real-sets") < paths.index("/{slug}")


def test_real_sets_scrubs_venue_names_and_opens_at_copy() -> None:
    snap = _load_snapshot()
    c19 = snap["containers"]["celtics-next-3-games"]
    b19 = next(
        b for b in snap["bundles"]
        if (b["data"].get("collection_ref") or {}).get("slug") == "celtics-next-3-games"
    )
    noisy = json.loads(json.dumps(b19))
    noisy["headline"] = "Boston opens at 79% in Washington on Kalshi"
    res = build_kit_card_for_real_set(noisy, c19)
    assert res["fits"] is True
    assert "opens at" not in res["stat_caption"].lower()
    assert "kalshi" not in res["stat_caption"].lower()

