"""Independent oracle for recomposing chunked calibration coverage counts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FIXTURES = ROOT / "tests/evals/fixtures/chunked_coverage_recomposition_contract.json"


def evaluate(case: dict[str, Any]) -> dict[str, Any]:
    planned = case["planned_chunks"]
    rows = case.get("chunks", [])
    errors: list[str] = []
    warnings: list[str] = []

    by_id: dict[str, dict[str, Any]] = {}
    for row in rows:
        chunk_id = row.get("id")
        if chunk_id in by_id:
            errors.append("DUPLICATE_CHUNK")
        else:
            by_id[chunk_id] = row
    if set(by_id) != set(planned):
        errors.append("INCOMPLETE_CHUNK_SET")

    columns = case["columns"]
    totals: dict[str, int | None] = {}
    for column in columns:
        values = []
        complete = True
        for chunk_id in planned:
            row = by_id.get(chunk_id)
            if row is None or column not in row.get("census", {}) or row["census"][column] is None:
                complete = False
                continue
            value = row["census"][column]
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                errors.append("INVALID_CENSUS_VALUE")
                complete = False
                continue
            values.append(value)
        totals[column] = sum(values) if complete else None

    global_row = case.get("global", {})
    for column, value in global_row.items():
        if column not in totals:
            errors.append("UNDECLARED_GLOBAL_COLUMN")
        elif totals[column] is None:
            # Unknown chunk contribution cannot become known through a global addend.
            continue
        elif isinstance(value, bool) or not isinstance(value, int) or value < 0:
            errors.append("INVALID_GLOBAL_VALUE")
        else:
            totals[column] += value

    plotted_rows = sum(int(row.get("plotted_rows", 0)) for row in rows)
    if plotted_rows == 0 and any(value is not None and value > 0 for value in totals.values()):
        warnings.append("CENSUS_WITH_EMPTY_CURVE")

    expected_total = case.get("expected_population_total")
    measured_total = totals.get("coverage_total")
    if expected_total is not None and measured_total is not None:
        ratio = measured_total / expected_total if expected_total else None
        if ratio is not None and ratio >= case.get("inflation_ratio", 2):
            errors.append("CHUNK_MULTIPLICATION")

    return {
        "verdict": "refuse" if errors else ("publish_empty_curve_with_census" if warnings else "publish"),
        "errors": sorted(set(errors)),
        "warnings": sorted(set(warnings)),
        "totals": totals,
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
