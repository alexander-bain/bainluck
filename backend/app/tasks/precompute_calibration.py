"""Precompute heavy calibration queries and cache results in Redis.

These queries time out during Heroku's 30-second request window on production
data volumes (500K+ snapshot rows). Running them as background Celery tasks
with results cached in Redis lets the API endpoints serve instantly.
"""

import json
import logging
import math
import random
from datetime import datetime, timezone

from sqlalchemy import text

logger = logging.getLogger(__name__)

# Redis cache TTL: 24 hours (results don't change quickly)
_CACHE_TTL = 86400

# Main calibration cache TTL: 2 hours (refreshed every 1h by beat)
_MAIN_CACHE_TTL = 7200

# Horizons: (label, days_before_resolution)
_HORIZONS = [
    ("T-30", 30),
    ("T-7", 7),
    ("T-1", 1),
    ("T-0", 0),
]

_MIN_OUTCOMES_PER_HORIZON = 50


def _wilson_ci(wins: int, total: int, z: float = 1.96) -> tuple[float, float]:
    if total == 0:
        return (0.0, 0.0)
    p = wins / total
    denom = 1 + z**2 / total
    center = (p + z**2 / (2 * total)) / denom
    spread = z * math.sqrt((p * (1 - p) + z**2 / (4 * total)) / total) / denom
    return (max(0.0, center - spread), min(1.0, center + spread))


def _bootstrap_mce_ci(
    bucket_list: list[dict],
    n_boot: int = 1000,
    seed: int = 42,
) -> tuple[float, float]:
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


def _compute_horizon_mce(buckets: list[dict]) -> float | None:
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


async def _precompute_calibration_main():
    """Precompute the main /api/calibration response and store in Redis.

    This mirrors the logic in routes/calibration.py public_calibration() but
    runs as a Celery background task so the HTTP endpoint can serve instantly
    from the Redis cache instead of running 6 heavy queries in-request.
    """
    from sqlalchemy import func, select

    from app.models import FuturesMarket
    from app.tasks.base import get_task_session
    from app.tasks.redis_state import get_redis_client

    async with get_task_session() as db:
        # -----------------------------------------------------------
        # Query 1: Main futures calibration buckets
        # -----------------------------------------------------------
        main_sql = text("""
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
            vm_stats AS (
                SELECT
                    vm.vm_id, vm.source, vm.category, vm.is_grouped,
                    vm.mutually_exclusive,
                    COUNT(DISTINCT vm.market_id) AS market_count,
                    COUNT(*) AS total_outcomes,
                    COUNT(*) FILTER (WHERE fo.is_winner = true) AS has_winner,
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
                  AND has_winner >= 1
            ),
            ranked_outcomes AS (
                SELECT
                    COALESCE(fo.calibration_probability, fo.opening_probability) AS adj_opening_probability,
                    fo.is_winner AS is_winner,
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
                  AND (fo.resolution_source IS NULL
                       OR fo.resolution_source NOT IN ('pass2_guess', 'pass3_threshold'))
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
        result = await db.execute(main_sql)
        rows = result.all()

        # -----------------------------------------------------------
        # Query 2: Ground-truth sports calibration from events table
        # -----------------------------------------------------------
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

        # -----------------------------------------------------------
        # Query 3: Spread calibration
        # -----------------------------------------------------------
        spreads_sql = text("""
            SELECT
                LEAST(FLOOR(prob * 10)::int, 9) AS bucket_idx,
                'odds_api_spreads' AS source,
                s.key AS category,
                COUNT(*) AS n,
                SUM(CASE WHEN won THEN 1 ELSE 0 END) AS winners,
                AVG(prob) AS avg_prob,
                SUM(prob::float) AS sum_prob,
                SUM((prob::float - CASE WHEN won THEN 1.0 ELSE 0.0 END)^2) AS sum_sq_err
            FROM (
                SELECT
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
                           ELSE 100.0 / (closing_away_spread_odds + 100.0) END))
                    AS prob,
                    ((home_score - away_score) + closing_home_spread > 0) AS won,
                    sport_id
                FROM events
                WHERE status IN ('completed', 'closed')
                  AND closing_home_spread IS NOT NULL
                  AND closing_home_spread_odds IS NOT NULL
                  AND closing_away_spread_odds IS NOT NULL
                  AND home_score IS NOT NULL AND away_score IS NOT NULL
                  AND (home_score - away_score) + closing_home_spread != 0
            ) outcomes
            JOIN sports s ON s.id = outcomes.sport_id
            WHERE prob > 0 AND prob < 1
            GROUP BY bucket_idx, s.key
            ORDER BY bucket_idx, s.key
        """)
        spreads_result = await db.execute(spreads_sql)
        spreads_rows = spreads_result.all()

        # -----------------------------------------------------------
        # Query 4: Totals calibration
        # -----------------------------------------------------------
        totals_sql = text("""
            SELECT
                LEAST(FLOOR(prob * 10)::int, 9) AS bucket_idx,
                'odds_api_totals' AS source,
                s.key AS category,
                COUNT(*) AS n,
                SUM(CASE WHEN won THEN 1 ELSE 0 END) AS winners,
                AVG(prob) AS avg_prob,
                SUM(prob::float) AS sum_prob,
                SUM((prob::float - CASE WHEN won THEN 1.0 ELSE 0.0 END)^2) AS sum_sq_err
            FROM (
                SELECT
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
                           ELSE 100.0 / (closing_under_odds + 100.0) END))
                    AS prob,
                    ((home_score + away_score) > closing_over_under) AS won,
                    sport_id
                FROM events
                WHERE status IN ('completed', 'closed')
                  AND closing_over_under IS NOT NULL
                  AND closing_over_odds IS NOT NULL
                  AND closing_under_odds IS NOT NULL
                  AND home_score IS NOT NULL AND away_score IS NOT NULL
                  AND (home_score + away_score) != closing_over_under
            ) outcomes
            JOIN sports s ON s.id = outcomes.sport_id
            WHERE prob > 0 AND prob < 1
            GROUP BY bucket_idx, s.key
            ORDER BY bucket_idx, s.key
        """)
        totals_result = await db.execute(totals_sql)
        totals_rows = totals_result.all()

        # -----------------------------------------------------------
        # Query 5: Per-bookmaker calibration from Redis
        # -----------------------------------------------------------
        bookmaker_rows = []
        try:
            from types import SimpleNamespace as _NS
            rc = get_redis_client()
            _cached = rc.get("bainluck:bookmaker_calibration")
            if _cached:
                bookmaker_rows = [_NS(**row) for row in json.loads(_cached)]
        except Exception:
            pass

        # -----------------------------------------------------------
        # Query 6: Total resolved markets count
        # -----------------------------------------------------------
        total_markets_result = await db.execute(
            select(func.count()).select_from(FuturesMarket).where(
                FuturesMarket.status == "resolved"
            )
        )
        total_markets = total_markets_result.scalar()

        # -----------------------------------------------------------
        # Query 7: Closing line coverage
        # -----------------------------------------------------------
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

    # -----------------------------------------------------------
    # Post-processing (runs outside the DB session)
    # -----------------------------------------------------------
    all_rows = list(rows) + list(events_rows) + list(spreads_rows) + list(totals_rows) + list(bookmaker_rows)
    total_outcomes = sum(r.n for r in all_rows)
    total_winners = sum(r.winners for r in all_rows)

    # Build bucket dicts with Wilson CIs
    bucket_dicts = []
    for r in all_rows:
        ci_lo, ci_hi = _wilson_ci(r.winners, r.n)
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
    mce_ci_lo, mce_ci_hi = _bootstrap_mce_ci(agg_list)

    # Cohort-level MCE: closing line vs opening price
    def _cohort_mce(buckets: list[dict], pred: object) -> float | None:
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

    # Per-category MCE breakdown
    cat_agg: dict[str, dict[int, dict]] = {}
    cat_outcomes: dict[str, int] = {}
    for b in bucket_dicts:
        cat = b["category"]
        idx = b["bucket_idx"]
        if cat not in cat_agg:
            cat_agg[cat] = {}
            cat_outcomes[cat] = 0
        if idx not in cat_agg[cat]:
            cat_agg[cat][idx] = {"n": 0, "winners": 0, "sum_prob": 0.0}
        cat_agg[cat][idx]["n"] += b["n"]
        cat_agg[cat][idx]["winners"] += b["winners"]
        cat_agg[cat][idx]["sum_prob"] += b["sum_prob"]
        cat_outcomes[cat] += b["n"]

    by_category = []
    for cat, buckets_by_idx in sorted(cat_agg.items()):
        total_n = cat_outcomes[cat]
        if total_n == 0:
            continue
        cat_mce = _compute_horizon_mce([
            {"n": v["n"], "winners": v["winners"], "sum_prob": v["sum_prob"]}
            for v in buckets_by_idx.values()
        ])
        by_category.append({"category": cat, "mce": cat_mce, "outcomes": total_n})
    by_category.sort(key=lambda x: x["outcomes"], reverse=True)

    # Per-source MCE breakdown
    src_agg: dict[str, dict[int, dict]] = {}
    src_outcomes: dict[str, int] = {}
    for b in bucket_dicts:
        src = b["source"]
        idx = b["bucket_idx"]
        if src not in src_agg:
            src_agg[src] = {}
            src_outcomes[src] = 0
        if idx not in src_agg[src]:
            src_agg[src][idx] = {"n": 0, "winners": 0, "sum_prob": 0.0}
        src_agg[src][idx]["n"] += b["n"]
        src_agg[src][idx]["winners"] += b["winners"]
        src_agg[src][idx]["sum_prob"] += b["sum_prob"]
        src_outcomes[src] += b["n"]

    by_source = []
    for src, buckets_by_idx in sorted(src_agg.items()):
        total_n = src_outcomes[src]
        if total_n == 0:
            continue
        src_mce = _compute_horizon_mce([
            {"n": v["n"], "winners": v["winners"], "sum_prob": v["sum_prob"]}
            for v in buckets_by_idx.values()
        ])
        by_source.append({"source": src, "mce": src_mce, "outcomes": total_n})
    by_source.sort(key=lambda x: x["outcomes"], reverse=True)

    # Spread / Total summaries
    def _source_summary(source_key: str) -> dict:
        sport_agg: dict[str, dict[int, dict]] = {}
        sport_outcomes: dict[str, int] = {}
        total_n = 0
        total_w = 0
        for b in bucket_dicts:
            if b["source"] != source_key:
                continue
            sport = b["category"]
            idx = b["bucket_idx"]
            if sport not in sport_agg:
                sport_agg[sport] = {}
                sport_outcomes[sport] = 0
            if idx not in sport_agg[sport]:
                sport_agg[sport][idx] = {"n": 0, "winners": 0, "sum_prob": 0.0}
            sport_agg[sport][idx]["n"] += b["n"]
            sport_agg[sport][idx]["winners"] += b["winners"]
            sport_agg[sport][idx]["sum_prob"] += b["sum_prob"]
            sport_outcomes[sport] += b["n"]
            total_n += b["n"]
            total_w += b["winners"]

        by_sport = []
        for sport, buckets_by_idx in sorted(sport_agg.items()):
            sn = sport_outcomes[sport]
            if sn == 0:
                continue
            sport_mce = _compute_horizon_mce([
                {"n": v["n"], "winners": v["winners"], "sum_prob": v["sum_prob"]}
                for v in buckets_by_idx.values()
            ])
            by_sport.append({"sport": sport, "mce": sport_mce, "outcomes": sn})
        by_sport.sort(key=lambda x: x["outcomes"], reverse=True)

        all_agg: dict[int, dict] = {}
        for b in bucket_dicts:
            if b["source"] != source_key:
                continue
            idx = b["bucket_idx"]
            if idx not in all_agg:
                all_agg[idx] = {"n": 0, "winners": 0, "sum_prob": 0.0}
            all_agg[idx]["n"] += b["n"]
            all_agg[idx]["winners"] += b["winners"]
            all_agg[idx]["sum_prob"] += b["sum_prob"]
        overall_mce = _compute_horizon_mce([
            {"n": v["n"], "winners": v["winners"], "sum_prob": v["sum_prob"]}
            for v in all_agg.values()
        ])

        return {
            "mce": overall_mce,
            "outcomes": total_n,
            "winners": total_w,
            "by_sport": by_sport,
        }

    spreads_summary = _source_summary("odds_api_spreads")
    totals_summary = _source_summary("odds_api_totals")

    response = {
        "closing_line_coverage": {
            "has_closing": closing_row.has_closing,
            "needs_closing": closing_row.needs_closing,
            "total": closing_row.total_completed,
        },
        "buckets": bucket_dicts,
        "by_category": by_category,
        "by_source": by_source,
        "spreads_summary": spreads_summary,
        "totals_summary": totals_summary,
        "total_markets": total_markets,
        "total_outcomes": total_outcomes,
        "total_winners": total_winners,
        "mce_ci_lower": round(mce_ci_lo * 100, 2),
        "mce_ci_upper": round(mce_ci_hi * 100, 2),
        "mce_closing_line": mce_closing_line,
        "mce_opening_price": mce_opening_price,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    # Store in Redis
    rc = get_redis_client()
    rc.set("bainluck:calibration:main", json.dumps(response), ex=_MAIN_CACHE_TTL)
    logger.info("Cached main calibration in Redis (%d buckets, %d outcomes)", len(bucket_dicts), total_outcomes)
    return {"status": "ok", "buckets": len(bucket_dicts), "outcomes": total_outcomes}


async def _compute_time_horizon_calibration():
    """Compute time-horizon calibration and store in Redis."""
    from app.tasks.base import get_task_session
    from app.tasks.redis_state import get_redis_client

    async with get_task_session() as db:
        horizons_result: dict = {}

        for label, days in _HORIZONS:
            if days == 0:
                cutoff_expr = "eo.resolution_date"
            else:
                cutoff_expr = "eo.resolution_date - make_interval(days => :days)"

            horizon_sql = text(f"""
                WITH eligible_outcomes AS (
                    SELECT fo.id AS outcome_id,
                           fo.is_winner,
                           fm.resolution_date,
                           fm.source,
                           COALESCE(fm.llm_sport_category, 'uncategorized') AS category
                    FROM futures_outcomes fo
                    JOIN futures_markets fm ON fm.id = fo.market_id
                    WHERE fm.status = 'resolved'
                      AND fm.event_id IS NULL
                      AND fm.resolution_date IS NOT NULL
                      AND fo.opening_probability IS NOT NULL
                      AND fo.opening_probability > 0 AND fo.opening_probability < 1
                      AND (fo.resolution_source IS NULL
                           OR fo.resolution_source NOT IN ('pass2_guess', 'pass3_threshold'))
                ),
                horizon_snap AS (
                    SELECT
                        eo.outcome_id,
                        eo.is_winner,
                        eo.source,
                        eo.category,
                        horizon.probability AS horizon_prob
                    FROM eligible_outcomes eo
                    LEFT JOIN LATERAL (
                        SELECT fos.probability
                        FROM futures_odds_snapshots fos
                        WHERE fos.outcome_id = eo.outcome_id
                          AND fos.captured_at <= {cutoff_expr}
                          AND fos.probability > 0 AND fos.probability < 1
                        ORDER BY fos.captured_at DESC
                        LIMIT 1
                    ) horizon ON true
                    WHERE horizon.probability IS NOT NULL
                ),
                bucketed AS (
                    SELECT *,
                        LEAST(FLOOR(horizon_prob * 10)::int, 9) AS bucket_idx
                    FROM horizon_snap
                )
                SELECT bucket_idx, source, category,
                    COUNT(*) AS n,
                    SUM(CASE WHEN is_winner THEN 1 ELSE 0 END) AS winners,
                    AVG(horizon_prob) AS avg_prob,
                    SUM(horizon_prob::float) AS sum_prob,
                    SUM((horizon_prob::float - CASE WHEN is_winner THEN 1.0 ELSE 0.0 END)^2) AS sum_sq_err
                FROM bucketed
                GROUP BY bucket_idx, source, category
                ORDER BY bucket_idx, source, category
            """)

            params: dict = {}
            if days > 0:
                params["days"] = days

            result = await db.execute(horizon_sql, params)
            rows = result.all()

            bucket_dicts = []
            for r in rows:
                ci_lo, ci_hi = _wilson_ci(r.winners, r.n)
                bucket_dicts.append({
                    "bucket_idx": r.bucket_idx,
                    "source": r.source,
                    "category": r.category,
                    "n": r.n,
                    "winners": r.winners,
                    "avg_prob": round(float(r.avg_prob), 4),
                    "sum_prob": round(float(r.sum_prob), 4),
                    "sum_sq_err": round(float(r.sum_sq_err), 4),
                    "ci_lower": round(ci_lo, 4),
                    "ci_upper": round(ci_hi, 4),
                })

            total_n = sum(b["n"] for b in bucket_dicts)
            total_winners = sum(b["winners"] for b in bucket_dicts)

            if total_n < _MIN_OUTCOMES_PER_HORIZON:
                horizons_result[label] = {
                    "buckets": bucket_dicts,
                    "total_outcomes": total_n,
                    "total_winners": total_winners,
                    "mce": None,
                    "mce_ci_lower": None,
                    "mce_ci_upper": None,
                    "skipped": True,
                    "skip_reason": f"Only {total_n} outcomes (minimum {_MIN_OUTCOMES_PER_HORIZON})",
                }
                continue

            # Aggregate for MCE
            agg: dict[int, dict] = {}
            for b in bucket_dicts:
                idx = b["bucket_idx"]
                if idx not in agg:
                    agg[idx] = {"n": 0, "winners": 0, "sum_prob": 0.0}
                agg[idx]["n"] += b["n"]
                agg[idx]["winners"] += b["winners"]
                agg[idx]["sum_prob"] += b["sum_prob"]

            mce = _compute_horizon_mce([
                {"n": v["n"], "winners": v["winners"], "sum_prob": v["sum_prob"]}
                for v in agg.values()
            ])

            # Bootstrap CI
            agg_list = [
                {"n": v["n"], "winners": v["winners"],
                 "avg_prob": v["sum_prob"] / v["n"]}
                for v in agg.values() if v["n"] > 0
            ]
            mce_ci_lo, mce_ci_hi = _bootstrap_mce_ci(agg_list)

            # Per-source MCE
            by_source: dict[str, dict[int, dict]] = {}
            for b in bucket_dicts:
                src = b["source"]
                idx = b["bucket_idx"]
                if src not in by_source:
                    by_source[src] = {}
                if idx not in by_source[src]:
                    by_source[src][idx] = {"n": 0, "winners": 0, "sum_prob": 0.0}
                by_source[src][idx]["n"] += b["n"]
                by_source[src][idx]["winners"] += b["winners"]
                by_source[src][idx]["sum_prob"] += b["sum_prob"]
            mce_by_source = {}
            for src, src_agg in by_source.items():
                src_total = sum(v["n"] for v in src_agg.values())
                if src_total >= _MIN_OUTCOMES_PER_HORIZON:
                    mce_by_source[src] = _compute_horizon_mce([
                        {"n": v["n"], "winners": v["winners"], "sum_prob": v["sum_prob"]}
                        for v in src_agg.values()
                    ])

            # Per-category MCE
            by_cat: dict[str, dict[int, dict]] = {}
            for b in bucket_dicts:
                cat = b["category"]
                idx = b["bucket_idx"]
                if cat not in by_cat:
                    by_cat[cat] = {}
                if idx not in by_cat[cat]:
                    by_cat[cat][idx] = {"n": 0, "winners": 0, "sum_prob": 0.0}
                by_cat[cat][idx]["n"] += b["n"]
                by_cat[cat][idx]["winners"] += b["winners"]
                by_cat[cat][idx]["sum_prob"] += b["sum_prob"]
            mce_by_category = {}
            for cat, cat_agg in by_cat.items():
                cat_total = sum(v["n"] for v in cat_agg.values())
                if cat_total >= _MIN_OUTCOMES_PER_HORIZON:
                    mce_by_category[cat] = _compute_horizon_mce([
                        {"n": v["n"], "winners": v["winners"], "sum_prob": v["sum_prob"]}
                        for v in cat_agg.values()
                    ])

            horizons_result[label] = {
                "buckets": bucket_dicts,
                "total_outcomes": total_n,
                "total_winners": total_winners,
                "mce": mce,
                "mce_ci_lower": round(mce_ci_lo * 100, 2),
                "mce_ci_upper": round(mce_ci_hi * 100, 2),
                "mce_by_source": mce_by_source,
                "mce_by_category": mce_by_category,
            }

        response = {
            "horizons": horizons_result,
            "description": (
                "Calibration at multiple time horizons for non-event markets "
                "(elections, economics, entertainment, etc.). Each horizon shows "
                "prediction accuracy using the last available snapshot N days "
                "before market resolution."
            ),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    # Store in Redis
    rc = get_redis_client()
    rc.set("bainluck:calibration:time_horizon", json.dumps(response), ex=_CACHE_TTL)
    logger.info("Cached time-horizon calibration in Redis")
    return {"status": "ok", "horizons": len(horizons_result)}


# ---------------------------------------------------------------------------
# Fair-fight comparison precomputation
# ---------------------------------------------------------------------------

# Minimum shared markets to report a pair
_MIN_SHARED = 100


def _compute_mce(probs: list[float], outcomes: list[bool]) -> float | None:
    if not probs:
        return None
    bucket_n: dict[int, int] = {}
    bucket_sum_prob: dict[int, float] = {}
    bucket_winners: dict[int, int] = {}
    for p, won in zip(probs, outcomes):
        idx = min(int(p * 10), 9)
        bucket_n[idx] = bucket_n.get(idx, 0) + 1
        bucket_sum_prob[idx] = bucket_sum_prob.get(idx, 0.0) + p
        bucket_winners[idx] = bucket_winners.get(idx, 0) + (1 if won else 0)
    if not bucket_n:
        return None
    total_abs_err = 0.0
    k = 0
    for idx in bucket_n:
        n = bucket_n[idx]
        avg_prob = bucket_sum_prob[idx] / n
        actual = bucket_winners[idx] / n
        total_abs_err += abs(actual - avg_prob)
        k += 1
    return round(total_abs_err / k * 100, 2) if k > 0 else None


# Kalshi prop filter — same as source_intelligence.py
_KALSHI_PROP_FILTER = """
    AND NOT (
        wp.source = 'kalshi'
        AND wp.game_state->>'market_name' IS NOT NULL
        AND (
            wp.game_state->>'market_name' ILIKE '%spread%'
            OR wp.game_state->>'market_name' ILIKE '%total%'
            OR wp.game_state->>'market_name' ILIKE '%overtime%'
            OR wp.game_state->>'market_name' ILIKE '%half winner%'
            OR wp.game_state->>'market_name' ILIKE '%half total%'
            OR wp.game_state->>'market_name' ILIKE '%half spread%'
            OR wp.game_state->>'market_name' ILIKE '% points%'
            OR wp.game_state->>'market_name' ILIKE '% rebounds%'
            OR wp.game_state->>'market_name' ILIKE '% assists%'
            OR wp.game_state->>'market_name' ILIKE '% steals%'
            OR wp.game_state->>'market_name' ILIKE '% blocks%'
            OR wp.game_state->>'market_name' ILIKE '%three pointer%'
            OR wp.game_state->>'market_name' ILIKE '%double double%'
            OR wp.game_state->>'market_name' ILIKE '%triple double%'
            OR wp.game_state->>'market_name' ILIKE '%leader%'
            OR wp.game_state->>'market_name' ILIKE '%strikeout%'
            OR wp.game_state->>'market_name' ILIKE '%home run%'
        )
    )
"""


async def _query_futures_fair_fight_impl(db):
    """Paired MCE comparison for Kalshi vs Polymarket on futures markets."""
    sql = text("""
        WITH source_questions AS (
            SELECT
                fm.source,
                fm.id AS market_id,
                fm.group_id,
                fm.canonical_market_key,
                COALESCE(fm.llm_sport_category, 'uncategorized') AS category
            FROM futures_markets fm
            WHERE fm.status = 'resolved'
              AND fm.source IN ('kalshi', 'polymarket')
        ),
        group_pairs AS (
            SELECT DISTINCT sq1.group_id AS match_key, 'group_id' AS match_type,
                sq1.category
            FROM source_questions sq1
            JOIN source_questions sq2 ON sq1.group_id = sq2.group_id
            WHERE sq1.source = 'kalshi' AND sq2.source = 'polymarket'
              AND sq1.group_id IS NOT NULL
        ),
        key_pairs AS (
            SELECT DISTINCT sq1.canonical_market_key AS match_key, 'canonical' AS match_type,
                sq1.category
            FROM source_questions sq1
            JOIN source_questions sq2 ON sq1.canonical_market_key = sq2.canonical_market_key
            WHERE sq1.source = 'kalshi' AND sq2.source = 'polymarket'
              AND sq1.canonical_market_key IS NOT NULL
              AND NOT EXISTS (
                  SELECT 1 FROM source_questions sq3
                  JOIN source_questions sq4 ON sq3.group_id = sq4.group_id
                  WHERE sq3.source = 'kalshi' AND sq4.source = 'polymarket'
                    AND sq3.group_id IS NOT NULL
                    AND sq3.canonical_market_key = sq1.canonical_market_key
              )
        ),
        all_matches AS (
            SELECT match_key, match_type, category FROM group_pairs
            UNION ALL
            SELECT match_key, match_type, category FROM key_pairs
        ),
        matched_outcomes AS (
            SELECT
                am.match_key, am.match_type, am.category,
                fm.source,
                fo.id AS outcome_id,
                COALESCE(fo.calibration_probability, fo.opening_probability) AS prob,
                fo.is_winner
            FROM all_matches am
            JOIN futures_markets fm ON (
                (am.match_type = 'group_id' AND fm.group_id = am.match_key)
                OR (am.match_type = 'canonical' AND fm.canonical_market_key = am.match_key)
            )
            JOIN futures_outcomes fo ON fo.market_id = fm.id
            WHERE fm.status = 'resolved'
              AND fm.source IN ('kalshi', 'polymarket')
              AND fo.opening_probability IS NOT NULL
              AND fo.opening_probability > 0 AND fo.opening_probability < 1
              AND (fo.resolution_source IS NULL
                   OR fo.resolution_source NOT IN ('pass2_guess', 'pass3_threshold'))
        )
        SELECT source, category, prob, is_winner
        FROM matched_outcomes
        WHERE prob IS NOT NULL AND prob > 0 AND prob < 1
        ORDER BY source, category
    """)
    result = await db.execute(sql)
    rows = result.all()

    by_cat: dict[str, dict[str, tuple[list[float], list[bool]]]] = {}
    for r in rows:
        cat = r.category
        src = r.source
        if cat not in by_cat:
            by_cat[cat] = {}
        if src not in by_cat[cat]:
            by_cat[cat][src] = ([], [])
        by_cat[cat][src][0].append(float(r.prob))
        by_cat[cat][src][1].append(bool(r.is_winner))

    all_kalshi_probs: list[float] = []
    all_kalshi_outcomes: list[bool] = []
    all_poly_probs: list[float] = []
    all_poly_outcomes: list[bool] = []
    by_category: list[dict] = []

    for cat, sources in sorted(by_cat.items()):
        k_data = sources.get("kalshi")
        p_data = sources.get("polymarket")
        if not k_data or not p_data:
            continue
        k_probs, k_wins = k_data
        p_probs, p_wins = p_data
        shared_n = min(len(k_probs), len(p_probs))
        if shared_n < 10:
            continue
        all_kalshi_probs.extend(k_probs)
        all_kalshi_outcomes.extend(k_wins)
        all_poly_probs.extend(p_probs)
        all_poly_outcomes.extend(p_wins)
        k_mce = _compute_mce(k_probs, k_wins)
        p_mce = _compute_mce(p_probs, p_wins)
        if k_mce is not None and p_mce is not None:
            by_category.append({
                "category": cat,
                "kalshi_n": len(k_probs),
                "polymarket_n": len(p_probs),
                "mce_kalshi": k_mce,
                "mce_polymarket": p_mce,
            })

    pairs = []
    total_shared = min(len(all_kalshi_probs), len(all_poly_probs))
    if total_shared >= _MIN_SHARED:
        mce_k = _compute_mce(all_kalshi_probs, all_kalshi_outcomes)
        mce_p = _compute_mce(all_poly_probs, all_poly_outcomes)
        if mce_k is not None and mce_p is not None:
            winner = "kalshi" if mce_k < mce_p else "polymarket" if mce_p < mce_k else "tie"
            pairs.append({
                "source_a": "kalshi",
                "source_b": "polymarket",
                "shared_markets": total_shared,
                "mce_a": mce_k,
                "mce_b": mce_p,
                "winner": winner,
                "advantage_pp": round(abs(mce_k - mce_p), 2),
                "by_category": [c for c in by_category if c["kalshi_n"] >= 20],
            })
    return pairs


async def _query_sports_fair_fight_impl(db):
    """Paired MCE comparison for prediction markets vs Odds API on sports events."""
    sql = text(f"""
        WITH wp_closing AS (
            SELECT DISTINCT ON (wp.event_id, wp.source)
                wp.event_id, wp.source, wp.home_win_probability
            FROM win_prob_snapshots wp
            JOIN events e ON e.id = wp.event_id
            WHERE e.status IN ('completed', 'closed')
              AND e.home_score IS NOT NULL AND e.away_score IS NOT NULL
              AND e.home_score != e.away_score
              AND wp.source IN ('kalshi', 'polymarket')
              AND wp.home_win_probability IS NOT NULL
              AND wp.home_win_probability > 0
              AND wp.home_win_probability < 1
              {_KALSHI_PROP_FILTER}
            ORDER BY wp.event_id, wp.source, wp.captured_at DESC
        )
        SELECT
            wc.event_id, wc.source AS pm_source,
            wc.home_win_probability AS pm_prob,
            COALESCE(e.closing_home_probability, e.opening_home_probability) AS odds_prob,
            (e.home_score > e.away_score) AS home_won,
            s.key AS sport
        FROM wp_closing wc
        JOIN events e ON e.id = wc.event_id
        JOIN sports s ON s.id = e.sport_id
        WHERE COALESCE(e.closing_home_probability, e.opening_home_probability) IS NOT NULL
          AND COALESCE(e.closing_home_probability, e.opening_home_probability) > 0
          AND COALESCE(e.closing_home_probability, e.opening_home_probability) < 1
        ORDER BY wc.source, s.key
    """)
    result = await db.execute(sql)
    rows = result.all()

    by_src: dict[str, dict[str, dict]] = {}
    for r in rows:
        src = r.pm_source
        sport = r.sport
        if src not in by_src:
            by_src[src] = {}
        if sport not in by_src[src]:
            by_src[src][sport] = {
                "pm_probs": [], "pm_outcomes": [],
                "odds_probs": [], "odds_outcomes": [],
            }
        won = bool(r.home_won)
        by_src[src][sport]["pm_probs"].append(float(r.pm_prob))
        by_src[src][sport]["pm_outcomes"].append(won)
        by_src[src][sport]["odds_probs"].append(float(r.odds_prob))
        by_src[src][sport]["odds_outcomes"].append(won)

    pairs = []
    for pm_source, sports_data in sorted(by_src.items()):
        all_pm_probs: list[float] = []
        all_pm_outcomes: list[bool] = []
        all_odds_probs: list[float] = []
        all_odds_outcomes: list[bool] = []
        by_sport: list[dict] = []

        for sport, data in sorted(sports_data.items()):
            n = len(data["pm_probs"])
            if n < 10:
                continue
            all_pm_probs.extend(data["pm_probs"])
            all_pm_outcomes.extend(data["pm_outcomes"])
            all_odds_probs.extend(data["odds_probs"])
            all_odds_outcomes.extend(data["odds_outcomes"])
            mce_pm = _compute_mce(data["pm_probs"], data["pm_outcomes"])
            mce_odds = _compute_mce(data["odds_probs"], data["odds_outcomes"])
            if mce_pm is not None and mce_odds is not None:
                by_sport.append({
                    "category": sport,
                    f"{pm_source}_n": n,
                    "odds_api_n": n,
                    f"mce_{pm_source}": mce_pm,
                    "mce_odds_api": mce_odds,
                })

        total = len(all_pm_probs)
        if total >= _MIN_SHARED:
            mce_pm = _compute_mce(all_pm_probs, all_pm_outcomes)
            mce_odds = _compute_mce(all_odds_probs, all_odds_outcomes)
            if mce_pm is not None and mce_odds is not None:
                winner = pm_source if mce_pm < mce_odds else "odds_api" if mce_odds < mce_pm else "tie"
                pairs.append({
                    "source_a": pm_source,
                    "source_b": "odds_api",
                    "shared_markets": total,
                    "mce_a": mce_pm,
                    "mce_b": mce_odds,
                    "winner": winner,
                    "advantage_pp": round(abs(mce_pm - mce_odds), 2),
                    "by_category": [s for s in by_sport if s.get(f"{pm_source}_n", 0) >= 20],
                })
    return pairs


async def _compute_fair_fight_comparison():
    """Compute fair-fight comparison and store in Redis."""
    from app.tasks.base import get_task_session
    from app.tasks.redis_state import get_redis_client

    async with get_task_session() as db:
        try:
            futures_pairs = await _query_futures_fair_fight_impl(db)
        except Exception:
            logger.exception("fair-fight precompute: futures query failed")
            futures_pairs = []

        try:
            sports_pairs = await _query_sports_fair_fight_impl(db)
        except Exception:
            logger.exception("fair-fight precompute: sports query failed")
            sports_pairs = []

    response = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "methodology": (
            "Paired MCE comparison: for each source pair, only markets/events "
            "covered by BOTH sources are evaluated. This controls for difficulty "
            "— a source covering only easy markets cannot look artificially accurate."
        ),
        "min_shared_threshold": _MIN_SHARED,
        "pairs": futures_pairs + sports_pairs,
    }

    rc = get_redis_client()
    rc.set("bainluck:calibration:fair_fight", json.dumps(response), ex=_CACHE_TTL)
    logger.info("Cached fair-fight comparison in Redis")
    return {"status": "ok", "pairs": len(futures_pairs) + len(sports_pairs)}


async def _snapshot_coverage_metrics():
    """Daily snapshot of coverage metrics for tracking progress over time.

    Stores one row per day in a Redis sorted set keyed by date. Each row
    captures opening_probability, is_winner, and calibration_probability
    coverage per source and time window. This lets us answer "is coverage
    improving?" without re-running heavy queries.
    """
    from app.tasks.base import get_task_session
    from app.tasks.redis_state import get_redis_client

    stats = {"snapshots": 0, "errors": []}

    try:
        async with get_task_session() as session:
            result = await session.execute(
                text("""
                    SELECT
                        fm.source,
                        CASE
                            WHEN fm.resolution_date >= NOW() - INTERVAL '7 days' THEN '7d'
                            WHEN fm.resolution_date >= NOW() - INTERVAL '30 days' THEN '30d'
                            ELSE '90d+'
                        END AS age_bucket,
                        s.key AS league,
                        COUNT(*) AS total_resolved,
                        COUNT(fo.opening_probability) AS has_opening,
                        COUNT(fo.calibration_probability) AS has_cal_prob,
                        COUNT(CASE WHEN fo.is_winner IS NOT NULL THEN 1 END) AS has_winner,
                        AVG(CASE WHEN snap_counts.cnt IS NOT NULL THEN snap_counts.cnt ELSE 0 END)::int AS avg_snapshots
                    FROM futures_outcomes fo
                    JOIN futures_markets fm ON fo.market_id = fm.id
                    LEFT JOIN sports s ON s.id = fm.sport_id
                    LEFT JOIN LATERAL (
                        SELECT COUNT(*) AS cnt
                        FROM futures_odds_snapshots fos
                        WHERE fos.outcome_id = fo.id
                    ) snap_counts ON true
                    WHERE fm.status = 'resolved'
                      AND fm.resolution_date IS NOT NULL
                    GROUP BY fm.source, age_bucket, s.key
                    ORDER BY fm.source, age_bucket, total_resolved DESC
                """)
            )
            rows = result.fetchall()

            snapshot = {
                "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                "computed_at": datetime.now(timezone.utc).isoformat(),
                "by_source_age_league": [
                    {
                        "source": r.source,
                        "age": r.age_bucket,
                        "league": r.league or "unknown",
                        "total": r.total_resolved,
                        "has_opening": r.has_opening,
                        "has_cal_prob": r.has_cal_prob,
                        "has_winner": r.has_winner,
                        "avg_snapshots": r.avg_snapshots,
                    }
                    for r in rows
                ],
                "totals": {},
            }

            from collections import defaultdict
            by_source = defaultdict(lambda: {"total": 0, "opening": 0, "cal_prob": 0, "winner": 0})
            for r in rows:
                by_source[r.source]["total"] += r.total_resolved
                by_source[r.source]["opening"] += r.has_opening
                by_source[r.source]["cal_prob"] += r.has_cal_prob
                by_source[r.source]["winner"] += r.has_winner

            snapshot["totals"] = {
                src: {
                    "total": s["total"],
                    "opening_pct": round(100 * s["opening"] / max(s["total"], 1), 1),
                    "cal_prob_pct": round(100 * s["cal_prob"] / max(s["total"], 1), 1),
                    "winner_pct": round(100 * s["winner"] / max(s["total"], 1), 1),
                }
                for src, s in by_source.items()
            }

            rc = get_redis_client()
            date_key = snapshot["date"]
            rc.hset("bainluck:coverage_snapshots", date_key, json.dumps(snapshot))
            rc.expire("bainluck:coverage_snapshots", 90 * 86400)

            stats["snapshots"] = len(rows)
            logger.info(
                "Coverage snapshot: %s — %s",
                date_key,
                {src: f'{s["cal_prob_pct"]}% cal_prob' for src, s in snapshot["totals"].items()},
            )

            # Also precompute the backfill-winners/status cache.
            # This query is too heavy for the web dyno's 30s timeout
            # but runs fine on the background worker.
            try:
                status_result = await session.execute(
                    text("""
                        WITH market_status AS (
                            SELECT fm.id, fm.source,
                                BOOL_OR(fo.is_winner) AS has_winner,
                                MAX(fo.current_probability) AS max_prob,
                                BOOL_AND(fo.calibration_probability IS NULL
                                         AND fo.opening_probability IS NULL) AS all_cal_null
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
                                  AND NOT (all_cal_null AND source != 'datagolf')
                                  AND (max_prob IS NULL OR max_prob > 0.10)
                            ) AS needs_backfill,
                            COUNT(*) FILTER (
                                WHERE all_cal_null AND source != 'datagolf'
                            ) AS untradeable_excluded
                        FROM market_status
                        GROUP BY source
                    """)
                )
                winner_status = {
                    "sources": [
                        {"source": r.source, "resolved": r.resolved_markets,
                         "has_winner": r.has_winner, "needs_backfill": r.needs_backfill,
                         "untradeable_excluded": r.untradeable_excluded}
                        for r in status_result.all()
                    ],
                    "precomputed_at": datetime.now(timezone.utc).isoformat(),
                }
                rc.setex(
                    "bainluck:backfill_winners_status",
                    1800,
                    json.dumps(winner_status, default=str),
                )
                logger.info("Precomputed backfill-winners/status cache")
            except Exception as ws_err:
                logger.warning("Failed to precompute winner status: %s", ws_err)

    except Exception as e:
        stats["errors"].append(str(e)[:200])
        logger.error("Coverage snapshot error: %s", e)

    return stats
