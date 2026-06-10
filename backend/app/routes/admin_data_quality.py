"""Admin endpoints for calibration, backfill, snapshot health, data quality, and cleanup."""


import os
import sys
from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from sqlalchemy import select, update, or_, text, func

from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy.orm import selectinload

from app.models import Event, FuturesMarket, FuturesOddsSnapshot

from app.models.models import WinProbSnapshot

from app.services import get_db, get_db_rw

from app.routes.admin_utils import _check_admin_secret


router = APIRouter()


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


@router.post("/snapshots/distribution")
async def trigger_snapshot_distribution(
    secret: str = Query(..., description="Admin secret for authorization"),
):
    """Queue a Celery task to compute snapshot distribution (too slow for a request)."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.tasks import compute_snapshot_distribution
    task = compute_snapshot_distribution.delay()
    return {"status": "queued", "task_id": str(task.id)}


@router.get("/snapshots/distribution")
async def get_snapshot_distribution(
    secret: str = Query(..., description="Admin secret for authorization"),
):
    """Read cached snapshot distribution from Redis (computed by Celery task)."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    import json as _json
    from app.tasks.redis_state import get_redis_client

    redis = get_redis_client()
    cached = redis.get("bainluck:snapshot_distribution")
    if not cached:
        raise HTTPException(
            status_code=404,
            detail="No cached result. POST /api/admin/snapshots/distribution to compute.",
        )
    return _json.loads(cached)


# =============================================================================
# Prediction Market → Event Matching
# =============================================================================


@router.post("/futures/groups/discover")
async def discover_market_groups(
    secret: str = Query(""),
    limit: int = Query(500, ge=1, le=5000),
    source: Optional[str] = Query(None, description="Filter by source (polymarket, kalshi, odds_api)"),
    dry_run: bool = Query(False),
    db: AsyncSession = Depends(get_db_rw),
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
    db: AsyncSession = Depends(get_db_rw),
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
    db: AsyncSession = Depends(get_db_rw),
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
    db: AsyncSession = Depends(get_db_rw),
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
    db: AsyncSession = Depends(get_db_rw),
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
    db: AsyncSession = Depends(get_db_rw),
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
    db: AsyncSession = Depends(get_db_rw),
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
    db: AsyncSession = Depends(get_db_rw),
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
    db: AsyncSession = Depends(get_db_rw),
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
    from app.tasks import celery_app
    result = celery_app.send_task(
        "app.tasks.backfill_winners",
        kwargs={"dry_run": dry_run, "limit": limit},
        queue="background",
    )
    return {"status": "queued", "task_id": result.id, "dry_run": dry_run, "limit": limit}


@router.post("/calibration/recompute")
async def trigger_calibration_recompute(secret: str = Query(...)):
    """Force recompute the public calibration cache."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")
    from app.tasks import celery_app
    result = celery_app.send_task("app.tasks.precompute_calibration_main", queue="background")
    return {"status": "queued", "task_id": result.id}


@router.post("/backfill-volume-direct")
async def backfill_volume_direct(
    secret: str = Query(...),
    series: str = Query("KXNHLGOAL"),
    db: AsyncSession = Depends(get_db_rw),
):
    """Directly populate volume for one series — runs in-request, no Celery."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")
    try:
        from app.services.kalshi_api import KalshiAPIService
        svc = KalshiAPIService()
        total_tickers = 0
        total_updated = 0
        total_pages = 0
        cursor = None
        for page in range(50):
            events, cursor = await svc.get_events(
                status="settled", series_ticker=series,
                with_nested_markets=True, limit=200, cursor=cursor,
            )
            if not events:
                break
            total_pages += 1
            tickers = []
            volumes = []
            for ev in events:
                for mkt in (ev.get("markets") or []):
                    tk = mkt.get("ticker", "")
                    vol = mkt.get("volume_fp")
                    if tk and vol is not None:
                        tickers.append(tk)
                        volumes.append(int(float(vol)))
            total_tickers += len(tickers)
            if tickers:
                r = await db.execute(text("""
                    UPDATE futures_outcomes fo
                    SET volume = v.vol
                    FROM unnest(CAST(:tickers AS text[]), CAST(:volumes AS int[])) AS v(tk, vol)
                    WHERE fo.external_id = v.tk
                """), {"tickers": tickers, "volumes": volumes})
                total_updated += r.rowcount
                await db.commit()
            if not cursor:
                break
        await svc.close()
        return {"series": series, "pages": total_pages,
                "tickers": total_tickers, "updated": total_updated}
    except Exception as e:
        return {"error": str(e), "type": type(e).__name__}


@router.post("/backfill-volume")
async def trigger_volume_backfill(secret: str = Query(...)):
    """Fast volume-only backfill — skips all phases except volume writes."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")
    from app.tasks import celery_app
    result = celery_app.send_task("app.tasks.backfill_kalshi_volume", queue="background")
    return {"status": "queued", "task_id": result.id}


@router.post("/backfill-trades")
async def trigger_trade_history_backfill(
    secret: str = Query(...),
    limit: int = Query(500),
):
    """Backfill snapshots from Kalshi trade history for outcomes missing cal_prob."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")
    from app.tasks import celery_app
    result = celery_app.send_task(
        "app.tasks.backfill_kalshi_trades",
        kwargs={"limit": limit},
        queue="background",
    )
    return {"status": "queued", "task_id": result.id, "limit": limit}


@router.post("/backfill-candlestick")
async def trigger_candlestick_backfill(
    secret: str = Query(...),
    limit: int = Query(500),
):
    """Backfill hourly snapshots from Kalshi candlestick API for sparse outcomes."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")
    from app.tasks import celery_app
    result = celery_app.send_task(
        "app.tasks.backfill_kalshi_candlestick",
        kwargs={"limit": limit},
        queue="background",
    )
    return {"status": "queued", "task_id": result.id, "limit": limit}


@router.post("/backfill-winners/score-resolution")
async def trigger_score_resolution(
    secret: str = Query(...),
):
    """Run ONLY the score-based resolution phases (Phase 1a).

    Tests the fix for pass2_guess re-resolution. Returns counts of
    resolved moneyline, spread, total, player prop, and period prop
    markets.
    """
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.tasks.backfill_winners import (
        _resolve_kalshi_from_scores,
        _resolve_kalshi_spread_total_from_scores,
        _resolve_kalshi_player_props_from_boxscore,
        _resolve_kalshi_period_props,
    )
    from app.tasks.base import get_task_session

    # Re-null misresolved non-moneyline outcomes first (#755)
    repair_stats = {"nulled": 0, "errors": []}
    try:
        async with get_task_session() as session:
            r = await session.execute(text("""
                UPDATE futures_outcomes fo
                SET is_winner = NULL, resolution_source = NULL
                FROM futures_markets fm
                WHERE fo.market_id = fm.id
                  AND fm.source = 'kalshi'
                  AND fo.resolution_source = 'game_score'
                  AND fm.external_id ~* '(teamtotal|spread|pts|reb|ast|3pt|blk|stl|hrr|hit|tb|ks|1hwinner|2hwinner|1htotal|2htotal|1hspread|mention|rfi|f5)'
            """))
            repair_stats["nulled"] = r.rowcount
            await session.commit()
    except Exception as e:
        repair_stats["errors"].append(str(e))

    score_stats = await _resolve_kalshi_from_scores()
    spread_total_stats = await _resolve_kalshi_spread_total_from_scores()
    player_prop_stats = await _resolve_kalshi_player_props_from_boxscore()
    period_prop_stats = await _resolve_kalshi_period_props()

    # Phase 2b: upgrade pass2_guess LOSERS → clean_resolution
    upgrade_stats = {"upgraded": 0, "errors": []}
    try:
        async with get_task_session() as session:
            r = await session.execute(text("""
                UPDATE futures_outcomes fo
                SET resolution_source = 'clean_resolution'
                FROM futures_markets fm
                WHERE fo.market_id = fm.id
                  AND fm.status = 'resolved'
                  AND fo.resolution_source = 'pass2_guess'
                  AND fo.is_winner = false
                  AND fo.current_probability <= 0.05
            """))
            upgrade_stats["upgraded"] = r.rowcount
            await session.commit()
    except Exception as e:
        upgrade_stats["errors"].append(str(e))

    return {
        "ml_repair": repair_stats,
        "guess_upgrade": upgrade_stats,
        "score_resolution": score_stats,
        "spread_total_resolution": spread_total_stats,
        "player_props": player_prop_stats,
        "period_props": period_prop_stats,
    }


@router.post("/backfill-winners/kalshi-markets")
async def trigger_kalshi_markets_backfill(
    secret: str = Query(...),
    limit: int = Query(10000),
):
    """Resolve Kalshi winners via the markets API (not events API).

    Much faster for old events where the per-event API returns empty
    markets. Pages through GET /markets?status=settled with cursor
    persistence, 1000 markets/page.
    """
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")
    from app.tasks.backfill_winners import _backfill_kalshi_winners_via_markets
    stats = await _backfill_kalshi_winners_via_markets(limit=limit)
    return stats


@router.post("/backfill-winners/kalshi-targeted")
async def trigger_kalshi_targeted(
    secret: str = Query(...),
    limit: int = Query(200),
):
    """Look up specific event tickers that need resolution via markets API.

    O(events needing work) not O(all settled events). Queries DB for
    event tickers with pass2_guess outcomes, then GET /markets?event_ticker=X
    for each to get the result field.
    """
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")
    from app.tasks.backfill_winners import _backfill_kalshi_winners_targeted
    stats = await _backfill_kalshi_winners_targeted(limit=limit)
    return stats


@router.post("/test-ticker-linking")
async def test_ticker_linking(
    secret: str = Query(...),
    limit: int = Query(20),
    db: AsyncSession = Depends(get_db),
):
    """Test name-based event linking for unlinked Kalshi markets."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")
    from app.utils.prediction_market_matching import extract_game_date_from_ticker
    from datetime import timedelta
    import re

    _MATCHUP_RE = re.compile(r'^(.+?)\s+(?:at|vs\.?|v)\s+(.+?)(?:\s*:\s*.+)?$', re.IGNORECASE)

    r = await db.execute(text("""
        SELECT fm.id, fm.external_id, fm.name
        FROM futures_markets fm
        WHERE fm.source = 'kalshi' AND fm.event_id IS NULL
          AND fm.name LIKE '%at%:%'
          AND EXISTS (SELECT 1 FROM futures_outcomes fo WHERE fo.market_id = fm.id AND fo.resolution_source = 'pass2_guess')
        ORDER BY random() LIMIT :lim
    """), {"lim": limit})
    markets = r.all()

    results = []
    for mkt in markets:
        game_date = extract_game_date_from_ticker(mkt.external_id)
        m = _MATCHUP_RE.match(mkt.name or "")
        if not game_date or not m:
            results.append({"name": (mkt.name or "")[:50], "parsed": False})
            continue

        team_a, team_b = m.group(1).strip(), m.group(2).strip()
        match = await db.execute(text("""
            SELECT e.id, e.home_team_name, e.away_team_name, e.home_score, e.away_score
            FROM events e
            WHERE e.commence_time BETWEEN :s AND :e
              AND e.status IN ('completed', 'closed')
              AND (
                  (LOWER(e.home_team_name) LIKE :ta AND LOWER(e.away_team_name) LIKE :tb)
                  OR (LOWER(e.home_team_name) LIKE :tb AND LOWER(e.away_team_name) LIKE :ta)
              )
            ORDER BY ABS(EXTRACT(EPOCH FROM e.commence_time - :d))
            LIMIT 1
        """), {"s": game_date - timedelta(hours=28), "e": game_date + timedelta(hours=28),
               "ta": f"%{team_a.lower()}%", "tb": f"%{team_b.lower()}%", "d": game_date})
        event = match.first()
        results.append({
            "name": (mkt.name or "")[:50],
            "date": str(game_date)[:10],
            "team_a": team_a, "team_b": team_b,
            "event_found": event is not None,
            "score": f"{event[3]}-{event[4]}" if event and event[3] else None,
        })

    matched = sum(1 for r in results if r.get("event_found"))
    return {"total": len(results), "matched": matched, "results": results}


@router.post("/run-lean-settled")
async def run_lean_settled(
    secret: str = Query(...),
    series: str = Query("KXNCAAMBTOTAL"),
    max_pages: int = Query(10),
):
    """Run the lean settled events scanner for ONE series inline (no Celery).
    Returns immediately with results — bypasses worker queue."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.services.kalshi_api import KalshiAPIService
    from app.tasks.redis_state import get_redis_client
    from app.tasks.base import get_task_session
    import asyncio

    rc = get_redis_client()
    ck = f"bainluck:settled_cursor:{series}"
    cursor = rc.get(ck)
    if cursor:
        cursor = cursor.decode() if isinstance(cursor, bytes) else cursor

    stats = {"pages": 0, "resolved": 0, "events": 0, "empty_pages": 0}
    service = KalshiAPIService()
    try:
        for _ in range(max_pages):
            try:
                events, cursor = await service.get_events(
                    status="settled", series_ticker=series,
                    with_nested_markets=True, limit=200, cursor=cursor)
            except Exception as e:
                stats["error"] = str(e)[:200]
                break
            stats["pages"] += 1
            if not events:
                break
            stats["events"] += len(events)
            yes_t, no_t = [], []
            for ev in events:
                for mkt in (ev.get("markets") or []):
                    tk = mkt.get("ticker", "")
                    rs = mkt.get("result")
                    if tk and rs is not None:
                        (yes_t if rs == "yes" else no_t).append(tk)

            page_resolved = 0
            async with get_task_session() as sess:
                if yes_t:
                    r = await sess.execute(text("""
                        UPDATE futures_outcomes SET is_winner=true, resolution_source='api_settlement'
                        WHERE external_id=ANY(:t) AND (resolution_source IS NULL OR resolution_source IN ('pass2_guess','binary_higher_wins','multi_max_prob','clean_resolution','pass2_loser','pass3_threshold'))
                    """), {"t": yes_t})
                    page_resolved += r.rowcount
                if no_t:
                    r = await sess.execute(text("""
                        UPDATE futures_outcomes SET is_winner=false, resolution_source='api_settlement'
                        WHERE external_id=ANY(:t) AND (resolution_source IS NULL OR resolution_source IN ('pass2_guess','binary_higher_wins','multi_max_prob','clean_resolution','pass2_loser','pass3_threshold'))
                    """), {"t": no_t})
                    page_resolved += r.rowcount
                await sess.commit()

            stats["resolved"] += page_resolved
            if page_resolved == 0:
                stats["empty_pages"] += 1
            else:
                stats["empty_pages"] = 0

            if not cursor:
                rc.delete(ck)
                break
            if stats["empty_pages"] >= max_pages:  # no early exit when testing
                rc.setex(ck, 86400 * 7, cursor)
                break
            rc.setex(ck, 86400 * 7, cursor)
            await asyncio.sleep(0.1)
    finally:
        await service.close()

    # Collect sample tickers for debugging
    if stats["resolved"] == 0 and stats["pages"] > 0:
        # Re-fetch first page to show sample tickers
        try:
            rc.delete(ck)
            events2, _ = await service.get_events(
                status="settled", series_ticker=series,
                with_nested_markets=True, limit=5)
            api_tickers = []
            for ev in (events2 or []):
                for mkt in (ev.get("markets") or []):
                    tk = mkt.get("ticker", "")
                    if tk:
                        api_tickers.append(tk)

            async with get_task_session() as sess:
                r = await sess.execute(text("""
                    SELECT fo.external_id FROM futures_outcomes fo
                    JOIN futures_markets fm ON fo.market_id = fm.id
                    WHERE fo.resolution_source = 'pass2_guess'
                      AND fm.source = 'kalshi'
                      AND fm.external_id LIKE :prefix
                    ORDER BY random() LIMIT 5
                """), {"prefix": series + "%"})
                db_tickers = [row[0] for row in r.fetchall()]

            stats["debug"] = {
                "api_sample": api_tickers[:5],
                "db_sample": db_tickers[:5],
            }
        except Exception:
            pass

    return {"series": series, **stats}


@router.get("/test-kalshi-market-endpoint")
async def test_kalshi_market_endpoint(
    secret: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Test if Kalshi GET /markets/{ticker} works for old settled tickers."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    r = await db.execute(text("""
        SELECT DISTINCT fo.external_id AS outcome_ticker,
               fm.external_id AS market_ticker
        FROM futures_outcomes fo
        JOIN futures_markets fm ON fo.market_id = fm.id
        WHERE fo.resolution_source = 'pass2_guess'
          AND fm.source = 'kalshi' AND fm.status = 'resolved'
          AND fm.event_id IS NULL
        ORDER BY random() LIMIT 5
    """))
    rows = r.fetchall()
    tickers = [(row[0], row[1]) for row in rows]  # (outcome_ticker, market_ticker)

    from app.services.kalshi_api import KalshiAPIService
    service = KalshiAPIService()
    results = []
    try:
        for outcome_ticker, market_ticker in tickers:
            # Try market ticker (the correct one for the API)
            market = await service.get_market(market_ticker)
            results.append({
                "outcome_ticker": outcome_ticker,
                "market_ticker": market_ticker,
                "found": market is not None,
                "result": market.get("result") if market else None,
                "status": market.get("status") if market else None,
            })
    finally:
        await service.close()

    return {"test_results": results}


@router.get("/redis-read")
async def redis_read(
    secret: str = Query(...),
    key: str = Query("bainluck:option_c_analysis"),
):
    """Read any bainluck: prefixed Redis key. For diagnostic scripts that
    save results to Redis for retrieval via the API."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")
    if not key.startswith("bainluck:"):
        raise HTTPException(status_code=400, detail="Key must start with bainluck:")
    import json as _json
    from app.tasks.redis_state import get_redis_client
    rc = get_redis_client()
    data = rc.get(key)
    if not data:
        raise HTTPException(status_code=404, detail=f"Key {key} not found")
    try:
        return _json.loads(data)
    except Exception:
        return {"raw": data.decode() if isinstance(data, bytes) else str(data)}


@router.get("/option-c-analysis")
async def option_c_analysis(
    secret: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Exact numbers for Option C: re-null clean_resolution winners that
    originated from pass2_guess and are blocking score-based resolution."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    queries = {}

    r = await db.execute(text("""
        SELECT COUNT(*) FROM futures_outcomes fo
        JOIN futures_markets fm ON fo.market_id = fm.id
        WHERE fo.resolution_source = 'clean_resolution'
          AND fo.is_winner = true
          AND fm.source = 'kalshi' AND fm.status = 'resolved'
    """))
    queries["kalshi_clean_winners_total"] = r.scalar()

    r = await db.execute(text("""
        SELECT COUNT(DISTINCT fm.id) FROM futures_markets fm
        JOIN futures_outcomes fo ON fo.market_id = fm.id
        WHERE fm.source = 'kalshi' AND fm.status = 'resolved'
          AND fo.resolution_source = 'clean_resolution' AND fo.is_winner = true
          AND EXISTS (
              SELECT 1 FROM futures_outcomes fo2
              WHERE fo2.market_id = fm.id
                AND fo2.resolution_source = 'pass2_guess'
          )
    """))
    queries["markets_with_clean_winner_AND_pass2guess_sibling"] = r.scalar()

    r = await db.execute(text("""
        SELECT COUNT(fo.id) FROM futures_outcomes fo
        JOIN futures_markets fm ON fo.market_id = fm.id
        JOIN events e ON fm.event_id = e.id
        WHERE fo.resolution_source = 'clean_resolution'
          AND fo.is_winner = true AND fm.source = 'kalshi'
          AND e.home_score IS NOT NULL AND e.status IN ('completed', 'closed')
    """))
    queries["clean_winners_with_game_scores"] = r.scalar()

    r = await db.execute(text("""
        SELECT COUNT(fo.id) FROM futures_outcomes fo
        JOIN futures_markets fm ON fo.market_id = fm.id
        JOIN events e ON fm.event_id = e.id
        WHERE fo.resolution_source = 'pass2_guess'
          AND fm.source = 'kalshi' AND fm.status = 'resolved'
          AND e.home_score IS NOT NULL AND e.status IN ('completed', 'closed')
          AND EXISTS (
              SELECT 1 FROM futures_outcomes fo2
              WHERE fo2.market_id = fm.id
                AND fo2.resolution_source = 'clean_resolution'
                AND fo2.is_winner = true
          )
    """))
    queries["pass2_guess_BLOCKED_by_clean_winner_sibling"] = r.scalar()

    r = await db.execute(text("""
        SELECT regexp_replace(fm.external_id, '-.*', ''), COUNT(fo.id)
        FROM futures_outcomes fo
        JOIN futures_markets fm ON fo.market_id = fm.id
        JOIN events e ON fm.event_id = e.id
        WHERE fo.resolution_source = 'clean_resolution'
          AND fo.is_winner = true AND fm.source = 'kalshi'
          AND e.home_score IS NOT NULL
        GROUP BY 1 ORDER BY 2 DESC LIMIT 15
    """))
    queries["clean_winners_with_scores_by_prefix"] = {
        row[0]: row[1] for row in r.fetchall()
    }

    r = await db.execute(text("""
        SELECT
            CASE
                WHEN fo.current_probability >= 0.95 THEN 'prob>=0.95'
                WHEN fo.current_probability >= 0.50 THEN 'prob 0.50-0.95'
                WHEN fo.current_probability IS NULL THEN 'prob NULL'
                ELSE 'prob<0.50 (LIKELY WRONG)'
            END, COUNT(*)
        FROM futures_outcomes fo
        JOIN futures_markets fm ON fo.market_id = fm.id
        WHERE fo.resolution_source = 'clean_resolution'
          AND fo.is_winner = true AND fm.source = 'kalshi'
        GROUP BY 1 ORDER BY 2 DESC
    """))
    queries["clean_winner_probability_distribution"] = {
        row[0]: row[1] for row in r.fetchall()
    }

    r = await db.execute(text("""
        SELECT fm.source, fo.is_winner, COUNT(*)
        FROM futures_outcomes fo
        JOIN futures_markets fm ON fo.market_id = fm.id
        WHERE fo.resolution_source = 'clean_resolution'
        GROUP BY 1, 2 ORDER BY 3 DESC
    """))
    queries["all_clean_resolution_by_source"] = [
        {"source": row[0], "is_winner": row[1], "count": row[2]}
        for row in r.fetchall()
    ]

    # What Option C would re-null: clean_resolution winners on markets
    # that have game scores AND still have pass2_guess siblings
    r = await db.execute(text("""
        SELECT COUNT(fo.id)
        FROM futures_outcomes fo
        JOIN futures_markets fm ON fo.market_id = fm.id
        JOIN events e ON fm.event_id = e.id
        WHERE fo.resolution_source = 'clean_resolution'
          AND fo.is_winner = true AND fm.source = 'kalshi'
          AND e.home_score IS NOT NULL AND e.status IN ('completed', 'closed')
          AND EXISTS (
              SELECT 1 FROM futures_outcomes fo2
              WHERE fo2.market_id = fm.id
                AND fo2.resolution_source IN ('pass2_guess', 'pass2_loser',
                    'binary_higher_wins', 'multi_max_prob')
          )
    """))
    queries["option_c_re_null_count"] = r.scalar()

    return queries


@router.get("/retrotag-pool")
async def retrotag_pool(
    secret: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Count outcomes that retro-tagging would discover on next run."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    r = await db.execute(text("""
        SELECT
            COUNT(*) FILTER (WHERE fo.resolution_source IS NULL
                AND fo.current_probability IS NOT NULL
                AND (fo.current_probability >= 0.95 OR fo.current_probability <= 0.05)
            ) AS retrotag_clean,
            COUNT(*) FILTER (WHERE fo.resolution_source IS NULL
                AND fo.is_winner = true
                AND (fo.current_probability IS NULL
                     OR (fo.current_probability > 0.05 AND fo.current_probability < 0.95))
            ) AS retrotag_guess,
            COUNT(*) FILTER (WHERE fo.resolution_source IS NULL) AS total_null_source
        FROM futures_outcomes fo
        JOIN futures_markets fm ON fo.market_id = fm.id
        WHERE fm.status = 'resolved'
    """))
    row = r.first()
    return {
        "retrotag_clean_candidates": row[0],
        "retrotag_guess_candidates": row[1],
        "total_null_source": row[2],
    }


@router.post("/backfill-settled/reset-cursors")
async def reset_settled_cursors(
    secret: str = Query(...),
):
    """Reset all settled events series cursors to start from page 1."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")
    from app.tasks.redis_state import get_redis_client
    rc = get_redis_client()
    deleted = 0
    for key in rc.scan_iter("bainluck:settled_cursor:*"):
        rc.delete(key)
        deleted += 1
    rc.delete("bainluck:settled_series_cursor")
    return {"cursors_deleted": deleted + 1}


@router.post("/backfill-winners/kalshi-api-only")
async def trigger_kalshi_api_only(
    secret: str = Query(...),
    limit: int = Query(500),
):
    """Run ONLY the Kalshi per-event API winner backfill (no other phases).

    Returns detailed stats including api_miss rate, so we can see how
    much of the backlog is actually reachable via the API.
    """
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")
    from app.tasks.backfill_winners import _backfill_kalshi_winners
    stats = await _backfill_kalshi_winners(limit=limit)
    return stats


@router.get("/box-score-gap")
async def box_score_gap(
    secret: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Count events missing box_score_data that have Kalshi player props."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    r = await db.execute(text("""
        SELECT COUNT(DISTINCT e.id) as events_needing,
               COUNT(DISTINCT fm.id) as markets_needing,
               COUNT(fo.id) as outcomes_needing
        FROM events e
        JOIN futures_markets fm ON fm.event_id = e.id
        JOIN futures_outcomes fo ON fo.market_id = fm.id
        WHERE e.status IN ('completed', 'closed')
          AND e.espn_id IS NOT NULL
          AND e.box_score_data IS NULL
          AND fm.source = 'kalshi'
          AND fm.status = 'resolved'
          AND fo.resolution_source = 'pass2_guess'
    """))
    row = r.first()

    r2 = await db.execute(text("""
        SELECT COUNT(DISTINCT e.id)
        FROM events e
        WHERE e.status IN ('completed', 'closed')
          AND e.espn_id IS NOT NULL
          AND e.box_score_data IS NULL
    """))
    total_missing = r2.scalar()

    return {
        "priority_events": row[0],
        "priority_markets": row[1],
        "priority_outcomes": row[2],
        "total_events_missing_box_score": total_missing,
    }


@router.post("/backfill-box-scores")
async def trigger_backfill_box_scores(
    secret: str = Query(...),
    limit: int = Query(500),
    priority: bool = Query(True, description="Prioritize events with Kalshi player props"),
):
    """Trigger ESPN box score backfill for events missing box_score_data."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")
    from app.tasks import celery_app
    result = celery_app.send_task(
        "app.tasks.backfill_box_scores",
        kwargs={"limit": limit, "priority_calibration": priority},
        queue="background",
    )
    return {"status": "queued", "task_id": str(result.id), "limit": limit, "priority_calibration": priority}


@router.get("/backfill-winners/unresolved-samples")
async def unresolved_linked_samples(
    secret: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Sample unresolved linked game outcomes for debugging no_parse."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    r = await db.execute(text("""
        SELECT fo.name AS outcome_name, fm.name AS market_name,
               fm.external_id AS ticker,
               e.home_team_name, e.away_team_name,
               e.home_score, e.away_score
        FROM futures_outcomes fo
        JOIN futures_markets fm ON fo.market_id = fm.id
        JOIN events e ON fm.event_id = e.id
        WHERE fo.resolution_source = 'pass2_guess'
          AND fm.source = 'kalshi'
          AND fm.status = 'resolved'
          AND e.status IN ('completed', 'closed')
          AND e.home_score IS NOT NULL
          AND e.away_score IS NOT NULL
        ORDER BY random()
        LIMIT 30
    """))
    samples = [
        {
            "outcome": row[0], "market": row[1], "ticker": row[2],
            "home": row[3], "away": row[4],
            "home_score": row[5], "away_score": row[6],
        }
        for row in r.fetchall()
    ]
    return {"samples": samples}


@router.post("/backfill-winners/probability-only")
async def trigger_probability_backfill(
    secret: str = Query(...),
    db: AsyncSession = Depends(get_db_rw),
):
    """Run the probability-based is_winner passes using the request DB session."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    stats = {"clean_w": 0, "clean_l": 0, "mutex_w": 0, "mutex_l": 0,
             "thresh_w": 0, "thresh_l": 0, "all_losers": 0, "errors": []}

    try:
        # Pass 1: Clean resolution (all at 0 or 1)
        r1 = await db.execute(text("""
            WITH cleanly_resolved AS (
                SELECT fm.id AS market_id
                FROM futures_markets fm
                JOIN futures_outcomes fo ON fo.market_id = fm.id
                WHERE fm.status = 'resolved'
                GROUP BY fm.id
                HAVING SUM(CASE WHEN fo.is_winner THEN 1 ELSE 0 END) = 0
                   AND COUNT(*) FILTER (
                       WHERE fo.current_probability >= 0.95
                          OR fo.current_probability <= 0.05
                   ) = COUNT(*)
                   AND COUNT(*) >= 1
            )
            UPDATE futures_outcomes fo
            SET is_winner = (fo.current_probability >= 0.95)
            FROM cleanly_resolved cr
            WHERE fo.market_id = cr.market_id
              AND fo.current_probability IS NOT NULL
            RETURNING fo.is_winner
        """))
        rows1 = r1.all()
        stats["clean_w"] = sum(1 for r in rows1 if r[0])
        stats["clean_l"] = sum(1 for r in rows1 if not r[0])
        await db.commit()

        # Pass 2: Mutually exclusive (prob sum 0.5-1.5), max wins
        r2 = await db.execute(text("""
            WITH stuck_markets AS (
                SELECT fm.id AS market_id,
                       MAX(fo.current_probability) AS max_prob
                FROM futures_markets fm
                JOIN futures_outcomes fo ON fo.market_id = fm.id
                WHERE fm.status = 'resolved'
                  AND fo.current_probability IS NOT NULL
                GROUP BY fm.id
                HAVING SUM(CASE WHEN fo.is_winner THEN 1 ELSE 0 END) = 0
                   AND SUM(fo.current_probability) BETWEEN 0.5 AND 1.5
                   AND MAX(fo.current_probability) > 0.05
                   AND COUNT(*) >= 2
                LIMIT 50000
            ),
            ranked AS (
                SELECT fo.id AS outcome_id,
                       ROW_NUMBER() OVER (
                           PARTITION BY fo.market_id
                           ORDER BY fo.current_probability DESC
                       ) AS rn
                FROM futures_outcomes fo
                JOIN stuck_markets sm ON sm.market_id = fo.market_id
                WHERE fo.current_probability IS NOT NULL
            )
            UPDATE futures_outcomes fo
            SET is_winner = (r.rn = 1)
            FROM ranked r
            WHERE fo.id = r.outcome_id
            RETURNING fo.is_winner
        """))
        rows2 = r2.all()
        stats["mutex_w"] = sum(1 for r in rows2 if r[0])
        stats["mutex_l"] = sum(1 for r in rows2 if not r[0])
        await db.commit()

        # Pass 3: Threshold markets (prob sum > 1.5), each > 0.50 wins
        r3 = await db.execute(text("""
            WITH threshold_markets AS (
                SELECT fm.id AS market_id
                FROM futures_markets fm
                JOIN futures_outcomes fo ON fo.market_id = fm.id
                WHERE fm.status = 'resolved'
                  AND fo.current_probability IS NOT NULL
                GROUP BY fm.id
                HAVING SUM(CASE WHEN fo.is_winner THEN 1 ELSE 0 END) = 0
                   AND SUM(fo.current_probability) > 1.5
                   AND COUNT(*) >= 2
                LIMIT 50000
            )
            UPDATE futures_outcomes fo
            SET is_winner = (fo.current_probability > 0.50)
            FROM threshold_markets tm
            WHERE fo.market_id = tm.market_id
              AND fo.current_probability IS NOT NULL
              AND fo.current_probability != 0.50
            RETURNING fo.is_winner
        """))
        rows3 = r3.all()
        stats["thresh_w"] = sum(1 for r in rows3 if r[0])
        stats["thresh_l"] = sum(1 for r in rows3 if not r[0])
        await db.commit()

        # Pass 4: All-losers (max prob <= 0.10)
        r4 = await db.execute(text("""
            WITH all_loser_markets AS (
                SELECT fm.id AS market_id
                FROM futures_markets fm
                JOIN futures_outcomes fo ON fo.market_id = fm.id
                WHERE fm.status = 'resolved'
                  AND fo.current_probability IS NOT NULL
                GROUP BY fm.id
                HAVING SUM(CASE WHEN fo.is_winner THEN 1 ELSE 0 END) = 0
                   AND MAX(fo.current_probability) <= 0.10
                   AND COUNT(*) >= 1
                LIMIT 50000
            )
            UPDATE futures_outcomes fo
            SET is_winner = false
            FROM all_loser_markets al
            WHERE fo.market_id = al.market_id
            RETURNING 1
        """))
        stats["all_losers"] = r4.rowcount
        await db.commit()

        # Pass 6: Binary markets (2 outcomes) — higher probability wins
        r6 = await db.execute(text("""
            WITH binary_unresolved AS (
                SELECT fm.id AS market_id
                FROM futures_markets fm
                JOIN futures_outcomes fo ON fo.market_id = fm.id
                WHERE fm.status = 'resolved'
                  AND fo.current_probability IS NOT NULL
                GROUP BY fm.id
                HAVING SUM(CASE WHEN fo.is_winner THEN 1 ELSE 0 END) = 0
                   AND COUNT(*) = 2
                   AND MAX(fo.current_probability) > 0.10
                   AND MAX(fo.current_probability) != MIN(fo.current_probability)
                LIMIT 50000
            )
            UPDATE futures_outcomes fo
            SET is_winner = (fo.current_probability > 0.50),
                resolution_source = 'binary_higher_wins'
            FROM binary_unresolved bu
            WHERE fo.market_id = bu.market_id
              AND fo.current_probability IS NOT NULL
            RETURNING fo.is_winner
        """))
        rows6 = r6.all()
        stats["binary_w"] = sum(1 for r in rows6 if r[0])
        stats["binary_l"] = sum(1 for r in rows6 if not r[0])
        await db.commit()

        # Pass 7: Multi-outcome (3+) — highest probability wins
        r7 = await db.execute(text("""
            WITH multi_unresolved AS (
                SELECT fm.id AS market_id,
                       MAX(fo.current_probability) AS max_prob
                FROM futures_markets fm
                JOIN futures_outcomes fo ON fo.market_id = fm.id
                WHERE fm.status = 'resolved'
                  AND fo.current_probability IS NOT NULL
                GROUP BY fm.id
                HAVING SUM(CASE WHEN fo.is_winner THEN 1 ELSE 0 END) = 0
                   AND COUNT(*) >= 3
                   AND MAX(fo.current_probability) > 0.10
                LIMIT 50000
            )
            UPDATE futures_outcomes fo
            SET is_winner = (fo.current_probability = mu.max_prob),
                resolution_source = 'multi_max_prob'
            FROM multi_unresolved mu
            WHERE fo.market_id = mu.market_id
              AND fo.current_probability IS NOT NULL
            RETURNING fo.is_winner
        """))
        rows7 = r7.all()
        stats["multi_w"] = sum(1 for r in rows7 if r[0])
        stats["multi_l"] = sum(1 for r in rows7 if not r[0])
        await db.commit()

    except Exception as e:
        stats["errors"].append(str(e))

    return {"status": "completed", "stats": stats}


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


@router.post("/backfill-polymarket-history/sync")
async def trigger_backfill_polymarket_history_sync(
    secret: str = Query(...),
    limit: int = Query(20, description="Max outcomes to process"),
    mode: str = Query("resolved_zero"),
):
    """Run Polymarket price history backfill synchronously (returns stats)."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")
    from app.tasks.polymarket import _backfill_polymarket_price_history
    stats = await _backfill_polymarket_price_history(limit=limit, mode=mode)
    return stats


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


@router.get("/debug-kalshi-settled")
async def debug_kalshi_settled(
    secret: str = Query(...),
    series: str = Query("KXNBAPTS"),
    db: AsyncSession = Depends(get_db),
):
    """Debug the settled events backfill — show what it finds."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.services.kalshi_api import KalshiAPIService
    service = KalshiAPIService()

    try:
        events, cursor = await service.get_events(
            status="settled", series_ticker=series,
            with_nested_markets=True, limit=5,
        )

        page_tickers = []
        for ev in events:
            for mkt in (ev.get("markets") or []):
                t = mkt.get("ticker", "")
                if t:
                    page_tickers.append(t)

        matched = await db.execute(
            text("""
                SELECT fo.id, fo.external_id, fo.opening_probability,
                       fo.calibration_probability,
                       fm.status AS market_status, fm.event_id,
                       (SELECT COUNT(*) FROM futures_odds_snapshots fos
                        WHERE fos.outcome_id = fo.id) AS snapshot_count
                FROM futures_outcomes fo
                JOIN futures_markets fm ON fo.market_id = fm.id
                WHERE fo.external_id = ANY(:tickers)
                  AND fm.source = 'kalshi'
                  AND fo.calibration_probability IS NULL
            """),
            {"tickers": page_tickers},
        )
        rows = [{
            "id": r.id, "ticker": r.external_id,
            "opening": float(r.opening_probability) if r.opening_probability else None,
            "cal": float(r.calibration_probability) if r.calibration_probability else None,
            "market_status": r.market_status,
            "event_id": r.event_id,
            "snapshot_count": r.snapshot_count,
        } for r in matched.fetchall()]

        return {
            "events": len(events),
            "page_tickers": page_tickers[:20],
            "matched_needing_cal": len(rows),
            "sample_matches": rows[:10],
        }
    finally:
        await service.close()


@router.post("/backfill-kalshi-settled")
async def trigger_backfill_kalshi_settled(
    secret: str = Query(...),
    limit: int = Query(5000, description="Max outcomes to process"),
):
    """Recover full price history from Kalshi settled events API."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")
    from app.tasks import celery_app
    result = celery_app.send_task("app.tasks.backfill_kalshi_settled", args=[limit])
    return {"status": "queued", "task_id": str(result.id), "limit": limit}


@router.post("/fix-commence-times")
async def fix_commence_times(secret: str = Query(...)):
    """Run golf + hockey commence_time fixes synchronously (no Celery)."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")
    from app.tasks.kalshi import _fix_golf_commence_times, _fix_hockey_commence_times
    golf = await _fix_golf_commence_times()
    hockey = await _fix_hockey_commence_times()
    return {"golf_fixed": golf, "hockey_fixed": hockey}


@router.get("/backfill-winners/kalshi-probe")
async def kalshi_settlement_probe(
    secret: str = Query(...),
    sample: int = Query(50, description="Number of tickers to probe"),
    db: AsyncSession = Depends(get_db),
):
    """Probe the Kalshi API for a sample of stuck markets to diagnose Phase 2 failures."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    try:
        from app.services.kalshi_api import KalshiAPIService
    except Exception as e:
        return {"error": f"import failed: {e}"}

    stuck = await db.execute(text("""
        SELECT fm.external_id, fm.category, fm.llm_sport_category
        FROM futures_markets fm
        JOIN futures_outcomes fo ON fo.market_id = fm.id
        WHERE fm.source = 'kalshi'
          AND fm.status = 'resolved'
          AND fo.current_probability IS NOT NULL
          AND fo.current_probability > 0.10
        GROUP BY fm.external_id, fm.category, fm.llm_sport_category
        HAVING SUM(CASE WHEN fo.is_winner THEN 1 ELSE 0 END) = 0
        ORDER BY RANDOM()
        LIMIT :sample
    """), {"sample": sample})
    tickers = stuck.all()

    if not tickers:
        return {"probed": 0, "message": "No stuck Kalshi markets found"}

    service = KalshiAPIService()
    results = {"api_miss": [], "no_result": [], "has_result": [], "errors": []}
    try:
        for row in tickers:
            ticker = row[0]  # external_id
            cat = row[2] or row[1]  # llm_sport_category or category
            try:
                event_data = await service.get_event(ticker)
                if not event_data:
                    results["api_miss"].append({"ticker": ticker, "category": cat})
                    continue

                nested = event_data.get("markets") or []
                any_result = any(m.get("result") is not None for m in nested)

                if any_result:
                    results["has_result"].append({
                        "ticker": ticker, "category": cat,
                        "n_markets": len(nested),
                        "sample_result": nested[0].get("result") if nested else None,
                    })
                else:
                    results["no_result"].append({
                        "ticker": ticker, "category": cat,
                        "n_markets": len(nested),
                    })
            except Exception as e:
                results["errors"].append({"ticker": ticker, "error": str(e)[:100]})
    finally:
        await service.close()

    return {
        "probed": len(tickers),
        "api_miss": len(results["api_miss"]),
        "no_result": len(results["no_result"]),
        "has_result": len(results["has_result"]),
        "errors": len(results["errors"]),
        "api_miss_samples": results["api_miss"][:10],
        "no_result_samples": results["no_result"][:10],
        "has_result_samples": results["has_result"][:5],
        "error_samples": results["errors"][:5],
        "by_category": _count_by_cat(results),
    }


def _count_by_cat(results: dict) -> dict:
    cats: dict = {}
    for bucket in ["api_miss", "no_result", "has_result"]:
        for item in results[bucket]:
            cat = item.get("category", "unknown")
            if cat not in cats:
                cats[cat] = {"api_miss": 0, "no_result": 0, "has_result": 0}
            cats[cat][bucket] += 1
    return cats


@router.get("/backfill-winners/golf-debug")
async def golf_cross_ref_debug(
    secret: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Debug the golf cross-reference: what DataGolf leaderboards exist, what Kalshi markets match."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    try:
        from app.routes.golf import _normalize_tournament
    except Exception as e:
        return {"error": f"import failed: {e}"}

    # DataGolf win markets
    dg = await db.execute(text("""
        SELECT name, external_id, market_metadata IS NOT NULL AS has_meta
        FROM futures_markets
        WHERE source = 'datagolf' AND status = 'resolved'
          AND external_id LIKE :pattern
        ORDER BY name
    """), {"pattern": "%:win"})

    dg_tournaments = []
    for r in dg.all():
        key = _normalize_tournament(r[0])
        dg_tournaments.append({"name": r[0], "ext": r[1], "key": key, "has_meta": r[2]})

    # Kalshi golf markets — full breakdown by ticker prefix
    kalshi = await db.execute(text("""
        SELECT fm.external_id, fm.name,
               COUNT(fo.id) AS n_outcomes
        FROM futures_markets fm
        JOIN futures_outcomes fo ON fo.market_id = fm.id
        WHERE fm.source = 'kalshi' AND fm.status = 'resolved'
          AND fm.llm_sport_category = 'golf'
        GROUP BY fm.id, fm.external_id, fm.name
    """))

    import re as _re
    kalshi_samples = []
    prefix_counts: dict[str, int] = {}
    prefix_outcomes: dict[str, int] = {}
    for r in kalshi.all():
        key = _normalize_tournament(r[0])
        ticker = r[1] or ""
        m = _re.match(r"(kx[a-z0-9]+)", ticker.lower())
        prefix = m.group(1) if m else "unknown"
        prefix_counts[prefix] = prefix_counts.get(prefix, 0) + 1
        prefix_outcomes[prefix] = prefix_outcomes.get(prefix, 0) + r[2]
        kalshi_samples.append({"name": r[0], "ticker": ticker, "key": key})

    # Show which keys overlap
    dg_keys = set(t["key"] for t in dg_tournaments)
    kalshi_keys = set(s["key"] for s in kalshi_samples)
    overlap = dg_keys & kalshi_keys

    return {
        "datagolf_count": len(dg_tournaments),
        "datagolf_tournaments": dg_tournaments,
        "kalshi_total_markets": len(kalshi_samples),
        "kalshi_by_prefix": sorted(
            [{"prefix": p, "markets": prefix_counts[p], "outcomes": prefix_outcomes[p]}
             for p in prefix_counts],
            key=lambda x: x["outcomes"], reverse=True,
        ),
        "matching_keys": sorted(overlap),
        "dg_only_keys": sorted(dg_keys - kalshi_keys),
        "kalshi_only_keys": sorted(kalshi_keys - dg_keys)[:10],
        "kalshi_ticker_samples": [s["ticker"] for s in kalshi_samples[:20]],
        "cross_ref_dry_run": await _golf_cross_ref_dry_run(db, _normalize_tournament),
    }


async def _golf_cross_ref_dry_run(db, _normalize_tournament):
    """Dry-run the golf cross-reference to show what would match."""
    from app.routes.golf import _match_key

    # Get DataGolf leaderboards
    dg = await db.execute(text("""
        SELECT name, market_metadata FROM futures_markets
        WHERE source = 'datagolf' AND status = 'resolved'
          AND external_id LIKE :p AND market_metadata IS NOT NULL
    """), {"p": "%:win"})

    tournament_lbs = {}
    for r in dg.all():
        meta = r[1] or {}
        lb = meta.get("leaderboard", [])
        if lb:
            key = _normalize_tournament(r[0])
            tournament_lbs[key] = lb

    # Get a sample Kalshi golf market and try to match
    kalshi = await db.execute(text("""
        SELECT fm.id, fm.name, fm.external_id
        FROM futures_markets fm
        WHERE fm.source = 'kalshi' AND fm.status = 'resolved'
          AND fm.llm_sport_category = 'golf'
        LIMIT 5
    """))

    results = []
    for row in kalshi.all():
        t_key = _normalize_tournament(row[1] or row[2] or "")
        lb = tournament_lbs.get(t_key)
        market_type = None
        lower = (row[1] or "").lower()
        if "winner" in lower or "champion" in lower:
            market_type = "win"
        elif "top 5" in lower:
            market_type = "top_5"
        elif "make" in lower and "cut" in lower:
            market_type = "make_cut"

        # Get outcome names
        outs = await db.execute(text(
            "SELECT name FROM futures_outcomes WHERE market_id = :mid LIMIT 5"
        ), {"mid": row[0]})
        outcome_names = [o[0] for o in outs.all()]

        matched_players = 0
        if lb:
            lb_keys = {_match_key(e.get("name", "")): e.get("position") for e in lb if e.get("name")}
            for oname in outcome_names:
                if _match_key(oname) in lb_keys:
                    matched_players += 1

        results.append({
            "market_name": row[1],
            "tournament_key": t_key,
            "market_type": market_type,
            "lb_found": lb is not None,
            "lb_size": len(lb) if lb else 0,
            "outcome_samples": outcome_names[:3],
            "matched_players": matched_players,
            "total_outcomes": len(outcome_names),
        })

    return {
        "tournaments_with_leaderboards": len(tournament_lbs),
        "tournament_keys": sorted(tournament_lbs.keys()),
        "samples": results,
    }


@router.post("/backfill-winners/golf-cross-ref")
async def trigger_golf_cross_ref(
    secret: str = Query(...),
):
    """Run the golf cross-reference synchronously and return stats."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.tasks.backfill_winners import _resolve_kalshi_golf_from_datagolf
    stats = await _resolve_kalshi_golf_from_datagolf()
    return stats


@router.post("/backfill-winners/golf-outrights")
async def trigger_golf_outrights(
    secret: str = Query(...),
):
    """Resolve DataGolf golf outcomes using historical outrights settlement data.

    Uses bet_outcome_numeric (1=won, 0=lost) from the DataGolf historical
    outrights API. More authoritative than leaderboard inference. Covers
    win, top_5, top_10, top_20, and make_cut markets across all tours.
    """
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.tasks.backfill_winners import _resolve_golf_from_historical_outrights
    stats = await _resolve_golf_from_historical_outrights()
    return stats


@router.get("/backfill-winners/stuck-diagnosis")
async def stuck_diagnosis(
    secret: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Lightweight diagnosis of stuck outcomes by source and bucket."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    await db.execute(text("SET LOCAL statement_timeout = '15s'"))
    result = await db.execute(text("""
        SELECT source, bucket, COUNT(*) AS markets, SUM(outcomes) AS outcomes FROM (
            SELECT fm.source,
                   CASE
                       WHEN MAX(fo.current_probability) > 0.95 THEN 'clean_but_unmarked'
                       WHEN MAX(fo.current_probability) BETWEEN 0.05 AND 0.95 THEN 'midrange'
                       WHEN MAX(fo.current_probability) <= 0.05 THEN 'all_near_zero'
                       ELSE 'null_prob'
                   END AS bucket,
                   COUNT(*) AS outcomes
            FROM futures_markets fm
            JOIN futures_outcomes fo ON fo.market_id = fm.id
            WHERE fm.status = 'resolved'
            GROUP BY fm.id, fm.source
            HAVING SUM(CASE WHEN fo.is_winner THEN 1 ELSE 0 END) = 0
        ) sub
        GROUP BY source, bucket
        ORDER BY source, markets DESC
    """))
    rows = [{"source": r[0], "bucket": r[1], "markets": r[2], "outcomes": r[3]} for r in result.all()]

    sample = await db.execute(text("""
        SELECT fm.source, fm.id, fm.name, fm.external_id,
               MAX(fo.current_probability) AS max_prob,
               COUNT(*) AS outcomes,
               fm.market_metadata->>'polymarket_event_id' AS poly_eid
        FROM futures_markets fm
        JOIN futures_outcomes fo ON fo.market_id = fm.id
        WHERE fm.status = 'resolved'
          AND fm.source IN ('polymarket', 'kalshi')
        GROUP BY fm.id
        HAVING SUM(CASE WHEN fo.is_winner THEN 1 ELSE 0 END) = 0
        ORDER BY COUNT(*) DESC
        LIMIT 10
    """))
    samples = [{"source": r[0], "id": r[1], "name": r[2][:80], "external_id": r[3][:50],
                "max_prob": float(r[4]) if r[4] else None, "outcomes": r[5],
                "poly_event_id": r[6]} for r in sample.all()]

    # Also check orphan outcomes: individual outcomes with is_winner=NULL
    # on markets that DO have other resolved outcomes
    orphan = await db.execute(text("""
        SELECT fm.source,
               COUNT(*) AS orphan_outcomes,
               COUNT(DISTINCT fm.id) AS affected_markets
        FROM futures_outcomes fo
        JOIN futures_markets fm ON fm.id = fo.market_id
        WHERE fm.status = 'resolved'
          AND fo.is_winner IS NULL
        GROUP BY fm.source
        ORDER BY orphan_outcomes DESC
    """))
    orphans = [{"source": r[0], "orphan_outcomes": r[1], "affected_markets": r[2]} for r in orphan.all()]

    # Sample orphan outcomes
    orphan_sample = await db.execute(text("""
        SELECT fm.source, fm.id, fm.name, fo.external_id AS outcome_ext,
               fo.name AS outcome_name, fo.current_probability
        FROM futures_outcomes fo
        JOIN futures_markets fm ON fm.id = fo.market_id
        WHERE fm.status = 'resolved'
          AND fo.is_winner IS NULL
        ORDER BY fm.id DESC
        LIMIT 10
    """))
    orphan_samples = [{"source": r[0], "market_id": r[1], "market": r[2][:60],
                       "outcome_ext": r[3][:50] if r[3] else None,
                       "outcome": r[4][:50] if r[4] else None,
                       "prob": float(r[5]) if r[5] else None} for r in orphan_sample.all()]

    # Reproduce the exact status endpoint logic to see the breakdown
    status_breakdown = await db.execute(text("""
        WITH market_status AS (
            SELECT fm.id, fm.source,
                BOOL_OR(fo.is_winner) AS has_winner,
                MAX(fo.current_probability) AS max_prob,
                BOOL_AND(fo.calibration_probability IS NULL
                         AND fo.opening_probability IS NULL) AS all_cal_null
            FROM futures_markets fm
            JOIN futures_outcomes fo ON fo.market_id = fm.id
            WHERE fm.status = 'resolved'
            GROUP BY fm.id, fm.source
        )
        SELECT source,
            COUNT(*) AS resolved,
            COUNT(*) FILTER (WHERE has_winner) AS real_winner,
            COUNT(*) FILTER (WHERE NOT has_winner AND max_prob <= 0.10) AS all_losers,
            COUNT(*) FILTER (WHERE NOT has_winner AND NOT all_cal_null AND max_prob > 0.10) AS needs_backfill,
            COUNT(*) FILTER (WHERE all_cal_null) AS untradeable
        FROM market_status
        GROUP BY source
        ORDER BY resolved DESC
    """))
    status_rows = [{"source": r[0], "resolved": r[1], "real_winner": r[2],
                    "all_losers": r[3], "needs_backfill": r[4], "untradeable": r[5]}
                   for r in status_breakdown.all()]

    # Sample untradeables — 5 per major category for diversity
    untrade_sample = await db.execute(text("""
        WITH ranked AS (
            SELECT fm.source, fm.id, fm.name, fm.external_id,
                   COALESCE(fm.llm_sport_category, fm.category) AS cat,
                   COUNT(*) AS outcomes,
                   fm.commence_time::text AS commence,
                   fm.volume, fm.volume_24h, fm.open_interest,
                   (SELECT COUNT(*) FROM futures_odds_snapshots fos
                    JOIN futures_outcomes fo2 ON fo2.id = fos.outcome_id
                    WHERE fo2.market_id = fm.id) AS total_snapshots,
                   ROW_NUMBER() OVER (
                       PARTITION BY fm.source, COALESCE(fm.llm_sport_category, fm.category)
                       ORDER BY RANDOM()
                   ) AS rn
            FROM futures_markets fm
            JOIN futures_outcomes fo ON fo.market_id = fm.id
            WHERE fm.status = 'resolved'
            GROUP BY fm.id
            HAVING BOOL_AND(fo.calibration_probability IS NULL AND fo.opening_probability IS NULL)
        )
        SELECT source, id, name, external_id, cat, outcomes, commence,
               volume, volume_24h, open_interest, total_snapshots
        FROM ranked
        WHERE rn <= 3
        ORDER BY source, cat
    """))
    untrade_samples = [{"source": r[0], "id": r[1], "name": r[2],
                        "external_id": r[3], "category": r[4],
                        "outcomes": r[5], "commence": r[6][:10] if r[6] else None,
                        "volume": r[7], "volume_24h": r[8],
                        "open_interest": r[9], "total_snapshots": r[10]}
                       for r in untrade_sample.all()]

    # Needs_backfill breakdown by category (lightweight)
    needs_cats = await db.execute(text("""
        WITH needs AS (
            SELECT fm.id, fm.source,
                   COALESCE(fm.llm_sport_category, fm.category, 'unknown') AS cat,
                   fm.name
            FROM futures_markets fm
            JOIN futures_outcomes fo ON fo.market_id = fm.id
            WHERE fm.status = 'resolved'
            GROUP BY fm.id, fm.source, COALESCE(fm.llm_sport_category, fm.category, 'unknown'), fm.name
            HAVING SUM(CASE WHEN fo.is_winner THEN 1 ELSE 0 END) = 0
               AND NOT BOOL_AND(fo.calibration_probability IS NULL AND fo.opening_probability IS NULL AND fm.source != 'datagolf')
               AND (MAX(fo.current_probability) IS NULL OR MAX(fo.current_probability) > 0.10)
        )
        SELECT source, cat, COUNT(*) AS markets,
               (array_agg(name ORDER BY id DESC))[1:3] AS sample_names,
               (array_agg(external_id ORDER BY id DESC))[1:3] AS sample_ext_ids
        FROM needs
        GROUP BY source, cat
        ORDER BY markets DESC
    """))
    needs_by_cat = [{"source": r[0], "category": r[1], "markets": r[2],
                     "samples": [n[:60] for n in (r[3] or [])],
                     "ext_ids": [e[:50] for e in (r[4] or [])]}
                    for r in needs_cats.all()]

    return {"buckets": rows, "sample_stuck": samples,
            "orphan_outcomes": orphans, "orphan_samples": orphan_samples,
            "status_breakdown": status_rows,
            "untradeable_samples": untrade_samples,
            "needs_backfill_by_category": needs_by_cat}


@router.post("/backfill-winners/datagolf-leaderboards")
async def trigger_datagolf_leaderboard_backfill(
    secret: str = Query(...),
):
    """Re-fetch full leaderboards for resolved DataGolf markets with truncated data.

    Fixes the regression from the leaderboard[:50] truncation: markets that
    were resolved before the full-leaderboard fix still have only 50 players,
    causing incorrect make_cut and placement resolution.
    """
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.tasks.backfill_winners import _backfill_datagolf_leaderboards
    stats = await _backfill_datagolf_leaderboards()
    return stats


@router.get("/backfill-winners/status")
async def backfill_winners_status(
    secret: str = Query(...),
    bust: bool = Query(False, description="Bypass cache"),
    db: AsyncSession = Depends(get_db),
):
    """Check how many markets still need is_winner backfill."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    import json as _json
    from app.tasks.redis_state import get_redis_client
    _cache_key = "bainluck:backfill_winners_status"
    if not bust:
        try:
            _rc = get_redis_client()
            _cached = _rc.get(_cache_key)
            if _cached:
                return _json.loads(_cached)
        except Exception:
            pass

    result = await db.execute(text("""
        WITH market_status AS (
            SELECT fm.id, fm.source,
                BOOL_OR(fo.is_winner) AS has_winner,
                MAX(fo.current_probability) AS max_prob,
                BOOL_AND(fo.calibration_probability IS NULL
                         AND fo.opening_probability IS NULL) AS all_cal_null
            FROM futures_markets fm
            JOIN futures_outcomes fo ON fo.market_id = fm.id
            WHERE fm.status = 'resolved'
            GROUP BY fm.id, fm.source
        )
        SELECT source,
            COUNT(*) AS resolved_markets,
            COUNT(*) FILTER (
                WHERE (has_winner OR (max_prob IS NOT NULL AND max_prob <= 0.10))
                  AND NOT (all_cal_null AND source != 'datagolf')
            ) AS has_winner,
            COUNT(*) FILTER (
                WHERE NOT has_winner
                  AND NOT (all_cal_null AND source != 'datagolf')
                  AND (max_prob IS NULL OR max_prob > 0.10)
            ) AS needs_backfill,
            COUNT(*) FILTER (
                WHERE all_cal_null AND source != 'datagolf'
            ) AS untradeable_excluded
        FROM market_status
        GROUP BY source
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

    _response = {
        "sources": [
            {"source": r.source, "resolved": r.resolved_markets,
             "has_winner": r.has_winner, "needs_backfill": r.needs_backfill,
             "untradeable_excluded": r.untradeable_excluded}
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
        "stuck_diagnosis": await _diagnose_stuck_winners(db),
    }
    try:
        _rc = get_redis_client()
        _rc.setex(_cache_key, 1800, _json.dumps(_response, default=str))
    except Exception:
        pass
    return _response


async def _diagnose_stuck_winners(db: AsyncSession) -> dict:
    """Why are is_winner backfills stuck? Categorize the blockers."""
    # Polymarket: check current_probability distribution on stuck markets
    poly_diag = await db.execute(text("""
        WITH stuck AS (
            SELECT fm.id AS market_id, fm.source
            FROM futures_markets fm
            WHERE fm.status = 'resolved'
              AND NOT EXISTS (
                  SELECT 1 FROM futures_outcomes fo
                  WHERE fo.market_id = fm.id AND fo.is_winner = true
              )
        ),
        outcome_status AS (
            SELECT s.source, fo.market_id,
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE fo.current_probability >= 0.95) AS at_one,
                COUNT(*) FILTER (WHERE fo.current_probability <= 0.05) AS at_zero,
                COUNT(*) FILTER (WHERE fo.current_probability IS NULL) AS null_prob,
                COUNT(*) FILTER (WHERE fo.current_probability > 0.05
                                   AND fo.current_probability < 0.95) AS midrange
            FROM stuck s
            JOIN futures_outcomes fo ON fo.market_id = s.market_id
            GROUP BY s.source, fo.market_id
        )
        SELECT source,
            COUNT(*) AS stuck_markets,
            COUNT(*) FILTER (WHERE at_one >= 1 AND midrange = 0 AND null_prob = 0) AS cleanly_resolved,
            COUNT(*) FILTER (WHERE midrange > 0) AS has_midrange_probs,
            COUNT(*) FILTER (WHERE null_prob > 0 AND midrange = 0) AS has_null_probs,
            COUNT(*) FILTER (WHERE total = at_zero AND at_one = 0) AS all_losers_no_winner,
            ROUND(AVG(total), 1) AS avg_outcomes
        FROM outcome_status
        GROUP BY source
        ORDER BY source
    """))
    poly_rows = poly_diag.all()

    # Sample stuck Polymarket markets with midrange probabilities
    sample = await db.execute(text("""
        WITH stuck AS (
            SELECT fm.id, fm.name, fm.source
            FROM futures_markets fm
            WHERE fm.status = 'resolved'
              AND fm.source IN ('polymarket', 'kalshi')
              AND NOT EXISTS (
                  SELECT 1 FROM futures_outcomes fo
                  WHERE fo.market_id = fm.id AND fo.is_winner = true
              )
            LIMIT 5000
        )
        SELECT s.source, s.name,
            ARRAY_AGG(
                fo.name || '=' || ROUND(fo.current_probability::numeric, 3)
                ORDER BY fo.current_probability DESC NULLS LAST
            ) AS outcome_probs
        FROM stuck s
        JOIN futures_outcomes fo ON fo.market_id = s.id
        WHERE fo.current_probability > 0.05 AND fo.current_probability < 0.95
        GROUP BY s.source, s.name, s.id
        ORDER BY RANDOM()
        LIMIT 10
    """))

    # Snapshot distribution for stuck midrange markets — how much trading actually happened?
    snap_dist = await db.execute(text("""
        WITH stuck AS (
            SELECT fm.id AS mid, fm.source
            FROM futures_markets fm
            JOIN futures_outcomes fo ON fo.market_id = fm.id
            WHERE fm.status = 'resolved' AND fo.current_probability IS NOT NULL
            GROUP BY fm.id, fm.source
            HAVING SUM(CASE WHEN fo.is_winner THEN 1 ELSE 0 END) = 0
               AND MAX(fo.current_probability) BETWEEN 0.10 AND 0.95
        ),
        outcome_snaps AS (
            SELECT st.source, fo.id AS oid,
                   fo.calibration_probability AS cp,
                   fo.opening_probability AS op,
                   (SELECT COUNT(*) FROM futures_odds_snapshots fos
                    WHERE fos.outcome_id = fo.id) AS snaps
            FROM stuck st JOIN futures_outcomes fo ON fo.market_id = st.mid
        )
        SELECT source, COUNT(*) AS total_outcomes,
               COUNT(*) FILTER(WHERE snaps = 0) AS snap_0,
               COUNT(*) FILTER(WHERE snaps BETWEEN 1 AND 2) AS snap_1_2,
               COUNT(*) FILTER(WHERE snaps BETWEEN 3 AND 5) AS snap_3_5,
               COUNT(*) FILTER(WHERE snaps BETWEEN 6 AND 20) AS snap_6_20,
               COUNT(*) FILTER(WHERE snaps BETWEEN 21 AND 100) AS snap_21_100,
               COUNT(*) FILTER(WHERE snaps > 100) AS snap_100_plus,
               COUNT(*) FILTER(WHERE cp IS NULL) AS cal_null,
               COUNT(*) FILTER(WHERE cp IS NOT NULL AND op IS NOT NULL AND cp = op) AS cal_eq_open,
               ROUND(AVG(snaps)::numeric, 1) AS avg_snaps,
               PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY snaps) AS median_snaps
        FROM outcome_snaps GROUP BY source ORDER BY source
    """))

    # Category breakdown for stuck markets
    cat_breakdown = await db.execute(text("""
        WITH stuck AS (
            SELECT fm.id, fm.source, fm.category, fm.llm_sport_category
            FROM futures_markets fm
            JOIN futures_outcomes fo ON fo.market_id = fm.id
            WHERE fm.status = 'resolved' AND fo.current_probability IS NOT NULL
            GROUP BY fm.id, fm.source, fm.category, fm.llm_sport_category
            HAVING SUM(CASE WHEN fo.is_winner THEN 1 ELSE 0 END) = 0
               AND MAX(fo.current_probability) BETWEEN 0.10 AND 0.95
        )
        SELECT source, COALESCE(llm_sport_category, category, 'null') AS cat,
               COUNT(*) AS markets
        FROM stuck GROUP BY source, cat ORDER BY source, markets DESC
    """))

    return {
        "by_source": [
            {
                "source": r.source,
                "stuck_markets": r.stuck_markets,
                "cleanly_resolved_but_missed": r.cleanly_resolved,
                "has_midrange_probs": r.has_midrange_probs,
                "has_null_probs": r.has_null_probs,
                "all_losers_no_winner": r.all_losers_no_winner,
                "avg_outcomes": float(r.avg_outcomes),
            }
            for r in poly_rows
        ],
        "midrange_samples": [
            {"source": r.source, "name": r.name, "probs": r.outcome_probs}
            for r in sample.all()
        ],
        "snapshot_distribution": [
            {
                "source": r.source,
                "total_outcomes": r.total_outcomes,
                "snap_0": r.snap_0,
                "snap_1_2": r.snap_1_2,
                "snap_3_5": r.snap_3_5,
                "snap_6_20": r.snap_6_20,
                "snap_21_100": r.snap_21_100,
                "snap_100_plus": r.snap_100_plus,
                "cal_null": r.cal_null,
                "cal_eq_open": r.cal_eq_open,
                "avg_snaps": float(r.avg_snaps) if r.avg_snaps else 0,
                "median_snaps": float(r.median_snaps) if r.median_snaps else 0,
            }
            for r in snap_dist.all()
        ],
        "category_breakdown": [
            {"source": r.source, "category": r.cat, "markets": r.markets}
            for r in cat_breakdown.all()
        ],
    }


@router.get("/calibration/resolution-status")
async def calibration_resolution_status(
    secret: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Quick status: how many markets can we resolve, by type?"""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    # Box score coverage
    bs = await db.execute(text("""
        SELECT
            COUNT(*) FILTER (WHERE espn_id IS NOT NULL) AS has_espn_id,
            COUNT(*) FILTER (WHERE box_score_data IS NOT NULL
                AND box_score_data->>'error' IS NULL) AS has_real_boxscore,
            COUNT(*) FILTER (WHERE box_score_data IS NOT NULL
                AND box_score_data->>'error' IS NOT NULL) AS marked_unavailable,
            COUNT(*) FILTER (WHERE espn_id IS NOT NULL AND box_score_data IS NULL) AS needs_backfill,
            COUNT(*) AS total
        FROM events WHERE status IN ('completed', 'closed')
    """))
    bs_row = bs.one()

    # Kalshi markets — simple counts by category
    res = await db.execute(text("""
        SELECT
            fm.llm_sport_category AS cat,
            COUNT(*) AS markets,
            COUNT(*) FILTER (WHERE fm.event_id IS NOT NULL) AS linked
        FROM futures_markets fm
        WHERE fm.source = 'kalshi' AND fm.status = 'resolved'
        GROUP BY fm.llm_sport_category
        ORDER BY markets DESC
    """))

    return {
        "espn_box_score_coverage": {
            "has_espn_id": bs_row.has_espn_id,
            "has_real_boxscore": bs_row.has_real_boxscore,
            "marked_unavailable": bs_row.marked_unavailable,
            "needs_backfill": bs_row.needs_backfill,
            "total_completed": bs_row.total,
        },
        "kalshi_by_category": [
            {"category": r.cat or "null", "markets": r.markets, "linked": r.linked}
            for r in res.all()
        ],
        "espn_unavailable_breakdown": await _espn_unavailable_breakdown(db),
    }


async def _espn_unavailable_breakdown(db):
    """Why are ESPN box scores unavailable? Retention or coverage?"""
    result = await db.execute(text("""
        SELECT s.key AS sport,
               COUNT(*) AS total,
               MIN(e.commence_time) AS earliest,
               MAX(e.commence_time) AS latest
        FROM events e
        JOIN sports s ON s.id = e.sport_id
        WHERE e.status IN ('completed', 'closed')
          AND e.espn_id IS NOT NULL
          AND e.box_score_data IS NOT NULL
          AND e.box_score_data->>'error' = 'not_available'
        GROUP BY s.key
        ORDER BY total DESC
    """))
    rows = result.all()
    return [
        {
            "sport": r.sport,
            "count": r.total,
            "earliest": str(r.earliest)[:10] if r.earliest else None,
            "latest": str(r.latest)[:10] if r.latest else None,
        }
        for r in rows
    ]


@router.get("/calibration/coverage-audit")
async def calibration_coverage_audit(
    secret: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Complete audit of what's in the DB vs what enters calibration.

    Shows every (source, category) combination with outcome counts at each
    filter gate, so we can see exactly what's being dropped and why.
    """
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    # Gate-by-gate funnel for futures outcomes
    futures_funnel = await db.execute(text("""
        SELECT
            fm.source,
            COALESCE(fm.llm_sport_category, fm.category, 'uncategorized') AS cat,
            COUNT(*) AS total_resolved_outcomes,
            COUNT(*) FILTER (
                WHERE fo.opening_probability IS NOT NULL
                  AND fo.opening_probability > 0 AND fo.opening_probability < 1
            ) AS has_opening_prob,
            COUNT(*) FILTER (
                WHERE fo.current_probability IS NOT NULL
                  AND (fo.current_probability >= 0.95 OR fo.current_probability <= 0.05)
            ) AS has_current_extreme,
            COUNT(*) FILTER (
                WHERE fo.opening_probability IS NOT NULL
                  AND fo.opening_probability > 0 AND fo.opening_probability < 1
                  AND fo.current_probability IS NOT NULL
                  AND (fo.current_probability >= 0.95 OR fo.current_probability <= 0.05)
            ) AS passes_both_gates,
            COUNT(*) FILTER (
                WHERE fo.opening_probability IS NULL
                  OR fo.opening_probability <= 0 OR fo.opening_probability >= 1
            ) AS dropped_no_opening,
            COUNT(*) FILTER (
                WHERE fo.opening_probability IS NOT NULL
                  AND fo.opening_probability > 0 AND fo.opening_probability < 1
                  AND (fo.current_probability IS NULL
                       OR (fo.current_probability > 0.05 AND fo.current_probability < 0.95))
            ) AS dropped_current_midrange,
            COUNT(*) FILTER (
                WHERE fo.is_winner = true
            ) AS has_is_winner
        FROM futures_markets fm
        JOIN futures_outcomes fo ON fo.market_id = fm.id
        WHERE fm.status = 'resolved'
        GROUP BY fm.source, cat
        ORDER BY total_resolved_outcomes DESC
    """))

    # Events table coverage (Odds API moneyline/spreads/totals)
    events_coverage = await db.execute(text("""
        SELECT
            s.key AS sport,
            COUNT(*) AS completed_events,
            COUNT(*) FILTER (
                WHERE COALESCE(e.closing_home_probability, e.opening_home_probability) IS NOT NULL
            ) AS has_moneyline,
            COUNT(*) FILTER (
                WHERE e.closing_home_spread IS NOT NULL
                  AND e.closing_home_spread_odds IS NOT NULL
                  AND e.closing_away_spread_odds IS NOT NULL
            ) AS has_spread,
            COUNT(*) FILTER (
                WHERE e.closing_over_under IS NOT NULL
                  AND e.closing_over_odds IS NOT NULL
                  AND e.closing_under_odds IS NOT NULL
            ) AS has_total,
            COUNT(*) FILTER (
                WHERE e.home_score IS NOT NULL AND e.away_score IS NOT NULL
            ) AS has_scores
        FROM events e
        JOIN sports s ON s.id = e.sport_id
        WHERE e.status IN ('completed', 'closed')
        GROUP BY s.key
        ORDER BY completed_events DESC
    """))

    # Per-bookmaker odds_snapshot coverage — lightweight estimate
    bookmaker_coverage = await db.execute(text("""
        SELECT
            (SELECT COUNT(*) FROM events WHERE status IN ('completed', 'closed')) AS completed_events,
            (SELECT COUNT(DISTINCT bookmaker) FROM odds_snapshots LIMIT 100) AS unique_bookmakers
    """))
    bm_row = bookmaker_coverage.one()

    return {
        "futures_funnel": [
            {
                "source": r.source,
                "category": r.cat,
                "total_resolved": r.total_resolved_outcomes,
                "has_opening_prob": r.has_opening_prob,
                "has_current_extreme": r.has_current_extreme,
                "passes_both_gates": r.passes_both_gates,
                "dropped_no_opening": r.dropped_no_opening,
                "dropped_current_midrange": r.dropped_current_midrange,
                "has_is_winner": r.has_is_winner,
                "drop_pct": round(100 * (1 - r.passes_both_gates / max(r.total_resolved_outcomes, 1)), 1),
            }
            for r in futures_funnel.all()
        ],
        "events_coverage": [
            {
                "sport": r.sport,
                "completed_events": r.completed_events,
                "has_moneyline": r.has_moneyline,
                "has_spread": r.has_spread,
                "has_total": r.has_total,
                "has_scores": r.has_scores,
                "moneyline_cal_points": r.has_moneyline * 2,
                "spread_cal_points": r.has_spread,
                "total_cal_points": r.has_total,
            }
            for r in events_coverage.all()
        ],
        "odds_snapshot_potential": {
            "completed_events": bm_row.completed_events,
            "unique_bookmakers": bm_row.unique_bookmakers,
            "estimated_per_book_cal_points": bm_row.completed_events * bm_row.unique_bookmakers * 2,
            "note": "Per-bookmaker closing lines NOT yet in calibration.",
        },
    }


@router.post("/calibration/tag-guesses")
async def tag_guesses(
    secret: str = Query(...),
    db: AsyncSession = Depends(get_db_rw),
):
    """Tag midrange untagged outcomes as pass2_guess."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    count = await db.execute(text("""
        SELECT COUNT(*) FROM futures_outcomes fo
        JOIN futures_markets fm ON fo.market_id = fm.id
        WHERE fm.status = 'resolved'
          AND fo.resolution_source IS NULL
          AND fo.is_winner = true
          AND (fo.current_probability IS NULL
               OR (fo.current_probability > 0.05 AND fo.current_probability < 0.95))
    """))
    should_match = count.scalar()

    try:
        r = await db.execute(text("""
            UPDATE futures_outcomes fo
            SET resolution_source = 'pass2_guess'
            WHERE fo.id IN (
                SELECT fo2.id FROM futures_outcomes fo2
                JOIN futures_markets fm ON fo2.market_id = fm.id
                WHERE fm.status = 'resolved'
                  AND fo2.resolution_source IS NULL
                  AND fo2.is_winner = true
                  AND (fo2.current_probability IS NULL
                       OR (fo2.current_probability > 0.05 AND fo2.current_probability < 0.95))
                LIMIT 50000
            )
        """))
        await db.commit()
        return {"should_match": should_match, "updated": r.rowcount, "error": None}
    except Exception as e:
        return {"should_match": should_match, "updated": 0, "error": str(e)}


@router.post("/calibration/test-retrotag")
async def test_retrotag(
    secret: str = Query(...),
    db: AsyncSession = Depends(get_db_rw),
):
    """Test the retroactive tagging query directly."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    # First count how many SHOULD match
    count = await db.execute(text("""
        SELECT COUNT(*) FROM futures_outcomes fo
        JOIN futures_markets fm ON fo.market_id = fm.id
        WHERE fm.status = 'resolved'
          AND fo.resolution_source IS NULL
          AND fo.current_probability IS NOT NULL
          AND (fo.current_probability >= 0.95 OR fo.current_probability <= 0.05)
    """))
    should_match = count.scalar()

    # Now try the actual update (small batch)
    try:
        r = await db.execute(text("""
            UPDATE futures_outcomes fo
            SET resolution_source = 'clean_resolution'
            WHERE fo.id IN (
                SELECT fo2.id FROM futures_outcomes fo2
                JOIN futures_markets fm ON fo2.market_id = fm.id
                WHERE fm.status = 'resolved'
                  AND fo2.resolution_source IS NULL
                  AND fo2.current_probability IS NOT NULL
                  AND (fo2.current_probability >= 0.95 OR fo2.current_probability <= 0.05)
                LIMIT 50000
            )
        """))
        await db.commit()
        return {
            "should_match": should_match,
            "actually_updated": r.rowcount,
            "error": None,
        }
    except Exception as e:
        return {
            "should_match": should_match,
            "actually_updated": 0,
            "error": str(e),
        }


@router.get("/calibration/decomposition")
async def calibration_decomposition(
    secret: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Full quality funnel by source × league × market_type × age.

    Shows N, opening derivation, resolution source breakdown, and
    whether we're capturing forward for each cell.
    """
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    result = await db.execute(text("""
        SELECT
            fm.source,
            COALESCE(fm.llm_sport_category, 'uncategorized') AS sport,
            COALESCE(
                CASE WHEN fm.llm_league IS NOT NULL THEN fm.llm_league
                     WHEN s.key IS NOT NULL THEN s.key
                     ELSE NULL END,
                'unknown'
            ) AS league,
            CASE
                WHEN fm.updated_at >= NOW() - INTERVAL '7 days' THEN '7d'
                WHEN fm.updated_at >= NOW() - INTERVAL '30 days' THEN '30d'
                WHEN fm.updated_at >= NOW() - INTERVAL '90 days' THEN '90d'
                ELSE '91d+'
            END AS age,
            COUNT(*) AS total_outcomes,
            COUNT(*) FILTER (
                WHERE fo.opening_probability IS NOT NULL
                  AND fo.opening_probability > 0 AND fo.opening_probability < 1
            ) AS has_opening,
            COUNT(*) FILTER (WHERE fo.is_winner = true) AS has_winner,
            COUNT(*) FILTER (WHERE fo.resolution_source IS NOT NULL) AS has_resolution_tag,
            COUNT(*) FILTER (WHERE fo.resolution_source = 'api_settlement') AS res_api,
            COUNT(*) FILTER (WHERE fo.resolution_source = 'game_score') AS res_score,
            COUNT(*) FILTER (WHERE fo.resolution_source = 'box_score') AS res_boxscore,
            COUNT(*) FILTER (WHERE fo.resolution_source = 'scoring_plays') AS res_plays,
            COUNT(*) FILTER (WHERE fo.resolution_source = 'leaderboard') AS res_leaderboard,
            COUNT(*) FILTER (WHERE fo.resolution_source = 'clean_resolution') AS res_clean,
            COUNT(*) FILTER (WHERE fo.resolution_source = 'pass2_guess') AS res_guess,
            COUNT(*) FILTER (WHERE fo.resolution_source = 'pass3_threshold') AS res_threshold,
            COUNT(*) FILTER (WHERE fo.resolution_source = 'settlement_sync') AS res_sync,
            COUNT(*) FILTER (WHERE fo.resolution_source IS NULL AND fo.is_winner = true) AS res_untagged,
            COUNT(*) FILTER (WHERE fo.opening_source = 'bid_ask_midpoint') AS open_bidask,
            COUNT(*) FILTER (WHERE fo.opening_source = 'first_snapshot') AS open_snapshot,
            COUNT(*) FILTER (WHERE fo.opening_source IS NULL AND fo.opening_probability IS NOT NULL) AS open_untagged
        FROM futures_outcomes fo
        JOIN futures_markets fm ON fm.id = fo.market_id
        LEFT JOIN events e ON e.id = fm.event_id
        LEFT JOIN sports s ON s.id = e.sport_id
        WHERE fm.status = 'resolved'
        GROUP BY fm.source, sport, league, age
        HAVING COUNT(*) >= 20
        ORDER BY total_outcomes DESC
    """))

    rows = result.all()
    cells = []
    for r in rows:
        authoritative = r.res_api + r.res_score + r.res_boxscore + r.res_plays + r.res_leaderboard + r.res_clean
        guess = r.res_guess + r.res_threshold
        guess_pct = round(100 * guess / max(r.has_winner, 1), 1) if r.has_winner > 0 else 0
        cells.append({
            "source": r.source,
            "sport": r.sport,
            "league": r.league,
            "age": r.age,
            "total": r.total_outcomes,
            "has_opening": r.has_opening,
            "has_winner": r.has_winner,
            "resolution": {
                "api_settlement": r.res_api,
                "game_score": r.res_score,
                "box_score": r.res_boxscore,
                "scoring_plays": r.res_plays,
                "leaderboard": r.res_leaderboard,
                "clean_resolution": r.res_clean,
                "pass2_guess": r.res_guess,
                "pass3_threshold": r.res_threshold,
                "settlement_sync": r.res_sync,
                "untagged": r.res_untagged,
            },
            "opening": {
                "bid_ask_midpoint": r.open_bidask,
                "first_snapshot": r.open_snapshot,
                "untagged": r.open_untagged,
            },
            "authoritative_pct": round(100 * authoritative / max(r.has_winner, 1), 1) if r.has_winner > 0 else 0,
            "guess_pct": guess_pct,
            "flag": guess_pct > 20,
        })

    # Summary stats
    total = sum(c["total"] for c in cells)
    total_winners = sum(c["has_winner"] for c in cells)
    total_auth = sum(c["resolution"]["api_settlement"] + c["resolution"]["game_score"] + c["resolution"]["box_score"] + c["resolution"]["scoring_plays"] + c["resolution"]["leaderboard"] + c["resolution"]["clean_resolution"] for c in cells)
    total_guess = sum(c["resolution"]["pass2_guess"] + c["resolution"]["pass3_threshold"] for c in cells)
    flagged = [c for c in cells if c["flag"]]

    # MCE per source × sport (for outcomes actually in calibration)
    mce_result = await db.execute(text("""
        SELECT
            fm.source,
            COALESCE(fm.llm_sport_category, 'uncategorized') AS sport,
            LEAST(FLOOR(COALESCE(fo.calibration_probability, fo.opening_probability) * 10)::int, 9) AS bucket,
            COUNT(*) AS n,
            SUM(CASE WHEN fo.is_winner THEN 1 ELSE 0 END) AS winners,
            AVG(COALESCE(fo.calibration_probability, fo.opening_probability)) AS avg_prob
        FROM futures_outcomes fo
        JOIN futures_markets fm ON fm.id = fo.market_id
        WHERE fm.status = 'resolved'
          AND fo.opening_probability IS NOT NULL
          AND fo.opening_probability > 0 AND fo.opening_probability < 1
          AND (fo.resolution_source IS NULL
               OR fo.resolution_source NOT IN ('pass2_guess', 'pass3_threshold'))
        GROUP BY fm.source, sport, bucket
        HAVING COUNT(*) >= 10
    """))
    mce_rows = mce_result.all()

    # Compute MCE per source × sport
    mce_cells: dict = {}
    for r in mce_rows:
        key = f"{r.source}|{r.sport}"
        if key not in mce_cells:
            mce_cells[key] = {"source": r.source, "sport": r.sport, "buckets": {}, "total_n": 0}
        mce_cells[key]["buckets"][r.bucket] = {
            "n": r.n, "winners": r.winners, "avg_prob": float(r.avg_prob),
        }
        mce_cells[key]["total_n"] += r.n

    mce_by_cell = []
    for key, cell in sorted(mce_cells.items(), key=lambda x: -x[1]["total_n"]):
        ae = 0; nb = 0
        for b in cell["buckets"].values():
            if b["n"] < 5:
                continue
            actual = b["winners"] / b["n"]
            ae += abs(actual - b["avg_prob"])
            nb += 1
        if nb > 0:
            mce_by_cell.append({
                "source": cell["source"],
                "sport": cell["sport"],
                "mce_pp": round(ae / nb * 100, 1),
                "n": cell["total_n"],
                "buckets_used": nb,
            })

    return {
        "summary": {
            "total_outcomes": total,
            "total_with_winner": total_winners,
            "authoritative_resolutions": total_auth,
            "guess_resolutions": total_guess,
            "flagged_cells": len(flagged),
        },
        "cells": cells[:100],
        "flagged": flagged[:20],
        "mce_by_source_sport": mce_by_cell[:30],
    }


@router.post("/backfill-calibration-prices")
async def trigger_calibration_prices(
    secret: str = Query(...),
):
    """Queue the calibration_probability computation as a background Celery task."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.tasks import celery_app
    result = celery_app.send_task("app.tasks.compute_calibration_prices")
    return {"status": "queued", "task_id": str(result.id)}


import re as _re

_MUTATING_RE = _re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|CREATE|GRANT|REVOKE|COPY)\b",
    _re.IGNORECASE,
)


@router.get("/query")
async def admin_query(
    sql: str = Query(..., description="SELECT-only SQL query"),
    secret: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Run a read-only SQL query and return JSON results.

    Admin-secret gated. Only SELECT statements allowed.
    1000 row limit, 30 second statement timeout.
    """
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    sql_stripped = sql.strip().rstrip(";")
    if _MUTATING_RE.search(sql_stripped):
        raise HTTPException(status_code=400, detail="Only SELECT queries are allowed")
    if not sql_stripped.upper().startswith("SELECT"):
        raise HTTPException(status_code=400, detail="Query must start with SELECT")

    try:
        has_limit = "limit" in sql_stripped.lower().split("order")[-1] or "fetch" in sql_stripped.lower()
        bounded = sql_stripped if has_limit else sql_stripped + " LIMIT 1000"
        await db.execute(text("SET LOCAL statement_timeout = '30s'"))
        result = await db.execute(text(bounded))
        columns = list(result.keys())
        rows = [dict(zip(columns, row)) for row in result.fetchall()]
        return {"columns": columns, "rows": rows, "count": len(rows)}
    except Exception as e:
        return {"error": str(e)[:500], "columns": [], "rows": [], "count": 0}


@router.get("/debug-cal-prob")
async def debug_cal_prob(
    secret: str = Query(...),
    outcome_id: int = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Debug why calibration_probability is NULL for a specific outcome."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    result = await db.execute(
        text("""
            SELECT fo.id, fo.external_id, fo.opening_probability,
                   fo.calibration_probability, fo.is_winner,
                   fm.status AS market_status, fm.event_id,
                   e.commence_time AS event_commence_time,
                   fm.commence_time AS market_commence_time,
                   (SELECT COUNT(*) FROM futures_odds_snapshots fos
                    WHERE fos.outcome_id = fo.id) AS total_snapshots,
                   (SELECT COUNT(*) FROM futures_odds_snapshots fos
                    WHERE fos.outcome_id = fo.id
                      AND fos.captured_at < e.commence_time) AS pre_game_snapshots,
                   (SELECT MIN(fos.captured_at) FROM futures_odds_snapshots fos
                    WHERE fos.outcome_id = fo.id) AS earliest_snapshot,
                   (SELECT MAX(fos.captured_at) FROM futures_odds_snapshots fos
                    WHERE fos.outcome_id = fo.id) AS latest_snapshot
            FROM futures_outcomes fo
            JOIN futures_markets fm ON fm.id = fo.market_id
            LEFT JOIN events e ON e.id = fm.event_id
            WHERE fo.id = :oid
        """),
        {"oid": outcome_id},
    )
    row = result.fetchone()
    if not row:
        return {"error": "outcome not found"}

    return {
        "outcome_id": row.id,
        "ticker": row.external_id,
        "opening_probability": float(row.opening_probability) if row.opening_probability else None,
        "calibration_probability": float(row.calibration_probability) if row.calibration_probability else None,
        "is_winner": row.is_winner,
        "market_status": row.market_status,
        "event_id": row.event_id,
        "event_commence_time": str(row.event_commence_time) if row.event_commence_time else None,
        "market_commence_time": str(row.market_commence_time) if row.market_commence_time else None,
        "total_snapshots": row.total_snapshots,
        "pre_game_snapshots": row.pre_game_snapshots,
        "earliest_snapshot": str(row.earliest_snapshot) if row.earliest_snapshot else None,
        "latest_snapshot": str(row.latest_snapshot) if row.latest_snapshot else None,
    }


@router.post("/debug-compute-cal-prob")
async def debug_compute_cal_prob(
    secret: str = Query(...),
    outcome_ids: str = Query("125766040,125766041"),
    db: AsyncSession = Depends(get_db_rw),
):
    """Run Part A calibration computation for specific outcomes and return results."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    ids = [int(x.strip()) for x in outcome_ids.split(",") if x.strip().isdigit()]

    result = await db.execute(
        text("""
            WITH needs_cal AS (
                SELECT fo.id AS outcome_id, e.commence_time,
                       fo.opening_probability
                FROM futures_outcomes fo
                JOIN futures_markets fm ON fm.id = fo.market_id
                JOIN events e ON e.id = fm.event_id
                WHERE fm.status = 'resolved'
                  AND fo.calibration_probability IS NULL
                  AND fm.event_id IS NOT NULL
                  AND e.commence_time IS NOT NULL
                  AND fo.id = ANY(:ids)
            ),
            closing AS (
                SELECT DISTINCT ON (nc.outcome_id)
                    nc.outcome_id,
                    fos.probability
                FROM needs_cal nc
                JOIN futures_odds_snapshots fos ON fos.outcome_id = nc.outcome_id
                WHERE fos.captured_at < nc.commence_time
                  AND fos.probability > 0 AND fos.probability < 1
                ORDER BY nc.outcome_id, fos.captured_at DESC
            ),
            final_price AS (
                SELECT nc.outcome_id,
                       COALESCE(cl.probability, nc.opening_probability) AS cal_prob
                FROM needs_cal nc
                LEFT JOIN closing cl ON cl.outcome_id = nc.outcome_id
            )
            SELECT fp.outcome_id, fp.cal_prob
            FROM final_price fp
            WHERE fp.cal_prob IS NOT NULL
        """),
        {"ids": ids},
    )
    rows = [{"outcome_id": r.outcome_id, "cal_prob": float(r.cal_prob)} for r in result.fetchall()]

    if rows:
        for row in rows:
            await db.execute(
                text("UPDATE futures_outcomes SET calibration_probability = :p WHERE id = :id"),
                {"p": row["cal_prob"], "id": row["outcome_id"]},
            )
        await db.commit()

    return {"outcomes_found": len(rows), "results": rows}


@router.post("/fix-market-status")
async def fix_market_status(
    secret: str = Query(...),
    outcome_ids: str = Query(...),
    db: AsyncSession = Depends(get_db_rw),
):
    """Fix market status to 'resolved' for markets containing specific outcomes."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    ids = [int(x.strip()) for x in outcome_ids.split(",") if x.strip().isdigit()]

    result = await db.execute(
        text("""
            UPDATE futures_markets
            SET status = 'resolved'
            WHERE id IN (
                SELECT DISTINCT fm.id
                FROM futures_outcomes fo
                JOIN futures_markets fm ON fo.market_id = fm.id
                WHERE fo.id = ANY(:ids)
                  AND fm.source = 'kalshi'
                  AND fm.status != 'resolved'
            )
        """),
        {"ids": ids},
    )
    await db.commit()
    return {"markets_resolved": result.rowcount}


@router.post("/fix-datagolf-market-status")
async def fix_datagolf_market_status(
    secret: str = Query(...),
    dry_run: bool = Query(False, description="Preview without writing"),
    db: AsyncSession = Depends(get_db_rw),
):
    """Resolve stuck DataGolf markets: transition closed -> resolved.

    DataGolf markets carry their own leaderboard metadata for resolution,
    so 'closed' is the wrong terminal status — the backfill_winners
    pipeline only processes status='resolved'.
    """
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    # Find all DataGolf markets stuck at 'closed'
    stuck = await db.execute(
        text("""
            SELECT fm.id, fm.name, fm.external_id, fm.status,
                   (SELECT COUNT(*) FROM futures_outcomes fo
                    WHERE fo.market_id = fm.id) AS outcome_count,
                   (SELECT COUNT(*) FROM futures_outcomes fo
                    WHERE fo.market_id = fm.id AND fo.is_winner IS NOT NULL) AS has_winner_count
            FROM futures_markets fm
            WHERE fm.source = 'datagolf'
              AND fm.status = 'closed'
            ORDER BY fm.id
        """)
    )
    rows = stuck.all()

    if not dry_run and rows:
        result = await db.execute(
            text("""
                UPDATE futures_markets
                SET status = 'resolved'
                WHERE source = 'datagolf'
                  AND status = 'closed'
            """)
        )
        await db.commit()
        updated = result.rowcount
    else:
        updated = 0

    return {
        "dry_run": dry_run,
        "stuck_markets": len(rows),
        "resolved": updated,
        "markets": [
            {
                "id": r.id,
                "name": r.name,
                "external_id": r.external_id,
                "outcomes": r.outcome_count,
                "has_winner": r.has_winner_count,
            }
            for r in rows
        ],
    }


@router.post("/sync-polymarket-resolved")
async def trigger_sync_polymarket_resolved(
    secret: str = Query(...),
):
    """Scan closed Polymarket events and update stuck market statuses to 'resolved'."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")
    from app.tasks import celery_app
    result = celery_app.send_task("app.tasks.sync_polymarket_resolved")
    return {"status": "queued", "task_id": str(result.id)}


@router.post("/backfill-espn-win-prob")
async def trigger_backfill_espn_win_prob(
    secret: str = Query(...),
    limit: int = Query(200),
):
    """Backfill ESPN win probability history for completed events with sparse snapshots.

    Processes ALL historical events with espn_id that have fewer than 10 ESPN
    win probability snapshots. No time-window limit -- targets 100% coverage.
    """
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")
    from app.tasks import celery_app
    result = celery_app.send_task(
        "app.tasks.backfill_espn_win_prob", args=[limit]
    )
    return {"status": "queued", "task_id": str(result.id), "limit": limit}


@router.get("/coverage-trends")
async def get_coverage_trends(
    secret: str = Query(...),
    days: int = Query(30, description="Number of days of history"),
):
    """Get daily coverage metric snapshots for tracking progress over time."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.tasks.redis_state import get_redis_client
    import json as _json

    rc = get_redis_client()
    all_snapshots = rc.hgetall("bainluck:coverage_snapshots")

    snapshots = []
    for date_key, snapshot_json in sorted(all_snapshots.items()):
        try:
            snap = _json.loads(snapshot_json)
            snapshots.append(snap)
        except Exception:
            pass

    if days and len(snapshots) > days:
        snapshots = snapshots[-days:]

    return {
        "days": len(snapshots),
        "snapshots": [
            {"date": s["date"], "totals": s.get("totals", {})}
            for s in snapshots
        ],
        "latest": snapshots[-1] if snapshots else None,
    }


@router.post("/coverage-trends/snapshot")
async def trigger_coverage_snapshot(
    secret: str = Query(...),
):
    """Take a coverage metrics snapshot right now."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")
    from app.tasks import celery_app
    result = celery_app.send_task("app.tasks.snapshot_coverage_metrics")
    return {"status": "queued", "task_id": str(result.id)}


@router.get("/debug-winner-backfill")
async def debug_winner_backfill(
    secret: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Debug: show what the Kalshi winner backfill query would select."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    result = await db.execute(
        text("""
            SELECT fm.external_id, COUNT(*) AS outcome_count,
                   COUNT(*) FILTER (WHERE fo.is_winner IS NULL) AS null_winners,
                   COUNT(*) FILTER (WHERE fo.is_winner = true) AS winners,
                   COUNT(*) FILTER (WHERE fo.is_winner = false) AS losers,
                   COUNT(*) FILTER (WHERE fo.resolution_source = 'api_settlement') AS api_settled,
                   COUNT(*) FILTER (WHERE fo.resolution_source IS NULL) AS null_source,
                   array_agg(DISTINCT fo.resolution_source) FILTER (WHERE fo.resolution_source IS NOT NULL) AS sources
            FROM futures_markets fm
            JOIN futures_outcomes fo ON fo.market_id = fm.id
            WHERE fm.source = 'kalshi'
              AND fm.status = 'resolved'
              AND fm.updated_at >= NOW() - INTERVAL '90 days'
              AND COALESCE(fo.resolution_source, '') != 'api_settlement'
            GROUP BY fm.external_id
            ORDER BY MAX(fm.updated_at) ASC
            LIMIT 10
        """)
    )
    rows = [
        {
            "ticker": r.external_id,
            "outcomes": r.outcome_count,
            "null_winners": r.null_winners,
            "winners": r.winners,
            "losers": r.losers,
            "api_settled": r.api_settled,
            "null_source": r.null_source,
            "sources": r.sources,
        }
        for r in result.fetchall()
    ]
    return {"tickers": len(rows), "sample": rows}


@router.get("/debug-phase3")
async def debug_phase3(
    secret: str = Query(...),
    ticker: str = Query("KXNBASPREAD-26MAY28OKCSAS-SAS26"),
    db: AsyncSession = Depends(get_db),
):
    """Debug Phase 3: check if a ticker would be updated."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    # Check what exists in DB for this ticker
    result = await db.execute(
        text("""
            SELECT fo.id, fo.external_id, fo.is_winner, fo.resolution_source,
                   fm.source, fm.external_id AS market_ext
            FROM futures_outcomes fo
            JOIN futures_markets fm ON fo.market_id = fm.id
            WHERE fo.external_id = :ticker
        """),
        {"ticker": ticker},
    )
    rows = [{"id": r.id, "ext": r.external_id, "winner": r.is_winner,
             "res_src": r.resolution_source, "fm_src": r.source, "mkt_ext": r.market_ext}
            for r in result.fetchall()]

    # Check what Phase 3's UPDATE would match
    match_result = await db.execute(
        text("""
            SELECT COUNT(*) FROM futures_outcomes
            WHERE external_id = :ticker
              AND COALESCE(resolution_source, '') != 'api_settlement'
              AND market_id IN (SELECT id FROM futures_markets WHERE source = 'kalshi')
        """),
        {"ticker": ticker},
    )
    would_update = match_result.scalar()

    return {"ticker": ticker, "db_rows": rows, "would_update": would_update}


@router.get("/task-metrics")
async def get_task_metrics(
    secret: str = Query(...),
    task_name: str = Query("kalshi_settled"),
):
    """Read task execution metrics from Redis."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    import json as _json
    from app.tasks.redis_state import get_redis_client

    try:
        rc = get_redis_client()
        key = f"bainluck:task_metrics:{task_name}"
        data = rc.hgetall(key)
        result = {}
        for k, v in data.items():
            if k == "last_result_summary":
                try:
                    result[k] = _json.loads(v)
                except Exception:
                    result[k] = v
            else:
                result[k] = v
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/debug-settled-precheck")
async def debug_settled_precheck(
    secret: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Run the settled events needs_work pre-check and return which series need work."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    # Discover series
    series_result = await db.execute(
        text("""
            SELECT DISTINCT regexp_replace(external_id, '-.*', '') AS series_prefix
            FROM futures_markets
            WHERE source = 'kalshi'
              AND status IN ('open', 'resolved')
              AND external_id ~ '^KX'
            ORDER BY 1
        """)
    )
    all_series = [r[0] for r in series_result.all()]

    # Check priority series + first 50 alphabetical
    priority = ["KXNBAGAME", "KXNBASPREAD", "KXNBAPTS", "KXNBA3PT",
                "KXNBAREB", "KXNBAAST", "KXNHLGAME", "KXMLBSTGAME"]
    check_list = priority + [s for s in all_series if s not in priority][:50]

    needing_work = []
    not_needing = []
    for candidate in check_list:
        needs = await db.execute(
            text("""
                SELECT EXISTS (
                    SELECT 1 FROM futures_markets fm
                    WHERE fm.source = 'kalshi'
                      AND fm.external_id LIKE :prefix || '%'
                      AND (
                          fm.status != 'resolved'
                          OR EXISTS (
                              SELECT 1 FROM futures_outcomes fo
                              WHERE fo.market_id = fm.id
                                AND COALESCE(fo.resolution_source, '') != 'api_settlement'
                          )
                      )
                    LIMIT 1
                )
            """),
            {"prefix": candidate},
        )
        if needs.scalar():
            needing_work.append(candidate)
        else:
            not_needing.append(candidate)

    return {
        "total_series": len(all_series),
        "needing_work": len(needing_work),
        "not_needing": len(not_needing),
        "series_needing_work": needing_work[:20],
        "series_not_needing": not_needing[:10],
    }


@router.post("/backfill-polymarket-winners")
async def trigger_backfill_polymarket_winners(
    secret: str = Query(...),
    limit: int = Query(10000),
):
    """Resolve Polymarket winners from Gamma API settlement data."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")
    from app.tasks import celery_app
    result = celery_app.send_task("app.tasks.backfill_polymarket_winners", args=[limit])
    return {"status": "queued", "task_id": str(result.id), "limit": limit}


@router.get("/audit-pass2-guess")
async def audit_pass2_guess(
    secret: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Deep audit of remaining pass2_guess outcomes."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    r = await db.execute(text("""
        SELECT fm.source, COUNT(*) as cnt
        FROM futures_outcomes fo
        JOIN futures_markets fm ON fo.market_id = fm.id
        WHERE fo.resolution_source = 'pass2_guess'
        GROUP BY fm.source ORDER BY 2 DESC
    """))
    by_source = {row[0]: row[1] for row in r.fetchall()}

    r = await db.execute(text("""
        SELECT
            regexp_replace(fm.external_id, E'-[0-9]{2}[A-Z]{3}[0-9]{2,4}.*', '') as prefix,
            fm.status, COUNT(*) as cnt
        FROM futures_outcomes fo
        JOIN futures_markets fm ON fo.market_id = fm.id
        WHERE fo.resolution_source = 'pass2_guess' AND fm.source = 'kalshi'
        GROUP BY 1, 2 ORDER BY 3 DESC LIMIT 40
    """))
    kalshi_prefixes = [
        {"prefix": row[0], "status": row[1], "count": row[2]}
        for row in r.fetchall()
    ]

    r = await db.execute(text("""
        SELECT COALESCE(fm.llm_sport_category, 'null'), fm.status, COUNT(*)
        FROM futures_outcomes fo
        JOIN futures_markets fm ON fo.market_id = fm.id
        WHERE fo.resolution_source = 'pass2_guess' AND fm.source = 'polymarket'
        GROUP BY 1, 2 ORDER BY 3 DESC LIMIT 20
    """))
    poly_categories = [
        {"category": row[0], "status": row[1], "count": row[2]}
        for row in r.fetchall()
    ]

    r = await db.execute(text("""
        SELECT fm.source, fm.status, COUNT(DISTINCT fm.id) as markets, COUNT(*) as outcomes
        FROM futures_outcomes fo
        JOIN futures_markets fm ON fo.market_id = fm.id
        WHERE fo.resolution_source = 'pass2_guess'
        GROUP BY 1, 2 ORDER BY 4 DESC
    """))
    status_breakdown = [
        {"source": row[0], "status": row[1], "markets": row[2], "outcomes": row[3]}
        for row in r.fetchall()
    ]

    r = await db.execute(text("""
        SELECT
            CASE WHEN fm.event_id IS NOT NULL THEN 'linked' ELSE 'no_event' END,
            COUNT(DISTINCT fm.id), COUNT(*)
        FROM futures_outcomes fo
        JOIN futures_markets fm ON fo.market_id = fm.id
        WHERE fo.resolution_source = 'pass2_guess' AND fm.source = 'kalshi'
        GROUP BY 1
    """))
    kalshi_linkage = {row[0]: {"markets": row[1], "outcomes": row[2]} for row in r.fetchall()}

    r = await db.execute(text("""
        SELECT fm.source, fo.is_winner, COUNT(*)
        FROM futures_outcomes fo
        JOIN futures_markets fm ON fo.market_id = fm.id
        WHERE fo.resolution_source = 'pass2_guess'
        GROUP BY 1, 2 ORDER BY 1, 2
    """))
    winner_dist = [
        {"source": row[0], "is_winner": row[1], "count": row[2]}
        for row in r.fetchall()
    ]

    r = await db.execute(text("""
        SELECT
            fm.source,
            CASE
                WHEN fo.calibration_probability >= 0.90 THEN 'cal>=0.90'
                WHEN fo.calibration_probability >= 0.50 THEN 'cal>=0.50'
                WHEN fo.calibration_probability IS NULL THEN 'cal_null'
                ELSE 'cal<0.50'
            END as bucket,
            COUNT(*)
        FROM futures_outcomes fo
        JOIN futures_markets fm ON fo.market_id = fm.id
        WHERE fo.resolution_source = 'pass2_guess' AND fo.is_winner = true
        GROUP BY 1, 2 ORDER BY 1, 3 DESC
    """))
    winner_accuracy = [
        {"source": row[0], "bucket": row[1], "count": row[2]}
        for row in r.fetchall()
    ]

    r = await db.execute(text("""
        SELECT
            fm.source,
            CASE
                WHEN fm.commence_time > NOW() - INTERVAL '30 days' THEN '0-30d'
                WHEN fm.commence_time > NOW() - INTERVAL '90 days' THEN '30-90d'
                WHEN fm.commence_time > NOW() - INTERVAL '180 days' THEN '90-180d'
                WHEN fm.commence_time > NOW() - INTERVAL '365 days' THEN '180-365d'
                ELSE '365d+'
            END as age_bucket,
            COUNT(*) as cnt
        FROM futures_outcomes fo
        JOIN futures_markets fm ON fo.market_id = fm.id
        WHERE fo.resolution_source = 'pass2_guess'
        GROUP BY 1, 2 ORDER BY 1, MIN(fm.commence_time)
    """))
    age_dist = [
        {"source": row[0], "age": row[1], "count": row[2]}
        for row in r.fetchall()
    ]

    r = await db.execute(text("""
        SELECT
            CASE WHEN e.home_score IS NOT NULL THEN 'has_scores' ELSE 'no_scores' END,
            COUNT(DISTINCT fm.id), COUNT(*)
        FROM futures_outcomes fo
        JOIN futures_markets fm ON fo.market_id = fm.id
        JOIN events e ON fm.event_id = e.id
        WHERE fo.resolution_source = 'pass2_guess' AND fm.source = 'kalshi'
        GROUP BY 1
    """))
    game_score_fixable = {
        row[0]: {"markets": row[1], "outcomes": row[2]} for row in r.fetchall()
    }

    return {
        "by_source": by_source,
        "total": sum(by_source.values()),
        "kalshi_prefixes": kalshi_prefixes,
        "poly_categories": poly_categories,
        "status_breakdown": status_breakdown,
        "kalshi_linkage": kalshi_linkage,
        "winner_distribution": winner_dist,
        "winner_accuracy_check": winner_accuracy,
        "age_distribution": age_dist,
        "game_score_fixable": game_score_fixable,
    }


@router.get("/calibration/price-audit")
async def calibration_price_audit(
    secret: str = Query(..., description="Admin secret for authorization"),
    category: str = Query("golf", description="Sport category to audit (golf, hockey, etc.)"),
    db: AsyncSession = Depends(get_db),
):
    """Audit calibration_probability accuracy for a given sport category.

    Diagnoses inverted calibration curves by showing:
    - Distribution of cal_prob values in 10% buckets
    - How many outcomes have cal_prob == opening_probability (Part A2 didn't improve)
    - Average divergence between cal_prob and opening_probability
    - Sample outcomes where cal_prob > 0.7 but is_winner = false (inverted bucket)
    """
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    # Total outcomes with calibration_probability set
    r = await db.execute(text("""
        SELECT COUNT(*)
        FROM futures_outcomes fo
        JOIN futures_markets fm ON fo.market_id = fm.id
        WHERE fm.llm_sport_category = :category
          AND fo.calibration_probability IS NOT NULL
    """), {"category": category})
    total_with_cal = r.scalar() or 0

    # How many have cal_prob == opening_probability
    r = await db.execute(text("""
        SELECT COUNT(*)
        FROM futures_outcomes fo
        JOIN futures_markets fm ON fo.market_id = fm.id
        WHERE fm.llm_sport_category = :category
          AND fo.calibration_probability IS NOT NULL
          AND fo.opening_probability IS NOT NULL
          AND fo.calibration_probability = fo.opening_probability
    """), {"category": category})
    cal_equals_opening = r.scalar() or 0

    # Distribution in 10% buckets
    r = await db.execute(text("""
        SELECT
            CASE
                WHEN fo.calibration_probability < 0.1 THEN '0-10%'
                WHEN fo.calibration_probability < 0.2 THEN '10-20%'
                WHEN fo.calibration_probability < 0.3 THEN '20-30%'
                WHEN fo.calibration_probability < 0.4 THEN '30-40%'
                WHEN fo.calibration_probability < 0.5 THEN '40-50%'
                WHEN fo.calibration_probability < 0.6 THEN '50-60%'
                WHEN fo.calibration_probability < 0.7 THEN '60-70%'
                WHEN fo.calibration_probability < 0.8 THEN '70-80%'
                WHEN fo.calibration_probability < 0.9 THEN '80-90%'
                ELSE '90-100%'
            END AS bucket,
            COUNT(*) AS cnt,
            SUM(CASE WHEN fo.is_winner THEN 1 ELSE 0 END) AS winners,
            ROUND(AVG(CASE WHEN fo.is_winner THEN 1.0 ELSE 0.0 END)::numeric, 3) AS win_rate
        FROM futures_outcomes fo
        JOIN futures_markets fm ON fo.market_id = fm.id
        WHERE fm.llm_sport_category = :category
          AND fo.calibration_probability IS NOT NULL
        GROUP BY 1
        ORDER BY MIN(fo.calibration_probability)
    """), {"category": category})
    distribution = [
        {"bucket": row[0], "count": row[1], "winners": row[2], "win_rate": float(row[3]) if row[3] is not None else None}
        for row in r.fetchall()
    ]

    # Average abs(cal_prob - opening_probability)
    r = await db.execute(text("""
        SELECT
            ROUND(AVG(ABS(fo.calibration_probability - fo.opening_probability))::numeric, 4) AS avg_shift,
            ROUND(MAX(ABS(fo.calibration_probability - fo.opening_probability))::numeric, 4) AS max_shift,
            ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (
                ORDER BY ABS(fo.calibration_probability - fo.opening_probability)
            )::numeric, 4) AS median_shift
        FROM futures_outcomes fo
        JOIN futures_markets fm ON fo.market_id = fm.id
        WHERE fm.llm_sport_category = :category
          AND fo.calibration_probability IS NOT NULL
          AND fo.opening_probability IS NOT NULL
    """), {"category": category})
    shift_row = r.fetchone()
    price_shift = {
        "avg": float(shift_row[0]) if shift_row and shift_row[0] is not None else None,
        "max": float(shift_row[1]) if shift_row and shift_row[1] is not None else None,
        "median": float(shift_row[2]) if shift_row and shift_row[2] is not None else None,
    }

    # Sample outcomes where cal_prob > 0.7 but is_winner = false (inverted bucket)
    r = await db.execute(text("""
        SELECT
            fo.id AS outcome_id,
            fo.name AS outcome_name,
            fm.name AS market_name,
            fm.source,
            fm.external_id,
            ROUND(fo.calibration_probability::numeric, 4) AS cal_prob,
            ROUND(fo.opening_probability::numeric, 4) AS opening_prob,
            ROUND(fo.current_probability::numeric, 4) AS current_prob,
            fm.commence_time,
            fm.llm_sport_category
        FROM futures_outcomes fo
        JOIN futures_markets fm ON fo.market_id = fm.id
        WHERE fm.llm_sport_category = :category
          AND fo.calibration_probability > 0.7
          AND fo.is_winner = false
          AND fo.calibration_probability IS NOT NULL
        ORDER BY fo.calibration_probability DESC
        LIMIT 20
    """), {"category": category})
    inverted_samples = [
        {
            "outcome_id": row[0],
            "outcome_name": row[1],
            "market_name": row[2],
            "source": row[3],
            "external_id": row[4],
            "cal_prob": float(row[5]) if row[5] is not None else None,
            "opening_prob": float(row[6]) if row[6] is not None else None,
            "current_prob": float(row[7]) if row[7] is not None else None,
            "commence_time": str(row[8]) if row[8] else None,
            "category": row[9],
        }
        for row in r.fetchall()
    ]

    # Outcomes with large divergence (> 0.40) between cal_prob and opening
    r = await db.execute(text("""
        SELECT COUNT(*)
        FROM futures_outcomes fo
        JOIN futures_markets fm ON fo.market_id = fm.id
        WHERE fm.llm_sport_category = :category
          AND fo.calibration_probability IS NOT NULL
          AND fo.opening_probability IS NOT NULL
          AND ABS(fo.calibration_probability - fo.opening_probability) > 0.40
    """), {"category": category})
    large_divergence_count = r.scalar() or 0

    return {
        "category": category,
        "total_with_calibration_probability": total_with_cal,
        "cal_equals_opening": cal_equals_opening,
        "cal_equals_opening_pct": round(cal_equals_opening / total_with_cal * 100, 1) if total_with_cal > 0 else None,
        "large_divergence_count": large_divergence_count,
        "price_shift_from_opening": price_shift,
        "distribution": distribution,
        "inverted_samples_high_cal_not_winner": inverted_samples,
    }


@router.get("/audit-clean-resolution-candidates")
async def audit_clean_resolution_candidates(
    secret: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Count markets that WOULD be fixed by the widened clean resolution guard.

    These are resolved markets where:
    - All outcomes have current_probability at extremes (>= 0.95 or <= 0.05)
    - But pass2_guess already set is_winner, blocking clean resolution
    """
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    r = await db.execute(text("""
        SELECT fm.source, COUNT(*) as market_count,
               SUM(outcome_count) as outcome_count
        FROM (
            SELECT fm.id, fm.source, COUNT(*) as outcome_count
            FROM futures_markets fm
            JOIN futures_outcomes fo ON fo.market_id = fm.id
            WHERE fm.status = 'resolved'
            GROUP BY fm.id, fm.source
            HAVING SUM(CASE WHEN fo.is_winner
                       AND fo.resolution_source IN
                           ('pass2_guess', 'binary_higher_wins', 'multi_max_prob')
                       THEN 1 ELSE 0 END) > 0
               AND SUM(CASE WHEN fo.is_winner
                       AND fo.resolution_source NOT IN
                           ('pass2_guess', 'binary_higher_wins', 'multi_max_prob')
                       THEN 1 ELSE 0 END) = 0
               AND COUNT(*) FILTER (
                   WHERE fo.current_probability >= 0.95
                      OR fo.current_probability <= 0.05
               ) = COUNT(*)
        ) sub
        JOIN futures_markets fm ON fm.id = sub.id
        GROUP BY fm.source
        ORDER BY 3 DESC
    """))
    candidates = [
        {"source": row[0], "markets": row[1], "outcomes": row[2]}
        for row in r.fetchall()
    ]
    return {"clean_resolution_candidates": candidates,
            "total_outcomes": sum(c["outcomes"] for c in candidates)}


@router.get("/calibration-mce-by-sport")
async def calibration_mce_by_sport(
    secret: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Lightweight per-sport MCE computation for calibration monitoring."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    result = await db.execute(text("""
        WITH cal_data AS (
            SELECT
                fo.calibration_probability,
                fo.is_winner,
                CASE
                    WHEN fo.calibration_probability < 0.05 THEN 0.025
                    WHEN fo.calibration_probability < 0.15 THEN 0.10
                    WHEN fo.calibration_probability < 0.25 THEN 0.20
                    WHEN fo.calibration_probability < 0.35 THEN 0.30
                    WHEN fo.calibration_probability < 0.45 THEN 0.40
                    WHEN fo.calibration_probability < 0.55 THEN 0.50
                    WHEN fo.calibration_probability < 0.65 THEN 0.60
                    WHEN fo.calibration_probability < 0.75 THEN 0.70
                    WHEN fo.calibration_probability < 0.85 THEN 0.80
                    WHEN fo.calibration_probability < 0.95 THEN 0.90
                    ELSE 0.975
                END AS bucket_mid,
                fm.llm_sport_category AS sport
            FROM futures_outcomes fo
            JOIN futures_markets fm ON fm.id = fo.market_id
            WHERE fm.status = 'resolved'
              AND fo.calibration_probability IS NOT NULL
              AND fo.is_winner IS NOT NULL
        ),
        buckets AS (
            SELECT sport, bucket_mid,
                   AVG(CASE WHEN is_winner THEN 1.0 ELSE 0.0 END) AS actual_rate,
                   COUNT(*) AS n
            FROM cal_data
            GROUP BY sport, bucket_mid
        )
        SELECT sport,
            ROUND((SUM(ABS(actual_rate - bucket_mid) * n) / SUM(n) * 100)::numeric, 2) AS mce_pp,
            SUM(n) AS total_outcomes
        FROM buckets
        GROUP BY sport
        ORDER BY mce_pp DESC
    """))
    sports = [
        {"sport": row.sport, "mce_pp": float(row.mce_pp), "outcomes": int(row.total_outcomes)}
        for row in result.fetchall()
    ]

    detail_sport = None
    for q_sport in ("hockey", "golf"):
        for s in sports:
            if s["sport"] == q_sport and s["mce_pp"] > 6:
                detail_sport = q_sport
                break
        if detail_sport:
            break

    detail_buckets = []
    if detail_sport:
        br = await db.execute(text("""
            WITH cal_data AS (
                SELECT
                    CASE
                        WHEN fo.calibration_probability < 0.05 THEN '00-05'
                        WHEN fo.calibration_probability < 0.15 THEN '05-15'
                        WHEN fo.calibration_probability < 0.25 THEN '15-25'
                        WHEN fo.calibration_probability < 0.35 THEN '25-35'
                        WHEN fo.calibration_probability < 0.45 THEN '35-45'
                        WHEN fo.calibration_probability < 0.55 THEN '45-55'
                        WHEN fo.calibration_probability < 0.65 THEN '55-65'
                        WHEN fo.calibration_probability < 0.75 THEN '65-75'
                        WHEN fo.calibration_probability < 0.85 THEN '75-85'
                        WHEN fo.calibration_probability < 0.95 THEN '85-95'
                        ELSE '95-100'
                    END AS bucket,
                    fo.is_winner
                FROM futures_outcomes fo
                JOIN futures_markets fm ON fm.id = fo.market_id
                WHERE fm.status = 'resolved'
                  AND fm.llm_sport_category = :sport
                  AND fo.calibration_probability IS NOT NULL
                  AND fo.is_winner IS NOT NULL
            )
            SELECT bucket,
                   ROUND(AVG(CASE WHEN is_winner THEN 1.0 ELSE 0.0 END) * 100, 1) AS actual_pct,
                   COUNT(*) AS n
            FROM cal_data
            GROUP BY bucket
            ORDER BY bucket
        """), {"sport": detail_sport})
        detail_buckets = [
            {"bucket": r.bucket, "actual_pct": float(r.actual_pct), "n": int(r.n)}
            for r in br.fetchall()
        ]

    bad_samples = []
    if detail_sport:
        sr = await db.execute(text("""
            SELECT fo.id, fo.name AS outcome_name, fm.name AS market_name,
                   fm.external_id, fm.event_id, fm.source,
                   fo.calibration_probability, fo.opening_probability,
                   fo.is_winner, fo.resolution_source,
                   e.commence_time AS event_commence,
                   fm.commence_time AS market_commence,
                   (SELECT COUNT(*) FROM futures_odds_snapshots fos WHERE fos.outcome_id = fo.id) AS snaps,
                   (SELECT COUNT(*) FROM futures_outcomes fo2
                    WHERE fo2.market_id = fm.id AND fo2.is_winner = true
                      AND fo2.resolution_source NOT IN ('pass2_guess','binary_higher_wins','multi_max_prob')
                   ) AS sibling_winners
            FROM futures_outcomes fo
            JOIN futures_markets fm ON fm.id = fo.market_id
            LEFT JOIN events e ON e.id = fm.event_id
            WHERE fm.status = 'resolved'
              AND fm.llm_sport_category = :sport
              AND fo.calibration_probability >= 0.75
              AND fo.calibration_probability < 0.85
              AND fo.is_winner IS NOT NULL
              AND NOT fo.is_winner
              AND fo.calibration_probability IS NOT NULL
            ORDER BY RANDOM()
            LIMIT 20
        """), {"sport": detail_sport})
        bad_samples = [
            {
                "outcome": r.outcome_name, "market": r.market_name,
                "external_id": r.external_id, "event_id": r.event_id,
                "source": r.source,
                "cal_prob": round(float(r.calibration_probability), 4),
                "opening_prob": round(float(r.opening_probability), 4) if r.opening_probability else None,
                "resolution_source": r.resolution_source,
                "snaps": r.snaps,
                "sibling_winners": r.sibling_winners,
                "event_commence": str(r.event_commence) if r.event_commence else None,
            }
            for r in sr.fetchall()
        ]
        null_ct = await db.execute(text("""
            SELECT
                COUNT(*) FILTER (WHERE e.commence_time IS NULL AND fm.event_id IS NOT NULL) AS linked_no_ct,
                COUNT(*) FILTER (WHERE fm.event_id IS NULL) AS unlinked,
                COUNT(*) FILTER (WHERE e.commence_time IS NOT NULL AND fm.event_id IS NOT NULL) AS linked_with_ct,
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE fm.source = 'kalshi') AS kalshi,
                COUNT(*) FILTER (WHERE fm.source = 'polymarket') AS polymarket,
                COUNT(*) FILTER (WHERE fm.source = 'datagolf') AS datagolf
            FROM futures_markets fm
            LEFT JOIN events e ON e.id = fm.event_id
            WHERE fm.status = 'resolved'
              AND fm.llm_sport_category = :sport
        """), {"sport": detail_sport})
        ct_row = null_ct.first()
        ct_debug = {
            "linked_no_commence_time": ct_row.linked_no_ct,
            "unlinked": ct_row.unlinked,
            "linked_with_commence_time": ct_row.linked_with_ct,
            "total": ct_row.total,
            "kalshi": ct_row.kalshi,
            "polymarket": ct_row.polymarket,
            "datagolf": ct_row.datagolf,
        } if ct_row else {}

    snapshot_debug = []
    if detail_sport:
        sd = await db.execute(text("""
            WITH cal_data AS (
                SELECT fo.calibration_probability, fo.is_winner,
                    fm.source,
                    CASE
                        WHEN fm.external_id LIKE 'KXNHLGAME%' THEN 'game'
                        WHEN fm.external_id LIKE 'KX%' AND fm.source = 'kalshi' THEN 'prop'
                        WHEN fm.source = 'polymarket' AND fm.event_id IS NOT NULL THEN 'pm_game'
                        ELSE 'pm_futures'
                    END AS market_type,
                    CASE
                        WHEN fo.calibration_probability < 0.05 THEN 0.025
                        WHEN fo.calibration_probability < 0.15 THEN 0.10
                        WHEN fo.calibration_probability < 0.25 THEN 0.20
                        WHEN fo.calibration_probability < 0.35 THEN 0.30
                        WHEN fo.calibration_probability < 0.45 THEN 0.40
                        WHEN fo.calibration_probability < 0.55 THEN 0.50
                        WHEN fo.calibration_probability < 0.65 THEN 0.60
                        WHEN fo.calibration_probability < 0.75 THEN 0.70
                        WHEN fo.calibration_probability < 0.85 THEN 0.80
                        WHEN fo.calibration_probability < 0.95 THEN 0.90
                        ELSE 0.975
                    END AS bucket_mid
                FROM futures_outcomes fo
                JOIN futures_markets fm ON fm.id = fo.market_id
                WHERE fm.status = 'resolved'
                  AND fm.llm_sport_category = :sport
                  AND fo.calibration_probability IS NOT NULL
                  AND fo.is_winner IS NOT NULL
            ),
            buckets AS (
                SELECT market_type, bucket_mid,
                       AVG(CASE WHEN is_winner THEN 1.0 ELSE 0.0 END) AS actual,
                       COUNT(*) AS n
                FROM cal_data
                GROUP BY market_type, bucket_mid
            )
            SELECT market_type,
                ROUND((SUM(ABS(actual - bucket_mid) * n) / SUM(n) * 100)::numeric, 2) AS mce,
                SUM(n) AS total
            FROM buckets
            GROUP BY market_type
            ORDER BY mce DESC
        """), {"sport": detail_sport})
        snapshot_debug = [
            {"type": r.market_type, "mce_pp": float(r.mce), "outcomes": int(r.total)}
            for r in sd.fetchall()
        ]

    bucket_breakdown = {}
    if detail_sport:
        bb = await db.execute(text("""
            WITH prop_data AS (
                SELECT fo.calibration_probability, fo.opening_probability,
                       fo.is_winner,
                       (SELECT COUNT(*) FROM futures_odds_snapshots fos WHERE fos.outcome_id = fo.id) AS snaps
                FROM futures_outcomes fo
                JOIN futures_markets fm ON fm.id = fo.market_id
                WHERE fm.status = 'resolved'
                  AND fm.llm_sport_category = :sport
                  AND fm.source = 'kalshi'
                  AND fm.external_id NOT LIKE 'KXNHLGAME%%'
                  AND fo.calibration_probability IS NOT NULL
                  AND fo.is_winner IS NOT NULL
            )
            SELECT
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE calibration_probability != opening_probability) AS cal_moved,
                COUNT(*) FILTER (WHERE calibration_probability != opening_probability AND NOT is_winner AND calibration_probability >= 0.65) AS cal_moved_high_losers,
                COUNT(*) FILTER (WHERE snaps <= 5) AS low_snap_le5,
                AVG(snaps)::numeric(10,1) AS avg_snaps,
                COUNT(*) FILTER (WHERE calibration_probability >= 0.65 AND NOT is_winner) AS high_cal_losers,
                COUNT(*) FILTER (WHERE calibration_probability >= 0.65) AS high_cal_total
            FROM prop_data
        """), {"sport": detail_sport})
        bb_row = bb.first()
        if bb_row:
            bucket_breakdown = {
                "total_props": bb_row.total,
                "cal_moved_from_opening": bb_row.cal_moved,
                "cal_moved_high_losers": bb_row.cal_moved_high_losers,
                "low_snap_le5": bb_row.low_snap_le5,
                "avg_snaps": float(bb_row.avg_snaps) if bb_row.avg_snaps else 0,
                "high_cal_losers": bb_row.high_cal_losers,
                "high_cal_total": bb_row.high_cal_total,
            }
        sim = await db.execute(text("""
            WITH prop_sim AS (
                SELECT fo.opening_probability AS p, fo.is_winner,
                    CASE
                        WHEN fo.opening_probability < 0.05 THEN 0.025
                        WHEN fo.opening_probability < 0.15 THEN 0.10
                        WHEN fo.opening_probability < 0.25 THEN 0.20
                        WHEN fo.opening_probability < 0.35 THEN 0.30
                        WHEN fo.opening_probability < 0.45 THEN 0.40
                        WHEN fo.opening_probability < 0.55 THEN 0.50
                        WHEN fo.opening_probability < 0.65 THEN 0.60
                        WHEN fo.opening_probability < 0.75 THEN 0.70
                        WHEN fo.opening_probability < 0.85 THEN 0.80
                        WHEN fo.opening_probability < 0.95 THEN 0.90
                        ELSE 0.975
                    END AS mid
                FROM futures_outcomes fo
                JOIN futures_markets fm ON fm.id = fo.market_id
                WHERE fm.status = 'resolved'
                  AND fm.llm_sport_category = :sport
                  AND fm.source = 'kalshi'
                  AND fm.external_id NOT LIKE 'KXNHLGAME%%'
                  AND fo.opening_probability IS NOT NULL
                  AND fo.is_winner IS NOT NULL
            ),
            b AS (
                SELECT mid, AVG(CASE WHEN is_winner THEN 1.0 ELSE 0.0 END) AS a, COUNT(*) AS n
                FROM prop_sim GROUP BY mid
            )
            SELECT ROUND((SUM(ABS(a - mid) * n) / SUM(n) * 100)::numeric, 2) AS mce FROM b
        """), {"sport": detail_sport})
        sim_row = sim.first()
        if sim_row and sim_row.mce is not None:
            bucket_breakdown["sim_mce_opening"] = float(sim_row.mce)
        vol_check = await db.execute(text("""
            SELECT
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE fm.volume > 0) AS has_volume,
                COUNT(*) FILTER (WHERE fm.volume > 10) AS vol_gt_10,
                COUNT(*) FILTER (WHERE fm.volume > 100) AS vol_gt_100,
                AVG(fm.volume) FILTER (WHERE fm.volume > 0) AS avg_vol,
                COUNT(*) FILTER (WHERE fo.calibration_probability >= 0.95
                    AND NOT fo.is_winner) AS top_bucket_losers,
                COUNT(*) FILTER (WHERE fo.calibration_probability >= 0.95
                    AND NOT fo.is_winner AND fm.volume > 0) AS top_losers_with_vol
            FROM futures_outcomes fo
            JOIN futures_markets fm ON fm.id = fo.market_id
            WHERE fm.status = 'resolved'
              AND fm.llm_sport_category = :sport
              AND fm.source = 'kalshi'
              AND fm.external_id NOT LIKE 'KXNHLGAME%%'
              AND fo.calibration_probability IS NOT NULL
              AND fo.is_winner IS NOT NULL
        """), {"sport": detail_sport})
        vr = vol_check.first()
        bucket_breakdown["volume_analysis"] = {
            "total_props": vr.total,
            "has_volume": vr.has_volume,
            "vol_gt_10": vr.vol_gt_10,
            "vol_gt_100": vr.vol_gt_100,
            "avg_vol_where_nonzero": round(float(vr.avg_vol), 1) if vr.avg_vol else 0,
            "top_bucket_losers": vr.top_bucket_losers,
            "top_losers_with_volume": vr.top_losers_with_vol,
        } if vr else {}

        orphan = await db.execute(text("""
            SELECT COUNT(*) AS cnt
            FROM futures_outcomes fo
            JOIN futures_markets fm ON fm.id = fo.market_id
            WHERE fm.status = 'resolved'
              AND fm.llm_sport_category = :sport
              AND fo.is_winner = false
              AND fo.resolution_source IS NULL
              AND EXISTS (
                  SELECT 1 FROM futures_outcomes fo2
                  WHERE fo2.market_id = fm.id AND fo2.is_winner = true
                    AND fo2.resolution_source NOT IN
                        ('pass2_guess', 'binary_higher_wins', 'multi_max_prob')
              )
        """), {"sport": detail_sport})
        orphan_row = orphan.scalar()
        bucket_breakdown["unresolved_in_partial_markets"] = orphan_row or 0

    return {
        "sports": sports, "detail_sport": detail_sport,
        "detail_buckets": detail_buckets, "bad_samples": bad_samples,
        "commence_time_debug": ct_debug if detail_sport else {},
        "snapshot_debug": snapshot_debug,
        "bucket_95_100_breakdown": bucket_breakdown,
    }


@router.get("/volume-stats")
async def volume_stats(
    secret: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Check how many outcomes have volume populated."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")
    try:
        r = await db.execute(text("""
            SELECT
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE fo.volume IS NOT NULL) AS has_volume,
                COUNT(*) FILTER (WHERE fo.volume = 0) AS vol_zero,
                COUNT(*) FILTER (WHERE fo.volume > 0) AS vol_positive,
                COUNT(*) FILTER (WHERE fo.volume IS NULL) AS vol_null,
                COUNT(*) FILTER (WHERE fo.external_id LIKE 'KX%%-%%-%%') AS submarket_ext,
                COUNT(*) FILTER (WHERE fo.external_id NOT LIKE 'KX%%-%%-%%') AS other_ext
            FROM futures_outcomes fo
            JOIN futures_markets fm ON fm.id = fo.market_id
            WHERE fm.source = 'kalshi' AND fm.status = 'resolved'
        """))
    except Exception as e:
        return {"error": str(e), "hint": "volume column may not exist — check if migration ran"}
    row = r.first()
    return {
        "total": row.total, "has_volume": row.has_volume,
        "vol_zero": row.vol_zero, "vol_positive": row.vol_positive,
        "vol_null": row.vol_null,
        "submarket_ext_format": row.submarket_ext,
        "other_ext_format": row.other_ext,
    }


@router.get("/calibration-90plus-losers")
async def calibration_90plus_losers(
    secret: str = Query(...),
    category: str = Query("hockey"),
    db: AsyncSession = Depends(get_db),
):
    """Show actual outcomes in the 90%+ bucket that are losing."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    r = await db.execute(text("""
        SELECT fo.name, fm.name AS market_name, fm.source,
               fm.external_id AS market_ext_id, fo.external_id AS outcome_ext_id,
               fo.opening_probability, fo.calibration_probability,
               fo.is_winner, fo.resolution_source,
               (SELECT COUNT(*) FROM futures_odds_snapshots fos WHERE fos.outcome_id = fo.id) AS snaps
        FROM futures_outcomes fo
        JOIN futures_markets fm ON fm.id = fo.market_id
        WHERE fm.status = 'resolved'
          AND COALESCE(fm.llm_sport_category, '') = :cat
          AND COALESCE(fo.calibration_probability, fo.opening_probability) >= 0.90
          AND fo.is_winner = false
          AND fo.opening_probability IS NOT NULL
          AND (fo.resolution_source IS NULL
               OR fo.resolution_source NOT IN ('pass2_guess', 'pass3_threshold',
                                                'did_not_play', 'withdrew'))
        ORDER BY RANDOM()
        LIMIT 25
    """), {"cat": category})
    samples = [
        {
            "outcome": row.name, "market": row.market_name[:50],
            "source": row.source, "mkt_ext": row.market_ext_id[:40],
            "outcome_ext": row.outcome_ext_id[:60] if row.outcome_ext_id else None,
            "open": round(float(row.opening_probability), 4) if row.opening_probability else None,
            "cal": round(float(row.calibration_probability), 4) if row.calibration_probability else None,
            "resolution": row.resolution_source, "snaps": row.snaps,
        }
        for row in r.fetchall()
    ]

    # Count totals
    r2 = await db.execute(text("""
        SELECT COUNT(*) AS total,
               COUNT(*) FILTER (WHERE fo.calibration_probability IS NULL) AS cal_null,
               COUNT(*) FILTER (WHERE fo.calibration_probability IS NOT NULL
                   AND fo.calibration_probability >= 0.90) AS cal_high,
               COUNT(*) FILTER (WHERE fo.calibration_probability IS NULL
                   AND fo.opening_probability >= 0.90) AS cal_null_open_high
        FROM futures_outcomes fo
        JOIN futures_markets fm ON fm.id = fo.market_id
        WHERE fm.status = 'resolved'
          AND COALESCE(fm.llm_sport_category, '') = :cat
          AND COALESCE(fo.calibration_probability, fo.opening_probability) >= 0.90
          AND fo.is_winner = false
          AND fo.opening_probability IS NOT NULL
          AND (fo.resolution_source IS NULL
               OR fo.resolution_source NOT IN ('pass2_guess', 'pass3_threshold',
                                                'did_not_play', 'withdrew'))
    """), {"cat": category})
    counts = r2.first()

    return {
        "category": category,
        "total_90plus_losers": counts.total,
        "breakdown": {
            "cal_null_open_high": counts.cal_null_open_high,
            "cal_high": counts.cal_high,
            "cal_null_total": counts.cal_null,
        },
        "samples": samples,
    }


@router.post("/datagolf-retag")
async def datagolf_retag(
    secret: str = Query(...),
    db: AsyncSession = Depends(get_db_rw),
):
    """Retag DataGolf non-authoritative losers as did_not_play."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    # Fix: restore multi_max_prob winners that were wrongly retagged
    fix = await db.execute(text("""
        UPDATE futures_outcomes fo
        SET resolution_source = 'multi_max_prob'
        FROM futures_markets fm
        WHERE fo.market_id = fm.id
          AND fm.source = 'datagolf'
          AND fo.is_winner = true
          AND fo.resolution_source = 'did_not_play'
    """))

    # Revert wrongly-tagged did_not_play outcomes: those that ARE on the
    # leaderboard (with CUT/MC/WD position) should be 'leaderboard', not
    # 'did_not_play'. Also revert outcomes in markets without leaderboards
    # — those should have NULL resolution_source (we can't determine status).
    revert_on_lb = await db.execute(text("""
        UPDATE futures_outcomes fo
        SET resolution_source = 'leaderboard'
        FROM futures_markets fm
        WHERE fo.market_id = fm.id
          AND fm.source = 'datagolf'
          AND fo.resolution_source = 'did_not_play'
          AND fo.is_winner = false
          AND fm.market_metadata->'leaderboard' IS NOT NULL
          AND jsonb_typeof(fm.market_metadata->'leaderboard') = 'array'
          AND EXISTS (
              SELECT 1
              FROM jsonb_array_elements(fm.market_metadata->'leaderboard') AS lb
              WHERE lb->>'dg_id' = SUBSTRING(fo.external_id FROM 4)
          )
    """))
    revert_no_lb = await db.execute(text("""
        UPDATE futures_outcomes fo
        SET resolution_source = NULL
        FROM futures_markets fm
        WHERE fo.market_id = fm.id
          AND fm.source = 'datagolf'
          AND fo.resolution_source = 'did_not_play'
          AND fo.is_winner = false
          AND (fm.market_metadata IS NULL
               OR fm.market_metadata->'leaderboard' IS NULL
               OR jsonb_typeof(fm.market_metadata->'leaderboard') != 'array')
    """))
    await db.commit()
    return {
        "restored_winners": fix.rowcount,
        "reverted_on_leaderboard": revert_on_lb.rowcount,
        "reverted_no_leaderboard": revert_no_lb.rowcount,
    }


@router.get("/calibration-datagolf-diagnosis")
async def datagolf_calibration_diagnosis(
    secret: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Diagnose DataGolf 15.4pp MCE — check NULL is_winner hypothesis."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    # 1. Resolution coverage by market type
    r1 = await db.execute(text("""
        SELECT SPLIT_PART(fm.external_id, ':', 4) AS mtype,
               COUNT(*) AS total,
               COUNT(*) FILTER (WHERE fo.is_winner = true) AS winners,
               COUNT(*) FILTER (WHERE fo.is_winner = false) AS losers,
               COUNT(*) FILTER (WHERE fo.is_winner IS NULL) AS unresolved
        FROM futures_outcomes fo
        JOIN futures_markets fm ON fm.id = fo.market_id
        WHERE fm.source = 'datagolf' AND fm.status = 'resolved'
        GROUP BY SPLIT_PART(fm.external_id, ':', 4)
        ORDER BY total DESC
    """))
    by_type = [dict(r._mapping) for r in r1.fetchall()]

    # 2. Per-bucket NULL is_winner count
    r2 = await db.execute(text("""
        SELECT LEAST(FLOOR(COALESCE(fo.calibration_probability, fo.opening_probability) * 10)::int, 9) AS bucket,
               COUNT(*) AS total,
               COUNT(*) FILTER (WHERE fo.is_winner = true) AS winners,
               COUNT(*) FILTER (WHERE fo.is_winner IS NULL) AS null_winner,
               ROUND(AVG(COALESCE(fo.calibration_probability, fo.opening_probability))::numeric, 3) AS avg_prob,
               ROUND((COUNT(*) FILTER (WHERE fo.is_winner = true)::numeric
                      / NULLIF(COUNT(*), 0)), 3) AS win_rate
        FROM futures_outcomes fo
        JOIN futures_markets fm ON fm.id = fo.market_id
        WHERE fm.source = 'datagolf' AND fm.status = 'resolved'
          AND fo.opening_probability IS NOT NULL
          AND fo.opening_probability > 0.005 AND fo.opening_probability < 0.98
        GROUP BY bucket ORDER BY bucket
    """))
    by_bucket = [dict(r._mapping) for r in r2.fetchall()]

    # 3. Resolution source distribution
    r3 = await db.execute(text("""
        SELECT COALESCE(fo.resolution_source, 'NULL') AS src,
               COUNT(*) AS n,
               COUNT(*) FILTER (WHERE fo.is_winner = true) AS winners,
               COUNT(*) FILTER (WHERE fo.is_winner IS NULL) AS null_winner
        FROM futures_outcomes fo
        JOIN futures_markets fm ON fm.id = fo.market_id
        WHERE fm.source = 'datagolf' AND fm.status = 'resolved'
        GROUP BY fo.resolution_source ORDER BY n DESC
    """))
    by_source = [dict(r._mapping) for r in r3.fetchall()]

    # 4. Simulated MCE excluding NULL is_winner
    r4 = await db.execute(text("""
        WITH dg AS (
            SELECT COALESCE(fo.calibration_probability, fo.opening_probability) AS p,
                   fo.is_winner,
                   CASE
                       WHEN COALESCE(fo.calibration_probability, fo.opening_probability) < 0.05 THEN 0.025
                       WHEN COALESCE(fo.calibration_probability, fo.opening_probability) < 0.15 THEN 0.10
                       WHEN COALESCE(fo.calibration_probability, fo.opening_probability) < 0.25 THEN 0.20
                       WHEN COALESCE(fo.calibration_probability, fo.opening_probability) < 0.35 THEN 0.30
                       WHEN COALESCE(fo.calibration_probability, fo.opening_probability) < 0.45 THEN 0.40
                       WHEN COALESCE(fo.calibration_probability, fo.opening_probability) < 0.55 THEN 0.50
                       WHEN COALESCE(fo.calibration_probability, fo.opening_probability) < 0.65 THEN 0.60
                       WHEN COALESCE(fo.calibration_probability, fo.opening_probability) < 0.75 THEN 0.70
                       WHEN COALESCE(fo.calibration_probability, fo.opening_probability) < 0.85 THEN 0.80
                       WHEN COALESCE(fo.calibration_probability, fo.opening_probability) < 0.95 THEN 0.90
                       ELSE 0.975
                   END AS mid
            FROM futures_outcomes fo
            JOIN futures_markets fm ON fm.id = fo.market_id
            WHERE fm.source = 'datagolf' AND fm.status = 'resolved'
              AND fo.is_winner IS NOT NULL
              AND fo.opening_probability > 0.005 AND fo.opening_probability < 0.98
        ),
        b AS (
            SELECT mid, AVG(CASE WHEN is_winner THEN 1.0 ELSE 0.0 END) AS a, COUNT(*) AS n
            FROM dg GROUP BY mid
        )
        SELECT ROUND((SUM(ABS(a - mid) * n) / SUM(n) * 100)::numeric, 2) AS mce,
               SUM(n) AS outcomes
        FROM b
    """))
    sim = r4.first()

    # 5. Cal prob vs opening prob
    r5 = await db.execute(text("""
        SELECT
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE fo.calibration_probability IS NULL) AS cal_null,
            COUNT(*) FILTER (WHERE fo.calibration_probability IS NOT NULL
                AND fo.calibration_probability = fo.opening_probability) AS cal_eq_open,
            COUNT(*) FILTER (WHERE fo.calibration_probability IS NOT NULL
                AND fo.calibration_probability != fo.opening_probability) AS cal_diff,
            ROUND(AVG(fo.opening_probability)::numeric, 4) AS avg_open,
            ROUND(AVG(fo.calibration_probability)::numeric, 4) AS avg_cal
        FROM futures_outcomes fo
        JOIN futures_markets fm ON fm.id = fo.market_id
        WHERE fm.source = 'datagolf' AND fm.status = 'resolved'
          AND fo.opening_probability IS NOT NULL
    """))
    cp = r5.first()

    # 6. Per-bucket using ONLY calibration_probability (no COALESCE)
    r6 = await db.execute(text("""
        WITH dg AS (
            SELECT fo.calibration_probability AS p, fo.is_winner,
                   LEAST(FLOOR(fo.calibration_probability * 10)::int, 9) AS bucket
            FROM futures_outcomes fo
            JOIN futures_markets fm ON fm.id = fo.market_id
            WHERE fm.source = 'datagolf' AND fm.status = 'resolved'
              AND fo.calibration_probability IS NOT NULL
              AND fo.is_winner IS NOT NULL
              AND fo.calibration_probability > 0.005 AND fo.calibration_probability < 0.98
        )
        SELECT bucket, COUNT(*) AS n,
               ROUND(AVG(p)::numeric, 3) AS avg_prob,
               ROUND(AVG(CASE WHEN is_winner THEN 1.0 ELSE 0.0 END)::numeric, 3) AS win_rate
        FROM dg GROUP BY bucket ORDER BY bucket
    """))
    cal_only_buckets = [dict(r._mapping) for r in r6.fetchall()]

    # 7. Sample high-probability losers
    r7 = await db.execute(text("""
        SELECT fo.name, fm.name AS market_name,
               SPLIT_PART(fm.external_id, ':', 4) AS mtype,
               fo.opening_probability, fo.calibration_probability,
               fo.is_winner, fo.resolution_source
        FROM futures_outcomes fo
        JOIN futures_markets fm ON fm.id = fo.market_id
        WHERE fm.source = 'datagolf' AND fm.status = 'resolved'
          AND COALESCE(fo.calibration_probability, fo.opening_probability) >= 0.40
          AND fo.is_winner = false
        ORDER BY COALESCE(fo.calibration_probability, fo.opening_probability) DESC
        LIMIT 10
    """))
    high_losers = [
        {"name": r.name, "market": r.market_name[:40], "type": r.mtype,
         "open": round(float(r.opening_probability), 3) if r.opening_probability else None,
         "cal": round(float(r.calibration_probability), 3) if r.calibration_probability else None,
         "res": r.resolution_source}
        for r in r7.fetchall()
    ]

    # 8. Probability sum check per market
    r8 = await db.execute(text("""
        SELECT fm.name, fm.external_id,
               SPLIT_PART(fm.external_id, ':', 4) AS mtype,
               COUNT(fo.id) AS outcomes,
               ROUND(SUM(COALESCE(fo.calibration_probability, fo.opening_probability))::numeric, 2) AS prob_sum,
               ROUND(SUM(fo.opening_probability)::numeric, 2) AS open_sum,
               COUNT(*) FILTER (WHERE fo.is_winner = true) AS winners
        FROM futures_outcomes fo
        JOIN futures_markets fm ON fm.id = fo.market_id
        WHERE fm.source = 'datagolf' AND fm.status = 'resolved'
          AND fo.opening_probability IS NOT NULL
        GROUP BY fm.id, fm.name, fm.external_id
        ORDER BY prob_sum DESC
        LIMIT 15
    """))
    prob_sums = [dict(r._mapping) for r in r8.fetchall()]

    # 9a. Per-market-type MCE excluding did_not_play/withdrew
    r9a = await db.execute(text("""
        WITH dg AS (
            SELECT SPLIT_PART(fm.external_id, ':', 4) AS mtype,
                   COALESCE(fo.calibration_probability, fo.opening_probability) AS p,
                   fo.is_winner,
                   CASE
                       WHEN COALESCE(fo.calibration_probability, fo.opening_probability) < 0.05 THEN 0.025
                       WHEN COALESCE(fo.calibration_probability, fo.opening_probability) < 0.15 THEN 0.10
                       WHEN COALESCE(fo.calibration_probability, fo.opening_probability) < 0.25 THEN 0.20
                       WHEN COALESCE(fo.calibration_probability, fo.opening_probability) < 0.35 THEN 0.30
                       WHEN COALESCE(fo.calibration_probability, fo.opening_probability) < 0.45 THEN 0.40
                       WHEN COALESCE(fo.calibration_probability, fo.opening_probability) < 0.55 THEN 0.50
                       WHEN COALESCE(fo.calibration_probability, fo.opening_probability) < 0.65 THEN 0.60
                       WHEN COALESCE(fo.calibration_probability, fo.opening_probability) < 0.75 THEN 0.70
                       WHEN COALESCE(fo.calibration_probability, fo.opening_probability) < 0.85 THEN 0.80
                       WHEN COALESCE(fo.calibration_probability, fo.opening_probability) < 0.95 THEN 0.90
                       ELSE 0.975
                   END AS mid
            FROM futures_outcomes fo
            JOIN futures_markets fm ON fm.id = fo.market_id
            WHERE fm.source = 'datagolf' AND fm.status = 'resolved'
              AND fo.is_winner IS NOT NULL
              AND fo.opening_probability > 0.005 AND fo.opening_probability < 0.98
              AND (fo.resolution_source IS NULL
                   OR fo.resolution_source NOT IN ('did_not_play', 'withdrew', 'pass2_guess', 'pass3_threshold'))
        ),
        b AS (
            SELECT mtype, mid,
                   AVG(CASE WHEN is_winner THEN 1.0 ELSE 0.0 END) AS a,
                   COUNT(*) AS n
            FROM dg GROUP BY mtype, mid
        )
        SELECT mtype,
            ROUND((SUM(ABS(a - mid) * n) / SUM(n) * 100)::numeric, 2) AS mce,
            SUM(n) AS outcomes
        FROM b GROUP BY mtype ORDER BY mce DESC
    """))
    per_type_mce = [
        {"type": r.mtype, "mce_pp": float(r.mce), "outcomes": int(r.outcomes)}
        for r in r9a.fetchall()
    ]

    # 9. Leaderboard analysis for make_cut markets
    r9 = await db.execute(text("""
        SELECT fm.name, fm.external_id,
               jsonb_array_length(fm.market_metadata->'leaderboard') AS lb_size,
               (SELECT COUNT(*) FROM jsonb_array_elements(fm.market_metadata->'leaderboard') lb
                WHERE lb->>'position' ~ '^T?[0-9]+$') AS numeric_pos,
               (SELECT COUNT(*) FROM jsonb_array_elements(fm.market_metadata->'leaderboard') lb
                WHERE UPPER(lb->>'position') IN ('CUT','MC','MDF','WD','DQ','DNS','W/D')) AS cut_pos,
               (SELECT COUNT(*) FROM futures_outcomes fo
                WHERE fo.market_id = fm.id AND fo.is_winner = true) AS fo_winners,
               (SELECT COUNT(*) FROM futures_outcomes fo
                WHERE fo.market_id = fm.id AND fo.is_winner = false
                  AND fo.resolution_source NOT IN ('did_not_play','withdrew')) AS fo_losers_in_cal
        FROM futures_markets fm
        WHERE fm.source = 'datagolf' AND fm.status = 'resolved'
          AND SPLIT_PART(fm.external_id, ':', 4) = 'make_cut'
          AND fm.market_metadata->'leaderboard' IS NOT NULL
          AND jsonb_typeof(fm.market_metadata->'leaderboard') = 'array'
        ORDER BY jsonb_array_length(fm.market_metadata->'leaderboard') DESC
        LIMIT 10
    """))
    spot_check = [
        {"name": r.name[:45], "lb_size": r.lb_size, "numeric": r.numeric_pos,
         "cut": r.cut_pos, "fo_winners": r.fo_winners, "fo_losers_in_cal": r.fo_losers_in_cal}
        for r in r9.fetchall()
    ]

    # 10. Sample losers in calibration for a truncated-lb tournament
    r10 = await db.execute(text("""
        SELECT fo.name, fo.opening_probability, fo.is_winner,
               fo.resolution_source,
               (SELECT lb->>'position' FROM jsonb_array_elements(fm.market_metadata->'leaderboard') lb
                WHERE lb->>'dg_id' = SUBSTRING(fo.external_id FROM 4) LIMIT 1) AS lb_position
        FROM futures_outcomes fo
        JOIN futures_markets fm ON fm.id = fo.market_id
        WHERE fm.source = 'datagolf' AND fm.status = 'resolved'
          AND fm.name LIKE '%PLAYERS%Make the Cut%'
          AND fo.is_winner = false
          AND fo.resolution_source NOT IN ('did_not_play', 'withdrew')
        ORDER BY fo.opening_probability DESC
        LIMIT 10
    """))
    truncated_losers = [
        {"name": r.name, "open": round(float(r.opening_probability), 3) if r.opening_probability else None,
         "res": r.resolution_source, "lb_pos": r.lb_position}
        for r in r10.fetchall()
    ]

    # 11. Make_cut breakdown
    r11 = await db.execute(text("""
        SELECT COUNT(*) AS total,
               COUNT(*) FILTER (WHERE fo.is_winner) AS winners,
               COUNT(*) FILTER (WHERE NOT fo.is_winner) AS losers,
               COUNT(*) FILTER (WHERE fo.opening_probability IS NOT NULL) AS has_open,
               COUNT(*) FILTER (WHERE fo.calibration_probability IS NOT NULL) AS has_cal,
               COUNT(*) FILTER (WHERE fo.resolution_source = 'did_not_play') AS dnp,
               COUNT(*) FILTER (WHERE fo.resolution_source = 'leaderboard') AS lb
        FROM futures_outcomes fo
        JOIN futures_markets fm ON fm.id = fo.market_id
        WHERE fm.source = 'datagolf' AND fm.status = 'resolved'
          AND SPLIT_PART(fm.external_id, ':', 4) = 'make_cut'
    """))
    mc_row = r11.first()
    make_cut_detail = {
        "total": mc_row.total, "winners": mc_row.winners, "losers": mc_row.losers,
        "has_open": mc_row.has_open, "has_cal": mc_row.has_cal,
        "did_not_play": mc_row.dnp, "leaderboard": mc_row.lb,
    } if mc_row else {}

    return {
        "by_market_type": by_type,
        "by_bucket": by_bucket,
        "by_resolution_source": by_source,
        "simulated_mce_excluding_null": {
            "mce_pp": float(sim.mce) if sim and sim.mce else None,
            "outcomes": int(sim.outcomes) if sim and sim.outcomes else 0,
        },
        "cal_vs_opening": {
            "total": cp.total, "cal_null": cp.cal_null,
            "cal_eq_open": cp.cal_eq_open, "cal_diff": cp.cal_diff,
            "avg_open": float(cp.avg_open) if cp.avg_open else None,
            "avg_cal": float(cp.avg_cal) if cp.avg_cal else None,
        } if cp else {},
        "cal_only_buckets": cal_only_buckets,
        "high_probability_losers": high_losers,
        "probability_sums": prob_sums,
        "per_type_mce": per_type_mce,
        "leaderboard_analysis": spot_check,
        "truncated_lb_losers": truncated_losers,
        "make_cut_detail": make_cut_detail,
    }
