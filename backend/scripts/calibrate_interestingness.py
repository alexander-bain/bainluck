"""Lightweight calibration scaffold for market interestingness scoring.

This script intentionally does not read from the database or any external
service. It can score CSV, JSON, or JSONL rows with optional labels so future
ground-truth exports can be evaluated without touching runtime feed ranking.

Usage:
    python3 scripts/calibrate_interestingness.py --input labels.csv
    python3 scripts/calibrate_interestingness.py --input labels.json --json
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.utils.market_interestingness import (  # noqa: E402
    MarketInterestingnessInputs,
    score_market_interestingness,
)


def load_rows(path: str | Path) -> list[dict[str, Any]]:
    """Load candidate rows from CSV, JSON array/object, or JSONL."""

    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".csv":
        with path.open(newline="") as handle:
            return list(csv.DictReader(handle))

    if suffix == ".jsonl":
        rows = []
        with path.open() as handle:
            for line in handle:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
        return rows

    with path.open() as handle:
        data = json.load(handle)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        rows = data.get("rows") or data.get("markets") or data.get("items")
        if isinstance(rows, list):
            return rows
    raise ValueError(f"Unsupported input shape for {path}")


def score_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Score rows and append deterministic score details."""

    scored = []
    for index, row in enumerate(rows):
        result = score_market_interestingness(MarketInterestingnessInputs.from_mapping(row))
        scored.append(
            {
                "index": index,
                "id": row.get("id") or row.get("market_id") or index,
                "name": row.get("name") or row.get("market_name") or "",
                "label": row.get("label"),
                "score": result.score,
                "components": result.components,
                "reasons": result.reasons,
                "row": row,
            }
        )
    scored.sort(key=lambda item: item["score"], reverse=True)
    return scored


def evaluate_labeled_rows(
    scored_rows: list[dict[str, Any]],
    *,
    label_column: str = "label",
    top_n: int = 20,
) -> dict[str, Any]:
    """Compute small ranking metrics when labels are present."""

    labels = []
    for row in scored_rows:
        raw_label = row["row"].get(label_column, row.get("label"))
        label = _parse_label(raw_label)
        if label is not None:
            labels.append((row, label))

    positives = [(row, label) for row, label in labels if label]
    negatives = [(row, label) for row, label in labels if not label]
    top_rows = scored_rows[:top_n]
    top_positive_count = 0
    top_labeled_count = 0
    positive_ids = {id(row) for row, _ in positives}

    for row in top_rows:
        parsed = _parse_label(row["row"].get(label_column, row.get("label")))
        if parsed is None:
            continue
        top_labeled_count += 1
        if id(row) in positive_ids:
            top_positive_count += 1

    return {
        "total_rows": len(scored_rows),
        "labeled_rows": len(labels),
        "positive_rows": len(positives),
        "negative_rows": len(negatives),
        "average_score": _average(row["score"] for row in scored_rows),
        "positive_average_score": _average(row["score"] for row, _ in positives),
        "negative_average_score": _average(row["score"] for row, _ in negatives),
        f"precision_at_{top_n}": (
            top_positive_count / top_labeled_count if top_labeled_count else None
        ),
        f"recall_at_{top_n}": (
            top_positive_count / len(positives) if positives else None
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", help="CSV, JSON, or JSONL rows to score")
    parser.add_argument("--label-column", default="label")
    parser.add_argument("--top-n", type=int, default=20)
    parser.add_argument("--json", action="store_true", help="Print JSON output")
    args = parser.parse_args()

    if not args.input:
        print("No input supplied. Pass --input with CSV, JSON, or JSONL rows.")
        return 0

    rows = load_rows(args.input)
    scored = score_rows(rows)
    metrics = evaluate_labeled_rows(
        scored,
        label_column=args.label_column,
        top_n=args.top_n,
    )

    if args.json:
        print(json.dumps({"metrics": metrics, "top_rows": scored[: args.top_n]}, indent=2))
        return 0

    print("Market interestingness calibration")
    print(f"Rows: {metrics['total_rows']} ({metrics['labeled_rows']} labeled)")
    print(f"Average score: {metrics['average_score']:.2f}")
    if metrics["labeled_rows"]:
        precision_key = f"precision_at_{args.top_n}"
        recall_key = f"recall_at_{args.top_n}"
        print(f"Positive average: {metrics['positive_average_score']:.2f}")
        print(f"Negative average: {metrics['negative_average_score']:.2f}")
        print(f"Precision@{args.top_n}: {_format_optional(metrics[precision_key])}")
        print(f"Recall@{args.top_n}: {_format_optional(metrics[recall_key])}")

    print("\nTop scored rows:")
    for row in scored[: args.top_n]:
        name = row["name"] or row["id"]
        print(f"  {row['score']:6.2f}  {name}")
    return 0


def _parse_label(value: Any) -> bool | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value > 0
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "y", "interesting", "positive"}:
        return True
    if normalized in {"0", "false", "no", "n", "boring", "negative"}:
        return False
    try:
        return float(normalized) > 0
    except ValueError:
        return None


def _average(values: Any) -> float:
    values = list(values)
    if not values:
        return 0.0
    return sum(values) / len(values)


def _format_optional(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.2%}"


if __name__ == "__main__":
    raise SystemExit(main())
