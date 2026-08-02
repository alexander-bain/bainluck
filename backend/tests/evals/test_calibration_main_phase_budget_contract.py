from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from scripts.evals.calibration_main_phase_budget_contract import evaluate_case, evaluate_corpus, load_corpus, materialize

FIXTURE = Path(__file__).parent / "fixtures" / "calibration_main_phase_budget_contract.json"


def _case(case_id: str) -> dict:
    corpus = load_corpus(FIXTURE)
    raw = next(row for row in corpus["cases"] if row["id"] == case_id)
    return materialize(corpus, raw)


def test_committed_corpus_is_complete_and_matches_oracles() -> None:
    corpus = load_corpus(FIXTURE)
    report = evaluate_corpus(corpus)
    assert report["total"] == 31
    assert report["passed"] == 31
    ids = {row["id"] for row in corpus["cases"]}
    assert {"first-phase-timeout", "middle-phase-timeout", "final-phase-timeout"} <= ids
    assert {"poison-first", "poison-middle", "poison-last", "checked-zero"} <= ids


def test_declared_phase_budgets_leave_cleanup_margin() -> None:
    row = _case("clean-complete-publish")
    row["plan"]["phases"][0]["budget_ms"] = row["plan"]["soft_limit_ms"]
    assert "DECLARED_BUDGETS_EXHAUST_SOFT_LIMIT" in evaluate_case(row)


def test_statement_timeout_sits_inside_phase_not_at_task_ceiling() -> None:
    assert evaluate_case(_case("statement-timeout-equals-phase-refused")) == ["STATEMENT_TIMEOUT_NOT_INSIDE_PHASE"]


@pytest.mark.parametrize("case_id", ["first-phase-timeout", "middle-phase-timeout", "final-phase-timeout"])
def test_timeouts_preserve_prior_and_never_publish(case_id: str) -> None:
    row = _case(case_id)
    assert evaluate_case(row) == []
    row["run"]["published"] = True
    assert "INCOMPLETE_RUN_PUBLISHED" in evaluate_case(row)


def test_checkpoint_advances_only_after_commit_and_successful_checkpoint_write() -> None:
    assert "CHECKPOINT_BEFORE_COMMIT" in evaluate_case(_case("checkpoint-before-commit-refused"))
    assert "CHECKPOINT_ADVANCED_AFTER_WRITE_FAILURE" in evaluate_case(_case("checkpoint-write-failure-refused"))


def test_population_version_change_invalidates_checkpoint() -> None:
    assert evaluate_case(_case("population-version-change")) == []
    assert evaluate_case(_case("version-reuse-refused")) == ["CHECKPOINT_VERSION_REUSED"]


def test_durable_success_allows_redis_failure_but_not_reverse() -> None:
    assert evaluate_case(_case("redis-failure-durable-success")) == []
    row = _case("durable-failure")
    row["run"].update({"published": True, "volatile": "ok"})
    errors = evaluate_case(row)
    assert {"INCOMPLETE_RUN_PUBLISHED", "PUBLISHED_WITHOUT_DURABLE", "VOLATILE_AHEAD_OF_DURABLE"} <= set(errors)


def test_health_is_derived_from_artifact_not_invocation() -> None:
    assert evaluate_case(_case("stale-artifact-health-refused")) == ["STALE_ARTIFACT_GREEN"]
    assert evaluate_case(_case("invocation-only-health-refused")) == ["INVOCATION_ONLY_GREEN"]


@pytest.mark.parametrize("case_id", ["poison-first", "poison-middle", "poison-last"])
def test_poison_order_preserves_healthy_progress(case_id: str) -> None:
    row = _case(case_id)
    row["poison"]["healthy_progress_preserved"] = False
    assert "POISON_ERASES_HEALTHY_PROGRESS" in evaluate_case(row)


def test_multi_beat_progress_is_monotonic_and_publishes_only_at_completion() -> None:
    row = _case("partial-across-beats")
    assert evaluate_case(row) == []
    row["sequence"]["cursor_after"] = [10, 9, 30]
    assert "CURSOR_NOT_MONOTONIC" in evaluate_case(row)


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
