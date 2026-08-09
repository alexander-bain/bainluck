"""Cross-surface contract for desktop/mobile search dropdown behavior."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FIXTURES = ROOT / "tests/evals/fixtures/search_dropdown_cross_surface_contract.json"


def _strong_team(row: dict[str, Any], query: str) -> bool:
    if row.get("type") != "team":
        return False
    q = query.strip().lower()
    name = str(row.get("text") or "").lower()
    abbr = str(row.get("abbreviation") or "").lower()
    return bool(q and (name.startswith(q) or q.startswith(name) or (len(q) >= 3 and q in name) or abbr == q))


def rank(rows: list[dict[str, Any]], query: str, enabled: bool) -> list[str]:
    if not enabled:
        return [row["id"] for row in rows]
    promoted = [row for row in rows if _strong_team(row, query)]
    rest = [row for row in rows if not _strong_team(row, query)]
    return [row["id"] for row in promoted + rest]


def evaluate(case: dict[str, Any]) -> dict[str, Any]:
    rows = case["suggestions"]
    desktop = rank(rows, case["query"], case["desktop"]["team_promotion"])
    mobile = rank(rows, case["query"], case["mobile"]["team_promotion"])
    errors: list[str] = []
    if desktop != mobile:
        errors.append("ORDER_PARITY_DRIFT")
    if sorted(desktop) != sorted(mobile):
        errors.append("MEMBERSHIP_PARITY_DRIFT")
    if case["desktop"].get("click_analytics") != case["mobile"].get("click_analytics"):
        errors.append("CLICK_ANALYTICS_PARITY_DRIFT")
    if case["desktop"].get("answer_analytics") != case["mobile"].get("answer_analytics"):
        errors.append("ANSWER_ANALYTICS_PARITY_DRIFT")
    if case["desktop"].get("navigation") != case["mobile"].get("navigation"):
        errors.append("NAVIGATION_PARITY_DRIFT")
    if not case["mobile"].get("option_semantics"):
        errors.append("MOBILE_OPTIONS_NOT_EXPOSED")
    if case.get("invalid_probability") and not case["desktop"].get("invalid_probability_withheld"):
        errors.append("INVALID_PROBABILITY_RENDERED")
    if case.get("invalid_time") and not case["desktop"].get("invalid_time_withheld"):
        errors.append("INVALID_TIME_RENDERED")
    return {
        "verdict": "refuse" if errors else "accept",
        "errors": sorted(set(errors)),
        "desktop_order": desktop,
        "mobile_order": mobile,
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
