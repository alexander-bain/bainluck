"""Snapshot sparsity audit and historical odds backfill endpoints."""

import logging
import traceback
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import get_db
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
