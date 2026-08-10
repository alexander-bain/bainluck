"""Extends feed_card_trust_contract: settlement-authority attack oracle.

The oracle describes the required decision at the winner-write boundary.  The
companion test projects the real resolution_authority module and winner-task SQL
into these decisions; dictionary fixtures alone are not production evidence.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FIXTURES = ROOT / "tests/evals/fixtures/settlement_authority_ladder_contract.json"
TIERS = {
    "pass2_guess": 0,
    "multi_max_prob": 0,
    "clean_resolution": 1,
    "box_score": 2,
    "api_settlement": 3,
    "clob_authoritative": 3,
    "settlement_sync": 3,
}
INDEPENDENT_AUTHORITY = {"api_settlement", "clob_authoritative", "box_score"}
TERMINAL_STATUSES = {"resolved", "closed"}


def load_pack(path: Path = DEFAULT_FIXTURES) -> dict[str, Any]:
    return json.loads(path.read_text())


def evaluate(case: dict[str, Any]) -> dict[str, Any]:
    attack = case["attack"]
    if attack == "overwrite":
        existing = case.get("existing_source")
        incoming = case.get("incoming_source")
        allowed = not existing or TIERS.get(incoming, -1) >= TIERS.get(existing, -1)
        return {
            "guard_bites": not allowed,
            "verdict": "refuse_downgrade" if not allowed else "allow_write",
        }
    if attack == "repair_shield":
        source = case.get("winner_source")
        shields = source in INDEPENDENT_AUTHORITY
        return {
            "guard_bites": shields == case["should_shield_repair"],
            "verdict": "shield" if shields else "repair_eligible",
        }
    if attack == "write_path":
        centralized = case.get("calls_authority_guard") is True
        return {
            "guard_bites": centralized,
            "verdict": "guarded" if centralized else "bypass",
        }
    if attack == "market_status":
        source = case.get("winner_source")
        allowed = case.get("market_status") in TERMINAL_STATUSES or source in {
            "api_settlement", "clob_authoritative"
        }
        return {
            "guard_bites": not allowed,
            "verdict": "clear_premature" if not allowed else "winner_may_stand",
        }
    raise ValueError(f"unknown attack: {attack}")


def evaluate_pack(pack: dict[str, Any]) -> dict[str, Any]:
    rows = []
    for case in pack["cases"]:
        result = evaluate(case)
        mismatches = {
            key: {"expected": value, "actual": result.get(key)}
            for key, value in case["expected"].items()
            if result.get(key) != value
        }
        rows.append({"id": case["id"], **result, "mismatches": mismatches})
    return {
        "contract_version": pack["contract_version"],
        "cases": len(rows),
        "passed": sum(not row["mismatches"] for row in rows),
        "results": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixtures", type=Path, default=DEFAULT_FIXTURES)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = evaluate_pack(load_pack(args.fixtures))
    print(json.dumps(result, indent=2, sort_keys=True) if args.json else
          f"{result['passed']}/{result['cases']} settlement-ladder cases passed")
    return 0 if result["passed"] == result["cases"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
