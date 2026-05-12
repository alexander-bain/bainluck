"""Public calibration endpoint — no auth required, cached for 1 hour."""

import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func

from app.models import FuturesMarket
from app.services import get_db

router = APIRouter()

_cache: dict = {"data": None, "timestamp": 0}
CACHE_TTL = 3600


@router.get("/calibration")
async def public_calibration(db: AsyncSession = Depends(get_db)):
    """Public calibration data for the /calibration page. Cached for 1 hour."""

    now = time.time()
    if _cache["data"] and (now - _cache["timestamp"]) < CACHE_TTL:
        return _cache["data"]

    # Same query as admin calibration-data endpoint
    sql = text("""
        WITH market_info AS (
            SELECT fm.id AS market_id, fm.source, fm.event_id, fm.group_id,
                COALESCE(fm.llm_sport_category, 'uncategorized') AS category,
                fm.mutually_exclusive
            FROM futures_markets fm
            WHERE fm.status = 'resolved'
              -- Exclude Kalshi game-level markets (linked to events):
              -- these have unreliable opening_probability from early bid/ask
              -- spreads. Game-level calibration comes from Odds API events
              -- data instead (ground truth from scores).
              AND NOT (fm.source = 'kalshi' AND fm.event_id IS NOT NULL)
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
                COALESCE(gs.group_size >= 3, false) OR COALESCE(es.event_size >= 3, false) AS is_grouped,
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
                fo.opening_probability AS adj_opening_probability,
                (fo.current_probability >= 0.95) AS is_winner,
                cv.vm_id, cv.source, cv.category,
                cv.eligible, cv.is_grouped,
                (cv.is_grouped OR (cv.mutually_exclusive AND cv.eligible >= 3)) AS is_multi,
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
        mode_prices AS (
            SELECT vm_id, adj_opening_probability AS mode_price,
                   COUNT(*) AS mode_count, eligible
            FROM ranked_outcomes
            WHERE is_multi AND eligible >= 20
            GROUP BY vm_id, adj_opening_probability, eligible
            HAVING COUNT(*) > eligible * 0.5
        ),
        deduped AS (
            SELECT ro.* FROM ranked_outcomes ro
            LEFT JOIN mode_prices mp
              ON mp.vm_id = ro.vm_id AND mp.mode_price = ro.adj_opening_probability
            WHERE
                CASE
                    WHEN ro.is_multi AND ro.eligible >= 20
                        THEN ro.adj_opening_probability > 0.005
                         AND ro.adj_opening_probability < 0.50
                         AND mp.vm_id IS NULL
                    WHEN ro.is_multi
                        THEN ro.adj_opening_probability > 0.005
                         AND ro.adj_opening_probability < 0.98
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
    # Uses opening probability (vig-removed consensus across 20+ sportsbooks).
    # TODO: add closing line from odds_snapshots via materialized view for speed.
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
                   (home_score > away_score) AS won, sport_id
            FROM events
            WHERE status = 'completed'
              AND opening_home_probability IS NOT NULL
              AND opening_home_probability > 0 AND opening_home_probability < 1
              AND home_score IS NOT NULL AND away_score IS NOT NULL
              AND home_score != away_score
            UNION ALL
            SELECT opening_away_probability AS prob,
                   (away_score > home_score) AS won, sport_id
            FROM events
            WHERE status = 'completed'
              AND opening_away_probability IS NOT NULL
              AND opening_away_probability > 0 AND opening_away_probability < 1
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

    # Diagnostic: sample outcomes from problem areas
    diag_sql = text("""
        SELECT fm.name AS market_name, fm.source, fm.group_id,
               fm.llm_sport_category AS category,
               fo.name AS outcome_name, fo.opening_probability,
               fo.current_probability,
               (SELECT COUNT(*) FROM futures_outcomes fo2
                WHERE fo2.market_id = fm.id) AS sibling_count
        FROM futures_outcomes fo
        JOIN futures_markets fm ON fo.market_id = fm.id
        WHERE fm.status = 'resolved'
          AND fo.opening_probability > 0.35 AND fo.opening_probability < 0.55
          AND fo.current_probability IS NOT NULL
          AND fm.llm_sport_category IN ('entertainment', 'economics', 'golf')
          AND NOT (fm.source = 'kalshi' AND fm.event_id IS NOT NULL)
        ORDER BY fm.llm_sport_category, fm.source, RANDOM()
        LIMIT 40
    """)
    diag_result = await db.execute(diag_sql)
    diagnostics = [
        {"market": r.market_name, "source": r.source, "category": r.category,
         "outcome": r.outcome_name, "opening": float(r.opening_probability),
         "current": float(r.current_probability), "siblings": r.sibling_count,
         "group_id": r.group_id}
        for r in diag_result.all()
    ]

    response = {
        "diagnostics": diagnostics,
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
