"""Dependency-free oracle for whether a live probability may be presented now."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path


FIXTURE = Path(__file__).parents[2] / "tests/evals/fixtures/live_probability_freshness_contract.json"


def load_corpus() -> dict:
    return json.loads(FIXTURE.read_text())


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def evaluate_case(case: dict) -> dict:
    now = _dt(case["now"])
    commence = _dt(case["commence_time"])
    status = case["status"].lower()
    status_live = status == "live" and commence <= now

    reasons = []
    probability = None
    if status == "live" and commence > now:
        reasons.append("future_commence_not_live")
    if status_live:
        signal = case.get("signal")
        if not signal or signal.get("probability") is None or not signal.get("observed", False):
            reasons.append("no_current_signal")
        else:
            age = (now - _dt(signal["observed_at"])).total_seconds()
            if age < 0 or age > case["max_signal_age_seconds"]:
                reasons.append("stale_signal")
            else:
                probability = signal["probability"]

    return {
        "display_probability": probability,
        "status_live": status_live,
        "reason_codes": sorted(reasons),
    }


def evaluate_corpus(corpus: dict) -> dict:
    rows = []
    for case in corpus["cases"]:
        actual = evaluate_case(case)
        rows.append({"id": case["id"], "passed": actual == case["expected"], "actual": actual})
    return {"total": len(rows), "passed": sum(row["passed"] for row in rows), "cases": rows}


if __name__ == "__main__":
    print(json.dumps(evaluate_corpus(load_corpus()), indent=2, sort_keys=True))
