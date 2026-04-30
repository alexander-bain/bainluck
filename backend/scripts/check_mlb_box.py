"""Check MLB box score state and test ESPN fetch on Heroku."""
import asyncio, json, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

async def check():
    from app.tasks.base import get_task_session
    from app.services.espn_api import ESPNAPIService
    from sqlalchemy import text

    async with get_task_session() as s:
        # Check MLB events specifically
        r = await s.execute(text(
            "SELECT e.id, espn_id, "
            "box_score_data IS NOT NULL as has_bsd, "
            "CASE WHEN box_score_data IS NOT NULL THEN substring(box_score_data::text, 1, 120) END as preview, "
            "status, home_team_name, away_team_name "
            "FROM events e JOIN sports s ON e.sport_id = s.id "
            "WHERE s.key = 'baseball_mlb' "
            "AND e.status IN ('completed', 'closed') "
            "AND e.commence_time >= NOW() - INTERVAL '24 hours' "
            "ORDER BY e.commence_time DESC LIMIT 10"
        ))
        events = r.all()
        print(f"MLB completed (24h): {len(events)}")
        for row in events:
            eid_str = row.espn_id or "NULL"
            print(f"  {row.id}: espn_id={eid_str:>12s} bsd={row.has_bsd} {row.away_team_name[:15]:>15s} @ {row.home_team_name[:15]}")
            if row.preview:
                print(f"    {row.preview}")

        # Test ESPN fetch for a game with espn_id
        test_events = [e for e in events if e.espn_id]
        if test_events:
            ev = test_events[0]
            print(f"\nTesting ESPN fetch for {ev.id} (espn_id={ev.espn_id})...")
            espn = ESPNAPIService()
            try:
                ctx = await espn.get_event_context("baseball_mlb", ev.espn_id)
                bs = ctx.get("box_score", {})
                sp = ctx.get("scoring_plays", [])
                print(f"  box_score: {type(bs).__name__} len={len(bs) if bs else 0}")
                print(f"  scoring_plays: {len(sp)}")
                if not bs and not sp:
                    print(f"  Context keys: {list(ctx.keys())}")
                elif bs:
                    if isinstance(bs, list):
                        print(f"  First player: {bs[0].get('name','?') if bs else 'none'}")
                    elif isinstance(bs, dict):
                        print(f"  Keys: {list(bs.keys())[:5]}")
            finally:
                await espn.close()

asyncio.run(check())
