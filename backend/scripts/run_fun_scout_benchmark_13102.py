"""Benchmark and pre-flight helper for the Nightly Fun Scout (#13102, Ruling 276: B).

Usage:
  # 1. Confirm ANTHROPIC_API_KEY_SCOUT is visible without printing it:
  python3 scripts/run_fun_scout_benchmark_13102.py --check-key

  # 2. Validate the frozen Nov 19 benchmark input and print Decide 61-A
  #    pre-run spend estimates (zero model calls):
  python3 scripts/run_fun_scout_benchmark_13102.py --dry-run

  # 3. Monday comparison (ONLY after Alex's explicit yes — paid API calls):
  #    Runs Sonnet vs Opus against the frozen Nov 19 input and compares their
  #    proposed sets against Fable's 17 hand-made seed sets in one command:
  python3 scripts/run_fun_scout_benchmark_13102.py --execute
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services.llm_models import CLAUDE_OPUS_MODEL, CLAUDE_SONNET_MODEL  # noqa: E402
from app.services.llm_request import JobBudget  # noqa: E402
from app.utils.discover_fun_scout import (  # noqa: E402
    SCOUT_ANTHROPIC_API_KEY_ENV,
    SCOUT_RUN_CAP_USD,
    ScoutMarketRow,
    ScoutUncoveredFamily,
    build_scout_anthropic_client,
    build_scout_openai_client,
    check_scout_member,
    check_scout_anthropic_key_status,
    estimate_fun_scout_spend,
    evaluate_scout_against_seed_sets,
    evaluate_tagging_pass_against_seed_sets,
    format_fun_scout_pre_run_spend_line,
    run_nightly_fun_scout,
    run_scout_tagging_pass,
)
from app.utils.discover_fun_tags import load_fun_markets_registry  # noqa: E402

DEFAULT_BENCHMARK_FIXTURE = (
    BACKEND_DIR / "data" / "discover" / "fun-scout-benchmark-2026-11-19.json"
)


def _parse_dt(raw: Any) -> datetime | None:
    if not raw or not isinstance(raw, str):
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def load_titles_fixture(
    path: Path,
) -> tuple[list[ScoutMarketRow], list[ScoutUncoveredFamily], datetime | None]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    captured_at = _parse_dt(raw.get("captured_at"))
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
    return markets, families, captured_at


def summarize_fixture_dry_run(
    fixture_path: Path,
    *,
    models: list[str],
    prior_month_usd: float = 0.0,
) -> dict[str, Any]:
    """Validate a frozen benchmark input and estimate spend with zero model calls."""
    markets, families, captured_at = load_titles_fixture(fixture_path)
    check_now = captured_at or datetime.now(timezone.utc)
    passing_by_source: Counter[str] = Counter()
    rejected_by_reason: Counter[str] = Counter()
    passing_count = 0
    for row in markets:
        ok, reason = check_scout_member(row, now=check_now)
        if ok:
            passing_count += 1
            passing_by_source[row.source] += 1
        else:
            rejected_by_reason[reason or "rejected"] += 1

    seed_ids = set(load_fun_markets_registry().markets.keys())
    fixture_ids = {m.market_id for m in markets}
    spend_lines: list[str] = []
    combined_est_usd = 0.0
    prior = prior_month_usd
    for idx, model in enumerate(models):
        est = estimate_fun_scout_spend(
            len(markets),
            set_model=model,
            prior_monthly_spend_usd=prior,
        )
        spend_lines.append(format_fun_scout_pre_run_spend_line(est))
        # The benchmark runs the small-model tagging pass once and feeds the
        # exact same tagged candidate list to every Claude model.
        incremental = float(est["estimated_run_cost_usd"]) if idx == 0 else float(est["set_cost_usd"])
        combined_est_usd += incremental
        prior += incremental

    return {
        "fixture": str(fixture_path),
        "captured_at": captured_at.isoformat() if captured_at else None,
        "total_markets": len(markets),
        "passing_code_checks": passing_count,
        "rejected_code_checks": len(markets) - passing_count,
        "passing_by_source": dict(passing_by_source),
        "rejected_by_reason": dict(rejected_by_reason),
        "uncovered_families": len(families),
        "seed_markets_present": len(seed_ids & fixture_ids),
        "seed_markets_total": len(seed_ids),
        "spend_lines": spend_lines,
        "combined_est_usd": round(combined_est_usd, 4),
    }


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
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate the frozen benchmark input and print spend estimates with zero API calls.",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Required to make paid OpenAI + Anthropic benchmark calls (Alex approval required).",
    )
    parser.add_argument("--title-count", type=int, default=3424)
    parser.add_argument("--prior-month-usd", type=float, default=0.0)
    parser.add_argument(
        "--max-estimate-usd",
        type=float,
        default=2.0,
        help="Refuse --execute before any model call if combined pre-run estimate exceeds this USD ceiling.",
    )
    parser.add_argument(
        "--fixture",
        type=Path,
        default=DEFAULT_BENCHMARK_FIXTURE,
        help="Frozen titles fixture (defaults to backend/data/discover/fun-scout-benchmark-2026-11-19.json).",
    )
    parser.add_argument(
        "--models",
        nargs="+",
        default=[CLAUDE_SONNET_MODEL, CLAUDE_OPUS_MODEL],
    )
    parser.add_argument(
        "--dump-tagged-json",
        type=Path,
        default=None,
        help="Optional path to save the first-pass tagged candidates as JSON.",
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

    summary = summarize_fixture_dry_run(
        args.fixture,
        models=list(args.models),
        prior_month_usd=args.prior_month_usd,
    )
    if args.dry_run or not args.execute:
        print(
            f"Fixture ready (dry-run, zero model calls): {summary['fixture']}\n"
            f"  captured_at={summary['captured_at']} total={summary['total_markets']} "
            f"passing={summary['passing_code_checks']} rejected={summary['rejected_code_checks']} "
            f"sources={summary['passing_by_source']}\n"
            f"  seed_markets_present={summary['seed_markets_present']}/{summary['seed_markets_total']} "
            f"combined_est=${summary['combined_est_usd']:.4f}"
        )
        for line in summary["spend_lines"]:
            print(line)
        if not args.dry_run:
            print("Pass --execute after Alex's go to run paid Sonnet vs Opus calls.")
        return 0

    print(
        f"Pre-run estimate: combined_est=${summary['combined_est_usd']:.4f} "
        f"(limit=${args.max_estimate_usd:.2f})"
    )
    for line in summary["spend_lines"]:
        print(line)
    if float(summary["combined_est_usd"]) > float(args.max_estimate_usd):
        sys.stderr.write(
            f"STOP: combined pre-run estimate ${summary['combined_est_usd']:.4f} "
            f"exceeds --max-estimate-usd ${args.max_estimate_usd:.2f}; zero model calls made.\n"
        )
        return 2

    markets, families, captured_at = load_titles_fixture(args.fixture)
    examples = list(load_fun_markets_registry().markets.values())
    openai_client = build_scout_openai_client()
    anthropic_client = build_scout_anthropic_client()

    shared_tag_budget = JobBudget(SCOUT_RUN_CAP_USD)
    tagged, shared_tag_cost = run_scout_tagging_pass(
        markets,
        openai_client=openai_client,
        approved_examples=examples,
        job_budget=shared_tag_budget,
    )
    print(
        f"\nShared tagging pass complete: {len(tagged)} candidates tagged from {len(markets)} markets; "
        f"actual_tag_cost=${shared_tag_cost:.4f}"
    )
    tag_eval = evaluate_tagging_pass_against_seed_sets(tagged, markets)
    print(
        f"First-pass seed survival (unique): {tag_eval['unique_seed_survived']}/"
        f"{tag_eval['unique_seed_in_input']} present "
        f"(of {tag_eval['unique_seed_total']} total):"
    )
    for row in tag_eval["groups"]:
        print(
            f"  * {row['seed_group']}: survived={row['survived_first_pass']}/"
            f"{row['in_input']} in_input (seed={row['seed_size']})"
        )
    if args.dump_tagged_json is not None:
        args.dump_tagged_json.parent.mkdir(parents=True, exist_ok=True)
        args.dump_tagged_json.write_text(
            json.dumps(
                [
                    {
                        "market_id": t.market_id,
                        "fun_group": t.fun_group,
                        "is_fun_single": t.is_fun_single,
                        "set_hint": t.set_hint,
                        "reason": t.reason,
                    }
                    for t in tagged
                ],
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"Saved tagged list to {args.dump_tagged_json}")

    prior = args.prior_month_usd + shared_tag_cost
    total_actual_usd = shared_tag_cost
    prev_model_env = os.environ.get("LLM_MODEL_FUN_SCOUT_SETS")
    try:
        for model in args.models:
            os.environ["LLM_MODEL_FUN_SCOUT_SETS"] = model
            run = run_nightly_fun_scout(
                markets,
                families,
                openai_client=openai_client,
                anthropic_client=anthropic_client,
                approved_examples=examples,
                prior_monthly_spend_usd=prior,
                now=captured_at,
                pretagged=(tagged, 0.0),
            )
            set_cost = float(run["actual_set_cost_usd"])
            prior += set_cost
            total_actual_usd += set_cost
            eval_report = evaluate_scout_against_seed_sets(run["validated_sets"])
            print(f"\n=== Model: {model} ===")
            print(run["spend_line"])
            print(
                f"Actual cost: set_pass=${set_cost:.4f} "
                f"(with shared tag=${shared_tag_cost:.4f} -> standalone_equiv=${shared_tag_cost + set_cost:.4f})"
            )
            print(
                f"Proposed={run['proposed_set_count']} Validated={len(run['validated_sets'])} "
                f"Rejected={len(run['rejected_sets'])} VerifiedSingles={len(run['verified_singles'])}"
            )
            print(
                f"Seed overlap: rebuilt {eval_report['matched_seed_count']}/{eval_report['seed_group_count']} "
                f"hand-made seed sets; {len(eval_report['novel_scout_sets'])} novel sets."
            )
            if eval_report["matched_seed_groups"]:
                print("Matched seed sets:")
                for m in eval_report["matched_seed_groups"]:
                    print(
                        f"  * {m['seed_group']} -> {m['scout_slug']} "
                        f"({m['overlap']}/{m['seed_size']}, recall={m['recall']:.3f})"
                    )
            if eval_report["missed_seed_groups"]:
                print("Missed seed sets: " + ", ".join(eval_report["missed_seed_groups"]))
            print("Validated sets:")
            for v in run["validated_sets"]:
                print(
                    f"  - [{v.look}] {v.name} (slug={v.slug}, category={v.category}, "
                    f"{len(v.members)} live): {v.why_better_together}"
                )
                for member in v.members:
                    print(f"      * {member.market_id} [{member.source}] {member.title}")
            if run["rejected_sets"]:
                print("Rejected sets:")
                for rej in run["rejected_sets"]:
                    print(f"  - {rej.get('name')} ({rej.get('slug')}): {rej.get('reason')}")
    finally:
        if prev_model_env is None:
            os.environ.pop("LLM_MODEL_FUN_SCOUT_SETS", None)
        else:
            os.environ["LLM_MODEL_FUN_SCOUT_SETS"] = prev_model_env
    print(
        f"\n=== Benchmark total actual spend: ${total_actual_usd:.4f} "
        f"(shared_tag=${shared_tag_cost:.4f}, set_passes=${total_actual_usd - shared_tag_cost:.4f}) ==="
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
