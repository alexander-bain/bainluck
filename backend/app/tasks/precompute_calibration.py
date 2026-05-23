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
                    SELECT DISTINCT ON (eo.outcome_id)
                        eo.outcome_id,
                        eo.is_winner,
                        eo.source,
                        eo.category,
                        fos.probability AS horizon_prob
                    FROM eligible_outcomes eo
                    JOIN futures_odds_snapshots fos ON fos.outcome_id = eo.outcome_id
                    WHERE fos.captured_at <= {cutoff_expr}
                      AND fos.probability > 0 AND fos.probability < 1
                    ORDER BY eo.outcome_id, fos.captured_at DESC
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
