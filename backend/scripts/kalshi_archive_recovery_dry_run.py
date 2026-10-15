#!/usr/bin/env python3
"""#683 archive recovery — READ-ONLY dry run. Writes nothing, anywhere.

PILLAR: TRUTH. SHIP: settled Kalshi questions that have no price history get
back their real pre-resolution probability timeline, and archive provenance stays
separate from live capture.

It selects zero-snapshot resolved Kalshi outcomes, reads Kalshi's historical tier
for each one by its EXACT stored ticker, and prints the exact-ID plan
(``app.services.kalshi_archive_recovery``). Each planned point says whether it
could be a calibration FORECAST (the whole candle ends at or before the
authoritative start), READER-ONLY history, or refused. The digest is repeatable.

    python3 scripts/kalshi_archive_recovery_dry_run.py --limit 20 --max-requests 45 \
        --output /tmp/683-plan.json
    python3 scripts/kalshi_archive_recovery_dry_run.py --outcome-ids 101,102 --output ...
    python3 scripts/kalshi_archive_recovery_dry_run.py --after-id <next_after_id> ...

``--outcome-ids`` reads the stored identity WITHOUT the keyset's local backstop
and status filters; the venue's settlement and the provider cutoff choose the
tier. A run that stops mid-outcome reports ``held_outcome`` (listing cursor, or
the unread hourly/minute windows) and does not advance ``next_after_id`` past it.
An outcome planned ``incomplete`` names its ``owed_windows``.

Needs ``DATABASE_URL`` for the candidate read (a read-only transaction) and makes
public Kalshi GETs. ``--apply`` does not exist as a mode. It is refused with exit 2,
and the refusal names the gates that are still unpaid.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

UNPAID_GATES = (
    "provenance/schema decision for where archive rows live (Goal Root)",
    "independent exact-cohort + raw-payload validation (Measurement)",
    "authenticated access + rate budget for the archive endpoints (Measurement)",
    "independent review of the write path, which does not exist yet",
)


def _parse(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument(
        "--limit", type=int, default=20, help="outcomes to plan (hard max 200)"
    )
    p.add_argument(
        "--after-id", type=int, default=0, help="keyset resume: plan outcome ids > this"
    )
    p.add_argument(
        "--outcome-ids", default="", help="comma-separated exact outcome ids"
    )
    p.add_argument(
        "--max-requests",
        type=int,
        default=45,
        help="Kalshi GETs this run (hard max 400)",
    )
    p.add_argument(
        "--pace", type=float, default=1.0, help="seconds between GETs (min 0.5)"
    )
    p.add_argument("--deadline", type=float, default=600.0, help="wall-clock seconds")
    p.add_argument("--output", default="", help="write the full JSON plan here")
    p.add_argument(
        "--apply", action="store_true", help="REFUSED: there is no write path"
    )
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = _parse(argv)
    if args.apply:
        print("REFUSED: this arm has no write path. Unpaid gates:", file=sys.stderr)
        for gate in UNPAID_GATES:
            print(f"  - {gate}", file=sys.stderr)
        return 2
    ids = [int(x) for x in args.outcome_ids.split(",") if x.strip()] or None

    from app.services.kalshi_archive_recovery import plan_archive_recovery

    report = asyncio.run(
        plan_archive_recovery(
            limit=args.limit,
            after_id=args.after_id,
            outcome_ids=ids,
            max_requests=args.max_requests,
            pace_seconds=args.pace,
            deadline_seconds=args.deadline,
        )
    )
    summary = {k: v for k, v in report.items() if k != "plans"}
    print(json.dumps(summary, indent=2, default=str))
    if args.output:
        with open(args.output, "w") as fh:
            json.dump(report, fh, indent=2, default=str)
        print(args.output)
    return 0 if report["terminal"] in ("complete", "partial") else 1


if __name__ == "__main__":
    sys.exit(main())
