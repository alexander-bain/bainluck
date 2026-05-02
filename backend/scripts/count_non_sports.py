"""Count non-sports markets in the DB to understand why Discover has so few."""
import asyncio, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

async def run():
    from app.tasks.base import get_task_session
    from sqlalchemy import text

    async with get_task_session() as s:
        sports = "basketball,football,baseball,hockey,soccer,golf,mma,boxing,tennis,cricket,motorsports,esports,rugby,lacrosse"
        sports_list = sports.split(",")
        sports_sql = ",".join(f"'{s}'" for s in sports_list)

        r1 = await s.execute(text(f"SELECT COUNT(*) FROM futures_markets WHERE status = 'open' AND event_id IS NULL AND (llm_sport_category NOT IN ({sports_sql}) OR llm_sport_category IS NULL)"))
        total = r1.scalar()
        print(f"Open non-sport futures (no name filter): {total}")

        r2 = await s.execute(text(f"SELECT COUNT(*) FROM futures_markets WHERE status = 'open' AND event_id IS NULL AND (llm_sport_category NOT IN ({sports_sql}) OR llm_sport_category IS NULL) AND name NOT ILIKE '%% vs %%' AND name NOT ILIKE '%% vs.%%' AND name NOT ILIKE '%% at %%'"))
        filtered = r2.scalar()
        print(f"After vs/at filter: {filtered}")
        print(f"Killed by vs/at filter: {total - filtered}")

        r3 = await s.execute(text(f"""
            SELECT COALESCE(llm_sport_category, 'NULL'), COUNT(*)
            FROM futures_markets
            WHERE status = 'open' AND event_id IS NULL
              AND (llm_sport_category NOT IN ({sports_sql}) OR llm_sport_category IS NULL)
            GROUP BY llm_sport_category ORDER BY COUNT(*) DESC LIMIT 20
        """))
        print(f"\nNon-sport categories:")
        for row in r3.all():
            print(f"  {str(row[0] or 'NULL'):20s} {row[1]:>5d}")

        # Sample some interesting ones
        r4 = await s.execute(text(f"""
            SELECT name, llm_sport_category, source
            FROM futures_markets
            WHERE status = 'open' AND event_id IS NULL
              AND llm_sport_category IN ('politics','economics','tech','entertainment','culture','health','geopolitics')
            ORDER BY volume_24h DESC NULLS LAST
            LIMIT 20
        """))
        print(f"\nTop non-sport markets by volume:")
        for row in r4.all():
            print(f"  [{row[1] or '?':12s}] {row[2]:12s} {row[0][:55]}")

asyncio.run(run())
