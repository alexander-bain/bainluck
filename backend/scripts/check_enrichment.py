#!/usr/bin/env python3
"""Check enrichment status for specific market IDs."""
import asyncio
from sqlalchemy import select
from app.tasks.base import get_task_session

async def check():
    from app.models.models import FuturesMarket
    feed_ids = [12233895, 12182710, 11419216, 11242950, 10639676, 10803833, 10639674, 9462044, 10837961]
    async with get_task_session() as session:
        result = await session.execute(
            select(FuturesMarket.id, FuturesMarket.name, FuturesMarket.image_url, FuturesMarket.hook_description)
            .where(FuturesMarket.id.in_(feed_ids))
        )
        for row in result.all():
            print(f"ID {row.id}: img={'YES' if row.image_url else 'NO'} hook={'YES' if row.hook_description else 'NO'} — {row.name[:50]}")

        # Also count total enriched
        total = await session.execute(
            select(FuturesMarket.id).where(FuturesMarket.image_url.isnot(None))
        )
        print(f"\nTotal markets with image_url: {len(total.all())}")
        total_hooks = await session.execute(
            select(FuturesMarket.id).where(FuturesMarket.hook_description.isnot(None))
        )
        print(f"Total markets with hook: {len(total_hooks.all())}")

asyncio.run(check())
