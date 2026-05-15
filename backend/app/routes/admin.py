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

router = APIRouter()


def _check_admin_secret(secret: str) -> bool:
    """Verify admin secret for protected endpoints.

    Checks ADMIN_TOKEN (canonical, set on Heroku) with ADMIN_SECRET as
    fallback for backward compatibility. See gotchas-reference.md #40.
    """
    expected = os.getenv("ADMIN_TOKEN") or os.getenv("ADMIN_SECRET")
    if not expected:
        return False
    return secret == expected


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
    db: AsyncSession = Depends(get_db),
):
    """
    Diagnose why events don't have EI scores.

    Breaks down completed/closed events with raw_ei=NULL by root cause,
    including sport breakdown for zero-snapshot events.
    """
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
    db: AsyncSession = Depends(get_db),
):
    """
    Get the current status of EI (Excitement Index) calculations.

    Returns counts of events with and without EI scores.
    """
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


@router.post("/futures/categorize")
async def categorize_futures(
    secret: str = Query(..., description="Admin secret for authorization"),
    limit: int = Query(100, description="Max markets to categorize per batch"),
):
    """
    Categorize uncategorized futures markets using rules + LLM.

    Queues a background Celery task to avoid Heroku's 30-second timeout.
    Use /futures/task/{task_id} to check status.
    """
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.tasks import categorize_futures_task

    try:
        task = categorize_futures_task.delay(limit=limit, force_llm=False)
        return {
            "status": "queued",
            "task_id": task.id,
            "message": f"Categorization task queued (limit={limit}). "
                       f"Use /api/admin/futures/task/{task.id} to check status.",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to queue task: {str(e)}")


@router.post("/futures/recategorize-other")
async def recategorize_other_futures(
    secret: str = Query(..., description="Admin secret for authorization"),
    limit: int = Query(500, description="Max markets to re-check"),
    from_category: str = Query(None, description="Target a specific category instead of 'other'/NULL (e.g., 'basketball')"),
):
    """
    Re-run rules on markets to fix miscategorizations.

    By default targets 'other' and NULL markets. Use from_category to
    re-evaluate markets in a specific category (e.g., after adding new
    patterns that would reclassify some basketball markets as soccer).
    """
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.tasks import recategorize_other_task

    try:
        task = recategorize_other_task.delay(limit=limit, from_category=from_category)
        target = from_category or "other/NULL"
        return {
            "status": "queued",
            "task_id": task.id,
            "message": f"Recategorize task queued (target={target}, limit={limit}). "
                       f"Use /api/admin/futures/task/{task.id} to check status.",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to queue task: {str(e)}")


@router.post("/futures/regenerate-tags")
async def regenerate_tags(
    secret: str = Query(..., description="Admin secret for authorization"),
    limit: int = Query(5000, description="Max markets to process"),
    category: str = Query(None, description="Only regenerate tags for this category (e.g., 'crypto', 'politics')"),
):
    """
    Regenerate category_tags for existing markets using current keyword patterns.

    Use after adding new entity patterns to _TAG_KEYWORDS. Does NOT change
    llm_sport_category — only updates the subcategory tags used for grouping.
    """
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.tasks import regenerate_tags_task

    try:
        task = regenerate_tags_task.delay(limit=limit, category=category)
        target = category or "all"
        return {
            "status": "queued",
            "task_id": task.id,
            "message": f"Regenerate-tags task queued (category={target}, limit={limit}). "
                       f"Use /api/admin/futures/task/{task.id} to check status.",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to queue task: {str(e)}")


@router.get("/futures/categorization-status")
async def futures_categorization_status(
    db: AsyncSession = Depends(get_db),
):
    """
    Get the current status of futures categorization.

    Returns counts of categorized vs uncategorized markets.
    """
    from sqlalchemy import func
    from app.models import FuturesMarket
    from app.services import llm

    result = await db.execute(
        select(
            func.count().label("total"),
            func.count().filter(FuturesMarket.sport_id.isnot(None)).label("with_sport_id"),
            func.count().filter(
                FuturesMarket.sport_id.is_(None),
                FuturesMarket.llm_sport_category.isnot(None)
            ).label("with_llm_category"),
            func.count().filter(
                FuturesMarket.sport_id.is_(None),
                FuturesMarket.llm_sport_category.is_(None)
            ).label("uncategorized"),
        )
    )
    row = result.one()

    return {
        "total": row.total,
        "with_sport_id": row.with_sport_id,
        "with_llm_category": row.with_llm_category,
        "uncategorized": row.uncategorized,
        "llm_available": llm.is_available(),
        "completion_pct": round(
            (row.with_sport_id + row.with_llm_category) / row.total * 100, 1
        ) if row.total > 0 else 100,
    }


@router.get("/futures/uncategorized")
async def list_uncategorized_futures(
    limit: int = Query(100, description="Max markets to return"),
    db: AsyncSession = Depends(get_db),
):
    """
    List uncategorized futures markets.

    Shows market names to help identify patterns that should be added.
    No auth required - this is diagnostic info only.
    """
    from app.models import FuturesMarket
    from app.utils.futures_categorization import categorize_by_rules

    result = await db.execute(
        select(FuturesMarket)
        .where(
            FuturesMarket.sport_id.is_(None),
            FuturesMarket.llm_sport_category.is_(None),
        )
        .order_by(FuturesMarket.name)
        .limit(limit)
    )
    markets = result.scalars().all()

    # For each market, show what rules would categorize it as (to debug)
    uncategorized = []
    for m in markets:
        rule_result = categorize_by_rules(m.name, m.external_id)
        uncategorized.append({
            "id": m.id,
            "name": m.name,
            "sport_key": m.external_id,
            "source": m.source,
            "rule_would_return": rule_result,  # What pattern matching returns
        })

    return {
        "count": len(uncategorized),
        "markets": uncategorized,
        "hint": "Markets with rule_would_return=null need LLM or new patterns",
    }


@router.post("/futures/force-categorize")
async def force_categorize_futures(
    secret: str = Query(..., description="Admin secret for authorization"),
    limit: int = Query(100, description="Max markets to categorize"),
):
    """
    Force-categorize ALL uncategorized futures using LLM.

    Unlike /categorize which tries rules first, this forces LLM on every market.
    Queues a background Celery task to avoid Heroku's 30-second timeout.
    Use /futures/task/{task_id} to check status.
    """
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.tasks import categorize_futures_task

    try:
        task = categorize_futures_task.delay(limit=limit, force_llm=True)
        return {
            "status": "queued",
            "task_id": task.id,
            "message": f"Force-categorization task queued (limit={limit}). "
                       f"Use /api/admin/futures/task/{task.id} to check status.",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to queue task: {str(e)}")


# ============================================================================
# LLM Metadata Enrichment Endpoints
# ============================================================================


@router.post("/events/enrich-metadata")
async def enrich_events_metadata(
    secret: str = Query(..., description="Admin secret for authorization"),
    limit: int = Query(50, description="Max events to process per batch"),
    dry_run: bool = Query(False, description="Preview enrichment without saving"),
    force: bool = Query(False, description="Re-enrich events that already have metadata (for team normalization)"),
    db: AsyncSession = Depends(get_db),
):
    """
    Enrich events with LLM-generated metadata (gender, level, league, importance).

    Finds events without metadata and uses LLM + heuristics to classify them.
    Results are cached in the database to avoid repeat API calls.

    Set force=true to re-enrich events that have metadata but need team name normalization.
    """
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.services import llm
    from sqlalchemy.orm import selectinload

    # Find events to enrich
    if force:
        # Re-enrich events without normalized team names
        result = await db.execute(
            select(Event)
            .options(selectinload(Event.sport))
            .where(
                Event.home_team_normalized.is_(None),
            )
            .order_by(Event.commence_time.desc())
            .limit(limit)
        )
    else:
        # Find events without metadata (prioritize recent events)
        result = await db.execute(
            select(Event)
            .options(selectinload(Event.sport))
            .where(
                Event.llm_gender.is_(None),
                Event.llm_level.is_(None),
            )
            .order_by(Event.commence_time.desc())
            .limit(limit)
        )
    events = result.scalars().all()

    if not events:
        return {
            "status": "complete",
            "message": "No events need metadata enrichment",
            "processed": 0,
        }

    enriched = []
    errors = []

    for event in events:
        try:
            sport_key = event.sport.key if event.sport else None
            text = f"{event.away_team_name} at {event.home_team_name}"

            metadata = {
                "gender": llm.classify_gender_cached(text, sport_key),
                "level": llm.classify_level_cached(text, sport_key),
                "league": llm.classify_league_cached(text, sport_key),
                "importance": llm.classify_importance_cached(text, sport_key),
            }

            # Normalize team names for better matching
            home_norm, home_vars = llm.normalize_team_name_cached(event.home_team_name, sport_key)
            away_norm, away_vars = llm.normalize_team_name_cached(event.away_team_name, sport_key)

            enriched.append({
                "id": event.id,
                "teams": f"{event.away_team_name} @ {event.home_team_name}",
                "sport_key": sport_key,
                "home_normalized": home_norm,
                "away_normalized": away_norm,
                **metadata,
            })

            if not dry_run:
                event.llm_gender = metadata["gender"]
                event.llm_level = metadata["level"]
                event.llm_league = metadata["league"]
                event.llm_importance = metadata["importance"]
                event.home_team_normalized = home_norm
                event.away_team_normalized = away_norm
                event.home_team_alt_names = list(home_vars)
                event.away_team_alt_names = list(away_vars)

        except Exception as e:
            if len(errors) < 5:
                errors.append(f"Event {event.id}: {str(e)}")

    if not dry_run:
        await db.commit()

    # Count remaining
    remaining_result = await db.execute(
        select(Event.id).where(
            Event.llm_gender.is_(None),
            Event.llm_level.is_(None),
        )
    )
    remaining = len(remaining_result.all())

    return {
        "status": "success",
        "dry_run": dry_run,
        "processed": len(events),
        "enriched": len(enriched),
        "errors": len(errors),
        "remaining": remaining,
        "llm_available": llm.is_available(),
        "results": enriched[:10],  # Preview first 10
        "error_details": errors if errors else None,
        "message": f"Enriched {len(enriched)}/{len(events)} events." +
                   (f" {remaining} remaining." if remaining > 0 else " All done!"),
    }


@router.get("/events/metadata-status")
async def events_metadata_status(
    db: AsyncSession = Depends(get_db),
):
    """
    Get the current status of event metadata enrichment.

    Returns counts of enriched vs un-enriched events.
    """
    from sqlalchemy import func
    from app.services import llm

    result = await db.execute(
        select(
            func.count().label("total"),
            func.count().filter(Event.llm_gender.isnot(None)).label("with_gender"),
            func.count().filter(Event.llm_level.isnot(None)).label("with_level"),
            func.count().filter(Event.llm_league.isnot(None)).label("with_league"),
            func.count().filter(Event.llm_importance.isnot(None)).label("with_importance"),
            func.count().filter(
                Event.llm_gender.is_(None),
                Event.llm_level.is_(None),
            ).label("un_enriched"),
        )
    )
    row = result.one()

    return {
        "total": row.total,
        "with_gender": row.with_gender,
        "with_level": row.with_level,
        "with_league": row.with_league,
        "with_importance": row.with_importance,
        "un_enriched": row.un_enriched,
        "llm_available": llm.is_available(),
        "completion_pct": round(
            (row.total - row.un_enriched) / row.total * 100, 1
        ) if row.total > 0 else 100,
    }


@router.post("/futures/enrich-metadata")
async def enrich_futures_metadata(
    secret: str = Query(..., description="Admin secret for authorization"),
    limit: int = Query(50, description="Max markets to process per batch"),
    dry_run: bool = Query(False, description="Preview enrichment without saving"),
    db: AsyncSession = Depends(get_db),
):
    """
    Enrich futures markets with LLM-generated metadata (gender, level, league).

    Works alongside the existing categorize endpoint but adds more detailed metadata.
    """
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.models import FuturesMarket
    from app.services import llm

    # Find markets without metadata
    result = await db.execute(
        select(FuturesMarket)
        .where(
            FuturesMarket.llm_gender.is_(None),
            FuturesMarket.llm_level.is_(None),
        )
        .limit(limit)
    )
    markets = result.scalars().all()

    if not markets:
        return {
            "status": "complete",
            "message": "No markets need metadata enrichment",
            "processed": 0,
        }

    enriched = []
    errors = []

    for market in markets:
        try:
            metadata = llm.enrich_market_metadata(market.name)

            enriched.append({
                "id": market.id,
                "name": market.name,
                **metadata,
            })

            if not dry_run:
                market.llm_gender = metadata["gender"]
                market.llm_level = metadata["level"]
                market.llm_league = metadata["league"]

        except Exception as e:
            if len(errors) < 5:
                errors.append(f"Market {market.id}: {str(e)}")

    if not dry_run:
        await db.commit()

    # Count remaining
    remaining_result = await db.execute(
        select(FuturesMarket.id).where(
            FuturesMarket.llm_gender.is_(None),
            FuturesMarket.llm_level.is_(None),
        )
    )
    remaining = len(remaining_result.all())

    return {
        "status": "success",
        "dry_run": dry_run,
        "processed": len(markets),
        "enriched": len(enriched),
        "errors": len(errors),
        "remaining": remaining,
        "llm_available": llm.is_available(),
        "results": enriched[:10],
        "error_details": errors if errors else None,
        "message": f"Enriched {len(enriched)}/{len(markets)} markets." +
                   (f" {remaining} remaining." if remaining > 0 else " All done!"),
    }


@router.get("/futures/metadata-status")
async def futures_metadata_status(
    db: AsyncSession = Depends(get_db),
):
    """
    Get the current status of futures metadata enrichment.

    Returns counts of enriched vs un-enriched markets.
    """
    from sqlalchemy import func
    from app.models import FuturesMarket
    from app.services import llm

    result = await db.execute(
        select(
            func.count().label("total"),
            func.count().filter(FuturesMarket.llm_gender.isnot(None)).label("with_gender"),
            func.count().filter(FuturesMarket.llm_level.isnot(None)).label("with_level"),
            func.count().filter(FuturesMarket.llm_league.isnot(None)).label("with_league"),
            func.count().filter(
                FuturesMarket.llm_gender.is_(None),
                FuturesMarket.llm_level.is_(None),
            ).label("un_enriched"),
        )
    )
    row = result.one()

    return {
        "total": row.total,
        "with_gender": row.with_gender,
        "with_level": row.with_level,
        "with_league": row.with_league,
        "un_enriched": row.un_enriched,
        "llm_available": llm.is_available(),
        "completion_pct": round(
            (row.total - row.un_enriched) / row.total * 100, 1
        ) if row.total > 0 else 100,
    }


# ============================================================================
# ESPN Integration Endpoints
# ============================================================================


@router.get("/pulse/distributions")
@router.get("/ei/distributions")
async def ei_distributions(
    db: AsyncSession = Depends(get_db),
):
    """
    Analyze the distribution of EI scores and metadata across all scored events.

    Returns histograms and statistics for the overall score and EI metadata
    (raw_ei, lead_changes, comeback_factor).
    No auth required - diagnostic/read-only.
    """
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
    db: AsyncSession = Depends(get_db),
):
    """
    Get the status of ESPN team enrichment.

    Shows how many teams have ESPN data (colors, logos).
    """
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
    sport_key: str = Query(..., description="Sport key (e.g., 'americanfootball_nfl')"),
    db: AsyncSession = Depends(get_db),
):
    """Debug: show team names, abbreviations, and roster status for a sport."""
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
    db: AsyncSession = Depends(get_db),
):
    """
    Get the status of ESPN event enrichment.

    Shows how many events have ESPN data (clock, period, venue, win prob).
    """
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
):
    """
    Backfill ESPN box score data for completed events.

    Fetches box scores for completed/closed events that have an ESPN ID
    but are missing box_score_data. Stores player stats for expected-vs-actual
    display on stat prop markets.
    """
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.tasks import backfill_box_scores as task

    result = task.delay(limit=limit)
    return {
        "status": "queued",
        "task_id": result.id,
        "message": f"Box score backfill queued (limit={limit}). Check status at /api/admin/espn/task/{{task_id}}",
    }


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


@router.get("/celery/health")
async def celery_health():
    """Check Celery worker health via heartbeat timestamp in Redis."""
    from app.tasks.redis_state import get_redis_client

    try:
        r = get_redis_client()
        heartbeat = r.get("bainluck:heartbeat")
        if not heartbeat:
            return {"status": "unknown", "message": "No heartbeat found — worker may not have started yet"}

        heartbeat_time = datetime.fromisoformat(heartbeat.decode())
        age_seconds = (datetime.now(timezone.utc) - heartbeat_time).total_seconds()

        if age_seconds > 180:  # 3 minutes
            return {
                "status": "unhealthy",
                "last_heartbeat": heartbeat_time.isoformat(),
                "age_seconds": round(age_seconds),
                "message": "Heartbeat is stale — Celery worker may be down",
            }

        return {
            "status": "healthy",
            "last_heartbeat": heartbeat_time.isoformat(),
            "age_seconds": round(age_seconds),
        }
    except Exception as e:
        return {"status": "error", "message": f"Redis error: {str(e)}"}


@router.get("/celery/dashboard")
async def celery_dashboard():
    """
    Task-level success metrics dashboard.

    Shows success/failure rates, last run times, durations, and key output
    metrics for all tracked tasks. Detects degraded performance (not just
    crashes) — e.g., ESPN sync matching 0 events, odds polling returning
    empty results.
    """
    from app.tasks.redis_state import get_all_task_metrics, get_redis_client

    # Get per-task metrics
    tasks = get_all_task_metrics()

    # Get Odds API quota (passive, from Redis cache)
    from app.tasks.redis_state import get_odds_api_quota
    odds_api_quota = get_odds_api_quota()

    # Get heartbeat status for overall worker health
    try:
        r = get_redis_client()
        heartbeat = r.get("bainluck:heartbeat")
        if heartbeat:
            heartbeat_time = datetime.fromisoformat(heartbeat.decode())
            heartbeat_age = (datetime.now(timezone.utc) - heartbeat_time).total_seconds()
            worker_status = "healthy" if heartbeat_age < 180 else "unhealthy"
        else:
            heartbeat_age = None
            worker_status = "unknown"
    except Exception:
        heartbeat_age = None
        worker_status = "error"

    # Compute overall health
    critical_tasks = [t for t in tasks if t.get("health") == "critical"]
    degraded_tasks = [t for t in tasks if t.get("health") == "degraded"]

    if worker_status != "healthy":
        overall = "worker_down"
    elif critical_tasks:
        overall = "critical"
    elif degraded_tasks:
        overall = "degraded"
    elif not tasks:
        overall = "no_data"
    else:
        overall = "healthy"

    return {
        "overall_health": overall,
        "worker_status": worker_status,
        "worker_heartbeat_age_seconds": round(heartbeat_age) if heartbeat_age else None,
        "tracked_tasks": len(tasks),
        "critical_tasks": [t["task"] for t in critical_tasks],
        "degraded_tasks": [t["task"] for t in degraded_tasks],
        "tasks": tasks,
        "odds_api_quota": odds_api_quota,
    }


@router.get("/celery/task-metrics/{task_name}")
async def get_task_metrics_endpoint(task_name: str):
    """Get detailed metrics for a specific task."""
    from app.tasks.redis_state import get_task_metrics
    return get_task_metrics(task_name)


@router.get("/celery/inspect")
async def celery_inspect():
    """Inspect Celery worker: registered tasks, active tasks, reserved queue."""
    from app.tasks import celery_app
    i = celery_app.control.inspect(timeout=5)
    registered = i.registered() or {}
    active = i.active() or {}
    reserved = i.reserved() or {}

    result = {}
    for worker_name in set(list(registered) + list(active) + list(reserved)):
        worker_tasks = registered.get(worker_name, [])
        taxonomy = [t for t in worker_tasks if "taxonomy" in t or "event_tag" in t]
        result[worker_name] = {
            "total_registered": len(worker_tasks),
            "taxonomy_tasks": taxonomy,
            "active": [
                {"name": t.get("name"), "id": t.get("id")}
                for t in active.get(worker_name, [])
            ],
            "reserved_count": len(reserved.get(worker_name, [])),
            "reserved_sample": [
                {"name": t.get("name"), "id": t.get("id")}
                for t in reserved.get(worker_name, [])[:10]
            ],
        }
    return result


@router.get("/taxonomy/debug-redis")
async def taxonomy_debug_redis():
    """Check Redis markers set by taxonomy piggybacking code."""
    import redis
    import os
    r = redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))
    return {
        "taxonomy_debug": r.get("bainluck:taxonomy_debug"),
        "llm_enrich_gate": r.get("bainluck:llm_enrich_gate"),
    }


# ---------------------------------------------------------------------------
# Odds API Quota Monitoring
# ---------------------------------------------------------------------------

@router.get("/odds-api/usage")
async def odds_api_usage():
    """Current Odds API quota status and hourly history."""
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
async def statpal_usage():
    """Current StatPal API usage and daily history."""
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
    db: AsyncSession = Depends(get_db),
    month: int = Query(2, description="Month (1-12)"),
    year: int = Query(2026, description="Year"),
    table: str = Query("odds", description="Table to query: odds, futures, winprob, or all"),
):
    """Infer daily Odds API call volume from snapshot row counts.

    Query one table at a time (table=odds|futures|winprob) to stay within
    Heroku's 30-second timeout, or table=all to try all three.
    """
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

@router.post("/snapshots/collapse")
async def trigger_snapshot_collapse(
    secret: str = Query(..., description="Admin secret for authorization"),
    table: str = Query("odds", description="Table to collapse: 'odds', 'winprob', or 'futures'"),
    limit: int = Query(200, description="Max events/outcomes to process per run"),
    min_age_hours: int = Query(48, description="Only collapse snapshots older than this many hours"),
):
    """Trigger retroactive snapshot collapsing for one table (runs as background Celery task).

    Collapses consecutive identical snapshot rows. Lossless — original
    time series can be reconstructed from collapsed rows.

    Run once per table: table=odds, table=winprob, table=futures.
    Use limit to control batch size (default 200 events/outcomes per run).
    """
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    if table not in ("odds", "winprob", "futures"):
        raise HTTPException(status_code=400, detail="table must be 'odds', 'winprob', or 'futures'")

    from app.tasks import collapse_snapshots

    task = collapse_snapshots.delay(min_age_hours=min_age_hours, table=table, limit=limit)
    return {
        "status": "queued",
        "task_id": task.id,
        "table": table,
        "limit": limit,
        "message": f"Collapse [{table}] queued (limit={limit}). Use /api/admin/snapshots/task/{task.id} to check status.",
    }


@router.get("/snapshots/task/{task_id}")
async def get_snapshot_task_status(
    task_id: str,
    secret: str = Query(..., description="Admin secret for authorization"),
):
    """Check the status of a snapshot collapse task."""
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


@router.get("/snapshots/stats")
async def get_snapshot_stats(
    secret: str = Query(..., description="Admin secret for authorization"),
    db: AsyncSession = Depends(get_db),
):
    """Get current snapshot table row counts."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from sqlalchemy import func
    from app.models import OddsSnapshot, WinProbSnapshot, FuturesOddsSnapshot

    odds_count = (await db.execute(select(func.count(OddsSnapshot.id)))).scalar()
    winprob_count = (await db.execute(select(func.count(WinProbSnapshot.id)))).scalar()
    futures_count = (await db.execute(select(func.count(FuturesOddsSnapshot.id)))).scalar()

    return {
        "odds_snapshots": odds_count,
        "win_prob_snapshots": winprob_count,
        "futures_odds_snapshots": futures_count,
        "total": odds_count + winprob_count + futures_count,
    }


# =============================================================================
# Prediction Market → Event Matching
# =============================================================================


@router.post("/prediction-markets/match")
async def trigger_prediction_market_matching(
    secret: str = Query(..., description="Admin secret for authorization"),
    limit: int = Query(500, description="Max markets to scan"),
):
    """
    Trigger prediction market → event matching.

    Scans Kalshi and Polymarket game-level markets and links them to events.
    Also writes win_prob_snapshots for linked markets.
    """
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.tasks import match_prediction_markets

    try:
        task = match_prediction_markets.delay(limit=limit)
        return {
            "status": "queued",
            "task_id": task.id,
            "message": f"Prediction market matching task queued (limit={limit}). "
                       f"Use /api/admin/prediction-markets/task/{task.id} to check status.",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to queue task: {str(e)}")


@router.post("/prediction-markets/poll-live")
async def trigger_live_prediction_market_poll(
    secret: str = Query(..., description="Admin secret for authorization"),
):
    """
    Trigger a one-off live prediction market price poll.

    Fetches current prices from Kalshi and Polymarket ONLY for markets
    linked to events with status='live'. Much faster than full polls.
    Normally runs automatically every 2 minutes via beat schedule.
    """
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.tasks import poll_live_prediction_markets

    try:
        task = poll_live_prediction_markets.delay()
        return {
            "status": "queued",
            "task_id": task.id,
            "message": f"Live prediction market poll queued. "
                       f"Use /api/admin/prediction-markets/task/{task.id} to check status.",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to queue task: {str(e)}")


@router.post("/prediction-markets/backfill-history")
async def trigger_polymarket_win_prob_backfill(
    secret: str = Query(..., description="Admin secret for authorization"),
    market_id: int = Query(..., description="FuturesMarket ID"),
    event_id: int = Query(..., description="Event ID"),
):
    """
    Backfill win_prob_snapshots from Polymarket CLOB price history.

    Fetches historical prices for the moneyline outcome and writes them
    as win_prob_snapshots for the event's OddsChart trend line.
    """
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.tasks import backfill_polymarket_win_prob

    try:
        task = backfill_polymarket_win_prob.delay(market_id, event_id)
        return {
            "status": "queued",
            "task_id": task.id,
            "message": f"Polymarket win_prob backfill queued for market={market_id} event={event_id}. "
                       f"Use /api/admin/prediction-markets/task/{task.id} to check status.",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to queue task: {str(e)}")


@router.get("/prediction-markets/task/{task_id}")
async def get_prediction_market_task_status(
    task_id: str,
    secret: str = Query(..., description="Admin secret for authorization"),
):
    """Check the status of a prediction market matching task."""
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


@router.get("/prediction-markets/status")
async def prediction_market_status(
    secret: str = Query(..., description="Admin secret for authorization"),
    db: AsyncSession = Depends(get_db),
):
    """
    Show prediction market → event linking status.

    Reports how many game-level markets are linked vs unlinked,
    and how many win_prob_snapshots exist per source.
    """
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from sqlalchemy import func, case
    from app.models.models import FuturesMarket, WinProbSnapshot

    # Count linked vs unlinked by source
    link_stats = await db.execute(
        select(
            FuturesMarket.source,
            func.count().label("total"),
            func.count(FuturesMarket.event_id).label("linked"),
        )
        .where(FuturesMarket.source.in_(["kalshi", "polymarket"]))
        .group_by(FuturesMarket.source)
    )
    links_by_source = {}
    for row in link_stats.all():
        links_by_source[row.source] = {
            "total_markets": row.total,
            "linked_to_events": row.linked,
            "unlinked": row.total - row.linked,
        }

    # Count win_prob_snapshots for prediction market sources
    wp_stats = await db.execute(
        select(
            WinProbSnapshot.source,
            func.count().label("snapshot_count"),
            func.count(func.distinct(WinProbSnapshot.event_id)).label("event_count"),
        )
        .where(WinProbSnapshot.source.in_(["kalshi", "polymarket"]))
        .group_by(WinProbSnapshot.source)
    )
    snapshots_by_source = {}
    for row in wp_stats.all():
        snapshots_by_source[row.source] = {
            "snapshot_count": row.snapshot_count,
            "event_count": row.event_count,
        }

    # Show some recently linked markets as examples
    recent_result = await db.execute(
        select(
            FuturesMarket.source,
            FuturesMarket.name,
            FuturesMarket.event_id,
        )
        .where(
            FuturesMarket.source.in_(["kalshi", "polymarket"]),
            FuturesMarket.event_id.isnot(None),
        )
        .order_by(FuturesMarket.updated_at.desc())
        .limit(10)
    )
    recent_linked = [
        {"source": r.source, "name": r.name, "event_id": r.event_id}
        for r in recent_result.all()
    ]

    return {
        "links_by_source": links_by_source,
        "win_prob_snapshots": snapshots_by_source,
        "recent_linked": recent_linked,
    }


@router.post("/prediction-markets/fix-sport-categories")
async def fix_sport_categories(
    secret: str = Query(..., description="Admin secret for authorization"),
    db: AsyncSession = Depends(get_db),
):
    """Bulk-fix llm_sport_category for Kalshi markets based on ticker prefix."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.utils.sport_keys import KALSHI_TICKER_TO_SPORT_KEY, KALSHI_FUTURES_TICKER_TO_SPORT_KEY, SPORT_PREFIX_TO_LLM_CATEGORY

    all_tickers = {**KALSHI_TICKER_TO_SPORT_KEY, **KALSHI_FUTURES_TICKER_TO_SPORT_KEY}

    fixed_by_sport: dict[str, int] = {}
    total_fixed = 0

    for prefix, sport_key in all_tickers.items():
        sport_prefix = sport_key.split("_")[0]
        correct_category = SPORT_PREFIX_TO_LLM_CATEGORY.get(sport_prefix)
        if not correct_category:
            continue

        result = await db.execute(
            text(
                "UPDATE futures_markets "
                "SET llm_sport_category = :category "
                "WHERE source = 'kalshi' "
                "AND LOWER(external_id) LIKE :pattern "
                "AND (llm_sport_category IS NULL OR llm_sport_category != :category)"
            ),
            {"category": correct_category, "pattern": f"{prefix}%"},
        )
        if result.rowcount > 0:
            fixed_by_sport[correct_category] = fixed_by_sport.get(correct_category, 0) + result.rowcount
            total_fixed += result.rowcount

    await db.commit()

    return {
        "total_fixed": total_fixed,
        "by_sport": fixed_by_sport,
    }


@router.get("/prediction-markets/link-rate")
async def prediction_market_link_rate(
    secret: str = Query(..., description="Admin secret for authorization"),
    db: AsyncSession = Depends(get_db),
):
    """
    Game-level market link rate — the metric that matters.

    Filters to only markets that SHOULD be linked (game-level sports markets,
    excluding politics/crypto/weather) and reports what % are actually linked,
    broken down by sport.
    """
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    _SPORT_CATEGORIES = [
        "basketball", "football", "baseball", "hockey", "soccer",
        "golf", "tennis", "mma", "boxing", "cricket", "rugby",
        "lacrosse", "esports", "aussierules",
    ]

    # Build game-level ticker filter for Kalshi.
    # Only count markets with game ticker prefixes — these are the markets
    # the matching task's Pass 1 scans. The old `event_id IS NOT NULL` clause
    # pulled in season futures (awards, Stanley Cup, etc.) that were
    # erroneously linked, inflating the denominator with unlinkable markets.
    _kalshi_ticker_conditions = [
        func.lower(FuturesMarket.external_id).like(f"{p}%")
        for p in KALSHI_GAME_TICKER_PREFIXES
    ]
    _kalshi_game_filter = or_(*_kalshi_ticker_conditions)

    # Kalshi: game-level markets only (ticker prefix match)
    kalshi_result = await db.execute(
        select(
            FuturesMarket.llm_sport_category.label("sport"),
            FuturesMarket.llm_league.label("league"),
            func.count().label("total"),
            func.count(FuturesMarket.event_id).label("linked"),
            func.count().filter(FuturesMarket.status == "open").label("open_total"),
            func.count(FuturesMarket.event_id).filter(FuturesMarket.status == "open").label("open_linked"),
        )
        .where(
            FuturesMarket.source == "kalshi",
            FuturesMarket.llm_sport_category.isnot(None),
            FuturesMarket.llm_sport_category.in_(_SPORT_CATEGORIES),
            _kalshi_game_filter,
        )
        .group_by(FuturesMarket.llm_sport_category, FuturesMarket.llm_league)
        .order_by(func.count().desc())
    )
    kalshi_by_sport = []
    kalshi_totals = {"total": 0, "linked": 0, "open_total": 0, "open_linked": 0}
    for row in kalshi_result.all():
        sport_data = {
            "sport": row.sport,
            "league": row.league,
            "total": row.total,
            "linked": row.linked,
            "link_rate": round(row.open_linked / row.open_total * 100, 1) if row.open_total else 0,
            "open_total": row.open_total,
            "open_linked": row.open_linked,
            "link_rate_all": round(row.linked / row.total * 100, 1) if row.total else 0,
        }
        kalshi_by_sport.append(sport_data)
        for k in kalshi_totals:
            kalshi_totals[k] += sport_data[k]

    # Polymarket: game-level = has "vs"/"at" in name + sports category
    poly_result = await db.execute(
        select(
            FuturesMarket.llm_sport_category.label("sport"),
            FuturesMarket.llm_league.label("league"),
            func.count().label("total"),
            func.count(FuturesMarket.event_id).label("linked"),
            func.count().filter(FuturesMarket.status == "open").label("open_total"),
            func.count(FuturesMarket.event_id).filter(FuturesMarket.status == "open").label("open_linked"),
        )
        .where(
            FuturesMarket.source == "polymarket",
            FuturesMarket.llm_sport_category.isnot(None),
            FuturesMarket.llm_sport_category.in_(_SPORT_CATEGORIES),
            or_(
                FuturesMarket.name.ilike("% vs.%"),
                FuturesMarket.name.ilike("% vs %"),
                FuturesMarket.name.ilike("% at %"),
            ),
        )
        .group_by(FuturesMarket.llm_sport_category, FuturesMarket.llm_league)
        .order_by(func.count().desc())
    )
    poly_by_sport = []
    poly_totals = {"total": 0, "linked": 0, "open_total": 0, "open_linked": 0}
    for row in poly_result.all():
        sport_data = {
            "sport": row.sport,
            "league": row.league,
            "total": row.total,
            "linked": row.linked,
            "link_rate": round(row.open_linked / row.open_total * 100, 1) if row.open_total else 0,
            "open_total": row.open_total,
            "open_linked": row.open_linked,
            "link_rate_all": round(row.linked / row.total * 100, 1) if row.total else 0,
        }
        poly_by_sport.append(sport_data)
        for k in poly_totals:
            poly_totals[k] += sport_data[k]

    grand_total = kalshi_totals["total"] + poly_totals["total"]
    grand_linked = kalshi_totals["linked"] + poly_totals["linked"]
    grand_open_total = kalshi_totals["open_total"] + poly_totals["open_total"]
    grand_open_linked = kalshi_totals["open_linked"] + poly_totals["open_linked"]

    return {
        "overall": {
            "total_game_markets": grand_total,
            "linked": grand_linked,
            "link_rate_pct": round(grand_open_linked / grand_open_total * 100, 1) if grand_open_total else 0,
            "link_rate_all_pct": round(grand_linked / grand_total * 100, 1) if grand_total else 0,
            "open_total": grand_open_total,
            "open_linked": grand_open_linked,
            "denominator_note": "Headline rate uses open markets only. link_rate_all_pct includes all statuses.",
        },
        "kalshi": {
            "totals": {
                **kalshi_totals,
                "link_rate_pct": round(kalshi_totals["open_linked"] / kalshi_totals["open_total"] * 100, 1) if kalshi_totals["open_total"] else 0,
                "link_rate_all_pct": round(kalshi_totals["linked"] / kalshi_totals["total"] * 100, 1) if kalshi_totals["total"] else 0,
            },
            "by_sport": kalshi_by_sport,
        },
        "polymarket": {
            "totals": {
                **poly_totals,
                "link_rate_pct": round(poly_totals["open_linked"] / poly_totals["open_total"] * 100, 1) if poly_totals["open_total"] else 0,
                "link_rate_all_pct": round(poly_totals["linked"] / poly_totals["total"] * 100, 1) if poly_totals["total"] else 0,
            },
            "by_sport": poly_by_sport,
        },
    }


@router.get("/prediction-markets/tier1-compliance")
async def tier1_source_compliance(
    secret: str = Query(..., description="Admin secret for authorization"),
    db: AsyncSession = Depends(get_db),
):
    """Hill-climb metric: every Tier 1 event must have ALL sources linked.

    Tier 1 sports: MLB, NBA, NHL, NFL, PGA.
    Required sources: Odds API, ESPN, StatPal, Kalshi, Polymarket (+ DataGolf for PGA).
    Only counts scheduled/live events happening today (-6h to +12h).
    Target: 100% compliance for each sport × source cell. No excuses.
    """
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from sqlalchemy import text as _text
    await db.execute(_text("SET LOCAL statement_timeout = '15s'"))

    result = await db.execute(_text("""
        WITH tier1_events AS (
            SELECT e.id, s.key AS sport_key,
                   e.home_team_name, e.away_team_name,
                   e.external_id AS odds_api_id,
                   e.espn_id,
                   e.statpal_fixture_id,
                   e.commence_time, e.status
            FROM events e
            JOIN sports s ON e.sport_id = s.id
            WHERE s.key IN ('baseball_mlb', 'basketball_nba', 'icehockey_nhl', 'americanfootball_nfl')
              AND e.status IN ('scheduled', 'live')
              AND e.commence_time >= NOW() - INTERVAL '6 hours'
              AND e.commence_time <= NOW() + INTERVAL '12 hours'
        ),
        kalshi_links AS (
            SELECT DISTINCT fm.event_id
            FROM futures_markets fm
            WHERE fm.source = 'kalshi' AND fm.event_id IS NOT NULL
        ),
        poly_links AS (
            SELECT DISTINCT fm.event_id
            FROM futures_markets fm
            WHERE fm.source = 'polymarket' AND fm.event_id IS NOT NULL
        )
        SELECT
            te.sport_key,
            COUNT(*) AS total,
            COUNT(te.odds_api_id) AS has_odds_api,
            COUNT(te.espn_id) AS has_espn,
            COUNT(te.statpal_fixture_id) AS has_statpal,
            COUNT(kl.event_id) AS has_kalshi,
            COUNT(pl.event_id) AS has_polymarket,
            COUNT(CASE WHEN te.odds_api_id IS NOT NULL
                        AND te.espn_id IS NOT NULL
                        AND te.statpal_fixture_id IS NOT NULL
                        AND kl.event_id IS NOT NULL
                        AND pl.event_id IS NOT NULL
                       THEN 1 END) AS fully_compliant
        FROM tier1_events te
        LEFT JOIN kalshi_links kl ON kl.event_id = te.id
        LEFT JOIN poly_links pl ON pl.event_id = te.id
        GROUP BY te.sport_key
        ORDER BY te.sport_key
    """))

    by_sport = []
    totals = {"total": 0, "compliant": 0}
    for row in result.fetchall():
        t = row.total
        sport_data = {
            "sport": row.sport_key,
            "total": t,
            "odds_api": row.has_odds_api,
            "espn": row.has_espn,
            "statpal": row.has_statpal,
            "kalshi": row.has_kalshi,
            "polymarket": row.has_polymarket,
            "fully_compliant": row.fully_compliant,
            "compliance_pct": round(row.fully_compliant / max(t, 1) * 100, 1),
            "gaps": {
                "odds_api": t - row.has_odds_api,
                "espn": t - row.has_espn,
                "statpal": t - row.has_statpal,
                "kalshi": t - row.has_kalshi,
                "polymarket": t - row.has_polymarket,
            },
        }
        by_sport.append(sport_data)
        totals["total"] += t
        totals["compliant"] += row.fully_compliant

    # Per-event gaps for non-compliant events (show what's missing)
    gap_result = await db.execute(_text("""
        WITH tier1_events AS (
            SELECT e.id, s.key AS sport_key,
                   e.home_team_name, e.away_team_name,
                   e.external_id AS odds_api_id, e.espn_id, e.statpal_fixture_id,
                   e.commence_time, e.status
            FROM events e
            JOIN sports s ON e.sport_id = s.id
            WHERE s.key IN ('baseball_mlb', 'basketball_nba', 'icehockey_nhl', 'americanfootball_nfl')
              AND e.status IN ('scheduled', 'live')
              AND e.commence_time >= NOW() - INTERVAL '6 hours'
              AND e.commence_time <= NOW() + INTERVAL '12 hours'
        ),
        kalshi_links AS (
            SELECT DISTINCT fm.event_id FROM futures_markets fm
            WHERE fm.source = 'kalshi' AND fm.event_id IS NOT NULL
        ),
        poly_links AS (
            SELECT DISTINCT fm.event_id FROM futures_markets fm
            WHERE fm.source = 'polymarket' AND fm.event_id IS NOT NULL
        )
        SELECT te.id, te.sport_key,
               te.away_team_name || ' @ ' || te.home_team_name AS matchup,
               te.commence_time, te.status,
               te.odds_api_id IS NULL AS missing_odds_api,
               te.espn_id IS NULL AS missing_espn,
               te.statpal_fixture_id IS NULL AS missing_statpal,
               kl.event_id IS NULL AS missing_kalshi,
               pl.event_id IS NULL AS missing_polymarket
        FROM tier1_events te
        LEFT JOIN kalshi_links kl ON kl.event_id = te.id
        LEFT JOIN poly_links pl ON pl.event_id = te.id
        WHERE te.odds_api_id IS NULL
           OR te.espn_id IS NULL
           OR te.statpal_fixture_id IS NULL
           OR kl.event_id IS NULL
           OR pl.event_id IS NULL
        ORDER BY te.commence_time
        LIMIT 30
    """))
    gaps = []
    for row in gap_result.fetchall():
        missing = []
        if row.missing_odds_api: missing.append("odds_api")
        if row.missing_espn: missing.append("espn")
        if row.missing_statpal: missing.append("statpal")
        if row.missing_kalshi: missing.append("kalshi")
        if row.missing_polymarket: missing.append("polymarket")
        gaps.append({
            "id": row.id,
            "sport": row.sport_key,
            "matchup": row.matchup,
            "time": row.commence_time.isoformat() if row.commence_time else None,
            "status": row.status,
            "missing": missing,
        })

    return {
        "target": "100% — every Tier 1 event happening today has all 5 sources",
        "compliance_pct": round(totals["compliant"] / max(totals["total"], 1) * 100, 1),
        "total_events": totals["total"],
        "fully_compliant": totals["compliant"],
        "by_sport": by_sport,
        "non_compliant_events": gaps,
        "golf": await _golf_compliance(db),
    }


async def _golf_compliance(db: AsyncSession) -> dict:
    """PGA compliance: active PGA tournament must have all market types from all 3 sources."""
    from sqlalchemy import text as _text

    _REQUIRED_TYPES = ["win", "top_5", "top_10", "top_20", "make_cut"]
    _REQUIRED_SOURCES = ["datagolf", "kalshi", "polymarket"]

    try:
        # Find active PGA tournaments from DataGolf (tour = 'pga', status != 'resolved')
        result = await db.execute(_text("""
            SELECT DISTINCT
                fm.market_metadata->>'datagolf_event_id' AS event_id,
                SPLIT_PART(fm.name, ' - ', 1) AS tournament_name
            FROM futures_markets fm
            WHERE fm.source = 'datagolf'
              AND fm.status IN ('open', 'closed')
              AND COALESCE(fm.market_metadata->>'tour', '') = 'pga'
            ORDER BY tournament_name
        """))
        pga_tournaments = result.fetchall()

        tournaments = []
        for t in pga_tournaments:
            event_id = t.event_id
            name = t.tournament_name
            search_term = name.strip()[:30].lower()
            if not search_term:
                continue

            by_source = {}
            for source in _REQUIRED_SOURCES:
                if source == "datagolf":
                    type_result = await db.execute(_text(
                        "SELECT SPLIT_PART(external_id, ':', 4) AS mtype"
                        " FROM futures_markets"
                        " WHERE source = 'datagolf' AND status IN ('open', 'closed')"
                        "   AND market_metadata->>'datagolf_event_id' = :eid"
                    ), {"eid": event_id})
                else:
                    type_result = await db.execute(_text(
                        "SELECT CASE"
                        "   WHEN lower(name) LIKE :win THEN 'win'"
                        "   WHEN lower(name) LIKE :cut THEN 'make_cut'"
                        "   WHEN lower(name) LIKE :t5 THEN 'top_5'"
                        "   WHEN lower(name) LIKE :t10 THEN 'top_10'"
                        "   WHEN lower(name) LIKE :t20 THEN 'top_20'"
                        "   ELSE 'other' END AS mtype"
                        " FROM futures_markets"
                        " WHERE source = :source AND llm_sport_category = 'golf'"
                        "   AND status = 'open' AND lower(name) LIKE :pattern"
                    ), {
                        "source": source, "pattern": f"%{search_term}%",
                        "win": "%winner%", "cut": "%make%cut%",
                        "t5": "%top 5%", "t10": "%top 10%", "t20": "%top 20%",
                    })
                found_types = {row.mtype for row in type_result.fetchall()} - {"other"}
                by_source[source] = sorted(found_types)

            missing = {}
            for source in _REQUIRED_SOURCES:
                missing_types = [mt for mt in _REQUIRED_TYPES if mt not in by_source.get(source, [])]
                if missing_types:
                    missing[source] = missing_types

            tournaments.append({
                "tournament": name,
                "event_id": event_id,
                "by_source": by_source,
                "missing": missing,
                "compliant": not missing,
            })

        compliant_count = sum(1 for t in tournaments if t["compliant"])
        return {
            "total": len(tournaments),
            "compliant": compliant_count,
            "compliance_pct": round(compliant_count / max(len(tournaments), 1) * 100, 1),
            "required_types": _REQUIRED_TYPES,
            "required_sources": _REQUIRED_SOURCES,
            "tournaments": tournaments,
        }
    except Exception as e:
        return {"error": str(e), "total": 0, "compliant": 0, "compliance_pct": 0, "tournaments": []}


@router.get("/prediction-markets/game-diagnostics")
async def prediction_market_game_diagnostics(
    secret: str = Query(..., description="Admin secret for authorization"),
    sport: str = Query(None, description="Filter to prefixes for a sport (e.g. 'mlb', 'nba')"),
    db: AsyncSession = Depends(get_db),
):
    """
    Diagnose game-level prediction market matching for major sports.

    Shows counts of game-level markets by ticker prefix, their link status,
    and sample unlinked markets to identify matching failures.
    Pass ?sport=mlb to filter to MLB prefixes only.
    """
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from sqlalchemy import func, case, text as _text
    from app.models.models import FuturesMarket
    from app.utils.sport_keys import KALSHI_GAME_TICKER_PREFIXES

    await db.execute(_text("SET LOCAL statement_timeout = '20s'"))

    results = {}

    prefixes = KALSHI_GAME_TICKER_PREFIXES
    if sport:
        prefixes = [p for p in prefixes if sport.lower() in p.lower()]

    for prefix in prefixes:
        pattern = f"{prefix}%"
        stats_result = await db.execute(
            select(
                func.count().label("total"),
                func.count(FuturesMarket.event_id).label("linked"),
                func.count(case((FuturesMarket.status == "open", 1))).label("open"),
            )
            .where(
                FuturesMarket.source == "kalshi",
                func.lower(FuturesMarket.external_id).like(pattern),
            )
        )
        row = stats_result.one()
        if row.total > 0:
            # Get sample unlinked open markets
            sample_result = await db.execute(
                select(
                    FuturesMarket.id,
                    FuturesMarket.external_id,
                    FuturesMarket.name,
                    FuturesMarket.event_id,
                    FuturesMarket.status,
                    FuturesMarket.commence_time,
                )
                .where(
                    FuturesMarket.source == "kalshi",
                    func.lower(FuturesMarket.external_id).like(pattern),
                    FuturesMarket.event_id.is_(None),
                    FuturesMarket.status == "open",
                )
                .order_by(FuturesMarket.commence_time.desc())
                .limit(5)
            )
            samples = [
                {
                    "id": r.id, "external_id": r.external_id, "name": r.name,
                    "event_id": r.event_id, "status": r.status,
                    "commence_time": r.commence_time.isoformat() if r.commence_time else None,
                }
                for r in sample_result.all()
            ]
            results[prefix] = {
                "total": row.total, "linked": row.linked,
                "unlinked": row.total - row.linked, "open": row.open,
                "sample_unlinked": samples,
            }

    # Also check Polymarket game markets (name contains "vs.")
    for sport_label, name_pattern in [
        ("polymarket_vs", "% vs.%"), ("polymarket_vs_space", "% vs %"),
    ]:
        pm_result = await db.execute(
            select(
                func.count().label("total"),
                func.count(FuturesMarket.event_id).label("linked"),
                func.count(case((FuturesMarket.status == "open", 1))).label("open"),
            )
            .where(
                FuturesMarket.source == "polymarket",
                FuturesMarket.name.ilike(name_pattern),
            )
        )
        pm_row = pm_result.one()
        # Sample unlinked
        pm_sample = await db.execute(
            select(
                FuturesMarket.id, FuturesMarket.external_id,
                FuturesMarket.name, FuturesMarket.event_id,
                FuturesMarket.status, FuturesMarket.commence_time,
                FuturesMarket.llm_sport_category,
            )
            .where(
                FuturesMarket.source == "polymarket",
                FuturesMarket.name.ilike(name_pattern),
                FuturesMarket.event_id.is_(None),
                FuturesMarket.status == "open",
            )
            .order_by(FuturesMarket.updated_at.desc())
            .limit(10)
        )
        results[sport_label] = {
            "total": pm_row.total, "linked": pm_row.linked,
            "unlinked": pm_row.total - pm_row.linked, "open": pm_row.open,
            "sample_unlinked": [
                {
                    "id": r.id, "name": r.name, "event_id": r.event_id,
                    "status": r.status, "sport": r.llm_sport_category,
                    "commence_time": r.commence_time.isoformat() if r.commence_time else None,
                }
                for r in pm_sample.all()
            ],
        }

    # Check NBA events without prediction market links
    # Link is via FuturesMarket.event_id → Event.id
    from app.models.models import Event, Sport
    from sqlalchemy.orm import aliased

    # Get NBA event IDs that DO have linked prediction markets
    linked_event_ids_subq = (
        select(FuturesMarket.event_id)
        .where(
            FuturesMarket.source.in_(["kalshi", "polymarket"]),
            FuturesMarket.event_id.isnot(None),
        )
        .distinct()
        .scalar_subquery()
    )

    nba_no_links = await db.execute(
        select(
            Event.id, Event.home_team_name, Event.away_team_name,
            Event.commence_time, Event.status,
        )
        .join(Sport, Event.sport_id == Sport.id)
        .where(
            Sport.key == "basketball_nba",
            Event.status.in_(["scheduled", "live"]),
            ~Event.id.in_(linked_event_ids_subq),
        )
        .order_by(Event.commence_time)
        .limit(10)
    )
    nba_missing = [
        {
            "event_id": r.id,
            "matchup": f"{r.home_team_name} vs {r.away_team_name}",
            "commence_time": r.commence_time.isoformat() if r.commence_time else None,
            "status": r.status,
        }
        for r in nba_no_links.all()
    ]

    return {
        "kalshi_game_ticker_stats": {k: v for k, v in results.items() if not k.startswith("polymarket")},
        "polymarket_game_stats": {k: v for k, v in results.items() if k.startswith("polymarket")},
        "nba_events_missing_prediction_markets": nba_missing,
    }


@router.get("/prediction-markets/debug")
async def prediction_market_debug(
    secret: str = Query(..., description="Admin secret for authorization"),
    source: Optional[str] = Query(None, description="Filter by source (kalshi, polymarket)"),
    sample_size: int = Query(50, description="Number of unlinked markets to analyze"),
    db: AsyncSession = Depends(get_db),
):
    """
    Debug prediction market matching by analyzing sample unlinked markets.

    Shows the matching funnel: how many markets pass each stage
    (game-level detection → matchup extraction → event lookup).
    Includes sample market names at each stage for pattern analysis.
    """
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from sqlalchemy import func
    from app.models.models import FuturesMarket, FuturesOutcome
    from app.utils.prediction_market_matching import (
        is_game_level_market,
        extract_matchup,
    )

    # Fetch sample of unlinked markets
    query = (
        select(FuturesMarket)
        .where(
            FuturesMarket.source.in_(["kalshi", "polymarket"]),
            FuturesMarket.event_id.is_(None),
            FuturesMarket.status == "open",
        )
        .order_by(FuturesMarket.updated_at.desc())
        .limit(sample_size)
    )
    if source:
        query = query.where(FuturesMarket.source == source)

    result = await db.execute(query)
    markets = result.scalars().all()

    # Analyze each market through the funnel
    funnel = {
        "total_analyzed": len(markets),
        "game_level": [],      # Passed is_game_level_market
        "not_game_level": [],   # Failed — most common bucket
        "matchup_extracted": [],
        "no_matchup": [],       # Passed game-level but no matchup extracted
    }

    for market in markets:
        entry = {
            "source": market.source,
            "name": market.name,
            "external_id": market.external_id,
            "category": market.category,
            "llm_sport_category": market.llm_sport_category,
        }

        if not is_game_level_market(
            market.name, market.category,
            external_id=market.external_id,
        ):
            funnel["not_game_level"].append(entry)
            continue

        matchup = extract_matchup(market.name, external_id=market.external_id)
        if not matchup:
            entry["note"] = "passed is_game_level but extract_matchup returned None"
            funnel["no_matchup"].append(entry)
            continue

        entry["team_a"] = matchup.team_a
        entry["team_b"] = matchup.team_b
        entry["format_type"] = matchup.format_type
        funnel["game_level"].append(entry)
        funnel["matchup_extracted"].append(entry)

    # Summary counts
    summary = {
        "total_analyzed": funnel["total_analyzed"],
        "not_game_level": len(funnel["not_game_level"]),
        "game_level_detected": len(funnel["game_level"]),
        "matchup_extracted": len(funnel["matchup_extracted"]),
        "no_matchup_after_detection": len(funnel["no_matchup"]),
    }

    return {
        "summary": summary,
        "sample_game_level": funnel["game_level"][:20],
        "sample_not_game_level": funnel["not_game_level"][:20],
        "sample_no_matchup": funnel["no_matchup"][:10],
    }


@router.get("/prediction-markets/tier1-gaps")
async def prediction_market_tier1_gaps(
    secret: str = Query(..., description="Admin secret for authorization"),
    db: AsyncSession = Depends(get_db),
):
    """Diagnose every unlinked open Tier 1 game market with failure reasons."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from datetime import datetime, timezone, timedelta
    from sqlalchemy import func, or_, text as _text
    from app.models.models import FuturesMarket, Event, Sport
    from app.utils.prediction_market_matching import (
        extract_matchup_with_ticker_fallback,
        extract_game_date_from_ticker,
    )
    from app.utils.sport_keys import KALSHI_GAME_TICKER_PREFIXES

    await db.execute(_text("SET LOCAL statement_timeout = '45s'"))

    _TIER1_PREFIXES = [
        p for p in KALSHI_GAME_TICKER_PREFIXES
        if any(p.startswith(s) for s in ("kxnba", "kxnhl", "kxmlb", "kxnfl"))
    ]
    tier1_conditions = [
        func.lower(FuturesMarket.external_id).like(f"{p}%")
        for p in _TIER1_PREFIXES
    ]

    result = await db.execute(
        select(FuturesMarket)
        .where(
            FuturesMarket.source == "kalshi",
            FuturesMarket.event_id.is_(None),
            FuturesMarket.status == "open",
            or_(*tier1_conditions),
        )
        .order_by(FuturesMarket.commence_time.desc())
        .limit(50)
    )
    markets = result.scalars().all()

    now = datetime.now(timezone.utc)
    gaps = []

    for market in markets:
        entry = {
            "id": market.id,
            "external_id": market.external_id,
            "name": market.name,
            "commence_time": market.commence_time.isoformat() if market.commence_time else None,
        }

        matchup = extract_matchup_with_ticker_fallback(
            market.name, external_id=market.external_id,
        )
        if not matchup:
            entry["failure"] = "matchup_extraction_failed"
            gaps.append(entry)
            continue

        entry["extracted_team_a"] = matchup.team_a
        entry["extracted_team_b"] = matchup.team_b
        entry["format_type"] = matchup.format_type

        ticker_date = extract_game_date_from_ticker(market.external_id)
        entry["ticker_date"] = ticker_date.isoformat() if ticker_date else None

        teams_to_search = [matchup.team_a]
        if matchup.team_b:
            teams_to_search.append(matchup.team_b)

        def _esc(s: str) -> str:
            return s.replace("%", r"\%").replace("_", r"\_")

        ilike_conditions = []
        for team in teams_to_search:
            pattern = f"%{_esc(team)}%"
            ilike_conditions.append(Event.home_team_name.ilike(pattern))
            ilike_conditions.append(Event.away_team_name.ilike(pattern))

        ref_time = ticker_date or market.commence_time or now
        time_delta = timedelta(hours=36) if ticker_date else timedelta(days=7)
        time_start = ref_time - time_delta
        time_end = ref_time + time_delta

        event_result = await db.execute(
            select(Event.id, Event.home_team_name, Event.away_team_name,
                   Event.commence_time, Event.status)
            .where(
                or_(*ilike_conditions),
                Event.commence_time.between(time_start, time_end),
            )
            .order_by(Event.commence_time)
            .limit(5)
        )
        candidates = event_result.all()

        if not candidates:
            event_any = await db.execute(
                select(Event.id, Event.home_team_name, Event.away_team_name,
                       Event.commence_time, Event.status)
                .where(or_(*ilike_conditions))
                .order_by(Event.commence_time.desc())
                .limit(3)
            )
            any_candidates = event_any.all()
            if any_candidates:
                entry["failure"] = "event_exists_but_outside_time_window"
                entry["nearest_events"] = [
                    {"id": c.id, "teams": f"{c.home_team_name} vs {c.away_team_name}",
                     "time": c.commence_time.isoformat() if c.commence_time else None,
                     "status": c.status}
                    for c in any_candidates
                ]
            else:
                entry["failure"] = "no_event_with_matching_teams"
                entry["search_terms"] = teams_to_search
        else:
            entry["failure"] = "event_found_but_scoring_rejected"
            entry["candidates"] = [
                {"id": c.id, "teams": f"{c.home_team_name} vs {c.away_team_name}",
                 "time": c.commence_time.isoformat() if c.commence_time else None,
                 "status": c.status}
                for c in candidates
            ]

        gaps.append(entry)

    by_failure = {}
    for g in gaps:
        f = g.get("failure", "unknown")
        by_failure.setdefault(f, []).append(g)

    return {
        "total_tier1_gaps": len(gaps),
        "by_failure": {k: {"count": len(v), "samples": v[:5]} for k, v in by_failure.items()},
        "all_gaps": gaps,
    }


@router.get("/prediction-markets/event-debug")
async def prediction_market_event_debug(
    secret: str = Query(..., description="Admin secret for authorization"),
    event_id: int = Query(..., description="Event ID to debug"),
    db: AsyncSession = Depends(get_db),
):
    """
    Debug prediction market matching for a specific event.

    Shows:
    - Event details (teams, status, commence_time)
    - Any linked FuturesMarkets (with source, name, external_id)
    - Outcomes for each linked market (name, probability, bid/ask)
    - Any win_prob_snapshots written for this event (by source)
    - Potential unlinked markets that SHOULD match (searches by team name)
    """
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from datetime import datetime, timezone, timedelta
    from sqlalchemy import or_
    from app.models.models import (
        FuturesMarket, FuturesOutcome, WinProbSnapshot,
    )
    from app.utils.prediction_market_matching import (
        is_game_level_market, extract_matchup, extract_matchup_with_ticker_fallback,
        extract_teams_from_ticker, extract_game_date_from_ticker,
        match_teams_to_event, find_moneyline_outcome, _fuzzy_team_match,
    )

    # Load event
    event_result = await db.execute(select(Event).where(Event.id == event_id))
    event = event_result.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail=f"Event {event_id} not found")

    result = {
        "event": {
            "id": event.id,
            "home_team": event.home_team_name,
            "away_team": event.away_team_name,
            "status": event.status,
            "commence_time": event.commence_time.isoformat() if event.commence_time else None,
            "sport_id": event.sport_id,
        },
        "linked_markets": [],
        "win_prob_snapshots": {},
        "potential_unlinked_matches": [],
        "diagnosis": [],
    }

    # 1. Find linked markets
    linked_result = await db.execute(
        select(FuturesMarket)
        .where(
            FuturesMarket.event_id == event_id,
            FuturesMarket.source.in_(["kalshi", "polymarket"]),
        )
    )
    linked_markets = linked_result.scalars().all()

    for market in linked_markets:
        # Get outcomes
        outcome_result = await db.execute(
            select(FuturesOutcome)
            .where(FuturesOutcome.market_id == market.id)
            .order_by(FuturesOutcome.rank)
        )
        outcomes = outcome_result.scalars().all()

        # Try matchup extraction
        matchup = extract_matchup_with_ticker_fallback(
            market.name, external_id=market.external_id,
        )

        # Try find_moneyline_outcome
        ml_result = None
        ml_diagnosis = "no matchup extracted"
        if matchup:
            ml_result = find_moneyline_outcome(
                outcomes, matchup,
                event.home_team_name, event.away_team_name,
            )
            if ml_result:
                ml_diagnosis = f"found: outcome='{ml_result[0].name}', yes_is_home={ml_result[1]}, prob={float(ml_result[0].current_probability)}"
            else:
                ml_diagnosis = f"find_moneyline_outcome returned None (matchup: {matchup.team_a} vs {matchup.team_b}, format={matchup.format_type})"

        market_info = {
            "id": market.id,
            "source": market.source,
            "name": market.name,
            "external_id": market.external_id,
            "status": market.status,
            "commence_time": market.commence_time.isoformat() if market.commence_time else None,
            "matchup": {
                "team_a": matchup.team_a if matchup else None,
                "team_b": matchup.team_b if matchup else None,
                "format_type": matchup.format_type if matchup else None,
            } if matchup else None,
            "moneyline_diagnosis": ml_diagnosis,
            "outcomes": [
                {
                    "id": o.id,
                    "name": o.name,
                    "external_id": o.external_id,
                    "probability": float(o.current_probability) if o.current_probability is not None else None,
                    "yes_bid": float(o.current_yes_bid) if o.current_yes_bid is not None else None,
                    "yes_ask": float(o.current_yes_ask) if o.current_yes_ask is not None else None,
                    "fuzzy_matches_home": _fuzzy_team_match(o.name or "", event.home_team_name),
                    "fuzzy_matches_away": _fuzzy_team_match(o.name or "", event.away_team_name),
                }
                for o in outcomes
            ],
        }
        result["linked_markets"].append(market_info)

    # 2. Check win_prob_snapshots for this event
    wp_result = await db.execute(
        select(WinProbSnapshot)
        .where(WinProbSnapshot.event_id == event_id)
        .order_by(WinProbSnapshot.captured_at.desc())
        .limit(50)
    )
    wp_snapshots = wp_result.scalars().all()

    sources_seen = {}
    for snap in wp_snapshots:
        if snap.source not in sources_seen:
            sources_seen[snap.source] = {
                "count": 0,
                "latest": None,
                "latest_home_prob": None,
            }
        sources_seen[snap.source]["count"] += 1
        if sources_seen[snap.source]["latest"] is None:
            sources_seen[snap.source]["latest"] = snap.captured_at.isoformat()
            sources_seen[snap.source]["latest_home_prob"] = float(snap.home_win_probability) if snap.home_win_probability else None
    result["win_prob_snapshots"] = sources_seen

    # 3. Search for potential unlinked markets that should match this event
    # Search by team names in market name or external_id
    home_short = event.home_team_name.split()[-1] if event.home_team_name else ""
    away_short = event.away_team_name.split()[-1] if event.away_team_name else ""

    search_conditions = []
    for team in [event.home_team_name, event.away_team_name, home_short, away_short]:
        if team and len(team) >= 3:
            pattern = f"%{team}%"
            search_conditions.append(FuturesMarket.name.ilike(pattern))
            search_conditions.append(FuturesMarket.external_id.ilike(pattern))

    # Also find Polymarket markets linked to a DIFFERENT event (mislinked)
    result["mislinked_polymarket"] = []
    if search_conditions:
        mislinked_result = await db.execute(
            select(
                FuturesMarket.id, FuturesMarket.name, FuturesMarket.event_id,
                FuturesMarket.group_id, FuturesMarket.group_type,
                FuturesMarket.llm_sport_category, FuturesMarket.status,
            )
            .where(
                FuturesMarket.source == "polymarket",
                FuturesMarket.event_id.isnot(None),
                FuturesMarket.event_id != event_id,
                or_(*search_conditions),
            )
            .limit(10)
        )
        for r in mislinked_result.all():
            result["mislinked_polymarket"].append({
                "id": r.id, "name": r.name, "event_id": r.event_id,
                "group_id": r.group_id, "group_type": r.group_type,
                "sport_cat": r.llm_sport_category, "status": r.status,
            })

    if search_conditions:
        potential_result = await db.execute(
            select(FuturesMarket)
            .where(
                FuturesMarket.source.in_(["kalshi", "polymarket"]),
                FuturesMarket.event_id.is_(None),
                or_(*search_conditions),
            )
            .limit(20)
        )
        potential_markets = potential_result.scalars().all()

        for market in potential_markets:
            ticker_date = extract_game_date_from_ticker(market.external_id)
            ticker_teams = extract_teams_from_ticker(market.external_id)
            is_game = is_game_level_market(
                market.name, market.category,
                external_id=market.external_id,
            )
            matchup = extract_matchup_with_ticker_fallback(
                market.name, external_id=market.external_id,
            )

            result["potential_unlinked_matches"].append({
                "id": market.id,
                "source": market.source,
                "name": market.name,
                "external_id": market.external_id,
                "status": market.status,
                "commence_time": market.commence_time.isoformat() if market.commence_time else None,
                "is_game_level": is_game,
                "ticker_game_date": ticker_date.isoformat() if ticker_date else None,
                "ticker_teams": list(ticker_teams) if ticker_teams else None,
                "matchup_extracted": {
                    "team_a": matchup.team_a,
                    "team_b": matchup.team_b,
                    "format_type": matchup.format_type,
                } if matchup else None,
            })

    # 4. Search for MISLINKED markets — markets that match team names but
    #    are linked to a DIFFERENT event. This catches the common case where
    #    the time-window search matched a market to the wrong game.
    result["mislinked_markets"] = []
    if search_conditions:
        mislinked_result = await db.execute(
            select(FuturesMarket)
            .where(
                FuturesMarket.source.in_(["kalshi", "polymarket"]),
                FuturesMarket.event_id.isnot(None),
                FuturesMarket.event_id != event_id,
                or_(*search_conditions),
            )
            .limit(20)
        )
        mislinked_markets = mislinked_result.scalars().all()

        for market in mislinked_markets:
            # Check if this market's name actually matches BOTH teams
            matchup = extract_matchup_with_ticker_fallback(
                market.name, external_id=market.external_id,
            )
            both_match = False
            if matchup and matchup.team_b:
                a_matches = (
                    _fuzzy_team_match(matchup.team_a, event.home_team_name)
                    or _fuzzy_team_match(matchup.team_a, event.away_team_name)
                )
                b_matches = (
                    _fuzzy_team_match(matchup.team_b, event.home_team_name)
                    or _fuzzy_team_match(matchup.team_b, event.away_team_name)
                )
                both_match = a_matches and b_matches

            # Load the event it's linked to
            linked_event_result = await db.execute(
                select(Event).where(Event.id == market.event_id)
            )
            linked_event = linked_event_result.scalar_one_or_none()

            result["mislinked_markets"].append({
                "market_id": market.id,
                "source": market.source,
                "name": market.name,
                "external_id": market.external_id,
                "both_teams_match_this_event": both_match,
                "currently_linked_to_event": {
                    "id": linked_event.id if linked_event else None,
                    "teams": f"{linked_event.away_team_name} at {linked_event.home_team_name}" if linked_event else None,
                    "status": linked_event.status if linked_event else None,
                    "commence_time": linked_event.commence_time.isoformat() if linked_event and linked_event.commence_time else None,
                } if linked_event else None,
                "matchup": {
                    "team_a": matchup.team_a,
                    "team_b": matchup.team_b,
                } if matchup else None,
            })

    # 5. Generate diagnosis
    if not linked_markets and not result["potential_unlinked_matches"] and not result["mislinked_markets"]:
        result["diagnosis"].append("No linked, potential, or mislinked markets found. Kalshi/Polymarket may not have a market for this game, or it hasn't been polled yet.")
    elif not linked_markets and result["mislinked_markets"]:
        mislinked_both = [m for m in result["mislinked_markets"] if m["both_teams_match_this_event"]]
        if mislinked_both:
            result["diagnosis"].append(
                f"MISLINKED: {len(mislinked_both)} market(s) match BOTH teams but are linked to a different event. "
                f"These need to be unlinked and re-matched. Use POST /api/admin/prediction-markets/link to fix manually, "
                f"or POST /api/admin/prediction-markets/unlink?market_id=X to unlink."
            )
    elif not linked_markets and result["potential_unlinked_matches"]:
        result["diagnosis"].append(f"Found {len(result['potential_unlinked_matches'])} potential markets but none are linked. The matching task may not have run, or time window / team name matching is failing.")
    elif linked_markets and not sources_seen:
        result["diagnosis"].append("Markets are linked but no win_prob_snapshots exist. Check find_moneyline_outcome — outcome names may not match team names, or probability values may be NULL/0/1.")
    elif linked_markets and sources_seen:
        for src, info in sources_seen.items():
            result["diagnosis"].append(f"Source '{src}': {info['count']} snapshots, latest at {info['latest']} (home_prob={info['latest_home_prob']})")

    return result


@router.post("/prediction-markets/unlink")
async def unlink_prediction_market(
    secret: str = Query(..., description="Admin secret for authorization"),
    market_id: int = Query(..., description="FuturesMarket.id to unlink"),
    db: AsyncSession = Depends(get_db),
):
    """
    Unlink a prediction market from its event. Sets event_id to NULL so the
    matching task can re-link it to the correct event on next run.
    """
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.models.models import FuturesMarket
    market_result = await db.execute(
        select(FuturesMarket).where(FuturesMarket.id == market_id)
    )
    market = market_result.scalar_one_or_none()
    if not market:
        raise HTTPException(status_code=404, detail=f"FuturesMarket {market_id} not found")

    old_event_id = market.event_id
    snapshots_deleted = 0

    # Delete orphaned win_prob_snapshots for the old event
    if old_event_id:
        from sqlalchemy import delete as sql_delete
        from app.models.models import WinProbSnapshot
        del_result = await db.execute(
            sql_delete(WinProbSnapshot).where(
                WinProbSnapshot.event_id == old_event_id,
                WinProbSnapshot.source == market.source,
            )
        )
        snapshots_deleted = del_result.rowcount

    market.event_id = None
    await db.commit()

    return {
        "status": "unlinked",
        "market_id": market_id,
        "market_name": market.name,
        "old_event_id": old_event_id,
        "snapshots_deleted": snapshots_deleted,
    }


@router.post("/prediction-markets/fix-inversions")
async def fix_inverted_prediction_market_snapshots(
    secret: str = Query(..., description="Admin secret for authorization"),
    event_id: int = Query(..., description="Event.id to fix inversions for"),
    source: Optional[str] = Query(None, description="Source to fix (kalshi/polymarket). If omitted, fixes both."),
    db: AsyncSession = Depends(get_db),
):
    """
    Fix inverted win_prob_snapshots for a specific event.

    Compares prediction market snapshots against the sportsbook consensus
    (from odds_snapshots) and flips any that appear inverted.
    """
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.models.models import Event, WinProbSnapshot, OddsSnapshot
    import statistics

    # Load event for consensus
    event = await db.get(Event, event_id)
    if not event:
        raise HTTPException(status_code=404, detail=f"Event {event_id} not found")

    # Get sportsbook consensus: latest odds snapshot or opening odds
    consensus = None
    latest_snap = await db.execute(
        select(OddsSnapshot.home_win_probability)
        .where(
            OddsSnapshot.event_id == event_id,
            OddsSnapshot.home_win_probability.isnot(None),
        )
        .order_by(OddsSnapshot.captured_at.desc())
        .limit(1)
    )
    snap_prob = latest_snap.scalar_one_or_none()
    if snap_prob is not None:
        consensus = float(snap_prob)
    elif event.opening_home_probability is not None:
        consensus = float(event.opening_home_probability)

    if consensus is None:
        raise HTTPException(
            status_code=400,
            detail="No sportsbook consensus available for this event",
        )

    # Query prediction market snapshots
    sources_filter = [source] if source else ["kalshi", "polymarket"]
    result = await db.execute(
        select(WinProbSnapshot)
        .where(
            WinProbSnapshot.event_id == event_id,
            WinProbSnapshot.source.in_(sources_filter),
        )
        .order_by(WinProbSnapshot.captured_at)
    )
    snapshots = result.scalars().all()

    if not snapshots:
        return {
            "status": "no_snapshots",
            "event_id": event_id,
            "message": "No prediction market snapshots found for this event",
        }

    # Check if snapshots are inverted: compare median snapshot against consensus
    probs = [float(s.home_win_probability) for s in snapshots if s.home_win_probability is not None]
    if not probs:
        return {"status": "no_valid_probs", "event_id": event_id}

    median_prob = statistics.median(probs)
    raw_diff = abs(median_prob - consensus)
    flipped_diff = abs((1.0 - median_prob) - consensus)

    if raw_diff <= 0.25 or flipped_diff >= raw_diff:
        return {
            "status": "not_inverted",
            "event_id": event_id,
            "consensus": round(consensus, 4),
            "median_pm_prob": round(median_prob, 4),
            "raw_diff": round(raw_diff, 4),
            "flipped_diff": round(flipped_diff, 4),
            "snapshot_count": len(snapshots),
            "message": "Snapshots appear correct (not inverted)",
        }

    # Flip all snapshots
    flipped_count = 0
    for snap in snapshots:
        if snap.home_win_probability is not None:
            old_home = float(snap.home_win_probability)
            snap.home_win_probability = round(1.0 - old_home, 4)
            snap.away_win_probability = round(old_home, 4)
            flipped_count += 1

    await db.commit()

    return {
        "status": "fixed",
        "event_id": event_id,
        "sources": sources_filter,
        "consensus": round(consensus, 4),
        "median_before_flip": round(median_prob, 4),
        "median_after_flip": round(1.0 - median_prob, 4),
        "raw_diff": round(raw_diff, 4),
        "flipped_diff": round(flipped_diff, 4),
        "snapshots_flipped": flipped_count,
        "total_snapshots": len(snapshots),
    }


@router.post("/prediction-markets/link")
async def manual_link_prediction_market(
    secret: str = Query(..., description="Admin secret for authorization"),
    market_id: int = Query(..., description="FuturesMarket.id to link"),
    event_id: int = Query(..., description="Event.id to link to"),
    db: AsyncSession = Depends(get_db),
):
    """
    Manually link a prediction market to an event.

    Sets FuturesMarket.event_id and immediately writes a win_prob_snapshot.
    Use when auto-matching fails (e.g., name patterns don't match, or the game
    is already completed and the market is resolved).
    """
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from datetime import datetime, timezone
    from app.models.models import FuturesMarket, FuturesOutcome, WinProbSnapshot
    from app.utils.prediction_market_matching import (
        extract_matchup, match_teams_to_event, find_moneyline_outcome,
    )
    from app.tasks.snapshots import _create_or_update_win_prob_snapshot

    # Load market
    market_result = await db.execute(
        select(FuturesMarket).where(FuturesMarket.id == market_id)
    )
    market = market_result.scalar_one_or_none()
    if not market:
        raise HTTPException(status_code=404, detail=f"FuturesMarket {market_id} not found")

    # Load event
    event_result = await db.execute(
        select(Event).where(Event.id == event_id)
    )
    event = event_result.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail=f"Event {event_id} not found")

    # Link the market
    market.event_id = event_id

    # Try to write a snapshot immediately
    snapshot_result = None
    matchup = extract_matchup(market.name, external_id=market.external_id)
    if matchup:
        # Load outcomes
        outcome_result = await db.execute(
            select(FuturesOutcome)
            .where(FuturesOutcome.market_id == market.id)
            .order_by(FuturesOutcome.rank)
        )
        outcomes = outcome_result.scalars().all()

        ml_result = find_moneyline_outcome(
            outcomes, matchup,
            event.home_team_name, event.away_team_name,
        )
        if ml_result:
            outcome, yes_is_home = ml_result
            yes_prob = float(outcome.current_probability)
            home_prob = yes_prob if yes_is_home else (1.0 - yes_prob)
            away_prob = 1.0 - home_prob

            snapshot, is_new = await _create_or_update_win_prob_snapshot(
                db,
                event_id=event_id,
                source=market.source,
                home_win_probability=round(home_prob, 4),
                away_win_probability=round(away_prob, 4),
                game_state={
                    "market_name": market.name,
                    "market_id": market.id,
                    "outcome_name": outcome.name,
                    "yes_probability": yes_prob,
                    "manual_link": True,
                },
            )
            if is_new:
                db.add(snapshot)
            snapshot_result = {
                "home_prob": round(home_prob, 4),
                "away_prob": round(away_prob, 4),
                "source": market.source,
                "is_new": is_new,
            }

    await db.commit()

    return {
        "status": "linked",
        "market_id": market_id,
        "event_id": event_id,
        "market_name": market.name,
        "market_source": market.source,
        "event_teams": f"{event.home_team_name} vs {event.away_team_name}",
        "snapshot": snapshot_result,
    }


# =============================================================================
# MLB Win Probability Admin Endpoints
# =============================================================================


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

@router.post("/audit/canonical-keys")
async def trigger_audit_canonical_keys(
    secret: str = Query(..., description="Admin secret for authorization"),
    limit: int = Query(50, description="Number of groups/markets to sample"),
):
    """Trigger canonical key dedup audit (runs as background Celery task)."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.tasks import audit_canonical_keys
    task = audit_canonical_keys.delay(limit)
    return {
        "status": "queued",
        "task_id": task.id,
        "message": "Canonical key audit queued. Use /api/admin/audit/task/{task_id} to check status.",
    }


@router.post("/audit/prediction-market-links")
async def trigger_audit_prediction_market_links(
    secret: str = Query(..., description="Admin secret for authorization"),
    limit: int = Query(50, description="Number of links/markets to sample"),
):
    """Trigger prediction market → event link audit (background task)."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.tasks import audit_prediction_market_links
    task = audit_prediction_market_links.delay(limit)
    return {
        "status": "queued",
        "task_id": task.id,
        "message": "Prediction market link audit queued. Use /api/admin/audit/task/{task_id} to check status.",
    }


@router.post("/audit/related-futures")
async def trigger_audit_related_futures(
    secret: str = Query(..., description="Admin secret for authorization"),
    limit: int = Query(30, description="Number of events/outcomes to sample"),
):
    """Trigger related futures coverage audit (background task)."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.tasks import audit_related_futures
    task = audit_related_futures.delay(limit)
    return {
        "status": "queued",
        "task_id": task.id,
        "message": "Related futures audit queued. Use /api/admin/audit/task/{task_id} to check status.",
    }


@router.get("/audit/task/{task_id}")
async def get_audit_task_status(
    task_id: str,
    secret: str = Query(..., description="Admin secret for authorization"),
):
    """Check the status of an audit task."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.tasks import celery_app as _celery

    result = _celery.AsyncResult(task_id)
    response = {
        "task_id": task_id,
        "state": result.state,
    }

    if result.ready():
        try:
            response["result"] = result.result
        except Exception as e:
            response["error"] = str(e)

    return response


@router.get("/audit/canonical-keys")
async def get_audit_canonical_keys(
    secret: str = Query(..., description="Admin secret for authorization"),
    db: AsyncSession = Depends(get_db),
):
    """Get latest canonical key audit results."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.models import LineMovementAnalysis

    result = await db.execute(
        select(LineMovementAnalysis)
        .where(LineMovementAnalysis.analysis_type == "audit_canonical")
        .order_by(LineMovementAnalysis.created_at.desc())
        .limit(1)
    )
    row = result.scalar_one_or_none()
    if not row:
        return {"status": "no_data", "message": "No canonical key audit has been run yet."}

    return {
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "summary": row.explanation,
        **row.movement_data,
    }


@router.get("/audit/prediction-market-links")
async def get_audit_prediction_market_links(
    secret: str = Query(..., description="Admin secret for authorization"),
    db: AsyncSession = Depends(get_db),
):
    """Get latest prediction market link audit results."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.models import LineMovementAnalysis

    result = await db.execute(
        select(LineMovementAnalysis)
        .where(LineMovementAnalysis.analysis_type == "audit_pred_market")
        .order_by(LineMovementAnalysis.created_at.desc())
        .limit(1)
    )
    row = result.scalar_one_or_none()
    if not row:
        return {"status": "no_data", "message": "No prediction market link audit has been run yet."}

    return {
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "summary": row.explanation,
        **row.movement_data,
    }


@router.get("/audit/related-futures")
async def get_audit_related_futures(
    secret: str = Query(..., description="Admin secret for authorization"),
    db: AsyncSession = Depends(get_db),
):
    """Get latest related futures audit results."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.models import LineMovementAnalysis

    result = await db.execute(
        select(LineMovementAnalysis)
        .where(LineMovementAnalysis.analysis_type == "audit_related_fut")
        .order_by(LineMovementAnalysis.created_at.desc())
        .limit(1)
    )
    row = result.scalar_one_or_none()
    if not row:
        return {"status": "no_data", "message": "No related futures audit has been run yet."}

    return {
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "summary": row.explanation,
        **row.movement_data,
    }


@router.get("/audit/patterns")
async def get_audit_patterns(
    secret: str = Query(..., description="Admin secret for authorization"),
    days: int = Query(30, description="Look back period in days"),
    db: AsyncSession = Depends(get_db),
):
    """Aggregate pattern_category across recent audit findings.

    Shows recurring issues ranked by frequency, with suggested deterministic
    rules to prevent them. When a pattern appears 3+ times, it's a strong
    signal to add a deterministic rule.
    """
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.models import LineMovementAnalysis

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    result = await db.execute(
        select(LineMovementAnalysis)
        .where(
            LineMovementAnalysis.analysis_type.in_([
                "audit_canonical", "audit_pred_market", "audit_related_fut",
            ]),
            LineMovementAnalysis.created_at >= cutoff,
        )
        .order_by(LineMovementAnalysis.created_at.desc())
    )
    audit_rows = result.scalars().all()

    # Aggregate patterns
    pattern_counts: dict[str, dict] = {}
    for row in audit_rows:
        data = row.movement_data or {}
        for finding in data.get("findings", []):
            cat = finding.get("pattern_category")
            if not cat or cat == "null":
                continue
            if cat not in pattern_counts:
                pattern_counts[cat] = {
                    "category": cat,
                    "count": 0,
                    "latest_suggestion": None,
                    "audit_types": set(),
                    "finding_types": set(),
                }
            pattern_counts[cat]["count"] += 1
            rule = finding.get("suggested_rule")
            if rule and rule != "null":
                pattern_counts[cat]["latest_suggestion"] = rule
            pattern_counts[cat]["audit_types"].add(data.get("audit_type", ""))
            pattern_counts[cat]["finding_types"].add(finding.get("type", ""))

    # Convert sets to lists for JSON and sort by count
    patterns = sorted(pattern_counts.values(), key=lambda p: p["count"], reverse=True)
    for p in patterns:
        p["audit_types"] = sorted(p["audit_types"])
        p["finding_types"] = sorted(p["finding_types"])

    return {
        "days": days,
        "total_audit_runs": len(audit_rows),
        "unique_patterns": len(patterns),
        "patterns": patterns[:50],
    }


@router.get("/matching/metrics")
async def get_matching_metrics(
    secret: str = Query(..., description="Admin secret for authorization"),
):
    """Get current matching coverage metrics and history for trending."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.tasks.matching_audit import _compute_matching_metrics_impl, get_matching_metrics_history
    from app.tasks.base import run_async as _run_async

    metrics = await _compute_matching_metrics_impl()
    history = get_matching_metrics_history(days=90)

    return {
        "current": metrics,
        "history": history,
    }


@router.post("/matching/metrics/compute")
async def trigger_matching_metrics(
    secret: str = Query(..., description="Admin secret for authorization"),
):
    """Trigger matching metrics computation as a Celery task."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.tasks import compute_matching_metrics
    result = compute_matching_metrics.delay()
    return {"status": "dispatched", "task_id": result.id}


# =============================================================================
# StatPal Integration
# =============================================================================


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

@router.post("/taxonomy/backfill")
async def backfill_taxonomy(
    secret: str = Query(..., description="Admin secret for authorization"),
    limit: int = Query(500, description="Max items to process"),
    sync: bool = Query(False, description="Run synchronously instead of via Celery"),
    db: AsyncSession = Depends(get_db),
):
    """Trigger taxonomy tag computation for events and futures markets."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    if sync:
        # Run directly in the web process using the existing DB session
        import traceback
        from app.utils.event_taxonomy import compute_event_tags, compute_market_tags
        from app.utils.aggregation import compute_aggregate_probability
        from app.utils import compute_highlight

        try:
            # --- Tag events ---
            stmt = (
                select(Event)
                .options(selectinload(Event.sport))
                .where(
                    or_(
                        Event.event_tags == None,  # noqa: E711
                        Event.event_tags == [],
                    )
                )
                .order_by(Event.commence_time.desc())
                .limit(limit)
            )
            result = await db.execute(stmt)
            events = result.scalars().all()

            events_tagged = 0
            events_errors = 0
            for event in events:
                try:
                    sport_key = event.sport.key if event.sport else ""
                    current_home_prob = compute_aggregate_probability(event)
                    opening_home_prob = (
                        float(event.opening_home_probability)
                        if event.opening_home_probability is not None else None
                    )
                    current_away_prob = (1.0 - current_home_prob) if current_home_prob else None
                    opening_away_prob = (1.0 - opening_home_prob) if opening_home_prob else None

                    highlight_result = None
                    if opening_home_prob is not None and current_home_prob is not None:
                        highlight_result = compute_highlight(
                            status=event.status,
                            commence_time=event.commence_time,
                            sport_key=sport_key,
                            opening_home_prob=opening_home_prob,
                            opening_away_prob=opening_away_prob,
                            current_home_prob=current_home_prob,
                            current_away_prob=current_away_prob,
                        )

                    raw_ei = float(event.raw_ei) if event.raw_ei is not None else None
                    tags = compute_event_tags(
                        sport_key=sport_key,
                        status=event.status,
                        commence_time=event.commence_time,
                        llm_importance=event.llm_importance,
                        llm_gender=event.llm_gender,
                        llm_level=event.llm_level,
                        llm_league=event.llm_league,
                        raw_ei=raw_ei,
                        broadcast_info=getattr(event, "broadcast_info", None),
                        highlight_result=highlight_result,
                    )
                    event.event_tags = tags
                    events_tagged += 1
                except Exception:
                    events_errors += 1

            if events_tagged > 0:
                await db.commit()

            # --- Tag futures markets ---
            from app.models import FuturesMarket as FM
            fm_stmt = (
                select(FM)
                .where(or_(FM.market_tags == None, FM.market_tags == []))  # noqa: E711
                .order_by(FM.updated_at.desc())
                .limit(limit)
            )
            fm_result = await db.execute(fm_stmt)
            markets = fm_result.scalars().all()
            futures_tagged = 0
            for market in markets:
                try:
                    mtags = compute_market_tags(
                        llm_sport_category=market.llm_sport_category,
                        llm_league=market.llm_league,
                        llm_gender=market.llm_gender,
                        llm_level=market.llm_level,
                        market_tier=market.market_tier,
                        category=market.category,
                        status=market.status,
                        resolution_date=market.resolution_date,
                        source=market.source,
                    )
                    market.market_tags = mtags
                    futures_tagged += 1
                except Exception:
                    pass
            if futures_tagged > 0:
                await db.commit()

            return {
                "status": "completed",
                "result": {
                    "events_tagged": events_tagged,
                    "events_errors": events_errors,
                    "futures_tagged": futures_tagged,
                },
            }
        except Exception as exc:
            return {
                "status": "error",
                "error": str(exc),
                "trace": traceback.format_exc().split("\n")[-5:],
            }

    from app.tasks import update_event_tags as task

    result = task.delay(limit=limit)
    return {
        "status": "queued",
        "task_id": result.id,
        "message": f"Taxonomy backfill queued (limit={limit}). Check status at /api/admin/taxonomy/task/{{task_id}}",
    }


@router.get("/taxonomy/task/{task_id}")
async def taxonomy_task_status(
    task_id: str,
    secret: str = Query(..., description="Admin secret for authorization"),
):
    """Check taxonomy task status."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.tasks import celery_app as app

    result = app.AsyncResult(task_id)
    response = {
        "task_id": task_id,
        "state": result.state,
    }
    if result.state == "SUCCESS":
        response["result"] = result.result
    elif result.state == "FAILURE":
        response["error"] = str(result.result)
    return response


@router.get("/taxonomy/vocabulary")
async def taxonomy_vocabulary(
    secret: str = Query(..., description="Admin secret for authorization"),
):
    """Return the controlled tag vocabulary for inspection."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.utils.event_taxonomy import ALLOWED_TAGS

    return {
        namespace: sorted(values)
        for namespace, values in sorted(ALLOWED_TAGS.items())
    }


@router.get("/taxonomy/dashboard")
async def taxonomy_dashboard(
    secret: str = Query(..., description="Admin secret for authorization"),
    db: AsyncSession = Depends(get_db),
):
    """Tag distribution and content quality dashboard.

    Returns coverage stats, tag value distributions, and data quality signals
    for monitoring the event taxonomy system.
    """
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from sqlalchemy import text, func as sqlfunc
    from datetime import timezone

    now = datetime.now(timezone.utc)

    # 1. Event tag coverage
    event_coverage_result = await db.execute(
        text("""
            SELECT
                COUNT(*) FILTER (WHERE event_tags IS NOT NULL AND event_tags != '[]'::jsonb) AS tagged,
                COUNT(*) FILTER (WHERE event_tags IS NULL OR event_tags = '[]'::jsonb) AS untagged
            FROM events
            WHERE status IN ('scheduled', 'live')
        """)
    )
    ec = event_coverage_result.first()
    event_coverage = {
        "tagged": ec.tagged if ec else 0,
        "untagged": ec.untagged if ec else 0,
    }

    # 2. Futures tag coverage
    futures_coverage_result = await db.execute(
        text("""
            SELECT
                COUNT(*) FILTER (WHERE market_tags IS NOT NULL AND market_tags != '[]'::jsonb) AS tagged,
                COUNT(*) FILTER (WHERE market_tags IS NULL OR market_tags = '[]'::jsonb) AS untagged
            FROM futures_markets
            WHERE status = 'open'
        """)
    )
    fc = futures_coverage_result.first()
    futures_coverage = {
        "tagged": fc.tagged if fc else 0,
        "untagged": fc.untagged if fc else 0,
    }

    # 3. Event tag distribution (last 7 days)
    event_tags_result = await db.execute(
        text("""
            SELECT tag, COUNT(*) AS count
            FROM events, jsonb_array_elements_text(event_tags) AS tag
            WHERE status IN ('scheduled', 'live', 'completed')
              AND commence_time > :cutoff
            GROUP BY tag
            ORDER BY count DESC
            LIMIT 50
        """),
        {"cutoff": now - timedelta(days=7)},
    )
    event_tag_distribution = [
        {"tag": row.tag, "count": row.count}
        for row in event_tags_result.all()
    ]

    # 4. Futures tag distribution
    futures_tags_result = await db.execute(
        text("""
            SELECT tag, COUNT(*) AS count
            FROM futures_markets, jsonb_array_elements_text(market_tags) AS tag
            WHERE status = 'open'
            GROUP BY tag
            ORDER BY count DESC
            LIMIT 50
        """)
    )
    futures_tag_distribution = [
        {"tag": row.tag, "count": row.count}
        for row in futures_tags_result.all()
    ]

    # 5. Sport distribution for events
    sport_dist_result = await db.execute(
        text("""
            SELECT s.key AS sport_key, COUNT(*) AS count
            FROM events e
            JOIN sports s ON e.sport_id = s.id
            WHERE e.status IN ('scheduled', 'live')
            GROUP BY s.key
            ORDER BY count DESC
            LIMIT 30
        """)
    )
    sport_distribution = [
        {"sport": row.sport_key, "count": row.count}
        for row in sport_dist_result.all()
    ]

    # 6. Signal tag breakdown (interesting for monitoring)
    signal_tags_result = await db.execute(
        text("""
            SELECT tag, COUNT(*) AS count
            FROM events, jsonb_array_elements_text(event_tags) AS tag
            WHERE status IN ('live', 'scheduled')
              AND tag LIKE 'signal:%'
            GROUP BY tag
            ORDER BY count DESC
        """)
    )
    signal_distribution = [
        {"tag": row.tag, "count": row.count}
        for row in signal_tags_result.all()
    ]

    return {
        "generated_at": now.isoformat(),
        "event_coverage": event_coverage,
        "futures_coverage": futures_coverage,
        "event_tag_distribution": event_tag_distribution,
        "futures_tag_distribution": futures_tag_distribution,
        "sport_distribution": sport_distribution,
        "signal_distribution": signal_distribution,
    }


@router.post("/taxonomy/enrich")
async def enrich_taxonomy(
    secret: str = Query(..., description="Admin secret for authorization"),
    event_limit: int = Query(50, description="Max events to enrich"),
    market_limit: int = Query(30, description="Max futures markets to enrich"),
):
    """Trigger LLM taxonomy enrichment for events and futures markets."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.tasks import enrich_taxonomy_llm as task

    result = task.delay(event_limit=event_limit, market_limit=market_limit)
    return {
        "status": "queued",
        "task_id": result.id,
        "message": f"LLM enrichment queued (events={event_limit}, markets={market_limit}). "
                   f"Check status at /api/admin/taxonomy/task/{result.id}",
    }


@router.get("/taxonomy/enrichment-status")
async def taxonomy_enrichment_status(
    secret: str = Query(..., description="Admin secret for authorization"),
    db: AsyncSession = Depends(get_db),
):
    """LLM enrichment coverage — events and markets with/without LLM-generated tags."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from sqlalchemy import text
    from app.utils.event_taxonomy import LLM_ENRICHMENT_NAMESPACES

    now = datetime.now(timezone.utc)
    llm_prefixes = [f"{ns}:" for ns in sorted(LLM_ENRICHMENT_NAMESPACES)]

    # Events with any LLM tags vs without (last 7 days)
    event_result = await db.execute(
        text("""
            SELECT
                COUNT(*) FILTER (
                    WHERE EXISTS (
                        SELECT 1 FROM jsonb_array_elements_text(event_tags) AS t
                        WHERE t LIKE 'stakes:%' OR t LIKE 'narrative:%'
                           OR t LIKE 'audience:%' OR t LIKE 'competitive_structure:%'
                    )
                ) AS enriched,
                COUNT(*) FILTER (
                    WHERE NOT EXISTS (
                        SELECT 1 FROM jsonb_array_elements_text(event_tags) AS t
                        WHERE t LIKE 'stakes:%' OR t LIKE 'narrative:%'
                           OR t LIKE 'audience:%' OR t LIKE 'competitive_structure:%'
                    )
                ) AS unenriched
            FROM events
            WHERE status IN ('scheduled', 'live', 'completed')
              AND commence_time > :cutoff
        """),
        {"cutoff": now - timedelta(days=7)},
    )
    er = event_result.first()
    event_enrichment = {
        "enriched": er.enriched if er else 0,
        "unenriched": er.unenriched if er else 0,
    }

    # Futures with LLM tags
    market_result = await db.execute(
        text("""
            SELECT
                COUNT(*) FILTER (
                    WHERE EXISTS (
                        SELECT 1 FROM jsonb_array_elements_text(market_tags) AS t
                        WHERE t LIKE 'stakes:%' OR t LIKE 'narrative:%'
                           OR t LIKE 'audience:%'
                    )
                ) AS enriched,
                COUNT(*) FILTER (
                    WHERE NOT EXISTS (
                        SELECT 1 FROM jsonb_array_elements_text(market_tags) AS t
                        WHERE t LIKE 'stakes:%' OR t LIKE 'narrative:%'
                           OR t LIKE 'audience:%'
                    )
                ) AS unenriched
            FROM futures_markets
            WHERE status = 'open'
        """)
    )
    mr = market_result.first()
    market_enrichment = {
        "enriched": mr.enriched if mr else 0,
        "unenriched": mr.unenriched if mr else 0,
    }

    # LLM tag distribution
    llm_tags_result = await db.execute(
        text("""
            SELECT tag, COUNT(*) AS count
            FROM events, jsonb_array_elements_text(event_tags) AS tag
            WHERE status IN ('scheduled', 'live', 'completed')
              AND commence_time > :cutoff
              AND (tag LIKE 'stakes:%' OR tag LIKE 'narrative:%'
                   OR tag LIKE 'audience:%' OR tag LIKE 'competitive_structure:%')
            GROUP BY tag
            ORDER BY count DESC
            LIMIT 40
        """),
        {"cutoff": now - timedelta(days=7)},
    )
    llm_tag_distribution = [
        {"tag": row.tag, "count": row.count}
        for row in llm_tags_result.all()
    ]

    # Cache status (taxonomy_enrichment entries in LineMovementAnalysis)
    cache_result = await db.execute(
        text("""
            SELECT
                analysis_type,
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE expires_at IS NULL OR expires_at > NOW()) AS active,
                COUNT(*) FILTER (WHERE expires_at IS NOT NULL AND expires_at <= NOW()) AS expired
            FROM line_movement_analyses
            WHERE analysis_type IN ('taxonomy_enrichment', 'taxonomy_market')
            GROUP BY analysis_type
        """)
    )
    cache_status = {}
    for row in cache_result.all():
        cache_status[row.analysis_type] = {
            "total": row.total,
            "active": row.active,
            "expired": row.expired,
        }

    return {
        "generated_at": now.isoformat(),
        "llm_namespaces": sorted(LLM_ENRICHMENT_NAMESPACES),
        "event_enrichment": event_enrichment,
        "market_enrichment": market_enrichment,
        "llm_tag_distribution": llm_tag_distribution,
        "cache_status": cache_status,
    }


@router.get("/hook-coverage")
async def hook_coverage(
    secret: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Hook description and image coverage stats for open markets."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")
    from sqlalchemy import text
    result = await db.execute(text("""
        SELECT
            COUNT(*) AS total,
            COUNT(hook_description) AS with_hook,
            COUNT(image_url) AS with_image,
            MAX(hook_generated_at) AS latest_hook,
            COUNT(*) FILTER (WHERE hook_generated_at > NOW() - INTERVAL '24 hours') AS hooks_last_24h,
            COUNT(*) FILTER (WHERE market_tier <= 3) AS tier_1_3_total,
            COUNT(*) FILTER (WHERE market_tier <= 3 AND hook_description IS NOT NULL) AS tier_1_3_with_hook
        FROM futures_markets WHERE status = 'open'
    """))
    r = result.first()
    return {
        "total_open": r.total,
        "with_hook": r.with_hook,
        "with_image": r.with_image,
        "hook_pct": round(r.with_hook / r.total * 100, 1) if r.total else 0,
        "image_pct": round(r.with_image / r.total * 100, 1) if r.total else 0,
        "latest_hook_generated_at": r.latest_hook.isoformat() if r.latest_hook else None,
        "hooks_generated_last_24h": r.hooks_last_24h,
        "tier_1_3_total": r.tier_1_3_total,
        "tier_1_3_with_hook": r.tier_1_3_with_hook,
        "tier_1_3_hook_pct": round(r.tier_1_3_with_hook / r.tier_1_3_total * 100, 1) if r.tier_1_3_total else 0,
    }


@router.post("/hook-enrichment/trigger")
async def trigger_hook_enrichment(
    secret: str = Query(...),
    limit: int = Query(100, ge=1, le=250),
):
    """Queue hook enrichment for feed-prioritized open markets."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.tasks import celery_app

    task = celery_app.send_task("app.tasks.enrich_market_hooks", kwargs={"limit": limit})
    return {
        "queued": True,
        "task_id": task.id,
        "limit": limit,
    }


@router.get("/discover-quality/trace/{market_id}")
async def discover_quality_market_trace(
    market_id: int,
    secret: str = Query(...),
    include_events: bool = Query(False),
    event_pct: float = Query(0.15, ge=0, le=1),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """Explain how a futures market flows through Discover ranking."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.routes.feed import build_discover_market_trace

    trace = await build_discover_market_trace(
        db,
        market_id,
        include_events=include_events,
        event_pct=event_pct,
        limit=limit,
    )
    if not trace:
        raise HTTPException(status_code=404, detail="Market not found")
    return trace


_DISCOVER_CONFIG_KEY = "bainluck:discover_runtime_config"


class DiscoverReviewDecisionIn(BaseModel):
    item_type: str = Field(..., max_length=20)
    item_id: str = Field(..., max_length=100)
    item_name: Optional[str] = Field(None, max_length=300)
    category: Optional[str] = Field(None, max_length=80)
    surface: Optional[str] = Field(None, max_length=20)
    auth_segment: Optional[str] = Field(None, max_length=20)
    family_key: Optional[str] = Field(None, max_length=300)
    archetype: Optional[str] = Field(None, max_length=80)
    decision: str = Field(..., max_length=40)
    admin_notes: Optional[str] = Field(None, max_length=5000)


def _discover_config_defaults() -> dict:
    return {
        "interaction_suppression_enabled": os.getenv("DISCOVER_INTERACTION_SUPPRESSION", "true").lower() != "false",
        "seen_suppression_hours": float(os.getenv("DISCOVER_SEEN_SUPPRESSION_HOURS", "48")),
        "dismiss_suppression_days": float(os.getenv("DISCOVER_DISMISS_SUPPRESSION_DAYS", "14")),
        "stale_no_movement_days": float(os.getenv("DISCOVER_STALE_NO_MOVEMENT_DAYS", "2")),
        "no_resolution_stale_days": float(os.getenv("DISCOVER_NO_RESOLUTION_STALE_DAYS", "5")),
    }


async def _load_discover_runtime_config() -> dict:
    config = _discover_config_defaults()
    try:
        from app.tasks.redis_state import get_async_redis_client

        redis = get_async_redis_client()
        raw = await redis.hgetall(_DISCOVER_CONFIG_KEY)
        if raw:
            decoded = {
                (k.decode() if isinstance(k, bytes) else k): (v.decode() if isinstance(v, bytes) else v)
                for k, v in raw.items()
            }
            if "interaction_suppression_enabled" in decoded:
                config["interaction_suppression_enabled"] = decoded["interaction_suppression_enabled"].lower() == "true"
            for key in (
                "seen_suppression_hours",
                "dismiss_suppression_days",
                "stale_no_movement_days",
                "no_resolution_stale_days",
            ):
                if key in decoded:
                    config[key] = float(decoded[key])
    except Exception:
        pass
    return config


@router.get("/discover-config")
async def get_discover_runtime_config(
    secret: str = Query(...),
):
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")
    return await _load_discover_runtime_config()


@router.post("/discover-config")
async def update_discover_runtime_config(
    secret: str = Query(...),
    body: dict = Body(...),
):
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    allowed = _discover_config_defaults()
    values = {}
    for key, default in allowed.items():
        if key not in body:
            continue
        value = body[key]
        if isinstance(default, bool):
            values[key] = "true" if bool(value) else "false"
        else:
            number = float(value)
            if number < 0:
                raise HTTPException(status_code=400, detail=f"{key} must be non-negative")
            values[key] = str(number)
    if not values:
        raise HTTPException(status_code=400, detail="No valid Discover config fields provided")

    try:
        from app.tasks.redis_state import get_async_redis_client

        redis = get_async_redis_client()
        await redis.hset(_DISCOVER_CONFIG_KEY, mapping=values)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Redis unavailable: {exc}") from exc
    return await _load_discover_runtime_config()


@router.post("/discover-review-decisions")
async def create_discover_review_decision(
    payload: DiscoverReviewDecisionIn,
    secret: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")
    valid = {"accepted_promote", "accepted_downrank", "ignored", "needs_design_fix", "needs_data_fix"}
    if payload.decision not in valid:
        raise HTTPException(status_code=400, detail=f"decision must be one of: {sorted(valid)}")

    clauses = [
        DiscoverReviewDecision.item_type == payload.item_type,
        DiscoverReviewDecision.item_id == payload.item_id,
    ]
    if payload.surface is None:
        clauses.append(DiscoverReviewDecision.surface.is_(None))
    else:
        clauses.append(DiscoverReviewDecision.surface == payload.surface)
    if payload.auth_segment is None:
        clauses.append(DiscoverReviewDecision.auth_segment.is_(None))
    else:
        clauses.append(DiscoverReviewDecision.auth_segment == payload.auth_segment)

    existing_result = await db.execute(
        select(DiscoverReviewDecision)
        .where(and_(*clauses))
        .order_by(DiscoverReviewDecision.created_at.desc())
        .limit(1)
    )
    row = existing_result.scalars().first()
    if row:
        for key, value in payload.model_dump().items():
            setattr(row, key, value)
        row.created_at = datetime.now(timezone.utc)
    else:
        row = DiscoverReviewDecision(**payload.model_dump())
        db.add(row)
    await db.commit()
    await db.refresh(row)
    return {"status": "ok", "id": row.id}


@router.get("/discover-review-decisions")
async def list_discover_review_decisions(
    secret: str = Query(...),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")
    result = await db.execute(
        select(DiscoverReviewDecision)
        .order_by(DiscoverReviewDecision.created_at.desc())
        .limit(limit)
    )
    rows = []
    seen_keys = set()
    for row in result.scalars().all():
        key = (row.item_type, row.item_id, row.surface, row.auth_segment)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        rows.append(row)
    return {
        "decisions": [
            {
                "id": row.id,
                "item_type": row.item_type,
                "item_id": row.item_id,
                "item_name": row.item_name,
                "category": row.category,
                "surface": row.surface,
                "auth_segment": row.auth_segment,
                "family_key": row.family_key,
                "archetype": row.archetype,
                "decision": row.decision,
                "admin_notes": row.admin_notes,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in rows
        ]
    }


@router.get("/discover-engagement")
async def discover_engagement_summary(
    secret: str = Query(..., description="Admin secret for authorization"),
    days: int = Query(7, ge=1, le=30),
    db: AsyncSession = Depends(get_db),
):
    """Summarize first-party Discover engagement by surface/category/type."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    result = await db.execute(
        select(
            DiscoverInteraction.surface,
            DiscoverInteraction.category,
            DiscoverInteraction.item_type,
            DiscoverInteraction.action,
            func.count(DiscoverInteraction.id).label("count"),
        )
        .where(DiscoverInteraction.created_at >= cutoff)
        .group_by(
            DiscoverInteraction.surface,
            DiscoverInteraction.category,
            DiscoverInteraction.item_type,
            DiscoverInteraction.action,
        )
    )

    groups: dict[tuple[str, str, str], dict] = {}
    for surface, category, item_type, action, count in result.all():
        key = (surface or "unknown", category or "other", item_type or "unknown")
        bucket = groups.setdefault(
            key,
            {
                "surface": key[0],
                "category": key[1],
                "item_type": key[2],
                "impressions": 0,
                "opens": 0,
                "dismisses": 0,
                "shares": 0,
                "likes": 0,
                "group_expands": 0,
                "context_expands": 0,
                "context_collapses": 0,
                "challenge_starts": 0,
                "challenge_completes": 0,
                "actions": 0,
            },
        )
        n = int(count or 0)
        if action == "impression":
            bucket["impressions"] += n
        elif action in ("detail_click", "open"):
            bucket["opens"] += n
            bucket["actions"] += n
        elif action == "dismiss":
            bucket["dismisses"] += n
            bucket["actions"] += n
        elif action == "share":
            bucket["shares"] += n
            bucket["actions"] += n
        elif action in ("like", "unlike"):
            bucket["likes"] += n
            bucket["actions"] += n
        elif action == "group_expand":
            bucket["group_expands"] += n
            bucket["actions"] += n
        elif action == "context_expand":
            bucket["context_expands"] += n
            bucket["actions"] += n
        elif action == "context_collapse":
            bucket["context_collapses"] += n
            bucket["actions"] += n
        elif action == "challenge_start":
            bucket["challenge_starts"] += n
            bucket["actions"] += n
        elif action == "challenge_complete":
            bucket["challenge_completes"] += n
            bucket["actions"] += n
        else:
            bucket["actions"] += n

    rows = []
    totals = {
        "impressions": 0,
        "opens": 0,
        "dismisses": 0,
        "shares": 0,
        "likes": 0,
        "group_expands": 0,
        "context_expands": 0,
        "context_collapses": 0,
        "challenge_starts": 0,
        "challenge_completes": 0,
        "actions": 0,
    }
    for bucket in groups.values():
        impressions = bucket["impressions"]
        for key in totals:
            totals[key] += bucket[key]
        rows.append(
            {
                **bucket,
                "open_rate": round(bucket["opens"] / impressions, 4) if impressions else 0,
                "dismiss_rate": round(bucket["dismisses"] / impressions, 4) if impressions else 0,
                "share_rate": round(bucket["shares"] / impressions, 4) if impressions else 0,
                "context_expand_rate": round(bucket["context_expands"] / impressions, 4)
                if impressions
                else 0,
                "challenge_completion_rate": round(bucket["challenge_completes"] / bucket["challenge_starts"], 4)
                if bucket["challenge_starts"]
                else 0,
            }
        )

    opportunities = []
    for row in rows:
        impressions = row["impressions"]
        if impressions < 10:
            continue
        label = f"{row['surface']} / {row['category']} / {row['item_type']}"
        if row["open_rate"] >= 0.18 or row["share_rate"] >= 0.04:
            opportunities.append(
                {
                    "kind": "promote",
                    "priority": round((row["open_rate"] * 100) + (row["share_rate"] * 250), 2),
                    "label": label,
                    "surface": row["surface"],
                    "category": row["category"],
                    "item_type": row["item_type"],
                    "metric": "open_share_rate",
                    "value": round(row["open_rate"] + row["share_rate"], 4),
                    "impressions": impressions,
                    "recommendation": "Consider a small ranking lift or stronger first-page representation.",
                }
            )
        if row["context_expand_rate"] >= 0.08:
            opportunities.append(
                {
                    "kind": "promote",
                    "priority": round(row["context_expand_rate"] * 120, 2),
                    "label": label,
                    "surface": row["surface"],
                    "category": row["category"],
                    "item_type": row["item_type"],
                    "metric": "context_expand_rate",
                    "value": row["context_expand_rate"],
                    "impressions": impressions,
                    "recommendation": "Users are asking for more context here; consider stronger snippet wording or ranking lift.",
                }
            )
        if row["dismiss_rate"] >= 0.12:
            opportunities.append(
                {
                    "kind": "investigate",
                    "priority": round(row["dismiss_rate"] * 100, 2),
                    "label": label,
                    "surface": row["surface"],
                    "category": row["category"],
                    "item_type": row["item_type"],
                    "metric": "dismiss_rate",
                    "value": row["dismiss_rate"],
                    "impressions": impressions,
                    "recommendation": "Review card wording, repetition, or category weighting before boosting similar items.",
                }
            )
        if impressions >= 50 and row["open_rate"] <= 0.02 and row["share_rate"] == 0:
            opportunities.append(
                {
                    "kind": "downrank",
                    "priority": round((0.02 - row["open_rate"]) * 100 + impressions / 100, 2),
                    "label": label,
                    "surface": row["surface"],
                    "category": row["category"],
                    "item_type": row["item_type"],
                    "metric": "low_open_rate",
                    "value": row["open_rate"],
                    "impressions": impressions,
                    "recommendation": "Candidate for a bounded score cap or improved explanation/media treatment.",
                }
            )

    from app.utils.feed_market_quality import classify_market_quality, editorial_archetype

    signed_in_expr = DiscoverInteraction.user_id.isnot(None).label("signed_in")
    review_result = await db.execute(
        select(
            DiscoverInteraction.item_type,
            DiscoverInteraction.item_id,
            func.max(DiscoverInteraction.item_name).label("item_name"),
            func.max(DiscoverInteraction.category).label("category"),
            DiscoverInteraction.surface,
            signed_in_expr,
            DiscoverInteraction.action,
            func.count(DiscoverInteraction.id).label("count"),
            func.avg(DiscoverInteraction.rank).label("avg_rank"),
            func.avg(DiscoverInteraction.score).label("avg_score"),
        )
        .where(DiscoverInteraction.created_at >= cutoff)
        .group_by(
            DiscoverInteraction.item_type,
            DiscoverInteraction.item_id,
            DiscoverInteraction.surface,
            signed_in_expr,
            DiscoverInteraction.action,
        )
    )

    review_buckets: dict[tuple[str, str, str, str], dict] = {}
    for (
        item_type,
        item_id,
        item_name,
        category,
        surface,
        signed_in,
        action,
        count,
        avg_rank,
        avg_score,
    ) in review_result.all():
        key = (
            item_type or "unknown",
            str(item_id),
            surface or "unknown",
            "signed_in" if signed_in else "anonymous",
        )
        bucket = review_buckets.setdefault(
            key,
            {
                "item_type": key[0],
                "item_id": key[1],
                "item_name": item_name,
                "category": category or "other",
                "surface": key[2],
                "auth_segment": key[3],
                "impressions": 0,
                "opens": 0,
                "dismisses": 0,
                "shares": 0,
                "likes": 0,
                "group_expands": 0,
                "context_expands": 0,
                "avg_rank": None,
                "avg_score": None,
            },
        )
        if item_name:
            bucket["item_name"] = item_name
        if category:
            bucket["category"] = category
        n = int(count or 0)
        if action == "impression":
            bucket["impressions"] += n
            if avg_rank is not None:
                bucket["avg_rank"] = round(float(avg_rank), 1)
            if avg_score is not None:
                bucket["avg_score"] = round(float(avg_score), 1)
        elif action in ("detail_click", "open"):
            bucket["opens"] += n
        elif action == "dismiss":
            bucket["dismisses"] += n
        elif action == "share":
            bucket["shares"] += n
        elif action in ("like", "unlike"):
            bucket["likes"] += n
        elif action == "group_expand":
            bucket["group_expands"] += n
        elif action == "context_expand":
            bucket["context_expands"] += n

    review_decisions_result = await db.execute(
        select(DiscoverReviewDecision)
        .order_by(DiscoverReviewDecision.created_at.desc())
        .limit(500)
    )
    all_review_decisions = []
    seen_review_decision_keys = set()
    for row in review_decisions_result.scalars().all():
        key = (row.item_type, row.item_id, row.surface, row.auth_segment)
        if key in seen_review_decision_keys:
            continue
        seen_review_decision_keys.add(key)
        all_review_decisions.append(row)
    reviewed_keys = {
        (
            row.item_type,
            row.item_id,
            row.surface or "unknown",
            row.auth_segment or "anonymous",
        )
        for row in all_review_decisions
    }

    review_queue = []
    for bucket in review_buckets.values():
        if (
            bucket["item_type"],
            bucket["item_id"],
            bucket["surface"],
            bucket["auth_segment"],
        ) in reviewed_keys:
            continue
        impressions = bucket["impressions"]
        if impressions < 5:
            continue
        open_rate = bucket["opens"] / impressions if impressions else 0
        dismiss_rate = bucket["dismisses"] / impressions if impressions else 0
        share_rate = bucket["shares"] / impressions if impressions else 0
        context_expand_rate = bucket["context_expands"] / impressions if impressions else 0
        avg_rank = bucket["avg_rank"] if bucket["avg_rank"] is not None else 999
        item_name = bucket["item_name"] or ""
        category = bucket["category"] or "other"
        if bucket["item_type"] == "futures":
            quality = classify_market_quality(item_name, category)
            archetype = editorial_archetype(item_name, category)
            family_key = quality.story_key or quality.family_key
        elif bucket["item_type"] == "event":
            archetype = "sports_story"
            family_key = f"event:{category}"
        else:
            archetype = "other"
            family_key = f"{bucket['item_type']}:{category}"

        kind = None
        recommendation = None
        priority = 0.0
        if dismiss_rate >= 0.18 and avg_rank <= 30 and open_rate <= 0.08 and share_rate <= 0.01:
            kind = "downrank"
            priority = (dismiss_rate * 100) + max(0, 30 - avg_rank)
            recommendation = "High dismiss rate for a high-ranked card. Review for score cap, family cap, stale odds, or weak explanation."
        elif open_rate >= 0.20 or share_rate >= 0.03 or context_expand_rate >= 0.10:
            kind = "promote"
            priority = (open_rate * 80) + (share_rate * 250) + (context_expand_rate * 80) + max(0, 30 - avg_rank) / 4
            recommendation = "Users are opening, sharing, or expanding this card. Review for a bounded lift or stronger family representation."
        elif dismiss_rate >= 0.12 and context_expand_rate >= 0.08:
            kind = "investigate"
            priority = (dismiss_rate * 80) + (context_expand_rate * 60)
            recommendation = "Mixed signal: people want more context but also dismiss it. Review wording and snippet length."
        if not kind:
            continue

        review_queue.append(
            {
                **bucket,
                "kind": kind,
                "priority": round(priority, 2),
                "family_key": family_key,
                "archetype": archetype,
                "open_rate": round(open_rate, 4),
                "dismiss_rate": round(dismiss_rate, 4),
                "share_rate": round(share_rate, 4),
                "context_expand_rate": round(context_expand_rate, 4),
                "recommendation": recommendation,
            }
        )

    runtime_config = await _load_discover_runtime_config()

    repeat_result = await db.execute(
        select(
            DiscoverInteraction.session_id,
            DiscoverInteraction.item_type,
            DiscoverInteraction.item_id,
            func.max(DiscoverInteraction.item_name).label("item_name"),
            func.max(DiscoverInteraction.category).label("category"),
            func.max(DiscoverInteraction.surface).label("surface"),
            func.count(DiscoverInteraction.id).label("impressions"),
        )
        .where(
            DiscoverInteraction.created_at >= cutoff,
            DiscoverInteraction.action == "impression",
            DiscoverInteraction.session_id.isnot(None),
        )
        .group_by(
            DiscoverInteraction.session_id,
            DiscoverInteraction.item_type,
            DiscoverInteraction.item_id,
        )
        .having(func.count(DiscoverInteraction.id) > 1)
    )
    repeat_rows = repeat_result.all()
    repeat_extra = sum(max(0, int(row.impressions or 0) - 1) for row in repeat_rows)
    repeat_sessions = {row.session_id for row in repeat_rows if row.session_id}
    repeat_top = sorted(
        [
            {
                "session_id": row.session_id,
                "item_type": row.item_type,
                "item_id": row.item_id,
                "item_name": row.item_name,
                "category": row.category,
                "surface": row.surface,
                "impressions": int(row.impressions or 0),
                "extra_impressions": max(0, int(row.impressions or 0) - 1),
            }
            for row in repeat_rows
        ],
        key=lambda row: row["extra_impressions"],
        reverse=True,
    )[:20]

    impression_items_result = await db.execute(
        select(
            DiscoverInteraction.item_type,
            DiscoverInteraction.item_id,
            func.max(DiscoverInteraction.item_name).label("item_name"),
            func.max(DiscoverInteraction.category).label("category"),
            func.max(DiscoverInteraction.surface).label("surface"),
            func.count(DiscoverInteraction.id).label("impressions"),
        )
        .where(
            DiscoverInteraction.created_at >= cutoff,
            DiscoverInteraction.action == "impression",
            DiscoverInteraction.item_type.in_(("event", "futures")),
        )
        .group_by(DiscoverInteraction.item_type, DiscoverInteraction.item_id)
    )
    impression_items = impression_items_result.all()
    futures_ids = []
    event_ids = []
    for row in impression_items:
        try:
            item_id_int = int(row.item_id)
        except (TypeError, ValueError):
            continue
        if row.item_type == "futures":
            futures_ids.append(item_id_int)
        elif row.item_type == "event":
            event_ids.append(item_id_int)

    futures_by_id = {}
    if futures_ids:
        futures_result = await db.execute(
            select(
                FuturesMarket.id,
                FuturesMarket.status,
                FuturesMarket.updated_at,
                FuturesMarket.resolution_date,
            ).where(FuturesMarket.id.in_(futures_ids))
        )
        futures_by_id = {row.id: row for row in futures_result.all()}

    events_by_id = {}
    if event_ids:
        events_result = await db.execute(
            select(Event.id, Event.status, Event.commence_time).where(Event.id.in_(event_ids))
        )
        events_by_id = {row.id: row for row in events_result.all()}

    now = datetime.now(timezone.utc)
    stale_impressions = 0
    stale_items = []
    for row in impression_items:
        try:
            item_id_int = int(row.item_id)
        except (TypeError, ValueError):
            continue
        impressions = int(row.impressions or 0)
        stale_reason = None
        if row.item_type == "futures":
            market = futures_by_id.get(item_id_int)
            if market:
                updated_at = market.updated_at
                if updated_at and updated_at.tzinfo is None:
                    updated_at = updated_at.replace(tzinfo=timezone.utc)
                resolution_date = market.resolution_date
                if resolution_date and resolution_date.tzinfo is None:
                    resolution_date = resolution_date.replace(tzinfo=timezone.utc)
                if market.status in ("closed", "resolved"):
                    stale_reason = "closed"
                elif resolution_date and resolution_date < now:
                    stale_reason = "past_resolution"
                elif updated_at and (now - updated_at).total_seconds() / 86400 > runtime_config["stale_no_movement_days"]:
                    stale_reason = "stale_updated_at"
        elif row.item_type == "event":
            event = events_by_id.get(item_id_int)
            if event and event.status in ("completed", "closed"):
                commence_time = event.commence_time
                if commence_time and commence_time.tzinfo is None:
                    commence_time = commence_time.replace(tzinfo=timezone.utc)
                if commence_time and (now - commence_time).total_seconds() > 8 * 3600:
                    stale_reason = "completed_old"
        if stale_reason:
            stale_impressions += impressions
            stale_items.append(
                {
                    "item_type": row.item_type,
                    "item_id": row.item_id,
                    "item_name": row.item_name,
                    "category": row.category,
                    "surface": row.surface,
                    "impressions": impressions,
                    "reason": stale_reason,
                }
            )
    stale_items.sort(key=lambda row: row["impressions"], reverse=True)

    recent_decisions = [
        row
        for row in all_review_decisions
        if row.created_at and row.created_at.replace(tzinfo=row.created_at.tzinfo or timezone.utc) >= cutoff
    ][:20]

    top_items_result = await db.execute(
        select(
            DiscoverInteraction.item_type,
            DiscoverInteraction.item_id,
            func.max(DiscoverInteraction.item_name).label("item_name"),
            func.max(DiscoverInteraction.category).label("category"),
            func.max(DiscoverInteraction.surface).label("surface"),
            func.count(DiscoverInteraction.id).label("actions"),
        )
        .where(
            DiscoverInteraction.created_at >= cutoff,
            DiscoverInteraction.action != "impression",
        )
        .group_by(DiscoverInteraction.item_type, DiscoverInteraction.item_id)
        .order_by(func.count(DiscoverInteraction.id).desc())
        .limit(20)
    )

    return {
        "days": days,
        "totals": {
            **totals,
            "open_rate": round(totals["opens"] / totals["impressions"], 4) if totals["impressions"] else 0,
            "dismiss_rate": round(totals["dismisses"] / totals["impressions"], 4) if totals["impressions"] else 0,
            "share_rate": round(totals["shares"] / totals["impressions"], 4) if totals["impressions"] else 0,
            "context_expand_rate": round(totals["context_expands"] / totals["impressions"], 4)
            if totals["impressions"]
            else 0,
            "challenge_completion_rate": round(totals["challenge_completes"] / totals["challenge_starts"], 4)
            if totals["challenge_starts"]
            else 0,
        },
        "groups": sorted(rows, key=lambda r: (r["surface"], -r["impressions"], r["category"]))[:100],
        "opportunities": sorted(opportunities, key=lambda r: r["priority"], reverse=True)[:20],
        "review_queue": sorted(review_queue, key=lambda r: r["priority"], reverse=True)[:50],
        "runtime_config": runtime_config,
        "launch_health": {
            "repeat_extra_impressions": repeat_extra,
            "repeat_rate": round(repeat_extra / totals["impressions"], 4) if totals["impressions"] else 0,
            "repeat_sessions": len(repeat_sessions),
            "stale_impressions": stale_impressions,
            "stale_rate": round(stale_impressions / totals["impressions"], 4) if totals["impressions"] else 0,
            "top_repeat_items": repeat_top,
            "top_stale_items": stale_items[:20],
        },
        "recent_review_decisions": [
            {
                "id": row.id,
                "item_type": row.item_type,
                "item_id": row.item_id,
                "item_name": row.item_name,
                "category": row.category,
                "surface": row.surface,
                "auth_segment": row.auth_segment,
                "family_key": row.family_key,
                "archetype": row.archetype,
                "decision": row.decision,
                "admin_notes": row.admin_notes,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in recent_decisions
        ],
        "top_items": [
            {
                "item_type": item_type,
                "item_id": item_id,
                "item_name": item_name,
                "category": category,
                "surface": surface,
                "actions": int(actions or 0),
            }
            for item_type, item_id, item_name, category, surface, actions in top_items_result.all()
        ],
    }


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
    secret: str = Query("", description="Admin secret"),
    days: int = Query(30, description="Look back period in days"),
    db: AsyncSession = Depends(get_db),
):
    """Per-sport breakdown of commence_time_source to audit date accuracy."""
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


@router.post("/futures/groups/discover")
async def discover_market_groups(
    secret: str = Query(""),
    limit: int = Query(500, ge=1, le=5000),
    source: Optional[str] = Query(None, description="Filter by source (polymarket, kalshi, odds_api)"),
    dry_run: bool = Query(False),
    db: AsyncSession = Depends(get_db),
):
    """
    Discover and set group_id on existing markets that don't have one.

    Scans markets without group_id and assigns based on:
    1. Source-specific hierarchy (polymarket:X, kalshi:X)
    2. Canonical market key grouping

    Use dry_run=true to preview without saving.
    """
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.utils.market_grouping import discover_group_id_for_market
    from sqlalchemy import func as sqla_func

    # Find markets without group_id
    filters = [FuturesMarket.group_id.is_(None)]
    if source:
        filters.append(FuturesMarket.source == source)

    stmt = (
        select(FuturesMarket)
        .where(*filters)
        .order_by(FuturesMarket.id)
        .limit(limit)
    )
    result = await db.execute(stmt)
    markets = result.scalars().all()

    stats = {
        "scanned": 0,
        "assigned": 0,
        "skipped": 0,
        "by_type": {},
        "dry_run": dry_run,
    }

    for market in markets:
        stats["scanned"] += 1

        group_info = discover_group_id_for_market(
            source=market.source,
            external_id=market.external_id,
            canonical_market_key=market.canonical_market_key,
            name=market.name,
            market_id=market.id,
        )

        if group_info:
            group_id, group_type = group_info
            stats["assigned"] += 1
            stats["by_type"][group_type] = stats["by_type"].get(group_type, 0) + 1

            if not dry_run:
                market.group_id = group_id
                market.group_type = group_type
                market.group_position = 0
        else:
            stats["skipped"] += 1

    if not dry_run:
        await db.commit()

    return stats


@router.get("/futures/groups/status")
async def group_status(
    secret: str = Query(""),
    db: AsyncSession = Depends(get_db),
):
    """
    Show current market grouping status.

    Returns counts of grouped vs ungrouped markets, breakdown by group_type.
    """
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from sqlalchemy import func as sqla_func

    # Total markets
    total_stmt = select(sqla_func.count(FuturesMarket.id))
    total = (await db.execute(total_stmt)).scalar() or 0

    # Markets with group_id
    grouped_stmt = select(sqla_func.count(FuturesMarket.id)).where(
        FuturesMarket.group_id.isnot(None)
    )
    grouped = (await db.execute(grouped_stmt)).scalar() or 0

    # Breakdown by group_type
    type_stmt = (
        select(
            FuturesMarket.group_type,
            sqla_func.count(FuturesMarket.id),
        )
        .where(FuturesMarket.group_id.isnot(None))
        .group_by(FuturesMarket.group_type)
    )
    type_result = await db.execute(type_stmt)
    by_type = {row[0]: row[1] for row in type_result.all()}

    # Breakdown by source
    source_stmt = (
        select(
            FuturesMarket.source,
            sqla_func.count(FuturesMarket.id),
        )
        .where(FuturesMarket.group_id.isnot(None))
        .group_by(FuturesMarket.source)
    )
    source_result = await db.execute(source_stmt)
    by_source = {row[0]: row[1] for row in source_result.all()}

    # Distinct group count
    distinct_stmt = select(
        sqla_func.count(sqla_func.distinct(FuturesMarket.group_id))
    ).where(FuturesMarket.group_id.isnot(None))
    distinct_groups = (await db.execute(distinct_stmt)).scalar() or 0

    return {
        "total_markets": total,
        "grouped": grouped,
        "ungrouped": total - grouped,
        "grouped_pct": round(grouped / total * 100, 1) if total > 0 else 0,
        "distinct_groups": distinct_groups,
        "by_type": by_type,
        "by_source": by_source,
    }


# ============================================================================
# Matching review — admin UI for approving/rejecting grid matching decisions
# ============================================================================


@router.get("/matching-review/{league_slug}")
async def get_matching_review(
    league_slug: str,
    secret: str = Query(default=""),
    db: AsyncSession = Depends(get_db),
):
    """Get current matching issues and overrides for a league grid.

    Surfaces:
    - Cross-source divergences (>15% between sources for same team+column)
    - Existing overrides (team aliases, exclusions, etc.)
    """
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.config.league_configs import get_league_config
    from app.routes.playoffs import (
        _normalize_team_name,
        _merge_probabilities,
    )
    from collections import defaultdict
    import statistics

    config = get_league_config(league_slug)
    if not config:
        raise HTTPException(404, f"Unknown league: {league_slug}")

    # 1. Fetch existing overrides
    stmt = select(MatchingOverride).where(
        MatchingOverride.league_slug == league_slug
    )
    result = await db.execute(stmt)
    overrides = result.scalars().all()

    override_list = []
    for o in overrides:
        override_list.append({
            "id": o.id,
            "type": o.override_type,
            "source_name": o.source_name,
            "target_name": o.target_name,
            "decision": o.decision,
            "context": o.context,
            "created_at": o.created_at.isoformat() if o.created_at else None,
        })

    # 2. Fetch current grid data to find issues
    # Get all matching markets
    conditions = []
    if config.league_name_patterns:
        import re
        for pat in config.league_name_patterns:
            conditions.append(FuturesMarket.name.op("~*")(pat))

    sport_cat = config.sport_category
    if conditions:
        market_filter = or_(
            FuturesMarket.llm_sport_category == sport_cat,
            *conditions,
        )
    else:
        market_filter = FuturesMarket.llm_sport_category == sport_cat

    stmt = (
        select(FuturesMarket)
        .where(market_filter, FuturesMarket.status != "resolved")
        .options(selectinload(FuturesMarket.outcomes))
    )
    result = await db.execute(stmt)
    markets = result.scalars().all()

    # Build grid_raw to detect issues — apply same filters as the grid builder
    grid_raw = defaultdict(lambda: defaultdict(list))
    from app.routes.playoffs import (
        _match_market_to_column,
        _NON_PLAYOFF_MARKET_RE,
    )

    # Apply league_name_patterns filter in Python (same as grid builder step 1)
    league_patterns = config.league_name_patterns or []
    filtered_markets = []
    for market in markets:
        if league_patterns:
            name_lower = (market.name or "").lower()
            if not any(re.search(pat, name_lower) for pat in league_patterns):
                continue
        filtered_markets.append(market)

    for market in filtered_markets:
        col_key = _match_market_to_column(market, config)
        if not col_key:
            continue
        for outcome in (market.outcomes or []):
            prob = outcome.current_probability
            if prob is None:
                # Fallback: compute from bid/ask when current_probability
                # wasn't written (e.g. during API format migrations).
                if (outcome.current_yes_bid is not None
                        and outcome.current_yes_ask is not None
                        and float(outcome.current_yes_ask) > 0):
                    prob = (float(outcome.current_yes_bid) + float(outcome.current_yes_ask)) / 2
                else:
                    continue
            if prob <= 0 or prob >= 1.0:
                continue
            oname = outcome.name or ""
            # Skip non-team outcomes (same filters as grid builder)
            if _NON_PLAYOFF_MARKET_RE.search(oname):
                continue
            if oname.lower().strip() in ("yes", "no", "over", "under"):
                continue
            # Skip prediction market 0.5 noise, but allow outcomes
            # with real trading activity (bid > 0).
            if market.source in ("kalshi", "polymarket") and abs(prob - 0.5) < 0.02:
                has_real_activity = (
                    outcome.current_yes_bid is not None
                    and float(outcome.current_yes_bid) > 0
                )
                if not has_real_activity:
                    continue
            norm = _normalize_team_name(oname)
            grid_raw[norm][col_key].append({
                "source": market.source,
                "probability": float(prob),
                "market_name": market.name,
                "market_id": market.id,
                "outcome_name": oname,
            })

    # Dedup within same source per team+column (keep lowest prob — same as grid builder)
    for norm_name in grid_raw:
        for col_key in grid_raw[norm_name]:
            entries = grid_raw[norm_name][col_key]
            if len(entries) <= 1:
                continue
            by_source: dict[str, list] = defaultdict(list)
            for e in entries:
                by_source[e["source"]].append(e)
            deduped = []
            for source, source_entries in by_source.items():
                best = min(source_entries, key=lambda e: e["probability"])
                deduped.append(best)
            grid_raw[norm_name][col_key] = deduped

    # 3. Find cross-source divergences
    divergences = []
    col_keys = [c.key for c in config.columns]
    for norm_name, col_map in grid_raw.items():
        for col_key in col_keys:
            entries = col_map.get(col_key, [])
            if len(entries) < 2:
                continue
            # Group by source
            by_source = defaultdict(list)
            for e in entries:
                by_source[e["source"]].append(e)
            if len(by_source) < 2:
                continue
            source_probs = {s: es[0]["probability"] for s, es in by_source.items()}
            vals = list(source_probs.values())
            spread = max(vals) - min(vals)
            if spread > 0.15:
                # Include market details so the admin can see exactly which markets diverge
                source_details = {}
                for s, es in by_source.items():
                    source_details[s] = {
                        "probability": round(es[0]["probability"], 4),
                        "market_name": es[0]["market_name"],
                        "market_id": es[0].get("market_id"),
                    }
                divergences.append({
                    "team": norm_name,
                    "column": col_key,
                    "spread": round(spread, 3),
                    "sources": {s: round(source_probs[s], 4) for s in source_probs},
                    "source_details": source_details,
                    "status": "needs_review",
                })

    # Sort by spread descending
    divergences.sort(key=lambda d: d["spread"], reverse=True)

    # 4. Find teams with sparse data (have championship but missing most rounds)
    sparse_teams = []
    for norm_name, col_map in grid_raw.items():
        filled = sum(1 for ck in col_keys if col_map.get(ck))
        if filled <= 2 and len(col_keys) >= 4:
            champ_prob = 0
            champ_entries = col_map.get(col_keys[-1], [])
            if champ_entries:
                champ_prob = statistics.median([e["probability"] for e in champ_entries])
            sparse_teams.append({
                "team": norm_name,
                "filled_columns": filled,
                "total_columns": len(col_keys),
                "championship_prob": round(champ_prob, 4),
                "status": "needs_review",
            })
    sparse_teams.sort(key=lambda t: t["championship_prob"])

    return {
        "league": league_slug,
        "total_teams": len(grid_raw),
        "total_columns": len(col_keys),
        "columns": col_keys,
        "overrides": override_list,
        "divergences": divergences[:30],  # Top 30
        "divergence_count": len(divergences),
        "sparse_teams": sparse_teams[:20],  # Top 20
        "sparse_count": len(sparse_teams),
    }


@router.post("/matching-review/{league_slug}/override")
async def add_matching_override(
    league_slug: str,
    override_type: str = Query(..., description="team_alias, team_exclude, team_include, market_column, source_trust, dismiss"),
    source_name: str = Query(..., description="The name/id to override"),
    target_name: Optional[str] = Query(default=None, description="Target for aliases/columns"),
    decision: str = Query(default="approved", description="approved or rejected"),
    reason: Optional[str] = Query(default=None, description="Why this decision was made"),
    secret: str = Query(default=""),
    db: AsyncSession = Depends(get_db),
):
    """Add or update a matching override. Accepts JSON body or query params.

    Override types:
    - team_alias: source_name is an alias for target_name (merge them)
    - team_exclude: source_name should be excluded from the grid
    - team_include: source_name must appear in the grid
    - market_column: source_name is a market name/id, target_name is column key
    - source_trust: source_name is "source:column", marks trust level
    - dismiss: mark a divergence as reviewed/acceptable (no grid effect)
    """
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")
    from app.config.league_configs import get_league_config
    config = get_league_config(league_slug)
    if not config:
        raise HTTPException(404, f"Unknown league: {league_slug}")

    valid_types = {"team_alias", "team_exclude", "team_include", "market_column", "source_trust", "dismiss"}
    if override_type not in valid_types:
        raise HTTPException(400, f"Invalid override_type. Must be one of: {valid_types}")

    context: dict = {}
    if reason:
        context["reason"] = reason
    context["decided_at"] = datetime.now(timezone.utc).isoformat()

    # Upsert
    stmt = select(MatchingOverride).where(
        MatchingOverride.league_slug == league_slug,
        MatchingOverride.override_type == override_type,
        MatchingOverride.source_name == source_name,
    )
    result = await db.execute(stmt)
    existing = result.scalar_one_or_none()

    if existing:
        existing.target_name = target_name
        existing.decision = decision
        existing.context = context
    else:
        override = MatchingOverride(
            league_slug=league_slug,
            override_type=override_type,
            source_name=source_name,
            target_name=target_name,
            decision=decision,
            context=context,
        )
        db.add(override)

    await db.commit()

    return {
        "status": "saved",
        "league": league_slug,
        "type": override_type,
        "source_name": source_name,
        "target_name": target_name,
        "decision": decision,
    }


@router.delete("/matching-review/{league_slug}/override/{override_id}")
async def delete_matching_override(
    league_slug: str,
    override_id: int,
    secret: str = Query(default=""),
    db: AsyncSession = Depends(get_db),
):
    """Delete a matching override."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")
    stmt = select(MatchingOverride).where(
        MatchingOverride.id == override_id,
        MatchingOverride.league_slug == league_slug,
    )
    result = await db.execute(stmt)
    override = result.scalar_one_or_none()
    if not override:
        raise HTTPException(404, "Override not found")

    await db.delete(override)
    await db.commit()
    return {"status": "deleted", "id": override_id}


# ── Eval Decisions (persisted, cross-device) ─────────────────────────────────

@router.get("/eval/decisions")
async def get_eval_decisions(
    category: Optional[str] = Query(default=None, description="Filter by category: grid, futures"),
    secret: str = Query(default=""),
    db: AsyncSession = Depends(get_db),
):
    """Get all eval decisions. Used by frontend to check 'already seen' across devices."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")
    stmt = select(MatchingOverride).where(
        MatchingOverride.override_type.in_(["eval_grid", "eval_futures"])
    )
    if category == "grid":
        stmt = stmt.where(MatchingOverride.override_type == "eval_grid")
    elif category == "futures":
        stmt = stmt.where(MatchingOverride.override_type == "eval_futures")
    stmt = stmt.order_by(MatchingOverride.created_at.desc())
    result = await db.execute(stmt)
    rows = result.scalars().all()
    return {
        "decisions": [
            {
                "id": r.id,
                "source_name": r.source_name,
                "decision": r.decision,
                "context": r.context,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ],
        "count": len(rows),
    }


@router.post("/eval/decision")
async def save_eval_decision(
    source_name: str = Query(..., description="Unique key: 'league:team:column' for grid, 'futures:market_id' for futures"),
    decision: str = Query(..., description="correct, wrong, interesting, skip, never"),
    category: str = Query(default="grid", description="grid or futures"),
    reason: Optional[str] = Query(default=None, description="Context about the decision"),
    secret: str = Query(default=""),
    db: AsyncSession = Depends(get_db),
):
    """Save an eval decision to the database. Replaces localStorage persistence."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")
    valid_decisions = {"correct", "wrong", "interesting", "skip", "never"}
    if decision not in valid_decisions:
        raise HTTPException(400, f"Invalid decision. Must be one of: {valid_decisions}")

    override_type = "eval_grid" if category == "grid" else "eval_futures"

    context: dict = {}
    if reason:
        context["reason"] = reason
    context["decided_at"] = datetime.now(timezone.utc).isoformat()

    # Upsert by source_name + override_type
    stmt = select(MatchingOverride).where(
        MatchingOverride.override_type == override_type,
        MatchingOverride.source_name == source_name,
    )
    result = await db.execute(stmt)
    existing = result.scalar_one_or_none()

    if existing:
        existing.decision = decision
        existing.context = context
    else:
        override = MatchingOverride(
            league_slug="_eval",
            override_type=override_type,
            source_name=source_name,
            decision=decision,
            context=context,
        )
        db.add(override)

    await db.commit()
    return {"status": "saved", "source_name": source_name, "decision": decision}


@router.get("/matching-review/{league_slug}/playoffstatus")
async def get_playoffstatus_comparison(
    league_slug: str,
    secret: str = Query(default=""),
    db: AsyncSession = Depends(get_db),
):
    """Compare our grid against playoffstatus.com reference data.

    Fetches the current team list and probabilities from playoffstatus.com
    and compares against our grid data. Returns:
    - Teams in playoffstatus but missing from our grid
    - Teams in our grid but not on playoffstatus
    - Probability divergences between our data and theirs
    """
    # For now, return the stored reference data if available
    # (populated by the scraper task)
    from app.config.league_configs import get_league_config
    config = get_league_config(league_slug)
    if not config:
        raise HTTPException(404, f"Unknown league: {league_slug}")

    # Check for stored reference overrides of type "team_include"
    stmt = select(MatchingOverride).where(
        MatchingOverride.league_slug == league_slug,
        MatchingOverride.override_type.in_(["team_include", "team_exclude"]),
    )
    result = await db.execute(stmt)
    overrides = result.scalars().all()

    includes = [o.source_name for o in overrides if o.override_type == "team_include" and o.decision == "approved"]
    excludes = [o.source_name for o in overrides if o.override_type == "team_exclude" and o.decision == "approved"]

    return {
        "league": league_slug,
        "reference_includes": includes,
        "reference_excludes": excludes,
        "note": "Use POST /admin/matching-review/{league}/scrape-playoffstatus to fetch fresh reference data",
    }


@router.post("/matching-review/{league_slug}/scrape-playoffstatus")
async def scrape_playoffstatus(
    league_slug: str,
    secret: str = Query(default=""),
    db: AsyncSession = Depends(get_db),
):
    """Scrape playoffstatus.com for reference team list and probabilities."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")
    import httpx
    import re
    from app.config.league_configs import get_league_config

    config = get_league_config(league_slug)
    if not config:
        raise HTTPException(404, f"Unknown league: {league_slug}")

    # Map league slugs to playoffstatus URLs
    url_map = {
        "nba": [
            "https://www.playoffstatus.com/nba/easternstandings.html",
            "https://www.playoffstatus.com/nba/westernstandings.html",
        ],
        "nhl": [
            "https://www.playoffstatus.com/nhl/easternstandings.html",
            "https://www.playoffstatus.com/nhl/westernstandings.html",
        ],
        "ncaa-basketball": [
            "https://www.playoffstatus.com/ncaabasketball/ncaabasketball.html",
        ],
    }

    urls = url_map.get(league_slug, [])
    if not urls:
        return {"status": "unsupported", "message": f"No playoffstatus URL mapping for {league_slug}"}

    teams_found = []
    errors = []

    async with httpx.AsyncClient(timeout=30) as client:
        for url in urls:
            try:
                resp = await client.get(url, follow_redirects=True)
                resp.raise_for_status()
                html = resp.text

                # Parse team names from HTML tables
                # Playoffstatus uses table rows with team names in specific patterns
                # Extract team names from table cells with class patterns
                # The HTML structure varies by sport but team names appear in
                # <td> tags often with links

                # Generic team name extraction from HTML
                # Look for patterns like team names in table rows
                team_pattern = re.findall(
                    r'<a[^>]*>([A-Z][a-zA-Z\s&\'\.\-]+(?:ers|ics|ets|ons|ies|ors|ins|awks|eat|urs|ols|ers|lts|nes|ings|oos|ies|gers|ks|ns|rs|ts|es|gs|ds|cs|bs|ps|ves|zes))</a>',
                    html,
                )
                # Also try simpler team name patterns
                if not team_pattern:
                    team_pattern = re.findall(
                        r'>(\w[\w\s\'\.]+(?:76ers|Heat|Jazz|Suns|Magic|Nets|Bucks|Bulls|Hawks|Knicks|Spurs|Kings|Celtics|Lakers|Pistons|Rockets|Thunder|Raptors|Hornets|Pacers|Wizards|Nuggets|Grizzlies|Pelicans|Warriors|Clippers|Cavaliers|Mavericks|Timberwolves))<',
                        html,
                    )

                # Extract probabilities if present
                prob_pattern = re.findall(r'(\d+(?:\.\d+)?)\s*%', html)

                for team_name in team_pattern:
                    team_name = team_name.strip()
                    if len(team_name) > 3 and team_name not in teams_found:
                        teams_found.append(team_name)

            except Exception as e:
                errors.append({"url": url, "error": str(e)})

    # Store as team_include overrides
    created = 0
    for team_name in teams_found:
        norm = team_name.lower().strip()
        stmt = select(MatchingOverride).where(
            MatchingOverride.league_slug == league_slug,
            MatchingOverride.override_type == "team_include",
            MatchingOverride.source_name == norm,
        )
        result = await db.execute(stmt)
        existing = result.scalar_one_or_none()
        if not existing:
            override = MatchingOverride(
                league_slug=league_slug,
                override_type="team_include",
                source_name=norm,
                target_name=team_name,
                decision="approved",
                context={"source": "playoffstatus.com", "scraped_at": datetime.now(timezone.utc).isoformat()},
            )
            db.add(override)
            created += 1

    if created:
        await db.commit()

    return {
        "status": "scraped",
        "league": league_slug,
        "teams_found": len(teams_found),
        "teams_created": created,
        "teams": teams_found,
        "errors": errors,
    }


# ---------------------------------------------------------------------------
# Consolidated Operations Dashboard
# ---------------------------------------------------------------------------

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
    """
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from sqlalchemy import text, func as sa_func, distinct, case, literal_column
    from app.tasks.redis_state import (
        get_odds_api_quota, get_odds_api_quota_history,
        get_odds_api_task_breakdown,
        get_odds_api_sport_breakdown,
        get_all_task_metrics, get_redis_client,
    )
    import calendar as cal_mod

    now = datetime.now(timezone.utc)

    # --- 1. Odds API Quota ---
    quota = get_odds_api_quota()
    history = get_odds_api_quota_history(hours=720)  # 30 days
    task_breakdown = get_odds_api_task_breakdown(hours=720)  # 30 days
    sport_breakdown_24h = get_odds_api_sport_breakdown(hours=24)
    sport_breakdown_7d = get_odds_api_sport_breakdown(hours=168)

    # Compute daily usage deltas — only include current month (UTC)
    current_month_prefix = now.strftime("%Y-%m-")
    daily_map: dict[str, dict] = {}
    for entry in history:
        day = entry["hour"][:10]
        if not day.startswith(current_month_prefix):
            continue  # skip previous month's data
        daily_map[day] = entry
    daily_usage = []
    sorted_days = sorted(daily_map.keys())
    for i, day in enumerate(sorted_days):
        used = daily_map[day]["used"]
        prev_used = daily_map[sorted_days[i - 1]]["used"] if i > 0 else 0
        delta = used - prev_used
        if delta < 0:
            delta = used  # month rollover
        daily_usage.append({"date": day, "daily_requests": delta, "cumulative": used})

    # Budget projection
    total_budget = 5_000_000
    today = now.date()
    days_in_month = cal_mod.monthrange(today.year, today.month)[1]
    day_of_month = today.day
    days_remaining = days_in_month - day_of_month

    # 48h pace: average daily burn over last 2 COMPLETE days (exclude today's partial)
    today_str = today.isoformat()
    complete_days = [d for d in daily_usage if d["daily_requests"] > 0 and d["date"] != today_str]
    recent_daily = complete_days[-2:] if len(complete_days) >= 2 else complete_days[-1:] if complete_days else []
    pace_48h = sum(d["daily_requests"] for d in recent_daily) / max(len(recent_daily), 1)
    projected_eom = (quota.get("used", 0) or 0) + int(pace_48h * days_remaining)

    # Linear budget line
    linear_daily_budget = total_budget / days_in_month

    quota_section = {
        "current": quota,
        "daily_usage": daily_usage,
        "daily_by_task": task_breakdown,
        "by_sport_24h": sport_breakdown_24h,
        "by_sport_7d": sport_breakdown_7d,
        "hourly_history": history[-168:],  # last 7 days
        "budget": {
            "total": total_budget,
            "days_in_month": days_in_month,
            "day_of_month": day_of_month,
            "days_remaining": days_remaining,
            "linear_daily_budget": round(linear_daily_budget),
            "pace_48h_daily": round(pace_48h),
            "projected_eom": projected_eom,
            "projected_surplus": total_budget - projected_eom,
        },
    }

    # --- 2. Source Coverage by Sport ---
    # Count events per sport and how many have data from each source
    try:
        await db.execute(text("SET LOCAL statement_timeout = '10s'"))

        # 2a. Event-level source coverage
        coverage_q = await db.execute(text("""
            WITH recent_events AS (
                SELECT e.id, s.key AS sport_key,
                       e.external_id, e.espn_id, e.statpal_fixture_id,
                       e.win_probability_sources,
                       e.status
                FROM events e
                JOIN sports s ON e.sport_id = s.id
                WHERE e.commence_time >= NOW() - INTERVAL '7 days'
                  AND e.commence_time <= NOW() + INTERVAL '2 days'
            ),
            pm_links AS (
                SELECT DISTINCT fm.event_id, fm.source AS pm_source
                FROM futures_markets fm
                WHERE fm.event_id IS NOT NULL
                  AND fm.market_type = 'game'
            ),
            wp_sources AS (
                SELECT DISTINCT wp.event_id, wp.source AS wp_source
                FROM win_prob_snapshots wp
                WHERE wp.captured_at >= NOW() - INTERVAL '7 days'
            )
            SELECT
                re.sport_key,
                COUNT(*) AS total_events,
                COUNT(CASE WHEN re.status = 'live' THEN 1 END) AS live_events,
                COUNT(re.external_id) AS has_odds_api,
                COUNT(re.espn_id) AS has_espn,
                COUNT(re.statpal_fixture_id) AS has_statpal,
                COUNT(DISTINCT CASE WHEN wp.wp_source = 'espn' THEN re.id END) AS has_espn_wp,
                COUNT(DISTINCT CASE WHEN wp.wp_source = 'stat_model' THEN re.id END) AS has_model,
                COUNT(DISTINCT CASE WHEN wp.wp_source = 'mlb' THEN re.id END) AS has_mlb,
                COUNT(DISTINCT CASE WHEN wp.wp_source = 'kalshi' THEN re.id END) AS has_kalshi_wp,
                COUNT(DISTINCT CASE WHEN wp.wp_source = 'polymarket' THEN re.id END) AS has_polymarket_wp,
                COUNT(DISTINCT CASE WHEN pm.pm_source = 'kalshi' THEN re.id END) AS has_kalshi_pm,
                COUNT(DISTINCT CASE WHEN pm.pm_source = 'polymarket' THEN re.id END) AS has_polymarket_pm
            FROM recent_events re
            LEFT JOIN pm_links pm ON pm.event_id = re.id
            LEFT JOIN wp_sources wp ON wp.event_id = re.id
            GROUP BY re.sport_key
            ORDER BY COUNT(*) DESC
        """))
        source_coverage = [
            {
                "sport": r.sport_key,
                "total": r.total_events,
                "live": r.live_events,
                "odds_api": r.has_odds_api,
                "espn": r.has_espn,
                "statpal": r.has_statpal,
                "espn_wp": r.has_espn_wp,
                "model": r.has_model,
                "mlb": r.has_mlb,
                "kalshi": max(r.has_kalshi_wp, r.has_kalshi_pm),
                "polymarket": max(r.has_polymarket_wp, r.has_polymarket_pm),
            }
            for r in coverage_q.all()
        ]

        # 2a-ii. Per-sport snapshot counts (proxy for API activity)
        sport_activity_q = await db.execute(text("""
            SELECT s.key AS sport_key,
                   COUNT(*) AS snapshots_24h
            FROM odds_snapshots os
            JOIN events e ON os.event_id = e.id
            JOIN sports s ON e.sport_id = s.id
            WHERE os.captured_at >= NOW() - INTERVAL '24 hours'
            GROUP BY s.key
            ORDER BY COUNT(*) DESC
        """))
        sport_activity = {r.sport_key: r.snapshots_24h for r in sport_activity_q.all()}
        # Attach to coverage rows
        for row in source_coverage:
            row["snapshots_24h"] = sport_activity.get(row["sport"], 0)

        # 2a-iii. Trended coverage for top-tier sports (daily %)
        # Look back 14 days + forward to all scheduled events
        tier1_sports = [
            'basketball_nba', 'americanfootball_nfl', 'icehockey_nhl',
            'baseball_mlb', 'basketball_ncaab', 'golf_pga',
        ]
        trend_q = await db.execute(text("""
            WITH daily_events AS (
                SELECT
                    DATE(e.commence_time) AS event_date,
                    s.key AS sport_key,
                    COUNT(*) AS total,
                    COUNT(e.external_id) AS has_odds_api,
                    COUNT(e.espn_id) AS has_espn,
                    COUNT(e.statpal_fixture_id) AS has_statpal
                FROM events e
                JOIN sports s ON e.sport_id = s.id
                WHERE s.key = ANY(:sports)
                  AND e.commence_time >= NOW() - INTERVAL '14 days'
                  AND e.commence_time <= NOW() + INTERVAL '30 days'
                GROUP BY DATE(e.commence_time), s.key
                HAVING COUNT(*) >= 1
            )
            SELECT * FROM daily_events
            ORDER BY sport_key, event_date
        """), {"sports": tier1_sports})
        coverage_trend_raw = trend_q.all()

        # Also get win_prob source coverage per day for past events
        wp_trend_q = await db.execute(text("""
            SELECT
                DATE(e.commence_time) AS event_date,
                s.key AS sport_key,
                COUNT(DISTINCT e.id) AS total,
                COUNT(DISTINCT CASE WHEN wp.source = 'espn' THEN e.id END) AS espn_wp,
                COUNT(DISTINCT CASE WHEN wp.source = 'stat_model' THEN e.id END) AS model,
                COUNT(DISTINCT CASE WHEN wp.source = 'kalshi' THEN e.id END) AS kalshi,
                COUNT(DISTINCT CASE WHEN wp.source = 'polymarket' THEN e.id END) AS polymarket
            FROM events e
            JOIN sports s ON e.sport_id = s.id
            LEFT JOIN win_prob_snapshots wp ON wp.event_id = e.id
            WHERE s.key = ANY(:sports)
              AND e.commence_time >= NOW() - INTERVAL '14 days'
              AND e.commence_time <= NOW()
            GROUP BY DATE(e.commence_time), s.key
        """), {"sports": tier1_sports})
        wp_trend_raw = {
            (r.event_date.isoformat(), r.sport_key): r
            for r in wp_trend_q.all()
        }

        coverage_trend: list[dict] = []
        for r in coverage_trend_raw:
            entry: dict = {
                "date": r.event_date.isoformat(),
                "sport": r.sport_key,
                "total": r.total,
                "odds_api_pct": round(r.has_odds_api / r.total * 100) if r.total else 0,
                "espn_pct": round(r.has_espn / r.total * 100) if r.total else 0,
                "statpal_pct": round(r.has_statpal / r.total * 100) if r.total else 0,
                "is_future": r.event_date > now.date(),
            }
            # Add win prob sources for past dates
            wp_key = (r.event_date.isoformat(), r.sport_key)
            if wp_key in wp_trend_raw:
                wp = wp_trend_raw[wp_key]
                entry["espn_wp_pct"] = round(wp.espn_wp / wp.total * 100) if wp.total else 0
                entry["model_pct"] = round(wp.model / wp.total * 100) if wp.total else 0
                entry["kalshi_pct"] = round(wp.kalshi / wp.total * 100) if wp.total else 0
                entry["polymarket_pct"] = round(wp.polymarket / wp.total * 100) if wp.total else 0
            coverage_trend.append(entry)

        # 2b. Futures-level source coverage (by sport category)
        futures_q = await db.execute(text("""
            SELECT
                COALESCE(s.key, fm.llm_sport_category, 'unknown') AS sport_key,
                COUNT(DISTINCT fm.id) AS total_markets,
                COUNT(DISTINCT CASE WHEN fm.source = 'odds_api' THEN fm.id END) AS odds_api,
                COUNT(DISTINCT CASE WHEN fm.source = 'kalshi' THEN fm.id END) AS kalshi,
                COUNT(DISTINCT CASE WHEN fm.source = 'polymarket' THEN fm.id END) AS polymarket,
                COUNT(DISTINCT CASE WHEN fm.source = 'datagolf' THEN fm.id END) AS datagolf
            FROM futures_markets fm
            LEFT JOIN sports s ON fm.sport_id = s.id
            WHERE (fm.market_type IS NULL OR fm.market_type != 'game')
              AND fm.event_id IS NULL
            GROUP BY COALESCE(s.key, fm.llm_sport_category, 'unknown')
            ORDER BY COUNT(DISTINCT fm.id) DESC
        """))
        futures_coverage = [
            {
                "sport": r.sport_key,
                "total_markets": r.total_markets,
                "odds_api": r.odds_api,
                "kalshi": r.kalshi,
                "polymarket": r.polymarket,
                "datagolf": r.datagolf,
            }
            for r in futures_q.all()
        ]
    except Exception as e:
        source_coverage = [{"error": str(e)}]
        coverage_trend = []
        futures_coverage = [{"error": str(e)}]

    # --- 3. Worker Task Metrics ---
    tasks = get_all_task_metrics()

    # Worker heartbeat
    try:
        r = get_redis_client()
        heartbeat = r.get("bainluck:heartbeat")
        if heartbeat:
            heartbeat_time = datetime.fromisoformat(heartbeat.decode())
            heartbeat_age = (now - heartbeat_time).total_seconds()
            worker_status = "healthy" if heartbeat_age < 180 else "unhealthy"
        else:
            heartbeat_age = None
            worker_status = "unknown"
    except Exception:
        heartbeat_age = None
        worker_status = "error"

    _ESSENTIAL_TASKS = {
        "poll_odds", "espn_sync", "statpal_livescores", "statpal_schedules",
        "prediction_market_match", "prediction_market_live", "mlb_sync",
        "discover_events", "transition_statuses",
    }
    critical_tasks = [t for t in tasks if t.get("health") == "critical"]
    degraded_tasks = [t for t in tasks if t.get("health") == "degraded"]
    essential_critical = [t for t in critical_tasks if t.get("task") in _ESSENTIAL_TASKS]

    worker_section = {
        "worker_status": worker_status,
        "heartbeat_age_seconds": round(heartbeat_age) if heartbeat_age else None,
        "overall_health": (
            "worker_down" if worker_status != "healthy"
            else "critical" if essential_critical
            else "degraded" if critical_tasks or degraded_tasks
            else "healthy" if tasks
            else "no_data"
        ),
        "critical_tasks": [t["task"] for t in critical_tasks],
        "degraded_tasks": [t["task"] for t in degraded_tasks],
        "tasks": tasks,
    }

    # --- 4. Database Health ---
    try:
        db_q = await db.execute(text("""
            SELECT
                (SELECT COUNT(*) FROM events WHERE status IN ('live', 'scheduled')
                 AND commence_time >= NOW() - INTERVAL '1 day') AS active_events,
                (SELECT COUNT(*) FROM events WHERE status = 'live') AS live_events,
                (SELECT COUNT(*) FROM odds_snapshots
                 WHERE captured_at >= NOW() - INTERVAL '1 hour') AS snapshots_last_hour,
                (SELECT COUNT(*) FROM win_prob_snapshots
                 WHERE captured_at >= NOW() - INTERVAL '1 hour') AS winprob_last_hour,
                (SELECT pg_database_size(current_database())) AS db_size_bytes,
                (SELECT MIN(captured_at) FROM odds_snapshots
                 WHERE captured_at >= NOW() - INTERVAL '7 days') AS oldest_snapshot_7d
        """))
        db_row = db_q.one()

        db_size_mb = db_row.db_size_bytes / 1024 / 1024
        db_size_gb = db_row.db_size_bytes / (1024 ** 3)

        # Compute growth rate from snapshot row counts
        # Each odds_snapshot row ≈ 0.5KB, each winprob row ≈ 0.3KB
        # Use rows written per day as proxy for daily growth
        growth_rate_mb_per_day = None
        days_until_full = None
        try:
            growth_q = await db.execute(text("""
                SELECT
                    COALESCE((SELECT COUNT(*) FROM odds_snapshots
                     WHERE captured_at >= NOW() - INTERVAL '24 hours'), 0) AS odds_rows_24h,
                    COALESCE((SELECT COUNT(*) FROM win_prob_snapshots
                     WHERE captured_at >= NOW() - INTERVAL '24 hours'), 0) AS wp_rows_24h,
                    COALESCE((SELECT COUNT(*) FROM futures_odds_snapshots
                     WHERE captured_at >= NOW() - INTERVAL '24 hours'), 0) AS futures_rows_24h
            """))
            g = growth_q.one()
            # Rough estimate: odds ~500B/row, winprob ~300B/row, futures ~400B/row
            daily_bytes = (g.odds_rows_24h * 500) + (g.wp_rows_24h * 300) + (g.futures_rows_24h * 400)
            growth_rate_mb_per_day = round(daily_bytes / 1024 / 1024, 1)
            storage_limit_gb = 64  # standard-0 plan
            remaining_gb = storage_limit_gb - db_size_gb
            if growth_rate_mb_per_day > 0:
                days_until_full = round((remaining_gb * 1024) / growth_rate_mb_per_day)
        except Exception:
            pass

        # Table sizes
        table_q = await db.execute(text("""
            SELECT
                tablename,
                pg_total_relation_size('public.' || tablename) AS size_bytes
            FROM pg_tables
            WHERE schemaname = 'public'
            ORDER BY pg_total_relation_size('public.' || tablename) DESC
        """))
        table_sizes = [
            {"table": r.tablename, "size_mb": round(r.size_bytes / 1024 / 1024, 1)}
            for r in table_q.all()
        ]

        # Dead tuple stats from pg_stat_user_tables
        dead_tuple_q = await db.execute(text("""
            SELECT relname, n_live_tup, n_dead_tup,
                   last_autovacuum, last_autoanalyze
            FROM pg_stat_user_tables
            WHERE schemaname = 'public'
              AND n_live_tup + n_dead_tup > 1000
            ORDER BY n_dead_tup DESC
        """))
        dead_tuples = [
            {
                "table": r.relname,
                "live_tuples": r.n_live_tup,
                "dead_tuples": r.n_dead_tup,
                "dead_pct": round(r.n_dead_tup / max(r.n_live_tup + r.n_dead_tup, 1) * 100, 1),
                "last_autovacuum": r.last_autovacuum.isoformat() if r.last_autovacuum else None,
            }
            for r in dead_tuple_q.all()
        ]
        total_live = sum(d["live_tuples"] for d in dead_tuples)
        total_dead = sum(d["dead_tuples"] for d in dead_tuples)

        # Record DB size for trending and fetch history
        from app.tasks.redis_state import record_db_size, get_db_size_history
        record_db_size(db_size_mb)
        db_size_trend = get_db_size_history(days=90)

        db_section = {
            "active_events": db_row.active_events,
            "live_events": db_row.live_events,
            "snapshots_last_hour": db_row.snapshots_last_hour,
            "winprob_last_hour": db_row.winprob_last_hour,
            "db_size_mb": round(db_size_mb, 1),
            "growth_rate_mb_per_day": growth_rate_mb_per_day,
            "days_until_full": days_until_full,
            "table_sizes": table_sizes,
            "dead_tuples": dead_tuples,
            "total_live_tuples": total_live,
            "total_dead_tuples": total_dead,
            "dead_tuple_pct": round(total_dead / max(total_live + total_dead, 1) * 100, 1),
            "size_trend": db_size_trend,
            "plan": {
                "name": "standard-0",
                "storage_limit_gb": 64,
                "storage_used_gb": round(db_size_gb, 2),
                "storage_pct": round(db_size_gb / 64 * 100, 1),
                "connections_limit": 200,
            },
        }
    except Exception as e:
        db_section = {"error": str(e)}

    # --- 6. Matching Metrics ---
    try:
        from app.tasks.matching_audit import get_matching_metrics_history
        matching_history = get_matching_metrics_history(days=90)
    except Exception:
        matching_history = []

    # --- 7. Game State Indicators by Sport ---
    game_state_section: list[dict] = []
    try:
        from app.utils.sport_keys import EXPECTED_GAME_STATE_INDICATORS

        gs_sql = text("""
            SET LOCAL statement_timeout = '15s';

            WITH completed_events AS (
                SELECT e.id AS event_id, s.key AS sport_key
                FROM events e
                JOIN sports s ON s.id = e.sport_id
                WHERE e.status IN ('completed', 'closed')
                  AND e.commence_time >= NOW() - INTERVAL '14 days'
                  AND e.espn_id IS NOT NULL
            ),
            indicators AS (
                SELECT ce.event_id, ce.sport_key, sp.period AS indicator
                FROM completed_events ce
                JOIN scoring_plays sp ON sp.event_id = ce.event_id
                WHERE sp.period IS NOT NULL
                UNION
                SELECT ce.event_id, ce.sport_key, es.period AS indicator
                FROM completed_events ce
                JOIN espn_snapshots es ON es.event_id = ce.event_id
                WHERE es.period IS NOT NULL
                UNION
                SELECT ce.event_id, ce.sport_key,
                       wp.game_state->>'period' AS indicator
                FROM completed_events ce
                JOIN win_prob_snapshots wp ON wp.event_id = ce.event_id
                WHERE wp.game_state->>'period' IS NOT NULL
            ),
            per_event AS (
                SELECT event_id, sport_key,
                       COUNT(DISTINCT indicator) AS indicator_count
                FROM indicators
                GROUP BY event_id, sport_key
            )
            SELECT sport_key,
                   COUNT(*) AS total_events,
                   MIN(indicator_count) AS min_indicators,
                   MAX(indicator_count) AS max_indicators,
                   ROUND(AVG(indicator_count), 1) AS avg_indicators,
                   COUNT(*) FILTER (WHERE indicator_count = 0) AS zero_count
            FROM per_event
            GROUP BY sport_key
            ORDER BY total_events DESC
        """)
        gs_result = await db.execute(gs_sql)
        gs_rows = gs_result.fetchall()

        for row in gs_rows:
            sport_key = row[0]
            total = int(row[1])
            min_ind = int(row[2])
            max_ind = int(row[3])
            avg_ind = float(row[4])
            zero_count = int(row[5])
            expected = EXPECTED_GAME_STATE_INDICATORS.get(sport_key)

            entry: dict = {
                "sport_key": sport_key,
                "total_events": total,
                "min_indicators": min_ind,
                "max_indicators": max_ind,
                "avg_indicators": avg_ind,
                "zero_count": zero_count,
                "expected": expected,
            }

            if expected is not None:
                # Fixed-period sport: bucket into met/under/over
                # Re-query would be expensive; approximate from aggregates.
                # We already have min/max/total — query per-bucket counts.
                entry["type"] = "fixed"
            else:
                entry["type"] = "variable"

            game_state_section.append(entry)

        # Second pass for fixed sports: get actual bucket counts.
        if any(e["type"] == "fixed" for e in game_state_section):
            bucket_sql = text("""
                SET LOCAL statement_timeout = '15s';

                WITH completed_events AS (
                    SELECT e.id AS event_id, s.key AS sport_key
                    FROM events e
                    JOIN sports s ON s.id = e.sport_id
                    WHERE e.status IN ('completed', 'closed')
                      AND e.commence_time >= NOW() - INTERVAL '14 days'
                      AND e.espn_id IS NOT NULL
                ),
                indicators AS (
                    SELECT ce.event_id, ce.sport_key, sp.period AS indicator
                    FROM completed_events ce
                    JOIN scoring_plays sp ON sp.event_id = ce.event_id
                    WHERE sp.period IS NOT NULL
                    UNION
                    SELECT ce.event_id, ce.sport_key, es.period AS indicator
                    FROM completed_events ce
                    JOIN espn_snapshots es ON es.event_id = ce.event_id
                    WHERE es.period IS NOT NULL
                    UNION
                    SELECT ce.event_id, ce.sport_key,
                           wp.game_state->>'period' AS indicator
                    FROM completed_events ce
                    JOIN win_prob_snapshots wp ON wp.event_id = ce.event_id
                    WHERE wp.game_state->>'period' IS NOT NULL
                ),
                per_event AS (
                    SELECT event_id, sport_key,
                           COUNT(DISTINCT indicator) AS indicator_count
                    FROM indicators
                    GROUP BY event_id, sport_key
                )
                SELECT sport_key, indicator_count, COUNT(*) AS cnt
                FROM per_event
                GROUP BY sport_key, indicator_count
                ORDER BY sport_key, indicator_count
            """)
            bucket_result = await db.execute(bucket_sql)
            bucket_rows = bucket_result.fetchall()

            # Build lookup: sport_key -> {indicator_count: count}
            buckets: dict[str, dict[int, int]] = {}
            for brow in bucket_rows:
                sk = brow[0]
                ic = int(brow[1])
                cnt = int(brow[2])
                buckets.setdefault(sk, {})[ic] = cnt

            for entry in game_state_section:
                if entry["type"] != "fixed":
                    continue
                sk = entry["sport_key"]
                expected = entry["expected"]
                sport_buckets = buckets.get(sk, {})
                met = 0
                under = 0
                over = 0
                for ic, cnt in sport_buckets.items():
                    if ic == expected:
                        met += cnt
                    elif ic < expected:
                        under += cnt
                    else:
                        over += cnt
                entry["met"] = met
                entry["under"] = under
                entry["over"] = over
                entry["pct_met"] = round(met / max(entry["total_events"], 1) * 100, 1)

    except Exception as e:
        game_state_section = [{"error": str(e)}]

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


@router.post("/cleanup/crypto")
async def cleanup_crypto_futures(
    secret: str = Query(..., description="Admin secret for authorization"),
    batch_size: int = Query(5000, description="Rows to delete per batch"),
):
    """
    Dispatch a Celery background task to delete all crypto futures data.
    Returns immediately with a task ID — check Celery logs for progress.
    """
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.tasks import cleanup_crypto
    result = cleanup_crypto.delay(batch_size=batch_size)

    return {
        "status": "dispatched",
        "message": "Crypto cleanup task dispatched to Celery worker",
        "task_id": result.id,
    }


@router.post("/cleanup/turbo-collapse")
async def turbo_collapse(
    secret: str = Query(..., description="Admin secret for authorization"),
    limit: int = Query(5000, description="Max partitions to process per table"),
):
    """
    Run aggressive collapse on snapshot tables (same dedup logic, higher limit).

    Collapses consecutive identical values into single rows with reading_count.
    Prioritizes resolved futures markets. No data is lost — just deduplicated.
    """
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.tasks import turbo_collapse_futures, turbo_collapse_odds

    futures_task = turbo_collapse_futures.delay(limit=limit)
    odds_task = turbo_collapse_odds.delay(limit=limit)

    return {
        "status": "dispatched",
        "futures_task_id": futures_task.id,
        "odds_task_id": odds_task.id,
        "message": f"Turbo collapse dispatched (limit={limit} partitions per table). Check logs for progress.",
    }


@router.post("/cleanup/reclassify-events")
async def reclassify_misclassified_events(
    secret: str = Query(...),
    dry_run: bool = Query(True),
    db: AsyncSession = Depends(get_db),
):
    """Reclassify events whose sport_key doesn't match their Kalshi ticker.

    Finds events with pm_kalshi_ external_ids in wrong sport categories
    (e.g., tennis events in basketball_other) and moves them to the correct
    sport based on their ticker prefix.
    """
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.models.models import Sport
    from app.utils.sport_keys import KALSHI_TICKER_TO_SPORT_KEY

    # Find all events with pm_kalshi_ external_ids
    result = await db.execute(
        select(Event).join(Sport).where(
            Event.external_id.like("pm_kalshi_%"),
        )
    )
    events = result.scalars().all()

    reclassified = []
    sport_cache: dict[str, int] = {}

    for event in events:
        ext_id = event.external_id or ""
        ticker = ext_id.replace("pm_kalshi_", "").lower()
        # Find matching prefix
        correct_sport_key = None
        for prefix, sport_key in KALSHI_TICKER_TO_SPORT_KEY.items():
            if ticker.startswith(prefix):
                correct_sport_key = sport_key
                break

        if not correct_sport_key:
            continue

        # Get current sport key
        current_sport = await db.execute(
            select(Sport.key).where(Sport.id == event.sport_id)
        )
        current_key = current_sport.scalar_one_or_none()

        if current_key == correct_sport_key:
            continue  # Already correct

        # Get or create the correct sport
        if correct_sport_key not in sport_cache:
            sport_result = await db.execute(
                select(Sport).where(Sport.key == correct_sport_key)
            )
            sport = sport_result.scalar_one_or_none()
            if not sport:
                # Create the sport
                sport = Sport(
                    key=correct_sport_key,
                    name=correct_sport_key.replace("_", " ").title(),
                    group=correct_sport_key.split("_")[0],
                    active=True,
                )
                db.add(sport)
                await db.flush()
            sport_cache[correct_sport_key] = sport.id

        reclassified.append({
            "event_id": event.id,
            "teams": f"{event.away_team_name} @ {event.home_team_name}",
            "from": current_key,
            "to": correct_sport_key,
            "ticker": ext_id[:50],
        })

        if not dry_run:
            event.sport_id = sport_cache[correct_sport_key]

    if not dry_run:
        await db.commit()

    return {
        "dry_run": dry_run,
        "reclassified_count": len(reclassified),
        "reclassified": reclassified[:100],  # Cap output
        "message": f"{'Would reclassify' if dry_run else 'Reclassified'} {len(reclassified)} events. "
                   f"Set dry_run=false to apply.",
    }


@router.post("/cleanup/merge-duplicate-events")
async def merge_duplicate_events(
    secret: str = Query(...),
    dry_run: bool = Query(True),
    limit: int = Query(200, description="Max pm_ events to process per call"),
    sport: Optional[str] = Query(None, description="Filter to specific sport_id"),
    db: AsyncSession = Depends(get_db),
):
    """Find and merge duplicate events created by prediction market matching.

    When the quota guard blocked discover_events, Kalshi's auto-create made
    separate events with pm_ external_ids for games that later got real events
    from The Odds API or StatPal. This endpoint finds those duplicates and
    merges them: migrates any snapshots/futures links from the pm_ event to
    the real event, then deletes the pm_ event.
    """
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.models.models import OddsSnapshot, WinProbSnapshot, Sport
    from app.utils.name_normalization import names_match

    # Major sports only by default to avoid Heroku timeout
    major_sport_keys = [
        "basketball_nba", "americanfootball_nfl", "icehockey_nhl",
        "baseball_mlb", "basketball_ncaab", "basketball_wnba",
        "basketball_wncaab", "americanfootball_ncaaf",
    ]
    sport_keys = [sport] if sport else major_sport_keys

    # Resolve sport keys to IDs
    sport_id_result = await db.execute(
        select(Sport.id).where(Sport.key.in_(sport_keys))
    )
    sport_ids = [row[0] for row in sport_id_result.all()]

    # Find pm_ events, limited to avoid timeout
    pm_result = await db.execute(
        select(Event).where(
            Event.external_id.like("pm_%"),
            Event.sport_id.in_(sport_ids),
            Event.status.in_(["scheduled", "live", "completed", "closed"]),
        ).limit(limit)
    )
    pm_events = pm_result.scalars().all()

    merges = []
    no_match = []

    for pm_event in pm_events:
        # Search for a real event with the same teams on the same day
        time_start = pm_event.commence_time - timedelta(hours=24)
        time_end = pm_event.commence_time + timedelta(hours=24)

        candidates_result = await db.execute(
            select(Event).where(
                Event.id != pm_event.id,
                Event.sport_id == pm_event.sport_id,
                Event.commence_time.between(time_start, time_end),
                ~Event.external_id.like("pm_%"),  # Must be a "real" event
            )
        )
        candidates = candidates_result.scalars().all()

        best_match = None
        for candidate in candidates:
            # Check if teams match
            home_match = names_match(
                pm_event.home_team_name or "", candidate.home_team_name or ""
            ) or names_match(
                pm_event.home_team_name or "", candidate.away_team_name or ""
            )
            away_match = names_match(
                pm_event.away_team_name or "", candidate.away_team_name or ""
            ) or names_match(
                pm_event.away_team_name or "", candidate.home_team_name or ""
            )
            if home_match and away_match:
                best_match = candidate
                break

        if not best_match:
            no_match.append({
                "event_id": pm_event.id,
                "teams": f"{pm_event.away_team_name} @ {pm_event.home_team_name}",
                "ext_id": (pm_event.external_id or "")[:50],
                "time": pm_event.commence_time.isoformat()[:16] if pm_event.commence_time else "?",
            })
            continue

        merges.append({
            "pm_event_id": pm_event.id,
            "pm_teams": f"{pm_event.away_team_name} @ {pm_event.home_team_name}",
            "pm_ext_id": (pm_event.external_id or "")[:50],
            "real_event_id": best_match.id,
            "real_teams": f"{best_match.away_team_name} @ {best_match.home_team_name}",
            "real_ext_id": (best_match.external_id or "")[:50],
        })

        if not dry_run:
            eid = pm_event.id
            target = best_match.id
            # Migrate all event_id references to real event
            for tbl in ["odds_snapshots", "win_prob_snapshots", "score_snapshots",
                        "espn_snapshots", "scoring_plays", "odds_aggregated",
                        "line_movement_analyses", "futures_markets"]:
                await db.execute(text(
                    f"UPDATE {tbl} SET event_id = :target WHERE event_id = :eid"
                ).bindparams(target=target, eid=eid))
            # Delete the pm_ event
            await db.execute(text(
                "DELETE FROM events WHERE id = :eid"
            ).bindparams(eid=eid))

    if not dry_run:
        await db.commit()

    return {
        "dry_run": dry_run,
        "merged_count": len(merges),
        "no_match_count": len(no_match),
        "merges": merges[:100],
        "no_match_sample": no_match[:20],
        "message": f"{'Would merge' if dry_run else 'Merged'} {len(merges)} duplicate events. "
                   f"{len(no_match)} pm_ events had no matching real event.",
    }


@router.post("/cleanup/purge-orphan-pm-events")
async def purge_orphan_pm_events(
    secret: str = Query(...),
    dry_run: bool = Query(True),
    limit: int = Query(500, description="Max events to process per call"),
    sport: Optional[str] = Query(None, description="Filter to specific sport key"),
    db: AsyncSession = Depends(get_db),
):
    """Delete pm_ events that have no matching real event and no useful data.

    These are empty shell events auto-created by Kalshi matching when quota
    guard blocked discovery. They have no odds snapshots and just clutter
    the database.
    """
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.models.models import OddsSnapshot, WinProbSnapshot, Sport

    # Build sport filter
    sport_filter_q = select(Sport.id)
    if sport:
        sport_filter_q = sport_filter_q.where(Sport.key == sport)

    sport_ids_result = await db.execute(sport_filter_q)
    sport_ids = [row[0] for row in sport_ids_result.all()]

    # Find pm_ events with no odds snapshots
    pm_result = await db.execute(
        select(Event).where(
            Event.external_id.like("pm_%"),
            Event.sport_id.in_(sport_ids),
        ).limit(limit)
    )
    pm_events = pm_result.scalars().all()

    to_delete = []
    has_data = []

    for pm_event in pm_events:
        # Check if this event has any snapshots worth keeping
        snap_count = await db.execute(
            select(func.count()).where(OddsSnapshot.event_id == pm_event.id)
        )
        odds_count = snap_count.scalar() or 0

        wp_count = await db.execute(
            select(func.count()).where(WinProbSnapshot.event_id == pm_event.id)
        )
        win_prob_count = wp_count.scalar() or 0

        if odds_count == 0 and win_prob_count == 0:
            to_delete.append({
                "event_id": pm_event.id,
                "teams": f"{pm_event.away_team_name} @ {pm_event.home_team_name}",
                "ext_id": (pm_event.external_id or "")[:50],
                "sport_id": pm_event.sport_id,
                "status": pm_event.status,
            })
            if not dry_run:
                eid = pm_event.id
                # Clear all FK references before deleting
                for tbl in ["scoring_plays", "odds_snapshots", "odds_aggregated",
                            "score_snapshots", "espn_snapshots", "win_prob_snapshots",
                            "line_movement_analyses"]:
                    await db.execute(text(
                        f"DELETE FROM {tbl} WHERE event_id = :eid"
                    ).bindparams(eid=eid))
                # futures chain: odds → outcomes → markets
                await db.execute(text("""
                    DELETE FROM futures_odds_snapshots WHERE outcome_id IN (
                        SELECT fo.id FROM futures_outcomes fo
                        JOIN futures_markets fm ON fo.market_id = fm.id
                        WHERE fm.event_id = :eid
                    )
                """).bindparams(eid=eid))
                await db.execute(text("""
                    DELETE FROM futures_outcomes WHERE market_id IN (
                        SELECT id FROM futures_markets WHERE event_id = :eid
                    )
                """).bindparams(eid=eid))
                await db.execute(text(
                    "DELETE FROM futures_markets WHERE event_id = :eid"
                ).bindparams(eid=eid))
                # Now delete the event itself
                await db.execute(text(
                    "DELETE FROM events WHERE id = :eid"
                ).bindparams(eid=eid))
        else:
            has_data.append({
                "event_id": pm_event.id,
                "teams": f"{pm_event.away_team_name} @ {pm_event.home_team_name}",
                "odds_snapshots": odds_count,
                "win_prob_snapshots": win_prob_count,
            })

    if not dry_run:
        await db.commit()

    return {
        "dry_run": dry_run,
        "deleted_count": len(to_delete),
        "kept_with_data": len(has_data),
        "deleted_sample": to_delete[:30],
        "kept_sample": has_data[:10],
        "message": f"{'Would delete' if dry_run else 'Deleted'} {len(to_delete)} orphan pm_ events. "
                   f"{len(has_data)} pm_ events have snapshot data and were kept.",
    }


# ── DB Storage Analysis & Cleanup ─────────────────────────────────────


@router.get("/db/storage-analysis")
async def db_storage_analysis(
    secret: str = Query("", description="Admin secret"),
    detail: str = Query("sizes", description="What to analyze: sizes, age, status, orphans, all"),
    db: AsyncSession = Depends(get_db),
):
    """
    Analyze DB storage. Split into sections to avoid Heroku 30s timeout.
    Use detail=sizes (fast), detail=age, detail=status, detail=orphans,
    or detail=all (slow, may timeout).
    """
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    results = {}

    if detail in ("sizes", "all"):
        row = (await db.execute(text(
            "SELECT pg_size_pretty(pg_total_relation_size('futures_odds_snapshots')),"
            " pg_size_pretty(pg_total_relation_size('odds_snapshots')),"
            " pg_size_pretty(pg_total_relation_size('win_prob_snapshots')),"
            " pg_size_pretty(pg_database_size(current_database())),"
            " pg_total_relation_size('futures_odds_snapshots'),"
            " pg_database_size(current_database())"
        ))).fetchone()
        results["sizes"] = {
            "futures_odds_snapshots": row[0],
            "odds_snapshots": row[1],
            "win_prob_snapshots": row[2],
            "database_total": row[3],
            "futures_odds_snapshots_bytes": row[4],
            "database_total_bytes": row[5],
            "futures_pct_of_db": round(row[4] / max(row[5], 1) * 100, 1),
        }

        # Use pg_stat estimates for row counts (instant, no seq scan)
        row_estimates = (await db.execute(text(
            "SELECT relname, n_live_tup, n_dead_tup"
            " FROM pg_stat_user_tables"
            " WHERE relname IN ('futures_odds_snapshots', 'odds_snapshots', 'win_prob_snapshots')"
            " ORDER BY n_live_tup DESC"
        ))).fetchall()
        results["row_estimates"] = [
            {"table": r[0], "live_rows": r[1], "dead_rows": r[2]}
            for r in row_estimates
        ]

        # Resolved vs active market counts (fast — small table)
        market_status = (await db.execute(text(
            "SELECT status, COUNT(*) FROM futures_markets GROUP BY 1"
        ))).fetchall()
        results["market_status"] = [
            {"status": r[0], "count": r[1]} for r in market_status
        ]

        # Resolved outcome IDs count (for estimating snapshot impact)
        resolved_outcomes = (await db.execute(text(
            "SELECT COUNT(*) FROM futures_outcomes fo"
            " JOIN futures_markets fm ON fo.market_id = fm.id"
            " WHERE fm.status = 'resolved'"
        ))).scalar()
        total_outcomes = (await db.execute(text(
            "SELECT COUNT(*) FROM futures_outcomes"
        ))).scalar()
        results["outcomes"] = {
            "total": total_outcomes,
            "resolved": resolved_outcomes,
            "active": total_outcomes - resolved_outcomes,
        }

    if detail in ("age", "all"):
        # Use MIN/MAX instead of GROUP BY for speed
        age_bounds = (await db.execute(text(
            "SELECT MIN(captured_at), MAX(captured_at),"
            " COUNT(*) FROM futures_odds_snapshots"
        ))).fetchone()
        results["futures_snapshots"] = {
            "oldest": str(age_bounds[0]) if age_bounds[0] else None,
            "newest": str(age_bounds[1]) if age_bounds[1] else None,
            "total_rows": age_bounds[2],
        }

        # Monthly breakdown using date_trunc (can use index)
        monthly = (await db.execute(text(
            "SELECT date_trunc('month', captured_at)::date as month, COUNT(*)"
            " FROM futures_odds_snapshots"
            " GROUP BY 1 ORDER BY 1"
        ))).fetchall()
        results["futures_by_month"] = [
            {"month": str(r[0]), "rows": r[1],
             "est_mb": round(r[1] * 144 / 1024 / 1024)}
            for r in monthly
        ]

    if detail in ("status", "all"):
        # Snapshot count by market status using outcome_id IN (resolved outcome IDs)
        # This avoids a 3-way JOIN on the huge table
        resolved_snap_count = (await db.execute(text(
            "SELECT COUNT(*) FROM futures_odds_snapshots"
            " WHERE outcome_id IN ("
            "   SELECT fo.id FROM futures_outcomes fo"
            "   JOIN futures_markets fm ON fo.market_id = fm.id"
            "   WHERE fm.status = 'resolved'"
            ")"
        ))).scalar()
        total_snaps = (await db.execute(text(
            "SELECT COUNT(*) FROM futures_odds_snapshots"
        ))).scalar()
        results["snapshots_by_market_status"] = {
            "resolved": resolved_snap_count,
            "active": total_snaps - resolved_snap_count,
            "total": total_snaps,
            "resolved_est_mb": round(resolved_snap_count * 144 / 1024 / 1024),
            "active_est_mb": round((total_snaps - resolved_snap_count) * 144 / 1024 / 1024),
        }

    if detail in ("space_map",):
        # Exact breakdown of live, dead, and free space in the table file.
        # Uses pgstattuple extension if available, falls back to estimates.
        # Check available extensions
        avail_ext = (await db.execute(text(
            "SELECT name FROM pg_available_extensions"
            " WHERE name IN ('pgstattuple', 'pg_repack', 'pg_squeeze')"
        ))).fetchall()
        results["available_extensions"] = [r[0] for r in avail_ext]

        # Enable pgstattuple if available
        pgstattuple_available = False
        try:
            await db.execute(text("CREATE EXTENSION IF NOT EXISTS pgstattuple"))
            await db.commit()
            # Verify it works
            await db.execute(text("SELECT pgstattuple('pg_class')"))
            pgstattuple_available = True
        except Exception as e:
            results["pgstattuple_error"] = str(e)
            await db.rollback()

        for tbl_name in ["futures_odds_snapshots", "odds_snapshots"]:
            key = tbl_name.replace("_snapshots", "") + "_space_map"
            if pgstattuple_available:
                try:
                    st = (await db.execute(text(
                        f"SELECT * FROM pgstattuple('{tbl_name}')"
                    ))).fetchone()
                    results[key] = {
                        "table_len_mb": round(st[0] / 1024 / 1024),
                        "live_tuple_count": st[1],
                        "live_tuple_mb": round(st[2] / 1024 / 1024),
                        "live_pct": st[3],
                        "dead_tuple_count": st[4],
                        "dead_tuple_mb": round(st[5] / 1024 / 1024),
                        "dead_pct": st[6],
                        "free_space_mb": round(st[7] / 1024 / 1024),
                        "free_pct": st[8],
                    }
                except Exception:
                    await db.rollback()

            if key not in results:
                # Fallback: heap/index sizes + pg_stat estimates
                sizes = (await db.execute(text(
                    f"SELECT pg_relation_size('{tbl_name}'),"
                    f" pg_indexes_size('{tbl_name}'),"
                    f" pg_total_relation_size('{tbl_name}')"
                ))).fetchone()
                stats = (await db.execute(text(
                    "SELECT n_live_tup, n_dead_tup"
                    " FROM pg_stat_user_tables"
                    f" WHERE relname = '{tbl_name}'"
                ))).fetchone()
                results[key] = {
                    "heap_mb": round(sizes[0] / 1024 / 1024),
                    "indexes_mb": round(sizes[1] / 1024 / 1024),
                    "total_mb": round(sizes[2] / 1024 / 1024),
                    "live_tuples_est": stats[0] if stats else None,
                    "dead_tuples_pending": stats[1] if stats else None,
                    "note": "pgstattuple not available. dead_tuples_pending shows only rows "
                            "waiting for next autovacuum — NOT total reusable space. "
                            "Free space (from past autovacuum runs) is invisible without pgstattuple.",
                }

    if detail in ("orphans", "all", "categories"):
        orphan_count = (await db.execute(text(
            "SELECT COUNT(*) FROM futures_odds_snapshots"
            " WHERE outcome_id NOT IN (SELECT id FROM futures_outcomes)"
        ))).scalar()
        results["orphan_snapshots"] = orphan_count

    if detail in ("categories",):
        # Check for remaining crypto or other category data
        cats = (await db.execute(text(
            "SELECT COALESCE(llm_sport_category, 'NULL') as cat,"
            " COUNT(*) as markets,"
            " SUM(CASE WHEN status = 'resolved' THEN 1 ELSE 0 END) as resolved"
            " FROM futures_markets GROUP BY 1 ORDER BY 2 DESC"
        ))).fetchall()
        results["market_categories"] = [
            {"category": r[0], "markets": r[1], "resolved": r[2]}
            for r in cats
        ]

        # Count snapshots for crypto outcomes specifically
        crypto_snaps = (await db.execute(text(
            "SELECT COUNT(*) FROM futures_odds_snapshots"
            " WHERE outcome_id IN ("
            "   SELECT fo.id FROM futures_outcomes fo"
            "   JOIN futures_markets fm ON fo.market_id = fm.id"
            "   WHERE fm.llm_sport_category = 'crypto'"
            ")"
        ))).scalar()
        results["crypto_snapshots_remaining"] = crypto_snaps

    if detail in ("indexes",):
        # Per-table breakdown: heap vs indexes, plus individual index sizes
        table_sizes = (await db.execute(text("""
            SELECT
                relname AS table,
                pg_size_pretty(pg_relation_size(c.oid)) AS heap,
                pg_size_pretty(pg_indexes_size(c.oid)) AS indexes,
                pg_size_pretty(pg_total_relation_size(c.oid)) AS total,
                pg_relation_size(c.oid) AS heap_bytes,
                pg_indexes_size(c.oid) AS idx_bytes,
                pg_total_relation_size(c.oid) AS total_bytes
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public' AND c.relkind = 'r'
            ORDER BY pg_total_relation_size(c.oid) DESC
            LIMIT 15
        """))).fetchall()
        results["table_sizes"] = [
            {
                "table": r[0], "heap": r[1], "indexes": r[2], "total": r[3],
                "index_pct": round(r[5] / max(r[6], 1) * 100, 1),
            }
            for r in table_sizes
        ]

        # Individual index sizes for the big 3 tables
        idx_details = (await db.execute(text("""
            SELECT
                tablename,
                indexname,
                pg_size_pretty(pg_relation_size(indexname::regclass)) AS size,
                pg_relation_size(indexname::regclass) AS size_bytes
            FROM pg_indexes
            WHERE schemaname = 'public'
              AND tablename IN ('futures_odds_snapshots', 'odds_snapshots', 'win_prob_snapshots')
            ORDER BY pg_relation_size(indexname::regclass) DESC
        """))).fetchall()
        results["index_details"] = [
            {"table": r[0], "index": r[1], "size": r[2], "size_bytes": r[3]}
            for r in idx_details
        ]

        # Duplicate index detection: show full CREATE INDEX statement for each
        dup_check = (await db.execute(text("""
            SELECT indexname, indexdef
            FROM pg_indexes
            WHERE schemaname = 'public'
              AND tablename IN ('futures_odds_snapshots', 'odds_snapshots', 'win_prob_snapshots')
            ORDER BY tablename, indexname
        """))).fetchall()
        results["index_definitions"] = [
            {"name": r[0], "definition": r[1]} for r in dup_check
        ]

        # Summary
        total_idx = sum(r[5] for r in table_sizes)
        total_heap = sum(r[4] for r in table_sizes)
        results["index_summary"] = {
            "total_index_mb": round(total_idx / 1024 / 1024),
            "total_heap_mb": round(total_heap / 1024 / 1024),
            "index_to_heap_ratio": round(total_idx / max(total_heap, 1), 2),
        }

    if detail in ("collapse_estimate",):
        # Sample a few resolved outcomes and measure collapse ratio using
        # window functions (same approach as retention.py).
        # Pick 50 outcomes to keep it fast.
        sample_ids = (await db.execute(text("""
            SELECT fo.id FROM futures_outcomes fo
            JOIN futures_markets fm ON fo.market_id = fm.id
            WHERE fm.status = 'resolved'
            LIMIT 50
        """))).fetchall()
        sample_outcome_ids = [r[0] for r in sample_ids]

        if sample_outcome_ids:
            # Count total rows for these outcomes
            total_rows = (await db.execute(text(
                "SELECT COUNT(*) FROM futures_odds_snapshots"
                " WHERE outcome_id = ANY(:ids)"
            ), {"ids": sample_outcome_ids})).scalar()

            # Count rows that are duplicates of their predecessor
            # (same outcome_id, bookmaker, probability as the previous row)
            dup_count = (await db.execute(text("""
                WITH ordered AS (
                    SELECT id, outcome_id, bookmaker, probability,
                           LAG(probability) OVER (
                               PARTITION BY outcome_id, bookmaker
                               ORDER BY captured_at, id
                           ) AS prev_prob
                    FROM futures_odds_snapshots
                    WHERE outcome_id = ANY(:ids)
                )
                SELECT COUNT(*) FROM ordered
                WHERE probability IS NOT DISTINCT FROM prev_prob
                  AND prev_prob IS NOT NULL
            """), {"ids": sample_outcome_ids})).scalar()

            ratio = dup_count / max(total_rows, 1)
            # Get total resolved snapshots for extrapolation
            total_resolved = (await db.execute(text(
                "SELECT COUNT(*) FROM futures_odds_snapshots"
                " WHERE outcome_id IN ("
                "   SELECT fo.id FROM futures_outcomes fo"
                "   JOIN futures_markets fm ON fo.market_id = fm.id"
                "   WHERE fm.status = 'resolved'"
                ")"
            ))).scalar()

            results["collapse_estimate"] = {
                "sampled_outcomes": len(sample_outcome_ids),
                "sample_total_rows": total_rows,
                "sample_duplicate_rows": dup_count,
                "sample_unique_rows": total_rows - dup_count,
                "dedup_ratio": round(ratio, 3),
                "total_resolved_snapshots": total_resolved,
                "extrapolated_deletable": round(total_resolved * ratio),
                "extrapolated_mb_freed": round(total_resolved * ratio * 144 / 1024 / 1024),
            }

    return results


@router.post("/db/collapse-resolved-futures")
async def collapse_resolved_futures(
    secret: str = Query("", description="Admin secret"),
    limit: int = Query(10000, description="Number of outcomes to process"),
):
    """
    Queue an aggressive collapse of resolved futures snapshots as a Celery task.
    Uses the same dedup logic as the existing retention system but with a much
    higher outcome limit. Returns immediately with a task ID.
    """
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.tasks import turbo_collapse_futures
    task = turbo_collapse_futures.delay(limit=limit)
    return {
        "queued": True,
        "task_id": str(task.id),
        "limit": limit,
        "message": f"Collapse task queued with limit={limit}. "
                   f"Check worker logs for progress.",
    }


@router.post("/db/delete-orphan-futures-snapshots")
async def delete_orphan_futures_snapshots(
    secret: str = Query("", description="Admin secret"),
    batch_size: int = Query(50000, description="Delete in batches"),
    dry_run: bool = Query(True, description="Preview without deleting"),
    db: AsyncSession = Depends(get_db),
):
    """Delete futures_odds_snapshots with no matching outcome."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    if dry_run:
        count_result = (await db.execute(text(
            "SELECT COUNT(*) FROM futures_odds_snapshots"
            " WHERE outcome_id NOT IN (SELECT id FROM futures_outcomes)"
        ))).scalar()
        return {
            "dry_run": True,
            "would_delete": count_result,
            "est_mb_freed": round(count_result * 144 / 1024 / 1024),
        }

    result = await db.execute(text(
        "DELETE FROM futures_odds_snapshots"
        " WHERE id IN ("
        "   SELECT id FROM futures_odds_snapshots"
        "   WHERE outcome_id NOT IN (SELECT id FROM futures_outcomes)"
        "   LIMIT :batch"
        ")"
    ).bindparams(batch=batch_size))
    deleted = result.rowcount
    await db.commit()

    return {
        "dry_run": False,
        "deleted_this_batch": deleted,
        "done": deleted < batch_size,
    }


@router.post("/db/vacuum")
async def vacuum_table(
    secret: str = Query("", description="Admin secret"),
    table: str = Query("futures_odds_snapshots", description="Table to vacuum"),
    full: bool = Query(False, description="VACUUM FULL (rewrites table, reclaims disk)"),
    db: AsyncSession = Depends(get_db),
):
    """
    Run VACUUM on a table. VACUUM (regular) marks dead tuples as reusable.
    VACUUM FULL rewrites the table to reclaim disk space but locks the table.
    Requires sufficient free disk space (~equal to table size) for FULL.
    """
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    # Allowlist tables
    allowed = {"futures_odds_snapshots", "odds_snapshots", "win_prob_snapshots",
               "odds_aggregated", "score_snapshots", "espn_snapshots"}
    if table not in allowed:
        raise HTTPException(status_code=400, detail=f"Table must be one of: {allowed}")

    # Get table size before
    size_before = (await db.execute(text(
        f"SELECT pg_size_pretty(pg_total_relation_size('{table}')),"
        f" pg_total_relation_size('{table}')"
    ))).fetchone()

    # VACUUM requires running outside a transaction — use raw asyncpg connection
    import asyncpg
    from app.services.database import DATABASE_URL

    dsn = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
    raw = await asyncpg.connect(dsn)
    try:
        cmd = f"VACUUM FULL {table}" if full else f"VACUUM {table}"
        await raw.execute(cmd)
    finally:
        await raw.close()

    # Get table size after
    size_after = (await db.execute(text(
        f"SELECT pg_size_pretty(pg_total_relation_size('{table}')),"
        f" pg_total_relation_size('{table}')"
    ))).fetchone()

    return {
        "table": table,
        "vacuum_type": "FULL" if full else "regular",
        "size_before": size_before[0],
        "size_after": size_after[0],
        "bytes_freed": size_before[1] - size_after[1],
        "freed_pretty": f"{(size_before[1] - size_after[1]) / 1024 / 1024:.1f} MB",
    }


@router.post("/db/drop-duplicate-index")
async def drop_duplicate_index(
    secret: str = Query("", description="Admin secret"),
    index_name: str = Query(..., description="Index name to drop"),
    db: AsyncSession = Depends(get_db),
):
    """Drop a duplicate index by name. Only allows dropping known-safe duplicates."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    # Verify it exists and get its definition
    idx_info = (await db.execute(text(
        "SELECT tablename, indexdef FROM pg_indexes"
        " WHERE schemaname = 'public' AND indexname = :name"
    ), {"name": index_name})).fetchone()
    if not idx_info:
        raise HTTPException(status_code=404, detail=f"Index '{index_name}' not found")

    # Check for another index on the same table with the same column definition
    # (i.e., confirm it's actually a duplicate before dropping)
    all_indexes = (await db.execute(text(
        "SELECT indexname, indexdef FROM pg_indexes"
        " WHERE schemaname = 'public' AND tablename = :tbl AND indexname != :name"
    ), {"tbl": idx_info[0], "name": index_name})).fetchall()

    # Extract column list from indexdef (everything after USING btree/hash/etc)
    import re
    def extract_cols(indexdef):
        m = re.search(r'USING \w+ \((.+)\)$', indexdef)
        return m.group(1).strip() if m else None

    target_cols = extract_cols(idx_info[1])
    duplicates = [r[0] for r in all_indexes if extract_cols(r[1]) == target_cols]

    if not duplicates:
        raise HTTPException(
            status_code=400,
            detail=f"No duplicate found for '{index_name}' — refusing to drop a unique index"
        )

    # Get size before dropping — cast to regclass via explicit syntax
    idx_size = (await db.execute(text(
        "SELECT pg_size_pretty(pg_relation_size(quote_ident(:name))),"
        " pg_relation_size(quote_ident(:name))",
    ), {"name": index_name})).fetchone()

    # Use safe identifier quoting
    await db.execute(text(f'DROP INDEX "{index_name}"'))
    await db.commit()

    return {
        "dropped": index_name,
        "size_freed": idx_size[0],
        "bytes_freed": idx_size[1],
        "kept_duplicate": duplicates[0],
        "table": idx_info[0],
    }


# =========================================================================
# Data Quality Monitoring
# =========================================================================

@router.get("/data-quality")
async def get_data_quality_report(
    secret: str = Query(...),
):
    """Get the latest data quality report (classification + matching health).

    Report is generated daily by the check_data_quality task and cached in Redis.
    Trigger a fresh check with POST /api/admin/data-quality/check.
    """
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    import json as _json
    from app.tasks.redis_state import get_redis_client

    try:
        r = get_redis_client()
        raw = r.get("bainluck:data_quality:latest")
        if raw:
            return _json.loads(raw)
        return {"status": "no_data", "message": "No data quality report yet. Run POST /api/admin/data-quality/check to generate one."}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/data-quality/check")
async def trigger_data_quality_check(
    secret: str = Query(...),
):
    """Trigger an immediate data quality check (runs inline, not queued)."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.tasks.data_quality import _check_data_quality

    report = await _check_data_quality()
    return report


@router.get("/audit")
async def run_audit(
    secret: str = Query(...),
    grid: str = Query("mlb", description="Grid to audit: nba, nhl, mlb, golf"),
    skip_event: bool = Query(False, description="Skip event detail audit"),
    skip_grid: bool = Query(False, description="Skip grid audit"),
):
    """Run the page health audit and return JSON results.

    Executes the audit_matching_quality.py script with --json --skip-llm
    and returns the structured report for dashboard display.
    """
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    import asyncio
    import json as json_mod

    cmd = [
        sys.executable, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "scripts", "audit_matching_quality.py"),
        "--json", "--skip-llm", "--grid", grid,
    ]
    if skip_event:
        cmd.append("--skip-event")
    if skip_grid:
        cmd.append("--skip-grid")

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**os.environ, "PYTHONPATH": "."},
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)

        if proc.returncode != 0:
            return {
                "status": "error",
                "returncode": proc.returncode,
                "stderr": stderr.decode()[-500:],
            }

        # Script prints debug lines before JSON — extract the JSON block
        output = stdout.decode()
        json_start = output.find("{")
        if json_start == -1:
            return {"status": "error", "error": "No JSON in output", "raw": output[-500:]}
        return json_mod.loads(output[json_start:])

    except asyncio.TimeoutError:
        return {"status": "error", "error": "Audit timed out after 60s"}
    except Exception as exc:
        return {"status": "error", "error": str(exc)[:500]}


@router.get("/audit/all")
async def run_audit_all_grids(
    secret: str = Query(...),
):
    """Run audit across all grids and return combined results."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    import asyncio
    import json as json_mod

    grids = ["nba", "nhl", "mlb", "golf"]
    results = {}

    for grid in grids:
        cmd = [
            sys.executable, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "scripts", "audit_matching_quality.py"),
            "--json", "--skip-llm", "--skip-event", "--grid", grid,
        ]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env={**os.environ, "PYTHONPATH": "."},
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)

            if proc.returncode == 0:
                output = stdout.decode()
                json_start = output.find("{")
                if json_start >= 0:
                    results[grid] = json_mod.loads(output[json_start:])
                else:
                    results[grid] = {"status": "error", "error": "No JSON"}
            else:
                results[grid] = {"status": "error", "stderr": stderr.decode()[-200:]}
        except Exception as exc:
            results[grid] = {"status": "error", "error": str(exc)[:200]}

    # Summary row
    scores = {
        g: r.get("health_score", "?")
        for g, r in results.items()
        if isinstance(r.get("health_score"), int)
    }

    return {
        "scores": scores,
        "avg_score": round(sum(scores.values()) / len(scores)) if scores else None,
        "grids": results,
    }


@router.get("/debug/golf-markets")
async def debug_golf_markets(
    secret: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """List all golf markets from Kalshi/Polymarket/Odds API in the DB.

    Shows market names, sources, outcome counts, and probabilities
    to diagnose tournament matching issues in the golf grid.
    """
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    stmt = (
        select(FuturesMarket)
        .where(
            or_(
                FuturesMarket.llm_sport_category == "golf",
                FuturesMarket.external_id.ilike("golf_%"),
            ),
            FuturesMarket.status != "resolved",
            FuturesMarket.source != "datagolf",
        )
        .options(selectinload(FuturesMarket.outcomes))
        .order_by(FuturesMarket.source, FuturesMarket.name)
    )
    result = await db.execute(stmt)
    markets = result.scalars().unique().all()

    market_list = []
    for m in markets:
        outcomes = sorted(
            m.outcomes,
            key=lambda o: float(o.current_probability or 0),
            reverse=True,
        )
        top_outcomes = [
            {
                "name": o.name,
                "probability": float(o.current_probability) if o.current_probability else None,
                "yes_bid": float(o.current_yes_bid) if o.current_yes_bid else None,
                "yes_ask": float(o.current_yes_ask) if o.current_yes_ask else None,
            }
            for o in outcomes[:5]
        ]
        prob_sum = sum(
            float(o.current_probability)
            for o in outcomes
            if o.current_probability
        )
        market_list.append({
            "id": m.id,
            "source": m.source,
            "name": m.name,
            "external_id": m.external_id[:80] if m.external_id else None,
            "category": m.category,
            "market_tier": m.market_tier,
            "mutually_exclusive": m.mutually_exclusive,
            "outcome_count": len(outcomes),
            "prob_sum": round(prob_sum, 3),
            "top_outcomes": top_outcomes,
        })

    return {
        "total_markets": len(market_list),
        "by_source": {
            src: sum(1 for m in market_list if m["source"] == src)
            for src in sorted(set(m["source"] for m in market_list))
        },
        "markets": market_list,
    }


@router.post("/events/backfill-completed-at")
async def backfill_completed_at(
    secret: str = Query(...),
    limit: int = Query(5000),
    db: AsyncSession = Depends(get_db),
):
    """Backfill completed_at for historical events using authoritative sources.

    Priority: statpal_end_time > last ESPN snapshot > last stat_model snapshot.
    """
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.models.models import Event, ESPNSnapshot, WinProbSnapshot

    result = await db.execute(
        select(Event)
        .where(
            Event.status.in_(["completed", "closed"]),
            Event.completed_at.is_(None),
        )
        .order_by(Event.commence_time.desc())
        .limit(limit)
    )
    events = result.scalars().all()

    stats = {"total": len(events), "from_statpal": 0, "from_espn": 0, "from_stat_model": 0, "unfilled": 0}

    for event in events:
        completed_at = None

        # Priority 1: statpal_end_time (definitive)
        if event.statpal_end_time:
            completed_at = event.statpal_end_time
            stats["from_statpal"] += 1

        # Priority 2: last ESPN snapshot
        if not completed_at:
            espn_result = await db.execute(
                select(ESPNSnapshot.captured_at)
                .where(ESPNSnapshot.event_id == event.id)
                .order_by(ESPNSnapshot.captured_at.desc())
                .limit(1)
            )
            last_espn = espn_result.scalar_one_or_none()
            if last_espn:
                completed_at = last_espn
                stats["from_espn"] += 1

        # Priority 3: last stat_model win_prob_snapshot
        if not completed_at:
            wp_result = await db.execute(
                select(WinProbSnapshot.captured_at)
                .where(
                    WinProbSnapshot.event_id == event.id,
                    WinProbSnapshot.source == "stat_model",
                )
                .order_by(WinProbSnapshot.captured_at.desc())
                .limit(1)
            )
            last_sm = wp_result.scalar_one_or_none()
            if last_sm:
                completed_at = last_sm
                stats["from_stat_model"] += 1

        if completed_at:
            await db.execute(
                Event.__table__.update()
                .where(Event.id == event.id)
                .values(completed_at=completed_at)
            )
        else:
            stats["unfilled"] += 1

    await db.commit()
    return stats


# =============================================================================
# Bug Report Inbox (Rage Shake)
# =============================================================================

ADMIN_USER_IDS = {364}

async def _check_admin_auth(secret: str | None, request: Request, db=None) -> bool:
    if secret and _check_admin_secret(secret):
        return True
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        try:
            from app.services.firebase_auth import verify_id_token
            claims = verify_id_token(token)
            if claims:
                firebase_uid = claims.get("uid") or claims.get("sub")
                if firebase_uid and db:
                    from app.models.models import User
                    result = await db.execute(
                        select(User).where(User.firebase_uid == firebase_uid)
                    )
                    user = result.scalar_one_or_none()
                    if user and user.id in ADMIN_USER_IDS:
                        return True
        except Exception:
            pass
    return False

@router.get("/bug-reports")
async def list_bug_reports(
    request: Request,
    secret: str = Query(None),
    status: str = Query(None),
    limit: int = Query(50),
    db: AsyncSession = Depends(get_db),
):
    if not await _check_admin_auth(secret, request, db):
        raise HTTPException(status_code=403, detail="Unauthorized")

    query = select(BugReport).order_by(BugReport.created_at.desc()).limit(limit)
    if status:
        query = query.where(BugReport.status == status)

    result = await db.execute(query)
    reports = result.scalars().all()

    return {
        "reports": [
            {
                "id": r.id,
                "user_id": r.user_id,
                "session_id": r.session_id,
                "description": r.description,
                "has_screenshot": r.screenshot_base64 is not None,
                "app_state": r.app_state,
                "status": r.status,
                "admin_notes": r.admin_notes,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in reports
        ],
        "count": len(reports),
    }


@router.patch("/bug-reports/{report_id}")
async def update_bug_report(
    report_id: int,
    request: Request,
    secret: str = Query(None),
    status: str = Query(None),
    admin_notes: str = Query(None),
    resolution_summary: str = Query(None),
    backlog_ref: str = Query(None),
    db: AsyncSession = Depends(get_db),
):
    if not await _check_admin_auth(secret, request, db):
        raise HTTPException(status_code=403, detail="Unauthorized")

    _VALID_STATUSES = {"new", "reviewed", "in_progress", "fixed", "wont_fix", "duplicate", "actioned", "dismissed"}
    values = {}
    if status:
        if status not in _VALID_STATUSES:
            raise HTTPException(400, f"Invalid status. Must be one of: {sorted(_VALID_STATUSES)}")
        values["status"] = status
    if admin_notes is not None:
        if len(admin_notes) > 5000:
            raise HTTPException(400, "Admin notes too long (max 5000 chars)")
        values["admin_notes"] = admin_notes
    if resolution_summary is not None:
        values["resolution_summary"] = resolution_summary
    if backlog_ref is not None:
        values["backlog_ref"] = backlog_ref

    if values:
        result = await db.execute(
            update(BugReport).where(BugReport.id == report_id).values(**values)
        )
        if result.rowcount == 0:
            raise HTTPException(404, f"Bug report {report_id} not found")
        await db.commit()

        if status == "fixed" and resolution_summary:
            try:
                from app.tasks.bug_notifications import send_bug_fixed_email
                await send_bug_fixed_email(report_id, db)
            except Exception as e:
                logger.warning("Bug fix email failed for report %d: %s", report_id, e)

    return {"status": "ok"}


@router.get("/bug-reports/{report_id}/screenshot")
async def get_bug_screenshot(
    report_id: int,
    request: Request,
    secret: str = Query(None),
    db: AsyncSession = Depends(get_db),
):
    if not await _check_admin_auth(secret, request, db):
        raise HTTPException(status_code=403, detail="Unauthorized")

    result = await db.execute(
        select(BugReport.screenshot_base64).where(BugReport.id == report_id)
    )
    b64 = result.scalar_one_or_none()
    if not b64:
        raise HTTPException(status_code=404, detail="No screenshot")

    import base64
    from fastapi.responses import Response
    try:
        image_data = base64.b64decode(b64)
    except Exception:
        raise HTTPException(400, "Invalid screenshot data")
    media_type = "image/png" if image_data[:4] == b"\x89PNG" else "image/jpeg"
    return Response(content=image_data, media_type=media_type)


@router.get("/calibration-data")
async def calibration_data(
    secret: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Return pre-aggregated calibration buckets for resolved prediction markets."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    # Calibration methodology (auditable, no ad-hoc exclusions):
    #
    # Step 1: Reconstruct "virtual markets" from the physical market structure.
    #   - A Kalshi championship market with 20 outcomes = 1 virtual market (20 outcomes)
    #   - A Polymarket "Who wins?" event with 10 binary sub-markets sharing a
    #     group_id = 1 virtual market (10 outcomes). This is structurally identical
    #     to a championship market but stored differently.
    #   - A Kalshi binary game market (1 outcome) = 1 virtual market (1 outcome)
    #   - A Kalshi threshold market (10 outcomes, non-ME) = 1 virtual market
    #     but only the most informative outcome (closest to 50%) is used
    #
    # Step 2: Clean resolution filter — only include virtual markets where 80%+
    #   of outcomes resolved to near-0 or near-1.
    #
    # Step 3: For large virtual markets (20+ outcomes), filter inverted Kalshi
    #   field prices (opening_probability > 0.90 that should be 1 - opening).
    sql = text("""
        WITH market_info AS (
            SELECT fm.id AS market_id, fm.source, fm.event_id, fm.group_id,
                fm.commence_time,
                COALESCE(fm.llm_sport_category, 'uncategorized') AS category,
                fm.mutually_exclusive
            FROM futures_markets fm
            WHERE fm.status = 'resolved'
        ),
        group_sizes AS (
            SELECT group_id, source, COUNT(*) AS group_size
            FROM market_info
            WHERE group_id IS NOT NULL
            GROUP BY group_id, source
        ),
        event_sizes AS (
            SELECT event_id, source, COUNT(*) AS event_size
            FROM market_info
            WHERE event_id IS NOT NULL
            GROUP BY event_id, source
        ),
        virtual_market AS (
            SELECT
                mi.market_id, mi.source, mi.category, mi.event_id,
                CASE WHEN gs.group_size >= 3
                     THEN 'g:' || mi.group_id
                     WHEN es.event_size >= 3
                     THEN 'e:' || mi.event_id::text
                     ELSE 'm:' || mi.market_id::text
                END AS vm_id,
                COALESCE(gs.group_size >= 3, false)
                  OR COALESCE(es.event_size >= 3, false) AS is_grouped,
                mi.mutually_exclusive
            FROM market_info mi
            LEFT JOIN group_sizes gs
              ON gs.group_id = mi.group_id AND gs.source = mi.source
            LEFT JOIN event_sizes es
              ON es.event_id = mi.event_id AND es.source = mi.source
        ),
        -- Compute resolution quality per virtual market
        vm_stats AS (
            SELECT
                vm.vm_id, vm.source, vm.category, vm.is_grouped,
                vm.mutually_exclusive,
                COUNT(DISTINCT vm.market_id) AS market_count,
                COUNT(*) AS total_outcomes,
                COUNT(*) FILTER (WHERE fo.current_probability >= 0.95) AS near_one,
                COUNT(*) FILTER (WHERE fo.current_probability <= 0.05) AS near_zero,
                COUNT(*) FILTER (WHERE fo.opening_probability IS NOT NULL
                                  AND fo.opening_probability > 0
                                  AND fo.opening_probability < 1) AS eligible
            FROM virtual_market vm
            JOIN futures_outcomes fo ON fo.market_id = vm.market_id
            GROUP BY vm.vm_id, vm.source, vm.category, vm.is_grouped,
                     vm.mutually_exclusive
        ),
        clean_vms AS (
            SELECT * FROM vm_stats
            WHERE eligible >= 1
              AND (near_one + near_zero) >= total_outcomes * 0.8
              AND near_one >= 1
        ),
        -- Determine which virtual markets are multi-outcome (keep all outcomes)
        -- vs binary/threshold (keep one outcome)
        ranked_outcomes AS (
            SELECT
                COALESCE(fo.calibration_probability, fo.opening_probability) AS adj_opening_probability,
                (fo.current_probability >= 0.95) AS is_winner,
                cv.vm_id, cv.source, cv.category,
                cv.eligible, cv.is_grouped,
                cv.is_grouped AS is_multi,
                ROW_NUMBER() OVER (
                    PARTITION BY cv.vm_id
                    ORDER BY ABS(fo.opening_probability - 0.5)
                ) AS rn
            FROM futures_outcomes fo
            JOIN virtual_market vm ON vm.market_id = fo.market_id
            JOIN clean_vms cv ON cv.vm_id = vm.vm_id AND cv.source = vm.source
            WHERE fo.opening_probability IS NOT NULL
              AND fo.opening_probability > 0 AND fo.opening_probability < 1
              AND fo.current_probability IS NOT NULL
              AND (fo.current_probability >= 0.95 OR fo.current_probability <= 0.05)
              -- Outcomes without trading activity have opening_probability
              -- set to NULL by the backfill task, so the IS NOT NULL filter
              -- above naturally excludes them.
        ),
        mode_prices AS (
            SELECT vm_id, adj_opening_probability AS mode_price
            FROM ranked_outcomes
            WHERE is_multi AND eligible >= 3
            GROUP BY vm_id, adj_opening_probability, eligible
            HAVING COUNT(*) > GREATEST(eligible * 0.5, 2)
        ),
        deduped AS (
            SELECT ro.* FROM ranked_outcomes ro
            LEFT JOIN mode_prices mp
              ON mp.vm_id = ro.vm_id AND mp.mode_price = ro.adj_opening_probability
            WHERE
                CASE
                    WHEN ro.is_multi
                        THEN ro.adj_opening_probability > 0.005
                         AND ro.adj_opening_probability < 0.98
                         AND mp.vm_id IS NULL
                    ELSE ro.rn = 1
                END
        ),
        bucketed AS (
            SELECT *, LEAST(FLOOR(adj_opening_probability * 10)::int, 9) AS bucket_idx
            FROM deduped
        )
        SELECT bucket_idx, source, category,
            COUNT(*) AS n,
            SUM(CASE WHEN is_winner THEN 1 ELSE 0 END) AS winners,
            AVG(adj_opening_probability) AS avg_prob,
            SUM(adj_opening_probability::float) AS sum_prob,
            SUM((adj_opening_probability::float - CASE WHEN is_winner THEN 1.0 ELSE 0.0 END)^2) AS sum_sq_err
        FROM bucketed
        GROUP BY bucket_idx, source, category
        ORDER BY bucket_idx, source, category
    """)

    result = await db.execute(sql)
    rows = result.all()

    # --- Odds API / Events data (ground truth from scores) ---
    # Each completed event with opening odds produces 2 data points:
    # home team (opening_home_probability, won if home_score > away_score)
    # away team (opening_away_probability, won if away_score > home_score)
    # Excludes draws (home_score = away_score) since those are ambiguous.
    events_sql = text("""
        SELECT
            LEAST(FLOOR(prob * 10)::int, 9) AS bucket_idx,
            'odds_api' AS source,
            s.key AS category,
            COUNT(*) AS n,
            SUM(CASE WHEN won THEN 1 ELSE 0 END) AS winners,
            AVG(prob) AS avg_prob,
            SUM(prob::float) AS sum_prob,
            SUM((prob::float - CASE WHEN won THEN 1.0 ELSE 0.0 END)^2) AS sum_sq_err
        FROM (
            SELECT opening_home_probability AS prob,
                   (home_score > away_score) AS won,
                   sport_id
            FROM events
            WHERE status IN ('completed', 'closed')
              AND opening_home_probability IS NOT NULL
              AND opening_home_probability > 0
              AND opening_home_probability < 1
              AND home_score IS NOT NULL
              AND away_score IS NOT NULL
              AND home_score != away_score
            UNION ALL
            SELECT opening_away_probability AS prob,
                   (away_score > home_score) AS won,
                   sport_id
            FROM events
            WHERE status IN ('completed', 'closed')
              AND opening_away_probability IS NOT NULL
              AND opening_away_probability > 0
              AND opening_away_probability < 1
              AND home_score IS NOT NULL
              AND away_score IS NOT NULL
              AND home_score != away_score
        ) outcomes
        JOIN sports s ON s.id = outcomes.sport_id
        GROUP BY bucket_idx, s.key
        ORDER BY bucket_idx, s.key
    """)
    events_result = await db.execute(events_sql)
    events_rows = events_result.all()

    # Merge futures + events rows
    all_rows = list(rows) + list(events_rows)

    total_markets_result = await db.execute(
        select(func.count()).select_from(FuturesMarket).where(FuturesMarket.status == "resolved")
    )
    total_markets = total_markets_result.scalar()

    events_count_result = await db.execute(
        text("SELECT COUNT(*) FROM events WHERE status IN ('completed', 'closed') AND opening_home_probability IS NOT NULL AND home_score IS NOT NULL AND away_score IS NOT NULL AND home_score != away_score")
    )
    total_events = events_count_result.scalar()

    total_outcomes = sum(r.n for r in all_rows)
    total_winners = sum(r.winners for r in all_rows)

    return {
        "buckets": [
            {
                "bucket_idx": r.bucket_idx, "source": r.source, "category": r.category,
                "n": r.n, "winners": r.winners,
                "avg_prob": round(float(r.avg_prob), 4),
                "sum_prob": round(float(r.sum_prob), 4),
                "sum_sq_err": round(float(r.sum_sq_err), 4),
            }
            for r in all_rows
        ],
        "total_markets": total_markets,
        "total_events": total_events,
        "total_outcomes": total_outcomes,
        "total_winners": total_winners,
    }


@router.post("/backfill-winners")
async def trigger_backfill_winners(
    secret: str = Query(...),
    dry_run: bool = Query(False, description="Log what would change without writing"),
    limit: int = Query(2000, description="Max Kalshi events to process"),
):
    """Trigger the is_winner backfill task."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")
    from app.tasks import backfill_winners as task
    result = task.delay(dry_run=dry_run, limit=limit)
    return {"status": "queued", "task_id": result.id, "dry_run": dry_run, "limit": limit}


@router.post("/backfill-polymarket-history")
async def trigger_backfill_polymarket_history(
    secret: str = Query(...),
    limit: int = Query(500, description="Max outcomes to process"),
):
    """Trigger Polymarket price history backfill for outcomes with sparse data."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")
    from app.tasks import backfill_polymarket_history as task
    result = task.delay(limit=limit)
    return {"status": "queued", "task_id": result.id, "limit": limit}


@router.post("/backfill-kalshi-history")
async def trigger_backfill_kalshi_history(
    secret: str = Query(...),
    limit: int = Query(500, description="Max outcomes to process"),
):
    """Trigger Kalshi price history backfill for outcomes with sparse data."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")
    from app.tasks import backfill_kalshi_history as task
    result = task.delay(limit=limit)
    return {"status": "queued", "task_id": result.id, "limit": limit}


@router.get("/backfill-winners/status")
async def backfill_winners_status(
    secret: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Check how many markets still need is_winner backfill."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    result = await db.execute(text("""
        SELECT fm.source,
            COUNT(DISTINCT fm.id) AS resolved_markets,
            COUNT(DISTINCT fm.id) FILTER (
                WHERE EXISTS (SELECT 1 FROM futures_outcomes fo WHERE fo.market_id = fm.id AND fo.is_winner = true)
            ) AS has_winner,
            COUNT(DISTINCT fm.id) FILTER (
                WHERE NOT EXISTS (SELECT 1 FROM futures_outcomes fo WHERE fo.market_id = fm.id AND fo.is_winner = true)
            ) AS needs_backfill
        FROM futures_markets fm
        WHERE fm.status = 'resolved'
        GROUP BY fm.source
    """))
    # Sample Polymarket soccer outcomes in the 40-50% bucket that LOST
    sample_diag = await db.execute(text("""
        SELECT fo.id, fo.opening_probability, fo.name AS outcome_name,
            fm.name AS market_name, fo.current_probability,
            fo.opening_captured_at,
            (SELECT COUNT(*) FROM futures_odds_snapshots fos WHERE fos.outcome_id = fo.id) AS snap_count,
            (SELECT probability FROM futures_odds_snapshots fos WHERE fos.outcome_id = fo.id
             ORDER BY captured_at DESC LIMIT 1) AS last_snap_prob
        FROM futures_outcomes fo
        JOIN futures_markets fm ON fo.market_id = fm.id
        WHERE fm.source = 'polymarket' AND fm.status = 'resolved'
          AND fm.llm_sport_category = 'soccer'
          AND fo.opening_probability > 0.35 AND fo.opening_probability < 0.55
          AND fo.current_probability <= 0.05
        ORDER BY RANDOM()
        LIMIT 15
    """))
    opening_diag = await db.execute(text("SELECT 1 AS cat"))

    cal_result = await db.execute(text("""
        SELECT
            COUNT(*) AS total_resolved,
            COUNT(fo.calibration_probability) AS has_cal_prob,
            COUNT(*) FILTER (WHERE fo.calibration_probability IS NULL
                             AND fm.commence_time IS NOT NULL) AS needs_cal_with_commence,
            COUNT(*) FILTER (WHERE fo.calibration_probability IS NULL
                             AND fm.commence_time IS NULL) AS needs_cal_without_commence,
            AVG(ABS(fo.calibration_probability - fo.opening_probability))
                FILTER (WHERE fo.calibration_probability IS NOT NULL) AS avg_price_shift
        FROM futures_outcomes fo
        JOIN futures_markets fm ON fo.market_id = fm.id
        WHERE fm.status = 'resolved'
          AND fo.opening_probability IS NOT NULL
          AND fo.opening_probability > 0 AND fo.opening_probability < 1
    """))
    cal_row = cal_result.one()

    group_result = await db.execute(text("""
        WITH poly_groups AS (
            SELECT fm.group_id, COUNT(*) AS group_size
            FROM futures_markets fm
            WHERE fm.source = 'polymarket' AND fm.status = 'resolved'
              AND fm.group_id IS NOT NULL
            GROUP BY fm.group_id
        )
        SELECT
            COUNT(*) FILTER (WHERE fm.group_id IS NULL) AS null_group_id,
            COUNT(*) FILTER (WHERE pg.group_size = 1) AS orphan_group_id,
            COUNT(*) FILTER (WHERE pg.group_size = 2) AS pair_group_id,
            COUNT(*) FILTER (WHERE pg.group_size >= 3) AS proper_group_id,
            COUNT(*) AS total_resolved_poly
        FROM futures_markets fm
        LEFT JOIN poly_groups pg ON pg.group_id = fm.group_id
        WHERE fm.source = 'polymarket' AND fm.status = 'resolved'
    """))
    group_row = group_result.one()

    return {
        "sources": [
            {"source": r.source, "resolved": r.resolved_markets,
             "has_winner": r.has_winner, "needs_backfill": r.needs_backfill}
            for r in result.all()
        ],
        "calibration_probability_coverage": {
            "total_resolved_outcomes": cal_row.total_resolved,
            "has_calibration_probability": cal_row.has_cal_prob,
            "needs_cal_with_commence": cal_row.needs_cal_with_commence,
            "needs_cal_without_commence": cal_row.needs_cal_without_commence,
            "pct_covered": round(100 * cal_row.has_cal_prob / max(cal_row.total_resolved, 1), 1),
            "avg_price_shift": round(float(cal_row.avg_price_shift or 0), 4),
        },
        "polymarket_group_id_health": {
            "total_resolved": group_row.total_resolved_poly,
            "null_group_id": group_row.null_group_id,
            "orphan_size_1": group_row.orphan_group_id,
            "pair_size_2": group_row.pair_group_id,
            "proper_size_3_plus": group_row.proper_group_id,
        },
        "orphan_samples": [
            {"id": r.id, "name": r.name, "category": r.cat,
             "group_id": r.group_id, "group_type": r.group_type,
             "external_id": r.external_id, "outcomes": r.outcome_count,
             "poly_event_id": r.poly_event_id}
            for r in (await db.execute(text("""
                WITH orphan_groups AS (
                    SELECT group_id FROM futures_markets
                    WHERE source = 'polymarket' AND status = 'resolved'
                      AND group_id IS NOT NULL
                    GROUP BY group_id HAVING COUNT(*) = 1
                )
                SELECT fm.id, fm.name,
                    COALESCE(fm.llm_sport_category, 'uncategorized') AS cat,
                    fm.group_id, fm.group_type, fm.external_id,
                    fm.market_metadata->>'polymarket_event_id' AS poly_event_id,
                    (SELECT COUNT(*) FROM futures_outcomes fo WHERE fo.market_id = fm.id) AS outcome_count
                FROM futures_markets fm
                JOIN orphan_groups og ON og.group_id = fm.group_id
                WHERE fm.source = 'polymarket' AND fm.status = 'resolved'
                ORDER BY RANDOM() LIMIT 15
            """))).all()
        ],
        "soccer_samples": [
            {"id": r.id, "opening": float(r.opening_probability),
             "outcome": r.outcome_name, "market": r.market_name,
             "current": float(r.current_probability),
             "captured_at": str(r.opening_captured_at) if r.opening_captured_at else None,
             "snaps": r.snap_count,
             "last_snap": float(r.last_snap_prob) if r.last_snap_prob else None}
            for r in sample_diag.all()
        ],
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


@router.post("/daily-digest/test")
async def test_daily_digest(
    request: Request,
    secret: str = Query(None),
    email: str = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Send a test daily digest email."""
    if not await _check_admin_auth(secret, request, db):
        raise HTTPException(status_code=403, detail="Unauthorized")

    if not email:
        raise HTTPException(400, "email query parameter required")

    from app.tasks.daily_digest import send_daily_digest
    success = await send_daily_digest(db, to_email=email)
    return {"status": "sent" if success else "no_content", "to": email}


@router.get("/sawtooth-audit")
async def sawtooth_audit(
    secret: str = Query(..., description="Admin secret"),
    jump_threshold: float = Query(0.03, description="Min |delta| to count as a big jump"),
    rate_threshold: float = Query(0.30, description="Min jump_rate to flag as affected"),
    limit: int = Query(10, description="Number of worst offenders to return"),
    db: AsyncSession = Depends(get_db),
):
    """Detect Kalshi dual-market sawtooth oscillation in win_prob_snapshots.

    The bug: Phase 2 and the live poller picked different dual markets for
    the same event, causing home_win_probability to oscillate between two
    values (e.g., 60% and 58%) on consecutive snapshots.

    Returns affected event counts, snapshot totals, worst offenders, and a
    post-fix stability check on snapshots from the last 2 hours.
    """
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    # ── Historical sawtooth detection via window functions ──
    historical_sql = text("""
        WITH consecutive AS (
            SELECT
                event_id,
                home_win_probability,
                LAG(home_win_probability) OVER (
                    PARTITION BY event_id ORDER BY captured_at
                ) AS prev_prob
            FROM win_prob_snapshots
            WHERE source = 'kalshi'
        ),
        jumps AS (
            SELECT
                event_id,
                COUNT(*) AS total_snaps,
                COUNT(*) FILTER (
                    WHERE ABS(home_win_probability - prev_prob) > :jump_threshold
                ) AS big_jumps
            FROM consecutive
            WHERE prev_prob IS NOT NULL
            GROUP BY event_id
        )
        SELECT
            j.event_id,
            e.home_team_name,
            e.away_team_name,
            e.status,
            j.total_snaps,
            j.big_jumps,
            ROUND((j.big_jumps::numeric / NULLIF(j.total_snaps, 0)), 4) AS jump_rate
        FROM jumps j
        JOIN events e ON e.id = j.event_id
        WHERE j.total_snaps >= 4
          AND j.big_jumps::float / NULLIF(j.total_snaps, 0) > :rate_threshold
        ORDER BY j.big_jumps DESC, jump_rate DESC
        LIMIT :lim
    """)

    worst_result = await db.execute(
        historical_sql,
        {"jump_threshold": jump_threshold, "rate_threshold": rate_threshold, "lim": limit},
    )
    worst_offenders = worst_result.fetchall()

    # ── Aggregate counts (affected events + total affected snapshots) ──
    counts_sql = text("""
        WITH consecutive AS (
            SELECT
                event_id,
                home_win_probability,
                LAG(home_win_probability) OVER (
                    PARTITION BY event_id ORDER BY captured_at
                ) AS prev_prob
            FROM win_prob_snapshots
            WHERE source = 'kalshi'
        ),
        jumps AS (
            SELECT
                event_id,
                COUNT(*) AS total_snaps,
                COUNT(*) FILTER (
                    WHERE ABS(home_win_probability - prev_prob) > :jump_threshold
                ) AS big_jumps
            FROM consecutive
            WHERE prev_prob IS NOT NULL
            GROUP BY event_id
        )
        SELECT
            COUNT(*) AS affected_events,
            COALESCE(SUM(total_snaps), 0) AS affected_snapshots,
            COALESCE(SUM(big_jumps), 0) AS total_big_jumps
        FROM jumps
        WHERE jumps.total_snaps >= 4
          AND jumps.big_jumps::float / NULLIF(jumps.total_snaps, 0) > :rate_threshold
    """)

    counts_result = await db.execute(
        counts_sql,
        {"jump_threshold": jump_threshold, "rate_threshold": rate_threshold},
    )
    counts = counts_result.fetchone()

    # ── Post-fix check: last 2 hours of Kalshi snapshots ──
    postfix_sql = text("""
        WITH recent AS (
            SELECT
                event_id,
                home_win_probability,
                LAG(home_win_probability) OVER (
                    PARTITION BY event_id ORDER BY captured_at
                ) AS prev_prob
            FROM win_prob_snapshots
            WHERE source = 'kalshi'
              AND captured_at > NOW() - INTERVAL '2 hours'
        ),
        recent_jumps AS (
            SELECT
                event_id,
                COUNT(*) AS total_snaps,
                COUNT(*) FILTER (
                    WHERE ABS(home_win_probability - prev_prob) > :jump_threshold
                ) AS big_jumps
            FROM recent
            WHERE prev_prob IS NOT NULL
            GROUP BY event_id
        )
        SELECT
            COUNT(*) AS events_checked,
            COALESCE(SUM(total_snaps), 0) AS snapshots_checked,
            COUNT(*) FILTER (
                WHERE total_snaps >= 2
                  AND big_jumps::float / NULLIF(total_snaps, 0) > :rate_threshold
            ) AS still_affected
        FROM recent_jumps
    """)

    postfix_result = await db.execute(
        postfix_sql,
        {"jump_threshold": jump_threshold, "rate_threshold": rate_threshold},
    )
    postfix = postfix_result.fetchone()

    return {
        "historical": {
            "affected_events": int(counts.affected_events) if counts else 0,
            "affected_snapshots": int(counts.affected_snapshots) if counts else 0,
            "total_big_jumps": int(counts.total_big_jumps) if counts else 0,
            "thresholds": {
                "jump_threshold": jump_threshold,
                "rate_threshold": rate_threshold,
                "min_snapshots": 4,
            },
            "worst_offenders": [
                {
                    "event_id": row.event_id,
                    "home_team": row.home_team_name,
                    "away_team": row.away_team_name,
                    "status": row.status,
                    "snapshot_count": int(row.total_snaps),
                    "jump_count": int(row.big_jumps),
                    "jump_rate": float(row.jump_rate),
                }
                for row in worst_offenders
            ],
        },
        "post_fix_check": {
            "window": "last 2 hours",
            "events_checked": int(postfix.events_checked) if postfix else 0,
            "snapshots_checked": int(postfix.snapshots_checked) if postfix else 0,
            "still_affected": int(postfix.still_affected) if postfix else 0,
            "fix_working": (postfix.still_affected == 0) if postfix else True,
        },
    }


@router.get("/sawtooth-diagnosis")
async def sawtooth_diagnosis(
    secret: str = Query(..., description="Admin secret"),
    jump_threshold: float = Query(0.03, description="Min |delta| to count as a big jump"),
    rate_threshold: float = Query(0.30, description="Min jump_rate to flag"),
    limit: int = Query(52, description="Max events to diagnose"),
    db: AsyncSession = Depends(get_db),
):
    """Diagnose root cause of sawtooth oscillation for each affected event.

    For each event with sawtooth Kalshi snapshots, returns:
    - Currently linked Kalshi futures_markets (event_id FK)
    - Distinct market_ids referenced in win_prob_snapshot game_state
    - Classification: multi_game (Type A), dual_market (Type B), or other (Type C)
    """
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    # Step 1: Find affected events (same query as sawtooth-audit)
    affected_sql = text("""
        WITH consecutive AS (
            SELECT
                event_id,
                home_win_probability,
                LAG(home_win_probability) OVER (
                    PARTITION BY event_id ORDER BY captured_at
                ) AS prev_prob
            FROM win_prob_snapshots
            WHERE source = 'kalshi'
        ),
        jumps AS (
            SELECT
                event_id,
                COUNT(*) AS total_snaps,
                COUNT(*) FILTER (
                    WHERE ABS(home_win_probability - prev_prob) > :jump_threshold
                ) AS big_jumps
            FROM consecutive
            WHERE prev_prob IS NOT NULL
            GROUP BY event_id
        )
        SELECT
            j.event_id,
            e.home_team_name,
            e.away_team_name,
            e.status,
            e.commence_time,
            j.total_snaps,
            j.big_jumps,
            ROUND((j.big_jumps::numeric / NULLIF(j.total_snaps, 0)), 4) AS jump_rate
        FROM jumps j
        JOIN events e ON e.id = j.event_id
        WHERE j.total_snaps >= 4
          AND j.big_jumps::float / NULLIF(j.total_snaps, 0) > :rate_threshold
        ORDER BY j.big_jumps DESC, jump_rate DESC
        LIMIT :lim
    """)

    affected_result = await db.execute(
        affected_sql,
        {"jump_threshold": jump_threshold, "rate_threshold": rate_threshold, "lim": limit},
    )
    affected_events = affected_result.fetchall()

    diagnoses = []
    for row in affected_events:
        event_id = row.event_id

        # Get currently linked Kalshi futures_markets
        linked_result = await db.execute(
            select(FuturesMarket)
            .where(
                FuturesMarket.event_id == event_id,
                FuturesMarket.source == "kalshi",
            )
        )
        linked_markets = linked_result.scalars().all()

        # Get distinct market_ids from win_prob_snapshot game_state
        # game_state->'market_id' tells us which market generated each snapshot
        snapshot_markets_sql = text("""
            SELECT
                DISTINCT game_state->>'market_id' AS market_id,
                game_state->>'market_name' AS market_name,
                COUNT(*) AS snapshot_count,
                MIN(captured_at) AS first_snap,
                MAX(captured_at) AS last_snap,
                MIN(home_win_probability) AS min_prob,
                MAX(home_win_probability) AS max_prob,
                AVG(home_win_probability) AS avg_prob
            FROM win_prob_snapshots
            WHERE event_id = :event_id
              AND source = 'kalshi'
              AND game_state IS NOT NULL
              AND game_state->>'market_id' IS NOT NULL
            GROUP BY game_state->>'market_id', game_state->>'market_name'
            ORDER BY snapshot_count DESC
        """)
        snap_markets_result = await db.execute(
            snapshot_markets_sql, {"event_id": event_id}
        )
        snap_market_rows = snap_markets_result.fetchall()

        # Also get snapshots WITHOUT game_state (legacy snapshots)
        legacy_count_result = await db.execute(text("""
            SELECT COUNT(*) FROM win_prob_snapshots
            WHERE event_id = :event_id
              AND source = 'kalshi'
              AND (game_state IS NULL OR game_state->>'market_id' IS NULL)
        """), {"event_id": event_id})
        legacy_count = legacy_count_result.scalar() or 0

        # Classify the root cause
        distinct_market_ids = set()
        market_avg_probs = {}
        for srow in snap_market_rows:
            mid = srow.market_id
            if mid:
                distinct_market_ids.add(mid)
                market_avg_probs[mid] = float(srow.avg_prob) if srow.avg_prob else None

        # Check if linked markets have different tickers (different games)
        linked_tickers = {}
        for m in linked_markets:
            # Extract ticker prefix + date to identify unique games
            ticker = m.external_id or ""
            linked_tickers[str(m.id)] = {
                "ticker": ticker,
                "name": m.name,
                "status": m.status,
            }

        # Classification logic
        if len(distinct_market_ids) >= 2:
            # Multiple markets wrote snapshots — check if they're different games
            # Type A: different game tickers (multi-game)
            # Type B: same game, dual market (Team A win? + Team B win?)
            avg_probs = list(market_avg_probs.values())
            avg_probs = [p for p in avg_probs if p is not None]

            if len(avg_probs) >= 2:
                # If average probs are roughly complementary (~sum to 1), it's dual market
                avg_probs.sort()
                prob_sum = avg_probs[0] + avg_probs[-1]
                if 0.85 < prob_sum < 1.15:
                    cause_type = "B_dual_market"
                else:
                    cause_type = "A_multi_game"
            else:
                cause_type = "A_multi_game"
        elif len(linked_markets) >= 2 and len(distinct_market_ids) <= 1:
            cause_type = "B_dual_market_linked"
        else:
            cause_type = "C_other"

        diagnoses.append({
            "event_id": event_id,
            "home_team": row.home_team_name,
            "away_team": row.away_team_name,
            "status": row.status,
            "commence_time": row.commence_time.isoformat() if row.commence_time else None,
            "snapshot_count": int(row.total_snaps),
            "jump_count": int(row.big_jumps),
            "jump_rate": float(row.jump_rate),
            "cause_type": cause_type,
            "linked_kalshi_markets": [
                {
                    "market_id": m.id,
                    "external_id": m.external_id,
                    "name": m.name,
                    "status": m.status,
                    "commence_time": m.commence_time.isoformat() if m.commence_time else None,
                }
                for m in linked_markets
            ],
            "snapshot_source_markets": [
                {
                    "market_id": srow.market_id,
                    "market_name": srow.market_name,
                    "snapshot_count": int(srow.snapshot_count),
                    "first_snap": srow.first_snap.isoformat() if srow.first_snap else None,
                    "last_snap": srow.last_snap.isoformat() if srow.last_snap else None,
                    "min_prob": round(float(srow.min_prob), 4) if srow.min_prob is not None else None,
                    "max_prob": round(float(srow.max_prob), 4) if srow.max_prob is not None else None,
                    "avg_prob": round(float(srow.avg_prob), 4) if srow.avg_prob is not None else None,
                }
                for srow in snap_market_rows
            ],
            "legacy_snapshots_no_market_id": legacy_count,
        })

    # Summary stats
    type_counts = {}
    for d in diagnoses:
        t = d["cause_type"]
        type_counts[t] = type_counts.get(t, 0) + 1

    return {
        "total_diagnosed": len(diagnoses),
        "cause_type_summary": type_counts,
        "diagnoses": diagnoses,
    }


@router.post("/sawtooth-fix")
async def sawtooth_fix(
    secret: str = Query(..., description="Admin secret"),
    event_id: Optional[int] = Query(None, description="Fix a single event (or all if omitted)"),
    dry_run: bool = Query(True, description="Preview changes without applying"),
    jump_threshold: float = Query(0.03, description="Min |delta| to count as big jump"),
    rate_threshold: float = Query(0.30, description="Min jump_rate to flag"),
    db: AsyncSession = Depends(get_db),
):
    """Fix sawtooth oscillation by unlinking wrong markets and deleting bad snapshots.

    For each affected event:
    - Type A (multi-game): Identifies which market is the outlier (by avg probability
      distance from sportsbook consensus) and unlinks it + deletes its snapshots.
    - Type B (dual-market): Keeps all linked markets but deletes ALL historical
      snapshots (the devig averaging fix handles future writes correctly).
    - Type C (other): Deletes all Kalshi snapshots for the event (nuclear option
      for events with no linked markets or unparseable patterns).

    Use dry_run=true (default) to preview, then dry_run=false to apply.
    """
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    # Find affected events
    if event_id:
        affected_sql = text("""
            WITH consecutive AS (
                SELECT
                    event_id,
                    home_win_probability,
                    LAG(home_win_probability) OVER (
                        PARTITION BY event_id ORDER BY captured_at
                    ) AS prev_prob
                FROM win_prob_snapshots
                WHERE source = 'kalshi'
                  AND event_id = :event_id
            ),
            jumps AS (
                SELECT
                    event_id,
                    COUNT(*) AS total_snaps,
                    COUNT(*) FILTER (
                        WHERE ABS(home_win_probability - prev_prob) > :jump_threshold
                    ) AS big_jumps
                FROM consecutive
                WHERE prev_prob IS NOT NULL
                GROUP BY event_id
            )
            SELECT j.event_id, j.total_snaps, j.big_jumps,
                   e.home_team_name, e.away_team_name, e.status
            FROM jumps j
            JOIN events e ON e.id = j.event_id
            WHERE j.total_snaps >= 4
        """)
        affected_result = await db.execute(
            affected_sql,
            {"event_id": event_id, "jump_threshold": jump_threshold},
        )
    else:
        affected_sql = text("""
            WITH consecutive AS (
                SELECT
                    event_id,
                    home_win_probability,
                    LAG(home_win_probability) OVER (
                        PARTITION BY event_id ORDER BY captured_at
                    ) AS prev_prob
                FROM win_prob_snapshots
                WHERE source = 'kalshi'
            ),
            jumps AS (
                SELECT
                    event_id,
                    COUNT(*) AS total_snaps,
                    COUNT(*) FILTER (
                        WHERE ABS(home_win_probability - prev_prob) > :jump_threshold
                    ) AS big_jumps
                FROM consecutive
                WHERE prev_prob IS NOT NULL
                GROUP BY event_id
            )
            SELECT j.event_id, j.total_snaps, j.big_jumps,
                   e.home_team_name, e.away_team_name, e.status
            FROM jumps j
            JOIN events e ON e.id = j.event_id
            WHERE j.total_snaps >= 4
              AND j.big_jumps::float / NULLIF(j.total_snaps, 0) > :rate_threshold
        """)
        affected_result = await db.execute(
            affected_sql,
            {"jump_threshold": jump_threshold, "rate_threshold": rate_threshold},
        )

    affected_rows = affected_result.fetchall()

    results = []
    total_markets_unlinked = 0
    total_snapshots_deleted = 0

    for row in affected_rows:
        eid = row.event_id
        fix_detail = {
            "event_id": eid,
            "home_team": row.home_team_name,
            "away_team": row.away_team_name,
            "status": row.status,
            "snapshot_count": int(row.total_snaps),
            "actions": [],
        }

        # Get currently linked Kalshi markets
        linked_result = await db.execute(
            select(FuturesMarket)
            .where(
                FuturesMarket.event_id == eid,
                FuturesMarket.source == "kalshi",
            )
        )
        linked_markets = linked_result.scalars().all()

        # Get snapshot source breakdown by market_id
        snap_markets_result = await db.execute(text("""
            SELECT
                game_state->>'market_id' AS market_id,
                game_state->>'market_name' AS market_name,
                COUNT(*) AS snap_count,
                AVG(home_win_probability) AS avg_prob
            FROM win_prob_snapshots
            WHERE event_id = :event_id
              AND source = 'kalshi'
              AND game_state IS NOT NULL
              AND game_state->>'market_id' IS NOT NULL
            GROUP BY game_state->>'market_id', game_state->>'market_name'
            ORDER BY snap_count DESC
        """), {"event_id": eid})
        snap_sources = snap_markets_result.fetchall()

        distinct_market_ids = {s.market_id for s in snap_sources if s.market_id}
        market_avgs = {
            s.market_id: float(s.avg_prob) for s in snap_sources
            if s.market_id and s.avg_prob is not None
        }

        # Get sportsbook consensus for this event
        consensus_result = await db.execute(text("""
            SELECT home_win_probability FROM odds_snapshots
            WHERE event_id = :event_id
              AND home_win_probability IS NOT NULL
            ORDER BY captured_at DESC
            LIMIT 1
        """), {"event_id": eid})
        consensus_row = consensus_result.fetchone()

        # Also try opening odds as fallback
        if not consensus_row:
            consensus_result2 = await db.execute(text("""
                SELECT opening_home_probability FROM events WHERE id = :event_id
            """), {"event_id": eid})
            consensus_row = consensus_result2.fetchone()

        consensus = None
        if consensus_row and consensus_row[0] is not None:
            consensus = float(consensus_row[0])

        # Classify and decide fix action
        if len(distinct_market_ids) >= 2 and market_avgs:
            avg_probs = list(market_avgs.values())
            avg_probs_sorted = sorted(avg_probs)

            # Check if dual-market (complementary probs sum ~1)
            if len(avg_probs_sorted) == 2:
                prob_sum = avg_probs_sorted[0] + avg_probs_sorted[1]
                if 0.85 < prob_sum < 1.15:
                    # Type B: dual-market inversion — delete ALL Kalshi snapshots
                    # The devig averaging in Phase 2 handles future writes correctly
                    fix_detail["cause_type"] = "B_dual_market"

                    snap_count_result = await db.execute(text("""
                        SELECT COUNT(*) FROM win_prob_snapshots
                        WHERE event_id = :event_id AND source = 'kalshi'
                    """), {"event_id": eid})
                    to_delete = snap_count_result.scalar() or 0

                    fix_detail["actions"].append({
                        "action": "delete_all_kalshi_snapshots",
                        "reason": "dual-market complementary probs cause oscillation; devig fix handles future writes",
                        "snapshots_to_delete": to_delete,
                    })

                    if not dry_run:
                        del_result = await db.execute(
                            delete(WinProbSnapshot).where(
                                WinProbSnapshot.event_id == eid,
                                WinProbSnapshot.source == "kalshi",
                            )
                        )
                        total_snapshots_deleted += del_result.rowcount
                        fix_detail["actions"][-1]["snapshots_deleted"] = del_result.rowcount
                    else:
                        total_snapshots_deleted += to_delete
                else:
                    # Type A: multi-game linkage
                    fix_detail["cause_type"] = "A_multi_game"

                    # Find the outlier market — the one whose avg prob is furthest
                    # from consensus (if available), or the one with fewer snapshots
                    if consensus is not None:
                        # Pick the market closest to consensus as "correct"
                        best_mid = min(market_avgs, key=lambda mid: abs(market_avgs[mid] - consensus))
                        outlier_mids = [mid for mid in distinct_market_ids if mid != best_mid]
                    else:
                        # No consensus — keep the market with more snapshots
                        snap_counts = {s.market_id: int(s.snap_count) for s in snap_sources}
                        best_mid = max(snap_counts, key=lambda mid: snap_counts.get(mid, 0))
                        outlier_mids = [mid for mid in distinct_market_ids if mid != best_mid]

                    for omid in outlier_mids:
                        # Delete snapshots from the outlier market
                        snap_del_count_result = await db.execute(text("""
                            SELECT COUNT(*) FROM win_prob_snapshots
                            WHERE event_id = :event_id
                              AND source = 'kalshi'
                              AND game_state->>'market_id' = :market_id
                        """), {"event_id": eid, "market_id": str(omid)})
                        to_delete = snap_del_count_result.scalar() or 0

                        # Find the market name for this outlier
                        outlier_name = next(
                            (s.market_name for s in snap_sources if s.market_id == omid),
                            "unknown"
                        )

                        fix_detail["actions"].append({
                            "action": "delete_outlier_snapshots",
                            "outlier_market_id": omid,
                            "outlier_market_name": outlier_name,
                            "outlier_avg_prob": round(market_avgs.get(omid, 0), 4),
                            "kept_market_id": best_mid,
                            "consensus": round(consensus, 4) if consensus else None,
                            "reason": f"market avg={market_avgs.get(omid, 0):.3f} is far from consensus={consensus:.3f}" if consensus else "market has fewer snapshots",
                            "snapshots_to_delete": to_delete,
                        })

                        if not dry_run:
                            del_result = await db.execute(text("""
                                DELETE FROM win_prob_snapshots
                                WHERE event_id = :event_id
                                  AND source = 'kalshi'
                                  AND game_state->>'market_id' = :market_id
                            """), {"event_id": eid, "market_id": str(omid)})
                            total_snapshots_deleted += del_result.rowcount
                            fix_detail["actions"][-1]["snapshots_deleted"] = del_result.rowcount

                        # Unlink the outlier market if it's still linked
                        omid_int = int(omid) if omid and omid.isdigit() else None
                        if omid_int:
                            for m in linked_markets:
                                if m.id == omid_int:
                                    fix_detail["actions"].append({
                                        "action": "unlink_market",
                                        "market_id": m.id,
                                        "market_name": m.name,
                                        "external_id": m.external_id,
                                        "reason": "wrong game linked to this event",
                                    })
                                    if not dry_run:
                                        m.event_id = None
                                        total_markets_unlinked += 1
            else:
                # 3+ distinct markets — nuclear: delete all, keep the majority
                fix_detail["cause_type"] = "A_multi_game_complex"

                snap_counts = {s.market_id: int(s.snap_count) for s in snap_sources}
                best_mid = max(snap_counts, key=lambda mid: snap_counts.get(mid, 0)) if snap_counts else None

                # Delete snapshots from all outlier markets
                for omid in distinct_market_ids:
                    if omid == best_mid:
                        continue
                    snap_del_count_result = await db.execute(text("""
                        SELECT COUNT(*) FROM win_prob_snapshots
                        WHERE event_id = :event_id
                          AND source = 'kalshi'
                          AND game_state->>'market_id' = :market_id
                    """), {"event_id": eid, "market_id": str(omid)})
                    to_delete = snap_del_count_result.scalar() or 0

                    fix_detail["actions"].append({
                        "action": "delete_outlier_snapshots",
                        "outlier_market_id": omid,
                        "kept_market_id": best_mid,
                        "snapshots_to_delete": to_delete,
                    })

                    if not dry_run:
                        del_result = await db.execute(text("""
                            DELETE FROM win_prob_snapshots
                            WHERE event_id = :event_id
                              AND source = 'kalshi'
                              AND game_state->>'market_id' = :market_id
                        """), {"event_id": eid, "market_id": str(omid)})
                        total_snapshots_deleted += del_result.rowcount

                    omid_int = int(omid) if omid and omid.isdigit() else None
                    if omid_int:
                        for m in linked_markets:
                            if m.id == omid_int:
                                fix_detail["actions"].append({
                                    "action": "unlink_market",
                                    "market_id": m.id,
                                    "external_id": m.external_id,
                                })
                                if not dry_run:
                                    m.event_id = None
                                    total_markets_unlinked += 1

        elif len(distinct_market_ids) == 0:
            # No game_state market_ids — legacy snapshots. Delete all.
            fix_detail["cause_type"] = "C_legacy_no_market_id"
            snap_count_result = await db.execute(text("""
                SELECT COUNT(*) FROM win_prob_snapshots
                WHERE event_id = :event_id AND source = 'kalshi'
            """), {"event_id": eid})
            to_delete = snap_count_result.scalar() or 0

            fix_detail["actions"].append({
                "action": "delete_all_kalshi_snapshots",
                "reason": "legacy snapshots without market_id; cannot attribute to specific market",
                "snapshots_to_delete": to_delete,
            })

            if not dry_run:
                del_result = await db.execute(
                    delete(WinProbSnapshot).where(
                        WinProbSnapshot.event_id == eid,
                        WinProbSnapshot.source == "kalshi",
                    )
                )
                total_snapshots_deleted += del_result.rowcount

        else:
            # Single market_id but still sawtooth — must be inversion within
            # one market. Delete all Kalshi snapshots.
            fix_detail["cause_type"] = "C_single_market_oscillation"
            snap_count_result = await db.execute(text("""
                SELECT COUNT(*) FROM win_prob_snapshots
                WHERE event_id = :event_id AND source = 'kalshi'
            """), {"event_id": eid})
            to_delete = snap_count_result.scalar() or 0

            fix_detail["actions"].append({
                "action": "delete_all_kalshi_snapshots",
                "reason": "single market oscillating; likely yes_is_home flip-flop",
                "snapshots_to_delete": to_delete,
            })

            if not dry_run:
                del_result = await db.execute(
                    delete(WinProbSnapshot).where(
                        WinProbSnapshot.event_id == eid,
                        WinProbSnapshot.source == "kalshi",
                    )
                )
                total_snapshots_deleted += del_result.rowcount

        # Also clear kalshi from win_probability_sources on the event
        if not dry_run and fix_detail["actions"]:
            wps_result = await db.execute(
                select(Event.win_probability_sources).where(Event.id == eid)
            )
            wps = wps_result.scalar_one_or_none() or {}
            if "kalshi" in wps:
                del wps["kalshi"]
                await db.execute(
                    update(Event)
                    .where(Event.id == eid)
                    .values(win_probability_sources=wps)
                )
                fix_detail["actions"].append({
                    "action": "clear_kalshi_from_win_prob_sources",
                })

        results.append(fix_detail)

    if not dry_run:
        await db.commit()

    return {
        "dry_run": dry_run,
        "events_processed": len(results),
        "total_markets_unlinked": total_markets_unlinked,
        "total_snapshots_deleted": total_snapshots_deleted,
        "results": results,
    }
