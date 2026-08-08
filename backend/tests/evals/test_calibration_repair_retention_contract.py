from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from scripts.evals.calibration_repair_retention_contract import evaluate_case, evaluate_corpus, load_corpus

FIXTURE = Path(__file__).parent / "fixtures/calibration_repair_retention_contract.json"


def _case(case_id: str) -> dict:
    return copy.deepcopy(next(row for row in load_corpus(FIXTURE)["cases"] if row["id"] == case_id))


def test_committed_corpus_is_complete_and_matches_oracles() -> None:
    corpus = load_corpus(FIXTURE)
    report = evaluate_corpus(corpus)
    assert report["total"] >= 24
    assert report["passed"] == report["total"]
    ids = {row["id"] for row in corpus["cases"]}
    assert {"repair-cap-cursor-skip", "retention-deadline-cursor-skip", "empty-200-unknown-existence", "legitimate-multi-winner"} <= ids


def test_repair_cursor_cannot_advance_past_capped_candidates() -> None:
    assert "CURSOR_SKIPS_UNPROCESSED" in evaluate_case(_case("repair-cap-cursor-skip"))["reason_codes"]


def test_retention_cursor_cannot_advance_past_unfetched_candidates() -> None:
    assert "CURSOR_SKIPS_UNFETCHED" in evaluate_case(_case("retention-deadline-cursor-skip"))["reason_codes"]


def test_empty_response_needs_existence_authority() -> None:
    assert "EMPTY_RESPONSE_INVENTS_ABSENCE" in evaluate_case(_case("empty-200-unknown-existence"))["reason_codes"]


def test_loader_rejects_wrong_version_and_duplicate_ids(tmp_path: Path) -> None:
    corpus = load_corpus(FIXTURE)
    corpus["schema_version"] = "wrong"
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(corpus), encoding="utf-8")
    with pytest.raises(ValueError, match="SCHEMA_VERSION_INVALID"):
        load_corpus(path)
    corpus = load_corpus(FIXTURE)
    corpus["cases"].append(copy.deepcopy(corpus["cases"][0]))
    path.write_text(json.dumps(corpus), encoding="utf-8")
    with pytest.raises(ValueError, match="CASE_ID_DUPLICATE"):
        load_corpus(path)
