"""Validation and leak-guard tests for Ruling 363: A blind decks."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routes import admin_judgments

REPO_ROOT = Path(__file__).resolve().parents[2]
DISCOVER_DATA_DIR = REPO_ROOT / "backend" / "data" / "discover"
FRONTEND_DATA_DIR = REPO_ROOT / "frontend" / "data"
FORMS_DECK_PATH = DISCOVER_DATA_DIR / "forms_blind_deck_2026_11_23.json"
FRONTEND_FORMS_PUBLIC_PATH = FRONTEND_DATA_DIR / "forms_blind_deck_public_2026_11_23.json"
CONTAINERS_DECK_PATH = DISCOVER_DATA_DIR / "containers_blind_20_deck_2026_11_23.json"
FRONTEND_CONTAINERS_DECK_PATH = FRONTEND_DATA_DIR / "containers_blind_20_deck_2026_11_23.json"
EXPECTED_SHA = "f164f38c7ff15874b1c7d85c10465dd954302d33"
CARD_IMAGES_SHA = "cc1f3de00dcf9163409408ce5415d8ae861c43e0"
EXPECTED_RAW_PREFIX = f"https://raw.githubusercontent.com/alexander-bain/bainluck/{EXPECTED_SHA}/"
CARD_IMAGES_RAW_PREFIX = f"https://raw.githubusercontent.com/alexander-bain/bainluck/{CARD_IMAGES_SHA}/"


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
        assert item["card_image_url"] == f"{CARD_IMAGES_RAW_PREFIX}containers-deck-2026-11-23/c{i:02d}-card.png"
        assert item["page_image_url"] == f"{EXPECTED_RAW_PREFIX}containers-deck-2026-11-23/c{i:02d}-page.png"

    # Sealed key must remain outside the repository until Alex freezes grades.
    leaked = list(DISCOVER_DATA_DIR.rglob("*containers_blind_20_key*"))
    assert leaked == [], f"Blind key must not exist in repo: {leaked}"


def test_frontend_blind_manifests_have_no_leaks() -> None:
    backend_forms = json.loads(FORMS_DECK_PATH.read_text(encoding="utf-8"))
    public_forms = json.loads(FRONTEND_FORMS_PUBLIC_PATH.read_text(encoding="utf-8"))

    assert public_forms["deck_id"] == "forms-blind-deck-2026-11-23"
    assert public_forms["blind"] is True
    assert public_forms["seed"] == 2026112304
    assert "sheet_image_url" not in public_forms
    assert len(public_forms["forms"]) == len(backend_forms["forms"]) == 14

    public_raw = FRONTEND_FORMS_PUBLIC_PATH.read_text(encoding="utf-8").lower()
    for secret_key in ("form_id", "display_name", "source_slug", "nominations", "mvp", "ladder"):
        assert secret_key not in public_raw, f"Leaked key/label {secret_key!r} in public forms manifest"

    expected_by_id = {f["item_id"]: f for f in backend_forms["forms"]}
    for item in public_forms["forms"]:
        assert set(item.keys()) == {"item_id", "image_url", "width_px", "height_px"}
        ref = expected_by_id[item["item_id"]]
        assert item["image_url"] == ref["image_url"]
        assert item["width_px"] == ref["width_px"]
        assert item["height_px"] == ref["height_px"]

    assert FRONTEND_CONTAINERS_DECK_PATH.read_text(encoding="utf-8") == CONTAINERS_DECK_PATH.read_text(
        encoding="utf-8"
    )


class _DummyWriteDB:
    def __init__(self) -> None:
        self.added = None
        self.committed = False

    async def execute(self, _statement):
        return SimpleNamespace(scalar_one_or_none=lambda: None)

    def add(self, row) -> None:
        self.added = row

    async def commit(self) -> None:
        self.committed = True

    async def refresh(self, row) -> None:
        row.id = 901
        row.date = date(2026, 11, 23)
        row.created_at = datetime(2026, 11, 23, 20, 0, tzinfo=timezone.utc)


def test_ranking_judgments_grade_decks_roundtrip(monkeypatch) -> None:
    db = _DummyWriteDB()
    monkeypatch.setattr(admin_judgments, "_check_admin_secret", lambda secret, **kw: secret == "ok")

    app = FastAPI()
    app.include_router(admin_judgments.router)

    async def _override_db():
        return db

    app.dependency_overrides[admin_judgments.get_db] = _override_db
    app.dependency_overrides[admin_judgments.get_db_rw] = _override_db
    client = TestClient(app)

    unauth = client.post(
        "/admin/ranking-judgments",
        json={
            "surface": "grade_forms_deck",
            "item_type": "forms_deck",
            "market_name": "forms-blind-deck-2026-11-23",
            "label": "piles_saved",
        },
    )
    assert unauth.status_code == 403

    r_forms = client.post(
        "/admin/ranking-judgments",
        json={
            "secret": "ok",
            "surface": "grade_forms_deck",
            "item_type": "forms_deck",
            "market_name": "forms-blind-deck-2026-11-23",
            "label": "piles_saved",
            "reviewer": "alex",
            "label_metadata": {
                "deck_id": "forms-blind-deck-2026-11-23",
                "seed": 2026112304,
                "piles": [{"pile_id": "pile-1", "label": "Pile 1", "item_ids": ["f01", "f03"]}],
            },
        },
    )
    assert r_forms.status_code == 200
    assert db.committed is True
    assert db.added.surface == "grade_forms_deck"

    db2 = _DummyWriteDB()
    app.dependency_overrides[admin_judgments.get_db] = lambda: db2
    app.dependency_overrides[admin_judgments.get_db_rw] = lambda: db2
    client2 = TestClient(app)
    r_containers = client2.post(
        "/admin/ranking-judgments",
        json={
            "secret": "ok",
            "surface": "grade_containers_deck",
            "item_type": "containers_deck",
            "market_name": "containers-blind-20-2026-11-23:c01",
            "label": "Keep",
            "notes": "Clean 390 layout",
            "reviewer": "alex",
            "label_metadata": {"deck_id": "containers-blind-20-2026-11-23", "item_id": "c01", "grade": "Keep"},
        },
    )
    assert r_containers.status_code == 200
    assert db2.committed is True
    assert db2.added.surface == "grade_containers_deck"
    assert db2.added.label == "Keep"
