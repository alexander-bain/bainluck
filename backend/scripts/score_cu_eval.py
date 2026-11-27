#!/usr/bin/env python3
"""Score a Content Understanding writer run against an answer key (#13901).

Usage:
  # Emit the pre-label placeholder file for /evals:
  python3 scripts/score_cu_eval.py --not-measured-yet --date 2026-11-27 \
    --out ../frontend/lib/evals/data/cu-scorecard-2026-11.json

  # Score a writer run file against an answer key JSON:
  python3 scripts/score_cu_eval.py --answers path/to/answers.json \
    --predictions path/to/predictions.json --date 2026-12-11 \
    --out ../frontend/lib/evals/data/cu-scorecard-2026-12.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from app.utils.cu_eval_scorecard import (  # noqa: E402
    build_unlabeled_scorecard,
    format_scorecard_table,
    score_cu_eval_run,
    write_scorecard_json,
)


def _load_rows(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return payload, {}
    for key in ("rows", "markets", "profiles", "items"):
        rows = payload.get(key)
        if isinstance(rows, list):
            return rows, payload
    raise ValueError(f"Expected list or dict with rows/markets/profiles in {path}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Score a CU evaluation run.")
    parser.add_argument("--not-measured-yet", action="store_true", help="Write pre-label scorecard")
    parser.add_argument("--answers", type=Path, help="Path to human-labeled answer key JSON")
    parser.add_argument("--predictions", type=Path, help="Path to writer output JSON")
    parser.add_argument("--date", required=True, help="Pacific calendar date YYYY-MM-DD")
    parser.add_argument("--dataset", default="sealed", help="Dataset split label (sealed|dev)")
    parser.add_argument("--writer-rev", type=int, default=None, help="Override writer revision")
    parser.add_argument("--model", default=None, help="Override model name")
    parser.add_argument("--cost-usd", type=float, default=None, help="Override total USD spend")
    parser.add_argument("--out", type=Path, default=None, help="Optional output JSON file")
    args = parser.parse_args(argv)

    if args.not_measured_yet:
        scorecard = build_unlabeled_scorecard(
            as_of=args.date,
            writer_rev=args.writer_rev,
            model=args.model,
            dataset=args.dataset,
        )
    else:
        if not args.answers or not args.predictions:
            parser.error("--answers and --predictions are required unless --not-measured-yet is set")
        answer_rows, answer_meta = _load_rows(args.answers)
        pred_rows, pred_meta = _load_rows(args.predictions)
        writer_rev = args.writer_rev if args.writer_rev is not None else pred_meta.get("writer_rev")
        model = args.model or pred_meta.get("model")
        cost = dict(pred_meta.get("cost") or {})
        if "actual_usd" in pred_meta and "total_usd" not in cost:
            cost["total_usd"] = pred_meta["actual_usd"]
        if args.cost_usd is not None:
            cost["total_usd"] = args.cost_usd
        scorecard = score_cu_eval_run(
            answer_rows,
            pred_rows,
            as_of=args.date,
            writer_rev=writer_rev,
            model=model,
            dataset=args.dataset or answer_meta.get("dataset", "sealed"),
            cost=cost or None,
            run_id=pred_meta.get("run_id"),
        )

    print(format_scorecard_table(scorecard))
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        write_scorecard_json(scorecard, str(args.out))
        print(f"\nWrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
