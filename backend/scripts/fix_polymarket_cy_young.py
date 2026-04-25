#!/usr/bin/env python3
"""One-off fix: re-poll Polymarket event 215638 (AL Cy Young) to replace
"player AA" garbage names with real names from groupItemTitle."""

import asyncio
import sys
sys.path.insert(0, ".")

from sqlalchemy import select, delete as sa_delete
from sqlalchemy.dialects.postgresql import insert as pg_insert
from app.models import FuturesMarket, FuturesOutcome, FuturesOddsSnapshot
from app.services.polymarket_api import PolymarketAPIService
from app.tasks.base import get_task_session
from app.utils.odds_math import probability_to_american


async def fix():
    service = PolymarketAPIService()
    try:
        raw = await service.get_event_by_id("215638")
        if not raw:
            print("Event not found")
            return

        title = raw.get("title", "?")
        markets = raw.get("markets", [])
        print(f"Event: {title} ({len(markets)} markets)")

        async with get_task_session() as session:
            # Find our FuturesMarket
            result = await session.execute(
                select(FuturesMarket.id).where(
                    FuturesMarket.source == "polymarket",
                    FuturesMarket.external_id == "215638",
                )
            )
            market_id = result.scalar_one_or_none()
            if not market_id:
                print("Market not in DB")
                return
            print(f"DB market_id: {market_id}")

            # Delete ALL existing outcomes for this market
            old_outcomes = await session.execute(
                select(FuturesOutcome.id).where(FuturesOutcome.market_id == market_id)
            )
            old_ids = old_outcomes.scalars().all()
            if old_ids:
                await session.execute(
                    sa_delete(FuturesOddsSnapshot).where(
                        FuturesOddsSnapshot.outcome_id.in_(old_ids)
                    )
                )
                await session.execute(
                    sa_delete(FuturesOutcome).where(
                        FuturesOutcome.market_id == market_id
                    )
                )
                print(f"Deleted {len(old_ids)} old outcomes")

            # Re-create with correct names
            from sqlalchemy import func
            now = func.now()
            created = 0
            for rank, m in enumerate(markets, 1):
                condition_id = m.get("conditionId", m.get("condition_id", ""))
                name = m.get("groupItemTitle") or m.get("question", "Unknown")
                ltp = m.get("lastTradePrice")
                prob = float(ltp) if ltp else None
                if prob is None or prob <= 0:
                    continue
                american = probability_to_american(prob) if 0 < prob < 1 else None

                stmt = pg_insert(FuturesOutcome).values(
                    market_id=market_id,
                    external_id=condition_id,
                    name=name,
                    current_probability=prob,
                    current_american_odds=american,
                    opening_probability=prob,
                    opening_american_odds=american,
                    opening_captured_at=now,
                    rank=rank,
                ).on_conflict_do_update(
                    index_elements=["market_id", "external_id"],
                    set_={
                        "name": name,
                        "current_probability": prob,
                        "current_american_odds": american,
                        "rank": rank,
                        "last_updated": now,
                    },
                )
                await session.execute(stmt)
                created += 1

            await session.commit()
            print(f"Created {created} outcomes with real names")

    finally:
        await service.close()


if __name__ == "__main__":
    asyncio.run(fix())
