"""Fit interestingness component weights against exported human verdicts.

Input may be CSV, JSON, or JSONL. Rows must contain scorer inputs plus either a
binary ``label`` or a label-pass ``decision`` (accepted/rejected promote or
downrank). This script is offline: it never opens the application database.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import itertools
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

BACKEND = Path(__file__).resolve().parents[2]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.utils.market_interestingness import (  # noqa: E402
    DEFAULT_WEIGHTS,
    InterestingnessWeights,
    MarketInterestingnessInputs,
    score_market_interestingness,
)
from scripts.evals.interestingness_temporal_holdout_contract import (  # noqa: E402
    _population_hash,
    evaluate_case,
)

COMPONENTS = tuple(DEFAULT_WEIGHTS.__dataclass_fields__)


def load_rows(path: str | Path) -> list[dict[str, Any]]:
    path = Path(path)
    if path.suffix.lower() == ".csv":
        with path.open(newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle))
    if path.suffix.lower() == ".jsonl":
        with path.open(encoding="utf-8") as handle:
            return [json.loads(line) for line in handle if line.strip()]
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return data
    for key in ("rows", "verdicts", "items"):
        if isinstance(data.get(key), list):
            return data[key]
    raise ValueError(f"No row array found in {path}")


def verdict_label(row: dict[str, Any], label_column: str = "label") -> int | None:
    value = row.get(label_column)
    if value not in (None, ""):
        normalized = str(value).strip().lower()
        if normalized in {"1", "true", "interesting", "love", "positive"}:
            return 1
        if normalized in {"0", "false", "boring", "bad", "kill", "negative"}:
            return 0
        return None
    decision = str(row.get("decision") or row.get("verdict") or "").lower()
    action = str(row.get("action") or row.get("proposed_action") or "").lower()
    if decision in {"accept", "reject"} and action:
        decision = f"{decision}ed_{action}"
    return {
        "accepted_promote": 1,
        "rejected_downrank": 1,
        "accepted_downrank": 0,
        "rejected_promote": 0,
    }.get(decision)


def stable_item_id(row: dict[str, Any], index: int) -> str:
    """A tie-break identity that is NOT the answer key.

    Falls back to the input index only when the row carries no identity at all;
    that keeps the sort total, but a corpus of index-only rows cannot claim
    order-independence, so ``precision_at`` still only ever sorts on this.
    """
    for key in ("id", "market_id", "judgment_id", "item_id"):
        value = row.get(key)
        if value not in (None, ""):
            return str(value)
    return f"idx:{index}"


def signal_rows(
    rows: Iterable[dict[str, Any]], label_column: str = "label"
) -> list[tuple[dict[str, float], int, str]]:
    result = []
    for index, row in enumerate(rows):
        label = verdict_label(row, label_column)
        if label is None:
            continue
        score = score_market_interestingness(MarketInterestingnessInputs.from_mapping(row))
        result.append((score.normalized_signals, label, stable_item_id(row, index)))
    return result


def scores(samples: list[tuple[dict[str, float], int, str]], weights: InterestingnessWeights) -> list[float]:
    total = weights.total or 1.0
    return [sum(signals[name] * getattr(weights, name) for name in COMPONENTS) / total for signals, _, _ in samples]


def auc(labels: list[int], values: list[float]) -> float | None:
    positives = [value for value, label in zip(values, labels) if label]
    negatives = [value for value, label in zip(values, labels) if not label]
    if not positives or not negatives:
        return None
    wins = sum((p > n) + 0.5 * (p == n) for p in positives for n in negatives)
    return wins / (len(positives) * len(negatives))


def precision_at(
    labels: list[int], values: list[float], n: int = 20, item_ids: list[str] | None = None
) -> float | None:
    """Precision@n, ranked score-DESC then stable-id-ASC.

    The label must never participate in the ordering. It used to: ranking bare
    ``(score, label)`` tuples made Python compare element two on a tie and put
    label 1 ahead of label 0, so precision@n was inflated whenever tied scores
    straddled the cutoff — an "improvement" manufacturable with no fitting at
    all (Codex C216).
    """
    if item_ids is None:
        item_ids = [str(index) for index in range(len(values))]
    order = sorted(range(len(values)), key=lambda i: (-values[i], item_ids[i]))[:n]
    return sum(labels[i] for i in order) / len(order) if order else None


def evaluate(samples: list[tuple[dict[str, float], int, str]], weights: InterestingnessWeights, top_n: int = 20) -> dict[str, float | int | None]:
    labels = [label for _, label, _ in samples]
    item_ids = [item_id for _, _, item_id in samples]
    values = scores(samples, weights)
    return {
        "rows": len(samples),
        "positives": sum(labels),
        "auc": auc(labels, values),
        f"precision_at_{top_n}": precision_at(labels, values, top_n, item_ids),
    }


def fit_weights(samples: list[tuple[dict[str, float], int]]) -> InterestingnessWeights:
    """Deterministic coordinate search maximizing AUC, then precision@20."""
    current = {name: getattr(DEFAULT_WEIGHTS, name) for name in COMPONENTS}
    best = InterestingnessWeights(**current)
    best_key = _objective(evaluate(samples, best))
    for step in (10.0, 5.0, 2.0):
        improved = True
        while improved:
            improved = False
            for name, delta in itertools.product(COMPONENTS, (-step, step)):
                candidate = dict(current)
                candidate[name] = max(0.0, candidate[name] + delta)
                trial = InterestingnessWeights(**candidate)
                key = _objective(evaluate(samples, trial))
                if key > best_key:
                    current, best, best_key, improved = candidate, trial, key, True
    return best


def _objective(metrics: dict[str, Any]) -> tuple[float, float]:
    precision_key = next(key for key in metrics if key.startswith("precision_at_"))
    return (metrics["auc"] or -1.0, metrics[precision_key] or -1.0)


LABEL_TIME_KEYS = ("labeled_at", "created_at", "timestamp")


def label_observation_time(row: dict[str, Any]) -> tuple[datetime | None, str | None]:
    """The time the LABEL was observed — never the market's own dates.

    Returns (parsed, which_field). A row whose observation time is missing or
    unparseable belongs to neither partition; it is dropped and counted, never
    defaulted into train.
    """
    for key in LABEL_TIME_KEYS:
        value = row.get(key)
        if value in (None, ""):
            continue
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00")), key
        except (TypeError, ValueError):
            continue
    return None, None


def partition_rows(
    rows: list[dict[str, Any]], cutoff: datetime
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int, str | None]:
    """``labeled_at < cutoff`` -> train; ``>= cutoff`` -> holdout (the exact cutoff is holdout)."""
    train: list[dict[str, Any]] = []
    holdout: list[dict[str, Any]] = []
    dropped = 0
    authority: str | None = None
    for row in rows:
        observed, field = label_observation_time(row)
        if observed is None:
            dropped += 1
            continue
        authority = authority or field
        (train if observed < cutoff else holdout).append(row)
    return train, holdout, dropped, authority


def build_envelope(
    rows: list[dict[str, Any]],
    *,
    cutoff: datetime,
    label_column: str,
    top_n: int,
    floor_points: float = 2.0,
) -> dict[str, Any]:
    """Fit on train ONLY, score baseline and candidate on the identical holdout.

    Emits a claim-gate-ready envelope adjudicated by the C216 oracle
    (``interestingness_temporal_holdout_contract``) rather than a second
    implementation of the same rules.
    """
    train_rows, holdout_rows, dropped, authority = partition_rows(rows, cutoff)

    train_samples = signal_rows(train_rows, label_column)
    holdout_samples = signal_rows(holdout_rows, label_column)

    fitted = fit_weights(train_samples) if len({s[1] for s in train_samples}) >= 2 else DEFAULT_WEIGHTS

    baseline_scores = scores(holdout_samples, DEFAULT_WEIGHTS)
    candidate_scores = scores(holdout_samples, fitted)
    case_rows = [
        {
            "item_id": item_id,
            "label": label,
            "labeled_at": label_observation_time(row)[0].isoformat(),
            "baseline_score": baseline_scores[index],
            "candidate_score": candidate_scores[index],
        }
        for index, ((_, label, item_id), row) in enumerate(zip(holdout_samples, holdout_rows))
    ]
    holdout_hash = _population_hash(case_rows)

    verdict = evaluate_case(
        {
            "cutoff": cutoff.isoformat(),
            "rows": case_rows,
            "top_k": top_n,
            "floor_points": floor_points,
            "min_holdout": top_n,
            "fit_population": "train",
            "evaluation_population": "holdout",
            "time_authority": "labeled_at",
            "baseline_population_hash": holdout_hash,
            "candidate_population_hash": holdout_hash,
        }
    )

    train_ids = sorted(item_id for _, _, item_id in train_samples)
    return {
        "cutoff": cutoff.isoformat(),
        "time_authority_field": authority,
        "train": {"hash": _hash_ids(train_ids), "size": len(train_samples)},
        "holdout": {"hash": holdout_hash, "size": len(holdout_samples)},
        "dropped_no_timestamp": dropped,
        "label_policy": (
            "love|interesting|positive|1|true=1; bad|kill|boring|negative|0|false=0; "
            "fine/neutral excluded"
        ),
        "top_k": top_n,
        "floor_points": floor_points,
        "baseline_p_at_k": verdict.get("baseline_precision_at_k"),
        "candidate_p_at_k": verdict.get("candidate_precision_at_k"),
        "delta_points": verdict.get("delta_points"),
        "verdict": _claim_verdict(verdict),
        "refusal_reasons": verdict.get("reasons", []),
        "recommended_weights": {name: getattr(fitted, name) for name in COMPONENTS},
    }


def _claim_verdict(oracle: dict[str, Any]) -> str:
    """Map the oracle's verdict into the claim vocabulary the ruling uses."""
    if oracle.get("verdict") == "REFUSE":
        return "INSUFFICIENT_EVIDENCE"
    return oracle.get("verdict", "INSUFFICIENT_EVIDENCE")


def _hash_ids(item_ids: list[str]) -> str:
    return hashlib.sha256("\n".join(sorted(item_ids)).encode()).hexdigest()[:16]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input")
    parser.add_argument("--label-column", default="label")
    parser.add_argument("--top-n", type=int, default=20)
    parser.add_argument(
        "--cutoff",
        help=(
            "ISO-8601 label-observation cutoff. Rows before it train, rows at or after it "
            "are the holdout. REQUIRED for any claim — without it this run fits and reports "
            "on the same population and prints no recommendation."
        ),
    )
    parser.add_argument("--floor-points", type=float, default=2.0)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    rows = load_rows(args.input)

    if args.cutoff:
        try:
            cutoff = datetime.fromisoformat(args.cutoff.replace("Z", "+00:00"))
        except ValueError:
            parser.error(f"--cutoff must be ISO-8601, got {args.cutoff!r}")
        envelope = build_envelope(
            rows,
            cutoff=cutoff,
            label_column=args.label_column,
            top_n=args.top_n,
            floor_points=args.floor_points,
        )
        print(json.dumps(envelope, indent=2) if args.json else _format_envelope(envelope))
        return 0 if envelope["verdict"] != "INSUFFICIENT_EVIDENCE" else 1

    samples = signal_rows(rows, args.label_column)
    if not samples or len({label for _, label, _ in samples}) < 2:
        parser.error("input must contain at least one positive and one negative verdict")
    fitted = fit_weights(samples)
    report = {
        "current": evaluate(samples, DEFAULT_WEIGHTS, args.top_n),
        "fitted": evaluate(samples, fitted, args.top_n),
        "recommended_weights": {name: getattr(fitted, name) for name in COMPONENTS},
        "evidence": {
            "input": str(args.input),
            "labeled_rows": len(samples),
            "method": "deterministic coordinate search; optimize AUC then precision@20",
            "verdict": "INSUFFICIENT_EVIDENCE",
            "refusal_reasons": ["NO_TEMPORAL_CUTOFF"],
            "warning": (
                "No --cutoff: weights were selected and scored on the SAME rows. "
                "These numbers are in-sample and support no claim (ruling 016)."
            ),
        },
    }
    print(json.dumps(report, indent=2) if args.json else _format_report(report, args.top_n))
    return 1


def _format_envelope(envelope: dict[str, Any]) -> str:
    lines = [
        "Interestingness temporal-holdout claim envelope",
        f"cutoff:   {envelope['cutoff']}  (authority: {envelope['time_authority_field']})",
        f"train:    n={envelope['train']['size']} hash={envelope['train']['hash']}",
        f"holdout:  n={envelope['holdout']['size']} hash={envelope['holdout']['hash']}",
        f"dropped (no timestamp): {envelope['dropped_no_timestamp']}",
        f"baseline p@{envelope['top_k']}:  {envelope['baseline_p_at_k']}",
        f"candidate p@{envelope['top_k']}: {envelope['candidate_p_at_k']}",
        f"delta:    {envelope['delta_points']} points (floor {envelope['floor_points']})",
        f"VERDICT:  {envelope['verdict']}",
    ]
    if envelope["refusal_reasons"]:
        lines.append("reasons:  " + ", ".join(envelope["refusal_reasons"]))
    if envelope["verdict"] == "INSUFFICIENT_EVIDENCE":
        lines.append("No recommendation printed — this evidence supports no claim.")
    else:
        lines.append("recommended: " + json.dumps(envelope["recommended_weights"], sort_keys=True))
    return "\n".join(lines)


def _format_report(report: dict[str, Any], top_n: int) -> str:
    lines = ["Interestingness calibration", f"Labeled rows: {report['evidence']['labeled_rows']}"]
    for name in ("current", "fitted"):
        metric = report[name]
        lines.append(f"{name}: AUC={metric['auc']:.3f} precision@{top_n}={metric[f'precision_at_{top_n}']:.3f}")
    lines.append("recommended: " + json.dumps(report["recommended_weights"], sort_keys=True))
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
