from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from scripts.evals.provider_task_propagation_contract import evaluate_case, evaluate_corpus, load_corpus

FIXTURE = Path(__file__).parent / "fixtures/provider_task_propagation_contract.json"


def _case(case_id: str) -> dict:
    return copy.deepcopy(next(row for row in load_corpus(FIXTURE)["cases"] if row["id"] == case_id))


def test_corpus_covers_false_green_boundaries() -> None:
    corpus = load_corpus(FIXTURE)
    report = evaluate_corpus(corpus)
    assert report["total"] >= 20
    assert report["passed"] == report["total"]
    ids = {row["id"] for row in corpus["cases"]}
    assert {"mlb-schedule-timeout", "kalshi-history-rate-limit", "mixed-sibling-failure", "nothing-eligible"} <= ids


def test_primary_failure_never_certifies_success_or_replaces_cache() -> None:
    verdict = evaluate_case(_case("mlb-schedule-timeout"))
    assert verdict["task_verdict"] == "failed"
    assert verdict["metrics_action"] == "failure"
    assert verdict["cache_action"] == "preserve"
    assert verdict["display_state"] == "unavailable"


def test_optional_failure_is_visible_but_nonblocking() -> None:
    verdict = evaluate_case(_case("optional-image-timeout"))
    assert verdict["classification"] == "DEGRADED_VISIBLE"
    assert verdict["task_verdict"] == "partial"


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
