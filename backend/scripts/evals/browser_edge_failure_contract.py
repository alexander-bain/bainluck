"""Dependency-free C134 contract for CORS-visible throttling and bounded retries."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "browser-edge-failure-contract/v1"
FIXTURE = (
    Path(__file__).parents[2]
    / "tests"
    / "evals"
    / "fixtures"
    / "browser_edge_failure_contract.json"
)

POLICY_REFS = {"threshold_ref", "identity_strategy_ref", "foreground_retry_ref"}


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


def _positive_retry_after(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    try:
        return int(value) > 0 and str(int(value)) == str(value)
    except (TypeError, ValueError):
        return False


def evaluate_case(row: dict[str, Any]) -> list[str]:
    """Return stable refusal codes; empty means the described edge flow is safe."""
    errors: list[str] = []
    policy = row.get("policy") or {}
    request = row.get("request") or {}
    limiter = row.get("limiter") or {}
    response = row.get("response") or {}
    retry = row.get("retry") or {}

    if not POLICY_REFS <= set(policy) or any(not policy.get(ref) for ref in POLICY_REFS):
        errors.append("POLICY_AUTHORITY_MISSING")

    origin_class = request.get("origin_class")
    cors_applied = response.get("cors_applied") is True
    allow_origin = response.get("allow_origin")
    if origin_class == "allowed":
        if not cors_applied or allow_origin != request.get("origin"):
            errors.append("ALLOWED_ORIGIN_RESPONSE_OPAQUE")
    elif origin_class in {"disallowed", "malformed"} and allow_origin:
        errors.append("DISALLOWED_ORIGIN_REFLECTED")

    decision = limiter.get("decision")
    status = response.get("status")
    if decision == "reject":
        if status != 429:
            errors.append("LIMIT_REJECTION_BYPASSED")
        header = response.get("retry_after_header")
        body_value = (response.get("body") or {}).get("retry_after")
        if not _positive_retry_after(header) or str(body_value) != str(header):
            errors.append("RETRY_AFTER_INVALID")
    elif decision == "allow" and status == 429:
        errors.append("ALLOWED_REQUEST_FALSELY_THROTTLED")

    if request.get("method") == "OPTIONS" and limiter.get("counted"):
        errors.append("PREFLIGHT_CONSUMES_RATE_BUDGET")
    if limiter.get("bucket_class") == "authenticated" and not limiter.get(
        "identity_verified"
    ):
        errors.append("UNVERIFIED_IDENTITY_RATE_BYPASS")
    if response.get("exposes_limiter_identity"):
        errors.append("LIMITER_IDENTITY_EXPOSED")
    if limiter.get("actual_count_delta") != limiter.get("expected_count_delta"):
        errors.append("LIMIT_ACCOUNTING_DRIFT")

    if retry:
        if retry.get("cancelled") and retry.get("graded_success"):
            errors.append("CANCELLATION_GRADED_SUCCESS")
        if retry.get("foreground_storm"):
            errors.append("FOREGROUND_RETRY_STORM")
        allowed_at = retry.get("allowed_at_ms")
        attempted_at = retry.get("attempted_at_ms")
        if (
            isinstance(allowed_at, int)
            and isinstance(attempted_at, int)
            and attempted_at < allowed_at
        ):
            errors.append("RETRY_BEFORE_ALLOWED_TIME")
        if retry.get("background_retry") and not retry.get("foreground_terminal"):
            errors.append("BACKGROUND_RETRY_OWNS_FOREGROUND")

    if response.get("body") and any(
        key in response["body"] for key in ("bucket_key", "client_ip", "user_id", "token")
    ):
        errors.append("INTERNAL_LIMITER_DETAIL_EXPOSED")

    return sorted(set(errors))


def evaluate_corpus(corpus: dict[str, Any]) -> dict[str, Any]:
    results = []
    for row in corpus["cases"]:
        actual = evaluate_case(row)
        expected = sorted(row.get("expected_refusals") or [])
        results.append({"id": row["id"], "ok": actual == expected, "actual": actual})
    return {
        "total": len(results),
        "passed": sum(row["ok"] for row in results),
        "cases": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", default=str(FIXTURE))
    args = parser.parse_args()
    report = evaluate_corpus(load_corpus(args.fixture))
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["passed"] == report["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
