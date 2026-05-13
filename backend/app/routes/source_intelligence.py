"""Source Intelligence endpoint — public, cached for 6 hours.

Analyzes cross-source probability disagreements for completed sports events
and determines which source was closest to the actual outcome.

Only considers "well-covered" events: those with 20+ snapshots from at
least 2 sources during live play. Events with thin coverage are excluded
entirely — if a Tier 1 event lacks dense multi-source data, that's a
pipeline bug to fix, not sparse data to analyze.
"""

import json
import logging
import time
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import get_db

logger = logging.getLogger(__name__)

router = APIRouter()

_cache: dict = {"data": None, "timestamp": 0}
CACHE_TTL = 21600  # 6 hours

_RECENCY = "e.commence_time > NOW() - INTERVAL '3 months'"

_BASE_FILTER = f"""
    e.status IN ('completed', 'closed')
    AND e.home_score IS NOT NULL AND e.away_score IS NOT NULL
    AND e.home_score != e.away_score
    AND {_RECENCY}
"""

# Minimum snapshots per source per event to consider the source "present".
# Below this threshold, the data is too thin to draw conclusions from.
MIN_SNAPS = 20

# CTE fragment: for each (event, source) pair, count live-game snapshots
# and take the closing probability. Only sources with >= MIN_SNAPS qualify.
_RICH_SOURCES_CTE = f"""
    rich_sources AS (
        SELECT
            wp.event_id,
            wp.source,
            COUNT(*) AS snap_count
        FROM win_prob_snapshots wp
        JOIN events e ON e.id = wp.event_id
        WHERE {_BASE_FILTER}
          AND wp.home_win_probability IS NOT NULL
          AND wp.home_win_probability > 0
          AND wp.home_win_probability < 1
          AND wp.captured_at >= e.commence_time
          AND wp.captured_at <= COALESCE(
              e.completed_at,
              e.commence_time + INTERVAL '4 hours'
          )
        GROUP BY wp.event_id, wp.source
        HAVING COUNT(*) >= {MIN_SNAPS}
    ),
    rich_events AS (
        SELECT event_id
        FROM rich_sources
        GROUP BY event_id
        HAVING COUNT(DISTINCT source) >= 2
    )
"""


# Shared CTE for betting closing lines.
# win_probability_sources->'betting' can be a plain float or a dict
# with a "value" key. Compute the probability once in a subquery,
# then filter in the outer query.
_BETTING_CTE = """
    betting_closing AS (
        SELECT event_id, home_win_probability
        FROM (
            SELECT re.event_id,
                CASE
                    WHEN jsonb_typeof(e.win_probability_sources->'betting') = 'number'
                    THEN (e.win_probability_sources->>'betting')::float
                    WHEN jsonb_typeof(e.win_probability_sources->'betting') = 'object'
                    THEN (e.win_probability_sources->'betting'->>'value')::float
                END AS home_win_probability
            FROM rich_events re
            JOIN events e ON e.id = re.event_id
            WHERE e.win_probability_sources->'betting' IS NOT NULL
        ) sub
        WHERE home_win_probability IS NOT NULL
          AND home_win_probability > 0
          AND home_win_probability < 1
    )
"""


async def _set_timeout(db: AsyncSession) -> None:
    await db.execute(text("SET LOCAL statement_timeout = '25s'"))


async def _query_coverage(db: AsyncSession) -> dict:
    """Query 1: Source coverage — events with rich multi-source data."""

    by_source_sql = text(f"""
        WITH {_RICH_SOURCES_CTE}
        SELECT
            s.key AS sport,
            COUNT(DISTINCT e.id) AS total,
            COUNT(DISTINCT e.id) FILTER (
                WHERE e.win_probability_sources->'betting' IS NOT NULL
            ) AS betting,
            COUNT(DISTINCT e.id) FILTER (WHERE rs.source = 'espn') AS espn,
            COUNT(DISTINCT e.id) FILTER (WHERE rs.source = 'stat_model') AS stat_model,
            COUNT(DISTINCT e.id) FILTER (WHERE rs.source = 'kalshi') AS kalshi,
            COUNT(DISTINCT e.id) FILTER (WHERE rs.source = 'polymarket') AS polymarket,
            COUNT(DISTINCT e.id) FILTER (WHERE rs.source = 'mlb') AS mlb
        FROM rich_events re
        JOIN events e ON e.id = re.event_id
        JOIN sports s ON s.id = e.sport_id
        LEFT JOIN rich_sources rs ON rs.event_id = e.id
        GROUP BY s.key
        ORDER BY COUNT(DISTINCT e.id) DESC
    """)

    overlap_sql = text(f"""
        WITH {_RICH_SOURCES_CTE}
        SELECT source_count AS sources, COUNT(*) AS events
        FROM (
            SELECT re.event_id,
                COUNT(DISTINCT rs.source)
                + CASE WHEN e.win_probability_sources->'betting' IS NOT NULL THEN 1 ELSE 0 END
                AS source_count
            FROM rich_events re
            JOIN events e ON e.id = re.event_id
            LEFT JOIN rich_sources rs ON rs.event_id = re.event_id
            GROUP BY re.event_id, e.opening_home_probability
        ) sub
        GROUP BY source_count
        ORDER BY source_count
    """)

    by_source_result = await db.execute(by_source_sql)
    overlap_result = await db.execute(overlap_sql)

    by_sport = []
    total_events = 0
    for r in by_source_result.all():
        total_events += r.total
        by_sport.append({
            "sport": r.sport, "total": r.total,
            "betting": r.betting, "espn": r.espn,
            "stat_model": r.stat_model, "kalshi": r.kalshi,
            "polymarket": r.polymarket, "mlb": r.mlb,
        })

    overlap = [{"sources": r.sources, "events": r.events}
               for r in overlap_result.all()]
    multi = sum(o["events"] for o in overlap if o["sources"] >= 2)

    return {
        "total_events": total_events,
        "multi_source_events": multi,
        "by_source_count": overlap,
        "by_sport": by_sport,
    }


async def _query_source_accuracy(db: AsyncSession) -> list:
    """Query 2: Per-source closing accuracy — only well-covered events."""

    sql = text(f"""
        WITH {_RICH_SOURCES_CTE},
        wp_closing AS (
            SELECT DISTINCT ON (wp.event_id, wp.source)
                wp.event_id, wp.source, wp.home_win_probability
            FROM win_prob_snapshots wp
            JOIN rich_sources rs
                ON rs.event_id = wp.event_id AND rs.source = wp.source
            JOIN rich_events re ON re.event_id = wp.event_id
            WHERE wp.home_win_probability IS NOT NULL
              AND wp.home_win_probability > 0
              AND wp.home_win_probability < 1
            ORDER BY wp.event_id, wp.source, wp.captured_at DESC
        ),
        {_BETTING_CTE},
        all_closing AS (
            SELECT event_id, source, home_win_probability FROM wp_closing
            UNION ALL
            SELECT event_id, 'betting', home_win_probability FROM betting_closing
        )
        SELECT
            c.source,
            LEAST(FLOOR(c.home_win_probability * 10)::int, 9) AS idx,
            COUNT(*) AS n,
            AVG(c.home_win_probability::float) AS avg_prob,
            SUM(CASE WHEN e.home_score > e.away_score THEN 1 ELSE 0 END) AS winners,
            AVG(ABS(c.home_win_probability::float
                - CASE WHEN e.home_score > e.away_score THEN 1.0 ELSE 0.0 END)) AS mae,
            AVG((c.home_win_probability::float
                - CASE WHEN e.home_score > e.away_score THEN 1.0 ELSE 0.0 END)^2) AS brier,
            VARIANCE((c.home_win_probability::float
                - CASE WHEN e.home_score > e.away_score THEN 1.0 ELSE 0.0 END)^2) AS brier_var
        FROM all_closing c
        JOIN events e ON e.id = c.event_id
        GROUP BY c.source, idx
        ORDER BY c.source, idx
    """)

    result = await db.execute(sql)
    rows = result.all()

    import math

    sources: dict = {}
    for r in rows:
        src = r.source
        if src not in sources:
            sources[src] = {"source": src, "observations": 0,
                            "total_brier_num": 0.0, "total_mae_num": 0.0,
                            "sq_errs": [], "buckets": []}
        sources[src]["observations"] += r.n
        sources[src]["total_brier_num"] += float(r.brier) * r.n
        sources[src]["total_mae_num"] += float(r.mae) * r.n
        # Collect per-bucket variance for pooled CI
        if r.brier_var is not None and r.n > 1:
            sources[src]["sq_errs"].append((r.n, float(r.brier), float(r.brier_var)))
        sources[src]["buckets"].append({
            "idx": r.idx, "n": r.n,
            "avg_prob": round(float(r.avg_prob), 4),
            "actual": round(r.winners / r.n, 4) if r.n else 0,
        })

    out = []
    for s in sources.values():
        obs = s["observations"]
        brier = s["total_brier_num"] / obs if obs else 0
        # Pooled standard error: SE = sqrt(pooled_variance / n)
        # Pooled variance = weighted average of per-bucket variances
        pooled_var = 0.0
        total_n = 0
        for n, _mean, var in s["sq_errs"]:
            pooled_var += var * (n - 1)
            total_n += n - 1
        se = math.sqrt(pooled_var / total_n / obs) if total_n > 0 and obs > 0 else 0
        out.append({
            "source": s["source"],
            "observations": obs,
            "brier": round(brier, 4),
            "brier_ci": round(1.96 * se, 4),
            "mae": round(s["total_mae_num"] / obs, 4) if obs else 0,
            "buckets": s["buckets"],
        })
    return sorted(out, key=lambda x: x["brier"])


async def _query_disagreements(db: AsyncSession) -> dict:
    """Queries 3+4: Pairwise disagreement — only well-covered events."""

    sql = text(f"""
        WITH {_RICH_SOURCES_CTE},
        wp_closing AS (
            SELECT DISTINCT ON (wp.event_id, wp.source)
                wp.event_id, wp.source, wp.home_win_probability
            FROM win_prob_snapshots wp
            JOIN rich_sources rs
                ON rs.event_id = wp.event_id AND rs.source = wp.source
            JOIN rich_events re ON re.event_id = wp.event_id
            WHERE wp.home_win_probability IS NOT NULL
              AND wp.home_win_probability > 0
              AND wp.home_win_probability < 1
            ORDER BY wp.event_id, wp.source, wp.captured_at DESC
        ),
        {_BETTING_CTE},
        closing AS (
            SELECT event_id, source, home_win_probability FROM wp_closing
            UNION ALL
            SELECT event_id, 'betting', home_win_probability FROM betting_closing
        ),
        pairs AS (
            SELECT
                c1.event_id,
                c1.source AS source_a,
                c2.source AS source_b,
                c1.home_win_probability AS prob_a,
                c2.home_win_probability AS prob_b,
                ABS(c1.home_win_probability - c2.home_win_probability) AS divergence
            FROM closing c1
            JOIN closing c2
                ON c1.event_id = c2.event_id
                AND c1.source < c2.source
        ),
        with_outcome AS (
            SELECT
                p.*,
                (e.home_score > e.away_score) AS home_won,
                s.key AS sport
            FROM pairs p
            JOIN events e ON e.id = p.event_id
            JOIN sports s ON s.id = e.sport_id
        )
        SELECT
            source_a, source_b, sport,
            COUNT(*) AS comparisons,
            COUNT(*) FILTER (WHERE divergence > 0.05) AS disagree_5pp,
            COUNT(*) FILTER (WHERE divergence > 0.10) AS disagree_10pp,
            COUNT(*) FILTER (WHERE divergence > 0.20) AS disagree_20pp,
            AVG(divergence) FILTER (WHERE divergence > 0.05) AS avg_divergence,
            SUM(CASE WHEN divergence > 0.05
                      AND ABS(prob_a - CASE WHEN home_won THEN 1.0 ELSE 0.0 END)
                        < ABS(prob_b - CASE WHEN home_won THEN 1.0 ELSE 0.0 END)
                 THEN 1 ELSE 0 END) AS a_closer,
            SUM(CASE WHEN divergence > 0.05
                      AND ABS(prob_b - CASE WHEN home_won THEN 1.0 ELSE 0.0 END)
                        < ABS(prob_a - CASE WHEN home_won THEN 1.0 ELSE 0.0 END)
                 THEN 1 ELSE 0 END) AS b_closer
        FROM with_outcome
        GROUP BY source_a, source_b, sport
        ORDER BY source_a, source_b, sport
    """)

    result = await db.execute(sql)
    rows = result.all()

    total_comparisons = 0
    total_5pp = 0
    total_10pp = 0
    total_20pp = 0

    sport_agg: dict = {}
    pairwise: dict = {}

    for r in rows:
        total_comparisons += r.comparisons
        total_5pp += r.disagree_5pp
        total_10pp += r.disagree_10pp
        total_20pp += r.disagree_20pp

        if r.sport not in sport_agg:
            sport_agg[r.sport] = {"sport": r.sport, "comparisons": 0, "disagree_5pp": 0}
        sport_agg[r.sport]["comparisons"] += r.comparisons
        sport_agg[r.sport]["disagree_5pp"] += r.disagree_5pp

        pair_key = f"{r.source_a}|{r.source_b}"
        if pair_key not in pairwise:
            pairwise[pair_key] = {
                "source_a": r.source_a, "source_b": r.source_b,
                "count": 0, "divergence_sum": 0.0,
                "a_closer": 0, "b_closer": 0,
                "by_phase": {}, "by_sport": {},
            }
        pw = pairwise[pair_key]
        pw["count"] += r.disagree_5pp
        if r.avg_divergence and r.disagree_5pp:
            pw["divergence_sum"] += float(r.avg_divergence) * r.disagree_5pp
        pw["a_closer"] += r.a_closer
        pw["b_closer"] += r.b_closer

        if r.sport not in pw["by_sport"]:
            pw["by_sport"][r.sport] = {"comparisons": 0, "a_closer": 0, "b_closer": 0}
        pw["by_sport"][r.sport]["comparisons"] += r.disagree_5pp
        pw["by_sport"][r.sport]["a_closer"] += r.a_closer
        pw["by_sport"][r.sport]["b_closer"] += r.b_closer

    pairwise_list = []
    for pw in pairwise.values():
        count = pw["count"]
        if count < 10:
            continue
        total_closer = pw["a_closer"] + pw["b_closer"]
        pairwise_list.append({
            "source_a": pw["source_a"],
            "source_b": pw["source_b"],
            "count": count,
            "avg_divergence": round(pw["divergence_sum"] / count, 4) if count else 0,
            "a_closer_pct": round(pw["a_closer"] / total_closer, 4) if total_closer else 0.5,
            "by_phase": {},
            "by_sport": {
                sport: {
                    "comparisons": v["comparisons"],
                    "a_closer_pct": round(
                        v["a_closer"] / (v["a_closer"] + v["b_closer"]), 4
                    ) if (v["a_closer"] + v["b_closer"]) else 0.5,
                }
                for sport, v in pw["by_sport"].items()
                if v["comparisons"] >= 10
            },
        })

    by_sport = []
    for s in sport_agg.values():
        if s["comparisons"] >= 20:
            by_sport.append({
                "sport": s["sport"],
                "comparisons": s["comparisons"],
                "rate_5pp": round(s["disagree_5pp"] / s["comparisons"], 4)
                if s["comparisons"] else 0,
            })
    by_sport.sort(key=lambda x: x["rate_5pp"], reverse=True)

    return {
        "total_comparisons": total_comparisons,
        "rate_5pp": round(total_5pp / total_comparisons, 4) if total_comparisons else 0,
        "rate_10pp": round(total_10pp / total_comparisons, 4) if total_comparisons else 0,
        "rate_20pp": round(total_20pp / total_comparisons, 4) if total_comparisons else 0,
        "by_sport": by_sport,
        "pairwise": sorted(pairwise_list,
                           key=lambda x: x["count"], reverse=True),
    }


async def _query_case_studies(db: AsyncSession) -> list:
    """Query 5: Top sustained disagreements from well-covered events.

    Uses median probability per source (robust to transient spikes).
    Only considers live-game snapshots with 20+ readings per source.
    """

    peak_sql = text(f"""
        WITH {_RICH_SOURCES_CTE},
        live_snaps AS (
            SELECT
                wp.event_id, wp.source, wp.home_win_probability
            FROM win_prob_snapshots wp
            JOIN rich_sources rs
                ON rs.event_id = wp.event_id AND rs.source = wp.source
            JOIN rich_events re ON re.event_id = wp.event_id
            JOIN events e ON e.id = wp.event_id
            WHERE wp.home_win_probability IS NOT NULL
              AND wp.home_win_probability > 0.05
              AND wp.home_win_probability < 0.95
              AND wp.captured_at >= e.commence_time
              AND wp.captured_at <= COALESCE(
                  e.completed_at,
                  e.commence_time + INTERVAL '4 hours'
              )
        ),
        source_medians AS (
            SELECT
                event_id, source,
                PERCENTILE_CONT(0.5) WITHIN GROUP (
                    ORDER BY home_win_probability
                ) AS median_prob,
                COUNT(*) AS snap_count
            FROM live_snaps
            GROUP BY event_id, source
        ),
        event_divergence AS (
            SELECT
                s1.event_id,
                MAX(ABS(s1.median_prob - s2.median_prob)) AS max_div,
                COUNT(DISTINCT s1.source) + COUNT(DISTINCT s2.source) AS pair_sources,
                MAX(LEAST(s1.snap_count, s2.snap_count)) AS min_pair_snaps
            FROM source_medians s1
            JOIN source_medians s2
                ON s1.event_id = s2.event_id
                AND s1.source < s2.source
            GROUP BY s1.event_id
            HAVING MAX(ABS(s1.median_prob - s2.median_prob)) > 0.05
        )
        SELECT
            ed.event_id,
            ed.max_div,
            ed.min_pair_snaps,
            e.home_team_name,
            e.away_team_name,
            s.key AS sport,
            e.home_score,
            e.away_score,
            e.commence_time,
            e.completed_at
        FROM event_divergence ed
        JOIN events e ON e.id = ed.event_id
        JOIN sports s ON s.id = e.sport_id
        ORDER BY ed.max_div DESC
        LIMIT 10
    """)

    peak_result = await db.execute(peak_sql)
    peaks = peak_result.all()

    case_studies = []
    for p in peaks:
        if len(case_studies) >= 5:
            break

        game_end = p.completed_at or (
            p.commence_time + timedelta(hours=4)
        ) if p.commence_time else None
        if not p.commence_time or not game_end:
            continue

        ts_sql = text("""
            SELECT source, captured_at, home_win_probability
            FROM win_prob_snapshots
            WHERE event_id = :eid
              AND home_win_probability IS NOT NULL
              AND captured_at >= :start
              AND captured_at <= :end
            ORDER BY captured_at
        """)
        ts_result = await db.execute(ts_sql, {
            "eid": p.event_id,
            "start": p.commence_time,
            "end": game_end,
        })
        ts_rows = ts_result.all()

        series: dict = {}
        for tr in ts_rows:
            src = tr.source
            if src not in series:
                series[src] = []
            series[src].append({
                "t": tr.captured_at.isoformat(),
                "p": round(float(tr.home_win_probability), 4),
            })

        # Only keep sources with rich data
        series = {s: pts for s, pts in series.items() if len(pts) >= MIN_SNAPS}
        if len(series) < 2:
            continue

        case_studies.append({
            "event_id": p.event_id,
            "home_team": p.home_team_name,
            "away_team": p.away_team_name,
            "sport": p.sport,
            "score": f"{p.home_score}-{p.away_score}",
            "home_won": p.home_score > p.away_score,
            "max_divergence": round(float(p.max_div), 4),
            "date": p.commence_time.isoformat() if p.commence_time else None,
            "series": series,
        })

    return case_studies


@router.get("/source-intelligence/oscillation-audit")
async def oscillation_audit(db: AsyncSession = Depends(get_db)):
    """Find ALL events with stat_model oscillation — reverse matching eval.

    Returns every event where stat_model stddev > 0.25, with game_state
    data showing what scores were fed, so we can trace bad ESPN matches.
    """
    await _set_timeout(db)

    # Find all oscillating events (no time limit — full history)
    osc_sql = text("""
        SELECT
            wp.event_id,
            e.home_team_name,
            e.away_team_name,
            s.key AS sport,
            e.espn_id,
            e.home_score,
            e.away_score,
            e.commence_time::text,
            COUNT(*) AS snap_count,
            ROUND(STDDEV(wp.home_win_probability::float)::numeric, 4) AS std_dev,
            ROUND(MIN(wp.home_win_probability::float)::numeric, 4) AS min_prob,
            ROUND(MAX(wp.home_win_probability::float)::numeric, 4) AS max_prob
        FROM win_prob_snapshots wp
        JOIN events e ON e.id = wp.event_id
        JOIN sports s ON s.id = e.sport_id
        WHERE wp.source = 'stat_model'
          AND e.status IN ('completed', 'closed')
          AND wp.captured_at >= e.commence_time
          AND wp.home_win_probability IS NOT NULL
        GROUP BY wp.event_id, e.home_team_name, e.away_team_name, s.key,
                 e.espn_id, e.home_score, e.away_score, e.commence_time
        HAVING STDDEV(wp.home_win_probability::float) > 0.25
           AND COUNT(*) >= 10
        ORDER BY STDDEV(wp.home_win_probability::float) DESC
    """)
    result = await db.execute(osc_sql)
    rows = result.all()

    events = []
    for r in rows:
        # For each event, get a sample of game_state to show score progression
        gs_sql = text("""
            SELECT
                home_win_probability::float,
                game_state->>'home_score' AS gs_home,
                game_state->>'away_score' AS gs_away,
                game_state->>'clock' AS gs_clock,
                game_state->>'period' AS gs_period,
                game_state->>'time_source' AS gs_time_src
            FROM win_prob_snapshots
            WHERE event_id = :eid AND source = 'stat_model'
              AND game_state IS NOT NULL
            ORDER BY captured_at
        """)
        gs_result = await db.execute(gs_sql, {"eid": r.event_id})
        gs_rows = gs_result.all()

        # Detect score-backwards jumps
        prev_h, prev_a = None, None
        backwards = 0
        distinct_score_pairs = set()
        for gr in gs_rows:
            h, a = gr.gs_home, gr.gs_away
            if h is not None and a is not None:
                distinct_score_pairs.add((h, a))
                if prev_h is not None:
                    if int(h) < int(prev_h) or int(a) < int(prev_a):
                        backwards += 1
                prev_h, prev_a = h, a

        events.append({
            "event_id": r.event_id,
            "home_team": r.home_team_name,
            "away_team": r.away_team_name,
            "sport": r.sport,
            "espn_id": r.espn_id,
            "final_score": f"{r.home_score}-{r.away_score}",
            "date": r.commence_time[:10] if r.commence_time else None,
            "snap_count": r.snap_count,
            "std_dev": float(r.std_dev),
            "range": [float(r.min_prob), float(r.max_prob)],
            "score_backwards_jumps": backwards,
            "distinct_score_pairs": len(distinct_score_pairs),
            "sample_states": [
                {
                    "prob": round(gr[0], 3),
                    "score": f"{gr.gs_home}-{gr.gs_away}",
                    "clock": gr.gs_clock,
                    "period": gr.gs_period,
                    "time_src": gr.gs_time_src,
                }
                for gr in gs_rows[:8]
            ],
        })

    # Summary stats
    null_espn = sum(1 for e in events if e["espn_id"] is None)
    has_backwards = sum(1 for e in events if e["score_backwards_jumps"] > 0)
    sports = {}
    for e in events:
        sports[e["sport"]] = sports.get(e["sport"], 0) + 1

    return {
        "total_oscillating": len(events),
        "espn_id_null": null_espn,
        "espn_id_set": len(events) - null_espn,
        "with_score_backwards": has_backwards,
        "by_sport": sports,
        "events": events,
    }


@router.post("/source-intelligence/cleanup-oscillation")
async def cleanup_oscillation(
    secret: str = "",
    dry_run: bool = True,
    db: AsyncSession = Depends(get_db),
):
    """Delete contaminated stat_model/espn snapshots and fix ESPN ID collisions.

    Pass ?dry_run=false&secret=ADMIN_TOKEN to execute.
    Default is dry_run=true (report only).
    """
    import os
    expected = os.getenv("ADMIN_TOKEN") or os.getenv("ADMIN_SECRET")
    if not expected or secret != expected:
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    await _set_timeout(db)

    results: dict = {
        "dry_run": dry_run,
        "oscillating_events": 0,
        "snapshots_deleted": 0,
        "espn_ids_cleared": 0,
        "espn_id_collisions_fixed": 0,
        "wps_cleaned": 0,
        "details": [],
    }

    # Step 1: Find all oscillating events (stat_model stddev > 0.25, 10+ snaps)
    osc_sql = text("""
        SELECT wp.event_id, STDDEV(wp.home_win_probability::float) AS sd
        FROM win_prob_snapshots wp
        JOIN events e ON e.id = wp.event_id
        WHERE wp.source = 'stat_model'
          AND e.status IN ('completed', 'closed')
          AND wp.captured_at >= e.commence_time
          AND wp.home_win_probability IS NOT NULL
        GROUP BY wp.event_id
        HAVING STDDEV(wp.home_win_probability::float) > 0.25
           AND COUNT(*) >= 10
    """)
    osc_result = await db.execute(osc_sql)
    osc_event_ids = [r.event_id for r in osc_result.all()]
    results["oscillating_events"] = len(osc_event_ids)

    if osc_event_ids:
        # Step 2: Delete stat_model and espn snapshots for these events
        count_sql = text("""
            SELECT COUNT(*) FROM win_prob_snapshots
            WHERE event_id = ANY(:ids)
              AND source IN ('stat_model', 'espn')
        """)
        count_result = await db.execute(count_sql, {"ids": osc_event_ids})
        snap_count = count_result.scalar()
        results["snapshots_deleted"] = snap_count

        if not dry_run:
            await db.execute(text("""
                DELETE FROM win_prob_snapshots
                WHERE event_id = ANY(:ids)
                  AND source IN ('stat_model', 'espn')
            """), {"ids": osc_event_ids})

        # Step 3: Clean stat_model/espn from win_probability_sources JSONB
        wps_sql = text("""
            SELECT id, win_probability_sources FROM events
            WHERE id = ANY(:ids)
              AND win_probability_sources IS NOT NULL
        """)
        wps_result = await db.execute(wps_sql, {"ids": osc_event_ids})
        wps_cleaned = 0
        for row in wps_result.all():
            wps = dict(row.win_probability_sources or {})
            changed = False
            for key in ("stat_model", "espn"):
                if key in wps:
                    del wps[key]
                    changed = True
            if changed:
                wps_cleaned += 1
                if not dry_run:
                    await db.execute(text("""
                        UPDATE events SET win_probability_sources = :wps
                        WHERE id = :eid
                    """), {"wps": json.dumps(wps), "eid": row.id})
        results["wps_cleaned"] = wps_cleaned

    # Step 4: Fix ESPN ID collisions — find espn_ids assigned to 2+ events
    collision_sql = text("""
        SELECT espn_id, COUNT(*) AS cnt,
               ARRAY_AGG(id ORDER BY id) AS event_ids
        FROM events
        WHERE espn_id IS NOT NULL
          AND status IN ('completed', 'closed', 'live', 'scheduled')
        GROUP BY espn_id
        HAVING COUNT(*) > 1
    """)
    collision_result = await db.execute(collision_sql)
    collisions = collision_result.all()

    for row in collisions:
        espn_id, cnt, event_ids_list = row.espn_id, row.cnt, row.event_ids
        results["espn_id_collisions_fixed"] += 1
        results["espn_ids_cleared"] += cnt

        results["details"].append({
            "espn_id": espn_id,
            "event_ids": event_ids_list,
            "action": "cleared espn_id on all — will re-match correctly",
        })

        if not dry_run:
            await db.execute(text("""
                UPDATE events SET espn_id = NULL
                WHERE espn_id = :eid
            """), {"eid": espn_id})

    if not dry_run:
        await db.commit()

    return results


@router.get("/source-intelligence")
async def source_intelligence(
    refresh: bool = False,
    db: AsyncSession = Depends(get_db),
):
    """Cross-source disagreement analysis for the /source-intelligence page."""

    now = time.time()
    if not refresh and _cache["data"] and (now - _cache["timestamp"]) < CACHE_TTL:
        return _cache["data"]

    await _set_timeout(db)

    try:
        coverage = await _query_coverage(db)
    except Exception:
        logger.exception("source-intelligence: coverage query failed")
        coverage = {"total_events": 0, "multi_source_events": 0,
                     "by_source_count": [], "by_sport": []}

    try:
        accuracy = await _query_source_accuracy(db)
    except Exception:
        logger.exception("source-intelligence: accuracy query failed")
        accuracy = []

    try:
        disagreements = await _query_disagreements(db)
    except Exception:
        logger.exception("source-intelligence: disagreements query failed")
        disagreements = {"total_comparisons": 0, "rate_5pp": 0,
                         "rate_10pp": 0, "rate_20pp": 0,
                         "by_sport": [], "pairwise": []}

    try:
        case_studies = await _query_case_studies(db)
    except Exception:
        logger.exception("source-intelligence: case studies query failed")
        case_studies = []

    response = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "coverage": coverage,
        "source_accuracy": accuracy,
        "disagreements": disagreements,
        "case_studies": case_studies,
    }

    _cache["data"] = response
    _cache["timestamp"] = now

    return response
