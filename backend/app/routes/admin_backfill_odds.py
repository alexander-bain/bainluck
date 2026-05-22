"""Snapshot sparsity audit and historical odds backfill endpoints."""

import logging
import os
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import get_db

router = APIRouter(prefix="/admin/snapshot-sparsity", tags=["admin-sparsity"])
logger = logging.getLogger(__name__)


from app.routes.admin_utils import _check_admin_secret


@router.get("/audit")
async def snapshot_sparsity_audit(
    db: AsyncSession = Depends(get_db),
    secret: str = Query(...),
    months_back: int = Query(6),
    min_tier: int = Query(1),
):
    """Audit snapshot sparsity across all historical events.

    Returns per-month, per-sport counts of sparse events (< threshold snapshots)
    along with specific sparse events suitable for historical backfill.
    """
    if not _check_admin_secret(secret):
        return {"error": "unauthorized"}

    await db.execute(text("SET LOCAL statement_timeout = '30s'"))

    cutoff = datetime.now(timezone.utc) - timedelta(days=months_back * 30)

    tier1_sports = (
        "basketball_nba", "icehockey_nhl", "baseball_mlb",
        "americanfootball_nfl", "basketball_ncaab",
    )
    tier2_sports = (
        "basketball_wnba", "soccer_epl", "soccer_usa_mls",
        "soccer_uefa_champs_league", "mma_mixed_martial_arts",
        "americanfootball_ncaaf",
    )
    sports = tier1_sports if min_tier <= 1 else ()
    if min_tier <= 2:
        sports = sports + tier2_sports

    sports_filter = ", ".join(f"'{s}'" for s in sports)

    # Monthly summary
    monthly_q = await db.execute(text(f"""
        WITH event_snaps AS (
            SELECT
                e.id,
                s.key AS sport_key,
                DATE_TRUNC('month', e.commence_time) AS month,
                COUNT(os.id) AS snaps,
                e.external_id
            FROM events e
            JOIN sports s ON e.sport_id = s.id
            LEFT JOIN odds_snapshots os ON os.event_id = e.id
            WHERE e.status IN ('completed', 'closed')
              AND e.commence_time >= :cutoff
              AND s.key IN ({sports_filter})
            GROUP BY e.id, s.key, e.commence_time, e.external_id
        )
        SELECT
            TO_CHAR(month, 'YYYY-MM') AS month,
            sport_key,
            COUNT(*) AS total_events,
            COUNT(CASE WHEN snaps < 5 THEN 1 END) AS sparse_lt5,
            COUNT(CASE WHEN snaps < 20 THEN 1 END) AS sparse_lt20,
            COUNT(CASE WHEN snaps = 0 THEN 1 END) AS zero_snaps,
            ROUND(AVG(snaps)) AS avg_snaps,
            MIN(snaps) AS min_snaps,
            MAX(snaps) AS max_snaps
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
            "avg_snaps": r.avg_snaps,
            "min_snaps": r.min_snaps,
            "max_snaps": r.max_snaps,
        }
        for r in monthly_q.all()
    ]

    # Top sparse events suitable for backfill (have external_id for API lookup)
    sparse_q = await db.execute(text(f"""
        SELECT
            e.id,
            s.key AS sport_key,
            e.home_team,
            e.away_team,
            e.commence_time,
            e.status,
            e.external_id,
            COUNT(os.id) AS snapshot_count
        FROM events e
        JOIN sports s ON e.sport_id = s.id
        LEFT JOIN odds_snapshots os ON os.event_id = e.id
        WHERE e.status IN ('completed', 'closed')
          AND e.commence_time >= :cutoff
          AND e.external_id IS NOT NULL
          AND s.key IN ({sports_filter})
        GROUP BY e.id, s.key, e.home_team, e.away_team, e.commence_time, e.status, e.external_id
        HAVING COUNT(os.id) < 20
        ORDER BY e.commence_time DESC
        LIMIT 200
    """), {"cutoff": cutoff})

    sparse_events = [
        {
            "event_id": r.id,
            "sport": r.sport_key,
            "home_team": r.home_team,
            "away_team": r.away_team,
            "commence_time": r.commence_time.isoformat() if r.commence_time else None,
            "status": r.status,
            "external_id": r.external_id,
            "snapshot_count": r.snapshot_count,
            "backfill_eligible": r.external_id is not None,
        }
        for r in sparse_q.all()
    ]

    # Summary stats
    total_sparse_lt5 = sum(m["sparse_lt5"] for m in monthly)
    total_sparse_lt20 = sum(m["sparse_lt20"] for m in monthly)
    total_zero = sum(m["zero_snaps"] for m in monthly)
    total_events = sum(m["total_events"] for m in monthly)

    # Estimate backfill cost
    # Historical API: 10 requests per region per market
    # For h2h only, us region: 10 per timestamp
    # A 3-hour game at 5-min intervals = 36 timestamps × 10 = 360 requests
    backfill_cost_per_event = 360
    total_backfill_cost = len(sparse_events) * backfill_cost_per_event

    return {
        "audit_time": datetime.now(timezone.utc).isoformat(),
        "months_back": months_back,
        "sports_audited": list(sports),
        "summary": {
            "total_events": total_events,
            "sparse_lt5": total_sparse_lt5,
            "sparse_lt20": total_sparse_lt20,
            "zero_snapshots": total_zero,
            "sparse_pct": round(100 * total_sparse_lt20 / max(total_events, 1), 1),
            "backfill_eligible": len([e for e in sparse_events if e["backfill_eligible"]]),
            "estimated_backfill_cost": total_backfill_cost,
            "estimated_backfill_cost_pct_of_monthly": round(100 * total_backfill_cost / 5_000_000, 2),
        },
        "monthly": monthly,
        "sparse_events": sparse_events[:100],
    }


@router.post("/trigger-backfill")
async def trigger_historical_backfill(
    db: AsyncSession = Depends(get_db),
    secret: str = Query(...),
    sport_key: str = Query(...),
    event_external_id: str = Query(...),
    event_id: int = Query(...),
    start_time: str = Query(..., description="ISO format commence_time"),
    duration_hours: float = Query(3.0),
    interval_minutes: int = Query(5),
    markets: str = Query("h2h"),
    regions: str = Query("us"),
):
    """Trigger historical odds backfill for a specific event using the historical API."""
    if not _check_admin_secret(secret):
        return {"error": "unauthorized"}

    from app.services.odds_api import OddsAPIService
    from app.models.models import OddsSnapshot, Event
    from app.utils.odds_math import moneyline_to_probability
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    service = OddsAPIService()
    start_dt = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
    end_dt = start_dt + timedelta(hours=duration_hours)

    snapshots_created = 0
    timestamps_fetched = 0
    errors = []

    current = start_dt
    while current <= end_dt:
        date_param = current.strftime("%Y-%m-%dT%H:%M:%SZ")
        try:
            url = f"{service.BASE_URL}/historical/sports/{sport_key}/odds"
            response = await service.client.get(url, params={
                "apiKey": service.api_key,
                "regions": regions,
                "markets": markets,
                "date": date_param,
            })
            service._capture_quota(response)

            if response.status_code == 200:
                data = response.json()
                timestamp = data.get("timestamp")
                events_data = data.get("data", [])
                timestamps_fetched += 1

                for ev in events_data:
                    if ev.get("id") != event_external_id:
                        continue

                    for bookmaker in ev.get("bookmakers", []):
                        for market in bookmaker.get("markets", []):
                            if market["key"] != "h2h":
                                continue

                            outcomes = market.get("outcomes", [])
                            if len(outcomes) < 2:
                                continue

                            home_prob = None
                            away_prob = None
                            for o in outcomes:
                                prob = moneyline_to_probability(o["price"]) if isinstance(o["price"], (int, float)) else None
                                if o["name"] == ev.get("home_team"):
                                    home_prob = prob
                                elif o["name"] == ev.get("away_team"):
                                    away_prob = prob

                            captured_at = datetime.fromisoformat(
                                timestamp.replace("Z", "+00:00")
                            ) if timestamp else current

                            stmt = pg_insert(OddsSnapshot).values(
                                event_id=event_id,
                                bookmaker=bookmaker["key"],
                                home_odds=outcomes[0].get("price"),
                                away_odds=outcomes[1].get("price") if len(outcomes) > 1 else None,
                                home_probability=home_prob,
                                away_probability=away_prob,
                                captured_at=captured_at,
                            ).on_conflict_do_nothing()
                            await db.execute(stmt)
                            snapshots_created += 1

                # Use next_timestamp for pagination
                next_ts = data.get("next_timestamp")
                if next_ts:
                    current = datetime.fromisoformat(next_ts.replace("Z", "+00:00"))
                else:
                    current += timedelta(minutes=interval_minutes)
            else:
                errors.append(f"{date_param}: HTTP {response.status_code}")
                current += timedelta(minutes=interval_minutes)

        except Exception as e:
            errors.append(f"{date_param}: {str(e)}")
            current += timedelta(minutes=interval_minutes)

    await db.commit()

    return {
        "event_id": event_id,
        "sport": sport_key,
        "external_id": event_external_id,
        "timestamps_fetched": timestamps_fetched,
        "snapshots_created": snapshots_created,
        "errors": errors[:10],
        "quota_remaining": service.last_requests_remaining,
    }
