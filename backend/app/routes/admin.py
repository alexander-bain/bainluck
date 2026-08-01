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
from app.utils import health_reads, probability_to_american
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

    #1500 — this rail used to report green through the tail it exists to
    measure. Two changes make it honest:

    * **Nearest-rank percentiles with an explicit ``n`` and a minimum-sample
      rule.** The old estimator floored to a low-order sample (at n=2, the
      MINIMUM), which is how it reported a 1.2 ms p99 on an endpoint whose
      slowest sample in the window was 12.9 s. Below the minimum n for a given
      percentile the field is ``null`` — unavailable, never a fabricated number.
    * **Cache-status buckets.** ``/api/feed`` is dominated by warm hits, so a
      blended percentile cannot express the cold cost. Each sample now carries
      its ``X-Feed-Cache`` bucket and ``by_cache_status`` reports each bucket
      separately, so the ``miss`` p95 is readable on its own.
    """
    _check_admin_secret(secret, request=request)

    import time as _time
    from collections import defaultdict as _defaultdict

    from app.middleware.latency import _ALWAYS_SAMPLE
    from app.utils.latency_stats import parse_sample_member, summarize

    # `get_redis_client()` constructs lazily, so a dead Redis surfaces on the
    # FIRST command, not here. Both must be inside the guard or an unreachable
    # store returns an opaque 500 instead of a truthful "cannot measure" 503.
    r, failure = health_reads.client(key="latency:_endpoints")
    if failure is not None:
        raise HTTPException(
            status_code=503, detail=f"Redis unavailable: {failure.error}"
        )
    members = health_reads.command(
        "latency:_endpoints", lambda: r.smembers("latency:_endpoints")
    )
    if members.unavailable:
        raise HTTPException(
            status_code=503, detail=f"Redis unavailable: {members.error}"
        )
    endpoints_set = members.value

    if not endpoints_set:
        return {"endpoints": [], "note": "No latency data collected yet"}

    now = _time.time()
    cutoff = now - 3600  # last hour only
    results = []
    # C102: the per-endpoint sorted-set read used to sit OUTSIDE the acquisition
    # guard above, so a connection dropped after a successful SMEMBERS turned the
    # whole rail into an opaque 500. Each read is now classified: siblings that
    # succeed are still reported, the failures are named, and a rail where NO
    # endpoint could be measured degrades to the same bounded 503 as a dead
    # client rather than pretending the window was simply empty.
    read_errors: list[dict] = []

    for raw_ep in endpoints_set:
        ep = raw_ep.decode() if isinstance(raw_ep, bytes) else raw_ep
        key = f"latency:{ep}"

        # Get all members within the time window (score = timestamp).
        # member format: "timestamp:latency_ms[:cache_bucket]"
        window = health_reads.command(
            key, lambda k=key: r.zrangebyscore(k, cutoff, "+inf")
        )
        if window.unavailable:
            read_errors.append(
                {
                    "endpoint": ep,
                    "status": window.status,
                    "error_class": window.error_class,
                    "error": window.error,
                }
            )
            continue
        pairs = window.value
        if not pairs:
            continue

        latencies: list[float] = []
        by_bucket: dict[str, list[float]] = _defaultdict(list)
        for raw_member in pairs:
            m = raw_member.decode() if isinstance(raw_member, bytes) else raw_member
            parsed = parse_sample_member(m)
            if parsed is None:
                continue
            latency, bucket = parsed
            latencies.append(latency)
            by_bucket[bucket].append(latency)
        if not latencies:
            continue

        entry = {
            "endpoint": ep,
            "samples": len(latencies),
            "always_sampled": ep in _ALWAYS_SAMPLE,
            **summarize(latencies),
        }
        # Only surface the cache dimension where it exists — an endpoint that
        # sets no X-Feed-Cache header lands entirely in the "none" bucket, and
        # repeating the blended numbers under a second heading would be noise.
        real_buckets = {b: v for b, v in by_bucket.items() if b != "none"}
        if real_buckets:
            entry["by_cache_status"] = {
                bucket: summarize(values)
                for bucket, values in sorted(real_buckets.items())
            }
        results.append(entry)

    # Sort by p95 descending so the slowest endpoints are first. A null p95
    # (too few samples to answer) must not sort as "fast" — fall back to the
    # observed max, which is a lower bound on the true p95.
    def _sort_key(e):
        return e.get("p95_ms") if e.get("p95_ms") is not None else (e.get("max_ms") or 0)

    # Nothing measurable AND at least one read failed = the rail is down, not
    # quiet. Say so with a bounded 503 instead of returning a confident, empty,
    # green-looking payload. Checked before sorting/truncation so the rail's
    # verdict does not depend on presentation.
    if read_errors and not results:
        raise HTTPException(
            status_code=503,
            detail=(
                f"Redis unavailable: latency samples unreadable for all "
                f"{len(read_errors)} tracked endpoint(s) — {read_errors[0]['error']}"
            ),
        )

    results.sort(key=_sort_key, reverse=True)
    results = results[:top]

    return {
        "window": "1 hour",
        "sample_rate": f"1/{os.getenv('LATENCY_SAMPLE_RATE', '10')}",
        "always_sampled_endpoints": sorted(_ALWAYS_SAMPLE),
        "percentile_method": "nearest-rank (ceil(pct/100 * n) - 1)",
        "note": (
            "A null percentile means too few samples in the window to answer "
            "it (see min_samples), NOT a fast endpoint."
        ),
        "endpoints": results,
        "total_endpoints_tracked": len(endpoints_set),
        # Explicit partial-read provenance: an endpoint whose samples could not
        # be read is named here, never silently absent from `endpoints`.
        "unreadable_endpoints": read_errors,
        "completeness": (
            "partial" if read_errors else "complete"
        ),
    }


@router.get("/candidate-base-state")
async def get_candidate_base_state(
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
):
    """Read-only state of the Discover candidate-ID base (#1500 scope 4).

    Answers "which namespace/version is actually being written, is the kill
    switch on, how old are the keys, and how many IDs did the last publish
    carry?" without a `debug=true` feed call — which today is the only way to
    read the provenance signal, and which costs ~2x the request being measured
    (it runs the ground-truth block and disables the response cache).

    STRICTLY read-only: no flip, no flush, no trigger, no raw Redis passthrough.
    Only the allowlisted fields below are returned, and candidate IDs / market
    content are never exposed — just counts and ages.
    """
    _check_admin_secret(secret, request=request)

    import time as _time

    from app.utils import candidate_base as cb

    state: dict = {
        "namespace": cb._REDIS_NS,
        "key_prefix": cb._KEY_PREFIX,
        "key_version": cb._KEY_VERSION,
        "schema_version": cb.CANDIDATE_BASE_SCHEMA_VERSION,
        "kill_switch_key": cb.CANDIDATE_BASE_ENABLED_KEY,
        "policy": {
            "fresh_seconds": cb.CANDIDATE_BASE_FRESH_SECONDS,
            "last_good_max_age_s": cb.CANDIDATE_BASE_LAST_GOOD_MAX_AGE_S,
            "fresh_ttl_s": cb.CANDIDATE_BASE_FRESH_TTL_S,
            "last_good_ttl_s": cb.CANDIDATE_BASE_LAST_GOOD_TTL_S,
        },
        "provenance_labels": [
            cb.PROV_FRESH, cb.PROV_LAST_GOOD, cb.PROV_DIRECT,
            cb.PROV_DISABLED, cb.PROV_UNAVAILABLE,
        ],
    }

    r, failure = health_reads.client(key=cb.CANDIDATE_BASE_ENABLED_KEY)
    if failure is not None:
        # UNKNOWN, not "disabled" — an unreadable store is not a configuration.
        state["enabled"] = None
        state["status"] = "unavailable"
        state["error_class"] = failure.error_class
        state["error"] = failure.error
        return state

    switch_read = health_reads.read_text(r, cb.CANDIDATE_BASE_ENABLED_KEY)
    if switch_read.unavailable:
        state["enabled"] = None
        state["status"] = "unavailable"
        state["error_class"] = switch_read.error_class
        state["error"] = switch_read.error
        return state
    raw_switch = switch_read.value if switch_read.ok else None

    # Absent key = enabled (the switch is an opt-OUT set to "0"); report the raw
    # value too so "unset" and "explicitly 1" stay distinguishable.
    state["kill_switch_value"] = raw_switch
    state["enabled"] = raw_switch != "0"
    state["status"] = "enabled" if state["enabled"] else "disabled"

    # The default (sport=None, no static tags) identity is the one the beat
    # publishes and the anonymous cold feed reads.
    identity = cb.base_identity(sport_filter=None, static_tag_filter=None)
    fresh_key, last_good_key = cb._redis_keys(identity)
    state["default_identity"] = identity

    now_ms = _time.time() * 1000
    keys: dict[str, dict] = {}
    reads: dict[str, health_reads.RedisRead] = {}
    envelopes: dict[str, dict] = {}
    for label, key in (("fresh", fresh_key), ("last_good", last_good_key)):
        info: dict = {"present": False, "key_status": None}
        read = health_reads.read_json(r, key)
        reads[label] = read
        info["key_status"] = read.status
        if read.unavailable:
            # A key we could not READ is not a key that is ABSENT. Leave
            # `present` unknown rather than asserting False.
            info["present"] = None
            info["error_class"] = read.error_class
            info["error"] = read.error
            keys[label] = info
            continue
        if read.missing:
            info["ttl_s"] = None
            keys[label] = info
            continue

        info["present"] = True
        ttl_read = health_reads.command(key, lambda k=key: r.ttl(k))
        info["ttl_s"] = (
            ttl_read.value
            if ttl_read.ok and isinstance(ttl_read.value, int) and ttl_read.value >= 0
            else None
        )
        if read.status == health_reads.MALFORMED:
            info["valid"] = False
            info["error_class"] = read.error_class
            info["error"] = f"unparseable envelope: {read.error}"
            keys[label] = info
            continue
        if read.status == health_reads.WRONG_SHAPE:
            # A valid-JSON list/scalar used to reach `envelope.get(...)` and 500
            # the whole rail. It is a shape fault, reported as one.
            info["valid"] = False
            info["error_class"] = read.error_class
            info["error"] = f"envelope is not an object: {read.error}"
            keys[label] = info
            continue

        envelope = read.value
        envelopes[label] = envelope
        info["valid"] = cb.payload_valid(envelope, expected_identity=identity)
        info["schema_version"] = envelope.get("schema_version")
        info["generated_at"] = envelope.get("generated_at")
        generated_ms = envelope.get("generated_epoch_ms")
        if isinstance(generated_ms, (int, float)) and not isinstance(generated_ms, bool):
            # NOT clamped at zero: an envelope stamped in the future is clock
            # skew, and the production reader rejects it (`_usable` requires a
            # non-negative age). Hiding the sign hid the rejection.
            info["age_seconds"] = round((now_ms - generated_ms) / 1000.0, 1)
            info["is_fresh"] = 0 <= info["age_seconds"] <= cb.CANDIDATE_BASE_FRESH_SECONDS
            info["within_last_good_max_age"] = (
                0 <= info["age_seconds"] <= cb.CANDIDATE_BASE_LAST_GOOD_MAX_AGE_S
            )
        else:
            info["age_seconds"] = None
            info["is_fresh"] = None
            info["within_last_good_max_age"] = None
        # The publication clock (`generated_epoch_ms`, used for the monotonic
        # compare-and-set) and the clock the READER gates on (`generated_at`)
        # are separate fields. `build_envelope` writes both from one instant, so
        # a disagreement means a malformed or hand-written envelope — and the
        # reader would silently rule on a different age than this rail reports.
        # Surface both instead of picking one.
        info["reader_age_seconds"] = health_reads.age_seconds(
            envelope.get("generated_at")
        )
        if (
            info["age_seconds"] is not None
            and info["reader_age_seconds"] is not None
            and abs(info["age_seconds"] - info["reader_age_seconds"]) > 5
        ):
            info["clock_disagreement_s"] = round(
                info["reader_age_seconds"] - info["age_seconds"], 1
            )
        ids = envelope.get("candidate_ids")
        info["candidate_id_count"] = len(ids) if isinstance(ids, list) else None
        info["pool_counts"] = envelope.get("pool_counts")
        info["source_watermark"] = envelope.get("source_watermark")
        keys[label] = info
    state["keys"] = keys

    # A payload key we could not read leaves the whole rail's answer partial —
    # the kill switch reading fine does not make the base's state known. Both
    # payload keys unreadable is a dependency loss, not a configuration.
    state["completeness"] = health_reads.completeness(reads)
    degraded = [label for label, read in reads.items() if read.unavailable]
    if len(degraded) == len(reads):
        state["status"] = "unavailable"
    elif degraded:
        state["status"] = "partial"
    state["degraded_keys"] = degraded

    # What provenance an anonymous cold request would get RIGHT NOW. This must
    # apply the PRODUCTION reader's policy (`candidate_base._usable`: schema +
    # identity + a non-negative age inside the relevant max age), not a laxer
    # "structurally valid" test — an expired last-good was previously advertised
    # as serveable forever.
    now_dt = datetime.now(timezone.utc)

    def _usable(label: str, max_age_s: float) -> bool:
        envelope = envelopes.get(label)
        return envelope is not None and cb._usable(envelope, now_dt, max_age_s, identity)

    if not state["enabled"]:
        state["would_serve"] = cb.PROV_DISABLED
    elif _usable("fresh", cb.CANDIDATE_BASE_FRESH_SECONDS):
        state["would_serve"] = cb.PROV_FRESH
    elif _usable("fresh", cb.CANDIDATE_BASE_LAST_GOOD_MAX_AGE_S) or _usable(
        "last_good", cb.CANDIDATE_BASE_LAST_GOOD_MAX_AGE_S
    ):
        state["would_serve"] = cb.PROV_LAST_GOOD
    elif degraded:
        # We cannot see what the reader would see, so we must not claim it would
        # fall through to a direct query.
        state["would_serve"] = None
        state["would_serve_status"] = "unknown"
    else:
        state["would_serve"] = cb.PROV_DIRECT

    # The production reader can also serve a PROCESS-LOCAL last-good that is
    # invisible from here (a warm dyno surviving a Redis outage), so this is the
    # Redis-visible inference, not a promise about a specific dyno.
    state["would_serve_scope"] = "redis_visible"

    return state


@router.get("/category-precompute/last")
async def get_category_precompute_last(
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
):
    """Last category-page precompute run report (#1484, read-only).

    Makes the grid warm's dispatch/start/success/failure observable. Before
    this, a league whose warm timed out was swallowed into a log line and the
    task's return value listed only the SUCCESSES — so "the MLB grid warm timed
    out" and "the task never reached grids" (they run last) were the same
    observation from outside. Tuning the task's time limits without this rail
    would be tuning blind.
    """
    _check_admin_secret(secret, request=request)

    from app.tasks.precompute_category_pages import (
        PRECOMPUTE_STATUS_KEY,
        PRECOMPUTE_STATUS_TTL,
    )

    read = health_reads.read_json_key(PRECOMPUTE_STATUS_KEY)
    if read.unavailable:
        raise HTTPException(
            status_code=503, detail=f"Redis unavailable: {read.error}"
        )

    if read.missing:
        return {
            "status": "unknown",
            "report": None,
            "key": PRECOMPUTE_STATUS_KEY,
            "ttl_s": PRECOMPUTE_STATUS_TTL,
            "note": (
                "No report present. The beat runs hourly at :25 and the report "
                "is written even on failure, so an absent report means the task "
                "did not run (or was hard-killed before its finally block)."
            ),
        }

    if read.status == health_reads.MALFORMED:
        return {
            "status": "unparseable",
            "key": PRECOMPUTE_STATUS_KEY,
            "error_class": read.error_class,
            "error": read.error,
            "report": None,
        }

    # A report that decodes to a list/scalar is not a report. Previously it was
    # returned as `status: ok`, so a consumer reading `report["sections"]` broke
    # downstream instead of here, where the fault actually is.
    if read.status == health_reads.WRONG_SHAPE:
        return {
            "status": "wrong_shape",
            "key": PRECOMPUTE_STATUS_KEY,
            "error_class": read.error_class,
            "error": read.error,
            "report": None,
        }

    report = read.value
    # Schema + freshness annotation only — the producer is untouched. `sections`
    # is what every consumer indexes; a report missing it is structurally
    # incomplete even though it parsed.
    missing_fields = [f for f in ("sections",) if f not in report]
    age_s = health_reads.age_seconds(
        report.get("generated_at") or report.get("completed_at") or report.get("started_at")
    )
    return {
        "status": "ok" if not missing_fields else "incomplete_schema",
        "key": PRECOMPUTE_STATUS_KEY,
        "missing_fields": missing_fields,
        "age_seconds": age_s,
        "stale": (age_s is not None and age_s > PRECOMPUTE_STATUS_TTL),
        "report": report,
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


async def _sentinel_last_payload(key: str, db=None, *, identity: str | None = None) -> dict:
    """Shared fail-honest read for every cached sentinel ``/last`` rail (#1197).

    Each of these rails used to be a bare ``get_redis_client().get(key)`` plus
    ``json.loads`` — so a dead store, an evicted key and a half-written payload
    were an opaque 500, while ONLY a genuine absence produced the honest
    ``no_run_cached``. The four cases are now distinct:

    * dependency loss (construction or command)  → bounded **503**
    * the store answered and the key is absent   → ``no_run_cached`` (unchanged)
    * bytes that do not decode                   → ``unparseable`` + error class
    * decodes to a non-object                    → ``wrong_shape``

    Queue 298 (#1512) adds the tier that makes those distinctions worth having.
    Typing an unreadable Redis correctly did not put the evidence back — the
    scorecards were being EVICTED from a 49.5/50MB allkeys-lru instance, so a
    healthy nightly beat still read ``no_run_cached`` by morning. When the
    producer has been migrated to the durable substrate, the rail now serves the
    retained verdict with an additive dated ``provenance`` block; ``no_run_cached``
    is reserved for the case where BOTH tiers genuinely have nothing.

    The happy path still returns the sentinel's persisted payload verbatim, so
    every existing consumer of these rails is unaffected.
    """
    # The durable tier is strictly ADDITIVE: if it can serve a trustworthy
    # retained verdict it does (that is the whole point — an evicted key or a
    # dead Redis no longer erases the evidence), and in every other case we fall
    # through to the Queue 294 classification below, unchanged. That keeps a
    # dependency loss a bounded 503 and a genuine absence ``no_run_cached``,
    # rather than trading one blind answer for another.
    if identity is not None and db is not None:
        try:
            from app.services.durable_snapshots import read_sentinel_evidence

            served = await read_sentinel_evidence(db, identity=identity, redis_key=key)
            if served is not None:
                return served
        except Exception:  # noqa: BLE001 — never let the new tier break the rail
            logger.warning(
                "sentinel rail %s: durable read failed, falling back to Redis",
                identity, exc_info=True,
            )

    # Un-migrated families (the Board Sentinel, whose producer is owned by an
    # active sibling edit) and every unservable case keep the Queue 294 behavior.
    read = health_reads.read_json_key(key)
    if read.unavailable:
        raise HTTPException(status_code=503, detail=f"Redis unavailable: {read.error}")
    if read.missing:
        return {"status": "no_run_cached", "key": key}
    if read.status == health_reads.MALFORMED:
        return {
            "status": "unparseable",
            "key": key,
            "error_class": read.error_class,
            "error": read.error,
        }
    if read.status == health_reads.WRONG_SHAPE:
        return {
            "status": "wrong_shape",
            "key": key,
            "error_class": read.error_class,
            "error": read.error,
        }
    return read.value


@router.get("/calibration-sentinel/last")
async def get_calibration_sentinel_last(
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
    backtest: bool = Query(False, description="Read the last backtest run instead of the last live run"),
    db: AsyncSession = Depends(get_db),
):
    """#1054: read the last cached Calibration Sentinel run (findings + filed
    issues). Lets an enqueued worker run be inspected without a web-request scan."""
    _check_admin_secret(secret, request=request)

    key = (
        "bainluck:calibration_sentinel:last_backtest"
        if backtest
        else "bainluck:calibration_sentinel:last"
    )
    identity = "sentinel:calibration:backtest" if backtest else "sentinel:calibration"
    return await _sentinel_last_payload(key, db, identity=identity)


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
    db: AsyncSession = Depends(get_db),
):
    """#1078: read the last cached Flow Sentinel run (scorecard + filed issues).
    Lets an enqueued worker run be inspected without re-running the flows, and is
    the persisted scorecard the cockpit can tile later."""
    _check_admin_secret(secret, request=request)

    return await _sentinel_last_payload(
        "bainluck:flow_sentinel:last", db, identity="sentinel:flow"
    )


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
    db: AsyncSession = Depends(get_db),
):
    """Queue #196: read the last cached Grid Sentinel run (verdict scorecard +
    filed issues). Lets an enqueued worker run be inspected without re-running,
    and is the persisted scorecard the cockpit grid tile consumes."""
    _check_admin_secret(secret, request=request)

    return await _sentinel_last_payload(
        "bainluck:grid_sentinel:last", db, identity="sentinel:grid"
    )


@router.post("/grid-register-sentinel/run")
async def trigger_grid_register_sentinel(
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
    apply: bool = Query(False, description="Publish validated register versions (default: dry-run/diff only)"),
    file_issues: bool = Query(True, description="File GitHub issues (False = detect-only)"),
    inline: bool = Query(False, description="Run inline and return the scorecard (default: enqueue on worker)"),
):
    """Queue #295: on-demand run of the Grid Register Sentinel.

    Diffs each committed grid register against current source inventory.
    Defaults to ``apply=false`` — it reports the diff and any proposed version
    without publishing, which is the intended way to inspect drift
    (?inline=true&file_issues=false). Ambiguous drift is never applied.
    Identity only; never writes market data (gotcha #21)."""
    _check_admin_secret(secret, request=request)

    if inline:
        from app.tasks.grid_register_sentinel import _run_grid_register_sentinel

        return await _run_grid_register_sentinel(apply=apply, file_issues=file_issues)

    result = _safe_send_task(
        "app.tasks.grid_register_sentinel",
        kwargs={"apply": apply, "file_issues": file_issues},
    )
    return {"status": "enqueued", "task_id": result.id}


@router.get("/grid-register-sentinel/last")
async def get_grid_register_sentinel_last(
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
    db: AsyncSession = Depends(get_db),
):
    """Queue #295: read the last cached Grid Register Sentinel run — per-league
    register version, age, missing/settled/live counts, drift and ambiguity
    counts, and any failure cause."""
    _check_admin_secret(secret, request=request)

    return await _sentinel_last_payload(
        "bainluck:grid_register_sentinel:last", db, identity="sentinel:grid-register"
    )


@router.get("/grid-register/proposal")
async def get_grid_register_proposal(
    request: Request,
    league: str = Query(..., description="League slug, e.g. nba/nhl/mlb/nfl"),
    secret: str = Query(None, description="Admin secret for authorization"),
    include_entries: bool = Query(True, description="Include the full proposed register body"),
    db: AsyncSession = Depends(get_db),
):
    """Queue #296: read-only grid-register proposal for pre-commit review.

    Register files are committed to the repo, but they can only be *generated*
    against production inventory — there is no local DATABASE_URL, which is why
    Queue 295 shipped the generator with no register alongside it. This rail runs
    the SAME shared observation path as ``scripts/generate_grid_register.py`` and
    the daily sentinel (``generate_register``), then returns the proposed
    register, every unresolved ambiguity, and the validator's findings, so the
    file can be reviewed by a human and committed by hand.

    Strictly read-only: it writes no register file and touches no market data
    (gotcha #21). A proposal that fails validation comes back with its findings
    and ``publishable: false`` — it is never presented as ready to commit.
    """
    _check_admin_secret(secret, request=request)

    from app.config.league_configs import get_all_league_slugs, get_league_config
    from app.services.grid_register_source import generate_register
    from app.utils.grid_register import build_contract, register_filename, validate_register

    config = get_league_config(league)
    if not config:
        raise HTTPException(
            status_code=404,
            detail=f"unknown league {league!r}; have {sorted(get_all_league_slugs())}",
        )

    register, unresolved = await generate_register(db, config)

    contract = build_contract({
        config.slug: {
            "season": config.season_pattern,
            "stages": [c.key for c in config.columns],
        },
    })
    findings = validate_register(register, contract)

    status_counts: dict[str, int] = {}
    for entry in register["entries"]:
        status_counts[entry["status"]] = status_counts.get(entry["status"], 0) + 1
    reasons: dict[str, int] = {}
    for row in unresolved:
        reasons[row["reason"]] = reasons.get(row["reason"], 0) + 1

    return {
        "league": config.slug,
        "season": config.season_pattern,
        "filename": register_filename(config.slug, config.season_pattern),
        "entries_total": len(register["entries"]),
        "status_counts": dict(sorted(status_counts.items())),
        "unresolved_total": len(unresolved),
        "unresolved_reasons": dict(sorted(reasons.items())),
        "findings": findings,
        "publishable": not findings,
        "register": register if include_entries else None,
        "unresolved": unresolved,
    }


@router.post("/board-sentinel/run")
async def trigger_board_sentinel(
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
    file_issues: bool = Query(True, description="File/close GitHub issues (False = detect-only)"),
    inline: bool = Query(False, description="Run inline and return the verdict (default: enqueue on worker)"),
):
    """Queue #258: on-demand run of the Board Sentinel.

    Enqueues the daily board-hygiene task, or (inline=True) runs it in-request and
    returns the verdict scorecard — handy for verification
    (?inline=true&file_issues=false). Classifies board-hygiene findings as REAL vs
    UNKNOWN (API/auth inability is never GREEN); files ONE deduped board-cleanup
    issue on RED and closes it on GREEN via the shared filing rail. Read-only
    against GitHub — never bulk-mutates the board (Ops owns the one-time cleanup)."""
    _check_admin_secret(secret, request=request)

    if inline:
        from app.tasks.board_sentinel import _run_board_sentinel

        return await _run_board_sentinel(file_issues=file_issues)

    result = _safe_send_task(
        "app.tasks.board_sentinel",
        kwargs={"file_issues": file_issues},
    )
    return {"status": "enqueued", "task_id": result.id}


@router.get("/board-sentinel/last")
async def get_board_sentinel_last(
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
):
    """Queue #258: read the last cached Board Sentinel run (verdict + counts +
    offenders). Lets an enqueued worker run be inspected without re-running, and is
    the persisted verdict the cockpit board tile consumes."""
    _check_admin_secret(secret, request=request)

    # Not yet migrated to the durable substrate: the Board Sentinel producer is
    # owned by an active sibling edit and is excluded from Queue 298. This rail
    # keeps the Queue 294 typed-Redis behavior until that lands.
    return await _sentinel_last_payload("bainluck:board_sentinel:last")


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
    db: AsyncSession = Depends(get_db),
):
    """Queue #223: read the last cached Horizon Sentinel run (scorecard + filed
    issues). Lets an enqueued worker run be inspected without re-running the
    calendar walk."""
    _check_admin_secret(secret, request=request)

    return await _sentinel_last_payload(
        "bainluck:horizon_sentinel:last", db, identity="sentinel:horizon"
    )


# ---------------------------------------------------------------------------
# Ops snapshot (#237 Item 1) — one compact digest for ops rounds / Item-0 reads
# ---------------------------------------------------------------------------

_OPS_SNAPSHOT_CACHE: dict = {"at": 0.0, "data": None}
_OPS_SNAPSHOT_TTL = 300  # 5 min


def _ops_compact(payload) -> dict:
    """Compact a cached sentinel/warm payload down to an ops digest: keep scalar
    top-level fields (incl. ``generated_at``) verbatim and replace list values with
    a ``<key>_count``. Nested dicts are dropped to stay small. Robust to whatever
    schema each source persists.

    A non-dict payload means the key was READ and held nothing usable — callers
    that could not read the key at all must use the read's own status object
    (``RedisRead.as_status()``) instead, so an outage never lands here."""
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
    whole snapshot. 5-min in-process cache (``fresh=true`` to bypass).

    C102 fix: "guarded" used to mean "swallowed". Every read now carries its own
    classified status, so a Redis outage reads as ``unavailable`` with a cause
    rather than borrowing the vocabulary of a cold cache (``no_data`` /
    ``no_run_cached``) or a genuine zero. The envelope reports ``completeness``,
    and a degraded snapshot is cached only with that provenance attached — it can
    no longer masquerade as an ordinary cold beat for five minutes.
    """
    _check_admin_secret(secret, request=request)

    import time as _time

    now = _time.time()
    if not fresh and _OPS_SNAPSHOT_CACHE["data"] is not None:
        age = now - _OPS_SNAPSHOT_CACHE["at"]
        if age < _OPS_SNAPSHOT_TTL:
            cached = dict(_OPS_SNAPSHOT_CACHE["data"])
            cached["cache"] = "hit"
            # Explicit cache provenance: `generated_at` is preserved (it is the
            # compute stamp, not the read stamp), and the age of the thing being
            # served is stated rather than inferred.
            cached["cache_age_s"] = round(age, 1)
            cached["cache_source"] = "in_process"
            cached["cache_ttl_s"] = _OPS_SNAPSHOT_TTL
            return cached

    from app.tasks.redis_state import (
        get_all_task_metrics,
        get_odds_api_quota,
        get_task_metrics,
    )

    reads: dict[str, health_reads.RedisRead] = {}
    r, client_failure = health_reads.client(key="ops-snapshot")

    def _read(field: str, key: str) -> health_reads.RedisRead:
        """One classified warm read, recorded for the completeness rollup."""
        if r is None:
            failed = health_reads.RedisRead(
                status=health_reads.UNAVAILABLE,
                key=key,
                error_class=client_failure.error_class,
                error=client_failure.error,
            )
            reads[field] = failed
            return failed
        read = health_reads.read_json(r, key)
        reads[field] = read
        return read

    def _compact_field(field: str, key: str) -> dict:
        """``_ops_compact`` for a readable key; a status object for one we could
        not read. The two must never collapse into the same shape."""
        read = _read(field, key)
        if read.degraded:
            return read.as_status()
        if read.missing:
            return {"status": "no_data", "source": key}
        return _ops_compact(read.value)

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
            return {
                "status": "error",
                "error_class": exc.__class__.__name__,
                "error": health_reads.redact(exc),
            }

    snapshot: dict = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "cache": "miss",
        "cache_source": "computed",
        "cache_age_s": 0.0,
    }

    # 1. Link rate + matured linkage (warm Redis keys — never recompute).
    lr_read = _read("link_rate", "bainluck:admin:link_rate")
    if lr_read.degraded:
        snapshot["link_rate"] = lr_read.as_status()
    elif lr_read.missing:
        snapshot["link_rate"] = {"status": "no_data", "source": lr_read.key}
    else:
        snapshot["link_rate"] = {
            "overall": lr_read.value.get("overall"),
            "generated_at": lr_read.value.get("generated_at"),
            "age_seconds": health_reads.payload_age_seconds(lr_read.value),
        }
    snapshot["matured_linkage"] = _compact_field(
        "matured_linkage", "bainluck:admin:matured_linkage"
    )

    # 2. Coverage poll counts.
    snapshot["coverage"] = {
        "poll_kalshi": _metric_subset("poll_kalshi"),
        "poll_polymarket": _metric_subset("poll_polymarket"),
    }

    # 3. Cal-beat health.
    snapshot["cal_beat"] = _metric_subset("calibration_prices")

    # 4. Time-horizon state (calibration time-horizon precompute).
    snapshot["time_horizon"] = _compact_field(
        "time_horizon", "bainluck:calibration:time_horizon"
    )

    # 5. The three sentinel verdicts (+ generated_at, via _ops_compact).
    snapshot["sentinels"] = {
        "flow": _compact_field("sentinel_flow", "bainluck:flow_sentinel:last"),
        "calibration": _compact_field(
            "sentinel_calibration", "bainluck:calibration_sentinel:last"
        ),
        "grid": _compact_field("sentinel_grid", "bainluck:grid_sentinel:last"),
    }

    # 6. Quota.
    try:
        snapshot["quota"] = get_odds_api_quota()
    except Exception as exc:  # noqa: BLE001
        snapshot["quota"] = {
            "status": "error",
            "error_class": exc.__class__.__name__,
            "error": health_reads.redact(exc),
        }

    # 7. Top Sentry 24h (cached beat — never a live Sentry call here).
    # #1501: the Sentry rail is already dark when its quota is exhausted; making
    # "no token", "beat never ran", and "cannot read Redis" the same `no_data`
    # compounded that. They stay separate.
    sentry_read = _read("sentry", "bainluck:sentry:top_24h")
    if sentry_read.degraded:
        snapshot["sentry"] = sentry_read.as_status()
    elif sentry_read.missing:
        snapshot["sentry"] = {"status": "no_data", "source": sentry_read.key}
    else:
        snapshot["sentry"] = sentry_read.value

    # 8. Celery / queue health.
    depths: dict = {}
    for q in ("background", "realtime", "heavy"):
        if r is None:
            depths[q] = None
            continue
        depth = health_reads.command(q, lambda queue=q: r.llen(queue))
        # A depth we could not read is NOT a depth of zero and not a plain null:
        # it says so.
        depths[q] = depth.value if depth.ok else depth.as_status()
    try:
        health_counts: dict = {}
        for m in get_all_task_metrics() or []:
            h = m.get("health") or "unknown"
            health_counts[h] = health_counts.get(h, 0) + 1
        snapshot["celery"] = {"queue_depths": depths, "task_health": health_counts}
    except Exception as exc:  # noqa: BLE001
        snapshot["celery"] = {
            "status": "error",
            "error_class": exc.__class__.__name__,
            "error": health_reads.redact(exc),
            "queue_depths": depths,
        }

    snapshot["completeness"] = health_reads.completeness(reads)

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
    db: AsyncSession = Depends(get_db),
):
    """Queue #226: read the last cached Settled-Concept Sentinel run (scorecard +
    filed issues) without re-running the checks."""
    _check_admin_secret(secret, request=request)

    return await _sentinel_last_payload(
        "bainluck:settled_concept_sentinel:last", db, identity="sentinel:settled-concept"
    )


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
