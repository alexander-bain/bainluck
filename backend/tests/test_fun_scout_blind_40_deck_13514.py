"""Integrity and blindness tests for the 40-card Fun Scout blind deck (#13514)."""

from __future__ import annotations

import json
import re
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "discover"
DECK_PATH = DATA_DIR / "fun_scout_blind_40_deck_2026_11_23.json"
KEY_PATH = DATA_DIR / "fun_scout_blind_40_key_2026_11_23.json"

BANNED_VOICE_RE = re.compile(r"\b(?:traders?|bets?|betting)\b", re.IGNORECASE)
FULL_LEAK_TOKENS = (
    "machinery-",
    "batch3",
    "batch4",
    "batch5",
    "batch6",
    "batch7",
    "batch8",
    "hand_written",
    "model_proposed",
    "claude-",
    "curated",
    "scout",
)
CARD_META_LEAK_TOKENS = (*FULL_LEAK_TOKENS, "opus", "sonnet")


def test_blind_40_deck_schema_uniformity_and_zero_leaks():
    deck_raw = DECK_PATH.read_text(encoding="utf-8")
    deck = json.loads(deck_raw)

    assert deck["card_count"] == 40
    assert deck["grade_options"] == ["Keep", "Fix", "Drop"]
    assert deck["blind"] is True

    cards = deck["cards"]
    assert len(cards) == 40
    assert [card["card_id"] for card in cards] == [f"blind-{idx:02d}" for idx in range(1, 41)]

    expected_card_keys = {
        "card_id",
        "title",
        "kicker",
        "category",
        "summary",
        "look",
        "members",
        "grade_options",
    }
    full_lower = deck_raw.lower()
    for token in FULL_LEAK_TOKENS:
        assert token not in full_lower, f"Provenance token {token!r} leaked into deck JSON"

    for card in cards:
        assert set(card.keys()) == expected_card_keys
        assert card["grade_options"] == ["Keep", "Fix", "Drop"]
        assert card["title"].strip()
        assert card["kicker"] == card["category"].upper()
        assert card["summary"].strip()
        assert card["look"] in {"bars", "faces", "map"}

        meta_text = " ".join(
            [card["card_id"], card["title"], card["kicker"], card["category"], card["summary"]]
        ).lower()
        for token in CARD_META_LEAK_TOKENS:
            assert token not in meta_text, f"Leak token {token!r} in {card['card_id']} metadata"
        assert not BANNED_VOICE_RE.search(meta_text), f"Banned voice word in {card['card_id']}"

        members = card["members"]
        assert 3 <= len(members) <= 6
        seen_member_ids = set()
        for member in members:
            assert set(member.keys()) == {"market_id", "source", "title"}
            assert isinstance(member["market_id"], int) and member["market_id"] > 0
            assert member["market_id"] not in seen_member_ids
            seen_member_ids.add(member["market_id"])
            assert member["source"] in {"kalshi", "polymarket"}
            assert isinstance(member["title"], str) and member["title"].strip()


def test_sealed_key_maps_exact_20_20_split_without_duplicates():
    deck = json.loads(DECK_PATH.read_text(encoding="utf-8"))
    key = json.loads(KEY_PATH.read_text(encoding="utf-8"))

    assert key["deck_id"] == deck["deck_id"]
    assert key["counts"] == {"hand_written": 20, "model_proposed": 20}

    key_cards = key["cards"]
    deck_ids = [card["card_id"] for card in deck["cards"]]
    assert set(key_cards.keys()) == set(deck_ids)

    origins = [entry["origin"] for entry in key_cards.values()]
    assert origins.count("hand_written") == 20
    assert origins.count("model_proposed") == 20

    source_refs = [entry["source_ref"] for entry in key_cards.values()]
    assert len(set(source_refs)) == 40
