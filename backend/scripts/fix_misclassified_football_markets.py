#!/usr/bin/env python3
"""One-off backfill: re-categorize Kalshi markets misclassified as football.

Background (issue #1081 / #181 forensics / Queue #201):
`llm_sport_category = 'football'` became a dumping ground. When a Kalshi
ticker prefix was unmapped, ``get_sport_key_from_ticker()`` returned ``None`` and
``_categorize_kalshi_market`` fell to name rules (coach-of-the-year, wins
over/under, seasonal bare-matchup) that default to ``football`` — so esports
(Call of Duty / Dota 2 / Rainbow Six / Overwatch), Asian baseball (KBO / NPB),
rugby (NRL), cricket (T20 / IPL), international basketball (NZ NBL / VBA / German
BBL), international soccer (K-League / Eredivisie), AFL, Olympic curling, and FIFA
World Cup structure markets all piled into the football calibration cohort.

The mapping fix lives in ``app.utils.sport_keys`` (new ticker prefixes +
``_UNSUPPORTED_LEAGUE_PREFIXES`` entries). This script repairs EXISTING rows.

It scans every Kalshi market currently stored as ``llm_sport_category =
'football'`` and, for each, re-derives the category from the TICKER only
(``get_sport_key_from_ticker`` → ``SPORT_PREFIX_TO_LLM_CATEGORY``). A row is
rewritten ONLY when the ticker now resolves to a non-football category. Rows
whose ticker still resolves to football (real NFL/NCAAF/CFL) or does not resolve
at all (name-classified football — draft picks, coach markets) are left
untouched. This makes the backfill precise and idempotent: it moves exactly the
newly-mapped families out of football and nothing else.

Polymarket football rows are intentionally skipped — their category is
tag-derived, not name-defaulted, so they are not part of this dumping ground and
their external_id is not a Kalshi ticker.

Usage:
    cd backend && python3 scripts/fix_misclassified_football_markets.py [--apply]

Without ``--apply`` it runs in dry-run mode and only prints the proposed changes.
The regular Kalshi polling task already re-classifies actively-polled markets on
its next run; this script guarantees the fix lands immediately and covers rows
that have stopped being polled (e.g. settled Kalshi markets — see gotcha #33).
"""

import argparse
import asyncio
import sys
from collections import Counter

sys.path.insert(0, ".")

from sqlalchemy import select, update
from sqlalchemy import func

from app.models import FuturesMarket
from app.tasks.base import get_task_session
from app.utils.sport_keys import (
    get_sport_key_from_ticker,
    SPORT_PREFIX_TO_LLM_CATEGORY,
)


def _category_from_ticker(external_id: str) -> str | None:
    """Re-derive the llm_sport_category from a Kalshi ticker (authoritative path).

    Returns ``None`` when the ticker does not resolve — those rows are
    name-classified and must be left alone.
    """
    sport_key = get_sport_key_from_ticker(external_id or "")
    if not sport_key:
        return None
    prefix = sport_key.split("_")[0]
    return SPORT_PREFIX_TO_LLM_CATEGORY.get(prefix)


async def run(apply: bool) -> None:
    async with get_task_session() as session:
        result = await session.execute(
            select(
                FuturesMarket.id,
                FuturesMarket.name,
                FuturesMarket.external_id,
            )
            .where(FuturesMarket.llm_sport_category == "football")
            .where(FuturesMarket.source == "kalshi")
        )
        rows = result.all()
        print(f"Scanning {len(rows)} Kalshi markets currently classified as 'football'...")

        changes: list[tuple[int, str, str, str]] = []
        for market_id, name, external_id in rows:
            new_category = _category_from_ticker(external_id)
            if new_category and new_category != "football":
                changes.append((market_id, name, new_category, external_id))

        if not changes:
            print("No misclassified football markets found. Nothing to do.")
            return

        by_cat = Counter(c[2] for c in changes)
        print(f"\nFound {len(changes)} misclassified football market(s):")
        for cat, n in by_cat.most_common():
            print(f"  football -> {cat:<12} {n}")
        print("\nSamples:")
        for market_id, name, new_category, ext in changes[:25]:
            print(f"  [{market_id}] football -> {new_category:<12} ({ext})  {name}")

        if not apply:
            print("\nDry run. Re-run with --apply to write changes.")
            return

        for market_id, _name, new_category, _ext in changes:
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
