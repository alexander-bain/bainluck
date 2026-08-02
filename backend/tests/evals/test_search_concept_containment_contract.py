from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from scripts.evals.search_concept_containment_contract import evaluate_case, evaluate_corpus, load_corpus, meaningful_tokens, tokens

FIXTURE = Path(__file__).parent / "fixtures" / "search_concept_containment_contract.json"


def _case(case_id: str) -> dict:
    return copy.deepcopy(next(row for row in load_corpus(FIXTURE)["cases"] if row["id"] == case_id))


def test_committed_corpus_is_complete_and_matches_oracles() -> None:
    corpus = load_corpus(FIXTURE)
    report = evaluate_corpus(corpus)
    assert report["total"] == 24
    assert report["passed"] == 24
    ids = {row["id"] for row in corpus["cases"]}
    assert {"quidditch-world-cup-broken", "synthetic-final-event-broken", "oakland-as"} <= ids
    assert {"poison-first", "poison-middle", "poison-last"} <= ids


def test_query_derived_concept_must_explain_all_meaningful_terms() -> None:
    row = _case("bare-world-cup")
    row["query"] = "quidditch world cup"
    assert "CONCEPT_UNEXPLAINED_TERMS" in evaluate_case(row)


def test_specific_event_keeps_gold_top_one_over_parent_concept() -> None:
    row = _case("synthetic-final-event-broken")
    errors = evaluate_case(row)
    assert {"CONCEPT_UNEXPLAINED_TERMS", "TOP_IDENTITY_CHANGED"} <= set(errors)


def test_registered_historical_alias_resolves_canonical_identity() -> None:
    row = _case("oakland-as")
    row["result"]["candidates"][0]["id"] = "team:golden-grizzlies"
    row["result"]["identity_order"][0] = "team:golden-grizzlies"
    errors = evaluate_case(row)
    assert {"REGISTERED_ALIAS_NOT_CANONICAL", "TOP_IDENTITY_CHANGED"} <= set(errors)


def test_ambiguous_alias_does_not_force_a_winner() -> None:
    row = _case("oakland-ambiguous")
    row["result"].update({"outcome": "found", "candidates": [{"id": "team:guess", "surface": "team"}], "identity_order": ["team:guess"]})
    errors = evaluate_case(row)
    assert {"AMBIGUOUS_ALIAS_FORCED", "AMBIGUITY_SELECTS_TOP", "OUTCOME_DRIFT"} <= set(errors)


def test_punctuation_case_and_possessive_normalization() -> None:
    assert tokens("Oakland A’s") == ["oakland", "as"]
    assert meaningful_tokens("THE World—Cup?!") == {"world", "cup"}


def test_response_equivalence_preserves_counts_filters_and_pagination() -> None:
    row = _case("response-equivalence")
    row["response"]["returned_counts"]["futures"] = 0
    row["response"]["filters"] = {"sport": "soccer"}
    errors = evaluate_case(row)
    assert {"RESPONSE_COUNT_FALSE", "RESPONSE_TOTAL_FALSE", "FILTER_DRIFT"} <= set(errors)


def test_unruled_identity_is_not_selected_by_the_evaluator() -> None:
    assert "IDENTITY_NEEDS_ALEX_RULING" in evaluate_case(_case("unruled-identity-refused"))


@pytest.mark.parametrize("case_id", ["poison-first", "poison-middle", "poison-last"])
def test_poison_order_preserves_healthy_candidates(case_id: str) -> None:
    row = _case(case_id)
    row["poison"]["healthy_survive"] = False
    assert "POISON_WIPES_HEALTHY_CANDIDATES" in evaluate_case(row)


def test_evaluation_is_order_independent() -> None:
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
