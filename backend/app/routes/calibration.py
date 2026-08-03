"""Public calibration endpoint — no auth required, cached for 1 hour."""

import logging
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.routes.admin_utils import _check_admin_secret
from app.services import get_db, get_db_rw

# Queue #257 Item 1: the in-request calibration fallback used to re-implement the
# whole CTE chain + wilson_ci / bootstrap_mce_ci / _compute_horizon_mce here (a
# drifting second copy). It now delegates to the ONE shared
# app.tasks.precompute_calibration.compute_calibration_payload, so those local
# stats helpers (and their math/random/select/func imports) are gone.

logger = logging.getLogger(__name__)

router = APIRouter()

_cache: dict = {"data": None, "timestamp": 0}
CACHE_TTL = 3600


@router.get("/calibration/outcome-timeline")
async def calibration_outcome_timeline(
    request: Request,
    db: AsyncSession = Depends(get_db),
    secret: str = Query(""),
    market_ext_id: str = Query(...),
    source: str = Query("kalshi"),
):
    """Show snapshot timeline for all outcomes in a market."""
    _check_admin_secret(secret, request=request)

    result = await db.execute(text("""
        SELECT fo.name AS outcome, fo.opening_probability, fo.calibration_probability,
            fo.current_probability, fm.commence_time,
            fos.probability, fos.captured_at
        FROM futures_outcomes fo
        JOIN futures_markets fm ON fm.id = fo.market_id
        LEFT JOIN futures_odds_snapshots fos ON fos.outcome_id = fo.id
        WHERE fm.source = :source AND fm.external_id = :ext_id
        ORDER BY fo.name, fos.captured_at
    """), {"source": source, "ext_id": market_ext_id})

    by_outcome: dict = {}
    for r in result:
        name = r.outcome
        if name not in by_outcome:
            by_outcome[name] = {
                "outcome": name,
                "opening": float(r.opening_probability) if r.opening_probability else None,
                "calibration": float(r.calibration_probability) if r.calibration_probability else None,
                "current": float(r.current_probability) if r.current_probability else None,
                "commence_time": str(r.commence_time) if r.commence_time else None,
                "snapshots": [],
            }
        if r.probability is not None:
            by_outcome[name]["snapshots"].append({
                "t": str(r.captured_at),
                "p": round(float(r.probability), 4),
            })

    return {"market": market_ext_id, "outcomes": list(by_outcome.values())}


@router.get("/calibration/bucket-debug")
async def calibration_bucket_debug(
    request: Request,
    db: AsyncSession = Depends(get_db),
    secret: str = Query(""),
    category: str = Query("golf"),
    source: str = Query("kalshi"),
    bucket: int = Query(1),
):
    """Show specific outcomes in a calibration bucket for debugging.

    Queue #262 Item 2: samples from the CANONICAL published population (``deduped``)
    and reports the truth as ``is_winner`` — never terminal ``current_probability``.
    Every returned outcome is a row the published curve actually buckets, so the
    debug view matches what the point is built from (no eligibility drift).
    """
    _check_admin_secret(secret, request=request)

    from app.tasks.precompute_calibration import (
        CALIBRATION_POPULATION_VERSION,
        _calibration_population_ctes,
    )

    rows = (await db.execute(
        text("WITH " + _calibration_population_ctes() + """
        SELECT d.outcome_name, fm.name AS market_name,
            d.raw_cp AS opening,
            d.adj_opening_probability AS used_prob,
            d.is_winner AS is_winner,
            fm.external_id AS market_ext_id,
            fm.group_id, fm.commence_time,
            (SELECT COUNT(*) FROM futures_odds_snapshots fos WHERE fos.outcome_id = d.outcome_id) AS snap_count
        FROM deduped d
        JOIN futures_markets fm ON fm.id = d.market_id
        WHERE d.source = :source
          AND d.category = :category
          AND LEAST(FLOOR(d.adj_opening_probability * 10)::int, 9) = :bucket
        ORDER BY RANDOM()
        LIMIT 25
    """), {"source": source, "category": category, "bucket": bucket})).all()

    return {
        "population_version": CALIBRATION_POPULATION_VERSION,
        "source": source, "category": category, "bucket_idx": bucket,
        "outcomes": [
            {"outcome": r.outcome_name, "market": (r.market_name or "")[:80],
             "raw_price": float(r.opening) if r.opening is not None else None,
             "used_prob": float(r.used_prob) if r.used_prob is not None else None,
             "resolved": "winner" if r.is_winner else "loser",
             "market_ext_id": r.market_ext_id, "group_id": r.group_id,
             "snap_count": r.snap_count,
             "commence_time": str(r.commence_time) if r.commence_time else None}
            for r in rows
        ],
    }


@router.get("/calibration/snapshot-health")
async def calibration_snapshot_health(
    request: Request,
    db: AsyncSession = Depends(get_db),
    secret: str = Query(""),
):
    """How many calibration-eligible outcomes have 0 snapshots?

    Queue #262 Item 2: the "calibration-eligible" population is the CANONICAL
    published set (``deduped``) — not a terminal ``current_probability`` band proxy
    — so snapshot coverage is measured over the outcomes the curve is actually
    built from.
    """
    _check_admin_secret(secret, request=request)

    from app.tasks.precompute_calibration import (
        CALIBRATION_POPULATION_VERSION,
        _calibration_population_ctes,
    )

    result = await db.execute(text("WITH " + _calibration_population_ctes() + """
        SELECT d.source,
            d.category AS cat,
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE NOT EXISTS (
                SELECT 1 FROM futures_odds_snapshots fos WHERE fos.outcome_id = d.outcome_id
            )) AS zero_snap,
            COUNT(*) FILTER (WHERE fo.calibration_probability IS NOT NULL
                AND fo.calibration_probability = fo.opening_probability) AS price_stuck
        FROM deduped d
        JOIN futures_outcomes fo ON fo.id = d.outcome_id
        GROUP BY d.source, d.category
        HAVING COUNT(*) >= 50
        ORDER BY COUNT(*) DESC
    """))

    out = [
        {"source": r.source, "category": r.cat, "total": r.total,
         "zero_snap": r.zero_snap,
         "pct_zero": round(r.zero_snap * 100.0 / max(r.total, 1), 1),
         "price_stuck": r.price_stuck,
         "pct_stuck": round(r.price_stuck * 100.0 / max(r.total, 1), 1)}
        for r in result
    ]
    total_all = sum(r["total"] for r in out)
    total_zero = sum(r["zero_snap"] for r in out)
    total_stuck = sum(r["price_stuck"] for r in out)

    return {
        "population_version": CALIBRATION_POPULATION_VERSION,
        "total_outcomes": total_all,
        "zero_snapshots": total_zero,
        "pct_zero": round(total_zero * 100.0 / max(total_all, 1), 1),
        "price_stuck": total_stuck,
        "pct_stuck": round(total_stuck * 100.0 / max(total_all, 1), 1),
        "by_source_category": out,
    }


@router.get("/calibration/unchanged-samples")
async def calibration_unchanged_samples(
    request: Request,
    db: AsyncSession = Depends(get_db),
    secret: str = Query(""),
):
    """Show specific outcomes where calibration_probability = opening_probability."""
    _check_admin_secret(secret, request=request)

    # Sample of unchanged outcomes by category, with snapshot count and volume
    result = await db.execute(text("""
        SELECT fm.source, COALESCE(fm.llm_sport_category, 'uncategorized') AS cat,
            fm.name AS market_name, fo.name AS outcome_name,
            fo.opening_probability, fo.calibration_probability,
            fo.current_probability,
            fm.volume, fm.volume_24h, fm.liquidity,
            (SELECT COUNT(*) FROM futures_odds_snapshots fos WHERE fos.outcome_id = fo.id) AS snap_count,
            (SELECT ROUND(AVG(fos.probability)::numeric, 4)
             FROM futures_odds_snapshots fos WHERE fos.outcome_id = fo.id
             AND fos.probability > 0 AND fos.probability < 1) AS avg_snap_prob,
            (SELECT MIN(fos.probability)
             FROM futures_odds_snapshots fos WHERE fos.outcome_id = fo.id
             AND fos.probability > 0 AND fos.probability < 1) AS min_snap_prob,
            (SELECT MAX(fos.probability)
             FROM futures_odds_snapshots fos WHERE fos.outcome_id = fo.id
             AND fos.probability > 0 AND fos.probability < 1) AS max_snap_prob
        FROM futures_outcomes fo
        JOIN futures_markets fm ON fm.id = fo.market_id
        WHERE fm.status = 'resolved'
          AND fo.opening_probability IS NOT NULL
          AND fo.opening_probability > 0 AND fo.opening_probability < 1
          AND fo.calibration_probability = fo.opening_probability
          AND fo.current_probability IS NOT NULL
          AND (fo.current_probability >= 0.95 OR fo.current_probability <= 0.05)
        ORDER BY RANDOM()
        LIMIT 50
    """))
    samples = []
    for r in result:
        samples.append({
            "source": r.source, "category": r.cat,
            "market": r.market_name[:80], "outcome": r.outcome_name[:50],
            "opening": float(r.opening_probability),
            "calibration": float(r.calibration_probability),
            "resolved_to": "winner" if r.current_probability >= 0.95 else "loser",
            "volume": r.volume, "snap_count": r.snap_count,
            "snap_range": f"{float(r.min_snap_prob):.3f}-{float(r.max_snap_prob):.3f}" if r.min_snap_prob else "none",
            "avg_snap": float(r.avg_snap_prob) if r.avg_snap_prob else None,
        })

    # Summary by source + category
    summary = await db.execute(text("""
        SELECT fm.source, COALESCE(fm.llm_sport_category, 'uncategorized') AS cat,
            COUNT(*) AS n,
            COUNT(CASE WHEN fm.volume IS NULL THEN 1 END) AS vol_null,
            COUNT(CASE WHEN fm.volume > 0 THEN 1 END) AS vol_positive,
            ROUND(AVG(
                (SELECT COUNT(*) FROM futures_odds_snapshots fos WHERE fos.outcome_id = fo.id)
            )::numeric, 1) AS avg_snaps
        FROM futures_outcomes fo
        JOIN futures_markets fm ON fm.id = fo.market_id
        WHERE fm.status = 'resolved'
          AND fo.opening_probability IS NOT NULL
          AND fo.opening_probability > 0 AND fo.opening_probability < 1
          AND fo.calibration_probability = fo.opening_probability
          AND fo.current_probability IS NOT NULL
          AND (fo.current_probability >= 0.95 OR fo.current_probability <= 0.05)
        GROUP BY fm.source, cat
        HAVING COUNT(*) >= 50
        ORDER BY COUNT(*) DESC
        LIMIT 20
    """))
    cat_summary = [
        {"source": r.source, "category": r.cat, "n": r.n,
         "vol_null": r.vol_null, "vol_positive": r.vol_positive,
         "pct_vol_null": round(r.vol_null * 100.0 / max(r.n, 1), 1),
         "avg_snaps": float(r.avg_snaps)}
        for r in summary
    ]

    return {"summary": cat_summary, "samples": samples}


@router.get("/calibration/volume-samples")
async def calibration_volume_samples(
    request: Request,
    db: AsyncSession = Depends(get_db),
    secret: str = Query(""),
    category: str = Query("soccer"),
):
    """Sample resolved Polymarket markets with $0 volume to check if it's real."""
    _check_admin_secret(secret, request=request)

    result = await db.execute(text("""
        SELECT fm.name, fm.external_id, fm.volume, fm.volume_24h,
            fm.liquidity, fm.volume_updated_at, fm.commence_time,
            fm.created_at, fm.updated_at, fm.status,
            COUNT(fo.id) AS outcome_count,
            (SELECT COUNT(*) FROM futures_odds_snapshots fos
             JOIN futures_outcomes fo2 ON fo2.id = fos.outcome_id
             WHERE fo2.market_id = fm.id) AS total_snapshots
        FROM futures_markets fm
        JOIN futures_outcomes fo ON fo.market_id = fm.id
        WHERE fm.source = 'polymarket'
          AND fm.status = 'resolved'
          AND COALESCE(fm.volume, 0) = 0
          AND COALESCE(fm.llm_sport_category, 'uncategorized') = :category
        GROUP BY fm.id
        ORDER BY fm.commence_time DESC NULLS LAST
        LIMIT 20
    """), {"category": category})
    zero_vol = [
        {"name": r.name, "external_id": r.external_id,
         "volume": r.volume, "volume_24h": r.volume_24h,
         "liquidity": float(r.liquidity) if r.liquidity else None,
         "volume_updated_at": str(r.volume_updated_at) if r.volume_updated_at else None,
         "commence_time": str(r.commence_time) if r.commence_time else None,
         "created_at": str(r.created_at) if r.created_at else None,
         "updated_at": str(r.updated_at) if r.updated_at else None,
         "outcome_count": r.outcome_count, "total_snapshots": r.total_snapshots}
        for r in result
    ]

    # Also get samples of markets WITH volume for comparison
    result2 = await db.execute(text("""
        SELECT fm.name, fm.external_id, fm.volume, fm.volume_24h,
            fm.liquidity, fm.volume_updated_at,
            COUNT(fo.id) AS outcome_count
        FROM futures_markets fm
        JOIN futures_outcomes fo ON fo.market_id = fm.id
        WHERE fm.source = 'polymarket'
          AND fm.status = 'resolved'
          AND fm.volume > 0
          AND COALESCE(fm.llm_sport_category, 'uncategorized') = :category
        GROUP BY fm.id
        ORDER BY fm.volume DESC
        LIMIT 10
    """), {"category": category})
    with_vol = [
        {"name": r.name, "volume": r.volume, "volume_24h": r.volume_24h,
         "liquidity": float(r.liquidity) if r.liquidity else None,
         "outcome_count": r.outcome_count}
        for r in result2
    ]

    # Count NULL vs 0
    null_vs_zero = await db.execute(text("""
        SELECT
            COUNT(CASE WHEN fm.volume IS NULL THEN 1 END) AS vol_null,
            COUNT(CASE WHEN fm.volume = 0 THEN 1 END) AS vol_zero,
            COUNT(CASE WHEN fm.volume > 0 THEN 1 END) AS vol_positive
        FROM futures_markets fm
        WHERE fm.source = 'polymarket'
          AND fm.status = 'resolved'
          AND COALESCE(fm.llm_sport_category, 'uncategorized') = :category
    """), {"category": category})
    nz = null_vs_zero.first()

    return {
        "category": category,
        "null_vs_zero": {"null": nz.vol_null, "zero": nz.vol_zero, "positive": nz.vol_positive},
        "zero_volume_samples": zero_vol,
        "high_volume_samples": with_vol,
    }


@router.get("/calibration/volume-distribution")
async def calibration_volume_distribution(
    request: Request,
    db: AsyncSession = Depends(get_db),
    secret: str = Query(""),
):
    """Volume distribution of outcomes in calibration, by source+category."""
    _check_admin_secret(secret, request=request)

    result = await db.execute(text("""
        SELECT fm.source,
            COALESCE(fm.llm_sport_category, 'uncategorized') AS cat,
            COUNT(*) AS total,
            COUNT(CASE WHEN COALESCE(fm.volume, 0) = 0 THEN 1 END) AS vol_zero,
            COUNT(CASE WHEN fm.volume > 0 AND fm.volume < 1000 THEN 1 END) AS vol_lt_1k,
            COUNT(CASE WHEN fm.volume >= 1000 AND fm.volume < 10000 THEN 1 END) AS vol_1k_10k,
            COUNT(CASE WHEN fm.volume >= 10000 AND fm.volume < 100000 THEN 1 END) AS vol_10k_100k,
            COUNT(CASE WHEN fm.volume >= 100000 THEN 1 END) AS vol_100k_plus
        FROM futures_outcomes fo
        JOIN futures_markets fm ON fm.id = fo.market_id
        WHERE fm.status = 'resolved'
          AND fo.opening_probability IS NOT NULL
          AND fo.opening_probability > 0 AND fo.opening_probability < 1
          AND fm.source = 'polymarket'
        GROUP BY fm.source, cat
        HAVING COUNT(*) >= 500
        ORDER BY COUNT(*) DESC
    """))
    return [
        {"source": r.source, "category": r.cat, "total": r.total,
         "vol_zero": r.vol_zero, "pct_zero": round(r.vol_zero * 100.0 / max(r.total, 1), 1),
         "vol_lt_1k": r.vol_lt_1k, "vol_1k_10k": r.vol_1k_10k,
         "vol_10k_100k": r.vol_10k_100k, "vol_100k_plus": r.vol_100k_plus}
        for r in result
    ]


@router.get("/calibration/price-quality")
async def calibration_price_quality(
    request: Request,
    db: AsyncSession = Depends(get_db),
    secret: str = Query(""),
):
    """Lightweight: how many outcomes still use opening prices, by source+category."""
    _check_admin_secret(secret, request=request)

    result = await db.execute(text("""
        SELECT fm.source,
            COALESCE(fm.llm_sport_category, 'uncategorized') AS cat,
            COUNT(*) AS total,
            COUNT(CASE WHEN fo.calibration_probability = fo.opening_probability THEN 1 END) AS same_as_open,
            COUNT(CASE WHEN fo.calibration_probability IS NOT NULL
                        AND fo.calibration_probability != fo.opening_probability THEN 1 END) AS price_moved,
            ROUND(AVG(ABS(COALESCE(fo.calibration_probability, 0)
                        - COALESCE(fo.opening_probability, 0)))::numeric, 4) AS avg_shift,
            ROUND(AVG(fm.volume)::numeric, 0) AS avg_volume,
            ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY COALESCE(fm.volume, 0))::numeric, 0) AS median_volume,
            ROUND(AVG(fm.volume_24h)::numeric, 0) AS avg_volume_24h
        FROM futures_outcomes fo
        JOIN futures_markets fm ON fm.id = fo.market_id
        WHERE fm.status = 'resolved'
          AND fo.opening_probability IS NOT NULL
          AND fo.opening_probability > 0 AND fo.opening_probability < 1
        GROUP BY fm.source, cat
        HAVING COUNT(*) >= 100
        ORDER BY fm.source, COUNT(*) DESC
    """))
    return [
        {"source": r.source, "category": r.cat, "total": r.total,
         "same_as_open": r.same_as_open,
         "pct_same": round(r.same_as_open * 100.0 / max(r.total, 1), 1),
         "price_moved": r.price_moved, "avg_shift": float(r.avg_shift),
         "avg_volume": int(r.avg_volume) if r.avg_volume else 0,
         "median_volume": int(r.median_volume) if r.median_volume else 0,
         "avg_volume_24h": int(r.avg_volume_24h) if r.avg_volume_24h else 0}
        for r in result
    ]


@router.get("/calibration/diagnostics")
async def calibration_diagnostics(
    request: Request,
    db: AsyncSession = Depends(get_db),
    secret: str = Query(""),
):
    """Diagnostic data for calibration debugging — admin only."""
    _check_admin_secret(secret, request=request)

    result = await db.execute(text("""
        SELECT COALESCE(fm.llm_sport_category, 'uncategorized') AS cat,
            COUNT(*) AS total,
            COUNT(CASE WHEN fo.calibration_probability = fo.opening_probability THEN 1 END) AS cal_eq_open,
            COUNT(CASE WHEN fo.calibration_probability IS NOT NULL
                        AND fo.calibration_probability != fo.opening_probability THEN 1 END) AS cal_diff,
            ROUND(AVG(ABS(COALESCE(fo.calibration_probability, 0)
                        - COALESCE(fo.opening_probability, 0)))::numeric, 4) AS avg_shift,
            COUNT(CASE WHEN fm.commence_time IS NULL THEN 1 END) AS no_commence
        FROM futures_outcomes fo
        JOIN futures_markets fm ON fm.id = fo.market_id
        WHERE fm.status = 'resolved'
          AND fo.opening_probability IS NOT NULL
          AND fo.opening_probability > 0 AND fo.opening_probability < 1
        GROUP BY cat ORDER BY total DESC
    """))
    by_category = [
        {"category": r.cat, "total": r.total, "cal_eq_open": r.cal_eq_open,
         "pct_same": round(r.cal_eq_open * 100.0 / max(r.total, 1), 1),
         "cal_diff": r.cal_diff, "avg_shift": float(r.avg_shift),
         "no_commence": r.no_commence}
        for r in result
    ]

    problem_result = await db.execute(text("""
        SELECT COALESCE(fm.llm_sport_category, 'uncategorized') AS cat, fm.source,
            COUNT(*) AS n,
            COUNT(CASE WHEN ABS(COALESCE(fo.calibration_probability, fo.opening_probability) - 0.5) < 0.05 THEN 1 END) AS near_50,
            COUNT(CASE WHEN fo.calibration_probability = fo.opening_probability THEN 1 END) AS same_as_open,
            COUNT(CASE WHEN fm.commence_time IS NULL THEN 1 END) AS no_commence,
            AVG(ABS(COALESCE(fo.calibration_probability, fo.opening_probability)
                    - fo.opening_probability)) AS avg_cal_shift
        FROM futures_outcomes fo
        JOIN futures_markets fm ON fm.id = fo.market_id
        WHERE fm.status = 'resolved'
          AND fo.opening_probability > 0 AND fo.opening_probability < 1
          AND fo.current_probability IS NOT NULL
          AND (fo.current_probability >= 0.95 OR fo.current_probability <= 0.05)
          AND COALESCE(fm.llm_sport_category, 'uncategorized') IN
              ('economics', 'hockey', 'golf', 'tennis', 'weather', 'politics',
               'basketball', 'baseball', 'soccer', 'esports', 'entertainment',
               'football', 'cricket', 'mma', 'motorsports', 'geopolitics',
               'lacrosse', 'tech', 'olympics')
        GROUP BY cat, fm.source ORDER BY cat, fm.source
    """))
    problem_cats = [
        {"category": r.cat, "source": r.source, "n": r.n, "near_50": r.near_50,
         "pct_near_50": round(r.near_50 * 100.0 / max(r.n, 1), 1),
         "same_as_open": r.same_as_open,
         "pct_same": round(r.same_as_open * 100.0 / max(r.n, 1), 1),
         "no_commence": r.no_commence,
         "avg_cal_shift": round(float(r.avg_cal_shift or 0), 4)}
        for r in problem_result
    ]

    snapshot_result = await db.execute(text("""
        SELECT COALESCE(fm.llm_sport_category, 'uncategorized') AS cat, fm.source,
            ROUND(AVG(snap_count)::numeric, 1) AS avg_snaps,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY snap_count) AS median_snaps,
            COUNT(*) AS n
        FROM (
            SELECT fo.id, fm.id AS fmid, fm.source,
                COALESCE(fm.llm_sport_category, 'uncategorized') AS fcat,
                (SELECT COUNT(*) FROM futures_odds_snapshots fos WHERE fos.outcome_id = fo.id) AS snap_count
            FROM futures_outcomes fo
            JOIN futures_markets fm ON fm.id = fo.market_id
            WHERE fm.status = 'resolved'
              AND fo.opening_probability > 0 AND fo.opening_probability < 1
              AND ABS(COALESCE(fo.calibration_probability, fo.opening_probability) - 0.5) < 0.05
              AND fo.current_probability IS NOT NULL
              AND (fo.current_probability >= 0.95 OR fo.current_probability <= 0.05)
              AND COALESCE(fm.llm_sport_category, 'uncategorized') IN ('economics', 'hockey', 'golf')
            LIMIT 2000
        ) sub
        JOIN futures_markets fm ON fm.id = sub.fmid
        GROUP BY cat, fm.source ORDER BY cat, fm.source
    """))
    snap_info = [
        {"category": r.cat, "source": r.source, "n": r.n,
         "avg_snapshots": float(r.avg_snaps), "median_snapshots": float(r.median_snaps)}
        for r in snapshot_result
    ]

    # Check why Part C rescue failed: sample stuck Polymarket outcomes
    rescue_check = await db.execute(text("""
        SELECT fm.source,
            COUNT(*) AS stuck_total,
            COUNT(CASE WHEN snap_exists THEN 1 END) AS has_any_snap,
            COUNT(CASE WHEN snap_exists AND snap_prob != fo_open THEN 1 END) AS has_diff_snap
        FROM (
            SELECT fo.id AS foid, fo.opening_probability AS fo_open,
                fm.id AS fmid, fm.source, fm.commence_time,
                EXISTS(
                    SELECT 1 FROM futures_odds_snapshots fos
                    WHERE fos.outcome_id = fo.id
                      AND fos.probability > 0 AND fos.probability < 1
                ) AS snap_exists,
                (
                    SELECT fos.probability FROM futures_odds_snapshots fos
                    WHERE fos.outcome_id = fo.id
                      AND fos.probability > 0 AND fos.probability < 1
                    ORDER BY fos.captured_at DESC LIMIT 1
                ) AS snap_prob
            FROM futures_outcomes fo
            JOIN futures_markets fm ON fm.id = fo.market_id
            WHERE fm.status = 'resolved'
              AND fo.calibration_probability IS NOT NULL
              AND fo.opening_probability IS NOT NULL
              AND fo.calibration_probability = fo.opening_probability
              AND fm.source = 'polymarket'
            LIMIT 5000
        ) sub
        JOIN futures_markets fm ON fm.id = sub.fmid
        JOIN futures_outcomes fo ON fo.id = sub.foid
        GROUP BY fm.source
    """))
    rescue_info = [
        {"source": r.source, "stuck_total": r.stuck_total,
         "has_any_snap": r.has_any_snap, "has_diff_snap": r.has_diff_snap}
        for r in rescue_check
    ]

    # Also check commence_time vs first snapshot timing
    timing_check = await db.execute(text("""
        SELECT
            COUNT(*) AS total,
            COUNT(CASE WHEN first_snap < commence_time THEN 1 END) AS snap_before_commence,
            COUNT(CASE WHEN first_snap >= commence_time THEN 1 END) AS snap_after_commence,
            ROUND(AVG(EXTRACT(EPOCH FROM (first_snap - commence_time)) / 3600)::numeric, 1) AS avg_hours_diff
        FROM (
            SELECT fm.commence_time,
                (SELECT MIN(fos.captured_at) FROM futures_odds_snapshots fos
                 WHERE fos.outcome_id = fo.id) AS first_snap
            FROM futures_outcomes fo
            JOIN futures_markets fm ON fm.id = fo.market_id
            WHERE fm.status = 'resolved'
              AND fm.source = 'polymarket'
              AND fo.calibration_probability = fo.opening_probability
              AND fo.opening_probability IS NOT NULL
            LIMIT 2000
        ) sub
        WHERE first_snap IS NOT NULL
    """))
    timing_row = timing_check.first()
    timing_info = {
        "total": timing_row.total if timing_row else 0,
        "snap_before_commence": timing_row.snap_before_commence if timing_row else 0,
        "snap_after_commence": timing_row.snap_after_commence if timing_row else 0,
        "avg_hours_first_snap_minus_commence": float(timing_row.avg_hours_diff) if timing_row and timing_row.avg_hours_diff else None,
    } if timing_row else {}

    return {
        "by_category": by_category,
        "problem_categories_in_calibration": problem_cats,
        "near_50_snapshot_counts": snap_info,
        "polymarket_rescue_check": rescue_info,
        "polymarket_timing": timing_info,
    }


@router.get("/calibration/events-funnel")
async def calibration_events_funnel(
    request: Request,
    db: AsyncSession = Depends(get_db),
    secret: str = Query(""),
):
    """Per-sport filter funnel for odds_api calibration events — admin only."""
    _check_admin_secret(secret, request=request)

    result = await db.execute(text("""
        SELECT s.key,
            COUNT(*) AS completed,
            COUNT(CASE WHEN e.opening_home_probability IS NOT NULL THEN 1 END) AS has_opening,
            COUNT(CASE WHEN e.closing_home_probability IS NOT NULL THEN 1 END) AS has_closing,
            COUNT(CASE WHEN COALESCE(e.closing_home_probability, e.opening_home_probability) IS NOT NULL THEN 1 END) AS has_any_prob,
            COUNT(CASE WHEN COALESCE(e.closing_home_probability, e.opening_home_probability) IS NOT NULL
                        AND COALESCE(e.closing_home_probability, e.opening_home_probability) > 0
                        AND COALESCE(e.closing_home_probability, e.opening_home_probability) < 1 THEN 1 END) AS prob_in_range,
            COUNT(CASE WHEN e.home_score IS NOT NULL AND e.away_score IS NOT NULL THEN 1 END) AS has_scores,
            COUNT(CASE WHEN e.home_score IS NOT NULL AND e.away_score IS NOT NULL
                        AND e.home_score != e.away_score THEN 1 END) AS no_ties,
            COUNT(CASE WHEN COALESCE(e.closing_home_probability, e.opening_home_probability) IS NOT NULL
                        AND COALESCE(e.closing_home_probability, e.opening_home_probability) > 0
                        AND COALESCE(e.closing_home_probability, e.opening_home_probability) < 1
                        AND e.home_score IS NOT NULL AND e.away_score IS NOT NULL
                        AND e.home_score != e.away_score THEN 1 END) AS passes_all_filters
        FROM events e
        JOIN sports s ON s.id = e.sport_id
        WHERE e.status IN ('completed', 'closed')
        GROUP BY s.key
        ORDER BY completed DESC
    """))
    per_sport = [
        {
            "sport_key": r.key, "completed": r.completed,
            "has_opening": r.has_opening, "has_closing": r.has_closing,
            "has_any_prob": r.has_any_prob, "prob_in_range": r.prob_in_range,
            "has_scores": r.has_scores, "no_ties": r.no_ties,
            "passes_all_filters": r.passes_all_filters,
            "pct_opening": round(r.has_opening * 100.0 / max(r.completed, 1), 1),
            "gap": r.completed - r.passes_all_filters,
        }
        for r in result
    ]

    # Monthly breakdown for key sports
    monthly = await db.execute(text("""
        SELECT s.key,
            DATE_TRUNC('month', e.commence_time)::date AS month,
            COUNT(*) AS completed,
            COUNT(CASE WHEN e.opening_home_probability IS NOT NULL THEN 1 END) AS has_opening,
            COUNT(CASE WHEN e.closing_home_probability IS NOT NULL THEN 1 END) AS has_closing
        FROM events e
        JOIN sports s ON s.id = e.sport_id
        WHERE e.status IN ('completed', 'closed')
          AND s.key IN ('baseball_mlb', 'basketball_nba', 'icehockey_nhl', 'baseball_mlb_preseason')
        GROUP BY s.key, month
        ORDER BY s.key, month
    """))
    monthly_data = [
        {"sport_key": r.key, "month": str(r.month), "completed": r.completed,
         "has_opening": r.has_opening, "has_closing": r.has_closing}
        for r in monthly
    ]

    # Events with scores but no probability at all
    no_prob = await db.execute(text("""
        SELECT s.key, COUNT(*) AS n
        FROM events e
        JOIN sports s ON s.id = e.sport_id
        WHERE e.status IN ('completed', 'closed')
          AND e.home_score IS NOT NULL AND e.away_score IS NOT NULL
          AND e.opening_home_probability IS NULL
          AND e.closing_home_probability IS NULL
        GROUP BY s.key
        ORDER BY n DESC
        LIMIT 20
    """))
    no_prob_data = [{"sport_key": r.key, "count": r.n} for r in no_prob]

    # All statuses for key sports
    status_dist = await db.execute(text("""
        SELECT s.key, e.status, COUNT(*) AS n
        FROM events e
        JOIN sports s ON s.id = e.sport_id
        WHERE s.key IN ('baseball_mlb', 'basketball_nba', 'icehockey_nhl',
                        'baseball_mlb_preseason', 'basketball_ncaab')
        GROUP BY s.key, e.status
        ORDER BY s.key, n DESC
    """))
    status_data = [
        {"sport_key": r.key, "status": r.status, "count": r.n}
        for r in status_dist
    ]

    # Check for non-completed MLB events that look like they should be completed
    stuck_mlb = await db.execute(text("""
        SELECT e.status, COUNT(*) AS n,
            MIN(e.commence_time)::date AS earliest,
            MAX(e.commence_time)::date AS latest,
            COUNT(CASE WHEN e.home_score IS NOT NULL THEN 1 END) AS has_scores
        FROM events e
        JOIN sports s ON s.id = e.sport_id
        WHERE s.key = 'baseball_mlb'
          AND e.status != 'completed'
          AND e.commence_time < NOW() - INTERVAL '1 day'
        GROUP BY e.status
        ORDER BY n DESC
    """))
    stuck_data = [
        {"status": r.status, "count": r.n,
         "earliest": str(r.earliest), "latest": str(r.latest),
         "has_scores": r.has_scores}
        for r in stuck_mlb
    ]

    return {
        "per_sport": per_sport,
        "monthly_key_sports": monthly_data,
        "no_prob_top20": no_prob_data,
        "status_distribution": status_data,
        "stuck_mlb_events": stuck_data,
    }


@router.post("/calibration/rescue")
async def calibration_rescue(
    request: Request,
    db: AsyncSession = Depends(get_db_rw),
    secret: str = Query(""),
    limit: int = Query(50000),
):
    """Run Part C rescue directly — admin only."""
    _check_admin_secret(secret, request=request)

    result = await db.execute(text("""
        WITH stuck AS (
            SELECT fo.id AS outcome_id, fo.opening_probability
            FROM futures_outcomes fo
            JOIN futures_markets fm ON fm.id = fo.market_id
            WHERE fm.status = 'resolved'
              AND fo.calibration_probability IS NOT NULL
              AND fo.opening_probability IS NOT NULL
              AND fo.calibration_probability = fo.opening_probability
            LIMIT :limit
        ),
        last_snap AS (
            SELECT DISTINCT ON (s.outcome_id)
                s.outcome_id,
                fos.probability
            FROM stuck s
            JOIN futures_odds_snapshots fos ON fos.outcome_id = s.outcome_id
            WHERE fos.probability > 0 AND fos.probability < 1
            ORDER BY s.outcome_id, fos.captured_at DESC
        )
        UPDATE futures_outcomes fo
        SET calibration_probability = ls.probability
        FROM last_snap ls
        WHERE fo.id = ls.outcome_id
          AND ls.probability != fo.opening_probability
    """), {"limit": limit})
    await db.commit()

    return {"rescued": result.rowcount, "limit": limit}


@router.get("/calibration")
async def public_calibration(
    db: AsyncSession = Depends(get_db),
    bust: int = Query(0, include_in_schema=False),
):
    """Public calibration data for the /calibration page.

    Served from Redis (precomputed by precompute_calibration_main task every 1h).
    Falls back to in-process cache, then a truthful last-good/stale payload, and
    only as a last resort a deadline-guarded compute.

    Queue 271 (#1459/#1197) hardening:
    * The Redis read is now a *shared async* client + a hard-bounded op — no more
      SYNCHRONOUS ``get_redis_client().get()`` on the async event loop (gotcha
      #39), which blocked the loop for the whole read.
    * On a Redis *failure* (stall/error) a usable in-process/last-good payload is
      served instead of recomputing during flakiness.
    * The in-request ``compute_calibration_payload`` CTE (the 12-27s cold path
      that H12'd at the router) is now wrapped in a hard compute deadline: it
      either finishes fast or fails fast + explicit (503 + Retry-After). It is
      never allowed to run toward the router cutoff and never synthesizes a curve.
    """
    import asyncio
    import json as _json

    from app.utils import request_cache as _rc
    from app.utils.calibration_coverage_bridge import ensure_census as _ensure_census
    from app.utils.calibration_publish_gate import SERVE_MAX_AGE_S, snapshot_verdict

    _lg_key = "calibration:main"

    # Queue 297 Item 1: ONE absolute budget for the whole handler. Each tier below
    # already had its own bound, but the reported failure was ~18s of opaque
    # spinning — two ~9s compute attempts, each individually legal. A whole-request
    # budget is the only thing that catches that shape.
    _started = time.monotonic()

    def _remaining_ms() -> float:
        return _rc.CALIBRATION_ROUTE_BUDGET_MS - (time.monotonic() - _started) * 1000

    def _expected_version():
        try:
            from app.tasks.precompute_calibration import CALIBRATION_POPULATION_VERSION

            return CALIBRATION_POPULATION_VERSION
        except Exception:  # noqa: BLE001 — a version we can't read isn't a mismatch
            return None

    def _degraded(payload: dict, reason: str, verdict=None) -> dict:
        """A last-good copy, marked stale and dated so the page can say how old it is.

        Never presented as current: ``status`` is always ``stale`` and the age is
        explicit, so the banner can render "as of <time>" rather than implying the
        numbers are live.
        """
        # Queue 300C: a last-good/durable copy can predate the coverage census.
        # Absent is not zero — mark it explicitly unavailable so the page cannot
        # read "no census" as "nothing was excluded".
        out = dict(_ensure_census(payload, reason="payload_predates_census"))
        cache = {"status": "stale", "reason": reason}
        if verdict is not None:
            if verdict.age_s is not None:
                cache["age_s"] = round(verdict.age_s)
            if verdict.generated_at:
                cache["generated_at"] = verdict.generated_at
        elif isinstance(payload.get("generated_at"), str):
            cache["generated_at"] = payload["generated_at"]
        out["cache"] = cache
        return out

    def _unavailable(reason: str) -> HTTPException:
        """The typed unavailable response — honest, actionable, never opaque.

        Still a 503 (the semantics are right and Retry-After is meaningful), but
        the body is structured so the page renders a dated "temporarily
        unavailable, retry" state instead of a bare "Failed to load".
        """
        return HTTPException(
            status_code=503,
            detail={
                "status": "unavailable",
                "reason": reason,
                "retry_after_s": 30,
                "message": (
                    "Calibration data is temporarily unavailable. It is rebuilt "
                    "hourly — please retry shortly."
                ),
            },
            headers={"Retry-After": "30"},
        )

    # 1. In-process cache (survives between requests on same dyno). A
    #    stale-marked copy (Tier 2b, main key absent) is deliberately NOT served
    #    from here: it stays honestly marked on every response, but each request
    #    re-attempts Redis main so a later fresh-main read replaces it promptly
    #    (Queue #284 Item 3). TTL and compute behavior are unchanged.
    now = time.time()
    if (
        not bust
        and isinstance(_cache["data"], dict)
        and (now - _cache["timestamp"]) < CACHE_TTL
        and _cache["data"].get("cache", {}).get("status") != "stale"
    ):
        return _cache["data"]

    # 2. Redis precomputed cache (survives deploys) — shared async client + a
    #    hard-bounded op so a Redis stall can never block the loop or the router.
    _redis_failed = False
    try:
        rc = await _rc.get_shared_async_redis()
        res = await _rc.bounded_redis_call(lambda: rc.get("bainluck:calibration:main"))
        if res.is_ok:
            data = _json.loads(res.value)
            # C111 P2: check the population contract at THIS tier too, not just on
            # last-good. Scope is deliberately narrow — only a version mismatch is
            # rejected here. ``main`` is written by our own publisher, which now
            # runs the stricter publish gate at WRITE time, and its 2h TTL bounds
            # its age; re-validating shape on read would mean a payload-shape
            # addition could reject a freshly published copy and degrade the page,
            # which is the exact failure this queue exists to end. The durable
            # last-good gets the full check because it can be ancient and written
            # under a different contract.
            main_verdict = snapshot_verdict(
                data, expected_version=_expected_version(), max_age_s=SERVE_MAX_AGE_S
            )
            if isinstance(data, dict) and main_verdict.status != "wrong_version":
                # Queue 300C: same guard as the stale tiers. A ``main`` key
                # written by the last pre-census build is fresh and correct for
                # the curve, but carries no census — say so explicitly.
                data = _ensure_census(data, reason="payload_predates_census")
                _cache["data"] = data
                _cache["timestamp"] = now
                _rc.remember_last_good(_lg_key, data)
                return data
            elif isinstance(data, dict):
                logger.warning(
                    "calibration: main key rejected (%s: %s) — falling back to last-good",
                    main_verdict.status, main_verdict.reason,
                )
        _redis_failed = res.is_failure
    except Exception:
        _redis_failed = True

    # 2b. Clean miss of the FRESH key (Redis healthy, ``main`` key just absent —
    #     the observed failure: the hourly precompute timed out for >2h and the 2h
    #     TTL expired). Before paying a cold compute, serve the DURABLE last-good
    #     key the precompute writes on every successful publish (Queue 272 #1459).
    #     It is served ``stale`` with its own generated_at so freshness is honest,
    #     and cached in-process so subsequent same-dyno reads are instant. ``bust``
    #     skips this to force a genuine recompute.
    if not _redis_failed and not bust:
        try:
            rc = await _rc.get_shared_async_redis()
            lg = await _rc.bounded_redis_call(
                lambda: rc.get("bainluck:calibration:main:last_good")
            )
            if lg.is_ok:
                data = _json.loads(lg.value)
                # Queue 297 Item 1: only a TRUSTWORTHY last-good may be served. A
                # cross-process durable key can be malformed, written by an older
                # population version, or simply ancient — serving any of those as
                # "the calibration curve" is the dishonesty this item closes. A
                # rejected copy falls through to the cold compute below.
                verdict = snapshot_verdict(
                    data,
                    expected_version=_expected_version(),
                    max_age_s=SERVE_MAX_AGE_S,
                )
                if verdict.is_servable:
                    # Queue #284 Item 3: build the stale-marked copy BEFORE it is
                    # memoized, so a later same-dyno Tier-1 hit cannot serve an
                    # unmarked (falsely-fresh) copy. The process cache and the
                    # durable last-good both store the marked payload.
                    degraded = _degraded(data, "main_key_absent", verdict)
                    _cache["data"] = degraded
                    _cache["timestamp"] = now
                    _rc.remember_last_good(_lg_key, degraded)
                    return degraded
                logger.warning(
                    "calibration: durable last-good rejected (%s: %s)",
                    verdict.status, verdict.reason,
                )
        except Exception:
            # Falling through to the cold compute is the right behavior, but this
            # used to be a silent `pass` — which is how a NameError in the branch
            # above stayed invisible while quietly disabling the whole last-good
            # tier. Never swallow this without saying so.
            logger.warning("calibration: durable last-good read failed", exc_info=True)

    # 3. DURABLE substrate (Queue 298, #1512). Everything above this line is an
    #    accelerator living in one 50MB allkeys-lru Redis: on eviction, on a TLS
    #    failure, or on a fresh dyno, all of it is gone at once — which is how the
    #    public page reached "Failed to load" while a perfectly good snapshot had
    #    been computed hours earlier. This tier is the survivor, and it is
    #    deliberately ABOVE the process-local fallback: durable is the authority,
    #    process memory is only ever an accelerator.
    #
    #    It is cheap (one indexed primary-key read of a bounded payload, bounded
    #    by its own statement_timeout) and it is only paid when the fast tiers
    #    have already failed. ``bust`` skips it to force a genuine recompute.
    if not bust:
        try:
            from app.services.durable_snapshots import read_snapshot

            durable = await read_snapshot(
                db,
                "calibration:main",
                expected_version=_expected_version(),
                max_age_s=SERVE_MAX_AGE_S,
            )
            if durable.ok and isinstance(durable.envelope.payload, dict):
                payload = durable.envelope.payload
                # The envelope already proved version, checksum, completeness and
                # age. The SHAPE still gets Q297's full check, because a durable
                # row can be ancient and written under an older payload contract —
                # the same reason the Redis last-good keeps it.
                verdict = snapshot_verdict(
                    payload, expected_version=_expected_version(), max_age_s=SERVE_MAX_AGE_S
                )
                if verdict.is_servable:
                    degraded = _degraded(
                        payload,
                        "redis_unavailable_durable" if _redis_failed else "main_key_absent_durable",
                        verdict,
                    )
                    # Additive provenance so an operator (and the page) can see
                    # WHICH tier answered and how old it is — never a silent
                    # substitution dressed up as current.
                    degraded["provenance"] = durable.envelope.provenance(
                        served_from="durable"
                    )
                    _cache["data"] = degraded
                    _cache["timestamp"] = now
                    _rc.remember_last_good(_lg_key, degraded)
                    return degraded
                logger.warning(
                    "calibration: durable snapshot rejected on shape (%s: %s)",
                    verdict.status, verdict.reason,
                )
            elif not durable.missing:
                logger.warning(
                    "calibration: durable snapshot unusable (%s: %s)",
                    durable.status, durable.error,
                )
        except Exception:
            # Never let the durable tier's own failure take down the request —
            # but never swallow it silently either (the Q297 lesson).
            logger.warning("calibration: durable snapshot read failed", exc_info=True)

    # 4. Redis unavailable (not a clean miss): prefer a truthful stale/last-good
    #    payload over recomputing during Redis flakiness (Queue 271 Item 2).
    #    ``bust`` explicitly asks for a fresh recompute, so it skips this.
    if _redis_failed and not bust:
        stale = (
            _cache["data"]
            if isinstance(_cache["data"], dict)
            # Queue 297: age-bound the process-local copy too. Its SHAPE is not the
            # risk (this process served it earlier), but a long-lived dyno could
            # otherwise keep serving a week-old curve as though Redis were merely
            # blipping.
            else _rc.recall_last_good(_lg_key, max_age_s=SERVE_MAX_AGE_S)
        )
        if isinstance(stale, dict):
            return _degraded(stale, "redis_unavailable")

    # 5. Clean cache miss (Redis empty, nothing durable) — compute via the ONE
    #    shared canonical path, but under a HARD deadline so it can never run to
    #    the router cutoff. On breach: serve last-good if any, else fail fast.
    from app.tasks.precompute_calibration import compute_calibration_payload

    # The compute gets whatever is left of the absolute budget, never more than its
    # own deadline. If the earlier tiers already burned the budget, we do not start
    # a compute we cannot finish — we answer honestly now (Item 1: never spin).
    compute_deadline_ms = min(_rc.CALIBRATION_COMPUTE_DEADLINE_MS, _remaining_ms())
    if compute_deadline_ms <= 0:
        raise _unavailable("route_budget_exhausted")

    try:
        data = await _rc.run_with_deadline(
            compute_calibration_payload(db),
            deadline_ms=int(compute_deadline_ms),
        )
        _cache["data"] = data
        _cache["timestamp"] = now
        _rc.remember_last_good(_lg_key, data)
        return data
    except asyncio.CancelledError:
        raise
    except Exception:
        stale = (
            _cache["data"]
            if isinstance(_cache["data"], dict)
            else _rc.recall_last_good(_lg_key, max_age_s=SERVE_MAX_AGE_S)
        )
        if isinstance(stale, dict):
            return _degraded(stale, "compute_deadline")
        raise _unavailable("no_trustworthy_snapshot")


# ---------------------------------------------------------------------------
# L2-103 Item 2: per-bucket examples drill-in
# ---------------------------------------------------------------------------

_examples_cache: dict = {}
_EXAMPLES_TTL = 3600
_FUTURES_EXAMPLE_SOURCES = {"kalshi", "polymarket"}


@router.get("/calibration/examples")
async def calibration_examples(
    db: AsyncSession = Depends(get_db),
    source: str = Query(...),
    bucket: int = Query(..., ge=0, le=9),
    well_traded: int = Query(1),
    limit: int = Query(5, ge=1, le=10),
):
    """A representative sample of the real outcomes inside one calibration bucket.

    Reader-trust feature: the /calibration By Source chart lets a skeptic click any
    point (source × 10-pt probability bucket) and see 3-5 concrete outcomes —
    market name, outcome, predicted price, settled result, settle date — so the
    bucket is verifiable, not a black box. Read-only; mirrors the published curve's
    core exclusions so the sample reflects what the bucket is actually built from.
    Cached in-process for 1h. Never mutates anything.
    """
    source = (source or "").strip()
    wt = str(well_traded) not in ("0", "false", "False", "")
    cache_key = f"{source}|{bucket}|{int(wt)}|{limit}"
    now = time.time()
    hit = _examples_cache.get(cache_key)
    if hit and (now - hit[1]) < _EXAMPLES_TTL:
        return hit[0]

    examples: list[dict] = []
    note: str | None = None

    def _fmt_dt(dt) -> str | None:
        return dt.isoformat() if dt is not None else None

    if source in _FUTURES_EXAMPLE_SOURCES:
        # Queue #262 Item 2: sample DIRECTLY from the canonical published population
        # (``deduped`` from _calibration_population_ctes) instead of re-implementing
        # eligibility. This guarantees every returned example is ACTUALLY in the
        # requested published bucket (bucketed on the SAME adj_opening_probability +
        # is_winner the curve uses), and that NULL/price-derived truth + every
        # artifact exclusion (liquidity, poly/golf placeholder, malformed binary,
        # esports bundle, prop threshold, weather wide spread, incomplete field) are
        # absent BY CONSTRUCTION — not a hand-maintained subset that drifts. Read-
        # only (gotcha #21). Heavy CTE, but the endpoint is cached 1h in-process.
        from app.tasks.precompute_calibration import _calibration_population_ctes

        # Well-traded cohort for futures = the price actually moved off its open
        # (matches the page's price_moved !== false default) — the canonical flag.
        wt_clause = "AND d.price_moved = true" if wt else ""
        sql = text(
            "WITH " + _calibration_population_ctes() + f"""
            SELECT fm.name AS market_name, d.outcome_name AS outcome_name,
                d.adj_opening_probability AS price,
                d.is_winner AS is_winner,
                COALESCE(fm.resolution_date, fm.commence_time, fm.updated_at) AS settle_date
            FROM deduped d
            JOIN futures_markets fm ON fm.id = d.market_id
            WHERE d.source = :source
              AND LEAST(FLOOR(d.adj_opening_probability * 10)::int, 9) = :bucket
              {wt_clause}
            ORDER BY RANDOM()
            LIMIT :limit
        """)
        rows = (await db.execute(sql, {"source": source, "bucket": bucket, "limit": limit})).all()
        examples = [
            {
                "market_name": r.market_name or "—",
                "outcome_name": r.outcome_name or "—",
                "price": round(float(r.price), 4),
                "result": "Yes" if r.is_winner else "No",
                "settle_date": _fmt_dt(r.settle_date),
            }
            for r in rows
        ]

    elif source in ("odds_api", "odds_api_spreads", "odds_api_totals"):
        # Event-sourced markets: reconstruct the same outcome rows the curve buckets.
        if source == "odds_api":
            sql = text("""
                SELECT market_name, outcome_name, price, won AS is_winner, settle_date FROM (
                    SELECT (home_team_name || ' vs ' || away_team_name) AS market_name,
                        home_team_name AS outcome_name,
                        COALESCE(closing_home_probability, opening_home_probability) AS price,
                        (home_score > away_score) AS won,
                        COALESCE(completed_at, commence_time) AS settle_date, sport_id
                    FROM events
                    WHERE status IN ('completed','closed')
                      AND COALESCE(closing_home_probability, opening_home_probability) > 0
                      AND COALESCE(closing_home_probability, opening_home_probability) < 1
                      AND home_score IS NOT NULL AND away_score IS NOT NULL AND home_score != away_score
                    UNION ALL
                    SELECT (home_team_name || ' vs ' || away_team_name) AS market_name,
                        away_team_name AS outcome_name,
                        COALESCE(closing_away_probability, opening_away_probability) AS price,
                        (away_score > home_score) AS won,
                        COALESCE(completed_at, commence_time) AS settle_date, sport_id
                    FROM events
                    WHERE status IN ('completed','closed')
                      AND COALESCE(closing_away_probability, opening_away_probability) > 0
                      AND COALESCE(closing_away_probability, opening_away_probability) < 1
                      AND home_score IS NOT NULL AND away_score IS NOT NULL AND home_score != away_score
                ) o
                JOIN sports s ON s.id = o.sport_id
                WHERE s.key NOT LIKE 'soccer_%'
                  AND LEAST(FLOOR(price * 10)::int, 9) = :bucket
                ORDER BY RANDOM()
                LIMIT :limit
            """)
        elif source == "odds_api_spreads":
            sql = text("""
                SELECT market_name, outcome_name, price, won AS is_winner, settle_date FROM (
                    SELECT (home_team_name || ' vs ' || away_team_name) AS market_name,
                        (home_team_name || ' ' ||
                         CASE WHEN closing_home_spread > 0 THEN '+' ELSE '' END ||
                         closing_home_spread::text) AS outcome_name,
                        (CASE WHEN closing_home_spread_odds < 0
                              THEN ABS(closing_home_spread_odds)::numeric / (ABS(closing_home_spread_odds) + 100.0)
                              ELSE 100.0 / (closing_home_spread_odds + 100.0) END)
                        /
                        ((CASE WHEN closing_home_spread_odds < 0
                               THEN ABS(closing_home_spread_odds)::numeric / (ABS(closing_home_spread_odds) + 100.0)
                               ELSE 100.0 / (closing_home_spread_odds + 100.0) END)
                         +
                         (CASE WHEN closing_away_spread_odds < 0
                               THEN ABS(closing_away_spread_odds)::numeric / (ABS(closing_away_spread_odds) + 100.0)
                               ELSE 100.0 / (closing_away_spread_odds + 100.0) END)) AS price,
                        ((home_score - away_score) + closing_home_spread > 0) AS won,
                        COALESCE(completed_at, commence_time) AS settle_date, sport_id
                    FROM events
                    WHERE status IN ('completed','closed')
                      AND closing_home_spread IS NOT NULL
                      AND closing_home_spread_odds IS NOT NULL AND closing_away_spread_odds IS NOT NULL
                      AND home_score IS NOT NULL AND away_score IS NOT NULL
                      AND (home_score - away_score) + closing_home_spread != 0
                ) o
                JOIN sports s ON s.id = o.sport_id
                WHERE price > 0 AND price < 1
                  AND LEAST(FLOOR(price * 10)::int, 9) = :bucket
                ORDER BY RANDOM()
                LIMIT :limit
            """)
        else:  # odds_api_totals
            sql = text("""
                SELECT market_name, outcome_name, price, won AS is_winner, settle_date FROM (
                    SELECT (home_team_name || ' vs ' || away_team_name) AS market_name,
                        ('Over ' || closing_over_under::text) AS outcome_name,
                        (CASE WHEN closing_over_odds < 0
                              THEN ABS(closing_over_odds)::numeric / (ABS(closing_over_odds) + 100.0)
                              ELSE 100.0 / (closing_over_odds + 100.0) END)
                        /
                        ((CASE WHEN closing_over_odds < 0
                               THEN ABS(closing_over_odds)::numeric / (ABS(closing_over_odds) + 100.0)
                               ELSE 100.0 / (closing_over_odds + 100.0) END)
                         +
                         (CASE WHEN closing_under_odds < 0
                               THEN ABS(closing_under_odds)::numeric / (ABS(closing_under_odds) + 100.0)
                               ELSE 100.0 / (closing_under_odds + 100.0) END)) AS price,
                        ((home_score + away_score) > closing_over_under) AS won,
                        COALESCE(completed_at, commence_time) AS settle_date, sport_id
                    FROM events
                    WHERE status IN ('completed','closed')
                      AND closing_over_under IS NOT NULL
                      AND closing_over_odds IS NOT NULL AND closing_under_odds IS NOT NULL
                      AND home_score IS NOT NULL AND away_score IS NOT NULL
                      AND (home_score + away_score) != closing_over_under
                ) o
                JOIN sports s ON s.id = o.sport_id
                WHERE price > 0 AND price < 1
                  AND LEAST(FLOOR(price * 10)::int, 9) = :bucket
                ORDER BY RANDOM()
                LIMIT :limit
            """)
        rows = (await db.execute(sql, {"bucket": bucket, "limit": limit})).all()
        examples = [
            {
                "market_name": r.market_name or "—",
                "outcome_name": r.outcome_name or "—",
                "price": round(float(r.price), 4),
                "result": "Yes" if r.is_winner else "No",
                "settle_date": _fmt_dt(r.settle_date),
            }
            for r in rows
        ]

    elif source == "odds_api_bookmaker":
        note = (
            "Per-bookmaker closing lines are aggregated from odds snapshots — "
            "individual rows aren't sampled here. See the moneyline (Odds API) "
            "examples for representative games."
        )
    else:
        note = "No examples available for this source."

    if not examples and note is None:
        note = "No examples matched this bucket for the current view."

    from app.tasks.precompute_calibration import CALIBRATION_POPULATION_VERSION

    result = {
        "source": source,
        "bucket_idx": bucket,
        "examples": examples,
        "note": note,
        # Queue #262 Item 2: name the population so future drift is visible. For
        # futures sources the examples are sampled from this exact population.
        "population_version": CALIBRATION_POPULATION_VERSION,
    }
    _examples_cache[cache_key] = (result, now)
    return result


# ---------------------------------------------------------------------------
# Time-horizon calibration for non-event markets
# ---------------------------------------------------------------------------

_th_cache: dict = {"data": None, "timestamp": 0}

# Horizons: (label, days_before_resolution)
_HORIZONS = [
    ("T-30", 30),
    ("T-7", 7),
    ("T-1", 1),
    ("T-0", 0),
]

# Minimum outcomes per horizon to include it in the response
_MIN_OUTCOMES_PER_HORIZON = 50


def _compute_horizon_mce(buckets: list[dict]) -> float | None:
    """Compute MCE from a list of bucket dicts with keys n, winners, sum_prob."""
    if not buckets:
        return None
    total_abs_err = 0.0
    count = 0
    for b in buckets:
        if b["n"] == 0:
            continue
        avg_prob = b["sum_prob"] / b["n"]
        actual = b["winners"] / b["n"]
        total_abs_err += abs(actual - avg_prob)
        count += 1
    if count == 0:
        return None
    return round(total_abs_err / count * 100, 2)


@router.get("/calibration/time-horizon")
async def calibration_time_horizon(
    db: AsyncSession = Depends(get_db),
    bust: int = Query(0, include_in_schema=False),
    source: str | None = Query(None, description="Filter by source (kalshi, polymarket)"),
    category: str | None = Query(None, description="Filter by llm_sport_category"),
):
    """Time-horizon calibration for non-event markets.

    Returns calibration buckets at T-30, T-7, T-1, and T-0 days before
    resolution. Only includes non-event markets (elections, economics, etc.)
    that have resolution_date set and sufficient snapshot history.

    Precomputed by a Celery task every 6 hours; served from Redis cache.
    """
    import json as _json

    # Serve from Redis cache (precomputed by compute_time_horizon_calibration task)
    try:
        from app.tasks.redis_state import get_redis_client
        rc = get_redis_client()
        cached = rc.get("bainluck:calibration:time_horizon")
        if cached:
            return _json.loads(cached)
    except Exception:
        pass

    # Not yet computed — tell caller to check back
    return {
        "status": "computing",
        "message": "Results being computed. Check back in 60 seconds.",
    }
