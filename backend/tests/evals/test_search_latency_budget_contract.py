from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from scripts.evals.search_latency_budget_contract import (
    evaluate_case,
    evaluate_corpus,
    load_corpus,
)

FIXTURE = Path(__file__).parent / "fixtures" / "search_latency_budget_contract.json"


def _case(case_id: str) -> dict:
    return copy.deepcopy(next(row for row in load_corpus(FIXTURE)["cases"] if row["id"] == case_id))


def test_committed_corpus_is_versioned_complete_and_matches_oracles() -> None:
    corpus = load_corpus(FIXTURE)
    report = evaluate_corpus(corpus)
    assert report["total"] == 23
    assert report["passed"] == 23
    ids = {row["id"] for row in corpus["cases"]}
    assert {"nba-champion-contained", "lebron-james-gold", "world-series-concept"} <= ids
    assert {"poison-first", "poison-middle", "poison-last"} <= ids


def test_multiword_league_token_cannot_be_a_standalone_event_match() -> None:
    row = _case("nba-champion-contained")
    row["plan"]["event_scope"] = "league_token_or_all_events"
    assert "LEAGUE_TERM_BROADENS_EVENT_SCOPE" in evaluate_case(row)


def test_count_must_be_predicate_only_without_order_projection_or_eager_work() -> None:
    row = _case("nba-champion-contained")
    row["plan"].update({
        "count_shape": "ordered_full_entity_subquery",
        "count_has_ordering": True,
        "count_has_entity_projection": True,
        "count_has_eager_load": True,
    })
    assert {"COUNT_SHAPE_WIDE", "COUNT_HAS_ORDERING", "COUNT_HAS_UNUSED_WORK"} <= set(evaluate_case(row))


def test_absolute_and_statement_deadlines_are_required() -> None:
    row = _case("team-query")
    row["plan"]["absolute_deadline_ms"] = 0
    row["plan"]["statement_timeout_ms"] = 0
    errors = evaluate_case(row)
    assert "ABSOLUTE_DEADLINE_MISSING" in errors
    assert "STATEMENT_TIMEOUT_UNBOUNDED" in errors


def test_success_after_deadline_is_refused_even_when_results_exist() -> None:
    row = _case("slow-optional-after-authority")
    row["result"]["outcome"] = "success"
    assert "SUCCESS_AFTER_DEADLINE" in evaluate_case(row)


def test_pre_authority_timeout_cannot_fabricate_empty_or_partial_truth() -> None:
    row = _case("slow-count-before-authority")
    row["result"].update({"outcome": "typed_partial", "entity_ids": ["fake:row"], "total_mode": "exact"})
    errors = evaluate_case(row)
    assert "PRE_AUTHORITY_TIMEOUT_NOT_TYPED" in errors
    assert "PRE_AUTHORITY_TIMEOUT_FABRICATES_RESULTS" in errors


def test_post_authority_optional_timeout_preserves_identity_and_is_typed() -> None:
    row = _case("slow-optional-after-authority")
    assert evaluate_case(row) == []
    row["result"]["entity_ids"] = ["team:wrong"]
    errors = evaluate_case(row)
    assert "REQUIRED_RESULT_MISSING" in errors
    assert "TOP_RESULT_CHANGED" in errors


def test_bounded_total_requires_a_reason() -> None:
    row = _case("slow-optional-after-authority")
    del row["result"]["total_bound_reason"]
    assert "BOUNDED_TOTAL_UNTYPED" in evaluate_case(row)


def test_analytics_and_cancellation_cannot_hide_on_the_critical_path() -> None:
    row = _case("team-query")
    row["plan"]["analytics_awaited"] = True
    row["plan"]["cancellation"] = "swallowed"
    errors = evaluate_case(row)
    assert "ANALYTICS_ON_CRITICAL_PATH" in errors
    assert "CANCELLATION_SWALLOWED" in errors


@pytest.mark.parametrize("case_id", ["poison-first", "poison-middle", "poison-last"])
def test_poison_order_never_wipes_healthy_siblings(case_id: str) -> None:
    row = _case(case_id)
    assert evaluate_case(row) == []
    row["poison"]["healthy_siblings_survive"] = False
    assert "POISON_WIPES_HEALTHY_RESULTS" in evaluate_case(row)


def test_duplicate_results_and_top_one_regressions_are_explicit() -> None:
    row = _case("team-query")
    row["result"]["entity_ids"] = ["team:wrong", "team:boston-red-sox", "team:boston-red-sox"]
    errors = evaluate_case(row)
    assert {"TOP_RESULT_CHANGED", "DUPLICATE_RESULT"} <= set(errors)


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
