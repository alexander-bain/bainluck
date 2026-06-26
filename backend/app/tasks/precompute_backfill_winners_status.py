"""Precompute the backfill-winners/status endpoint and cache in Redis.

The /api/admin/backfill-winners/status endpoint runs multiple expensive
aggregation queries across the futures_markets, futures_outcomes, and
futures_odds_snapshots tables.  These routinely exceed Heroku's 30-second
request timeout on production data volumes.

This task runs the same queries on the background Celery worker and stores
the full JSON response in Redis so the endpoint can serve instantly.
"""

import json
import logging
from datetime import datetime, timezone

from sqlalchemy import text

logger = logging.getLogger(__name__)

CACHE_KEY = "bainluck:backfill_winners_status"
CACHE_TTL = 7200  # 2 hours — task runs every 1h so always fresh


async def _precompute_backfill_winners_status() -> dict:
    """Run all backfill-winners/status queries and cache the result."""
    from app.tasks.base import get_task_session
    from app.tasks.redis_state import get_redis_client

    stats: dict = {"status": "ok", "errors": []}

    try:
        async with get_task_session() as session:
            # ── 1. Sources summary (main query) ─────────────────────────
            # #940 metric honesty: a market with no winning outcome is NOT
            # automatically "needs_backfill". Most are single-sided Kalshi/Poly
            # threshold/binary markets that correctly resolved NO (gotcha #17 —
            # "Over 224.5", total 211 → the lone outcome is correctly is_winner=
            # false; there is no winner BY STRUCTURE). Split the no-winner-tradeable
            # universe three ways by resolution_source:
            #   needs_backfill        = NO resolution_source at all (the genuine gap)
            #   resolved_single_sided = authoritative (api_settlement/game_score/
            #                           box_score) — correctly resolved, EXCLUDED
            #   heuristic_resolved    = guessed (pass2_loser/all_losers/
            #                           clean_resolution[=relabeled pass2_guess]/…)
            #                           — correctness is the SEPARATE #754 audit
            # Count/denominator-only — NO is_winner/cal_prob mutation (gotcha #21).
            # clean_resolution is treated as heuristic (it is renamed pass2_guess,
            # see backfill_winners repair) — held for #754, NOT excluded as correct.
            result = await session.execute(text("""
                WITH market_status AS (
                    SELECT fm.id, fm.source,
                        BOOL_OR(fo.is_winner) AS has_winner,
                        MAX(fo.current_probability) AS max_prob,
                        BOOL_AND(fo.calibration_probability IS NULL
                                 AND fo.opening_probability IS NULL) AS all_cal_null,
                        BOOL_OR(fo.resolution_source IS NOT NULL) AS any_rsrc,
                        BOOL_OR(fo.resolution_source IN
                                ('api_settlement', 'game_score', 'box_score'))
                            AS authoritative
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
                          AND NOT any_rsrc
                          AND NOT (all_cal_null AND source != 'datagolf')
                          AND (max_prob IS NULL OR max_prob > 0.10)
                    ) AS needs_backfill,
                    COUNT(*) FILTER (
                        WHERE NOT has_winner AND authoritative
                          AND NOT (all_cal_null AND source != 'datagolf')
                          AND (max_prob IS NULL OR max_prob > 0.10)
                    ) AS resolved_single_sided,
                    COUNT(*) FILTER (
                        WHERE NOT has_winner AND any_rsrc AND NOT authoritative
                          AND NOT (all_cal_null AND source != 'datagolf')
                          AND (max_prob IS NULL OR max_prob > 0.10)
                    ) AS heuristic_resolved,
                    COUNT(*) FILTER (
                        WHERE all_cal_null AND source != 'datagolf'
                    ) AS untradeable_excluded
                FROM market_status
                GROUP BY source
            """))
            sources = [
                {"source": r.source, "resolved": r.resolved_markets,
                 "has_winner": r.has_winner, "needs_backfill": r.needs_backfill,
                 "resolved_single_sided": r.resolved_single_sided,
                 "heuristic_resolved": r.heuristic_resolved,
                 "untradeable_excluded": r.untradeable_excluded}
                for r in result.all()
            ]

            # ── 2. Sample Polymarket soccer outcomes (diagnostics) ──────
            sample_diag = await session.execute(text("""
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
            soccer_samples = [
                {"id": r.id, "opening": float(r.opening_probability),
                 "outcome": r.outcome_name, "market": r.market_name,
                 "current": float(r.current_probability),
                 "captured_at": str(r.opening_captured_at) if r.opening_captured_at else None,
                 "snaps": r.snap_count,
                 "last_snap": float(r.last_snap_prob) if r.last_snap_prob else None}
                for r in sample_diag.all()
            ]

            # ── 3. Calibration probability coverage ─────────────────────
            cal_result = await session.execute(text("""
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

            # ── 4. Polymarket group_id health ───────────────────────────
            group_result = await session.execute(text("""
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

            # ── 5. Orphan group samples ─────────────────────────────────
            orphan_result = await session.execute(text("""
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
            """))
            orphan_samples = [
                {"id": r.id, "name": r.name, "category": r.cat,
                 "group_id": r.group_id, "group_type": r.group_type,
                 "external_id": r.external_id, "outcomes": r.outcome_count,
                 "poly_event_id": r.poly_event_id}
                for r in orphan_result.all()
            ]

            # ── 6. Stuck winners diagnosis ──────────────────────────────
            stuck_diagnosis = await _diagnose_stuck_winners(session)

            # ── Build full response ─────────────────────────────────────
            response = {
                "sources": sources,
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
                "orphan_samples": orphan_samples,
                "soccer_samples": soccer_samples,
                "stuck_diagnosis": stuck_diagnosis,
                "computed_at": datetime.now(timezone.utc).isoformat(),
            }

            # ── Write to Redis ──────────────────────────────────────────
            rc = get_redis_client()
            rc.setex(CACHE_KEY, CACHE_TTL, json.dumps(response, default=str))
            stats["cached"] = True
            stats["sources_count"] = len(sources)
            logger.info("Precomputed backfill-winners/status cache (%d sources)", len(sources))

    except Exception as e:
        stats["status"] = "error"
        stats["errors"].append(str(e)[:500])
        logger.error("Failed to precompute backfill-winners/status: %s", e)

    return stats


async def _diagnose_stuck_winners(session) -> dict:
    """Why are is_winner backfills stuck? Categorize the blockers."""
    # Polymarket: check current_probability distribution on stuck markets
    poly_diag = await session.execute(text("""
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

    # Sample stuck markets with midrange probabilities
    sample = await session.execute(text("""
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

    # Snapshot distribution for stuck midrange markets
    snap_dist = await session.execute(text("""
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
    cat_breakdown = await session.execute(text("""
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
