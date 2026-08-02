from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from scripts.evals.search_response_truth_contract import evaluate_case, evaluate_corpus, load_corpus

FIXTURE = Path(__file__).parent / "fixtures" / "search_response_truth_contract.json"


def _case(case_id: str) -> dict:
    return copy.deepcopy(next(row for row in load_corpus(FIXTURE)["cases"] if row["id"] == case_id))


def test_committed_corpus_is_versioned_complete_and_matches_oracles() -> None:
    corpus = load_corpus(FIXTURE)
    report = evaluate_corpus(corpus)
    assert report["total"] == 22
    assert report["passed"] == 22
    ids = {row["id"] for row in corpus["cases"]}
    assert {"nba-champion-contained", "lebron-james-count-repair", "world-series-deadline"} <= ids
    assert {"poison-first", "poison-middle", "poison-last"} <= ids


def test_cross_family_total_must_equal_declared_returned_counts() -> None:
    row = _case("mixed-all-families")
    row["response"]["total"]["value"] = 3
    assert "EXACT_TOTAL_FALSE" in evaluate_case(row)


def test_event_only_total_must_name_its_scope() -> None:
    row = _case("ambiguous-event-total-refused")
    assert "EVENT_TOTAL_FIELD_AMBIGUOUS" in evaluate_case(row)
    row["response"]["total"]["field"] = "event_total_results"
    assert evaluate_case(row) == []


def test_per_family_returned_counts_are_not_advisory() -> None:
    row = _case("futures-only")
    row["response"]["returned_counts"]["futures"] = 0
    assert "RETURNED_COUNT_MISMATCH" in evaluate_case(row)


def test_pre_authority_timeout_cannot_masquerade_as_an_honest_miss() -> None:
    row = _case("unknown-total-timeout")
    row["response"].update({"outcome": "success", "complete": True, "omitted_families": []})
    errors = evaluate_case(row)
    assert "SUCCESS_TOTAL_NOT_EXACT" in errors


def test_partial_response_names_every_omitted_family() -> None:
    row = _case("bounded-total")
    row["response"]["omitted_families"] = []
    assert "PARTIAL_OMISSION_UNDECLARED" in evaluate_case(row)


def test_frozen_identity_order_top_filter_and_pagination_are_preserved() -> None:
    row = _case("mixed-all-families")
    row["response"]["families"]["concepts"] = []
    row["response"]["returned_counts"]["concepts"] = 0
    row["response"]["identity_order"] = ["team:t1", "event:e1", "future:f1"]
    row["response"]["total"]["value"] = 3
    errors = evaluate_case(row)
    assert {"REQUIRED_IDENTITY_MISSING", "IDENTITY_DRIFT", "TOP_IDENTITY_CHANGED"} <= set(errors)


def test_semantic_change_is_a_ruling_not_an_optimization() -> None:
    assert evaluate_case(_case("semantic-change-refused")) == ["SEMANTIC_CHANGE_NEEDS_RULING"]


def test_stale_optional_enrichment_cannot_change_identity() -> None:
    row = _case("stale-enrichment")
    row["response"]["enrichment"]["changes_identity"] = True
    assert "STALE_ENRICHMENT_CHANGES_IDENTITY" in evaluate_case(row)


@pytest.mark.parametrize("case_id", ["poison-first", "poison-middle", "poison-last"])
def test_poison_order_preserves_healthy_siblings(case_id: str) -> None:
    row = _case(case_id)
    row["poison"]["healthy_siblings_survive"] = False
    assert "POISON_WIPES_HEALTHY_RESULTS" in evaluate_case(row)


def test_duplicate_identities_are_refused_across_the_response() -> None:
    assert evaluate_case(_case("duplicate-identity-refused")) == ["DUPLICATE_IDENTITY"]


def test_evaluation_is_deterministic_regardless_of_case_order() -> None:
    corpus = load_corpus(FIXTURE)
    reversed_corpus = copy.deepcopy(corpus)
    reversed_corpus["cases"].reverse()
    assert evaluate_corpus(corpus) == evaluate_corpus(reversed_corpus)


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
