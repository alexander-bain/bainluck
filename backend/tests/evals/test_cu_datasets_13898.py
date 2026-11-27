"""Integrity & quarantine guards for the frozen CU sealed and dev datasets (#13898)."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.draw_cu_eval_sets import (
    DEV_PATH,
    DRAW_SEED,
    MANIFEST_PATH,
    SEALED_PATH,
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
    for payload in (sealed, dev):
        for entry in payload["markets"]:
            assert forbidden_keys.isdisjoint(entry.keys())
            assert isinstance(entry["market_id"], int)
            assert entry["title"]
            assert entry["source"]
            assert isinstance(entry["outcome_names"], list)
            assert "resolution_date" in entry
            assert "rules_text" in entry
    assert sum(1 for m in sealed["markets"] if m["outcome_names"]) >= 295
    assert all(m["outcome_names"] for m in dev["markets"])


def test_negative_control_hash_mismatch_is_caught(tmp_path):
    raw = SEALED_PATH.read_bytes()
    tampered = tmp_path / "tampered.json"
    tampered.write_bytes(raw + b" ")
    manifest = _load(MANIFEST_PATH)
    expected = manifest["files"]["cu_sealed_300_v1.json"]["sha256"]
    assert sha256_bytes(tampered.read_bytes()) != expected
