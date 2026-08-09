"""Independent contract for calibration watchdog ledger evidence.

The alert itself must fire even when diagnostic ledger fields are malformed.
Valid phase/stage evidence should survive a malformed sibling where possible.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FIXTURES = ROOT / "tests/evals/fixtures/watchdog_ledger_evidence_contract.json"
DONE = {"complete", "resumed"}


def load_pack(path: Path = DEFAULT_FIXTURES) -> dict[str, Any]:
    return json.loads(path.read_text())


def _phase_rows(phases: Any, *, strict: bool) -> list[dict[str, Any]]:
    if phases is None and strict:
        return []
    if not isinstance(phases, list):
        if strict:
            raise ValueError("phases is not an array")
        return []
    rows = []
    for phase in phases:
        if not isinstance(phase, dict):
            if strict:
                raise ValueError("phase row is not an object")
            continue
        if phase.get("status") in DONE or phase.get("status") is None:
            continue
        rows.append({
            "kind": "phase",
            "name": phase.get("name"),
            "status": phase.get("status"),
            "detail": str(phase.get("detail") or "")[:300],
            "duration_ms": phase.get("duration_ms"),
        })
    return rows


def _stage_rows(stages: Any, *, strict: bool) -> list[dict[str, Any]]:
    if stages is None:
        if strict:
            raise ValueError("stages is JSON null")
        return []
    if not isinstance(stages, dict):
        if strict:
            raise ValueError("stages is not an object")
        return []
    rows = []
    for name, value in stages.items():
        try:
            if isinstance(value, bool):
                raise ValueError
            duration = int(value)
            if duration < 0:
                raise ValueError
        except (TypeError, ValueError, OverflowError):
            if strict:
                raise ValueError(f"stage {name} is not a nonnegative bigint")
            continue
        rows.append({"kind": "stage", "name": f"stage:{name}", "duration_ms": duration})
    return sorted(rows, key=lambda row: (-row["duration_ms"], row["name"]))


def extract(payload: Any, *, current_sql: bool, limit: int = 10) -> dict[str, Any]:
    """Model current all-or-nothing SQL or the fail-soft evidence contract."""
    if not isinstance(payload, dict):
        return {"verdict": "no_evidence", "names": []}
    try:
        phases = _phase_rows(payload.get("phases"), strict=current_sql)
        stages = _stage_rows(payload.get("stages", {}), strict=current_sql)
    except ValueError:
        # _run_context_query catches the SQL error and returns an empty string.
        return {"verdict": "no_evidence", "names": []}
    rows = (phases + stages)[:limit]
    return {
        "verdict": "useful_evidence" if rows else "no_evidence",
        "names": [row["name"] for row in rows],
    }


def evaluate_pack(pack: dict[str, Any]) -> dict[str, Any]:
    results = []
    passed = 0
    for case in pack["cases"]:
        current = extract(case["payload"], current_sql=True, limit=pack["policy"]["row_limit"])
        contract = extract(case["payload"], current_sql=False, limit=pack["policy"]["row_limit"])
        mismatches = []
        if current != case["expected_current"]:
            mismatches.append("CURRENT_MODEL")
        if contract != case["expected_contract"]:
            mismatches.append("CONTRACT_MODEL")
        if not mismatches:
            passed += 1
        results.append({"id": case["id"], "current": current, "contract": contract,
                        "expected_mismatches": mismatches})
    return {"cases": len(results), "passed": passed, "results": results}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixtures", type=Path, default=DEFAULT_FIXTURES)
    args = parser.parse_args()
    result = evaluate_pack(load_pack(args.fixtures))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["passed"] == result["cases"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
