"""Admin endpoints for futures categorization, metadata enrichment, and taxonomy."""


import os
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from sqlalchemy import select, or_, text, func

from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy.orm import selectinload

from app.models import Event, FuturesMarket

from app.services import get_db, get_db_rw

from app.routes.admin_utils import _check_admin_secret


router = APIRouter()


@router.post("/futures/categorize")
async def categorize_futures(
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
    limit: int = Query(100, description="Max markets to categorize per batch"),
):
    """
    Categorize uncategorized futures markets using rules + LLM.

    Queues a background Celery task to avoid Heroku's 30-second timeout.
    Use /futures/task/{task_id} to check status.
    """
    _check_admin_secret(secret, request=request)

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
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
    limit: int = Query(500, description="Max markets to re-check"),
    from_category: str = Query(None, description="Target a specific category instead of 'other'/NULL (e.g., 'basketball')"),
):
    """
    Re-run rules on markets to fix miscategorizations.

    By default targets 'other' and NULL markets. Use from_category to
    re-evaluate markets in a specific category (e.g., after adding new
    patterns that would reclassify some basketball markets as soccer).
    """
    _check_admin_secret(secret, request=request)

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
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
    limit: int = Query(5000, description="Max markets to process"),
    category: str = Query(None, description="Only regenerate tags for this category (e.g., 'crypto', 'politics')"),
):
    """
    Regenerate category_tags for existing markets using current keyword patterns.

    Use after adding new entity patterns to _TAG_KEYWORDS. Does NOT change
    llm_sport_category — only updates the subcategory tags used for grouping.
    """
    _check_admin_secret(secret, request=request)

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
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
    db: AsyncSession = Depends(get_db),
):
    """
    Get the current status of futures categorization.

    Returns counts of categorized vs uncategorized markets.
    """
    _check_admin_secret(secret, request=request)

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
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
    limit: int = Query(100, description="Max markets to return"),
    db: AsyncSession = Depends(get_db),
):
    """
    List uncategorized futures markets.

    Shows market names to help identify patterns that should be added.
    """
    _check_admin_secret(secret, request=request)

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
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
    limit: int = Query(100, description="Max markets to categorize"),
):
    """
    Force-categorize ALL uncategorized futures using LLM.

    Unlike /categorize which tries rules first, this forces LLM on every market.
    Queues a background Celery task to avoid Heroku's 30-second timeout.
    Use /futures/task/{task_id} to check status.
    """
    _check_admin_secret(secret, request=request)

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
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
    limit: int = Query(50, description="Max events to process per batch"),
    dry_run: bool = Query(False, description="Preview enrichment without saving"),
    force: bool = Query(False, description="Re-enrich events that already have metadata (for team normalization)"),
    db: AsyncSession = Depends(get_db_rw),
):
    """
    Enrich events with LLM-generated metadata (gender, level, league, importance).

    Finds events without metadata and uses LLM + heuristics to classify them.
    Results are cached in the database to avoid repeat API calls.

    Set force=true to re-enrich events that have metadata but need team name normalization.
    """
    _check_admin_secret(secret, request=request)

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
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
    db: AsyncSession = Depends(get_db),
):
    """
    Get the current status of event metadata enrichment.

    Returns counts of enriched vs un-enriched events.
    """
    _check_admin_secret(secret, request=request)

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
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
    limit: int = Query(50, description="Max markets to process per batch"),
    dry_run: bool = Query(False, description="Preview enrichment without saving"),
    db: AsyncSession = Depends(get_db_rw),
):
    """
    Enrich futures markets with LLM-generated metadata (gender, level, league).

    Works alongside the existing categorize endpoint but adds more detailed metadata.
    """
    _check_admin_secret(secret, request=request)

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
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
    db: AsyncSession = Depends(get_db),
):
    """
    Get the current status of futures metadata enrichment.

    Returns counts of enriched vs un-enriched markets.
    """
    _check_admin_secret(secret, request=request)

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


@router.get("/taxonomy/debug-redis")
async def taxonomy_debug_redis(
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
):
    """Check Redis markers set by taxonomy piggybacking code."""
    _check_admin_secret(secret, request=request)

    # #1197: route through the bounded, retry-wrapped helper instead of a raw
    # from_url (no timeout, no keepalive, no TLS-EOF retry).
    from app.tasks.redis_state import get_redis_client

    r = get_redis_client()
    return {
        "taxonomy_debug": r.get("bainluck:taxonomy_debug"),
        "llm_enrich_gate": r.get("bainluck:llm_enrich_gate"),
    }


# ---------------------------------------------------------------------------
# Odds API Quota Monitoring
# ---------------------------------------------------------------------------


@router.post("/taxonomy/backfill")
async def backfill_taxonomy(
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
    limit: int = Query(500, description="Max items to process"),
    sync: bool = Query(False, description="Run synchronously instead of via Celery"),
    db: AsyncSession = Depends(get_db_rw),
):
    """Trigger taxonomy tag computation for events and futures markets."""
    _check_admin_secret(secret, request=request)

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
    request: Request,
    task_id: str,
    secret: str = Query(None, description="Admin secret for authorization"),
):
    """Check taxonomy task status."""
    _check_admin_secret(secret, request=request)

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
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
):
    """Return the controlled tag vocabulary for inspection."""
    _check_admin_secret(secret, request=request)

    from app.utils.event_taxonomy import ALLOWED_TAGS

    return {
        namespace: sorted(values)
        for namespace, values in sorted(ALLOWED_TAGS.items())
    }


# Candidate cap for the futures classification census. Real defect candidates
# (sportless / stored-sport-tag disagreeing) number in the low single digits in
# production; this generous bound only exists so a pathological population can
# never load unbounded into the web process. Hitting it marks the census
# incomplete (YELLOW), never a silent truncation.
_FUTURES_CANDIDATE_CAP = 20000


async def _compute_classification_health(db: AsyncSession, now: datetime) -> dict:
    """Build the versioned ``classification_health`` envelope (UX-P001).

    Separates product-visible classification defects from backfill debt:

    * Events (the active scheduled/live population, ~1.7k) get a FULL census —
      every eligible event's inline authority (``compute_event_tags``) is
      compared against its persisted ``event_tags``.
    * Futures (open, ~120k) get a bounded, complete census: SQL narrows to the
      only runtime defect candidates — sportless rows (``llm_sport_category IS
      NULL`` → inline yields no sport → MISSING) and rows whose stored ``sport:``
      tag disagrees with ``llm_sport_category`` (AUTHORITY_DISAGREE). Because
      ``compute_market_tags`` only ever persists validated tags derived from the
      same source columns the inline authority reads, a non-candidate open row
      cannot carry an identity defect or an invalid tag under normal operation —
      it is clean by construction. Candidates are refined for eligibility with
      ``should_exclude_from_featured`` and fully re-run through the pure
      ``classify_record`` (which also catches INVALID / league / category
      disagreement within the candidate set).

    Fail-closed: any query error yields the UNKNOWN envelope, never GREEN.
    """
    from sqlalchemy import text
    from app.utils.classification_health import (
        KindCensus,
        RecordInput,
        evaluate,
        unknown_envelope,
    )
    from app.utils.event_taxonomy import compute_event_tags, compute_market_tags
    from app.utils.market_staleness import should_exclude_from_featured

    try:
        # ── Events: full census of the active population ──
        ev_stmt = (
            select(Event)
            .options(selectinload(Event.sport))
            .where(Event.status.in_(["scheduled", "live"]))
        )
        ev_result = await db.execute(ev_stmt)
        events = ev_result.scalars().all()

        event_records: list[RecordInput] = []
        for e in events:
            sport_key = e.sport.key if e.sport else ""
            inline = compute_event_tags(
                sport_key=sport_key,
                status=e.status,
                commence_time=e.commence_time,
                llm_importance=e.llm_importance,
                llm_gender=e.llm_gender,
                llm_level=e.llm_level,
                llm_league=e.llm_league,
                raw_ei=None,
                broadcast_info=getattr(e, "broadcast_info", None),
                highlight_result=None,
            )
            event_records.append(
                RecordInput(
                    kind="event",
                    id=e.id,
                    inline_tags=inline,
                    stored_tags=list(e.event_tags or []),
                )
            )
        events_census = KindCensus(
            eligible_total=len(event_records),
            verified=len(event_records),
            census_complete=True,
            records=event_records,
        )

        # ── Futures: bounded complete census over defect candidates ──
        fut_denom_row = (
            await db.execute(
                text("SELECT COUNT(*) AS n FROM futures_markets WHERE status = 'open'")
            )
        ).first()
        futures_eligible_total = int(fut_denom_row.n) if fut_denom_row else 0

        candidate_rows = (
            await db.execute(
                text(
                    """
                    SELECT id, name, llm_sport_category, llm_league, llm_gender,
                           llm_level, market_tier, category, status,
                           resolution_date, source, market_tags
                    FROM futures_markets
                    WHERE status = 'open'
                      AND (
                        llm_sport_category IS NULL
                        OR EXISTS (
                            SELECT 1
                            FROM jsonb_array_elements_text(market_tags) AS t
                            WHERE t LIKE 'sport:%'
                              AND t <> 'sport:' || llm_sport_category
                        )
                      )
                    ORDER BY id ASC
                    LIMIT :cap
                    """
                ),
                {"cap": _FUTURES_CANDIDATE_CAP},
            )
        ).all()

        futures_records: list[RecordInput] = []
        for row in candidate_rows:
            exclude_reason = should_exclude_from_featured(
                row.name, row.llm_sport_category, row.status, None, now
            )
            if exclude_reason is not None:
                # Ineligible (resolved / probability-extreme / title-stale) —
                # not product-visible, so not an actionable defect.
                continue
            inline = compute_market_tags(
                llm_sport_category=row.llm_sport_category,
                llm_league=row.llm_league,
                llm_gender=row.llm_gender,
                llm_level=row.llm_level,
                market_tier=row.market_tier,
                category=row.category,
                status=row.status,
                resolution_date=row.resolution_date,
                source=row.source,
            )
            stored = row.market_tags if isinstance(row.market_tags, list) else []
            futures_records.append(
                RecordInput(
                    kind="futures",
                    id=row.id,
                    inline_tags=inline,
                    stored_tags=list(stored),
                )
            )

        futures_complete = len(candidate_rows) < _FUTURES_CANDIDATE_CAP
        futures_census = KindCensus(
            eligible_total=futures_eligible_total,
            verified=futures_eligible_total if futures_complete else len(futures_records),
            census_complete=futures_complete,
            records=futures_records,
        )

        return evaluate(
            events=events_census,
            futures=futures_census,
            generated_at=now.isoformat(),
        )
    except Exception as exc:  # noqa: BLE001 — the verdict must fail closed, not 500
        return unknown_envelope(f"census_error:{type(exc).__name__}", now.isoformat())


@router.get("/taxonomy/dashboard")
async def taxonomy_dashboard(
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
    db: AsyncSession = Depends(get_db),
):
    """Tag distribution and content quality dashboard.

    Returns coverage stats, tag value distributions, and data quality signals
    for monitoring the event taxonomy system.
    """
    _check_admin_secret(secret, request=request)

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

    # UX-P001: the versioned verdict answering "is classification hurting the
    # product?" — separate from the raw stored-coverage (backfill-debt) fields
    # above, which are kept for compatibility.
    classification_health = await _compute_classification_health(db, now)

    return {
        "generated_at": now.isoformat(),
        "classification_health": classification_health,
        "event_coverage": event_coverage,
        "futures_coverage": futures_coverage,
        "event_tag_distribution": event_tag_distribution,
        "futures_tag_distribution": futures_tag_distribution,
        "sport_distribution": sport_distribution,
        "signal_distribution": signal_distribution,
    }


@router.post("/taxonomy/enrich")
async def enrich_taxonomy(
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
    event_limit: int = Query(50, description="Max events to enrich"),
    market_limit: int = Query(30, description="Max futures markets to enrich"),
):
    """Trigger LLM taxonomy enrichment for events and futures markets."""
    _check_admin_secret(secret, request=request)

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
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
    db: AsyncSession = Depends(get_db),
):
    """LLM enrichment coverage — events and markets with/without LLM-generated tags."""
    _check_admin_secret(secret, request=request)

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
