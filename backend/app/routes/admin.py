"""Admin API endpoints for maintenance tasks."""

import os
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, update
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
async def recalculate_pulse(
    secret: str = Query(..., description="Admin secret for authorization"),
    limit: int = Query(100, description="Max events to process per batch"),
    force: bool = Query(False, description="Force recalculation even if Pulse already exists"),
    db: AsyncSession = Depends(get_db),
):
    """
    Trigger Pulse recalculation for completed events.

    - If force=False: Only processes events without Pulse scores
    - If force=True: Clears existing Pulse data and recalculates all

    This is useful for:
    - Initial backfill after deploying Pulse
    - Recalculating after algorithm changes
    """
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.utils.pulse import calculate_pulse, PulseDataPoint
    from app.models import OddsSnapshot

    # If force mode, clear existing Pulse data first
    cleared_count = 0
    if force:
        result = await db.execute(
            update(Event)
            .where(
                Event.status.in_(["completed", "closed"]),
                Event.raw_gei.isnot(None),
            )
            .values(raw_gei=None, gei_components=None, gei_computed_at=None)
        )
        cleared_count = result.rowcount
        await db.commit()

    # Find finished events without Pulse
    result = await db.execute(
        select(Event)
        .options(selectinload(Event.sport))
        .where(
            Event.status.in_(["completed", "closed"]),
            Event.raw_gei.is_(None),
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
                continue

            # Convert to PulseDataPoint objects
            data_points = [
                PulseDataPoint(
                    captured_at=s.captured_at,
                    home_win_probability=float(s.home_win_probability) if s.home_win_probability else None,
                    bookmaker=s.bookmaker,
                )
                for s in snapshots
            ]

            game_end = max(s.captured_at for s in snapshots)
            sport_key = event.sport.key if event.sport else "unknown"

            pulse_result = calculate_pulse(
                snapshots=data_points,
                game_start=event.commence_time,
                current_time=game_end,
                sport_key=sport_key,
            )

            if pulse_result and pulse_result.data_quality != "minimal":
                event.raw_gei = pulse_result.score / 100.0
                event.gei_components = pulse_result.components.to_json()
                event.gei_computed_at = datetime.now(timezone.utc)
                processed += 1

        except Exception as e:
            errors += 1
            if len(error_details) < 5:
                error_details.append(f"Event {event.id}: {str(e)}")

    await db.commit()

    # Check how many events still need processing
    remaining_result = await db.execute(
        select(Event.id)
        .where(
            Event.status.in_(["completed", "closed"]),
            Event.raw_gei.is_(None),
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


@router.get("/pulse/status")
async def pulse_status(
    db: AsyncSession = Depends(get_db),
):
    """
    Get the current status of Pulse calculations.

    Returns counts of events with and without Pulse scores.
    """
    from sqlalchemy import func

    # Count events by Pulse status
    result = await db.execute(
        select(
            Event.status,
            func.count().filter(Event.raw_gei.isnot(None)).label("with_pulse"),
            func.count().filter(Event.raw_gei.is_(None)).label("without_pulse"),
        )
        .group_by(Event.status)
    )
    rows = result.all()

    status_counts = {}
    total_with = 0
    total_without = 0

    for status, with_pulse, without_pulse in rows:
        status_counts[status] = {
            "with_pulse": with_pulse,
            "without_pulse": without_pulse,
        }
        total_with += with_pulse
        total_without += without_pulse

    return {
        "total": {
            "with_pulse": total_with,
            "without_pulse": total_without,
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
    limit: int = Query(50, description="Max markets to categorize per batch"),
    dry_run: bool = Query(False, description="Preview categorizations without saving"),
    db: AsyncSession = Depends(get_db),
):
    """
    Categorize uncategorized futures markets using LLM.

    Finds markets without sport_id or llm_sport_category and uses:
    1. Pattern matching rules (fast, free)
    2. LLM fallback (smart, for edge cases)

    Results are cached in the llm_sport_category column.
    """
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.models import FuturesMarket
    from app.utils.futures_categorization import categorize_market
    from app.services import llm

    # Find uncategorized markets
    result = await db.execute(
        select(FuturesMarket)
        .where(
            FuturesMarket.sport_id.is_(None),
            FuturesMarket.llm_sport_category.is_(None),
        )
        .limit(limit)
    )
    markets = result.scalars().all()

    if not markets:
        return {
            "status": "complete",
            "message": "No uncategorized markets found",
            "processed": 0,
        }

    categorized = []
    failed = []

    for market in markets:
        category = categorize_market(market.name, use_llm=llm.is_available())

        if category:
            categorized.append({
                "id": market.id,
                "name": market.name,
                "category": category,
            })
            if not dry_run:
                market.llm_sport_category = category
        else:
            failed.append({
                "id": market.id,
                "name": market.name,
            })

    if not dry_run:
        await db.commit()

    # Count remaining
    remaining_result = await db.execute(
        select(FuturesMarket)
        .where(
            FuturesMarket.sport_id.is_(None),
            FuturesMarket.llm_sport_category.is_(None),
        )
    )
    remaining = len(remaining_result.scalars().all())

    return {
        "status": "success",
        "dry_run": dry_run,
        "processed": len(markets),
        "categorized": len(categorized),
        "failed": len(failed),
        "remaining": remaining,
        "llm_available": llm.is_available(),
        "results": categorized[:10],  # Preview first 10
        "failures": failed[:10] if failed else None,
        "message": f"Categorized {len(categorized)}/{len(markets)} markets." +
                   (f" {remaining} remaining." if remaining > 0 else ""),
    }


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
    dry_run: bool = Query(False, description="Preview without saving"),
    db: AsyncSession = Depends(get_db),
):
    """
    Force-categorize ALL uncategorized futures using LLM.

    Unlike /categorize which only runs LLM on pattern-miss, this endpoint
    runs LLM on EVERY uncategorized market and saves the result (even "other").

    This ensures no market is left with llm_sport_category=NULL.
    """
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.models import FuturesMarket
    from app.services import llm

    if not llm.is_available():
        raise HTTPException(
            status_code=503,
            detail="LLM service not available (OPENAI_API_KEY not set?)"
        )

    # Find uncategorized markets
    result = await db.execute(
        select(FuturesMarket)
        .where(
            FuturesMarket.sport_id.is_(None),
            FuturesMarket.llm_sport_category.is_(None),
        )
        .limit(limit)
    )
    markets = result.scalars().all()

    if not markets:
        return {
            "status": "complete",
            "message": "No uncategorized markets found",
            "processed": 0,
        }

    results = []
    by_category = {}

    for market in markets:
        # Always use LLM (which now always returns a category)
        category = llm.classify_futures_market(market.name)

        results.append({
            "id": market.id,
            "name": market.name,
            "category": category,
        })

        by_category[category] = by_category.get(category, 0) + 1

        if not dry_run:
            market.llm_sport_category = category

    if not dry_run:
        await db.commit()

    # Count remaining
    remaining_result = await db.execute(
        select(FuturesMarket)
        .where(
            FuturesMarket.sport_id.is_(None),
            FuturesMarket.llm_sport_category.is_(None),
        )
    )
    remaining = len(remaining_result.scalars().all())

    return {
        "status": "success",
        "dry_run": dry_run,
        "processed": len(markets),
        "remaining": remaining,
        "by_category": by_category,
        "sample_results": results[:20],
        "message": f"Categorized {len(markets)} markets. {remaining} remaining.",
    }


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
async def pulse_distributions(
    db: AsyncSession = Depends(get_db),
):
    """
    Analyze the distribution of Pulse scores and components across all scored events.

    Returns histograms and statistics for the overall score and each component
    (heart_rate, amplitude, arrhythmia, vitals), plus saturation analysis.
    No auth required - diagnostic/read-only.
    """
    import json
    from sqlalchemy import func

    # Fetch all events with Pulse data
    result = await db.execute(
        select(
            Event.id,
            Event.raw_gei,
            Event.gei_components,
            Event.status,
        )
        .where(Event.raw_gei.isnot(None))
        .order_by(Event.raw_gei.desc())
    )
    rows = result.all()

    if not rows:
        return {"status": "no_data", "message": "No events with Pulse scores found"}

    scores = []
    components = {
        "heart_rate": [],
        "amplitude": [],
        "arrhythmia": [],
        "vitals": [],
        "time_weight": [],
    }
    lead_changes_list = []
    by_status = {}

    for event_id, raw_gei, gei_components_str, status in rows:
        score = max(1, min(100, round(float(raw_gei) * 100)))
        scores.append(score)

        # Count by event status
        by_status[status] = by_status.get(status, 0) + 1

        if gei_components_str:
            try:
                comp = json.loads(gei_components_str) if isinstance(gei_components_str, str) else gei_components_str
                for key in components:
                    if key in comp:
                        components[key].append(float(comp[key]))
                if "lead_changes" in comp:
                    lead_changes_list.append(int(comp["lead_changes"]))
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

    # Saturation analysis: how many are at 100% (>=0.99)
    saturation = {}
    for key, vals in components.items():
        if vals:
            at_max = sum(1 for v in vals if v >= 0.99)
            saturation[key] = {
                "at_100_pct": at_max,
                "at_100_pct_ratio": round(at_max / len(vals) * 100, 1),
            }

    # Pulse status distribution
    status_labels = {
        "flatline": (1, 20),
        "weak": (21, 40),
        "steady": (41, 60),
        "strong": (61, 80),
        "racing": (81, 100),
    }
    pulse_status_dist = {}
    for label, (lo, hi) in status_labels.items():
        count = sum(1 for s in scores if lo <= s <= hi)
        pulse_status_dist[label] = {
            "count": count,
            "pct": round(count / len(scores) * 100, 1),
        }

    return {
        "total_events": len(scores),
        "by_event_status": by_status,
        "score": {
            "stats": compute_stats(scores),
            "histogram": compute_histogram(scores, score_buckets),
            "status_distribution": pulse_status_dist,
        },
        "components": {
            key: {
                "stats": compute_stats(vals),
                "histogram": compute_histogram(vals, comp_buckets),
            }
            for key, vals in components.items()
        },
        "saturation": saturation,
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


@router.post("/espn/fix-commence-times")
async def fix_commence_times(
    secret: str = Query(..., description="Admin secret for authorization"),
    limit: int = Query(200, description="Max events to check"),
):
    """
    Fix incorrect commence_time values using ESPN as authoritative source.

    Finds events with espn_id, fetches ESPN scoreboard data for the relevant
    dates, and corrects any commence_time that differs by more than 5 minutes.

    Queues as a background Celery task to avoid HTTP timeout.
    Use /api/admin/espn/task/{task_id} to check results.
    """
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.tasks import fix_commence_times_from_espn

    try:
        task = fix_commence_times_from_espn.delay(limit=limit)
        return {
            "status": "queued",
            "task_id": task.id,
            "message": f"Checking up to {limit} events with ESPN IDs. Use /api/admin/espn/task/{task.id} for results.",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to queue task: {str(e)}")


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
