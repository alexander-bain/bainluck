"""Source Intelligence endpoint — public, cached for 6 hours.

Analyzes cross-source probability disagreements for completed sports events
and determines which source was closest to the actual outcome.
"""

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

# Only analyze recent events to keep queries fast on Heroku (30s timeout)
_RECENCY = "e.commence_time > NOW() - INTERVAL '3 months'"

_BASE_FILTER = f"""
    e.status IN ('completed', 'closed')
    AND e.home_score IS NOT NULL AND e.away_score IS NOT NULL
    AND e.home_score != e.away_score
    AND {_RECENCY}
"""


async def _set_timeout(db: AsyncSession) -> None:
    await db.execute(text("SET LOCAL statement_timeout = '25s'"))


async def _query_coverage(db: AsyncSession) -> dict:
    """Query 1: Source coverage — events per source, overlap distribution."""

    by_source_sql = text(f"""
        SELECT
            s.key AS sport,
            COUNT(DISTINCT e.id) AS total,
            COUNT(DISTINCT e.id) FILTER (
                WHERE e.opening_home_probability IS NOT NULL
            ) AS betting,
            COUNT(DISTINCT e.id) FILTER (WHERE src = 'espn') AS espn,
            COUNT(DISTINCT e.id) FILTER (WHERE src = 'stat_model') AS stat_model,
            COUNT(DISTINCT e.id) FILTER (WHERE src = 'kalshi') AS kalshi,
            COUNT(DISTINCT e.id) FILTER (WHERE src = 'polymarket') AS polymarket,
            COUNT(DISTINCT e.id) FILTER (WHERE src = 'mlb') AS mlb
        FROM events e
        JOIN sports s ON s.id = e.sport_id
        LEFT JOIN LATERAL (
            SELECT DISTINCT source AS src
            FROM win_prob_snapshots wp
            WHERE wp.event_id = e.id
        ) wp ON true
        WHERE {_BASE_FILTER}
        GROUP BY s.key
        ORDER BY COUNT(DISTINCT e.id) DESC
    """)

    overlap_sql = text(f"""
        SELECT source_count AS sources, COUNT(*) AS events
        FROM (
            SELECT e.id,
                (SELECT COUNT(DISTINCT source) FROM win_prob_snapshots wp WHERE wp.event_id = e.id)
                + CASE WHEN e.opening_home_probability IS NOT NULL THEN 1 ELSE 0 END
                AS source_count
            FROM events e
            WHERE {_BASE_FILTER}
        ) sub
        WHERE source_count > 0
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
    """Query 2: Per-source closing accuracy vs actual outcome."""

    # win_prob_snapshots sources (espn, stat_model, kalshi, polymarket, mlb)
    # UNION with sportsbook data from events.opening_home_probability
    sql = text(f"""
        WITH wp_closing AS (
            SELECT DISTINCT ON (wp.event_id, wp.source)
                wp.event_id, wp.source, wp.home_win_probability
            FROM win_prob_snapshots wp
            JOIN events e ON e.id = wp.event_id
            WHERE {_BASE_FILTER}
              AND wp.home_win_probability IS NOT NULL
              AND wp.home_win_probability > 0
              AND wp.home_win_probability < 1
            ORDER BY wp.event_id, wp.source, wp.captured_at DESC
        ),
        all_closing AS (
            SELECT event_id, source, home_win_probability FROM wp_closing
            UNION ALL
            SELECT e.id, 'betting', e.opening_home_probability
            FROM events e
            WHERE {_BASE_FILTER}
              AND e.opening_home_probability IS NOT NULL
              AND e.opening_home_probability > 0
              AND e.opening_home_probability < 1
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
                - CASE WHEN e.home_score > e.away_score THEN 1.0 ELSE 0.0 END)^2) AS brier
        FROM all_closing c
        JOIN events e ON e.id = c.event_id
        GROUP BY c.source, idx
        ORDER BY c.source, idx
    """)

    result = await db.execute(sql)
    rows = result.all()

    sources: dict = {}
    for r in rows:
        src = r.source
        if src not in sources:
            sources[src] = {"source": src, "observations": 0,
                            "total_brier_num": 0.0, "total_mae_num": 0.0,
                            "buckets": []}
        sources[src]["observations"] += r.n
        sources[src]["total_brier_num"] += float(r.brier) * r.n
        sources[src]["total_mae_num"] += float(r.mae) * r.n
        sources[src]["buckets"].append({
            "idx": r.idx, "n": r.n,
            "avg_prob": round(float(r.avg_prob), 4),
            "actual": round(r.winners / r.n, 4) if r.n else 0,
        })

    out = []
    for s in sources.values():
        obs = s["observations"]
        out.append({
            "source": s["source"],
            "observations": obs,
            "brier": round(s["total_brier_num"] / obs, 4) if obs else 0,
            "mae": round(s["total_mae_num"] / obs, 4) if obs else 0,
            "buckets": s["buckets"],
        })
    return sorted(out, key=lambda x: x["brier"])


async def _query_disagreements(db: AsyncSession) -> dict:
    """Queries 3+4: Pairwise disagreement analysis and frequency.

    Uses per-event last-snapshot approach instead of full time-bucketed
    self-join to stay within Heroku's 30s timeout.
    """

    # Simpler approach: compare each source's LAST reading per event.
    # This avoids the expensive time-bucket self-join while still capturing
    # the core question: when sources' closing probabilities diverge,
    # which was closer to the truth?
    sql = text(f"""
        WITH wp_closing AS (
            SELECT DISTINCT ON (wp.event_id, wp.source)
                wp.event_id, wp.source, wp.home_win_probability
            FROM win_prob_snapshots wp
            JOIN events e ON e.id = wp.event_id
            WHERE {_BASE_FILTER}
              AND wp.home_win_probability IS NOT NULL
              AND wp.home_win_probability > 0
              AND wp.home_win_probability < 1
            ORDER BY wp.event_id, wp.source, wp.captured_at DESC
        ),
        closing AS (
            SELECT event_id, source, home_win_probability FROM wp_closing
            UNION ALL
            SELECT e.id, 'betting', e.opening_home_probability
            FROM events e
            WHERE {_BASE_FILTER}
              AND e.opening_home_probability IS NOT NULL
              AND e.opening_home_probability > 0
              AND e.opening_home_probability < 1
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
    """Query 5: Top sustained disagreements with full time-series.

    Finds events where sources held genuinely different views for sustained
    periods during live play. Filters out:
    - Transient spikes (single snapshots at 0% or 100%)
    - Pregame divergence (flat lines hours before game)
    - Stale prices (extreme values at game end)
    """

    # Use the median probability per source per event (robust to spikes)
    # and find events where two sources' medians diverge significantly.
    # Only consider live-game snapshots (after commence_time, before
    # completed_at or 4h after commence) with moderate probabilities (5-95%).
    peak_sql = text(f"""
        WITH live_snaps AS (
            SELECT
                wp.event_id, wp.source, wp.home_win_probability
            FROM win_prob_snapshots wp
            JOIN events e ON e.id = wp.event_id
            WHERE {_BASE_FILTER}
              AND wp.home_win_probability IS NOT NULL
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
            HAVING COUNT(*) >= 3
        ),
        event_divergence AS (
            SELECT
                s1.event_id,
                s1.source AS source_a,
                s2.source AS source_b,
                ABS(s1.median_prob - s2.median_prob) AS median_div,
                GREATEST(s1.snap_count, s2.snap_count) AS max_snaps
            FROM source_medians s1
            JOIN source_medians s2
                ON s1.event_id = s2.event_id
                AND s1.source < s2.source
        ),
        ranked AS (
            SELECT
                event_id,
                MAX(median_div) AS max_div,
                MAX(max_snaps) AS richness
            FROM event_divergence
            WHERE median_div > 0.08
            GROUP BY event_id
            HAVING COUNT(DISTINCT source_a) + COUNT(DISTINCT source_b) >= 3
            ORDER BY MAX(median_div) DESC
            LIMIT 20
        )
        SELECT
            r.event_id,
            r.max_div,
            r.richness,
            e.home_team_name,
            e.away_team_name,
            s.key AS sport,
            e.home_score,
            e.away_score,
            e.commence_time,
            e.completed_at
        FROM ranked r
        JOIN events e ON e.id = r.event_id
        JOIN sports s ON s.id = e.sport_id
        ORDER BY r.max_div DESC
    """)

    peak_result = await db.execute(peak_sql)
    peaks = peak_result.all()

    case_studies = []
    for p in peaks[:5]:
        # Only fetch live-game snapshots for the chart
        ts_sql = text("""
            SELECT source, captured_at, home_win_probability
            FROM win_prob_snapshots
            WHERE event_id = :eid
              AND home_win_probability IS NOT NULL
              AND captured_at >= :start
              AND captured_at <= :end
            ORDER BY captured_at
        """)
        game_end = p.completed_at or (
            p.commence_time + timedelta(hours=4)
        ) if p.commence_time else None
        if not p.commence_time or not game_end:
            continue

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

        # Skip if fewer than 2 sources have data
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


@router.get("/source-intelligence")
async def source_intelligence(db: AsyncSession = Depends(get_db)):
    """Cross-source disagreement analysis for the /source-intelligence page."""

    now = time.time()
    if _cache["data"] and (now - _cache["timestamp"]) < CACHE_TTL:
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
