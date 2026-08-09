"""Authority for observation-vs-independent-question calibration evidence."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FIXTURES = ROOT / "tests/evals/fixtures/calibration_independence_disclosure_contract.json"


def evaluate(case: dict[str, Any]) -> dict[str, Any]:
    rows = case["rows"]
    errors: list[str] = []
    observations = len(rows)
    questions = {row.get("question_id") for row in rows if row.get("question_id")}
    unknown_identity = sum(1 for row in rows if not row.get("question_id"))
    by_cohort: dict[str, dict[str, int]] = defaultdict(lambda: {"observations": 0, "questions": 0})
    cohort_questions: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        cohort = str(row.get("cohort") or "unknown")
        by_cohort[cohort]["observations"] += 1
        if row.get("question_id"):
            cohort_questions[cohort].add(str(row["question_id"]))
    for cohort, ids in cohort_questions.items():
        by_cohort[cohort]["questions"] = len(ids)

    declared = case["declared"]
    if declared.get("observations") != observations:
        errors.append("OBSERVATION_COUNT_DRIFT")
    if unknown_identity:
        errors.append("QUESTION_IDENTITY_INCOMPLETE")
    elif declared.get("independent_questions") != len(questions):
        errors.append("QUESTION_COUNT_DRIFT")
    if not declared.get("cohort_question_counts"):
        errors.append("COHORT_INDEPENDENCE_HIDDEN")
    if case.get("consequential_claim") and not declared.get("clustered_uncertainty"):
        errors.append("CLUSTERED_UNCERTAINTY_MISSING")
    if declared.get("confidence_unit") == "outcome" and len(questions) < observations:
        errors.append("CORRELATED_ROWS_TREATED_INDEPENDENT")
    if case.get("surface_shows_observations") and not case.get("surface_shows_questions"):
        errors.append("PUBLIC_INDEPENDENCE_DISCLOSURE_MISSING")

    return {
        "verdict": "refuse" if errors else "allow",
        "errors": sorted(set(errors)),
        "observations": observations,
        "independent_questions": None if unknown_identity else len(questions),
        "unknown_identity_rows": unknown_identity,
        "cohorts": {key: by_cohort[key] for key in sorted(by_cohort)},
    }


def evaluate_pack(pack: dict[str, Any]) -> dict[str, Any]:
    results = []
    passed = 0
    for case in pack["cases"]:
        actual = evaluate(case["input"])
        mismatches = [] if actual == case["expected"] else ["EXPECTED_RESULT_MISMATCH"]
        passed += not mismatches
        results.append({"id": case["id"], "actual": actual, "expected_mismatches": mismatches})
    return {"cases": len(results), "passed": passed, "results": results}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixtures", type=Path, default=DEFAULT_FIXTURES)
    args = parser.parse_args()
    result = evaluate_pack(json.loads(args.fixtures.read_text()))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["passed"] == result["cases"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
