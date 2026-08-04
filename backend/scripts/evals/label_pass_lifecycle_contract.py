"""Dependency-free C143 oracle for lifecycle-safe Label Pass decisions."""
from __future__ import annotations
import argparse, json
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "label-pass-lifecycle-contract/v1"
FIXTURE = Path(__file__).parents[2] / "tests" / "evals" / "fixtures" / "label_pass_lifecycle_contract.json"
TERMINAL = {"resolved", "closed", "settled", "finalized"}

def load_corpus(path: str | Path = FIXTURE) -> dict[str, Any]:
    p = json.loads(Path(path).read_text())
    if p.get("schema_version") != SCHEMA_VERSION: raise ValueError("SCHEMA_VERSION_INVALID")
    rows = p.get("cases")
    if not isinstance(rows, list) or not rows: raise ValueError("CASES_REQUIRED")
    ids = [r.get("id") for r in rows]
    if len(ids) != len(set(ids)) or None in ids: raise ValueError("CASE_IDS_INVALID")
    d = p.get("defaults") or {}; p["cases"] = [{**d, **r} for r in rows]; return p

def pending_decision(r: dict[str, Any]) -> tuple[str, str]:
    if r.get("authority_available") is False: return "quarantine", "authority_unavailable"
    if r.get("superseded"): return "retired", "proposal_superseded"
    if r.get("item_type") == "email" and not r.get("canonical_market_id"): return "retired", "canonical_identity_missing"
    if not r.get("market_exists"): return "retired", "market_missing"
    if r.get("canonical_market_id") != r.get("market_id"): return "retired", "canonical_identity_mismatch"
    if r.get("status") in TERMINAL: return "retired", "lifecycle_terminal"
    if r.get("resolution_date_past"): return "retired", "lifecycle_past"
    if r.get("authoritative_overtaken"): return "retired", "premise_overtaken"
    if r.get("title_or_llm_only_stale"): return "quarantine", "non_authoritative_staleness"
    if r.get("evidence_generation") != r.get("proposal_generation"): return "retired", "generation_mismatch"
    return "actionable", "current"

def post_decision(r: dict[str, Any]) -> dict[str, Any]:
    state, reason = pending_decision(r)
    if r.get("posted_generation") != r.get("proposal_generation"): state, reason = "retired", "posted_generation_mismatch"
    if r.get("duplicate_post"): return {"status":"conflict","reason":"duplicate_verdict","writes":0,"delta":0}
    if r.get("transaction_ok") is False: return {"status":"error","reason":"transaction_failed","writes":0,"delta":0}
    if state != "actionable": return {"status":"conflict","reason":reason,"writes":0,"delta":0}
    verdict = r.get("verdict")
    delta = 8 if verdict == "accept" and r.get("kill_switch_enabled") else (-18 if verdict == "reject" and r.get("kill_switch_enabled") else 0)
    return {"status":"written","reason":"current","writes":1,"delta":max(-20,min(20,delta))}

def evaluate_corpus(c: dict[str, Any]) -> dict[str, Any]:
    out=[]
    for r in c["cases"]:
        p=list(pending_decision(r)); q=post_decision(r); ok=p==r["expected_pending"] and q==r["expected_post"]
        out.append({"id":r["id"],"ok":ok,"pending":p,"post":q})
    return {"total":len(out),"passed":sum(x["ok"] for x in out),"cases":out}

def main() -> int:
    a=argparse.ArgumentParser(); a.add_argument("--fixture",default=str(FIXTURE)); x=a.parse_args(); r=evaluate_corpus(load_corpus(x.fixture)); print(json.dumps(r,indent=2,sort_keys=True)); return 0 if r["total"]==r["passed"] else 1
if __name__ == "__main__": raise SystemExit(main())
