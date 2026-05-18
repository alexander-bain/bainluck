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

from app.services import get_db

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


@router.get("/snapshots/distribution")
async def get_snapshot_distribution(
    secret: str = Query(..., description="Admin secret for authorization"),
    status_filter: str = Query("open", description="Market status filter: open, resolved, all"),
    db: AsyncSession = Depends(get_db),
):
    """Snapshot count distribution per outcome by source.

    Uses a fast per-market sampling approach: picks ~200 random markets per
    source, then counts snapshots for just those outcomes.
    """
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    status_clause = ""
    if status_filter == "open":
        status_clause = "AND fm.status IN ('open', 'active')"
    elif status_filter == "resolved":
        status_clause = "AND fm.status = 'resolved'"

    await db.execute(text("SET LOCAL statement_timeout = '25s'"))

    sources_result = (await db.execute(text(f"""
        SELECT DISTINCT source FROM futures_markets WHERE 1=1 {status_clause}
    """))).all()

    all_sources = []
    for source_row in sources_result:
        src = source_row.source
        src_clause = status_clause.replace("fm.", "fm2.")

        sample_rows = (await db.execute(text(f"""
            WITH sample_markets AS (
                SELECT fm2.id
                FROM futures_markets fm2
                WHERE fm2.source = :src {src_clause}
                ORDER BY fm2.id DESC
                LIMIT 200
            ),
            outcome_snaps AS (
                SELECT fo.id AS outcome_id,
                       (SELECT COUNT(*) FROM futures_odds_snapshots fos
                        WHERE fos.outcome_id = fo.id) AS snap_count
                FROM futures_outcomes fo
                WHERE fo.market_id IN (SELECT id FROM sample_markets)
            )
            SELECT COUNT(*) AS total,
                   COUNT(*) FILTER (WHERE snap_count = 0) AS zero,
                   COUNT(*) FILTER (WHERE snap_count BETWEEN 1 AND 5) AS bucket_1_5,
                   COUNT(*) FILTER (WHERE snap_count BETWEEN 6 AND 20) AS bucket_6_20,
                   COUNT(*) FILTER (WHERE snap_count BETWEEN 21 AND 50) AS bucket_21_50,
                   COUNT(*) FILTER (WHERE snap_count BETWEEN 51 AND 100) AS bucket_51_100,
                   COUNT(*) FILTER (WHERE snap_count > 100) AS bucket_100_plus,
                   ROUND(AVG(snap_count)::numeric, 1) AS avg_snaps,
                   PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY snap_count) AS median_snaps
            FROM outcome_snaps
        """), {"src": src})).first()

        total_result = (await db.execute(text(f"""
            SELECT COUNT(*) FROM futures_outcomes fo
            JOIN futures_markets fm ON fm.id = fo.market_id
            WHERE fm.source = :src {status_clause}
        """), {"src": src})).scalar()

        if sample_rows and sample_rows.total > 0:
            r = sample_rows
            all_sources.append({
                "source": src,
                "total_outcomes": total_result or 0,
                "sampled_outcomes": r.total,
                "zero_snapshots": r.zero,
                "1_to_5": r.bucket_1_5,
                "6_to_20": r.bucket_6_20,
                "21_to_50": r.bucket_21_50,
                "51_to_100": r.bucket_51_100,
                "100_plus": r.bucket_100_plus,
                "avg_snapshots": float(r.avg_snaps) if r.avg_snaps else 0,
                "median_snapshots": float(r.median_snaps) if r.median_snaps else 0,
                "sparse_pct": round(100 * (r.zero + r.bucket_1_5) / max(r.total, 1), 1),
            })

    return {
        "status_filter": status_filter,
        "method": "200 most-recent markets per source",
        "sources": sorted(all_sources, key=lambda s: s["source"]),
    }


# =============================================================================
# Prediction Market → Event Matching
# =============================================================================


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


@router.post("/backfill-winners/probability-only")
async def trigger_probability_backfill(
    secret: str = Query(...),
    db: AsyncSession = Depends(get_db),
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


@router.post("/fix-commence-times")
async def fix_commence_times(secret: str = Query(...)):
    """Run golf + hockey commence_time fixes synchronously (no Celery)."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")
    from app.tasks.kalshi import _fix_golf_commence_times, _fix_hockey_commence_times
    golf = await _fix_golf_commence_times()
    hockey = await _fix_hockey_commence_times()
    return {"golf_fixed": golf, "hockey_fixed": hockey}


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
        "stuck_diagnosis": await _diagnose_stuck_winners(db),
    }


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
    }

