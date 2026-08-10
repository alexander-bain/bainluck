"""Subcohort-diagnosis extension of canonical calibration_population_integrity.

This contract separates a confirmed mechanism from a large descriptive gap and
keeps missing independence, chronology, or reachability evidence UNKNOWN.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


FIXTURE = (
    Path(__file__).parents[2]
    / "tests/evals/fixtures/calibration_subcohort_diagnosis_contract.json"
)


def evaluate(case: dict[str, Any]) -> dict[str, Any]:
    kind = case.get("kind")
    reasons: list[str] = []

    if kind == "anomaly":
        if not case.get("published_population_correspondence"):
            reasons.append("PUBLISHED_POPULATION_MISMATCH")
        if not case.get("exact_independent_question_count"):
            reasons.append("INDEPENDENCE_APPROXIMATE")
        if not case.get("comparison_family_complete"):
            reasons.append("COMPARISON_FAMILY_INCOMPLETE")
        if case.get("multiplicity_adjusted_p") is None:
            reasons.append("MULTIPLICITY_UNTESTED")
        verdict = "CONFIRMED" if not reasons and case["multiplicity_adjusted_p"] <= 0.05 else "UNKNOWN"

    elif kind == "mechanism":
        sides = case.get("sides") or []
        if {row.get("price_moved") for row in sides} != {False, True}:
            reasons.append("MOVED_SIDE_CONTROL_MISSING")
        if any(row.get("multiwinner_markets", 0) < 30 for row in sides):
            reasons.append("INDEPENDENT_SAMPLE_TOO_SMALL")
        if any(row.get("multiwinner_gap_pp", 0) < 20 for row in sides):
            reasons.append("SIGNATURE_NOT_REPLICATED")
        if any(abs(row.get("coherent_gap_pp", 999)) >= row.get("multiwinner_gap_pp", 0) for row in sides):
            reasons.append("COHERENT_CONTROL_NOT_SEPARATED")
        if not case.get("draw_absent_on_every_multiwinner"):
            reasons.append("MISSING_THIRD_OUTCOME_NOT_IDENTIFIED")
        verdict = "CONFIRMED" if not reasons else "REFUTED"

    elif kind == "rival":
        if not case.get("structural_relation_invalid"):
            reasons.append("STRUCTURAL_DEFECT_UNPROVEN")
        strata = case.get("liquidity_strata_gap_pp") or {}
        if set(strata) != {"null", "zero", "positive"}:
            reasons.append("LIQUIDITY_RIVAL_INCOMPLETE")
        elif any(abs(value) < 15 for value in strata.values()):
            reasons.append("ERROR_DOES_NOT_SURVIVE_LIQUIDITY_STRATA")
        if case.get("claims_timing_mechanism") and not case.get("quote_chronology_present"):
            reasons.append("TIMING_RIVAL_UNTESTABLE")
        verdict = "CONFIRMED" if not reasons else "UNKNOWN"

    elif kind == "backfill_priority":
        if case.get("reachability_status") != "complete":
            reasons.append("CATEGORY_REACHABILITY_INCOMPLETE")
        if not case.get("recoverable_n_by_category"):
            reasons.append("RECOVERABLE_VALUE_MISSING")
        if not case.get("independent_questions_by_category"):
            reasons.append("CATEGORY_INDEPENDENCE_MISSING")
        verdict = "RANK" if not reasons else "UNKNOWN"

    else:
        verdict = "UNKNOWN"
        reasons.append("DIAGNOSIS_KIND_UNKNOWN")

    return {"verdict": verdict, "reasons": sorted(reasons)}


def evaluate_corpus(payload: dict[str, Any]) -> dict[str, Any]:
    rows = []
    for case in payload["cases"]:
        actual = evaluate(case["input"])
        rows.append({"id": case["id"], "actual": actual, "ok": actual == case["expected"]})
    return {"total": len(rows), "passed": sum(row["ok"] for row in rows), "cases": rows}


def main() -> int:
    result = evaluate_corpus(json.loads(FIXTURE.read_text()))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["passed"] == result["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
