"""Evaluate Discover ranking against human-label gold sets.

Input rows should come from ``export_discover_labeled_dataset.py`` or a
compatible CSV/JSON/JSONL file. The script is offline-only and computes the
first label-based metrics for ranking changes.

Usage:
    python3 scripts/evaluate_discover_label_gold_set.py --input /tmp/labels.csv
    python3 scripts/evaluate_discover_label_gold_set.py --input labels.jsonl --json
    python3 scripts/evaluate_discover_label_gold_set.py --input labels.csv --top-k 20
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


DEFAULT_TOP_K = 20


def load_rows(path: str | Path) -> list[dict[str, Any]]:
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
        rows = data.get("rows") or data.get("items") or data.get("judgments")
        if isinstance(rows, list):
            return rows
    raise ValueError(f"Unsupported input shape for {path}")


def rank_rows(
    rows: list[dict[str, Any]],
    *,
    rank_column: str = "rank_seen",
    score_column: str = "score_at_review",
) -> list[dict[str, Any]]:
    """Sort rows by known rank, then by score descending."""

    return sorted(
        rows,
        key=lambda row: (
            _rank_value(row.get(rank_column)),
            -(_float_value(row.get(score_column)) or 0.0),
            str(row.get("id") or row.get("judgment_id") or ""),
        ),
    )


def evaluate_gold_set(
    rows: list[dict[str, Any]],
    *,
    top_k: int = DEFAULT_TOP_K,
    rank_column: str = "rank_seen",
    score_column: str = "score_at_review",
) -> dict[str, Any]:
    ranked = rank_rows(rows, rank_column=rank_column, score_column=score_column)
    top_rows = ranked[:top_k]

    tapworthy_rows = [row for row in ranked if _is_tapworthy(row)]
    metrics = {
        "row_count": len(rows),
        "top_k": top_k,
        "rank_column": rank_column,
        "score_column": score_column,
        f"tapworthy_at_{top_k}": _rate(top_rows, _is_tapworthy),
        f"boring_rate_at_{top_k}": _rate(top_rows, _is_boring),
        f"duplicate_family_rate_at_{top_k}": _rate(top_rows, _is_duplicate),
        f"unclear_rate_at_{top_k}": _rate(top_rows, _is_unclear),
        f"bad_explanation_rate_at_{top_k}": _rate(top_rows, _has_bad_explanation),
        f"bad_image_rate_at_{top_k}": _rate(top_rows, _has_bad_image),
        f"broad_appeal_at_{top_k}": _rate(top_rows, _has_broad_appeal),
        f"fixable_interest_rate_at_{top_k}": _rate(top_rows, _has_fixable_interest),
        "tapworthy_total": len(tapworthy_rows),
        f"tapworthy_recall_at_{top_k}": (
            sum(1 for row in top_rows if _is_tapworthy(row)) / len(tapworthy_rows)
            if tapworthy_rows
            else None
        ),
        "label_counts": _counts(rows, "label"),
        "category_counts": _counts(rows, "category"),
        "fixable_interest": summarize_fixable_interest(rows),
        "top_rows": [
            {
                "rank": index + 1,
                "id": row.get("id"),
                "name": row.get("name"),
                "label": row.get("label"),
                "category": row.get("category"),
                "score": row.get(score_column),
                "fix_type": row.get("fix_type"),
            }
            for index, row in enumerate(top_rows)
        ],
    }
    return metrics


def summarize_fixable_interest(rows: list[dict[str, Any]]) -> dict[str, Any]:
    fixable = [row for row in rows if _has_fixable_interest(row)]
    by_type = _counts(fixable, "fix_type", default="unspecified")
    issue_candidates = sum(1 for row in fixable if _bool_value(row.get("create_issue_candidate")))
    high_value = [
        row
        for row in fixable
        if (_float_value(row.get("fixable_interest_score")) or 0) >= 4
    ]
    return {
        "rows": len(fixable),
        "issue_candidates": issue_candidates,
        "high_value_rows": len(high_value),
        "by_fix_type": by_type,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K)
    parser.add_argument("--rank-column", default="rank_seen")
    parser.add_argument("--score-column", default="score_at_review")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    rows = load_rows(args.input)
    metrics = evaluate_gold_set(
        rows,
        top_k=args.top_k,
        rank_column=args.rank_column,
        score_column=args.score_column,
    )
    if args.json:
        print(json.dumps(metrics, indent=2, sort_keys=True))
        return 0

    print("Discover human-label gold-set eval")
    print("=" * 72)
    print(f"Rows: {metrics['row_count']}")
    print(f"Top K: {metrics['top_k']}")
    for key, value in metrics.items():
        if key.endswith(f"_at_{args.top_k}") or key.endswith(f"_rate_at_{args.top_k}"):
            print(f"{key}: {_format_rate(value)}")
    print(f"tapworthy_total: {metrics['tapworthy_total']}")
    print(f"label_counts: {metrics['label_counts']}")
    print(f"fixable_interest: {metrics['fixable_interest']}")
    return 0


def _rate(rows: list[dict[str, Any]], predicate) -> float | None:
    if not rows:
        return None
    return round(sum(1 for row in rows if predicate(row)) / len(rows), 6)


def _is_tapworthy(row: dict[str, Any]) -> bool:
    score = _float_value(row.get("tapworthy_score"))
    if score is not None:
        return score >= 4
    return _norm(row.get("label")) == "love"


def _is_boring(row: dict[str, Any]) -> bool:
    explicit = _bool_or_none(row.get("boring"))
    if explicit is not None:
        return explicit
    return _norm(row.get("label")) in {"bad", "kill"}


def _is_duplicate(row: dict[str, Any]) -> bool:
    if _norm(row.get("duplicate_severity")) in {"minor", "major"}:
        return True
    return "duplicate" in _tags(row)


def _is_unclear(row: dict[str, Any]) -> bool:
    clarity = _norm(row.get("clarity"))
    return bool(clarity and clarity != "clear")


def _has_bad_explanation(row: dict[str, Any]) -> bool:
    return _norm(row.get("explanation_quality")) in {"generic", "misleading", "missing"}


def _has_bad_image(row: dict[str, Any]) -> bool:
    return _norm(row.get("image_fit")) in {"bad", "wrong_entity"}


def _has_broad_appeal(row: dict[str, Any]) -> bool:
    return _norm(row.get("audience_scope")) in {"broad", "category_fan"}


def _has_fixable_interest(row: dict[str, Any]) -> bool:
    return bool(row.get("fix_type") or row.get("would_be_interesting_if"))


def _counts(
    rows: list[dict[str, Any]],
    key: str,
    *,
    default: str = "unknown",
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        value = str(row.get(key) or default)
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _rank_value(value: Any) -> float:
    parsed = _float_value(value)
    if parsed is None or parsed <= 0:
        return 1_000_000
    return parsed


def _float_value(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _bool_or_none(value: Any) -> bool | None:
    if value is None or value == "":
        return None
    return _bool_value(value)


def _bool_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def _tags(row: dict[str, Any]) -> set[str]:
    raw = row.get("reason_tags") or ""
    if isinstance(raw, list):
        return {_norm(tag) for tag in raw if _norm(tag)}
    return {_norm(tag) for tag in str(raw).split(",") if _norm(tag)}


def _norm(value: Any) -> str:
    return str(value or "").strip().lower()


def _format_rate(value: Any) -> str:
    if value is None:
        return "n/a"
    return f"{float(value):.1%}"


if __name__ == "__main__":
    raise SystemExit(main())
