"""Offline eval harness for Discover LLM judge labels.

The harness compares precomputed judge outputs against human-labeled rows from
``export_discover_labeled_dataset.py``. It can also export prompt rows for a
separate batch/dry-run workflow. It never calls a live LLM API.

Usage:
    python3 scripts/evaluate_discover_llm_judge.py --human-labels /tmp/labels.csv --judge-labels /tmp/judge.jsonl
    python3 scripts/evaluate_discover_llm_judge.py --human-labels labels.jsonl --prompt-output /tmp/judge_prompts.jsonl
    python3 scripts/evaluate_discover_llm_judge.py --human-labels labels.json --dry-run --json
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.utils.discover_reason_tags import canonical_reason_tags


PROMPT_SCHEMA_VERSION = "discover-llm-judge-v1"

JUDGE_PROMPT_SCHEMA: dict[str, Any] = {
    "version": PROMPT_SCHEMA_VERSION,
    "task": "Judge Discover feed card quality against human-label dimensions.",
    "response_schema": {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "tapworthy",
            "duplicate",
            "clarity",
            "explanation_quality",
            "audience_scope",
            "image_quality",
            "fixable_interest",
            "rationale",
        ],
        "properties": {
            "tapworthy": {"type": "boolean"},
            "duplicate": {"type": "boolean"},
            "clarity": {
                "type": "string",
                "enum": ["clear", "needs_context", "confusing", "misleading"],
            },
            "explanation_quality": {
                "type": "string",
                "enum": ["strong", "adequate", "generic", "missing", "misleading"],
            },
            "audience_scope": {
                "type": "string",
                "enum": ["broad", "category_fan", "niche", "expert_only"],
            },
            "image_quality": {
                "type": "string",
                "enum": ["good", "adequate", "generic", "wrong_entity", "missing"],
            },
            "fixable_interest": {"type": "boolean"},
            "rationale": {"type": "string"},
        },
    },
    "label_semantics": {
        "tapworthy": "true when a casual Discover user would likely tap/open the card.",
        "duplicate": "true when the card substantially duplicates another market/story.",
        "clarity": "clear unless the question/headline needs context, is confusing, or misleads.",
        "explanation_quality": "strong/adequate only when the hook explains why the market matters.",
        "audience_scope": "broad/category_fan for mainstream or category-relevant appeal; niche/expert_only otherwise.",
        "image_quality": "good/adequate only when the image fits the actual subject/entity.",
        "fixable_interest": "true when the underlying idea is promising but needs a better entity, variant, explanation, or image.",
    },
}

LABEL_SPECS: dict[str, dict[str, Any]] = {
    "tapworthiness": {
        "human": lambda row: _human_tapworthy(row),
        "judge": lambda row: _judge_bool(row, ("tapworthy", "tapworthiness", "is_tapworthy")),
    },
    "duplicate": {
        "human": lambda row: _human_duplicate(row),
        "judge": lambda row: _judge_bool(row, ("duplicate", "is_duplicate")),
    },
    "clarity": {
        "human": lambda row: _human_clarity_issue(row),
        "judge": lambda row: _judge_clarity_issue(row),
    },
    "explanation_quality": {
        "human": lambda row: _human_explanation_issue(row),
        "judge": lambda row: _judge_explanation_issue(row),
    },
    "broad_appeal": {
        "human": lambda row: _human_broad_appeal(row),
        "judge": lambda row: _judge_broad_appeal(row),
    },
    "image_quality": {
        "human": lambda row: _human_image_issue(row),
        "judge": lambda row: _judge_image_issue(row),
    },
    "fixable_interest": {
        "human": lambda row: _human_fixable_interest(row),
        "judge": lambda row: _judge_bool(row, ("fixable_interest", "fixable", "interesting_if_fixed")),
    },
}


def load_rows(path: str | Path) -> list[dict[str, Any]]:
    """Load CSV, JSONL, or JSON row files."""

    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".csv":
        with path.open(newline="", encoding="utf-8") as handle:
            return [dict(row) for row in csv.DictReader(handle)]
    if suffix == ".jsonl":
        rows: list[dict[str, Any]] = []
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line:
                    parsed = json.loads(line)
                    rows.append(_ensure_dict(parsed, path))
        return rows

    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if isinstance(data, list):
        return [_ensure_dict(row, path) for row in data]
    if isinstance(data, dict):
        for key in ("rows", "items", "judgments", "results", "data"):
            rows = data.get(key)
            if isinstance(rows, list):
                return [_ensure_dict(row, path) for row in rows]
    raise ValueError(f"Unsupported input shape for {path}")


def build_prompt_row(row: dict[str, Any]) -> dict[str, Any]:
    """Build one JSONL-safe prompt row for offline/batch judge execution."""

    prompt_input = {
        "id": _row_id(row),
        "name": row.get("name") or "",
        "headline": row.get("headline") or "",
        "category": row.get("category") or "",
        "archetype": row.get("archetype") or "",
        "quality_class": row.get("quality_class") or "",
        "source": row.get("source") or "",
        "market_status": row.get("market_status") or "",
        "leader_probability": row.get("leader_probability") or "",
        "movement_24h": row.get("movement_24h") or "",
        "volume_24h": row.get("volume_24h") or "",
        "resolution_date": row.get("resolution_date") or "",
        "image_url": row.get("image_url") or "",
        "hook_description": row.get("hook_description") or "",
    }
    return {
        "custom_id": _row_id(row),
        "prompt_schema_version": PROMPT_SCHEMA_VERSION,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are an offline evaluator for Bain Luck Discover feed cards. "
                    "Return only JSON matching the provided schema."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "schema": JUDGE_PROMPT_SCHEMA["response_schema"],
                        "label_semantics": JUDGE_PROMPT_SCHEMA["label_semantics"],
                        "card": prompt_input,
                    },
                    sort_keys=True,
                ),
            },
        ],
        "metadata": {
            "item_id": str(row.get("item_id") or ""),
            "market_id": str(row.get("market_id") or ""),
            "judgment_id": str(row.get("judgment_id") or ""),
        },
    }


def build_prompt_rows(
    rows: list[dict[str, Any]], *, limit: int | None = None
) -> list[dict[str, Any]]:
    selected = rows[:limit] if limit is not None else rows
    return [build_prompt_row(row) for row in selected]


def write_jsonl(rows: list[dict[str, Any]], path: str | Path) -> None:
    with Path(path).open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def evaluate_judge_outputs(
    human_rows: list[dict[str, Any]],
    judge_rows: list[dict[str, Any]],
    *,
    disagreement_limit: int = 10,
) -> dict[str, Any]:
    human_by_id = {_row_id(row): row for row in human_rows}
    judge_by_id = {_row_id(row): _extract_judge_labels(row) for row in judge_rows}

    metrics = {
        name: _empty_metric()
        for name in LABEL_SPECS
    }
    disagreements: dict[str, dict[str, list[dict[str, Any]]]] = {
        name: {"false_positive": [], "false_negative": []}
        for name in LABEL_SPECS
    }

    for row_id, human in human_by_id.items():
        judge = judge_by_id.get(row_id)
        if judge is None:
            for metric in metrics.values():
                metric["missing_judge"] += 1
            continue

        for name, spec in LABEL_SPECS.items():
            human_value = spec["human"](human)
            judge_value = spec["judge"](judge)
            metric = metrics[name]
            if human_value is None or judge_value is None:
                metric["skipped"] += 1
                continue

            metric["compared"] += 1
            if human_value == judge_value:
                metric["agree"] += 1

            if human_value and judge_value:
                metric["tp"] += 1
            elif not human_value and judge_value:
                metric["fp"] += 1
                _append_disagreement(
                    disagreements[name]["false_positive"],
                    human=human,
                    judge=judge,
                    human_value=human_value,
                    judge_value=judge_value,
                    limit=disagreement_limit,
                )
            elif human_value and not judge_value:
                metric["fn"] += 1
                _append_disagreement(
                    disagreements[name]["false_negative"],
                    human=human,
                    judge=judge,
                    human_value=human_value,
                    judge_value=judge_value,
                    limit=disagreement_limit,
                )
            else:
                metric["tn"] += 1

    finalized = {name: _finalize_metric(metric) for name, metric in metrics.items()}
    return {
        "prompt_schema_version": PROMPT_SCHEMA_VERSION,
        "human_rows": len(human_rows),
        "judge_rows": len(judge_rows),
        "matched_rows": len(set(human_by_id) & set(judge_by_id)),
        "missing_judge_rows": len(set(human_by_id) - set(judge_by_id)),
        "extra_judge_rows": len(set(judge_by_id) - set(human_by_id)),
        "metrics": finalized,
        "disagreement_buckets": disagreements,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--human-labels", "--input", dest="human_labels", required=True)
    parser.add_argument("--judge-labels")
    parser.add_argument("--prompt-output")
    parser.add_argument("--prompt-limit", type=int)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--disagreement-limit", type=int, default=10)
    args = parser.parse_args()

    human_rows = load_rows(args.human_labels)
    if args.prompt_output or args.dry_run:
        prompt_rows = build_prompt_rows(human_rows, limit=args.prompt_limit)
        if args.prompt_output:
            write_jsonl(prompt_rows, args.prompt_output)
        if args.dry_run:
            payload = {
                "prompt_schema": JUDGE_PROMPT_SCHEMA,
                "prompt_rows": prompt_rows,
            }
            print(json.dumps(payload, indent=2, sort_keys=True))
            return 0

    if not args.judge_labels:
        if args.prompt_output:
            print(f"Wrote prompt rows: {args.prompt_output}")
            return 0
        raise SystemExit("--judge-labels is required unless --prompt-output or --dry-run is used")

    judge_rows = load_rows(args.judge_labels)
    results = evaluate_judge_outputs(
        human_rows,
        judge_rows,
        disagreement_limit=args.disagreement_limit,
    )
    if args.json:
        print(json.dumps(results, indent=2, sort_keys=True))
        return 0

    _print_text_report(results)
    return 0


def _print_text_report(results: dict[str, Any]) -> None:
    print("Discover LLM judge eval")
    print("=" * 72)
    print(f"Prompt/schema: {results['prompt_schema_version']}")
    print(f"Human rows: {results['human_rows']}")
    print(f"Judge rows: {results['judge_rows']}")
    print(f"Matched rows: {results['matched_rows']}")
    print(f"Missing judge rows: {results['missing_judge_rows']}")
    print(f"Extra judge rows: {results['extra_judge_rows']}")
    print("")
    print("Metric                 N    Agreement  Precision  Recall   F1")
    for name, metric in results["metrics"].items():
        print(
            f"{name:<22} {metric['compared']:>4}  "
            f"{_format_rate(metric['agreement']):>9}  "
            f"{_format_rate(metric['precision']):>9}  "
            f"{_format_rate(metric['recall']):>6}  "
            f"{_format_rate(metric['f1']):>6}"
        )

    print("")
    print("Disagreement buckets")
    for name, buckets in results["disagreement_buckets"].items():
        fp = len(buckets["false_positive"])
        fn = len(buckets["false_negative"])
        if fp or fn:
            print(f"{name}: false_positive={fp}, false_negative={fn}")


def _empty_metric() -> dict[str, int]:
    return {
        "compared": 0,
        "agree": 0,
        "tp": 0,
        "fp": 0,
        "fn": 0,
        "tn": 0,
        "skipped": 0,
        "missing_judge": 0,
    }


def _finalize_metric(metric: dict[str, int]) -> dict[str, Any]:
    compared = metric["compared"]
    precision = _divide(metric["tp"], metric["tp"] + metric["fp"])
    recall = _divide(metric["tp"], metric["tp"] + metric["fn"])
    return {
        **metric,
        "agreement": _divide(metric["agree"], compared),
        "precision": precision,
        "recall": recall,
        "f1": _f1(precision, recall),
    }


def _append_disagreement(
    bucket: list[dict[str, Any]],
    *,
    human: dict[str, Any],
    judge: dict[str, Any],
    human_value: bool,
    judge_value: bool,
    limit: int,
) -> None:
    if len(bucket) >= limit:
        return
    bucket.append(
        {
            "id": _row_id(human),
            "name": human.get("name") or "",
            "category": human.get("category") or "",
            "human": human_value,
            "judge": judge_value,
            "label": human.get("label") or "",
            "reason_tags": human.get("reason_tags") or "",
            "judge_rationale": judge.get("rationale") or judge.get("reason") or "",
        }
    )


def _row_id(row: dict[str, Any]) -> str:
    for key in ("id", "custom_id", "item_id", "judgment_id", "market_id"):
        value = row.get(key)
        if value not in (None, ""):
            return str(value)
    raise ValueError(f"Row is missing an id: {row}")


def _extract_judge_labels(row: dict[str, Any]) -> dict[str, Any]:
    for key in ("judge_labels", "labels", "output", "result"):
        nested = _jsonish(row.get(key))
        if isinstance(nested, dict):
            return nested

    response = row.get("response")
    if isinstance(response, dict):
        body = response.get("body")
        if isinstance(body, dict):
            choices = body.get("choices")
            if isinstance(choices, list) and choices:
                message = choices[0].get("message") if isinstance(choices[0], dict) else None
                if isinstance(message, dict):
                    parsed = _jsonish(message.get("content"))
                    if isinstance(parsed, dict):
                        return parsed

    return row


def _human_tapworthy(row: dict[str, Any]) -> bool | None:
    score = _float_value(row.get("tapworthy_score"))
    if score is not None:
        return score >= 4
    label = _norm(row.get("label"))
    if label:
        return label in {"love", "great", "tapworthy"}
    return None


def _human_duplicate(row: dict[str, Any]) -> bool:
    severity = _norm(row.get("duplicate_severity"))
    if severity in {"minor", "major", "true", "yes"}:
        return True
    return "duplicate" in _tags(row)


def _human_clarity_issue(row: dict[str, Any]) -> bool | None:
    clarity = _norm(row.get("clarity"))
    if not clarity:
        return None
    return clarity not in {"clear", "good"}


def _human_explanation_issue(row: dict[str, Any]) -> bool | None:
    value = _norm(row.get("explanation_quality"))
    if not value:
        return None
    if value in {"strong", "good", "specific", "adequate"}:
        return False
    return value in {"generic", "missing", "misleading", "bad", "weak"}


def _human_broad_appeal(row: dict[str, Any]) -> bool | None:
    value = _norm(row.get("audience_scope"))
    if not value:
        return None
    if value in {"broad", "category_fan", "mainstream"}:
        return True
    if value in {"niche", "expert", "expert_only", "local"}:
        return False
    return None


def _human_image_issue(row: dict[str, Any]) -> bool | None:
    value = _norm(row.get("image_fit") or row.get("image_quality"))
    if not value:
        return None
    if value in {"good", "relevant", "adequate"}:
        return False
    return value in {"bad", "wrong_entity", "missing", "generic", "weak"}


def _human_fixable_interest(row: dict[str, Any]) -> bool | None:
    has_columns = any(
        key in row
        for key in (
            "fixable_interest_score",
            "fix_type",
            "would_be_interesting_if",
            "create_issue_candidate",
        )
    )
    if not has_columns:
        return None
    score = _float_value(row.get("fixable_interest_score"))
    if score is not None:
        return score >= 3
    return bool(row.get("fix_type") or row.get("would_be_interesting_if"))


def _judge_bool(row: dict[str, Any], keys: tuple[str, ...]) -> bool | None:
    value = _first_value(row, keys)
    if value is None or value == "":
        return None
    return _bool_value(value)


def _judge_clarity_issue(row: dict[str, Any]) -> bool | None:
    value = _norm(_first_value(row, ("clarity", "clarity_quality")))
    if not value:
        return None
    return value not in {"clear", "good"}


def _judge_explanation_issue(row: dict[str, Any]) -> bool | None:
    value = _norm(_first_value(row, ("explanation_quality", "hook_quality")))
    if not value:
        return None
    if value in {"strong", "good", "specific", "adequate"}:
        return False
    return value in {"generic", "missing", "misleading", "bad", "weak"}


def _judge_broad_appeal(row: dict[str, Any]) -> bool | None:
    explicit = _judge_bool(row, ("broad_appeal", "broad_audience"))
    if explicit is not None:
        return explicit
    value = _norm(_first_value(row, ("audience_scope", "audience")))
    if not value:
        return None
    if value in {"broad", "category_fan", "mainstream"}:
        return True
    if value in {"niche", "expert", "expert_only", "local"}:
        return False
    return None


def _judge_image_issue(row: dict[str, Any]) -> bool | None:
    explicit = _judge_bool(row, ("bad_image", "image_issue"))
    if explicit is not None:
        return explicit
    value = _norm(_first_value(row, ("image_quality", "image_fit")))
    if not value:
        return None
    if value in {"good", "relevant", "adequate"}:
        return False
    return value in {"bad", "wrong_entity", "missing", "generic", "weak"}


def _first_value(row: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in row:
            return row.get(key)
    return None


def _tags(row: dict[str, Any]) -> set[str]:
    return set(canonical_reason_tags(row.get("reason_tags")))


def _jsonish(value: Any) -> Any:
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return None
    return value


def _ensure_dict(row: Any, path: Path) -> dict[str, Any]:
    if isinstance(row, dict):
        return row
    raise ValueError(f"Expected object rows in {path}")


def _float_value(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _bool_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def _divide(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return round(numerator / denominator, 6)


def _f1(precision: float | None, recall: float | None) -> float | None:
    if precision is None or recall is None or precision + recall == 0:
        return None
    return round(2 * precision * recall / (precision + recall), 6)


def _norm(value: Any) -> str:
    return str(value or "").strip().lower()


def _format_rate(value: Any) -> str:
    if value is None:
        return "n/a"
    return f"{float(value):.1%}"


if __name__ == "__main__":
    raise SystemExit(main())
