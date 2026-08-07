"""Dependency-free oracle for sportsbook snapshot-density health."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any

FIXTURES = Path(__file__).resolve().parents[2] / "tests/evals/fixtures/odds_snapshot_density_contract.json"

def decide(c: dict[str, Any]) -> dict[str, str]:
    if not c.get("eligible", False):
        return {"verdict":"unknown","reason":"not_in_eligible_slate"}
    if not c.get("identity_valid", True):
        return {"verdict":"refuse","reason":"identity_invalid"}
    if c.get("worker_alive") is False or c.get("beat_alive") is False:
        return {"verdict":"red","reason":"poller_dead"}
    if c.get("source_state") in {"error","unknown","quota_blocked"}:
        return {"verdict":"unknown","reason":"source_not_authoritative"}
    if c.get("commit_failed") or c.get("timeout") or c.get("overlap"):
        return {"verdict":"red","reason":"run_not_durable"}
    expected = int(c.get("expected_observations", 0))
    observed = int(c.get("distinct_observation_times", 0))
    if expected <= 0:
        return {"verdict":"unknown","reason":"cadence_expectation_absent"}
    if c.get("last_seen_fresh") and observed >= expected:
        return {"verdict":"green","reason":"fresh_and_dense"}
    if c.get("last_seen_fresh") and c.get("unchanged_readings", 0) >= expected:
        return {"verdict":"green","reason":"fresh_unchanged_market"}
    if c.get("ever_seen") and not c.get("last_seen_fresh"):
        return {"verdict":"red","reason":"capture_stopped"}
    if not c.get("ever_seen"):
        return {"verdict":"unknown","reason":"coverage_unproven"}
    return {"verdict":"red","reason":"observation_density_low"}

def recovery(c: dict[str, Any]) -> dict[str,str]:
    if c.get("history_available") and c.get("identity_valid"):
        return {"verdict":"recoverable","reason":"authoritative_history"}
    if c.get("history_available") is False:
        return {"verdict":"lost","reason":"history_absent"}
    return {"verdict":"refuse","reason":"recovery_unproven"}

def load(): return json.loads(FIXTURES.read_text())
def evaluate(pack):
    rows=[]
    for c in pack["cases"]:
        actual=recovery(c) if c["kind"]=="recovery" else decide(c)
        rows.append({"id":c["id"],"passed":actual==c["expected"],"actual":actual})
    return {"total":len(rows),"passed":sum(r["passed"] for r in rows),"cases":rows}
if __name__ == "__main__": print(json.dumps(evaluate(load()),indent=2,sort_keys=True))
