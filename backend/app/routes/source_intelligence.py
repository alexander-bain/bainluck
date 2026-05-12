"""Source Intelligence endpoint — public, cached for 6 hours.

Analyzes cross-source probability disagreements for completed sports events
and determines which source was closest to the actual outcome.
"""

import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import get_db

router = APIRouter()

_cache: dict = {"data": None, "timestamp": 0}
CACHE_TTL = 21600  # 6 hours

# Base filter used by all queries
_BASE_FILTER = """
    e.status IN ('completed', 'closed')
    AND e.home_score IS NOT NULL AND e.away_score IS NOT NULL
    AND e.home_score != e.away_score
"""


async def _query_coverage(db: AsyncSession) -> dict:
    """Query 1: Source coverage — events per source, overlap distribution."""

    by_source_sql = text(f"""
        SELECT
            s.key AS sport,
            COUNT(DISTINCT e.id) AS total,
            COUNT(DISTINCT e.id) FILTER (WHERE wp.source = 'betting') AS betting,
            COUNT(DISTINCT e.id) FILTER (WHERE wp.source = 'espn') AS espn,
            COUNT(DISTINCT e.id) FILTER (WHERE wp.source = 'stat_model') AS stat_model,
            COUNT(DISTINCT e.id) FILTER (WHERE wp.source = 'kalshi') AS kalshi,
            COUNT(DISTINCT e.id) FILTER (WHERE wp.source = 'polymarket') AS polymarket,
            COUNT(DISTINCT e.id) FILTER (WHERE wp.source = 'mlb') AS mlb
        FROM events e
        JOIN sports s ON s.id = e.sport_id
        LEFT JOIN (
            SELECT DISTINCT event_id, source FROM win_prob_snapshots
        ) wp ON wp.event_id = e.id
        WHERE {_BASE_FILTER}
        GROUP BY s.key
        ORDER BY COUNT(DISTINCT e.id) DESC
    """)

    overlap_sql = text(f"""
        SELECT source_count AS sources, COUNT(*) AS events
        FROM (
            SELECT wp.event_id, COUNT(DISTINCT wp.source) AS source_count
            FROM win_prob_snapshots wp
            JOIN events e ON e.id = wp.event_id
            WHERE {_BASE_FILTER}
            GROUP BY wp.event_id
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
    """Query 2: Per-source closing accuracy vs actual outcome."""

    sql = text(f"""
        SELECT
            wp.source,
            LEAST(FLOOR(wp.home_win_probability * 10)::int, 9) AS idx,
            COUNT(*) AS n,
            AVG(wp.home_win_probability::float) AS avg_prob,
            SUM(CASE WHEN e.home_score > e.away_score THEN 1 ELSE 0 END) AS winners,
            AVG(ABS(wp.home_win_probability::float
                - CASE WHEN e.home_score > e.away_score THEN 1.0 ELSE 0.0 END)) AS mae,
            AVG((wp.home_win_probability::float
                - CASE WHEN e.home_score > e.away_score THEN 1.0 ELSE 0.0 END)^2) AS brier
        FROM (
            SELECT DISTINCT ON (event_id, source)
                event_id, source, home_win_probability
            FROM win_prob_snapshots
            WHERE home_win_probability IS NOT NULL
              AND home_win_probability > 0 AND home_win_probability < 1
            ORDER BY event_id, source, captured_at DESC
        ) wp
        JOIN events e ON e.id = wp.event_id
        WHERE {_BASE_FILTER}
        GROUP BY wp.source, idx
        ORDER BY wp.source, idx
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
    """Queries 3+4: Pairwise disagreement analysis and frequency."""

    sql = text(f"""
        SET LOCAL statement_timeout = '30s';

        WITH bucketed AS (
            SELECT
                wp.event_id,
                wp.source,
                wp.home_win_probability,
                wp.captured_at,
                date_trunc('hour', wp.captured_at)
                    + INTERVAL '5 min' * FLOOR(
                        EXTRACT(EPOCH FROM wp.captured_at
                            - date_trunc('hour', wp.captured_at)) / 300
                    ) AS time_bucket
            FROM win_prob_snapshots wp
            JOIN events e ON e.id = wp.event_id
            WHERE {_BASE_FILTER}
              AND wp.home_win_probability IS NOT NULL
              AND wp.home_win_probability > 0
              AND wp.home_win_probability < 1
        ),
        deduped AS (
            SELECT DISTINCT ON (event_id, source, time_bucket)
                event_id, source, home_win_probability, time_bucket
            FROM bucketed
            ORDER BY event_id, source, time_bucket, captured_at DESC
        ),
        pairs AS (
            SELECT
                d1.event_id,
                d1.source AS source_a,
                d2.source AS source_b,
                d1.home_win_probability AS prob_a,
                d2.home_win_probability AS prob_b,
                ABS(d1.home_win_probability - d2.home_win_probability) AS divergence,
                d1.time_bucket
            FROM deduped d1
            JOIN deduped d2
                ON d1.event_id = d2.event_id
                AND d1.time_bucket = d2.time_bucket
                AND d1.source < d2.source
        ),
        with_outcome AS (
            SELECT
                p.*,
                (e.home_score > e.away_score) AS home_won,
                s.key AS sport,
                CASE WHEN p.time_bucket < e.commence_time
                     THEN 'pregame' ELSE 'live' END AS phase
            FROM pairs p
            JOIN events e ON e.id = p.event_id
            JOIN sports s ON s.id = e.sport_id
        )
        SELECT
            source_a, source_b, sport, phase,
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
        GROUP BY source_a, source_b, sport, phase
        ORDER BY source_a, source_b, sport, phase
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

        # Sport-level aggregation
        if r.sport not in sport_agg:
            sport_agg[r.sport] = {"sport": r.sport, "comparisons": 0, "disagree_5pp": 0}
        sport_agg[r.sport]["comparisons"] += r.comparisons
        sport_agg[r.sport]["disagree_5pp"] += r.disagree_5pp

        # Pairwise aggregation
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

        # Phase breakdown
        if r.phase not in pw["by_phase"]:
            pw["by_phase"][r.phase] = {"comparisons": 0, "a_closer": 0, "b_closer": 0}
        pw["by_phase"][r.phase]["comparisons"] += r.disagree_5pp
        pw["by_phase"][r.phase]["a_closer"] += r.a_closer
        pw["by_phase"][r.phase]["b_closer"] += r.b_closer

        # Sport breakdown
        if r.sport not in pw["by_sport"]:
            pw["by_sport"][r.sport] = {"comparisons": 0, "a_closer": 0, "b_closer": 0}
        pw["by_sport"][r.sport]["comparisons"] += r.disagree_5pp
        pw["by_sport"][r.sport]["a_closer"] += r.a_closer
        pw["by_sport"][r.sport]["b_closer"] += r.b_closer

    # Finalize pairwise
    pairwise_list = []
    for pw in pairwise.values():
        count = pw["count"]
        if count < 50:
            continue
        total_closer = pw["a_closer"] + pw["b_closer"]
        pairwise_list.append({
            "source_a": pw["source_a"],
            "source_b": pw["source_b"],
            "count": count,
            "avg_divergence": round(pw["divergence_sum"] / count, 4) if count else 0,
            "a_closer_pct": round(pw["a_closer"] / total_closer, 4) if total_closer else 0.5,
            "by_phase": {
                phase: {
                    "comparisons": v["comparisons"],
                    "a_closer_pct": round(
                        v["a_closer"] / (v["a_closer"] + v["b_closer"]), 4
                    ) if (v["a_closer"] + v["b_closer"]) else 0.5,
                }
                for phase, v in pw["by_phase"].items()
                if v["comparisons"] >= 20
            },
            "by_sport": {
                sport: {
                    "comparisons": v["comparisons"],
                    "a_closer_pct": round(
                        v["a_closer"] / (v["a_closer"] + v["b_closer"]), 4
                    ) if (v["a_closer"] + v["b_closer"]) else 0.5,
                }
                for sport, v in pw["by_sport"].items()
                if v["comparisons"] >= 20
            },
        })

    # Sport frequency
    by_sport = []
    for s in sport_agg.values():
        if s["comparisons"] >= 50:
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
    """Query 5: Top dramatic disagreements with full time-series."""

    # Find events with largest peak divergence across any source pair
    peak_sql = text(f"""
        SET LOCAL statement_timeout = '15s';

        WITH bucketed AS (
            SELECT
                wp.event_id,
                wp.source,
                wp.home_win_probability,
                wp.captured_at,
                date_trunc('hour', wp.captured_at)
                    + INTERVAL '5 min' * FLOOR(
                        EXTRACT(EPOCH FROM wp.captured_at
                            - date_trunc('hour', wp.captured_at)) / 300
                    ) AS time_bucket
            FROM win_prob_snapshots wp
            JOIN events e ON e.id = wp.event_id
            WHERE {_BASE_FILTER}
              AND wp.home_win_probability IS NOT NULL
              AND wp.home_win_probability > 0.02
              AND wp.home_win_probability < 0.98
        ),
        deduped AS (
            SELECT DISTINCT ON (event_id, source, time_bucket)
                event_id, source, home_win_probability, time_bucket
            FROM bucketed
            ORDER BY event_id, source, time_bucket, captured_at DESC
        ),
        event_peaks AS (
            SELECT
                d1.event_id,
                MAX(ABS(d1.home_win_probability - d2.home_win_probability)) AS max_div
            FROM deduped d1
            JOIN deduped d2
                ON d1.event_id = d2.event_id
                AND d1.time_bucket = d2.time_bucket
                AND d1.source < d2.source
            GROUP BY d1.event_id
            HAVING COUNT(DISTINCT d1.source) >= 3
        )
        SELECT
            ep.event_id,
            ep.max_div,
            e.home_team_name,
            e.away_team_name,
            s.key AS sport,
            e.home_score,
            e.away_score,
            e.commence_time
        FROM event_peaks ep
        JOIN events e ON e.id = ep.event_id
        JOIN sports s ON s.id = e.sport_id
        ORDER BY ep.max_div DESC
        LIMIT 5
    """)

    peak_result = await db.execute(peak_sql)
    peaks = peak_result.all()

    case_studies = []
    for p in peaks:
        # Fetch full time series for this event
        ts_sql = text("""
            SELECT source, captured_at, home_win_probability
            FROM win_prob_snapshots
            WHERE event_id = :eid
              AND home_win_probability IS NOT NULL
            ORDER BY captured_at
        """)
        ts_result = await db.execute(ts_sql, {"eid": p.event_id})
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

    coverage = await _query_coverage(db)
    accuracy = await _query_source_accuracy(db)
    disagreements = await _query_disagreements(db)
    case_studies = await _query_case_studies(db)

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
