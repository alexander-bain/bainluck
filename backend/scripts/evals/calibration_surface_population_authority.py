"""Cross-surface authority for calibration population counts and freshness."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FIXTURES = ROOT / "tests/evals/fixtures/calibration_surface_population_authority.json"


def decide(case: dict[str, Any]) -> dict[str, Any]:
    payload = case["payload"]
    surface = case["surface"]
    errors: list[str] = []

    plotted = payload.get("total_outcomes")
    census = payload.get("coverage_census")
    coverage = None
    census_complete = False
    if isinstance(census, dict):
        units = census.get("units") if isinstance(census.get("units"), dict) else {}
        covered = units.get("outcomes_with_calibration_coverage", {})
        coverage = covered.get("value") if isinstance(covered, dict) else None
        census_complete = (
            census.get("status") == "complete"
            and census.get("population_version") == payload.get("population_version")
            and isinstance(coverage, int) and not isinstance(coverage, bool) and coverage >= 0
            and census.get("invariants_ok") is True
        )

    stale = payload.get("cache_status") == "stale"
    curve_present = bool(payload.get("bucket_count", 0))
    rendered = case["rendered"]

    if rendered.get("plotted_value") != plotted:
        errors.append("PLOTTED_VALUE_DRIFT")
    if rendered.get("plotted_label") != "published curve observations":
        errors.append("PLOTTED_UNIT_MISLABELLED")

    if census_complete:
        if rendered.get("coverage_value") != coverage:
            errors.append("COMPLETE_COVERAGE_HIDDEN_OR_WRONG")
        if rendered.get("coverage_label") != "outcomes with calibration-price coverage":
            errors.append("COVERAGE_UNIT_MISLABELLED")
    elif rendered.get("coverage_value") is not None:
        errors.append("INCOMPLETE_COVERAGE_RENDERED")

    if stale and (rendered.get("shows_numbers") or surface == "about"):
        if not rendered.get("stale_disclosed"):
            errors.append("STALE_NUMBERS_PRESENTED_CURRENT")
    if not curve_present and rendered.get("curve_metrics"):
        errors.append("EMPTY_CURVE_HAS_METRICS")
    if not curve_present and census_complete and rendered.get("coverage_value") != coverage:
        errors.append("EMPTY_CURVE_ERASES_CENSUS")

    return {
        "verdict": "refuse" if errors else "allow",
        "errors": sorted(set(errors)),
        "coverage_authoritative": census_complete,
        "curve_present": curve_present,
    }


def evaluate_pack(pack: dict[str, Any]) -> dict[str, Any]:
    results = []
    passed = 0
    for case in pack["cases"]:
        actual = decide(case)
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
