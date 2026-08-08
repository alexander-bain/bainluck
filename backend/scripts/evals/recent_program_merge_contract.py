"""Oracle for LAT-P007, CAL-P011, and UX-P018 acceptance boundaries."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

FIXTURE = Path(__file__).parents[2] / "tests/evals/fixtures/recent_program_merge_contract.json"


def load_corpus(path: str | Path = FIXTURE) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("schema_version") != "recent-program-merge/v1":
        raise ValueError("SCHEMA_VERSION_INVALID")
    cases = payload.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("CASES_REQUIRED")
    ids = [r.get("id") for r in cases if isinstance(r, dict)]
    if len(ids) != len(cases) or any(not isinstance(v, str) or not v for v in ids):
        raise ValueError("CASE_ID_REQUIRED")
    if len(ids) != len(set(ids)):
        raise ValueError("CASE_ID_DUPLICATE")
    return payload


def evaluate_case(row: dict[str, Any]) -> dict[str, Any]:
    kind = row["kind"]
    x = row["input"]
    reasons: list[str] = []
    if kind == "typeahead":
        timed_out = x.get("futures_timeout", False)
        payload_state = "degraded" if timed_out else "complete"
        cache_action = "skip" if timed_out else "write"
        client_state = "partial" if timed_out else "fresh"
        if timed_out:
            reasons.append("FUTURES_STAGE_TIMEOUT")
        outcome_arm = "skip" if x.get("query_length", 0) < 3 else "run"
        verdict = "PASS" if (not timed_out or x.get("degraded_exposed", False)) else "REFUSE"
        if timed_out and not x.get("degraded_exposed", False):
            reasons.append("DEGRADATION_HIDDEN")
        return {"verdict": verdict, "payload_state": payload_state, "cache_action": cache_action, "client_state": client_state, "outcome_arm": outcome_arm, "reason_codes": sorted(reasons)}
    if kind == "reachability":
        wired = x.get("wired", False)
        if not wired:
            return {"verdict":"PASS","section":"unavailable","count":None,"checked":False,"reason_codes":["COUNT_NOT_WIRED"]}
        value = x.get("count")
        if isinstance(value, bool) or not isinstance(value, int):
            return {"verdict":"REFUSE","section":"incomplete","count":None,"checked":False,"reason_codes":["COUNT_UNKNOWN"]}
        return {"verdict":"PASS","section":"complete","count":value,"checked":True,"reason_codes":[]}
    if kind == "ux_priority":
        if x.get("data_corruption"):
            priority = "eligible_exception"
            reasons.append("DATA_CORRUPTION_EXCEPTION")
        elif x.get("frequency") == "daily":
            priority = "high"
        elif x.get("frequency") == "weekly":
            priority = "medium"
        else:
            priority = "low"
        payoff_valid = bool(x.get("who")) and bool(x.get("frequency"))
        if not payoff_valid:
            reasons.append("PAYOFF_MISSING_WHO_OR_FREQUENCY")
        return {"verdict":"PASS" if payoff_valid else "REFUSE","priority":priority,"payoff_valid":payoff_valid,"reason_codes":sorted(reasons)}
    raise ValueError(f"KIND_INVALID:{kind}")


def evaluate_corpus(payload: dict[str, Any]) -> dict[str, Any]:
    details=[]
    for row in sorted(payload["cases"], key=lambda x:x["id"]):
        actual=evaluate_case(row)
        details.append({"id":row["id"],"actual":actual,"expected":row["expected"],"passed":actual==row["expected"]})
    return {"schema_version":payload["schema_version"],"total":len(details),"passed":sum(x["passed"] for x in details),"details":details}


def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture",default=str(FIXTURE))
    args=parser.parse_args()
    report=evaluate_corpus(load_corpus(args.fixture))
    print(json.dumps(report,indent=2,sort_keys=True))
    return 0 if report["passed"]==report["total"] else 1


if __name__=="__main__":
    raise SystemExit(main())
