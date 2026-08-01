"""Dependency-free contract evaluator for calibration candidate publication."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from copy import deepcopy
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FIXTURES = ROOT / "tests/evals/fixtures/calibration_publish_gate_contract.json"


def load_pack(path: Path = DEFAULT_FIXTURES) -> dict[str, Any]:
    return json.loads(path.read_text())


def _resolve_case(case: dict[str, Any], pack: dict[str, Any]) -> dict[str, Any]:
    """Resolve named artifacts while keeping the JSON corpus compact and reviewable."""
    resolved = deepcopy(case)
    artifacts = pack.get("artifacts", {})
    for key in ("prior", "candidate"):
        ref = resolved.pop(f"{key}_artifact", None)
        if ref is not None:
            resolved[key] = deepcopy(artifacts[ref])
    poison_index = resolved.pop("poison_category_index", None)
    if poison_index is not None:
        resolved["candidate"]["categories"][poison_index] = "poison-row"
    for key in ("prior", "candidate"):
        overrides = resolved.pop(f"{key}_category_overrides", {})
        for row in resolved.get(key, {}).get("categories", []):
            if isinstance(row, dict) and row.get("name") in overrides:
                row.update(overrides[row["name"]])
    return resolved


def _finite_number(value: Any, *, integer: bool = False) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    if integer and not isinstance(value, int):
        return False
    return math.isfinite(float(value))


def _indexed(rows: Any, *, kind: str) -> tuple[dict[str, dict[str, Any]], list[str]]:
    if not isinstance(rows, list):
        return {}, [f"{kind.upper()}_WRONG_SHAPE"]
    indexed: dict[str, dict[str, Any]] = {}
    findings: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            findings.append(f"POISON_{kind.upper()}_ROW")
            continue
        name = row.get("name")
        if not isinstance(name, str) or not name:
            findings.append(f"INVALID_{kind.upper()}_NAME")
            continue
        if name in indexed:
            findings.append(f"DUPLICATE_{kind.upper()}")
            continue
        if not _finite_number(row.get("n"), integer=True) or row["n"] < 0:
            findings.append(f"INVALID_{kind.upper()}_COUNT")
            continue
        if not _finite_number(row.get("ece_pp")) or row["ece_pp"] < 0:
            findings.append(f"INVALID_{kind.upper()}_METRIC")
            continue
        indexed[name] = row
    return indexed, findings


def validate_artifact(artifact: Any, policy: dict[str, Any]) -> list[str]:
    if not isinstance(artifact, dict):
        return ["ARTIFACT_WRONG_SHAPE"]
    findings: list[str] = []
    required = {
        "schema_version", "population_version", "build_status", "total_outcomes",
        "completed_sections", "categories", "activity_tiers",
    }
    if required - artifact.keys():
        return ["ARTIFACT_MISSING_FIELDS"]
    if artifact.get("schema_version") != policy.get("artifact_schema_version"):
        findings.append("ARTIFACT_SCHEMA_MISMATCH")
    if not isinstance(artifact.get("population_version"), str) or not artifact["population_version"]:
        findings.append("INVALID_POPULATION_VERSION")
    if artifact.get("build_status") != "complete":
        findings.append("BUILD_NOT_COMPLETE")
    if not _finite_number(artifact.get("total_outcomes"), integer=True) or artifact["total_outcomes"] <= 0:
        findings.append("INVALID_POPULATION_COUNT")
    sections = artifact.get("completed_sections")
    if not isinstance(sections, list) or any(not isinstance(x, str) for x in sections):
        findings.append("COMPLETED_SECTIONS_WRONG_SHAPE")
    else:
        missing = set(policy.get("required_sections", [])) - set(sections)
        if missing:
            findings.append("REQUIRED_SECTIONS_INCOMPLETE")
    _, category_findings = _indexed(artifact.get("categories"), kind="category")
    _, tier_findings = _indexed(artifact.get("activity_tiers"), kind="activity_tier")
    findings.extend(category_findings)
    findings.extend(tier_findings)
    return sorted(set(findings))


def _bridge_valid(prior: dict[str, Any], candidate: dict[str, Any]) -> bool:
    bridge = candidate.get("population_bridge")
    if not isinstance(bridge, dict):
        return False
    required = {"from_version", "to_version", "prior_total", "candidate_total", "components", "rationale"}
    if required - bridge.keys() or not isinstance(bridge.get("rationale"), str) or not bridge["rationale"].strip():
        return False
    if (
        bridge["from_version"] != prior.get("population_version")
        or bridge["to_version"] != candidate.get("population_version")
        or bridge["prior_total"] != prior.get("total_outcomes")
        or bridge["candidate_total"] != candidate.get("total_outcomes")
        or not isinstance(bridge.get("components"), list)
    ):
        return False
    deltas: list[int] = []
    for row in bridge["components"]:
        if not isinstance(row, dict) or not isinstance(row.get("reason"), str):
            return False
        if not _finite_number(row.get("delta"), integer=True):
            return False
        deltas.append(row["delta"])
    return sum(deltas) == candidate["total_outcomes"] - prior["total_outcomes"]


def _pct_change(prior: int, candidate: int) -> float | None:
    if prior <= 0:
        return None
    return (candidate - prior) * 100.0 / prior


def _tier_inversions(
    prior: dict[str, dict[str, Any]],
    candidate: dict[str, dict[str, Any]],
    tolerance: float,
) -> list[dict[str, Any]]:
    common = sorted(set(prior) & set(candidate))
    inversions: list[dict[str, Any]] = []
    for i, left in enumerate(common):
        for right in common[i + 1:]:
            before = prior[left]["ece_pp"] - prior[right]["ece_pp"]
            after = candidate[left]["ece_pp"] - candidate[right]["ece_pp"]
            if abs(before) > tolerance and abs(after) > tolerance and before * after < 0:
                inversions.append({
                    "left": left,
                    "right": right,
                    "prior_delta_pp": round(before, 4),
                    "candidate_delta_pp": round(after, 4),
                })
    return inversions


def gate_candidate(
    prior: dict[str, Any],
    candidate: dict[str, Any],
    policy: dict[str, Any],
) -> dict[str, Any]:
    findings = validate_artifact(candidate, policy)
    warnings: list[str] = []
    details: dict[str, Any] = {"category_deltas": [], "tier_inversions": []}
    prior_findings = validate_artifact(prior, policy)
    if prior_findings:
        findings.append("PRIOR_ARTIFACT_INVALID")

    version_changed = candidate.get("population_version") != prior.get("population_version")
    bridge_ok = _bridge_valid(prior, candidate) if version_changed else False
    if version_changed and not bridge_ok:
        findings.append("VERSION_BUMP_WITHOUT_COUNT_BRIDGE")

    if not prior_findings and not {"INVALID_POPULATION_COUNT", "ARTIFACT_MISSING_FIELDS"} & set(findings):
        change = _pct_change(prior["total_outcomes"], candidate["total_outcomes"])
        details["population_change_pct"] = None if change is None else round(change, 4)
        if change is None:
            findings.append("PRIOR_POPULATION_ZERO")
        elif abs(change) > float(policy["population_change_limit_pct"]):
            if not (version_changed and bridge_ok):
                findings.append("POPULATION_CHANGE_EXCEEDS_LIMIT")

    prior_categories, _ = _indexed(prior.get("categories"), kind="category")
    candidate_categories, _ = _indexed(candidate.get("categories"), kind="category")
    for name in sorted(set(prior_categories) | set(candidate_categories)):
        old = prior_categories.get(name)
        new = candidate_categories.get(name)
        if old is None:
            details["category_deltas"].append({"name": name, "status": "added", "candidate_n": new["n"]})
            continue
        if new is None:
            details["category_deltas"].append({"name": name, "status": "missing", "prior_n": old["n"]})
            findings.append("REQUIRED_CATEGORY_MISSING")
            continue
        n_change = _pct_change(old["n"], new["n"])
        ece_change = new["ece_pp"] - old["ece_pp"]
        details["category_deltas"].append({
            "name": name,
            "prior_n": old["n"],
            "candidate_n": new["n"],
            "n_change_pct": None if n_change is None else round(n_change, 4),
            "ece_change_pp": round(ece_change, 4),
        })
        if n_change is None:
            findings.append("PRIOR_CATEGORY_ZERO")
        elif n_change < -float(policy["category_drop_limit_pct"]):
            if not (version_changed and bridge_ok):
                findings.append("CATEGORY_COUNT_DROP_EXCEEDS_LIMIT")
        if new["n"] < int(policy["category_min_n"]):
            if abs(ece_change) > float(policy["category_ece_regression_pp"]):
                warnings.append("LOW_N_CATEGORY_DISTORTION")
        elif ece_change > float(policy["category_ece_regression_pp"]):
            findings.append("MATERIAL_CATEGORY_ACCURACY_REGRESSION")

    prior_tiers, _ = _indexed(prior.get("activity_tiers"), kind="activity_tier")
    candidate_tiers, _ = _indexed(candidate.get("activity_tiers"), kind="activity_tier")
    details["tier_inversions"] = _tier_inversions(
        prior_tiers,
        candidate_tiers,
        float(policy["tier_inversion_tolerance_pp"]),
    )
    if details["tier_inversions"]:
        findings.append("ACTIVITY_TIER_RANK_INVERSION")

    findings = sorted(set(findings))
    warnings = sorted(set(warnings))
    verdict = "publish" if not findings else "refuse"
    result = {
        "verdict": verdict,
        "findings": findings,
        "warnings": warnings,
        "details": details,
        "main_state": "candidate" if verdict == "publish" else "prior",
        "last_good_state": "candidate" if verdict == "publish" else "prior",
        "issue": None,
    }
    if findings:
        fingerprint_input = {
            "contract": policy["contract_version"],
            "prior_version": prior.get("population_version"),
            "candidate_version": candidate.get("population_version"),
            "findings": findings,
            "categories": [row.get("name") for row in details["category_deltas"]],
            "tier_pairs": [f"{row['left']}:{row['right']}" for row in details["tier_inversions"]],
        }
        fingerprint = hashlib.sha256(
            json.dumps(fingerprint_input, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()[:16]
        result["issue"] = {
            "priority": "P2",
            "labels": ["needs-triage"],
            "fingerprint": f"calibration-publish-gate:{fingerprint}",
            "title": "Calibration candidate refused by publish gate",
            "prior_version": prior.get("population_version"),
            "candidate_version": candidate.get("population_version"),
            "prior_total": prior.get("total_outcomes"),
            "candidate_total": candidate.get("total_outcomes"),
            "failed_gates": findings,
            "warnings": warnings,
            "category_deltas": details["category_deltas"],
            "tier_inversions": details["tier_inversions"],
        }
    return result


def evaluate_case(case: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    result = gate_candidate(case.get("prior"), case.get("candidate"), policy)
    expected = case.get("expected", {})
    mismatches: list[str] = []
    for key in ("verdict", "main_state", "last_good_state", "findings", "warnings", "issue"):
        if key in expected and result.get(key) != expected[key]:
            mismatches.append(key)
    if "expected_issue" in case and result.get("issue") != case["expected_issue"]:
        mismatches.append("expected_issue")
    return {"id": case.get("id"), **result, "expected_mismatches": mismatches}


def evaluate_pack(pack: dict[str, Any]) -> dict[str, Any]:
    policy = pack["policy"]
    rows = [evaluate_case(_resolve_case(case, pack), policy) for case in pack.get("cases", [])]
    return {
        "contract_version": policy["contract_version"],
        "cases": len(rows),
        "passed": sum(not row["expected_mismatches"] for row in rows),
        "results": rows,
    }


def simulate_publication(
    store: dict[str, Any], candidate: dict[str, Any], policy: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Pure atomicity model: refusal preserves both keys; pass replaces both."""
    before = deepcopy(store)
    result = gate_candidate(before["main"], candidate, policy)
    if result["verdict"] == "publish":
        after = {"main": deepcopy(candidate), "last_good": deepcopy(candidate)}
    else:
        after = before
    return after, result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixtures", type=Path, default=DEFAULT_FIXTURES)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = evaluate_pack(load_pack(args.fixtures))
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"{result['passed']}/{result['cases']} calibration publish-gate cases passed")
        for row in result["results"]:
            if row["expected_mismatches"]:
                print(f"FAIL {row['id']}: {row['expected_mismatches']}")
    return 0 if result["passed"] == result["cases"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
