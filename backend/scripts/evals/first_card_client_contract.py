"""Dependency-free C132 contract for public first-card client behavior."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "first-card-client-contract/v1"
FIXTURE = (
    Path(__file__).parents[2]
    / "tests"
    / "evals"
    / "fixtures"
    / "first_card_client_contract.json"
)

REAL_CARD_REQUIRED = {"kind", "stable_id", "mounted"}
FROZEN_SEMANTICS = {
    "ranking_unchanged",
    "probability_unchanged",
    "eligibility_unchanged",
    "freshness_unchanged",
}


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


def _duplicates(values: list[Any]) -> bool:
    return len(values) != len(set(values))


def evaluate_case(row: dict[str, Any]) -> list[str]:
    """Return stable refusal codes; empty means the described flow is safe."""
    errors: list[str] = []
    phases = row.get("phases") or []
    phase_times = [phase.get("at_ms") for phase in phases]
    if any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in phase_times):
        errors.append("PHASE_TIME_INVALID")
    elif phase_times != sorted(phase_times):
        errors.append("PHASE_ORDER_INVALID")

    flow = row.get("flow") or {}
    if flow.get("public_surface"):
        request_at = flow.get("initial_request_at_ms")
        auth_at = flow.get("auth_terminal_at_ms")
        if request_at is None:
            errors.append("PUBLIC_REQUEST_NEVER_STARTED")
        elif auth_at is not None and request_at >= auth_at:
            errors.append("AUTH_BLOCKS_PUBLIC_REQUEST")

    render = row.get("render") or {}
    if render.get("verdict") == "real_card":
        if not REAL_CARD_REQUIRED <= set(render):
            errors.append("FIRST_CARD_EVIDENCE_INCOMPLETE")
        elif (
            render.get("kind") != "card"
            or not render.get("stable_id")
            or render.get("mounted") is not True
        ):
            errors.append("FAKE_FIRST_CARD_SUCCESS")
    elif render.get("counted_as_first_card"):
        errors.append("NON_CARD_COUNTED_AS_FIRST_CARD")

    principal = row.get("principal") or {}
    if principal.get("late_response_applied") and (
        principal.get("late_response_generation") != principal.get("current_generation")
        or principal.get("late_response_principal") != principal.get("current_principal")
    ):
        errors.append("STALE_PRINCIPAL_OVERWRITE")

    paging = row.get("paging") or {}
    if paging:
        legacy = paging.get("legacy_ids") or []
        pages = paging.get("pages") or []
        offsets = [page.get("offset") for page in pages]
        combined = [value for page in pages for value in (page.get("ids") or [])]
        first_size = paging.get("first_page_size")
        if not isinstance(first_size, int) or first_size <= 0:
            errors.append("FIRST_PAGE_SIZE_INVALID")
        elif combined[:first_size] != legacy[:first_size]:
            errors.append("FIRST_PAGE_IDENTITY_OR_ORDER_DRIFT")
        if offsets and (offsets[0] != 0 or offsets != sorted(set(offsets))):
            errors.append("PAGINATION_OFFSET_NON_MONOTONIC")
        if _duplicates(combined):
            errors.append("PAGINATION_DUPLICATE_ID")
        if paging.get("complete") and combined != legacy:
            errors.append("PAGINATION_TRUNCATED_OR_REORDERED")
        if paging.get("declared_exhausted") and set(combined) != set(legacy):
            errors.append("PREMATURE_EXHAUSTION")
        if paging.get("late_page_failed") and paging.get("cleared_prior_cards"):
            errors.append("LATE_PAGE_FAILURE_CLEARED_CARDS")

    failure = row.get("failure") or {}
    if failure:
        if failure.get("requires_foreground_terminal") and not failure.get("budget_ref"):
            errors.append("FOREGROUND_BUDGET_NEEDS_APPROVAL")
        if failure.get("retries_block_foreground"):
            errors.append("RETRIES_HOLD_SKELETON")
        if failure.get("terminal") in {None, "loading", "skeleton"}:
            errors.append("FAILURE_HAS_NO_HONEST_TERMINAL")
        if failure.get("last_good_present") and failure.get("last_good_preserved") is not True:
            errors.append("FAILURE_CLEARED_LAST_GOOD")
        if failure.get("background_retry") and failure.get("foreground_terminal") is not True:
            errors.append("BACKGROUND_RETRY_OWNS_FOREGROUND")

    semantics = row.get("semantics") or {}
    if semantics and (
        not FROZEN_SEMANTICS <= set(semantics)
        or any(semantics.get(name) is not True for name in FROZEN_SEMANTICS)
    ):
        errors.append("PRODUCT_SEMANTICS_DRIFT")

    return sorted(set(errors))


def evaluate_corpus(corpus: dict[str, Any]) -> dict[str, Any]:
    results = []
    for case in corpus["cases"]:
        actual = evaluate_case(case)
        expected = sorted(case.get("expected_refusals") or [])
        results.append({"id": case["id"], "ok": actual == expected, "actual": actual})
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
