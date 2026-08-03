"""Dependency-free evaluator for the C127 calibration orphan contract."""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any

FIXTURE = Path(__file__).parents[2] / "tests" / "evals" / "fixtures" / "calibration_orphan_containment_contract.json"
SCHEMA = "calibration-orphan-containment-contract/v1"


def _merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def load_corpus(path: str | Path = FIXTURE) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("schema_version") != SCHEMA:
        raise ValueError("SCHEMA_VERSION_INVALID")
    cases = payload.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("CASES_REQUIRED")
    ids = [row.get("id") for row in cases if isinstance(row, dict)]
    if len(ids) != len(cases) or any(not isinstance(value, str) or not value for value in ids):
        raise ValueError("CASE_ID_REQUIRED")
    if len(ids) != len(set(ids)):
        raise ValueError("CASE_ID_DUPLICATE")
    if not isinstance(payload.get("defaults"), dict):
        raise ValueError("DEFAULTS_REQUIRED")
    return payload


def materialize(payload: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    merged = _merge(payload["defaults"], row)
    merged["id"] = row["id"]
    merged["expected_errors"] = row["expected_errors"]
    return merged


def _identity(session: dict[str, Any]) -> tuple[Any, ...]:
    return tuple(session.get(key) for key in ("pid", "backend_start", "xact_start", "query_start", "fingerprint"))


def evaluate_case(row: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    policy = row["policy"]
    observations = row.get("observations", [])
    recheck = row.get("recheck", [])
    action = row["action"]
    verification = row["verification"]

    maximum = policy.get("max_candidates")
    if not isinstance(maximum, int) or maximum <= 0:
        errors.append("MAX_CANDIDATES_INVALID")
        maximum = 0
    if len(observations) > maximum:
        errors.append("CANDIDATE_SET_TOO_LARGE")

    recheck_by_pid = {item.get("pid"): item for item in recheck}
    eligible: set[int] = set()
    for session in observations:
        pid = session.get("pid")
        if session.get("fingerprint") not in policy.get("allowlisted_fingerprints", []):
            errors.append("FINGERPRINT_NOT_ALLOWLISTED")
        if session.get("age_s", 0) >= policy.get("min_age_s", 0) and not session.get("identity_evidence"):
            errors.append("AGE_ONLY_AUTHORITY")
        if session.get("state") != "active":
            errors.append("SESSION_NOT_ACTIVE")
        if session.get("xmin") is None:
            errors.append("XMIN_MISSING")
        if session.get("generation_relation") == "current" or session.get("current_beat"):
            errors.append("CURRENT_GENERATION_TARGETED")
        if session.get("generation_relation") not in {"predeploy", "superseded", "current"}:
            errors.append("GENERATION_AUTHORITY_UNKNOWN")
        if session.get("observation_count", 0) < 2:
            errors.append("REPEAT_OBSERVATION_REQUIRED")
        if session.get("application_name") in {None, ""} and not session.get("independent_generation_authority"):
            errors.append("OWNER_IDENTITY_AMBIGUOUS")
        current = recheck_by_pid.get(pid)
        if current is None:
            if action.get("terminate_pids") and pid in action.get("terminate_pids", []):
                errors.append("TERMINATE_AFTER_NATURAL_COMPLETION")
            continue
        if _identity(current) != _identity(session):
            errors.append("PID_OR_IDENTITY_CHANGED")
            continue
        if current.get("fingerprint") not in policy.get("allowlisted_fingerprints", []):
            errors.append("RECHECK_FINGERPRINT_CHANGED")
            continue
        if current.get("current_beat") or current.get("generation_relation") == "current":
            errors.append("RECHECK_BECAME_CURRENT")
            continue
        if not current.get("fresh", False):
            errors.append("RECHECK_STALE")
            continue
        eligible.add(pid)

    mode = action.get("mode")
    cancel_pids = set(action.get("cancel_pids", []))
    terminate_pids = set(action.get("terminate_pids", []))
    known_pids = {item.get("pid") for item in observations}
    if mode == "dry_run":
        if cancel_pids or terminate_pids:
            errors.append("DRY_RUN_MUTATED")
    elif mode == "apply":
        if not policy.get("alex_ruling_selected"):
            errors.append("ALEX_RULING_REQUIRED")
        if not action.get("attended"):
            errors.append("ATTENDED_OPERATOR_REQUIRED")
        if cancel_pids - eligible or terminate_pids - eligible:
            errors.append("ACTION_OUTSIDE_REVALIDATED_SET")
        if terminate_pids - cancel_pids:
            errors.append("TERMINATE_WITHOUT_CANCEL_FIRST")
        if terminate_pids and not action.get("grace_elapsed"):
            errors.append("TERMINATE_WITHOUT_GRACE_RECHECK")
        if action.get("requested_pids") and set(action["requested_pids"]) != (cancel_pids | terminate_pids):
            errors.append("ACTION_PID_SET_MISMATCH")
        if (cancel_pids | terminate_pids) - known_pids:
            errors.append("UNKNOWN_PID_ACTION")
    else:
        errors.append("ACTION_MODE_INVALID")

    if action.get("connection_lost") and action.get("reported_success"):
        errors.append("CONNECTION_LOSS_REPORTED_SUCCESS")
    if action.get("partial_failure") and action.get("reported_success"):
        errors.append("PARTIAL_ACTION_REPORTED_SUCCESS")
    if action.get("double_action"):
        errors.append("DOUBLE_ACTION")

    if verification.get("reported_success"):
        if not verification.get("candidates_gone"):
            errors.append("SUCCESS_WITH_CANDIDATE_PRESENT")
        if verification.get("replacement_orphan"):
            errors.append("SUCCESS_WITH_REPLACEMENT_ORPHAN")
        if not verification.get("xmin_advanced"):
            errors.append("SUCCESS_WITHOUT_XMIN_ADVANCE")
    if verification.get("bloat_reclaimed") and not verification.get("separate_reclaim_observation"):
        errors.append("RECLAIM_CONFLATED_WITH_TERMINATION")
    if verification.get("vacuum_executed"):
        errors.append("VACUUM_OUTSIDE_CONTAINMENT_ACTION")
    if verification.get("rollback_claimed"):
        errors.append("TERMINATION_FALSELY_ROLLBACKABLE")

    poison = row.get("poison")
    if poison:
        if poison.get("position") not in {"first", "middle", "last"}:
            errors.append("POISON_POSITION_INVALID")
        if not poison.get("siblings_preserved"):
            errors.append("POISON_ERASES_SIBLINGS")
    return sorted(set(errors))


def evaluate_corpus(payload: dict[str, Any]) -> dict[str, Any]:
    details = []
    for raw in sorted(payload["cases"], key=lambda value: value["id"]):
        actual = evaluate_case(materialize(payload, raw))
        expected = sorted(raw["expected_errors"])
        details.append({"id": raw["id"], "actual_errors": actual, "expected_errors": expected, "passed": actual == expected})
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
