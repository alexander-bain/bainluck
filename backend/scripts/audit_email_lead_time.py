"""Audit: did we surface a market before Polymarket's email featured it? (#142)

Uses the candidate-pool snapshot first-surfaced dates (Item 1a) vs the Polymarket
email ground-truth dates. "Beat the email" rate is the timeliness ground truth
and the anti-Kalshi thesis as a number (plan addendum item 1).

Meaningful only once the candidate-pool snapshot has accrued history across the
email window; reports a clear note otherwise.

Usage:
    python3 scripts/audit_email_lead_time.py --days 30
    python3 scripts/audit_email_lead_time.py --json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    from app.services.database import async_session_maker
    from app.utils.discover_candidate_snapshot import compute_email_lead_time

    async def _run():
        async with async_session_maker() as db:
            return await compute_email_lead_time(db, days=args.days)

    metric = asyncio.run(_run())

    if args.json:
        print(json.dumps(metric, indent=2, sort_keys=True))
        return 0

    print("Email lead-time audit (did we beat the email?)")
    print("=" * 60)
    print(f"Window: {metric['window_days']}d")
    print(f"Snapshot markets: {metric['snapshot_markets']}  email items: {metric['email_items']}")
    print(f"Matched: {metric['matched']}")
    if metric["note"]:
        print(f"NOTE: {metric['note']}")
        return 0
    print(f"Beat-email rate: {metric['beat_email_rate']:.1%} "
          f"({metric['beat_email_count']}/{metric['matched']})")
    print(f"Mean lead: {metric['mean_lead_days']}d  median: {metric['median_lead_days']}d")
    print("\nTop lead times (positive = we surfaced first):")
    for row in metric["rows"][:20]:
        print(f"  {row['lead_days']:+4}d  {row['our_name'][:50]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
