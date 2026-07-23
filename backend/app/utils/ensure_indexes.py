"""#1197 (r259) — runtime CONCURRENTLY builder for the missing team-route indexes.

ROOT CAUSE of the 7-17.6s warm team route (NOT the rate limiter — /api/sports, same
middleware, is 0.4s): the team page's event lookup ORs four UNINDEXED columns —
``events.home_team_id``, ``away_team_id``, ``home_team_name``, ``away_team_name``
(none had an index) — so it full-seq-scans the large events table TWICE per request
(upcoming + recent). Indexing all four lets Postgres BitmapOr four index scans.

gotcha #31: we do NOT add these in an Alembic migration — a plain CREATE INDEX on
the actively-written events table takes an ACCESS EXCLUSIVE lock (blocks polling
writes; can stall the release), and CONCURRENTLY hangs the release phase. We build
them CONCURRENTLY at task runtime instead (a Celery worker has no release timeout;
CONCURRENTLY takes no exclusive lock), idempotently (IF NOT EXISTS), per-index
guarded so one failure never blocks the others.
"""
from __future__ import annotations

import logging

from sqlalchemy import text

logger = logging.getLogger(__name__)

# (index_name, "table (columns)") — the four team-route event lookups + a
# belt-and-suspenders on futures_outcomes.external_id (also built by the settled
# backfill; IF NOT EXISTS makes the overlap a no-op).
PERF_INDEXES = [
    ("ix_events_home_team_id", "events (home_team_id)"),
    ("ix_events_away_team_id", "events (away_team_id)"),
    ("ix_events_home_team_name", "events (home_team_name)"),
    ("ix_events_away_team_name", "events (away_team_name)"),
    ("ix_futures_outcomes_external_id", "futures_outcomes (external_id)"),
]


async def ensure_perf_indexes() -> dict:
    """Build each PERF_INDEXES entry CONCURRENTLY IF NOT EXISTS on its own
    autocommit connection. Returns {index_name: 'ok' | 'error: ...'}. Never raises
    — a failed index just persists its seq scan until the next run."""
    from app.tasks.base import _get_task_engine

    engine = _get_task_engine()
    results: dict[str, str] = {}
    try:
        for name, target in PERF_INDEXES:
            try:
                # CONCURRENTLY must run outside a transaction → AUTOCOMMIT.
                async with engine.connect() as conn:
                    conn = await conn.execution_options(isolation_level="AUTOCOMMIT")
                    await conn.execute(text(
                        f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {name} ON {target}"
                    ))
                results[name] = "ok"
                logger.info("ensure_perf_indexes: %s ready", name)
            except Exception as e:
                results[name] = f"error: {e}"
                logger.warning("ensure_perf_indexes: %s failed: %s", name, e)
    finally:
        await engine.dispose()
    return results
