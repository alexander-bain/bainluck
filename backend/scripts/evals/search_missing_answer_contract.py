"""Dependency-free oracle for search answers that go missing under a deadline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

FIXTURE = Path(__file__).parents[2] / "tests/evals/fixtures/search_missing_answer_contract.json"
FAMILIES = ("events", "futures", "teams", "concepts")


def load_corpus(path: str | Path = FIXTURE) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("schema_version") != "search-missing-answer-contract/v1":
        raise ValueError("SCHEMA_VERSION_INVALID")
    cases = payload.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("CASES_REQUIRED")
    ids = [row.get("id") for row in cases if isinstance(row, dict)]
    if len(ids) != len(cases) or any(not isinstance(value, str) or not value for value in ids):
        raise ValueError("CASE_ID_REQUIRED")
    if len(ids) != len(set(ids)):
        raise ValueError("CASE_ID_DUPLICATE")
    return payload


def decide(row: dict[str, Any]) -> dict[str, Any]:
    """Return the user-facing state, cache decision, and stable reason codes."""

    result = row["result"]
    degraded = set(result.get("degraded", []))
    returned = result["returned"]
    known = row.get("known_matches", {})
    reasons: list[str] = []

    deadline_ms = result.get("deadline_ms")
    elapsed_ms = result.get("elapsed_ms")
    if not isinstance(deadline_ms, int) or deadline_ms <= 0 or deadline_ms >= 30000:
        reasons.append("DEADLINE_NOT_BELOW_H12")
    if not isinstance(elapsed_ms, int) or elapsed_ms < 0:
        reasons.append("ELAPSED_INVALID")

    for family in FAMILIES:
        if family not in returned or not isinstance(returned[family], list):
            reasons.append("FAMILY_SHAPE_INCOMPLETE")

    missing_known = [
        family for family in FAMILIES
        if known.get(family) and not set(known[family]).intersection(returned.get(family, []))
    ]
    for family in missing_known:
        reasons.append(f"KNOWN_{family.upper()}_MISSING")
    if missing_known and not set(missing_known).issubset(degraded):
        reasons.append("MISSING_ANSWER_UNTYPED")

    has_results = any(returned.get(family) for family in FAMILIES)
    if degraded:
        display_state = "PARTIAL" if has_results else "UNKNOWN"
        cacheable = False
        reasons.append("DEGRADED_RESPONSE")
    else:
        display_state = "RESULTS" if has_results else "NO_MATCHES"
        cacheable = True

    if result.get("display_state") != display_state:
        reasons.append("DISPLAY_STATE_DISHONEST")
    if result.get("cacheable") is not cacheable:
        reasons.append("CACHE_DECISION_DISHONEST")
    if degraded and result.get("complete") is not False:
        reasons.append("DEGRADED_CLAIMS_COMPLETE")
    if not degraded and result.get("complete") is not True:
        reasons.append("COMPLETE_RESPONSE_UNCERTIFIED")
    if result.get("event_total_known") is False and result.get("event_total") is not None:
        reasons.append("UNKNOWN_EVENT_TOTAL_FABRICATED")

    return {
        "display_state": display_state,
        "cacheable": cacheable,
        "reason_codes": sorted(set(reasons)),
    }


def evaluate_corpus(payload: dict[str, Any]) -> dict[str, Any]:
    details = []
    for row in sorted(payload["cases"], key=lambda item: item["id"]):
        actual = decide(row)
        expected = row["expected"]
        details.append({"id": row["id"], "actual": actual, "expected": expected, "passed": actual == expected})
    return {"schema_version": payload["schema_version"], "total": len(details), "passed": sum(item["passed"] for item in details), "details": details}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", default=str(FIXTURE))
    args = parser.parse_args()
    report = evaluate_corpus(load_corpus(args.fixture))
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["passed"] == report["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
