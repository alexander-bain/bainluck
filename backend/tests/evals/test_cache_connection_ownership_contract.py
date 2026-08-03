from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from scripts.evals.cache_connection_ownership_contract import evaluate_case, evaluate_corpus, load_corpus, materialize

FIXTURE = Path(__file__).parent / "fixtures" / "cache_connection_ownership_contract.json"


def _case(case_id: str) -> dict:
    corpus = load_corpus(FIXTURE)
    return materialize(corpus, next(row for row in corpus["cases"] if row["id"] == case_id))


def test_corpus_is_complete_and_matches_oracles() -> None:
    corpus = load_corpus(FIXTURE)
    report = evaluate_corpus(corpus)
    assert report["total"] == 32
    assert report["passed"] == 32
    ids = {row["id"] for row in corpus["cases"]}
    assert {"poison-first", "poison-middle", "poison-last", "checked-zero"} <= ids
    assert {"plan-40-clean", "plan-80-clean", "deploy-overlap", "redis-down-durable-fallback", "pubsub-reserved", "multi-dyno-multiplication"} <= ids


def test_capacity_is_aggregate_not_per_pool() -> None:
    row = _case("plan-40-clean")
    row["clients"][0]["max_connections"] = 40
    assert "CONSERVATIVE_DEMAND_EXCEEDS_PLAN" in evaluate_case(row)


@pytest.mark.parametrize("construction", ["per_request", "per_market", "per_call"])
def test_multiplying_constructors_are_refused(construction: str) -> None:
    row = _case("plan-40-clean")
    row["clients"][0]["construction"] = construction
    assert "POOL_CONSTRUCTION_MULTIPLIES" in evaluate_case(row)


def test_task_pool_requires_all_close_paths() -> None:
    assert evaluate_case(_case("cancelled-operation-safe")) == []
    assert evaluate_case(_case("cancelled-operation-leak")) == ["CANCELLATION_LEAKS_CONNECTION", "POOL_CLOSE_PATH_INCOMPLETE"]


def test_retry_must_stay_inside_declared_pool() -> None:
    assert evaluate_case(_case("tls-eof-bounded-retry")) == []
    assert evaluate_case(_case("retry-storm-new-pools")) == ["RETRY_ESCAPES_POOL_BUDGET"]


def test_cache_failure_never_overrides_durable_truth() -> None:
    assert evaluate_case(_case("redis-down-durable-fallback")) == []
    assert set(evaluate_case(_case("redis-down-false-green"))) == {"CACHE_BECOMES_DURABLE_AUTHORITY", "CACHE_FAILURE_FALSE_GREEN_OR_NO_DATA"}


@pytest.mark.parametrize("case_id", ["poison-first", "poison-middle", "poison-last"])
def test_poison_position_preserves_siblings(case_id: str) -> None:
    row = _case(case_id)
    row["poison"]["siblings_preserved"] = False
    assert "POISON_ERASES_SIBLING_CLIENTS" in evaluate_case(row)


def test_order_independent() -> None:
    corpus = load_corpus(FIXTURE)
    reversed_corpus = copy.deepcopy(corpus)
    reversed_corpus["cases"].reverse()
    assert evaluate_corpus(corpus) == evaluate_corpus(reversed_corpus)


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
