"""Precompute the backfill-progress endpoint's heavy census and cache in Redis.

Queue #179 (Issue #1052): "#1052 unmeasurable" — this task builds the measurement.
It computes the two expensive tiles that a request-time endpoint cannot afford
(both time out under the ~15s db-query statement limit on production volumes):

  (a) candlestick/snapshot DENSITY — resolved outcomes with >=15 history points
      vs total, sampled per source and bucketed by settlement month, plus the
      post-Jul-2 "success cohort" and the June freeze window called out
      separately; and
  (b) the JUNE-GAP recovery ledger — freeze-window (Jun 3 - Jul 2) Kalshi markets
      counted honestly as recovered vs pending vs (gotcha #35) permanently
      aged-out.

The cheap/live tiles — backfill_winners phase throughput and worker load — are
read directly by the GET endpoint (they are near-instant) and are NOT computed
here.

Design mirrors precompute_backfill_winners_status.py: heavy SQL runs on the
background Celery worker (which does not carry the endpoint's short statement
timeout) and the JSON is served instantly from Redis.  Every heavy query is
sampled + bounded + wrapped so a single slow query degrades one tile instead of
breaking the whole endpoint (gotcha: never let a census OOM/timeout — see the
calibration #899/#907 starvation history).
"""

import json
import logging
from datetime import date, datetime, timezone

from sqlalchemy import text

logger = logging.getLogger(__name__)

CACHE_KEY = "bainluck:backfill_progress"
CACHE_TTL = 1800  # 30 min — task runs every 15 min so always fresh

# The freeze window (#995 Kalshi create-freeze; gotcha #35).
FREEZE_START = "2026-06-03"
FREEZE_END = "2026-07-02"
# The "cruising on autopilot" success cohort: everything settled after the freeze.
SUCCESS_COHORT_START = "2026-07-02"
# Density is measured over the trailing window (covers June freeze + July cohort).
DENSITY_SINCE = "2026-06-01"
# Sampling fraction for the per-outcome snapshot-count probes.  Percentages are
# what the tile reports; the fraction only bounds probe count so the query stays
# well under a minute even as the resolved population grows.
DENSITY_SAMPLE_FRAC = 0.05
# Minimum history points for a resolved outcome to count as "densely captured".
DENSE_POINTS = 15


async def _precompute_backfill_progress() -> dict:
    """Run the heavy density + June-ledger census and cache the result."""
    from app.tasks.base import get_task_session
    from app.tasks.redis_state import get_redis_client

    stats: dict = {"status": "ok", "errors": []}
    # asyncpg requires date/datetime objects (not strings) for timestamptz binds.
    _freeze_start = date.fromisoformat(FREEZE_START)
    _freeze_end = date.fromisoformat(FREEZE_END)
    _cohort_start = date.fromisoformat(SUCCESS_COHORT_START)
    _density_since = date.fromisoformat(DENSITY_SINCE)
    response: dict = {
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "freeze_window": {"start": FREEZE_START, "end": FREEZE_END},
        "success_cohort_start": SUCCESS_COHORT_START,
    }

    try:
        async with get_task_session() as session:
            # Give the heavy sampled query room; the worker session does not
            # inherit the endpoint's short statement timeout.
            try:
                await session.execute(text("SET LOCAL statement_timeout = '150s'"))
            except Exception:
                pass

            # ── (a) Snapshot DENSITY by source × settlement month ───────────
            # Sampled: random()<frac is evaluated during the scan (no full sort),
            # then a per-outcome index probe on ix_futures_odds_snapshots_outcome_id.
            try:
                dens = await session.execute(text("""
                    WITH ro AS (
                        SELECT fo.id AS oid, fm.source AS source,
                               to_char(fm.resolution_date, 'YYYY-MM') AS mon,
                               fo.calibration_probability AS cp
                        FROM futures_outcomes fo
                        JOIN futures_markets fm ON fm.id = fo.market_id
                        WHERE fm.status = 'resolved'
                          AND fm.resolution_date >= :since
                          AND random() < :frac
                    ),
                    os AS (
                        SELECT ro.source, ro.mon, ro.cp,
                               (SELECT COUNT(*) FROM futures_odds_snapshots s
                                WHERE s.outcome_id = ro.oid) AS snaps
                        FROM ro
                    )
                    SELECT source, mon,
                           COUNT(*) AS sampled,
                           COUNT(*) FILTER (WHERE snaps >= :dense) AS ge_dense,
                           COUNT(*) FILTER (WHERE snaps >= 1) AS any_snap,
                           COUNT(*) FILTER (WHERE cp IS NOT NULL) AS has_cal,
                           ROUND(AVG(snaps)::numeric, 1) AS avg_snaps
                    FROM os
                    GROUP BY source, mon
                    ORDER BY mon DESC, source
                """), {"since": _density_since, "frac": DENSITY_SAMPLE_FRAC,
                       "dense": DENSE_POINTS})
                by_month = []
                for r in dens.all():
                    sampled = r.sampled or 0
                    by_month.append({
                        "source": r.source,
                        "settlement_month": r.mon,
                        "sampled_resolved": sampled,
                        "dense_ge15_pct": round(100.0 * (r.ge_dense or 0) / max(sampled, 1), 1),
                        "any_snapshot_pct": round(100.0 * (r.any_snap or 0) / max(sampled, 1), 1),
                        "calibration_prob_pct": round(100.0 * (r.has_cal or 0) / max(sampled, 1), 1),
                        "avg_snapshots": float(r.avg_snaps) if r.avg_snaps is not None else 0.0,
                    })
                response["density_by_month"] = {
                    "since": DENSITY_SINCE,
                    "sampled": True,
                    "sample_frac": DENSITY_SAMPLE_FRAC,
                    "dense_threshold_points": DENSE_POINTS,
                    "by_source_month": by_month,
                }
            except Exception as e:  # degrade this tile only
                response["density_by_month"] = {"error": str(e)[:300]}
                stats["errors"].append("density: " + str(e)[:200])

            # ── (a') SUCCESS COHORT — settled after the freeze (the SLA target)
            # This is the number Alex's "cruising on autopilot" question turns on:
            # of resolved outcomes settled after Jul-2, how many carry a
            # calibration_probability AND >=15 history points.
            try:
                coh = await session.execute(text("""
                    WITH ro AS (
                        SELECT fo.id AS oid, fm.source AS source,
                               fo.calibration_probability AS cp,
                               fo.resolution_source AS rs
                        FROM futures_outcomes fo
                        JOIN futures_markets fm ON fm.id = fo.market_id
                        WHERE fm.status = 'resolved'
                          AND fm.resolution_date >= :since
                          AND random() < :frac
                    ),
                    os AS (
                        SELECT ro.source, ro.cp, ro.rs,
                               (SELECT COUNT(*) FROM futures_odds_snapshots s
                                WHERE s.outcome_id = ro.oid) AS snaps
                        FROM ro
                    )
                    SELECT source,
                           COUNT(*) AS sampled,
                           COUNT(*) FILTER (WHERE cp IS NOT NULL) AS has_cal,
                           COUNT(*) FILTER (WHERE snaps >= :dense) AS ge_dense,
                           COUNT(*) FILTER (WHERE cp IS NOT NULL AND snaps >= :dense) AS cal_and_dense,
                           COUNT(*) FILTER (WHERE rs IN
                               ('api_settlement','game_score','box_score')) AS authoritative
                    FROM os
                    GROUP BY source
                    ORDER BY sampled DESC
                """), {"since": _cohort_start, "frac": DENSITY_SAMPLE_FRAC,
                       "dense": DENSE_POINTS})
                cohort = []
                for r in coh.all():
                    sampled = r.sampled or 0
                    cohort.append({
                        "source": r.source,
                        "sampled_resolved": sampled,
                        "calibration_prob_pct": round(100.0 * (r.has_cal or 0) / max(sampled, 1), 1),
                        "dense_ge15_pct": round(100.0 * (r.ge_dense or 0) / max(sampled, 1), 1),
                        "sla_met_pct": round(100.0 * (r.cal_and_dense or 0) / max(sampled, 1), 1),
                        "authoritative_pct": round(100.0 * (r.authoritative or 0) / max(sampled, 1), 1),
                    })
                response["success_cohort"] = {
                    "since": SUCCESS_COHORT_START,
                    "sampled": True,
                    "sample_frac": DENSITY_SAMPLE_FRAC,
                    "sla_definition": "calibration_probability IS NOT NULL AND >=15 history points",
                    "by_source": cohort,
                }
            except Exception as e:
                response["success_cohort"] = {"error": str(e)[:300]}
                stats["errors"].append("cohort: " + str(e)[:200])

            # ── (b) JUNE-GAP recovery ledger (Kalshi, freeze window) ────────
            # Two honest cuts:
            #   created_in_window  = markets CREATED during the freeze that made it
            #       into the DB at all (creation was throttled — small vs normal).
            #   settled_in_window  = markets whose resolution_date falls in the
            #       window, split by authoritative resolution vs guessed/none.
            # aged_out (gotcha #35): markets that opened AND settled inside the
            # freeze and were never ingested cannot be counted directly (they are
            # not in the DB); the gap-creation backfill recovers what it can and
            # the remainder is a permanent, honestly-acknowledged loss.
            try:
                created = await session.execute(text("""
                    SELECT COUNT(*) AS total,
                           COUNT(*) FILTER (WHERE fm.status = 'resolved') AS resolved,
                           COUNT(*) FILTER (WHERE fm.status != 'resolved') AS pending
                    FROM futures_markets fm
                    WHERE fm.source = 'kalshi'
                      AND fm.created_at >= :s AND fm.created_at < :e
                """), {"s": _freeze_start, "e": _freeze_end})
                c = created.one()

                settled = await session.execute(text("""
                    SELECT COUNT(*) AS total,
                           COUNT(*) FILTER (WHERE fm.status = 'resolved') AS resolved,
                           COUNT(*) FILTER (WHERE EXISTS (
                               SELECT 1 FROM futures_outcomes fo
                               WHERE fo.market_id = fm.id
                                 AND fo.resolution_source IN
                                     ('api_settlement','game_score','box_score')
                           )) AS authoritative
                    FROM futures_markets fm
                    WHERE fm.source = 'kalshi'
                      AND fm.resolution_date >= :s AND fm.resolution_date < :e
                """), {"s": _freeze_start, "e": _freeze_end})
                s = settled.one()

                created_total = c.total or 0
                created_resolved = c.resolved or 0
                settled_total = s.total or 0
                settled_auth = s.authoritative or 0
                response["june_gap_ledger"] = {
                    "window": f"{FREEZE_START}..{FREEZE_END}",
                    "kalshi_created_in_window": {
                        "total": created_total,
                        "recovered_resolved": created_resolved,
                        "pending": c.pending or 0,
                        "recovered_pct": round(100.0 * created_resolved / max(created_total, 1), 1),
                    },
                    "kalshi_settled_in_window": {
                        "total": settled_total,
                        "resolved": s.resolved or 0,
                        "authoritative": settled_auth,
                        "authoritative_pct": round(100.0 * settled_auth / max(settled_total, 1), 1),
                    },
                    "aged_out_note": (
                        "Markets that opened AND settled entirely inside the freeze "
                        "and were never ingested are not in the DB and cannot be "
                        "counted directly (gotcha #35: Kalshi market data ages out "
                        "of the API after ~2-3 months). What remains here is what "
                        "was captured; the gap-creation backfill recovers the "
                        "reachable remainder and the rest is a permanent loss."
                    ),
                }
            except Exception as e:
                response["june_gap_ledger"] = {"error": str(e)[:300]}
                stats["errors"].append("june_ledger: " + str(e)[:200])

            # ── Write to Redis ──────────────────────────────────────────────
            rc = get_redis_client()
            rc.setex(CACHE_KEY, CACHE_TTL, json.dumps(response, default=str))
            stats["cached"] = True
            logger.info("Precomputed backfill-progress cache (errors=%d)", len(stats["errors"]))

    except Exception as e:
        stats["status"] = "error"
        stats["errors"].append(str(e)[:500])
        logger.error("Failed to precompute backfill-progress: %s", e)

    return stats
