#!/usr/bin/env python3
"""One-off backfill: re-categorize futures markets misclassified as golf.

Background (Queue #34 part 2 / issue #889):
The bare ``\\bgolf\\b`` rule in ``SPORT_PATTERNS`` matched venue names like
"Trump National Golf Club", so politics/legal markets ("How many times will
Trump visit Trump National Golf Club", "Will Trump pardon Tiger Woods") were
filed under golf on the league/browse pages.

The mapping fix lives in ``app.utils.futures_categorization``: a non-sport
override now classifies a political figure performing a civic action as
``politics`` before the incidental sport keyword can win.

This script repairs EXISTING rows. It re-runs ``categorize_by_rules`` over every
market currently stored as ``llm_sport_category = 'golf'`` and rewrites the
category for any row that now resolves to something else. It is safe to re-run
(idempotent) and only touches rows whose recomputed category differs.

Usage:
    cd backend && python3 scripts/fix_misclassified_golf_markets.py [--apply]

Without ``--apply`` it runs in dry-run mode and only prints the proposed
changes. The regular Kalshi/Polymarket polling tasks already re-classify on
their next run for markets that are still actively polled; this script
guarantees the fix lands immediately and covers any rows that have stopped
being polled (e.g. settled Kalshi markets — see gotcha #33).
"""

import argparse
import asyncio
import sys

sys.path.insert(0, ".")

from sqlalchemy import select, update
from sqlalchemy import func

from app.models import FuturesMarket
from app.tasks.base import get_task_session
from app.utils.futures_categorization import categorize_by_rules


async def run(apply: bool) -> None:
    async with get_task_session() as session:
        result = await session.execute(
            select(
                FuturesMarket.id,
                FuturesMarket.name,
                FuturesMarket.external_id,
                FuturesMarket.source,
            ).where(FuturesMarket.llm_sport_category == "golf")
        )
        rows = result.all()
        print(f"Scanning {len(rows)} markets currently classified as 'golf'...")

        changes: list[tuple[int, str, str, str]] = []
        for market_id, name, external_id, source in rows:
            # Recompute WITHOUT a sport_key — these are Kalshi/Polymarket rows
            # categorized from the market name. Passing the stale 'golf' value
            # would defeat the override.
            new_category = categorize_by_rules(name or "")
            if new_category and new_category != "golf":
                changes.append((market_id, name, new_category, f"{source}:{external_id}"))

        if not changes:
            print("No misclassified golf markets found. Nothing to do.")
            return

        print(f"\nFound {len(changes)} misclassified golf market(s):")
        for market_id, name, new_category, src in changes:
            print(f"  [{market_id}] golf -> {new_category}  ({src})  {name}")

        if not apply:
            print("\nDry run. Re-run with --apply to write changes.")
            return

        for market_id, _name, new_category, _src in changes:
            # Core update() — never ORM attribute assignment for category writes.
            await session.execute(
                update(FuturesMarket)
                .where(FuturesMarket.id == market_id)
                .values(llm_sport_category=new_category, updated_at=func.now())
            )
        await session.commit()
        print(f"\nApplied {len(changes)} re-categorization(s).")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write changes (default is dry-run).",
    )
    args = parser.parse_args()
    asyncio.run(run(args.apply))
