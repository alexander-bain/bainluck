from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from scripts.evals.search_missing_answer_contract import decide, evaluate_corpus, load_corpus

FIXTURE = Path(__file__).parent / "fixtures/search_missing_answer_contract.json"


def _case(case_id: str) -> dict:
    return copy.deepcopy(next(row for row in load_corpus(FIXTURE)["cases"] if row["id"] == case_id))


def test_committed_corpus_is_complete_and_matches_oracles() -> None:
    corpus = load_corpus(FIXTURE)
    report = evaluate_corpus(corpus)
    assert report["total"] >= 16
    assert report["passed"] == report["total"]
    ids = {row["id"] for row in corpus["cases"]}
    assert {"us-recession-2026", "futures-timeout-with-events", "all-stages-timeout", "count-result-disagreement"} <= ids


def test_degraded_empty_can_never_be_no_matches_or_cacheable() -> None:
    row = _case("us-recession-2026")
    row["result"].update({"display_state": "NO_MATCHES", "cacheable": True})
    assert {"DISPLAY_STATE_DISHONEST", "CACHE_DECISION_DISHONEST"} <= set(decide(row)["reason_codes"])


def test_partial_results_remain_visible_but_are_not_complete() -> None:
    row = _case("futures-timeout-with-events")
    assert decide(row)["display_state"] == "PARTIAL"
    row["result"]["complete"] = True
    assert "DEGRADED_CLAIMS_COMPLETE" in decide(row)["reason_codes"]


def test_honest_clean_miss_is_distinct_from_unknown() -> None:
    verdict = decide(_case("clean-honest-miss"))
    assert verdict == {"display_state": "NO_MATCHES", "cacheable": True, "reason_codes": []}


def test_known_answer_must_be_typed_when_omitted() -> None:
    row = _case("us-recession-2026")
    row["result"]["degraded"] = []
    errors = decide(row)["reason_codes"]
    assert {"KNOWN_FUTURES_MISSING", "MISSING_ANSWER_UNTYPED"} <= set(errors)


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
