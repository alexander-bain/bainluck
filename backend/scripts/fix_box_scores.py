"""One-off: fetch and write box_score_data for events with espn_id but no box score."""
import asyncio
import json
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

async def fix():
    from app.tasks.base import get_task_session
    from app.services.espn_api import ESPNAPIService
    from sqlalchemy import text

    async with get_task_session() as s:
        r = await s.execute(text(
            "SELECT id, espn_id, home_team_name, away_team_name "
            "FROM events "
            "WHERE espn_id IS NOT NULL "
            "AND box_score_data IS NULL "
            "AND status IN ('completed', 'closed') "
            "AND commence_time >= NOW() - INTERVAL '48 hours' "
            "ORDER BY commence_time DESC LIMIT 10"
        ))
        events = r.all()
        print(f"Events with espn_id but no box_score: {len(events)}")

        if not events:
            print("Nothing to fix!")
            return

        espn = ESPNAPIService()
        try:
            for eid, espn_id, home, away in events:
                try:
                    ctx = await espn.get_event_context("baseball_mlb", espn_id)
                    bs = ctx.get("box_score", {})
                    sp = ctx.get("scoring_plays", [])
                    bsd = json.dumps({"source": "espn", "players": bs, "scoring_plays": sp})
                    await s.execute(
                        text("UPDATE events SET box_score_data = cast(:bsd AS jsonb) WHERE id = :eid"),
                        {"bsd": bsd, "eid": eid},
                    )
                    bp = len(bs) if isinstance(bs, (list, dict)) else 0
                    print(f"  {eid}: {away} @ {home} — {bp} players, {len(sp)} scoring plays")
                except Exception as e:
                    print(f"  {eid}: ERROR — {e}")
        finally:
            await espn.close()

asyncio.run(fix())
