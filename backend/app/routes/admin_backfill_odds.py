"""Snapshot sparsity audit and historical odds backfill endpoints."""

import logging
import traceback
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import get_db, get_db_rw
from app.routes.admin_utils import _check_admin_secret

router = APIRouter(prefix="/admin/snapshot-sparsity", tags=["admin-sparsity"])
logger = logging.getLogger(__name__)


@router.get("/audit")
async def snapshot_sparsity_audit(
    db: AsyncSession = Depends(get_db),
    secret: str = Query(...),
    days_back: int = Query(30),
    sport: str = Query("baseball_mlb"),
    threshold: int = Query(20),
):
    """Audit snapshot sparsity for a single sport over a time window."""
    if not _check_admin_secret(secret):
        return {"error": "unauthorized"}

    try:
        await db.execute(text("SET LOCAL statement_timeout = '30s'"))
        cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)

        # Use a lateral subquery to count snapshots per event instead of
        # a full JOIN + GROUP BY on the massive odds_snapshots table.
        q = await db.execute(text("""
            SELECT
                e.id,
                e.home_team_name,
                e.away_team_name,
                e.commence_time,
                e.external_id,
                e.status,
                COALESCE(sc.cnt, 0) AS snapshot_count
            FROM events e
            JOIN sports s ON e.sport_id = s.id
            LEFT JOIN LATERAL (
                SELECT COUNT(*) AS cnt
                FROM odds_snapshots os
                WHERE os.event_id = e.id
            ) sc ON true
            WHERE e.status IN ('completed', 'closed')
              AND e.commence_time >= :cutoff
              AND s.key = :sport
            ORDER BY snapshot_count ASC
            LIMIT 200
        """), {"cutoff": cutoff, "sport": sport})

        events = []
        sparse_count = 0
        zero_count = 0
        total = 0
        for r in q.all():
            total += 1
            is_sparse = r.snapshot_count < threshold
            if is_sparse:
                sparse_count += 1
            if r.snapshot_count == 0:
                zero_count += 1
            events.append({
                "event_id": r.id,
                "home_team": r.home_team_name,
                "away_team": r.away_team_name,
                "commence_time": r.commence_time.isoformat() if r.commence_time else None,
                "external_id": r.external_id,
                "status": r.status,
                "snapshot_count": r.snapshot_count,
                "sparse": is_sparse,
            })

        sparse_events = [e for e in events if e["sparse"]]

        return {
            "sport": sport,
            "days_back": days_back,
            "threshold": threshold,
            "summary": {
                "total_events": total,
                "sparse": sparse_count,
                "zero_snapshots": zero_count,
                "sparse_pct": round(100 * sparse_count / max(total, 1), 1),
                "backfill_eligible": len([e for e in sparse_events if e["external_id"]]),
                "estimated_backfill_cost": len([e for e in sparse_events if e["external_id"]]) * 360,
            },
            "sparse_events": sparse_events[:50],
            "all_events_by_snapshots": events[:20],
        }
    except Exception as exc:
        logger.exception("Sparsity audit failed")
        return {"error": str(exc), "trace": traceback.format_exc()[:500]}



@router.post("/backfill-historical")
async def backfill_historical_odds(
    secret: str = Query(...),
    sport: str = Query("baseball_mlb"),
    days_back: int = Query(30),
    max_events: int = Query(500),
):
    """Queue a Celery task to backfill sparse events from historical API.

    Returns immediately with a task ID. The actual backfill runs in
    the background worker with no timeout limit.
    """
    if not _check_admin_secret(secret):
        return {"error": "unauthorized"}

    from app.tasks import backfill_historical_odds_task
    task = backfill_historical_odds_task.delay(
        sport=sport, days_back=days_back, max_events=max_events
    )
    return {
        "status": "queued",
        "task_id": task.id,
        "sport": sport,
        "days_back": days_back,
        "max_events": max_events,
        "message": "Backfill running in background. Check /api/admin/celery-debug for progress.",
    }

@router.get("/inventory")
async def snapshot_inventory(
    db: AsyncSession = Depends(get_db),
    secret: str = Query(...),
    days_back: int = Query(30),
    threshold: int = Query(20),
):
    """Full inventory of Tier 1 events grouped by sport and date, showing snapshot coverage.

    Returns every event with its snapshot count, grouped by sport then by date.
    Events below threshold are flagged as sparse.
    """
    if not _check_admin_secret(secret):
        return {"error": "unauthorized"}

    try:
        await db.execute(text("SET LOCAL statement_timeout = '20s'"))
        cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)

        tier1 = [
            "basketball_nba", "icehockey_nhl", "baseball_mlb",
            "americanfootball_nfl", "basketball_ncaab",
        ]

        inventory = {}

        for sport in tier1:
            q = await db.execute(text("""
                SELECT
                    e.id, e.home_team_name, e.away_team_name,
                    e.commence_time, e.external_id, e.espn_id,
                    e.status,
                    COUNT(os.id) AS snap_count
                FROM events e
                JOIN sports s ON e.sport_id = s.id
                LEFT JOIN odds_snapshots os ON os.event_id = e.id
                WHERE e.commence_time >= :cutoff
                  AND s.key = :sport
                  AND e.status IN ('completed', 'closed', 'live', 'scheduled')
                GROUP BY e.id, e.home_team_name, e.away_team_name,
                         e.commence_time, e.external_id, e.espn_id, e.status
                ORDER BY e.commence_time DESC
            """), {"cutoff": cutoff, "sport": sport})

            events = []
            by_date = {}
            total = 0
            sparse = 0
            zero = 0

            for r in q.all():
                total += 1
                is_sparse = r.snap_count < threshold
                if is_sparse:
                    sparse += 1
                if r.snap_count == 0:
                    zero += 1

                day = str(r.commence_time)[:10]
                by_date.setdefault(day, {"total": 0, "sparse": 0, "zero": 0, "events": []})
                by_date[day]["total"] += 1
                if is_sparse:
                    by_date[day]["sparse"] += 1
                if r.snap_count == 0:
                    by_date[day]["zero"] += 1
                by_date[day]["events"].append({
                    "id": r.id,
                    "teams": f"{r.away_team_name} @ {r.home_team_name}",
                    "time": str(r.commence_time)[:16],
                    "snaps": r.snap_count,
                    "has_odds_api": r.external_id is not None,
                    "has_espn": r.espn_id is not None,
                    "status": r.status,
                    "sparse": is_sparse,
                })

            inventory[sport] = {
                "total": total,
                "sparse": sparse,
                "zero": zero,
                "coverage_pct": round(100 * (total - sparse) / max(total, 1), 1),
                "by_date": dict(sorted(by_date.items(), reverse=True)),
            }

        # Summary
        all_total = sum(v["total"] for v in inventory.values())
        all_sparse = sum(v["sparse"] for v in inventory.values())
        all_zero = sum(v["zero"] for v in inventory.values())

        return {
            "days_back": days_back,
            "threshold": threshold,
            "summary": {
                "total_tier1_events": all_total,
                "sparse": all_sparse,
                "zero_snapshots": all_zero,
                "coverage_pct": round(100 * (all_total - all_sparse) / max(all_total, 1), 1),
            },
            "sports": inventory,
        }

    except Exception as exc:
        import traceback
        return {"error": str(exc), "trace": traceback.format_exc()[:500]}
