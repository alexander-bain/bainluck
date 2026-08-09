"""Oracle for honest temporal-holdout interestingness claims.

The production fitter may consume this contract when it is taught to separate
weight selection from evaluation.  It deliberately operates on precomputed
baseline/candidate scores, keeping the fixture independent of scorer code.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any


def _time(value: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _rank_key(row: dict[str, Any], score_key: str) -> tuple[float, str]:
    # Stable ID tie-break makes the selected top-k reproducible across input order.
    return (-float(row[score_key]), str(row["item_id"]))


def _precision(rows: list[dict[str, Any]], score_key: str, k: int) -> float | None:
    if not rows:
        return None
    ranked = sorted(rows, key=lambda row: _rank_key(row, score_key))[:k]
    return sum(int(row["label"]) for row in ranked) / len(ranked)


def _population_hash(rows: list[dict[str, Any]]) -> str:
    material = "\n".join(sorted(str(row["item_id"]) for row in rows))
    return hashlib.sha256(material.encode()).hexdigest()[:16]


def evaluate_case(case: dict[str, Any]) -> dict[str, Any]:
    cutoff = _time(case.get("cutoff"))
    reasons: set[str] = set()
    if cutoff is None:
        return {"verdict": "REFUSE", "reasons": ["INVALID_CUTOFF"]}

    train: list[dict[str, Any]] = []
    holdout: list[dict[str, Any]] = []
    for row in case.get("rows", []):
        observed = _time(row.get("labeled_at"))
        if observed is None:
            reasons.add("INVALID_LABEL_TIME")
            continue
        if row.get("label") not in (0, 1):
            reasons.add("INVALID_LABEL")
            continue
        try:
            float(row["baseline_score"])
            float(row["candidate_score"])
        except (KeyError, TypeError, ValueError):
            reasons.add("INVALID_SCORE")
            continue
        (train if observed < cutoff else holdout).append(row)

    train_ids = {str(row["item_id"]) for row in train}
    holdout_ids = {str(row["item_id"]) for row in holdout}
    if train_ids & holdout_ids:
        reasons.add("ITEM_LEAKAGE")
    if len(holdout) < int(case.get("min_holdout", 20)):
        reasons.add("HOLDOUT_TOO_SMALL")
    if len({row["label"] for row in holdout}) < 2:
        reasons.add("HOLDOUT_ONE_CLASS")
    if case.get("fit_population") != "train":
        reasons.add("FIT_NOT_TRAIN_ONLY")
    if case.get("evaluation_population") != "holdout":
        reasons.add("EVAL_NOT_HOLDOUT_ONLY")
    if case.get("time_authority") != "labeled_at":
        reasons.add("WRONG_TIME_AUTHORITY")

    expected_hash = _population_hash(holdout)
    if case.get("baseline_population_hash") != expected_hash:
        reasons.add("BASELINE_POPULATION_MISMATCH")
    if case.get("candidate_population_hash") != expected_hash:
        reasons.add("CANDIDATE_POPULATION_MISMATCH")

    k = int(case.get("top_k", 20))
    baseline = _precision(holdout, "baseline_score", k)
    candidate = _precision(holdout, "candidate_score", k)
    delta_points = None if baseline is None or candidate is None else round((candidate - baseline) * 100, 6)
    floor = float(case.get("floor_points", 2.0))
    if not reasons and delta_points is not None and delta_points < floor:
        verdict = "NO_MEANINGFUL_CHANGE"
    elif reasons:
        verdict = "REFUSE"
    else:
        verdict = "IMPROVEMENT"
    return {
        "verdict": verdict,
        "reasons": sorted(reasons),
        "train_rows": len(train),
        "holdout_rows": len(holdout),
        "holdout_population_hash": expected_hash,
        "baseline_precision_at_k": baseline,
        "candidate_precision_at_k": candidate,
        "delta_points": delta_points,
    }


def evaluate_corpus(pack: dict[str, Any]) -> list[dict[str, Any]]:
    return [{"id": case["id"], **evaluate_case(case)} for case in pack["cases"]]
