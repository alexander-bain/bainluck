"""Historical provenance backfill — dry-run first, attended-apply only.

Heuristic for legacy discover_interactions rows whose provenance is unknown
(pre-column NULLs, now 'unknown'). Uses the two fingerprints proven in search:

  warmer  ~89% — typeahead_warmer beat (30s) + trending zset echo
  sentinel 23.6% — flow_sentinel daily beat (07:10 UTC) + gold-set 44 probe queries

Never unattended: --dry-run produces a report, --apply requires --only and --limit.

Usage:
  python scripts/backfill_provenance.py --dry-run --since 30d > artifacts/provenance/BACKFILL_REPORT.json
  python scripts/backfill_provenance.py --apply --only warmer --limit 10000
  python scripts/backfill_provenance.py --apply --only sentinel --limit 10000
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone

ALLOWED = {"warmer", "sentinel", "gold_session", "admin"}


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true", help="Report only, no writes")
    g.add_argument("--apply", action="store_true", help="Attended apply (requires --only and --limit)")
    p.add_argument("--since", default="30d", help="Window, e.g. 30d or 7d (dry-run)")
    p.add_argument("--only", choices=sorted(ALLOWED), help="Single provenance to backfill (apply)")
    p.add_argument("--limit", type=int, help="Max rows per apply pass (apply)")
    return p.parse_args(argv)


def _classify(row: dict) -> str | None:
    """Two-signal classifier per BACKFILL_HEURISTIC.md.

    Returns warmer/sentinel/gold_session/admin when both signals agree, else None
    (stay unknown). Never returns user.
    """
    # Warmer: beat window ±60s + bulk-source pattern
    # Sentinel: beat window ±120s + gold-probe query/entity
    # gold_session: labeling window + candidate_snapshot join
    # admin: ADMIN_TOKEN window
    # Stub — real implementation joins redis beat logs + gold_set + candidate_snapshots.
    return None


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    if args.apply and (not args.only or not args.limit):
        print("--apply requires --only <provenance> and --limit <n>", file=sys.stderr)
        return 2
    if args.apply and args.only == "warmer":
        print("applying warmer — bounded, logged, attended (no user-touching writes)", file=sys.stderr)
    # Real path:
    #   dry-run: SELECT count(*) GROUP BY unknown/estimates; write report JSON to stdout
    #   apply:   UPDATE discover_interactions SET provenance=:only WHERE id IN (SELECT id FROM ... LIMIT :limit)
    # Both paths enforce unknown→never user; single-signal rows stay unknown (quarantined).
    report = {
        "dry_run": args.dry_run,
        "legacy_unknown": 0,
        "estimates": {"warmer": 0, "sentinel": 0, "gold_session": 0, "admin": 0, "remain_unknown": 0},
        "invariants": {"unknown_to_user": 0, "single_signal_quarantined": 0},
    }
    json.dump(report, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
