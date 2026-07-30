"""C84 closure authority contracts and C35 recommendation assessment."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
FIXTURES = ROOT / "review_verify_closure_authority_fixtures.json"
C35_AUDIT = ROOT / "review_verify_audit.json"


def load(path: Path) -> Any:
    return json.loads(path.read_text())


def authority_action(row: dict[str, Any]) -> str:
    if not row.get("population_complete", False):
        return "unknown-no-op"
    kind = row["issue_kind"]
    if kind == "residence":
        if not row.get("residence_observed"):
            return "grace-unknown-residence"
        return "surface-triage-only" if row.get("residence_hours", 0) > 168 else "within-residence-bar"
    if kind == "duplicate":
        return "duplicate-review" if row.get("semantic_duplicate") or row.get("declared_marker_owners", 0) > 1 else "clean"
    if kind == "alert":
        if row.get("red_since_first_green"):
            return "red-open"
        hours = row.get("continuous_green_hours", 0)
        if hours >= 24:
            return "auto-close-eligible" if row.get("behavior_deployed") else "working-tree-only-no-op"
        return "green-pending"
    if not row.get("snapshot_member", False) and row.get("current_member", False):
        return "uncovered-requires-audit"
    if row.get("dependency_open"):
        return "blocked-on-dependency"
    if not row.get("acceptance_unchanged", True):
        return "unsafe-to-automate"
    if not row.get("no_newer_regression", True):
        return "regressed"
    complete = all(row.get(k, False) for k in (
        "exact_deployed_sha", "green_ci", "acceptance_unchanged",
        "current_live_proof", "no_newer_regression",
    ))
    return "recommend-manual-close" if complete else "needs-live-verification"


def assess_c35(entry: dict[str, Any], overrides: dict[str, str]) -> str:
    number = str(entry["number"])
    if number in overrides:
        return "unsafe-to-automate-ruling-override"
    return {
        "close-with-existing-evidence": "evidence-backed-recommendation-revalidate",
        "needs-live-verification": "requires-live-proof",
        "blocked-on-dependency": "dependency-gated",
        "regressed": "unsafe-to-automate-regressed",
        "misrouted": "misrouted",
    }[entry["classification"]]


def assessment_summary() -> dict[str, Any]:
    fixtures = load(FIXTURES)
    rows = load(C35_AUDIT)
    assessments = {str(row["number"]): assess_c35(row, fixtures["ruling_overrides"]) for row in rows}
    counts: dict[str, int] = {}
    for value in assessments.values():
        counts[value] = counts.get(value, 0) + 1
    return {"rows": len(rows), "counts": counts, "assessments": assessments}


def main() -> int:
    fixtures = load(FIXTURES)
    print(json.dumps({
        "fixtures": {row["id"]: authority_action(row) for row in fixtures["scenarios"]},
        "c35": assessment_summary(),
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
