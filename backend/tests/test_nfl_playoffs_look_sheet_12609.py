"""#12609 — NFL Playoffs and Super Bowl Container Look Sheet tests."""

from __future__ import annotations

import json
from pathlib import Path

from app.routes.admin_ranking_eval import (
    NFL_PLAYOFFS_LOOK_SHEET_SLATE_ID,
    load_grouping_grade_deck,
)


def test_load_nfl_playoffs_look_sheet_deck():
    sheet_path = (
        Path(__file__).resolve().parents[1]
        / "data"
        / "groupings"
        / "nfl-playoffs-look-sheet.json"
    )
    assert sheet_path.exists()
    raw = json.loads(sheet_path.read_text(encoding="utf-8"))
    assert raw["slate_id"] == "nfl-playoffs-look-sheet-2026-11"
    assert len(raw["items"]) == 7

    deck = load_grouping_grade_deck(slate_id=NFL_PLAYOFFS_LOOK_SHEET_SLATE_ID)
    assert deck["slate_id"] == "nfl-playoffs-look-sheet-2026-11"
    assert deck["surface"] == "grouping"
    items = deck["items"]
    assert len(items) == 7
    assert [it["position"] for it in items] == list(range(1, 8))

    expected_keys = [
        "nfl-section-1-playoffs-to-super-bowl-paired-bars",
        "nfl-section-2-afc-nfc-conference-paths",
        "nfl-section-3-division-races-by-shape",
        "nfl-section-4-mvp-and-awards-spotlight",
        "nfl-section-5-games-that-move-the-picture",
        "nfl-section-6-too-many-props-steelers-bengals",
        "nfl-container-full-rhythm-preview",
    ]
    assert [it["item_key"] for it in items] == expected_keys

    # Adjacent sections never share a proposed_kind
    kinds = [it["proposed_kind"] for it in items]
    for i in range(1, len(kinds)):
        assert kinds[i] != kinds[i - 1], f"Adjacent sections {i} and {i+1} share {kinds[i]}"

    # Section 1 stands on the unified Super Bowl winner board (#86832 / #12530) and Feb 14, 2027
    s1 = items[0]
    assert "Feb 14, 2027" in s1["proposed_card"]["subtitle"]
    assert s1["best_single"]["id"] == 86832
    assert s1["best_single"]["rendered_percent"] == 13

    # Section 6 is the 'too many props' section on Steelers at Bengals (671 markets)
    s6 = items[5]
    assert s6["member_count"] == 671
    assert "384 player props" in s6["proposed_card"]["subtitle"]

    # No reader-facing card copy calls a market a 'question' (#12591)
    for it in items:
        card = it["proposed_card"]
        for field in ("title", "subtitle", "count_line", "footer"):
            val = str(card.get(field) or "").lower()
            assert "question" not in val
