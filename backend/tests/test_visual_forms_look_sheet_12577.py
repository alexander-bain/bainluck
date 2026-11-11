"""#12577 / #12523 — Visual Forms Look Sheet deck & Paired-Metric Register tests."""

from __future__ import annotations

import json
from pathlib import Path

from app.routes.admin_ranking_eval import (
    VISUAL_FORMS_LOOK_SHEET_SLATE_ID,
    load_grouping_grade_deck,
)


def test_paired_metric_register_is_valid_and_never_blends():
    reg_path = (
        Path(__file__).resolve().parents[1]
        / "data"
        / "groupings"
        / "paired_metric_register.json"
    )
    assert reg_path.exists()
    data = json.loads(reg_path.read_text(encoding="utf-8"))
    assert data["rules"]["never_blend_propositions"] is True
    assert data["rules"]["pairing_authority"] == "hand_kept_register"
    assert data["rules"]["kid_safe_gate_issue"] == 7461

    sets = data["sets"]
    assert "oscars-2027-best-picture" in sets
    assert "nhl-2026-27-playoffs-and-cup" in sets

    bp = sets["oscars-2027-best-picture"]
    assert bp["stage_1_market"]["id"] == 5165726
    assert bp["stage_2_market"]["id"] == 6173044
    assert len(bp["entries"]) == 10
    rocky = next(e for e in bp["entries"] if e["subject"] == "I Play Rocky")
    assert rocky["stage_1_probability"] == 0.475
    assert rocky["stage_2_probability"] is None
    assert "No recent win %" in rocky["missing_stage_2_reason"]


def test_load_visual_forms_look_sheet_deck():
    deck = load_grouping_grade_deck(slate_id=VISUAL_FORMS_LOOK_SHEET_SLATE_ID)
    assert deck["slate_id"] == "visual-forms-look-sheet-2026-11"
    assert deck["surface"] == "grouping"
    items = deck["items"]
    assert len(items) == 9

    positions = [it["position"] for it in items]
    assert positions == list(range(1, 10))

    # First 6 items are the 6 visual form cards (including non-Oscars NHL #5)
    assert items[0]["item_key"] == "form-1-paired-bars-with-art-best-picture"
    assert items[4]["item_key"] == "form-5-sports-playoffs-to-title-nhl"
    assert items[4]["category"] == "hockey"

    # Last 3 items are the 3 Oscars container options (#12523)
    assert items[6]["item_key"] == "container-a-alternating-form-magazine"
    assert items[7]["item_key"] == "container-b-shape-driven-contrast"
    assert items[8]["item_key"] == "container-c-two-act-ballot"
