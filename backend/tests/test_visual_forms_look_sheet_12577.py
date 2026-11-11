"""#12577 / #12523 — Visual Forms Look Sheet (Sheet 1 + Sheet 2) & Paired-Metric Register tests."""

from __future__ import annotations

import json
from pathlib import Path

from app.routes.admin_ranking_eval import (
    VISUAL_FORMS_LOOK_SHEET_SLATE_ID,
    load_grouping_grade_deck,
)
from app.services.paired_metric_register import (
    SERVER_BLEND_AUTHORITY,
    compute_server_venue_blend,
    load_paired_metric_register,
)
from app.utils import aggregation


def test_paired_metric_register_is_valid_and_never_blends():
    reg_path = (
        Path(__file__).resolve().parents[1]
        / "data"
        / "groupings"
        / "paired_metric_register.json"
    )
    assert reg_path.exists()
    data = load_paired_metric_register(reg_path)
    assert data["rules"]["never_blend_propositions"] is True
    assert data["rules"]["blend_equivalent_venue_legs"] is True
    assert data["rules"]["blend_authority"] == SERVER_BLEND_AUTHORITY
    assert data["rules"]["pairing_authority"] == "hand_kept_register"
    assert data["rules"]["rounding_helper"] == "renderedPercent"
    assert data["rules"]["kid_safe_gate_issue"] == 7461
    assert data["rules"]["tmdb_logo_required"] is True
    assert data["rules"]["tmdb_attribution_url"] == "https://www.themoviedb.org/"

    sets = data["sets"]
    for expected_set_id in (
        "oscars-2027-best-picture",
        "oscars-2027-best-director",
        "oscars-2027-best-actor",
        "oscars-2027-best-actress",
        "oscars-2027-best-animated",
        "nhl-2026-27-playoffs-and-cup",
    ):
        assert expected_set_id in sets

    bp = sets["oscars-2027-best-picture"]
    assert bp["selection_rule"] == "top_10_by_stage_1_probability"
    assert "Top 10 most likely to be nominated" in bp["subtitle"]
    assert bp["stage_1_market"]["id"] == 5165726
    assert bp["stage_1_market"]["companion_polymarket_id"] == 27988771
    assert bp["stage_2_market"]["id"] == 6173044
    assert len(bp["entries"]) == 10
    rocky = next(e for e in bp["entries"] if e["subject"] == "I Play Rocky")
    assert rocky["stage_1_kalshi_probability"] == 0.475
    assert rocky["stage_1_polymarket_probability"] == 0.5
    assert rocky["stage_1_probability"] == 0.4875
    assert rocky["stage_2_probability"] is None
    assert rocky["missing_stage_2_reason"] == "Not listed to win"

    debut = next(e for e in bp["entries"] if e["subject"] == "The Debut")
    assert debut["detail"] == "Jesse Eisenberg · Topic Studios"
    assert debut["credit_source"] == "tmdb:movie:1391239"

    dir_set = sets["oscars-2027-best-director"]
    fielder = next(e for e in dir_set["entries"] if e["subject"] == "Nathan Fielder")
    assert fielder["art"]["tmdb_id"] == 1212667
    assert (
        fielder["art"]["url"]
        == "https://image.tmdb.org/t/p/w185/x0UOcjml8WnBfnb89QOh0iXM0w0.jpg"
    )

    nhl = sets["nhl-2026-27-playoffs-and-cup"]
    assert len(nhl["entries"]) == 9
    nhl_subjects = [e["subject"] for e in nhl["entries"]]
    assert "Dallas Stars" in nhl_subjects
    assert "Tampa Bay Lightning" in nhl_subjects


def test_load_visual_forms_look_sheet_deck():
    retired_v1_keys = {
        "form-1-paired-bars-with-art-best-picture",
        "form-2-poster-spotlight-tiles-best-picture",
        "form-3-step-conversion-path-best-picture",
        "form-4-leader-and-chasers-split-best-picture",
        "form-5-sports-playoffs-to-title-nhl",
        "form-6-post-nominations-settled-gate",
        "container-a-alternating-form-magazine",
        "container-b-shape-driven-contrast",
        "container-c-two-act-ballot",
    }

    # Raw file retains the 9 retired v1 records ("graded as sheet 1 stood on Nov 10") + 15 active items
    sheet_path = (
        Path(__file__).resolve().parents[1]
        / "data"
        / "groupings"
        / "visual-forms-look-sheet.json"
    )
    raw = json.loads(sheet_path.read_text(encoding="utf-8"))
    assert len(raw["items"]) == 24
    retired_items = [it for it in raw["items"] if it.get("retired")]
    assert len(retired_items) == 9
    assert {it["item_key"] for it in retired_items} == retired_v1_keys
    for it in retired_items:
        assert it["retired_note"] == "graded as sheet 1 stood on Nov 10"

    # The deck dealt for this slate holds 15 items (positions 1..15), none with a v1 key
    deck = load_grouping_grade_deck(slate_id=VISUAL_FORMS_LOOK_SHEET_SLATE_ID)
    assert deck["slate_id"] == "visual-forms-look-sheet-2026-11"
    assert deck["surface"] == "grouping"
    items = deck["items"]
    assert len(items) == 15
    assert [it["position"] for it in items] == list(range(1, 16))
    for it in items:
        assert it["item_key"] not in retired_v1_keys

    # Items 1–6: Sheet 2 shorter Card 1 variants (1A–1C) + 3 wilder forms
    assert items[0]["item_key"] == "form-1a-paired-bars-top5-expandable-best-picture"
    assert items[1]["item_key"] == "form-1b-paired-bars-single-line-best-picture"
    assert items[2]["item_key"] == "form-1c-paired-bars-top3-plus-strip-best-picture"
    assert items[3]["item_key"] == "form-7-podium-and-tiers-best-picture"
    assert items[4]["item_key"] == "form-8-barbell-race-track-best-picture"
    assert items[5]["item_key"] == "form-9-ballot-quadrant-map-best-picture"

    # Items 7–15: Revised v2 Sheet 1 cards + containers with distinct v2 item_keys
    assert items[6]["item_key"] == "form-1-v2-paired-bars-with-art-best-picture"
    assert items[10]["item_key"] == "form-5-v2-sports-playoffs-to-title-nhl"
    assert items[10]["category"] == "hockey"
    assert items[12]["item_key"] == "container-a-v2-alternating-form-magazine"
    assert items[13]["item_key"] == "container-b-v2-shape-driven-contrast"
    assert items[14]["item_key"] == "container-c-v2-two-act-ballot"

    # Server-hydrated paired_metric_sets are attached to the look-sheet deck
    assert deck["blend_authority"] == SERVER_BLEND_AUTHORITY
    assert "oscars-2027-best-picture" in deck["paired_metric_sets"]
    assert items[0]["paired_metric_set"]["set_id"] == "oscars-2027-best-picture"
    assert (
        items[0]["paired_metric_set"]["blend_authority"] == SERVER_BLEND_AUTHORITY
    )
    assert items[10]["paired_metric_set"]["set_id"] == "nhl-2026-27-playoffs-and-cup"
    assert items[12]["paired_metric_set"] is None


def test_server_venue_blend_delegates_to_compute_aggregate_probability(monkeypatch):
    # With default weights (kalshi=0.8, polymarket=0.8), 0.475 and 0.500 blend to 0.4875
    assert compute_server_venue_blend(0.475, 0.500) == (
        0.4875,
        SERVER_BLEND_AUTHORITY,
    )
    assert compute_server_venue_blend(0.575, None) == (0.575, "single_venue")
    assert compute_server_venue_blend(None, 0.72) == (0.72, "single_venue")
    assert compute_server_venue_blend(None, None) == (None, None)

    # Changing SOURCE_WEIGHTS in app.utils.aggregation shifts the blended result,
    # proving compute_server_venue_blend delegates to compute_aggregate_probability
    # (including cap_weight_shares and assess_divergence) rather than computing
    # a hardcoded (a + b) / 2.
    patched_weights = dict(aggregation.SOURCE_WEIGHTS)
    patched_weights["kalshi"] = 3.0
    patched_weights["polymarket"] = 1.0
    monkeypatch.setattr(aggregation, "SOURCE_WEIGHTS", patched_weights)

    # Normal spread (0.50 vs 0.60): with equal default weights (0.8/0.8), compute_server_venue_blend is 0.55;
    # with kalshi=3.0, polymarket=1.0, compute_aggregate_probability's weighted median selects 0.50 (not 0.55)
    blended_normal, auth_normal = compute_server_venue_blend(0.50, 0.60)
    assert auth_normal == SERVER_BLEND_AUTHORITY
    assert blended_normal == 0.50

    # Wide divergence (0.40 vs 0.80): assess_divergence triggers _weighted_median -> 0.40 (not 0.60)
    assert compute_server_venue_blend(0.40, 0.80) == (
        0.4,
        SERVER_BLEND_AUTHORITY,
    )

