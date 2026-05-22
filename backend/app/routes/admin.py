"""Admin API endpoints for maintenance tasks."""

import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select, update, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from sqlalchemy import text, func, delete, and_

from app.models import Event, FuturesMarket, FuturesOutcome, FuturesOddsSnapshot, MatchingOverride
from app.models.models import BugReport, DiscoverInteraction, DiscoverReviewDecision, WinProbSnapshot
from app.services import get_db
from app.utils import probability_to_american
from app.utils.sport_keys import KALSHI_GAME_TICKER_PREFIXES

from app.routes.admin_utils import _check_admin_secret, _check_admin_auth  # noqa: F401 — re-exported for backward compat

router = APIRouter()


@router.post("/pulse/recalculate")
@router.post("/ei/recalculate")
async def recalculate_ei(
    secret: str = Query(..., description="Admin secret for authorization"),
    limit: int = Query(100, description="Max events to process per batch"),
    force: bool = Query(False, description="Force recalculation even if EI already exists"),
    db: AsyncSession = Depends(get_db),
):
    """
    Trigger EI (Excitement Index) recalculation for completed events.

    - If force=False: Only processes events without EI scores
    - If force=True: Clears existing EI data and recalculates all

    This is useful for:
    - Initial backfill after deploying EI
    - Recalculating after algorithm changes
    """
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.utils.excitement_index import calculate_ei, EIDataPoint
    from app.models import OddsSnapshot

    # If force mode, clear existing EI data first
    cleared_count = 0
    if force:
        # Clear scored events
        result = await db.execute(
            update(Event)
            .where(
                Event.status.in_(["completed", "closed"]),
                Event.raw_ei.isnot(None),
            )
            .values(raw_ei=None, ei_metadata=None, ei_computed_at=None)
        )
        cleared_count = result.rowcount
        # Also reset events previously marked as evaluated-but-unscorable
        await db.execute(
            update(Event)
            .where(
                Event.status.in_(["completed", "closed"]),
                Event.raw_ei.is_(None),
                Event.ei_computed_at.isnot(None),
            )
            .values(ei_computed_at=None)
        )
        await db.commit()

    # Find finished events that haven't been evaluated yet
    result = await db.execute(
        select(Event)
        .options(selectinload(Event.sport))
        .where(
            Event.status.in_(["completed", "closed"]),
            Event.ei_computed_at.is_(None),
        )
        .order_by(Event.commence_time.desc())
        .limit(limit)
    )
    events = result.scalars().all()

    if not events:
        return {
            "status": "success",
            "message": "No events to process",
            "cleared": cleared_count,
            "processed": 0,
            "remaining": 0,
        }

    processed = 0
    errors = 0
    error_details = []

    for event in events:
        try:
            # Get snapshots for this event
            snap_result = await db.execute(
                select(OddsSnapshot)
                .where(OddsSnapshot.event_id == event.id)
                .order_by(OddsSnapshot.captured_at)
            )
            snapshots = snap_result.scalars().all()

            if len(snapshots) < 3:
                # Mark as evaluated so we don't re-fetch it every time
                event.ei_computed_at = datetime.now(timezone.utc)
                continue

            # Convert to EIDataPoint objects
            data_points = [
                EIDataPoint(
                    captured_at=s.captured_at,
                    home_win_probability=float(s.home_win_probability) if s.home_win_probability else None,
                    source=s.bookmaker,
                    valid_until=s.valid_until,
                )
                for s in snapshots
            ]

            game_end = max(s.captured_at for s in snapshots)
            sport_key = event.sport.key if event.sport else "unknown"

            ei_result = calculate_ei(
                snapshots=data_points,
                game_start=event.commence_time,
                current_time=game_end,
                sport_key=sport_key,
            )

            if ei_result and ei_result.data_quality != "minimal":
                event.raw_ei = ei_result.score / 100.0
                event.ei_metadata = ei_result.metadata.to_json()
                event.ei_computed_at = datetime.now(timezone.utc)
                processed += 1
            else:
                # Evaluated but insufficient data — mark so we skip next time
                event.ei_computed_at = datetime.now(timezone.utc)

        except Exception as e:
            errors += 1
            if len(error_details) < 5:
                error_details.append(f"Event {event.id}: {str(e)}")

    await db.commit()

    # Check how many events still need evaluation
    remaining_result = await db.execute(
        select(Event.id)
        .where(
            Event.status.in_(["completed", "closed"]),
            Event.ei_computed_at.is_(None),
        )
    )
    remaining = len(remaining_result.all())

    return {
        "status": "success",
        "cleared": cleared_count,
        "processed": processed,
        "errors": errors,
        "error_details": error_details if error_details else None,
        "remaining": remaining,
        "message": f"Processed {processed} events. {remaining} remaining." +
                   (f" Call again to continue." if remaining > 0 else " All done!"),
    }


@router.get("/ei/diagnosis")
async def ei_diagnosis(
    secret: str = Query(..., description="Admin secret for authorization"),
    db: AsyncSession = Depends(get_db),
):
    """
    Diagnose why events don't have EI scores.

    Breaks down completed/closed events with raw_ei=NULL by root cause,
    including sport breakdown for zero-snapshot events.
    """
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from sqlalchemy import func, text

    # Count completed/closed events with no EI, grouped by snapshot count
    result = await db.execute(text("""
        SELECT
            CASE
                WHEN snap_count = 0 THEN 'zero_snapshots'
                WHEN snap_count < 3 THEN 'few_snapshots'
                ELSE 'has_snapshots'
            END AS category,
            COUNT(*) AS event_count
        FROM (
            SELECT e.id,
                   COALESCE((SELECT COUNT(*) FROM odds_snapshots os WHERE os.event_id = e.id), 0) AS snap_count
            FROM events e
            WHERE e.status IN ('completed', 'closed')
              AND e.raw_ei IS NULL
        ) sub
        GROUP BY 1
        ORDER BY 1
    """))
    rows = result.all()
    breakdown = {row[0]: row[1] for row in rows}
    total = sum(breakdown.values())

    # For zero-snapshot events: which sports and how old?
    zero_snap_detail = await db.execute(text("""
        SELECT s.key AS sport_key, COUNT(*) AS cnt,
               MIN(e.commence_time) AS oldest,
               MAX(e.commence_time) AS newest
        FROM events e
        LEFT JOIN sports s ON s.id = e.sport_id
        WHERE e.status IN ('completed', 'closed')
          AND e.raw_ei IS NULL
          AND NOT EXISTS (SELECT 1 FROM odds_snapshots os WHERE os.event_id = e.id)
        GROUP BY s.key
        ORDER BY cnt DESC
        LIMIT 15
    """))
    zero_by_sport = [
        {"sport": row[0], "count": row[1],
         "oldest": row[2].isoformat() if row[2] else None,
         "newest": row[3].isoformat() if row[3] else None}
        for row in zero_snap_detail.all()
    ]

    # For has_snapshots events: distribution of snapshot counts
    has_snap_detail = await db.execute(text("""
        SELECT
            CASE
                WHEN snap_count BETWEEN 3 AND 5 THEN '3-5'
                WHEN snap_count BETWEEN 6 AND 10 THEN '6-10'
                WHEN snap_count BETWEEN 11 AND 20 THEN '11-20'
                WHEN snap_count BETWEEN 21 AND 50 THEN '21-50'
                ELSE '51+'
            END AS bucket,
            COUNT(*) AS cnt
        FROM (
            SELECT e.id,
                   (SELECT COUNT(*) FROM odds_snapshots os WHERE os.event_id = e.id) AS snap_count
            FROM events e
            WHERE e.status IN ('completed', 'closed')
              AND e.raw_ei IS NULL
              AND (SELECT COUNT(*) FROM odds_snapshots os WHERE os.event_id = e.id) >= 3
        ) sub
        GROUP BY 1
        ORDER BY 1
    """))
    has_snap_buckets = {row[0]: row[1] for row in has_snap_detail.all()}

    return {
        "total_unscorable": total,
        "breakdown": breakdown,
        "zero_snapshots_by_sport": zero_by_sport,
        "has_snapshots_distribution": has_snap_buckets,
    }


@router.get("/pulse/status")
@router.get("/ei/status")
async def ei_status(
    secret: str = Query(..., description="Admin secret for authorization"),
    db: AsyncSession = Depends(get_db),
):
    """
    Get the current status of EI (Excitement Index) calculations.

    Returns counts of events with and without EI scores.
    """
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from sqlalchemy import func

    # Count events by EI status
    result = await db.execute(
        select(
            Event.status,
            func.count().filter(Event.raw_ei.isnot(None)).label("with_ei"),
            func.count().filter(Event.raw_ei.is_(None)).label("without_ei"),
        )
        .group_by(Event.status)
    )
    rows = result.all()

    status_counts = {}
    total_with = 0
    total_without = 0

    for status, with_ei, without_ei in rows:
        status_counts[status] = {
            "with_ei": with_ei,
            "without_ei": without_ei,
        }
        total_with += with_ei
        total_without += without_ei

    return {
        "total": {
            "with_ei": total_with,
            "without_ei": total_without,
        },
        "by_status": status_counts,
        "completion_pct": round(total_with / (total_with + total_without) * 100, 1) if (total_with + total_without) > 0 else 0,
    }


@router.post("/kalshi/poll")
async def trigger_kalshi_poll(
    secret: str = Query(..., description="Admin secret for authorization"),
):
    """
    Manually trigger Kalshi market polling.

    Queues the polling task to run in the background via Celery.
    Returns immediately with task ID - check Celery logs for results.
    Requires KALSHI_API_KEY to be configured.
    """
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    kalshi_key = os.getenv("KALSHI_API_KEY")
    if not kalshi_key:
        raise HTTPException(
            status_code=400,
            detail="KALSHI_API_KEY not configured. Add it to your environment variables."
        )

    # Queue the task to run in background (avoids Heroku's 30s timeout)
    from app.tasks import poll_kalshi_markets

    try:
        task = poll_kalshi_markets.delay()
        return {
            "status": "queued",
            "task_id": task.id,
            "message": "Kalshi polling task queued. Check Celery worker logs for results.",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to queue task: {str(e)}")


@router.get("/kalshi/task/{task_id}")
async def get_kalshi_task_status(
    task_id: str,
    secret: str = Query(..., description="Admin secret for authorization"),
):
    """
    Check the status of a Kalshi polling task.

    Returns the task state and result (if complete).
    """
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.tasks import celery_app

    result = celery_app.AsyncResult(task_id)
    response = {
        "task_id": task_id,
        "state": result.state,
    }

    if result.ready():
        if result.successful():
            response["result"] = result.result
        else:
            response["error"] = str(result.result)

    return response


@router.get("/kalshi/debug-discovery")
async def debug_kalshi_discovery(
    secret: str = Query(..., description="Admin secret for authorization"),
    search: Optional[str] = Query(None, description="Search term to filter series (e.g., 'olympic')"),
):
    """
    Debug Kalshi series discovery: shows what series each category returns,
    and optionally searches all series for a keyword.
    """
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    kalshi_key = os.getenv("KALSHI_API_KEY")
    if not kalshi_key:
        raise HTTPException(status_code=400, detail="KALSHI_API_KEY not configured")

    import asyncio
    from app.services.kalshi_api import KalshiAPIService

    service = KalshiAPIService()
    try:
        # Step 1: Discover tags by categories (reveals subcategories like Olympics)
        tags_by_category = None
        try:
            tags_by_category = await service.get_tags_by_categories()
        except Exception as e:
            tags_by_category = {"error": str(e)}

        await asyncio.sleep(0.3)

        # Step 2: Check each category
        categories = service.SPORTS_CATEGORIES
        category_results = {}

        for category in categories:
            await asyncio.sleep(0.3)
            try:
                series_list, _ = await service.get_series(category=category)
                tickers = [s.get("ticker") for s in series_list if s.get("ticker")]
                titles = [s.get("title", s.get("ticker", "?")) for s in series_list]
                tags_seen = set()
                for s in series_list:
                    for tag in (s.get("tags") or []):
                        tags_seen.add(tag)
                category_results[category] = {
                    "count": len(tickers),
                    "tickers": sorted(tickers)[:30],
                    "titles": titles[:30],
                    "tags_on_series": sorted(tags_seen),
                }
            except Exception as e:
                category_results[category] = {"error": str(e)}

        # Step 3: Try tag-based discovery for Olympics specifically
        olympics_tag_results = {}
        for tag in ["Olympics", "olympics", "Winter Olympics", "winter-olympics"]:
            await asyncio.sleep(0.3)
            try:
                series_list, _ = await service.get_series(category="Sports", tags=tag)
                tickers = [s.get("ticker") for s in series_list if s.get("ticker")]
                titles = [s.get("title", s.get("ticker", "?")) for s in series_list]
                olympics_tag_results[tag] = {
                    "count": len(tickers),
                    "tickers": sorted(tickers)[:20],
                    "titles": titles[:20],
                }
            except Exception as e:
                olympics_tag_results[tag] = {"error": str(e)}

        # Step 4: If search term provided, scan ALL series for keyword
        search_results = None
        if search:
            search_lower = search.lower()
            all_series = []
            cursor = None
            for page in range(10):  # Up to 10 pages
                await asyncio.sleep(0.3)
                page_series, cursor = await service.get_series(cursor=cursor)
                all_series.extend(page_series)
                if not cursor:
                    break

            matches = []
            for s in all_series:
                ticker = s.get("ticker", "")
                title = s.get("title", "")
                cat = s.get("category", "")
                tags = s.get("tags") or []
                tags_str = ",".join(tags).lower()
                if (search_lower in ticker.lower()
                    or search_lower in title.lower()
                    or search_lower in cat.lower()
                    or search_lower in tags_str):
                    matches.append({
                        "ticker": ticker,
                        "title": title,
                        "category": cat,
                        "tags": tags,
                    })

            search_results = {
                "query": search,
                "total_series_scanned": len(all_series),
                "matches": matches,
            }

        return {
            "tags_by_category": tags_by_category,
            "categories_checked": category_results,
            "olympics_tag_search": olympics_tag_results,
            "search_results": search_results,
        }

    finally:
        await service.close()


@router.post("/polymarket/poll")
async def trigger_polymarket_poll(
    secret: str = Query(..., description="Admin secret for authorization"),
):
    """
    Manually trigger Polymarket polling.

    Queues the polling task to run in the background via Celery.
    Returns immediately with task ID - check Celery logs for results.
    No API key required (Polymarket is fully public).
    """
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.tasks import poll_polymarket_markets

    try:
        task = poll_polymarket_markets.delay()
        return {
            "status": "queued",
            "task_id": task.id,
            "message": "Polymarket polling task queued. Use /api/admin/polymarket/task/{task_id} to check status.",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to queue task: {str(e)}")


@router.get("/polymarket/task/{task_id}")
async def get_polymarket_task_status(
    task_id: str,
    secret: str = Query(..., description="Admin secret for authorization"),
):
    """
    Check the status of a Polymarket polling/backfill task.

    Returns the task state and result (if complete).
    """
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.tasks import celery_app

    result = celery_app.AsyncResult(task_id)
    response = {
        "task_id": task_id,
        "state": result.state,
    }

    if result.ready():
        if result.successful():
            response["result"] = result.result
        else:
            response["error"] = str(result.result)

    return response


@router.post("/polymarket/backfill-history")
async def trigger_polymarket_history_backfill(
    secret: str = Query(..., description="Admin secret for authorization"),
    limit: int = Query(50, description="Max outcomes to process per run"),
    fidelity: int = Query(60, description="Price granularity in minutes (60=hourly, 1440=daily)"),
    interval: str = Query("max", description="Time range: 1h, 6h, 1d, 1w, max"),
):
    """
    Backfill historical price data from Polymarket's CLOB API.

    Fetches /prices-history for Polymarket outcomes that have sparse
    snapshot data. Prioritizes outcomes with the fewest existing snapshots.
    Uses ON CONFLICT DO NOTHING to avoid duplicate inserts.
    """
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.tasks import backfill_polymarket_history

    try:
        task = backfill_polymarket_history.delay(limit, fidelity, interval)
        return {
            "status": "queued",
            "task_id": task.id,
            "message": "Polymarket history backfill queued. Use /api/admin/polymarket/task/{task_id} to check status.",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to queue task: {str(e)}")


@router.post("/polymarket/fix-outcome-names")
async def fix_polymarket_outcome_names(
    secret: str = Query(..., description="Admin secret for authorization"),
):
    """
    Fix Polymarket outcome names using groupItemTitle from Gamma API.

    Finds FuturesMarket records (source='polymarket') where multiple outcomes
    share the same name, re-fetches the event from Polymarket's Gamma API,
    and updates outcome names using the groupItemTitle field.

    Runs as a background Celery task to avoid Heroku's 30-second HTTP timeout.
    """
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.tasks import fix_outcome_names

    try:
        task = fix_outcome_names.delay()
        return {
            "status": "queued",
            "task_id": task.id,
            "message": "Outcome names fix queued. Use /api/admin/polymarket/task/{task_id} to check status.",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to queue task: {str(e)}")


@router.post("/futures/poll")
async def trigger_futures_poll(
    secret: str = Query(..., description="Admin secret for authorization"),
):
    """
    Manually trigger futures/outrights polling from The Odds API.

    Queues the polling task to run in the background via Celery.
    Returns immediately with task ID - use /futures/task/{id} to check status.
    """
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.tasks import poll_futures_odds

    try:
        task = poll_futures_odds.delay()
        return {
            "status": "queued",
            "task_id": task.id,
            "message": "Futures polling task queued. Check Celery worker logs for results.",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to queue task: {str(e)}")


@router.get("/futures/task/{task_id}")
async def get_futures_task_status(
    task_id: str,
    secret: str = Query(..., description="Admin secret for authorization"),
):
    """
    Check the status of a futures polling task.

    Returns the task state and result (if complete).
    """
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.tasks import celery_app

    result = celery_app.AsyncResult(task_id)
    response = {
        "task_id": task_id,
        "state": result.state,
    }

    if result.ready():
        if result.successful():
            response["result"] = result.result
        else:
            response["error"] = str(result.result)

    return response


@router.get("/futures/sports")
async def get_sports_with_outrights(
    secret: str = Query(..., description="Admin secret for authorization"),
):
    """
    Debug endpoint: Get list of sports that have outrights/futures available.

    This calls The Odds API to see which sports have has_outrights=True.
    Useful for debugging why certain futures aren't appearing.
    """
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.services.odds_api import OddsAPIService

    try:
        service = OddsAPIService()
        outright_sports = await service.get_sports_with_outrights()
        return {
            "status": "success",
            "count": len(outright_sports),
            "sports": outright_sports,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch sports: {str(e)}")


@router.get("/pulse/distributions")
@router.get("/ei/distributions")
async def ei_distributions(
    secret: str = Query(..., description="Admin secret for authorization"),
    db: AsyncSession = Depends(get_db),
):
    """
    Analyze the distribution of EI scores and metadata across all scored events.

    Returns histograms and statistics for the overall score and EI metadata
    (raw_ei, lead_changes, comeback_factor).
    """
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    import json
    from sqlalchemy import func

    # Fetch all events with EI data
    result = await db.execute(
        select(
            Event.id,
            Event.raw_ei,
            Event.ei_metadata,
            Event.status,
        )
        .where(Event.raw_ei.isnot(None))
        .order_by(Event.raw_ei.desc())
    )
    rows = result.all()

    if not rows:
        return {"status": "no_data", "message": "No events with EI scores found"}

    scores = []
    # EI metadata fields (new format)
    metadata_fields = {
        "raw_ei": [],
        "comeback_factor": [],
    }
    lead_changes_list = []
    by_status = {}

    for event_id, raw_ei, ei_metadata_str, status in rows:
        score = max(1, min(100, round(float(raw_ei) * 100)))
        scores.append(score)

        # Count by event status
        by_status[status] = by_status.get(status, 0) + 1

        if ei_metadata_str:
            try:
                meta = json.loads(ei_metadata_str) if isinstance(ei_metadata_str, str) else ei_metadata_str
                for key in metadata_fields:
                    if key in meta:
                        metadata_fields[key].append(float(meta[key]))
                if "lead_changes" in meta:
                    lead_changes_list.append(int(meta["lead_changes"]))
            except (json.JSONDecodeError, TypeError, ValueError):
                pass

    def compute_stats(values: list) -> dict:
        if not values:
            return {}
        sorted_vals = sorted(values)
        n = len(sorted_vals)
        return {
            "count": n,
            "mean": round(sum(sorted_vals) / n, 2),
            "median": round(sorted_vals[n // 2], 2),
            "min": round(sorted_vals[0], 2),
            "max": round(sorted_vals[-1], 2),
            "p10": round(sorted_vals[int(n * 0.1)], 2),
            "p25": round(sorted_vals[int(n * 0.25)], 2),
            "p75": round(sorted_vals[int(n * 0.75)], 2),
            "p90": round(sorted_vals[int(n * 0.9)], 2),
        }

    def compute_histogram(values: list, buckets: list[tuple]) -> list[dict]:
        hist = []
        for label, lo, hi in buckets:
            count = sum(1 for v in values if lo <= v < hi)
            pct = round(count / len(values) * 100, 1) if values else 0
            hist.append({"range": label, "count": count, "pct": pct})
        return hist

    # Score histogram (10-point buckets)
    score_buckets = [
        ("1-10", 1, 11), ("11-20", 11, 21), ("21-30", 21, 31),
        ("31-40", 31, 41), ("41-50", 41, 51), ("51-60", 51, 61),
        ("61-70", 61, 71), ("71-80", 71, 81), ("81-90", 81, 91),
        ("91-100", 91, 101),
    ]

    # Component histogram (0-1 in 10% buckets, displayed as percentages)
    comp_buckets = [
        ("0-10%", 0.0, 0.1), ("10-20%", 0.1, 0.2), ("20-30%", 0.2, 0.3),
        ("30-40%", 0.3, 0.4), ("40-50%", 0.4, 0.5), ("50-60%", 0.5, 0.6),
        ("60-70%", 0.6, 0.7), ("70-80%", 0.7, 0.8), ("80-90%", 0.8, 0.9),
        ("90-100%", 0.9, 1.01),  # 1.01 to include exactly 1.0
    ]

    # EI status distribution
    status_labels = {
        "flat": (1, 20),
        "quiet": (21, 40),
        "competitive": (41, 60),
        "exciting": (61, 80),
        "incredible": (81, 100),
    }
    ei_status_dist = {}
    for label, (lo, hi) in status_labels.items():
        count = sum(1 for s in scores if lo <= s <= hi)
        ei_status_dist[label] = {
            "count": count,
            "pct": round(count / len(scores) * 100, 1),
        }

    return {
        "total_events": len(scores),
        "by_event_status": by_status,
        "score": {
            "stats": compute_stats(scores),
            "histogram": compute_histogram(scores, score_buckets),
            "status_distribution": ei_status_dist,
        },
        "metadata": {
            key: {
                "stats": compute_stats(vals),
                "histogram": compute_histogram(vals, comp_buckets),
            }
            for key, vals in metadata_fields.items()
        },
        "lead_changes": {
            "stats": compute_stats(lead_changes_list),
            "distribution": {
                str(i): sum(1 for lc in lead_changes_list if lc == i)
                for i in range(max(lead_changes_list) + 1)
            } if lead_changes_list else {},
        },
    }


@router.post("/espn/sync-teams")
async def sync_espn_teams(
    secret: str = Query(..., description="Admin secret for authorization"),
    sport_key: str = Query(..., description="Sport key to sync (e.g., basketball_nba)"),
    dry_run: bool = Query(False, description="Preview sync without saving"),
    db: AsyncSession = Depends(get_db),
):
    """
    Sync team data from ESPN (colors, logos, abbreviations).

    Fetches teams from ESPN API and updates matching teams in our database.
    Uses LLM for fuzzy name matching when direct match fails.
    """
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.services import get_espn_service, llm
    from app.models import Team, Sport

    espn = get_espn_service()

    # Get our teams for this sport
    sport_result = await db.execute(
        select(Sport).where(Sport.key == sport_key)
    )
    sport = sport_result.scalar_one_or_none()
    if not sport:
        raise HTTPException(status_code=404, detail=f"Sport not found: {sport_key}")

    teams_result = await db.execute(
        select(Team).where(Team.sport_id == sport.id)
    )
    our_teams = teams_result.scalars().all()

    if not our_teams:
        return {"status": "no_teams", "message": f"No teams found for {sport_key}"}

    # Fetch ESPN teams
    espn_teams = await espn.get_teams(sport_key)
    if not espn_teams:
        return {"status": "espn_error", "message": "Could not fetch teams from ESPN"}

    # Build lookup by name variations
    espn_lookup = {}
    for et in espn_teams:
        for name in [et.name, et.display_name, et.short_name, et.nickname, et.abbreviation]:
            if name:
                espn_lookup[name.lower()] = et

    matched = []
    unmatched = []
    updated = []

    for team in our_teams:
        espn_team = None
        match_type = None

        # Try exact match first
        name_lower = team.name.lower()
        if name_lower in espn_lookup:
            espn_team = espn_lookup[name_lower]
            match_type = "exact"
        else:
            # Try partial matching
            for key, et in espn_lookup.items():
                if key in name_lower or name_lower in key:
                    espn_team = et
                    match_type = "partial"
                    break

        # If still no match, try LLM
        if not espn_team and llm.is_available():
            best_score = 0
            for et in espn_teams:
                score = llm.match_team_names_cached(team.name, et.display_name or et.name, sport_key)
                if score > best_score and score >= 0.8:
                    best_score = score
                    espn_team = et
                    match_type = f"llm_{score:.2f}"

        if espn_team:
            matched.append({
                "our_team": team.name,
                "espn_team": espn_team.display_name or espn_team.name,
                "espn_id": espn_team.espn_id,
                "match_type": match_type,
                "primary_color": espn_team.primary_color,
                "secondary_color": espn_team.secondary_color,
                "logo": espn_team.logo_url,
            })

            if not dry_run:
                # Update team with ESPN data
                changed = False
                if espn_team.espn_id and team.espn_id != espn_team.espn_id:
                    team.espn_id = espn_team.espn_id
                    changed = True
                if espn_team.primary_color and team.primary_color != espn_team.primary_color:
                    team.primary_color = espn_team.primary_color
                    changed = True
                if espn_team.secondary_color and team.secondary_color != espn_team.secondary_color:
                    team.secondary_color = espn_team.secondary_color
                    changed = True
                if espn_team.logo_url and team.logo_url_small != espn_team.logo_url:
                    team.logo_url_small = espn_team.logo_url
                    team.logo_url_large = espn_team.logo_url
                    changed = True
                if espn_team.abbreviation and team.abbreviation != espn_team.abbreviation:
                    team.abbreviation = espn_team.abbreviation
                    changed = True
                if espn_team.record and team.current_record != espn_team.record:
                    team.current_record = espn_team.record
                    changed = True

                # Build alternate names
                alt_names = [espn_team.name, espn_team.display_name, espn_team.short_name, espn_team.nickname]
                alt_names = [n for n in alt_names if n and n != team.name]
                if alt_names:
                    team.alternate_names = alt_names
                    changed = True

                if changed:
                    updated.append(team.name)
        else:
            unmatched.append(team.name)

    if not dry_run:
        await db.commit()

    return {
        "status": "success",
        "dry_run": dry_run,
        "sport_key": sport_key,
        "our_teams": len(our_teams),
        "espn_teams": len(espn_teams),
        "matched": len(matched),
        "unmatched": len(unmatched),
        "updated": len(updated) if not dry_run else 0,
        "matches": matched[:20],  # Preview first 20
        "unmatched_teams": unmatched[:10] if unmatched else None,
    }


@router.get("/espn/teams-status")
async def espn_teams_status(
    secret: str = Query(..., description="Admin secret for authorization"),
    db: AsyncSession = Depends(get_db),
):
    """
    Get the status of ESPN team enrichment.

    Shows how many teams have ESPN data (colors, logos).
    """
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from sqlalchemy import func
    from app.models import Team

    result = await db.execute(
        select(
            func.count().label("total"),
            func.count().filter(Team.espn_id.isnot(None)).label("with_espn_id"),
            func.count().filter(Team.primary_color.isnot(None)).label("with_color"),
            func.count().filter(Team.logo_url_small.isnot(None)).label("with_logo"),
            func.count().filter(Team.alternate_names.isnot(None)).label("with_alt_names"),
        )
    )
    row = result.one()

    return {
        "total": row.total,
        "with_espn_id": row.with_espn_id,
        "with_color": row.with_color,
        "with_logo": row.with_logo,
        "with_alt_names": row.with_alt_names,
        "enrichment_pct": round(row.with_espn_id / row.total * 100, 1) if row.total > 0 else 0,
    }


@router.get("/rosters/teams-debug")
async def rosters_teams_debug(
    secret: str = Query(..., description="Admin secret for authorization"),
    sport_key: str = Query(..., description="Sport key (e.g., 'americanfootball_nfl')"),
    db: AsyncSession = Depends(get_db),
):
    """Debug: show team names, abbreviations, and roster status for a sport."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.models import Team, Sport

    sport_result = await db.execute(
        select(Sport.id, Sport.key).where(Sport.key == sport_key)
    )
    sport_row = sport_result.first()
    if not sport_row:
        return {"error": f"Sport '{sport_key}' not found"}

    result = await db.execute(
        select(
            Team.id, Team.name, Team.abbreviation, Team.roster_players
        ).where(Team.sport_id == sport_row.id).order_by(Team.name)
    )
    teams = result.all()

    return {
        "sport_key": sport_key,
        "sport_id": sport_row.id,
        "team_count": len(teams),
        "teams": [
            {
                "id": t.id,
                "name": t.name,
                "abbreviation": t.abbreviation,
                "roster_count": len(t.roster_players) if t.roster_players else 0,
            }
            for t in teams
        ],
    }


@router.post("/espn/sync-live-events")
async def sync_espn_live_events(
    secret: str = Query(..., description="Admin secret for authorization"),
    sport_key: str = Query(..., description="Sport key to sync"),
    dry_run: bool = Query(False, description="Preview sync without saving"),
    skip_llm: bool = Query(False, description="Skip LLM matching (faster, avoids timeout)"),
    db: AsyncSession = Depends(get_db),
):
    """
    Sync live event data from ESPN (scores, clock, period, venue, broadcast).

    Matches ESPN events to our events and updates game state.
    Use skip_llm=true to avoid timeouts when LLM matching is slow.
    """
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.services import get_espn_service, llm
    from app.models import Venue
    from sqlalchemy.orm import selectinload

    espn = get_espn_service()

    # Get ESPN scoreboard
    espn_events = await espn.get_scoreboard(sport_key)
    if not espn_events:
        return {"status": "no_events", "message": "No events from ESPN scoreboard"}

    # Get our live/upcoming events for this sport
    events_result = await db.execute(
        select(Event)
        .options(selectinload(Event.sport))
        .where(
            Event.sport.has(key=sport_key),
            Event.status.in_(["scheduled", "live"]),
        )
    )
    our_events = events_result.scalars().all()

    matched = []
    updated = []
    llm_matched = []

    def names_match(our_names: list, espn_name: str) -> bool:
        """Check if any of our name variations match the ESPN name."""
        espn_lower = (espn_name or "").lower()
        for name in our_names:
            name_lower = name.lower()
            if name_lower in espn_lower or espn_lower in name_lower:
                return True
        return False

    for event in our_events:
        # Build list of name variations for matching
        home_names = [event.home_team_name]
        away_names = [event.away_team_name]

        # Add normalized name if available
        if event.home_team_normalized:
            home_names.append(event.home_team_normalized)
        if event.away_team_normalized:
            away_names.append(event.away_team_normalized)

        # Add alternate names if available
        if event.home_team_alt_names:
            home_names.extend(event.home_team_alt_names)
        if event.away_team_alt_names:
            away_names.extend(event.away_team_alt_names)

        # Try to match by team names
        espn_event = None
        match_method = None

        for ee in espn_events:
            if not ee.home_team or not ee.away_team:
                continue

            espn_home = ee.home_team.display_name or ee.home_team.name or ""
            espn_away = ee.away_team.display_name or ee.away_team.name or ""

            # Check if team names match using all variations
            home_match = names_match(home_names, espn_home)
            away_match = names_match(away_names, espn_away)

            if home_match and away_match:
                espn_event = ee
                match_method = "name_match"
                break

        # LLM fallback for unmatched events (skip if skip_llm=true to avoid timeout)
        if not espn_event and not skip_llm and llm.is_available():
            for ee in espn_events:
                if not ee.home_team or not ee.away_team:
                    continue

                espn_home = ee.home_team.display_name or ee.home_team.name or ""
                espn_away = ee.away_team.display_name or ee.away_team.name or ""

                # Use LLM to compare team names
                home_conf = llm.match_team_names_cached(event.home_team_name, espn_home, sport_key)
                away_conf = llm.match_team_names_cached(event.away_team_name, espn_away, sport_key)

                if home_conf >= 0.8 and away_conf >= 0.8:
                    espn_event = ee
                    match_method = "llm"
                    llm_matched.append({
                        "our_event": f"{event.away_team_name} @ {event.home_team_name}",
                        "espn_event": f"{espn_away} @ {espn_home}",
                        "home_confidence": home_conf,
                        "away_confidence": away_conf,
                    })
                    break

        if espn_event:
            matched.append({
                "our_event": f"{event.away_team_name} @ {event.home_team_name}",
                "espn_event": espn_event.short_name,
                "espn_id": espn_event.espn_id,
                "status": espn_event.status,
                "clock": espn_event.clock,
                "period": espn_event.status_detail,
                "home_score": espn_event.home_score,
                "away_score": espn_event.away_score,
                "broadcasts": espn_event.broadcasts,
                "win_prob": espn_event.home_win_probability,
            })

            if not dry_run:
                changed = False

                # Update ESPN ID
                if espn_event.espn_id and event.espn_id != espn_event.espn_id:
                    event.espn_id = espn_event.espn_id
                    changed = True

                # Update game clock
                if espn_event.clock and event.game_clock != espn_event.clock:
                    event.game_clock = espn_event.clock
                    changed = True

                # Update period
                if espn_event.status_detail and event.period != espn_event.status_detail:
                    event.period = espn_event.status_detail
                    changed = True

                # Update broadcast info
                if espn_event.broadcasts:
                    broadcast_str = ", ".join(espn_event.broadcasts[:3])
                    if event.broadcast_info != broadcast_str:
                        event.broadcast_info = broadcast_str
                        changed = True

                # Update ESPN win probability
                if espn_event.home_win_probability is not None:
                    event.espn_win_prob_home = espn_event.home_win_probability
                    # Also update win_probability_sources
                    sources = event.win_probability_sources or {}
                    sources["espn"] = espn_event.home_win_probability
                    event.win_probability_sources = sources
                    changed = True

                # Handle venue
                if espn_event.venue and not event.venue_id:
                    # Check if venue exists
                    venue_result = await db.execute(
                        select(Venue).where(Venue.espn_id == espn_event.venue.espn_id)
                    )
                    venue = venue_result.scalar_one_or_none()

                    if not venue:
                        # Create new venue
                        venue = Venue(
                            name=espn_event.venue.name,
                            city=espn_event.venue.city,
                            state=espn_event.venue.state,
                            country=espn_event.venue.country,
                            capacity=espn_event.venue.capacity,
                            espn_id=espn_event.venue.espn_id,
                        )
                        db.add(venue)
                        await db.flush()

                    event.venue_id = venue.id
                    changed = True

                if changed:
                    updated.append(event.id)

    if not dry_run:
        await db.commit()

    return {
        "status": "success",
        "dry_run": dry_run,
        "sport_key": sport_key,
        "espn_events": len(espn_events),
        "our_events": len(our_events),
        "matched": len(matched),
        "llm_matched_count": len(llm_matched),
        "updated": len(updated) if not dry_run else 0,
        "matches": matched[:15],
        "llm_matches": llm_matched[:10] if llm_matched else [],
    }


@router.get("/espn/events-status")
async def espn_events_status(
    secret: str = Query(..., description="Admin secret for authorization"),
    db: AsyncSession = Depends(get_db),
):
    """
    Get the status of ESPN event enrichment.

    Shows how many events have ESPN data (clock, period, venue, win prob).
    """
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from sqlalchemy import func

    result = await db.execute(
        select(
            func.count().label("total"),
            func.count().filter(Event.espn_id.isnot(None)).label("with_espn_id"),
            func.count().filter(Event.game_clock.isnot(None)).label("with_clock"),
            func.count().filter(Event.period.isnot(None)).label("with_period"),
            func.count().filter(Event.venue_id.isnot(None)).label("with_venue"),
            func.count().filter(Event.broadcast_info.isnot(None)).label("with_broadcast"),
            func.count().filter(Event.espn_win_prob_home.isnot(None)).label("with_win_prob"),
        )
    )
    row = result.one()

    return {
        "total": row.total,
        "with_espn_id": row.with_espn_id,
        "with_clock": row.with_clock,
        "with_period": row.with_period,
        "with_venue": row.with_venue,
        "with_broadcast": row.with_broadcast,
        "with_win_prob": row.with_win_prob,
    }


@router.post("/espn/match-teams")
async def match_espn_teams(
    secret: str = Query(..., description="Admin secret for authorization"),
    our_team_name: str = Query(..., description="Our team name"),
    sport_key: str = Query(..., description="Sport key"),
    db: AsyncSession = Depends(get_db),
):
    """
    Debug endpoint: Try to match a team name using ESPN + LLM.

    Useful for testing entity resolution before bulk sync.
    """
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.services import get_espn_service, llm

    espn = get_espn_service()
    espn_teams = await espn.get_teams(sport_key)

    if not espn_teams:
        return {"status": "error", "message": "Could not fetch ESPN teams"}

    results = []
    for et in espn_teams:
        espn_name = et.display_name or et.name
        score = llm.match_team_names_cached(our_team_name, espn_name, sport_key) if llm.is_available() else 0.0

        if score >= 0.5:  # Only show likely matches
            results.append({
                "espn_name": espn_name,
                "espn_id": et.espn_id,
                "abbreviation": et.abbreviation,
                "confidence": score,
                "primary_color": et.primary_color,
            })

    # Sort by confidence
    results.sort(key=lambda x: x["confidence"], reverse=True)

    return {
        "query": our_team_name,
        "sport_key": sport_key,
        "espn_teams_searched": len(espn_teams),
        "llm_available": llm.is_available(),
        "matches": results[:10],
    }


@router.post("/futures/normalize-probabilities")
async def normalize_futures_probabilities(
    secret: str = Query(..., description="Admin secret for authorization"),
    dry_run: bool = Query(False, description="Preview changes without saving"),
    db: AsyncSession = Depends(get_db),
):
    """
    Normalize historical Odds API futures probabilities to remove vig/overround.

    Raw implied probabilities from American odds sum to >100% per bookmaker
    (typically 130-150% for markets with many outcomes). This endpoint:

    1. Normalizes all futures_odds_snapshots for odds_api markets
    2. Recalculates current_probability on futures_outcomes
    3. Recalculates opening_probability on futures_outcomes
    4. Recalculates American odds from normalized probabilities
    """
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from collections import defaultdict
    from statistics import mean

    stats = {
        "markets_processed": 0,
        "snapshots_normalized": 0,
        "outcomes_updated": 0,
        "sample_changes": [],
    }

    # Get all Odds API futures markets with their outcomes
    result = await db.execute(
        select(FuturesMarket)
        .options(selectinload(FuturesMarket.outcomes))
        .where(FuturesMarket.source == "odds_api")
    )
    markets = result.scalars().all()

    for market in markets:
        outcome_ids = [o.id for o in market.outcomes]
        if not outcome_ids:
            continue

        # Fetch all snapshots for this market's outcomes
        snap_result = await db.execute(
            select(FuturesOddsSnapshot)
            .where(FuturesOddsSnapshot.outcome_id.in_(outcome_ids))
            .order_by(FuturesOddsSnapshot.captured_at)
        )
        snapshots = snap_result.scalars().all()

        if not snapshots:
            continue

        stats["markets_processed"] += 1

        # Group snapshots by (bookmaker, captured_at) to find normalization factor
        # Key: (bookmaker, captured_at) -> list of (snapshot, probability)
        groups: dict[tuple, list] = defaultdict(list)
        for snap in snapshots:
            if snap.probability is not None:
                groups[(snap.bookmaker, snap.captured_at)].append(snap)

        # Normalize each group
        for (bookmaker, captured_at), group_snaps in groups.items():
            total_prob = sum(float(s.probability) for s in group_snaps)
            if total_prob <= 0 or abs(total_prob - 1.0) < 0.01:
                # Already normalized or invalid, skip
                continue

            for snap in group_snaps:
                old_prob = float(snap.probability)
                new_prob = old_prob / total_prob
                new_american = probability_to_american(new_prob) if new_prob > 0 else None

                if not dry_run:
                    snap.probability = new_prob
                    snap.american_odds = new_american

                stats["snapshots_normalized"] += 1

                # Capture a few examples
                if len(stats["sample_changes"]) < 10:
                    outcome_name = next(
                        (o.name for o in market.outcomes if o.id == snap.outcome_id),
                        "?"
                    )
                    stats["sample_changes"].append({
                        "market": market.name,
                        "outcome": outcome_name,
                        "bookmaker": bookmaker,
                        "old_prob": round(old_prob, 6),
                        "new_prob": round(new_prob, 6),
                        "normalization_factor": round(total_prob, 4),
                    })

        # Now recalculate current_probability and opening_probability
        # on each outcome using normalized snapshots
        for outcome in market.outcomes:
            outcome_snaps = [s for s in snapshots if s.outcome_id == outcome.id]
            if not outcome_snaps:
                continue

            # Current probability: average of most recent snapshot per bookmaker
            latest_by_bm: dict[str, FuturesOddsSnapshot] = {}
            for snap in outcome_snaps:
                bm = snap.bookmaker
                if bm not in latest_by_bm or snap.captured_at > latest_by_bm[bm].captured_at:
                    latest_by_bm[bm] = snap

            if latest_by_bm:
                avg_current = mean(
                    float(s.probability) for s in latest_by_bm.values()
                    if s.probability is not None
                )
                new_american = probability_to_american(avg_current) if avg_current > 0 else None
                if not dry_run:
                    outcome.current_probability = avg_current
                    outcome.current_american_odds = new_american

            # Opening probability: average of earliest snapshot per bookmaker
            earliest_by_bm: dict[str, FuturesOddsSnapshot] = {}
            for snap in outcome_snaps:
                bm = snap.bookmaker
                if bm not in earliest_by_bm or snap.captured_at < earliest_by_bm[bm].captured_at:
                    earliest_by_bm[bm] = snap

            if earliest_by_bm:
                avg_opening = mean(
                    float(s.probability) for s in earliest_by_bm.values()
                    if s.probability is not None
                )
                opening_american = probability_to_american(avg_opening) if avg_opening > 0 else None
                if not dry_run:
                    outcome.opening_probability = avg_opening
                    outcome.opening_american_odds = opening_american

            stats["outcomes_updated"] += 1

    if not dry_run:
        await db.commit()

    return {
        "status": "dry_run" if dry_run else "completed",
        "stats": stats,
    }


@router.post("/teams/backfill-logos")
async def trigger_team_logo_backfill(
    secret: str = Query(..., description="Admin secret for authorization"),
):
    """
    Manually trigger team logo backfill from ESPN's /teams endpoint.

    Fetches all teams for supported leagues and fills in missing logos.
    Queues as a background Celery task and returns immediately.
    """
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.tasks import backfill_team_logos

    try:
        task = backfill_team_logos.delay()
        return {
            "status": "queued",
            "task_id": task.id,
            "message": "Team logo backfill task queued. Check /api/admin/teams/task/{task_id} for results.",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to queue task: {str(e)}")


@router.get("/teams/task/{task_id}")
async def get_team_task_status(
    task_id: str,
    secret: str = Query(..., description="Admin secret for authorization"),
):
    """Check the status of a team logo backfill task."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.tasks import celery_app

    result = celery_app.AsyncResult(task_id)
    response = {
        "task_id": task_id,
        "state": result.state,
    }

    if result.ready():
        if result.successful():
            response["result"] = result.result
        else:
            response["error"] = str(result.result)

    return response


@router.get("/espn/task/{task_id}")
async def get_espn_task_status(
    task_id: str,
    secret: str = Query(..., description="Admin secret for authorization"),
):
    """Check the status of an ESPN correction task."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.tasks import celery_app

    result = celery_app.AsyncResult(task_id)
    response = {
        "task_id": task_id,
        "state": result.state,
    }

    if result.ready():
        if result.successful():
            response["result"] = result.result
        else:
            response["error"] = str(result.result)

    return response


@router.post("/espn/cleanup-bad-matches")
async def cleanup_bad_espn_matches(
    secret: str = Query(..., description="Admin secret for authorization"),
):
    """
    Validate existing ESPN ID assignments and clear bad matches.

    Fetches ESPN teams for each sport, compares team names using token-overlap
    scoring, and clears ESPN data (ID, logos, colors) for teams below the
    match threshold. Returns task_id for status checking.
    """
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.tasks import cleanup_bad_espn_matches as task

    result = task.delay()
    return {
        "status": "queued",
        "task_id": result.id,
        "message": "Cleanup task queued. Check status at /api/admin/espn/task/{task_id}",
    }


@router.post("/espn/backfill-boxscores")
async def backfill_box_scores(
    secret: str = Query(..., description="Admin secret for authorization"),
    limit: int = Query(100, description="Max events to process"),
    priority: str = Query("recent", description="'recent' (default) or 'calibration' (events with Kalshi props)"),
):
    """
    Backfill ESPN box score data for completed events.

    priority=calibration targets events with Kalshi player prop markets
    needing is_winner resolution first.
    """
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.tasks import backfill_box_scores as task

    result = task.delay(limit=limit, priority_calibration=(priority == "calibration"))
    return {
        "status": "queued",
        "task_id": result.id,
        "message": f"Box score backfill queued (limit={limit}). Check status at /api/admin/espn/task/{{task_id}}",
    }


@router.post("/espn/clear-unavailable")
async def clear_espn_unavailable(
    secret: str = Query(...),
    sport: str = Query(..., description="Sport key prefix to clear (e.g., 'icehockey')"),
    db: AsyncSession = Depends(get_db),
):
    """Clear 'not_available' box_score_data on events so they get retried."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.models.models import Event, Sport
    result = await db.execute(
        text("""
            UPDATE events e
            SET box_score_data = NULL
            FROM sports s
            WHERE e.sport_id = s.id
              AND s.key LIKE :pattern
              AND e.box_score_data IS NOT NULL
              AND e.box_score_data->>'error' = 'not_available'
        """),
        {"pattern": f"{sport}%"},
    )
    await db.commit()
    return {"cleared": result.rowcount, "sport_pattern": f"{sport}%"}


@router.post("/events/backfill-game-state")
async def backfill_game_state(
    secret: str = Query(..., description="Admin secret for authorization"),
    limit: int = Query(500, description="Max events to process"),
    sport: Optional[str] = Query(None, description="Sport key filter (e.g., 'baseball_mlb', 'basketball')"),
):
    """
    Backfill missing game state (period markers) for completed events.

    Finds completed/closed events with no period data in ScoringPlay table
    and reconstructs from ESPNSnapshot period data or score progression.
    Writes markers as WinProbSnapshot records with game_state.period so the
    history endpoint's existing fallback logic picks them up.

    Run with sport=baseball_mlb first (most impactful), then without filter
    for all sports. Safe to run multiple times — skips events that already
    have data.
    """
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.tasks import backfill_game_state as task

    result = task.delay(limit=limit, sport_filter=sport)
    return {
        "status": "queued",
        "task_id": result.id,
        "message": (
            f"Game state backfill queued (limit={limit}, sport={sport or 'all'}). "
            f"Check status at /api/admin/events/task/{{task_id}}"
        ),
    }


@router.get("/events/task/{task_id}")
async def get_event_task_status(
    task_id: str,
    secret: str = Query(..., description="Admin secret for authorization"),
):
    """Check the status of an event backfill task."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.tasks import celery_app

    result = celery_app.AsyncResult(task_id)
    response = {"task_id": task_id, "state": result.state}
    if result.ready():
        if result.successful():
            response["result"] = result.result
        else:
            response["error"] = str(result.result)
    return response


@router.get("/odds-api/usage")
async def odds_api_usage(
    secret: str = Query(..., description="Admin secret for authorization"),
):
    """Current Odds API quota status and hourly history."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.tasks.redis_state import get_odds_api_quota, get_odds_api_quota_history

    quota = get_odds_api_quota()
    history = get_odds_api_quota_history(hours=720)  # 30 days

    # Compute daily aggregates from hourly data
    daily = {}
    for entry in history:
        day = entry["hour"][:10]
        daily[day] = entry  # Last reading of each day

    daily_usage = []
    sorted_days = sorted(daily.keys())
    for i, day in enumerate(sorted_days):
        used = daily[day]["used"]
        prev_used = daily[sorted_days[i - 1]]["used"] if i > 0 else 0
        delta = used - prev_used
        # Handle month rollover (used resets to 0)
        if delta < 0:
            delta = used
        daily_usage.append({"date": day, "daily_requests": delta, "cumulative": used})

    return {
        "current": quota,
        "daily_usage": daily_usage,
        "hourly_history": history[-168:],  # Last 7 days hourly
    }


@router.get("/statpal/usage")
async def statpal_usage(
    secret: str = Query(..., description="Admin secret for authorization"),
):
    """Current StatPal API usage and daily history."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.tasks.redis_state import get_statpal_usage, get_statpal_usage_history

    daily_limit = 300_000
    current = get_statpal_usage()
    history = get_statpal_usage_history(days=90)

    # Add percentage and health status
    if current.get("request_count") is not None:
        count = current["request_count"]
        pct = round(count / daily_limit * 100, 1)
        current["daily_limit"] = daily_limit
        current["pct_used"] = pct
        current["health"] = "critical" if pct > 80 else "warning" if pct > 50 else "healthy"

    return {
        "current": current,
        "daily_history": history,
    }


@router.get("/odds-api/daily-activity")
async def odds_api_daily_activity(
    secret: str = Query(..., description="Admin secret for authorization"),
    db: AsyncSession = Depends(get_db),
    month: int = Query(2, description="Month (1-12)"),
    year: int = Query(2026, description="Year"),
    table: str = Query("odds", description="Table to query: odds, futures, winprob, or all"),
):
    """Infer daily Odds API call volume from snapshot row counts.

    Query one table at a time (table=odds|futures|winprob) to stay within
    Heroku's 30-second timeout, or table=all to try all three.
    """
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from sqlalchemy import text
    from datetime import date

    start = date(year, month, 1)
    if month == 12:
        end = date(year + 1, 1, 1)
    else:
        end = date(year, month + 1, 1)

    # Set a statement timeout to avoid blocking the DB
    await db.execute(text("SET LOCAL statement_timeout = '25s'"))

    results = {}

    if table in ("odds", "all"):
        try:
            odds_q = await db.execute(text("""
                SELECT captured_at::date AS day,
                       COUNT(*) AS rows,
                       COUNT(DISTINCT event_id) AS events
                FROM odds_snapshots
                WHERE captured_at >= :start AND captured_at < :end
                GROUP BY 1 ORDER BY 1
            """), {"start": start, "end": end})
            results["odds"] = [
                {"date": str(r.day), "rows": r.rows, "events": r.events}
                for r in odds_q.all()
            ]
        except Exception as e:
            results["odds_error"] = str(e)

    if table in ("futures", "all"):
        try:
            futures_q = await db.execute(text("""
                SELECT captured_at::date AS day,
                       COUNT(*) AS rows,
                       COUNT(DISTINCT outcome_id) AS outcomes
                FROM futures_odds_snapshots
                WHERE captured_at >= :start AND captured_at < :end
                GROUP BY 1 ORDER BY 1
            """), {"start": start, "end": end})
            results["futures"] = [
                {"date": str(r.day), "rows": r.rows, "outcomes": r.outcomes}
                for r in futures_q.all()
            ]
        except Exception as e:
            results["futures_error"] = str(e)

    if table in ("winprob", "all"):
        try:
            wp_q = await db.execute(text("""
                SELECT captured_at::date AS day,
                       COUNT(*) AS rows
                FROM win_prob_snapshots
                WHERE captured_at >= :start AND captured_at < :end
                GROUP BY 1 ORDER BY 1
            """), {"start": start, "end": end})
            results["winprob"] = [
                {"date": str(r.day), "rows": r.rows}
                for r in wp_q.all()
            ]
        except Exception as e:
            results["winprob_error"] = str(e)

    return {
        "month": f"{year}-{month:02d}",
        "table_filter": table,
        **results,
    }


# ---------------------------------------------------------------------------
# Team Linking (Futures → Teams)
# ---------------------------------------------------------------------------

@router.post("/futures/link-teams")
async def trigger_team_linking(
    secret: str = Query(..., description="Admin secret for authorization"),
    limit: int = Query(200, description="Max outcomes to process per run"),
    use_llm: bool = Query(True, description="Use LLM for player-team classification"),
):
    """Trigger team linking backfill for futures outcomes.

    Populates team_id on FuturesOutcome records (matching outcome names
    to Team records) and market_tier on FuturesMarket records.

    Runs as a background Celery task to avoid HTTP timeouts.
    """
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.tasks import backfill_team_links

    task = backfill_team_links.delay(limit=limit, use_llm=use_llm)
    return {
        "status": "queued",
        "task_id": task.id,
        "limit": limit,
        "use_llm": use_llm,
        "message": f"Team linking queued (limit={limit}). Use /api/admin/futures/link-teams/task/{task.id} to check status.",
    }


@router.get("/futures/link-teams/task/{task_id}")
async def get_team_linking_task_status(
    task_id: str,
    secret: str = Query(..., description="Admin secret for authorization"),
):
    """Check the status of a team linking backfill task."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.tasks import celery_app

    result = celery_app.AsyncResult(task_id)
    response = {
        "task_id": task_id,
        "state": result.state,
    }

    if result.ready():
        if result.successful():
            response["result"] = result.result
        else:
            response["error"] = str(result.result)

    return response


@router.get("/futures/team-links-status")
async def get_team_links_status(
    secret: str = Query(..., description="Admin secret for authorization"),
    db: AsyncSession = Depends(get_db),
):
    """Check the status of team linking across futures outcomes."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from sqlalchemy import func

    # Count outcomes with/without team_id
    total = (await db.execute(
        select(func.count(FuturesOutcome.id))
    )).scalar()
    linked = (await db.execute(
        select(func.count(FuturesOutcome.id))
        .where(FuturesOutcome.team_id.is_not(None))
    )).scalar()
    unlinked = total - linked

    # Count markets with/without market_tier
    markets_total = (await db.execute(
        select(func.count(FuturesMarket.id))
    )).scalar()
    markets_tiered = (await db.execute(
        select(func.count(FuturesMarket.id))
        .where(FuturesMarket.market_tier.is_not(None))
    )).scalar()

    return {
        "outcomes_total": total,
        "outcomes_linked": linked,
        "outcomes_unlinked": unlinked,
        "link_percentage": round(linked / total * 100, 1) if total else 0,
        "markets_total": markets_total,
        "markets_tiered": markets_tiered,
        "markets_untiered": markets_total - markets_tiered,
    }


@router.post("/teams/merge")
async def merge_duplicate_team(
    secret: str = Query(...),
    source_id: int = Query(..., description="Team ID to merge FROM (duplicate, will be deleted)"),
    target_id: int = Query(..., description="Team ID to merge INTO (canonical, will be kept)"),
    db: AsyncSession = Depends(get_db),
):
    """Merge a duplicate team into the canonical one. Reassigns all FKs then deletes the duplicate."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.models import Team
    from sqlalchemy import text

    # Verify both teams exist
    source = await db.get(Team, source_id)
    target = await db.get(Team, target_id)
    if not source:
        raise HTTPException(status_code=404, detail=f"Source team {source_id} not found")
    if not target:
        raise HTTPException(status_code=404, detail=f"Target team {target_id} not found")

    # Reassign all FKs from source to target
    fk_updates = [
        "UPDATE events SET home_team_id = :target WHERE home_team_id = :source",
        "UPDATE events SET away_team_id = :target WHERE away_team_id = :source",
        "UPDATE futures_outcomes SET team_id = :target WHERE team_id = :source",
        "UPDATE user_favorites SET team_id = :target WHERE team_id = :source",
        "UPDATE team_identity_mapping SET team_id = :target WHERE team_id = :source",
    ]
    counts = {}
    for sql in fk_updates:
        table = sql.split("UPDATE ")[1].split(" SET")[0]
        result = await db.execute(text(sql), {"source": source_id, "target": target_id})
        counts[table] = result.rowcount

    # Delete the duplicate
    await db.execute(text("DELETE FROM teams WHERE id = :source"), {"source": source_id})
    await db.commit()

    return {
        "merged": f"{source.name} (id={source_id}) → {target.name} (id={target_id})",
        "fk_updates": counts,
        "deleted_team_id": source_id,
    }


@router.get("/futures/team-links-sample")
async def sample_team_linked_outcomes(
    secret: str = Query(...),
    limit: int = Query(50),
    db: AsyncSession = Depends(get_db),
):
    """Sample recently linked outcomes to verify matching accuracy."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.models import Team

    result = await db.execute(
        select(
            FuturesOutcome.id,
            FuturesOutcome.name,
            FuturesOutcome.team_id,
            Team.name.label("team_name"),
            Team.sport_id,
            FuturesMarket.name.label("market_name"),
            FuturesMarket.source,
            FuturesMarket.llm_sport_category,
        )
        .join(Team, FuturesOutcome.team_id == Team.id)
        .join(FuturesMarket, FuturesOutcome.market_id == FuturesMarket.id)
        .where(FuturesOutcome.team_id.isnot(None))
        .order_by(FuturesOutcome.id.desc())
        .limit(limit)
    )
    samples = [
        {
            "outcome_id": r.id,
            "outcome_name": r.name,
            "team_id": r.team_id,
            "team_name": r.team_name,
            "market_name": r.market_name,
            "source": r.source,
            "sport_category": r.llm_sport_category,
        }
        for r in result.all()
    ]

    return {"count": len(samples), "samples": samples}


@router.get("/futures/team-links-debug")
async def debug_team_links(
    secret: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Debug team linking: show distribution of unlinked outcomes."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from sqlalchemy import text

    # How many markets have event_id?
    event_linked = await db.execute(text("""
        SELECT
            COUNT(*) FILTER (WHERE fm.event_id IS NOT NULL) AS markets_with_event,
            COUNT(*) FILTER (WHERE fm.event_id IS NULL) AS markets_without_event
        FROM futures_markets fm
    """))
    el = event_linked.first()

    # Unlinked outcomes on event-linked markets
    unlinked_event = await db.execute(text("""
        SELECT COUNT(*) FROM futures_outcomes fo
        JOIN futures_markets fm ON fo.market_id = fm.id
        WHERE fo.team_id IS NULL AND fm.event_id IS NOT NULL
    """))

    # Comprehensive breakdown by scope
    breakdown = await db.execute(text("""
        SELECT
            CASE
                WHEN fm.event_id IS NOT NULL THEN 'event_linked'
                WHEN fm.llm_sport_category IS NOT NULL THEN 'sport_scoped'
                ELSE 'unscoped'
            END AS scope,
            fm.source,
            fm.market_tier,
            COUNT(*) AS total_outcomes,
            COUNT(fo.team_id) AS linked,
            COUNT(*) - COUNT(fo.team_id) AS unlinked,
            -- Classify outcome types
            COUNT(*) FILTER (WHERE fo.name IN ('Yes', 'No')) AS yes_no_outcomes,
            COUNT(*) FILTER (WHERE fo.name ~* '^(Over|Under|O/U|Spread|Handicap|Draw|Tie)') AS generic_outcomes,
            COUNT(*) FILTER (WHERE fo.name ~* '(Winner|Game [0-9]|Map [0-9]|Match Winner)') AS game_label_outcomes,
            COUNT(*) FILTER (WHERE fo.name !~* '^(Yes|No|Over|Under|O/U|Spread|Handicap|Draw|Tie|Winner|Game [0-9]|Map [0-9]|Match Winner)'
                              AND length(fo.name) >= 4
                              AND fo.name ~ '[A-Z][a-z]+ [A-Z]') AS likely_names
        FROM futures_outcomes fo
        JOIN futures_markets fm ON fo.market_id = fm.id
        GROUP BY scope, fm.source, fm.market_tier
        ORDER BY scope, fm.source, fm.market_tier
    """))
    breakdown_rows = [
        {
            "scope": r.scope, "source": r.source, "tier": r.market_tier,
            "total": r.total_outcomes, "linked": r.linked, "unlinked": r.unlinked,
            "yes_no": r.yes_no_outcomes, "generic": r.generic_outcomes,
            "game_labels": r.game_label_outcomes, "likely_names": r.likely_names,
        }
        for r in breakdown.all()
    ]

    # Sample of "likely_names" that are unlinked (the ones we SHOULD be matching)
    name_samples = await db.execute(text("""
        SELECT fo.name, fm.name AS market_name, fm.event_id, fm.source,
               fm.llm_sport_category, fm.market_tier,
               CASE WHEN fm.event_id IS NOT NULL THEN 'event_linked'
                    WHEN fm.llm_sport_category IS NOT NULL THEN 'sport_scoped'
                    ELSE 'unscoped' END AS scope
        FROM futures_outcomes fo
        JOIN futures_markets fm ON fo.market_id = fm.id
        WHERE fo.team_id IS NULL
          AND fo.name !~* '^(Yes|No|Over|Under|O/U|Spread|Handicap|Draw|Tie|Winner|Game [0-9]|Map [0-9]|Match Winner)'
          AND length(fo.name) >= 4
          AND fo.name ~ '[A-Z][a-z]+ [A-Z]'
        ORDER BY random()
        LIMIT 40
    """))
    name_sample_list = [
        {"outcome": r.name, "market": r.market_name, "event_id": r.event_id,
         "source": r.source, "sport": r.llm_sport_category, "tier": r.market_tier,
         "scope": r.scope}
        for r in name_samples.all()
    ]

    # Team roster coverage
    roster_coverage = await db.execute(text("""
        SELECT s.key AS sport_key,
            COUNT(*) AS total_teams,
            COUNT(*) FILTER (WHERE t.roster_players IS NOT NULL AND t.roster_players != '[]'::jsonb) AS with_roster,
            AVG(jsonb_array_length(COALESCE(t.roster_players, '[]'::jsonb))) FILTER
                (WHERE t.roster_players IS NOT NULL AND t.roster_players != '[]'::jsonb) AS avg_roster_size
        FROM teams t
        JOIN sports s ON t.sport_id = s.id
        WHERE s.key IN ('basketball_nba', 'baseball_mlb', 'americanfootball_nfl', 'icehockey_nhl',
                        'basketball_ncaab', 'americanfootball_ncaaf')
        GROUP BY s.key
        ORDER BY total_teams DESC
    """))
    roster_data = [
        {"sport": r.sport_key, "total_teams": r.total_teams, "with_roster": r.with_roster,
         "avg_roster_size": round(float(r.avg_roster_size or 0), 1)}
        for r in roster_coverage.all()
    ]

    # US major sport matching rates
    us_sports = await db.execute(text("""
        SELECT
            fm.llm_sport_category AS sport,
            COUNT(*) AS total_outcomes,
            COUNT(fo.team_id) AS linked,
            COUNT(*) FILTER (
                WHERE fo.team_id IS NULL
                  AND fo.name !~* '^(Yes|No|Over|Under|O/U|Spread|Handicap|Draw|Tie|Push)$'
                  AND fo.name !~* '^(Match Winner|Game [0-9]|Map [0-9]|Round [0-9]|Odd/Even|Total Kills|First Blood)'
                  AND fo.name !~* '^[0-9]'
                  AND length(fo.name) >= 4
                  AND fo.name ~ '[A-Z][a-z]+ [A-Z]'
            ) AS unlinked_names
        FROM futures_outcomes fo
        JOIN futures_markets fm ON fo.market_id = fm.id
        WHERE fm.llm_sport_category IN ('basketball', 'baseball', 'football', 'hockey', 'golf')
        GROUP BY fm.llm_sport_category
        ORDER BY total_outcomes DESC
    """))
    us_sport_rates = [
        {"sport": r.sport, "total": r.total_outcomes, "linked": r.linked,
         "unlinked_names": r.unlinked_names,
         "match_rate": f"{r.linked*100/(r.linked+r.unlinked_names):.1f}%" if (r.linked + r.unlinked_names) > 0 else "0%"}
        for r in us_sports.all()
    ]

    return {
        "markets_with_event_id": el.markets_with_event if el else 0,
        "markets_without_event_id": el.markets_without_event if el else 0,
        "unlinked_outcomes_on_event_markets": unlinked_event.scalar(),
        "roster_coverage": roster_data,
        "us_sport_match_rates": us_sport_rates,
        "breakdown": breakdown_rows,
        "unlinked_name_samples": name_sample_list,
    }


# ---------------------------------------------------------------------------
# Canonical Market Key (Cross-source matching)
# ---------------------------------------------------------------------------

@router.post("/futures/backfill-canonical-keys")
async def trigger_canonical_key_backfill(
    secret: str = Query(..., description="Admin secret for authorization"),
    limit: int = Query(500, description="Max markets to process per run"),
):
    """Trigger backfill of canonical_market_key and llm_league on futures markets.

    Runs as a background Celery task. Returns task_id for status polling.
    """
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.tasks import backfill_canonical_keys
    task = backfill_canonical_keys.delay(limit)

    return {
        "status": "queued",
        "task_id": task.id,
        "message": f"Backfilling canonical keys for up to {limit} markets",
    }


@router.get("/futures/canonical-key-status")
async def get_canonical_key_status(
    secret: str = Query(..., description="Admin secret for authorization"),
    db: AsyncSession = Depends(get_db),
):
    """Check the status of canonical market key population across futures markets."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from sqlalchemy import func

    total = (await db.execute(
        select(func.count(FuturesMarket.id))
    )).scalar()
    with_key = (await db.execute(
        select(func.count(FuturesMarket.id))
        .where(FuturesMarket.canonical_market_key.is_not(None))
    )).scalar()
    with_league = (await db.execute(
        select(func.count(FuturesMarket.id))
        .where(FuturesMarket.llm_league.is_not(None))
    )).scalar()

    # Count distinct canonical keys with multiple sources
    multi_source = (await db.execute(
        select(func.count())
        .select_from(
            select(FuturesMarket.canonical_market_key)
            .where(FuturesMarket.canonical_market_key.is_not(None))
            .group_by(FuturesMarket.canonical_market_key)
            .having(func.count(func.distinct(FuturesMarket.source)) > 1)
            .subquery()
        )
    )).scalar()

    return {
        "markets_total": total,
        "markets_with_canonical_key": with_key,
        "markets_without_canonical_key": total - with_key,
        "markets_with_league": with_league,
        "canonical_key_percentage": round(with_key / total * 100, 1) if total else 0,
        "multi_source_keys": multi_source,
    }


# ---------------------------------------------------------------------------
# ESPN ID Backfill — retroactively match events to ESPN
# ---------------------------------------------------------------------------

@router.delete("/events/delete-duplicates")
async def delete_duplicate_events(
    secret: str = Query(...),
    event_ids: str = Query(..., description="Comma-separated event IDs to delete"),
    db: AsyncSession = Depends(get_db),
):
    """Delete specific duplicate events with FK cleanup."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from sqlalchemy import text

    ids = [int(x.strip()) for x in event_ids.split(",") if x.strip().isdigit()]
    if not ids:
        return {"error": "No valid event IDs provided"}

    # Clean up FKs
    fk_tables = [
        "odds_snapshots", "odds_aggregated", "win_prob_snapshots",
        "espn_snapshots", "score_snapshots", "scoring_plays",
        "line_movement_analyses",
    ]
    for table in fk_tables:
        await db.execute(text(f"DELETE FROM {table} WHERE event_id = ANY(:ids)"), {"ids": ids})

    await db.execute(text("UPDATE futures_markets SET event_id = NULL WHERE event_id = ANY(:ids)"), {"ids": ids})
    await db.execute(text("UPDATE user_pins SET target_id = NULL WHERE pin_type = 'event' AND target_id = ANY(:ids)"), {"ids": ids})

    result = await db.execute(text("DELETE FROM events WHERE id = ANY(:ids)"), {"ids": ids})
    await db.commit()

    return {"deleted": result.rowcount, "event_ids": ids}


@router.post("/teams/add-alias")
async def add_team_alias(
    secret: str = Query(...),
    team_id: int = Query(...),
    alias: str = Query(..., description="Alias to add to alternate_names"),
    db: AsyncSession = Depends(get_db),
):
    """Add an alias to a team's alternate_names list."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.models import Team
    team = await db.get(Team, team_id)
    if not team:
        raise HTTPException(status_code=404, detail=f"Team {team_id} not found")

    current = team.alternate_names or []
    if alias not in current:
        current.append(alias)
        team.alternate_names = current
        await db.commit()

    return {"team_id": team_id, "name": team.name, "alternate_names": current}


@router.post("/futures/retier")
async def retier_futures_markets(
    secret: str = Query(...),
    limit: int = Query(1000),
    db: AsyncSession = Depends(get_db),
):
    """Re-compute market_tier for all futures markets using current patterns."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.utils.market_label_normalization import compute_market_tier

    result = await db.execute(
        select(FuturesMarket).limit(limit)
    )
    markets = result.scalars().all()
    changed = 0
    for market in markets:
        new_tier = compute_market_tier(
            market.name, market.category,
            sport_category=market.llm_sport_category,
        )
        if market.market_tier != new_tier:
            market.market_tier = new_tier
            changed += 1

    await db.commit()
    return {"scanned": len(markets), "changed": changed}


@router.post("/espn/backfill-ids")
async def backfill_espn_ids(
    secret: str = Query(...),
    days: int = Query(7, description="How many days back to scan"),
    sport: Optional[str] = Query(None, description="Sport key filter (e.g., basketball_nba)"),
    dry_run: bool = Query(True, description="If true, report matches without updating"),
    db: AsyncSession = Depends(get_db),
):
    """Retroactively match events to ESPN schedules and set espn_id.

    Scans events from the last N days that have no espn_id, fetches ESPN's
    schedule for each date, and matches by team names.
    """
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.services.espn_api import ESPNAPIService
    from app.utils.sport_keys import ESPN_SPORT_MAPPING
    from app.utils.name_normalization import names_match
    from datetime import timedelta

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days)

    # Find events without ESPN ID
    from sqlalchemy.orm import selectinload
    query = (
        select(Event)
        .options(selectinload(Event.sport))
        .where(
            Event.espn_id.is_(None),
            Event.commence_time >= cutoff,
        )
        .order_by(Event.commence_time.desc())
    )
    if sport:
        query = query.where(Event.sport.has(key=sport))

    result = await db.execute(query)
    events = result.scalars().all()

    # Group by sport_key + date for efficient ESPN API calls.
    # ESPN uses US Eastern time for date boundaries, so a 10pm ET game on
    # April 14 = 2am UTC April 15. We must check BOTH UTC date and previous
    # day to catch cross-midnight games.
    from collections import defaultdict
    groups: dict[tuple[str, str], list] = defaultdict(list)
    for event in events:
        if not event.sport:
            continue
        sport_key = event.sport.key
        if sport_key not in ESPN_SPORT_MAPPING:
            continue
        utc_date = event.commence_time.strftime("%Y%m%d")
        prev_date = (event.commence_time - timedelta(days=1)).strftime("%Y%m%d")
        groups[(sport_key, utc_date)].append(event)
        # Also check previous day for late-night US games
        groups[(sport_key, prev_date)].append(event)

    # Fetch ESPN schedules and match
    espn = ESPNAPIService()
    matched = 0
    scanned = 0
    matches = []

    try:
        for (sport_key, date_str), group_events in groups.items():
            try:
                espn_events = await espn.get_scoreboard(sport_key, date=date_str)
            except Exception as e:
                continue

            if not espn_events:
                continue

            for event in group_events:
                scanned += 1
                for ee in espn_events:
                    if not ee.home_team or not ee.away_team:
                        continue
                    espn_home = ee.home_team.display_name or ee.home_team.name or ""
                    espn_away = ee.away_team.display_name or ee.away_team.name or ""

                    # Match both teams (either orientation)
                    normal = (
                        names_match(event.home_team_name, espn_home) and
                        names_match(event.away_team_name, espn_away)
                    )
                    swapped = (
                        names_match(event.home_team_name, espn_away) and
                        names_match(event.away_team_name, espn_home)
                    )

                    if normal or swapped:
                        matches.append({
                            "event_id": event.id,
                            "our_teams": f"{event.home_team_name} vs {event.away_team_name}",
                            "espn_teams": f"{espn_home} vs {espn_away}",
                            "espn_id": ee.espn_id,
                            "date": date_str,
                            "sport": sport_key,
                            "orientation": "normal" if normal else "swapped",
                        })

                        if not dry_run:
                            event.espn_id = ee.espn_id
                            # Also update win prob if ESPN has it
                            if ee.home_win_probability is not None:
                                event.espn_win_prob_home = ee.home_win_probability
                                sources = event.win_probability_sources or {}
                                sources["espn"] = ee.home_win_probability
                                event.win_probability_sources = sources

                        matched += 1
                        break

        if not dry_run:
            await db.commit()

    finally:
        await espn.close()

    # Collect unmatched events with details
    matched_event_ids = {m["event_id"] for m in matches}
    unmatched = []
    for event in events:
        if event.id not in matched_event_ids and event.sport and event.sport.key in ESPN_SPORT_MAPPING:
            date_str = event.commence_time.strftime("%Y%m%d")
            espn_for_date = []
            for (sk, ds), evts in groups.items():
                if sk == event.sport.key and ds == date_str:
                    # We need to re-check what ESPN had for this date
                    pass
            unmatched.append({
                "event_id": event.id,
                "our_teams": f"{event.home_team_name} vs {event.away_team_name}",
                "sport": event.sport.key,
                "date": date_str,
                "status": event.status,
            })

    return {
        "dry_run": dry_run,
        "days_scanned": days,
        "events_without_espn_id": len(events),
        "events_scanned": scanned,
        "events_matched": matched,
        "match_rate": f"{matched*100/scanned:.1f}%" if scanned else "N/A",
        "matches": matches[:50],
        "unmatched": unmatched[:30],
    }


# ---------------------------------------------------------------------------
# Roster Sync (ESPN + MLB Stats API)
# ---------------------------------------------------------------------------

@router.post("/rosters/sync")
async def trigger_roster_sync(
    secret: str = Query(..., description="Admin secret for authorization"),
    sport_key: Optional[str] = Query(None, description="Sport key (e.g., 'basketball_nba'). If omitted, syncs all supported sports."),
):
    """Trigger roster sync from ESPN + MLB Stats API (runs as background Celery task).

    Fetches player rosters and stores them on Team.roster_players for use
    in related-futures player name matching.
    """
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.tasks import sync_rosters

    task = sync_rosters.delay(sport_key=sport_key)
    return {
        "status": "queued",
        "task_id": task.id,
        "sport_key": sport_key or "all",
        "message": f"Roster sync queued. Use /api/admin/rosters/task/{task.id} to check status.",
    }


@router.get("/rosters/task/{task_id}")
async def get_roster_sync_task_status(
    task_id: str,
    secret: str = Query(..., description="Admin secret for authorization"),
):
    """Check the status of a roster sync task."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.tasks import celery_app

    result = celery_app.AsyncResult(task_id)
    response = {
        "task_id": task_id,
        "state": result.state,
    }

    if result.ready():
        if result.successful():
            response["result"] = result.result
        else:
            response["error"] = str(result.result)

    return response


# ---------------------------------------------------------------------------
# Snapshot Retention
# ---------------------------------------------------------------------------


@router.post("/mlb/sync")
async def trigger_mlb_win_prob_sync(
    secret: str = Query(..., description="Admin secret for authorization"),
):
    """
    Trigger a one-off MLB win probability sync.

    Fetches live MLB games from the MLB Stats API and writes win probability
    snapshots for matched events. Normally runs automatically every 2 minutes.
    """
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.tasks import sync_mlb_win_probability

    try:
        task = sync_mlb_win_probability.delay()
        return {
            "status": "queued",
            "task_id": task.id,
            "message": f"MLB win probability sync queued. "
                       f"Use /api/admin/mlb/task/{task.id} to check status.",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to queue task: {str(e)}")


@router.get("/mlb/task/{task_id}")
async def get_mlb_task_status(
    task_id: str,
    secret: str = Query(..., description="Admin secret for authorization"),
):
    """Check the status of an MLB sync task."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.tasks import celery_app

    result = celery_app.AsyncResult(task_id)
    response = {"task_id": task_id, "state": result.state}
    if result.ready():
        if result.successful():
            response["result"] = result.result
        else:
            response["error"] = str(result.result)
    return response


# =============================================================================
# Manual Event Creation (for sports not covered by The Odds API)
# =============================================================================


@router.post("/events/create")
async def create_event_manually(
    secret: str = Query(..., description="Admin secret for authorization"),
    home_team: str = Query(..., description="Home team name (e.g., 'USA', 'Canada')"),
    away_team: str = Query(..., description="Away team name"),
    sport_key: str = Query(..., description="Sport key (e.g., 'icehockey_olympics')"),
    sport_name: Optional[str] = Query(None, description="Sport display name (auto-generated if omitted)"),
    commence_time: Optional[str] = Query(None, description="ISO 8601 timestamp (defaults to now)"),
    status: str = Query("live", description="Event status: scheduled, live, completed, closed"),
    db: AsyncSession = Depends(get_db),
):
    """
    Manually create an Event for sports that The Odds API doesn't cover.

    Useful for Olympics, special events, or any sport where events need to
    exist for prediction market linking.

    After creating, use POST /api/admin/prediction-markets/link to connect
    prediction markets, or trigger the matching task to auto-link.
    """
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.models.models import Sport

    # Parse commence_time
    ct = datetime.now(timezone.utc)
    if commence_time:
        try:
            ct = datetime.fromisoformat(commence_time)
            if ct.tzinfo is None:
                ct = ct.replace(tzinfo=timezone.utc)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid commence_time: {commence_time}")

    # Get or create Sport record
    sport_result = await db.execute(
        select(Sport).where(Sport.key == sport_key)
    )
    sport = sport_result.scalar_one_or_none()
    if not sport:
        display_name = sport_name or sport_key.replace("_", " ").title()
        group = sport_key.split("_")[0].title() if "_" in sport_key else display_name
        sport = Sport(key=sport_key, name=display_name, group=group, active=True)
        db.add(sport)
        await db.flush()

    # Check for duplicate
    existing = await db.execute(
        select(Event).where(
            Event.home_team_name == home_team,
            Event.away_team_name == away_team,
            Event.status.in_(["scheduled", "live"]),
        ).limit(1)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=409,
            detail=f"Event already exists for {home_team} vs {away_team}",
        )

    # Create event
    external_id = f"manual_{sport_key}_{home_team}_{away_team}_{int(ct.timestamp())}"
    event = Event(
        sport_id=sport.id,
        external_id=external_id,
        home_team_name=home_team,
        away_team_name=away_team,
        commence_time=ct,
        status=status,
    )
    db.add(event)
    await db.commit()
    await db.refresh(event)

    return {
        "status": "created",
        "event_id": event.id,
        "external_id": event.external_id,
        "home_team": home_team,
        "away_team": away_team,
        "sport_key": sport_key,
        "commence_time": ct.isoformat(),
        "event_status": status,
        "url": f"https://bainluck.com/events/{event.id}",
        "next_step": f"Link prediction markets: POST /api/admin/prediction-markets/link?market_id=XXX&event_id={event.id}&secret=...",
    }


@router.patch("/events/{event_id}")
async def patch_event(
    event_id: int,
    secret: str = Query(..., description="Admin secret for authorization"),
    home_team: Optional[str] = Query(None, description="New home team name"),
    away_team: Optional[str] = Query(None, description="New away team name"),
    status: Optional[str] = Query(None, description="New status"),
    db: AsyncSession = Depends(get_db),
):
    """Patch an event's fields (admin only)."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    result = await db.execute(select(Event).where(Event.id == event_id))
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail=f"Event {event_id} not found")

    updates = {}
    if home_team is not None:
        event.home_team_name = home_team
        updates["home_team"] = home_team
    if away_team is not None:
        event.away_team_name = away_team
        updates["away_team"] = away_team
    if status is not None:
        event.status = status
        updates["status"] = status

    await db.commit()
    return {"event_id": event_id, "updated": updates}


@router.post("/fix-live-statuses")
async def fix_live_statuses(
    secret: str = Query(..., description="Admin secret for authorization"),
    dry_run: bool = Query(False, description="Preview without making changes"),
    db: AsyncSession = Depends(get_db),
):
    """Fix events incorrectly stuck in 'live' status.

    Resets events to 'scheduled' if they are marked 'live' but their
    commence_time is more than 1 hour in the future (clearly haven't started).
    """
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from datetime import timedelta

    now = datetime.now(timezone.utc)
    cutoff = now + timedelta(hours=1)  # Buffer for clock drift

    # Find events marked live but with future commence_time
    result = await db.execute(
        select(Event).where(
            Event.status == "live",
            Event.commence_time > cutoff,
        )
    )
    bad_events = result.scalars().all()

    if dry_run:
        return {
            "dry_run": True,
            "events_to_fix": len(bad_events),
            "samples": [
                {
                    "id": e.id,
                    "external_id": e.external_id[:60] if e.external_id else None,
                    "home_team": e.home_team_name,
                    "away_team": e.away_team_name,
                    "commence_time": e.commence_time.isoformat() if e.commence_time else None,
                    "status": e.status,
                }
                for e in bad_events[:20]
            ],
        }

    # Fix them
    fixed_count = 0
    for event in bad_events:
        event.status = "scheduled"
        fixed_count += 1

    await db.commit()

    return {
        "fixed": fixed_count,
        "message": f"Reset {fixed_count} events from 'live' to 'scheduled'",
    }


# =========================================================================
# Matching Audit endpoints
# =========================================================================


@router.post("/statpal/sync-schedules")
async def trigger_statpal_schedule_sync(
    secret: str = Query(..., description="Admin secret for authorization"),
    sport_key: str = Query(None, description="Sport key (e.g., basketball_nba). If omitted, syncs all."),
):
    """
    Trigger a StatPal schedule/fixture sync.

    Fetches fixtures from StatPal, corrects commence_time errors from The Odds API,
    populates end_time for finished games, and stores StatPal fixture IDs for
    play-by-play lookups.
    """
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.tasks import sync_statpal_schedules

    try:
        task = sync_statpal_schedules.delay(sport_key=sport_key)
        return {
            "status": "queued",
            "task_id": task.id,
            "message": f"StatPal schedule sync queued{f' for {sport_key}' if sport_key else ' (all sports)'}. "
                       f"Use /api/admin/statpal/task/{task.id} to check status.",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to queue task: {str(e)}")


@router.get("/events/creation-lead-time")
async def event_creation_lead_time(
    secret: str = Query(..., description="Admin secret for authorization"),
    sport: str = Query("basketball_nba", description="Sport key"),
    days: int = Query(14, description="Look back N days"),
    db: AsyncSession = Depends(get_db),
):
    """How far in advance are Tier 1 events created before their commence_time?"""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from datetime import datetime, timezone, timedelta
    from sqlalchemy import text as _text

    await db.execute(_text("SET LOCAL statement_timeout = '15s'"))

    result = await db.execute(_text("""
        SELECT
            e.id,
            e.home_team_name,
            e.away_team_name,
            e.commence_time,
            e.created_at,
            e.status,
            e.external_id,
            e.statpal_fixture_id,
            e.commence_time_source,
            EXTRACT(EPOCH FROM (e.commence_time - e.created_at)) / 3600 AS lead_hours
        FROM events e
        JOIN sports s ON e.sport_id = s.id
        WHERE s.key = :sport
          AND e.commence_time > NOW() - make_interval(days => :days_back)
          AND e.created_at IS NOT NULL
          AND e.commence_time IS NOT NULL
        ORDER BY e.commence_time DESC
        LIMIT 50
    """), {"sport": sport, "days_back": days})
    rows = result.all()

    events = []
    for r in rows:
        events.append({
            "id": r.id,
            "matchup": f"{r.away_team_name} vs {r.home_team_name}",
            "commence": r.commence_time.isoformat()[:16] if r.commence_time else None,
            "created": r.created_at.isoformat()[:16] if r.created_at else None,
            "lead_hours": round(r.lead_hours, 1) if r.lead_hours else None,
            "status": r.status,
            "source": r.commence_time_source,
            "has_odds_api": r.external_id is not None,
            "has_statpal": r.statpal_fixture_id is not None,
        })

    lead_hours = [e["lead_hours"] for e in events if e["lead_hours"] is not None]
    return {
        "sport": sport,
        "events_analyzed": len(events),
        "lead_time_stats": {
            "min_hours": round(min(lead_hours), 1) if lead_hours else None,
            "max_hours": round(max(lead_hours), 1) if lead_hours else None,
            "median_hours": round(sorted(lead_hours)[len(lead_hours) // 2], 1) if lead_hours else None,
            "avg_hours": round(sum(lead_hours) / len(lead_hours), 1) if lead_hours else None,
            "under_6h": sum(1 for h in lead_hours if h < 6),
            "under_24h": sum(1 for h in lead_hours if h < 24),
            "under_48h": sum(1 for h in lead_hours if h < 48),
        },
        "events": events,
    }


@router.get("/statpal/probe-endpoints")
async def statpal_probe_endpoints(
    secret: str = Query(..., description="Admin secret for authorization"),
    sport: str = Query("nba", description="StatPal sport"),
):
    """Probe StatPal with different endpoints/params to find playoff schedules."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.services.statpal_api import StatPalAPIService, is_available
    if not is_available():
        return {"error": "StatPal API key not configured"}

    from datetime import datetime, timezone
    svc = StatPalAPIService()
    results = {}

    probes = [
        ("season-schedule (default)", "season-schedule", {}),
        ("season-schedule (season=2025-2026)", "season-schedule", {"season": "2025-2026"}),
        ("season-schedule (season=2026)", "season-schedule", {"season": "2026"}),
        ("season-schedule (season=playoffs)", "season-schedule", {"season": "playoffs"}),
        ("season-schedule (season=postseason)", "season-schedule", {"season": "postseason"}),
        ("fixtures (no params)", "fixtures", {}),
        ("schedule (no params)", "schedule", {}),
        ("upcoming-schedule", "upcoming-schedule", {}),
        ("season-schedule (date=2026-05-11)", "season-schedule", {"date": "2026-05-11"}),
        ("daily-schedule", "daily-schedule", {}),
        ("daily-schedule (date=today)", "daily-schedule", {"date": "2026-05-11"}),
        ("games", "games", {}),
        ("games/today", "games/today", {}),
        ("results", "results", {}),
        ("matches", "matches", {}),
        ("events", "events", {}),
        ("playoff-schedule", "playoff-schedule", {}),
        ("postseason-schedule", "postseason-schedule", {}),
        ("playoffs", "playoffs", {}),
    ]

    now = datetime.now(timezone.utc)

    # Grab RAW JSON to see if playoffs are present but dropped by parser
    raw_data = await svc._get(sport, "season-schedule", {})
    raw_debug = {}
    if raw_data and isinstance(raw_data, dict):
        raw_debug["top_keys"] = list(raw_data.keys())[:10]
        # Drill into scores → tournament structure
        scores = raw_data.get("scores")
        if isinstance(scores, dict):
            raw_debug["scores_keys"] = list(scores.keys())[:10]
            tournament = scores.get("tournament")
            if isinstance(tournament, dict):
                raw_debug["tournament_type"] = "dict"
                raw_debug["tournament_keys"] = list(tournament.keys())[:10]
                matches = tournament.get("match", [])
                raw_debug["match_count"] = len(matches) if isinstance(matches, list) else "not_a_list"
                raw_debug["tournament_league"] = tournament.get("league")
                raw_debug["tournament_season"] = tournament.get("season")
                raw_debug["tournament_id"] = tournament.get("id")
                raw_debug["tournament_country"] = tournament.get("country")
                raw_debug["tournament_week"] = tournament.get("week")
            elif isinstance(tournament, list):
                raw_debug["tournament_type"] = "LIST"
                raw_debug["tournament_count"] = len(tournament)
                for i, t in enumerate(tournament[:5]):
                    if isinstance(t, dict):
                        league = t.get("league", "?")
                        match_count = len(t.get("match", [])) if isinstance(t.get("match"), list) else "?"
                        raw_debug[f"tournament_{i}"] = {
                            "league": league,
                            "match_count": match_count,
                            "keys": list(t.keys())[:8],
                        }
            else:
                raw_debug["tournament_type"] = type(tournament).__name__ if tournament else "missing"

    for label, endpoint, params in probes:
        try:
            data = await svc._get(sport, endpoint, params)
            if data is None:
                results[label] = {"status": "null/error", "count": 0}
                continue
            fixtures = svc._parse_fixtures(data, sport)
            future = [f for f in fixtures if f.start_time and f.start_time > now]
            latest = max((f.start_time for f in fixtures if f.start_time), default=None)
            results[label] = {
                "status": "ok",
                "total": len(fixtures),
                "future": len(future),
                "latest_date": latest.isoformat()[:10] if latest else None,
                "sample_future": [
                    {"home": f.home_team, "away": f.away_team,
                     "time": f.start_time.isoformat()[:16] if f.start_time else None}
                    for f in future[:5]
                ],
            }
        except Exception as e:
            results[label] = {"status": f"error: {str(e)[:100]}", "count": 0}

    results["_raw_debug"] = raw_debug
    return results


@router.get("/statpal/fixture-debug")
async def statpal_fixture_debug(
    secret: str = Query(..., description="Admin secret for authorization"),
    sport: str = Query("nba", description="StatPal sport (nba, nhl, mlb)"),
):
    """Show raw StatPal fixture data to debug date parsing."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.services.statpal_api import StatPalAPIService, is_available
    if not is_available():
        return {"error": "StatPal API key not configured"}

    svc = StatPalAPIService()
    fixtures = await svc.get_fixtures(sport)

    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    none_count = sum(1 for f in fixtures if f.start_time is None)
    future = [f for f in fixtures if f.start_time and f.start_time > now]
    past_week = [f for f in fixtures if f.start_time and (now - f.start_time).days < 7 and f.start_time <= now]

    return {
        "total_fixtures": len(fixtures),
        "with_start_time": len(fixtures) - none_count,
        "without_start_time": none_count,
        "future_fixtures": len(future),
        "past_week_fixtures": len(past_week),
        "sample_future": [
            {"home": f.home_team, "away": f.away_team,
             "start_time": f.start_time.isoformat() if f.start_time else None,
             "status": f.status, "fixture_id": f.fixture_id}
            for f in future[:10]
        ],
        "sample_none_time": [
            {"home": f.home_team, "away": f.away_team,
             "fixture_id": f.fixture_id, "status": f.status}
            for f in fixtures[:5] if f.start_time is None
        ][:5],
        "date_range": {
            "earliest": min((f.start_time for f in fixtures if f.start_time), default=None),
            "latest": max((f.start_time for f in fixtures if f.start_time), default=None),
        } if fixtures else {},
        "sample_all": [
            {"home": f.home_team, "away": f.away_team,
             "start_time": f.start_time.isoformat() if f.start_time else None,
             "fixture_id": f.fixture_id, "status": f.status}
            for f in fixtures[-5:]
        ],
    }


@router.post("/statpal/sync-injuries")
async def trigger_statpal_injury_sync(
    secret: str = Query(..., description="Admin secret for authorization"),
    sport_key: str = Query(None, description="Sport key (e.g., basketball_nba). If omitted, syncs all."),
):
    """
    Trigger a StatPal injury report sync.

    Fetches injury reports and attaches them to upcoming/live events for
    "Why Did the Line Move?" context.
    """
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.tasks import sync_statpal_injuries

    try:
        task = sync_statpal_injuries.delay(sport_key=sport_key)
        return {
            "status": "queued",
            "task_id": task.id,
            "message": f"StatPal injury sync queued. "
                       f"Use /api/admin/statpal/task/{task.id} to check status.",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to queue task: {str(e)}")


@router.post("/statpal/sync-plays")
async def trigger_statpal_play_sync(
    secret: str = Query(..., description="Admin secret for authorization"),
    sport_key: str = Query(None, description="Sport key. If omitted, syncs all live games."),
):
    """
    Trigger a StatPal play-by-play sync for live games.

    Fetches recent plays from live games to provide context for probability
    movements and Pulse calculations.
    """
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.tasks import sync_statpal_live_plays

    try:
        task = sync_statpal_live_plays.delay(sport_key=sport_key)
        return {
            "status": "queued",
            "task_id": task.id,
            "message": f"StatPal play-by-play sync queued. "
                       f"Use /api/admin/statpal/task/{task.id} to check status.",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to queue task: {str(e)}")


@router.post("/statpal/sync-rosters")
async def trigger_statpal_roster_sync(
    secret: str = Query(..., description="Admin secret for authorization"),
    sport_key: str = Query(None, description="Sport key. If omitted, syncs all."),
):
    """
    Trigger a StatPal roster sync (supplements ESPN roster data).

    Only updates teams that don't already have roster data from ESPN.
    """
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.tasks import sync_statpal_rosters

    try:
        task = sync_statpal_rosters.delay(sport_key=sport_key)
        return {
            "status": "queued",
            "task_id": task.id,
            "message": f"StatPal roster sync queued. "
                       f"Use /api/admin/statpal/task/{task.id} to check status.",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to queue task: {str(e)}")


@router.get("/statpal/task/{task_id}")
async def get_statpal_task_status(
    task_id: str,
    secret: str = Query(..., description="Admin secret for authorization"),
):
    """Check the status of a StatPal sync task."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.tasks import celery_app

    result = celery_app.AsyncResult(task_id)
    response = {"task_id": task_id, "state": result.state}
    if result.ready():
        if result.successful():
            response["result"] = result.result
        else:
            response["error"] = str(result.result)
    return response


@router.get("/statpal/status")
async def statpal_status(
    secret: str = Query(..., description="Admin secret for authorization"),
):
    """Check StatPal integration status — API key configured, sport mapping, etc."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.services.statpal_api import is_available
    from app.tasks.config import STATPAL_SPORT_MAPPING

    return {
        "api_key_configured": is_available(),
        "mapped_sports": list(STATPAL_SPORT_MAPPING.keys()),
        "endpoints": {
            "sync_schedules": "POST /api/admin/statpal/sync-schedules",
            "sync_injuries": "POST /api/admin/statpal/sync-injuries",
            "sync_plays": "POST /api/admin/statpal/sync-plays",
            "sync_rosters": "POST /api/admin/statpal/sync-rosters",
            "sync_standings": "POST /api/admin/statpal/sync-standings",
            "sync_team_stats": "POST /api/admin/statpal/sync-team-stats",
            "task_status": "GET /api/admin/statpal/task/{task_id}",
        },
    }


@router.post("/statpal/sync-standings")
async def trigger_statpal_standings_sync(
    secret: str = Query(..., description="Admin secret for authorization"),
    sport_key: str = Query(None, description="Optional: limit to one sport key"),
):
    """Trigger StatPal standings sync (daily task, runs at 8:00 AM UTC)."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.tasks import sync_statpal_standings

    try:
        task = sync_statpal_standings.delay(sport_key=sport_key)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to queue task: {e}")
    return {
        "status": "queued",
        "task_id": task.id,
        "message": f"Standings sync queued. "
                   f"Use /api/admin/statpal/task/{task.id} to check status.",
    }


@router.post("/statpal/sync-team-stats")
async def trigger_statpal_team_stats_sync(
    secret: str = Query(..., description="Admin secret for authorization"),
    sport_key: str = Query(None, description="Optional: limit to one sport key"),
):
    """Trigger StatPal team stats sync (weekly task, runs Monday 9:00 AM UTC)."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.tasks import sync_statpal_team_stats

    try:
        task = sync_statpal_team_stats.delay(sport_key=sport_key)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to queue task: {e}")
    return {
        "status": "queued",
        "task_id": task.id,
        "message": f"Team stats sync queued. "
                   f"Use /api/admin/statpal/task/{task.id} to check status.",
    }


# =============================================================================
# Team Identity endpoints
# =============================================================================


@router.get("/team-identity/status")
async def team_identity_status(
    secret: str = Query(..., description="Admin secret for authorization"),
    db: AsyncSession = Depends(get_db),
):
    """Count mappings by source, total mapped teams, unmapped teams."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from sqlalchemy import func as sqlfunc
    from app.models import TeamIdentityMapping, Team

    # Count by source
    source_counts = await db.execute(
        select(TeamIdentityMapping.source, sqlfunc.count(TeamIdentityMapping.id))
        .group_by(TeamIdentityMapping.source)
    )
    by_source = {row[0]: row[1] for row in source_counts.all()}

    # Total mapped team IDs
    mapped_count = await db.execute(
        select(sqlfunc.count(sqlfunc.distinct(TeamIdentityMapping.team_id)))
    )
    total_mapped = mapped_count.scalar() or 0

    # Total teams
    total_teams = await db.execute(select(sqlfunc.count(Team.id)))
    total = total_teams.scalar() or 0

    return {
        "total_teams": total,
        "mapped_teams": total_mapped,
        "unmapped_teams": total - total_mapped,
        "mappings_by_source": by_source,
        "total_mappings": sum(by_source.values()),
    }


@router.post("/team-identity/backfill")
async def trigger_team_identity_backfill(
    secret: str = Query(..., description="Admin secret for authorization"),
):
    """Trigger one-time backfill of team identity mappings from existing data."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.tasks import backfill_team_identities
    try:
        task = backfill_team_identities.delay()
        return {
            "status": "queued",
            "task_id": task.id,
            "message": f"Team identity backfill queued. "
                       f"Use /api/admin/team-identity/task/{task.id} to check status.",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to queue task: {str(e)}")


@router.get("/team-identity/task/{task_id}")
async def team_identity_task_status(
    task_id: str,
    secret: str = Query(..., description="Admin secret for authorization"),
):
    """Check team identity task status."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.tasks import celery_app as app
    result = app.AsyncResult(task_id)
    response = {"task_id": task_id, "state": result.state}
    if result.state == "SUCCESS":
        response["result"] = result.result
    elif result.state == "FAILURE":
        response["error"] = str(result.result)
    return response


@router.get("/team-identity/search")
async def team_identity_search(
    q: str = Query(..., description="Search query for team name"),
    secret: str = Query(..., description="Admin secret for authorization"),
    db: AsyncSession = Depends(get_db),
):
    """Search team identity mappings across all sources."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.models import TeamIdentityMapping, Team

    result = await db.execute(
        select(TeamIdentityMapping, Team.name).join(
            Team, TeamIdentityMapping.team_id == Team.id,
        ).where(
            or_(
                TeamIdentityMapping.source_name.ilike(f"%{q}%"),
                TeamIdentityMapping.source_abbreviation.ilike(f"%{q}%"),
                TeamIdentityMapping.source_id.ilike(f"%{q}%"),
            )
        ).order_by(Team.name).limit(50)
    )

    rows = result.all()
    return {
        "query": q,
        "count": len(rows),
        "results": [
            {
                "mapping_id": mapping.id,
                "team_id": mapping.team_id,
                "team_name": team_name,
                "source": mapping.source,
                "source_id": mapping.source_id,
                "source_name": mapping.source_name,
                "source_abbreviation": mapping.source_abbreviation,
                "sport_key": mapping.sport_key,
            }
            for mapping, team_name in rows
        ],
    }


@router.get("/team-identity/team/{team_id}")
async def team_identity_detail(
    team_id: int,
    secret: str = Query(..., description="Admin secret for authorization"),
    db: AsyncSession = Depends(get_db),
):
    """All identity mappings for a specific team."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.models import TeamIdentityMapping, Team

    # Get team info
    team_result = await db.execute(select(Team).where(Team.id == team_id))
    team = team_result.scalar_one_or_none()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    # Get mappings
    mapping_result = await db.execute(
        select(TeamIdentityMapping).where(
            TeamIdentityMapping.team_id == team_id,
        ).order_by(TeamIdentityMapping.source)
    )
    mappings = mapping_result.scalars().all()

    return {
        "team": {
            "id": team.id,
            "name": team.name,
            "abbreviation": team.abbreviation,
            "espn_id": team.espn_id,
            "alternate_names": team.alternate_names,
        },
        "mappings": [
            {
                "id": m.id,
                "source": m.source,
                "source_id": m.source_id,
                "source_name": m.source_name,
                "source_abbreviation": m.source_abbreviation,
                "sport_key": m.sport_key,
                "updated_at": m.updated_at.isoformat() if m.updated_at else None,
            }
            for m in mappings
        ],
    }


@router.get("/team-identity/unmapped")
async def team_identity_unmapped(
    secret: str = Query(..., description="Admin secret for authorization"),
    sport_key: str = Query(None, description="Filter by sport key"),
    db: AsyncSession = Depends(get_db),
):
    """Teams with no identity mappings."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.services.team_identity import TeamIdentityService
    service = TeamIdentityService()
    teams = await service.get_unmapped_teams(db, sport_key=sport_key)

    return {
        "count": len(teams),
        "sport_key": sport_key,
        "teams": [
            {
                "id": t.id,
                "name": t.name,
                "abbreviation": t.abbreviation,
                "espn_id": t.espn_id,
                "sport_id": t.sport_id,
            }
            for t in teams
        ],
    }


@router.delete("/line-movement/cache/{event_id}")
async def clear_line_movement_cache(
    event_id: int,
    secret: str = Query(..., description="Admin secret for authorization"),
    db: AsyncSession = Depends(get_db),
):
    """Delete cached line movement explanations for an event so they regenerate."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.models.models import LineMovementAnalysis

    result = await db.execute(
        select(LineMovementAnalysis).where(
            LineMovementAnalysis.event_id == event_id,
            LineMovementAnalysis.analysis_type == "line_movement",
        )
    )
    rows = result.scalars().all()
    for row in rows:
        await db.delete(row)
    await db.commit()

    return {"deleted": len(rows), "event_id": event_id}


# =============================================================================
# Event Taxonomy
# =============================================================================


@router.get("/market-lookup")
async def market_lookup(
    secret: str = Query(...),
    ticker: str = Query(None),
    name: str = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Look up futures markets by external_id prefix or name pattern."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")
    from app.models import FuturesMarket
    query = select(
        FuturesMarket.id, FuturesMarket.external_id, FuturesMarket.name,
        FuturesMarket.status, FuturesMarket.source, FuturesMarket.market_tier,
        FuturesMarket.llm_sport_category,
    )
    if ticker:
        query = query.where(FuturesMarket.external_id.ilike(f"{ticker}%"))
    elif name:
        query = query.where(FuturesMarket.name.ilike(f"%{name}%"))
    else:
        raise HTTPException(status_code=400, detail="Provide ticker or name")
    query = query.limit(20)
    result = await db.execute(query)
    return [
        {"id": r.id, "external_id": r.external_id, "name": r.name,
         "status": r.status, "source": r.source, "tier": r.market_tier,
         "category": r.llm_sport_category}
        for r in result.all()
    ]


# ── Duplicate event detection + merge ──────────────────────────────────


@router.get("/events/duplicates")
async def list_duplicate_events(
    secret: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Find duplicate events: same sport, same teams, same date."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from sqlalchemy import text

    result = await db.execute(text("""
        WITH dupes AS (
            SELECT a.id AS id_a, b.id AS id_b
            FROM events a
            JOIN events b ON (
                a.sport_id = b.sport_id
                AND a.id < b.id
                AND LOWER(a.home_team_name) = LOWER(b.home_team_name)
                AND LOWER(a.away_team_name) = LOWER(b.away_team_name)
                AND ABS(EXTRACT(EPOCH FROM (a.commence_time - b.commence_time))) < 21600
            )
            WHERE a.commence_time > NOW() - INTERVAL '30 days'
              AND b.commence_time > NOW() - INTERVAL '30 days'
            LIMIT 100
        )
        SELECT
            a.id AS event_a_id, a.external_id AS event_a_external_id,
            EXISTS(SELECT 1 FROM odds_snapshots WHERE event_id = a.id LIMIT 1) AS event_a_has_snaps,
            a.statpal_fixture_id AS event_a_statpal,
            a.commence_time_source AS event_a_source,
            a.status AS event_a_status,
            b.id AS event_b_id, b.external_id AS event_b_external_id,
            EXISTS(SELECT 1 FROM odds_snapshots WHERE event_id = b.id LIMIT 1) AS event_b_has_snaps,
            b.statpal_fixture_id AS event_b_statpal,
            b.commence_time_source AS event_b_source,
            b.status AS event_b_status,
            s.key AS sport_key,
            a.home_team_name, a.away_team_name,
            a.commence_time AS commence_a,
            b.commence_time AS commence_b
        FROM dupes d
        JOIN events a ON a.id = d.id_a
        JOIN events b ON b.id = d.id_b
        JOIN sports s ON s.id = a.sport_id
        ORDER BY a.commence_time DESC
    """))
    rows = result.all()

    duplicates = []
    for row in rows:
        duplicates.append({
            "event_a": {
                "id": row.event_a_id,
                "external_id": row.event_a_external_id,
                "has_snapshots": row.event_a_has_snaps,
                "statpal_fixture_id": row.event_a_statpal,
                "commence_time_source": row.event_a_source,
                "status": row.event_a_status,
            },
            "event_b": {
                "id": row.event_b_id,
                "external_id": row.event_b_external_id,
                "has_snapshots": row.event_b_has_snaps,
                "statpal_fixture_id": row.event_b_statpal,
                "commence_time_source": row.event_b_source,
                "status": row.event_b_status,
            },
            "sport": row.sport_key,
            "home_team": row.home_team_name,
            "away_team": row.away_team_name,
            "commence_a": row.commence_a.isoformat() if row.commence_a else None,
            "commence_b": row.commence_b.isoformat() if row.commence_b else None,
        })

    return {
        "duplicate_count": len(duplicates),
        "duplicates": duplicates,
    }


@router.post("/events/merge-duplicates")
async def merge_duplicate_events(
    secret: str = Query(...),
    dry_run: bool = Query(True, description="Preview without making changes"),
):
    """Queue a Celery task to merge duplicate events.

    Runs in background to avoid Heroku 30s timeout.
    Check status with GET /api/admin/events/merge-task/{task_id}
    """
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.tasks import merge_duplicate_events_task
    task = merge_duplicate_events_task.delay(dry_run=dry_run)
    return {
        "status": "queued",
        "task_id": task.id,
        "dry_run": dry_run,
        "message": f"Merge task queued ({'dry run' if dry_run else 'LIVE'}). Check /api/admin/events/merge-task/{task.id}",
    }


@router.post("/events/merge-duplicates-sql")
async def merge_duplicate_events_sql(
    secret: str = Query(...),
    dry_run: bool = Query(True, description="Preview without making changes"),
    db: AsyncSession = Depends(get_db),
):
    """Merge duplicate events: find orphans, clear FK refs, then delete."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from sqlalchemy import text

    # Step 1: Find keeper-orphan pairs
    # Case A: keeper has external_id, orphan doesn't (StatPal vs Odds API)
    # Case B: both NULL external_id — keep lowest ID (StatPal vs StatPal dupes)
    result = await db.execute(text("""
        SELECT
            keeper.id AS keeper_id, orphan.id AS orphan_id,
            orphan.statpal_fixture_id, orphan.commence_time_source,
            orphan.statpal_end_time, orphan.home_team_id,
            orphan.away_team_id, orphan.espn_id
        FROM events keeper
        JOIN events orphan ON (
            keeper.sport_id = orphan.sport_id
            AND keeper.id != orphan.id
            AND LOWER(keeper.home_team_name) = LOWER(orphan.home_team_name)
            AND LOWER(keeper.away_team_name) = LOWER(orphan.away_team_name)
            AND ABS(EXTRACT(EPOCH FROM (keeper.commence_time - orphan.commence_time))) < 21600
        )
        WHERE keeper.commence_time > NOW() - INTERVAL '30 days'
          AND orphan.commence_time > NOW() - INTERVAL '30 days'
          AND NOT EXISTS(SELECT 1 FROM odds_snapshots WHERE event_id = orphan.id LIMIT 1)
          AND (
              -- Case A: keeper has external_id, orphan doesn't
              (keeper.external_id IS NOT NULL AND orphan.external_id IS NULL)
              OR
              -- Case B: both NULL, keep lowest ID
              (keeper.external_id IS NULL AND orphan.external_id IS NULL AND keeper.id < orphan.id)
          )
    """))
    pairs = result.all()

    if dry_run:
        return {"dry_run": True, "would_merge": len(pairs)}

    orphan_ids = [row.orphan_id for row in pairs]
    if not orphan_ids:
        return {"dry_run": False, "merged": 0, "deleted": 0}

    try:
        # Step 2: Absorb metadata per keeper
        for row in pairs:
            set_clauses = []
            params = {"kid": row.keeper_id}
            fields = [
                ("statpal_fixture_id", row.statpal_fixture_id),
                ("commence_time_source", row.commence_time_source),
                ("statpal_end_time", row.statpal_end_time),
                ("home_team_id", row.home_team_id),
                ("away_team_id", row.away_team_id),
                ("espn_id", row.espn_id),
            ]
            for i, (field, value) in enumerate(fields):
                if value is not None:
                    set_clauses.append(f"{field} = COALESCE({field}, :v{i})")
                    params[f"v{i}"] = value
            if set_clauses:
                await db.execute(
                    text(f"UPDATE events SET {', '.join(set_clauses)} WHERE id = :kid"),
                    params,
                )

        # Step 3: Clear ALL FK references to orphans before deleting
        # Tables with ON DELETE CASCADE (espn_snapshots, win_prob_snapshots) are auto-handled.
        fk_tables = [
            "odds_snapshots",
            "odds_aggregated",
            "score_snapshots",
            "line_movement_analyses",
        ]
        for table in fk_tables:
            await db.execute(
                text(f"DELETE FROM {table} WHERE event_id = ANY(:ids)"),
                {"ids": orphan_ids},
            )
        # futures_markets has nullable event_id — NULL it instead of deleting
        await db.execute(
            text("UPDATE futures_markets SET event_id = NULL WHERE event_id = ANY(:ids)"),
            {"ids": orphan_ids},
        )

        # Step 4: Now delete orphan events (CASCADE handles espn/win_prob snapshots)
        await db.execute(
            text("DELETE FROM events WHERE id = ANY(:ids)"),
            {"ids": orphan_ids},
        )

        await db.commit()
        return {
            "dry_run": False,
            "merged": len(pairs),
            "deleted": len(orphan_ids),
        }
    except Exception as e:
        await db.rollback()
        import traceback
        return {
            "error": str(e),
            "error_type": type(e).__name__,
            "traceback": traceback.format_exc()[-2000:],
            "orphan_ids": orphan_ids[:10],
            "pairs_count": len(pairs),
        }


@router.get("/events/merge-task/{task_id}")
async def check_merge_task(
    task_id: str,
    secret: str = Query(...),
):
    """Check status of a merge-duplicates background task."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from celery.result import AsyncResult
    from app.tasks import celery_app
    result = AsyncResult(task_id, app=celery_app)
    response = {
        "task_id": task_id,
        "state": result.state,
    }
    if result.state == "SUCCESS":
        response["result"] = result.result
    elif result.state == "FAILURE":
        response["error"] = str(result.result)
    return response


# =============================================================================
# DataGolf Admin Endpoints
# =============================================================================


@router.post("/datagolf/poll")
async def trigger_datagolf_poll(
    secret: str = Query(..., description="Admin secret for authorization"),
):
    """Manually trigger DataGolf market polling (runs inline, not via Celery queue).

    The worker only has 2 concurrency slots permanently occupied by
    high-frequency tasks, so Celery .delay() would queue but never execute.
    """
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.tasks.datagolf import _poll_datagolf_markets
    try:
        result = await _poll_datagolf_markets()
        return {"status": "completed", "result": result}
    except Exception as exc:
        return {"status": "error", "error": str(exc)[:500]}


@router.post("/datagolf/poll-live")
async def trigger_datagolf_live_poll(
    secret: str = Query(..., description="Admin secret for authorization"),
):
    """Manually trigger DataGolf live in-play polling (runs inline)."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.tasks.datagolf import _poll_datagolf_live
    try:
        result = await _poll_datagolf_live()
        return {"status": "completed", "result": result}
    except Exception as exc:
        return {"status": "error", "error": str(exc)[:500]}


@router.get("/datagolf/debug-schedule")
async def datagolf_debug_schedule(
    secret: str = Query(..., description="Admin secret for authorization"),
):
    """Fetch raw DataGolf schedule for field name discovery."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.services.datagolf_api import DataGolfAPIService
    service = DataGolfAPIService()
    try:
        data = await service._get("get-schedule", {"tour": "pga"})
        schedule = data.get("schedule", [])
        sample = schedule[:3] if schedule else []
        return {
            "top_level_keys": list(data.keys()),
            "schedule_count": len(schedule),
            "sample_entries": sample,
            "all_keys_first_entry": list(schedule[0].keys()) if schedule else [],
        }
    except Exception as exc:
        return {"error": str(exc)[:500]}
    finally:
        await service.close()


@router.get("/datagolf/status")
async def datagolf_status(
    secret: str = Query(..., description="Admin secret for authorization"),
    db: AsyncSession = Depends(get_db),
):
    """Check DataGolf integration status: markets, outcomes, live flags."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from sqlalchemy import func

    # Count DataGolf markets
    market_result = await db.execute(
        select(func.count(FuturesMarket.id)).where(
            FuturesMarket.source == "datagolf"
        )
    )
    total_markets = market_result.scalar() or 0

    # Count open DataGolf markets
    open_result = await db.execute(
        select(func.count(FuturesMarket.id)).where(
            FuturesMarket.source == "datagolf",
            FuturesMarket.status == "open",
        )
    )
    open_markets = open_result.scalar() or 0

    # Count outcomes across DataGolf markets
    outcome_result = await db.execute(
        select(func.count(FuturesOutcome.id)).where(
            FuturesOutcome.market_id.in_(
                select(FuturesMarket.id).where(FuturesMarket.source == "datagolf")
            )
        )
    )
    total_outcomes = outcome_result.scalar() or 0

    # Count snapshots (last 24h)
    snap_result = await db.execute(
        select(func.count(FuturesOddsSnapshot.id)).where(
            FuturesOddsSnapshot.bookmaker == "datagolf_model",
            FuturesOddsSnapshot.captured_at >= datetime.now(timezone.utc) - timedelta(hours=24),
        )
    )
    recent_snapshots = snap_result.scalar() or 0

    # Check Redis live flags
    live_tours = {}
    try:
        from app.tasks.redis_state import get_redis_client
        from app.tasks.datagolf import LIVE_KEY_PREFIX, POLL_TOURS
        r = get_redis_client()
        for tour in POLL_TOURS:
            key = f"{LIVE_KEY_PREFIX}:{tour}"
            live_tours[tour] = r.exists(key) == 1
    except Exception:
        live_tours = {"error": "Redis unavailable"}

    # Get latest DataGolf markets with metadata
    latest_result = await db.execute(
        select(FuturesMarket)
        .where(FuturesMarket.source == "datagolf", FuturesMarket.status == "open")
        .order_by(FuturesMarket.id.desc())
        .limit(10)
    )
    latest_markets = []
    for m in latest_result.scalars().all():
        entry = {
            "id": m.id,
            "name": m.name,
            "external_id": m.external_id,
            "category": m.category,
        }
        if m.market_metadata:
            entry["tour"] = m.market_metadata.get("tour")
            entry["course"] = m.market_metadata.get("course")
            entry["has_leaderboard"] = "leaderboard" in m.market_metadata
            entry["round_history_count"] = len(m.market_metadata.get("round_history", []))
        latest_markets.append(entry)

    return {
        "total_markets": total_markets,
        "open_markets": open_markets,
        "total_outcomes": total_outcomes,
        "recent_snapshots_24h": recent_snapshots,
        "live_tours": live_tours,
        "latest_markets": latest_markets,
    }


@router.get("/schedule/accuracy")
async def schedule_accuracy(
    secret: str = Query(..., description="Admin secret for authorization"),
    days: int = Query(30, description="Look back period in days"),
    db: AsyncSession = Depends(get_db),
):
    """Per-sport breakdown of commence_time_source to audit date accuracy."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from sqlalchemy import func as sqlfunc, text
    from app.models import Sport

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days)

    # Get per-sport breakdown of commence_time_source
    result = await db.execute(
        select(
            Sport.key,
            Event.commence_time_source,
            sqlfunc.count(Event.id).label("count"),
        )
        .join(Sport, Event.sport_id == Sport.id)
        .where(Event.commence_time >= cutoff)
        .group_by(Sport.key, Event.commence_time_source)
        .order_by(Sport.key, Event.commence_time_source)
    )
    rows = result.all()

    # Aggregate by sport
    sports: dict[str, dict] = {}
    for row in rows:
        sport_key = row.key
        source = row.commence_time_source or "null"
        count = row.count

        if sport_key not in sports:
            sports[sport_key] = {"total": 0, "sources": {}}
        sports[sport_key]["total"] += count
        sports[sport_key]["sources"][source] = count

    # Calculate reliability ratings
    for sport_key, data in sports.items():
        total = data["total"]
        espn_count = data["sources"].get("espn", 0)
        statpal_count = data["sources"].get("statpal", 0)
        null_count = data["sources"].get("null", 0)
        corrected = espn_count + statpal_count
        corrected_pct = round(corrected / total * 100, 1) if total > 0 else 0
        null_pct = round(null_count / total * 100, 1) if total > 0 else 0

        if corrected_pct >= 80:
            rating = "HIGH"
        elif corrected_pct >= 40:
            rating = "MEDIUM"
        else:
            rating = "LOW"

        data["corrected_pct"] = corrected_pct
        data["uncorrected_pct"] = null_pct
        data["reliability"] = rating

    # Sort by reliability (LOW first to surface problems)
    reliability_order = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}
    sorted_sports = dict(
        sorted(
            sports.items(),
            key=lambda item: (reliability_order.get(item[1].get("reliability", "LOW"), 3), item[0])
        )
    )

    return {
        "period_days": days,
        "sports": sorted_sports,
        "summary": {
            "total_sports": len(sorted_sports),
            "high_reliability": sum(1 for s in sorted_sports.values() if s.get("reliability") == "HIGH"),
            "medium_reliability": sum(1 for s in sorted_sports.values() if s.get("reliability") == "MEDIUM"),
            "low_reliability": sum(1 for s in sorted_sports.values() if s.get("reliability") == "LOW"),
        },
    }


# ── Market Grouping Admin Endpoints ──


@router.get("/dashboard")
async def operations_dashboard(
    secret: str = Query(default=""),
    db: AsyncSession = Depends(get_db),
):
    """Consolidated operations dashboard data.

    Returns:
    - Odds API quota + history with budget projection
    - Source coverage by sport (which sources cover which events)
    - Worker task metrics (success/failure, duration)
    - Database health stats

    Implementation lives in ``app.utils.admin_dashboard`` — each section is
    an independently testable helper function.
    """
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.utils.admin_dashboard import (
        build_quota_section,
        build_source_coverage_section,
        build_worker_section,
        build_database_section,
        build_matching_metrics,
        build_game_state_section,
    )

    now = datetime.now(timezone.utc)

    quota_section = build_quota_section(now)
    source_coverage, coverage_trend, futures_coverage = (
        await build_source_coverage_section(db, now)
    )
    worker_section = build_worker_section(now)
    db_section = await build_database_section(db)
    matching_history = build_matching_metrics()
    game_state_section = await build_game_state_section(db)

    return {
        "generated_at": now.isoformat(),
        "quota": quota_section,
        "source_coverage": source_coverage,
        "coverage_trend": coverage_trend,
        "futures_coverage": futures_coverage,
        "worker": worker_section,
        "database": db_section,
        "matching_metrics": matching_history,
        "game_state_coverage": game_state_section,
    }


@router.post("/merge-events")
async def merge_events_admin(
    secret: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Manually trigger the duplicate event merger (runs in non-dry-run mode)."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Unauthorized")

    from app.tasks.sports import _merge_duplicate_events_impl
    result = await _merge_duplicate_events_impl(dry_run=False)
    return result


# ---------------------------------------------------------------------------
# Latency stats (production observability)
# ---------------------------------------------------------------------------

@router.get("/latency-stats")
async def get_latency_stats(
    secret: str = Query(..., description="Admin secret for authorization"),
    top: int = Query(20, description="Number of slowest endpoints to return"),
):
    """Return p50/p95/p99 latency per endpoint from the last hour.

    Data comes from sampled request timings stored in Redis sorted sets
    by the LatencyMiddleware.
    """
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    import time as _time

    try:
        from app.tasks.redis_state import get_redis_client
        r = get_redis_client()
    except Exception:
        raise HTTPException(status_code=503, detail="Redis unavailable")

    endpoints_set = r.smembers("latency:_endpoints")
    if not endpoints_set:
        return {"endpoints": [], "note": "No latency data collected yet"}

    now = _time.time()
    cutoff = now - 3600  # last hour only
    results = []

    for raw_ep in endpoints_set:
        ep = raw_ep.decode() if isinstance(raw_ep, bytes) else raw_ep
        key = f"latency:{ep}"

        # Get all members within the time window (score = timestamp).
        # member format: "timestamp:latency_ms"
        pairs = r.zrangebyscore(key, cutoff, "+inf")
        if not pairs:
            continue

        latencies = []
        for raw_member in pairs:
            m = raw_member.decode() if isinstance(raw_member, bytes) else raw_member
            try:
                latencies.append(float(m.split(":", 1)[1]))
            except (IndexError, ValueError):
                continue
        if not latencies:
            continue
        latencies.sort()
        n = len(latencies)

        def _percentile(data, pct):
            idx = int(pct / 100 * (len(data) - 1))
            return round(data[idx], 1)

        results.append({
            "endpoint": ep,
            "samples": n,
            "p50_ms": _percentile(latencies, 50),
            "p95_ms": _percentile(latencies, 95),
            "p99_ms": _percentile(latencies, 99),
            "max_ms": round(latencies[-1], 1),
            "min_ms": round(latencies[0], 1),
        })

    # Sort by p95 descending so the slowest endpoints are first.
    results.sort(key=lambda x: x["p95_ms"], reverse=True)
    results = results[:top]

    return {
        "window": "1 hour",
        "sample_rate": f"1/{os.getenv('LATENCY_SAMPLE_RATE', '10')}",
        "endpoints": results,
        "total_endpoints_tracked": len(endpoints_set),
    }


# ---------------------------------------------------------------------------
# Include sub-routers (at bottom to avoid circular imports)
# ---------------------------------------------------------------------------
from app.routes.admin_celery import router as celery_router  # noqa: E402
from app.routes.admin_matching import router as matching_router  # noqa: E402
from app.routes.admin_taxonomy import router as taxonomy_router  # noqa: E402
from app.routes.admin_engagement import router as engagement_router  # noqa: E402
from app.routes.admin_data_quality import router as data_quality_router  # noqa: E402

router.include_router(celery_router)
router.include_router(matching_router)
router.include_router(taxonomy_router)
router.include_router(engagement_router)
router.include_router(data_quality_router)
