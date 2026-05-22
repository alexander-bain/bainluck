"""One-time backfill to link orphaned Odds API events to ESPN/StatPal events.

Uses the Python names_match() fuzzy matching instead of SQL exact matching,
so it catches "NY Knicks" vs "New York Knicks" style differences.
"""

import logging
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import get_db_rw
from app.routes.admin_utils import _check_admin_secret
from app.utils.name_normalization import names_match

router = APIRouter(prefix="/admin/backfill-linkage", tags=["admin-linkage"])
logger = logging.getLogger(__name__)


@router.post("/run")
async def run_linkage_backfill(
    db: AsyncSession = Depends(get_db_rw),
    secret: str = Query(...),
    days_back: int = Query(30),
    dry_run: bool = Query(True),
    sport: str = Query("baseball_mlb"),
):
    """Find orphaned Odds API events and link them to ESPN/StatPal events.

    Uses fuzzy names_match() instead of SQL exact matching.
    Set dry_run=false to actually merge.
    """
    if not _check_admin_secret(secret):
        return {"error": "unauthorized"}

    cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)

    # Step 1: Find events WITH external_id but WITHOUT espn_id (orphaned Odds API events)
    orphans_q = await db.execute(text("""
        SELECT e.id, e.home_team_name, e.away_team_name, e.commence_time,
               e.external_id, e.espn_id, e.statpal_fixture_id, e.status,
               s.key AS sport_key
        FROM events e
        JOIN sports s ON e.sport_id = s.id
        WHERE e.external_id IS NOT NULL
          AND e.espn_id IS NULL
          AND e.commence_time >= :cutoff
          AND s.key = :sport
        ORDER BY e.commence_time DESC
    """), {"cutoff": cutoff, "sport": sport})
    orphans = orphans_q.all()

    # Step 2: Find events WITHOUT external_id (ESPN/StatPal events that need linking)
    targets_q = await db.execute(text("""
        SELECT e.id, e.home_team_name, e.away_team_name, e.commence_time,
               e.external_id, e.espn_id, e.statpal_fixture_id, e.status,
               s.key AS sport_key
        FROM events e
        JOIN sports s ON e.sport_id = s.id
        WHERE e.external_id IS NULL
          AND (e.espn_id IS NOT NULL OR e.statpal_fixture_id IS NOT NULL)
          AND e.commence_time >= :cutoff
          AND s.key = :sport
        ORDER BY e.commence_time DESC
    """), {"cutoff": cutoff, "sport": sport})
    targets = targets_q.all()

    matches = []
    linked = 0

    for orphan in orphans:
        best_match = None
        for target in targets:
            # Time window: ±6 hours
            time_diff = abs((orphan.commence_time - target.commence_time).total_seconds())
            if time_diff > 21600:
                continue

            # Fuzzy name matching (handles "NY Knicks" vs "New York Knicks")
            home_match = names_match(orphan.home_team_name or "", target.home_team_name or "")
            away_match = names_match(orphan.away_team_name or "", target.away_team_name or "")

            # Normal or swapped orientation
            if home_match and away_match:
                best_match = target
                break

            home_swap = names_match(orphan.home_team_name or "", target.away_team_name or "")
            away_swap = names_match(orphan.away_team_name or "", target.home_team_name or "")
            if home_swap and away_swap:
                best_match = target
                break

        if best_match:
            matches.append({
                "orphan_id": orphan.id,
                "orphan_teams": f"{orphan.away_team_name} @ {orphan.home_team_name}",
                "orphan_external_id": orphan.external_id,
                "target_id": best_match.id,
                "target_teams": f"{best_match.away_team_name} @ {best_match.home_team_name}",
                "target_espn_id": best_match.espn_id,
                "target_statpal_id": best_match.statpal_fixture_id,
                "time_diff_min": round(abs((orphan.commence_time - best_match.commence_time).total_seconds()) / 60),
            })

            if not dry_run:
                # Transfer external_id from orphan to target
                await db.execute(text("""
                    UPDATE events SET external_id = :ext_id WHERE id = :target_id AND external_id IS NULL
                """), {"ext_id": orphan.external_id, "target_id": best_match.id})

                # Transfer odds_snapshots from orphan to target
                await db.execute(text("""
                    UPDATE odds_snapshots SET event_id = :target_id WHERE event_id = :orphan_id
                """), {"target_id": best_match.id, "orphan_id": orphan.id})

                # Transfer win_prob_snapshots
                await db.execute(text("""
                    UPDATE win_prob_snapshots SET event_id = :target_id WHERE event_id = :orphan_id
                """), {"target_id": best_match.id, "orphan_id": orphan.id})

                # Hide the orphan
                await db.execute(text("""
                    UPDATE events SET status = 'merged' WHERE id = :orphan_id
                """), {"orphan_id": orphan.id})

                linked += 1

    if not dry_run and linked > 0:
        await db.commit()

    # Sample orphans and targets for debugging
    orphan_samples = [
        {
            "id": o.id,
            "home": o.home_team_name,
            "away": o.away_team_name,
            "time": o.commence_time.isoformat() if o.commence_time else None,
            "ext_id": o.external_id,
            "status": o.status,
        }
        for o in orphans[:15]
    ]
    target_samples = [
        {
            "id": t.id,
            "home": t.home_team_name,
            "away": t.away_team_name,
            "time": t.commence_time.isoformat() if t.commence_time else None,
            "espn_id": t.espn_id,
            "statpal_id": t.statpal_fixture_id,
            "status": t.status,
        }
        for t in targets[:15]
    ]

    return {
        "sport": sport,
        "days_back": days_back,
        "dry_run": dry_run,
        "orphans_found": len(orphans),
        "targets_available": len(targets),
        "matches_found": len(matches),
        "linked": linked,
        "matches": matches[:50],
        "orphan_samples": orphan_samples,
        "target_samples": target_samples,
    }
