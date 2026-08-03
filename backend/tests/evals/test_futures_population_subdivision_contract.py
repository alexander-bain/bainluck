from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from scripts.evals.futures_population_subdivision_contract import evaluate_case, evaluate_corpus, load_corpus, materialize

FIXTURE = Path(__file__).parent / "fixtures" / "futures_population_subdivision_contract.json"


def _case(case_id: str) -> dict:
    corpus = load_corpus(FIXTURE)
    return materialize(corpus, next(row for row in corpus["cases"] if row["id"] == case_id))


def test_corpus_complete_and_matches_oracles() -> None:
    corpus = load_corpus(FIXTURE)
    report = evaluate_corpus(corpus)
    assert report["total"] == 44
    assert report["passed"] == 44
    ids = {row["id"] for row in corpus["cases"]}
    assert {"source-boundary", "date-boundary-collision", "id-boundary-collision", "representative-tie"} <= ids
    assert {"poison-first", "poison-middle", "poison-last", "checked-zero"} <= ids
    assert {"checkpoint-before-commit", "deploy-overlap-mixed", "publish-before-durable", "cleanup-authoritative-refused"} <= ids


@pytest.mark.parametrize("case_id", ["date-boundary-collision", "id-boundary-collision"])
def test_naive_chunk_boundaries_refused(case_id: str) -> None:
    assert "CROSS_CHUNK_PEER_SPLIT" in evaluate_case(_case(case_id))


def test_virtual_question_unit_is_equivalent() -> None:
    assert evaluate_case(_case("virtual-question-boundary")) == []


def test_every_output_dimension_is_compared() -> None:
    expectations = {
        "identity-drift": "OBSERVATION_IDENTITY_DRIFT",
        "representative-drift": "REPRESENTATIVE_DRIFT",
        "normalization-drift": "NORMALIZED_PROBABILITY_DRIFT",
        "cohort-drift": "COHORT_LABEL_DRIFT",
        "bucket-drift": "BUCKET_DRIFT",
        "census-drift": "CENSUS_DRIFT",
    }
    for case_id, code in expectations.items():
        assert code in evaluate_case(_case(case_id))


def test_tie_requires_frozen_authority() -> None:
    assert evaluate_case(_case("representative-tie")) == ["REPRESENTATIVE_TIE_UNSTABLE"]


def test_partial_never_publishes_or_greens() -> None:
    assert set(evaluate_case(_case("partial-published"))) == {"PARTIAL_GENERATION_GREEN", "PARTIAL_GENERATION_PUBLISHED"}


@pytest.mark.parametrize("case_id", ["poison-first", "poison-middle", "poison-last"])
def test_poison_keeps_siblings(case_id: str) -> None:
    row = _case(case_id)
    row["poison"]["siblings_preserved"] = False
    assert "POISON_ERASES_SIBLINGS" in evaluate_case(row)


def test_order_independent() -> None:
    corpus = load_corpus(FIXTURE)
    other = copy.deepcopy(corpus)
    other["cases"].reverse()
    assert evaluate_corpus(corpus) == evaluate_corpus(other)


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
