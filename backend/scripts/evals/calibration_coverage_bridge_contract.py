"""Dependency-free evaluator for the Queue 300C calibration coverage-bridge corpus.

The corpus pins the ONE thing the census must never get wrong: the ~653K
published curve observations and the ~1.28M outcomes with calibration-price
coverage are DIFFERENT UNITS, and the only honest way to show both is an
additive bridge whose rungs are a partition of the coverage population.

A case declares the counts a build measured plus the labels it intends to
publish; ``evaluate_case`` returns stable refusal codes. Empty means the census
that case describes is publishable.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from app.utils.calibration_coverage_bridge import (
    COVERAGE_BRIDGE_SCHEMA_VERSION,
    EXCLUSION_RUNGS,
    PLOTTED_RUNG,
    RUNG_KEYS,
    UNIT_CURVE_OBSERVATION,
    UNIT_FUTURES_OUTCOME,
    build_coverage_census,
    census_is_complete,
    unavailable_census,
)

FIXTURE = (
    Path(__file__).parents[2]
    / "tests"
    / "evals"
    / "fixtures"
    / "calibration_coverage_bridge_contract.json"
)

SCHEMA_VERSION = "calibration-coverage-bridge-contract/v1"


def load_corpus(path: str | Path = FIXTURE) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("SCHEMA_VERSION_INVALID")
    cases = payload.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("CASES_REQUIRED")
    ids = [row.get("id") for row in cases if isinstance(row, dict)]
    if len(ids) != len(cases) or any(not isinstance(v, str) or not v for v in ids):
        raise ValueError("CASE_ID_REQUIRED")
    if len(ids) != len(set(ids)):
        raise ValueError("CASE_ID_DUPLICATE")
    return payload


def build_from_case(row: dict[str, Any]) -> dict[str, Any]:
    """Produce the census object this case describes, via the shipped builder."""
    measured = row.get("measured") or {}
    if row.get("tier_has_no_census"):
        return unavailable_census(
            measured.get("unavailable_reason") or "payload_predates_census",
            population_version=measured.get("population_version"),
            generation=measured.get("generation"),
        )
    # A rung the case does not declare is UNMEASURED, not zero — the corpus
    # exercises that distinction directly.
    declared_rungs = measured.get("rungs") or {}
    return build_coverage_census(
        rung_counts={key: declared_rungs.get(key) for key in RUNG_KEYS},
        sportsbook_curve_legs=measured.get("sportsbook_curve_legs"),
        published_curve_observations=measured.get("published_curve_observations"),
        published_outcomes_crosscheck=measured.get("published_outcomes_crosscheck"),
        population_version=measured.get("population_version") or "unset",
        generation=measured.get("generation"),
        with_terminal_calibration_price=measured.get("with_terminal_calibration_price"),
    )


def evaluate_case(row: dict[str, Any]) -> list[str]:
    """Return stable refusal codes. Empty means the census is publishable."""
    codes: list[str] = []
    census = build_from_case(row)
    declared = row.get("declares") or {}
    measured = row.get("measured") or {}

    if census.get("schema_version") != COVERAGE_BRIDGE_SCHEMA_VERSION:
        codes.append("SCHEMA_VERSION_UNPINNED")

    # 1. The rungs must be a PARTITION of the coverage population. Every rung is
    #    reported (checked-zero included) and the exclusion rungs plus the
    #    plotted rung must equal the coverage headline exactly.
    rungs = {cell["key"]: cell for cell in census["coverage_bridge"]["rungs"]}
    if tuple(rungs) != RUNG_KEYS:
        codes.append("RUNG_SET_INCOMPLETE")
    coverage = census["units"]["outcomes_with_calibration_coverage"]["value"]
    plotted = census["observation_bridge"]["futures_outcomes_plotted"]
    values = [rungs[key]["outcomes"] for key in RUNG_KEYS if key in rungs]
    if coverage is not None and all(v is not None for v in values):
        if sum(values) != coverage:
            codes.append("COVERAGE_BRIDGE_RESIDUAL")
        exclusions = sum(rungs[k]["outcomes"] for k in EXCLUSION_RUNGS)
        terminal = rungs[PLOTTED_RUNG]["outcomes"]
        if plotted != terminal or terminal + exclusions != coverage:
            codes.append("ADDITIVE_BRIDGE_BROKEN")

    # 2. UNKNOWN never becomes zero, and a measured empty rung is a CHECKED zero.
    for key in RUNG_KEYS:
        cell = rungs.get(key) or {}
        if cell.get("outcomes") is None and cell.get("checked") is not False:
            codes.append("UNKNOWN_NOT_MARKED")
        if cell.get("outcomes") == 0 and cell.get("checked") is not True:
            codes.append("CHECKED_ZERO_NOT_MARKED")

    # 3. The two units are never interchanged. The published headline is a curve
    #    observation count; coverage is a futures-outcome count.
    units = census["units"]
    if units["published_curve_observations"]["unit"] != UNIT_CURVE_OBSERVATION:
        codes.append("OBSERVATION_UNIT_WRONG")
    if units["outcomes_with_calibration_coverage"]["unit"] != UNIT_FUTURES_OUTCOME:
        codes.append("COVERAGE_UNIT_WRONG")
    if declared.get("coverage_presented_as_plotted"):
        codes.append("COVERAGE_LABELLED_AS_PLOTTED")
    if declared.get("headline_unit") not in (None, UNIT_CURVE_OBSERVATION):
        codes.append("HEADLINE_UNIT_NOT_OBSERVATIONS")

    # 4. Sportsbook treatment. Curve observations that are not futures outcomes
    #    must be counted as their own leg, never folded into coverage.
    # An explicitly unavailable census has nothing to reconcile; its honesty is
    # checked below instead. Only a census that CLAIMS numbers must add up.
    if census.get("status") != "unavailable" and not census["observation_bridge"]["reconciles"]:
        codes.append("OBSERVATION_BRIDGE_BROKEN")

    # 5. The hinge is counted twice, by two paths, and must agree.
    if "PLOTTED_HINGE_DIVERGES" in census["invariants"]["violations"]:
        codes.append("PLOTTED_HINGE_DIVERGES")
    if "PLOTTED_HINGE_UNCHECKED" in census["invariants"]["violations"]:
        codes.append("PLOTTED_HINGE_UNCHECKED")

    # 6. Generations are never mixed: a census stapled to a payload built by a
    #    different generation or population version is two halves of two bridges.
    payload_gen = declared.get("payload_generation")
    if payload_gen is not None and census.get("generation") != payload_gen:
        codes.append("MIXED_GENERATION")
    payload_version = declared.get("payload_population_version")
    if payload_version is not None and census.get("population_version") != payload_version:
        codes.append("MIXED_POPULATION_VERSION")

    # 7. An incomplete census may never be presented as complete, and a tier with
    #    no census must say so rather than omit the key.
    if declared.get("published_as_complete") and not census_is_complete(census):
        codes.append("INCOMPLETE_PUBLISHED_AS_COMPLETE")
    if row.get("tier_has_no_census") and census.get("status") != "unavailable":
        codes.append("ABSENT_CENSUS_NOT_MARKED")

    # 8. The curve itself is untouched. This census is additive only.
    if declared.get("changed_plotted_population"):
        codes.append("PLOTTED_POPULATION_CHANGED")
    if declared.get("bumped_population_version"):
        codes.append("UNAUTHORIZED_VERSION_BUMP")

    if measured.get("expect_status") and census.get("status") != measured["expect_status"]:
        codes.append("STATUS_UNEXPECTED")

    return sorted(set(codes))


def evaluate_corpus(corpus: dict[str, Any]) -> dict[str, Any]:
    rows = []
    passed = 0
    for case in corpus["cases"]:
        actual = evaluate_case(case)
        expected = sorted(set(case.get("expected_refusals") or []))
        ok = actual == expected
        passed += 1 if ok else 0
        rows.append({"id": case["id"], "ok": ok, "actual": actual, "expected": expected})
    return {"total": len(rows), "passed": passed, "cases": rows}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", default=str(FIXTURE))
    args = parser.parse_args()
    report = evaluate_corpus(load_corpus(args.fixture))
    print(json.dumps(report, indent=2))
    return 0 if report["passed"] == report["total"] else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
