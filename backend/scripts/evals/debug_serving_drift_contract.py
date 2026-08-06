"""Dependency-free reproductions for debug-versus-serving semantic drift."""

from __future__ import annotations

import json
from pathlib import Path


FIXTURE = Path(__file__).parents[2] / "tests/evals/fixtures/debug_serving_drift_contract.json"


def load_corpus() -> dict:
    return json.loads(FIXTURE.read_text())


def evaluate_case(case: dict) -> dict:
    data = case["input"]
    kind = case["kind"]
    if kind == "expired_ladder_rung":
        diagnostic = max(data["outcomes"], key=lambda row: row["probability"])["name"]
        live = [row for row in data["outcomes"] if not row["expired"]]
        serving = max(live, key=lambda row: row["probability"])["name"] if live else None
    elif kind == "runtime_config":
        diagnostic = data["age_days"] <= data["debug_default_days"]
        serving = data["age_days"] <= data["serving_config_days"]
    elif kind == "stale_hook":
        diagnostic = data["base_score"] + (data["hook_bonus"] if data["hook_present"] else 0)
        serving = data["base_score"] + (
            data["hook_bonus"] if data["hook_present"] and not data["hook_stale"] else 0
        )
    elif kind == "candidate_cache":
        diagnostic = data["market_id"] in data["direct_query_ids"]
        serving = data["market_id"] in data["cached_base_ids"]
    elif kind == "score_adjustments":
        diagnostic = data["base_score"]
        serving = (
            (data["base_score"] + data["llm_adjustment"]) * (1 - data["interest_weight"])
            + data["interestingness_score"] * data["interest_weight"]
        )
    elif kind == "matching_broad_fallback":
        diagnostic = data["match_in_pass1"]
        serving = data["match_in_pass1"] or data["match_in_broad_fallback"]
    elif kind == "matching_candidate_cap":
        diagnostic = data["correct_candidate_position"] <= data["debug_limit"]
        serving = data["correct_candidate_position"] <= data["serving_limit"]
    else:
        raise ValueError(f"unknown drift kind: {kind}")
    return {
        "diagnostic_verdict": diagnostic,
        "serving_verdict": serving,
        "diverged": diagnostic != serving,
        "mismatch_reason": case["expected_mismatch_reason"] if diagnostic != serving else None,
    }


def evaluate_corpus(corpus: dict) -> dict:
    rows = []
    for case in corpus["drift_fixtures"]:
        actual = evaluate_case(case)
        rows.append({"id": case["id"], "passed": actual == case["expected"], "actual": actual})
    return {"total": len(rows), "passed": sum(row["passed"] for row in rows), "cases": rows}


if __name__ == "__main__":
    print(json.dumps(evaluate_corpus(load_corpus()), indent=2, sort_keys=True))
