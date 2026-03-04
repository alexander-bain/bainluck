"""Admin API endpoints for maintenance tasks."""

import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, update, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Event, FuturesMarket, FuturesOutcome, FuturesOddsSnapshot
from app.services import get_db
from app.utils import probability_to_american

router = APIRouter()


def _check_admin_secret(secret: str) -> bool:
    """Verify admin secret for protected endpoints."""
    expected = os.getenv("ADMIN_SECRET")
    if not expected:
        # If no secret configured, allow access (development mode)
        return True
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
    """Manually trigger DataGolf market polling (schedule + pre-tournament predictions)."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.tasks import poll_datagolf_markets
    result = poll_datagolf_markets.delay()
    return {
        "status": "queued",
        "task_id": result.id,
        "message": "DataGolf market polling task queued.",
    }


@router.post("/datagolf/poll-live")
async def trigger_datagolf_live_poll(
    secret: str = Query(..., description="Admin secret for authorization"),
):
    """Manually trigger DataGolf live in-play polling (bypasses Redis gate)."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.tasks import poll_datagolf_live
    result = poll_datagolf_live.delay()
    return {
        "status": "queued",
        "task_id": result.id,
        "message": "DataGolf live polling task queued.",
    }


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


@router.get("/datagolf/task/{task_id}")
async def get_datagolf_task_status(
    task_id: str,
    secret: str = Query(..., description="Admin secret for authorization"),
):
    """Check status of a DataGolf background task."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from celery.result import AsyncResult
    from app.tasks import celery_app
    result = AsyncResult(task_id, app=celery_app)
    response = {
        "task_id": task_id,
        "state": result.state,
    }
    if result.ready():
        response["result"] = result.result
    elif result.state == "FAILURE":
        response["error"] = str(result.result)
    return response

