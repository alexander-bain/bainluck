"""Integrity & quarantine guards for the frozen CU sealed and dev datasets (#13898)."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.draw_cu_eval_sets import (
    DEV_PATH,
    DRAW_SEED,
    MANIFEST_PATH,
    SEALED_PATH,
    _resolve_db_url,
    enrich_frozen_payload,
    sha256_bytes,
    verify_committed_sets,
)


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_committed_dataset_hashes_and_invariants_match_manifest():
    assert verify_committed_sets() == []

    manifest = _load(MANIFEST_PATH)
    assert manifest["seed"] == DRAW_SEED
    assert "quarterly_refresh_rule" in manifest and "third" in manifest["quarterly_refresh_rule"]

    sealed = _load(SEALED_PATH)
    dev = _load(DEV_PATH)
    assert sealed["seed"] == DRAW_SEED
    assert dev["seed"] == DRAW_SEED
    assert sealed["counts"] == {"total": 300, "reader_weighted": 200, "roster_spread": 100}
    assert dev["counts"] == {"total": 200, "reader_weighted": 100, "roster_spread": 50, "pilot_50": 50}
    assert sealed["reader_exposure_measure"]["date_range"] == manifest["reader_exposure_date_range"]
    for payload in (sealed, dev):
        assert "does not store contract rules text" in payload["rules_text_note"]
        assert "10 of 100" in payload["draw_order_note"]
        assert "69 of 200" in payload["draw_order_note"]


def test_sealed_and_dev_are_disjoint_and_sealed_excludes_all_pilot_markets():
    sealed = _load(SEALED_PATH)
    dev = _load(DEV_PATH)
    sealed_ids = {m["market_id"] for m in sealed["markets"]}
    dev_ids = {m["market_id"] for m in dev["markets"]}
    pilot_ids = {m["market_id"] for m in dev["markets"] if m["draw_bucket"] == "pilot_50"}

    assert len(pilot_ids) == 50
    assert sealed_ids.isdisjoint(dev_ids)
    assert sealed_ids.isdisjoint(pilot_ids)


def test_frozen_entries_have_required_inputs_and_no_reader_or_profile_leakage():
    forbidden_keys = {"search_query", "user_id", "discover_llm", "new_profile", "previous_profile"}
    sealed = _load(SEALED_PATH)
    dev = _load(DEV_PATH)
    linked_total = 0
    linked_with_league = 0
    for payload in (sealed, dev):
        for entry in payload["markets"]:
            assert forbidden_keys.isdisjoint(entry.keys())
            assert isinstance(entry["market_id"], int)
            assert entry["title"]
            assert entry["source"]
            assert isinstance(entry["outcome_names"], list)
            assert "resolution_date" in entry
            assert "rules_text" in entry
            for key in ("linked_league", "home_team_league", "away_team_league"):
                assert key in entry
            if entry.get("event_id") is not None:
                linked_total += 1
                if entry.get("linked_league"):
                    linked_with_league += 1
            outcomes = entry["outcomes"]
            assert entry["outcome_names"] == [o["name"] for o in outcomes]
            assert all("rank" in o for o in outcomes)
            sort_keys = [
                (o["rank"] is None, o["rank"] if o["rank"] is not None else 0, o["outcome_id"])
                for o in outcomes
            ]
            assert sort_keys == sorted(sort_keys)
    assert linked_total == 59
    assert linked_with_league == 59
    assert sum(1 for m in sealed["markets"] if m["outcome_names"]) >= 295
    assert all(m["outcome_names"] for m in dev["markets"])


def test_draw_requires_explicit_database_url_and_enrich_sorts_by_rank(monkeypatch):
    import pytest

    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError, match="Alex's explicit yes"):
        _resolve_db_url()

    enriched, stats = enrich_frozen_payload(
        {
            "schema_version": 1,
            "seed": DRAW_SEED,
            "quarterly_refresh_rule": "rule",
            "markets": [
                {
                    "market_id": 10,
                    "event_id": 99,
                    "linked_event_status": "scheduled",
                    "outcomes": [
                        {"outcome_id": 1, "name": "Unranked", "prob": 0.1, "move": None},
                        {"outcome_id": 2, "name": "Second", "prob": 0.3, "move": None},
                        {"outcome_id": 3, "name": "First", "prob": 0.6, "move": None},
                    ],
                    "outcome_names": ["Unranked", "Second", "First"],
                }
            ],
        },
        ranks_by_outcome_id={1: None, 2: 2, 3: 1},
        leagues_by_event_id={
            99: {
                "linked_league": "soccer_uefa_europa_league",
                "home_team_league": "soccer_italy_serie_a",
                "away_team_league": "soccer_england_efl_champ",
            }
        },
    )
    assert stats == {"total_outcomes": 3, "matched_outcomes": 3, "linked_markets_enriched": 1}
    m = enriched["markets"][0]
    assert m["outcome_names"] == ["First", "Second", "Unranked"]
    assert [o["rank"] for o in m["outcomes"]] == [1, 2, None]
    assert m["linked_league"] == "soccer_uefa_europa_league"
    assert m["home_team_league"] == "soccer_italy_serie_a"
    assert m["away_team_league"] == "soccer_england_efl_champ"


def test_negative_control_hash_mismatch_is_caught(tmp_path):
    raw = SEALED_PATH.read_bytes()
    tampered = tmp_path / "tampered.json"
    tampered.write_bytes(raw + b" ")
    manifest = _load(MANIFEST_PATH)
    expected = manifest["files"]["cu_sealed_300_v1.json"]["sha256"]
    assert sha256_bytes(tampered.read_bytes()) != expected
