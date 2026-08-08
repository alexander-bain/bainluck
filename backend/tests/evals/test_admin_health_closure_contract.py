from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from scripts.evals.admin_health_closure_contract import evaluate_case, evaluate_corpus, load_corpus, lower_fixture_index

FIXTURE = Path(__file__).parent / "fixtures/admin_health_closure_contract.json"


def _case(case_id: str) -> dict:
    return copy.deepcopy(next(r for r in load_corpus(FIXTURE)["cases"] if r["id"] == case_id))


def test_corpus_is_implementation_ready_and_all_refs_exist() -> None:
    corpus = load_corpus(FIXTURE)
    report = evaluate_corpus(corpus)
    assert report["total"] >= 20
    assert report["passed"] == report["total"]
    for row in corpus["cases"]:
        assert row["owner"]["program"]
        assert row["owner"]["modules"]
        assert set(row["composes"]) == {"fetch", "task", "health", "age", "parity"}


def test_kalshi_failure_stays_typed_end_to_end() -> None:
    verdict = evaluate_case(_case("kalshi-candles-rate-limit"), lower_fixture_index())
    assert verdict["helper_outcome"] == "error"
    assert verdict["task_terminal"] == "failed"
    assert verdict["cursor_action"] == "hold"
    assert set(verdict["surface_states"].values()) == {"red"}


def test_stale_last_good_is_dated_and_consistent() -> None:
    verdict = evaluate_case(_case("provider-timeout-dated-last-good"), lower_fixture_index())
    assert verdict["cache_action"] == "serve_stale"
    assert verdict["display_state"] == "stale"
    assert set(verdict["surface_states"].values()) == {"red"}


def test_missing_lower_fixture_ref_refuses() -> None:
    row = _case("clean-success")
    row["composes"]["fetch"] = "does-not-exist"
    verdict = evaluate_case(row, lower_fixture_index())
    assert verdict == {"verdict": "REFUSE", "missing_refs": ["fetch:does-not-exist"], "reason_codes": ["LOWER_FIXTURE_MISSING"]}


def test_loader_rejects_bad_version_and_duplicate_ids(tmp_path: Path) -> None:
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
