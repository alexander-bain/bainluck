from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from scripts.evals.discover_cardinality_containment_contract import evaluate_case, evaluate_corpus, load_corpus

FIXTURE = Path(__file__).parent / "fixtures/discover_cardinality_containment_contract.json"


def _case(case_id: str) -> dict:
    return copy.deepcopy(next(row for row in load_corpus(FIXTURE)["cases"] if row["id"] == case_id))


def test_committed_corpus_is_complete_and_matches_oracles() -> None:
    corpus = load_corpus(FIXTURE)
    report = evaluate_corpus(corpus)
    assert report["total"] >= 20
    assert report["passed"] == report["total"]
    ids = {row["id"] for row in corpus["cases"]}
    assert {"census-86-to-65", "census-65-to-55-unexplained", "tournaments-seven-to-zero", "task-conflicting-params"} <= ids


def test_unexplained_loss_refuses_without_inventing_a_numeric_floor() -> None:
    row = _case("census-65-to-55-unexplained")
    assert evaluate_case(row)["verdict"] == "REFUSE"
    row["census"]["removed"] = [{"id": f"card:{n}", "family": "futures", "reason": "expired"} for n in range(10)]
    assert evaluate_case(row)["verdict"] == "PUBLISH"


def test_crossed_book_is_not_a_narrow_tradeable_book() -> None:
    verdict = evaluate_case(_case("crossed-book-refused"))
    assert verdict["include"] is False
    assert "CROSSED_BOOK_REFUSED" in verdict["reason_codes"]


def test_word_on_is_not_deadline_evidence() -> None:
    verdict = evaluate_case(_case("ticker-up-down-on-earnings"))
    assert verdict["include"] is True
    assert verdict["reason_codes"] == ["DAILY_DIRECTION_DATE_UNPROVEN"]


def test_conflicting_task_parameters_refuse_ambiguity() -> None:
    verdict = evaluate_case(_case("task-conflicting-params"))
    assert verdict == {"verdict": "REFUSE", "subject": None, "reason_codes": ["TASK_SUBJECT_AMBIGUOUS"]}


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
