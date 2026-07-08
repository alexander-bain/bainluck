"""Calibration harness for market interestingness scoring (#142/RANK-2).

Scores CSV/JSON/JSONL rows — or the Discover human-label gold set pulled
directly from the DB (``--from-db``, via ``export_discover_labeled_dataset``) —
against the pure ``market_interestingness`` scorer, and can grid-search weight
vectors against the labels. This is the previously-missing connector between the
pure scorer and the gold set: the two halves were built but never wired.

Label vocabulary: understands both the binary ``interesting/boring`` form and the
gold-set ``love/fine/bad/kill`` form (``love`` = positive, ``bad``/``kill`` =
negative, ``fine`` = neutral/excluded), matching the gold-set predicates in
``evaluate_discover_label_gold_set``.

Usage:
    python3 scripts/calibrate_interestingness.py --input labels.csv
    python3 scripts/calibrate_interestingness.py --from-db --days 90 --json
    python3 scripts/calibrate_interestingness.py --from-db --grid-search
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
    DEFAULT_WEIGHTS,
    InterestingnessWeights,
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


def score_rows(
    rows: list[dict[str, Any]],
    *,
    weights: InterestingnessWeights = DEFAULT_WEIGHTS,
) -> list[dict[str, Any]]:
    """Score rows and append deterministic score details."""

    scored = []
    for index, row in enumerate(rows):
        result = score_market_interestingness(
            MarketInterestingnessInputs.from_mapping(row),
            weights=weights,
        )
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


def load_gold_set_from_db(
    *,
    days: int,
    surface: str | None,
    reviewer: str | None,
    labels: tuple[str, ...] | None,
) -> list[dict[str, Any]]:
    """Pull the human-label gold set straight from the DB (the missing wiring).

    Reuses ``export_discover_labeled_dataset.export_rows`` so the calibrator and
    the exporter share one query and one field schema.
    """
    import asyncio
    from datetime import datetime, timedelta, timezone

    from app.services.database import async_session_maker
    from scripts.export_discover_labeled_dataset import export_rows

    since = datetime.now(timezone.utc) - timedelta(days=days)

    async def _load() -> list[dict[str, Any]]:
        async with async_session_maker() as db:
            return await export_rows(
                db,
                since=since,
                limit=5000,
                surface=surface,
                reviewer=reviewer,
                labels=labels,
            )

    return asyncio.run(_load())


def candidate_weight_grid() -> list[tuple[str, InterestingnessWeights]]:
    """A small, human-readable weight grid to search against labels."""
    return [
        ("default", DEFAULT_WEIGHTS),
        (
            "movement_heavy",
            InterestingnessWeights(
                decisiveness=10, multi_source=8, recency=12, movement=28,
                resolution_proximity=12, category_novelty=8, volume=12, llm_quality=10,
            ),
        ),
        (
            "volume_heavy",
            InterestingnessWeights(
                decisiveness=10, multi_source=10, recency=10, movement=12,
                resolution_proximity=10, category_novelty=8, volume=30, llm_quality=10,
            ),
        ),
        (
            "quality_heavy",
            InterestingnessWeights(
                decisiveness=12, multi_source=8, recency=10, movement=14,
                resolution_proximity=10, category_novelty=10, volume=12, llm_quality=24,
            ),
        ),
        (
            "resolution_heavy",
            InterestingnessWeights(
                decisiveness=10, multi_source=8, recency=10, movement=14,
                resolution_proximity=28, category_novelty=8, volume=12, llm_quality=10,
            ),
        ),
    ]


def run_grid_search(
    rows: list[dict[str, Any]],
    *,
    label_column: str = "label",
    top_n: int = 20,
) -> list[dict[str, Any]]:
    """Score each weight vector against the labels; rank by positive/negative separation."""
    results = []
    for name, weights in candidate_weight_grid():
        scored = score_rows(rows, weights=weights)
        metrics = evaluate_labeled_rows(scored, label_column=label_column, top_n=top_n)
        pos = metrics["positive_average_score"]
        neg = metrics["negative_average_score"]
        results.append(
            {
                "config": name,
                "separation": round(pos - neg, 3),
                "positive_average": round(pos, 3),
                "negative_average": round(neg, 3),
                f"precision_at_{top_n}": metrics[f"precision_at_{top_n}"],
                f"recall_at_{top_n}": metrics[f"recall_at_{top_n}"],
                "labeled_rows": metrics["labeled_rows"],
            }
        )
    results.sort(key=lambda item: item["separation"], reverse=True)
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", help="CSV, JSON, or JSONL rows to score")
    parser.add_argument(
        "--from-db",
        action="store_true",
        help="Pull the human-label gold set directly from the DB",
    )
    parser.add_argument("--days", type=int, default=90)
    parser.add_argument("--surface")
    parser.add_argument("--reviewer")
    parser.add_argument("--label", action="append", help="Filter by label; repeatable.")
    parser.add_argument("--label-column", default="label")
    parser.add_argument("--top-n", type=int, default=20)
    parser.add_argument(
        "--grid-search",
        action="store_true",
        help="Search weight vectors against the labels",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON output")
    args = parser.parse_args()

    if args.from_db:
        rows = load_gold_set_from_db(
            days=args.days,
            surface=args.surface,
            reviewer=args.reviewer,
            labels=tuple(args.label) if args.label else None,
        )
    elif args.input:
        rows = load_rows(args.input)
    else:
        print("No input. Pass --input <file> or --from-db.")
        return 0

    if args.grid_search:
        grid = run_grid_search(rows, label_column=args.label_column, top_n=args.top_n)
        if args.json:
            print(json.dumps({"grid": grid, "rows": len(rows)}, indent=2))
            return 0
        print("Interestingness weight grid search")
        print(f"Rows: {len(rows)}")
        print(f"{'config':<18}{'separation':>12}{'pos_avg':>10}{'neg_avg':>10}{'prec':>8}")
        for entry in grid:
            print(
                f"{entry['config']:<18}"
                f"{entry['separation']:>12.3f}"
                f"{entry['positive_average']:>10.3f}"
                f"{entry['negative_average']:>10.3f}"
                f"{_format_optional(entry[f'precision_at_{args.top_n}']):>8}"
            )
        return 0

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
    """Return True (positive), False (negative), or None (neutral/unlabeled).

    Understands the binary interesting/boring form AND the gold-set
    ``love/fine/bad/kill`` vocabulary (``love`` positive; ``bad``/``kill``
    negative; ``fine`` neutral) — mirroring the gold-set predicates in
    evaluate_discover_label_gold_set so the two agree on what "tapworthy" means.
    """
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value > 0
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "y", "interesting", "positive", "love"}:
        return True
    if normalized in {"0", "false", "no", "n", "boring", "negative", "bad", "kill"}:
        return False
    if normalized in {"fine", "neutral", "ok", "meh"}:
        return None
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
