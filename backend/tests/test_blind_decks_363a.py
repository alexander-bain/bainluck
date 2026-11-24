"""Validation and leak-guard tests for Ruling 363: A blind decks."""

from __future__ import annotations

import json
from pathlib import Path

DISCOVER_DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "discover"
FORMS_DECK_PATH = DISCOVER_DATA_DIR / "forms_blind_deck_2026_11_23.json"
CONTAINERS_DECK_PATH = DISCOVER_DATA_DIR / "containers_blind_20_deck_2026_11_23.json"
EXPECTED_SHA = "f164f38c7ff15874b1c7d85c10465dd954302d33"
EXPECTED_RAW_PREFIX = f"https://raw.githubusercontent.com/alexander-bain/bainluck/{EXPECTED_SHA}/"


def test_forms_blind_deck_manifest_is_uniform_and_complete() -> None:
    doc = json.loads(FORMS_DECK_PATH.read_text(encoding="utf-8"))
    assert doc["deck_id"] == "forms-blind-deck-2026-11-23"
    assert doc["ruling"] == "363: A"
    assert doc["image_width_px"] == 780
    assert doc["css_width_px"] == 390
    assert doc["color_scheme"] == "light"
    assert doc["atlas_images_sha"] == EXPECTED_SHA
    assert doc["sheet_image_url"].startswith(EXPECTED_RAW_PREFIX)

    forms = doc["forms"]
    assert len(forms) == 14
    item_ids = [f["item_id"] for f in forms]
    form_ids = [f["form_id"] for f in forms]
    assert len(set(item_ids)) == 14
    assert len(set(form_ids)) == 14

    for f in forms:
        assert f["width_px"] == 780
        assert f["height_px"] > 200
        assert f["image_url"].startswith(f"{EXPECTED_RAW_PREFIX}forms-deck-2026-11-23/form-")
        assert f["display_name"]
        assert f["source_slug"]


def test_containers_blind_20_deck_is_unlabelled_and_key_not_committed() -> None:
    doc = json.loads(CONTAINERS_DECK_PATH.read_text(encoding="utf-8"))
    assert doc["deck_id"] == "containers-blind-20-2026-11-23"
    assert doc["blind"] is True
    assert doc["seed"] == 2026112303
    assert doc["universe_count"] == 41
    assert len(doc["sealed_checksum_sha256"]) == 64
    assert doc["image_width_px"] == 780
    assert doc["css_width_px"] == 390
    assert doc["color_scheme"] == "light"
    assert doc["grade_options"] == ["Keep", "Fix", "Drop"]

    items = doc["items"]
    assert len(items) == 20
    expected_keys = {
        "item_id",
        "card_image_url",
        "page_image_url",
        "card_width_px",
        "card_height_px",
        "page_width_px",
        "page_height_px",
    }
    forbidden_substrings = ("machinery-", "presidential", "white-christmas", "nfl-week", "oscars", "form_id")
    raw_text = CONTAINERS_DECK_PATH.read_text(encoding="utf-8").lower()
    for needle in forbidden_substrings:
        assert needle not in raw_text, f"Leaked identifier {needle!r} in blind containers deck"

    for i, item in enumerate(items, 1):
        assert set(item.keys()) == expected_keys
        assert item["item_id"] == f"c{i:02d}"
        assert item["card_width_px"] == 780
        assert item["page_width_px"] == 780
        assert item["card_height_px"] > 200
        assert item["page_height_px"] > item["card_height_px"]
        assert item["card_image_url"] == f"{EXPECTED_RAW_PREFIX}containers-deck-2026-11-23/c{i:02d}-card.png"
        assert item["page_image_url"] == f"{EXPECTED_RAW_PREFIX}containers-deck-2026-11-23/c{i:02d}-page.png"

    # Sealed key must remain outside the repository until Alex freezes grades.
    leaked = list(DISCOVER_DATA_DIR.rglob("*containers_blind_20_key*"))
    assert leaked == [], f"Blind key must not exist in repo: {leaked}"
