#!/usr/bin/env python3
"""One-off backfill: re-categorize Kalshi markets mis-tagged into a wrong category.

Background (issue #1081 / #181 forensics / Queue #201–#203):
When a Kalshi ticker prefix was unmapped, ``get_sport_key_from_ticker()`` returned
``None`` and ``_categorize_kalshi_market`` fell to name rules that default to a
"dumping-ground" category. Two such dumping grounds were found:

- ``football`` (Queue #201/#202): esports, Asian baseball, rugby, cricket, intl
  basketball/soccer, AFL, curling, FIFA World Cup structure markets all piled in.
  Repaired by ``scripts/fix_misclassified_football_markets.py``.
- ``motorsports`` (Queue #203): the broad ``\\bracing\\b`` / ``NNN winner`` name
  rules (``app/utils/futures_categorization.py``) swept non-race families in —
  AFL (``KXAFLGAME``→aussierules), French rugby (``KXRUGBYFRA14MATCH``→rugby),
  and the #181 named offender World Cup group points (``KXWCGROUPPTS``→soccer).

The mapping fix lives in ``app.utils.sport_keys`` (ticker prefixes are already
present — v3455/#201). This script repairs EXISTING rows whose category was
stamped before the maps were fixed and that have stopped being polled (settled
Kalshi markets — gotcha #33 — never get re-classified by the live poll).

It scans every Kalshi market currently stored as ``llm_sport_category =
<from_category>`` and, for each, re-derives the category from the TICKER only
(``get_sport_key_from_ticker`` → ``SPORT_PREFIX_TO_LLM_CATEGORY``). A row is
rewritten ONLY when the ticker now resolves to a DIFFERENT category. Rows whose
ticker still resolves to the same category (e.g. a genuine ``KXF1RACE`` /
``KXNASCARRACE`` staying motorsports — the positive-match guard) or does not
resolve at all (name-classified rows — motogp/indycar futures, ``NNN winner``
NASCAR) are left untouched. This makes the backfill precise and idempotent: it
moves exactly the newly-mapped families out and nothing else.

Polymarket rows are intentionally skipped — their category is tag-derived, not
name-defaulted, and their external_id is not a Kalshi ticker.

Usage:
    python3 scripts/fix_misclassified_kalshi_categories.py --from-category motorsports [--apply]

On Heroku (PROJECT_PATH=backend puts scripts at /app/scripts — do NOT ``cd backend``):
    heroku run:detached -a bainluck "python3 scripts/fix_misclassified_kalshi_categories.py --from-category motorsports --apply"

Without ``--apply`` it runs in dry-run mode and only prints the proposed changes.
The regular Kalshi polling task already re-classifies actively-polled markets on
its next run; this script guarantees the fix lands immediately and covers rows
that have stopped being polled (see gotcha #33).
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


async def run(apply: bool, from_category: str) -> None:
    async with get_task_session() as session:
        result = await session.execute(
            select(
                FuturesMarket.id,
                FuturesMarket.name,
                FuturesMarket.external_id,
            )
            .where(FuturesMarket.llm_sport_category == from_category)
            .where(FuturesMarket.source == "kalshi")
        )
        rows = result.all()
        print(
            f"Scanning {len(rows)} Kalshi markets currently classified as "
            f"'{from_category}'..."
        )

        changes: list[tuple[int, str, str, str]] = []
        for market_id, name, external_id in rows:
            new_category = _category_from_ticker(external_id)
            # Positive-match guard: a ticker that still resolves to from_category
            # (e.g. KXF1RACE/KXNASCARRACE → motorsports) is left in place.
            if new_category and new_category != from_category:
                changes.append((market_id, name, new_category, external_id))

        if not changes:
            print(f"No misclassified '{from_category}' markets found. Nothing to do.")
            return

        by_cat = Counter(c[2] for c in changes)
        print(f"\nFound {len(changes)} misclassified '{from_category}' market(s):")
        for cat, n in by_cat.most_common():
            print(f"  {from_category} -> {cat:<12} {n}")
        print("\nSamples:")
        for market_id, name, new_category, ext in changes[:25]:
            print(f"  [{market_id}] {from_category} -> {new_category:<12} ({ext})  {name}")

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
        "--from-category",
        required=True,
        help="The mis-tagged source category to sweep (e.g. 'motorsports').",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write changes (default is dry-run).",
    )
    args = parser.parse_args()
    asyncio.run(run(args.apply, args.from_category))
