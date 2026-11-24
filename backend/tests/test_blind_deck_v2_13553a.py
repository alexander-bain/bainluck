"""Validation, leak-guard, and judgment-write tests for #13544 / #13553a blind v2 deck."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routes import admin_judgments

DISCOVER_DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "discover"
SETS_V2_DECK_PATH = DISCOVER_DATA_DIR / "fun_scout_blind_40_deck_v2_2026_11_23.json"


def test_sets_v2_blind_40_deck_is_uniform_and_key_not_committed() -> None:
    raw = SETS_V2_DECK_PATH.read_text(encoding="utf-8")
    doc = json.loads(raw)
    assert doc["deck_id"] == "discover-blind-40-v2-2026-11-23"
    assert doc["blind"] is True
    assert doc["seed"] == 2026112302
    assert doc["card_count"] == 40
    assert doc["grade_options"] == ["Keep", "Fix", "Drop"]
    assert len(doc["sealed_checksum_sha256"]) == 64

    cards = doc["cards"]
    assert len(cards) == 40
    expected_card_keys = {
        "card_id",
        "title",
        "kicker",
        "category",
        "summary",
        "look",
        "grade_options",
        "members",
    }
    expected_member_keys = {"market_id", "source", "title"}

    for idx, card in enumerate(cards, 1):
        assert set(card.keys()) == expected_card_keys
        assert card["card_id"] == f"blind-{idx:02d}"
        assert card["grade_options"] == ["Keep", "Fix", "Drop"]
        for k in ("title", "kicker", "category", "summary", "look"):
            assert isinstance(card[k], str) and card[k].strip(), (card["card_id"], k)
        members = card["members"]
        assert 3 <= len(members) <= 6, card["card_id"]
        for m in members:
            assert set(m.keys()) == expected_member_keys
            assert isinstance(m["market_id"], int) and m["market_id"] > 0
            assert isinstance(m["source"], str) and m["source"].strip()
            assert isinstance(m["title"], str) and m["title"].strip()

    raw_lower = raw.lower()
    for leaked_arm in ('"arm"', '"baseline"', '"gated"', "atlas-13544-set-quality"):
        assert leaked_arm not in raw_lower

    leaked_keys = list(DISCOVER_DATA_DIR.rglob("*v2*key*")) + list(
        DISCOVER_DATA_DIR.rglob("*blind_40_key_v2*")
    )
    assert leaked_keys == [], f"Blind v2 key must not exist in repo: {leaked_keys}"


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
        row.id = 9001
        row.date = date(2026, 11, 24)
        row.created_at = datetime(2026, 11, 24, 15, 0, tzinfo=timezone.utc)


def _write_app(db: _DummyWriteDB) -> FastAPI:
    app = FastAPI()
    app.include_router(admin_judgments.router)

    async def _get_db():
        return db

    app.dependency_overrides[admin_judgments.get_db] = _get_db
    app.dependency_overrides[admin_judgments.get_db_rw] = _get_db
    return app


def test_ranking_judgments_accepts_sets_v2_deck_surface(monkeypatch) -> None:
    monkeypatch.setattr(admin_judgments, "_check_admin_secret", lambda secret, **_kw: secret == "ok")

    db = _DummyWriteDB()
    client = TestClient(_write_app(db))
    resp = client.post(
        "/admin/ranking-judgments",
        json={
            "secret": "ok",
            "surface": "grade_sets_v2_deck",
            "item_type": "fun_scout_blind_40_v2",
            "market_name": "blind-01",
            "label": "Keep",
            "notes": "clear rows",
            "reviewer": "alex",
            "label_metadata": {"deck_id": "discover-blind-40-v2-2026-11-23", "item_id": "blind-01", "grade": "Keep"},
        },
    )
    assert resp.status_code == 200
    assert db.committed is True
    assert db.added is not None
    assert db.added.surface == "grade_sets_v2_deck"
    assert db.added.label == "Keep"
