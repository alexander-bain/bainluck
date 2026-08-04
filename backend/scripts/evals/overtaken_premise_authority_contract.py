"""Dependency-free C142 contract for overtaken-by-events lifecycle authority."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "overtaken-premise-authority-contract/v1"
FIXTURE = Path(__file__).parents[2] / "tests" / "evals" / "fixtures" / "overtaken_premise_authority_contract.json"

AUTHORITATIVE = {"venue_settlement", "deterministic_public_result", "reviewed_result_manifest", "linked_canonical_event"}
NON_AUTHORITATIVE = {"title_inference", "keyword_match", "llm_assertion", "news_snippet", "user_report", "curator_discovery_row"}
SURFACES = {"discover", "category", "search"}


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
    defaults = payload.get("defaults") or {}
    payload["cases"] = [{**defaults, **row} for row in cases]
    return payload


def decide(row: dict[str, Any]) -> tuple[str, list[str]]:
    refusals: list[str] = []
    evidence = row.get("evidence") or []
    authoritative = [e for e in evidence if e.get("type") in AUTHORITATIVE and e.get("valid")]
    untrusted = [e for e in evidence if e.get("type") in NON_AUTHORITATIVE]
    completed = [e for e in authoritative if e.get("premise_state") == "completed"]
    live = [e for e in authoritative if e.get("premise_state") == "live"]

    if untrusted and not authoritative:
        refusals.append("NO_AUTHORITATIVE_PREMISE_EVIDENCE")
    if any(e.get("stale") for e in authoritative):
        refusals.append("STALE_AUTHORITY_EVIDENCE")
    if completed and live:
        refusals.append("AUTHORITATIVE_CONTRADICTION")
    if row.get("premise_id") != row.get("market_premise_id"):
        refusals.append("WRONG_PREMISE_IDENTITY")
    if row.get("entity_id") != row.get("market_entity_id"):
        refusals.append("WRONG_ENTITY_IDENTITY")
    if not row.get("explicit_dependency"):
        refusals.append("DEPENDENCY_NOT_EXPLICIT")
    if row.get("ambiguous_family"):
        refusals.append("AMBIGUOUS_FAMILY")
    if row.get("multi_stage") and not row.get("required_stage_complete"):
        refusals.append("PREMISE_ONLY_PARTIALLY_COMPLETE")
    if not row.get("generation_complete"):
        refusals.append("EVIDENCE_GENERATION_INCOMPLETE")
    if row.get("authority_outage"):
        refusals.append("AUTHORITY_UNAVAILABLE")

    decisive = bool(completed) and not refusals
    action = "overtaken" if decisive else ("review" if refusals or completed else "include")

    if action == "overtaken":
        if set(row.get("propagated_surfaces") or []) != SURFACES:
            refusals.append("SURFACE_PROPAGATION_INCOMPLETE")
            action = "review"
        if not row.get("negative_controls_preserved"):
            refusals.append("NEGATIVE_CONTROL_SUPPRESSED")
            action = "review"
    if row.get("poison_sibling") and not row.get("clean_sibling_preserved"):
        refusals.append("POISON_ERASED_CLEAN_SIBLING")
        action = "review"
    return action, sorted(set(refusals))


def closure_status(row: dict[str, Any], action: str, refusals: list[str]) -> str:
    closure = row.get("closure") or {}
    if not closure.get("claimed_closed"):
        return "NOT_OBSERVABLE"
    rendered = bool(
        action == "overtaken"
        and not refusals
        and closure.get("deployed_sha")
        and set(closure.get("surfaces_checked") or []) == SURFACES
        and closure.get("pinned_card_absent")
        and closure.get("negative_controls_present")
        and closure.get("adjacent_clean")
    )
    return "SHIPPED_GOOD" if rendered else "NOT_OBSERVABLE"


def evaluate_corpus(corpus: dict[str, Any]) -> dict[str, Any]:
    results = []
    for row in corpus["cases"]:
        action, refusals = decide(row)
        status = closure_status(row, action, refusals)
        ok = action == row.get("expected_action") and refusals == sorted(row.get("expected_refusals") or []) and status == row.get("expected_status")
        results.append({"id": row["id"], "ok": ok, "action": action, "refusals": refusals, "status": status})
    return {"total": len(results), "passed": sum(r["ok"] for r in results), "cases": results}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", default=str(FIXTURE))
    args = parser.parse_args()
    report = evaluate_corpus(load_corpus(args.fixture))
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["passed"] == report["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
