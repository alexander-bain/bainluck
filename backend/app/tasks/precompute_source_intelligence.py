"""Precompute the Source-Intelligence ("Measure") page snapshot into Redis.

L2-129 / #206: the Measure page's four corpus queries (coverage, source accuracy,
disagreements, case studies) are heavy CTE scans over win_prob_snapshots. Running them
on the request path meant a statement-timeout produced an all-empty payload that the
route then CACHED for 6h — a blank page that healed only when the TTL expired.

This task moves those queries off the request path (the fair-fight pattern): it runs
each in its OWN session with a generous per-statement timeout, and writes the result to
Redis ONLY when the build is healthy. A degraded/empty build is never persisted, so the
last good snapshot (primary + stale key) keeps serving instead of a blank page.
"""

import json
import logging
from datetime import datetime, timezone

from sqlalchemy import text

logger = logging.getLogger(__name__)


async def _compute_source_intelligence():
    """Build the Source-Intelligence snapshot and store it in Redis.

    Mirrors ``_compute_fair_fight_comparison``: each corpus query runs in its own
    session with a 240s statement_timeout so a slow scan degrades to its empty
    fallback in isolation rather than aborting the whole task. The result is written
    to Redis only when it is non-degenerate — an all-empty build is NEVER cached
    (that is the exact anti-pattern L2-129 found)."""
    from app.routes.source_intelligence import (
        _EMPTY_COVERAGE,
        _EMPTY_DISAGREEMENTS,
        _REDIS_KEY,
        _REDIS_STALE_KEY,
        _REDIS_STALE_TTL,
        _is_degenerate_si,
        _query_case_studies,
        _query_coverage,
        _query_disagreements,
        _query_source_accuracy,
        CACHE_TTL,
    )
    from app.tasks.base import get_task_session
    from app.tasks.redis_state import get_redis_client

    async def _run_bounded(impl, label, empty):
        try:
            async with get_task_session() as db:
                await db.execute(text("SET LOCAL statement_timeout = '240s'"))
                return await impl(db), False
        except Exception:
            logger.exception("source-intelligence precompute: %s query failed", label)
            return empty, True

    coverage, d1 = await _run_bounded(_query_coverage, "coverage", dict(_EMPTY_COVERAGE))
    accuracy, d2 = await _run_bounded(_query_source_accuracy, "accuracy", [])
    disagreements, d3 = await _run_bounded(
        _query_disagreements, "disagreements", dict(_EMPTY_DISAGREEMENTS)
    )
    case_studies, d4 = await _run_bounded(_query_case_studies, "case_studies", [])

    degraded = d1 or d2 or d3 or d4
    response = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "coverage": coverage,
        "source_accuracy": accuracy,
        "disagreements": disagreements,
        "case_studies": case_studies,
    }

    # No-poison contract: never overwrite the warm snapshot with a degraded/empty
    # build. Leave the last good primary + stale keys in place; retry next cycle.
    if degraded or _is_degenerate_si(coverage, accuracy, disagreements, case_studies):
        logger.warning(
            "source-intelligence precompute degraded (degraded=%s) — NOT caching, "
            "keeping last good snapshot", degraded,
        )
        return {"status": "degraded", "cached": False}

    rc = get_redis_client()
    payload = json.dumps(response, default=str)
    rc.set(_REDIS_KEY, payload, ex=CACHE_TTL)
    rc.set(_REDIS_STALE_KEY, payload, ex=_REDIS_STALE_TTL)
    logger.info("Cached source-intelligence snapshot in Redis")
    return {
        "status": "ok",
        "total_events": coverage.get("total_events", 0),
        "case_studies": len(case_studies),
    }
