"""Closure oracle for event positive/stale/negative cache publication races."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FIXTURES = ROOT / "tests/evals/fixtures/event_cache_repair_closure_contract.json"


def evaluate(case: dict) -> dict:
    errors: list[str] = []
    warnings: list[str] = []
    positive = bool(case.get("positive"))
    stale = bool(case.get("stale"))
    negative = bool(case.get("negative"))
    build = case.get("build")

    if positive:
        response = "positive"
    elif negative:
        response = "404"
    elif build == "success":
        response = "live"
    elif build in {"none", "exception"} and stale:
        if build == "none" and not case.get("none_reads_stale"):
            response = "404"
            errors.append("NONE_BYPASSES_LAST_GOOD")
        else:
            response = "stale"
    elif build == "none":
        response = "404"
    elif build == "exception":
        response = "error"
    else:
        raise ValueError(build)

    writes_negative = build == "none" and response == "404" and not positive and not negative
    if writes_negative and (stale or case.get("concurrent_positive_before_negative")):
        if not case.get("negative_rechecks_positive_and_stale"):
            errors.append("NEGATIVE_PUBLISHED_OVER_POSITIVE_EVIDENCE")
    if case.get("concurrent_negative_before_success") and build == "success":
        if not case.get("success_clears_negative"):
            errors.append("SUCCESS_LEAVES_NEGATIVE")
    if case.get("cache_write_partial") and not case.get("positive_precedes_negative_on_read"):
        errors.append("NEGATIVE_SHADOWS_POSITIVE")
    if case.get("negative_ttl_s", 60) > case.get("positive_ttl_s", 60):
        warnings.append("NEGATIVE_OUTLIVES_POSITIVE")

    return {
        "verdict": "refuse" if errors else ("watch" if warnings else "accept"),
        "response": response,
        "errors": sorted(set(errors)),
        "warnings": sorted(set(warnings)),
    }


def evaluate_pack(pack: dict) -> dict:
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
