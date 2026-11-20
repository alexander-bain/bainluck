"""Benchmark and pre-flight helper for the Nightly Fun Scout (#13102, Ruling 276: B).

Usage:
  # 1. Confirm ANTHROPIC_API_KEY_SCOUT is visible without printing it:
  python3 scripts/run_fun_scout_benchmark_13102.py --check-key

  # 2. Print mandatory Decide 61-A pre-run spend estimates (no model calls):
  python3 scripts/run_fun_scout_benchmark_13102.py --estimate-only --title-count 4400

  # 3. Run Sonnet vs Opus against a frozen Nov 19 titles fixture and compare
  #    their proposed sets against Fable's 17 hand-made seed sets:
  python3 scripts/run_fun_scout_benchmark_13102.py --fixture /path/to/nov19_titles.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services.llm_models import CLAUDE_OPUS_MODEL, CLAUDE_SONNET_MODEL
from app.utils.discover_fun_scout import (
    SCOUT_ANTHROPIC_API_KEY_ENV,
    ScoutMarketRow,
    ScoutUncoveredFamily,
    build_scout_anthropic_client,
    build_scout_openai_client,
    check_scout_anthropic_key_status,
    estimate_fun_scout_spend,
    evaluate_scout_against_seed_sets,
    format_fun_scout_pre_run_spend_line,
    run_nightly_fun_scout,
)


def _parse_dt(raw: Any) -> datetime | None:
    if not raw or not isinstance(raw, str):
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def load_titles_fixture(path: Path) -> tuple[list[ScoutMarketRow], list[ScoutUncoveredFamily]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    markets = [
        ScoutMarketRow(
            market_id=int(m["market_id"]),
            source=str(m.get("source") or ""),
            title=str(m.get("title") or ""),
            status=str(m.get("status") or "open"),
            category=m.get("category"),
            resolution_date=_parse_dt(m.get("resolution_date")),
            volume=float(m["volume"]) if m.get("volume") is not None else None,
            volume_24h=float(m["volume_24h"]) if m.get("volume_24h") is not None else None,
            canonical_market_key=m.get("canonical_market_key"),
            group_id=m.get("group_id"),
            market_metadata=m.get("market_metadata"),
            event_date=m.get("event_date"),
        )
        for m in raw.get("markets") or []
    ]
    families = [
        ScoutUncoveredFamily(
            family_key=str(f.get("family_key") or ""),
            sample_title=str(f.get("sample_title") or ""),
            open_count=int(f.get("open_count") or 0),
            source=f.get("source"),
        )
        for f in raw.get("uncovered_families") or []
    ]
    return markets, families


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fun Scout #13102 preflight and benchmark")
    parser.add_argument(
        "--check-key",
        action="store_true",
        help=f"Print only whether {SCOUT_ANTHROPIC_API_KEY_ENV} is set and its length.",
    )
    parser.add_argument(
        "--estimate-only",
        action="store_true",
        help="Print pre-run spend lines for both registered Claude models without calling any API.",
    )
    parser.add_argument("--title-count", type=int, default=4400)
    parser.add_argument("--prior-month-usd", type=float, default=0.0)
    parser.add_argument("--fixture", type=Path, default=None)
    parser.add_argument(
        "--models",
        nargs="+",
        default=[CLAUDE_SONNET_MODEL, CLAUDE_OPUS_MODEL],
    )
    args = parser.parse_args(argv)

    if args.check_key:
        status = check_scout_anthropic_key_status()
        is_configured = bool(status["is_set"])
        char_count = int(status["length"])
        if is_configured:
            sys.stdout.write(f"set, {char_count:d} characters\n")
            return 0
        sys.stdout.write("not set\n")
        return 1

    if args.estimate_only:
        for model in args.models:
            est = estimate_fun_scout_spend(
                args.title_count,
                set_model=model,
                prior_monthly_spend_usd=args.prior_month_usd,
            )
            print(format_fun_scout_pre_run_spend_line(est))
        return 0

    if args.fixture is None:
        parser.error("Provide --fixture <path>, --check-key, or --estimate-only.")

    markets, families = load_titles_fixture(args.fixture)
    openai_client = build_scout_openai_client()
    anthropic_client = build_scout_anthropic_client()

    prior = args.prior_month_usd
    for model in args.models:
        os.environ["LLM_MODEL_FUN_SCOUT_SETS"] = model
        run = run_nightly_fun_scout(
            markets,
            families,
            openai_client=openai_client,
            anthropic_client=anthropic_client,
            prior_monthly_spend_usd=prior,
        )
        prior += float(run["actual_total_cost_usd"])
        eval_report = evaluate_scout_against_seed_sets(run["validated_sets"])
        print(f"\n=== Model: {model} ===")
        print(run["spend_line"])
        print(
            f"Actual cost: ${run['actual_total_cost_usd']:.4f} "
            f"(tag=${run['actual_tag_cost_usd']:.4f}, sets=${run['actual_set_cost_usd']:.4f})"
        )
        print(
            f"Rebuilt {eval_report['matched_seed_count']}/{eval_report['seed_group_count']} "
            f"hand-made seed sets; {len(eval_report['novel_scout_sets'])} novel sets; "
            f"{len(run['rejected_sets'])} rejected by code checks."
        )
        for v in run["validated_sets"]:
            print(f"  - [{v.look}] {v.name} ({v.slug}, {len(v.members)} live): {v.why_better_together}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
