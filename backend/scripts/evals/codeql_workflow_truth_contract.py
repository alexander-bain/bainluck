"""Dependency-free oracle for mixed-language security workflow truth."""

from __future__ import annotations


CODEQL_LANGUAGES = {"python", "javascript-typescript", "swift"}


def evaluate(case: dict) -> dict:
    reasons: list[str] = []
    language = case.get("language")
    scanner = case.get("scanner", "codeql")
    runner = case.get("runner", "ubuntu-latest")

    if scanner == "codeql" and language not in CODEQL_LANGUAGES:
        reasons.append("unsupported_language")
    if scanner == "codeql" and language == "swift" and not runner.startswith("macos"):
        reasons.append("swift_requires_macos")
    if language == "swift" and scanner == "none":
        reasons.append("native_unscanned")
    if scanner == "native-static-analysis" and not runner.startswith("macos"):
        reasons.append("native_scanner_requires_macos")

    if case.get("uploads_sarif") and not case.get("security_events_write"):
        reasons.append("missing_sarif_permission")
    if case.get("event") == "pull_request_target" and case.get("checks_out_pr_head"):
        reasons.append("untrusted_code_with_write_token")
    if case.get("fork_pr") and case.get("requires_repo_secret"):
        reasons.append("fork_secret_unavailable")
    if case.get("failure_tolerated"):
        reasons.append("failure_masked")
    if case.get("matrix_failure") and case.get("aggregate_green"):
        reasons.append("matrix_partial_success_masked")
    if case.get("relevant_change") and not case.get("triggered", True):
        reasons.append("relevant_path_skipped")
    if case.get("action_ref_mutable"):
        reasons.append("mutable_action_ref")
    if case.get("generated_included") and not case.get("generated_is_product"):
        reasons.append("generated_noise")
    if case.get("duplicate_owner"):
        reasons.append("duplicate_scan_owner")
    if case.get("required_check_expected") and (
        case.get("job_name") != case.get("required_check_expected")
    ):
        reasons.append("required_check_detached")
    if case.get("event") not in {"push", "pull_request", "schedule", "workflow_dispatch"}:
        reasons.append("unsupported_event")

    return {
        "verdict": "REFUSE" if reasons else "ALLOW",
        "reason_codes": list(dict.fromkeys(reasons)),
    }


def evaluate_plan(plan: dict) -> dict:
    rows = plan.get("rows", [])
    results = [evaluate(row) for row in rows]
    covered = {
        row.get("language")
        for row, result in zip(rows, results)
        if result["verdict"] == "ALLOW"
    }
    required = set(plan.get("required_languages", []))
    reasons = [reason for result in results for reason in result["reason_codes"]]
    if not required <= covered:
        reasons.append("language_coverage_gap")
    return {
        "verdict": "REFUSE" if reasons else "ALLOW",
        "reason_codes": list(dict.fromkeys(reasons)),
    }

