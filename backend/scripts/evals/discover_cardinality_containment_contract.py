"""Dependency-free oracle for Discover suppression and census provenance."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

FIXTURE = Path(__file__).parents[2] / "tests/evals/fixtures/discover_cardinality_containment_contract.json"


def load_corpus(path: str | Path = FIXTURE) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("schema_version") != "discover-cardinality-containment-contract/v1":
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


def _market(row: dict[str, Any]) -> dict[str, Any]:
    market = row["market"]
    reasons: list[str] = []
    include = True
    delta = 0

    bid, ask = market.get("bid"), market.get("ask")
    probability = market.get("probability")
    if bid is not None and ask is not None and bid > ask:
        include = False
        delta = -1
        reasons.append("CROSSED_BOOK_REFUSED")
    elif market.get("fabricated_midpoint"):
        include = False
        delta = -1
        reasons.append("FABRICATED_MIDPOINT")
    elif market.get("daily_direction"):
        if not market.get("has_explicit_deadline"):
            reasons.append("DAILY_DIRECTION_DATE_UNPROVEN")
        else:
            include = False
            delta = -1
            reasons.append("DAILY_DIRECTION_FILLER")

    if market.get("exclusive") and market.get("survivor_sum") is not None:
        if not 0.75 <= market["survivor_sum"] <= 1.25:
            include = False
            delta = -1
            reasons.append("EXCLUSIVE_FIELD_INCOMPLETE")
    if not market.get("exclusive") and market.get("survivor_sum", 0) > 1.25:
        reasons.append("NONEXCLUSIVE_SUM_ALLOWED")

    if market.get("representative") and not include and not reasons:
        reasons.append("REPRESENTATIVE_DROPPED_UNTYPED")
    return {"include": include, "cardinality_delta": delta, "reason_codes": sorted(set(reasons))}


def _census(row: dict[str, Any]) -> dict[str, Any]:
    census = row["census"]
    reasons: list[str] = []
    before = census["before"]
    after = census["after"]
    removed = census.get("removed", [])
    explained = [item for item in removed if item.get("reason")]
    observed_drop = before - after
    if observed_drop < 0:
        reasons.append("CARDINALITY_INCREASE")
    if observed_drop != len(removed):
        reasons.append("CENSUS_DELTA_UNACCOUNTED")
    if len(explained) != len(removed):
        reasons.append("REMOVAL_REASON_MISSING")
    for family, counts in census.get("families", {}).items():
        family_drop = counts["before"] - counts["after"]
        family_removed = [item for item in removed if item.get("family") == family]
        if family_drop != len(family_removed):
            reasons.append(f"FAMILY_{family.upper()}_DELTA_UNACCOUNTED")
    if census.get("mode_peer_count") is not None and census.get("mode_divergence_reason") is None:
        if after != census["mode_peer_count"]:
            reasons.append("MODE_DIVERGENCE_UNEXPLAINED")
    verdict = "PUBLISH" if not [r for r in reasons if r != "CARDINALITY_INCREASE"] else "REFUSE"
    return {"verdict": verdict, "explained": verdict == "PUBLISH", "reason_codes": sorted(set(reasons))}


def _task(row: dict[str, Any]) -> dict[str, Any]:
    task = row["task"]
    primary, legacy = task.get("task"), task.get("task_name")
    reasons: list[str] = []
    if primary and legacy and primary != legacy:
        subject = None
        reasons.append("TASK_SUBJECT_AMBIGUOUS")
    else:
        subject = primary or legacy
    if not subject and not (primary and legacy):
        reasons.append("TASK_REQUIRED")
    if subject and task.get("response_task") != subject:
        reasons.append("TASK_RESPONSE_SUBJECT_MISMATCH")
    verdict = "ANSWER" if not reasons else "REFUSE"
    return {"verdict": verdict, "subject": subject, "reason_codes": sorted(set(reasons))}


def evaluate_case(row: dict[str, Any]) -> dict[str, Any]:
    kind = row.get("kind")
    if kind == "market":
        return _market(row)
    if kind == "census":
        return _census(row)
    if kind == "task":
        return _task(row)
    raise ValueError("CASE_KIND_INVALID")


def evaluate_corpus(payload: dict[str, Any]) -> dict[str, Any]:
    details = []
    for row in sorted(payload["cases"], key=lambda item: item["id"]):
        actual = evaluate_case(row)
        details.append({"id": row["id"], "actual": actual, "expected": row["expected"], "passed": actual == row["expected"]})
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
