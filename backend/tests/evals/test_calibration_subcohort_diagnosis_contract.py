from __future__ import annotations

import copy
import json

from scripts.evals.calibration_subcohort_diagnosis_contract import (
    FIXTURE,
    evaluate,
    evaluate_corpus,
)


def corpus() -> dict:
    return json.loads(FIXTURE.read_text())


def case(case_id: str) -> dict:
    return copy.deepcopy(next(row for row in corpus()["cases"] if row["id"] == case_id))


def test_committed_corpus_matches_oracle() -> None:
    result = evaluate_corpus(corpus())
    assert result["total"] == 9
    assert result["passed"] == result["total"], result["cases"]


def test_cricket_signature_requires_both_sides_and_draw_evidence() -> None:
    assert evaluate(case("cricket-missing-third-outcome-both-sides")["input"])["verdict"] == "CONFIRMED"
    assert evaluate(case("cricket-only-moved-side-is-insufficient")["input"])["verdict"] == "REFUTED"
    assert evaluate(case("cricket-draw-capture-not-proven")["input"])["verdict"] == "REFUTED"


def test_entertainment_separates_structural_and_timing_claims() -> None:
    assert evaluate(case("entertainment-structural-defect-survives-liquidity")["input"])["verdict"] == "CONFIRMED"
    assert evaluate(case("entertainment-settlement-collapse-still-unknown")["input"])["verdict"] == "UNKNOWN"


def test_missing_reachability_cannot_emit_a_priority_ranking() -> None:
    assert evaluate(case("category-backfill-ranking-refused")["input"])["verdict"] == "UNKNOWN"
    assert evaluate(case("category-backfill-ranking-complete")["input"])["verdict"] == "RANK"
