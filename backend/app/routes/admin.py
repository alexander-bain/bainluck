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

from app.routes.admin_utils import _check_admin_secret, _check_admin_auth, _safe_send_task  # noqa: F401 — re-exported for backward compat

router = APIRouter()


# =============================================================================
# Excitement Index (EI / Pulse)
# =============================================================================


@router.post("/pulse/recalculate")
@router.post("/ei/recalculate")
async def recalculate_ei(
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
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
    _check_admin_secret(secret, request=request)

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
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
    db: AsyncSession = Depends(get_db),
):
    """
    Diagnose why events don't have EI scores.

    Breaks down completed/closed events with raw_ei=NULL by root cause,
    including sport breakdown for zero-snapshot events.
    """
    _check_admin_secret(secret, request=request)

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
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
    db: AsyncSession = Depends(get_db),
):
    """
    Get the current status of EI (Excitement Index) calculations.

    Returns counts of events with and without EI scores.
    """
    _check_admin_secret(secret, request=request)

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


@router.get("/pulse/distributions")
@router.get("/ei/distributions")
async def ei_distributions(
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
    db: AsyncSession = Depends(get_db),
):
    """
    Analyze the distribution of EI scores and metadata across all scored events.

    Returns histograms and statistics for the overall score and EI metadata
    (raw_ei, lead_changes, comeback_factor).
    """
    _check_admin_secret(secret, request=request)

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


# =============================================================================
# Operations Dashboard
# =============================================================================


@router.get("/dashboard")
async def operations_dashboard(
    request: Request,
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
    _check_admin_secret(secret, request=request)

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


# ---------------------------------------------------------------------------
# Latency stats (production observability)
# ---------------------------------------------------------------------------

@router.get("/latency-stats")
async def get_latency_stats(
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
    top: int = Query(20, description="Number of slowest endpoints to return"),
):
    """Return p50/p95/p99 latency per endpoint from the last hour.

    Data comes from sampled request timings stored in Redis sorted sets
    by the LatencyMiddleware.
    """
    _check_admin_secret(secret, request=request)

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
# Featured market capture ground-truth status
# ---------------------------------------------------------------------------


@router.get("/ground-truth/status")
async def get_ground_truth_status(
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
    days: int = Query(7, description="Number of days to look back"),
    db: AsyncSession = Depends(get_db),
):
    """Show featured-market ground-truth capture health.

    Returns rows per source per day, match rate, and recent captures.
    Advisory signal for Discover ranking review — does not auto-promote.
    """
    _check_admin_secret(secret, request=request)

    from app.utils.featured_market_capture import get_featured_capture_status

    return await get_featured_capture_status(db, days=days)


@router.post("/ground-truth/capture")
async def trigger_ground_truth_capture(
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
    db: AsyncSession = Depends(get_db),
):
    """Manually trigger a featured-market capture for today."""
    _check_admin_secret(secret, request=request)

    from app.utils.featured_market_capture import capture_all_featured

    return await capture_all_featured(db)


@router.post("/calibration-sentinel/run")
async def trigger_calibration_sentinel(
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
    file_issues: bool = Query(True, description="File GitHub issues (False = detect-only)"),
    suppress_known: bool = Query(True, description="Suppress cohorts already covered by a shipped exclusion"),
    inline: bool = Query(False, description="Run inline and return findings (default: enqueue on worker)"),
    db: AsyncSession = Depends(get_db),
):
    """#1054: on-demand run of the Calibration Sentinel.

    Enqueues the weekly detection task, or (inline=True) runs it in-request and
    returns the findings — handy for the backtest rediscovery test
    (?inline=true&file_issues=false&suppress_known=false). Read-only detection;
    never writes market data (gotcha #21)."""
    _check_admin_secret(secret, request=request)

    if inline:
        from app.tasks.calibration_sentinel import _run_calibration_sentinel

        return await _run_calibration_sentinel(
            file_issues=file_issues, suppress_known=suppress_known
        )

    from app.tasks import celery_app

    result = _safe_send_task(
        "app.tasks.calibration_sentinel",
        kwargs={"file_issues": file_issues, "suppress_known": suppress_known},
    )
    return {"status": "enqueued", "task_id": result.id}


@router.get("/calibration-sentinel/last")
async def get_calibration_sentinel_last(
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
    backtest: bool = Query(False, description="Read the last backtest run instead of the last live run"),
):
    """#1054: read the last cached Calibration Sentinel run (findings + filed
    issues). Lets an enqueued worker run be inspected without a web-request scan."""
    _check_admin_secret(secret, request=request)

    import json

    from app.tasks.redis_state import get_redis_client

    key = (
        "bainluck:calibration_sentinel:last_backtest"
        if backtest
        else "bainluck:calibration_sentinel:last"
    )
    raw = get_redis_client().get(key)
    if not raw:
        return {"status": "no_run_cached", "key": key}
    return json.loads(raw)


@router.post("/flow-sentinel/run")
async def trigger_flow_sentinel(
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
    file_issues: bool = Query(True, description="File GitHub issues (False = detect-only)"),
    canary: bool = Query(False, description="Append a synthetic missing gold entity to prove filing works"),
    inline: bool = Query(False, description="Run inline and return the scorecard (default: enqueue on worker)"),
):
    """#1078: on-demand run of the Flow Sentinel.

    Enqueues the daily acceptance task, or (inline=True) runs it in-request and
    returns the scorecard — handy for verification
    (?inline=true&file_issues=false) and the canary proof
    (?inline=true&canary=true&file_issues=false). Read-only against production;
    the sentinel files work, it never writes data."""
    _check_admin_secret(secret, request=request)

    if inline:
        from app.tasks.flow_sentinel import _run_flow_sentinel

        return await _run_flow_sentinel(file_issues=file_issues, canary=canary)

    from app.tasks import celery_app

    result = _safe_send_task(
        "app.tasks.flow_sentinel",
        kwargs={"file_issues": file_issues, "canary": canary},
    )
    return {"status": "enqueued", "task_id": result.id}


@router.get("/flow-sentinel/last")
async def get_flow_sentinel_last(
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
):
    """#1078: read the last cached Flow Sentinel run (scorecard + filed issues).
    Lets an enqueued worker run be inspected without re-running the flows, and is
    the persisted scorecard the cockpit can tile later."""
    _check_admin_secret(secret, request=request)

    import json

    from app.tasks.redis_state import get_redis_client

    raw = get_redis_client().get("bainluck:flow_sentinel:last")
    if not raw:
        return {"status": "no_run_cached", "key": "bainluck:flow_sentinel:last"}
    return json.loads(raw)


@router.get("/mlb-schedule-coverage")
async def get_mlb_schedule_coverage(
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
    date: str = Query(None, description="YYYY-MM-DD (default today UTC)"),
):
    """#1201: the MLB schedule-diff sentinel check — every official MLB game that
    day should map to exactly one of our events. Reconciles statsapi's official
    schedule against our events and returns typed transitions (missing_event,
    duplicate_events, premature_settle, postponed). Read-only; fails soft when
    statsapi is unreachable (skipped, never a false RED)."""
    _check_admin_secret(secret, request=request)

    from app.tasks.schedule_coverage import run_mlb_schedule_coverage

    return await run_mlb_schedule_coverage(date=date)


@router.post("/grid-sentinel/run")
async def trigger_grid_sentinel(
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
    file_issues: bool = Query(True, description="File GitHub issues (False = detect-only)"),
    inline: bool = Query(False, description="Run inline and return the scorecard (default: enqueue on worker)"),
):
    """Queue #196: on-demand run of the Grid Sentinel.

    Enqueues the daily grid-reliability task, or (inline=True) runs it in-request
    and returns the verdict scorecard — handy for verification
    (?inline=true&file_issues=false). Classifies every finding against the
    season-window artifact registry so RED means REAL. Read-only against
    production + DB; never writes market data (gotcha #21)."""
    _check_admin_secret(secret, request=request)

    if inline:
        from app.tasks.grid_sentinel import _run_grid_sentinel

        return await _run_grid_sentinel(file_issues=file_issues)

    from app.tasks import celery_app

    result = _safe_send_task(
        "app.tasks.grid_sentinel",
        kwargs={"file_issues": file_issues},
    )
    return {"status": "enqueued", "task_id": result.id}


@router.get("/grid-sentinel/last")
async def get_grid_sentinel_last(
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
):
    """Queue #196: read the last cached Grid Sentinel run (verdict scorecard +
    filed issues). Lets an enqueued worker run be inspected without re-running,
    and is the persisted scorecard the cockpit grid tile consumes."""
    _check_admin_secret(secret, request=request)

    import json

    from app.tasks.redis_state import get_redis_client

    raw = get_redis_client().get("bainluck:grid_sentinel:last")
    if not raw:
        return {"status": "no_run_cached", "key": "bainluck:grid_sentinel:last"}
    return json.loads(raw)


@router.post("/horizon-sentinel/run")
async def trigger_horizon_sentinel(
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
    file_issues: bool = Query(True, description="File GitHub issues (False = detect-only)"),
    inline: bool = Query(False, description="Run inline and return the scorecard (default: enqueue on worker)"),
):
    """Queue #223: on-demand run of the Horizon Sentinel.

    Enqueues the daily marquee-event early-warning task, or (inline=True) runs it
    in-request and returns the scorecard — handy for verification
    (?inline=true&file_issues=false). Reads THE HORIZON CALENDAR
    (app/config/majors_calendar.yaml) and escalates each major as it nears (T-30 /
    T-14 / T-7 / in-progress-without-page = P0). Read-only against production; the
    sentinel files work, it never writes data."""
    _check_admin_secret(secret, request=request)

    if inline:
        from app.tasks.horizon_sentinel import _run_horizon_sentinel

        return await _run_horizon_sentinel(file_issues=file_issues)

    from app.tasks import celery_app

    result = _safe_send_task(
        "app.tasks.horizon_sentinel",
        kwargs={"file_issues": file_issues},
    )
    return {"status": "enqueued", "task_id": result.id}


@router.get("/horizon-sentinel/last")
async def get_horizon_sentinel_last(
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
):
    """Queue #223: read the last cached Horizon Sentinel run (scorecard + filed
    issues). Lets an enqueued worker run be inspected without re-running the
    calendar walk."""
    _check_admin_secret(secret, request=request)

    import json

    from app.tasks.redis_state import get_redis_client

    raw = get_redis_client().get("bainluck:horizon_sentinel:last")
    if not raw:
        return {"status": "no_run_cached", "key": "bainluck:horizon_sentinel:last"}
    return json.loads(raw)


# ---------------------------------------------------------------------------
# Ops snapshot (#237 Item 1) — one compact digest for ops rounds / Item-0 reads
# ---------------------------------------------------------------------------

_OPS_SNAPSHOT_CACHE: dict = {"at": 0.0, "data": None}
_OPS_SNAPSHOT_TTL = 300  # 5 min


def _ops_compact(payload) -> dict:
    """Compact a cached sentinel/warm payload down to an ops digest: keep scalar
    top-level fields (incl. ``generated_at``) verbatim and replace list values with
    a ``<key>_count``. Nested dicts are dropped to stay small. Robust to whatever
    schema each source persists."""
    if not isinstance(payload, dict):
        return {"status": "no_run_cached"}
    out: dict = {}
    for k, v in payload.items():
        if v is None or isinstance(v, (str, int, float, bool)):
            out[k] = v
        elif isinstance(v, list):
            out[f"{k}_count"] = len(v)
    return out


@router.get("/ops-snapshot")
async def get_ops_snapshot(
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
    fresh: bool = Query(False, description="Bypass the 5-min cache and recompute"),
):
    """#237 Item 1: ONE compact JSON digest of production health so an ops round or
    an Item-0 read is 1-2 calls instead of ~20. Composes only WARM sources (Redis
    keys + task-metrics + quota); it never recomputes the ~25s link-rate/matured
    queries and never calls Sentry live (the sentry field is served from the cached
    ``sentry_snapshot`` beat). Every field is independently guarded — a cold cache
    or Redis hiccup degrades that one field to a status object instead of 500ing the
    whole snapshot. 5-min in-process cache (``fresh=true`` to bypass)."""
    _check_admin_secret(secret, request=request)

    import json as _json
    import time as _time
    from datetime import datetime, timezone

    now = _time.time()
    if not fresh and _OPS_SNAPSHOT_CACHE["data"] is not None:
        if now - _OPS_SNAPSHOT_CACHE["at"] < _OPS_SNAPSHOT_TTL:
            cached = dict(_OPS_SNAPSHOT_CACHE["data"])
            cached["cache"] = "hit"
            return cached

    from app.tasks.redis_state import (
        get_all_task_metrics,
        get_odds_api_quota,
        get_redis_client,
        get_task_metrics,
    )

    r = get_redis_client()

    def _read_json(key):
        try:
            raw = r.get(key)
            return _json.loads(raw) if raw else None
        except Exception:
            return None

    def _metric_subset(label):
        try:
            m = get_task_metrics(label) or {}
            return {
                "successes_24h": m.get("successes_24h"),
                "failures_24h": m.get("failures_24h"),
                "consecutive_failures": m.get("consecutive_failures"),
                "health": m.get("health"),
                "last_result_summary": m.get("last_result_summary"),
            }
        except Exception as exc:  # noqa: BLE001
            return {"status": "error", "error": str(exc)[:120]}

    snapshot: dict = {"generated_at": datetime.now(timezone.utc).isoformat(), "cache": "miss"}

    # 1. Link rate + matured linkage (warm Redis keys — never recompute).
    try:
        lr = _read_json("bainluck:admin:link_rate") or {}
        snapshot["link_rate"] = {
            "overall": lr.get("overall"),
            "generated_at": lr.get("generated_at"),
        } if lr else {"status": "no_data"}
    except Exception as exc:  # noqa: BLE001
        snapshot["link_rate"] = {"status": "error", "error": str(exc)[:120]}
    try:
        ml = _read_json("bainluck:admin:matured_linkage")
        snapshot["matured_linkage"] = _ops_compact(ml) if ml else {"status": "no_data"}
    except Exception as exc:  # noqa: BLE001
        snapshot["matured_linkage"] = {"status": "error", "error": str(exc)[:120]}

    # 2. Coverage poll counts.
    snapshot["coverage"] = {
        "poll_kalshi": _metric_subset("poll_kalshi"),
        "poll_polymarket": _metric_subset("poll_polymarket"),
    }

    # 3. Cal-beat health.
    snapshot["cal_beat"] = _metric_subset("calibration_prices")

    # 4. Time-horizon state (calibration time-horizon precompute).
    try:
        th = _read_json("bainluck:calibration:time_horizon")
        snapshot["time_horizon"] = _ops_compact(th) if th else {"status": "no_data"}
    except Exception as exc:  # noqa: BLE001
        snapshot["time_horizon"] = {"status": "error", "error": str(exc)[:120]}

    # 5. The three sentinel verdicts (+ generated_at, via _ops_compact).
    snapshot["sentinels"] = {
        "flow": _ops_compact(_read_json("bainluck:flow_sentinel:last")),
        "calibration": _ops_compact(_read_json("bainluck:calibration_sentinel:last")),
        "grid": _ops_compact(_read_json("bainluck:grid_sentinel:last")),
    }

    # 6. Quota.
    try:
        snapshot["quota"] = get_odds_api_quota()
    except Exception as exc:  # noqa: BLE001
        snapshot["quota"] = {"status": "error", "error": str(exc)[:120]}

    # 7. Top Sentry 24h (cached beat — never a live Sentry call here).
    snapshot["sentry"] = _read_json("bainluck:sentry:top_24h") or {"status": "no_data"}

    # 8. Celery / queue health.
    try:
        depths = {}
        for q in ("background", "realtime", "heavy"):
            try:
                depths[q] = r.llen(q)
            except Exception:
                depths[q] = None
        health_counts: dict = {}
        for m in get_all_task_metrics() or []:
            h = m.get("health") or "unknown"
            health_counts[h] = health_counts.get(h, 0) + 1
        snapshot["celery"] = {"queue_depths": depths, "task_health": health_counts}
    except Exception as exc:  # noqa: BLE001
        snapshot["celery"] = {"status": "error", "error": str(exc)[:120]}

    _OPS_SNAPSHOT_CACHE["at"] = now
    _OPS_SNAPSHOT_CACHE["data"] = snapshot
    return snapshot


@router.post("/settled-concept-sentinel/run")
async def trigger_settled_concept_sentinel(
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
    file_issues: bool = Query(True, description="File GitHub issues (False = detect-only)"),
    inline: bool = Query(False, description="Run inline and return the scorecard (default: enqueue on worker)"),
    concept_key: str = Query(None, description="Check ONE specific concept key (overrides calendar target selection)"),
):
    """Queue #226: on-demand run of the Settled-Concept Sentinel.

    Enqueues the daily settled-contract check, or (inline=True) runs it in-request
    and returns the scorecard — handy for verification
    (?inline=true&file_issues=false&concept_key=event:golf:the-open-championship).
    Reads the LIVE event-concept surface for every recently-settled marquee
    concept (or the single ``concept_key`` given) and asserts champion hero /
    field membership / evolution resolves / round resolution, classifying REAL vs
    EXPLAINED. Read-only against production; the sentinel files work, never data."""
    _check_admin_secret(secret, request=request)

    keys = [concept_key] if concept_key else None
    if inline:
        from app.tasks.settled_concept_sentinel import _run_settled_concept_sentinel

        return await _run_settled_concept_sentinel(file_issues=file_issues, concept_keys=keys)

    from app.tasks import celery_app

    result = _safe_send_task(
        "app.tasks.settled_concept_sentinel",
        kwargs={"file_issues": file_issues},
    )
    return {"status": "enqueued", "task_id": result.id}


@router.get("/settled-concept-sentinel/last")
async def get_settled_concept_sentinel_last(
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
):
    """Queue #226: read the last cached Settled-Concept Sentinel run (scorecard +
    filed issues) without re-running the checks."""
    _check_admin_secret(secret, request=request)

    import json

    from app.tasks.redis_state import get_redis_client

    raw = get_redis_client().get("bainluck:settled_concept_sentinel:last")
    if not raw:
        return {"status": "no_run_cached", "key": "bainluck:settled_concept_sentinel:last"}
    return json.loads(raw)


# ---------------------------------------------------------------------------
# Pairwise Discover Card Preference Labeling
# ---------------------------------------------------------------------------


class PairwiseLabelBody(BaseModel):
    card_a_market_id: int
    card_b_market_id: int
    card_a_score: Optional[float] = None
    card_b_score: Optional[float] = None
    choice: str = Field(..., pattern=r"^(a|b|both|neither|skip)$")
    reviewer: str
    pair_id: Optional[str] = None
    pair_strategy: Optional[str] = None
    surface: Optional[str] = None
    batch_id: Optional[str] = None
    confidence: Optional[str] = None
    ranking_error: Optional[bool] = None
    notes: Optional[str] = None
    card_a_snapshot: Optional[dict] = None
    card_b_snapshot: Optional[dict] = None


@router.get("/pairwise/next")
async def pairwise_next(
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
    db: AsyncSession = Depends(get_db),
):
    """Serve a pair of Discover cards for pairwise preference labeling.

    Picks two open FuturesMarket rows from different score tiers
    (one from top third, one from bottom third of available markets)
    to maximize information value of each comparison.
    """
    _check_admin_secret(secret, request=request)

    from app.models.models import DiscoverPairwiseLabel

    # Query 50 random open markets with outcomes and enrichment data
    result = await db.execute(
        select(FuturesMarket)
        .options(selectinload(FuturesMarket.outcomes))
        .where(
            FuturesMarket.status == "open",
            FuturesMarket.hook_description.isnot(None),
        )
        .order_by(func.random())
        .limit(50)
    )
    markets = list(result.scalars().all())

    if len(markets) < 2:
        # Fall back: try without hook_description requirement
        result = await db.execute(
            select(FuturesMarket)
            .options(selectinload(FuturesMarket.outcomes))
            .where(FuturesMarket.status == "open")
            .order_by(func.random())
            .limit(50)
        )
        markets = list(result.scalars().all())

    if len(markets) < 2:
        raise HTTPException(
            status_code=404,
            detail="Not enough open markets for comparison",
        )

    # Score each market based on available signals
    scored = []
    for m in markets:
        score = 0.0
        # Volume signal
        if m.volume_24h and m.volume_24h > 0:
            score += min(m.volume_24h / 1000, 30)
        # Movement signal
        if m.max_movement_24h:
            score += float(m.max_movement_24h) * 100
        # Enrichment bonus
        if m.hook_description:
            score += 10
        if m.image_url:
            score += 5
        # Outcome count bonus (multi-outcome markets are richer)
        outcome_count = len(m.outcomes) if m.outcomes else 0
        if outcome_count > 2:
            score += 5
        scored.append((m, score))

    # Sort by score and pick from different tiers
    scored.sort(key=lambda x: x[1], reverse=True)
    third = max(1, len(scored) // 3)

    import random as rng

    card_a_market, card_a_score = rng.choice(scored[:third])
    # Pick card_b from bottom third, ensuring it differs from card_a
    bottom_pool = [(m, s) for m, s in scored[-third:] if m.id != card_a_market.id]
    if not bottom_pool:
        bottom_pool = [(m, s) for m, s in scored if m.id != card_a_market.id]
    card_b_market, card_b_score = rng.choice(bottom_pool)

    def _market_to_card(m: FuturesMarket, score: float) -> dict:
        outcomes_list = []
        if m.outcomes:
            # Sort by probability descending, take top 3
            sorted_outcomes = sorted(
                m.outcomes,
                key=lambda o: float(o.current_probability or 0),
                reverse=True,
            )
            for o in sorted_outcomes[:3]:
                outcomes_list.append(
                    {
                        "name": o.name,
                        "probability": (
                            float(o.current_probability)
                            if o.current_probability is not None
                            else None
                        ),
                    }
                )
        return {
            "market_id": m.id,
            "name": m.name,
            "category": m.llm_sport_category or m.category,
            "probability": (
                float(m.outcomes[0].current_probability)
                if m.outcomes and m.outcomes[0].current_probability is not None
                else None
            ),
            "image_url": m.image_url,
            "hook_description": m.hook_description,
            "outcomes": outcomes_list,
            "score": round(score, 2),
        }

    # Random pair_id for tracking
    import uuid as _uuid

    pair_id = str(_uuid.uuid4())[:12]

    return {
        "card_a": _market_to_card(card_a_market, card_a_score),
        "card_b": _market_to_card(card_b_market, card_b_score),
        "pair_id": pair_id,
    }


@router.post("/pairwise/label")
async def pairwise_label(
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
    body: PairwiseLabelBody = Body(...),
    db: AsyncSession = Depends(get_db),
):
    """Record a pairwise preference label."""
    _check_admin_secret(secret, request=request)

    from app.models.models import DiscoverPairwiseLabel

    label = DiscoverPairwiseLabel(
        reviewer=body.reviewer,
        card_a_market_id=body.card_a_market_id,
        card_b_market_id=body.card_b_market_id,
        card_a_score=body.card_a_score,
        card_b_score=body.card_b_score,
        choice=body.choice,
        pair_id=body.pair_id,
        pair_strategy=body.pair_strategy,
        surface=body.surface,
        batch_id=body.batch_id,
        confidence=body.confidence,
        ranking_error=body.ranking_error,
        notes=body.notes,
        card_a_snapshot=body.card_a_snapshot,
        card_b_snapshot=body.card_b_snapshot,
    )
    db.add(label)
    await db.commit()

    return {"status": "ok", "label_id": label.id}


@router.get("/pairwise/stats")
async def pairwise_stats(
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
    db: AsyncSession = Depends(get_db),
):
    """Show labeling statistics including agreement with current ranking."""
    _check_admin_secret(secret, request=request)

    from app.models.models import DiscoverPairwiseLabel

    # Total labels
    total_result = await db.execute(
        select(func.count(DiscoverPairwiseLabel.id))
    )
    total_labels = total_result.scalar() or 0

    # Labels by choice
    choice_result = await db.execute(
        select(
            DiscoverPairwiseLabel.choice,
            func.count(DiscoverPairwiseLabel.id),
        ).group_by(DiscoverPairwiseLabel.choice)
    )
    labels_by_choice = {row[0]: row[1] for row in choice_result.all()}

    # Agreement rate: among labels with choice 'a' or 'b' and both scores,
    # what % picked the higher-scored card?
    agree_result = await db.execute(
        select(DiscoverPairwiseLabel).where(
            DiscoverPairwiseLabel.choice.in_(["a", "b"]),
            DiscoverPairwiseLabel.card_a_score.isnot(None),
            DiscoverPairwiseLabel.card_b_score.isnot(None),
        )
    )
    agree_labels = agree_result.scalars().all()
    agree_count = 0
    total_comparable = 0
    for lbl in agree_labels:
        total_comparable += 1
        if lbl.choice == "a" and lbl.card_a_score >= lbl.card_b_score:
            agree_count += 1
        elif lbl.choice == "b" and lbl.card_b_score >= lbl.card_a_score:
            agree_count += 1
    agreement_rate = (
        round(agree_count / total_comparable, 4) if total_comparable > 0 else None
    )

    # Per-category agreement (join with FuturesMarket to get category)
    cat_query = await db.execute(
        select(
            FuturesMarket.llm_sport_category,
            DiscoverPairwiseLabel.choice,
            DiscoverPairwiseLabel.card_a_score,
            DiscoverPairwiseLabel.card_b_score,
        )
        .join(
            FuturesMarket,
            FuturesMarket.id == DiscoverPairwiseLabel.card_a_market_id,
        )
        .where(
            DiscoverPairwiseLabel.choice.in_(["a", "b"]),
            DiscoverPairwiseLabel.card_a_score.isnot(None),
            DiscoverPairwiseLabel.card_b_score.isnot(None),
        )
    )
    cat_rows = cat_query.all()
    cat_stats: dict[str, dict[str, int]] = {}
    for cat, choice, a_score, b_score in cat_rows:
        cat_key = cat or "unknown"
        if cat_key not in cat_stats:
            cat_stats[cat_key] = {"agree": 0, "total": 0}
        cat_stats[cat_key]["total"] += 1
        if choice == "a" and a_score >= b_score:
            cat_stats[cat_key]["agree"] += 1
        elif choice == "b" and b_score >= a_score:
            cat_stats[cat_key]["agree"] += 1
    per_category_agreement = {
        cat: round(v["agree"] / v["total"], 4) if v["total"] > 0 else None
        for cat, v in cat_stats.items()
    }

    # Recent labels (last 20)
    recent_result = await db.execute(
        select(DiscoverPairwiseLabel)
        .order_by(DiscoverPairwiseLabel.created_at.desc())
        .limit(20)
    )
    recent = recent_result.scalars().all()
    # Fetch market names for recent labels
    market_ids = set()
    for lbl in recent:
        market_ids.add(lbl.card_a_market_id)
        market_ids.add(lbl.card_b_market_id)
    market_names: dict[int, str] = {}
    if market_ids:
        names_result = await db.execute(
            select(FuturesMarket.id, FuturesMarket.name).where(
                FuturesMarket.id.in_(market_ids)
            )
        )
        for mid, mname in names_result.all():
            market_names[mid] = mname

    recent_labels = [
        {
            "id": lbl.id,
            "reviewer": lbl.reviewer,
            "card_a_name": market_names.get(lbl.card_a_market_id, f"#{lbl.card_a_market_id}"),
            "card_b_name": market_names.get(lbl.card_b_market_id, f"#{lbl.card_b_market_id}"),
            "card_a_score": lbl.card_a_score,
            "card_b_score": lbl.card_b_score,
            "choice": lbl.choice,
            "pair_id": lbl.pair_id,
            "pair_strategy": lbl.pair_strategy,
            "surface": lbl.surface,
            "ranking_error": lbl.ranking_error,
            "created_at": lbl.created_at.isoformat() if lbl.created_at else None,
        }
        for lbl in recent
    ]

    return {
        "total_labels": total_labels,
        "labels_by_choice": labels_by_choice,
        "agreement_rate": agreement_rate,
        "total_comparable": total_comparable,
        "per_category_agreement": per_category_agreement,
        "recent_labels": recent_labels,
    }


# ---------------------------------------------------------------------------
# Include sub-routers (at bottom to avoid circular imports)
# ---------------------------------------------------------------------------
from app.routes.admin_celery import router as celery_router  # noqa: E402
from app.routes.admin_matching import router as matching_router  # noqa: E402
from app.routes.admin_taxonomy import router as taxonomy_router  # noqa: E402
from app.routes.admin_engagement import router as engagement_router  # noqa: E402
from app.routes.admin_data_quality import router as data_quality_router  # noqa: E402
from app.routes.admin_providers import router as providers_router  # noqa: E402
from app.routes.admin_events import router as events_router  # noqa: E402
from app.routes.admin_teams import router as teams_router  # noqa: E402
from app.routes.admin_repairs import router as repairs_router  # noqa: E402

router.include_router(celery_router)
router.include_router(matching_router)
router.include_router(taxonomy_router)
router.include_router(engagement_router)
router.include_router(data_quality_router)
router.include_router(providers_router)
router.include_router(events_router)
router.include_router(teams_router)
router.include_router(repairs_router)
