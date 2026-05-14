"""Public calibration endpoint — no auth required, cached for 1 hour."""

import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func

from app.models import FuturesMarket
from app.services import get_db

router = APIRouter()

_cache: dict = {"data": None, "timestamp": 0}
CACHE_TTL = 3600


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
              ('economics', 'hockey', 'golf', 'tennis', 'weather', 'politics', 'basketball', 'baseball')
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
            WHERE status = 'completed'
              AND COALESCE(closing_home_probability, opening_home_probability) IS NOT NULL
              AND COALESCE(closing_home_probability, opening_home_probability) > 0
              AND COALESCE(closing_home_probability, opening_home_probability) < 1
              AND home_score IS NOT NULL AND away_score IS NOT NULL
              AND home_score != away_score
            UNION ALL
            SELECT COALESCE(closing_away_probability, opening_away_probability) AS prob,
                   (away_score > home_score) AS won, sport_id
            FROM events
            WHERE status = 'completed'
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
        WHERE status = 'completed'
          AND home_score IS NOT NULL AND away_score IS NOT NULL
    """)
    closing_result = await db.execute(closing_sql)
    closing_row = closing_result.one()

    response = {
        "closing_line_coverage": {
            "has_closing": closing_row.has_closing,
            "needs_closing": closing_row.needs_closing,
            "total": closing_row.total_completed,
        },
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
        "total_outcomes": total_outcomes,
        "total_winners": total_winners,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    _cache["data"] = response
    _cache["timestamp"] = now

    return response
