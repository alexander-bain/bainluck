"""Dependency-free contract evaluator for versioned championship-grid registers."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FIXTURES = ROOT / "tests/evals/fixtures/grid_register_contract.json"

REQUIRED_REGISTER_FIELDS = {
    "schema_version", "league", "season", "version", "generated_at", "entries"
}
REQUIRED_ENTRY_FIELDS = {
    "stage", "entity_key", "entity_name", "source", "status", "evidence"
}
TERMINAL_RESULTS = {"won", "eliminated"}


def load_pack(path: Path = DEFAULT_FIXTURES) -> dict[str, Any]:
    return json.loads(path.read_text())


def _iso8601(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def _validate_entry(
    entry: Any,
    *,
    league: str,
    season: str,
    stages: set[str],
    sources: set[str],
) -> list[str]:
    if not isinstance(entry, dict):
        return ["REGISTER_ENTRY_WRONG_SHAPE"]
    findings: list[str] = []
    missing = REQUIRED_ENTRY_FIELDS - entry.keys()
    if missing:
        findings.append("REGISTER_ENTRY_MISSING_FIELDS")
        return findings
    if entry.get("league", league) != league or entry.get("season", season) != season:
        findings.append("CROSS_SEASON_OR_LEAGUE_ENTRY")
    if entry["stage"] not in stages:
        findings.append("UNKNOWN_STAGE")
    if entry["source"] not in sources:
        findings.append("UNKNOWN_SOURCE")
    if entry["status"] not in {"live", "settled", "missing"}:
        findings.append("UNKNOWN_REGISTER_STATUS")
    evidence = entry.get("evidence")
    if not isinstance(evidence, dict) or not evidence.get("kind") or not _iso8601(evidence.get("observed_at")):
        findings.append("INVALID_EVIDENCE")
    if entry["status"] == "missing":
        if entry.get("market_id") is not None or entry.get("outcome_id") is not None:
            findings.append("MISSING_ENTRY_HAS_IDENTITY")
    elif entry.get("market_id") is None or entry.get("outcome_id") is None:
        findings.append("MAPPED_ENTRY_MISSING_IDENTITY")
    if entry["status"] == "settled" and entry.get("terminal_result") not in TERMINAL_RESULTS:
        findings.append("SETTLED_WITHOUT_RESULT")
    return findings


def validate_register(register: Any, contract: dict[str, Any]) -> list[str]:
    if not isinstance(register, dict):
        return ["REGISTER_WRONG_SHAPE"]
    findings: list[str] = []
    if REQUIRED_REGISTER_FIELDS - register.keys():
        return ["REGISTER_MISSING_FIELDS"]
    league = register.get("league")
    league_spec = contract.get("league_contracts", {}).get(league)
    if not league_spec:
        return ["UNKNOWN_LEAGUE"]
    if register.get("schema_version") != contract.get("register_schema_version"):
        findings.append("REGISTER_SCHEMA_MISMATCH")
    if register.get("season") != league_spec.get("season"):
        findings.append("REGISTER_SEASON_MISMATCH")
    if not isinstance(register.get("version"), int) or register["version"] < 1:
        findings.append("INVALID_REGISTER_VERSION")
    if not _iso8601(register.get("generated_at")):
        findings.append("INVALID_GENERATED_AT")
    entries = register.get("entries")
    if not isinstance(entries, list):
        return findings + ["REGISTER_ENTRIES_WRONG_SHAPE"]

    cell_keys: set[tuple[Any, ...]] = set()
    identity_keys: dict[tuple[Any, ...], tuple[Any, ...]] = {}
    for entry in entries:
        findings.extend(_validate_entry(
            entry,
            league=league,
            season=register.get("season"),
            stages=set(league_spec.get("stages", [])),
            sources=set(contract.get("allowed_sources", [])),
        ))
        if not isinstance(entry, dict) or not REQUIRED_ENTRY_FIELDS <= entry.keys():
            continue
        cell = (entry["stage"], entry["entity_key"], entry["source"])
        if cell in cell_keys:
            findings.append("DUPLICATE_CELL_SOURCE")
        cell_keys.add(cell)
        if entry["status"] != "missing":
            identity = (entry["source"], entry.get("market_id"), entry.get("outcome_id"))
            prior = identity_keys.get(identity)
            if prior is not None and prior != cell:
                findings.append("IDENTITY_REUSED_ACROSS_CELLS")
            identity_keys[identity] = cell
    return sorted(set(findings))


def _candidate_findings(case: dict[str, Any], register: dict[str, Any]) -> list[str]:
    findings: list[str] = []
    candidates = case.get("candidates", [])
    if not isinstance(candidates, list):
        return ["CANDIDATES_WRONG_SHAPE"]
    if any(not isinstance(row, dict) for row in candidates):
        return ["POISON_CANDIDATE"]

    for entry in register.get("entries", []):
        if not isinstance(entry, dict) or entry.get("status") == "missing":
            continue
        matches = [row for row in candidates if (
            row.get("stage") == entry.get("stage")
            and row.get("entity_key") == entry.get("entity_key")
            and row.get("source") == entry.get("source")
            and row.get("season") == register.get("season")
        )]
        if len(matches) > 1:
            findings.append("AMBIGUOUS_CANDIDATES")
            continue
        if not matches:
            findings.append("REGISTERED_IDENTITY_NOT_OBSERVED")
            continue
        row = matches[0]
        same_identity = (
            row.get("market_id") == entry.get("market_id")
            and row.get("outcome_id") == entry.get("outcome_id")
        )
        if not same_identity:
            findings.append("IDENTITY_DRIFT_AMBIGUOUS")
        elif row.get("status") == "settled" and entry.get("status") == "live":
            if row.get("terminal_result") not in TERMINAL_RESULTS:
                findings.append("SETTLEMENT_WITHOUT_RESULT")
            else:
                findings.append("UNAMBIGUOUS_SETTLEMENT_DRIFT")
        elif row.get("external_id") != entry.get("external_id"):
            findings.append("UNAMBIGUOUS_RENAME_DRIFT")

    current_season = register.get("season")
    if any(row.get("season") not in (None, current_season) for row in candidates):
        findings.append("NEXT_OR_OTHER_SEASON_CANDIDATE")
    return sorted(set(findings))


def _render_findings(case: dict[str, Any], register: dict[str, Any]) -> list[str]:
    rendered = case.get("rendered", [])
    if not isinstance(rendered, list):
        return ["RENDERED_WRONG_SHAPE"]
    findings: list[str] = []
    by_cell = {
        (e.get("stage"), e.get("entity_key"), e.get("source")): e
        for e in register.get("entries", []) if isinstance(e, dict)
    }
    for row in rendered:
        if not isinstance(row, dict):
            findings.append("POISON_RENDER_CELL")
            continue
        entry = by_cell.get((row.get("stage"), row.get("entity_key"), row.get("source")))
        if entry is None:
            findings.append("UNREGISTERED_RENDER_CELL")
            continue
        status = entry.get("status")
        state = row.get("state")
        probability = row.get("probability")
        if status == "missing" and (state != "missing" or probability is not None):
            findings.append("MISSING_RENDERED_AS_PROBABILITY")
        elif status == "settled":
            if state != entry.get("terminal_result") or probability is not None:
                findings.append("SETTLED_RENDERED_AS_LIVE")
        elif status == "live":
            if state != "live" or not isinstance(probability, (int, float)):
                findings.append("LIVE_RENDER_NOT_NUMERIC")
            elif not 0 <= float(probability) <= 1:
                findings.append("LIVE_PROBABILITY_OUT_OF_RANGE")
    return sorted(set(findings))


def _transition_findings(case: dict[str, Any], register: dict[str, Any]) -> list[str]:
    proposed = case.get("proposed_register")
    if proposed is None:
        return []
    findings = validate_register(proposed, case["contract"])
    if proposed.get("version") != register.get("version", 0) + 1:
        findings.append("NON_MONOTONIC_VERSION")
    if proposed.get("league") != register.get("league") or proposed.get("season") != register.get("season"):
        findings.append("TRANSITION_CHANGED_SCOPE")
    if proposed.get("supersedes_version") != register.get("version"):
        findings.append("MISSING_SUPERSEDES_LINK")
    return sorted(set(findings))


def evaluate_case(case: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    local = dict(case)
    local["contract"] = contract
    register = local.get("register")
    findings = validate_register(register, contract)
    if not findings and isinstance(register, dict):
        findings.extend(_candidate_findings(local, register))
        findings.extend(_transition_findings(local, register))
        # When drift has a proposed next version, the rendered proof must already
        # satisfy that version. This prevents publishing an authoritative
        # settlement while the page still presents the old live probability.
        render_register = local.get("proposed_register") or register
        findings.extend(_render_findings(local, render_register))
    findings = sorted(set(findings))

    hard_invalid = any(f.startswith(("REGISTER_", "INVALID_", "UNKNOWN_", "DUPLICATE_", "IDENTITY_REUSED", "CROSS_")) for f in findings)
    ambiguous = any(f in {
        "AMBIGUOUS_CANDIDATES", "IDENTITY_DRIFT_AMBIGUOUS",
        "NEXT_OR_OTHER_SEASON_CANDIDATE", "REGISTERED_IDENTITY_NOT_OBSERVED",
        "POISON_CANDIDATE",
    } for f in findings)
    unambiguous = any(f in {"UNAMBIGUOUS_RENAME_DRIFT", "UNAMBIGUOUS_SETTLEMENT_DRIFT"} for f in findings)
    render_bad = any(f in {
        "MISSING_RENDERED_AS_PROBABILITY", "SETTLED_RENDERED_AS_LIVE",
        "LIVE_RENDER_NOT_NUMERIC", "LIVE_PROBABILITY_OUT_OF_RANGE",
        "UNREGISTERED_RENDER_CELL", "POISON_RENDER_CELL",
    } for f in findings)

    if hard_invalid:
        classification, action, publish = "invalid", "reject_register", False
    elif ambiguous:
        classification, action, publish = "needs_ruling", "file_p2_needs_triage", False
    elif render_bad:
        classification, action, publish = "render_contract_failure", "block_release", False
    elif unambiguous:
        classification, action = "unambiguous_drift", "publish_new_version"
        publish = local.get("proposed_register") is not None and not _transition_findings(local, register)
    else:
        classification, action, publish = "clean", "no_change", False

    counters = Counter()
    for entry in register.get("entries", []) if isinstance(register, dict) else []:
        if isinstance(entry, dict):
            counters[entry.get("status", "invalid")] += 1
    return {
        "id": case.get("id"),
        "classification": classification,
        "action": action,
        "publish": publish,
        "findings": findings,
        "counters": dict(sorted(counters.items())),
    }


def evaluate_pack(pack: dict[str, Any]) -> dict[str, Any]:
    contract = {
        "register_schema_version": pack.get("register_schema_version"),
        "allowed_sources": pack.get("allowed_sources", []),
        "league_contracts": pack.get("league_contracts", {}),
    }
    results = [evaluate_case(case, contract) for case in pack.get("cases", [])]
    for row, case in zip(results, pack.get("cases", [])):
        expected = case.get("expected", {})
        actual = {key: row.get(key) for key in expected}
        if actual != expected:
            row["findings"] = sorted(set(row["findings"] + ["EXPECTED_OUTCOME_MISMATCH"]))
    return {
        "schema_version": pack.get("schema_version"),
        "cases": len(results),
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixtures", type=Path, default=DEFAULT_FIXTURES)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = evaluate_pack(load_pack(args.fixtures))
    mismatches = [row for row in result["results"] if "EXPECTED_OUTCOME_MISMATCH" in row["findings"]]
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"grid-register contract: {result['cases']} cases, {len(mismatches)} mismatches")
        for row in mismatches:
            print(f"FAIL {row['id']}: {', '.join(row['findings'])}")
    return 1 if mismatches else 0


if __name__ == "__main__":
    raise SystemExit(main())
