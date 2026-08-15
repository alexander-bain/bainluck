"""Dependency-free oracle for winner repair and Kalshi retention recovery."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

FIXTURE = Path(__file__).parents[2] / "tests/evals/fixtures/calibration_repair_retention_contract.json"


def load_corpus(path: str | Path = FIXTURE) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("schema_version") != "calibration-repair-retention-contract/v1":
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


def _repair(row: dict[str, Any]) -> dict[str, Any]:
    r = row["repair"]
    reasons: list[str] = []
    candidates = list(r.get("candidate_ids", []))
    processed = list(r.get("processed_ids", []))
    allowed = list(r.get("approved_ids", candidates))
    mutations = list(r.get("mutated_ids", []))
    next_cursor = r.get("next_cursor")
    remaining = [item for item in candidates if item not in processed]

    if any(item not in allowed for item in mutations):
        reasons.append("MUTATION_OUTSIDE_APPROVED_SET")
    if r.get("authority") != "single_authoritative_winner" and mutations:
        reasons.append("MUTATION_WITHOUT_AUTHORITY")
    if r.get("dry_run_ids") is not None and mutations and mutations != r["dry_run_ids"]:
        reasons.append("DRY_RUN_APPLY_IDENTITY_DRIFT")
    if remaining and next_cursor is not None and next_cursor >= max(remaining):
        reasons.append("CURSOR_SKIPS_UNPROCESSED")
    if r.get("poison_aborts_siblings"):
        reasons.append("POISON_ABORTS_BATCH")
    if r.get("rerun_mutations"):
        reasons.append("RERUN_NOT_IDEMPOTENT")

    action = "REFUSE" if reasons else ("APPLY" if mutations else "NOOP")
    return {"action": action, "allowed_mutations": mutations if not reasons else [], "reason_codes": sorted(set(reasons))}


def _retention(row: dict[str, Any]) -> dict[str, Any]:
    r = row["retention"]
    reasons: list[str] = []
    selected = list(r.get("selected_ids", []))
    fetched = list(r.get("fetched_ids", []))
    recovered = list(r.get("recovered_ids", []))
    next_cursor = r.get("next_cursor")
    remaining = [item for item in selected if item not in fetched]

    if remaining and next_cursor is not None and next_cursor >= max(remaining):
        reasons.append("CURSOR_SKIPS_UNFETCHED")
    if r.get("response") in {"timeout", "rate_limit", "error", "partial"} and r.get("verdict") == "complete":
        reasons.append("DEGRADED_RUN_MARKED_COMPLETE")
    if r.get("response") == "empty" and not r.get("existence_known") and r.get("claim") == "never_traded":
        reasons.append("EMPTY_RESPONSE_INVENTS_ABSENCE")
    if r.get("boundary_after") is not None and r.get("response") != "complete":
        reasons.append("DEGRADED_RUN_MOVES_BOUNDARY")
    if selected and fetched and not recovered and r.get("verdict") == "complete" and r.get("response") != "nothing_eligible":
        reasons.append("ZERO_YIELD_MARKED_COMPLETE")
    if len(fetched) != len(set(fetched)) and not r.get("deduped"):
        reasons.append("DUPLICATE_FETCH_UNHANDLED")
    if r.get("timestamps_valid") is False and r.get("boundary_after") is not None:
        reasons.append("MALFORMED_TIMESTAMP_MOVES_BOUNDARY")

    verdict = "REFUSE" if reasons else r.get("verdict", "unknown").upper()
    return {"verdict": verdict, "recovered_ids": recovered if not reasons else [], "reason_codes": sorted(set(reasons))}


def _invalidation(row: dict[str, Any]) -> dict[str, Any]:
    """When a calibration invalidation counts as DISCHARGED (CAL-P062).

    Re-derived here rather than imported, like every other rule in this file:
    the corpus is only an oracle if it is a second opinion. The shipping rule
    lives in ``app/utils/calibration_invalidation.invalidation_discharged`` and
    the test suite asserts the two agree case by case — a disagreement is the
    finding, and neither side is allowed to be the other's definition.

    The rule the certification asked for: ``nothing_written`` is a discharge
    ONLY for a plan proven never to have written. An open obligation carried in
    from an earlier call, rows written by this call, or unresolved concurrent
    drift each defeat that proof.
    """
    r = row["invalidation"]
    status = r.get("status")
    reasons: list[str] = []

    if status == "invalidated":
        return {"discharged": True, "reason_codes": []}
    if status != "nothing_written":
        return {"discharged": False, "reason_codes": ["INVALIDATION_NOT_EXECUTED"]}

    if r.get("prior_obligation_open"):
        reasons.append("PRIOR_OBLIGATION_UNDISCHARGED")
    if r.get("wrote_rows"):
        reasons.append("NOTHING_WRITTEN_CONTRADICTS_WRITES")
    if int(r.get("drift_count") or 0) > 0:
        reasons.append("DRIFT_LEAVES_NEVER_WROTE_UNPROVEN")

    return {"discharged": not reasons, "reason_codes": sorted(set(reasons))}


def evaluate_case(row: dict[str, Any]) -> dict[str, Any]:
    if row.get("kind") == "repair":
        return _repair(row)
    if row.get("kind") == "retention":
        return _retention(row)
    if row.get("kind") == "invalidation":
        return _invalidation(row)
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
