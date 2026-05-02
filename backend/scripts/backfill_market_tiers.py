"""Recompute market_tier for all futures markets using current classification logic.

Fixes the Polymarket issue where category="championship" caused everything to be tier 1.
Safe to run multiple times — idempotent.

Usage: heroku run python scripts/backfill_market_tiers.py -a bainluck
"""
import asyncio, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def run():
    from app.tasks.base import get_task_session
    from sqlalchemy import text
    from app.utils.market_label_normalization import compute_market_tier

    async with get_task_session() as s:
        result = await s.execute(text("""
            SELECT id, name, category, llm_sport_category, market_tier
            FROM futures_markets
            WHERE status = 'open'
        """))
        rows = result.fetchall()
        print(f"Checking {len(rows)} open markets...")

        changes = 0
        tier_counts = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
        for row in rows:
            market_id, name, category, sport_category, old_tier = row
            new_tier = compute_market_tier(name, category=category, sport_category=sport_category)
            tier_counts[new_tier] = tier_counts.get(new_tier, 0) + 1
            if new_tier != old_tier:
                await s.execute(
                    text("UPDATE futures_markets SET market_tier = :tier WHERE id = :id"),
                    {"tier": new_tier, "id": market_id},
                )
                changes += 1

        await s.commit()
        print(f"\nUpdated {changes} markets out of {len(rows)} total")
        print(f"Tier distribution: {tier_counts}")


if __name__ == "__main__":
    asyncio.run(run())
