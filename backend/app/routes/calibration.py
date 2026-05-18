"""Public calibration endpoint — no auth required, cached for 1 hour."""

import math
import random
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func

from app.models import FuturesMarket
from app.services import get_db


def wilson_ci(wins: int, total: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score 95% confidence interval for a binomial proportion."""
    if total == 0:
        return (0.0, 0.0)
    p = wins / total
    denom = 1 + z**2 / total
    center = (p + z**2 / (2 * total)) / denom
    spread = z * math.sqrt((p * (1 - p) + z**2 / (4 * total)) / total) / denom
    return (max(0.0, center - spread), min(1.0, center + spread))


def bootstrap_mce_ci(
    bucket_list: list[dict],
    n_boot: int = 1000,
    seed: int = 42,
) -> tuple[float, float]:
    """Bootstrap 95% CI on MCE by resampling buckets.

    Each bucket dict must have keys: ``avg_prob``, ``winners``, ``n``.
    """
    if not bucket_list:
        return (0.0, 0.0)
    rng = random.Random(seed)
    k = len(bucket_list)
    mce_samples: list[float] = []
    for _ in range(n_boot):
        sample = rng.choices(bucket_list, k=k)
        total_abs_err = 0.0
        for b in sample:
            actual = b["winners"] / b["n"] if b["n"] else 0.0
            total_abs_err += abs(actual - b["avg_prob"])
        mce_samples.append(total_abs_err / k)
    mce_samples.sort()
    lo = mce_samples[int(n_boot * 0.025)]
    hi = mce_samples[int(n_boot * 0.975)]
    return (lo, hi)

router = APIRouter()

_cache: dict = {"data": None, "timestamp": 0}
CACHE_TTL = 3600


@router.get("/calibration/outcome-timeline")
async def calibration_outcome_timeline(
    db: AsyncSession = Depends(get_db),
    secret: str = Query(""),
    market_ext_id: str = Query(...),
    source: str = Query("kalshi"),
):
    """Show snapshot timeline for all outcomes in a market."""
    import os

    if secret != os.environ.get("ADMIN_TOKEN", ""):
        return {"error": "invalid secret"}

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
    db: AsyncSession = Depends(get_db),
    secret: str = Query(""),
    category: str = Query("golf"),
    source: str = Query("kalshi"),
    bucket: int = Query(1),
):
    """Show specific outcomes in a calibration bucket for debugging."""
    import os

    if secret != os.environ.get("ADMIN_TOKEN", ""):
        return {"error": "invalid secret"}

    result = await db.execute(text("""
        SELECT fo.name AS outcome_name, fm.name AS market_name,
            fo.opening_probability, fo.calibration_probability,
            fo.current_probability,
            fm.external_id AS market_ext_id,
            fm.group_id, fm.commence_time,
            (SELECT COUNT(*) FROM futures_odds_snapshots fos WHERE fos.outcome_id = fo.id) AS snap_count,
            COALESCE(fo.calibration_probability, fo.opening_probability) AS used_prob
        FROM futures_outcomes fo
        JOIN futures_markets fm ON fm.id = fo.market_id
        WHERE fm.source = :source
          AND fm.status = 'resolved'
          AND COALESCE(fm.llm_sport_category, 'uncategorized') = :category
          AND fo.opening_probability IS NOT NULL
          AND fo.opening_probability > 0 AND fo.opening_probability < 1
          AND fo.current_probability IS NOT NULL
          AND (fo.current_probability >= 0.95 OR fo.current_probability <= 0.05)
          AND LEAST(FLOOR(COALESCE(fo.calibration_probability, fo.opening_probability) * 10)::int, 9) = :bucket
        ORDER BY RANDOM()
        LIMIT 25
    """), {"source": source, "category": category, "bucket": bucket})

    return [
        {"outcome": r.outcome_name, "market": r.market_name[:80],
         "opening": float(r.opening_probability),
         "calibration": float(r.calibration_probability) if r.calibration_probability else None,
         "used_prob": float(r.used_prob),
         "resolved": "winner" if r.current_probability >= 0.95 else "loser",
         "market_ext_id": r.market_ext_id, "group_id": r.group_id,
         "snap_count": r.snap_count,
         "commence_time": str(r.commence_time) if r.commence_time else None}
        for r in result
    ]


@router.get("/calibration/snapshot-health")
async def calibration_snapshot_health(
    db: AsyncSession = Depends(get_db),
    secret: str = Query(""),
):
    """How many calibration-eligible outcomes have 0 snapshots?"""
    import os

    if secret != os.environ.get("ADMIN_TOKEN", ""):
        return {"error": "invalid secret"}

    result = await db.execute(text("""
        SELECT fm.source,
            COALESCE(fm.llm_sport_category, 'uncategorized') AS cat,
            COUNT(*) AS total,
            COUNT(CASE WHEN NOT EXISTS (
                SELECT 1 FROM futures_odds_snapshots fos WHERE fos.outcome_id = fo.id
            ) THEN 1 END) AS zero_snap,
            COUNT(CASE WHEN fo.calibration_probability IS NOT NULL
                AND fo.calibration_probability = fo.opening_probability THEN 1 END) AS price_stuck
        FROM futures_outcomes fo
        JOIN futures_markets fm ON fm.id = fo.market_id
        WHERE fm.status = 'resolved'
          AND fo.opening_probability IS NOT NULL
          AND fo.opening_probability > 0 AND fo.opening_probability < 1
          AND fo.current_probability IS NOT NULL
          AND (fo.current_probability >= 0.95 OR fo.current_probability <= 0.05)
        GROUP BY fm.source, cat
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
        "total_outcomes": total_all,
        "zero_snapshots": total_zero,
        "pct_zero": round(total_zero * 100.0 / max(total_all, 1), 1),
        "price_stuck": total_stuck,
        "pct_stuck": round(total_stuck * 100.0 / max(total_all, 1), 1),
        "by_source_category": out,
    }


@router.get("/calibration/unchanged-samples")
async def calibration_unchanged_samples(
    db: AsyncSession = Depends(get_db),
    secret: str = Query(""),
):
    """Show specific outcomes where calibration_probability = opening_probability."""
    import os

    if secret != os.environ.get("ADMIN_TOKEN", ""):
        return {"error": "invalid secret"}

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
    db: AsyncSession = Depends(get_db),
    secret: str = Query(""),
    category: str = Query("soccer"),
):
    """Sample resolved Polymarket markets with $0 volume to check if it's real."""
    import os

    if secret != os.environ.get("ADMIN_TOKEN", ""):
        return {"error": "invalid secret"}

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
    db: AsyncSession = Depends(get_db),
    secret: str = Query(""),
):
    """Volume distribution of outcomes in calibration, by source+category."""
    import os

    if secret != os.environ.get("ADMIN_TOKEN", ""):
        return {"error": "invalid secret"}

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
    db: AsyncSession = Depends(get_db),
    secret: str = Query(""),
):
    """Lightweight: how many outcomes still use opening prices, by source+category."""
    import os

    if secret != os.environ.get("ADMIN_TOKEN", ""):
        return {"error": "invalid secret"}

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
    db: AsyncSession = Depends(get_db),
    secret: str = Query(""),
):
    """Diagnostic data for calibration debugging — admin only."""
    import os

    if secret != os.environ.get("ADMIN_TOKEN", ""):
        return {"error": "invalid secret"}

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
    db: AsyncSession = Depends(get_db),
    secret: str = Query(""),
):
    """Per-sport filter funnel for odds_api calibration events — admin only."""
    import os

    if secret != os.environ.get("ADMIN_TOKEN", ""):
        return {"error": "invalid secret"}

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
    db: AsyncSession = Depends(get_db),
    secret: str = Query(""),
    limit: int = Query(50000),
):
    """Run Part C rescue directly — admin only."""
    import os

    if secret != os.environ.get("ADMIN_TOKEN", ""):
        return {"error": "invalid secret"}

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
    """Public calibration data for the /calibration page. Cached for 1 hour."""

    now = time.time()
    if not bust and _cache["data"] and (now - _cache["timestamp"]) < CACHE_TTL:
        return _cache["data"]

    # Same query as admin calibration-data endpoint
    sql = text("""
        WITH market_info AS (
            SELECT fm.id AS market_id, fm.source, fm.event_id, fm.group_id,
                fm.commence_time,
                COALESCE(fm.llm_sport_category, 'uncategorized') AS category,
                fm.mutually_exclusive
            FROM futures_markets fm
            WHERE fm.status = 'resolved'
        ),
        -- Tier 1: explicit group_id
        group_sizes AS (
            SELECT group_id, source, COUNT(*) AS group_size
            FROM market_info
            WHERE group_id IS NOT NULL
            GROUP BY group_id, source
        ),
        -- Tier 2: shared event_id
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
        ranked_outcomes AS (
            SELECT
                COALESCE(fo.calibration_probability, fo.opening_probability) AS adj_opening_probability,
                (fo.is_winner = true OR fo.current_probability >= 0.95) AS is_winner,
                (fo.calibration_probability IS NOT NULL
                 AND fo.calibration_probability IS DISTINCT FROM fo.opening_probability) AS price_moved,
                cv.vm_id, cv.source, cv.category,
                cv.eligible, cv.is_grouped,
                (cv.is_grouped OR cv.eligible >= 3) AS is_multi,
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
        ),
        -- Detect default/placeholder pricing: if 50%+ of outcomes in a
        -- multi-outcome market share the exact same opening_probability,
        -- those outcomes had no real price discovery. Exclude them.
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
                    -- Multi-outcome: exclude default-priced + extreme tails
                    WHEN ro.is_multi
                        THEN ro.adj_opening_probability > 0.005
                         AND ro.adj_opening_probability < 0.98
                         AND mp.vm_id IS NULL
                    -- Binary/threshold: one outcome per virtual market
                    ELSE ro.rn = 1
                END
        ),
        bucketed AS (
            SELECT *, LEAST(FLOOR(adj_opening_probability * 10)::int, 9) AS bucket_idx
            FROM deduped
        )
        SELECT bucket_idx, source, category, price_moved,
            COUNT(*) AS n,
            SUM(CASE WHEN is_winner THEN 1 ELSE 0 END) AS winners,
            AVG(adj_opening_probability) AS avg_prob,
            SUM(adj_opening_probability::float) AS sum_prob,
            SUM((adj_opening_probability::float - CASE WHEN is_winner THEN 1.0 ELSE 0.0 END)^2) AS sum_sq_err
        FROM bucketed
        GROUP BY bucket_idx, source, category, price_moved
        ORDER BY bucket_idx, source, category, price_moved
    """)

    result = await db.execute(sql)
    rows = result.all()

    # Ground-truth sports calibration from events table.
    # Uses closing line (pre-computed by backfill task) when available,
    # falling back to opening probability.
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
            SELECT COALESCE(closing_home_probability, opening_home_probability) AS prob,
                   (home_score > away_score) AS won, sport_id
            FROM events
            WHERE status IN ('completed', 'closed')
              AND COALESCE(closing_home_probability, opening_home_probability) IS NOT NULL
              AND COALESCE(closing_home_probability, opening_home_probability) > 0
              AND COALESCE(closing_home_probability, opening_home_probability) < 1
              AND home_score IS NOT NULL AND away_score IS NOT NULL
              AND home_score != away_score
            UNION ALL
            SELECT COALESCE(closing_away_probability, opening_away_probability) AS prob,
                   (away_score > home_score) AS won, sport_id
            FROM events
            WHERE status IN ('completed', 'closed')
              AND COALESCE(closing_away_probability, opening_away_probability) IS NOT NULL
              AND COALESCE(closing_away_probability, opening_away_probability) > 0
              AND COALESCE(closing_away_probability, opening_away_probability) < 1
              AND home_score IS NOT NULL AND away_score IS NOT NULL
              AND home_score != away_score
        ) outcomes
        JOIN sports s ON s.id = outcomes.sport_id
        GROUP BY bucket_idx, s.key
        ORDER BY bucket_idx, s.key
    """)
    events_result = await db.execute(events_sql)
    events_rows = events_result.all()

    all_rows = list(rows) + list(events_rows)
    total_outcomes = sum(r.n for r in all_rows)
    total_winners = sum(r.winners for r in all_rows)

    total_markets_result = await db.execute(
        select(func.count()).select_from(FuturesMarket).where(FuturesMarket.status == "resolved")
    )
    total_markets = total_markets_result.scalar()

    # Closing line coverage
    closing_sql = text("""
        SELECT
            COUNT(*) FILTER (WHERE closing_home_probability IS NOT NULL) AS has_closing,
            COUNT(*) FILTER (WHERE closing_home_probability IS NULL
                             AND commence_time IS NOT NULL) AS needs_closing,
            COUNT(*) AS total_completed
        FROM events
        WHERE status IN ('completed', 'closed')
          AND home_score IS NOT NULL AND away_score IS NOT NULL
    """)
    closing_result = await db.execute(closing_sql)
    closing_row = closing_result.one()

    # Build bucket dicts with Wilson CIs
    bucket_dicts = []
    for r in all_rows:
        ci_lo, ci_hi = wilson_ci(r.winners, r.n)
        bucket_dicts.append({
            "bucket_idx": r.bucket_idx, "source": r.source, "category": r.category,
            "price_moved": getattr(r, "price_moved", None),
            "n": r.n, "winners": r.winners,
            "avg_prob": round(float(r.avg_prob), 4),
            "sum_prob": round(float(r.sum_prob), 4),
            "sum_sq_err": round(float(r.sum_sq_err), 4),
            "ci_lower": round(ci_lo, 4),
            "ci_upper": round(ci_hi, 4),
        })

    # Aggregate buckets for MCE bootstrap CI
    agg: dict[int, dict] = {}
    for b in bucket_dicts:
        idx = b["bucket_idx"]
        if idx not in agg:
            agg[idx] = {"n": 0, "winners": 0, "sum_prob": 0.0}
        agg[idx]["n"] += b["n"]
        agg[idx]["winners"] += b["winners"]
        agg[idx]["sum_prob"] += b["sum_prob"]
    agg_list = [
        {"n": v["n"], "winners": v["winners"], "avg_prob": v["sum_prob"] / v["n"]}
        for v in agg.values()
        if v["n"] > 0
    ]
    mce_ci_lo, mce_ci_hi = bootstrap_mce_ci(agg_list)

    # Compute cohort-level MCE: closing line (price_moved=True) vs opening price (price_moved=False)
    def _cohort_mce(buckets: list[dict], pred: object) -> float | None:
        """Compute MCE for a subset of bucket_dicts matching *pred*."""
        cohort_agg: dict[int, dict] = {}
        for b in buckets:
            if b.get("price_moved") != pred:
                continue
            idx = b["bucket_idx"]
            if idx not in cohort_agg:
                cohort_agg[idx] = {"n": 0, "winners": 0, "sum_prob": 0.0}
            cohort_agg[idx]["n"] += b["n"]
            cohort_agg[idx]["winners"] += b["winners"]
            cohort_agg[idx]["sum_prob"] += b["sum_prob"]
        if not cohort_agg:
            return None
        total_abs_err = 0.0
        for v in cohort_agg.values():
            if v["n"] == 0:
                continue
            avg_prob = v["sum_prob"] / v["n"]
            actual = v["winners"] / v["n"]
            total_abs_err += abs(actual - avg_prob)
        return round(total_abs_err / len(cohort_agg) * 100, 2)

    mce_closing_line = _cohort_mce(bucket_dicts, True)
    mce_opening_price = _cohort_mce(bucket_dicts, False)

    response = {
        "closing_line_coverage": {
            "has_closing": closing_row.has_closing,
            "needs_closing": closing_row.needs_closing,
            "total": closing_row.total_completed,
        },
        "buckets": bucket_dicts,
        "total_markets": total_markets,
        "total_outcomes": total_outcomes,
        "total_winners": total_winners,
        "mce_ci_lower": round(mce_ci_lo * 100, 2),
        "mce_ci_upper": round(mce_ci_hi * 100, 2),
        "mce_closing_line": mce_closing_line,
        "mce_opening_price": mce_opening_price,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    _cache["data"] = response
    _cache["timestamp"] = now

    return response
