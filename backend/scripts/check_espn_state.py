"""Diagnostic: check espn_id and box_score_data raw DB values."""
import asyncio, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

async def check():
    from app.tasks.base import get_task_session
    from sqlalchemy import text

    async with get_task_session() as s:
        r = await s.execute(text(
            "SELECT id, espn_id, box_score_data IS NOT NULL as has_bsd, "
            "CASE WHEN box_score_data IS NOT NULL THEN substring(box_score_data::text, 1, 100) END as bsd_preview, "
            "status, home_team_name "
            "FROM events "
            "WHERE status IN ('completed', 'closed') "
            "AND commence_time >= NOW() - INTERVAL '48 hours' "
            "ORDER BY commence_time DESC LIMIT 10"
        ))
        for row in r.all():
            print(f"  {row.id}: espn_id={row.espn_id or 'NULL':>12s} bsd={row.has_bsd} status={row.status:8s} {row.home_team_name[:20]}")
            if row.bsd_preview:
                print(f"    preview: {row.bsd_preview}")

asyncio.run(check())
