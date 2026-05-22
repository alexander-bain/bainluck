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


# =============================================================================
# Excitement Index (EI / Pulse)
# =============================================================================


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


# =============================================================================
# Operations Dashboard
# =============================================================================


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
# Featured market capture ground-truth status
# ---------------------------------------------------------------------------


@router.get("/ground-truth/status")
async def get_ground_truth_status(
    secret: str = Query(..., description="Admin secret for authorization"),
    days: int = Query(7, description="Number of days to look back"),
    db: AsyncSession = Depends(get_db),
):
    """Show featured-market ground-truth capture health.

    Returns rows per source per day, match rate, and recent captures.
    Advisory signal for Discover ranking review — does not auto-promote.
    """
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.utils.featured_market_capture import get_featured_capture_status

    return await get_featured_capture_status(db, days=days)


@router.post("/ground-truth/capture")
async def trigger_ground_truth_capture(
    secret: str = Query(..., description="Admin secret for authorization"),
    db: AsyncSession = Depends(get_db),
):
    """Manually trigger a featured-market capture for today."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.utils.featured_market_capture import capture_all_featured

    return await capture_all_featured(db)


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


@router.get("/pairwise/next")
async def pairwise_next(
    secret: str = Query(..., description="Admin secret for authorization"),
    db: AsyncSession = Depends(get_db),
):
    """Serve a pair of Discover cards for pairwise preference labeling.

    Picks two open FuturesMarket rows from different score tiers
    (one from top third, one from bottom third of available markets)
    to maximize information value of each comparison.
    """
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

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
    secret: str = Query(..., description="Admin secret for authorization"),
    body: PairwiseLabelBody = Body(...),
    db: AsyncSession = Depends(get_db),
):
    """Record a pairwise preference label."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.models.models import DiscoverPairwiseLabel

    label = DiscoverPairwiseLabel(
        reviewer=body.reviewer,
        card_a_market_id=body.card_a_market_id,
        card_b_market_id=body.card_b_market_id,
        card_a_score=body.card_a_score,
        card_b_score=body.card_b_score,
        choice=body.choice,
    )
    db.add(label)
    await db.commit()

    return {"status": "ok", "label_id": label.id}


@router.get("/pairwise/stats")
async def pairwise_stats(
    secret: str = Query(..., description="Admin secret for authorization"),
    db: AsyncSession = Depends(get_db),
):
    """Show labeling statistics including agreement with current ranking."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

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

router.include_router(celery_router)
router.include_router(matching_router)
router.include_router(taxonomy_router)
router.include_router(engagement_router)
router.include_router(data_quality_router)
router.include_router(providers_router)
router.include_router(events_router)
router.include_router(teams_router)
