"""Backfill probability_change_24h from snapshot history."""
import asyncio, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

async def run():
    from app.tasks.base import get_task_session
    from sqlalchemy import text

    async with get_task_session() as s:
        # Compute movement from the last two snapshots per outcome
        r = await s.execute(text("""
            UPDATE futures_outcomes fo
            SET probability_change_24h = sub.change
            FROM (
                SELECT DISTINCT ON (outcome_id)
                    f1.outcome_id,
                    f1.probability - f2.probability AS change
                FROM futures_odds_snapshots f1
                JOIN futures_odds_snapshots f2
                    ON f1.outcome_id = f2.outcome_id
                    AND f2.captured_at < f1.captured_at
                    AND f2.captured_at >= f1.captured_at - INTERVAL '48 hours'
                WHERE f1.captured_at >= NOW() - INTERVAL '48 hours'
                ORDER BY f1.outcome_id, f2.captured_at ASC
            ) sub
            WHERE fo.id = sub.outcome_id
              AND fo.probability_change_24h IS NULL
        """))
        print(f"Updated probability_change_24h: {r.rowcount} outcomes")

        # Backfill volume_24h on markets from Polymarket/Kalshi
        # (many are already set, this catches nulls)
        r2 = await s.execute(text("""
            UPDATE futures_markets fm
            SET volume_24h = sub.vol
            FROM (
                SELECT fo.market_id, SUM(
                    CASE WHEN fos.captured_at >= NOW() - INTERVAL '24 hours'
                    THEN 1 ELSE 0 END
                ) as vol
                FROM futures_outcomes fo
                JOIN futures_odds_snapshots fos ON fos.outcome_id = fo.id
                WHERE fos.captured_at >= NOW() - INTERVAL '48 hours'
                GROUP BY fo.market_id
            ) sub
            WHERE fm.id = sub.market_id
              AND (fm.volume_24h IS NULL OR fm.volume_24h = 0)
        """))
        print(f"Updated volume proxy (snapshot count): {r2.rowcount} markets")

asyncio.run(run())
