"""Public calibration endpoint — no auth required, cached for 1 hour."""

import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.routes.admin_utils import _check_admin_secret
from app.services import get_db, get_db_rw
from app.utils import calibration_scoring as _scoring
from app.utils.calibration_provability import (
    CELL_POPULATION,
    MIN_GRADED_SHARE,
    UNIT_OUTCOMES,
    GradedShareCensus,
    annotate_cells,
)

# Queue #257 Item 1: the in-request calibration fallback used to re-implement the
# whole CTE chain + wilson_ci / bootstrap_mce_ci / _compute_horizon_mce here (a
# drifting second copy). It now delegates to the ONE shared
# app.tasks.precompute_calibration.compute_calibration_payload, so those local
# stats helpers (and their math/random/select/func imports) are gone.

logger = logging.getLogger(__name__)

router = APIRouter()

_cache: dict = {"data": None, "timestamp": 0}
CACHE_TTL = 3600

#: #2007 / CAL-P076. The staged bank's as-of + drift, memoised per dyno. The two
#: durable rows behind it are primary-key reads of bounded payloads, but tier 1
#: of ``/api/calibration`` answers from process memory with NO database work at
#: all, and the disclosure must appear on that answer too — so it is cached
#: rather than paid per request. 120 s against an artifact that moves hourly is a
#: lag nothing can observe; it is not a freshness claim, and the block carries its
#: own ``staged_at`` so a stale read cannot make the disclosure look current.
_staged_cache: dict = {"data": None, "timestamp": 0.0}
STAGED_DISCLOSURE_TTL_S = 120.0


def _score_payload(payload: dict) -> dict:
    """Score the payload being served, or say plainly that it could not be.

    CAL-P998 / D46. The scoring itself lives in
    :mod:`app.utils.calibration_scoring`, which imports nothing from the app and
    is the ONE definition of the bars — ``backend/scripts/calibration_scorecard.py``
    imports the same constants rather than restating them, so the served field
    and the script can no longer disagree about what "at bar" means.

    The try/except is not defensive decoration. This runs on the ONE exit every
    ``/api/calibration`` answer passes through, including the dated fallback
    tiers whose whole purpose is that the page does not go dark (ruling CAL-P017).
    A malformed ``buckets`` array in some six-day-old last-good copy must cost
    the reader a scorecard, never the curve — so a failure degrades to an
    explicit ``unavailable`` block with its reason, which is louder than an
    absent key and can never be read as zero (gotcha #53).
    """
    try:
        return _scoring.scorecard(payload)
    except Exception as exc:  # noqa: BLE001 — a score must never take the page down
        logger.warning("calibration: scorecard could not be computed: %r", exc)
        return _scoring.unavailable(f"score_failed: {type(exc).__name__}")


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


async def _read_staged_disclosure(db: AsyncSession, *, now: float) -> dict:
    """#2007 — the ``staged`` block, read once per dyno per TTL.

    Two primary-key reads of ``durable_state_snapshots``: the staged futures
    cursor (for ``staged_at`` — the instant the futures bank last advanced) and
    the phase ledger (for the drift gauges). Both are bounded by
    ``read_snapshot``'s own ``statement_timeout``.

    **Every failure path returns a disclosure, never an exception and never an
    absence.** :func:`availability_floor` refuses ``fresh`` on an unmeasured
    block, so a read that breaks costs the page a word, not a number — which is
    the correct direction and the whole point of ruling (b).

    ``max_age_s`` is deliberately enormous. This is not a servability check: an
    ANCIENT bank is exactly the fact being disclosed, and refusing to read it
    past an age bound would hide the only case that matters.
    """
    from app.utils.calibration_staged_disclosure import build_disclosure, unmeasured

    cached = _staged_cache.get("data")
    if isinstance(cached, dict) and (now - _staged_cache["timestamp"]) < STAGED_DISCLOSURE_TTL_S:
        return cached

    try:
        from app.services.durable_snapshots import read_snapshot
        from app.tasks.calibration_main_build import (
            LEDGER_IDENTITY,
            STAGED_FUTURES_IDENTITY,
        )
        from app.utils.calibration_phase_ledger import PHASE_LEDGER_SCHEMA
        from app.utils.calibration_staged_futures import STAGED_FUTURES_SCHEMA

        _forever = 3650 * 86400
        bank = await read_snapshot(
            db,
            STAGED_FUTURES_IDENTITY,
            expected_version=STAGED_FUTURES_SCHEMA,
            max_age_s=_forever,
        )
        ledger = await read_snapshot(
            db, LEDGER_IDENTITY, expected_version=PHASE_LEDGER_SCHEMA, max_age_s=_forever
        )
        # ``ok``, not ``envelope is not None``. A ``wrong_version`` read still
        # carries an envelope (tier 3 below relies on exactly that), and taking
        # its ``generated_at`` would date this bank from some other artifact's
        # row. Version, checksum and completeness must all hold or the honest
        # answer is that the bank could not be read.
        if not bank.ok or bank.envelope is None:
            disclosure = unmeasured(f"staged_cursor_unreadable: {bank.status}")
        elif not ledger.ok or ledger.envelope is None or not isinstance(
            ledger.envelope.payload, dict
        ):
            disclosure = unmeasured(f"phase_ledger_unreadable: {ledger.status}")
        else:
            disclosure = build_disclosure(
                ledger_stages=ledger.envelope.payload.get("stages"),
                staged_generated_at=bank.envelope.generated_at,
            )
    except Exception as exc:  # noqa: BLE001 — reported, never swallowed (Q297)
        logger.warning("calibration: staged disclosure read failed", exc_info=True)
        disclosure = unmeasured(f"read_raised: {type(exc).__name__}")

    _staged_cache["data"] = disclosure
    _staged_cache["timestamp"] = now
    return disclosure


@router.get("/calibration")
async def public_calibration(
    db: AsyncSession = Depends(get_db),
):
    """Public calibration data for the /calibration page.

    Served from Redis (precomputed by precompute_calibration_main task every 1h).
    Falls back to in-process cache, the durable snapshot, and then a truthful
    dated last-good. There is no fifth tier: this handler NEVER builds.

    Queue 271 (#1459/#1197) hardening:
    * The Redis read is a *shared async* client + a hard-bounded op — no more
      SYNCHRONOUS ``get_redis_client().get()`` on the async event loop (gotcha
      #39), which blocked the loop for the whole read.
    * On a Redis *failure* (stall/error) a usable in-process/last-good payload is
      served instead of recomputing during flakiness.

    Queue 300B Item 0 — the request path is no longer a build authority:
    * ``compute_calibration_payload`` is the ~22-minute canonical futures CTE.
      A deadline around it bounded how long ONE request waited; it did not bound
      what the request STARTED. The abandoned backend kept running past the
      client, holding its xmin — which is the orphan/bloat shape #1479 records.
      An anonymous GET must never be able to launch that.
    * ``?bust=1`` is gone with it. It was an unauthenticated recompute trigger
      hiding behind ``include_in_schema=False``, and hidden is not authenticated.
      The recompute rail that survives is the admin-authenticated one
      (``/api/admin/calibration/mce?bust=true``), which QUEUES the heavy task and
      returns — it never runs the query inline.
    * So this endpoint has exactly three honest answers: fresh, dated-degraded,
      or the typed 503 + Retry-After. Concurrent requests start zero builds
      because there is no build to start.
    """
    import json as _json

    from app.utils import request_cache as _rc
    from app.utils.availability_envelope import (
        AVAILABILITY_DEGRADED,
        AVAILABILITY_EMPTY,
        AVAILABILITY_FIELD,
        AVAILABILITY_FRESH,
        AVAILABILITY_STALE,
        declare as _declare,
        never_stronger as _never_stronger,
    )
    from app.utils.calibration_coverage_bridge import ensure_census as _ensure_census
    from app.utils.calibration_publish_gate import (
        SERVE_MAX_AGE_S,
        payload_age_s,
        producer_stall,
        snapshot_verdict,
    )
    from app.utils.calibration_staged_disclosure import (
        STAGED_FIELD,
        availability_floor as _staged_floor,
        unmeasured as _staged_unmeasured,
    )

    _lg_key = "calibration:main"

    # #2007. Populated below, before any tier can answer. Until then it is an
    # explicit "not read", never an empty dict — an absent disclosure and a
    # healthy one must not look alike, and this value can reach ``_serve`` if a
    # tier is ever inserted above the read.
    staged_block: dict = _staged_unmeasured("not_read")

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

    def _compatible_versions() -> tuple[str, ...]:
        """The operator's explicit rollover declaration, or nothing.

        CAL-P070 / #1955. A version bump used to take this page DARK for the
        length of one build: the dyno boots expecting the new version, every
        cached artifact still carries the old one, all four tiers refuse in the
        same instant and the answer is a 503 (tried 2026-08-02, reverted the same
        hour). The ratified rollover contract has always said what should happen
        instead — ``deploy-before-candidate`` serves the predecessor as
        ``previous_degraded``: dated, provenanced, read-only — and no code
        implemented it, so the contract passed 26/26 while production went dark.
        This is the wire.

        Empty is the safe default and the honest one: an unreadable declaration
        is not a declaration, so the page refuses exactly as it does today.
        """
        try:
            from app.tasks.precompute_calibration import (
                COMPATIBLE_PREVIOUS_POPULATION_VERSIONS,
            )

            return tuple(COMPATIBLE_PREVIOUS_POPULATION_VERSIONS)
        except Exception:  # noqa: BLE001 — no declaration => no compatibility
            return ()

    def _serve(payload: dict, availability: str) -> dict:
        """The ONE exit for every payload this endpoint returns (#1680).

        Three things happen here and nowhere else, so no tier can forget any:

        1. **The producer declares itself.** ``producer`` carries the artifact's
           age, the beat cadence, how many publishes were missed and the named
           threshold — on every answer, not only the dated ones. A ``fresh``
           response that quietly means "under seven days" is exactly how a
           four-day publishing outage kept reading as healthy.
        2. **A stalled producer weakens the declaration.** ``fresh`` is bounded
           by ``SERVE_MAX_AGE_S`` (7d) because that is when the durable copy
           expires — a sensible bound for *serving*, and a nonsense one for a
           task that runs hourly. Past :data:`PRODUCER_STALL_AGE_S` the honest
           word is ``stale``, and ``never_stronger`` guarantees this can only
           ever move the claim down: a ``degraded`` payload stays ``degraded``.

        Not a 503. Ruling CAL-P017 (Alex, 2026-08-08) is standing and load-
        bearing here: every tier was once bounded by the same constant, they all
        refused in the same instant, and /calibration went dark. Stale-with-
        declaration beats dark. This adds a word, never a refusal — and the
        1-4 min post-release 503 (``_unavailable``) is a different path
        entirely, untouched.
        """
        out = dict(payload)
        stall = producer_stall(out)
        out["producer"] = stall
        if stall["stalled"]:
            availability = _never_stronger(availability, AVAILABILITY_STALE)
        # 3. **The ARTIFACT dates its own inputs** (#2007, CAL-P076). ``producer``
        #    above answers "is the publisher running"; it cannot answer "are the
        #    numbers it published re-read". Measured 2026-08-19: a curve whose
        #    futures bank had not advanced in six hours served ``fresh`` /
        #    ``beats_missed: 0`` / ``stalled: false`` on a two-minute-old
        #    ``generated_at``, because the staged bank is complete-forever and
        #    every beat re-serialises it. Publishing is not freshness. The
        #    ``staged`` block carries ``staged_at`` and ``units_drifted``, and a
        #    bank frozen over drift — or a disclosure that could not be read at
        #    all — cannot be called ``fresh``. Downgrade only: ``never_stronger``.
        out[STAGED_FIELD] = staged_block
        floor = _staged_floor(staged_block)
        if floor is not None:
            availability = _never_stronger(availability, floor)
        # 4. **The curve scores itself** (CAL-P998, D46 = A). ``cells at bar`` is
        #    the number this program is steered by, and until now it existed only
        #    while `backend/scripts/calibration_scorecard.py` was running — so the
        #    measurement bus read a different cut off `by_category` and the two
        #    figures looked like a contradiction. Both cuts are now computed here,
        #    from THIS payload, with the bars that produced them.
        #
        #    Computed at the exit rather than baked in by the producer for the
        #    same reason `producer` is: a score carried inside the artifact
        #    survives into the dated fallback tiers still describing whichever
        #    curve was current when it was baked. Derived from `out` means a
        #    stale copy is scored as the stale copy it is. Cost is ~2 ms against
        #    a ~470 KB serialisation (measured on the q269 payload, 2,134
        #    buckets); it declares no availability, because a score is a
        #    statement about the numbers, not about whether they arrived.
        out[_scoring.SCORECARD_FIELD] = _score_payload(out)
        return _declare(out, _never_stronger(out.get(AVAILABILITY_FIELD), availability))

    def _degraded(
        payload: dict, reason: str, verdict=None, availability: str = AVAILABILITY_STALE
    ) -> dict:
        """A last-good copy, marked stale and dated so the page can say how old it is.

        Never presented as current: ``status`` is always ``stale`` and the age is
        explicit, so the banner can render "as of <time>" rather than implying the
        numbers are live.

        Ruling 025: every construction of this shape IS the act of serving a
        dated substitute, so it carries the ``availability`` declaration too. The
        default is ``stale`` because what these tiers serve is a WHOLE copy of
        the pool that is merely old; a caller serving something incomplete or
        unvalidated passes ``degraded`` explicitly. This is computed at the
        construction site of the response — it is NOT a map from ``cache.status``
        (clause 2 forbids exactly that), which is why the value is an argument
        the serving tier chooses rather than something read back off ``cache``.

        Q330 / B1 defect 1 — **a re-wrap may weaken a declaration, never heal
        one.** Some payloads reaching here have already been classified by the
        tier that admitted them: the process-local fallback below re-wraps
        whatever the main tier memoized, which may be a shape-unvalidated copy
        stamped ``degraded``. This function's own default is ``stale``, computed
        from the only thing IT knows (the copy is old) — so without the clamp an
        incomplete payload came out the far side promising a whole one. The
        content is identical either way; only the claim about it improved, which
        is the direction that turns a disclosure into a lie.
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
            # A predecessor artifact must SAY it is one. Serving q267 numbers
            # while the build is labelled q268 and declaring only "stale" would
            # be a true statement standing in for the load-bearing one.
            if getattr(verdict, "is_previous_version", False):
                cache["population_version"] = verdict.population_version
                cache["expected_population_version"] = _expected_version()
                cache["version_relation"] = "previous"
        elif isinstance(payload.get("generated_at"), str):
            cache["generated_at"] = payload["generated_at"]
        out["cache"] = cache
        return _serve(out, availability)

    def _previous_version(payload: dict, verdict, reason: str) -> dict:
        """Serve a DECLARED-compatible predecessor: dated, degraded, read-only.

        ``read_only`` is the contract's word and it is the reason this is a
        function rather than three call sites. Every other dated tier ends with
        ``remember_last_good`` + a process-cache seed, which is right for a copy
        of the CURRENT population and wrong here: promoting a predecessor into
        the current version's caches is ``may_seed_current``, which the rollover
        contract forbids in every case that serves one. So this path persists
        NOTHING. The cost is one Redis GET per request while the first build
        under the new version runs; the alternative is the previous version
        outliving its own rollover window because we kept re-saving it.
        """
        logger.warning(
            "calibration: serving DECLARED-compatible predecessor %r (expected %r, "
            "reason=%s) — dated, degraded and read-only until the first build "
            "under the current version publishes",
            verdict.population_version, _expected_version(), reason,
        )
        return _degraded(payload, reason, verdict, availability=AVAILABILITY_DEGRADED)

    def _unavailable(reason: str) -> JSONResponse:
        """The typed unavailable response — honest, actionable, never opaque.

        Still a 503 (the semantics are right and Retry-After is meaningful), but
        the body is structured so the page renders a dated "temporarily
        unavailable, retry" state instead of a bare "Failed to load".

        Q330 / B1 defect 2 — **why this RETURNS a response instead of raising.**
        Ruling 025's promise is that a client reads ONE field across all five
        outcomes. Raising ``HTTPException(detail={...})`` cannot keep it: FastAPI
        serializes the detail nested, so the four served answers put
        ``availability`` at the top level of the body and the refusal put it at
        ``detail.availability``. A real HTTP client therefore had to special-case
        exactly the path that is hardest to reach and hardest to test — and a
        primitive with one exception is not a primitive. Composing the response
        here is what makes the wire path uniform; the default exception handler's
        envelope is not ours to reshape.

        ``detail`` is kept as a MIRROR of the same body, and that is deliberate
        rather than lazy: the shipped web page reads ``error.detail.status`` /
        ``.reason`` / ``.message`` to render its "temporarily unavailable" state
        (``frontend/app/calibration/page.tsx``), so dropping the key would take
        down the exact user-facing surface #1680 is about, on a queue whose whole
        point is that the page must not go dark. New readers use the top level;
        the mirror is compatibility, not a second contract.
        """
        body = {
            "status": "unavailable",
            # Ruling 025: nothing was served, and the refusal says so in the
            # same vocabulary as every other answer this endpoint gives, so a
            # client has one field to read across all five outcomes instead
            # of a special case for the failure.
            "availability": AVAILABILITY_EMPTY,
            "reason": reason,
            "retry_after_s": 30,
            "message": (
                "Calibration data is temporarily unavailable. It is rebuilt "
                "hourly — please retry shortly."
            ),
        }
        return JSONResponse(
            status_code=503,
            content={**body, "detail": dict(body)},
            headers={"Retry-After": "30"},
        )

    now = time.time()

    # 0. #2007 — read the staged bank's as-of BEFORE any tier answers, because
    #    every tier ends in ``_serve`` and every answer must carry it. Memoised
    #    for STAGED_DISCLOSURE_TTL_S so tier 1 (process memory, no database work)
    #    keeps that property. Cannot raise; a failed read becomes an unmeasured
    #    disclosure, which refuses ``fresh``.
    staged_block = await _read_staged_disclosure(db, now=now)

    # 1. In-process cache (survives between requests on same dyno). A
    #    stale-marked copy (Tier 2b, main key absent) is deliberately NOT served
    #    from here: it stays honestly marked on every response, but each request
    #    re-attempts Redis main so a later fresh-main read replaces it promptly
    #    (Queue #284 Item 3). TTL and compute behavior are unchanged.
    if (
        isinstance(_cache["data"], dict)
        and (now - _cache["timestamp"]) < CACHE_TTL
        and _cache["data"].get("cache", {}).get("status") != "stale"
    ):
        # Ruling 025: this tier re-derives the declaration from the CONTENT it is
        # about to serve rather than replaying whatever the producing tier
        # stamped an hour ago. The memo can only hold an unmarked copy admitted
        # by the main tier, but it can hold it for up to CACHE_TTL, and "it was
        # fresh when I stored it" is a claim about the past. Age only — no shape
        # re-check, for the reason recorded at the main tier below.
        memo_age = payload_age_s(_cache["data"])
        if _cache["data"].get("availability") == AVAILABILITY_DEGRADED:
            # A memo cannot HEAL. The copy stored here was already declared
            # unvalidated by the tier that admitted it, and re-deriving purely
            # from age would silently upgrade it to "fresh" — an incomplete
            # payload with a recent timestamp is recent and still incomplete.
            # Only a new read of the primary pool can clear this.
            memo_state = AVAILABILITY_DEGRADED
        elif memo_age is None:
            # Unknown age is not zero (gotcha #53's shape): content this process
            # cannot date is not content it can call fresh.
            memo_state = AVAILABILITY_DEGRADED
        else:
            memo_state = (
                AVAILABILITY_FRESH if memo_age <= SERVE_MAX_AGE_S else AVAILABILITY_STALE
            )
        return _serve(_cache["data"], memo_state)

    # 2. Redis precomputed cache (survives deploys) — shared async client + a
    #    hard-bounded op so a Redis stall can never block the loop or the router.
    _redis_failed = False
    try:
        rc = await _rc.get_shared_async_redis()
        res = await _rc.bounded_redis_call(lambda: rc.get("bainluck:calibration:main"))
        if res.is_ok:
            # Queue 300B: a MALFORMED value is a miss, not a Redis failure.
            # Previously this decode ran bare inside the tier's outer try, so a
            # truncated/corrupt ``main`` (an eviction mid-write, a partial read)
            # set ``_redis_failed`` and skipped tier 2b — meaning one poisoned
            # key took the perfectly healthy ``last_good`` sibling down with it.
            # Nothing surfaced it before, because the request then fell through
            # to the cold compute and served a curve anyway.
            try:
                data = _json.loads(res.value)
            except Exception:
                logger.warning(
                    "calibration: main key is not decodable JSON — treating as a "
                    "miss so the last-good tier still runs",
                )
                data = None
        else:
            data = None

        if isinstance(data, dict):
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
                data,
                expected_version=_expected_version(),
                max_age_s=SERVE_MAX_AGE_S,
                compatible_versions=_compatible_versions(),
            )
            if main_verdict.is_previous_version:
                return _previous_version(
                    data, main_verdict, "population_version_superseded"
                )
            if main_verdict.status != "wrong_version":
                # Queue 324 / ruling 025 — THE HOLE THIS CLOSES. The condition
                # above accepts three verdicts, not one: ``ok``, ``too_old`` and
                # ``malformed``. Only ``ok`` is the primary pool answering; the
                # other two were served here **unmarked** — no ``cache`` block,
                # no provenance, indistinguishable from a current curve — and the
                # inline justification for that was *"its 2h TTL bounds its
                # age"*, an assumption the consumer held about the producer. The
                # producer stopping is precisely the failure mode in play
                # (#1680), so the assumption fails exactly when it matters.
                #
                # What does NOT change: none of these are rejected. Refusing on
                # shape at this tier is what Queue 300B deliberately ruled out —
                # a payload-shape addition would blank the page for a reason that
                # is not a data problem. Declaring is not refusing.
                if main_verdict.status == "too_old":
                    # A WHOLE copy of the pool, past the age bound. Stale is the
                    # honest word and the dated banner is the right rendering, so
                    # it goes through the same construction as every other dated
                    # tier rather than getting a bespoke one.
                    degraded = _degraded(data, "main_key_over_age", main_verdict)
                    _cache["data"] = degraded
                    _cache["timestamp"] = now
                    _rc.remember_last_good(_lg_key, degraded)
                    return degraded
                # Queue 300C: same guard as the stale tiers. A ``main`` key
                # written by the last pre-census build is fresh and correct for
                # the curve, but carries no census — say so explicitly.
                data = _ensure_census(data, reason="payload_predates_census")
                if main_verdict.status != "ok":
                    # Shape-unvalidated (``malformed``): possibly partial, and
                    # this build cannot vouch for it. Not old, so ``cache`` stays
                    # untouched — calling a fresh payload "stale" would be a
                    # second false statement, not a correction — but the envelope
                    # says plainly that what you are looking at is not a copy we
                    # could validate.
                    logger.warning(
                        "calibration: main key served UNVALIDATED and declared "
                        "degraded (%s: %s)",
                        main_verdict.status, main_verdict.reason,
                    )
                    data = _serve(data, AVAILABILITY_DEGRADED)
                else:
                    data = _serve(data, AVAILABILITY_FRESH)
                _cache["data"] = data
                _cache["timestamp"] = now
                _rc.remember_last_good(_lg_key, data)
                return data
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
    #     and cached in-process so subsequent same-dyno reads are instant. Queue
    #     300B: no caller can skip this tier any more — there is nothing below it
    #     to skip TO except the durable read and an honest 503.
    if not _redis_failed:
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
                    compatible_versions=_compatible_versions(),
                )
                if verdict.is_previous_version:
                    return _previous_version(
                        data, verdict, "main_key_absent_version_superseded"
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
    #    have already failed.
    #
    #    Queue 300B: this is now the ONLY database work the request path does,
    #    and it is a single primary-key read — not a population scan. The route
    #    budget still gates it, so a request that already burned its budget in
    #    Redis answers honestly instead of opening a connection it cannot use.
    if _remaining_ms() > 0:
        try:
            from app.services.durable_snapshots import read_snapshot

            durable = await read_snapshot(
                db,
                "calibration:main",
                expected_version=_expected_version(),
                max_age_s=SERVE_MAX_AGE_S,
            )
            # CAL-P070: a durable row the ENVELOPE refused on version may still
            # be a declared-compatible predecessor. Nothing is relaxed to find
            # out — the envelope's own check keeps biting, and this branch serves
            # only when the payload's ``population_version`` INDEPENDENTLY names
            # a declared predecessor. Two defences that must agree, because the
            # envelope's ``schema_version`` column and the payload's
            # ``population_version`` are written separately and CAN disagree
            # (300B's ``test_durable_wrong_version_does_not_fall_through_to_a_
            # build`` is exactly that row: ancient envelope, current payload) —
            # so a single relaxed check here would have served it.
            if (
                durable.status == "wrong_version"
                and durable.envelope is not None
                and isinstance(durable.envelope.payload, dict)
            ):
                payload = durable.envelope.payload
                verdict = snapshot_verdict(
                    payload,
                    expected_version=_expected_version(),
                    max_age_s=SERVE_MAX_AGE_S,
                    compatible_versions=_compatible_versions(),
                )
                if verdict.is_previous_version:
                    degraded = _previous_version(
                        payload, verdict, "durable_version_superseded"
                    )
                    degraded["provenance"] = durable.envelope.provenance(
                        served_from="durable"
                    )
                    return degraded
            if durable.ok and isinstance(durable.envelope.payload, dict):
                payload = durable.envelope.payload
                # The envelope already proved version, checksum, completeness and
                # age. The SHAPE still gets Q297's full check, because a durable
                # row can be ancient and written under an older payload contract —
                # the same reason the Redis last-good keeps it.
                verdict = snapshot_verdict(
                    payload,
                    expected_version=_expected_version(),
                    max_age_s=SERVE_MAX_AGE_S,
                    compatible_versions=_compatible_versions(),
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

    # 4. LAST tier: a truthful stale/last-good copy from this process.
    #    Before Queue 300B this only ran when Redis had *failed*, because a clean
    #    miss fell through to a cold compute that had its own last-good rescue in
    #    its except branch. With the compute gone, that rescue has to live here or
    #    a clean miss would 503 past a perfectly serviceable dated copy.
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
        return _degraded(stale, "redis_unavailable" if _redis_failed else "cache_miss")

    # 5. LAST RESORT: the newest durable snapshot at ANY age, dated and labelled.
    #
    #    CAL-P017 (Alex, 2026-08-08). Every tier above is bounded by the SAME
    #    constant — the durable read passes SERVE_MAX_AGE_S, snapshot_verdict
    #    re-checks it, and the process/Redis tier passes it again — so all four
    #    refuse in the same instant and the page went from "dated, disclosed and
    #    useful" straight to 503 with nothing in between. That is precisely what
    #    happened at 2026-08-09 03:23Z, seven days after the last publish, and it
    #    is the gap Alex named: SERVE_MAX_AGE_S alone decided when the page went
    #    dark.
    #
    #    The honest-service ruling says degrade to a dated last-known snapshot
    #    behind a banner rather than 503, and the banner already exists —
    #    ``_degraded`` stamps ``cache.status = "stale"`` with ``age_s`` and
    #    ``generated_at``, and the page renders "as of <time> (N ago)". It worked
    #    for the whole week. It just had nothing left to render.
    #
    #    WHAT IS AND IS NOT RELAXED. Only the AGE bound, and only because the age
    #    is disclosed in the same payload: a reader can see a month-old curve is a
    #    month old. The VERSION check stays — a payload built under a different
    #    population contract is not servable at any age, because its numbers do
    #    not mean what the current page says they mean, and no banner fixes that.
    #    Nor does this touch the publish gate: #1517's "a bad build must never
    #    replace a good one" governs what gets WRITTEN, and is untouched here.
    #
    #    CAL-P070 does not relax this tier either, and that is deliberate rather
    #    than an omission: ``compatible_versions`` is passed at the tiers ABOVE,
    #    all of which are bounded by SERVE_MAX_AGE_S, so a declared-compatible
    #    predecessor is servable for as long as an ordinary dated copy is and
    #    refused after — which is exactly the rollover contract's
    #    ``previous-expired-refused`` case. An over-age predecessor is the one
    #    combination nobody has declared anything about, so it stays refused.
    if _remaining_ms() > 0:
        try:
            from app.services.durable_snapshots import read_snapshot
            from app.utils.durable_state import SOURCE_DURABLE

            aged = await read_snapshot(
                db,
                "calibration:main",
                expected_version=_expected_version(),
                # NOT None: both read_snapshot and snapshot_verdict compare
                # ``age_s > max_age_s`` numerically, so None would raise a
                # TypeError, get swallowed by the except below, and quietly
                # reproduce the very 503 this tier exists to prevent. Infinity
                # lifts ONLY the ceiling — the ``age_s < 0`` / future-dated guard
                # and the version check both still bite.
                max_age_s=float("inf"),
            )
            if aged.ok and isinstance(aged.envelope.payload, dict):
                payload = aged.envelope.payload
                verdict = snapshot_verdict(
                    payload,
                    expected_version=_expected_version(),
                    max_age_s=float("inf"),
                )
                if verdict.is_servable:
                    degraded = _degraded(payload, "durable_over_age", verdict)
                    # served_from stays the canonical "durable", NOT a bespoke
                    # tier name: provenance() derives ``dated`` from it
                    # (``served_from in (SOURCE_DURABLE, SOURCE_PROCESS)``), so a
                    # custom value would publish ``dated: False`` for the most
                    # dated copy we ever serve — precisely inverted. The tier is
                    # distinguished where every other tier distinguishes itself,
                    # in the ``cache.reason`` above.
                    degraded["provenance"] = aged.envelope.provenance(
                        served_from=SOURCE_DURABLE
                    )
                    return degraded
                logger.warning(
                    "calibration: over-age durable snapshot still not servable (%s: %s)",
                    verdict.status, verdict.reason,
                )
        except Exception:
            logger.warning(
                "calibration: over-age durable read failed", exc_info=True
            )

    # 6. Nothing anywhere, at any age. There is deliberately no build tier below
    #    this line: the honest 503 IS the answer, and the hourly beat is what
    #    fixes it. See the docstring for why a request may not start the CTE.
    if _remaining_ms() <= 0:
        return _unavailable("route_budget_exhausted")
    return _unavailable("no_trustworthy_snapshot")


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


#: CAL-P067 item 4. Per-category ``resolved outcomes`` denominators for the
#: selection-bias rule, keyed by ``llm_sport_category``.
#:
#: EMPTY, and deliberately so. The numerator (graded outcomes) is the ``n``
#: already on every published cell; the denominator is a
#: ``futures_outcomes x futures_markets`` aggregate, which is the exact query
#: class CAL-P066 documented as planner-hostile — every such join drives from a
#: Seq Scan on ``futures_outcomes``, so a category filter does not restrict it.
#: Measured this window: a single-category count hit ``statement_timeout``.
#: Obtaining it needs CAL-P066's recursive id-range bisection, which is a
#: measurement task rather than a rendering one.
#:
#: In-process override, for tests and for a hand-supplied census. Normally EMPTY
#: — the live denominator comes from the durable artifact the census rail writes
#: (:func:`load_provability_census`), because a constant in code is stale by
#: construction and this population grows continuously.
PROVABILITY_CENSUS: dict[str, int] = {}


def load_provability_census() -> dict[str, int]:
    """Per-category resolved-outcome denominators from the census rail, or ``{}``.

    CAL-P068 item 2 — what makes the selection-bias rule live rather than inert.
    Reads the artifact ``app.tasks.calibration_graded_share`` publishes, and
    returns ``{}`` for every failure mode, because ``{}`` renders as
    "graded share not measured" and that is the honest reading of a census we
    could not load.

    Crucially it also returns ``{}`` for a census that loaded fine but did NOT
    cover the whole population. ``census_from_payload`` enforces that, and the
    reason is one-directional: a denominator missing part of its own population
    is too small, every graded share computed from it is too large, and cells
    would flip from NOT-PROVABLE to provable. Of the two ways to be wrong, only
    one silently un-protects the page.
    """
    if PROVABILITY_CENSUS:
        return dict(PROVABILITY_CENSUS)
    try:
        from app.tasks.calibration_graded_share import census_from_payload
        from app.tasks.redis_state import get_redis_client

        raw = get_redis_client().get(GRADED_SHARE_CACHE_KEY)
        if not raw:
            return {}
        census = census_from_payload(json.loads(raw))
        return dict(census.by_key) if census is not None else {}
    except Exception as exc:  # noqa: BLE001 — never the reason the page is down
        logger.warning("graded-share census read failed: %s", exc)
        return {}


#: Where the census rail publishes, and the route reads.
GRADED_SHARE_CACHE_KEY = "bainluck:calibration:graded_share_census"

#: Why the census is absent, stated ONCE in the payload rather than as fifteen
#: "unmeasured" badges in the UI. The discipline is the same one CAL-P067's
#: ruling-075 fix enforces — a check that did not run must say so — but the
#: honest place to say it once is the payload, not once per row on a public page.
PROVABILITY_CENSUS_ABSENT_REASON = (
    "per-category resolved-outcome denominators are not measured yet: the "
    "futures_outcomes x futures_markets aggregate times out (CAL-P066's Seq Scan "
    "finding) and needs recursive id-range bisection. Until then no cell's graded "
    "share is known, so no cell is asserted provable."
)


def provability_payload_fields(
    cells: list[dict], *, census: Optional[dict[str, int]] = None
) -> dict[str, Any]:
    """The selection-bias annotation, ready for **the BUILDER** to merge.

    Deliberately NOT called from ``_serve``, and that is the whole design note.

    CAL-P067 first wired this into the route and
    ``test_route_serves_the_shared_compute_payload_unaltered`` refused it —
    correctly. That test enumerates its envelope keys rather than prefix-matching
    them precisely so a third cannot "join them by accident and quietly widen
    what unaltered excuses", and the criterion for joining is that the key is a
    **serve-time** fact the builder could not know: ``availability`` (which tier
    answered) and ``producer`` (how many beats since build) qualify.

    Provability does not. Whether a cell's graded share clears 50% is a fact
    about the DATA, not about which tier served it, and a builder writing it
    would be stating a measurement rather than a tautology. So its home is
    ``compute_calibration_payload`` and the route stays what Queue 300B made it:
    not a second builder.

    It cannot move there this window — that function is inside
    ``_main_input_fingerprint``'s digest and editing it resets the in-flight
    staged cursor (ruling 009). So the logic lives here, tested and callable,
    and the one-line call site is owed to the queue that lands after the
    producer publishes.

    Returns ``{"by_category": [...], "provability_census": {...}}``. With no
    census the cells come back untouched and the census block says ``measured:
    false`` with a reason — stating "we cannot check this" once, machine-
    readably, rather than stamping it on fifteen public rows.
    """
    if not isinstance(cells, list):
        return {}
    census = census if census is not None else load_provability_census()
    if not census:
        return {
            "by_category": cells,
            "provability_census": {
                "measured": False,
                "reason": PROVABILITY_CENSUS_ABSENT_REASON,
                "min_graded_share": MIN_GRADED_SHARE,
            },
        }
    return {
        "by_category": annotate_cells(
            cells,
            census=GradedShareCensus(
                by_key=census,
                unit=UNIT_OUTCOMES,
                population=CELL_POPULATION,
            ),
        ),
        "provability_census": {
            "measured": True,
            "categories": len(census),
            "min_graded_share": MIN_GRADED_SHARE,
            "unit": UNIT_OUTCOMES,
            "population": CELL_POPULATION,
        },
    }


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
