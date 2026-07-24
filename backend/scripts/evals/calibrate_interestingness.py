"""Fit interestingness component weights against exported human verdicts.

Input may be CSV, JSON, or JSONL. Rows must contain scorer inputs plus either a
binary ``label`` or a label-pass ``decision`` (accepted/rejected promote or
downrank). This script is offline: it never opens the application database.
"""

from __future__ import annotations

import argparse
import csv
import itertools
import json
import sys
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


def signal_rows(rows: Iterable[dict[str, Any]], label_column: str = "label") -> list[tuple[dict[str, float], int]]:
    result = []
    for row in rows:
        label = verdict_label(row, label_column)
        if label is None:
            continue
        score = score_market_interestingness(MarketInterestingnessInputs.from_mapping(row))
        result.append((score.normalized_signals, label))
    return result


def scores(samples: list[tuple[dict[str, float], int]], weights: InterestingnessWeights) -> list[float]:
    total = weights.total or 1.0
    return [sum(signals[name] * getattr(weights, name) for name in COMPONENTS) / total for signals, _ in samples]


def auc(labels: list[int], values: list[float]) -> float | None:
    positives = [value for value, label in zip(values, labels) if label]
    negatives = [value for value, label in zip(values, labels) if not label]
    if not positives or not negatives:
        return None
    wins = sum((p > n) + 0.5 * (p == n) for p in positives for n in negatives)
    return wins / (len(positives) * len(negatives))


def precision_at(labels: list[int], values: list[float], n: int = 20) -> float | None:
    ranked = sorted(zip(values, labels), reverse=True)[:n]
    return sum(label for _, label in ranked) / len(ranked) if ranked else None


def evaluate(samples: list[tuple[dict[str, float], int]], weights: InterestingnessWeights, top_n: int = 20) -> dict[str, float | int | None]:
    labels = [label for _, label in samples]
    values = scores(samples, weights)
    return {"rows": len(samples), "positives": sum(labels), "auc": auc(labels, values), f"precision_at_{top_n}": precision_at(labels, values, top_n)}


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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input")
    parser.add_argument("--label-column", default="label")
    parser.add_argument("--top-n", type=int, default=20)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    samples = signal_rows(load_rows(args.input), args.label_column)
    if not samples or len({label for _, label in samples}) < 2:
        parser.error("input must contain at least one positive and one negative verdict")
    fitted = fit_weights(samples)
    report = {
        "current": evaluate(samples, DEFAULT_WEIGHTS, args.top_n),
        "fitted": evaluate(samples, fitted, args.top_n),
        "recommended_weights": {name: getattr(fitted, name) for name in COMPONENTS},
        "evidence": {"input": str(args.input), "labeled_rows": len(samples), "method": "deterministic coordinate search; optimize AUC then precision@20"},
    }
    print(json.dumps(report, indent=2) if args.json else _format_report(report, args.top_n))
    return 0


def _format_report(report: dict[str, Any], top_n: int) -> str:
    lines = ["Interestingness calibration", f"Labeled rows: {report['evidence']['labeled_rows']}"]
    for name in ("current", "fitted"):
        metric = report[name]
        lines.append(f"{name}: AUC={metric['auc']:.3f} precision@{top_n}={metric[f'precision_at_{top_n}']:.3f}")
    lines.append("recommended: " + json.dumps(report["recommended_weights"], sort_keys=True))
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
