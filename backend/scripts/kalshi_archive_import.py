#!/usr/bin/env python3
"""#683 archive import — ATTENDED. Dry-run unless ``--write`` is given.

PILLAR: TRUTH. SHIP: a settled Kalshi question with missing history gains its
real recoverable pre-resolution probability journey on web and native, with
archive provenance and honest forecast eligibility.

Takes a plan written by ``kalshi_archive_recovery_dry_run.py --output`` and
imports it into the archive store (``app.services.kalshi_archive_apply``).

    # what WOULD be written, nothing is (read-only transaction):
    python3 scripts/kalshi_archive_import.py apply --plan /tmp/683-plan.json \\
        --expected-digest <plan_digest printed by the dry run>
    # the attended write, same command plus --write:
    python3 scripts/kalshi_archive_import.py apply --plan ... --expected-digest ... --write
    # undo exactly one import's own rows (dry-run first, then --write):
    python3 scripts/kalshi_archive_import.py restore --import-key <key> [--write]
    # cohort accounting for named outcomes (read-only):
    python3 scripts/kalshi_archive_import.py cohort --outcome-ids 101,102

``--expected-digest`` is the plan's content address and must be typed, not
read from the file: the apply refuses when it differs from the digest it
recomputes from the plan's points. Running ``--write`` against production is an
attended action under the existing approval gate. Nothing here schedules
itself, enables a reader or changes the Accuracy curve.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _parse(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("apply", help="dry-run (default) or apply one plan")
    a.add_argument("--plan", required=True, help="the dry run's --output JSON")
    a.add_argument("--expected-digest", required=True, help="the plan's digest, typed")
    a.add_argument("--write", action="store_true", help="actually write (attended)")
    a.add_argument("--output", default="", help="write the full result JSON here")
    r = sub.add_parser("restore", help="remove one import's own rows")
    r.add_argument("--import-key", required=True)
    r.add_argument("--write", action="store_true", help="actually delete (attended)")
    r.add_argument(
        "--allow-applying",
        action="store_true",
        help="restore an import whose apply never finished (its process is gone)",
    )
    c = sub.add_parser("cohort", help="zero-snapshot cohort vs archive history")
    c.add_argument("--outcome-ids", required=True, help="comma-separated ids")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = _parse(argv)
    from app.services import kalshi_archive_apply as imp

    if args.cmd == "apply":
        with open(args.plan) as fh:
            report = json.load(fh)
        try:
            result = asyncio.run(
                imp.apply_archive_plan(
                    report, expected_digest=args.expected_digest, write=args.write
                )
            )
        except imp.PlanRefused as e:
            print(f"REFUSED: {e.reason}", file=sys.stderr)
            return 2
        summary = {k: v for k, v in result.items() if k != "outcomes"}
        print(json.dumps(summary, indent=2, default=str))
        if args.output:
            with open(args.output, "w") as fh:
                json.dump(result, fh, indent=2, default=str)
        return 0 if result["status"] == "applied" else 1
    if args.cmd == "restore":
        result = asyncio.run(
            imp.restore_archive_import(
                args.import_key, write=args.write, allow_applying=args.allow_applying
            )
        )
        print(json.dumps(result, indent=2, default=str))
        return 0 if result["refused"] is None else 1
    ids = [int(x) for x in args.outcome_ids.split(",") if x.strip()]
    print(json.dumps(asyncio.run(imp.archive_cohort(ids)), indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
