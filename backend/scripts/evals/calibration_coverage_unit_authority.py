"""Dependency-free C128 evaluator for calibration count and label authority."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "calibration-coverage-unit-authority/v1"
RULING = "terminal_price_supporting_census"

UNITS = {
    "outcomes_with_terminal_calibration_price": {
        "unit": "futures_outcome",
        "predicate": (
            "resolved outcome AND opening_probability > 0 AND opening_probability < 1 "
            "AND calibration_probability IS NOT NULL"
        ),
        "label": "outcomes with a terminal calibration price",
    },
    "outcomes_with_usable_curve_price": {
        "unit": "futures_outcome",
        "predicate": (
            "resolved outcome AND opening_probability > 0 AND opening_probability < 1; "
            "curve price = COALESCE(calibration_probability, opening_probability)"
        ),
        "label": "outcomes with a usable curve price (including opening fallback)",
    },
    "published_curve_observations": {
        "unit": "curve_observation",
        "predicate": (
            "rows emitted by the complete published futures and sportsbook curve legs"
        ),
        "label": "published curve observations",
    },
}

FIXTURE = (
    Path(__file__).parents[2]
    / "tests"
    / "evals"
    / "fixtures"
    / "calibration_coverage_unit_authority.json"
)


def load_corpus(path: str | Path = FIXTURE) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("SCHEMA_VERSION_INVALID")
    cases = payload.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("CASES_REQUIRED")
    ids = [row.get("id") for row in cases if isinstance(row, dict)]
    if len(ids) != len(cases) or len(ids) != len(set(ids)):
        raise ValueError("CASE_IDS_INVALID")
    return payload


def evaluate_case(row: dict[str, Any]) -> list[str]:
    """Return stable refusal codes; empty means the proposed rendering is honest."""
    codes: list[str] = []
    fields = row.get("fields") or []
    payload_generation = row.get("payload_generation")
    payload_version = row.get("payload_population_version")

    if row.get("changes_population_methodology"):
        codes.append("LABEL_CHANGE_MAY_NOT_CHANGE_POPULATION")
    if row.get("bumps_population_version"):
        codes.append("LABEL_CHANGE_MAY_NOT_BUMP_VERSION")

    for field in fields:
        key = field.get("key")
        value = field.get("value")
        authority = UNITS.get(key)
        if authority is None:
            codes.append("UNKNOWN_MACHINE_UNIT")
            continue
        if field.get("unit") != authority["unit"]:
            codes.append("UNIT_MISMATCH")
        if field.get("predicate") != authority["predicate"]:
            codes.append("PREDICATE_MISMATCH")
        if value is None:
            if field.get("availability") != "unavailable":
                codes.append("MISSING_MUST_RENDER_UNAVAILABLE")
        elif isinstance(value, bool) or not isinstance(value, int) or value < 0:
            codes.append("COUNT_INVALID")
        if field.get("generation") != payload_generation:
            codes.append("MIXED_GENERATION")
        if field.get("population_version") != payload_version:
            codes.append("MIXED_POPULATION_VERSION")
        if field.get("headline") and key != "published_curve_observations":
            codes.append("HEADLINE_MUST_BE_PUBLISHED_OBSERVATIONS")

        label = field.get("label")
        if label == "calibration coverage":
            codes.append("AMBIGUOUS_COVERAGE_LABEL")
        if label != authority["label"]:
            codes.append("LABEL_DOES_NOT_MATCH_UNIT")

    keys = [field.get("key") for field in fields]
    if row.get("selected_option") == RULING:
        if "outcomes_with_terminal_calibration_price" not in keys:
            codes.append("RULED_SUPPORTING_CENSUS_MISSING")
        if row.get("supporting_key") != "outcomes_with_terminal_calibration_price":
            codes.append("RULED_SUPPORTING_CENSUS_WRONG")
    elif row.get("selected_option") in {
        "usable_price_supporting_census",
        "both_explicitly_labelled",
    }:
        codes.append("OPTION_NOT_SELECTED_BY_ALEX")

    return sorted(set(codes))


def evaluate_corpus(corpus: dict[str, Any]) -> dict[str, Any]:
    rows = []
    for case in corpus["cases"]:
        actual = evaluate_case(case)
        expected = sorted(case.get("expected_refusals") or [])
        rows.append({"id": case["id"], "ok": actual == expected, "actual": actual})
    return {"total": len(rows), "passed": sum(row["ok"] for row in rows), "cases": rows}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", default=str(FIXTURE))
    args = parser.parse_args()
    report = evaluate_corpus(load_corpus(args.fixture))
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["passed"] == report["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
