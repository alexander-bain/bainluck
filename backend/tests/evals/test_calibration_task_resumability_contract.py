from __future__ import annotations

import copy
from pathlib import Path

import pytest

from scripts.evals.calibration_task_resumability_contract import evaluate_case, evaluate_corpus, load_corpus

FIXTURE = Path(__file__).parent / "fixtures" / "calibration_task_resumability_contract.json"


def _case(suffix: str, task: str = "calibration_prices") -> dict:
    return copy.deepcopy(next(x for x in load_corpus(FIXTURE)["cases"] if x["id"] == f"{task}-{suffix}"))


def test_corpus_has_full_two_task_matrix_and_matches_oracles() -> None:
    report = evaluate_corpus(load_corpus(FIXTURE))
    assert report["total"] == 48 and report["passed"] == 48


@pytest.mark.parametrize("task", ["calibration_prices", "coverage_metrics"])
def test_checkpoint_never_advances_before_commit(task: str) -> None:
    row = _case("first-chunk", task)
    row["transaction"]["committed"] = False
    assert "CHECKPOINT_AHEAD_OF_COMMIT" in evaluate_case(row)


@pytest.mark.parametrize("task", ["calibration_prices", "coverage_metrics"])
def test_partial_and_interrupted_work_never_publish_or_green(task: str) -> None:
    row = _case("soft-after-commit", task)
    row["output"]["published"] = True
    row["health"]["verdict"] = "GREEN"
    assert {"PARTIAL_OUTPUT_PUBLISHED", "FALSE_GREEN"} <= set(evaluate_case(row))


def test_version_change_requires_invalidation() -> None:
    row = _case("version-change")
    row["version_action"] = "reuse"
    assert "STALE_CHECKPOINT_REUSED" in evaluate_case(row)


def test_overlap_non_owner_cannot_mutate() -> None:
    row = _case("overlapping-run")
    row["transaction"]["committed"] = True
    assert "NON_OWNER_MUTATED" in evaluate_case(row)


@pytest.mark.parametrize("position", ["first", "middle", "last"])
def test_poison_order_preserves_siblings(position: str) -> None:
    row = _case(f"poison-{position}")
    row["healthy_siblings_survive"] = False
    assert "POISON_WIPES_SIBLINGS" in evaluate_case(row)


def test_task_metric_loss_and_checked_zero_are_unknown() -> None:
    row = _case("metric-loss")
    row["health"]["verdict"] = "GREEN"
    assert "METRIC_LOSS_NOT_UNKNOWN" in evaluate_case(row)
    row = _case("checked-zero")
    row["health"]["verdict"] = "GREEN"
    assert "FALSE_GREEN" in evaluate_case(row)


def test_case_order_is_irrelevant() -> None:
    corpus = load_corpus(FIXTURE)
    reversed_corpus = copy.deepcopy(corpus); reversed_corpus["cases"].reverse()
    assert evaluate_corpus(corpus) == evaluate_corpus(reversed_corpus)
