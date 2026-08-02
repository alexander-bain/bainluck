from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from scripts.evals.calibration_version_rollover_contract import evaluate_case, evaluate_corpus, load_corpus

FIXTURE = Path(__file__).parent / "fixtures" / "calibration_version_rollover_contract.json"


def _case(case_id: str) -> dict:
    return copy.deepcopy(next(row for row in load_corpus(FIXTURE)["cases"] if row["id"] == case_id))


def test_committed_corpus_is_complete_and_matches_oracles() -> None:
    corpus = load_corpus(FIXTURE)
    report = evaluate_corpus(corpus)
    assert report["total"] == 26
    assert report["passed"] == 26
    ids = {row["id"] for row in corpus["cases"]}
    assert {"prepare-publish-deploy", "deploy-before-candidate", "rollback-prior-code"} <= ids
    assert {"poison-first", "poison-middle", "poison-last", "checked-zero"} <= ids


def test_deploy_before_build_serves_previous_only_as_explicit_degraded() -> None:
    row = _case("deploy-before-candidate")
    row["result"]["degraded"] = False
    assert "PREVIOUS_FALLBACK_NOT_EXPLICIT" in evaluate_case(row)


def test_previous_fallback_cannot_seed_the_new_version() -> None:
    row = _case("previous-complete-bounded")
    row["result"]["may_seed_current"] = True
    assert "PREVIOUS_FALLBACK_SEEDS_CURRENT" in evaluate_case(row)


@pytest.mark.parametrize("case_id", ["previous-incomplete-refused", "previous-invalid-refused", "previous-expired-refused", "future-refused"])
def test_untrustworthy_cross_version_artifacts_remain_unavailable(case_id: str) -> None:
    assert evaluate_case(_case(case_id)) == []


def test_volatile_generation_without_durable_backing_cannot_win() -> None:
    row = _case("torn-redis-ahead")
    assert evaluate_case(row) == []
    row["result"]["selected"] = "r-v2-300"
    assert "AUTHORITATIVE_SELECTION_FALSE" in evaluate_case(row)


def test_publication_is_durable_first_and_gate_respecting() -> None:
    assert evaluate_case(_case("volatile-before-durable-refused")) == ["VOLATILE_BEFORE_DURABLE"]
    row = _case("publish-gate-refusal-preserves-prior")
    row["publication"]["published"] = True
    assert "GATE_REFUSAL_PUBLISHED" in evaluate_case(row)


def test_population_unit_and_duration_are_not_guessed() -> None:
    assert evaluate_case(_case("population-unit-unruled")) == [
        "COMPATIBILITY_DURATION_NEEDS_RULING", "POPULATION_UNIT_NEEDS_RULING"
    ]


def test_current_client_version_divergences_are_executable() -> None:
    assert evaluate_case(_case("native-version-divergence")) == ["NATIVE_EXPECTED_VERSION_DIVERGES"]
    assert evaluate_case(_case("web-accepts-incompatible")) == ["WEB_ACCEPTS_INCOMPATIBLE"]


@pytest.mark.parametrize("case_id", ["poison-first", "poison-middle", "poison-last"])
def test_poison_order_preserves_healthy_candidates(case_id: str) -> None:
    row = _case(case_id)
    row["poison"]["healthy_candidates_survive"] = False
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
