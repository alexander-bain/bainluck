#!/usr/bin/env python3
"""Run one settlement-capture sweep. Queue 392 Item 1 (#2077).

    # rehearse — no probes, no writes, prints the plan and the burn-down
    heroku run:detached -a bainluck python scripts/run_settlement_sweep.py --dry-run

    # the real thing
    heroku run:detached -a bainluck python scripts/run_settlement_sweep.py --budget 2000

    # what did it actually save
    heroku run:detached -a bainluck python scripts/run_settlement_sweep.py --verify-only

RE-RUNNING IS SAFE AND IS THE INTENDED RECOVERY
------------------------------------------------

``--sweep-id`` defaults to ``kalshi-YYYY-MM-DD``, so a second invocation on the same
day resumes the same sweep: markets already captured under that id are excluded by
the candidate query, and a pre-insert guard closes the gap between selection and
write. A run killed at row 400 of 1,202 is recovered by running the identical
command again — no flag to remember, no cleanup, no double-write. That matters here
more than usual: the terminal bucket's deadline is the run's own date, so "start
over tomorrow" is not available.

Pass an explicit ``--sweep-id`` only to deliberately re-probe a population under a
new label; it does NOT bypass the terminal-disposition exclusion, which is a
statement about the source having answered rather than about this run.

RUNS ON A HEROKU ONE-OFF DYNO. The app root there is ``backend/``, so the path is
``scripts/run_settlement_sweep.py`` and ``cd backend &&`` silently no-ops
(``reference_heroku_oneoff_dyno_no_cd_backend``). Use ``run:detached`` and read the
result from the printed JSON in the dyno log or from ``--verify-only`` afterwards —
a non-detached ``heroku run`` aborts on an EPERM rendezvous without executing
(gotcha #48).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.database import async_session_maker  # noqa: E402
from app.services.settlement_sweep_runner import (  # noqa: E402
    DEFAULT_BUDGET,
    DEFAULT_CONCURRENCY,
    TERMINAL_FAILED,
    run_sweep,
    verify_sweep,
)
from app.utils.kalshi_retention import (  # noqa: E402
    CAPTURE_PLANNING_AGE_DAYS,
    MEASURED_ON,
    OBSERVED_PRESENT_MAX_AGE_DAYS,
    OBSERVED_PURGED_MIN_AGE_DAYS,
)
from app.utils.settlement_sweep_plan import TERMINAL_BUCKET  # noqa: E402
from app.utils.settlement_sweep_query import SWEEP_SOURCE, default_sweep_id  # noqa: E402


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--budget",
        type=int,
        default=DEFAULT_BUDGET,
        help=f"markets to probe this run (default {DEFAULT_BUDGET})",
    )
    parser.add_argument(
        "--sweep-id",
        default=None,
        help="override the date-derived sweep id; re-running with the same id resumes",
    )
    parser.add_argument("--source", default=SWEEP_SOURCE)
    parser.add_argument(
        "--concurrency", type=int, default=DEFAULT_CONCURRENCY,
        help=f"concurrent probes (default {DEFAULT_CONCURRENCY})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="plan and census only — no probes, no writes",
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="re-derive the burn-down from the database and exit",
    )
    parser.add_argument("--json", action="store_true", help="emit JSON only")
    return parser.parse_args(argv)


def _print_horizons() -> None:
    print("HORIZONS (all named constants — none of these is a literal in the runner)")
    print(f"  CAPTURE_PLANNING_AGE_DAYS       {CAPTURE_PLANNING_AGE_DAYS:>4}d   "
          "chosen — by when we must ALREADY have captured")
    print(f"  OBSERVED_PRESENT_MAX_AGE_DAYS   {OBSERVED_PRESENT_MAX_AGE_DAYS:>4}d   "
          f"measured {MEASURED_ON} — warn bound")
    print(f"  OBSERVED_PURGED_MIN_AGE_DAYS    {OBSERVED_PURGED_MIN_AGE_DAYS:>4}d   "
          f"measured {MEASURED_ON} — skip-work bound (the SQL window)")
    print()


def _print_buckets(title: str, counts: dict[str, int]) -> None:
    print(f"{title}")
    if not counts:
        print("  (empty)")
        return
    for label in sorted(counts, key=lambda k: (k != TERMINAL_BUCKET, k)):
        marker = "  <- terminal, dies first" if label == TERMINAL_BUCKET else ""
        print(f"  {label:>10s}  {counts[label]:>8,}{marker}")


def _print_report(report_dict: dict) -> None:
    print("=" * 78)
    print(f"SETTLEMENT CAPTURE SWEEP — {report_dict['sweep_id']}")
    print("=" * 78)
    _print_horizons()
    _print_buckets("AT-RISK COHORT (missing winner, inside the skip window)",
                   report_dict["cohort_by_bucket"])
    print()
    _print_buckets("UNCAPTURED — what a sweep can still drain",
                   report_dict["uncaptured_by_bucket"])
    print()
    excl = report_dict["exclusions"]
    print("EXCLUDED FROM THE WORK LIST (never summed — they mean different things)")
    print(f"  already captured this sweep   {excl['already_this_sweep']:>8,}"
          "   (resumability)")
    print(f"  terminal from an earlier sweep{excl['terminal_prior']:>8,}"
          "   (the source has answered)")
    print()
    print(f"fetched {report_dict['fetched']:,}"
          f"{' (FETCH CAP BOUND)' if report_dict['fetch_capped'] else ''}"
          f"  ->  selected {report_dict['selected']:,}"
          f"  ->  captured {report_dict['captured']:,}")
    if report_dict["by_disposition"]:
        print()
        print("DISPOSITIONS")
        for disposition, n in sorted(report_dict["by_disposition"].items()):
            print(f"  {disposition:>20s}  {n:>8,}")
    if report_dict["skipped_by_bucket"]:
        print()
        _print_buckets("LEFT FOR THE NEXT RUN (budget-capped)",
                       report_dict["skipped_by_bucket"])
    print()
    print(f"errors {report_dict['errors']:,}   "
          f"write collisions {report_dict['write_collisions']:,}")
    print(f"TERMINAL: {report_dict['terminal'].upper()} — {report_dict['reason']}")


def _print_verification(v: dict) -> None:
    print("=" * 78)
    print(f"VERIFICATION — {v['sweep_id']}")
    print("=" * 78)
    print(f"captured by this sweep: {v['captured_total']:,}")
    for disposition, n in sorted(v["by_disposition"].items()):
        print(f"  {disposition:>20s}  {n:>8,}")
    print()
    _print_buckets("CAPTURED THIS SWEEP, BY BUCKET", v["captured_by_bucket"])
    print()
    _print_buckets("STILL UNCAPTURED (the burn-down)", v["uncaptured_by_bucket"])
    print()
    verdict = "DRAINED" if v["terminal_bucket_drained"] else "NOT DRAINED"
    print(f"terminal bucket {v['terminal_bucket']}: "
          f"{v['terminal_bucket_uncaptured']:,} uncaptured -> {verdict}")


async def _main(args: argparse.Namespace) -> int:
    now = datetime.now(timezone.utc)
    sweep_id = args.sweep_id or default_sweep_id(now, args.source)

    async with async_session_maker() as session:
        if args.verify_only:
            result = await verify_sweep(
                session, sweep_id=sweep_id, now=now, source=args.source
            )
            print(json.dumps(result, indent=2) if args.json else "", end="")
            if not args.json:
                _print_verification(result)
            # A verification is a read. It reports; it does not pass or fail.
            return 0

        report = await run_sweep(
            session,
            budget=args.budget,
            sweep_id=sweep_id,
            now=now,
            dry_run=args.dry_run,
            source=args.source,
            concurrency=args.concurrency,
        )
        payload = report.to_dict()
        if args.json:
            print(json.dumps(payload, indent=2))
        else:
            _print_report(payload)

        # Only a real loss is a non-zero exit. `no_work` and `partial` are both
        # designed states — a resumable sweep returning partial is behaving as
        # specified — and exiting non-zero on them would train the operator to
        # ignore the exit code, which is the one signal that has to keep meaning
        # something (gotcha #54: 1 is a result, anything else is a story about the
        # harness).
        return 1 if payload["terminal"] == TERMINAL_FAILED else 0


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    return asyncio.run(_main(args))


if __name__ == "__main__":
    sys.exit(main())
