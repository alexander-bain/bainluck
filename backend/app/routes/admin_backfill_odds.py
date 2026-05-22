"""Snapshot sparsity audit and historical odds backfill endpoints."""

import logging
import os
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
    months_back: int = Query(3),
):
    """Audit snapshot sparsity across completed events."""
    if not _check_admin_secret(secret):
        return {"error": "unauthorized"}

    await db.execute(text("SET LOCAL statement_timeout = '25s'"))

    cutoff = datetime.now(timezone.utc) - timedelta(days=months_back * 30)

    # Monthly summary - simple query without sport filtering
    monthly_q = await db.execute(text("""
        WITH event_snaps AS (
            SELECT
                e.id,
                s.key AS sport_key,
                DATE_TRUNC('month', e.commence_time) AS month,
                COUNT(os.id) AS snaps
            FROM events e
            JOIN sports s ON e.sport_id = s.id
            LEFT JOIN odds_snapshots os ON os.event_id = e.id
            WHERE e.status IN ('completed', 'closed')
              AND e.commence_time >= :cutoff
              AND s.key IN (
                'basketball_nba', 'icehockey_nhl', 'baseball_mlb',
                'americanfootball_nfl', 'basketball_ncaab',
                'basketball_wnba', 'soccer_epl', 'soccer_usa_mls',
                'mma_mixed_martial_arts'
              )
            GROUP BY e.id, s.key, e.commence_time
        )
        SELECT
            TO_CHAR(month, 'YYYY-MM') AS month,
            sport_key,
            COUNT(*) AS total_events,
            COUNT(CASE WHEN snaps < 5 THEN 1 END) AS sparse_lt5,
            COUNT(CASE WHEN snaps < 20 THEN 1 END) AS sparse_lt20,
            COUNT(CASE WHEN snaps = 0 THEN 1 END) AS zero_snaps,
            ROUND(AVG(snaps)) AS avg_snaps
        FROM event_snaps
        GROUP BY month, sport_key
        ORDER BY month DESC, sport_key
    """), {"cutoff": cutoff})

    monthly = [
        {
            "month": r.month,
            "sport": r.sport_key,
            "total_events": r.total_events,
            "sparse_lt5": r.sparse_lt5,
            "sparse_lt20": r.sparse_lt20,
            "zero_snaps": r.zero_snaps,
            "avg_snaps": int(r.avg_snaps) if r.avg_snaps else 0,
        }
        for r in monthly_q.all()
    ]

    # Sparse events for backfill
    sparse_q = await db.execute(text("""
        SELECT
            e.id,
            s.key AS sport_key,
            e.home_team,
            e.away_team,
            e.commence_time,
            e.external_id,
            COUNT(os.id) AS snapshot_count
        FROM events e
        JOIN sports s ON e.sport_id = s.id
        LEFT JOIN odds_snapshots os ON os.event_id = e.id
        WHERE e.status IN ('completed', 'closed')
          AND e.commence_time >= :cutoff
          AND e.external_id IS NOT NULL
          AND s.key IN (
            'basketball_nba', 'icehockey_nhl', 'baseball_mlb',
            'americanfootball_nfl', 'basketball_ncaab'
          )
        GROUP BY e.id, s.key, e.home_team, e.away_team, e.commence_time, e.external_id
        HAVING COUNT(os.id) < 20
        ORDER BY e.commence_time DESC
        LIMIT 100
    """), {"cutoff": cutoff})

    sparse_events = [
        {
            "event_id": r.id,
            "sport": r.sport_key,
            "home_team": r.home_team,
            "away_team": r.away_team,
            "commence_time": r.commence_time.isoformat() if r.commence_time else None,
            "external_id": r.external_id,
            "snapshot_count": r.snapshot_count,
        }
        for r in sparse_q.all()
    ]

    total_sparse = sum(m["sparse_lt20"] for m in monthly)
    total_events = sum(m["total_events"] for m in monthly)

    return {
        "summary": {
            "total_events": total_events,
            "sparse_lt5": sum(m["sparse_lt5"] for m in monthly),
            "sparse_lt20": total_sparse,
            "zero_snapshots": sum(m["zero_snaps"] for m in monthly),
            "sparse_pct": round(100 * total_sparse / max(total_events, 1), 1),
            "backfill_eligible": len(sparse_events),
            "estimated_backfill_cost": len(sparse_events) * 360,
            "estimated_backfill_cost_pct_of_monthly": round(100 * len(sparse_events) * 360 / 5_000_000, 2),
        },
        "monthly": monthly,
        "sparse_events": sparse_events,
    }
