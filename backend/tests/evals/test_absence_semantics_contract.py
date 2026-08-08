from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from scripts.evals.absence_semantics_contract import decide, evaluate_corpus, load_corpus

FIXTURE = Path(__file__).parent / "fixtures/absence_semantics_contract.json"


def _case(case_id: str) -> dict:
    return copy.deepcopy(next(row for row in load_corpus(FIXTURE)["cases"] if row["id"] == case_id))


def test_committed_corpus_is_complete_and_matches_oracles() -> None:
    corpus = load_corpus(FIXTURE)
    report = evaluate_corpus(corpus)
    assert report["total"] >= 18
    assert report["passed"] == report["total"]
    ids = {row["id"] for row in corpus["cases"]}
    assert {"clean-complete-empty", "degraded-empty-first-load-web", "degraded-empty-first-load-native", "partial-primary-family-missing"} <= ids


def test_degraded_empty_never_becomes_honest_empty() -> None:
    row = _case("degraded-empty-first-load-web")
    assert decide(row)["display_state"] == "UNAVAILABLE"
    row["result"]["display_state"] = "EMPTY"
    assert "DISPLAY_STATE_DISHONEST" in decide(row)["reason_codes"]


def test_partial_results_stay_visible_but_disclose_omission() -> None:
    row = _case("partial-primary-family-missing")
    assert decide(row)["display_state"] == "PARTIAL"
    row["result"]["metadata_consumed"] = False
    assert "DEGRADATION_METADATA_IGNORED" in decide(row)["reason_codes"]


def test_stale_last_good_is_cacheable_but_retryable() -> None:
    verdict = decide(_case("stale-last-good"))
    assert verdict["display_state"] == "STALE_RESULTS"
    assert verdict["cacheable"] is True
    assert verdict["retryable"] is True


def test_loader_rejects_wrong_version_and_duplicates(tmp_path: Path) -> None:
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
