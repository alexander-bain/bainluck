from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from scripts.evals.typed_provider_fetch_contract import evaluate_case, evaluate_corpus, load_corpus

FIXTURE = Path(__file__).parent / "fixtures/typed_provider_fetch_contract.json"


def _case(case_id: str) -> dict:
    return copy.deepcopy(next(row for row in load_corpus(FIXTURE)["cases"] if row["id"] == case_id))


def test_committed_corpus_covers_provider_boundaries() -> None:
    corpus = load_corpus(FIXTURE)
    report = evaluate_corpus(corpus)
    assert report["total"] >= 20
    assert report["passed"] == report["total"]
    ids = {row["id"] for row in corpus["cases"]}
    assert {"kalshi-event-timeout", "kalshi-candles-429", "mlb-schedule-empty", "mlb-schedule-timeout", "poison-row"} <= ids


def test_failure_holds_cursor_and_preserves_truth() -> None:
    verdict = evaluate_case(_case("kalshi-event-timeout"))
    assert verdict["typed_outcome"] == "error"
    assert verdict["cursor_action"] == "hold"
    assert verdict["cache_action"] == "preserve"
    assert verdict["task_verdict"] == "failed"


def test_legitimate_empty_is_not_failure() -> None:
    verdict = evaluate_case(_case("mlb-schedule-empty"))
    assert verdict["typed_outcome"] == "empty"
    assert verdict["task_verdict"] == "complete"


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
